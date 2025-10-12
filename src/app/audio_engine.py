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
from pydub import AudioSegment
import edge_tts
import pyttsx3
from datetime import datetime
import queue

from ..utils.deps import (
    DEFAULT_EDGE_VOICE, ENGINE_EDGE, ENGINE_PYTTX3
)

class AudioEngine:
    def __init__(self, log, status_update_queue):
        """
        log(text, level='INFO')
        status_update_queue: A queue to send status updates to the UI thread.
        """
        self.log = log
        self.status_queue = status_update_queue

        self.current_engine = ENGINE_EDGE
        self.edge_voice = DEFAULT_EDGE_VOICE
        self.pyttsx3_voice_id = None

        self.tts_rate = 175
        self.tts_volume = 1.0

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
                self._process_and_play_text(text, loop)
            except Exception as e:
                self.log(f"音訊工作執行緒發生錯誤: {e}", "ERROR")
        self.log("音訊工作執行緒已結束。", "DEBUG")

    # ---------- 初始化 & 資源 ----------
    def init_pyttsx3(self):
        if not self._pyttsx3_engine:
            self._pyttsx3_engine = pyttsx3.init()
            self._pyttsx3_voices = self._pyttsx3_engine.getProperty("voices")

    async def load_edge_voices(self):
        try:
            vm = await edge_tts.VoicesManager.create()
            self._edge_voices = [v for v in vm.voices if v.get("Locale", "").startswith("zh-")]
        except Exception as e:
            self.log(f"Edge TTS 載入失敗: {e}", "WARN")

    def query_devices(self):
        return sd.query_devices()

    def load_devices(self):
        try:
            devices = sd.query_devices()
            output_devices = [d for d in devices if d['max_output_channels'] > 0]
            self._listen_devices = {d['name']: d['index'] for d in output_devices}
            self._local_output_devices = {d['name']: d['index'] for d in output_devices}
            found_cable = False
            for d in output_devices:
                if "CABLE Input".upper() in d['name'].upper():
                    self.local_output_device_name = d['name']
                    self.cable_is_present = True
                    found_cable = True
                    break
            if not found_cable:
                self.local_output_device_name = "未找到 VB-CABLE!"
                self.log("設備列表載入完成，但未偵測到 VB-CABLE。", "WARN")
            else:
                self.log(f"已綁定輸出設備：{self.local_output_device_name}")
        except Exception as e:
            self.log(f"取得音效卡失敗: {e}", "ERROR")

    # ---------- 參數設定 ----------
    def set_engine(self, engine: str):
        self.current_engine = engine

    def set_edge_voice(self, short_name: str):
        self.edge_voice = short_name or DEFAULT_EDGE_VOICE

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

    # ---------- 合成 ----------
    async def _synth_edge_to_file(self, text, path):
        rate_param = f"{int(round((self.tts_rate - 175) * (40 / 75))):+d}%"
        volume_param = f"{int((self.tts_volume - 1.0) * 100):+d}%"
        comm = edge_tts.Communicate(text, self.edge_voice, rate=rate_param, volume=volume_param)
        await comm.save(path)

    def _synth_pyttsx3_to_file(self, text, path):
        if not self._pyttsx3_engine:
            self.log("pyttsx3 引擎未初始化。", "ERROR")
            raise RuntimeError("pyttsx3 engine not initialized.")
        self._pyttsx3_engine.setProperty("rate", self.tts_rate)
        self._pyttsx3_engine.setProperty("volume", self.tts_volume)
        if self.pyttsx3_voice_id:
            self._pyttsx3_engine.setProperty("voice", self.pyttsx3_voice_id)
        self._pyttsx3_engine.save_to_file(text, path)
        self._pyttsx3_engine.runAndWait()

    # ---------- 播放 ----------
    def _animate_playback(self, text, stop_event):
        animation_chars = ['|', '/', '-', '\\']
        i = 0
        while not stop_event.is_set():
            char = animation_chars[i % len(animation_chars)]
            self.status_queue.put(("[PLAY]", f"[{char}]", f"正在處理: {text[:20]}..."))
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
        if not isinstance(text, str) or not text.strip():
            return
        self.play_queue.put(text)

    def preview_text(self, text: str):
        """Producer method for previewing: puts text into the queue to be played on listen device only."""
        if not isinstance(text, str) or not text.strip():
            return
        # 使用一個特殊元組來標記這是一個預覽請求
        self.play_queue.put((text, "preview"))

    def _process_and_play_text(self, text: str, loop: asyncio.AbstractEventLoop):
        """
        The actual implementation of text synthesis and playback.
        This runs in the audio worker thread.
        """

        animation_stop_event = threading.Event()
        is_preview = False
        if isinstance(text, tuple):
            text, mode = text
            if mode == "preview":
                is_preview = True

        animation_thread = threading.Thread(
            target=self._animate_playback, args=(text, animation_stop_event), daemon=True
        )
        synth_suffix = ".mp3" if self.current_engine == ENGINE_EDGE else ".wav"
        fd, synth_path = tempfile.mkstemp(suffix=synth_suffix)
        os.close(fd)

        animation_thread.start()

        try:
            if self.current_engine == ENGINE_EDGE:
                loop.run_until_complete(self._synth_edge_to_file(text, synth_path))
            else:
                self._synth_pyttsx3_to_file(text, synth_path)

            audio = AudioSegment.from_file(synth_path)

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
            
            # 如果是預覽，則主設備ID強制設為None
            if is_preview:
                main_device_id = None

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

            # 單設備
            if (not self.enable_listen_to_self and not is_preview) or listen_device_id is None or listen_device_id == main_device_id:
                target_sr = main_sr
                audio_play = self._resample_audio_segment(audio, target_sr) if int(audio.frame_rate) != int(target_sr) else audio
                samples = self._audiosegment_to_float32_numpy(audio_play)
                if samples.ndim == 1 and main_max_ch >= 2:
                    samples = np.column_stack((samples, samples))
                try:
                    sd.play(samples, samplerate=target_sr, device=main_device_id)
                    sd.wait()
                    self.status_queue.put(("[PLAY]", "[✔]", f"播放完畢: {text[:20]}..."))
                except Exception as e:
                    self.log(f"播放到主設備失敗: {e}", "ERROR")
                finally:
                    try: sd.stop()
                    except Exception: pass
                    return

            # 僅預覽（只播放在 listen_device_id 上）
            if is_preview:
                target_sr = listen_sr
                audio_play = self._resample_audio_segment(audio, target_sr) if int(audio.frame_rate) != int(target_sr) else audio
                samples = self._audiosegment_to_float32_numpy(audio_play) * float(self.listen_volume)
                if samples.ndim == 1 and listen_max_ch >= 2:
                    samples = np.column_stack((samples, samples))
                try:
                    sd.play(samples, samplerate=target_sr, device=listen_device_id)
                    sd.wait()
                    self.status_queue.put(("[PLAY]", "[✔]", f"試聽完畢: {text[:20]}..."))
                except Exception as e:
                    self.log(f"試聽失敗: {e}", "ERROR")
                finally:
                    try: sd.stop()
                    except Exception: pass
                return

            # 兩設備並行
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
                self.status_queue.put(("[PLAY]", "[✔]", f"播放完畢: {text[:20]}..."))
            else:
                self.status_queue.put(("[PLAY]", "[❌]", f"播放時發生錯誤: {text[:20]}..."))

        except Exception as e:
            self.log(f"播放錯誤: {e}", "ERROR")
        finally:
            animation_stop_event.set()
            try:
                if animation_thread.is_alive():
                    animation_thread.join(timeout=0.2)
            except Exception:
                pass
            if os.path.exists(synth_path):
                try: os.remove(synth_path)
                except Exception: pass
