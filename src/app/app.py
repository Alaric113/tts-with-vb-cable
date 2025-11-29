# -*- coding: utf-8 -*-
# 檔案: app.py
# 功用: 定義主應用程式 LocalTTSPlayer 類別，為程式的核心 UI 與事件處理中心。
#      - 使用 customtkinter 建構所有使用者介面元素。
#      - 管理應用程式的啟動、停止、關閉等生命週期。
#      - 協調 UI 操作與 audio_engine 和 utils_deps 模組的功能調用。

import queue
import os
import sys
import threading
import collections
import ctypes
import shutil
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import pyqtSignal, QObject, QTimer, Qt
from PyQt6.QtGui import QKeySequence, QShortcut

from pynput import keyboard
import sounddevice as sd

# 可選 Windows 依賴
try:
    import comtypes.client  # noqa: F401
    from comtypes import CLSCTX_ALL  # noqa: F401
    comtypes_installed = True
    import pythoncom
except Exception:
    comtypes_installed = False
try:
    import win32gui
    import win32con
    import win32api
    import win32process
    pywin32_installed = True
except ImportError:
    pywin32_installed = False

from ..utils.deps import (
    APP_VERSION, CABLE_INPUT_HINT,
    ENGINE_EDGE, ENGINE_PYTTX3, ENGINE_CHAT_TTS, DEFAULT_EDGE_VOICE,
    ENGINE_SHERPA_VITS_ZH_AISHELL3, ENGINE_VITS_PIPER_EN_US_GLADOS,
    DependencyManager, ModelDownloader, delete_model as util_delete_model, IS_WINDOWS, check_model_downloaded # NEW: import check_model_downloaded
)
from .audio_engine import AudioEngine
from ..ui.popups import SettingsWindow, QuickPhrasesWindow, ModelManagementWindow
from ..ui.main_window import MainWindow
from .config_manager import ConfigManager
from ..ui.animation import AnimationManager
from .updater_manager import UpdateManager
from .model_manager import PREDEFINED_MODELS # NEW: Import PREDEFINED_MODELS here


class AppSignals(QObject):
    """定義應用程式中所有需要跨執行緒通訊的信號。"""
    log_message = pyqtSignal(str, str, str)
    audio_status = pyqtSignal(str, str, str)
    update_ui_after_load = pyqtSignal(str) # NEW: Accepts string for model_id
    prompt_vbcable_setup = pyqtSignal(str)
    check_for_updates = pyqtSignal(bool) # title, message, type, callback_or_event
    show_messagebox_signal = pyqtSignal(str, str, str, object)
    show_quick_input_signal = pyqtSignal()

