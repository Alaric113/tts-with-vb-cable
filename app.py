# -*- coding: utf-8 -*-
# app.py — UI / 事件流程（LocalTTSPlayer）

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

class LocalTTSPlayer:
    def __init__(self):
        # 狀態/設定
        self._config = {}
        self.is_running = False

        # 音訊核心
        self.audio = AudioEngine(self.log_message, self._log_playback_status)

        # UI/其他
        self.current_hotkey = "+z"
        self.quick_phrases = []
        self.quick_input_position = "bottom-right"
        self.enable_quick_phrases = True

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

        # 載入設定
        self._load_config()
        self.audio.set_engine(self._config.get("engine", ENGINE_EDGE))
        self.audio.edge_voice = self._config.get("voice", DEFAULT_EDGE_VOICE)
        self.audio.tts_rate   = self._config.get("rate", 175)
        self.audio.tts_volume = self._config.get("volume", 1.0)
        self.quick_phrases = self._config.get("quick_phrases", [])
        self.quick_input_position = self._config.get("quick_input_position", "bottom-right")
        self.enable_quick_phrases = self._config.get("enable_quick_phrases", True)
        self.audio.enable_listen_to_self = self._config.get("enable_listen_to_self", False)
        self.audio.listen_device_name = self._config.get("listen_device_name", "Default")
        self.audio.listen_volume = self._config.get("listen_volume", 1.0)

        self.current_hotkey = self._normalize_hotkey(self._config.get("hotkey", "<shift>+z"))
        self._update_hotkey_display(self.current_hotkey)

        # 依賴流程（先 Log，再詢問）
        threading.Thread(target=self._dependency_flow_thread, daemon=True).start()

    # ===================== UI 建構 =====================
    def _build_ui(self):
        self.root = ctk.CTk()
        self.root.title("橘Mouth - TTS 語音助手")
        self.root.geometry("680x720")
        self.root.resizable(False, False)

        CORNER_RADIUS = 12
        PAD_X = 20
        PAD_Y = 10
        FG_COLOR = ("#FFFFFF", "#333333")
        self.BORDER_COLOR = ("#E0E0E0", "#404040")
        self.BTN_COLOR = "#708090"
        self.BTN_HOVER_COLOR = "#5D6D7E"

        self.root.grid_rowconfigure(6, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        ctrl = ctk.CTkFrame(self.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=1)
        ctrl.grid(row=0, column=0, sticky="ew", padx=PAD_X, pady=(20, PAD_Y))

        self.start_button = ctk.CTkButton(ctrl, text="▶ 啟動", command=self.start_local_player, corner_radius=CORNER_RADIUS, fg_color=self.BTN_COLOR, hover_color=self.BTN_HOVER_COLOR)
        self.start_button.grid(row=0, column=0, padx=15, pady=15)
        self.stop_button = ctk.CTkButton(ctrl, text="■ 停止", command=self.stop_local_player, state="disabled", fg_color="#D32F2F", hover_color="#B71C1C", corner_radius=CORNER_RADIUS)
        self.stop_button.grid(row=0, column=1, padx=15, pady=15)

        spacer = ctk.CTkLabel(ctrl, text="")
        spacer.grid(row=0, column=2, sticky="ew")
        ctrl.grid_columnconfigure(2, weight=1)

        self.quick_phrase_button = ctk.CTkButton(ctrl, text="快捷語音", command=self._open_quick_phrases_window, corner_radius=CORNER_RADIUS, fg_color=self.BTN_COLOR, hover_color=self.BTN_HOVER_COLOR)
        self.quick_phrase_button.grid(row=0, column=3, padx=(0, 10), pady=15)
        self.settings_button = ctk.CTkButton(ctrl, text="⚙️", command=self._open_settings_window, width=40, corner_radius=CORNER_RADIUS, fg_color=self.BTN_COLOR, hover_color=self.BTN_HOVER_COLOR)
        self.settings_button.grid(row=0, column=4, padx=(0, 15), pady=15)

        self.status_label = ctk.CTkLabel(ctrl, text="● 未啟動", text_color=["#D32F2F", "#FF5252"], font=ctk.CTkFont(size=14, weight="bold"))
        self.status_label.grid(row=0, column=5, padx=20, sticky="e")

        out = ctk.CTkFrame(self.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=1)
        out.grid(row=1, column=0, sticky="ew", padx=PAD_X, pady=PAD_Y)
        ctk.CTkLabel(out, text="輸出設備:", anchor="w").grid(row=0, column=0, padx=15, pady=10, sticky="w")
        self.local_device_combo = ctk.CTkOptionMenu(out, values=["Default"], corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, button_color=self.BTN_COLOR, button_hover_color=self.BTN_HOVER_COLOR)
        self.local_device_combo.set("Default")
        self.local_device_combo.configure(state="disabled")
        self.local_device_combo.grid(row=0, column=1, sticky="ew", padx=15, pady=10)
        ctk.CTkLabel(out, text=f"💡 Discord 麥克風請設定為: {CABLE_INPUT_HINT}", text_color=["#007BFF", "#1E90FF"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=1, column=0, columnspan=2, padx=15, pady=(5, 10), sticky="w")
        out.grid_columnconfigure(1, weight=1)

        sel = ctk.CTkFrame(self.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=1)
        sel.grid(row=2, column=0, sticky="ew", padx=PAD_X, pady=PAD_Y)
        ctk.CTkLabel(sel, text="TTS 引擎:").grid(row=0, column=0, padx=15, pady=10, sticky="w")
        self.engine_combo = ctk.CTkOptionMenu(sel, values=[ENGINE_EDGE, ENGINE_PYTTX3], command=self._on_engine_change, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, button_color=self.BTN_COLOR, button_hover_color=self.BTN_HOVER_COLOR)
        self.engine_combo.set(self.audio.current_engine)
        self.engine_combo.grid(row=0, column=1, sticky="ew", padx=15, pady=10)
        ctk.CTkLabel(sel, text="語音聲線:").grid(row=1, column=0, padx=15, pady=10, sticky="w")
        self.voice_combo = ctk.CTkOptionMenu(sel, values=[DEFAULT_EDGE_VOICE], command=self._on_voice_change, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, button_color=self.BTN_COLOR, button_hover_color=self.BTN_HOVER_COLOR)
        self.voice_combo.grid(row=1, column=1, sticky="ew", padx=15, pady=10)
        sel.grid_columnconfigure(1, weight=1)

        tts = ctk.CTkFrame(self.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=1)
        tts.grid(row=3, column=0, sticky="ew", padx=PAD_X, pady=PAD_Y)
        ctk.CTkLabel(tts, text="語速:", width=100).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        self.speed_slider = ctk.CTkSlider(tts, from_=100, to=250, command=self.update_tts_settings, button_color=self.BTN_COLOR, button_hover_color=self.BTN_HOVER_COLOR, progress_color=self.BTN_COLOR)
        self.speed_slider.set(self.audio.tts_rate)
        self.speed_slider.grid(row=0, column=1, sticky="ew", padx=15, pady=(15, 5))
        self.speed_value_label = ctk.CTkLabel(tts, text=f"{self.audio.tts_rate}", width=50)
        self.speed_value_label.grid(row=0, column=2, sticky="e", padx=15, pady=(15, 5))
        ctk.CTkLabel(tts, text="音量:", width=100).grid(row=1, column=0, padx=15, pady=(5, 15), sticky="w")
        self.volume_slider = ctk.CTkSlider(tts, from_=0.5, to=1.0, command=self.update_tts_settings, button_color=self.BTN_COLOR, button_hover_color=self.BTN_HOVER_COLOR, progress_color=self.BTN_COLOR)
        self.volume_slider.set(self.audio.tts_volume)
        self.volume_slider.grid(row=1, column=1, sticky="ew", padx=15, pady=(5, 15))
        self.volume_value_label = ctk.CTkLabel(tts, text=f"{self.audio.tts_volume:.2f}", width=50)
        self.volume_value_label.grid(row=1, column=2, sticky="e", padx=15, pady=(5, 15))
        tts.grid_columnconfigure(1, weight=1)

        hotkey_frame = ctk.CTkFrame(self.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=1)
        hotkey_frame.grid(row=4, column=0, sticky="ew", padx=PAD_X, pady=PAD_Y)
        ctk.CTkLabel(hotkey_frame, text="快捷鍵:").grid(row=0, column=0, padx=15, pady=15, sticky="w")
        keys_display_frame = ctk.CTkFrame(hotkey_frame, fg_color="transparent")
        keys_display_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=15)
        self.hotkey_key_buttons = []
        for i in range(3):
            btn = ctk.CTkButton(keys_display_frame, text="", width=80, state="disabled", corner_radius=8,
                                fg_color=("#EAEAEA", "#4A4A4A"),
                                text_color=("#101010", "#E0E0E0"),
                                border_color=("#C0C0C0", "#5A5A5A"),
                                border_width=1,
                                command=lambda idx=i: self._prepare_single_key_recording(idx))
            btn.grid(row=0, column=i, padx=5)
            self.hotkey_key_buttons.append(btn)
        hotkey_frame.grid_columnconfigure(1, weight=1)
        self.hotkey_edit_button = ctk.CTkButton(hotkey_frame, text="✏️ 編輯", width=100, command=self._toggle_hotkey_edit, corner_radius=CORNER_RADIUS, fg_color=self.BTN_COLOR, hover_color=self.BTN_HOVER_COLOR)
        self.hotkey_edit_button.grid(row=0, column=2, sticky="e", padx=15, pady=15)
        info = ctk.CTkFrame(self.root, fg_color="transparent")
        info.grid(row=5, column=0, sticky="ew", padx=PAD_X, pady=(0, 0))
        self.hotkey_info_label = ctk.CTkLabel(info, text="點擊 '編輯' 開始設定快捷鍵。", font=ctk.CTkFont(size=11), text_color="gray")
        self.hotkey_info_label.pack(pady=0, fill="x")

        dl_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        dl_frame.grid(row=6, column=0, sticky="sew", padx=PAD_X, pady=(0, PAD_Y))
        self.download_bar = ctk.CTkProgressBar(dl_frame, corner_radius=CORNER_RADIUS, progress_color=self.BTN_COLOR)
        self.download_bar.set(0.0)
        self.download_bar.pack(fill="x", expand=False, pady=(8, 2))
        self.download_label = ctk.CTkLabel(dl_frame, text="", anchor="w", font=ctk.CTkFont(family="Consolas"))
        self.download_label.pack(fill="x", expand=False)
        self._toggle_download_ui(False)

        log = ctk.CTkFrame(self.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=1)
        log.grid(row=6, column=0, sticky="nsew", padx=PAD_X, pady=(PAD_Y, 20))
        self.log_text = ctk.CTkTextbox(log, font=("Consolas", 12), corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=0)
        self.log_text.pack(fill="both", expand=True, padx=1, pady=1)
        self.log_text.configure(state="disabled")
        dl_frame.tkraise()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

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

    # ===================== 設定檔 =====================
    def _load_config(self):
        self._config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                import json
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            except Exception as e:
                self.log_message(f"載入配置檔失敗: {e}", "ERROR")

    def _save_config(self):
        import json
        cfg = self._config
        cfg["engine"] = self.audio.current_engine
        if self.audio.current_engine == ENGINE_EDGE:
            cfg["voice"] = self.audio.edge_voice
        elif self.audio.pyttsx3_voice_id and self.audio._pyttsx3_voices:
            voice_obj = next((v for v in self.audio._pyttsx3_voices if v.id == self.audio.pyttsx3_voice_id), None)
            cfg["voice"] = voice_obj.name if voice_obj else cfg.get("voice", "default")
        else:
            cfg["voice"] = cfg.get("voice", "default")
        cfg["rate"] = self.audio.tts_rate
        cfg["volume"] = self.audio.tts_volume

        clean_quick_phrases = []
        for phrase in self.quick_phrases:
            clean_quick_phrases.append({"text": phrase.get("text", ""), "hotkey": phrase.get("hotkey", "")})
        cfg["hotkey"] = self.current_hotkey
        cfg["quick_phrases"] = clean_quick_phrases
        cfg["quick_input_position"] = self.quick_input_position
        cfg["enable_quick_phrases"] = self.enable_quick_phrases
        cfg["enable_listen_to_self"] = self.audio.enable_listen_to_self
        cfg["listen_device_name"] = self.audio.listen_device_name
        cfg["listen_volume"] = self.audio.listen_volume
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log_message(f"儲存配置檔失敗: {e}", "ERROR")

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
            self.log_message("依賴與設備載入完成。")
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
            loaded_name = self._config.get("voice")
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
        self.log_message("服務已停止。")

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
            self.log_message(f"服務已啟動，監聽 {len(hotkeys)} 個快捷鍵。")
        except Exception as e:
            self.log_message(f"快捷鍵啟動失敗: {e}。請檢查格式。", "ERROR")

    def _play_quick_phrase(self, text):
        if not self.is_running:
            return
        threading.Thread(target=self.audio.play_text, args=(text,), daemon=True).start()

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
        btn.configure(text=key_text, fg_color=("#EAEAEA", "#4A4A4A"))
        self.log_message(f"第 {self._recording_key_index + 1} 個按鍵已設定為: {key_text or '無'}")
        self._recording_key_index = None
        return False

    def _prepare_single_key_recording(self, index):
        if not self._is_hotkey_edit_mode:
            return
        if self._recording_key_index is not None and self._recording_key_index != index:
            old_btn = self.hotkey_key_buttons[self._recording_key_index]
            old_btn.configure(fg_color=("#EAEAEA", "#4A4A4A"))
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
            self.log_message("進入快捷鍵編輯模式。請點擊下方按鈕進行錄製。")
            self.hotkey_info_label.configure(text="點擊按鍵區塊錄製單鍵，按 Esc 或 Delete 可清除。")
        else:
            if self._hotkey_recording_listener:
                self._hotkey_recording_listener.stop()
                self._hotkey_recording_listener = None
            if self._recording_key_index is not None:
                btn = self.hotkey_key_buttons[self._recording_key_index]
                btn.configure(fg_color=("#EAEAEA", "#4A4A4A"))
                self._recording_key_index = None
            self.hotkey_edit_button.configure(text="✏️ 編輯", fg_color=self.BTN_COLOR, hover_color=self.BTN_HOVER_COLOR)
            for btn in self.hotkey_key_buttons:
                btn.configure(state="disabled")
            self.hotkey_info_label.configure(text="點擊 '編輯' 開始設定快捷鍵。")
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
            self._save_config()

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
                threading.Thread(target=self.audio.play_text, args=(text,), daemon=True).start()
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
        self.settings_window = ctk.CTkToplevel(self.root)
        self.settings_window.title("設定")
        self.settings_window.geometry("450x450")
        self.settings_window.resizable(False, False)
        self.settings_window.transient(self.root)
        self.settings_window.grab_set()

        main_frame = ctk.CTkFrame(self.settings_window, fg_color="transparent")
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        quick_phrase_frame = ctk.CTkFrame(main_frame)
        quick_phrase_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(quick_phrase_frame, text="快捷語音功能:").pack(side="left", padx=10, pady=10)
        self.quick_phrase_switch = ctk.CTkSwitch(quick_phrase_frame, text="", command=self._on_toggle_quick_phrases)
        self.quick_phrase_switch.pack(side="right", padx=10, pady=10)
        if self.enable_quick_phrases:
            self.quick_phrase_switch.select()

        ctk.CTkLabel(main_frame, text="快捷輸入框顯示位置:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        position_var = tk.StringVar(value=self.quick_input_position)
        positions = {
            "螢幕中央": "center",
            "左上角": "top-left",
            "右上角": "top-right",
            "左下角": "bottom-left",
            "右下角": "bottom-right",
        }
        def on_position_change():
            self.quick_input_position = position_var.get()
            self.log_message(f"輸入框位置已設定為: {self.quick_input_position}")
            self._save_config()
        radio_frame = ctk.CTkFrame(main_frame); radio_frame.pack(pady=10, fill="x")
        for i, (text, value) in enumerate(positions.items()):
            rb = ctk.CTkRadioButton(radio_frame, text=text, variable=position_var, value=value, command=on_position_change)
            if i < 3: rb.grid(row=0, column=i, padx=10, pady=5, sticky="w")
            else:     rb.grid(row=1, column=i-3, padx=10, pady=5, sticky="w")

        listen_frame = ctk.CTkFrame(main_frame); listen_frame.pack(fill="x", expand=True, pady=10)
        listen_frame.grid_columnconfigure(1, weight=1)
        listen_switch_frame = ctk.CTkFrame(listen_frame, fg_color="transparent")
        listen_switch_frame.grid(row=0, column=0, columnspan=3, sticky="ew")
        ctk.CTkLabel(listen_switch_frame, text="聆聽自己的語音:").pack(side="left", padx=10, pady=10)
        self.listen_switch = ctk.CTkSwitch(listen_switch_frame, text="", command=self._on_toggle_listen_to_self)
        self.listen_switch.pack(side="right", padx=10, pady=10)
        if self.audio.enable_listen_to_self:
            self.listen_switch.select()

        ctk.CTkLabel(listen_frame, text="聆聽設備:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.listen_device_combo = ctk.CTkOptionMenu(listen_frame, values=self.audio.get_listen_device_names(), command=self._on_listen_device_change)
        self.listen_device_combo.grid(row=1, column=1, columnspan=2, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(listen_frame, text="聆聽音量:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.listen_volume_slider = ctk.CTkSlider(listen_frame, from_=0.0, to=1.0, command=self._on_listen_volume_change)
        self.listen_volume_slider.set(self.audio.listen_volume)
        self.listen_volume_slider.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        self.listen_volume_label = ctk.CTkLabel(listen_frame, text=f"{self.audio.listen_volume:.2f}", width=40)
        self.listen_volume_label.grid(row=2, column=2, padx=10, pady=5, sticky="w")
        self._toggle_listen_controls()

    def _on_toggle_quick_phrases(self):
        self.enable_quick_phrases = bool(self.quick_phrase_switch.get())
        self.log_message(f"快捷語音功能已 {'啟用' if self.enable_quick_phrases else '停用'}")
        self._save_config()
        if self.is_running:
            self._start_hotkey_listener()

    def _on_toggle_listen_to_self(self):
        self.audio.enable_listen_to_self = bool(self.listen_switch.get())
        self.log_message(f"聆聽自己的語音功能已 {'啟用' if self.audio.enable_listen_to_self else '停用'}")
        self._toggle_listen_controls()
        self._save_config()

    def _toggle_listen_controls(self):
        state = "normal" if self.audio.enable_listen_to_self else "disabled"
        self.listen_device_combo.configure(state=state)
        self.listen_volume_slider.configure(state=state)
        self.listen_volume_label.configure(state=state)

    def _on_listen_device_change(self, choice):
        self.audio.listen_device_name = choice
        self.log_message(f"聆聽設備已設定為: {self.audio.listen_device_name}")
        self._save_config()

    def _on_listen_volume_change(self, value):
        self.audio.listen_volume = round(float(value), 2)
        self.listen_volume_label.configure(text=f"{self.audio.listen_volume:.2f}")
        self._save_config()

    def _open_quick_phrases_window(self):
        if self.quick_phrases_window and self.quick_phrases_window.winfo_exists():
            self.quick_phrases_window.focus()
            return
        while len(self.quick_phrases) < 10:
            self.quick_phrases.append({"text": "", "hotkey": ""})
        self.quick_phrases = self.quick_phrases[:10]

        self.quick_phrases_window = ctk.CTkToplevel(self.root)
        self.quick_phrases_window.title("快捷語音設定")
        self.quick_phrases_window.geometry("600x550")
        self.quick_phrases_window.transient(self.root)
        self.quick_phrases_window.grab_set()

        self.phrase_list_frame = ctk.CTkScrollableFrame(self.quick_phrases_window, label_text="快捷語音列表")
        self.phrase_list_frame.pack(padx=20, pady=20, fill="both", expand=True)

        for index in range(10):
            phrase = self.quick_phrases[index]
            item_frame = ctk.CTkFrame(self.phrase_list_frame, fg_color=("gray90", "gray20"))
            item_frame.pack(fill="x", pady=5, padx=5)
            item_frame.grid_columnconfigure(0, weight=1)

            entry = ctk.CTkEntry(item_frame, placeholder_text=f"快捷語音 {index + 1}...")
            entry.insert(0, phrase.get("text", ""))
            entry.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
            entry.bind("<FocusOut>", lambda event, i=index, e=entry: self._update_phrase_text(i, e.get()))
            entry.bind("<Return>",   lambda event, i=index, e=entry: self._update_phrase_text(i, e.get(), True))

            hotkey_btn = ctk.CTkButton(item_frame, text=phrase.get("hotkey", "設定快捷鍵"), width=120,
                                       command=lambda i=index: self._record_quick_phrase_hotkey(i))
            hotkey_btn.grid(row=0, column=1, padx=10, pady=10)

            phrase["_entry_ref"] = entry
            phrase["_btn_ref"] = hotkey_btn

    def _update_phrase_text(self, index, text, unfocus=False):
        current_text = self.quick_phrases[index]["_entry_ref"].get()
        self.quick_phrases[index]["text"] = current_text.strip()
        self._save_config()
        self.log_message(f"快捷語音 {index + 1} 已更新。")
        if unfocus:
            self.quick_phrases_window.focus()

    def _record_quick_phrase_hotkey(self, index_to_edit):
        if not self._quick_phrase_lock.acquire(blocking=False):
            self.log_message("已在錄製另一個快捷鍵，請先完成。", "WARN")
            return
        for p in self.quick_phrases:
            btn = p.get("_btn_ref")
            if btn:
                btn.configure(state="disabled", fg_color="gray50")
        current_btn = self.quick_phrases[index_to_edit]["_btn_ref"]
        current_btn.configure(text="錄製中...", state="normal", fg_color="#FFA726")

        pressed = set()
        def on_press(key):
            key_str = self._key_to_str(key)
            if key_str:
                pressed.add(key_str)
                current_btn.configure(text="+".join(sorted(list(pressed))))
        def on_release(key):
            hotkey_str = "+".join(sorted(list(pressed))) if pressed else ""
            self.quick_phrases[index_to_edit]["hotkey"] = self._normalize_hotkey(hotkey_str)
            current_text = self.quick_phrases[index_to_edit]["_entry_ref"].get()
            self.quick_phrases[index_to_edit]["text"] = current_text.strip()
            self._save_config()
            for idx, p in enumerate(self.quick_phrases):
                btn = p.get("_btn_ref")
                if btn:
                    btn.configure(text=p.get("hotkey") or "設定快捷鍵", state="normal",
                                  fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"])
            self.log_message(f"快捷語音 {index_to_edit + 1} 的快捷鍵已設為: {self.quick_phrases[index_to_edit]['hotkey'] or '無'}")
            self._quick_phrase_lock.release()
            if self.is_running:
                self._start_hotkey_listener()
            return False

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

    # ===================== 其它事件 =====================
    def _on_engine_change(self, val):
        self.audio.set_engine(val)
        self.log_message(f"切換引擎: {self.audio.current_engine}")
        # 更新 voices
        if self.audio.current_engine == ENGINE_EDGE:
            values = self.audio.get_voice_names()
            self.voice_combo.configure(values=values)
            self.voice_combo.set(self.audio.edge_voice if self.audio.edge_voice in values else DEFAULT_EDGE_VOICE)
        else:
            names = self.audio.get_voice_names()
            self.voice_combo.configure(values=names)
        self._save_config()

    def _on_voice_change(self, choice):
        if self.audio.current_engine == ENGINE_EDGE:
            self.audio.set_edge_voice(choice)
        else:
            self.audio.set_pyttsx3_voice_by_name(choice)
        self.log_message(f"已選定語音: {choice}")
        self._save_config()

    def update_tts_settings(self, _=None):
        self.audio.tts_rate = int(self.speed_slider.get())
        self.audio.tts_volume = round(self.volume_slider.get(), 2)
        self.speed_value_label.configure(text=f"{self.audio.tts_rate}")
        self.volume_value_label.configure(text=f"{self.audio.tts_volume:.2f}")
        self._save_config()

    def on_closing(self):
        if self.hotkey_listener:
            try: self.hotkey_listener.stop()
            except Exception: pass
        if self.quick_input_window and self.quick_input_window.winfo_exists():
            self.quick_input_window.destroy()
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
        if self.quick_phrases_window and self.quick_phrases_window.winfo_exists():
            self.quick_phrases_window.destroy()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
