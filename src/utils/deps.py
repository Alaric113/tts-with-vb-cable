# -*- coding: utf-8 -*-
# 檔案: utils_deps.py
# 功用: 提供整個應用程式所需的共用常數、工具函式以及核心依賴管理。
#      - 常數定義: 如設定檔路徑、VB-CABLE 名稱提示、TTS 引擎名稱等。
#      - 路徑管理: 提供一個可靠的方式來獲取應用程式的基礎路徑 (無論是開發模式還是打包後)。
#      - 環境工具: 包含檢查系統 PATH、新增路徑到 PATH 等功能。
#      - 依賴管理器 (DependencyManager): 一個核心類別，用於處理外部依賴：
#        - FFmpeg: 檢查系統或內嵌版本，若缺少則引導使用者從網路下載並解壓縮。
#        - VB-CABLE: 檢查驅動是否存在，若缺少則引導使用者下載並執行安裝程式。
#      - 網路與檔案工具: 包含帶進度回報的下載功能、ZIP 解壓縮功能等。

import os
import sys
import json
import zipfile
import shutil
import tempfile
import time
import subprocess
import urllib.request
import requests

IS_WINDOWS = sys.platform.startswith("win")

# ================= 基本路徑與常數 =================
def get_base_path():
    """
    獲取應用程式的基礎路徑。
    - 打包後: 指向 exe 所在的目錄。
    - 開發時: 指向專案根目錄 (包含 src, main.py 的地方)。
    """
    if getattr(sys, 'frozen', False):
        # 打包後，基礎路徑是 exe 所在的目錄
        return os.path.dirname(sys.executable)
    # 開發模式，基礎路徑是 main.py 所在的專案根目錄
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# BASE_DIR 現在是所有路徑的統一基準
BASE_DIR = get_base_path()
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
CACHE_DIR = os.path.join(BASE_DIR, "audio_cache")

TTS_MODELS_DIR = os.path.join(BASE_DIR, "tts_models")

# --- 應用程式版本與更新資訊 ---
APP_VERSION = "1.2.7"  # 您可以根據您的版本進度修改此處
GITHUB_REPO = "Alaric113/tts-with-vb-cable" # !! 請務必將 YOUR_USERNAME 替換成您的 GitHub 使用者名稱 !!

CABLE_OUTPUT_HINT = "CABLE Input"
CABLE_INPUT_HINT  = "CABLE Output"
VB_CABLE_SETUP_EXE = "VBCABLE_Setup_x64.exe"
VB_CABLE_DOWNLOAD_URL = "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack43.zip"

DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"
ENGINE_EDGE   = "edge-tts"
ENGINE_PYTTX3 = "pyttsx3"
ENGINE_CHAT_TTS = "ChatTTS (experimental)"
ENGINE_SHERPA_VITS_ZH_AISHELL3 = "sherpa-vits-zh-aishell3"
ENGINE_VITS_PIPER_EN_US_GLADOS = "vits-piper-en_US-glados"

# Set a Sherpa-ONNX model as the default engine if you want
# DEFAULT_ENGINE = ENGINE_VITS_PIPER_EN_US_GLADOS 


FFMPEG_DIR = os.path.join(BASE_DIR, "ffmpeg")
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

# ================= 通用工具 =================
def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def prepend_env_path(p: str):
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

def ffmpeg_version_ok(path_ffmpeg: str, startupinfo=None) -> bool:
    try:
        # --- 核心修正: 傳遞 startupinfo 以隱藏視窗 ---
        res = subprocess.run(
            [path_ffmpeg, "-version"], capture_output=True, text=True, timeout=5,
            startupinfo=startupinfo
        )
        return res.returncode == 0 and ("ffmpeg" in (res.stdout.lower() + res.stderr.lower()))
    except Exception:
        return False

