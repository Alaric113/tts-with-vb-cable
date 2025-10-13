# -*- coding: utf-8 -*-
# 檔案: runtime_hook.py
# 功用: PyInstaller 執行階段掛鉤，用於在應用程式啟動時全域修補 subprocess 模組。

import sys
import os
import subprocess

# 只在 Windows 平台上執行此掛鉤
if sys.platform.startswith("win"):
    # 儲存原始的 Popen 類別
    _original_popen = subprocess.Popen

    # 定義一個新的 Popen 類別，它會自動加入隱藏視窗的參數
    class PatchedPopen(_original_popen):
        def __init__(self, *args, **kwargs):
            # 建立 startupinfo 物件以隱藏視窗
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)

    # 使用我們的新類別替換掉系統的 Popen
    subprocess.Popen = PatchedPopen