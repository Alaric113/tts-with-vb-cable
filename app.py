# -*- coding: utf-8 -*-
# 檔案: app.py
# 功用: 定義主應用程式 LocalTTSPlayer 類別，為程式的核心 UI 與事件處理中心。
#      - 使用 customtkinter 建構所有使用者介面元素。
#      - 管理應用程式的啟動、停止、關閉等生命週期。
#      - 處理所有 UI 事件，如按鈕點擊、滑桿調整、選項變更。
#      - 實現主快捷鍵與快捷語音的錄製、監聽與觸發邏輯 (使用 pynput)。
#      - 管理設定的載入與儲存 (config.json)。
#      - 顯示日誌訊息、下載進度等狀態。
#      - 創建並管理「設定」、「快捷語音」和「快速輸入」等彈出視窗。
#      - 協調 UI 操作與 audio_engine 和 utils_deps 模組的功能調用。

import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox
import ctypes

import customtkinter as ctk
from pynput import keyboard
import sounddevice as sd

# 可選 Windows 依賴
try:
    import comtypes.client  # noqa: F401
    from comtypes import CLSCTX_ALL  # noqa: F401
    comtypes_installed = True
except Exception:
    comtypes_installed = False
try:
    import win32gui
    import win32con
    import win32api
    pywin32_installed = True
except ImportError:
    pywin32_installed = False

from utils_deps import (
    SCRIPT_DIR, CONFIG_FILE,
    CABLE_INPUT_HINT, CABLE_OUTPUT_HINT,
    ENGINE_EDGE, ENGINE_PYTTX3, DEFAULT_EDGE_VOICE,
    DependencyManager, IS_WINDOWS
)
from audio_engine import AudioEngine
from ui.popups import SettingsWindow, QuickPhrasesWindow
from ui.main_window import build_main_window_ui
from config_manager import ConfigManager

