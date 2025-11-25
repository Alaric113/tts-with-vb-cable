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
import numpy as np
import sounddevice as sd
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
                          ENGINE_SHERPA_ONNX, CABLE_INPUT_HINT, TTS_MODELS_DIR)
from .model_manager import PREDEFINED_MODELS

class AudioEngine:
    def __init__(self, log_callback, status_queue, startupinfo=None):
        self.app_controller = None
        self.log = log_callback
        self.status_queue = status_queue
        self.startupinfo = startupinfo

        self.current_engine = ENGINE_SHERPA_ONNX # 預設改為 Sherpa-ONNX
        self.current_voice = "default"
        self.pyttsx3_voice_id = None
        self.sherpa_speaker_id = 0
        self.sherpa_speakers = []

        self.tts_rate = 1.0 # For Sherpa, 1.0 is default speed
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

    def init_sherpa_onnx(self, model_id="sherpa-vits-zh-aishell3"):
        if not self._lazy_import() or sherpa_onnx is None:
            return False

        if model_id not in PREDEFINED_MODELS:
            self.log(f"未定義的模型 ID: {model_id}", "ERROR")
            return False

        model_config = PREDEFINED_MODELS[model_id]
        model_dir = Path(TTS_MODELS_DIR) / model_id
        
        # 檢查所有模型檔案是否存在
        required_files = [model_dir / fname for fname in model_config["file_names"]]
        if not all(f.exists() for f in required_files):
            self.log(f"模型 '{model_id}' 檔案不完整，Sherpa-ONNX 未初始化。", "WARNING")
            self._sherpa_tts = None
            self.sherpa_model_id = None
            return False

        try:
            vits_model = str(model_dir / "vits-aishell3.onnx") # 假設 vits 模型檔名
            lexicon = str(model_dir / "lexicon.txt")
            tokens = str(model_dir / "tokens.txt")
            
            # 找到所有 rule FST 檔案
            rules_files = [str(f) for f in model_dir.glob("*.fsts")]

            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=vits_model,
                        lexicon=lexicon,
                        tokens=tokens,
                    ),
                    num_threads=2,
                    provider="cpu",
                ),
                rule_fsts=','.join(rules_files) if rules_files else ""
            )
            
            self._sherpa_tts = sherpa_onnx.OfflineTts(tts_config)
            self.sherpa_speakers = [f"Speaker {i}" for i in range(self._sherpa_tts.num_speakers)]
            self.sherpa_model_id = model_id
            self.log(f"Sherpa-ONNX 引擎已成功載入模型 '{model_id}'。", "DEBUG")
            return True
        except Exception as e:
            self.log(f"載入 Sherpa-ONNX 模型失敗: {e}", "ERROR")
            self._sherpa_tts = None
            self.sherpa_model_id = None
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
        if self.current_engine == ENGINE_SHERPA_ONNX and self.sherpa_speakers:
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
        if self.current_engine == ENGINE_SHERPA_ONNX:
            self.tts_rate = float(rate) # Speed for sherpa
        else:
            self.tts_rate = int(rate) # Rate for edge/pyttsx3
        self.tts_volume = float(volume)

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
            if self.current_engine == ENGINE_SHERPA_ONNX:
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
        elif self.current_engine == ENGINE_SHERPA_ONNX:
            return self.sherpa_speakers if self.sherpa_speakers else ["default"]
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
        self.status_queue.put(("PLAY", "[~]", f"正在處理: {text[:20]}..."))

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
                if self.current_engine == ENGINE_SHERPA_ONNX:
                    samples, sample_rate = self._synth_sherpa_onnx(text)
                    if samples is None: return

                elif self.current_engine == ENGINE_EDGE:
                    global AudioSegment
                    if AudioSegment is None: self._lazy_import()
                    samples, sample_rate = loop.run_until_complete(self._synth_edge_to_memory(text))
                    if samples is None: return

                elif self.current_engine == ENGINE_PYTTX3:
                    if AudioSegment is None: self._lazy_import()
                    samples, sample_rate = self._synth_pyttsx3_to_memory(text)
                    if samples is None: return
                
                # Cache the newly synthesized audio
                if samples is not None and sample_rate is not None:
                    self._audio_cache[cache_key] = (samples, sample_rate)
                    self.log(f"Cached newly synthesized phrase: '{text[:20]}...'", "DEBUG")

            except Exception as e:
                self.log(f"合成失敗: {e}", "ERROR")
                self.status_queue.put(("PLAY", "[❌]", f"合成失敗: {text[:20]}..."))
                return
        # --- End Caching Logic ---
            
        if samples is None:
            self.log(f"合成失敗，無法取得音訊數據: '{text[:20]}...'", "ERROR")
            self.status_queue.put(("PLAY", "[❌]", f"合成失敗: {text[:20]}..."))
            return

        self._play_audio(samples, sample_rate, text, is_preview)

    @staticmethod
    def _resample_audio(samples, current_sr, target_sr):
        # This is a placeholder for a real resampling implementation if needed.
        # For now, we rely on sounddevice handling it, but for multi-device, it's better to do it here.
        # Using a library like 'resampy' would be ideal.
        logging.warning("Resampling from %d to %d. For better quality, consider installing 'resampy'.", current_sr, target_sr)
        # Naive resampling, just for functionality.
        num_samples = int(len(samples) * target_sr / current_sr)
        return np.interp(np.linspace(0, len(samples), num_samples), np.arange(len(samples)), samples)


    def _play_audio(self, samples, sample_rate, text, is_preview):
        main_device_id = self._local_output_devices.get(self.local_output_device_name, sd.default.device[1])
        listen_device_id = self._listen_devices.get(self.listen_device_name, sd.default.device[1])
        
        play_to_main = not is_preview
        play_to_listen = is_preview or self.enable_listen_to_self

        # Apply master volume to main output samples
        samples_main = samples * self.tts_volume
        # Apply listen volume to listen output samples
        samples_listen = samples * self.listen_volume

        try:
            main_info = sd.query_devices(main_device_id)
            main_sr = int(main_info.get('default_samplerate', sample_rate))
        except Exception:
            main_sr = sample_rate
            self.log(f"Failed to query main device {main_device_id}, using synthesized sample rate {sample_rate}", "WARNING")
            
        try:
            listen_info = sd.query_devices(listen_device_id)
            listen_sr = int(listen_info.get('default_samplerate', sample_rate))
        except Exception:
            listen_sr = sample_rate
            self.log(f"Failed to query listen device {listen_device_id}, using synthesized sample rate {sample_rate}", "WARNING")

        # Resample if necessary - sounddevice handles this when using OutputStream if different.
        # However, for explicit control and potential future multi-channel mixing,
        # manual resampling (e.g., with resampy) before feeding to stream might be better.
        # For now, let's keep it simple and rely on sounddevice's internal resampling.
        
        streams = []
        try:
            if play_to_main:
                self.log(f"Starting main audio stream to device {main_device_id} at SR {main_sr}", "DEBUG")
                main_stream = sd.OutputStream(
                    samplerate=main_sr,
                    channels=1, # Assuming mono output from TTS
                    dtype=samples_main.dtype,
                    device=main_device_id
                )
                streams.append((main_stream, samples_main))
            
            if play_to_listen:
                self.log(f"Starting listen audio stream to device {listen_device_id} at SR {listen_sr}", "DEBUG")
                listen_stream = sd.OutputStream(
                    samplerate=listen_sr,
                    channels=1, # Assuming mono output from TTS
                    dtype=samples_listen.dtype,
                    device=listen_device_id
                )
                streams.append((listen_stream, samples_listen))

            if not streams:
                self.log("No audio streams to play.", "DEBUG")
                return

            for stream, data in streams:
                with stream: # Use 'with' statement for proper resource management
                    stream.write(data)
                self.log(f"Audio stream to device {stream.device} finished.", "DEBUG")

        except Exception as e:
            self.log(f"Error during audio playback: {e}", "ERROR")
            self.status_queue.put(("PLAY", "[❌]", f"播放時發生錯誤: {e}"))
            return

        self.status_queue.put(("PLAY", "[✔]", f"播放完畢: {text[:20]}..."))

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
