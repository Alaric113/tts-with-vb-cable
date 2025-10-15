# -*- mode: python ; coding: utf-8 -*-

import sys
import os
import sys
from PyInstaller.utils.hooks import collect_data_files

# --- 專案設定 ---
APP_NAME = "JuMouth"
MAIN_SCRIPT = "main.py"
UPDATE_WIZARD_SCRIPT = "update_wizard.py"
ICON_FILE = "icon.ico"

block_cipher = None
# --- 取得專案根目錄 ---
base_path = os.path.dirname(os.path.abspath(SPECPATH))
src_path = os.path.join(base_path, 'src')

# --- 核心修正: 將 src 目錄加入 Python 搜尋路徑 ---
sys.path.append(src_path)

# --- 輕量化方案: 定義要從 PyQt6 中排除的模組和資料 ---
pyqt_excludes = [
    'Qt6.QtDesigner',
    'Qt6.QtHelp',
    'Qt6.QtLocation',
    'Qt6.QtMultimedia',
    'Qt6.QtMultimediaWidgets',
    'Qt6.QtNetwork',
    'Qt6.QtNfc',
    'Qt6.QtPositioning',
    'Qt6.QtQml',
    'Qt6.QtQuick',
    'Qt6.QtSql',
    'Qt6.QtSvg',
    'Qt6.QtTest',
    'Qt6.QtWebChannel',
    'Qt6.QtWebSockets',
    'Qt6.QtXml',
]

# --- 主要應用程式的分析 (JuMouth.exe) ---
a = Analysis(
    [MAIN_SCRIPT],
    pathex=[base_path, src_path],
    binaries=[],
    datas=[
        # 包含圖示檔案
        (ICON_FILE, '.'),
        # 包含 PyQt6 平台外掛 (非常重要!)
        # --- 輕量化方案: 排除不必要的 PyQt6 資料檔案 ---
        *collect_data_files('PyQt6',
            include_py_files=True,
            excludes=['**/translations/qt_*', '**/translations/qtbase_*', '**/designer/**']
        ),
    ],
    hiddenimports=[
        'PyQt6.sip',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'sounddevice',
        'comtypes',
        'win32gui',
        'win32event',
        'win32api',
        'win32process',
        'packaging',
        'packaging.version',
        'packaging.specifiers',
        'packaging.requirements',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[], # 確保沒有使用 runtime_hook
    excludes=pyqt_excludes, # --- 輕量化方案: 排除不必要的 PyQt6 模組 ---
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# --- 為主要應用程式建立 PYZ ---
pyz_a = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# --- 更新精靈的分析 (update_wizard.exe) ---
b = Analysis(
    [UPDATE_WIZARD_SCRIPT],
    pathex=[base_path],
    binaries=[],
    datas=[
        # 更新精靈也需要 PyQt6 的外掛
        *collect_data_files('PyQt6', include_py_files=True),
    ],
    hiddenimports=[
        'PyQt6.sip',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=pyqt_excludes, # --- 輕量化方案: 更新精靈也排除這些模組 ---
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# --- 為更新精靈建立 PYZ ---
pyz_b = PYZ(b.pure, b.zipped_data, cipher=block_cipher)

# --- 主要應用程式的執行檔設定 ---
main_exe = EXE(
    pyz_a,
    a.scripts,
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 設定為 False 以隱藏主控台視窗
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_FILE,
)

# --- 更新精靈的執行檔設定 ---
wizard_exe = EXE(
    pyz_b,
    b.scripts,
    exclude_binaries=True,
    name='update_wizard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # 更新精靈也是 GUI，隱藏主控台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# --- 最終打包結構 ---
# 將 update_wizard.exe 及其依賴打包到一個名為 'update_wizard' 的資料夾中
wizard_coll = COLLECT(
    wizard_exe,
    b.binaries,
    b.zipfiles,
    b.datas,
    name='update_wizard'
)

# --- 最終修正: 重新組織最終的 COLLECT 結構 ---
# 1. 建立主應用程式的集合
main_coll = COLLECT(
    main_exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

# 2. 將更新精靈集合作為資料加入到主集合中，並指定正確的路徑
main_coll.toc.append(('_internal/update_wizard', wizard_coll, 'COLLECT'))

coll = main_coll