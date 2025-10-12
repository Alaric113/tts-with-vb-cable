# -*- coding: utf-8 -*-
# 檔案: updater_manager.py
# 功用: 負責處理應用程式的自動更新檢查與執行。

import os
import sys
import threading
import webbrowser
import requests
from packaging.version import parse as parse_version

from utils_deps import APP_VERSION, GITHUB_REPO, IS_WINDOWS

# 可選 Windows 依賴
try:
    import comtypes.client
    import pythoncom
    comtypes_installed = True
except ImportError:
    comtypes_installed = False

class UpdateManager:
    def __init__(self, app_controller):
        """
        初始化更新管理器。
        :param app_controller: 主應用程式 LocalTTSPlayer 的實例，用於回呼 UI 操作。
        """
        self.app = app_controller

    def check_for_updates(self, silent=False):
        """啟動一個背景執行緒來檢查更新。"""
        self.app.log_message("開始檢查更新...")
        threading.Thread(target=self._update_check_thread, args=(silent,), daemon=True).start()

    def _update_check_thread(self, silent=False):
        """在背景執行緒中執行的更新檢查邏輯。"""
        if IS_WINDOWS and comtypes_installed:
            pythoncom.CoInitializeEx(0)

        if "YOUR_USERNAME" in GITHUB_REPO:
            self.app.log_message("GitHub 倉庫路徑未設定，無法檢查更新。", "WARN")
            if not silent:
                self.app.root.after(0, lambda: self.app.show_messagebox("提示", "開發者尚未設定更新檢查路徑。", "warning"))
            return

        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            latest_release = response.json()
            latest_version_str = latest_release["tag_name"].lstrip('v')
            
            if parse_version(latest_version_str) > parse_version(APP_VERSION):
                self.app.log_message(f"發現新版本: {latest_version_str} (當前版本: {APP_VERSION})", "INFO")
                download_url = latest_release["html_url"]
                assets = latest_release.get('assets', [])
                
                exe_asset = next((a for a in assets if a['name'].endswith('.exe')), None)
                zip_asset = next((a for a in assets if a['name'].endswith('.zip')), None)

                def ask_and_act():
                    # 變更邏輯：優先檢查 .zip 進行原地熱更新
                    if zip_asset and getattr(sys, 'frozen', False):
                        if self.app.show_messagebox("發現新版本", f"檢測到新版本 {latest_version_str}！\n(您目前使用的是 {APP_VERSION})\n\n是否要立即下載並自動安裝更新？\n(此過程將會覆蓋當前程式檔案)", "yesno"):
                            self._start_update_process(zip_asset['browser_download_url'])
                    # 如果沒有 .zip 或不在打包模式，再檢查 .exe 安裝包
                    elif exe_asset:
                        if self.app.show_messagebox("發現新版本", f"檢測到新版本 {latest_version_str}！\n(您目前使用的是 {APP_VERSION})\n\n建議您下載新的安裝程式來進行更新。\n是否要前往下載頁面？", "yesno"):
                            webbrowser.open_new_tab(download_url)
                    else:
                        if not silent and self.app.show_messagebox("發現新版本", f"檢測到新版本 {latest_version_str}！\n(您目前使用的是 {APP_VERSION})\n\n未找到合適的自動更新檔，是否要前往下載頁面？", "yesno"):
                            webbrowser.open_new_tab(download_url)
                
                self.app.root.after(0, ask_and_act)

            else:
                self.app.log_message(f"目前已是最新版本 ({APP_VERSION})。", "INFO")
                if not silent:
                    self.app.root.after(0, lambda: self.app.show_messagebox("提示", f"您目前使用的 {APP_VERSION} 已是最新版本。", "info"))
        except requests.exceptions.RequestException as e:
            self.app.log_message(f"檢查更新失敗: {e}", "ERROR")
            if not silent:
                self.app.root.after(0, lambda: self.app.show_messagebox("錯誤", f"無法連線至 GitHub 檢查更新。\n請檢查您的網路連線。\n\n錯誤: {e}", "warning"))

    def _start_update_process(self, download_url):
        """啟動背景執行緒來下載並安裝更新。"""
        self.app.log_message("更新程序已啟動...")
        self.app.set_ui_updating_state(True)
        threading.Thread(target=self._update_download_thread, args=(download_url,), daemon=True).start()

    def _update_download_thread(self, url):
        """在背景執行緒中下載新版本並觸發更新腳本。"""
        if IS_WINDOWS and comtypes_installed:
            pythoncom.CoInitializeEx(0)

        try:
            import subprocess
            
            exe_path = sys.executable
            app_dir = os.path.dirname(exe_path)
            update_zip_path = os.path.join(app_dir, "update.zip")
            updater_bat_path = os.path.join(app_dir, "updater.bat")

            self.app.log_message(f"開始下載更新檔案從: {url}")
            self.app.root.after(0, lambda: self.app._toggle_download_ui(True))

            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded_size = 0
                with open(update_zip_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        progress = downloaded_size / total_size if total_size > 0 else 0
                        self.app.root.after(0, lambda p=progress, d=downloaded_size, t=total_size: self.app._update_download_ui(p, f"下載中... {d/1024/1024:.2f}MB / {t/1024/1024:.2f}MB"))

            self.app.log_message("下載完成，準備執行更新...")
            self.app.root.after(0, lambda: self.app._update_download_ui(1.0, "下載完成！應用程式即將重新啟動..."))

            updater_script = f"""
@echo off
chcp 65001 > NUL
echo [橘Mouth 更新程式] 正在等待主程式關閉...
set EXE_NAME={os.path.basename(exe_path)}
:wait_loop
tasklist /FI "IMAGENAME eq %EXE_NAME%" | find /I "%EXE_NAME%" > NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak > NUL
    goto wait_loop
)
echo [橘Mouth 更新程式] 正在解壓縮並覆蓋檔案...
powershell -command "Expand-Archive -Path '{update_zip_path}' -DestinationPath '{app_dir}' -Force"
echo [橘Mouth 更新程式] 清理暫存檔案...
del "{update_zip_path}"
echo [橘Mouth 更新程式] 正在重新啟動...
start "" "{exe_path}"
(goto) 2>NUL & del "%~f0"
"""
            with open(updater_bat_path, "w", encoding="utf-8-sig") as f:
                f.write(updater_script)

            # 使用 shell=True 來執行 cmd.exe 的內建 start 命令，這是最可靠的方式
            # 將命令組合成一個字串，並確保路徑被正確引用
            command_str = f'start "JuMouth Updater" "{updater_bat_path}"'
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_CONSOLE
            
            subprocess.Popen(command_str, shell=True, creationflags=flags)

            self.app.root.after(1000, self.app.on_closing)

        except Exception as e:
            error_msg = f"啟動更新程序時發生錯誤: {e!r}"
            self.app.log_message(error_msg, "ERROR")
            self.app.root.after(0, lambda: self.app.show_messagebox("更新失敗", f"下載或安裝更新時發生錯誤:\n{e}", "error"))
            self.app.root.after(0, lambda: self.app._toggle_download_ui(False))
            self.app.root.after(0, lambda: self.app.set_ui_updating_state(False))