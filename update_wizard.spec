# -*- mode: python ; coding: utf-8 -*-

import os
def get_tcl_tk_filters():
    """定義要從 Tcl/Tk 資料中排除的檔案/資料夾。"""
    # 我們只保留英文、繁體中文、簡體中文的語言包，以及基礎的編碼檔案。
    # 其他所有語言包和時區資料都可以被安全地移除。
    return [
        'tzdata',          # 排除所有時區資料
        'msgs/af.msg',
        'msgs/af_za.msg',
        'msgs/ar.msg',
        'msgs/ar_in.msg',
        'msgs/ar_jo.msg',
        'msgs/ar_lb.msg',
        'msgs/ar_sy.msg',
        'msgs/be.msg',
        'msgs/bg.msg',
        'msgs/bn.msg',
        'msgs/bn_in.msg',
        'msgs/ca.msg',
        'msgs/cs.msg',
        'msgs/da.msg',
        'msgs/de.msg',
        'msgs/de_at.msg',
        'msgs/de_be.msg',
        'msgs/el.msg',
        'msgs/en_au.msg',
        'msgs/en_bw.msg',
        'msgs/en_ca.msg',
        'msgs/en_gb.msg',
        'msgs/en_hk.msg',
        'msgs/en_ie.msg',
        'msgs/en_in.msg',
        'msgs/en_nz.msg',
        'msgs/en_ph.msg',
        'msgs/en_sg.msg',
        'msgs/en_za.msg',
        'msgs/en_zw.msg',
        'msgs/eo.msg',
        'msgs/es.msg',
        'msgs/es_ar.msg',
        'msgs/es_bo.msg',
        'msgs/es_cl.msg',
        'msgs/es_co.msg',
        'msgs/es_cr.msg',
        'msgs/es_do.msg',
        'msgs/es_ec.msg',
        'msgs/es_gt.msg',
        'msgs/es_hn.msg',
        'msgs/es_mx.msg',
        'msgs/es_ni.msg',
        'msgs/es_pa.msg',
        'msgs/es_pe.msg',
        'msgs/es_pr.msg',
        'msgs/es_py.msg',
        'msgs/es_sv.msg',
        'msgs/es_uy.msg',
        'msgs/es_ve.msg',
        'msgs/et.msg',
        'msgs/eu.msg',
        'msgs/eu_es.msg',
        'msgs/fa.msg',
        'msgs/fa_in.msg',
        'msgs/fa_ir.msg',
        'msgs/fi.msg',
        'msgs/fo.msg',
        'msgs/fo_fo.msg',
        'msgs/fr.msg',
        'msgs/fr_be.msg',
        'msgs/fr_ca.msg',
        'msgs/fr_ch.msg',
        'msgs/ga.msg',
        'msgs/ga_ie.msg',
        'msgs/gl.msg',
        'msgs/gl_es.msg',
        'msgs/gv.msg',
        'msgs/gv_gb.msg',
        'msgs/he.msg',
        'msgs/hi.msg',
        'msgs/hi_in.msg',
        'msgs/hr.msg',
        'msgs/hu.msg',
        'msgs/id.msg',
        'msgs/id_id.msg',
        'msgs/is.msg',
        'msgs/it.msg',
        'msgs/it_ch.msg',
        'msgs/ja.msg',
        'msgs/kl.msg',
        'msgs/kl_gl.msg',
        'msgs/ko.msg',
        'msgs/ko_kr.msg',
        'msgs/kok.msg',
        'msgs/kok_in.msg',
        'msgs/kw.msg',
        'msgs/kw_gb.msg',
        'msgs/lt.msg',
        'msgs/lv.msg',
        'msgs/mk.msg',
        'msgs/mr.msg',
        'msgs/mr_in.msg',
        'msgs/ms.msg',
        'msgs/ms_my.msg',
        'msgs/mt.msg',
        'msgs/nb.msg',
        'msgs/nl.msg',
        'msgs/nl_be.msg',
        'msgs/nn.msg',
        'msgs/pl.msg',
        'msgs/pt.msg',
        'msgs/pt_br.msg',
        'msgs/ro.msg',
        'msgs/ru.msg',
        'msgs/ru_ua.msg',
        'msgs/sh.msg',
        'msgs/sk.msg',
        'msgs/sl.msg',
        'msgs/sq.msg',
        'msgs/sr.msg',
        'msgs/sv.msg',
        'msgs/sw.msg',
        'msgs/ta.msg',
        'msgs/ta_in.msg',
        'msgs/te.msg',
        'msgs/te_in.msg',
        'msgs/th.msg',
        'msgs/tr.msg',
        'msgs/uk.msg',
        'msgs/vi.msg',
    ]

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

# --- 核心修改：過濾 a.datas 中的 Tcl/Tk 檔案 ---
tcl_filters = get_tcl_tk_filters()
a.datas = [
    (dest, src, typ) for (dest, src, typ) in a.datas
    if not any(
        (
            'tcl' in dest and any(f in dest.replace('\\', '/') for f in tcl_filters)
        ),
        (
            'tk' in dest and any(f in dest.replace('\\', '/') for f in tcl_filters)
        )
    )
]
# -----------------------------------------
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [], exclude_binaries=True,
    name='update_wizard',
    debug=False,
    console=False, # 更新精靈也是一個無主控台的視窗應用
    icon='icon.ico' # 您可以在此指定圖示路徑
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