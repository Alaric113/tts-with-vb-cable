# -*- coding: utf-8 -*-
# 檔案: update_wizard.py
# 功用: 一個獨立的 GUI 更新精靈，由主程式啟動，執行基於 manifest 的部分更新。

import sys
import os
import time
import threading
import shutil
import subprocess
from datetime import datetime
import requests
import json
import hashlib
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QProgressBar, QTextEdit, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, QObject, Qt, QTimer
from PyQt6.QtGui import QFont

class WizardSignals(QObject):
    """用於跨執行緒更新 UI 的信號"""
    log = pyqtSignal(str, str)
    status = pyqtSignal(str, str)
    progress = pyqtSignal(float)
    finished = pyqtSignal(bool) # 新增: 傳遞成功或失敗

class UpdateWizard:
    def __init__(self, pid_to_wait, manifest_url, app_dir, exe_to_restart):
        self.pid = int(pid_to_wait)
        self.app_dir = Path(app_dir)
        self.manifest_url = manifest_url
        self.exe_path = exe_to_restart
        self.update_finished = False

        # 從 manifest URL 推斷出基礎 URL
        self.base_download_url = self.manifest_url.rsplit('/', 1)[0] + '/'

        self.signals = WizardSignals()
        self._setup_ui()
        self._connect_signals()

        QTimer.singleShot(100, self.start_update)

    def _setup_ui(self):
        self.win = QWidget()
        self.win.setWindowTitle("橘Mouth 更新精靈")
        self.win.setFixedSize(500, 380)
        self.win.setStyleSheet("""
            QWidget {
                background-color: #F0F2F5;
                color: #212121;
                font-family: 'Segoe UI', 'Microsoft JhengHei UI', sans-serif;
            }
            QLabel { background-color: transparent; }
            QProgressBar {
                border: none; border-radius: 5px; text-align: center;
                background-color: #E9E9EB;
            }
            QProgressBar::chunk { background-color: #007AFF; border-radius: 4px; }
            QTextEdit {
                background-color: #FFFFFF; border: 1px solid #EAEAEA;
                border-radius: 5px; font-family: 'Consolas', 'Courier New', monospace;
            }
        """)

        layout = QVBoxLayout(self.win)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.title_label = QLabel("橘Mouth 增量更新")
        self.title_label.setFont(QFont("Microsoft JhengHei UI", 16, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("準備開始更新...")
        self.status_label.setFont(QFont("Microsoft JhengHei UI", 10))

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_text)

        self.win.show()
        self.win.activateWindow()
        self.win.raise_()

    def _connect_signals(self):
        self.signals.log.connect(self._log_slot)
        self.signals.status.connect(self._set_status_slot)
        self.signals.progress.connect(self._set_progress_slot)
        self.signals.finished.connect(self._on_finished)

    # ... UI signal slot methods ...
    def _log(self, message, level="INFO"): self.signals.log.emit(message, level)
    def _set_progress(self, value): self.signals.progress.emit(value)
    def _set_status(self, text, color=None): self.signals.status.emit(text, color or "")
    def _log_slot(self, message, level):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] [{level.upper():<5}] {message}")
    def _set_status_slot(self, text, color):
        self.status_label.setText(text)
        if color: self.status_label.setStyleSheet(f"color: {color};")
    def _set_progress_slot(self, value): self.progress_bar.setValue(int(value * 1000))

    def start_update(self):
        threading.Thread(target=self._update_thread, daemon=True).start()

    def _calculate_sha256(self, file_path):
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256.update(byte_block)
            return sha256.hexdigest()
        except FileNotFoundError:
            return None
        except Exception as e:
            self._log(f"無法計算檔案雜湊值 {os.path.basename(file_path)}: {e}", "ERROR")
            return None

    def _update_thread(self):
        try:
            # 1. 下載 manifest
            self._set_status("正在下載更新清單...")
            self._log("下載 manifest.json...")
            manifest_resp = requests.get(self.manifest_url, timeout=10)
            manifest_resp.raise_for_status()
            remote_manifest = manifest_resp.json()
            remote_files = remote_manifest["files"]
            self._log(f"成功取得版本 {remote_manifest['version']} 的檔案清單。")
            self._set_progress(0.05)

            # 2. 掃描本地檔案並比較
            self._set_status("正在校驗本地檔案...")
            files_to_download = []
            local_files_map = {}
            
            # 建立本地所有檔案的 map
            for root, _, files in os.walk(self.app_dir):
                for name in files:
                    local_path = Path(root) / name
                    relative_path = local_path.relative_to(self.app_dir).as_posix()
                    local_files_map[relative_path] = local_path

            # 比較遠端和本地
            for relative_path, remote_hash in remote_files.items():
                local_path = self.app_dir / relative_path.replace('/', os.sep)
                if local_path.exists():
                    local_hash = self._calculate_sha256(local_path)
                    if local_hash != remote_hash:
                        files_to_download.append(relative_path)
                        self._log(f"變更: {relative_path}", "DEBUG")
                else:
                    files_to_download.append(relative_path)
                    self._log(f"新增: {relative_path}", "DEBUG")
            
            self._log(f"共需下載 {len(files_to_download)} 個已變更/新增的檔案。")
            self._set_progress(0.15)
            
            # 找出需要刪除的檔案
            remote_file_set = set(remote_files.keys())
            local_file_set = set(local_files_map.keys())
            files_to_delete = local_file_set - remote_file_set
            
            # 過濾掉更新器本身和日誌檔
            files_to_delete = {
                f for f in files_to_delete 
                if 'update_wizard' not in f and not f.endswith(('.log', '.bak', '.bat'))
            }
            self._log(f"共需刪除 {len(files_to_delete)} 個過時的檔案。")

            # 3. 等待主程式關閉
            self._wait_for_pid()

            # 4. 下載檔案
            if files_to_download:
                total_files = len(files_to_download)
                for i, relative_path in enumerate(files_to_download):
                    self._set_status(f"下載檔案 ({i+1}/{total_files}): {os.path.basename(relative_path)}")
                    self._download_file(relative_path)
                    self._set_progress(0.15 + (i + 1) / total_files * 0.7) # 下載佔 70% 進度
            else:
                 self._set_progress(0.85)

            # 5. 刪除過時檔案
            if files_to_delete:
                self._set_status("正在刪除過時檔案...")
                for relative_path in files_to_delete:
                    try:
                        local_path_to_delete = local_files_map[relative_path]
                        self._log(f"刪除: {relative_path}", "DEBUG")
                        os.remove(local_path_to_delete)
                    except Exception as e:
                        self._log(f"無法刪除檔案 {relative_path}: {e}", "WARN")
            self._set_progress(0.95)

            # 6. 重啟
            self._set_status("更新完成！正在重新啟動...", color="green")
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
            self._set_progress(1.0)
            self._log("重啟主程式...")
            subprocess.Popen([self.exe_path], creationflags=subprocess.DETACHED_PROCESS, close_fds=True)

            time.sleep(2)
            self.signals.finished.emit(True) # True 表示成功

        except Exception as e:
            self._log(f"更新過程中發生嚴重錯誤: {e}", "ERROR")
            self._set_status("更新失敗！", color="red")
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: red; }")
            import traceback
            self._log(traceback.format_exc(), "ERROR")
            self.signals.finished.emit(False) # False 表示失敗

    def _download_file(self, relative_path):
        download_url = self.base_download_url + relative_path
        target_path = self.app_dir / relative_path.replace('/', os.sep)
        
        # 確保目標目錄存在
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._log(f"下載 {os.path.basename(relative_path)}...", "DEBUG")
        try:
            with requests.get(download_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(target_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        except Exception as e:
            self._log(f"下載檔案 {relative_path} 失敗: {e}", "ERROR")
            raise # 重新拋出錯誤，讓主循環捕獲

    def _wait_for_pid(self):
        self._set_status(f"等待主程式 (PID: {self.pid}) 關閉...")
        while True:
            try:
                # os.kill(pid, 0) 在 Windows 上會直接終止程序，不可用
                # 使用 tasklist
                result = subprocess.run(
                    ['tasklist', '/fi', f'pid eq {self.pid}'],
                    capture_output=True, text=True, check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if str(self.pid) not in result.stdout:
                    break # 程序已不存在
            except (subprocess.CalledProcessError, FileNotFoundError):
                # 命令失敗或找不到 tasklist，都視為程序已關閉
                break
            time.sleep(0.5)
        self._log("主程式已關閉。")
        time.sleep(1) # 額外等待檔案鎖釋放

    def _on_finished(self, success):
        if success:
            self._log("更新成功，本視窗將在3秒後關閉。")
            QTimer.singleShot(3000, self.win.close)
        else:
            self._log("更新失敗，請檢查日誌。本視窗不會自動關閉。")
        self.update_finished = True

def main():
    if len(sys.argv) != 5:
        return

    pid, manifest_url, app_dir, exe_path = sys.argv[1:5]

    app = QApplication(sys.argv)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    wizard = UpdateWizard(pid, manifest_url, app_dir, exe_path)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