def download_with_progress(url: str, dst: str, progress_cb=None):
    """使用 requests 函式庫並以較大的區塊下載檔案，以提升效能。"""
    start = time.time()
    headers = {"User-Agent": "Mozilla/5.0"}
    
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get('content-length', 0))
        downloaded = 0
        last_report = start
        last_bytes = 0
        chunk_size = 1024 * 512  # 512 KB chunk size for better performance

        with open(dst, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
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

def extract_zip(zip_path: str, target_dir: str, progress_cb=None):
    ensure_dir(target_dir)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(target_dir)
    if progress_cb:
        progress_cb(1.0, "解壓縮完成。")

def extract_ffmpeg_zip(zip_path: str, target_bin_dir: str, progress_cb=None, status_cb=None):
    ensure_dir(target_bin_dir)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        tmp_dir = tempfile.mkdtemp(prefix="ffmpeg_zip_")
        try:
            if status_cb: status_cb("解壓中…")
            zf.extractall(tmp_dir)
            cand_bin_dir = None
            for root, _, files in os.walk(tmp_dir):
                low = [f.lower() for f in files]
                if ("ffmpeg.exe" in low or "ffmpeg" in low) and ("ffprobe.exe" in low or "ffprobe" in low):
                    cand_bin_dir = root
                    break
                if os.path.basename(root).lower() == "bin":
                    if ("ffmpeg.exe" in low or "ffmpeg" in low):
                        cand_bin_dir = root
                        break
            if not cand_bin_dir:
                for root, _, files in os.walk(tmp_dir):
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
                    progress_cb(min(1.0, 0.8 + 0.2 * (i / total)), f"解壓中… {int(100 * (i/total))}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

# ================= 依賴處理（以回呼解耦 UI） =================
import tarfile
from pathlib import Path
from ..app.model_manager import PREDEFINED_MODELS

def extract_tar_bz2(tar_path: str, target_dir: str, progress_cb=None, log_cb=None):
    ensure_dir(target_dir)
    with tempfile.TemporaryDirectory() as tmp_extract_dir:
        # 1. Extract all contents to a temporary directory
        with tarfile.open(tar_path, "r:bz2") as tf:
            tf.extractall(path=tmp_extract_dir)

        if log_cb:
            log_cb(f"--- Extracted files in {tmp_extract_dir} ---", "INFO")
            for root, dirs, files in os.walk(tmp_extract_dir):
                level = root.replace(tmp_extract_dir, '').count(os.sep)
                indent = ' ' * 4 * (level)
                log_cb('{}{}/'.format(indent, os.path.basename(root)), "INFO")
                sub_indent = ' ' * 4 * (level + 1)
                for f in files:
                    log_cb('{}{}'.format(sub_indent, f), "INFO")
            log_cb("-------------------------------------------", "INFO")

        # 2. Check the contents of the temporary directory
        extracted_items = os.listdir(tmp_extract_dir)
        source_dir = tmp_extract_dir
        if log_cb:
            log_cb(f"Top-level extracted items: {extracted_items}", "INFO")

        # 3. If there is a single directory inside, assume it's the root and move its contents
        if len(extracted_items) == 1 and os.path.isdir(os.path.join(tmp_extract_dir, extracted_items[0])):
            source_dir = os.path.join(tmp_extract_dir, extracted_items[0])
            if log_cb:
                log_cb(f"Archive has a single root directory. Setting source_dir to: {source_dir}", "INFO")
        
        if log_cb:
            log_cb(f"Final source_dir for moving files is: {source_dir}", "INFO")
            try:
                log_cb(f"Items to be moved: {os.listdir(source_dir)}", "INFO")
            except Exception as e:
                log_cb(f"Could not list items in source_dir: {e}", "ERROR")


        # 4. Move all files and subdirectories from the source directory to the final target directory
        for item_name in os.listdir(source_dir):
            s = os.path.join(source_dir, item_name)
            d = os.path.join(target_dir, item_name)
            if log_cb:
                log_cb(f"Moving '{s}' to '{d}'", "INFO")
            
            # Overwrite existing files/dirs in the destination
            if os.path.exists(d):
                if os.path.isdir(d):
                    shutil.rmtree(d)
                else:
                    os.remove(d)
            shutil.move(s, d)

    if progress_cb:
        progress_cb(1.0, "模型解壓縮完成。")

def check_model_downloaded(model_id: str, log_cb=None) -> bool:
    if model_id not in PREDEFINED_MODELS:
        if log_cb: log_cb(f"Check failed for {model_id}: Not in PREDEFINED_MODELS.", "DEBUG")
        return False
    model_config = PREDEFINED_MODELS[model_id]
    model_dir = Path(TTS_MODELS_DIR) / model_id
    if not model_dir.exists():
        if log_cb: log_cb(f"Check failed for {model_id}: Directory {model_dir} does not exist.", "DEBUG")
        return False
    
    all_found = True
    for fname in model_config["file_names"]:
        f_path = model_dir / fname
        if not f_path.exists():
            if log_cb: log_cb(f"Check failed for {model_id}: File {f_path} does not exist.", "DEBUG")
            all_found = False
            # We could break here, but logging all missing files might be useful
    
    return all_found

def delete_model(model_id: str, log_cb=None):
    if model_id not in PREDEFINED_MODELS:
        if log_cb: log_cb(f"試圖刪除一個未定義的模型: {model_id}", "WARN")
        return
    try:
        model_dir = Path(TTS_MODELS_DIR) / model_id
        if model_dir.exists():
            shutil.rmtree(model_dir)
            if log_cb: log_cb(f"模型 '{model_id}' 已被刪除。", "INFO")
        else:
            if log_cb: log_cb(f"模型 '{model_id}' 不存在，無需刪除。", "INFO")
    except Exception as e:
        if log_cb: log_cb(f"刪除模型 '{model_id}' 時發生錯誤: {e}", "ERROR")

class DependencyManager:
    def __init__(self, log, status, ask_yes_no_sync, ask_yes_no_async, show_info, show_error, startupinfo=None):
        """
        log(text, level='INFO')
        status(icon_text, message, level='INFO')
        ask_yes_no_sync(title, message) -> bool
        ask_yes_no_async(title, message, callback)
        show_info(title, message)
        show_error(title, message)
        """
        self.log = log
        self.status = status
        self.ask_yes_no_sync = ask_yes_no_sync
        self.ask_yes_no_async = ask_yes_no_async
        self.show_info = show_info
        self.show_error = show_error
        self.startupinfo = startupinfo

        # NEW: Check for non-ASCII characters in TTS_MODELS_DIR
        try:
            TTS_MODELS_DIR.encode('ascii')
        except UnicodeEncodeError:
            self.log(f"警告：模型存放路徑 '{TTS_MODELS_DIR}' 包含非 ASCII 字元。這可能導致 Sherpa-ONNX 模型載入失敗。", "WARN")
            self.log("建議將應用程式移動到路徑不含中文或其他非英文字元的資料夾。", "WARN")


    # ---- ffmpeg ----
    def ensure_ffmpeg(self) -> bool:
        self.status("[|]", "檢查系統 ffmpeg/ffprobe…")
        if has_system_ffmpeg():
            self.status("[✔]", "已找到系統 ffmpeg/ffprobe，將直接使用。")
            return True

        self.status("[-]", "未找到系統 ffmpeg/ffprobe，檢查內嵌版本…")
        if os.path.isdir(FFMPEG_BIN_DIR):
            prepend_env_path(FFMPEG_BIN_DIR)

        if has_bundled_ffmpeg() and ffmpeg_version_ok(FFMPEG_EXE, self.startupinfo):
            self.status("[✔]", "已找到內嵌 ffmpeg/ffprobe，將直接使用。")
            prepend_env_path(FFMPEG_BIN_DIR)
            return True

        self.status("[!]", "未找到 ffmpeg/ffprobe，需要使用者操作。", "WARN")
        # --- 核心修正: 使用同步提問，並在本執行緒中處理下載 ---
        do_install = self.ask_yes_no_sync("依賴安裝助手", "未找到 ffmpeg/ffprobe。\n是否自動下載並安裝到本地 ffmpeg/bin？")

        if not do_install:
            self.log("使用者取消下載，依賴檢查未完成。", "WARN")
            self.show_error("錯誤", "缺少 ffmpeg/ffprobe，無法進行音訊轉檔/探測。")
            return False

        try:
            ensure_dir(FFMPEG_BIN_DIR)
            with tempfile.TemporaryDirectory(prefix="ffdl_") as temp_download_dir:
                ok = False
                last_err = None
                for src in FFMPEG_DOWNLOAD_SOURCES:
                    try:
                        tmp_zip = os.path.join(temp_download_dir, f"{src['name']}.zip")
                        self.status("[↓]", f"準備從 {src['name']} 下載 ffmpeg…", "INFO")
                        download_with_progress(
                            src["url"], tmp_zip,
                            progress_cb=lambda p, t: self.status("[↓]", t, "INFO")
                        )
                        self.status("[ unpacking ]", "下載完成，準備解壓…", "INFO")
                        extract_ffmpeg_zip(
                            tmp_zip, FFMPEG_BIN_DIR,
                            progress_cb=lambda p, t: self.status("[ unpacking ]", t, "INFO"),
                            status_cb=lambda t: self.log(t)
                        )
                        if has_bundled_ffmpeg() and ffmpeg_version_ok(FFMPEG_EXE, self.startupinfo):
                            ok = True
                            break
                    except Exception as e:
                        last_err = e
                        self.log(f"來源 {src['name']} 失敗：{e}", "WARN")
                        continue
                if not ok:
                    if last_err:
                        raise last_err
                    raise RuntimeError("無法從預設來源下載/解壓 ffmpeg。")
            prepend_env_path(FFMPEG_BIN_DIR)
            self.status("[✔]", f"ffmpeg 已成功安裝至 {FFMPEG_BIN_DIR}", "INFO")
            self.show_info("完成", "ffmpeg/ffprobe 已安裝到本地 ffmpeg/bin。")
            return True
        except Exception as e:
            self.log(f"安裝 ffmpeg 失敗：{e}", "ERROR")
            self.show_error("錯誤", f"安裝 ffmpeg 失敗：{e}")
            return False

    # ---- VB-CABLE （純流程與檔案處理，執行安裝仍交還 UI） ----
    def need_install_vbcable(self, list_devices_func) -> bool:
        try:
            devices = list_devices_func()
        except Exception as e:
            self.log(f"查詢音訊設備失敗: {e}", "ERROR")
            return True

        # CABLE_INPUT_HINT  = "CABLE Output" (這是麥克風/錄音設備)
        # CABLE_OUTPUT_HINT = "CABLE Input"  (這是喇叭/播放設備)
        device_names = [d.get('name', '').upper() for d in devices]

        # 僅偵測虛擬「麥克風」是否存在即可
        has_cable_input_device = any(CABLE_INPUT_HINT.upper() in name for name in device_names)

        if has_cable_input_device:
            self.log("已確認 VB-CABLE 存在。", "INFO")
            # 如果已安裝，則不需要做任何事，直接回報「不需要安裝」
            return False

        self.log(f"未偵測到 VB-CABLE，需要安裝。", "WARN")
        return True

    def prepare_vbcable_setup(self, on_have_setup_path, on_need_run_setup):
        """
        - 若 EXE 旁已有安裝檔，直接提示執行
        - 若無，詢問是否下載並解壓，完成後提示執行
        UI 互動交由呼叫端的 callback 處理
        """
        setup_path = os.path.join(BASE_DIR, "vbcable", VB_CABLE_SETUP_EXE)
        if os.path.exists(setup_path):
            on_have_setup_path(setup_path)
            return
        
        def on_user_choice(do_install):
            if not do_install:
                self.log("使用者取消下載 VB-CABLE。", "WARN")
                self.show_error("錯誤", "缺少 VB-CABLE 驅動，部分功能將無法使用。")
                return
            
            # 下載與解壓
            try:
                target_dir = os.path.join(BASE_DIR, "vbcable")
                ensure_dir(target_dir)
                with tempfile.TemporaryDirectory(prefix="vbcable_") as td:
                    tmp_zip = os.path.join(td, "VBCABLE_Driver_Pack.zip")
                    self.log("正在下載 VB-CABLE 安裝包...")
                    download_with_progress(
                        VB_CABLE_DOWNLOAD_URL, tmp_zip,
                        progress_cb=lambda p, t: self.log(t)
                    )
                    self.log("下載完成，正在解壓縮...")
                    extract_zip(tmp_zip, target_dir, progress_cb=lambda p, t: self.log(t))

                setup_path = os.path.join(target_dir, VB_CABLE_SETUP_EXE)
                if os.path.exists(setup_path):
                    self.log("VB-CABLE 安裝包已準備就緒。", "INFO")
                    on_need_run_setup(setup_path)
                else:
                    raise RuntimeError(f"解壓縮後未找到 {VB_CABLE_SETUP_EXE}")
            except Exception as e:
                self.log(f"下載或解壓縮 VB-CABLE 失敗: {e}", "ERROR")
                self.show_error("錯誤", f"下載 VB-CABLE 失敗: {e}")

        self.ask_yes_no_async("VB-CABLE 安裝助手", "未偵測到 VB-CABLE 驅動，且找不到安裝程式。\n\n是否要從官方網站自動下載 VB-CABLE 安裝包？", on_user_choice)

from PyQt6.QtCore import QObject, pyqtSignal # NEW: Import QObject and pyqtSignal
# ... (rest of imports)

# ... (other code)

class ModelDownloader(QObject): # Inherit from QObject
    download_progress_signal = pyqtSignal(str, float, str) # model_id, progress, status_text

    def __init__(self, log, status, ask_yes_no_sync):
        super().__init__() # Call QObject's constructor
        self.log = log
        self.status = status
        self.ask_yes_no_sync = ask_yes_no_sync

    def _progress_callback(self, model_id, progress, text):
        self.download_progress_signal.emit(model_id, progress, text)
        self.status("[↓]", text, "INFO") # Also update general status


    def ensure_model(self, model_id: str) -> bool:
        if model_id not in PREDEFINED_MODELS:
            self.log(f"未知的模型 ID: {model_id}", "ERROR")
            return False

        model_config = PREDEFINED_MODELS[model_id]
        model_dir = Path(TTS_MODELS_DIR) / model_id
        required_files = [model_dir / fname for fname in model_config["file_names"]]
        
        if all(f.exists() for f in required_files):
            self.log(f"模型 '{model_id}' 已存在。", "INFO")
            return True

        # MODIFICATION: Log which files are missing
        missing_files = [str(f) for f in required_files if not f.exists()]
        if missing_files:
            self.log(f"模型 '{model_id}' 缺少以下檔案：{', '.join(missing_files)}", "WARNING")
        
        self.status("[!]", f"TTS 模型 '{model_id}' 不完整或不存在。", "WARN")
        do_download = self.ask_yes_no_sync("模型下載", f"Sherpa-ONNX 引擎需要下載 TTS 模型 '{model_id}'。\n\n是否要自動下載模型 (約 80-150MB)？")

        if not do_download:
            self.log("使用者取消下載模型。", "WARN")
            return False

        try:
            ensure_dir(model_dir)
            download_url = model_config["download_url"]
            file_ext = "".join(Path(download_url).suffixes)
            
            with tempfile.TemporaryDirectory(prefix="model_dl_") as temp_download_dir:
                archive_path = Path(temp_download_dir) / f"{model_id}{file_ext}"

                self.status("[↓]", f"準備從網路下載模型 '{model_id}'…", "INFO")
                download_with_with_progress_cb = lambda p, t: self._progress_callback(model_id, p * 0.8, t) # Scale for download phase
                download_with_progress(
                    download_url, str(archive_path),
                    progress_cb=download_with_with_progress_cb
                )
                
                self.status("[unpacking]", "模型下載完成，準備解壓…", "INFO")
                extract_with_progress_cb = lambda p, t: self._progress_callback(model_id, 0.8 + p * 0.2, t) # Scale for extraction phase
                
                if download_url.endswith(".tar.bz2"):
                    extract_tar_bz2(
                        str(archive_path), str(model_dir),
                        progress_cb=extract_with_progress_cb,
                        log_cb=self.log
                    )
                else:
                    self.log(f"不支援的壓縮格式: {download_url}", "ERROR")
                    self.download_progress_signal.emit(model_id, 0, "下載失敗") # Emit failure
                    return False

            if all(f.exists() for f in required_files):
                self.log(f"模型 '{model_id}' 已成功下載並解壓。", "INFO")
                self.download_progress_signal.emit(model_id, 1.0, "下載完成") # Emit completion
                return True
            else:
                self.log(f"解壓後模型檔案仍不完整，請手動檢查。", "ERROR")
                for f in required_files:
                    self.log(f"檢查檔案: {f}, 是否存在: {f.exists()}", "ERROR")
                self.download_progress_signal.emit(model_id, 0, "解壓失敗") # Emit failure
                return False
        except Exception as e:
            self.log(f"下載或解壓模型 '{model_id}' 失敗: {e}", "ERROR")
            self.download_progress_signal.emit(model_id, 0, "下載失敗") # Emit failure
            return False