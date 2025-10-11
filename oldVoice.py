# -*- coding: utf-8 -*-
# voice.py — 修正回呼缺失：先顯示主視窗 -> Log 檢查 -> 需要才詢問下載 -> 顯示下載進度

import os
import sys
import asyncio
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox
import numpy as np
import json
import shutil
import zipfile
import functools
import subprocess
import time
import ctypes
from datetime import datetime

# 外部庫
import customtkinter as ctk
from pynput import keyboard
import sounddevice as sd
from pydub import AudioSegment
import edge_tts
import pyttsx3

# 匯入重構後的模組
from audio_player import AudioPlayer

# Windows 特定依賴（非強制）
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

# =================================================================
# 基本設定
# =================================================================
def get_base_path():
    """
    取得應用程式資料的基準路徑。
    打包後: C:\\Users\\<user>\\AppData\\Local\\橘Mouth
    開發時: 腳本所在目錄
    """
    if getattr(sys, 'frozen', False):
        # 如果在 PyInstaller 包中執行，使用 AppData/Local
        app_data_path = os.path.join(os.environ['LOCALAPPDATA'], '橘Mouth')
        os.makedirs(app_data_path, exist_ok=True)
        return app_data_path
    else:
        # 在正常的 Python 環境中執行
        return os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = get_base_path() # 現在 SCRIPT_DIR 會指向 AppData 或開發目錄
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
CABLE_OUTPUT_HINT = "CABLE Input"
CABLE_INPUT_HINT = "CABLE Output"
VB_CABLE_SETUP_EXE = "VBCABLE_Setup_x64.exe"

DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"
ENGINE_EDGE = "edge-tts"
ENGINE_PYTTX3 = "pyttsx3"

IS_WINDOWS = sys.platform.startswith("win")
EXE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
FFMPEG_DIR = os.path.join(SCRIPT_DIR, "ffmpeg")
FFMPEG_BIN_DIR = os.path.join(FFMPEG_DIR, "bin")
FFMPEG_EXE = os.path.join(FFMPEG_BIN_DIR, "ffmpeg.exe" if IS_WINDOWS else "ffmpeg")
FFPROBE_EXE = os.path.join(FFMPEG_BIN_DIR, "ffprobe.exe" if IS_WINDOWS else "ffprobe")

FFMPEG_DOWNLOAD_SOURCES = [
    {
        "name": "gyan.dev-essentials",
        "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "kind": "zip",
    },
    {
        "name": "gyan.dev-full-essentials",
        "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-full-essentials.zip",
        "kind": "zip",
    },
]

VB_CABLE_DOWNLOAD_URL = "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack43.zip"

def _extract_zip(zip_path: str, target_dir: str, progress_cb=None):
    _ensure_dir(target_dir)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(target_dir)
    if progress_cb:
        progress_cb(1.0, "解壓縮完成。")
# =================================================================
# 依賴助手工具函式
# =================================================================
def _console_info(msg: str):
    # 在打包版本中，我們不希望有控制台輸出。
    # 這些訊息已經透過 self.log_message() 顯示在 UI 上了。
    pass

def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def _prepend_env_path(p: str):
    if not p:
        return
    env_path = os.environ.get("PATH", "")
    parts = env_path.split(os.pathsep) if env_path else []
    if p not in parts:
        os.environ["PATH"] = p + os.pathsep + env_path if env_path else p

def _which(exe_names):
    for name in exe_names:
        p = shutil.which(name)
        if p:
            return p
    return None

def has_system_ffmpeg() -> bool:
    return bool(_which(["ffmpeg.exe", "ffmpeg"]) and _which(["ffprobe.exe", "ffprobe"]))

def has_bundled_ffmpeg() -> bool:
    return os.path.isfile(FFMPEG_EXE) and os.path.isfile(FFPROBE_EXE)

def _ffmpeg_version_ok(path_ffmpeg: str) -> bool:
    try:
        res = subprocess.run([path_ffmpeg, "-version"], capture_output=True, text=True, timeout=5)
        return res.returncode == 0 and ("ffmpeg" in (res.stdout.lower() + res.stderr.lower()))
    except Exception:
        return False

def _download_with_progress(url: str, dst: str, progress_cb=None):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    start = time.time()
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
        total = getattr(r, "length", None)
        downloaded = 0
        last_report = start
        last_bytes = 0
        chunk_size = 1024 * 512
        while True:
            chunk = r.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            now = time.time()
            if progress_cb:
                pct = (downloaded / total) if total else 0.0
                dt = max(1e-3, now - last_report)
                inst_speed = (downloaded - last_bytes) / dt  # B/s
                mbps = inst_speed / (1024 * 1024)
                elapsed = now - start
                if (now - last_report) >= 0.2 or (total and downloaded == total):
                    text = f"下載中… {pct*100:5.1f}% | {downloaded/1024/1024:,.2f} MB"
                    if total:
                        text += f" / {total/1024/1024:,.2f} MB"
                    text += f" | {mbps:,.2f} MB/s | {int(elapsed)}s"
                    progress_cb(min(0.8, pct * 0.8), text)
                    last_report = now
                    last_bytes = downloaded
        if progress_cb:
            progress_cb(0.8, "下載完成，準備解壓…")

def _extract_ffmpeg_zip(zip_path: str, target_bin_dir: str, progress_cb=None, status_cb=None):
    _ensure_dir(target_bin_dir)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        tmp_dir = tempfile.mkdtemp(prefix="ffmpeg_zip_")
        try:
            if status_cb: status_cb("解壓中…")
            zf.extractall(tmp_dir)
            cand_bin_dir = None
            for root, dirs, files in os.walk(tmp_dir):
                low = [f.lower() for f in files]
                if ("ffmpeg.exe" in low or "ffmpeg" in low) and ("ffprobe.exe" in low or "ffprobe" in low):
                    cand_bin_dir = root
                    break
                if os.path.basename(root).lower() == "bin":
                    if ("ffmpeg.exe" in low or "ffmpeg" in low):
                        cand_bin_dir = root
                        break
            if not cand_bin_dir:
                for root, dirs, files in os.walk(tmp_dir):
                    low = [f.lower() for f in files]
                    if "ffmpeg.exe" in low or "ffmpeg" in low:
                        cand_bin_dir = root
                        break
            if not cand_bin_dir:
                raise RuntimeError("壓縮包內未找到 ffmpeg/ffprobe")

            items = os.listdir(cand_bin_dir)
            total = max(1, len(items))
            for i, fname in enumerate(items, 1):
                src = os.path.join(cand_bin_dir, fname)
                dst = os.path.join(target_bin_dir, fname)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                if progress_cb:
                    progress_cb(min(1.0, 0.8 + 0.2 * (i / total)), f"解壓中… {int(100 * (i/total))}%")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

