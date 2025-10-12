# -*- coding: utf-8 -*-
# 檔案: ui/main_window.py
# 功用: 負責建構主應用程式視窗的所有 UI 元件。

import customtkinter as ctk
from utils.deps import CABLE_INPUT_HINT, ENGINE_EDGE, ENGINE_PYTTX3

def build_main_window_ui(app):
    """
    建構 LocalTTSPlayer 的主視窗 UI。
    這個函式將所有 UI 元件附加到傳入的 app 實例上。
    """
    app.root = ctk.CTk()
    app.root.title("JuMouth - TTS 語音助手")
    app.root.geometry("680x720")
    app.root.resizable(False, False)

    CORNER_RADIUS = 12
    PAD_X = 20
    PAD_Y = 10
    FG_COLOR = ("#FFFFFF", "#333333")
    app.BORDER_COLOR = ("#E0E0E0", "#404040")
    app.BTN_COLOR = "#708090"
    app.BTN_HOVER_COLOR = "#5D6D7E"

    app.root.grid_rowconfigure(6, weight=1)
    app.root.grid_columnconfigure(0, weight=1)

    # --- 控制按鈕區塊 ---
    ctrl = ctk.CTkFrame(app.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=app.BORDER_COLOR, border_width=1)
    ctrl.grid(row=0, column=0, sticky="ew", padx=PAD_X, pady=(20, PAD_Y))

    app.start_button = ctk.CTkButton(ctrl, text="▶ 啟動", command=app.start_local_player, corner_radius=CORNER_RADIUS, fg_color=app.BTN_COLOR, hover_color=app.BTN_HOVER_COLOR)
    app.start_button.grid(row=0, column=0, padx=15, pady=15)
    app.stop_button = ctk.CTkButton(ctrl, text="■ 停止", command=app.stop_local_player, state="disabled", fg_color="#D32F2F", hover_color="#B71C1C", corner_radius=CORNER_RADIUS)
    app.stop_button.grid(row=0, column=1, padx=15, pady=15)

    spacer = ctk.CTkLabel(ctrl, text="")
    spacer.grid(row=0, column=2, sticky="ew")
    ctrl.grid_columnconfigure(2, weight=1)

    app.quick_phrase_button = ctk.CTkButton(ctrl, text="快捷語音", command=app._open_quick_phrases_window, corner_radius=CORNER_RADIUS, fg_color=app.BTN_COLOR, hover_color=app.BTN_HOVER_COLOR)
    app.quick_phrase_button.grid(row=0, column=3, padx=(0, 10), pady=15)
    app.settings_button = ctk.CTkButton(ctrl, text="⚙️", command=app._open_settings_window, width=40, corner_radius=CORNER_RADIUS, fg_color=app.BTN_COLOR, hover_color=app.BTN_HOVER_COLOR)
    app.settings_button.grid(row=0, column=4, padx=(0, 15), pady=15)

    app.status_label = ctk.CTkLabel(ctrl, text="● 未啟動", text_color=["#D32F2F", "#FF5252"], font=ctk.CTkFont(size=14, weight="bold"))
    app.status_label.grid(row=0, column=5, padx=20, sticky="e")

    # --- 輸出設備區塊 ---
    out = ctk.CTkFrame(app.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=app.BORDER_COLOR, border_width=1)
    out.grid(row=1, column=0, sticky="ew", padx=PAD_X, pady=PAD_Y)
    ctk.CTkLabel(out, text="輸出設備:", anchor="w").grid(row=0, column=0, padx=15, pady=10, sticky="w")    
    app.local_device_combo = ctk.CTkOptionMenu(out, values=["正在載入..."], corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, button_color=app.BTN_COLOR, button_hover_color=app.BTN_HOVER_COLOR)
    app.local_device_combo.set("正在載入...")
    app.local_device_combo.grid(row=0, column=1, sticky="ew", padx=15, pady=10)
    ctk.CTkLabel(out, text=f"💡 Discord 麥克風請設定為: {CABLE_INPUT_HINT}", text_color=["#007BFF", "#1E90FF"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=1, column=0, columnspan=2, padx=15, pady=(5, 10), sticky="w")
    out.grid_columnconfigure(1, weight=1)

    # --- TTS 引擎與聲線選擇 ---
    sel = ctk.CTkFrame(app.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=app.BORDER_COLOR, border_width=1)
    sel.grid(row=2, column=0, sticky="ew", padx=PAD_X, pady=PAD_Y)
    ctk.CTkLabel(sel, text="TTS 引擎:").grid(row=0, column=0, padx=15, pady=10, sticky="w")
    app.engine_combo = ctk.CTkOptionMenu(sel, values=[ENGINE_EDGE, ENGINE_PYTTX3], command=app._on_engine_change, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, button_color=app.BTN_COLOR, button_hover_color=app.BTN_HOVER_COLOR)
    app.engine_combo.set(app.audio.current_engine)
    app.engine_combo.grid(row=0, column=1, sticky="ew", padx=15, pady=10)
    ctk.CTkLabel(sel, text="語音聲線:").grid(row=1, column=0, padx=15, pady=10, sticky="w")
    app.voice_combo = ctk.CTkOptionMenu(sel, values=[app.audio.edge_voice], command=app._on_voice_change, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, button_color=app.BTN_COLOR, button_hover_color=app.BTN_HOVER_COLOR)
    app.voice_combo.grid(row=1, column=1, sticky="ew", padx=15, pady=10)
    sel.grid_columnconfigure(1, weight=1)

    # --- 語速與音量調整 ---
    tts = ctk.CTkFrame(app.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=app.BORDER_COLOR, border_width=1)
    tts.grid(row=3, column=0, sticky="ew", padx=PAD_X, pady=PAD_Y)
    ctk.CTkLabel(tts, text="語速:", width=100).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
    app.speed_slider = ctk.CTkSlider(tts, from_=100, to=250, command=app.update_tts_settings, button_color=app.BTN_COLOR, button_hover_color=app.BTN_HOVER_COLOR, progress_color=app.BTN_COLOR)
    app.speed_slider.set(app.audio.tts_rate)
    app.speed_slider.grid(row=0, column=1, sticky="ew", padx=15, pady=(15, 5))
    app.speed_value_label = ctk.CTkLabel(tts, text=f"{app.audio.tts_rate}", width=50)
    app.speed_value_label.grid(row=0, column=2, sticky="e", padx=15, pady=(15, 5))
    ctk.CTkLabel(tts, text="音量:", width=100).grid(row=1, column=0, padx=15, pady=(5, 15), sticky="w")
    app.volume_slider = ctk.CTkSlider(tts, from_=0.5, to=1.0, command=app.update_tts_settings, button_color=app.BTN_COLOR, button_hover_color=app.BTN_HOVER_COLOR, progress_color=app.BTN_COLOR)
    app.volume_slider.set(app.audio.tts_volume)
    app.volume_slider.grid(row=1, column=1, sticky="ew", padx=15, pady=(5, 15))
    app.volume_value_label = ctk.CTkLabel(tts, text=f"{app.audio.tts_volume:.2f}", width=50)
    app.volume_value_label.grid(row=1, column=2, sticky="e", padx=15, pady=(5, 15))
    tts.grid_columnconfigure(1, weight=1)
    # 修正: 應該在 tts 這個 Frame 容器上設定其內部的網格欄位
    # 讓第二欄 (column 1, 包含 slider) 佔用多餘的空間
    tts.grid_columnconfigure(1, weight=1) 

    # --- 快捷鍵設定 ---
    hotkey_frame = ctk.CTkFrame(app.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=app.BORDER_COLOR, border_width=1)
    hotkey_frame.grid(row=4, column=0, sticky="ew", padx=PAD_X, pady=PAD_Y)
    ctk.CTkLabel(hotkey_frame, text="快捷鍵:").grid(row=0, column=0, padx=15, pady=15, sticky="w")
    keys_display_frame = ctk.CTkFrame(hotkey_frame, fg_color="transparent")
    keys_display_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=15)
    app.hotkey_key_buttons = []
    for i in range(3):
        btn = ctk.CTkButton(keys_display_frame, text="", width=80, state="disabled", corner_radius=8,
                            fg_color=('#EAEAEA', '#4A4A4A'),
                            text_color=('#101010', '#E0E0E0'),
                            border_color=('#C0C0C0', '#5A5A5A'),
                            border_width=1,
                            command=lambda idx=i: app._prepare_single_key_recording(idx))
        btn.grid(row=0, column=i, padx=5)
        app.hotkey_key_buttons.append(btn)
    hotkey_frame.grid_columnconfigure(1, weight=1)
    app.hotkey_edit_button = ctk.CTkButton(hotkey_frame, text="✏️ 編輯", width=100, command=app._toggle_hotkey_edit, corner_radius=CORNER_RADIUS, fg_color=app.BTN_COLOR, hover_color=app.BTN_HOVER_COLOR)
    app.hotkey_edit_button.grid(row=0, column=2, sticky="e", padx=15, pady=15)
    info = ctk.CTkFrame(app.root, fg_color="transparent")
    info.grid(row=5, column=0, sticky="ew", padx=PAD_X, pady=(0, 0))
    app.hotkey_info_label = ctk.CTkLabel(info, text="點擊 '編輯' 開始設定快捷鍵。", font=ctk.CTkFont(size=11), text_color="gray")
    app.hotkey_info_label.pack(pady=0, fill="x")

    log = ctk.CTkFrame(app.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=app.BORDER_COLOR, border_width=1)
    log.grid(row=6, column=0, sticky="nsew", padx=PAD_X, pady=(PAD_Y, 20))
    app.log_text = ctk.CTkTextbox(log, font=("Consolas", 12), corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=app.BORDER_COLOR, border_width=0)
    app.log_text.pack(fill="both", expand=True, padx=1, pady=1)
    app.log_text.configure(state="disabled")
    app.root.protocol("WM_DELETE_WINDOW", app.on_closing)