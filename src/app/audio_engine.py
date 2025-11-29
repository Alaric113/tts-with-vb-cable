# -*- coding: utf-8 -*-
# 檔案: audio_engine.py
# 功用: 封裝所有與音訊處理相關的核心邏輯，將 TTS 合成與播放功能抽象化。
#      - 定義 AudioEngine 類別，作為音訊處理的主要介面。
#      - TTS 引擎管理: 支援並切換 edge-tts、pyttsx3 和 Sherpa-ONNX。
#      - 語音資源載入: 非同步載入可用語音，並初始化 TTS 引擎。
#      - 設備管理: 查詢、載入並管理系統中的音訊輸出設備。
#      - TTS 合成: 根據選擇的引擎，將文字合成為音訊。
#      - 音訊播放: 將合成的音訊播放到指定的一或多個輸出設備。
#      - 多設備播放: 實現音訊同時串流到主輸出和一個額外的「聆聽」設備。

import os
import asyncio
import threading
import tempfile
import shutil # NEW import for file operations
import numpy as np
import sounddevice as sd
from scipy.signal import resample # NEW import
from datetime import datetime
import subprocess
import queue
import hashlib
from pathlib import Path
import logging

# 延遲匯入，避免在 ffmpeg 路徑設定前就發出警告
pyttsx3 = None
AudioSegment = None
sherpa_onnx = None
soundfile = None

from ..utils.deps import (DEFAULT_EDGE_VOICE, ENGINE_EDGE, ENGINE_PYTTX3,
                          CABLE_INPUT_HINT, TTS_MODELS_DIR)
from .model_manager import PREDEFINED_MODELS

