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
    ENGINE_EDGE, ENGINE_PYTTX3, DEFAULT_EDGE_VOICE,
    DependencyManager, IS_WINDOWS
)
from .audio_engine import AudioEngine
from ..ui.popups import SettingsWindow, QuickPhrasesWindow
from ..ui.main_window import MainWindow
from .config_manager import ConfigManager
from ..ui.animation import AnimationManager
from .updater_manager import UpdateManager

class AppSignals(QObject):
    """定義應用程式中所有需要跨執行緒通訊的信號。"""
    log_message = pyqtSignal(str, str, str)
    audio_status = pyqtSignal(str, str, str)
    update_ui_after_load = pyqtSignal()
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

        # 狀態/設定
        # 音訊核心 (必須在 _build_ui 之前建立，以便 UI 取得初始值)
        self.audio = AudioEngine(self.log_message, self.audio_status_queue, startupinfo=self.startupinfo)
        self.updater = UpdateManager(self) # 建立更新管理器

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
        self.audio.set_engine(self.config.get("engine"))
        self.audio.edge_voice = self.config.get("voice")
        self.audio.tts_rate   = self.config.get("rate")
        self.audio.tts_volume = self.config.get("volume")
        self.audio.tts_pitch  = self.config.get("pitch", 0)
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
        # --- 核心修正: 過濾 DEBUG 等級的日誌，使其不在 UI 上顯示 ---
        if level.upper() == 'DEBUG':
            return

        log_widget = self.main_window.log_text
        cursor = log_widget.textCursor()

        if mode == "replace_last":
            # --- 最終修正: 穩定地取代最後一行內容 ---
            # 1. 移動游標到文件末尾
            cursor.movePosition(cursor.MoveOperation.End)
            # 2. 選取從行首到目前游標位置的全部內容 (即最後一行)
            cursor.movePosition(cursor.MoveOperation.StartOfBlock, cursor.MoveMode.KeepAnchor)
            # 3. 插入新文字，這會自動取代選取的內容，並保留區塊結構
            cursor.insertText(formatted_msg)
        else:
            log_widget.append(formatted_msg)

    def show_messagebox(self, title, message, msg_type="info", callback_or_event=None):
        """
        安全地從任何執行緒顯示訊息框。
        - 如果傳入 callback，則為非同步呼叫。
        - 如果傳入 (threading.Event, list)，則為同步呼叫，會阻塞直到使用者回應。
        """
        # 檢查是否為同步呼叫
        is_sync_call = isinstance(callback_or_event, tuple) and len(callback_or_event) == 2 and isinstance(callback_or_event[0], threading.Event)

        self.signals.show_messagebox_signal.emit(title, message, msg_type, callback_or_event)

        if is_sync_call:
            event, result_container = callback_or_event
            # 等待 UI 執行緒設定事件
            event.wait()
            # 從容器中取得結果
            return result_container[0] if result_container else False
        return None # 非同步呼叫沒有返回值
        
    def _show_messagebox_slot(self, title, message, msg_type, callback):
        """在主執行緒中安全地顯示訊息框的槽函式。"""
        msg_box = QMessageBox(self.main_window)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if msg_type == "info":
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.exec()
        elif msg_type == "warning":
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.exec()
        elif msg_type == "error":
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.exec()
        elif msg_type == "yesno":
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            result = msg_box.exec()
            user_choice = (result == QMessageBox.StandardButton.Yes)

            # 根據 callback 的類型決定是同步還是非同步
            is_sync_call = isinstance(callback, tuple) and len(callback) == 2 and isinstance(callback[0], threading.Event)
            if is_sync_call:
                # 同步模式：將結果存入容器並設定事件
                event, result_container = callback
                result_container.append(user_choice)
                event.set()
            elif callable(callback):
                # 非同步模式：直接呼叫回呼函式
                callback(result == QMessageBox.StandardButton.Yes)

    # ===================== 依賴流程 =====================
    def _dependency_flow_thread(self):
        if IS_WINDOWS and comtypes_installed:
            pythoncom.CoInitializeEx(0)

        self.log_message("開始檢查依賴...")
        dm = DependencyManager(
            log=lambda msg, level="INFO": self.log_message(msg, level),
            status=lambda icon, msg, level="INFO": self.signals.audio_status.emit(level, icon, msg),
            # --- 核心修正: 提供同步和非同步兩種提問方式 ---
            ask_yes_no_sync=lambda title, msg: self.show_messagebox(
                title, msg, "yesno",
                # 傳入一個 (Event, 容器) 元組來觸發同步模式
                (threading.Event(), [])
            ),
            ask_yes_no_async=lambda title, msg, cb: self.show_messagebox(
                title, msg, "yesno", cb
            ),
            show_info=lambda t, m: self.show_messagebox(t, m, "info"),
            show_error=lambda t, m: self.show_messagebox(t, m, "error"),
            startupinfo=self.startupinfo
        )
        if not dm.ensure_ffmpeg():
            return
        # 載入語音與裝置
        try:
            if dm.need_install_vbcable(self.audio.query_devices):
                self.log_message("未偵測到 VB-CABLE 驅動。準備啟動安裝程序引導...", "WARN")
                def have_setup(path):
                    self._prompt_run_vbcable_setup(path)
                def need_run(path):
                    self._prompt_run_vbcable_setup(path)
                # --- 修正: prepare_vbcable_setup 是非同步的，不應處理其返回值 ---
                # 它會透過 callback (have_setup/need_run) 來觸發 UI 行為。
                # 我們只需呼叫它，然後讓執行緒結束即可。UI 的後續操作由 callback 處理。
                dm.prepare_vbcable_setup(have_setup, need_run)
                return # 流程到此為止，等待使用者互動
            # 已存在 VB-CABLE，繼續
            self.audio.init_pyttsx3()
            import asyncio
            asyncio.run(self.audio.load_edge_voices())
            self.audio.load_devices()
            self.signals.update_ui_after_load.emit()
            self.log_message("依賴與設備載入完成。" )

            # --- 修正: 依賴載入完成後，啟用啟動按鈕 ---
            self.main_window.start_button.setEnabled(True)
            # ---------------------------------------------

            # 如果設定了自動啟動，則在此處觸發
            if self.config.get("auto_start_service"):
                QTimer.singleShot(100, self.start_local_player)

        except Exception as e:
            self.log_message(f"初始化錯誤: {e}", "ERROR")

    def _prompt_run_vbcable_setup(self, setup_path: str):
        def on_user_choice(do_install):
            if do_install:
                try:
                    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", setup_path, None, os.path.dirname(setup_path), 1)
                    if ret <= 32:
                        raise OSError(f"ShellExecuteW 啟動安裝程式失敗，錯誤碼: {ret}")
                    QTimer.singleShot(1000, self.on_closing)
                except Exception as e:
                    self.log_message(f"VB-CABLE 安裝執行錯誤: {e}", "ERROR")
            else:
                self.log_message("使用者取消了 VB-CABLE 安裝。", "WARN")

        self.show_messagebox(
            "VB-CABLE 安裝提示",
            "TTS 語音輸入 Discord 需要 VB-CABLE 驅動程式。\n\n"
            f"點擊 '是' 將啟動安裝程序，您可能需要授權管理員權限並點擊 'Install Driver'。\n\n"
            "安裝後，請重新啟動本應用程式。",
            msg_type='yesno',
            callback=on_user_choice)

    def _update_ui_after_load(self):
        # --- 核心重構: 根據 visible_voices 重新建立下拉選單 ---
        self._ui_loading = True # 防止觸發 change 事件

        current_engine = self.config.get("engine")
        self.main_window.engine_combo.setCurrentText(current_engine)

        # 建立完整的聲線字典 { "顯示名稱": 資料物件 }
        self.all_voices_map = {}
        if current_engine == ENGINE_EDGE:
            for v in self.audio.get_all_edge_voices():
                self.all_voices_map[v["ShortName"]] = v
            for v in self.config.get("custom_voices", []):
                self.all_voices_map[v["name"]] = v
        else: # pyttsx3
            for v in self.audio.get_voice_names():
                self.all_voices_map[v] = {"name": v, "engine": ENGINE_PYTTX3}

        # 根據 visible_voices 篩選要顯示的項目
        visible_voices_config = self.config.get("visible_voices", [])
        visible_voices = [name for name in visible_voices_config if name in self.all_voices_map]
        
        # 如果可見列表為空，則加入預設的
        if not visible_voices and self.all_voices_map:
            default_voice_name = list(self.all_voices_map.keys())[0]
            visible_voices.append(default_voice_name)

        self.main_window.voice_combo.clear()
        self.main_window.voice_combo.addItems(visible_voices)

        # 設定當前選項
        current_selection = self.config.get("voice")
        if current_selection in visible_voices:
            self.main_window.voice_combo.setCurrentText(current_selection)
        elif visible_voices:
            self.main_window.voice_combo.setCurrentText(visible_voices[0])

        self.main_window.voice_combo.setEnabled(True)
        # devices
        devnames = self.audio.get_output_device_names()
        self.main_window.local_device_combo.clear()
        self.main_window.local_device_combo.addItems(devnames)

        # --- 修正: 優先使用 audio_engine 自動偵測的結果 ---
        # audio_engine.load_devices 已經智慧地選擇了最佳設備 (VB-CABLE 或替代品)。
        # 我們應該直接使用這個結果來更新 UI，而不是從 config 載入舊的。
        # 只有在 audio_engine 的選擇無效時，才退回使用 config 或預設值。
        if self.audio.local_output_device_name in devnames:
            self.main_window.local_device_combo.setCurrentText(self.audio.local_output_device_name)
        
        self.main_window.local_device_combo.setEnabled(True)

        # 處理早期日誌
        if self._early_log_queue:
            for msg in self._early_log_queue:
                self.main_window.log_text.append(msg)
            self._early_log_queue.clear()
        
        # --- 核心修正: UI 載入完成，允許事件觸發 ---
        self._ui_loading = False

        # 觸發一次設定更新，以確保 UI 和 config 一致
        self.update_tts_settings()

    def _process_audio_status_queue(self):
        """從音訊執行緒的佇列中讀取狀態並更新 UI。"""
        try:
            while not self.audio_status_queue.empty():
                level, icon, message = self.audio_status_queue.get_nowait()
                self.signals.audio_status.emit(level, icon, message)
        except queue.Empty:
            pass

    def _audio_status_slot(self, level, icon, message):
        """在主執行緒中處理來自 audio_engine 的狀態更新。"""
        self.log_message(f"{icon} {message}", level, mode="replace_last")

    # ===================== 啟停與播放 =====================
    def start_local_player(self):
        if self.is_running:
            return
        if not self.audio.cable_is_present and "CABLE" in (self.audio.local_output_device_name or ""):
            # 仍未就緒
            self.show_messagebox("錯誤", "無法啟動：未偵測到 VB-CABLE 虛擬喇叭。", "error")
            self.log_message("無法啟動：未偵測到 VB-CABLE。", "ERROR")
            return
        self.is_running = True
        
        # --- 增強: 使用動畫進行狀態切換 ---
        self.main_window.status_label.setText("● 運行中")
        self.main_window.status_label.setStyleSheet(f"color: {self.main_window.STATUS_GREEN_COLOR}; font-weight: bold;")
        
        # 樣式由 QSS 的 :disabled 偽類自動處理
        self.main_window.start_button.setEnabled(False)
        self.main_window.stop_button.setEnabled(True)
        
        self._start_hotkey_listener()
        self.log_message("服務已啟動")

    def stop_local_player(self):
        if not self.is_running:
            return
        self.is_running = False
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            
        # --- 增強: 使用動畫進行狀態切換 ---
        self.main_window.status_label.setText("● 已停止")
        self.main_window.status_label.setStyleSheet(f"color: {self.main_window.STATUS_ORANGE_COLOR}; font-weight: bold;")

        # 樣式由 QSS 的 :disabled 偽類自動處理
        self.main_window.start_button.setEnabled(True)
        self.main_window.stop_button.setEnabled(False)
        self.log_message("服務已停止。" )

    def _start_hotkey_listener(self):
        try:
            if self.hotkey_listener:
                self.hotkey_listener.stop()
            hotkeys = {}
            if self.current_hotkey:
                hotkeys[self.current_hotkey] = self._show_quick_input
            if self.enable_quick_phrases:
                for phrase in self.quick_phrases:
                    hk = phrase.get("hotkey")
                    text = phrase.get("text")
                    if hk and text:
                        import functools
                        hotkeys[hk] = functools.partial(self._play_quick_phrase, text, phrase_info=phrase)
            self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
            self.hotkey_listener.start()
            self.log_message(f"服務已啟動，監聽 {len(hotkeys)} 個快捷鍵。" )
        except Exception as e:
            self.log_message(f"快捷鍵啟動失敗: {e}。請檢查格式或重啟應用。", "ERROR")

    def _play_quick_phrase(self, text, phrase_info=None):
        if not self.is_running:
            return

        # --- 快取播放邏輯 ---
        if phrase_info:
            # 根據當前設定產生預期的快取路徑
            cache_path = self.audio._get_cache_path(
                phrase_info.get("text"),
                self.audio.current_engine,
                self.audio.edge_voice if self.audio.current_engine == self.ENGINE_EDGE else self.audio.pyttsx3_voice_id,
                self.audio.tts_rate,
                self.audio.tts_pitch
            )
            if os.path.exists(cache_path):
                # --- 核心修正: 將快取路徑和原始文字一起傳遞 ---
                # 讓音訊引擎知道這是一個快取播放，並能顯示正確的文字
                self.audio.play_text((cache_path, text))
                return

        # 如果快取不存在，則退回即時合成
        self.audio.play_text(text)

    # ===================== 快捷鍵編輯 =====================
    def _key_to_str(self, key):
        if isinstance(key, keyboard.Key):
            return f"<{key.name.split('_')[0]}>"
        if isinstance(key, keyboard.KeyCode):
            if key.char:
                return key.char.lower()
        return None

    def _on_key_press(self, key):
        if self._recording_key_index is None:
            return False
        if key == keyboard.Key.esc or key in (keyboard.Key.delete, keyboard.Key.backspace):
            key_text = ""
        else:
            key_str = self._key_to_str(key)
            key_text = key_str.replace('<', '').replace('>', '').capitalize() if key_str else ""
        btn = self.main_window.hotkey_key_buttons[self._recording_key_index]
        btn.setText(key_text)
        self.log_message(f"第 {self._recording_key_index + 1} 個按鍵已設定為: {key_text or '無'}")
        self._recording_key_index = None
        return False

    def _prepare_single_key_recording(self, index):
        if not self._is_hotkey_edit_mode:
            return
        if self._recording_key_index is not None and self._recording_key_index != index:
            old_btn = self.main_window.hotkey_key_buttons[self._recording_key_index]
            old_btn.setStyleSheet("") # 恢復預設樣式
        self._recording_key_index = index
        btn = self.main_window.hotkey_key_buttons[index]
        btn.setText("...") # 提示使用者輸入
        if self._hotkey_recording_listener:
            self._hotkey_recording_listener.stop()
        self._hotkey_recording_listener = keyboard.Listener(on_press=self._on_key_press)
        self._hotkey_recording_listener.start()
        self.log_message(f"正在錄製第 {index+1} 個按鍵... (按 Esc 或 Delete 清除)")

    def _toggle_hotkey_edit(self):
        self._is_hotkey_edit_mode = not self._is_hotkey_edit_mode
        if self._is_hotkey_edit_mode:
            self.main_window.hotkey_edit_button.setText("✔ 完成")
            for btn in self.main_window.hotkey_key_buttons:
                btn.setEnabled(True)
            self.log_message("進入快捷鍵編輯模式。請點擊下方按鈕進行錄製。" )
            self.main_window.hotkey_info_label.setText("點擊按鍵區塊錄製單鍵，按 Esc 或 Delete 可清除。" )
        else:
            if self._hotkey_recording_listener:
                self._hotkey_recording_listener.stop()
                self._hotkey_recording_listener = None
            if self._recording_key_index is not None:
                btn = self.main_window.hotkey_key_buttons[self._recording_key_index]
                btn.setStyleSheet("") # 恢復預設樣式
                self._recording_key_index = None

            self.main_window.hotkey_edit_button.setText("✏️ 編輯")
            
            # 從按鈕文字構建新的快捷鍵字串
            parts = []
            for btn in self.main_window.hotkey_key_buttons:
                text = btn.text()
                if text:
                    lower_text = text.lower()
                    if lower_text in ['ctrl', 'alt', 'shift', 'cmd', 'win']:
                        parts.append(f"<{lower_text}>")
                    else:
                        parts.append(lower_text)
            new_hotkey = "+".join(parts)
            normalized_hotkey = self._normalize_hotkey(new_hotkey)

            # 衝突檢測
            conflict_msg = self._check_hotkey_conflict(normalized_hotkey, 'main')
            if conflict_msg:
                self.show_messagebox("快捷鍵衝突", conflict_msg, "warning")
                self._update_hotkey_display(self.current_hotkey) # 恢復顯示舊的快捷鍵
                return # 偵測到衝突，直接返回，不儲存

            for btn in self.main_window.hotkey_key_buttons:
                btn.setEnabled(False)
            self.main_window.hotkey_info_label.setText("點擊 '編輯' 開始設定快捷鍵。" )

            self.current_hotkey = self._normalize_hotkey(new_hotkey)
            self._update_hotkey_display(self.current_hotkey)
            if self.is_running:
                self._start_hotkey_listener()
            self.log_message(f"快捷鍵已儲存並鎖定為: {self.current_hotkey or '無'}")
            self.config.set("hotkey", self.current_hotkey)

    def _update_hotkey_display(self, hotkey_str):
        parts = hotkey_str.split('+') if hotkey_str else []
        for i, btn in enumerate(self.main_window.hotkey_key_buttons):
            if i < len(parts):
                text = parts[i].replace('<', '').replace('>', '').capitalize()
                btn.setText(text)
            else:
                btn.setText("")

    def _normalize_hotkey(self, hotkey_str):
        if not hotkey_str:
            return ""
        parts = hotkey_str.lower().split('+')
        modifiers = sorted([p for p in parts if p.startswith('<') and p.endswith('>')])
        normal_keys = sorted([p for p in parts if not (p.startswith('<') and p.endswith('>'))])
        return "+".join(modifiers + normal_keys)

    def _check_hotkey_conflict(self, new_hotkey, exclude_type, exclude_index=None, phrases_to_check=None):
        """
        檢查新的快捷鍵是否與現有的衝突。
        :param new_hotkey: 要檢查的快捷鍵字串。
        :param exclude_type: 'main' 或 'quick_phrase'，表示當前正在編輯哪種類型的快捷鍵。
        :param exclude_index: 如果是 'quick_phrase'，則是要排除的索引。
        :param phrases_to_check: (可選) 傳入一個快捷語音列表進行檢查，預設使用 self.quick_phrases。
        :return: 衝突訊息字串，或 None (無衝突)。
        """
        if not new_hotkey:
            return None

        # 檢查與主快捷鍵的衝突
        if exclude_type != 'main' and self.current_hotkey == new_hotkey:
            return f"與主快捷鍵 '{self.current_hotkey}' 衝突。"

        # 檢查與快捷語音的衝突
        phrase_list = phrases_to_check if phrases_to_check is not None else self.quick_phrases
        for i, phrase in enumerate(phrase_list):
            if exclude_type == 'quick_phrase' and i == exclude_index:
                continue
            if phrase.get("hotkey") == new_hotkey:
                return f"與快捷語音 {i + 1} ('{phrase.get('text', '')[:10]}...') 的快捷鍵衝突。"
        return None

    def on_global_focus_changed(self, old_widget, new_widget):
        """
        監聽全域焦點變化。當焦點從快捷輸入框轉移到應用程式外部時，
        關閉快捷輸入框。
        """
        # 檢查快捷輸入框是否存在且可見
        if self.quick_input_window and self.quick_input_window.isVisible():
            # `new_widget` 為 None 表示焦點轉移到了此應用程式之外
            if new_widget is None:
                # 檢查舊焦點是否在快捷輸入框內
                is_child = self.quick_input_window.isAncestorOf(old_widget) if old_widget else False
                if old_widget == self.quick_input_window or is_child:
                    self.log_message("快捷輸入框因失去焦點而關閉。", "DEBUG")
                    self.quick_input_window.close()

    # ===================== 快速輸入框 =====================
    def _show_quick_input(self):
        """從任何執行緒請求顯示快速輸入框。"""
        self.signals.show_quick_input_signal.emit()

    def _show_quick_input_slot(self):
        """在主執行緒中建立並顯示快速輸入框的槽函式。"""
        if not self._input_window_lock.acquire(blocking=False):
            self.log_message("無法獲取輸入視窗鎖，可能已有視窗正在開啟。", "DEBUG")
            return

        try:
            # --- 核心修正: 修正縮排與邏輯 ---
            if self.quick_input_window: # 檢查參照是否存在
                # 如果視窗已存在，只需將其帶到最前
                self.log_message("偵測到現有輸入視窗，將其帶到最前。", "DEBUG")
                self.quick_input_window.show()
                self.quick_input_window.activateWindow()
                self.quick_input_window.raise_()
            else:
                # 如果視窗不存在，則建立新視窗
                self.log_message("建立新的輸入視窗。", "DEBUG")
                # 延遲匯入以避免循環依賴
                from ..ui.popups import QuickInputWindow
                
                win = QuickInputWindow(self, parent=self.main_window)
                self.quick_input_window = win # 在顯示前就設定好參照

                screen = QApplication.primaryScreen().geometry()
                screen_w, screen_h = screen.width(), screen.height()
                w, h = 420, 42

                pos = self.quick_input_position
                if pos == "center":
                    x = (screen_w - w) // 2; y = (screen_h - h) // 2
                elif pos == "top-left":
                    x = 20; y = 40
                elif pos == "top-right":
                    x = screen_w - w - 20; y = 40
                elif pos == "bottom-left":
                    x = 20; y = screen_h - h - 40
                else: # bottom-right
                    x = screen_w - w - 20; y = screen_h - h - 40

                win.setGeometry(x, y, w, h)
                win.show()
                win.activateWindow()
                win.raise_()
        finally:
            # 確保鎖總是被釋放
            self._input_window_lock.release()
            self.log_message("已釋放輸入視窗鎖。", "DEBUG")
    def handle_quick_input_history(self, entry, key):
        if not self.text_history:
            return

        if key == Qt.Key.Key_Up:
            self.quick_input_window.history_index += 1
        elif key == Qt.Key.Key_Down:
            self.quick_input_window.history_index -= 1
        else:
            return

        # 限制索引範圍
        idx = self.quick_input_window.history_index
        idx = max(-1, min(idx, len(self.text_history) - 1))
        self.quick_input_window.history_index = idx

        if idx != -1:
            entry.setText(self.text_history[idx])
        else:
            entry.clear()

    def send_quick_input(self):
        if self.quick_input_window:
            text = self.quick_input_window.entry.text().strip()
            if text:
                # 如果文字已存在，先移除舊的
                if text in self.text_history:
                    self.text_history.remove(text)
                # 將新文字加到最前面
                self.text_history.appendleft(text)
                self.config.set("text_history", list(self.text_history))
                self.audio.play_text(text)
            self.quick_input_window.close_window()

    # ===================== 設定視窗 & 快捷語音 =====================
    def _open_settings_window(self):
        # 檢查覆蓋層是否已經有內容
        if self.main_window.overlay_layout.count() > 0:
            return # 如果已經有東西，就不再開啟
        settings_widget = SettingsWindow(self.main_window, self)
        self.main_window.show_overlay(settings_widget)

    def _open_quick_phrases_window(self):
        if self.main_window.overlay_layout.count() > 0:
            return # 如果已經有東西，就不再開啟

        while len(self.quick_phrases) < 10:
            self.quick_phrases.append({"text": "", "hotkey": ""})
        self.quick_phrases = self.quick_phrases[:10]

        phrases_widget = QuickPhrasesWindow(self.main_window, self)
        self.main_window.show_overlay(phrases_widget)

    def _open_voice_selection_window(self):
        if self.main_window.overlay_layout.count() > 0:
            return
        from ..ui.popups import VoiceSelectionWindow
        voice_widget = VoiceSelectionWindow(self.main_window, self)
        self.main_window.show_overlay(voice_widget)

    def _on_toggle_quick_phrases(self):
        """當主視窗的快捷語音開關被切換時呼叫。"""
        self.enable_quick_phrases = self.main_window.quick_phrase_switch.isChecked()
        self.log_message(f"快捷語音功能已 {'啟用' if self.enable_quick_phrases else '停用'}")
        self.config.set("enable_quick_phrases", self.enable_quick_phrases)
        if self.is_running:
            self._start_hotkey_listener()

    def toggle_log_area(self, initial_load=False):
        """
        切換日誌區域的顯示/隱藏狀態。
        :param initial_load: 如果是程式初次載入，則只根據設定更新UI，不反轉狀態。
        """
        is_expanded = self.config.get("show_log_area", True)

        if not initial_load:
            is_expanded = not is_expanded
            self.config.set("show_log_area", is_expanded)

        if is_expanded:
            self.main_window.log_text.show()
            self.main_window.log_toggle_button.setText("▼")
            self.main_window.resize(self.main_window.width(), 890) # 展開後的高度
        else:
            self.main_window.log_text.hide()
            self.main_window.log_toggle_button.setText("▲")
            self.main_window.resize(self.main_window.width(), 610) # 收合後的高度

    # ===================== 其它事件 =====================
    def _on_engine_change(self, val):
        self.audio.set_engine(val)
        self.log_message(f"切換引擎: {self.audio.current_engine}")
        # 更新 voices
        if val == ENGINE_EDGE:
            self.main_window.pitch_slider.setEnabled(True)
            values = self.audio.get_voice_names()
            self.main_window.voice_combo.clear()
            self.main_window.voice_combo.addItems(values)
            self.main_window.voice_combo.setCurrentText(self.audio.edge_voice if self.audio.edge_voice in values else values[0])
        else:
            self.main_window.pitch_slider.setEnabled(False)
            names = self.audio.get_voice_names()
            self.main_window.voice_combo.clear()
            self.main_window.voice_combo.addItems(names)
            # 載入 pyttsx3 時，可能需要設定預設語音
            loaded_name = self.config.get("voice")
            self.main_window.voice_combo.setCurrentText(loaded_name if loaded_name in names else (names[0] if names else "default"))
        self.config.set("engine", val)

    def _on_voice_change(self, choice):
        if not choice or self._ui_loading: # 如果正在載入或選項為空，則不執行
            return
        
        # --- 核心重構: 處理自訂語音 ---
        voice_data = self.all_voices_map.get(choice)
        if not voice_data:
            self.log_message(f"錯誤：找不到名為 '{choice}' 的語音資料。", "ERROR")
            return

        # 判斷是否為自訂語音
        if voice_data.get("engine") == ENGINE_EDGE and "base_voice" in voice_data:
            # 是自訂語音，套用其設定
            self.audio.set_edge_voice(voice_data["base_voice"])
            self.main_window.speed_slider.setValue(voice_data["rate"])
            # --- 修正: 增加音量設定 ---
            self.main_window.volume_slider.setValue(int(voice_data.get("volume", 1.0) * 100))
            self.main_window.pitch_slider.setValue(voice_data.get("pitch", 0)) # 使用 .get 增加安全性
            self.update_tts_settings()
        else:
            # 是原始語音
            if self.audio.current_engine == ENGINE_EDGE:
                self.audio.set_edge_voice(voice_data["ShortName"])
            else:
                self.audio.set_pyttsx3_voice_by_name(voice_data["name"])
        
        self.config.set("voice", choice)
        self.log_message(f"當前語音已設定為: {choice}")

    def _on_local_device_change(self, device_name):
        """當輸出設備變更時呼叫。"""
        # 增加保護，防止在 UI 載入過程中觸發不必要的儲存
        if self._ui_loading:
            return

        if not device_name: # 忽略 UI 初始化時的空信號
            return
        self.audio.local_output_device_name = device_name
        self.log_message(f"主輸出設備已變更為: {device_name}")
        self.config.set("local_output_device_name", device_name)

    def update_tts_settings(self, _=None):
        # --- 核心修正: 防止在 UI 載入過程中觸發 ---
        if self._ui_loading:
            return

        self.audio.tts_rate = self.main_window.speed_slider.value()
        self.audio.tts_volume = round(self.main_window.volume_slider.value() / 100.0, 2)
        self.audio.tts_pitch = self.main_window.pitch_slider.value()
        self.main_window.speed_value_label.setText(f"{self.audio.tts_rate}")
        self.main_window.volume_value_label.setText(f"{self.audio.tts_volume:.2f}")
        self.main_window.pitch_value_label.setText(f"{self.audio.tts_pitch}")
        self.config.set("rate", self.audio.tts_rate)
        self.config.set("volume", self.audio.tts_volume)
        self.config.set("pitch", self.audio.tts_pitch)

    def on_closing(self):
        if self.hotkey_listener:
            try: self.hotkey_listener.stop() 
            except Exception: pass
        
        self.audio.stop() # 優雅地停止音訊工作執行緒        
        QApplication.instance().quit()
