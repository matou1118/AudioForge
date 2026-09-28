# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。产物是单文件 GUI exe，console=False。

注意：不打包 ffmpeg。它是使用者自装的依赖，而且 LGPL/GPL 再分发有合规成本。
界面会检测 ffmpeg 并明确告知用户怎么装。
"""
import sys
from pathlib import Path

block_cipher = None
ROOT = Path(getattr(sys, "_MEIPASS", ".")).resolve()
PROJ = Path(SPECPATH).resolve()

a = Analysis(
    ["gui.py"],
    pathex=[str(PROJ)],
    binaries=[],
    datas=[("settings.yaml", ".")],
    hiddenimports=[],
    hookspath=[],
    # 这些是 Qt/科学计算栈里体积大但本项目用不到的东西，排掉能省不少
    excludes=[
        "numpy", "matplotlib", "scipy", "pandas", "PIL", "PyQt5", "PyQt6",
        "PySide2", "tkinter", "IPython", "pytest", "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AudioForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUI 程序：没有控制台，所以 --version 走 stderr
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