# =================================================================
# 主應用
# =================================================================
class LocalTTSPlayer:
    def __init__(self):
        # 初始變數
        self._config = {}
        self.is_running = False
        self.current_engine = ENGINE_EDGE
        self.edge_voice = DEFAULT_EDGE_VOICE
        self.pyttsx3_voice_id = None
        self.tts_rate = 175
        self.tts_volume = 1.0
        self.current_hotkey = "+z"
        self.quick_phrases = [] # 新增：快捷語音列表
        self.quick_input_position = "bottom-right" # 新增：輸入框位置設定
        self.enable_quick_phrases = True
        self.enable_listen_to_self = False
        self.listen_device_name = "Default"
        self.listen_volume = 1.0
        self._listen_devices = {}
        self.listen_device_combo = None # 新增：提前初始化

        self.local_output_device_name = "Default"
        self._local_output_devices = {}
        self.cable_is_present = False
        self._input_window_lock = threading.Lock() # 新增一個鎖來防止重複開啟輸入框
        self._quick_phrase_lock = threading.Lock() # 用於快捷語音錄製
        self._playback_lock = threading.Lock() # 防止同時播放多個音訊

        self.hotkey_listener = None
        self.quick_input_window = None
        self.settings_window = None # 新增：設定視窗的引用
        self._pyttsx3_engine = None
        self._pyttsx3_voices = []
        self._edge_voices = []
        self.quick_phrases_window = None # 新增：快捷語音視窗的引用
        
        self._hotkey_recording_listener = None
        self._pressed_keys = set()
        self._is_hotkey_edit_mode = False

        # 初始化服務
        self.audio_player = AudioPlayer(self.log_message, self.get_config_value)
        self._listen_devices = {} # 仍然由主程式管理設備列表
        self._recording_key_index = None # 記錄當前正在錄製哪個按鈕 (0, 1, 2)
        
        # 先顯示主視窗
        ctk.set_appearance_mode("System") # System, Dark, Light
        self._build_ui()
        
        # 載入設定
        self._load_config()
        self.current_engine = self._config.get("engine", ENGINE_EDGE)
        self.edge_voice = self._config.get("voice", DEFAULT_EDGE_VOICE)
        self.tts_rate = self._config.get("rate", 175)
        self.tts_volume = self._config.get("volume", 1.0)
        self.quick_phrases = self._config.get("quick_phrases", [])
        self.quick_input_position = self._config.get("quick_input_position", "bottom-right")
        self.enable_quick_phrases = self._config.get("enable_quick_phrases", True)
        self.enable_listen_to_self = self._config.get("enable_listen_to_self", False)
        self.listen_device_name = self._config.get("listen_device_name", "Default")
        self.listen_volume = self._config.get("listen_volume", 1.0)
        
    def get_config_value(self, key, default=None):
        """提供給其他模組獲取設定值的方法"""
        # 優先從實例變數獲取，因為它代表了當前的UI狀態
        if hasattr(self, key):
            return getattr(self, key)
        return self._config.get(key, default)

        # 先從設定檔更新變數
        self.current_hotkey = self._normalize_hotkey(self._config.get("hotkey", "<shift>+z"))
        self._update_hotkey_display(self.current_hotkey)

        # 背景執行檢查流程（先 Log 檢查，再需要時才詢問）
        threading.Thread(target=self._dependency_flow_thread, daemon=True).start()

    # ================ UI 建構與進度列 =================
    def _build_ui(self):
        self.root = ctk.CTk()
        self.root.title("橘Mouth - TTS 語音助手")
        self.root.geometry("680x720")
        self.root.resizable(False, False)
        
        # --- 全域 UI 設定 ---
        CORNER_RADIUS = 12
        PAD_X = 20
        PAD_Y = 10
        
        # --- 顏色定義 ---
        FG_COLOR = ("#FFFFFF", "#333333")
        self.BORDER_COLOR = ("#E0E0E0", "#404040")
        self.BTN_COLOR = "#708090"  # 沉穩的藍灰色 (Slate Gray)
        self.BTN_HOVER_COLOR = "#5D6D7E" # 按下時的深色版本
        
        # 使用 Grid 佈局，並設定日誌行(row 7)和主列(column 0)可縮放
        self.root.grid_rowconfigure(6, weight=1) # 將權重行改為第 6 行
        self.root.grid_columnconfigure(0, weight=1)

        # --- 改為純 Grid 佈局 ---
        ctrl = ctk.CTkFrame(self.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=1)
        ctrl.grid(row=0, column=0, sticky="ew", padx=PAD_X, pady=(20, PAD_Y))

        self.start_button = ctk.CTkButton(ctrl, text="▶ 啟動", command=self.start_local_player, corner_radius=CORNER_RADIUS, fg_color=self.BTN_COLOR, hover_color=self.BTN_HOVER_COLOR)
        self.start_button.grid(row=0, column=0, padx=15, pady=15)

        self.stop_button = ctk.CTkButton(ctrl, text="■ 停止", command=self.stop_local_player, state="disabled", fg_color="#D32F2F", hover_color="#B71C1C", corner_radius=CORNER_RADIUS)
        self.stop_button.grid(row=0, column=1, padx=15, pady=15)

        # 使用一個空的 Label 來做彈性間隔
        spacer = ctk.CTkLabel(ctrl, text="")
        spacer.grid(row=0, column=2, sticky="ew")
        ctrl.grid_columnconfigure(2, weight=1) # 讓 spacer 填滿空間

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
        self.engine_combo.set(self.current_engine)
        self.engine_combo.grid(row=0, column=1, sticky="ew", padx=15, pady=10)

        ctk.CTkLabel(sel, text="語音聲線:").grid(row=1, column=0, padx=15, pady=10, sticky="w")
        self.voice_combo = ctk.CTkOptionMenu(sel, values=[DEFAULT_EDGE_VOICE], command=self._on_voice_change, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, button_color=self.BTN_COLOR, button_hover_color=self.BTN_HOVER_COLOR)
        self.voice_combo.grid(row=1, column=1, sticky="ew", padx=15, pady=10)
        sel.grid_columnconfigure(1, weight=1)

        tts = ctk.CTkFrame(self.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=1)
        tts.grid(row=3, column=0, sticky="ew", padx=PAD_X, pady=PAD_Y)

        ctk.CTkLabel(tts, text="語速:", width=100).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        self.speed_slider = ctk.CTkSlider(tts, from_=100, to=250, command=self.update_tts_settings, button_color=self.BTN_COLOR, button_hover_color=self.BTN_HOVER_COLOR, progress_color=self.BTN_COLOR)
        self.speed_slider.set(self.tts_rate)
        self.speed_slider.grid(row=0, column=1, sticky="ew", padx=15, pady=(15, 5))
        self.speed_value_label = ctk.CTkLabel(tts, text=f"{self.tts_rate}", width=50)
        self.speed_value_label.grid(row=0, column=2, sticky="e", padx=15, pady=(15, 5))

        ctk.CTkLabel(tts, text="音量:", width=100).grid(row=1, column=0, padx=15, pady=(5, 15), sticky="w")
        self.volume_slider = ctk.CTkSlider(tts, from_=0.5, to=1.0, command=self.update_tts_settings, button_color=self.BTN_COLOR, button_hover_color=self.BTN_HOVER_COLOR, progress_color=self.BTN_COLOR)
        self.volume_slider.set(self.tts_volume)
        self.volume_slider.grid(row=1, column=1, sticky="ew", padx=15, pady=(5, 15))
        self.volume_value_label = ctk.CTkLabel(tts, text=f"{self.tts_volume:.2f}", width=50)
        self.volume_value_label.grid(row=1, column=2, sticky="e", padx=15, pady=(5, 15))
        tts.grid_columnconfigure(1, weight=1)

        hotkey_frame = ctk.CTkFrame(self.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=1)
        hotkey_frame.grid(row=4, column=0, sticky="ew", padx=PAD_X, pady=PAD_Y)

        ctk.CTkLabel(hotkey_frame, text="快捷鍵:").grid(row=0, column=0, padx=15, pady=15, sticky="w")
        
        # --- 新的快捷鍵顯示區塊 ---
        keys_display_frame = ctk.CTkFrame(hotkey_frame, fg_color="transparent")
        keys_display_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=15)
        self.hotkey_key_buttons = []
        for i in range(3):
            # 使用 lambda 捕獲當前的 i 值
            btn = ctk.CTkButton(keys_display_frame, text="", width=80, state="disabled", corner_radius=8,
                                fg_color=("#EAEAEA", "#4A4A4A"),
                                text_color=("#101010", "#E0E0E0"),
                                border_color=("#C0C0C0", "#5A5A5A"), # 增加邊框以區分
                                border_width=1, # 增加邊框以區分
                                command=lambda idx=i: self._prepare_single_key_recording(idx))
            btn.grid(row=0, column=i, padx=5)
            self.hotkey_key_buttons.append(btn)
        
        # 讓按鍵區塊和編輯按鈕之間有彈性空間
        hotkey_frame.grid_columnconfigure(1, weight=1)

        self.hotkey_edit_button = ctk.CTkButton(hotkey_frame, text="✏️ 編輯", width=100, command=self._toggle_hotkey_edit, corner_radius=CORNER_RADIUS, fg_color=self.BTN_COLOR, hover_color=self.BTN_HOVER_COLOR)
        self.hotkey_edit_button.grid(row=0, column=2, sticky="e", padx=15, pady=15)

        info = ctk.CTkFrame(self.root, fg_color="transparent")
        info.grid(row=5, column=0, sticky="ew", padx=PAD_X, pady=(0, 0))
        self.hotkey_info_label = ctk.CTkLabel(info, text="點擊 '編輯' 開始設定快捷鍵。", font=ctk.CTkFont(size=11), text_color="gray")
        self.hotkey_info_label.pack(pady=0, fill="x")

        # 下載進度列
        dl_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        dl_frame.grid(row=6, column=0, sticky="sew", padx=PAD_X, pady=(0, PAD_Y)) # 讓它貼在底部
        self.download_bar = ctk.CTkProgressBar(dl_frame, corner_radius=CORNER_RADIUS, progress_color=self.BTN_COLOR)
        self.download_bar.set(0.0)
        self.download_bar.pack(fill="x", expand=False, pady=(8, 2))
        self.download_label = ctk.CTkLabel(dl_frame, text="", anchor="w", font=ctk.CTkFont(family="Consolas"))
        self.download_label.pack(fill="x", expand=False)
        self._toggle_download_ui(False)

        # 日誌區域
        log = ctk.CTkFrame(self.root, corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=1)
        log.grid(row=6, column=0, sticky="nsew", padx=PAD_X, pady=(PAD_Y, 20)) # 也放在第 6 行
        self.log_text = ctk.CTkTextbox(log, font=("Consolas", 12), corner_radius=CORNER_RADIUS, fg_color=FG_COLOR, border_color=self.BORDER_COLOR, border_width=0)
        self.log_text.pack(fill="both", expand=True, padx=1, pady=1)
        self.log_text.configure(state="disabled") # 設為唯讀

        dl_frame.tkraise() # 確保下載進度列在日誌區域之上
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _toggle_download_ui(self, show: bool):
        def upd():
            try:
                if show:
                    self.download_bar.grid()
                    self.download_label.configure(text="[----------] 0.0% | 下載準備中…")
                    self.download_bar.master.tkraise() # 顯示時，將其置於頂層
                else:
                    self.download_bar.master.grid_remove() # 隱藏整個 dl_frame
            except Exception:
                pass
        self.root.after(0, upd)

    def _update_download_ui(self, progress: float, text: str):
        # 將進度條改為文字顯示
        def upd():
            try:
                p = max(0.0, min(1.0, progress))
                self.download_bar.set(p) # 仍然更新背景的圖形進度條

                # 產生文字進度條
                bar_len = 20
                filled_len = int(bar_len * p)
                bar = '█' * filled_len + '-' * (bar_len - filled_len)
                
                # 組合最終的文字
                progress_text = f"[{bar}] {p*100:5.1f}% | {text}"
                self.download_label.configure(text=progress_text)
            except Exception:
                pass
        self.root.after(0, upd)

    def log_message(self, msg, level="INFO"):
        # 專業化日誌格式
        def upd():
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_msg = f"[{timestamp}] [{level.upper():<5}] {msg}\n"
            self.log_text.configure(state="normal") # 暫時啟用以插入文字
            self.log_text.insert(tk.END, formatted_msg)
            self.log_text.see(tk.END)
            self.log_text.configure(state="disabled") # 恢復唯讀
        self.root.after(0, upd)

    def _log_playback_status(self, status_icon, message):
        """專門用來更新播放狀態的日誌函式，會覆寫最後一行。"""
        def upd():
            timestamp = datetime.now().strftime("%H:%M:%S")
            # 組合最終的文字
            formatted_msg = f"[{timestamp}] [PLAY ] {status_icon} {message}\n"
            
            self.log_text.configure(state="normal")
            self.log_text.delete("end-2c linestart", "end-1c") # 刪除上一行
            self.log_text.insert(tk.END, formatted_msg)
            self.log_text.see(tk.END)
            self.log_text.configure(state="disabled")
        self.root.after(0, upd)

    # ================ 設定與保存 =================
    def _load_config(self):
        self._config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            except Exception as e:
                self.log_message(f"載入配置檔失敗: {e}", "ERROR")

    def _save_config(self):
        self._config["engine"] = self.current_engine
        if self.current_engine == ENGINE_EDGE:
            self._config["voice"] = self.edge_voice
        elif self.pyttsx3_voice_id and self._pyttsx3_voices:
            voice_obj = next((v for v in self._pyttsx3_voices if v.id == self.pyttsx3_voice_id), None)
            self._config["voice"] = voice_obj.name if voice_obj else self._config.get("voice", "default")
        else:
            self._config["voice"] = self._config.get("voice", "default")
        self._config["rate"] = self.tts_rate
        self._config["volume"] = self.tts_volume

        # 創建一個乾淨的快捷語音列表來儲存，移除UI元件的引用
        clean_quick_phrases = []
        for phrase in self.quick_phrases:
            clean_quick_phrases.append({
                "text": phrase.get("text", ""),
                "hotkey": phrase.get("hotkey", "")
            })
        self._config["hotkey"] = self.current_hotkey
        self._config["quick_phrases"] = clean_quick_phrases
        self._config["quick_input_position"] = self.quick_input_position
        self._config["enable_quick_phrases"] = self.enable_quick_phrases
        self._config["enable_listen_to_self"] = self.enable_listen_to_self
        self._config["listen_device_name"] = self.listen_device_name
        self._config["listen_volume"] = self.listen_volume
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log_message(f"儲存配置檔失敗: {e}", "ERROR")

    def _log_status_update(self, status_icon, message, level="INFO"):
        """專門用來更新狀態的日誌函式，會覆寫最後一行。"""
        def upd():
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_msg = f"[{timestamp}] [{level.upper():<5}] {status_icon} {message}\n"
            
            self.log_text.configure(state="normal")
            # 檢查文字框是否為空，如果不是，才刪除上一行
            if self.log_text.get("1.0", "end-1c").strip():
                self.log_text.delete("end-2c linestart", "end-1c")
            self.log_text.insert(tk.END, formatted_msg)
            self.log_text.see(tk.END)
            self.log_text.configure(state="disabled")
        self.root.after(0, upd)

    # ================ 依賴流程（先Log，後詢問） =================
    def _dependency_flow_thread(self):
        self.log_message("開始檢查依賴...") # 插入一個初始行
        self._log_status_update("[|]", "檢查系統 ffmpeg/ffprobe…")
        if has_system_ffmpeg():
            self._log_status_update("[✔]", "已找到系統 ffmpeg/ffprobe，將直接使用。")
            self._post_dependency_ok()
            return

        self._log_status_update("[-]", "未找到系統 ffmpeg/ffprobe，檢查內嵌版本…")

        if os.path.isdir(FFMPEG_BIN_DIR):
            _prepend_env_path(FFMPEG_BIN_DIR)

        if has_bundled_ffmpeg() and _ffmpeg_version_ok(FFMPEG_EXE):
            self._log_status_update("[✔]", "已找到內嵌 ffmpeg/ffprobe，將直接使用。")
            _prepend_env_path(FFMPEG_BIN_DIR)
            self._post_dependency_ok()
            return

        self._log_status_update("[!]", "未找到 ffmpeg/ffprobe，需要使用者操作。", "WARN")

        # 將決策權交回主執行緒
        self.root.after(0, self._prompt_ffmpeg_download)

    def _prompt_ffmpeg_download(self):
        """在主執行緒中詢問使用者是否下載，如果同意則啟動下載。"""
        should_download = messagebox.askyesno( # noqa: E127
            "依賴安裝助手",
            "未找到 ffmpeg/ffprobe。\n是否自動下載並安裝到本地 ffmpeg/bin？"
        )
        if should_download:
            # 在背景執行緒中執行下載和解壓縮
            threading.Thread(target=self._download_and_install_ffmpeg, daemon=True).start()
        else:
            self.log_message("使用者取消下載，依賴檢查未完成。", "WARN")
            messagebox.showerror("錯誤", "缺少 ffmpeg/ffprobe，無法進行音訊轉檔/探測。")

    def _download_and_install_ffmpeg(self):
        """實際執行下載和安裝的函式。"""
        # self._toggle_download_ui(True) # 不再使用獨立的下載UI，進度直接顯示在主日誌區
        try:
            _ensure_dir(FFMPEG_BIN_DIR)
            with tempfile.TemporaryDirectory(prefix="ffdl_") as temp_download_dir:
                ok = False
                last_err = None
                for src in FFMPEG_DOWNLOAD_SOURCES:
                    try:
                        tmp_zip = os.path.join(temp_download_dir, f"{src['name']}.zip")
                        self._log_status_update("[↓]", f"準備從 {src['name']} 下載 ffmpeg…", "INFO")
                        _download_with_progress(
                            src["url"], tmp_zip,
                            progress_cb=lambda p, t: self._log_status_update("[↓]", t, "INFO")
                        )
                        self._log_status_update("[ unpacking ]", "下載完成，準備解壓…", "INFO")
                        _extract_ffmpeg_zip(
                            tmp_zip, FFMPEG_BIN_DIR,
                            progress_cb=lambda p, t: self._log_status_update("[ unpacking ]", t, "INFO"),
                            status_cb=lambda t: self.log_message(t)
                        )
                        if has_bundled_ffmpeg() and _ffmpeg_version_ok(FFMPEG_EXE):
                            ok = True
                            break
                    except Exception as e:
                        last_err = e
                        self.log_message(f"來源 {src['name']} 失敗：{e}", "WARN")
                        continue
                if not ok:
                    if last_err:
                        raise last_err
                    raise RuntimeError("無法從預設來源下載/解壓 ffmpeg。")
            _prepend_env_path(FFMPEG_BIN_DIR)
            self._log_status_update("[✔]", f"ffmpeg 已成功安裝至 {FFMPEG_BIN_DIR}", "INFO")
            self.root.after(0, self._post_dependency_ok_ui)
        except Exception as e:
            self.log_message(f"安裝 ffmpeg 失敗：{e}", "ERROR")
            self.root.after(0, lambda: messagebox.showerror("錯誤", f"安裝 ffmpeg 失敗：{e}"))
        finally:
            pass # 下載進度現在顯示在主日誌區，不再需要獨立的UI

    def _post_dependency_ok(self):
        threading.Thread(target=self._load_voices_and_devices_background, daemon=True).start()

    def _post_dependency_ok_ui(self):
        """在主執行緒中處理 ffmpeg 安裝完成後的 UI 互動和後續步驟"""
        messagebox.showinfo("完成", "ffmpeg/ffprobe 已安裝到本地 ffmpeg/bin。")
        self._post_dependency_ok()

    # ================ VB-CABLE 與裝置載入 =================
    def _check_and_install_cable(self) -> bool:
        try:
            devices = sd.query_devices()
        except Exception as e:
            self.log_message(f"查詢音訊設備失敗: {e}", "ERROR")
            return False
        cable_installed = any(CABLE_OUTPUT_HINT.upper() in d['name'].upper() for d in devices)
        if cable_installed:
            self.log_message("VB-CABLE 驅動已存在，繼續載入。")
            self.cable_is_present = True
            
            # 清理邏輯：如果驅動已安裝，且安裝資料夾存在於 EXE 同目錄，則刪除它
            vbcable_install_dir = os.path.join(EXE_DIR, "vbcable")
            if os.path.isdir(vbcable_install_dir):
                try:
                    shutil.rmtree(vbcable_install_dir)
                    self.log_message("偵測到 VB-CABLE 已安裝，自動清理安裝檔案。")
                except Exception as e:
                    self.log_message(f"清理 VB-CABLE 安裝檔案失敗: {e}", "WARN")
            return True
        
        self.log_message("未偵測到 VB-CABLE 驅動。準備啟動安裝程序引導...", "WARN")
        
        # 將檢查、下載、安裝的邏輯都交給主執行緒處理
        self.root.after(0, self._handle_vbcable_installation)
        return False # 返回 False，因為安裝流程尚未完成

    def _handle_vbcable_installation(self):
        """在主執行緒中處理 VB-CABLE 的檢查、下載和安裝引導"""
        setup_path = os.path.join(EXE_DIR, "vbcable", VB_CABLE_SETUP_EXE)

        if os.path.exists(setup_path):
            self._prompt_run_vbcable_setup(setup_path)
        else:
            should_download = messagebox.askyesno(
                "VB-CABLE 安裝助手",
                "未偵測到 VB-CABLE 驅動，且找不到安裝程式。\n\n"
                "是否要從官方網站自動下載 VB-CABLE 安裝包？"
            )
            if should_download:
                threading.Thread(target=self._download_and_extract_vbcable, daemon=True).start()
            else:
                self.log_message("使用者取消下載 VB-CABLE。", "WARN")
                messagebox.showerror("錯誤", "缺少 VB-CABLE 驅動，部分功能將無法使用。")

    def _download_and_extract_vbcable(self):
        """在背景執行緒中下載並解壓縮 VB-CABLE"""
        self._toggle_download_ui(True)
        try:
            target_dir = os.path.join(EXE_DIR, "vbcable") # 下載到 EXE 旁邊，方便使用者找到安裝程式
            _ensure_dir(target_dir)
            with tempfile.TemporaryDirectory(prefix="vbcable_") as td:
                tmp_zip = os.path.join(td, "VBCABLE_Driver_Pack.zip")
                self.log_message("正在下載 VB-CABLE 安裝包...")
                _download_with_progress(
                    VB_CABLE_DOWNLOAD_URL, tmp_zip,
                    progress_cb=lambda p, t: self._update_download_ui(p, t)
                )
                self.log_message("下載完成，正在解壓縮...")
                _extract_zip(tmp_zip, target_dir, progress_cb=lambda p, t: self._update_download_ui(p, t))
            
            setup_path = os.path.join(target_dir, VB_CABLE_SETUP_EXE)
            if os.path.exists(setup_path):
                self.log_message("VB-CABLE 安裝包已準備就緒。")
                self.root.after(0, lambda: self._prompt_run_vbcable_setup(setup_path))
            else:
                raise RuntimeError(f"解壓縮後未找到 {VB_CABLE_SETUP_EXE}")
        except Exception as e:
            self.log_message(f"下載或解壓縮 VB-CABLE 失敗: {e}", "ERROR")
            self.root.after(0, lambda: messagebox.showerror("錯誤", f"下載 VB-CABLE 失敗: {e}"))
        finally:
            self._toggle_download_ui(False)

    def _prompt_run_vbcable_setup(self, setup_path: str):
        """在主執行緒中提示使用者執行安裝程式"""
        result = messagebox.askyesno(
            "VB-CABLE 安裝提示",
            "TTS 語音輸入 Discord 需要 VB-CABLE 驅動程式。\n\n"
            f"點擊 '是' 將啟動安裝程序，您可能需要授權管理員權限並點擊 'Install Driver'。\n\n"
            "安裝後，請重新啟動本應用程式。",
            icon='info'
        )
        if result:
            try:
                # 使用 ctypes.windll.shell32.ShellExecuteW 請求管理員權限 (runas)
                # 這是觸發 UAC 彈窗的標準方法
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None,  # hwnd
                    "runas",  # lpOperation
                    setup_path,  # lpFile
                    None,  # lpParameters
                    os.path.dirname(setup_path),  # lpDirectory
                    1  # nShowCmd
                )
                if ret <= 32: # 如果返回值小於等於32，表示發生錯誤
                    raise OSError(f"ShellExecuteW 啟動安裝程式失敗，錯誤碼: {ret}")
                self.root.after(1000, self.on_closing) # 延遲一秒後自動關閉，給使用者時間反應
            except Exception as e:
                self.log_message(f"VB-CABLE 安裝執行錯誤: {e}", "ERROR")
        else:
            self.log_message("使用者取消了 VB-CABLE 安裝。", "WARN")

    def _load_voices_and_devices_background(self):
        try:
            if not self._check_and_install_cable():
                return
            self._pyttsx3_engine = pyttsx3.init()
            self._pyttsx3_voices = self._pyttsx3_engine.getProperty("voices")
            asyncio.run(self._load_edge_voices())
            self._load_local_devices()
            self.root.after(0, self._update_ui_after_load)
            self.log_message("依賴與設備載入完成。")
        except Exception as e:
            self.log_message(f"初始化錯誤: {e}", "ERROR")

    def _update_ui_after_load(self):
        self.engine_combo.set(self.current_engine)
        self.speed_slider.set(self.tts_rate)
        self.volume_slider.set(self.tts_volume)
        self._update_voice_combobox_items()
        self._update_listen_device_combobox_items()
        self._update_local_device_combobox_items()

    async def _load_edge_voices(self):
        try:
            vm = await edge_tts.VoicesManager.create()
            self._edge_voices = [v for v in vm.voices if v.get("Locale", "").startswith("zh-")]
        except Exception as e:
            self.log_message(f"Edge TTS 載入失敗: {e}", "WARN")

    def _load_local_devices(self):
        try:
            devices = sd.query_devices()
            output_devices = [d for d in devices if d['max_output_channels'] > 0]
            self._listen_devices = {d['name']: d['index'] for d in output_devices}
            self._local_output_devices = {d['name']: d['index'] for d in output_devices}
            found_cable = False
            for d in output_devices:
                if CABLE_OUTPUT_HINT.upper() in d['name'].upper():
                    self.local_output_device_name = d['name']
                    self.cable_is_present = True
                    found_cable = True
                    break
            if not found_cable:
                self.local_output_device_name = "未找到 VB-CABLE!"
                self.log_message("設備列表載入完成，但未偵測到 VB-CABLE。", "WARN")
            else:
                self.log_message(f"已綁定輸出設備：{self.local_output_device_name}")
        except Exception as e:
            self.log_message(f"取得音效卡失敗: {e}", "ERROR")

    # ================ 控制與播放 =================
    def start_local_player(self):
        if self.is_running:
            return
        if not self.cable_is_present:
            messagebox.showerror(
                "錯誤",
                "無法啟動：未偵測到 VB-CABLE 虛擬喇叭。\n"
                "請重新啟動應用程式以啟動安裝引導，或手動安裝後再試。"
            )
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

            # 組合所有需要監聽的快捷鍵
            hotkeys = {}
            # 主輸入框快捷鍵
            if self.current_hotkey:
                hotkeys[self.current_hotkey] = self._show_quick_input
            
            # 快捷語音
            if self.enable_quick_phrases:
                for phrase in self.quick_phrases:
                    hk = phrase.get("hotkey")
                    text = phrase.get("text")
                    if hk and text:
                        # 使用 functools.partial 捕獲當前的 text 值
                        hotkeys[hk] = functools.partial(self._play_quick_phrase, text)

            self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
            self.hotkey_listener.start()
            self.log_message(f"服務已啟動，監聽 {len(hotkeys)} 個快捷鍵。")
        except Exception as e:
            self.log_message(f"快捷鍵啟動失敗: {e}。請檢查格式。", "ERROR")

    def _key_to_str(self, key):
        """將 pynput 的 key 物件轉換為標準化字串"""
        if isinstance(key, keyboard.Key):
            return f"<{key.name.split('_')[0]}>"
        if isinstance(key, keyboard.KeyCode):
            if key.char:
                return key.char.lower()
        return None

    async def _synth_edge_to_file(self, text, path):
        rate_param = f"{int(round((self.tts_rate - 175) * (40 / 75))):+d}%"
        volume_param = f"{int((self.tts_volume - 1.0) * 100):+d}%"
        comm = edge_tts.Communicate(text, self.edge_voice, rate=rate_param, volume=volume_param)
        await comm.save(path)

    def _synth_pyttsx3_to_file(self, text, path):
        if not self._pyttsx3_engine:
            self.log_message("pyttsx3 引擎未初始化。", "ERROR")
            raise RuntimeError("pyttsx3 engine not initialized.")
        self._pyttsx3_engine.setProperty("rate", self.tts_rate)
        self._pyttsx3_engine.setProperty("volume", self.tts_volume)
        if self.pyttsx3_voice_id:
            self._pyttsx3_engine.setProperty("voice", self.pyttsx3_voice_id)
        self._pyttsx3_engine.save_to_file(text, path)
        self._pyttsx3_engine.runAndWait()

    def _animate_playback(self, text, stop_event):
        """在背景執行緒中顯示播放動畫"""
        animation_chars = ['|', '/', '-', '\\']
        i = 0
        while not stop_event.is_set():
            char = animation_chars[i % len(animation_chars)]
            self._log_playback_status(f"[{char}]", f"正在處理: {text[:20]}...")
            i += 1
            time.sleep(0.1)

    def _resample_audio_segment(self, audio_segment, target_rate):
        """回傳已重取樣的 AudioSegment（如原本已是 target_rate，直接回傳）"""
        if int(audio_segment.frame_rate) == int(target_rate):
            return audio_segment
        return audio_segment.set_frame_rate(int(target_rate))

    def _audiosegment_to_float32_numpy(self, audio_segment):
        """把 pydub.AudioSegment 轉成 float32 numpy array（範圍 -1.0 .. +1.0）。
        若為雙聲道會回傳 shape (n,2)，單聲道回傳 (n,)
        """
        samples = np.array(audio_segment.get_array_of_samples())
        samples = samples.astype(np.float32)
        # pydub 的 samples 對於 stereo 會 interleave，需 reshape
        if audio_segment.channels == 2:
            samples = samples.reshape((-1, 2))
        else:
            samples = samples.reshape((-1,))

        # normalize by sample width (e.g. 2 bytes -> 16-bit)
        max_val = float(2 ** (8 * audio_segment.sample_width - 1))
        samples = samples / max_val
        return samples

    def _play_local(self, text):
        """重寫版 _play_local：自動處理各設備取樣率、重取樣與並行播放。
        會在日誌中紀錄嘗試與錯誤。
        """
        # 建立事件迴圈與動畫
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        animation_stop_event = threading.Event()
        animation_thread = threading.Thread(
            target=self._animate_playback,
            args=(text, animation_stop_event),
            daemon=True
        )

        synth_suffix = ".mp3" if self.current_engine == ENGINE_EDGE else ".wav"
        fd, synth_path = tempfile.mkstemp(suffix=synth_suffix)
        os.close(fd)

        animation_thread.start()

        try:
            # 產生語音檔
            if self.current_engine == ENGINE_EDGE:
                loop.run_until_complete(self._synth_edge_to_file(text, synth_path))
            else:
                self._synth_pyttsx3_to_file(text, synth_path)

            audio = AudioSegment.from_file(synth_path)

            # 取得主要設備與聆聽設備 id
            main_device_id = self._local_output_devices.get(self.local_output_device_name)
            if main_device_id is None:
                main_device_id = sd.default.device[1]

            listen_device_id = None
            if self.enable_listen_to_self:
                listen_device_id = self._listen_devices.get(self.listen_device_name)
                if listen_device_id is None:
                    listen_device_id = sd.default.device[1]

            # 查詢每個設備的 default_samplerate 與通道數
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

            # 如果不啟用聆聽或兩個設備相同，直接用 single-device 流（重取樣成 main_sr）
            if not self.enable_listen_to_self or listen_device_id is None or listen_device_id == main_device_id:
                # 只針對 main_device 播放z
                target_sr = main_sr
                if int(audio.frame_rate) != int(target_sr):
                    self.log_message(f"重取樣音訊: {audio.frame_rate}Hz -> {target_sr}Hz", "DEBUG")
                    audio_play = self._resample_audio_segment(audio, target_sr)
                else:
                    audio_play = audio

                samples = self._audiosegment_to_float32_numpy(audio_play)

                # 如果裝置期望 stereo 而 audio 為 mono，則複製一個 channel
                if samples.ndim == 1 and main_max_ch >= 2:
                    samples = np.column_stack((samples, samples))

                try:
                    sd.play(samples, samplerate=target_sr, device=main_device_id)
                    sd.wait()  # 等待播放結束
                    self._log_playback_status("[✔]", f"播放完畢: {text[:20]}...")
                except Exception as e:
                    self.log_message(f"播放到主設備失敗: {e}", "ERROR")
                    try:
                        sd.stop()
                    except Exception:
                        pass
                finally:
                    return

            # 若到此代表 enable_listen_to_self 且兩個設備不同：嘗試同時非阻塞播放到兩個設備（各自用其支援取樣率）
            # 準備 main samples
            if int(audio.frame_rate) != int(main_sr):
                self.log_message(f"重取樣給 main: {audio.frame_rate}Hz -> {main_sr}Hz", "DEBUG")
                audio_main = self._resample_audio_segment(audio, main_sr)
            else:
                audio_main = audio

            samples_main = self._audiosegment_to_float32_numpy(audio_main)
            if samples_main.ndim == 1 and main_max_ch >= 2:
                samples_main = np.column_stack((samples_main, samples_main))

            # 準備 listen samples（單獨用 listen_sr），注意乘上 listen_volume
            if int(audio.frame_rate) != int(listen_sr):
                audio_listen = self._resample_audio_segment(audio, listen_sr)
            else:
                audio_listen = audio

            samples_listen = self._audiosegment_to_float32_numpy(audio_listen) * float(self.listen_volume)
            if samples_listen.ndim == 1 and listen_max_ch >= 2:
                samples_listen = np.column_stack((samples_listen, samples_listen))

            # 使用獨立執行緒，以阻塞模式同時在兩個不同設備上播放音訊
            # 這是處理不同音訊設備最穩健的方法
            playback_errors = []

            def play_blocking(data, sr, dev_id, text_snippet):
                try:
                    sd.play(data, samplerate=sr, device=dev_id, blocking=True)
                except Exception as e:
                    playback_errors.append(e)
                    self.log_message(f"在設備 {dev_id} 播放 '{text_snippet}' 時失敗: {e}", "ERROR")

            thread_main = threading.Thread(
                target=play_blocking,
                args=(samples_main, main_sr, main_device_id, text[:10])
            )
            thread_listen = threading.Thread(
                target=play_blocking,
                args=(samples_listen, listen_sr, listen_device_id, text[:10])
            )

            thread_main.start()
            thread_listen.start()

            thread_main.join()
            thread_listen.join()

            if not playback_errors:
                self._log_playback_status("[✔]", f"播放完畢: {text[:20]}...")
            else:
                self._log_playback_status("[❌]", f"播放時發生錯誤: {text[:20]}...")

        except Exception as e:
            self.log_message(f"播放錯誤: {e}", "ERROR")
        finally:
            animation_stop_event.set()
            try:
                if animation_thread.is_alive():
                    animation_thread.join(timeout=0.2)
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass
            if os.path.exists(synth_path):
                try:
                    os.remove(synth_path)
                except Exception:
                    pass


    def _play_sequentially(self, samples, samplerate, main_device_id, listen_device_id):
        finally:
            self._playback_lock.release()
        """舊版兼容函式 — 我們保留但改為更健壯：會為每個設備個別重取樣並嘗試播放（blocking）"""
        try:
            # main
            try:
                sd.play(samples, samplerate=samplerate, device=main_device_id, blocking=True)
            except Exception as e_main:
                # 嘗試使用 main device 的 default samplerate
                try:
                    main_info = sd.query_devices(main_device_id)
                    main_sr = int(main_info.get('default_samplerate', samplerate))
                    self.log_message(f"main 播放失敗，嘗試重取樣到 main 的 default_samplerate: {main_sr}Hz", "DEBUG")
                    # 重新用 pydub 進行重取樣 — 但 samples 是 numpy，這裡我們保守處理為錯誤回報
                    raise e_main
                except Exception:
                    raise e_main

            # listen (若不同)
            if self.enable_listen_to_self and listen_device_id is not None and listen_device_id != main_device_id:
                try:
                    sd.play(samples * self.listen_volume, samplerate=samplerate, device=listen_device_id, blocking=True)
                except Exception as e_listen:
                    try:
                        listen_info = sd.query_devices(listen_device_id)
                        listen_sr = int(listen_info.get('default_samplerate', samplerate))
                        self.log_message(f"listen 播放失敗，建議重取樣到 {listen_sr}Hz 再試。", "WARN")
                    except Exception:
                        pass
                    raise e_listen
        except Exception as e:
            self.log_message(f"循序播放失敗: {e}", "ERROR")
            try:
                sd.stop()
            except Exception:
                pass

    def _play_quick_phrase(self, text):
        """專門用於播放快捷語音的函式"""
        if not self.is_running:
            return
        threading.Thread(target=self._play_local, args=(text,), daemon=True).start()

    # ================ Hotkey 與回呼（新版獨立錄製） =================
    def _format_keys(self, keys):
        """將 pynput 的按鍵物件集合格式化為字串"""
        if not keys:
            return ""
        key_str = self._key_to_str(list(keys)[0])
        return key_str.replace('<', '').replace('>', '').capitalize()

    def _on_key_press(self, key):
        """單鍵錄製模式下的按鍵按下事件"""
        if self._recording_key_index is None:
            return False

        # 按下 Esc 或 Delete 清除該按鈕
        if key == keyboard.Key.esc:
            key_text = ""
        elif key == keyboard.Key.delete or key == keyboard.Key.backspace:
            key_text = ""
        else:
            key_str = self._key_to_str(key)
            key_text = key_str.replace('<', '').replace('>', '').capitalize() if key_str else ""
        
        btn = self.hotkey_key_buttons[self._recording_key_index]
        btn.configure(text=key_text, fg_color=("#EAEAEA", "#4A4A4A"))
        
        self.log_message(f"第 {self._recording_key_index + 1} 個按鍵已設定為: {key_text or '無'}")
        self._recording_key_index = None
        return False # 停止監聽

    def _on_key_release(self, key):
        # 在單鍵錄製模式下，我們只關心 on_press，所以 on_release 可以忽略
        pass

    def _prepare_single_key_recording(self, index):
        """準備錄製單個按鍵，這是按鈕的 command"""
        if not self._is_hotkey_edit_mode:
            return
        
        # 如果正在錄製其他按鈕，先取消
        if self._recording_key_index is not None and self._recording_key_index != index:
            old_btn = self.hotkey_key_buttons[self._recording_key_index]
            old_btn.configure(fg_color=("#EAEAEA", "#4A4A4A")) # 恢復顏色

        self._recording_key_index = index
        btn = self.hotkey_key_buttons[index]
        btn.configure(text="...", fg_color="#FFA726") # 提示錄製中

        if self._hotkey_recording_listener:
            self._hotkey_recording_listener.stop()

        self._hotkey_recording_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self._hotkey_recording_listener.start()
        self.log_message(f"正在錄製第 {index+1} 個按鍵... (按 Esc 或 Delete 清除)")

    def _toggle_hotkey_edit(self):
        self._is_hotkey_edit_mode = not self._is_hotkey_edit_mode

        if self._is_hotkey_edit_mode:
            # 進入編輯模式
            self.hotkey_edit_button.configure(text="✅ 完成", fg_color="#FFA726", hover_color="#FB8C00")
            for btn in self.hotkey_key_buttons:
                btn.configure(state="normal")
            self.log_message("進入快捷鍵編輯模式。請點擊下方按鈕進行錄製。")
            self.hotkey_info_label.configure(text="點擊按鍵區塊錄製單鍵，按 Esc 或 Delete 可清除。")
        else:
            # 退出編輯模式，儲存結果
            if self._hotkey_recording_listener:
                self._hotkey_recording_listener.stop()
                self._hotkey_recording_listener = None
            if self._recording_key_index is not None:
                # 如果退出時還有按鈕在錄製中，恢復其外觀
                btn = self.hotkey_key_buttons[self._recording_key_index]
                btn.configure(fg_color=("#EAEAEA", "#4A4A4A"))
                self._recording_key_index = None

            self.hotkey_edit_button.configure(text="✏️ 編輯", fg_color=self.BTN_COLOR, hover_color=self.BTN_HOVER_COLOR)
            for btn in self.hotkey_key_buttons:
                btn.configure(state="disabled")
            self.hotkey_info_label.configure(text="點擊 '編輯' 開始設定快捷鍵。")

            # 從按鈕文字構建新的快捷鍵字串
            parts = []
            for btn in self.hotkey_key_buttons:
                text = btn.cget("text")
                if text:
                    # 將 'Ctrl' 這種易讀格式轉回 pynput 的 '<ctrl>' 格式
                    lower_text = text.lower()
                    if lower_text in ['ctrl', 'alt', 'shift', 'cmd', 'win']:
                        parts.append(f"<{lower_text}>")
                    else:
                        parts.append(lower_text)
            
            new_hotkey = "+".join(parts)
            self.current_hotkey = self._normalize_hotkey(new_hotkey)
            self._update_hotkey_display(self.current_hotkey) # 再次更新以確保格式正確

            if self.is_running:
                self._start_hotkey_listener()
            self.log_message(f"快捷鍵已儲存並鎖定為: {self.current_hotkey or '無'}")
            self._save_config()

    def _update_hotkey_display(self, hotkey_str):
        """更新快捷鍵顯示區塊的 UI"""
        parts = hotkey_str.split('+')
        for i, btn in enumerate(self.hotkey_key_buttons):
            if i < len(parts):
                # 將 <ctrl> 這種格式轉為更易讀的 Ctrl
                text = parts[i].replace('<', '').replace('>', '').capitalize()
                btn.configure(text=text)
            else:
                btn.configure(text="")
    
    def _normalize_hotkey(self, hotkey_str):
        """將快捷鍵字串標準化為 pynput 接受的格式"""
        # 確保組合鍵順序一致，並處理大小寫和尖括號
        if not hotkey_str:
            return ""
        
        parts = hotkey_str.lower().split('+')
        
        # 分離修飾鍵（帶尖括號）和普通鍵
        modifiers = sorted([p for p in parts if p.startswith('<') and p.endswith('>')])
        normal_keys = sorted([p for p in parts if not (p.startswith('<') and p.endswith('>'))])
        
        return "+".join(modifiers + normal_keys)

    def _on_engine_change(self, val):
        self.current_engine = val
        self.log_message(f"切換引擎: {self.current_engine}")
        self._update_voice_combobox_items()
        self._save_config()

    def _on_voice_change(self, choice):
        val = choice
        if self.current_engine == ENGINE_EDGE:
            self.edge_voice = val or DEFAULT_EDGE_VOICE
        else:
            if self._pyttsx3_voices:
                for v in self._pyttsx3_voices:
                    if v.name == val:
                        self.pyttsx3_voice_id = v.id
                        break
        self.log_message(f"已選定語音: {val}")
        self._save_config()

    def update_tts_settings(self, _=None):
        # UI 綁定回呼：同步滑桿到設定
        self.tts_rate = int(self.speed_slider.get())
        self.tts_volume = round(self.volume_slider.get(), 2)
        self.speed_value_label.configure(text=f"{self.tts_rate}")
        self.volume_value_label.configure(text=f"{self.tts_volume:.2f}")
        self._save_config()

    def _update_voice_combobox_items(self):
        def upd():
            if self.current_engine == ENGINE_EDGE:
                values = [DEFAULT_EDGE_VOICE] + [v["ShortName"] for v in self._edge_voices]
                self.voice_combo.configure(values=values)
                self.voice_combo.set(self.edge_voice if self.edge_voice in values else DEFAULT_EDGE_VOICE)
            else:
                names = [v.name for v in self._pyttsx3_voices]
                self.voice_combo.configure(values=names)
                loaded_name = self._config.get("voice")
                if loaded_name in names:
                    self.voice_combo.set(loaded_name)
                    for v in self._pyttsx3_voices:
                        if v.name == loaded_name:
                            self.pyttsx3_voice_id = v.id
                            break
                else:
                    self.voice_combo.set(names[0] if names else "default")
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, upd)
        else:
            upd()

    def _update_local_device_combobox_items(self):
        def upd():
            device_names = list(self._local_output_devices.keys())
            if not device_names:
                device_names = ["Default (無可用設備)"]
            self.local_device_combo.configure(values=device_names)
            if self.local_output_device_name not in device_names:
                self.local_output_device_name = device_names[0] if device_names else "Default"
                self.local_device_combo.set(self.local_output_device_name)
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, upd)
        else:
            upd()

    # ================ 其他 UI =================
    def _show_quick_input(self):
        # 嘗試獲取鎖，如果失敗（表示另一個執行緒正在創建視窗），則直接返回
        if not self._input_window_lock.acquire(blocking=False):
            return

        if self.quick_input_window and self.quick_input_window.winfo_exists():
            try:
                self.quick_input_window.lift()
                self.quick_input_window.focus_force()
            except:
                pass
            finally:
                self._input_window_lock.release() # 無論如何都要釋放鎖
            return

        win = ctk.CTkToplevel(self.root)
        win.overrideredirect(True) # 隱藏視窗的標題列和邊框
        
        # --- Windows 焦點強制取得 ---
        def force_foreground_and_focus(target_win):
            if not pywin32_installed or not target_win.winfo_exists():
                # 非 Windows 或視窗已關閉，使用 tkinter 內建方法
                target_win.lift()
                target_win.focus_force()
                return

            try:
                # 取得視窗的 HWND (handle)
                hwnd = target_win.winfo_id()

                # 將視窗帶到前景並設為焦點
                win32gui.SetForegroundWindow(hwnd)
            except Exception as e:
                self.log_message(f"強制前景失敗: {e}", "WARN")
                # 如果 API 呼叫失敗，退回使用 tkinter 的方法
                target_win.lift()
                target_win.focus_force()

        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.95)
        win._focus_established = False

        w, h = 420, 38
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        
        # 根據設定計算位置
        if self.quick_input_position == "center":
            x = (screen_w - w) // 2
            y = (screen_h - h) // 2
        elif self.quick_input_position == "top-left":
            x = 20
            y = 50
        elif self.quick_input_position == "top-right":
            x = screen_w - w - 20
            y = 50
        elif self.quick_input_position == "bottom-left":
            x = 20
            y = screen_h - h - 50
        else: # 預設 "bottom-right"
            x = screen_w - w - 20
            y = screen_h - h - 50

        win.geometry(f"{w}x{h}+{x}+{y}")
        entry = ctk.CTkEntry(win, font=("Arial", 14), height=h)
        entry.pack(fill="both", expand=True, padx=2, pady=2)

        def on_destroy(event=None):
            # 確保視窗銷毀時鎖被釋放
            if self._input_window_lock.locked():
                self._input_window_lock.release()

        def close_if_focus_lost(event=None):
            # 延遲檢查，避免因短暫的焦點切換而關閉視窗
            def _check():
                if not win.winfo_exists():
                    return
                
                # 如果當前的焦點不在這個視窗的任何元件上，就關閉它
                focused_widget = win.focus_get()
                if focused_widget is None or focused_widget.winfo_toplevel() is not win:
                    win.destroy()
            
            win.after(100, _check)

        def secure_focus():
            try:
                if not win.winfo_exists():
                    on_destroy() # 如果視窗在獲取焦點前被關閉，也要釋放鎖
                    return

                entry.focus_set()
                entry.select_range(0, tk.END)
            except Exception as e:
                self.log_message(f"Focus attempt failed: {e}", "ERROR")

        # 延遲呼叫，確保視窗完全渲染後再設定焦點
        win.after(10, lambda: force_foreground_and_focus(win))
        win.after(20, secure_focus)

        # 綁定事件
        def send(event=None):
            text = entry.get().strip()
            if text:
                threading.Thread(target=self._play_local, args=(text,), daemon=True).start()
            win.destroy()

        entry.bind("<Return>", send)
        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<FocusOut>", close_if_focus_lost)
        win.bind("<Destroy>", on_destroy)

        self.quick_input_window = win

    def _open_settings_window(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.focus()
            return

        self.settings_window = ctk.CTkToplevel(self.root)
        self.settings_window.title("設定")
        self.settings_window.geometry("450x450")
        self.settings_window.resizable(False, False)
        self.settings_window.transient(self.root) # 讓設定視窗保持在主視窗之上
        self.settings_window.grab_set() # 獨佔焦點

        main_frame = ctk.CTkFrame(self.settings_window, fg_color="transparent")
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        # --- 快捷語音開關 ---
        quick_phrase_frame = ctk.CTkFrame(main_frame)
        quick_phrase_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(quick_phrase_frame, text="快捷語音功能:").pack(side="left", padx=10, pady=10)
        self.quick_phrase_switch = ctk.CTkSwitch(quick_phrase_frame, text="", command=self._on_toggle_quick_phrases)
        self.quick_phrase_switch.pack(side="right", padx=10, pady=10)
        if self.enable_quick_phrases:
            self.quick_phrase_switch.select()

        ctk.CTkLabel(main_frame, text="快捷輸入框顯示位置:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")

        position_var = ctk.StringVar(value=self.quick_input_position)
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

        # 使用 RadioButton 讓選項更清晰
        radio_frame = ctk.CTkFrame(main_frame)
        radio_frame.pack(pady=10, fill="x")

        for i, (text, value) in enumerate(positions.items()):
            rb = ctk.CTkRadioButton(radio_frame, text=text, variable=position_var, value=value, command=on_position_change)
            if i < 3:
                rb.grid(row=0, column=i, padx=10, pady=5, sticky="w")
            else:
                rb.grid(row=1, column=i-3, padx=10, pady=5, sticky="w")
        
        # --- 聆聽自己的語音 ---
        listen_frame = ctk.CTkFrame(main_frame)
        listen_frame.pack(fill="x", expand=True, pady=10)
        listen_frame.grid_columnconfigure(1, weight=1)

        listen_switch_frame = ctk.CTkFrame(listen_frame, fg_color="transparent")
        listen_switch_frame.grid(row=0, column=0, columnspan=3, sticky="ew")
        ctk.CTkLabel(listen_switch_frame, text="聆聽自己的語音:").pack(side="left", padx=10, pady=10)
        self.listen_switch = ctk.CTkSwitch(listen_switch_frame, text="", command=self._on_toggle_listen_to_self)
        self.listen_switch.pack(side="right", padx=10, pady=10)
        if self.enable_listen_to_self:
            self.listen_switch.select()

        ctk.CTkLabel(listen_frame, text="聆聽設備:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.listen_device_combo = ctk.CTkOptionMenu(listen_frame, values=["Default"], command=self._on_listen_device_change)
        self.listen_device_combo.grid(row=1, column=1, columnspan=2, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(listen_frame, text="聆聽音量:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.listen_volume_slider = ctk.CTkSlider(listen_frame, from_=0.0, to=1.0, command=self._on_listen_volume_change)
        self.listen_volume_slider.set(self.listen_volume)
        self.listen_volume_slider.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        self.listen_volume_label = ctk.CTkLabel(listen_frame, text=f"{self.listen_volume:.2f}", width=40)
        self.listen_volume_label.grid(row=2, column=2, padx=10, pady=5, sticky="w")

        self._update_listen_device_combobox_items()
        self._toggle_listen_controls()

    def _on_toggle_quick_phrases(self):
        self.enable_quick_phrases = bool(self.quick_phrase_switch.get())
        self.log_message(f"快捷語音功能已 {'啟用' if self.enable_quick_phrases else '停用'}")
        self._save_config()
        if self.is_running:
            self._start_hotkey_listener()

    def _on_toggle_listen_to_self(self):
        self.enable_listen_to_self = bool(self.listen_switch.get())
        self.log_message(f"聆聽自己的語音功能已 {'啟用' if self.enable_listen_to_self else '停用'}")
        self._toggle_listen_controls()
        self._save_config()

    def _toggle_listen_controls(self):
        state = "normal" if self.enable_listen_to_self else "disabled"
        self.listen_device_combo.configure(state=state)
        self.listen_volume_slider.configure(state=state)
        self.listen_volume_label.configure(state=state)

    def _on_listen_device_change(self, choice):
        self.listen_device_name = choice
        self.log_message(f"聆聽設備已設定為: {self.listen_device_name}")
        self._save_config()

    def _on_listen_volume_change(self, value):
        self.listen_volume = round(value, 2)
        self.listen_volume_label.configure(text=f"{self.listen_volume:.2f}")
        self._save_config()

    def _open_quick_phrases_window(self):
        if self.quick_phrases_window and self.quick_phrases_window.winfo_exists():
            self.quick_phrases_window.focus()
            return

        # 確保 quick_phrases 列表長度為 10
        while len(self.quick_phrases) < 10:
            self.quick_phrases.append({"text": "", "hotkey": ""})
        self.quick_phrases = self.quick_phrases[:10]

        self.quick_phrases_window = ctk.CTkToplevel(self.root)
        self.quick_phrases_window.title("快捷語音設定")
        self.quick_phrases_window.geometry("600x550")
        self.quick_phrases_window.transient(self.root)
        self.quick_phrases_window.grab_set()

        # --- UI 結構 ---
        self.phrase_list_frame = ctk.CTkScrollableFrame(self.quick_phrases_window, label_text="快捷語音列表")
        self.phrase_list_frame.pack(padx=20, pady=20, fill="both", expand=True)

        # 建立 10 個固定的欄位
        for index in range(10):
            phrase = self.quick_phrases[index]

            item_frame = ctk.CTkFrame(self.phrase_list_frame, fg_color=("gray90", "gray20"))
            item_frame.pack(fill="x", pady=5, padx=5)
            item_frame.grid_columnconfigure(0, weight=1)

            # 文字輸入框
            entry = ctk.CTkEntry(item_frame, placeholder_text=f"快捷語音 {index + 1}...")
            entry.insert(0, phrase.get("text", ""))
            entry.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
            
            # 綁定事件，當文字變更時自動儲存
            entry.bind("<FocusOut>", lambda event, i=index, e=entry: self._update_phrase_text(i, e.get()))
            entry.bind("<Return>", lambda event, i=index, e=entry: self._update_phrase_text(i, e.get(), True))

            # 快捷鍵按鈕
            hotkey_btn = ctk.CTkButton(item_frame, text=phrase.get("hotkey", "設定快捷鍵"), width=120,
                                       command=lambda i=index: self._record_quick_phrase_hotkey(i))
            hotkey_btn.grid(row=0, column=1, padx=10, pady=10)

            # 將 UI 元件的引用儲存起來，方便後續更新
            phrase["_entry_ref"] = entry
            phrase["_btn_ref"] = hotkey_btn

    def _update_phrase_text(self, index, text, unfocus=False):
        """更新指定索引的快捷語音文字並儲存"""
        # 從 UI 元件取得最新文字並更新到資料結構中
        current_text = self.quick_phrases[index]["_entry_ref"].get()
        self.quick_phrases[index]["text"] = current_text.strip()
        
        self._save_config()
        self.log_message(f"快捷語音 {index + 1} 已更新。")
        if unfocus:
            self.quick_phrases_window.focus() # 取消 entry 的焦點

    def _record_quick_phrase_hotkey(self, index_to_edit):
        if not self._quick_phrase_lock.acquire(blocking=False):
            self.log_message("已在錄製另一個快捷鍵，請先完成。", "WARN")
            return

        # 讓所有按鈕變暗，除了當前這個
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
            # 同步更新對應的文字
            current_text = self.quick_phrases[index_to_edit]["_entry_ref"].get()
            self.quick_phrases[index_to_edit]["text"] = current_text.strip()
            
            self._save_config()
            # 重繪所有按鈕的狀態
            for idx, p in enumerate(self.quick_phrases):
                btn = p.get("_btn_ref")
                if btn:
                    btn.configure(
                        text=p.get("hotkey") or "設定快捷鍵",
                        state="normal",
                        fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"]
                    )
            
            self.log_message(f"快捷語音 {index_to_edit + 1} 的快捷鍵已設為: {self.quick_phrases[index_to_edit]['hotkey'] or '無'}")
            self._quick_phrase_lock.release()
            
            # 如果服務正在運行，立即重啟監聽器以應用變更
            if self.is_running:
                self._start_hotkey_listener()
            
            return False # 停止監聽

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

    def on_closing(self):
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
        # 確保主視窗關閉時，如果輸入框還存在，也一併關閉
        if self.quick_input_window and self.quick_input_window.winfo_exists():
            self.quick_input_window.destroy()
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
        if self.quick_phrases_window and self.quick_phrases_window.winfo_exists():
            self.quick_phrases_window.destroy()
        self.root.destroy()

    def _update_listen_device_combobox_items(self):
        def upd():
            if not self.listen_device_combo: # 新增：檢查 UI 元件是否存在
                return
            device_names = list(self._listen_devices.keys())
            if not device_names:
                device_names = ["Default (無可用設備)"]
            self.listen_device_combo.configure(values=device_names)
            if self.listen_device_name not in device_names:
                self.listen_device_name = device_names[0] if device_names else "Default"
            self.listen_device_combo.set(self.listen_device_name)
        self.root.after(0, upd)
        # ... (此函式可以移到 settings_window.py 中)
        pass

    def run(self):
        self.root.mainloop()

# =================================================================
# 入口
# =================================================================
if __name__ == "__main__":
    if not sys.platform.startswith("win"):
        # 為了在非 Windows 平台上也能看到 UI，暫時不直接退出
        messagebox.showwarning("警告", "此應用程式主要為 Windows 設計，在您目前的作業系統上，部分功能（如 VB-CABLE 安裝）將無法使用。")
    else:
        # 解決 Windows 上因 DPI 縮放導致的 UI 模糊問題
        ctypes.windll.shcore.SetProcessDpiAwareness(1)

    if IS_WINDOWS and not comtypes_installed:
        messagebox.showwarning("警告", "缺少 'comtypes' 模組，語音引擎 'pyttsx3' 可能無法正常運作。")

    if IS_WINDOWS and not pywin32_installed:
        messagebox.showwarning("警告", "缺少 'pywin32' 模組，快捷鍵輸入框的焦點控制可能不穩定。")

    try:
        app = LocalTTSPlayer()
        app.run()
    except Exception as e:
        # 捕獲頂層錯誤並顯示
        messagebox.showerror("嚴重錯誤", f"應用程式遇到無法處理的錯誤並即將關閉。\n\n錯誤訊息：\n{e}")
        sys.exit()
()
