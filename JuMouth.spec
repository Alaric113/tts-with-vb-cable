# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules # Removed collect_binaries

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

# --- Locate .libs directories for numpy and scipy ---
# This path construction assumes a standard Python installation structure
# and is robust to virtual environments by using sys.prefix.
site_packages_path = os.path.join(sys.prefix, 'Lib', 'site-packages')

extra_binaries = []

# For numpy
numpy_libs_path = os.path.join(site_packages_path, 'numpy', '.libs')
if os.path.isdir(numpy_libs_path):
    # Add all files from numpy/.libs to the bundle under numpy/.libs
    # The format is (source_path, dest_path_in_bundle)
    extra_binaries.append((numpy_libs_path, 'numpy/.libs')) 
    print(f"DEBUG: Added numpy .libs from: {numpy_libs_path}")
else:
    print(f"DEBUG: numpy .libs not found at: {numpy_libs_path}")

# For scipy
scipy_libs_path = os.path.join(site_packages_path, 'scipy', '.libs')
if os.path.isdir(scipy_libs_path):
    # Add all files from scipy/.libs to the bundle under scipy/.libs
    extra_binaries.append((scipy_libs_path, 'scipy/.libs'))
    print(f"DEBUG: Added scipy .libs from: {scipy_libs_path}")
else:
    print(f"DEBUG: scipy .libs not found at: {scipy_libs_path}")


# --- 主要應用程式的分析 (JuMouth.exe) ---
a = Analysis(
    [MAIN_SCRIPT],
    pathex=[base_path, src_path],
    binaries=extra_binaries, # Use the dynamically collected binaries
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
        # --- NEW: More specific hidden imports based on traceback ---
        'scipy.linalg.blas',
        'numpy.core._multiarray_umath',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['src/runtime_hook.py'],
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
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 設定為 True 以顯示主控台視窗進行除錯
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
    upx=False,
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
# 1. 建立主應用程式的集合 (will be created in dist/JuMouth)
coll_main = COLLECT(
    main_exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

# 2. 建立更新精靈的獨立集合 (will be created in dist/update_wizard)
coll_wizard = COLLECT(
    wizard_exe,
    b.binaries,
    b.zipfiles,
    b.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='update_wizard'
)