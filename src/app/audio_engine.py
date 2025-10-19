# -*- coding: utf-8 -*-
# 檔案: audio_engine.py
# 功用: 封裝所有與音訊處理相關的核心邏輯，將 TTS 合成與播放功能抽象化。
#      - 定義 AudioEngine 類別，作為音訊處理的主要介面。
#      - TTS 引擎管理: 支援並切換 edge-tts 和 pyttsx3 兩種引擎。
#      - 語音資源載入: 非同步載入 Edge TTS 的可用語音列表，並初始化 pyttsx3 引擎。
#      - 設備管理: 查詢、載入並管理系統中的音訊輸出設備，特別是偵測 VB-CABLE。
#      - TTS 合成: 根據當前選擇的引擎，將文字非同步或同步地合成為音訊檔案 (MP3/WAV)。
#      - 音訊播放: 使用 sounddevice 和 pydub 函式庫，將合成的音訊檔案解碼、重取樣，並播放到指定的一或多個輸出設備。
#      - 多設備播放: 實現將音訊同時串流到主輸出 (如 VB-CABLE) 和一個額外的「聆聽」設備的功能。

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

from ..utils.deps import (DEFAULT_EDGE_VOICE, ENGINE_EDGE, ENGINE_PYTTX3,
                          CABLE_INPUT_HINT)

# 延遲匯入，避免在 ffmpeg 路徑設定前就發出警告
pyttsx3 = None
AudioSegment = None

