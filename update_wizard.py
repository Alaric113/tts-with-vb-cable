# -*- coding: utf-8 -*-
# 檔案: update_wizard.py
# 功用: 一個獨立的 GUI 更新精靈，由主程式啟動。

import sys
import os
import time
import threading
import zipfile
import shutil
import subprocess
from datetime import datetime
import requests

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QProgressBar, QTextEdit, QVBoxLayout, QGridLayout
from PyQt6.QtCore import pyqtSignal, QObject, Qt, QTimer
from PyQt6.QtGui import QFont, QPalette, QColor

class WizardSignals(QObject):
    """用於跨執行緒更新 UI 的信號"""
    log = pyqtSignal(str, str)
    status = pyqtSignal(str, str)
    progress = pyqtSignal(float)
    finished = pyqtSignal()

class UpdateWizard:
    def __init__(self, pid_to_wait, download_url, app_dir, exe_to_restart):
        self.pid = int(pid_to_wait)
        self.app_dir = app_dir
        self.download_url = download_url
        self.exe_path = exe_to_restart
        self.update_finished = False  # 新增一個旗標來追蹤更新是否完成

        self.signals = WizardSignals()
        self._setup_ui()
        self._connect_signals()

        QTimer.singleShot(100, self.start_update)

    def _setup_ui(self):
        self.win = QWidget()
        self.win.setWindowTitle("橘Mouth 更新精靈")
        self.win.setFixedSize(500, 380)
        self.win.setStyleSheet("""
            QWidget {{
                background-color: #F0F2F5;
                color: #212121;
                font-family: 'Segoe UI', 'Microsoft JhengHei UI', sans-serif;
            }}
            QFrame, QLabel {{
                background-color: transparent;
            }
            QProgressBar {{
                border: none;
                border-radius: 5px;
                text-align: center;
                background-color: #E9E9EB;
            }}
            QProgressBar::chunk {{
                background-color: #007AFF;
                border-radius: 4px;
            }}
            QTextEdit {{
                background-color: #FFFFFF;
                border: 1px solid #EAEAEA;
                border-radius: 5px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)

        layout = QVBoxLayout(self.win)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.title_label = QLabel("橘Mouth 更新中")
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

    def _log(self, message, level="INFO"):
        self.signals.log.emit(message, level)

    def _set_progress(self, value):
        self.signals.progress.emit(value)

    def _set_status(self, text, color=None):
        self.signals.status.emit(text, color or "")

    def _log_slot(self, message, level):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] [{level.upper():<5}] {message}"
        self.log_text.append(formatted_msg)

    def _set_status_slot(self, text, color):
        self.status_label.setText(text)
        if color:
            self.status_label.setStyleSheet(f"color: {color};")

    def _set_progress_slot(self, value):
        self.progress_bar.setValue(int(value * 1000))

    def start_update(self):
        threading.Thread(target=self._update_thread, daemon=True).start()

    def _update_thread(self):
        try:
            try:
                # 1. 下載更新檔
                status_text = f"開始下載更新: {os.path.basename(self.download_url)}"
                self._log(status_text)
                self._set_status(status_text)

                zip_path = os.path.join(self.app_dir, "update.zip")

                with requests.get(self.download_url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get('content-length', 0))
                    downloaded_size = 0
                    with open(zip_path, 'wb') as f:
                        # --- 核心修正: 增加 chunk_size 以大幅提升下載速度 ---
                        for chunk in r.iter_content(chunk_size=1024 * 512): # 512 KB
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            progress = downloaded_size / total_size if total_size > 0 else 0
                            self._set_progress(progress * 0.5) # 下載佔用前 50% 的進度
                            status_text = f"下載中... {downloaded_size/1024/1024:.2f}MB / {total_size/1024/1024:.2f}MB"
                            self._set_status(status_text)

                self._log("下載完成。")
                self._set_progress(0.5)

                # 2. 等待主程式關閉
                status_text = f"等待主程式 (PID: {self.pid}) 關閉..."
                self._log(status_text)
                self._set_status(status_text)

                def is_pid_running_windows(pid_to_check):
                    """使用 tasklist 命令檢查 PID 是否在運行，並隱藏其視窗。"""
                    try:
                        # --- 再次修正: 直接使用 CREATE_NO_WINDOW 旗標，這是最可靠的方式 ---
                        creationflags = 0
                        if os.name == 'nt':
                            creationflags = subprocess.CREATE_NO_WINDOW
                        result = subprocess.run(
                            ['tasklist', '/fi', f'pid eq {pid_to_check}', '/nh'], 
                            capture_output=True, text=True, check=True,
                            creationflags=creationflags
                        )
                        # 如果命令成功且輸出包含 PID，則表示程序仍在運行
                        return str(pid_to_check) in result.stdout
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        # 命令失敗 (找不到 PID) 或找不到 tasklist.exe，都視為程序已關閉
                        return False
                
                wait_progress = 0.0
                while is_pid_running_windows(self.pid):
                    time.sleep(0.5)
                    wait_progress = min(0.05, wait_progress + 0.005) # 等待佔用 5% 的進度
                    self._set_progress(0.5 + wait_progress)

                self._log("主程式已關閉。")
                time.sleep(1) # 額外等待，確保檔案鎖已釋放

                # 3. 解壓縮檔案
                status_text = f"正在解壓縮更新檔: {os.path.basename(zip_path)}"
                self._log(status_text)
                self._set_status(status_text)
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    # --- 新的、更簡單可靠的更新邏輯 ---
                    # 由於精靈本身在外部執行，我們可以更安全地操作 app_dir
                    
                    # 1. 建立一個臨時目錄來解壓縮
                    temp_extract_dir = os.path.join(self.app_dir, "update_temp")
                    if os.path.exists(temp_extract_dir):
                        shutil.rmtree(temp_extract_dir)
                    os.makedirs(temp_extract_dir)

                    self._log(f"正在解壓縮到臨時目錄...")
                    zf.extractall(temp_extract_dir)

                    # 2. 智慧判斷來源目錄
                    extracted_items = os.listdir(temp_extract_dir)
                    source_dir = temp_extract_dir
                    if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_extract_dir, extracted_items[0])):
                        source_dir = os.path.join(temp_extract_dir, extracted_items[0])
                        self._log(f"檢測到單一頂層資料夾: {extracted_items[0]}，準備更新。")

                    # 3. 覆蓋檔案 (使用 copytree，因為它能處理子目錄)
                    self._log(f"正在將新檔案複製到目標位置: {self.app_dir}")
                    # dirs_exist_ok=True (Python 3.8+) 允許覆蓋現有目錄
                    shutil.copytree(source_dir, self.app_dir, dirs_exist_ok=True)
                    
                    # 4. 清理臨時解壓縮目錄
                    self._log("正在清理臨時檔案...")
                    try:
                        shutil.rmtree(temp_extract_dir)
                    except Exception as cleanup_error:
                        self._log(f"清理臨時檔案失敗: {cleanup_error!r} (可忽略)", "WARN")

                self._log("解壓縮完成。")
                self._set_progress(0.95)

                # 4. 清理更新檔
                status_text = "正在清理暫存檔案..."
                self._log(status_text)
                self._set_status(status_text)
                try:
                    os.remove(zip_path)
                    self._log("清理完成。")
                except Exception as e:
                    self._log(f"清理失敗: {e} (可忽略)")
                
                self._set_progress(0.98)

                # 5. 重啟主程式
                status_text = "更新完成！正在重新啟動主程式..."
                self._log(status_text)
                self._set_status(status_text, color="green")
                self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
                self._set_progress(1.0)
                
                # --- 再次修正: 確保重啟時也絕不顯示視窗 ---
                subprocess.Popen(
                    [self.exe_path],
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                    close_fds=True)

                self._log("主程式已啟動，本視窗將自動關閉並進行自我清理。")
                time.sleep(2)
                self.signals.finished.emit()

            except Exception as e:
                # 錯誤處理：嘗試還原備份
                backup_dir = os.path.join(self.app_dir, "update_backup")
                if os.path.exists(backup_dir):
                    self._log("更新失敗，正在嘗試從備份還原...", "WARN")
                    try:
                        shutil.copytree(backup_dir, self.app_dir, dirs_exist_ok=True)
                        self._log("已從備份還原。", "INFO")
                    except Exception as restore_error:
                        self._log(f"從備份還原失敗: {restore_error!r}", "ERROR")

                self._set_status("更新失敗！", color="red")
                self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: red; }")
                self._log(f"更新過程中發生嚴重錯誤: {e!r}")
                self._log("更新失敗！請手動重新啟動應用程式。")
                # 在這種情況下，我們不自動關閉，讓使用者看到錯誤訊息
        finally:
            # 無論成功或失敗，都將旗標設為 True，允許視窗關閉
            # 並嘗試自我清理
            try:
                wizard_temp_dir = os.path.dirname(sys.executable)
                if "jumouth_updater_" in os.path.basename(wizard_temp_dir):
                    self._log("準備自我清理...", "DEBUG")
                    # 建立一個 .bat 腳本來刪除自己所在的臨時資料夾。
                    # 使用 ping 提供可靠的延遲，並在最後自我刪除。
                    cleanup_script = f"""
@echo off
chcp 65001 > NUL
echo 正在等待更新精靈完全關閉...
REM 使用 timeout 作為更可靠的延遲，等待檔案鎖被釋放
timeout /t 2 /nobreak > NUL

echo 正在清理臨時更新檔案...
REM /s 刪除目錄樹，/q 安靜模式
rmdir /s /q "{wizard_temp_dir}"

echo 清理完成，正在刪除此腳本...
(goto) 2>nul & del "%~f0"
"""
                    # 使用時間戳確保批次檔名稱唯一
                    cleanup_bat_path = os.path.join(os.path.dirname(wizard_temp_dir), f"cleanup_{int(time.time())}.bat")
                    with open(cleanup_bat_path, "w", encoding="utf-8") as f: f.write(cleanup_script)
                    # 直接執行 bat，並使用 CREATE_NO_WINDOW 隱藏視窗
                    subprocess.Popen(f'"{cleanup_bat_path}"', shell=True, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
            except Exception as e:
                self._log(f"自我清理失敗: {e!r}", "WARN")
            self.update_finished = True

    def _on_finished(self):
        # 只有在更新完成後才允許關閉視窗
        if self.update_finished:
            self.win.close()
        else:
            self._log("更新正在進行中，請稍候...")
            QTimer.singleShot(3000, self.win.close) # 如果更新失敗，3秒後也關閉
def main():
    """
    入口函式。
    預期接收4個命令列參數:
    sys.argv[1]: 主程式 PID
    sys.argv[2]: update.zip 的下載 URL
    sys.argv[3]: 應用程式根目錄
    sys.argv[4]: 主程式 exe 的完整路徑
    """
    if len(sys.argv) != 5:
        print("錯誤: 更新精靈參數不足。")
        # 在沒有控制台的情況下，這個 print 看不到，但這是個好的防禦措施
        return

    pid, download_url, app_dir, exe_path = sys.argv[1:5]

    app = QApplication(sys.argv)
    # 高 DPI 支援
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    wizard = UpdateWizard(pid, download_url, app_dir, exe_path)
    sys.exit(app.exec())

if __name__ == "__main__":
    # 為了除錯，可以手動模擬參數
    # if len(sys.argv) == 1:
    #     sys.argv.extend(["12345", "https://example.com/update.zip", "C:/path/to/app", "C:/path/to/app/JuMouth.exe"])
    main()