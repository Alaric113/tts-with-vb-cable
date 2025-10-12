# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

# 獲取專案根目錄和 src 目錄的路徑
project_root = os.path.abspath(os.path.dirname(SPECPATH))
src_path = os.path.join(project_root, 'src')

a = Analysis(
    ['main.py'],
    # 告訴 PyInstaller 在專案根目錄和 src 目錄下尋找模組
    pathex=[project_root, src_path],
    binaries=[],
    # 將 ui 資料夾作為資料檔案一起打包
    # 'ui' 資料夾在專案根目錄，所以來源路徑是 'ui'
    datas=[('src/ui', 'ui'),
            ('src/app','app')    
        ],
    hiddenimports=[
        'customtkinter',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'pyttsx3.drivers.sapi5',
        'pkg_resources.py2_warn',
        'requests',
        'packaging',
        'sounddevice',
        '_sounddevice_data',
        'pydub'
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='JuMouth',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # 建立一個無主控台的視窗應用程式
    icon=None, # 您可以在此指定圖示路徑，例如 'assets/icon.ico'
    manifest_identity=None,
    manifest_version_file=None,
    uac_admin=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    uac_uiaccess=False
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='JuMouth'
)