class AudioEngine:
    def __init__(self, log_callback, status_queue, startupinfo=None):
        self.app_controller = None # 新增一個參照，用於存取 config
        """
        log(text, level='INFO')
        status_update_queue: A queue to send status updates to the UI thread.
        """
        self.log = log_callback
        self.status_queue = status_queue
        self.startupinfo = startupinfo

        self.current_engine = ENGINE_EDGE
        self.current_voice = DEFAULT_EDGE_VOICE
        self.pyttsx3_voice_id = None

        self.tts_rate = 175
        self.tts_volume = 1.0
        self.tts_pitch = 0

        self.enable_listen_to_self = False
        self.listen_device_name = "Default"
        self.listen_volume = 1.0

        self._pyttsx3_engine = None
        self._pyttsx3_voices = []
        self._edge_voices = []

        self._local_output_devices = {}
        self._listen_devices = {}

        self.local_output_device_name = "Default"
        self.cable_is_present = False

        # -- Refactor: Producer-Consumer Queue --
        self.play_queue = queue.Queue()
        self.worker_thread = None
        # -----------------------------------------

    def start(self):
        self.worker_thread = threading.Thread(target=self._audio_worker, daemon=True)
        self.worker_thread.start()

    def stop(self):
        """Signal the audio worker to stop and wait for it."""
        self.log("正在停止音訊引擎...", "DEBUG")
        self.play_queue.put(None)  # Sentinel value to stop the worker
        self.log("音訊引擎已停止。" )

    def _audio_worker(self):
        """The consumer thread that processes text from the play_queue."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.log("音訊工作執行緒已啟動。", "DEBUG")

        while True:
            try:
                text = self.play_queue.get()
                if text is None:  # Sentinel check
                    self.log("音訊工作執行緒收到停止信號。", "DEBUG")
                    break
                # Pass the running loop to the processing function
                self._process_and_play_text(text, loop, self.startupinfo)
            except Exception as e:
                self.log(f"音訊工作執行緒發生錯誤: {e}", "ERROR")
        self.log("音訊工作執行緒已結束。", "DEBUG")

    # ---------- 初始化 & 資源 ----------
    def init_pyttsx3(self):
        """
        僅檢查 pyttsx3 模組是否存在並載入可用語音列表。
        不再在此處初始化引擎實例，以避免跨執行緒問題。
        """
        global pyttsx3
        if pyttsx3 is None:
            try:
                import pyttsx3
            except ImportError:
                self.log("缺少 'pyttsx3' 模組，相關功能將無法使用。", "ERROR")
                return
        # 為了獲取語音列表，我們需要一個臨時引擎
        temp_engine = pyttsx3.init()
        self._pyttsx3_voices = temp_engine.getProperty("voices")
        temp_engine.stop() # 獲取後立即銷毀

    async def load_edge_voices(self):
        # --- 核心修正: 延遲匯入 edge_tts ---
        import edge_tts

        try:
            vm = await edge_tts.VoicesManager.create()
            self._edge_voices = [v for v in vm.voices if v.get("Locale", "").startswith("zh-")]
        except Exception as e:
            self.log(f"Edge TTS 載入失敗: {e}", "WARN")

    def query_devices(self):
        """
        查詢所有音訊設備（輸入與輸出）。
        傳入 device=None, kind=None 以確保能獲取所有 host API 的設備列表。
        """
        return sd.query_devices()

    def load_devices(self):
        try:
            devices = sd.query_devices()
            all_device_names_upper = [d['name'].upper() for d in devices]
            output_devices = [d for d in devices if d['max_output_channels'] > 0]

            self._listen_devices = {d['name']: d['index'] for d in output_devices}
            self._local_output_devices = {d['name']: d['index'] for d in output_devices}

            # 步驟 4: 判斷驅動是否存在 (以虛擬麥克風為依據)
            self.cable_is_present = any(CABLE_INPUT_HINT.upper() in name for name in all_device_names_upper)

            # 步驟 5: 智慧尋找輸出設備 (虛擬喇叭)
            best_candidate = None
            # 5.1 優先尋找標準的 "CABLE Input"
            for d in output_devices:
                if "CABLE Input".upper() in d['name'].upper():
                    best_candidate = d['name']
                    break
            
            # 5.2 若找不到，則擴大範圍尋找任何包含 "VB-AUDIO" 的設備
            if not best_candidate:
                for d in output_devices:
                    # 排除麥克風，因為有些系統會把麥克風也列為輸出
                    if "VB-AUDIO" in d['name'].upper() and "OUTPUT" not in d['name'].upper():
                        best_candidate = d['name']
                        break
            
            # 步驟 6: 設定預設設備
            if best_candidate:
                self.local_output_device_name = best_candidate
                self.log(f"已自動綁定輸出設備：{self.local_output_device_name}", "INFO")

        except Exception as e:
            self.log(f"取得音效卡失敗: {e}", "ERROR")

    # ---------- 參數設定 ----------
    def set_engine(self, engine: str):
        self.current_engine = engine

    def set_current_voice(self, voice_name: str):
        self.current_voice = voice_name or DEFAULT_EDGE_VOICE

    def set_pyttsx3_voice_by_name(self, name: str):
        if not self._pyttsx3_voices:
            return
        for v in self._pyttsx3_voices:
            if v.name == name:
                self.pyttsx3_voice_id = v.id
                break

    def set_rate_volume(self, rate: int, volume: float):
        self.tts_rate = int(rate)
        self.tts_volume = float(volume)

    def apply_listen_config(self, config: dict):
        self.enable_listen_to_self = config.get("enable_listen_to_self", False)
        self.listen_device_name = config.get("listen_device_name", "Default")
        self.listen_volume = config.get("listen_volume", 1.0)

    def set_listen_config(self, enable: bool, device_name: str, volume: float):
        self.enable_listen_to_self = bool(enable)
        self.listen_device_name = device_name
        self.listen_volume = float(volume)

    def get_voice_names(self):
        if self.current_engine == ENGINE_EDGE:
            return [DEFAULT_EDGE_VOICE] + [v["ShortName"] for v in self._edge_voices]
        else:
            return [v.name for v in self._pyttsx3_voices] if self._pyttsx3_voices else ["default"]

    def get_listen_device_names(self):
        return list(self._listen_devices.keys()) if self._listen_devices else ["Default (無可用設備)"]

    def get_output_device_names(self):
        return list(self._local_output_devices.keys()) if self._local_output_devices else ["Default (無可用設備)"]

    def get_all_edge_voices(self):
        return self._edge_voices

    # ---------- 合成 ----------
    async def _synth_edge_to_file(self, text, path, voice_override=None, rate_override=None, pitch_override=None):
        # --- 核心修正: 延遲匯入 edge_tts ---
        import edge_tts

        # 檢查當前選擇的語音是否為自訂語音
        custom_voices = self.app_controller.config.get("custom_voices", []) if self.app_controller else []
        custom_voice_data = next((v for v in custom_voices if v["name"] == self.current_voice), None)

        voice = self.current_voice
        rate = self.tts_rate
        pitch = self.tts_pitch

        # 如果是預覽，則使用覆寫參數
        if voice_override:
            voice = voice_override
            rate = rate_override if rate_override is not None else self.tts_rate
            pitch = pitch_override if pitch_override is not None else self.tts_pitch
            custom_voice_data = None # 預覽時不使用自訂語音設定

        # 如果是自訂語音，則使用其內部參數
        elif custom_voice_data:
            voice = custom_voice_data["base_voice"]
            rate = custom_voice_data["rate"]
            pitch = custom_voice_data["pitch"]

        rate_param = f"{int(round((rate - 175) * (40 / 75))):+d}%"
        volume_param = f"{int((self.tts_volume - 1.0) * 100):+d}%"
        pitch_param = f"{int(pitch):+d}Hz"
        comm = edge_tts.Communicate(text, voice, rate=rate_param, volume=volume_param, pitch=pitch_param)
        await comm.save(path)
        return True

    def _synth_pyttsx3_to_file(self, text, path) -> bool:
        """
        在音訊工作執行緒中即時建立、使用並銷毀 pyttsx3 引擎。
        這是最可靠的方式，可以從根本上避免多執行緒衝突。
        """
        global pyttsx3
        if pyttsx3 is None:
            self.log("pyttsx3 模組未載入，無法合成。", "ERROR")
            return False

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
            if engine:
                engine.stop() # 確保引擎被銷毀

    # ---------- 播放 ----------
    def _animate_playback(self, text, stop_event):
        animation_chars = ['|', '/', '-', '\\']
        i = 0
        while not stop_event.is_set():
            char = animation_chars[i % len(animation_chars)]
            self.status_queue.put(("PLAY", f"[{char}]", f"正在處理: {text[:20]}..."))
            i += 1
            import time
            time.sleep(0.1)

    @staticmethod
    def _resample_audio_segment(audio_segment, target_rate):
        if int(audio_segment.frame_rate) == int(target_rate):
            return audio_segment
        return audio_segment.set_frame_rate(int(target_rate))

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

    def play_text(self, text: str):
        """Producer method: puts text into the queue to be played."""
        # --- 修正: 處理元組格式的 text ---
        if isinstance(text, tuple):
            self.log(f"play_text received (cached): '{text[1]}'", "DEBUG")
        else:
            self.log(f"play_text received: '{text}'", "DEBUG")

        # --- 核心修正: 只有當 text 是字串時才進行空值檢查 ---
        if isinstance(text, str) and not text.strip():
            return

        self.play_queue.put(text)

    def cache_phrase(self, phrase_info: dict):
        """
        將快捷語音的文字合成為快取檔案。
        這會在背景執行緒中處理，不會阻塞 UI。
        """
        self.play_queue.put((phrase_info, "cache"))

    def _get_cache_path(self, text, engine, voice, rate, pitch):
        """根據參數產生唯一的快取檔案路徑。"""
        from ..utils.deps import CACHE_DIR, ensure_dir
        ensure_dir(CACHE_DIR)
        
        # 建立一個能代表當前語音設定的字串
        props_str = f"{text}-{engine}-{voice}-{rate}-{pitch}"
        
        # 使用 SHA1 產生穩定且唯一的檔名
        hasher = hashlib.sha1(props_str.encode('utf-8'))
        filename = f"{hasher.hexdigest()}.wav"
        
        return os.path.join(CACHE_DIR, filename)

    def _process_caching(self, phrase_info: dict, loop: asyncio.AbstractEventLoop):
        """在背景執行緒中合成並儲存快取檔案的實際邏輯。"""
        # --- 核心修正: 確保 pydub 已被匯入 ---
        global AudioSegment
        if AudioSegment is None:
            from pydub import AudioSegment

        text = phrase_info.get("text")
        if not text:
            return

        # 根據當前設定產生目標快取路徑
        cache_path = self._get_cache_path(text, self.current_engine, self.current_voice, self.tts_rate, self.tts_pitch)
        
        # 如果快取已存在，則無需重新生成
        if os.path.exists(cache_path):
            self.log(f"快取已存在: '{text[:10]}...'", "DEBUG")
            return

        self.log(f"正在為 '{text[:10]}...' 建立語音快取...")
        try:
            if self.current_engine == ENGINE_EDGE:
                # Edge-TTS 直接存成 WAV 可能有問題，先存 MP3 再轉
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_mp3:
                    loop.run_until_complete(self._synth_edge_to_file(text, tmp_mp3.name))
                    audio = AudioSegment.from_mp3(tmp_mp3.name)
                    audio.export(cache_path, format="wav")
                os.remove(tmp_mp3.name)
            else: # pyttsx3
                self._synth_pyttsx3_to_file(text, cache_path)
            self.log(f"快取建立成功: {os.path.basename(cache_path)}", "INFO")
        except Exception as e:
            self.log(f"為 '{text[:10]}...' 建立快取失敗: {e}", "ERROR")

    def preview_text(self, text: str, override_voice: str = None, override_rate: int = None, override_pitch: int = None):
        """Producer method for previewing: puts text into the queue to be played on listen device only."""
        self.log(f"preview_text received: '{text}'", "DEBUG")
        if not isinstance(text, str) or not text.strip():
            return
        # 使用一個特殊元組來標記這是一個預覽請求
        self.play_queue.put((text, "preview", override_voice, override_rate, override_pitch))

    def _process_and_play_text(self, text: str, loop: asyncio.AbstractEventLoop, startupinfo=None):
        """
        The actual implementation of text synthesis and playback.
        This runs in the audio worker thread.
        """

        animation_stop_event = threading.Event()
        
        # --- 快取邏輯 ---
        # 檢查傳入的是否為快取請求
        if isinstance(text, tuple) and text[1] == "cache":
            phrase_info = text[0]
            self._process_caching(phrase_info, loop)
            return # 快取任務完成後直接返回，不播放
        
        # --- 核心修正: 處理來自快取播放的元組 ---
        is_cached_play = False
        is_preview = False
        original_text_for_cache = None
        voice_override = None
        rate_override = None
        pitch_override = None

        if isinstance(text, tuple):
            original_tuple = text # 保存原始元組
            # 檢查是預覽元組 (text, "preview") 還是快取元組 (path, original_text)
            if len(original_tuple) >= 2 and original_tuple[1] == "preview": # (text, "preview", voice, rate, pitch)
                is_preview = True
                text = original_tuple[0]
                if len(original_tuple) > 2 and original_tuple[2] is not None:
                    voice_override = original_tuple[2]
                if len(original_tuple) > 3 and original_tuple[3] is not None:
                    rate_override = original_tuple[3]
                if len(original_tuple) > 4 and original_tuple[4] is not None:
                    pitch_override = original_tuple[4]
            elif len(original_tuple) == 2 and os.path.isfile(str(original_tuple[0])): # type: ignore
                is_cached_play = True
                original_text_for_cache = text[1]
                text = text[0] # text 現在是檔案路徑

        # 根據播放類型決定顯示的文字
        display_text = original_text_for_cache if is_cached_play else text

        # --- 檢查點 1: 開始處理 ---
        self.log(f"Worker: Starting to process text: '{display_text[:30]}...'", "DEBUG")

        animation_thread = threading.Thread(
            target=self._animate_playback, args=(display_text, animation_stop_event), daemon=True
        )
        synth_suffix = ".mp3" if self.current_engine == ENGINE_EDGE else ".wav"
        fd, synth_path = tempfile.mkstemp(suffix=synth_suffix, prefix="tts_")
        os.close(fd)

        animation_thread.start()

        try:
            global AudioSegment
            if AudioSegment is None:
                from pydub import AudioSegment

            # 如果是快取播放，直接使用該路徑；否則，即時合成
            play_file_path = text if is_cached_play else synth_path
            if not is_cached_play:
                synthesis_success = False
                if self.current_engine == ENGINE_EDGE:
                    # 將覆寫參數傳遞給合成函式
                    synthesis_success = loop.run_until_complete(self._synth_edge_to_file(
                        text, play_file_path,
                        voice_override=voice_override, rate_override=rate_override, pitch_override=pitch_override
                    ))
                else:
                    # pyttsx3 試聽暫不支援覆寫，因其引擎狀態是同步的
                    synthesis_success = self._synth_pyttsx3_to_file(text, play_file_path)

                # --- 核心修正: 檢查合成是否成功 ---
                if not synthesis_success:
                    self.log(f"Worker: Synthesis failed for text '{display_text[:30]}...'. Aborting playback.", "ERROR")
                    # 不需要再記錄一次錯誤，因為合成函式內部已經記錄過了
                    # self.status_queue.put(("PLAY", "[❌]", f"合成失敗: {display_text[:20]}..."))
                    return # 直接中止後續流程
                    
            # --- 清理: 移除本地猴子補丁，現在由全域的 runtime_hook 處理 ---
            audio = AudioSegment.from_file(play_file_path)

            # --- 播放邏輯 (與之前相同) ---
            main_device_id = None
            if not is_preview:
                main_device_id = self._local_output_devices.get(self.local_output_device_name)
                if main_device_id is None:
                    main_device_id = sd.default.device[1]

            listen_device_id = None
            # 如果是預覽，或者啟用了「聆聽自己」，就需要設定聆聽設備
            if is_preview or self.enable_listen_to_self:
                listen_device_id = self._listen_devices.get(self.listen_device_name)
                if listen_device_id is None:
                    listen_device_id = sd.default.device[1]
            
            try:
                main_info = sd.query_devices(main_device_id)
                main_sr = int(main_info.get('default_samplerate', audio.frame_rate))
                main_max_ch = int(main_info.get('max_output_channels', 2))
            except Exception:
                main_sr = int(audio.frame_rate)
                main_max_ch = 2

            listen_sr = None
            listen_max_ch = None
            if listen_device_id is not None:
                try:
                    listen_info = sd.query_devices(listen_device_id)
                    listen_sr = int(listen_info.get('default_samplerate', audio.frame_rate))
                    listen_max_ch = int(listen_info.get('max_output_channels', 2))
                except Exception:
                    listen_sr = int(audio.frame_rate)
                    listen_max_ch = 2

            # --- 檢查點 5: 播放設定後，實際播放前 ---
            self.log(f"Worker: Playback setup complete. Main Dev: {main_device_id}, Listen Dev: {listen_device_id}", "DEBUG")

            # --- 核心修正: 重新組織播放邏輯 ---
            # 1. 純預覽模式 (未啟用聆聽自己)
            if is_preview and not self.enable_listen_to_self:
                self._play_to_single_device(audio, listen_sr, listen_device_id, listen_max_ch, self.listen_volume, display_text, is_preview=True)
                return

            # 2. 單設備播放模式 (主設備播放，且未啟用聆聽)
            if not is_preview and not self.enable_listen_to_self:
                self._play_to_single_device(audio, main_sr, main_device_id, main_max_ch, 1.0, display_text, is_preview=False)
                return # 播放完成後直接返回
            
            # 3. 雙設備並行播放模式 (主設備 + 聆聽設備)
            if int(audio.frame_rate) != int(main_sr):
                audio_main = self._resample_audio_segment(audio, main_sr)
            else:
                audio_main = audio
            samples_main = self._audiosegment_to_float32_numpy(audio_main)
            if samples_main.ndim == 1 and main_max_ch >= 2:
                samples_main = np.column_stack((samples_main, samples_main))

            if int(audio.frame_rate) != int(listen_sr):
                audio_listen = self._resample_audio_segment(audio, listen_sr)
            else:
                audio_listen = audio
            samples_listen = self._audiosegment_to_float32_numpy(audio_listen) * float(self.listen_volume)
            if samples_listen.ndim == 1 and listen_max_ch >= 2:
                samples_listen = np.column_stack((samples_listen, samples_listen))

            playback_errors = []

            def play_blocking(data, sr, dev_id, text_snippet):
                try:
                    sd.play(data, samplerate=sr, device=dev_id, blocking=True)
                except Exception as e:
                    playback_errors.append(e)
                    self.log(f"在設備 {dev_id} 播放 '{text_snippet}' 時失敗: {e}", "ERROR")

            t1 = threading.Thread(target=play_blocking, args=(samples_main, main_sr, main_device_id, text[:10]))
            t2 = threading.Thread(target=play_blocking, args=(samples_listen, listen_sr, listen_device_id, text[:10]))

            t1.start(); t2.start()
            t1.join();  t2.join()

            if not playback_errors:
                self.status_queue.put(("PLAY", "[✔]", f"播放完畢: {display_text[:20]}..."))
            else:
                self.status_queue.put(("PLAY", "[❌]", f"播放時發生錯誤: {display_text[:20]}..."))

        except Exception as e:
            self.log(f"播放錯誤: {e}", "ERROR")
        finally:
            animation_stop_event.set()
            try:
                if animation_thread.is_alive():
                    animation_thread.join(timeout=0.2)
            except Exception:
                pass
            # 只刪除即時合成的臨時檔案，不刪除快取檔案
            if not is_cached_play and os.path.exists(synth_path):
                try:
                    os.remove(synth_path)
                except Exception:
                    pass

    def _play_to_single_device(self, audio, target_sr, device_id, max_ch, volume, display_text, is_preview=False):
        """將音訊播放到單一設備的輔助函式。"""
        audio_play = self._resample_audio_segment(audio, target_sr) if int(audio.frame_rate) != int(target_sr) else audio
        samples = self._audiosegment_to_float32_numpy(audio_play) * float(volume)
        if samples.ndim == 1 and max_ch >= 2:
            samples = np.column_stack((samples, samples))
        try:
            sd.play(samples, samplerate=target_sr, device=device_id)
            sd.wait()
            log_msg = f"試聽完畢: {display_text[:20]}..." if is_preview else f"播放完畢: {display_text[:20]}..."
            self.status_queue.put(("PLAY", "[✔]", log_msg))
        except Exception as e:
            log_msg = f"試聽失敗: {e}" if is_preview else f"播放到主設備失敗: {e}"
            self.log(log_msg, "ERROR")
        finally:
            try: sd.stop()
            except Exception: pass
