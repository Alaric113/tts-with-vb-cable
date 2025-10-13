# -*- coding: utf-8 -*-
# 檔案: ui/popups.py
# 功用: 提供獨立的 UI 彈出視窗元件。
#      - SettingsWindow: 「設定」彈出視窗的完整 UI 與邏輯。
#      - QuickPhrasesWindow: 「快捷語音」彈出視窗的完整 UI 與邏輯。

from ..utils.deps import APP_VERSION
import tkinter as tk
import customtkinter as ctk
from pynput import keyboard

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.audio = app.audio

        self.title("設定")
        self.geometry("450x550")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        # --- 風格常數 ---
        CARD_RADIUS = 18
        PILL_RADIUS = 18
        BG_COLOR = "#2E2E2E"
        CARD_COLOR = "#242424"
        BTN_COLOR = "#4A4A4A"
        BTN_HOVER_COLOR = "#5A5A5A"
        ACCENT_COLOR = "#007AFF"

        self.configure(fg_color=BG_COLOR)
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)
        main_frame.grid_columnconfigure(0, weight=1)

        # --- 啟動時自動運行服務 ---
        auto_start_frame = ctk.CTkFrame(main_frame, fg_color=CARD_COLOR, corner_radius=CARD_RADIUS)
        auto_start_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(auto_start_frame, text="啟動時自動運行服務:").pack(side="left", padx=10, pady=10)
        self.auto_start_switch = ctk.CTkSwitch(auto_start_frame, text="", command=self._on_toggle_auto_start, progress_color=ACCENT_COLOR)
        self.auto_start_switch.pack(side="right", padx=10, pady=10)
        if self.app.config.get("auto_start_service"):
            self.auto_start_switch.select()

        # --- 快捷輸入框位置 ---
        position_label = ctk.CTkLabel(main_frame, text="快捷輸入框顯示位置:", font=ctk.CTkFont(weight="bold"))
        position_label.grid(row=1, column=0, sticky="w", pady=(10, 5))

        position_var = tk.StringVar(value=self.app.quick_input_position)
        positions = {
            "螢幕中央": "center", "左上角": "top-left", "右上角": "top-right",
            "左下角": "bottom-left", "右下角": "bottom-right",
        }
        radio_frame = ctk.CTkFrame(main_frame, fg_color=CARD_COLOR, corner_radius=CARD_RADIUS)
        radio_frame.grid(row=2, column=0, sticky="ew", pady=10)
        
        def on_position_change():
            self.app.quick_input_position = position_var.get()
            self.app.log_message(f"輸入框位置已設定為: {self.app.quick_input_position}")
            self.app.config.set("quick_input_position", self.app.quick_input_position)

        for i, (text, value) in enumerate(positions.items()):
            rb = ctk.CTkRadioButton(radio_frame, text=text, variable=position_var, value=value, command=on_position_change, fg_color=ACCENT_COLOR)
            col, row = i % 2, i // 2
            rb.grid(row=row, column=col, padx=10, pady=5, sticky="w")

        # --- 聆聽自己語音 ---
        listen_frame = ctk.CTkFrame(main_frame, fg_color=CARD_COLOR, corner_radius=CARD_RADIUS)
        listen_frame.grid(row=3, column=0, sticky="ew", pady=10)
        listen_frame.grid_columnconfigure(1, weight=1)
        
        listen_switch_frame = ctk.CTkFrame(listen_frame, fg_color="transparent")
        listen_switch_frame.grid(row=0, column=0, columnspan=3, sticky="ew")
        ctk.CTkLabel(listen_switch_frame, text="聆聽自己的語音:").pack(side="left", padx=10, pady=10)
        self.listen_switch = ctk.CTkSwitch(listen_switch_frame, text="", command=self._on_toggle_listen_to_self, progress_color=ACCENT_COLOR)
        self.listen_switch.pack(side="right", padx=10, pady=10)
        if self.audio.enable_listen_to_self:
            self.listen_switch.select()

        ctk.CTkLabel(listen_frame, text="聆聽設備:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.listen_device_combo = ctk.CTkOptionMenu(listen_frame, values=self.audio.get_listen_device_names(), command=self._on_listen_device_change, corner_radius=PILL_RADIUS, fg_color=BG_COLOR, button_color=BTN_COLOR, button_hover_color=BTN_HOVER_COLOR)
        self.listen_device_combo.set(self.audio.listen_device_name)
        self.listen_device_combo.grid(row=1, column=1, columnspan=2, padx=10, pady=5, sticky="ew")
        
        ctk.CTkLabel(listen_frame, text="聆聽音量:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.listen_volume_slider = ctk.CTkSlider(listen_frame, from_=0.0, to=1.0, command=self._on_listen_volume_change, button_color=BTN_COLOR, button_hover_color=BTN_HOVER_COLOR, progress_color=ACCENT_COLOR)
        self.listen_volume_slider.set(self.audio.listen_volume)
        self.listen_volume_slider.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        
        self.listen_volume_label = ctk.CTkLabel(listen_frame, text=f"{self.audio.listen_volume:.2f}", width=40)
        self.listen_volume_label.grid(row=2, column=2, padx=10, pady=5, sticky="w")
        
        # --- 檢查更新按鈕 ---
        update_button = ctk.CTkButton(main_frame, text="檢查更新", command=lambda: self.app.updater.check_for_updates(silent=False), corner_radius=PILL_RADIUS, fg_color=BTN_COLOR, hover_color=BTN_HOVER_COLOR)
        update_button.grid(row=4, column=0, pady=(20, 10), sticky="ew")

        # --- 版本號標籤 ---
        version_label = ctk.CTkLabel(main_frame, text=f"版本: {APP_VERSION}",
                                     font=ctk.CTkFont(size=12), text_color="gray")
        version_label.grid(row=5, column=0, pady=(0, 5), sticky="e")

        self._toggle_listen_controls()

    def _on_toggle_auto_start(self):
        auto_start = bool(self.auto_start_switch.get())
        self.app.log_message(f"啟動時自動運行服務已 {'啟用' if auto_start else '停用'}")
        self.app.config.set("auto_start_service", auto_start)

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

        # 修正: 使用一個獨立的列表來儲存 UI 元件參照，避免污染 config 資料
        self.ui_elements = []

        self._build_ui()

    def _build_ui(self):
        # --- 風格常數 ---
        CARD_RADIUS = 18
        PILL_RADIUS = 18
        BG_COLOR = "#2E2E2E"
        CARD_COLOR = "#242424"
        BTN_COLOR = "#4A4A4A"
        BTN_HOVER_COLOR = "#5A5A5A"
        ACCENT_COLOR = "#FFA726" # 錄製中顏色

        self.configure(fg_color=BG_COLOR)
        self.phrase_list_frame = ctk.CTkScrollableFrame(self, label_text="快捷語音列表", corner_radius=CARD_RADIUS, fg_color=CARD_COLOR)
        self.phrase_list_frame.pack(padx=20, pady=20, fill="both", expand=True)

        for index in range(10):
            # 從 app.quick_phrases 讀取純資料
            phrase = self.app.quick_phrases[index]
            item_frame = ctk.CTkFrame(self.phrase_list_frame, fg_color=BG_COLOR, corner_radius=PILL_RADIUS)
            item_frame.pack(fill="x", pady=5, padx=5)
            item_frame.grid_columnconfigure(0, weight=1)

            entry = ctk.CTkEntry(item_frame, placeholder_text=f"快捷語音 {index + 1}...", border_width=0, fg_color="transparent")
            entry.insert(0, phrase.get("text", ""))
            entry.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
            entry.bind("<FocusOut>", lambda event, i=index: self._update_phrase_text(i))
            entry.bind("<Return>",   lambda event, i=index: self._update_phrase_text(i, True))

            hotkey_btn = ctk.CTkButton(item_frame, text=phrase.get("hotkey", "設定快捷鍵"), width=120,
                                       command=lambda i=index: self._record_quick_phrase_hotkey(i), corner_radius=PILL_RADIUS, fg_color=BTN_COLOR, hover_color=BTN_HOVER_COLOR)
            hotkey_btn.grid(row=0, column=1, padx=10, pady=10)

            # 將 UI 元件參照存到獨立的列表中
            self.ui_elements.append({"entry": entry, "button": hotkey_btn})

    def _update_phrase_text(self, index, unfocus=False):
        entry_widget = self.ui_elements[index]["entry"]
        current_text = entry_widget.get()
        self.app.quick_phrases[index]["text"] = current_text.strip()
        
        # 現在 app.quick_phrases 是乾淨的，可以直接儲存
        self.app.config.set("quick_phrases", self.app.quick_phrases)

        self.app.log_message(f"快捷語音 {index + 1} 已更新。")
        if unfocus:
            self.focus()

    def _record_quick_phrase_hotkey(self, index_to_edit):
        if not self.app._quick_phrase_lock.acquire(blocking=False):
            self.app.log_message("已在錄製另一個快捷鍵，請先完成。", "WARN")
            return

        for elem in self.ui_elements:
            elem["button"].configure(state="disabled", fg_color="gray50")

        current_btn = self.ui_elements[index_to_edit]["button"]
        current_btn.configure(text="錄製中...", state="normal", fg_color="#FFA726")

        pressed = set()

        def on_press(key):
            key_str = self.app._key_to_str(key)
            if key_str:
                pressed.add(key_str)
                current_btn.configure(text="+".join(sorted(list(pressed))))

        def on_release(key):
            hotkey_str = "+".join(sorted(list(pressed))) if pressed else ""
            normalized_hotkey = self.app._normalize_hotkey(hotkey_str)

            # 衝突檢測
            conflict_msg = self.app._check_hotkey_conflict(normalized_hotkey, 'quick_phrase', index_to_edit)
            if conflict_msg:
                messagebox.showwarning("快捷鍵衝突", conflict_msg)
                # 恢復按鈕外觀，但不儲存新快捷鍵
            else:
                # 無衝突，儲存新快捷鍵
                self.app.quick_phrases[index_to_edit]["hotkey"] = normalized_hotkey
                self._update_phrase_text(index_to_edit)
                self.app.log_message(f"快捷語音 {index_to_edit + 1} 的快捷鍵已設為: {normalized_hotkey or '無'}")

            # 無論是否有衝突，都要恢復所有按鈕的狀態
            for i, elem in enumerate(self.ui_elements):
                phrase_data = self.app.quick_phrases[i]
                elem["button"].configure(text=phrase_data.get("hotkey") or "設定快捷鍵", state="normal", fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"])

            self.app._quick_phrase_lock.release()

            if self.app.is_running:
                self.app._start_hotkey_listener()
            return False

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
