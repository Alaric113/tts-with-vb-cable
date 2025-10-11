# -*- mode: python ; coding: utf-8 -*-

# 這是 PyInstaller 的設定檔，用於專業地打包你的應用程式。

import customtkinter
import os

# 取得 customtkinter 的資源路徑
customtkinter_path = os.path.dirname(customtkinter.__file__)
assets_path = os.path.join(customtkinter_path, "assets")

a = Analysis(
    ['main.py'],  # 程式進入點
    pathex=[],
    binaries=[],
    datas=[
        # 關鍵：包含 customtkinter 的必要資源檔 (主題、圖片等)
        (assets_path, "customtkinter/assets")
    ],
    hiddenimports=[
        # 關鍵：加入 PyInstaller 可能偵測不到的隱藏依賴
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'pyttsx3.drivers',
        'pyttsx3.drivers.sapi5',
        'packaging',
        'packaging.version',
        'packaging.specifiers',
        'packaging.requirements',
        'requests', # 自動更新功能需要
        'win32gui', # 自動更新與單例模式需要
        'win32con', # 自動更新與單例模式需要
        'win32api', # 自動更新與單例模式需要
        'win32process', # 自動更新功能需要
        'win32event', # 單例模式需要
        'winerror', # 單例模式需要
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='JuMouth',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # 關鍵：設定為 False，執行時才不會跳出黑色的命令提示字元視窗
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico'        # 關鍵：指定你的應用程式圖示
)
