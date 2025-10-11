# -*- coding: utf-8 -*-
# 檔案: main.py (修正後)
# ... (註解不變) ...

import sys
from tkinter import messagebox
import ctypes

from app import LocalTTSPlayer
from utils_deps import IS_WINDOWS

# Windows 可選依賴提示
try:
    import comtypes
    comtypes_installed = True
except Exception:
    comtypes_installed = False
try:
    import win32gui
    import win32event
    import win32api
    from winerror import ERROR_ALREADY_EXISTS
    pywin32_installed = True
except Exception:
    pywin32_installed = False

class SingleInstance:
    """
    使用 Mutex (互斥鎖) 確保應用程式只有單一實例運行。
    """
    def __init__(self, name):
        self.mutex = None
        self.mutex_name = f"Global\\{name}"
        if pywin32_installed:
            try:
                self.mutex = win32event.CreateMutex(None, 1, self.mutex_name)
                self.last_error = win32api.GetLastError()
            except Exception as e:
                print(f"SingleInstance check failed: {e}")
                self.last_error = 0

    def is_already_running(self):
        return pywin32_installed and (self.last_error == ERROR_ALREADY_EXISTS)

    def __del__(self):
        if self.mutex:
            win32api.CloseHandle(self.mutex)

if __name__ == "__main__":
    if not sys.platform.startswith("win"):
        messagebox.showwarning("警告", "此應用程式主要為 Windows 設計，在您目前的作業系統上，部分功能（如 VB-CABLE 安裝）將無法使用。")
    else:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    if IS_WINDOWS and not comtypes_installed:
        messagebox.showwarning("警告", "缺少 'comtypes' 模組，語音引擎 'pyttsx3' 可能無法正常運作。")
    if IS_WINDOWS and not pywin32_installed:
        messagebox.showwarning("警告", "缺少 'pywin32' 模組，快捷鍵輸入框的焦點控制可能不穩定。")

    # --- 單例模式檢查 ---
    # 使用一個唯一的名稱來建立系統級的 Mutex
    instance_checker = SingleInstance("橘Mouth_TTS_Helper_App_Mutex_u123")
    if instance_checker.is_already_running():
        messagebox.showinfo("提示", "應用程式已經在運行了。")
        # 嘗試找到已存在的視窗並將其帶到前景
        try:
            hwnd = win32gui.FindWindow(None, "JuMouth - TTS 語音助手")
            if hwnd:
                win32gui.SetForegroundWindow(hwnd)
        except Exception as e:
            print(f"Failed to bring window to front: {e}")
        sys.exit(0)

    try:
        app = LocalTTSPlayer()
        app.run()
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        messagebox.showerror("嚴重錯誤", f"應用程式遇到無法處理的錯誤並即將關閉。\n\n錯誤詳情：\n{error_details}")
        # 將詳細錯誤寫入日誌檔，方便偵錯
        with open("error.log", "a", encoding="utf-8") as f:
            f.write(f"--- {__import__('datetime').datetime.now()} ---\n{error_details}\n")
        sys.exit(1)