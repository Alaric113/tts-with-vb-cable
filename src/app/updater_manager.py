# -*- coding: utf-8 -*-
# 檔案: updater_manager.py
# 功用: 負責處理應用程式的自動更新檢查與執行。

import os
import sys
import threading
import webbrowser
import requests
from packaging.version import parse as parse_version
from PyQt6.QtCore import QTimer
from ..utils.deps import APP_VERSION, GITHUB_REPO, IS_WINDOWS

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
                self.app.show_messagebox("提示", "開發者尚未設定更新檢查路徑。", "warning")
            return

        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            latest_release = response.json()
            latest_version_str = latest_release["tag_name"].lstrip('v')
            
            if parse_version(latest_version_str) > parse_version(APP_VERSION):
                self.app.log_message(f"發現新版本: {latest_version_str} (當前版本: {APP_VERSION})", "INFO")
                assets = latest_release.get('assets', [])
                
                # --- 核心修正: 尋找 JuMouth_update.zip 的下載連結 ---
                zip_asset = next((a for a in assets if a['name'] == 'JuMouth_update.zip'), None)

                if zip_asset and 'browser_download_url' in zip_asset:
                    zip_download_url = zip_asset['browser_download_url']
                    
                    def on_user_choice(do_update):
                        if do_update:
                            self._launch_update_wizard(zip_download_url)

                    self.app.show_messagebox(
                        "發現新版本",
                        f"檢測到新版本 {latest_version_str}！ (您目前使用的是 {APP_VERSION})\n\n是否要立即自動下載並更新？\n\n(主程式將在下載完成後自動關閉並重啟)",
                        "yesno",
                        callback=on_user_choice
                    )
                else:
                    # 如果找不到 zip 檔，則退回手動更新
                    self.app.log_message("在新版本中未找到 'JuMouth_update.zip'，引導使用者手動更新。", "WARN")
                    self.app.show_messagebox("發現新版本", f"檢測到新版本 {latest_version_str}！\n\n但在發布中未找到自動更新包，請前往 GitHub 頁面手動下載。", "info")
                    webbrowser.open_new_tab(latest_release["html_url"])

            else:
                self.app.log_message(f"目前已是最新版本 ({APP_VERSION})。", "INFO")
                if not silent:
                    self.app.show_messagebox("提示", f"您目前使用的 {APP_VERSION} 已是最新版本。", "info")
        except requests.exceptions.RequestException as e:
            self.app.log_message(f"檢查更新失敗: {e}", "ERROR")
            if not silent:
                self.app.show_messagebox("錯誤", f"無法連線至 GitHub 檢查更新。\n請檢查您的網路連線。\n\n錯誤: {e}", "warning")

    def _launch_update_wizard(self, download_url):
        """啟動獨立的 GUI 更新精靈，並將所有後續工作交給它。"""
        try:
            import subprocess
            import tempfile
            import shutil

            exe_path = sys.executable
            app_dir = os.path.dirname(exe_path)

            # 啟動獨立的更新精靈 GUI 程式
            # 根據 .spec 檔案的設定，更新精靈位於 _internal/update_wizard/
            updater_source_dir = os.path.join(app_dir, "_internal", "update_wizard")
            if not os.path.isdir(updater_source_dir):
                self.app.log_message("錯誤: 找不到更新精靈 'update_wizard.exe'。", "ERROR")
                self.app.show_messagebox("錯誤", "找不到更新精靈 'update_wizard.exe'，無法執行更新。", "error")
                return

            # --- 核心變更：將更新精靈複製到臨時目錄後再執行 ---
            # 1. 建立一個臨時資料夾
            temp_dir = tempfile.mkdtemp(prefix="jumouth_updater_")
            self.app.log_message(f"建立臨時更新目錄: {temp_dir}", "DEBUG")

            # 2. 將整個更新精靈資料夾複製到臨時位置
            shutil.copytree(updater_source_dir, temp_dir, dirs_exist_ok=True)
            self.app.log_message("已將更新精靈複製到臨時目錄。", "DEBUG")

            # 3. 從臨時目錄啟動更新精靈
            self.app.log_message("正在從臨時目錄啟動更新精靈...", "INFO")
            temp_updater_exe_path = os.path.join(temp_dir, "update_wizard.exe")
            
            pid = os.getpid()
            command = [
                temp_updater_exe_path, # 使用臨時目錄中的精靈
                str(pid),
                download_url, # 將下載 URL 作為參數傳遞
                app_dir,
                exe_path
            ]

            # 使用 DETACHED_PROCESS 確保更新精靈與主程式完全脫鉤。
            # 將從主程式傳入的 startupinfo 物件傳遞給 Popen，以確保在需要時能隱藏視窗。
            subprocess.Popen(
                command,
                creationflags=subprocess.DETACHED_PROCESS, close_fds=True, startupinfo=self.app.startupinfo
            )
            
            QTimer.singleShot(1000, self.app.on_closing)

        except Exception as e:
            error_msg = f"啟動更新程序時發生錯誤: {e!r}"
            self.app.log_message(error_msg, "ERROR")
            self.app.show_messagebox("更新失敗", f"啟動更新精靈時發生錯誤:\n{e}", "error")