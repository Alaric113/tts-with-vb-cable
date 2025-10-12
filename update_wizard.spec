# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

# 獲取專案根目錄
project_root = os.path.abspath(os.path.dirname(SPECPATH))

a = Analysis(
    ['update_wizard.py'],
    pathex=[project_root],
    binaries=[],
    datas=[],
    hiddenimports=[
        'customtkinter',
        'pkg_resources.py2_warn'
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
    name='update_wizard',
    debug=False,
    console=False, # 更新精靈也是一個無主控台的視窗應用
    icon=None # 您可以在此指定圖示路徑
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='update_wizard'
)