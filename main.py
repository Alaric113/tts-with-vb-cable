# -*- coding: utf-8 -*-
# main.py — 進入點

import sys
from tkinter import messagebox
import ctypes

from app import LocalTTSPlayer
from utils_deps import IS_WINDOWS

# Windows 可選依賴提示
try:
    import comtypes  # noqa: F401
    comtypes_installed = True
except Exception:
    comtypes_installed = False

try:
    import win32gui  # noqa: F401
    pywin32_installed = True
except Exception:
    pywin32_installed = False

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

    try:
        app = LocalTTSPlayer()
        app.run()
    except Exception as e:
        messagebox.showerror("嚴重錯誤", f"應用程式遇到無法處理的錯誤並即將關閉。\n\n錯誤訊息：\n{e}")
        sys.exit(1)