class LocalTTSPlayer(QObject):
    def __init__(self, startupinfo=None):
        super().__init__()
        # 狀態/設定 (提前初始化日誌佇列，以防 ConfigManager 初始化時就需要記錄)
        self._early_log_queue = []
        self.signals = AppSignals()
        self.config = ConfigManager(self.log_message)
        self.audio_status_queue = queue.Queue()
        self.startupinfo = startupinfo # 儲存 startupinfo 物件
        
        # 將共用常數設為實例屬性，方便 UI 存取
        self.CABLE_INPUT_HINT = CABLE_INPUT_HINT
        self.ENGINE_EDGE = ENGINE_EDGE
        self.ENGINE_PYTTX3 = ENGINE_PYTTX3
        self.ENGINE_CHAT_TTS = ENGINE_CHAT_TTS
        self.ENGINE_SHERPA_VITS_ZH_AISHELL3 = ENGINE_SHERPA_VITS_ZH_AISHELL3
        self.ENGINE_VITS_PIPER_EN_US_GLADOS = ENGINE_VITS_PIPER_EN_US_GLADOS

        # 狀態/設定
        # 音訊核心 (必須在 _build_ui 之前建立，以便 UI 取得初始值)
        self.audio = AudioEngine(self.log_message, self.audio_status_queue, startupinfo=self.startupinfo)
        self.updater = UpdateManager(self) # 建立更新管理器
        self.audio.app_controller = self # 讓 audio_engine 可以存取 app
        self.model_downloader = ModelDownloader(
            log=self.log_message,
            status=lambda icon, msg, level="INFO": self.signals.audio_status.emit(level, icon, msg),
            ask_yes_no_sync=lambda title, msg: self.show_messagebox(title, msg, "yesno", (threading.Event(), []))
        )
        self.model_downloader.download_progress_signal.connect(self._on_model_download_progress)
        self.model_management_window = None # To hold reference to the opened window


        self.is_running = False

        # UI/其他
        self.current_hotkey = self.config.get("hotkey")
        self.quick_phrases = self.config.get("quick_phrases")
        self.quick_input_position = self.config.get("quick_input_position")
        self.enable_quick_phrases = self.config.get("enable_quick_phrases")
        self.text_history = collections.deque(self.config.get("text_history", []), maxlen=20)

        self._input_window_lock = threading.Lock()
        self._quick_phrase_lock = threading.Lock()
        self.hotkey_listener = None

        self.quick_input_window = None
        self.settings_window = None
        self.quick_phrases_window = None

        self._hotkey_recording_listener = None
        self._pressed_keys = set()
        self._is_hotkey_edit_mode = False
        self._recording_key_index = None
        self._ui_loading = True # 新增旗標，用於防止啟動時觸發事件

        # --- PyQt UI 初始化 ---
        self.main_window = MainWindow(self)
        self.root = self.main_window # 為了相容舊的 self.root 參照

        # --- 修正: 在依賴載入前，禁用服務控制按鈕 ---
        self.main_window.start_button.setEnabled(False)
        self.main_window.stop_button.setEnabled(False)
        # ---------------------------------------------

        # --- 增強: 初始化動畫管理器 ---
        self.animator = AnimationManager(self.root)

        self.audio.start() # UI 建立完成後，再啟動音訊背景執行緒
        # 載入設定
        self.audio.set_engine(self.config.get("engine", ENGINE_PYTTX3)) # Default to pyttsx3
        self.audio.current_voice = self.config.get("voice")
        self.audio.tts_rate   = self.config.get("rate")
        self.audio.tts_volume = self.config.get("volume")
        self.audio.tts_pitch  = self.config.get("pitch", 0)
        self.log_message(f"DEBUG: LocalTTSPlayer.__init__: Loaded global TTS Rate: {self.audio.tts_rate}, Volume: {self.audio.tts_volume}, Pitch: {self.audio.tts_pitch}", "DEBUG")
        self.audio.set_listen_config(self.config.get("enable_listen_to_self"), self.config.get("listen_device_name"), self.config.get("listen_volume"))

        self._update_hotkey_display(self.config.get("hotkey"))

        # --- PyQt 信號連接 ---
        self._connect_signals()

        # 啟動音訊狀態佇列的消費者
        self.audio_status_timer = QTimer()
        self.audio_status_timer.timeout.connect(self._process_audio_status_queue)
        self.audio_status_timer.start(100)

        # 啟動後立即在背景檢查更新
        QTimer.singleShot(100, lambda: self.updater.check_for_updates(silent=True))

        # 依賴流程（先 Log，再詢問）
        QTimer.singleShot(2000, lambda: threading.Thread(target=self._dependency_flow_thread, daemon=True).start())
        
        # 在 UI 完全建立後，根據設定檔設定開關狀態
        if self.enable_quick_phrases:
            self.main_window.quick_phrase_switch.setChecked(True)

        if self.config.get("auto_start_service"):
            self.log_message("偵測到自動啟動選項，將在初始化完成後啟動服務。")

        # 根據設定初始化日誌區域可見性
        QTimer.singleShot(10, lambda: self.toggle_log_area(initial_load=True))

    def get_sherpa_onnx_engines(self):
        downloaded_sherpa_engines = []
        for model_id, model_config in PREDEFINED_MODELS.items():
            if "engine" in model_config and model_config["engine"] == model_id: # Assuming engine == model_id for Sherpa-ONNX models
                if check_model_downloaded(model_id):
                    downloaded_sherpa_engines.append(model_id)
        return downloaded_sherpa_engines


    def _connect_signals(self):
        """連接所有 PyQt 信號到對應的槽函數。"""
        self.signals.log_message.connect(self._log_message_slot, Qt.ConnectionType.QueuedConnection)
        self.signals.audio_status.connect(self._audio_status_slot, Qt.ConnectionType.QueuedConnection)
        self.signals.update_ui_after_load.connect(self._update_ui_after_load, Qt.ConnectionType.QueuedConnection)
        self.signals.prompt_vbcable_setup.connect(self._prompt_run_vbcable_setup, Qt.ConnectionType.QueuedConnection)
        self.signals.check_for_updates.connect(self.updater.check_for_updates, Qt.ConnectionType.QueuedConnection)
        self.signals.show_messagebox_signal.connect(self._show_messagebox_slot, Qt.ConnectionType.QueuedConnection)
        self.signals.show_quick_input_signal.connect(self._show_quick_input_slot, Qt.ConnectionType.QueuedConnection)

        # --- 核心修正: 監聽全域焦點變化以關閉快捷輸入框 ---
        QApplication.instance().focusChanged.connect(self.on_global_focus_changed)

    # ===================== Log 與進度 =====================
    def log_message(self, msg, level="INFO", mode="append"):
        """安全地記錄訊息，即使在 UI 建立之前。"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] [{level.upper():<5}] {msg}"

        if not hasattr(self, 'main_window') or not self.main_window.isVisible():
            self._early_log_queue.append(formatted_msg)
            return

        # 從任何執行緒發射信號
        self.signals.log_message.emit(formatted_msg, level, mode)

    def _log_message_slot(self, formatted_msg, level, mode):
        """在主執行緒中更新日誌 UI 的槽函數。"""
        # DEBUG 訊息現在會顯示，以協助診斷問題
        if level.upper() == 'DEBUG': return 

        log_widget = self.main_window.log_text
        cursor = log_widget.textCursor()

        if mode == "replace_last":
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.movePosition(cursor.MoveOperation.StartOfBlock, cursor.MoveMode.KeepAnchor)
            cursor.insertText(formatted_msg)
        else:
            log_widget.append(formatted_msg)

    def show_messagebox(self, title, message, msg_type="info", callback=None):
        is_sync_call = isinstance(callback, tuple) and len(callback) == 2 and isinstance(callback[0], threading.Event)
        self.signals.show_messagebox_signal.emit(title, message, msg_type, callback)

        if is_sync_call:
            event, result_container = callback
            event.wait()
            return result_container[0] if result_container else False
        return None
        
    def _show_messagebox_slot(self, title, message, msg_type, callback):
        msg_box = QMessageBox(self.main_window)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        icon_map = {
            "info": QMessageBox.Icon.Information, "warning": QMessageBox.Icon.Warning,
            "error": QMessageBox.Icon.Critical, "yesno": QMessageBox.Icon.Question
        }
        msg_box.setIcon(icon_map.get(msg_type, QMessageBox.Icon.NoIcon))

        if msg_type == "yesno":
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            result = msg_box.exec()
            user_choice = (result == QMessageBox.StandardButton.Yes)

            is_sync_call = isinstance(callback, tuple) and len(callback) == 2 and isinstance(callback[0], threading.Event)
            if is_sync_call:
                event, result_container = callback
                result_container.append(user_choice)
                event.set()
            elif callable(callback):
                callback(user_choice)
        else:
            msg_box.exec()

    # ===================== 依賴流程 =====================
    def _dependency_flow_thread(self):
        # --- NEW: Unzip internal components on first run ---
        try:
            # sys.executable is the path to JuMouth.exe
            # Use getattr to be safe in non-frozen environments
            if getattr(sys, 'frozen', False):
                app_dir = Path(sys.executable).parent
                internal_zip = app_dir / "_internal.zip"
                internal_dir = app_dir / "_internal"

                if internal_zip.exists():
                    self.log_message("第一次啟動，正在解壓縮內部元件...", "INFO")
                    # Clean up old directory if it exists, to ensure a fresh extraction
                    if internal_dir.exists():
                        shutil.rmtree(internal_dir)
                    
                    # Unzip the archive to the application's root directory
                    shutil.unpack_archive(internal_zip, app_dir)
                    
                    # Clean up the zip file
                    os.remove(internal_zip)
                    self.log_message("內部元件解壓縮完成。", "INFO")
        except Exception as e:
            self.log_message(f"解壓縮內部元件時發生錯誤: {e}", "ERROR")
            self.show_messagebox("嚴重錯誤", f"無法設定應用程式的必要元件: {e}", "error")
            return
        # --- END NEW ---

        if IS_WINDOWS and comtypes_installed:
            pythoncom.CoInitializeEx(0)

        self.log_message("開始檢查依賴...", "DEBUG")
        callbacks = {
            "log": lambda msg, level="INFO": self.log_message(msg, level),
            "status": lambda icon, msg, level="INFO": self.signals.audio_status.emit(level, icon, msg),
            "ask_yes_no_sync": lambda title, msg: self.show_messagebox(title, msg, "yesno", (threading.Event(), [])),
            "ask_yes_no_async": lambda title, msg, cb: self.show_messagebox(title, msg, "yesno", cb),
            "show_info": lambda t, m: self.show_messagebox(t, m, "info"),
            "show_error": lambda t, m: self.show_messagebox(t, m, "error"),
        }
        dm = DependencyManager(**callbacks, startupinfo=self.startupinfo)
        
        if not dm.ensure_ffmpeg():
            return
            
        try:
            if dm.need_install_vbcable(self.audio.query_devices):
                self.log_message("未偵測到 VB-CABLE 驅動。準備啟動安裝程序引導...", "WARN")
                def have_setup(path): self._prompt_run_vbcable_setup(path)
                def need_run(path): self._prompt_run_vbcable_setup(path)
                dm.prepare_vbcable_setup(have_setup, need_run)
                return

            self.log_message("檢查 TTS 模型...", "DEBUG")
            # model_downloader = ModelDownloader(log=callbacks["log"], status=callbacks["status"], ask_yes_no_sync=callbacks["ask_yes_no_sync"])
            # model_downloader.ensure_model("sherpa-vits-zh-aishell3") # Removed automatic model download at startup

            import asyncio
            self.audio.init_pyttsx3()
            asyncio.run(self.audio.load_edge_voices())
            sherpa_loaded = self.audio._init_sherpa_onnx_runtime()

            # Fallback logic
            if self.config.get("engine") in self.get_sherpa_onnx_engines() and not sherpa_loaded:
                self.log_message("預設引擎 Sherpa-ONNX 模型載入失敗，自動切換至備援引擎 pyttsx3。", "WARN")
                self.config.set("engine", ENGINE_PYTTX3)
                self.audio.set_engine(ENGINE_PYTTX3)
            
            self.audio.load_devices()
            self.signals.update_ui_after_load.emit("") # Provide empty string as argument
            self.log_message("依賴與設備載入完成。", "DEBUG")

            self.main_window.start_button.setEnabled(True)

            if self.config.get("auto_start_service"):
                QTimer.singleShot(100, self.start_local_player)

        except Exception as e:
            self.log_message(f"初始化錯誤: {e}", "ERROR")

    def _prompt_run_vbcable_setup(self, setup_path: str):
        def on_user_choice(do_install):
            if do_install:
                try:
                    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", setup_path, None, os.path.dirname(setup_path), 1)
                    if ret <= 32: raise OSError(f"ShellExecuteW 啟動安裝程式失敗，錯誤碼: {ret}")
                    QTimer.singleShot(1000, self.on_closing)
                except Exception as e:
                    self.log_message(f"VB-CABLE 安裝執行錯誤: {e}", "ERROR")
            else:
                self.log_message("使用者取消了 VB-CABLE 安裝。", "WARN")

        self.show_messagebox("VB-CABLE 安裝提示",
            "TTS 語音輸入 Discord 需要 VB-CABLE 驅動程式。\n\n"
            f"點擊 '是' 將啟動安裝程序，您可能需要授權管理員權限並點擊 'Install Driver'。\n\n"
            "安裝後，請重新啟動本應用程式。",
            msg_type='yesno', callback=on_user_choice)

    def _update_ui_after_load(self, new_engine_id=""):
        self._ui_loading = True

        engine_list = self.get_sherpa_onnx_engines()
        
        # Determine the current engine
        current_engine = new_engine_id if new_engine_id and new_engine_id in engine_list else self.config.get("engine")
        if not current_engine or current_engine not in engine_list:
            current_engine = engine_list[0] if engine_list else None
        
        self.log_message(f"DEBUG: _update_ui_after_load: Updating UI. Engine list: {engine_list}. Current engine: {current_engine}", "DEBUG")

        # Repopulate and set engine combo box
        if hasattr(self.main_window, 'engine_combo'):
            self.main_window.engine_combo.clear()
            if engine_list:
                self.main_window.engine_combo.addItems(engine_list)
                self.main_window.engine_combo.setCurrentText(current_engine)
        
        # Fallback if the saved engine isn't downloaded
        if self.main_window.engine_combo.currentIndex() == -1 and engine_list:
            self.main_window.engine_combo.setCurrentText(engine_list[0])

        # Other UI elements
        devnames = self.audio.get_output_device_names()
        self.main_window.local_device_combo.clear()
        self.main_window.local_device_combo.addItems(devnames)
        if self.audio.local_output_device_name in devnames:
            self.main_window.local_device_combo.setCurrentText(self.audio.local_output_device_name)
        self.main_window.local_device_combo.setEnabled(True)

        if self._early_log_queue:
            for msg in self._early_log_queue: self.main_window.log_text.append(msg)
            self._early_log_queue.clear()
        
        self._ui_loading = False
        
        # Trigger the change logic for the selected engine
        self._on_engine_change(self.main_window.engine_combo.currentText())

    def _on_engine_change(self, val):
        if self._ui_loading or not val: return
        
        self.audio.set_engine(val)
        self.log_message(f"切換引擎: {self.audio.current_engine}")

        # Set UI properties for Sherpa-ONNX models
        self.main_window.pitch_slider.setEnabled(False)
        self.main_window.pitch_value_label.setText("N/A")
        self.main_window.speed_slider.setRange(0, 20) # 0.0 to 2.0
        
        self.config.set("engine", val)
        # This will trigger on_voice_change, which handles loading speakers and settings
        self.on_voice_change(None)

    def on_voice_change(self, choice):
        if self._ui_loading and choice is not None: return

        model_id = self.audio.current_engine
        if not model_id: return

        # Load model if it's not already loaded
        if self.audio.sherpa_model_id != model_id:
            self.log_message(f"嘗試載入 Sherpa-ONNX 模型: {model_id}", "INFO")
            if not self.audio._load_sherpa_onnx_voice(model_id):
                self.show_messagebox("錯誤", f"載入 Sherpa-ONNX 模型 '{model_id}' 失敗。", "error")
                # Handle fallback if needed, e.g., switch to another model
                return
        
        # Populate speaker list and set selection
        combo = self.main_window.voice_combo
        combo.blockSignals(True)
        try:
            speakers = self.audio.get_voice_names()
            combo.clear()
            combo.addItems(speakers)

            if len(speakers) > 1:
                combo.setEnabled(True)
                # If a choice was passed (user clicked), use it. Otherwise, load from config.
                if choice and choice in speakers:
                    current_speaker = choice
                else:
                    speaker_id = self.config.get_model_setting(model_id, "speaker_id", 0)
                    current_speaker = f"Speaker {speaker_id}"
                
                if current_speaker in speakers:
                    combo.setCurrentText(current_speaker)
                elif speakers:
                    combo.setCurrentText(speakers[0])
            else:
                # single-speaker model
                combo.setEnabled(False)
        finally:
            combo.blockSignals(False)

        # Update audio engine and config with the final selection
        final_speaker_choice = combo.currentText()
        if not final_speaker_choice: return

        self.log_message(f"講者設定為: {final_speaker_choice}")
        try:
            speaker_id = int(final_speaker_choice.split(" ")[-1])
            self.audio.sherpa_speaker_id = speaker_id
            self.config.set_model_setting(model_id, "speaker_id", speaker_id)
        except (ValueError, IndexError):
            self.log_message(f"無法從 '{final_speaker_choice}' 解析講者 ID", "WARN")
        
        # Update settings sliders for the selected model
        self.update_tts_settings(force_load=True)

    def _on_local_device_change(self, device_name):
        if self._ui_loading or not device_name: return
        self.audio.local_output_device_name = device_name
        self.log_message(f"主輸出設備已變更為: {device_name}")
        self.config.set("local_output_device_name", device_name)

    def update_tts_settings(self, _=None, force_load=False):
        if self._ui_loading: return

        model_id = self.audio.current_engine
        if not model_id: return

        # On a forced load, we read from config and update the UI
        if force_load:
            rate = self.config.get_model_setting(model_id, "rate", 1.0)
            volume = self.config.get_model_setting(model_id, "volume", 1.0)
            self.main_window.speed_slider.setValue(int(rate * 10))
            self.main_window.volume_slider.setValue(int(volume * 100))
            return

        # Normal operation: read from UI and save to config
        rate = self.main_window.speed_slider.value() / 10.0
        volume = round(self.main_window.volume_slider.value() / 100.0, 2)
        
        self.audio.set_rate_volume(rate, volume)
        self.main_window.speed_value_label.setText(f"{rate:.1f}")
        self.main_window.volume_value_label.setText(f"{volume:.2f}")
        
        self.config.set_model_setting(model_id, "rate", rate)
        self.config.set_model_setting(model_id, "volume", volume)

    def _process_audio_status_queue(self):
        try:
            while not self.audio_status_queue.empty():
                level, icon, message = self.audio_status_queue.get_nowait()
                self.signals.audio_status.emit(level, icon, message)
        except queue.Empty: pass

    def _audio_status_slot(self, level, icon, message):
        self.log_message(f"{icon} {message}", level, mode="replace_last")

    # ===================== 啟停與播放 =====================
    def start_local_player(self):
        if self.is_running: return
        if not self.audio.cable_is_present and "CABLE" in (self.audio.local_output_device_name or ""):
            self.show_messagebox("錯誤", "無法啟動：未偵測到 VB-CABLE 虛擬喇叭。", "error")
            return
        self.is_running = True
        
        self.main_window.status_label.setText("● 運行中")
        self.main_window.status_label.setStyleSheet(f"color: {self.main_window.STATUS_GREEN_COLOR}; font-weight: bold;")
        self.main_window.start_button.setEnabled(False)
        self.main_window.stop_button.setEnabled(True)
        
        self._start_hotkey_listener()

    def stop_local_player(self):
        if not self.is_running: return
        self.is_running = False
        if self.hotkey_listener: self.hotkey_listener.stop()
            
        self.main_window.status_label.setText("● 已停止")
        self.main_window.status_label.setStyleSheet(f"color: {self.main_window.STATUS_ORANGE_COLOR}; font-weight: bold;")
        self.main_window.start_button.setEnabled(True)
        self.main_window.stop_button.setEnabled(False)
        self.log_message("服務已停止。")

    def _start_hotkey_listener(self):
        try:
            if self.hotkey_listener:
                self.hotkey_listener.stop()
            
            self.log_message(f"準備註冊快捷鍵。主要快捷鍵: '{self.current_hotkey}'", "DEBUG")

            hotkeys = {}
            config_changed = False

            # Validate and format main hotkey
            if self.current_hotkey:
                normalized_main_hotkey = self._normalize_hotkey(self.current_hotkey)
                if self._is_hotkey_valid_for_pynput(self.current_hotkey): # Pass original for validation, it will normalize internally
                    hotkeys[normalized_main_hotkey] = self._show_quick_input
                    # Update config if normalization changed the format (e.g., 'shift+z' to '<shift>+z')
                    if normalized_main_hotkey != self.current_hotkey:
                        self.config.set("hotkey", normalized_main_hotkey)
                        self.current_hotkey = normalized_main_hotkey
                        config_changed = True
                else:
                    self.log_message(f"已忽略並清除無效的主要快捷鍵 '{self.current_hotkey}'。請重新設定。", "WARN")
                    self.current_hotkey = ""
                    self.config.set("hotkey", "")
                    config_changed = True

            # Validate and format quick phrase hotkeys
            if self.enable_quick_phrases:
                for i, phrase in enumerate(self.quick_phrases):
                    phrase_hotkey = phrase.get("hotkey")
                    if phrase_hotkey and phrase.get("text"):
                        self.log_message(f"正在驗證快捷語音 {i} 的快捷鍵: '{phrase_hotkey}'", "DEBUG")
                        normalized_phrase_hotkey = self._normalize_hotkey(phrase_hotkey)
                        if self._is_hotkey_valid_for_pynput(phrase_hotkey): # Pass original for validation
                            import functools
                            hotkeys[normalized_phrase_hotkey] = functools.partial(self._play_quick_phrase, phrase["text"], phrase_info=phrase)
                            # Update config if normalization changed the format
                            if normalized_phrase_hotkey != phrase_hotkey:
                                phrase["hotkey"] = normalized_phrase_hotkey
                                config_changed = True
                        else:
                            self.log_message(f"已忽略並清除快捷語音的無效快捷鍵 '{phrase_hotkey}'。", "WARN")
                            phrase["hotkey"] = ""
                            config_changed = True
            
            if config_changed:
                self.config.set("quick_phrases", self.quick_phrases)
                self.config.save() # Save changes if any hotkey was normalized or cleared

            if not hotkeys:
                self.log_message("沒有有效的快捷鍵可供監聽。", "INFO")
                if self.hotkey_listener:
                    self.hotkey_listener.stop()
                return

            self.log_message(f"最終註冊的快捷鍵: {hotkeys}", "DEBUG")
            self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
            self.hotkey_listener.start()
            self.log_message(f"服務已啟動，監聽 {len(hotkeys)} 個快捷鍵。")
        except Exception as e:
            self.log_message(f"快捷鍵啟動失敗: {e}。請檢查格式或重啟應用。", "ERROR")
            import traceback
            self.log_message(traceback.format_exc(), "ERROR")

    def _play_quick_phrase(self, text, phrase_info=None):
        if not self.is_running: return
        self.audio.play_text(text)

    # ===================== 快捷鍵編輯 =====================
    def _key_to_str(self, key):
        """將 pynput 的 key 物件轉換為標準化的字串表示。"""
        if isinstance(key, keyboard.KeyCode):
            return key.char.lower() if key.char and len(key.char) == 1 else ''
        else:
            key_name = key.name
            if key_name.endswith(('_r', '_l')):
                key_name = key_name[:-2]
            return key_name

    def _normalize_hotkey(self, hotkey_str):
        """
        Normalizes a hotkey string for pynput, wrapping modifiers and special keys in <>.
        Example: 'Ctrl+A' -> '<ctrl>+a', 'f1' -> '<f1>'.
        """
        if not hotkey_str:
            return ""
        
        parts = {part.strip().lower() for part in hotkey_str.split('+') if part.strip()}
        
        modifiers = {'ctrl', 'alt', 'shift', 'cmd', 'alt_gr', 'win'} # Include 'alt_gr', 'win' for completeness
        # Add common special keys that pynput might expect in angle brackets
        special_keys = {
            'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12',
            'esc', 'insert', 'delete', 'home', 'end', 'page_up', 'page_down',
            'up', 'down', 'left', 'right', 'space', 'tab', 'enter', 'backspace',
            'caps_lock', 'num_lock', 'scroll_lock', 'print_screen', 'pause'
        }
        
        final_parts = []
        found_bracketed_keys = [] # For keys that need angle brackets
        found_other_keys = []    # For regular character keys

        for part in parts:
            if part in modifiers or part in special_keys:
                found_bracketed_keys.append(f"<{part}>")
            else:
                found_other_keys.append(part)
        
        # Sort for consistency
        found_bracketed_keys.sort()
        found_other_keys.sort()

        return "+".join(found_bracketed_keys + found_other_keys)

    def _is_hotkey_valid_for_pynput(self, hotkey_str: str) -> bool:
        """
        檢查快捷鍵字串是否為 pynput 可接受的有效格式。
        pynput 要求快捷鍵必須包含至少一個非修飾鍵。
        會先進行正規化，確保修飾鍵有尖括號包覆。
        """
        if not hotkey_str:
            return False
        
        # 先進行正規化，確保修飾鍵格式正確
        normalized_hotkey_str = self._normalize_hotkey(hotkey_str)
        
        # 移除尖括號，以便檢查是否包含非修飾鍵
        # pynput 的 parse 函數會將 'shift', 'ctrl', 'alt', 'alt_gr', 'win' 識別為修飾鍵
        modifier_keys_raw = {'shift', 'ctrl', 'alt', 'alt_gr', 'win'}
        
        parts = normalized_hotkey_str.replace('<', '').replace('>', '').split('+')
        has_non_modifier = any(part.lower() not in modifier_keys_raw for part in parts)
        
        # 確保至少有一個非修飾鍵且總部件數至少為1
        return has_non_modifier and len(parts) >= 1

    def _check_hotkey_conflict(self, hotkey_str, hotkey_type, index=None):
        """檢查指定的快捷鍵是否與現有的快捷鍵衝突。"""
        if not hotkey_str:
            return None

        normalized_hotkey = self._normalize_hotkey(hotkey_str)

        if hotkey_type != 'main' and self.current_hotkey:
            main_hotkey = self._normalize_hotkey(self.current_hotkey)
            if main_hotkey == normalized_hotkey:
                return f"此快捷鍵已被「快捷輸入框」使用。"

        for i, phrase in enumerate(self.quick_phrases):
            if hotkey_type == 'quick_phrase' and i == index:
                continue
            phrase_hotkey = self._normalize_hotkey(phrase.get("hotkey", ""))
            if phrase_hotkey == normalized_hotkey:
                phrase_text = phrase.get('text', '未命名')
                if len(phrase_text) > 10:
                    phrase_text = phrase_text[:10] + '...'
                return f"此快捷鍵已被快捷語音 {i+1} ({phrase_text}) 使用。"

        return None

    def _toggle_hotkey_edit(self, checked):
        btn = self.main_window.hotkey_edit_button
        if checked:
            self.log_message("進入快捷鍵編輯模式，請按下您想設定的組合鍵。")
            btn.setText("錄製中...")
            btn.setStyleSheet("background-color: #FF9500; color: white; font-weight: bold;")
            self._pressed_keys.clear()
            self._start_pynput_listener_for_main_hotkey()
        else:
            btn.setText("✏️ 編輯")
            btn.setStyleSheet("")
            if self._hotkey_recording_listener:
                self._hotkey_recording_listener.stop()
                self._hotkey_recording_listener = None

    def _start_pynput_listener_for_main_hotkey(self):
        from pynput import keyboard
        pressed = set()

        def on_press(key):
            key_str = self._key_to_str(key)
            if key_str:
                pressed.add(key_str)
                self._update_hotkey_display("+".join(sorted(list(pressed))))

        def on_release(key):
            modifiers = {'ctrl', 'alt', 'shift', 'cmd'}
            non_modifiers = [k for k in pressed if k not in modifiers]

            if not pressed or not non_modifiers:
                self.show_messagebox("無效的快捷鍵", "快捷鍵必須包含至少一個非修飾鍵 (例如 A, B, 1, 2)。", "warning")
                self._update_hotkey_display(self.current_hotkey)
                self.main_window.hotkey_edit_button.setChecked(False)
                return False

            hotkey_str = "+".join(sorted(list(pressed)))
            normalized_hotkey = self._normalize_hotkey(hotkey_str)

            conflict_msg = self._check_hotkey_conflict(normalized_hotkey, 'main')
            if conflict_msg:
                self.show_messagebox("快捷鍵衝突", conflict_msg, "warning")
                self._update_hotkey_display(self.current_hotkey)
            else:
                self.current_hotkey = normalized_hotkey
                self.config.set("hotkey", self.current_hotkey)
                self._update_hotkey_display(self.current_hotkey)
                self.log_message(f"快捷輸入框快捷鍵已更新為: {self.current_hotkey}")
                if self.is_running:
                    self._start_hotkey_listener()

            self.main_window.hotkey_edit_button.setChecked(False)
            return False

        if self._hotkey_recording_listener:
            self._hotkey_recording_listener.stop()
        self._hotkey_recording_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._hotkey_recording_listener.start()

    def _update_hotkey_display(self, hotkey_str):
        display_text = hotkey_str or "尚未設定"
        if self.main_window and self.main_window.hotkey_label:
            self.main_window.hotkey_label.setText(display_text)

    # ===================== 快速輸入框 =====================
    def _show_quick_input(self):
        self.signals.show_quick_input_signal.emit()

    def _show_quick_input_slot(self):
        if not self._input_window_lock.acquire(blocking=False): return
        try:
            if not self.quick_input_window:
                from ..ui.popups import QuickInputWindow
                self.quick_input_window = QuickInputWindow(self)

            win = self.quick_input_window
            win.adjustSize()
            screen_geometry = QApplication.primaryScreen().geometry()
            screen_width = screen_geometry.width()
            screen_height = screen_geometry.height()
            win_width = win.width()
            win_height = win.height()

            pos = self.quick_input_position
            margin = 30 # A small margin from screen edges
            if pos == "center":
                x = (screen_width - win_width) // 2
                y = (screen_height - win_height) // 2
            elif pos == "top-left":
                x = margin
                y = margin
            elif pos == "top-right":
                x = screen_width - win_width - margin
                y = margin
            elif pos == "bottom-left":
                x = margin
                y = screen_height - win_height - margin
            elif pos == "bottom-right":
                x = screen_width - win_width - margin
                y = screen_height - win_height - margin
            else: # Default to center
                x = (screen_width - win_width) // 2
                y = (screen_height - win_height) // 2
            
            win.move(x, y)

            win.show()
            win.activateWindow()
            win.raise_()
        finally:
            self._input_window_lock.release()

    def send_quick_input(self):
        if self.quick_input_window:
            text = self.quick_input_window.entry.text().strip()
            if text:
                if text in self.text_history: self.text_history.remove(text)
                self.text_history.appendleft(text)
                self.config.set("text_history", list(self.text_history))
                self.audio.play_text(text)
            self.quick_input_window.close()
    
    # ===================== 設定視窗 & 快捷語音 =====================
    def _open_settings_window(self):
        if self.main_window.stacked_layout.currentIndex() == 1: return
        settings_widget = SettingsWindow(self.main_window, self)
        self.main_window.show_overlay(settings_widget)

    def _open_quick_phrases_window(self):
        if self.main_window.stacked_layout.currentIndex() == 1: return
        while len(self.quick_phrases) < 10: self.quick_phrases.append({"text": "", "hotkey": ""})
        self.quick_phrases = self.quick_phrases[:10]
        phrases_widget = QuickPhrasesWindow(self.main_window, self)
        self.main_window.show_overlay(phrases_widget)

    def _open_model_management_window(self):
        if self.main_window.stacked_layout.currentIndex() == 1:
            return
        self.model_management_window = ModelManagementWindow(self.main_window, self)
        self.main_window.show_overlay(self.model_management_window)

    def _on_model_download_progress(self, model_id: str, progress: float, status_text: str):
        if self.model_management_window:
            self.model_management_window.update_download_progress(model_id, progress, status_text)

    def download_model(self, model_id):
        thread = threading.Thread(target=self._download_model_thread, args=(model_id,), daemon=True)
        thread.start()

    def _download_model_thread(self, model_id):
        if self.model_downloader.ensure_model(model_id):
            self.log_message(f"模型 {model_id} 已成功準備就緒。", "INFO")
            self.signals.update_ui_after_load.emit(model_id) # NEW: Signal with model_id to refresh UI
        else:
            self.log_message(f"模型 {model_id} 處理失敗。", "WARN")
        
        self._refresh_model_management_ui()

    def delete_model(self, model_id):
        thread = threading.Thread(target=self._delete_model_thread, args=(model_id,), daemon=True)
        thread.start()

    def _delete_model_thread(self, model_id):
        util_delete_model(model_id, log_cb=self.log_message)
        self._refresh_model_management_ui()

    def _refresh_model_management_ui(self):
        if self.main_window.stacked_layout.currentIndex() == 1:
            widget = self.main_window.overlay_layout.itemAt(0).widget()
            if isinstance(widget, ModelManagementWindow):
                QTimer.singleShot(0, widget.refresh_model_list)


    def _on_toggle_quick_phrases(self):
        self.enable_quick_phrases = self.main_window.quick_phrase_switch.isChecked()
        self.log_message(f"快捷語音功能已 {'啟用' if self.enable_quick_phrases else '停用'}")
        self.config.set("enable_quick_phrases", self.enable_quick_phrases)
        if self.is_running: self._start_hotkey_listener()
    
    def toggle_log_area(self, initial_load=False):
        is_expanded = self.config.get("show_log_area", True)
        if not initial_load:
            is_expanded = not is_expanded
            self.config.set("show_log_area", is_expanded)
        self.main_window.log_text.setVisible(is_expanded)
        self.main_window.log_toggle_button.setText("▼" if is_expanded else "▲")

    def on_closing(self):
        if self.hotkey_listener:
            try: self.hotkey_listener.stop() 
            except Exception: pass
        
        self.audio.stop()
        self.config.save() # NEW: Save config on exit
        QApplication.instance().quit()

    # --- Stubs for methods not fully shown ---
    def on_global_focus_changed(self, old, new): pass
    def handle_quick_input_history(self, entry, key): pass


    def _on_model_download_progress(self, model_id: str, progress: float, status_text: str):
        if self.model_management_window:
            self.model_management_window.update_download_progress(model_id, progress, status_text)
