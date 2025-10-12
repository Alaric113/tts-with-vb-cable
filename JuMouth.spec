# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # 將已經打包好的 update_wizard 資料夾作為資料包含進來
    datas=[
        ('icon.ico', '.'),
        ('dist/update_wizard', '_internal/update_wizard')
    ],
    hiddenimports=['requests', 'packaging'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, name='JuMouth', debug=False, strip=False, upx=True, console=False, icon='icon.ico')
coll = COLLECT(exe,
               a.binaries,
               a.datas,
               strip=False,
               upx=True,
               name='JuMouth')
