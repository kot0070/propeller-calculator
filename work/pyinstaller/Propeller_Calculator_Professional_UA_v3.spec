# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['..\\..\\src\\main.py'],
    pathex=['src', 'work\\build_tools\\qt_v33'],
    binaries=[],
    datas=[('C:\\Users\\kot00\\Documents\\Codex\\2026-08-05\\propeller-calculator-professional-ua-v3-windows\\work\\build\\propellers.db', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Propeller_Calculator_Professional_UA_v3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:\\Users\\kot00\\Documents\\Codex\\2026-08-05\\propeller-calculator-professional-ua-v3-windows\\work\\build_assets\\version_info.txt',
    icon=['C:\\Users\\kot00\\Documents\\Codex\\2026-08-05\\propeller-calculator-professional-ua-v3-windows\\work\\build_assets\\propcalc.ico'],
    manifest='C:\\Users\\kot00\\Documents\\Codex\\2026-08-05\\propeller-calculator-professional-ua-v3-windows\\work\\build_assets\\propcalc.manifest',
)