class AudioEngine:
    def __init__(self, log_cb, audio_status_queue, startupinfo=None):
        self.log = log_cb
        self.audio_status_queue = audio_status_queue
        self.startupinfo = startupinfo
        self.app_controller = None # 回傳給 app 的參照，用於存取其他 app 屬性

        self.current_engine = ENGINE_PYTTX3 # 預設改為 pyttsx3 (原 Sherpa-ONNX 已拆分)
        self.current_voice = "default"
        self.pyttsx3_voice_id = None
        self.sherpa_speaker_id = 0
        self.sherpa_speakers = []

        self.tts_rate = 1.0 # For Sherpa, 1.0 is default speed (changed from 0.5)
        self.tts_volume = 1.0
        self.tts_pitch = 0

        self.enable_listen_to_self = False
        self.listen_device_name = "Default"
        self.listen_volume = 1.0

        self._pyttsx3_engine = None
        self._pyttsx3_voices = []
        self._edge_voices = []
        self._sherpa_tts = None
        self.sherpa_model_id = None
        self._temp_model_dir = None # To hold the TemporaryDirectory object for Sherpa-ONNX models

        self._local_output_devices = {}
        self._listen_devices = {}

        self.local_output_device_name = "Default"
        self.cable_is_present = False

        self.play_queue = queue.Queue()
        self.worker_thread = None

        self._audio_cache = {} # Initialize audio cache for quick phrases

    def start(self):
        self.worker_thread = threading.Thread(target=self._audio_worker, daemon=True)
        self.worker_thread.start()

    def stop(self):
        self.log("正在停止音訊引擎...", "DEBUG")
        self.play_queue.put(None)
        self.log("音訊引擎已停止。")

    def _audio_worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.log("音訊工作執行緒已啟動。", "DEBUG")

        while True:
            try:
                item = self.play_queue.get()
                if item is None:
                    self.log("音訊工作執行緒收到停止信號。", "DEBUG")
                    break
                self._process_and_play_text(item, loop, self.startupinfo)
            except Exception as e:
                self.log(f"音訊工作執行緒發生錯誤: {e}", "ERROR")
        self.log("音訊工作執行緒已結束。", "DEBUG")

    # ---------- 初始化 & 資源 ----------
    def _lazy_import(self):
        """Lazy import of heavy modules."""
        global pyttsx3, AudioSegment, sherpa_onnx, soundfile
        if pyttsx3 is None:
            try:
                import pyttsx3
            except ImportError:
                self.log("缺少 'pyttsx3' 模組，相關功能將無法使用。", "WARNING")
        if AudioSegment is None:
            try:
                from pydub import AudioSegment
            except ImportError:
                 self.log("缺少 'pydub' 模組，部分功能可能受限。", "WARNING")
        if sherpa_onnx is None:
            try:
                import sherpa_onnx
                import soundfile
            except ImportError:
                self.log("缺少 'sherpa-onnx' 或 'soundfile' 模組，Sherpa-ONNX 引擎將無法使用。", "ERROR")
                return False
        return True

    def init_pyttsx3(self):
        if not self._lazy_import(): return
        if pyttsx3 is None: return

        try:
            temp_engine = pyttsx3.init()
            self._pyttsx3_voices = temp_engine.getProperty("voices")
            temp_engine.stop()
        except Exception as e:
            self.log(f"初始化 pyttsx3 失敗: {e}", "ERROR")

    async def load_edge_voices(self):
        try:
            import edge_tts
            vm = await edge_tts.VoicesManager.create()
            self._edge_voices = [v for v in vm.voices if v.get("Locale", "").startswith("zh-")]
        except Exception as e:
            self.log(f"Edge TTS 載入失敗: {e}", "WARN")

    def _init_sherpa_onnx_runtime(self):
        # This method only ensures sherpa_onnx can be imported.
        # Actual model loading happens in _load_sherpa_onnx_voice.
        if not self._lazy_import() or sherpa_onnx is None:
            return False
        return True

    def _load_sherpa_onnx_voice(self, model_id: str) -> bool:
        if not self._init_sherpa_onnx_runtime(): # Ensure runtime is initialized
            return False

        if model_id not in PREDEFINED_MODELS:
            self.log(f"未定義的模型 ID: {model_id}", "ERROR")
            return False

        model_config = PREDEFINED_MODELS[model_id]
        original_model_dir = Path(TTS_MODELS_DIR) / model_id
        
        # 檢查所有模型檔案是否存在 (原始位置)
        required_files_original = [original_model_dir / fname for fname in model_config["file_names"]]
        for f in required_files_original:
            if not f.exists():
                self.log(f"模型 '{model_id}' 缺少以下檔案：{str(f)}", "WARNING")
                self.log(f"模型 '{model_id}' 檔案不完整。", "WARNING")
                self._sherpa_tts = None
                self.sherpa_model_id = None
                return False

        # --- NEW: Create a temporary directory with ASCII-safe path and copy model files ---
        # Clean up previous temporary directory if it exists
        if self._temp_model_dir is not None:
            self._temp_model_dir.cleanup()
            self._temp_model_dir = None

        try:
            self._temp_model_dir = tempfile.TemporaryDirectory(prefix=f"sherpa_onnx_{model_id}_")
            temp_model_path = Path(self._temp_model_dir.name)
            self.log(f"DEBUG: 建立臨時模型目錄: {temp_model_path}", "DEBUG")

            # Copy all required files/directories to the temporary location
            for fname in model_config["file_names"]:
                src_path = original_model_dir / fname
                dst_path = temp_model_path / fname
                if src_path.is_dir():
                    shutil.copytree(src_path, dst_path)
                else:
                    shutil.copy2(src_path, dst_path)
                self.log(f"DEBUG: 複製 '{src_path}' 到 '{dst_path}'", "DEBUG")

            # Update paths to point to the temporary directory
            model_dir = temp_model_path

            # Dynamically find the .onnx file from model_config["file_names"]
            onnx_filename = ""
            for fname in model_config["file_names"]:
                if fname.endswith(".onnx"):
                    onnx_filename = fname
                    break
            if not onnx_filename:
                self.log(f"模型 '{model_id}' 的配置中未找到 .onnx 檔案。", "ERROR")
                self._sherpa_tts = None
                self.sherpa_model_id = None
                return False
            vits_model = str(model_dir / onnx_filename)

            glados_data_dir = "" # Initialize data_dir for glados model
            # Special handling for glados model, which requires data_dir
            if model_id == "vits-piper-en_US-glados":
                glados_data_dir = str(model_dir / "espeak-ng-data")

            lexicon_file = model_dir / "lexicon.txt"
            lexicon = str(lexicon_file) if lexicon_file.exists() else "" # Make lexicon optional
            tokens = str(model_dir / "tokens.txt")
            
            # 找到所有 rule FST 檔案
            rules_files = [str(f) for f in model_dir.glob("*.fst")]

            self.log(f"DEBUG: Sherpa-ONNX 載入參數 - model_id: {model_id}", "DEBUG")
            self.log(f"DEBUG: vits_model (temp): {vits_model}", "DEBUG")
            self.log(f"DEBUG: lexicon (temp): {lexicon}", "DEBUG")
            self.log(f"DEBUG: tokens (temp): {tokens}", "DEBUG")
            self.log(f"DEBUG: glados_data_dir (temp): {glados_data_dir}", "DEBUG")
            self.log(f"DEBUG: rules_files (temp): {rules_files}", "DEBUG")

            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=vits_model,
                        lexicon=lexicon,
                        tokens=tokens,
                        data_dir=glados_data_dir # Pass data_dir for glados
                    ),
                    num_threads=2,
                    provider="cpu",
                ),
                rule_fsts=','.join(rules_files) if rules_files else ""
            )
            self.log(f"DEBUG: tts_config constructed. Attempting to instantiate sherpa_onnx.OfflineTts...", "DEBUG")
            self._sherpa_tts = sherpa_onnx.OfflineTts(tts_config)
            self.log(f"DEBUG: sherpa_onnx.OfflineTts instantiated successfully.", "DEBUG")
            self.sherpa_speakers = [f"Speaker {i}" for i in range(self._sherpa_tts.num_speakers)]
            self.sherpa_model_id = model_id
            
            # Load model-specific rate and volume from config, fallback to default_rate/volume from model_config
            # Note: app_controller is LocalTTSPlayer, which has the config manager
            self.tts_rate = self.app_controller.config.get_model_setting(model_id, "rate", model_config.get("default_rate", 1.0))
            self.tts_volume = self.app_controller.config.get_model_setting(model_id, "volume", model_config.get("default_volume", 1.0))
            self.log(f"DEBUG: _load_sherpa_onnx_voice: Loaded model-specific TTS Rate: {self.tts_rate}, Volume: {self.tts_volume}", "DEBUG")

            self.log(f"DEBUG: Sherpa-ONNX 引擎已成功載入模型 '{model_id}'。設定速率: {self.tts_rate}, 音量: {self.tts_volume}", "DEBUG")
            return True
        except Exception as e:
            self.log(f"載入 Sherpa-ONNX 模型失敗: {e}", "ERROR")
            self._sherpa_tts = None
            self.sherpa_model_id = None
            # Ensure cleanup if an error occurs during loading after copying
            if self._temp_model_dir is not None:
                self._temp_model_dir.cleanup()
                self._temp_model_dir = None
            return False

    def query_devices(self):
        return sd.query_devices()

    def load_devices(self):
        try:
            devices = sd.query_devices()
            all_device_names_upper = [d['name'].upper() for d in devices]
            output_devices = [d for d in devices if d['max_output_channels'] > 0]

            self._listen_devices = {d['name']: d['index'] for d in output_devices}
            self._local_output_devices = {d['name']: d['index'] for d in output_devices}

            self.cable_is_present = any(CABLE_INPUT_HINT.upper() in name for name in all_device_names_upper)

            best_candidate = None
            for d in output_devices:
                if "CABLE Input".upper() in d['name'].upper():
                    best_candidate = d['name']
                    break
            if not best_candidate:
                for d in output_devices:
                    if "VB-AUDIO" in d['name'].upper() and "OUTPUT" not in d['name'].upper():
                        best_candidate = d['name']
                        break
            if best_candidate:
                self.local_output_device_name = best_candidate
                self.log(f"已自動綁定輸出設備：{self.local_output_device_name}", "DEBUG")

        except Exception as e:
            self.log(f"取得音效卡失敗: {e}", "ERROR")

    # ---------- 參數設定 ----------
    def set_engine(self, engine: str):
        self.current_engine = engine

    def set_current_voice(self, voice_name: str):
        self.current_voice = voice_name or "default"
        if self.app_controller and self.current_engine in self.app_controller.get_sherpa_onnx_engines() and self.sherpa_speakers:
            try:
                # voice_name is like "Speaker 1"
                self.sherpa_speaker_id = int(voice_name.split(" ")[-1])
            except:
                self.sherpa_speaker_id = 0

    def set_pyttsx3_voice_by_name(self, name: str):
        if not self._pyttsx3_voices: return
        for v in self._pyttsx3_voices:
            if v.name == name:
                self.pyttsx3_voice_id = v.id
                break

    def set_rate_volume(self, rate, volume):
        self.log(f"DEBUG: set_rate_volume: Received rate={rate}, volume={volume}", "DEBUG")
        if self.app_controller and self.current_engine in self.app_controller.get_sherpa_onnx_engines():
            self.tts_rate = float(rate) # Speed for sherpa
        else:
            self.tts_rate = int(rate) # Rate for edge/pyttsx3
        self.tts_volume = float(volume)
        self.log(f"DEBUG: set_rate_volume: Set self.tts_rate={self.tts_rate}, self.tts_volume={self.tts_volume}", "DEBUG")

    def apply_listen_config(self, config: dict):
        self.enable_listen_to_self = config.get("enable_listen_to_self", False)
        self.listen_device_name = config.get("listen_device_name", "Default")
        self.listen_volume = config.get("listen_volume", 1.0)

    def set_listen_config(self, enable: bool, device_name: str, volume: float):
        self.enable_listen_to_self = bool(enable)
        self.listen_device_name = device_name
        self.listen_volume = float(volume)

    def cache_phrase(self, phrase_info: dict):
        text = phrase_info.get("text", "").strip()
        if not text:
            return

        # Generate a unique key for the cache based on text and current TTS settings
        cache_key_components = [
            text,
            self.current_engine,
            self.current_voice,
            str(self.tts_rate),
            str(self.tts_volume),
            str(self.tts_pitch)
        ]
        cache_key = hashlib.md5('+'.join(cache_key_components).encode('utf-8')).hexdigest()

        # Check if already cached
        if cache_key in self._audio_cache:
            return

        self.log(f"Caching phrase: '{text[:20]}...' (Engine: {self.current_engine})", "DEBUG")

        samples = None
        sample_rate = None
        
        loop = asyncio.new_event_loop() # Create a new event loop for async operations in this thread
        asyncio.set_event_loop(loop)

        try:
            if self.app_controller and self.current_engine in self.app_controller.get_sherpa_onnx_engines():
                samples, sample_rate = self._synth_sherpa_onnx(text)
            elif self.current_engine == ENGINE_EDGE:
                samples, sample_rate = loop.run_until_complete(self._synth_edge_to_memory(text))
            elif self.current_engine == ENGINE_PYTTX3:
                samples, sample_rate = self._synth_pyttsx3_to_memory(text)
            
            if samples is not None and sample_rate is not None:
                self._audio_cache[cache_key] = (samples, sample_rate)
                self.log(f"Phrase cached successfully: '{text[:20]}...'", "DEBUG")
            else:
                self.log(f"Failed to cache phrase: '{text[:20]}...' (synthesis failed)", "WARNING")
        except Exception as e:
            self.log(f"Error caching phrase '{text[:20]}...': {e}", "ERROR")
        finally:
            loop.close()

    # ---------- 取得資訊 ----------
    def get_voice_names(self):
        if self.current_engine == ENGINE_EDGE:
            return [DEFAULT_EDGE_VOICE] + [v["ShortName"] for v in self._edge_voices]
        elif self.current_engine == ENGINE_PYTTX3:
            return [v.name for v in self._pyttsx3_voices] if self._pyttsx3_voices else ["default"]
        elif self.current_engine in self.app_controller.get_sherpa_onnx_engines(): # Updated condition
            return [self.current_engine] # The engine itself is the "voice"
        return ["default"]

    def get_listen_device_names(self):
        return list(self._listen_devices.keys()) if self._listen_devices else ["Default (無可用設備)"]

    def get_output_device_names(self):
        return list(self._local_output_devices.keys()) if self._local_output_devices else ["Default (無可用設備)"]

    def get_all_edge_voices(self):
        return self._edge_voices

    # ---------- 合成 ----------
    def _synth_sherpa_onnx(self, text):
        if not self._sherpa_tts:
            self.log("Sherpa-ONNX 引擎未初始化，無法合成。", "ERROR")
            return None, None
        try:
            self.log(f"DEBUG: _synth_sherpa_onnx: Generating speech with speed={self.tts_rate}, speaker_id={self.sherpa_speaker_id}", "DEBUG")
            audio = self._sherpa_tts.generate(text, sid=self.sherpa_speaker_id, speed=self.tts_rate)
            samples = np.array(audio.samples, dtype=np.float32)
            return samples, audio.sample_rate
        except Exception as e:
            self.log(f"Sherpa-ONNX 合成失敗: {e}", "ERROR")
            return None, None

    async def _synth_edge_to_file(self, text, path, **kwargs):
        import edge_tts
        # ... (logic from old file, simplified)
        rate_param = f"{int(round((self.tts_rate - 175) * (40 / 75))):+d}%"
        volume_param = f"{int((self.tts_volume - 1.0) * 100):+d}%"
        pitch_param = f"{int(self.tts_pitch):+d}Hz"
        comm = edge_tts.Communicate(text, self.current_voice, rate=rate_param, volume=volume_param, pitch=pitch_param)
        await comm.save(path)
        return True

    async def _synth_edge_to_memory(self, text):
        import edge_tts
        global AudioSegment # Ensure pydub is imported
        if AudioSegment is None: self._lazy_import()

        rate_param = f"{int(round((self.tts_rate - 175) * (40 / 75))):+d}%"
        volume_param = f"{int((self.tts_volume - 1.0) * 100):+d}%"
        pitch_param = f"{int(self.tts_pitch):+d}Hz"
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            try:
                comm = edge_tts.Communicate(text, self.current_voice, rate=rate_param, volume=volume_param, pitch=pitch_param)
                await comm.save(tmp_file.name)
                audio = AudioSegment.from_mp3(tmp_file.name)
                samples = self._audiosegment_to_float32_numpy(audio)
                sample_rate = audio.frame_rate
                return samples, sample_rate
            except Exception as e:
                self.log(f"Edge TTS 合成到記憶體失敗: {e}", "ERROR")
                return None, None
            finally:
                os.remove(tmp_file.name)

    def _synth_pyttsx3_to_file(self, text, path):
        if pyttsx3 is None: return False
        engine = None
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", self.tts_rate)
            engine.setProperty("volume", self.tts_volume)
            if self.pyttsx3_voice_id:
                engine.setProperty("voice", self.pyttsx3_voice_id)
            engine.save_to_file(text, path)
            engine.runAndWait()
            return True
        finally:
            if engine: engine.stop()

    def _synth_pyttsx3_to_memory(self, text):
        global pyttsx3, AudioSegment # Ensure modules are imported
        if pyttsx3 is None or AudioSegment is None: self._lazy_import()
        if pyttsx3 is None or AudioSegment is None: return None, None

        engine = None
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            try:
                engine = pyttsx3.init()
                engine.setProperty("rate", self.tts_rate)
                engine.setProperty("volume", self.tts_volume)
                if self.pyttsx3_voice_id:
                    engine.setProperty("voice", self.pyttsx3_voice_id)
                engine.save_to_file(text, tmp_file.name)
                engine.runAndWait()
                
                audio = AudioSegment.from_wav(tmp_file.name)
                samples = self._audiosegment_to_float32_numpy(audio)
                sample_rate = audio.frame_rate
                return samples, sample_rate
            except Exception as e:
                self.log(f"pyttsx3 合成到記憶體失敗: {e}", "ERROR")
                return None, None
            finally:
                if engine: engine.stop()
                os.remove(tmp_file.name)

    # ---------- 播放 ----------
    def play_text(self, text: str):
        if isinstance(text, str) and not text.strip(): return
        self.play_queue.put(text)

    def _process_and_play_text(self, item, loop: asyncio.AbstractEventLoop, startupinfo=None):
        text = item # Assuming item is just text for now
        is_preview = False # Simplified for now

        self.log(f"Worker: Starting to process text: '{text[:30]}...'", "DEBUG")
        self.audio_status_queue.put(("PLAY", "[~]", f"正在處理: {text[:20]}..."))

        samples = None
        sample_rate = None

        # --- New Caching Logic ---
        cache_key_components = [
            text,
            self.current_engine,
            self.current_voice,
            str(self.tts_rate),
            str(self.tts_volume),
            str(self.tts_pitch)
        ]
        cache_key = hashlib.md5('+'.join(cache_key_components).encode('utf-8')).hexdigest()

        if cache_key in self._audio_cache:
            samples, sample_rate = self._audio_cache[cache_key]
            self.log(f"Retrieved phrase from cache: '{text[:20]}...'", "DEBUG")
        else:
            try:
                if self.app_controller and self.current_engine in self.app_controller.get_sherpa_onnx_engines():
                    samples, sample_rate = self._synth_sherpa_onnx(text)
                    if samples is None: self.log(f"Sherpa-ONNX synthesis returned no samples for '{text[:20]}...'", "DEBUG"); return

                elif self.current_engine == ENGINE_EDGE:
                    global AudioSegment
                    if AudioSegment is None: self._lazy_import()
                    samples, sample_rate = loop.run_until_complete(self._synth_edge_to_memory(text))
                    if samples is None: self.log(f"Edge-TTS synthesis returned no samples for '{text[:20]}...'", "DEBUG"); return

                elif self.current_engine == ENGINE_PYTTX3:
                    if AudioSegment is None: self._lazy_import()
                    samples, sample_rate = self._synth_pyttsx3_to_memory(text)
                    if samples is None: self.log(f"pyttsx3 synthesis returned no samples for '{text[:20]}...'", "DEBUG"); return
                
                # Cache the newly synthesized audio
                if samples is not None and sample_rate is not None:
                    self._audio_cache[cache_key] = (samples, sample_rate)
                    self.log(f"Cached newly synthesized phrase: '{text[:20]}...'", "DEBUG")

            except Exception as e:
                self.log(f"合成失敗: {e}", "ERROR")
                self.audio_status_queue.put(("PLAY", "[❌]", f"合成失敗: {text[:20]}..."))
                return
        # --- End Caching Logic ---
        
        # Add log to confirm samples are ready for playback
        if samples is not None and sample_rate is not None:
            self.log(f"Prepared {len(samples)} samples at SR {sample_rate} for playback.", "DEBUG")
        else:
            self.log(f"No samples prepared for playback for '{text[:20]}...'.", "ERROR") # Change to ERROR from original log.
            self.audio_status_queue.put(("PLAY", "[❌]", f"合成失敗，無法取得音訊數據: {text[:20]}..."))
            return # Ensure to return if samples are None here

        self._play_audio(samples, sample_rate, text, is_preview)




    def _play_stream_threaded(self, stream, data, stream_name):
        """Plays an audio stream in a separate thread."""
        try:
            self.log(f"Opening and writing to {stream_name} stream. Data shape: {data.shape}, dtype: {data.dtype}", "DEBUG")
            with stream:
                stream.write(data)
            self.log(f"Audio stream to device {stream.device} finished.", "DEBUG")
        except Exception as e:
            self.log(f"Error during audio playback to stream {stream_name}: {e}", "ERROR")

    def _play_audio(self, samples, sample_rate, text, is_preview):
        self.log(f"_play_audio called. Samples shape: {samples.shape}, SR: {sample_rate}, is_preview: {is_preview}", "DEBUG")
        self.log(f"DEBUG: Applying TTS volume: {self.tts_volume}, Listen volume: {self.listen_volume}", "DEBUG")

        main_device_id = self._local_output_devices.get(self.local_output_device_name, sd.default.device[1])
        listen_device_id = self._listen_devices.get(self.listen_device_name, sd.default.device[1])
        
        play_to_main = not is_preview
        play_to_listen = is_preview or self.enable_listen_to_self

        self.log(f"Main Device: {self.local_output_device_name} (ID: {main_device_id}), Listen Device: {self.listen_device_name} (ID: {listen_device_id})", "DEBUG")
        self.log(f"Play to Main: {play_to_main}, Play to Listen: {play_to_listen}", "DEBUG")

        # Apply master volume to main output samples
        samples_main = samples * self.tts_volume
        # Apply listen volume to listen output samples
        samples_listen = samples * self.listen_volume

        try:
            main_info = sd.query_devices(main_device_id)
            main_sr = int(main_info.get('default_samplerate', sample_rate))
            self.log(f"Main device '{main_info['name']}' (ID: {main_device_id}) default SR: {main_sr}", "DEBUG")
        except Exception:
            main_sr = sample_rate
            self.log(f"Failed to query main device {main_device_id}, using synthesized sample rate {sample_rate}", "WARNING")
            
        try:
            listen_info = sd.query_devices(listen_device_id)
            listen_sr = int(listen_info.get('default_samplerate', sample_rate))
            self.log(f"Listen device '{listen_info['name']}' (ID: {listen_device_id}) default SR: {listen_sr}", "DEBUG")
        except Exception:
            listen_sr = sample_rate
            self.log(f"Failed to query listen device {listen_device_id}, using synthesized sample rate {sample_rate}", "WARNING")
        
        streams_to_play = []
        threads = []

        try:
            # Resample for main stream if necessary
            resampled_samples_main = samples_main
            if play_to_main and sample_rate != main_sr:
                self.log(f"Resampling main stream from {sample_rate} Hz to {main_sr} Hz.", "DEBUG")
                num_samples_resampled = int(len(samples_main) * main_sr / sample_rate)
                resampled_samples_main = resample(samples_main, num_samples_resampled)
                
            # Resample for listen stream if necessary
            resampled_samples_listen = samples_listen
            if play_to_listen and sample_rate != listen_sr:
                self.log(f"Resampling listen stream from {sample_rate} Hz to {listen_sr} Hz.", "DEBUG")
                num_samples_resampled = int(len(samples_listen) * listen_sr / sample_rate)
                resampled_samples_listen = resample(samples_listen, num_samples_resampled)

            if play_to_main:
                self.log(f"Preparing main audio stream to device {main_device_id} at SR {main_sr}", "DEBUG")
                main_stream = sd.OutputStream(
                    samplerate=main_sr,
                    channels=1,
                    dtype=resampled_samples_main.dtype,
                    device=main_device_id
                )
                streams_to_play.append({'stream': main_stream, 'data': resampled_samples_main, 'name': f"Main ({main_device_id})"})
            
            if play_to_listen:
                self.log(f"Preparing listen audio stream to device {listen_device_id} at SR {listen_sr}", "DEBUG")
                listen_stream = sd.OutputStream(
                    samplerate=listen_sr,
                    channels=1,
                    dtype=resampled_samples_listen.dtype,
                    device=listen_device_id
                )
                streams_to_play.append({'stream': listen_stream, 'data': resampled_samples_listen, 'name': f"Listen ({listen_device_id})"})

            if not streams_to_play:
                self.log("No audio streams to play.", "DEBUG")
                return

            for s_info in streams_to_play:
                thread = threading.Thread(target=self._play_stream_threaded, args=(s_info['stream'], s_info['data'], s_info['name']))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

        except Exception as e:
            self.log(f"Error during audio playback setup: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            self.audio_status_queue.put(("PLAY", "[❌]", f"播放時發生錯誤: {e}"))
            return

        self.audio_status_queue.put(("PLAY", "[✔]", f"播放完畢: {text[:20]}..."))

    @staticmethod
    def _audiosegment_to_float32_numpy(audio_segment):
        samples = np.array(audio_segment.get_array_of_samples()).astype(np.float32)
        if audio_segment.channels == 2:
            samples = samples.reshape((-1, 2))
        else:
            samples = samples.reshape((-1,))
        max_val = float(2 ** (8 * audio_segment.sample_width - 1))
        samples = samples / max_val
        return samples
