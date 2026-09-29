# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。产物是单文件 GUI exe，console=False。

注意两件事，都是踩过坑的：

1) 不打包 ffmpeg。它是使用者自装的依赖，而且 LGPL/GPL 再分发有合规成本。
   界面会检测 ffmpeg 并明确告知用户怎么装。

2) hiddenimports 必须显式列出 PySide6.QtCore/QtGui/QtWidgets。之前这里写的是
   空列表，打出来的 exe 启动就是白窗口 —— Qt 的平台插件（qwindows.dll）没
   被带上，QApplication 建不出窗口。AudioForge 就是这么白屏的。
"""
import sys
from pathlib import Path

PROJ = Path(SPECPATH).resolve()

a = Analysis(
    ['gui.py'],
    pathex=[str(PROJ)],
    binaries=[],
    datas=[('settings.yaml', '.')],
    hiddenimports=[
        # 不显式写，PyInstaller 不会把 PySide6 的 Qt 绑定和平台插件收进去，
        # 结果是 exe 起来一个白窗口（qwindows.dll 缺失）。
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排掉用不到的大件，能省不少体积
    excludes=[
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtWebEngineCore',
        'PySide6.Qt3DCore', 'PySide6.QtMultimedia', 'PySide6.QtNetwork',
        'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtCharts',
        'PySide6.QtDataVisualization', 'PySide2', 'PyQt5', 'PyQt6',
        'tkinter', 'numpy', 'matplotlib', 'IPython', 'pytest', 'notebook',
    ],
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
    name='AudioForge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # GUI 程序：没有控制台，所以 --version / --help 走 stderr
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
