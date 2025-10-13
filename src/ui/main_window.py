# -*- coding: utf-8 -*-
# 檔案: ui/main_window.py
# 功用: 負責建構主應用程式視窗的所有 UI 元件。
import customtkinter as ctk
from ..utils.deps import CABLE_INPUT_HINT, ENGINE_EDGE, ENGINE_PYTTX3


def build_main_window_ui(app):
    """
    建構 LocalTTSPlayer 的主視窗 UI。
    這個函式將所有 UI 元件附加到傳入的 app 實例上。
    """
    # --- 風格設定 ---
    ctk.set_appearance_mode("Dark")
    app.root = ctk.CTk()
    app.root.title("JuMouth - TTS 語音助手")
    app.root.geometry("680x720") # 恢復為預設初始值，實際大小由 app.py 控制
    app.root.resizable(False, False)
    
    # --- 風格常數定義 (MacCleaner X 風格) ---
    CARD_RADIUS = 18
    PILL_RADIUS = 18 # 膠囊按鈕
    PAD_X = 20
    PAD_Y = 10
    # 深色模式下的顏色
    BG_COLOR = "#242424" # 主背景色
    CARD_COLOR = "#2E2E2E" # 卡片顏色，比背景略亮
    BORDER_COLOR = "#404040" # 邊框光暈色
    BTN_COLOR = "#4A4A4A" # 按鈕基礎色
    BTN_HOVER_COLOR = "#5A5A5A" # 按鈕懸停色
    ACCENT_COLOR = "#007AFF" # 強調色 (e.g., 啟動按鈕)
    ACCENT_HOVER_COLOR = "#0056B3"
    RECORDING_COLOR = "#FFA726" # 錄製中顏色

    app.root.configure(fg_color=BG_COLOR)
    app.BORDER_COLOR = BORDER_COLOR
    app.BTN_COLOR = BTN_COLOR
    app.BTN_HOVER_COLOR = BTN_HOVER_COLOR
    
    # --- 主視窗網格佈局 ---
    app.root.grid_rowconfigure(1, weight=0) # 讓中間的頁籤區高度固定
    app.root.grid_rowconfigure(2, weight=1) # 讓底下的日誌區填滿剩餘空間
    app.root.grid_columnconfigure(0, weight=1)
    
    # --- A. 頂部整合控制區 ---
    dashboard_frame = ctk.CTkFrame(app.root, corner_radius=CARD_RADIUS, fg_color=CARD_COLOR, border_color=BORDER_COLOR, border_width=1)
    dashboard_frame.grid(row=0, column=0, sticky="ew", padx=PAD_X, pady=(20, PAD_Y))
    dashboard_frame.grid_columnconfigure(1, weight=1)
    
    # A.1 應用程式標題
    ctk.CTkLabel(dashboard_frame, text="JuMouth TTS", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=20, pady=15, sticky="w")
    
    # A.2 右側控制項容器
    right_controls_frame = ctk.CTkFrame(dashboard_frame, fg_color="transparent")
    right_controls_frame.grid(row=0, column=2, padx=(0, 15), pady=10, sticky="e")
    app.start_button = ctk.CTkButton(right_controls_frame, text="▶ 啟動服務", command=app.start_local_player, corner_radius=PILL_RADIUS, fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER_COLOR, width=120)
    app.start_button.grid(row=0, column=0, padx=0, pady=0)
    app.stop_button = ctk.CTkButton(right_controls_frame, text="■ 停止服務", command=app.stop_local_player, state="disabled", fg_color="#546E7A", hover_color="#D32F2F", corner_radius=PILL_RADIUS, width=120)
    app.stop_button.grid(row=0, column=1, padx=(10, 0), pady=0)
    
    # A.3 狀態標籤
    app.status_label = ctk.CTkLabel(dashboard_frame, text="● 已停止", text_color="#FF5252", font=ctk.CTkFont(size=14, weight="bold"), width=80)
    app.status_label.grid(row=0, column=3, padx=(10, 20), sticky="e")
    
    # --- B. 中間頁籤區 ---
    tab_view = ctk.CTkTabview(app.root, corner_radius=CARD_RADIUS, border_color=BORDER_COLOR, border_width=1,
                              fg_color=CARD_COLOR,
                              segmented_button_fg_color=CARD_COLOR,
                              segmented_button_selected_color=ACCENT_COLOR,
                              segmented_button_selected_hover_color=ACCENT_HOVER_COLOR,
                              segmented_button_unselected_hover_color=BTN_HOVER_COLOR)
    tab_view.grid(row=1, column=0, sticky="nsew", padx=PAD_X, pady=0)
    tab_main_settings = tab_view.add("主要設定")
    tab_hotkeys = tab_view.add("快捷鍵與功能")
    tab_main_settings.configure(fg_color=CARD_COLOR)
    tab_hotkeys.configure(fg_color=CARD_COLOR)
    
    # --- B.1 填充 "主要設定" 頁籤 ---
    # 使用 Grid 佈局來放置卡片
    tab_main_settings.grid_columnconfigure(0, weight=1)
    tab_main_settings.grid_columnconfigure(1, weight=1)
    tab_main_settings.grid_rowconfigure(1, weight=0) # 修正: 移除權重，避免垂直拉伸
    
    # B.1.1 輸出設備區塊
    out_frame = ctk.CTkFrame(tab_main_settings, fg_color=BG_COLOR, corner_radius=CARD_RADIUS)
    out_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=15, pady=15)
    out_frame.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(out_frame, text="輸出設備:", anchor="w").grid(row=0, column=0, padx=10, pady=5, sticky="w")
    app.local_device_combo = ctk.CTkOptionMenu(out_frame, values=["正在載入..."], corner_radius=PILL_RADIUS, fg_color=CARD_COLOR, button_color=BTN_COLOR, button_hover_color=BTN_HOVER_COLOR, state="disabled")
    app.local_device_combo.set("正在載入...")
    app.local_device_combo.grid(row=1, column=0, sticky="ew", padx=5, pady=0)
    ctk.CTkLabel(out_frame, text=f"💡 提示: Discord 麥克風請設為 {CABLE_INPUT_HINT}", text_color="#007AFF", font=ctk.CTkFont(size=12, weight="bold")).grid(row=2, column=0, padx=10, pady=5, sticky="w")
    
    # B.1.2 TTS 引擎與聲線選擇 (水平並排)
    sel_frame = ctk.CTkFrame(tab_main_settings, fg_color=BG_COLOR, corner_radius=CARD_RADIUS)
    sel_frame.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(10, 5))
    sel_frame.grid_columnconfigure(0, weight=1)
    
    ctk.CTkLabel(sel_frame, text="TTS 引擎:", anchor="w").grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")
    app.engine_combo = ctk.CTkOptionMenu(sel_frame, values=[ENGINE_EDGE, ENGINE_PYTTX3], command=app._on_engine_change, corner_radius=PILL_RADIUS, fg_color=CARD_COLOR, button_color=BTN_COLOR, button_hover_color=BTN_HOVER_COLOR)
    app.engine_combo.set(app.audio.current_engine)
    app.engine_combo.grid(row=1, column=0, sticky="ew", padx=10, pady=0)
    
    ctk.CTkLabel(sel_frame, text="語音聲線:", anchor="w").grid(row=2, column=0, padx=10, pady=(10, 5), sticky="w")
    app.voice_combo = ctk.CTkOptionMenu(sel_frame, values=["正在載入..."], command=app._on_voice_change, corner_radius=PILL_RADIUS, fg_color=CARD_COLOR, button_color=BTN_COLOR, button_hover_color=BTN_HOVER_COLOR, state="disabled")
    app.voice_combo.set("正在載入...")
    app.voice_combo.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 5))
    
    # B.1.3 語音參數調整 (緊湊佈局)
    tts_params_frame = ctk.CTkFrame(tab_main_settings, fg_color=BG_COLOR, corner_radius=CARD_RADIUS)
    tts_params_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(10, 5))
    tts_params_frame.grid_columnconfigure(1, weight=1)
    
    ctk.CTkLabel(tts_params_frame, text="語速:", width=60).grid(row=0, column=0, padx=(5, 10), pady=10, sticky="w")
    app.speed_slider = ctk.CTkSlider(tts_params_frame, from_=100, to=250, command=app.update_tts_settings, button_color=BTN_COLOR, button_hover_color=BTN_HOVER_COLOR, progress_color=ACCENT_COLOR, button_corner_radius=PILL_RADIUS)
    app.speed_slider.set(app.audio.tts_rate)
    app.speed_slider.grid(row=0, column=1, sticky="ew", padx=0, pady=10)
    app.speed_value_label = ctk.CTkLabel(tts_params_frame, text=f"{app.audio.tts_rate}", width=50)
    app.speed_value_label.grid(row=0, column=2, sticky="e", padx=(10, 5), pady=10)
    
    ctk.CTkLabel(tts_params_frame, text="音量:", width=60).grid(row=1, column=0, padx=(5, 10), pady=10, sticky="w")
    app.volume_slider = ctk.CTkSlider(tts_params_frame, from_=0.5, to=1.0, command=app.update_tts_settings, button_color=BTN_COLOR, button_hover_color=BTN_HOVER_COLOR, progress_color=ACCENT_COLOR, button_corner_radius=PILL_RADIUS)
    app.volume_slider.set(app.audio.tts_volume)
    app.volume_slider.grid(row=1, column=1, sticky="ew", padx=0, pady=10)
    app.volume_value_label = ctk.CTkLabel(tts_params_frame, text=f"{app.audio.tts_volume:.2f}", width=50)
    app.volume_value_label.grid(row=1, column=2, sticky="e", padx=(10, 5), pady=10)
    
    ctk.CTkLabel(tts_params_frame, text="音高:", width=60).grid(row=2, column=0, padx=(5, 10), pady=10, sticky="w")
    app.pitch_slider = ctk.CTkSlider(tts_params_frame, from_=-100, to=100, command=app.update_tts_settings, button_color=BTN_COLOR, button_hover_color=BTN_HOVER_COLOR, progress_color=ACCENT_COLOR, button_corner_radius=PILL_RADIUS)
    app.pitch_slider.set(app.audio.tts_pitch)
    app.pitch_slider.grid(row=2, column=1, sticky="ew", padx=0, pady=10)
    app.pitch_value_label = ctk.CTkLabel(tts_params_frame, text=f"{app.audio.tts_pitch}", width=50)
    app.pitch_value_label.grid(row=2, column=2, sticky="e", padx=(10, 5), pady=10)
    
    # --- B.2 填充 "快捷鍵與功能" 頁籤 ---
    tab_hotkeys.grid_columnconfigure(0, weight=1)
    tab_hotkeys.grid_rowconfigure(2, weight=1) # 讓 actions_frame 能夠推到底部
    
    # B.2.1 主快捷鍵設定
    hotkey_frame = ctk.CTkFrame(tab_hotkeys, fg_color=BG_COLOR, corner_radius=CARD_RADIUS)
    hotkey_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
    hotkey_frame.grid_columnconfigure(1, weight=1)
    
    ctk.CTkLabel(hotkey_frame, text="快速輸入框快捷鍵:").grid(row=0, column=0, padx=15, pady=15, sticky="w")
    keys_display_frame = ctk.CTkFrame(hotkey_frame, fg_color="transparent")
    keys_display_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=15)
    app.hotkey_key_buttons = []
    for i in range(3):
        btn = ctk.CTkButton(keys_display_frame, text="", width=80, state="disabled", corner_radius=PILL_RADIUS,
                            fg_color=CARD_COLOR, text_color='#E0E0E0',
                            border_color=BORDER_COLOR, border_width=1,
                            command=lambda idx=i: app._prepare_single_key_recording(idx))
        btn.grid(row=0, column=i, padx=5)
        app.hotkey_key_buttons.append(btn)
    
    app.hotkey_edit_button = ctk.CTkButton(hotkey_frame, text="✏️ 編輯", width=100, command=app._toggle_hotkey_edit, corner_radius=PILL_RADIUS, fg_color=BTN_COLOR, hover_color=BTN_HOVER_COLOR, text_color_disabled="gray60")
    app.hotkey_edit_button.grid(row=0, column=2, sticky="e", padx=15, pady=15)
    app.hotkey_info_label = ctk.CTkLabel(hotkey_frame, text="點擊 '編輯' 開始設定快捷鍵。", font=ctk.CTkFont(size=11), text_color="gray")
    app.hotkey_info_label.grid(row=1, column=0, columnspan=3, sticky="w", padx=15, pady=(0, 10))
    
    # B.2.3 快捷語音開關
    quick_phrase_switch_frame = ctk.CTkFrame(tab_hotkeys, fg_color=BG_COLOR, corner_radius=CARD_RADIUS)
    quick_phrase_switch_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 10))
    ctk.CTkLabel(quick_phrase_switch_frame, text="啟用快捷語音功能:").pack(side="left", padx=(10, 10))
    app.quick_phrase_switch = ctk.CTkSwitch(quick_phrase_switch_frame, text="", command=app._on_toggle_quick_phrases, progress_color=ACCENT_COLOR)
    app.quick_phrase_switch.pack(side="left")
    
    # B.2.4 功能按鈕 (放置於頁籤底部)
    actions_frame = ctk.CTkFrame(tab_hotkeys, fg_color=BG_COLOR, corner_radius=CARD_RADIUS)
    actions_frame.grid(row=3, column=0, sticky="sew", padx=10, pady=10)
    actions_frame.grid_columnconfigure(0, weight=1)
    actions_frame.grid_columnconfigure(1, weight=1)
    
    app.quick_phrase_button = ctk.CTkButton(actions_frame, text="快捷語音設定", command=app._open_quick_phrases_window, corner_radius=PILL_RADIUS, fg_color=BTN_COLOR, hover_color=BTN_HOVER_COLOR)
    app.quick_phrase_button.grid(row=0, column=0, padx=(0, 5), pady=10, sticky="ew")
    app.settings_button = ctk.CTkButton(actions_frame, text="其它設定", command=app._open_settings_window, corner_radius=PILL_RADIUS, fg_color=BTN_COLOR, hover_color=BTN_HOVER_COLOR)
    app.settings_button.grid(row=0, column=1, padx=(5, 0), pady=10, sticky="ew")
    
    # --- C. 底部日誌區 ---
    app.log_frame = ctk.CTkFrame(app.root, corner_radius=CARD_RADIUS, fg_color="transparent")
    app.log_frame.grid(row=2, column=0, sticky="nsew", padx=PAD_X, pady=(PAD_Y, 20))
    app.log_frame.grid_columnconfigure(0, weight=1)
    app.log_frame.grid_rowconfigure(1, weight=1)
    
    # C.1 日誌標題與收合按鈕
    log_title_frame = ctk.CTkFrame(app.log_frame, corner_radius=CARD_RADIUS, fg_color=CARD_COLOR, border_color=BORDER_COLOR, border_width=1)
    log_title_frame.grid(row=0, column=0, sticky="ew")
    log_title_frame.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(log_title_frame, text="日誌", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=15, pady=10, sticky="w")
    app.log_toggle_button = ctk.CTkButton(log_title_frame, text="▼", width=30, command=app.toggle_log_area, fg_color="transparent", hover_color=BTN_HOVER_COLOR, corner_radius=PILL_RADIUS)
    app.log_toggle_button.grid(row=0, column=1, padx=10, pady=5)
    
    # C.2 日誌文字區域
    log_bg_color = "#1C1C1C" # Console 效果的深色背景
    app.log_text = ctk.CTkTextbox(app.log_frame, font=("Consolas", 12), corner_radius=CARD_RADIUS, fg_color=log_bg_color, border_color=BORDER_COLOR, border_width=1)
    app.log_text.grid(row=1, column=0, sticky="nsew", pady=(0, 0))
    app.log_text.configure(state="disabled")
    
    app.root.protocol("WM_DELETE_WINDOW", app.on_closing)