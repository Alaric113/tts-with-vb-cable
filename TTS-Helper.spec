# -*- mode: python ; coding: utf-8 -*-

# 這是 PyInstaller 的設定檔，用於專業地打包你的應用程式。

import customtkinter
import os

a = Analysis(
    ['voice.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 包含 customtkinter 的必要資源檔
        (os.path.join(os.path.dirname(customtkinter.__file__), "assets"), "customtkinter/assets"),
        # 告訴 PyInstaller 將 vbcable 資料夾完整地複製到打包目錄中
        ('vbcable', 'vbcable'),
        # 捆綁 ffmpeg，讓使用者開箱即用
        ('ffmpeg', 'ffmpeg')
    ],
    hiddenimports=[
        # 有時 PyInstaller 無法自動偵測到這些隱藏的依賴，手動加入更保險
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'pyttsx3.drivers',
        'pyttsx3.drivers.sapi5',
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
    a.binaries,
    a.datas,
    [],
    name='TTS-Helper',
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
