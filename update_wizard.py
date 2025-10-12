# -*- coding: utf-8 -*-
# 檔案: update_wizard.py
# 功用: 一個獨立的 GUI 更新精靈，由主程式啟動。

import customtkinter as ctk
import tkinter as tk
import sys
import os
import time
import threading
import zipfile
import shutil
import subprocess
from datetime import datetime
import requests

class UpdateWizard:
    def __init__(self, root, pid_to_wait, download_url, app_dir, exe_to_restart):
        self.root = root
        self.pid = int(pid_to_wait)
        self.app_dir = app_dir
        self.download_url = download_url
        self.exe_path = exe_to_restart
        self.update_finished = False  # 新增一個旗標來追蹤更新是否完成

        self.root.title("橘Mouth 更新精靈")
        self.root.geometry("500x380")
        self.root.resizable(False, False)

        # --- 新的 UI 佈局 ---
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(3, weight=1)

        self.title_label = ctk.CTkLabel(self.root, text="橘Mouth 更新中", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.status_label = ctk.CTkLabel(self.root, text="準備開始更新...", font=ctk.CTkFont(size=14))
        self.status_label.grid(row=1, column=0, padx=20, pady=(0, 5), sticky="w")
        
        self.progress_bar = ctk.CTkProgressBar(self.root)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.log_text = ctk.CTkTextbox(self.root, font=("Consolas", 11), state="disabled")
        self.log_text.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        # 將視窗置於最前
        self.root.after(50, self.root.lift)
        self.root.after(100, self.start_update)

    def _log(self, message, level="INFO"):
        def upd():
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_msg = f"[{timestamp}] [{level.upper():<5}] {message}\n"
            self.log_text.configure(state="normal")
            self.log_text.insert(tk.END, formatted_msg)
            self.log_text.see(tk.END)
            self.log_text.configure(state="disabled")
        self.root.after(0, upd)

    def _set_progress(self, value):
        self.root.after(0, lambda: self.progress_bar.set(value))

    def _set_status(self, text, color=None):
        def upd():
            self.status_label.configure(text=text)
            if color: self.status_label.configure(text_color=color)
        self.root.after(0, upd)

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
                        for chunk in r.iter_content(chunk_size=8192):
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
                    """使用 tasklist 命令檢查 PID 是否在運行，這比 os.kill 更可靠。"""
                    try:
                        # /nh (no header), /fi (filter)
                        # CREATE_NO_WINDOW 確保不會彈出命令提示字元視窗
                        result = subprocess.run(
                            ['tasklist', '/fi', f'pid eq {pid_to_check}', '/nh'],
                            capture_output=True, text=True, check=True,
                            creationflags=subprocess.CREATE_NO_WINDOW
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
                self.progress_bar.configure(progress_color="green")
                self._set_progress(1.0)
                
                # 使用 DETACHED_PROCESS 確保更新精靈關閉後，主程式能繼續運行
                subprocess.Popen([self.exe_path], creationflags=subprocess.DETACHED_PROCESS, close_fds=True)

                self._log("主程式已啟動，本視窗將自動關閉並進行自我清理。")
                time.sleep(2)
                self.root.after(0, self.root.destroy)

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
                self.progress_bar.configure(progress_color="red")
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
                    # 建立一個 .bat 腳本來刪除自己所在的臨時資料夾
                    cleanup_script = f"""
@echo off
timeout /t 1 /nobreak > NUL
rmdir /s /q "{wizard_temp_dir}"
"""
                    cleanup_bat_path = os.path.join(os.path.dirname(wizard_temp_dir), "cleanup.bat")
                    with open(cleanup_bat_path, "w", encoding="utf-8") as f: f.write(cleanup_script)
                    subprocess.Popen(f'cmd.exe /c start /b "" "{cleanup_bat_path}" > NUL 2>&1', shell=True, creationflags=subprocess.DETACHED_PROCESS)
            except Exception as e:
                self._log(f"自我清理失敗: {e!r}", "WARN")
            self.update_finished = True

    def _on_closing(self):
        # 只有在更新完成後才允許關閉視窗
        if self.update_finished:
            self.root.destroy()
        else:
            self._log("更新正在進行中，請稍候...")

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

    ctk.set_appearance_mode("System")
    root = ctk.CTk()
    app = UpdateWizard(root, pid, download_url, app_dir, exe_path)
    root.mainloop()

if __name__ == "__main__":
    # 為了除錯，可以手動模擬參數
    # if len(sys.argv) == 1:
    #     sys.argv.extend(["12345", "https://example.com/update.zip", "C:/path/to/app", "C:/path/to/app/JuMouth.exe"])
    main()