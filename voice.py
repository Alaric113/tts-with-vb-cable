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
import subprocess
import time
from datetime import datetime

# 外部庫
import customtkinter as ctk
from pynput import keyboard
import sounddevice as sd
from pydub import AudioSegment
import edge_tts
import pyttsx3

# Windows 特定依賴（非強制）
try:
    import comtypes.client  # noqa: F401
    from comtypes import CLSCTX_ALL  # noqa: F401
    comtypes_installed = True
except Exception:
    comtypes_installed = False
    print("Warning: 'comtypes' not installed.")
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
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
CABLE_OUTPUT_HINT = "CABLE Input"
CABLE_INPUT_HINT = "CABLE Output"
VB_CABLE_SETUP_EXE = "VBCABLE_Setup_x64.exe"

DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"
ENGINE_EDGE = "edge-tts"
ENGINE_PYTTX3 = "pyttsx3"

IS_WINDOWS = sys.platform.startswith("win")
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

# =================================================================
# 依賴助手工具函式
# =================================================================
def _console_info(msg: str):
    print(f"[Dependency] {msg}")

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
                    text = f"下載中… {pct*100:5.1f}%  |  {downloaded/1024/1024:,.2f} MB"
                    if total:
                        text += f" / {total/1024/1024:,.2f} MB"
                    text += f"  |  {mbps:,.2f} MB/s  |  {int(elapsed)}s"
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

        self.local_output_device_name = "Default"
        self._local_output_devices = {}
        self.cable_is_present = False

        self.hotkey_listener = None
        self.quick_input_window = None
        self._pyttsx3_engine = None
        self._pyttsx3_voices = []
        self._edge_voices = []
        
        self._hotkey_recording_listener = None
        self._pressed_keys = set()

        # 先顯示主視窗
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self._build_ui()

        # 載入設定
        self._load_config()
        self.current_engine = self._config.get("engine", ENGINE_EDGE)
        self.edge_voice = self._config.get("voice", DEFAULT_EDGE_VOICE)
        self.tts_rate = self._config.get("rate", 175)
        self.tts_volume = self._config.get("volume", 1.0)
        self.current_hotkey = self._normalize_hotkey(self._config.get("hotkey", "<shift>+z"))

        # 背景執行檢查流程（先 Log 檢查，再需要時才詢問）
        threading.Thread(target=self._dependency_flow_thread, daemon=True).start()

    # ================ UI 建構與進度列 =================
    def _build_ui(self):
        self.root = ctk.CTk()
        self.root.title("TTS 虛擬麥克風控制器 (VB-CABLE)")
        self.root.geometry("600x690")
        self.root.resizable(False, False)
        
        # 使用 Grid 佈局，並設定日誌行(row 6)和主列(column 0)可縮放
        self.root.grid_rowconfigure(7, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # --- 改為純 Grid 佈局 ---
        ctrl = ctk.CTkFrame(self.root)
        ctrl.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        self.start_button = ctk.CTkButton(ctrl, text="啟動", command=self.start_local_player)
        self.start_button.grid(row=0, column=0, padx=10, pady=10)

        self.stop_button = ctk.CTkButton(ctrl, text="停止", command=self.stop_local_player, state="disabled", fg_color="red")
        self.stop_button.grid(row=0, column=1, padx=10, pady=10)

        self.status_label = ctk.CTkLabel(ctrl, text="狀態: 未啟動", text_color="red")
        self.status_label.grid(row=0, column=2, padx=10)
        ctrl.columnconfigure(2, weight=1) # 讓狀態標籤靠右

        out = ctk.CTkFrame(self.root)
        out.grid(row=1, column=0, sticky="ew", padx=20, pady=10)

        ctk.CTkLabel(out, text="輸出設備:", anchor="w").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.local_device_combo = ctk.CTkOptionMenu(out, values=["Default"])
        self.local_device_combo.set("Default")
        self.local_device_combo.configure(state="disabled")
        self.local_device_combo.grid(row=0, column=1, sticky="ew", padx=10, pady=5)

        ctk.CTkLabel(out, text=f"Discord 麥克風請設定為: {CABLE_INPUT_HINT} (虛擬麥克風)", text_color="cyan", font=ctk.CTkFont(size=12, weight="bold")).grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        out.columnconfigure(1, weight=1)

        sel = ctk.CTkFrame(self.root)
        sel.grid(row=2, column=0, sticky="ew", padx=20, pady=10)

        ctk.CTkLabel(sel, text="引擎:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.engine_combo = ctk.CTkOptionMenu(sel, values=[ENGINE_EDGE, ENGINE_PYTTX3], command=self._on_engine_change)
        self.engine_combo.set(self.current_engine)
        self.engine_combo.grid(row=0, column=1, sticky="ew", padx=10, pady=5)

        ctk.CTkLabel(sel, text="語音:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.voice_combo = ctk.CTkOptionMenu(sel, values=[DEFAULT_EDGE_VOICE], command=self._on_voice_change)
        self.voice_combo.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        sel.columnconfigure(1, weight=1)

        tts = ctk.CTkFrame(self.root)
        tts.grid(row=3, column=0, sticky="ew", padx=20, pady=10)

        ctk.CTkLabel(tts, text="語速:", width=100).grid(row=0, column=0, padx=10, sticky="w")
        self.speed_slider = ctk.CTkSlider(tts, from_=100, to=250, command=self.update_tts_settings)
        self.speed_slider.set(self.tts_rate)
        self.speed_slider.grid(row=0, column=1, sticky="ew", padx=10)
        self.speed_value_label = ctk.CTkLabel(tts, text=f"{self.tts_rate}", width=50)
        self.speed_value_label.grid(row=0, column=2, sticky="e", padx=10)

        ctk.CTkLabel(tts, text="音量:", width=100).grid(row=1, column=0, padx=10, sticky="w")
        self.volume_slider = ctk.CTkSlider(tts, from_=0.5, to=1.0, command=self.update_tts_settings)
        self.volume_slider.set(self.tts_volume)
        self.volume_slider.grid(row=1, column=1, sticky="ew", padx=10)
        self.volume_value_label = ctk.CTkLabel(tts, text=f"{self.tts_volume:.2f}", width=50)
        self.volume_value_label.grid(row=1, column=2, sticky="e", padx=10)
        tts.columnconfigure(1, weight=1)

        hotkey_frame = ctk.CTkFrame(self.root)
        hotkey_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=10)

        ctk.CTkLabel(hotkey_frame, text="全域快捷鍵:").grid(row=0, column=0, padx=10, sticky="w")
        self.hotkey_entry = ctk.CTkEntry(hotkey_frame)
        self.hotkey_entry.insert(0, self.current_hotkey)
        self.hotkey_entry.configure(state="disabled")
        self.hotkey_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self.hotkey_entry.bind("<Return>", self._on_hotkey_change_entry)

        self.hotkey_edit_button = ctk.CTkButton(hotkey_frame, text="編輯", width=120, command=self._toggle_hotkey_edit)
        self.hotkey_edit_button.grid(row=0, column=2, sticky="e", padx=10)
        hotkey_frame.columnconfigure(1, weight=1)

        info = ctk.CTkFrame(self.root, fg_color="transparent")
        info.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 10))
        ctk.CTkLabel(info, text="點擊 '編輯' 後，按下您想設定的組合鍵 (按 Esc 可取消錄製)。", font=ctk.CTkFont(size=10)).pack(pady=2, fill="x")

        # 下載進度列
        dl_frame = ctk.CTkFrame(self.root)
        dl_frame.grid(row=6, column=0, sticky="ew", padx=20, pady=10)
        self.download_bar = ctk.CTkProgressBar(dl_frame)
        self.download_bar.set(0.0)
        self.download_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
        self.download_label = ctk.CTkLabel(dl_frame, text="", anchor="w", font=ctk.CTkFont(family="Consolas"))
        self.download_label.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 8))
        dl_frame.columnconfigure(0, weight=1)
        self._toggle_download_ui(False)

        log = ctk.CTkFrame(self.root)
        log.grid(row=6, column=0, sticky="nsew", padx=20, pady=(0, 14))
        self.log_text = ctk.CTkTextbox(log, font=("Consolas", 12)) # 移除固定的 height=8
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_text.configure(state="disabled") # 設為唯讀

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _toggle_download_ui(self, show: bool):
        def upd():
            try:
                if show:
                    self.download_bar.grid()
                    self.download_label.grid()
                    self.download_label.configure(text="[----------] 0.0% | 下載準備中…")
                else:
                    self.download_bar.grid_remove()
                    self.download_label.grid_remove()
                    self.download_label.configure(text="")
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
        self._config["hotkey"] = self.current_hotkey
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log_message(f"儲存配置檔失敗: {e}", "ERROR")

    # ================ 依賴流程（先Log，後詢問） =================
    def _dependency_flow_thread(self):
        self.log_message("檢查依賴：正在檢查系統 ffmpeg/ffprobe…")
        if has_system_ffmpeg():
            self.log_message("已找到系統 ffmpeg/ffprobe，將直接使用。")
            self._post_dependency_ok()
            return

        self.log_message("未找到系統 ffmpeg/ffprobe。")
        self.log_message("檢查依賴：正在檢查內嵌 ffmpeg/ffprobe…")

        if os.path.isdir(FFMPEG_BIN_DIR):
            _prepend_env_path(FFMPEG_BIN_DIR)

        if has_bundled_ffmpeg() and _ffmpeg_version_ok(FFMPEG_EXE):
            self.log_message("已找到內嵌 ffmpeg/ffprobe，將直接使用。")
            _prepend_env_path(FFMPEG_BIN_DIR)
            self._post_dependency_ok()
            return

        self.log_message("未找到內嵌 ffmpeg/ffprobe。")

        # 將決策權交回主執行緒
        self.root.after(0, self._prompt_ffmpeg_download)

    def _prompt_ffmpeg_download(self):
        """在主執行緒中詢問使用者是否下載，如果同意則啟動下載。"""
        should_download = messagebox.askyesno(
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
        self._toggle_download_ui(True)
        try:
            _ensure_dir(FFMPEG_BIN_DIR)
            with tempfile.TemporaryDirectory(prefix="ffdl_") as td:
                ok = False
                last_err = None
                for src in FFMPEG_DOWNLOAD_SOURCES:
                    try:
                        tmp_zip = os.path.join(td, f"{src['name']}.zip")
                        self.log_message(f"從 {src['name']} 下載 ffmpeg 套件…")
                        _download_with_progress(
                            src["url"], tmp_zip,
                            progress_cb=lambda p, t: self._update_download_ui(p, t)
                        )
                        self._update_download_ui(0.8, "下載完成，準備解壓…")
                        _extract_ffmpeg_zip(
                            tmp_zip, FFMPEG_BIN_DIR,
                            progress_cb=lambda p, t: self._update_download_ui(p, t),
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
            self.root.after(0, lambda: messagebox.showinfo("完成", "ffmpeg/ffprobe 已安裝到本地 ffmpeg/bin。"))
            self._post_dependency_ok()
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("錯誤", f"安裝 ffmpeg 失敗：{e}")) and self.log_message(f"安裝 ffmpeg 失敗：{e}", "ERROR")
        finally:
            self._toggle_download_ui(False)

    def _post_dependency_ok(self):
        threading.Thread(target=self._load_voices_and_devices_background, daemon=True).start()

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
            return True

        self.log_message("未偵測到 VB-CABLE 驅動。準備啟動安裝程序引導...", "WARN")
        setup_path = os.path.join(SCRIPT_DIR, VB_CABLE_SETUP_EXE)
        if not os.path.exists(setup_path):
            self.log_message(f"錯誤: 找不到安裝檔 {VB_CABLE_SETUP_EXE}。請手動下載並安裝。", "ERROR")
            return True

        def run_setup():
            try:
                result = messagebox.askyesno(
                    "VB-CABLE 安裝提示",
                    "TTS 語音輸入 Discord 需要 VB-CABLE 驅動程式。\n\n"
                    f"點擊 '是' 將啟動安裝程序 ({VB_CABLE_SETUP_EXE})，您可能需要授權管理員權限並點擊 Install Driver。\n"
                    "安裝後，請重新啟動本應用程式。",
                    icon='info'
                )
                if result:
                    subprocess.Popen(setup_path, shell=True)
                    messagebox.showinfo(
                        "請注意",
                        "請在彈出的 VB-CABLE 視窗中點擊 'Install Driver' 完成安裝。\n"
                        "安裝完成後，請手動關閉本應用程式並重新啟動。"
                    )
                    self.root.after(0, self.on_closing)
                else:
                    self.log_message("使用者取消了 VB-CABLE 安裝。", "WARN")
            except Exception as e:
                self.log_message(f"VB-CABLE 安裝執行錯誤: {e}", "ERROR")

        self.root.after(0, run_setup)
        return False

    def _load_voices_and_devices_background(self):
        try:
            if not self._check_and_install_cable():
                return
            self._pyttsx3_engine = pyttsx3.init()
            self._pyttsx3_voices = self._pyttsx3_engine.getProperty("voices")
            asyncio.run(self._load_edge_voices())
            self._load_local_devices()
            self.root.after(0, self._update_ui_after_load)
        except Exception as e:
            self.log_message(f"初始化錯誤: {e}", "ERROR")

    def _update_ui_after_load(self):
        self.engine_combo.set(self.current_engine)
        self.speed_slider.set(self.tts_rate)
        self.volume_slider.set(self.tts_volume)
        self._update_voice_combobox_items()
        self._update_local_device_combobox_items()
        self.hotkey_entry.delete(0, tk.END)
        self.hotkey_entry.insert(0, self.current_hotkey)
        if not self.cable_is_present:
            self.start_button.configure(text="啟動 (無 VB-CABLE)", fg_color="gray", hover_color="darkgray")

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
        self.status_label.configure(text="狀態: 已停止", text_color="red")
        self.log_message("服務已停止。")

    def _start_hotkey_listener(self):
        def on_hotkey():
            if self.is_running:
                try:
                    self.root.after(0, self._show_quick_input)
                except Exception as e:
                    self.log_message(f"hotkey callback error: {e}", "ERROR")
        try:
            if self.hotkey_listener:
                self.hotkey_listener.stop()
            self.hotkey_listener = keyboard.GlobalHotKeys({self.current_hotkey: on_hotkey})
            self.hotkey_listener.start()
            self.log_message(f"全域快捷鍵 '{self.current_hotkey}' 已啟用")
        except Exception as e:
            self.log_message(f"快捷鍵 '{self.current_hotkey}' 啟動失敗: {e}。請檢查格式是否符合 pynput 要求。", "ERROR")

    async def _synth_edge_to_file(self, text, path):
        rate_param = f"{int(round((self.tts_rate - 175) * (40 / 75))):+d}%"
        volume_param = f"{int((self.tts_volume - 1.0) * 100):+d}%"
        comm = edge_tts.Communicate(text, self.edge_voice, rate=rate_param, volume=volume_param)
        await comm.save(path)

    def _synth_pyttsx3_to_file(self, text, path):
        eng = self._pyttsx3_engine or pyttsx3.init()
        eng.setProperty("rate", self.tts_rate)
        eng.setProperty("volume", self.tts_volume)
        if self.pyttsx3_voice_id:
            eng.setProperty("voice", self.pyttsx3_voice_id)
        eng.save_to_file(text, path)
        eng.runAndWait()
        eng.stop()

    def _play_local(self, text):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        synth_suffix = ".mp3" if self.current_engine == ENGINE_EDGE else ".wav"
        fd, synth_path = tempfile.mkstemp(suffix=synth_suffix)
        os.close(fd)
        try:
            if self.current_engine == ENGINE_EDGE:
                self.log_message(f"生成 Edge TTS 音訊: {text[:20]}...")
                loop.run_until_complete(self._synth_edge_to_file(text, synth_path))
            else:
                self.log_message(f"生成 Pyttsx3 音訊: {text[:20]}...")
                self._synth_pyttsx3_to_file(text, synth_path)

            audio = AudioSegment.from_file(synth_path)
            samples = np.array(audio.get_array_of_samples()).astype(np.float32) / (2 ** (8 * audio.sample_width - 1))

            device_id = self._local_output_devices.get(self.local_output_device_name)
            if device_id is None:
                self.log_message("找不到 VB-CABLE Input，改用預設裝置。", "WARN")
                device_id = sd.default.device[1]

            self.log_message(f"播放到設備 [{device_id}] {self.local_output_device_name}")
            sd.play(samples, samplerate=audio.frame_rate, device=device_id, blocking=True)
            sd.stop()
            self.log_message("播放完成。")
        except Exception as e:
            self.log_message(f"播放錯誤: {e}", "ERROR")
        finally:
            loop.close()
            if os.path.exists(synth_path):
                os.remove(synth_path)

    # ================ Hotkey 與回呼（補齊） =================
    def _format_keys(self, keys):
        """將 pynput 的按鍵物件集合格式化為字串"""
        if not keys:
            return ""
        
        # pynput.keyboard.Key or pynput.keyboard.KeyCode
        key_strings = []
        for key in sorted(keys, key=lambda k: str(k)):
            # 對於特殊鍵，例如 Key.shift, Key.ctrl
            if isinstance(key, keyboard.Key):
                key_name = key.name
                # 移除 _l 或 _r 後綴，並標準化
                if key_name.endswith(('_l', '_r')):
                    key_name = key_name[:-2]
                key_strings.append(f"<{key_name}>")
            # 對於普通按鍵，例如 'a', 'z'
            elif isinstance(key, keyboard.KeyCode):
                # 確保 key.char 不是 None
                if key.char:
                    key_strings.append(key.char)

        return "+".join(key_strings)

    def _on_key_press(self, key):
        """錄製模式下的按鍵按下事件"""
        if key == keyboard.Key.esc:
            self._stop_hotkey_recording(cancel=True)
            return False # 停止監聽

        # --- 去重邏輯 ---
        # 檢查是否有等效的按鍵已經被按下（例如 'z' 和 'Z'）
        key_char = getattr(key, 'char', None)
        if key_char:
            lower_char = key_char.lower()
            for pressed_key in self._pressed_keys:
                if getattr(pressed_key, 'char', None) and getattr(pressed_key, 'char').lower() == lower_char:
                    return True # 如果等效按鍵已存在，則忽略此次事件

        self._pressed_keys.add(key)
        formatted_keys = self._format_keys(self._pressed_keys)
        self.hotkey_entry.delete(0, tk.END)
        self.hotkey_entry.insert(0, formatted_keys)
        return True

    def _on_key_release(self, key):
        """錄製模式下的按鍵釋放事件"""
        # 當有按鍵釋放時，就認為組合鍵已確定，結束錄製
        self._stop_hotkey_recording()
        return False # 停止監聽

    def _start_hotkey_recording(self):
        """開始監聽鍵盤以錄製新熱鍵"""
        if self._hotkey_recording_listener:
            return

        self.log_message("開始錄製熱鍵... 請按下新的組合鍵 (按 Esc 取消)")
        self.hotkey_edit_button.configure(text="錄製中... (Esc取消)", fg_color="orange")
        self.hotkey_entry.delete(0, tk.END)
        self.hotkey_entry.configure(state="normal")
        self.hotkey_entry.focus_set()
        self._pressed_keys.clear()

        # 創建並啟動一個新的監聽器
        self._hotkey_recording_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self._hotkey_recording_listener.start()

    def _stop_hotkey_recording(self, cancel=False):
        """停止熱鍵錄製"""
        if not self._hotkey_recording_listener:
            return

        self._hotkey_recording_listener.stop()
        self._hotkey_recording_listener = None

        if cancel:
            self.log_message("熱鍵錄製已取消。", "WARN")
            self._update_hotkey_ui_and_save(self.current_hotkey, save=False) # 恢復顯示舊的熱鍵
        else:
            new_hotkey = self.hotkey_entry.get().strip()
            if new_hotkey:
                self._update_hotkey_ui_and_save(new_hotkey)
            else:
                self.log_message("錄製到空的熱鍵，操作取消。", "WARN")
                self._update_hotkey_ui_and_save(self.current_hotkey, save=False)

    def _toggle_hotkey_edit(self):
        # 如果正在錄製，則不做任何事
        if self._hotkey_recording_listener:
            return
        self._start_hotkey_recording()

    def _update_hotkey_ui_and_save(self, hotkey_str, save=True):
        self.current_hotkey = self._normalize_hotkey(hotkey_str)
        self.hotkey_entry.delete(0, tk.END)
        self.hotkey_entry.insert(0, self.current_hotkey)
        self.hotkey_entry.configure(state="disabled")
        self.hotkey_edit_button.configure(text="編輯", fg_color="#3B8ED4", hover_color="#36719F")
        if save:
            if self.is_running:
                self._start_hotkey_listener()
            self.log_message(f"快捷鍵已儲存並鎖定為: {self.current_hotkey}")
            self._save_config()
    
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

    def _on_hotkey_change_entry(self, event=None):
        # 這個函式在新的錄製模式下不再需要，但保留以防萬一
        # 如果使用者在錄製時按下了 Enter，會觸發 on_release，自動結束錄製
        pass

    def update_tts_settings(self, _=None):
        # UI 綁定回呼：同步滑桿到設定
        self.tts_rate = int(self.speed_slider.get())
        self.tts_volume = round(self.volume_slider.get(), 2)
        self.speed_value_label.configure(text=f"{self.tts_rate}")
        self.volume_value_label.configure(text=f"{self.tts_volume:.2f}")
        self._save_config()

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
        if self.quick_input_window and self.quick_input_window.winfo_exists():
            try:
                self.quick_input_window.lift()
                self.quick_input_window.focus_force()
            except:
                pass
            return

        win = ctk.CTkToplevel(self.root)

        # --- Windows 焦點強制取得 ---
        def force_foreground_and_focus(target_win):
            if not pywin32_installed or not target_win.winfo_exists():
                return

            try:
                # 取得視窗的 HWND (handle)
                hwnd = target_win.winfo_id()

                # 模擬 Alt 鍵按下再放開，這是 Windows 允許前景切換的技巧
                win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)

                # 將視窗帶到前景並設為焦點
                win32gui.SetForegroundWindow(hwnd)
            except Exception as e:
                self.log_message(f"強制前景失敗: {e}")

        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.95)
        win._focus_established = False

        w, h = 420, 38
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = int(screen_w - w - 20)
        y = int(screen_h - h - 50)
        win.geometry(f"{w}x{h}+{x}+{y}")

        entry = ctk.CTkEntry(win, font=("Arial", 14), height=h)
        entry.pack(fill="both", expand=True, padx=2, pady=2)

        def close_window_if_lost_focus(event=None):
            def check_and_close():
                if not win.winfo_exists():
                    return
                if not win._focus_established:
                    return
                current_focus_widget = win.focus_get()
                try:
                    focus_toplevel = current_focus_widget.winfo_toplevel() if current_focus_widget else None
                    focus_is_on_self = (focus_toplevel is win)
                except Exception:
                    focus_is_on_self = False
                if win._focus_established and current_focus_widget != entry and current_focus_widget != win and not focus_is_on_self:
                    # self.log_message("輸入框失去焦點，自動關閉。") # 這條日誌太頻繁，可以選擇性關閉
                    win.destroy()
            win.after(150, check_and_close)

        def secure_focus():
            if not win.winfo_exists():
                return

            # 先呼叫 Windows API 強制前景
            force_foreground_and_focus(win)

            try:
                win.lift()
                win.focus_force()
                entry.focus_set()
                entry.select_range(0, tk.END)
                win.bind("<FocusOut>", close_window_if_lost_focus)
                entry.bind("<FocusOut>", close_window_if_lost_focus)
                win.after(300, lambda: setattr(win, '_focus_established', True))
            except Exception as e:
                self.log_message(f"focus 嘗試失敗: {e}", "ERROR")
        win.after(10, secure_focus) # 稍微延遲以確保視窗已建立

        def send(event=None):
            text = entry.get().strip()
            if text:
                threading.Thread(target=self._play_local, args=(text,), daemon=True).start()
            win.destroy()

        entry.bind("<Return>", send)
        entry.bind("<Escape>", lambda e: win.destroy())
        self.quick_input_window = win

    def on_closing(self):
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()

# =================================================================
# 入口
# =================================================================
if __name__ == "__main__":
    if not sys.platform.startswith("win"):
        messagebox.showerror("錯誤", "僅支援 Windows 並需安裝 VB-CABLE。")
        sys.exit()

    app = LocalTTSPlayer()
    app.run()
