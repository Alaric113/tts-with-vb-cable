# -*- coding: utf-8 -*-
# 檔案: ui/popups.py
# 功用: 提供獨立的 UI 彈出視窗元件。
#      - SettingsWindow: 「設定」彈出視窗的完整 UI 與邏輯。
#      - QuickPhrasesWindow: 「快捷語音」彈出視窗的完整 UI 與邏輯。

import tkinter as tk
import customtkinter as ctk
from pynput import keyboard

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.audio = app.audio

        self.title("設定")
        self.geometry("450x450")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)
        main_frame.grid_columnconfigure(0, weight=1)

        # --- 快捷語音總開關 ---
        quick_phrase_frame = ctk.CTkFrame(main_frame)
        quick_phrase_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(quick_phrase_frame, text="快捷語音功能:").pack(side="left", padx=10, pady=10)
        self.quick_phrase_switch = ctk.CTkSwitch(quick_phrase_frame, text="", command=self._on_toggle_quick_phrases)
        self.quick_phrase_switch.pack(side="right", padx=10, pady=10)
        if self.app.enable_quick_phrases:
            self.quick_phrase_switch.select()

        # --- 快捷輸入框位置 ---
        position_label = ctk.CTkLabel(main_frame, text="快捷輸入框顯示位置:", font=ctk.CTkFont(weight="bold"))
        position_label.grid(row=1, column=0, sticky="w", pady=(10, 0))

        position_var = tk.StringVar(value=self.app.quick_input_position)
        positions = {
            "螢幕中央": "center", "左上角": "top-left", "右上角": "top-right",
            "左下角": "bottom-left", "右下角": "bottom-right",
        }
        radio_frame = ctk.CTkFrame(main_frame)
        radio_frame.grid(row=2, column=0, sticky="ew", pady=10)
        
        def on_position_change():
            self.app.quick_input_position = position_var.get()
            self.app.log_message(f"輸入框位置已設定為: {self.app.quick_input_position}")
            self.app.config.set("quick_input_position", self.app.quick_input_position)

        for i, (text, value) in enumerate(positions.items()):
            rb = ctk.CTkRadioButton(radio_frame, text=text, variable=position_var, value=value, command=on_position_change)
            col, row = i % 3, i // 3
            rb.grid(row=row, column=col, padx=10, pady=5, sticky="w")

        # --- 聆聽自己語音 ---
        listen_frame = ctk.CTkFrame(main_frame)
        listen_frame.grid(row=3, column=0, sticky="ew", pady=10)
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
        self.listen_device_combo.set(self.audio.listen_device_name)
        self.listen_device_combo.grid(row=1, column=1, columnspan=2, padx=10, pady=5, sticky="ew")
        
        ctk.CTkLabel(listen_frame, text="聆聽音量:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.listen_volume_slider = ctk.CTkSlider(listen_frame, from_=0.0, to=1.0, command=self._on_listen_volume_change)
        self.listen_volume_slider.set(self.audio.listen_volume)
        self.listen_volume_slider.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        
        self.listen_volume_label = ctk.CTkLabel(listen_frame, text=f"{self.audio.listen_volume:.2f}", width=40)
        self.listen_volume_label.grid(row=2, column=2, padx=10, pady=5, sticky="w")
        
        self._toggle_listen_controls()

    def _on_toggle_quick_phrases(self):
        self.app.enable_quick_phrases = bool(self.quick_phrase_switch.get())
        self.app.log_message(f"快捷語音功能已 {'啟用' if self.app.enable_quick_phrases else '停用'}")
        self.app.config.set("enable_quick_phrases", self.app.enable_quick_phrases)
        if self.app.is_running:
            self.app._start_hotkey_listener()

    def _on_toggle_listen_to_self(self):
        self.audio.enable_listen_to_self = bool(self.listen_switch.get())
        self.app.log_message(f"聆聽自己的語音功能已 {'啟用' if self.audio.enable_listen_to_self else '停用'}")
        self.app.config.set("enable_listen_to_self", self.audio.enable_listen_to_self)
        self._toggle_listen_controls()

    def _toggle_listen_controls(self):
        state = "normal" if self.audio.enable_listen_to_self else "disabled"
        self.listen_device_combo.configure(state=state)
        self.listen_volume_slider.configure(state=state)
        # 即使禁用，標籤也應該可見
        # self.listen_volume_label.configure(state=state)

    def _on_listen_device_change(self, choice):
        self.audio.listen_device_name = choice
        self.app.log_message(f"聆聽設備已設定為: {self.audio.listen_device_name}")
        self.app.config.set("listen_device_name", self.audio.listen_device_name)

    def _on_listen_volume_change(self, value):
        self.audio.listen_volume = round(float(value), 2)
        self.listen_volume_label.configure(text=f"{self.audio.listen_volume:.2f}")
        self.app.config.set("listen_volume", self.audio.listen_volume)

class QuickPhrasesWindow(ctk.CTkToplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

        self.title("快捷語音設定")
        self.geometry("600x550")
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        self.phrase_list_frame = ctk.CTkScrollableFrame(self, label_text="快捷語音列表")
        self.phrase_list_frame.pack(padx=20, pady=20, fill="both", expand=True)

        for index in range(10):
            phrase = self.app.quick_phrases[index]
            item_frame = ctk.CTkFrame(self.phrase_list_frame, fg_color=("gray90", "gray20"))
            item_frame.pack(fill="x", pady=5, padx=5)
            item_frame.grid_columnconfigure(0, weight=1)

            entry = ctk.CTkEntry(item_frame, placeholder_text=f"快捷語音 {index + 1}...")
            entry.insert(0, phrase.get("text", ""))
            entry.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
            entry.bind("<FocusOut>", lambda event, i=index: self._update_phrase_text(i))
            entry.bind("<Return>",   lambda event, i=index: self._update_phrase_text(i, True))

            hotkey_btn = ctk.CTkButton(item_frame, text=phrase.get("hotkey", "設定快捷鍵"), width=120,
                                       command=lambda i=index: self._record_quick_phrase_hotkey(i))
            hotkey_btn.grid(row=0, column=1, padx=10, pady=10)

            phrase["_entry_ref"] = entry
            phrase["_btn_ref"] = hotkey_btn

    def _update_phrase_text(self, index, unfocus=False):
        current_text = self.app.quick_phrases[index]["_entry_ref"].get()
        self.app.quick_phrases[index]["text"] = current_text.strip()
        
        # 直接操作 config 中的列表並儲存
        clean_phrases = [{"text": p.get("text", ""), "hotkey": p.get("hotkey", "")} for p in self.app.quick_phrases]
        self.app.config.set("quick_phrases", clean_phrases)

        self.app.log_message(f"快捷語音 {index + 1} 已更新。")
        if unfocus:
            self.focus()

    def _record_quick_phrase_hotkey(self, index_to_edit):
        if not self.app._quick_phrase_lock.acquire(blocking=False):
            self.app.log_message("已在錄製另一個快捷鍵，請先完成。", "WARN")
            return

        for p in self.app.quick_phrases:
            btn = p.get("_btn_ref")
            if btn:
                btn.configure(state="disabled", fg_color="gray50")

        current_btn = self.app.quick_phrases[index_to_edit]["_btn_ref"]
        current_btn.configure(text="錄製中...", state="normal", fg_color="#FFA726")

        pressed = set()

        def on_press(key):
            key_str = self.app._key_to_str(key)
            if key_str:
                pressed.add(key_str)
                current_btn.configure(text="+".join(sorted(list(pressed))))

        def on_release(key):
            hotkey_str = "+".join(sorted(list(pressed))) if pressed else ""
            self.app.quick_phrases[index_to_edit]["hotkey"] = self.app._normalize_hotkey(hotkey_str)
            self._update_phrase_text(index_to_edit)
            for p in self.app.quick_phrases:
                btn = p.get("_btn_ref")
                if btn:
                    btn.configure(text=p.get("hotkey") or "設定快捷鍵", state="normal", fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"])
            self.app.log_message(f"快捷語音 {index_to_edit + 1} 的快捷鍵已設為: {self.app.quick_phrases[index_to_edit]['hotkey'] or '無'}")
            self.app._quick_phrase_lock.release()
            if self.app.is_running:
                self.app._start_hotkey_listener()
            return False

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