class LocalTTSPlayer:
    def __init__(self):
        # 狀態/設定
        self.config = ConfigManager(self.log_message)
        # 音訊核心 (必須在 _build_ui 之前建立，以便 UI 取得初始值)
        self.audio = AudioEngine(self.log_message, self._log_playback_status)

        self.is_running = False

        # UI/其他
        self.current_hotkey = self.config.get("hotkey")
        self.quick_phrases = self.config.get("quick_phrases")
        self.quick_input_position = self.config.get("quick_input_position")
        self.enable_quick_phrases = self.config.get("enable_quick_phrases")

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

        # 先顯示主視窗
        ctk.set_appearance_mode("System")
        self._build_ui()

        self.audio.start() # UI 建立完成後，再啟動音訊背景執行緒
        # 載入設定
        self.audio.set_engine(self.config.get("engine"))
        self.audio.edge_voice = self.config.get("voice")
        self.audio.tts_rate   = self.config.get("rate")
        self.audio.tts_volume = self.config.get("volume")
        self.audio.set_listen_config(self.config.get("enable_listen_to_self"), self.config.get("listen_device_name"), self.config.get("listen_volume"))

        self._update_hotkey_display(self.config.get("hotkey"))

        # 依賴流程（先 Log，再詢問）
        self.root.after(100, lambda: threading.Thread(target=self._dependency_flow_thread, daemon=True).start())

    # ===================== UI 建構 =====================
    def _build_ui(self):
        """
        將 UI 建構邏輯委派給 ui.main_window 模組。
        """
        build_main_window_ui(self)

    # ===================== Log 與進度 =====================
    def _toggle_download_ui(self, show: bool):
        def upd():
            try:
                if show:
                    self.download_bar.grid()
                    self.download_label.configure(text="[----------] 0.0% | 下載準備中…")
                    self.download_bar.master.tkraise()
                else:
                    self.download_bar.master.grid_remove()
            except Exception:
                pass
        self.root.after(0, upd)

    def _update_download_ui(self, progress: float, text: str):
        def upd():
            try:
                p = max(0.0, min(1.0, progress))
                self.download_bar.set(p)
                bar_len = 20
                filled_len = int(bar_len * p)
                bar = '█' * filled_len + '-' * (bar_len - filled_len)
                progress_text = f"[{bar}] {p*100:5.1f}% | {text}"
                self.download_label.configure(text=progress_text)
            except Exception:
                pass
        self.root.after(0, upd)

    def log_message(self, msg, level="INFO"):
        def upd():
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_msg = f"[{timestamp}] [{level.upper():<5}] {msg}\n"
            self.log_text.configure(state="normal")
            self.log_text.insert(tk.END, formatted_msg)
            self.log_text.see(tk.END)
            self.log_text.configure(state="disabled")
        self.root.after(0, upd)

    def _log_playback_status(self, status_icon, message):
        def upd():
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_msg = f"[{timestamp}] [PLAY ] {status_icon} {message}\n"
            self.log_text.configure(state="normal")
            self.log_text.delete("end-2c linestart", "end-1c")
            self.log_text.insert(tk.END, formatted_msg)
            self.log_text.see(tk.END)
            self.log_text.configure(state="disabled")
        self.root.after(0, upd)

    def _log_status_update(self, status_icon, message, level="INFO"):
        def upd():
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_msg = f"[{timestamp}] [{level.upper():<5}] {status_icon} {message}\n"
            self.log_text.configure(state="normal")
            if self.log_text.get("1.0", "end-1c").strip():
                self.log_text.delete("end-2c linestart", "end-1c")
            self.log_text.insert(tk.END, formatted_msg)
            self.log_text.see(tk.END)
            self.log_text.configure(state="disabled")
        self.root.after(0, upd)

    # ===================== 依賴流程 =====================
    def _dependency_flow_thread(self):
        self.log_message("開始檢查依賴...")
        dm = DependencyManager(
            log=self.log_message,
            status=self._log_status_update,
            ask_yes_no=messagebox.askyesno,
            show_info=messagebox.showinfo,
            show_error=messagebox.showerror
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
                self.root.after(0, lambda: dm.prepare_vbcable_setup(have_setup, need_run))
                return
            # 已存在 VB-CABLE，繼續
            self.audio.init_pyttsx3()
            import asyncio
            asyncio.run(self.audio.load_edge_voices())
            self.audio.load_devices()
            self.root.after(0, self._update_ui_after_load)
            self.log_message("依賴與設備載入完成。" )
        except Exception as e:
            self.log_message(f"初始化錯誤: {e}", "ERROR")

    def _prompt_run_vbcable_setup(self, setup_path: str):
        result = messagebox.askyesno(
            "VB-CABLE 安裝提示",
            "TTS 語音輸入 Discord 需要 VB-CABLE 驅動程式。\n\n"
            f"點擊 '是' 將啟動安裝程序，您可能需要授權管理員權限並點擊 'Install Driver'。\n\n"
            "安裝後，請重新啟動本應用程式。",
            icon='info'
        )
        if result:
            try:
                ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", setup_path, None, os.path.dirname(setup_path), 1)
                if ret <= 32:
                    raise OSError(f"ShellExecuteW 啟動安裝程式失敗，錯誤碼: {ret}")
                self.root.after(1000, self.on_closing)
            except Exception as e:
                self.log_message(f"VB-CABLE 安裝執行錯誤: {e}", "ERROR")
        else:
            self.log_message("使用者取消了 VB-CABLE 安裝。", "WARN")

    def _update_ui_after_load(self):
        self.engine_combo.set(self.audio.current_engine)
        self.speed_slider.set(self.audio.tts_rate)
        self.volume_slider.set(self.audio.tts_volume)
        # voices
        if self.audio.current_engine == ENGINE_EDGE:
            values = self.audio.get_voice_names()
            self.voice_combo.configure(values=values)
            self.voice_combo.set(self.audio.edge_voice if self.audio.edge_voice in values else DEFAULT_EDGE_VOICE)
        else:
            names = self.audio.get_voice_names()
            self.voice_combo.configure(values=names)
            loaded_name = self.config.get("voice")
            self.voice_combo.set(loaded_name if loaded_name in names else (names[0] if names else "default"))
        # devices
        devnames = self.audio.get_output_device_names()
        self.local_device_combo.configure(values=devnames)
        if self.audio.local_output_device_name not in devnames:
            self.audio.local_output_device_name = devnames[0] if devnames else "Default"
        self.local_device_combo.set(self.audio.local_output_device_name)

    # ===================== 啟停與播放 =====================
    def start_local_player(self):
        if self.is_running:
            return
        if not self.audio.cable_is_present and "CABLE" in (self.audio.local_output_device_name or ""):
            # 仍未就緒
            messagebox.showerror("錯誤", "無法啟動：未偵測到 VB-CABLE 虛擬喇叭。")
            self.log_message("無法啟動：未偵測到 VB-CABLE。", "ERROR")
            return
        self.is_running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_label.configure(text="狀態: 運行中", text_color="green")
        self._start_hotkey_listener()
        self.log_message("服務已啟動")

    def stop_local_player(self):
        if not self.is_running:
            return
        self.is_running = False
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status_label.configure(text="● 已停止", text_color=["#D32F2F", "#FF5252"])
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
                        hotkeys[hk] = functools.partial(self._play_quick_phrase, text)
            self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
            self.hotkey_listener.start()
            self.log_message(f"服務已啟動，監聽 {len(hotkeys)} 個快捷鍵。" )
        except Exception as e:
            self.log_message(f"快捷鍵啟動失敗: {e}。請檢查格式。", "ERROR")

    def _play_quick_phrase(self, text):
        if not self.is_running:
            return
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
        btn = self.hotkey_key_buttons[self._recording_key_index]
        btn.configure(text=key_text, fg_color=('#EAEAEA', '#4A4A4A'))
        self.log_message(f"第 {self._recording_key_index + 1} 個按鍵已設定為: {key_text or '無'}")
        self._recording_key_index = None
        return False

    def _prepare_single_key_recording(self, index):
        if not self._is_hotkey_edit_mode:
            return
        if self._recording_key_index is not None and self._recording_key_index != index:
            old_btn = self.hotkey_key_buttons[self._recording_key_index]
            old_btn.configure(fg_color=('#EAEAEA', '#4A4A4A'))
        self._recording_key_index = index
        btn = self.hotkey_key_buttons[index]
        btn.configure(text="...", fg_color="#FFA726")
        if self._hotkey_recording_listener:
            self._hotkey_recording_listener.stop()
        self._hotkey_recording_listener = keyboard.Listener(on_press=self._on_key_press)
        self._hotkey_recording_listener.start()
        self.log_message(f"正在錄製第 {index+1} 個按鍵... (按 Esc 或 Delete 清除)")

    def _toggle_hotkey_edit(self):
        self._is_hotkey_edit_mode = not self._is_hotkey_edit_mode
        if self._is_hotkey_edit_mode:
            self.hotkey_edit_button.configure(text="✅ 完成", fg_color="#FFA726", hover_color="#FB8C00")
            for btn in self.hotkey_key_buttons:
                btn.configure(state="normal")
            self.log_message("進入快捷鍵編輯模式。請點擊下方按鈕進行錄製。" )
            self.hotkey_info_label.configure(text="點擊按鍵區塊錄製單鍵，按 Esc 或 Delete 可清除。" )
        else:
            if self._hotkey_recording_listener:
                self._hotkey_recording_listener.stop()
                self._hotkey_recording_listener = None
            if self._recording_key_index is not None:
                btn = self.hotkey_key_buttons[self._recording_key_index]
                btn.configure(fg_color=('#EAEAEA', '#4A4A4A'))
                self._recording_key_index = None
            self.hotkey_edit_button.configure(text="✏️ 編輯", fg_color=self.BTN_COLOR, hover_color=self.BTN_HOVER_COLOR)
            for btn in self.hotkey_key_buttons:
                btn.configure(state="disabled")
            self.hotkey_info_label.configure(text="點擊 '編輯' 開始設定快捷鍵。" )
            parts = []
            for btn in self.hotkey_key_buttons:
                text = btn.cget("text")
                if text:
                    lower_text = text.lower()
                    if lower_text in ['ctrl', 'alt', 'shift', 'cmd', 'win']:
                        parts.append(f"<{lower_text}>")
                    else:
                        parts.append(lower_text)
            new_hotkey = "+".join(parts)
            self.current_hotkey = self._normalize_hotkey(new_hotkey)
            self._update_hotkey_display(self.current_hotkey)
            if self.is_running:
                self._start_hotkey_listener()
            self.log_message(f"快捷鍵已儲存並鎖定為: {self.current_hotkey or '無'}")
            self.config.set("hotkey", self.current_hotkey)

    def _update_hotkey_display(self, hotkey_str):
        parts = hotkey_str.split('+') if hotkey_str else []
        for i, btn in enumerate(self.hotkey_key_buttons):
            if i < len(parts):
                text = parts[i].replace('<', '').replace('>', '').capitalize()
                btn.configure(text=text)
            else:
                btn.configure(text="")

    def _normalize_hotkey(self, hotkey_str):
        if not hotkey_str:
            return ""
        parts = hotkey_str.lower().split('+')
        modifiers = sorted([p for p in parts if p.startswith('<') and p.endswith('>')])
        normal_keys = sorted([p for p in parts if not (p.startswith('<') and p.endswith('>'))])
        return "+".join(modifiers + normal_keys)

    # ===================== 快速輸入框 =====================
    def _show_quick_input(self):
        if not self._input_window_lock.acquire(blocking=False):
            return
        if self.quick_input_window and self.quick_input_window.winfo_exists():
            try:
                self.quick_input_window.lift()
                self.quick_input_window.focus_force()
            finally:
                if self._input_window_lock.locked():
                    self._input_window_lock.release()
            return

        win = ctk.CTkToplevel(self.root)
        win.overrideredirect(True)
        def force_foreground_and_focus(target_win):
            if not pywin32_installed or not target_win.winfo_exists():
                target_win.lift(); target_win.focus_force(); return
            try:
                hwnd = target_win.winfo_id()
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                target_win.lift(); target_win.focus_force()

        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.95)

        w, h = 420, 38
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        pos = self.quick_input_position
        if pos == "center":
            x = (screen_w - w) // 2; y = (screen_h - h) // 2
        elif pos == "top-left":
            x = 20; y = 50
        elif pos == "top-right":
            x = screen_w - w - 20; y = 50
        elif pos == "bottom-left":
            x = 20; y = screen_h - h - 50
        else:
            x = screen_w - w - 20; y = screen_h - h - 50

        win.geometry(f"{w}x{h}+{x}+{y}")
        entry = ctk.CTkEntry(win, font=("Arial", 14), height=h)
        entry.pack(fill="both", expand=True, padx=2, pady=2)

        def on_destroy(event=None):
            if self._input_window_lock.locked():
                self._input_window_lock.release()

        def close_if_focus_lost(event=None):
            def _check():
                if not win.winfo_exists():
                    return
                focused_widget = win.focus_get()
                if focused_widget is None or focused_widget.winfo_toplevel() is not win:
                    win.destroy()
            win.after(100, _check)

        def secure_focus():
            try:
                if not win.winfo_exists():
                    on_destroy(); return
                entry.focus_set(); entry.select_range(0, tk.END)
            except Exception as e:
                self.log_message(f"Focus attempt failed: {e}", "ERROR")

        win.after(10, lambda: force_foreground_and_focus(win))
        win.after(20, secure_focus)

        def send(event=None):
            text = entry.get().strip()
            if text:
                self.audio.play_text(text)
            win.destroy()

        entry.bind("<Return>", send)
        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<FocusOut>", close_if_focus_lost)
        win.bind("<Destroy>", on_destroy)

        self.quick_input_window = win

    # ===================== 設定視窗 & 快捷語音 =====================
    def _open_settings_window(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.focus()
            return
        self.settings_window = SettingsWindow(self.root, self)

    def _open_quick_phrases_window(self):
        if self.quick_phrases_window and self.quick_phrases_window.winfo_exists():
            self.quick_phrases_window.focus()
            return

        while len(self.quick_phrases) < 10:
            self.quick_phrases.append({"text": "", "hotkey": ""})
        self.quick_phrases = self.quick_phrases[:10]

        self.quick_phrases_window = QuickPhrasesWindow(self.root, self)

    # ===================== 其它事件 =====================
    def _on_engine_change(self, val):
        self.audio.set_engine(val)
        self.log_message(f"切換引擎: {self.audio.current_engine}")
        # 更新 voices
        if self.audio.current_engine == ENGINE_EDGE:
            values = self.audio.get_voice_names()
            self.voice_combo.configure(values=values)
            self.voice_combo.set(self.audio.edge_voice if self.audio.edge_voice in values else values[0])
        else:
            names = self.audio.get_voice_names()
            self.voice_combo.configure(values=names)
        self.config.set("engine", val)

    def _on_voice_change(self, choice):
        if self.audio.current_engine == ENGINE_EDGE:
            self.audio.set_edge_voice(choice)
        else:
            self.audio.set_pyttsx3_voice_by_name(choice)
        self.log_message(f"試聽語音: {choice}", "DEBUG")
        self.audio.preview_text("你好") # 試聽
        self.config.set("voice", choice)

    def update_tts_settings(self, _=None):
        self.audio.tts_rate = int(self.speed_slider.get())
        self.audio.tts_volume = round(self.volume_slider.get(), 2)
        self.speed_value_label.configure(text=f"{self.audio.tts_rate}")
        self.volume_value_label.configure(text=f"{self.audio.tts_volume:.2f}")
        self.config.set("rate", self.audio.tts_rate) # 自動儲存
        self.config.set("volume", self.audio.tts_volume) # 自動儲存

    def on_closing(self):
        if self.hotkey_listener:
            try: self.hotkey_listener.stop() 
            except Exception: pass
        
        self.audio.stop() # 優雅地停止音訊工作執行緒

        if self.quick_input_window and self.quick_input_window.winfo_exists():
            self.quick_input_window.destroy()
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
        if self.quick_phrases_window and self.quick_phrases_window.winfo_exists():
            self.quick_phrases_window.destroy()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
