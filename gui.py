"""AudioForge 原生界面（PySide6）。转码逻辑在 audioforge.py，这里只管显示。"""
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
                               QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget, QProgressBar)

import audioforge as engine
import lang
from lang import T, set_lang

SEL_TINT = "rgba(91,140,255,26)"

AUDIO_FILTER = ("音频文件 (*.flac *.wav *.aiff *.aif *.alac *.m4a *.mp3 *.aac "
                "*.opus *.ogg *.oga *.wma *.ape *.wv *.m4b *.mp4);;"
                "所有文件 (*.*)")


def fmt_dur(sec: float) -> str:
    sec = int(max(0, sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_qss(t: Dict[str, str]) -> str:
    return f"""
/* 底色只给窗口和卡片，中间层透明：每层都有背景的话，Qt 重绘会从子控件
   一路传播到顶层，改一个进度条就是全窗重绘，扫描/转码时满屏闪。 */
QMainWindow, QWidget#root {{ background:{t['bg']}; }}
QWidget, QLabel, QCheckBox, QScrollArea, QProgressBar, QComboBox {{
  color:{t['fg']}; font-family:"Microsoft YaHei UI","Segoe UI",sans-serif;
  font-size:13px; background:transparent; border:none; }}

#title   {{ font-size:20px; font-weight:600; }}
#subtitle{{ font-size:12px; color:{t['fg3']}; }}
#statK   {{ font-size:10px; color:{t['fg3']}; letter-spacing:1px; }}
#statV   {{ font-size:19px; font-weight:600; }}
#statSave{{ font-size:19px; font-weight:600; color:{t['safe']}; }}
#statWarn{{ font-size:19px; font-weight:600; color:{t['caution']}; }}

QFrame#statTile {{ background:{t['panel2']}; border:1px solid {t['line']};
                   border-radius:9px; }}
QFrame#row      {{ background:transparent; border:none;
                   border-bottom:1px solid {t['line']}; }}
QFrame#row:hover {{ background:{t['panel2']}; }}
QFrame#rowSel   {{ background:rgba(91,140,255,26); }}
QFrame#foot     {{ background:{t['bg']}; border-top:1px solid {t['line2']}; }}
QFrame#drop     {{ background:{t['panel']}; border:2px dashed {t['line2']};
                   border-radius:14px; }}
QFrame#dropHot  {{ background:rgba(122,162,247,20); border:2px dashed {t['accent']};
                   border-radius:14px; }}
QFrame#bar      {{ background:{t['panel']}; border:1px solid {t['line']};
                   border-radius:10px; }}

#itemName {{ font-size:13px; font-weight:600; }}
#itemPath {{ font-size:10px; color:{t['fg3']}; font-family:Consolas,monospace; }}
#itemMeta {{ font-size:10px; color:{t['fg2']}; }}
#itemErr  {{ font-size:10px; color:{t['caution']}; }}
#itemSize {{ font-size:13px; font-weight:600; }}
#tag      {{ font-size:10px; color:{t['fg3']}; }}
#tagLoss  {{ font-size:10px; color:{t['safe']}; }}
#tagLossy {{ font-size:10px; color:{t['caution']}; }}
#stage    {{ font-size:12px; color:{t['fg2']}; }}
#footText {{ font-size:12px; color:{t['fg2']}; }}
#themeLbl {{ font-size:12px; color:{t['fg3']}; }}

QPushButton {{ background:{t['panel2']}; border:1px solid {t['line2']};
  border-radius:6px; padding:7px 15px; color:{t['fg']}; }}
QPushButton:hover   {{ background:{t['panel']}; border-color:{t['accent']}; }}
QPushButton:disabled{{ color:{t['fg3']}; border-color:{t['line']};
  background:{t['panel']}; }}
QPushButton#primary {{ background:{t['accent']}; border-color:{t['accent']};
  color:{t['onaccent']}; font-weight:600; padding:8px 20px; }}
QPushButton#primary:hover    {{ background:{t['accent2']}; border-color:{t['accent2']}; }}
QPushButton#primary:disabled {{ background:{t['panel2']}; border-color:{t['line']};
  color:{t['fg3']}; }}
QPushButton#small {{ padding:4px 11px; font-size:11px; }}
QPushButton#danger {{ color:{t['caution']}; }}

QComboBox {{ background:{t['panel2']}; border:1px solid {t['line2']};
  border-radius:6px; padding:5px 10px; color:{t['fg']}; min-width:88px; }}
QComboBox:hover {{ border-color:{t['accent']}; }}
QComboBox::drop-down {{ border:none; width:20px; }}
QComboBox QAbstractItemView {{ background:{t['panel2']}; border:1px solid {t['line2']};
  selection-background-color:{t['accent']}; color:{t['fg']}; }}

QCheckBox {{ spacing:8px; }}
QCheckBox::indicator {{ width:16px; height:16px; border:1px solid {t['line2']};
  border-radius:4px; background:{t['bg']}; }}
QCheckBox::indicator:hover {{ border-color:{t['accent']}; }}
QCheckBox::indicator:checked {{ background:{t['accent']};
  border-color:{t['accent']}; image:url("__CHECK__"); }}

QProgressBar {{ background:{t['panel']}; border:1px solid {t['line']};
  border-radius:4px; height:6px; text-align:center; }}
QProgressBar::chunk {{ background:{t['accent']}; border-radius:4px; }}

QScrollBar:vertical {{ background:transparent; width:11px; margin:2px; }}
QScrollBar::handle:vertical {{ background:{t['line2']}; border-radius:5px;
  min-height:36px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; }}
"""


class ElidedLabel(QLabel):
    """长路径用 ElideMiddle 挤掉中间，完整内容留 tooltip。

    路径前缀（用户配置时敲的）不如尾部（输出在哪）重要，所以挤中间。
    QLabel 没有内置这个行为，只能自己画。
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = text
        self.setToolTip(text)

    def setFull(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self.setText(text)      # 触发重算省略

    def fullText(self) -> str:
        return self._full

    def paintEvent(self, e) -> None:
        w = self.width()
        if self.fontMetrics().horizontalAdvance(self._full) <= w:
            super().paintEvent(e)
            return
        # 借用一个临时 painter 画省略后的串
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        elided = self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideMiddle, w)
        p.drawText(self.rect(), int(self.alignment()), elided)
        p.end()


def _lbl(text: str, obj: str = "") -> QLabel:
    w = QLabel(text)
    if obj:
        w.setObjectName(obj)
    return w


def _make_check_png(color: str) -> str:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPainter, QPen, QPixmap
    d = Path(os.environ.get("TEMP", ".")) / f"af_check_{color.lstrip('#')}.png"
    pm = QPixmap(16, 16)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 2.2, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPolyline([QPointF(3.5, 8.4), QPointF(6.6, 11.6), QPointF(12.5, 4.8)])
    p.end()
    pm.save(str(d), "PNG")
    return d.as_posix()


_check_png_cache: Dict[str, str] = {}


STATE_STYLE = {
    "pending": ("tag", "待处理"),
    "working": ("tag", "正在转码"),
    "done": ("tagLoss", "已完成"),
    "failed": ("itemErr", "失败"),
    "skipped": ("tag", "已跳过"),
}


class TrackRow(QFrame):
    toggled = Signal(str, bool)

    def __init__(self, tr: engine.Track, selectable: bool, parent=None):
        super().__init__(parent)
        self.path = tr.path
        self.tr = tr
        self.setObjectName("row")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(11)
        self.cb = QCheckBox()
        self.cb.setEnabled(selectable)
        self.cb.setChecked(tr.state == "pending")
        self.cb.toggled.connect(lambda v: self.toggled.emit(self.path, v))
        h.addWidget(self.cb, 0, Qt.AlignmentFlag.AlignTop)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(2)
        title = tr.title or Path(tr.path).stem
        body.addWidget(_lbl(title, "itemName"))
        body.addWidget(_lbl(str(tr.path), "itemPath"))
        bits = []
        if tr.ok:
            bits.append(f"{tr.codec}")
            if tr.sample_rate:
                bits.append(f"{tr.sample_rate} Hz")
            if tr.channels:
                bits.append(f"{'mono' if tr.channels == 1 else 'stereo' if tr.channels == 2 else str(tr.channels) + ' ch'}")
            if tr.bitrate:
                bits.append(f"{tr.bitrate // 1000} kbps")
            bits.append(fmt_dur(tr.duration))
            body.addWidget(_lbl(" · ".join(bits), "itemMeta"))
        else:
            body.addWidget(_lbl(tr.why, "itemErr"))
        wrap = QWidget()
        wrap.setLayout(body)
        h.addWidget(wrap, 1)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(3)
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        # done 状态显示的是产物大小（转换后可能变大或变小），pending 显示源大小
        shown = tr.out_size if tr.state == "done" and tr.out_path else tr.size
        self.size_lbl = _lbl(engine.human(shown), "itemSize")
        right.addWidget(self.size_lbl)
        obj, txt = STATE_STYLE.get(tr.state, ("tag", tr.state))
        self.state_lbl = _lbl(T(txt), obj)
        right.addWidget(self.state_lbl)
        if tr.ok:
            right.addWidget(_lbl(T("无损") if tr.lossless else T("有损"),
                                 "tagLoss" if tr.lossless else "tagLossy"))
        h.addLayout(right)

    def set_checked(self, on: bool) -> None:
        self.cb.blockSignals(True)
        self.cb.setChecked(on)
        self.cb.blockSignals(False)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window,
                     QColor(SEL_TINT) if on else QColor(0, 0, 0, 0))
        self.setPalette(pal)

    def refresh(self) -> None:
        tr = self.tr
        if tr.state == "done" and tr.out_path:
            self.size_lbl.setText(engine.human(tr.out_size))
        obj, txt = STATE_STYLE.get(tr.state, ("tag", tr.state))
        self.state_lbl.setObjectName(obj)
        self.state_lbl.setText(T(txt))
        # 换 objectName 后必须重新应用样式
        self.state_lbl.style().unpolish(self.state_lbl)
        self.state_lbl.style().polish(self.state_lbl)


class ProbeThread(QThread):
    one = Signal(object)
    all_done = Signal()

    def __init__(self, paths: List[str], parent=None):
        super().__init__(parent)
        self.paths = paths

    def run(self) -> None:
        for p in self.paths:
            self.one.emit(engine.probe(p))
        self.all_done.emit()


class ConvertThread(QThread):
    item = Signal(object)
    progress = Signal(float, str)
    all_done = Signal()

    def __init__(self, tracks: List[engine.Track], out_dir: Path,
                 target: engine.Target, bitrate: str, parent=None):
        super().__init__(parent)
        self.tracks = tracks
        self.out_dir = out_dir
        self.target = target
        self.bitrate = bitrate
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        done = 0
        total = max(1, len(self.tracks))
        for tr in self.tracks:
            if self._cancel:
                tr.state, tr.err = "skipped", T("已取消")
                self.item.emit(tr)
                continue
            self.item.emit(tr)
            engine.convert(tr, self.out_dir, self.target, self.bitrate,
                           on_line=lambda pct, path: self.progress.emit(pct, path))
            self.item.emit(tr)
            done += 1
            self.progress.emit(0.0, tr.path)
        self.all_done.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{engine.APP_NAME} {engine.__version__} · {T('本地转码')}")
        self.resize(1120, 820)
        self.setMinimumSize(860, 600)
        self.tracks: List[engine.Track] = []
        self.rows: List[TrackRow] = []
        self.pick: set = set()
        self.probe_thread: Optional[ProbeThread] = None
        self.conv_thread: Optional[ConvertThread] = None
        self.theme = engine.DEFAULT_THEME
        self._remember = True
        self._acceptDrag = False

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- 头部 ----
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(22, 16, 22, 12)
        hl.setSpacing(16)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(_lbl(f"● {engine.APP_NAME}", "title"))
        sub = _lbl(T("本地音频转码 · 源文件永不改动，输出到单独目录"), "subtitle")
        # Ignored 尺寸策略：英文比中文长一截，按内容撑开会被右边的主题/语言
        # 下拉框压掉尾巴（"… · sou"）。让它可以被压缩。
        sub.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        titles.addWidget(sub)
        hl.addLayout(titles, 1)
        hl.addStretch(0)

        self.cb_theme = QComboBox()
        for k in engine.THEME_ORDER:
            self.cb_theme.addItem(engine.THEMES[k]["n"], k)
        if engine.DEFAULT_THEME in engine.THEME_ORDER:
            self.cb_theme.setCurrentIndex(engine.THEME_ORDER.index(engine.DEFAULT_THEME))
        self.cb_theme.setToolTip(T("配色主题"))
        self.cb_theme.currentIndexChanged.connect(self.apply_theme)
        hl.addWidget(_lbl(T("主题"), "themeLbl"))
        hl.addWidget(self.cb_theme)

        self.cb_lang = QComboBox()
        self.cb_lang.addItem("中文", "zh")
        self.cb_lang.addItem("English", "en")
        self.cb_lang.setCurrentIndex(0 if lang.LANG == "zh" else 1)
        self.cb_lang.setToolTip(T("语言"))
        self.cb_lang.currentIndexChanged.connect(self._switch_lang)
        hl.addWidget(_lbl(T("语言"), "themeLbl"))
        hl.addWidget(self.cb_lang)

        self.t_save = self._tile(hl, T("可省下"), "—", "statSave")
        self.t_dur = self._tile(hl, T("总时长"), "—", "statV")
        self.t_n = self._tile(hl, T("条音频"), "—", "statV")
        outer.addWidget(head)

        # ---- 拖拽区 ----
        self.drop = QFrame()
        self.drop.setObjectName("drop")
        self.drop.setAcceptDrops(True)
        dl = QVBoxLayout(self.drop)
        dl.setContentsMargins(20, 26, 20, 26)
        dl.setSpacing(4)
        d1 = _lbl(T("拖拽音频文件到这里，或点击选择"), "itemName")
        d1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d2 = _lbl(T("支持 FLAC / WAV / ALAC / MP3 / AAC / Opus / OGG 等"), "tag")
        d2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(d1)
        dl.addWidget(d2)
        self.drop.mousePressEvent = lambda e: self.pick_files()
        outer.addWidget(self.drop, 0)

        # ---- 设置条 ----
        bar = QFrame()
        bar.setObjectName("bar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 10, 14, 10)
        bl.setSpacing(10)
        bl.addWidget(_lbl(T("目标格式"), "themeLbl"))
        self.cb_target = QComboBox()
        for t in engine.targets():
            self.cb_target.addItem(f"{t.label} ({t.ext})" + ("  " + T("无损") if t.lossless else ""), t.key)
        bl.addWidget(self.cb_target)
        bl.addWidget(_lbl(T("码率"), "themeLbl"))
        self.cb_rate = QComboBox()
        for key, _b, zh in engine.BITS:
            self.cb_rate.addItem(T(zh), key)
        self.cb_rate.setCurrentIndex(1)
        bl.addWidget(self.cb_rate)
        bl.addWidget(_lbl(T("输出到"), "themeLbl"))
        # 路径可能很长（深层目录），直接显示会把整条 bar 撑爆。用 ElideMiddle
        # 挤掉中间，完整路径留 tooltip。
        self.lbl_out = ElidedLabel(self.out_dir_text())
        self.lbl_out.setObjectName("itemPath")
        self.lbl_out.setMinimumWidth(120)
        bl.addWidget(self.lbl_out, 1)
        b_pick = QPushButton(T("选择输出目录"))
        b_pick.setObjectName("small")
        b_pick.clicked.connect(self.pick_outdir)
        bl.addWidget(b_pick)
        outer.addWidget(bar)

        # ---- 列表 ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.holder = QWidget()
        self.holder.setObjectName("row")
        self.list_layout = QVBoxLayout(self.holder)
        self.list_layout.setContentsMargins(22, 12, 22, 10)
        self.list_layout.setSpacing(0)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.holder)
        outer.addWidget(self.scroll, 1)
        self.placeholder = _lbl(T("还没有文件"), "tag")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_layout.insertWidget(0, self.placeholder)

        # ---- 底栏 ----
        foot = QFrame()
        foot.setObjectName("foot")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(22, 10, 22, 10)
        fl.setSpacing(10)
        self.foot = _lbl("—", "footText")
        fl.addWidget(self.foot)
        self.ff_ver = _lbl(T("ffmpeg 已就绪") if engine.ffmpeg_path() else T("找不到 ffmpeg"),
                           "tagLoss" if engine.ffmpeg_path() else "itemErr")
        self.ff_ver.setToolTip(engine.ffmpeg_version())
        fl.addWidget(self.ff_ver)
        fl.addStretch(1)
        b_clear = QPushButton(T("全部清空"))
        b_clear.setObjectName("small")
        b_clear.clicked.connect(self.clear_all)
        fl.addWidget(b_clear)
        b_open = QPushButton(T("打开输出目录"))
        b_open.setObjectName("small")
        b_open.clicked.connect(self.open_outdir)
        fl.addWidget(b_open)
        self.btn_go = QPushButton(T("开始转换"))
        self.btn_go.setObjectName("primary")
        self.btn_go.setEnabled(False)
        self.btn_go.clicked.connect(self.start_convert)
        fl.addWidget(self.btn_go)
        self.btn_cancel = QPushButton(T("取消"))
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self.do_cancel)
        fl.addWidget(self.btn_cancel)
        self.stage = _lbl("", "stage")
        fl.addWidget(self.stage)
        outer.addWidget(foot)

        self.setAcceptDrops(True)
        self.set_updates(False)

    def _tile(self, parent_layout, k, v, obj) -> QLabel:
        f = QFrame()
        f.setObjectName("statTile")
        f.setMinimumWidth(118)
        l = QVBoxLayout(f)
        l.setContentsMargins(14, 9, 14, 9)
        l.setSpacing(1)
        l.addWidget(_lbl(k, "statK"))
        val = _lbl(v, obj)
        l.addWidget(val)
        parent_layout.addWidget(f)
        return val

    def set_updates(self, on: bool) -> None:
        self.setUpdatesEnabled(on)

    # ---------------- 输出目录 ----------------
    def out_dir(self) -> Path:
        cfg = str(engine.CFG.get("out_dir") or "").strip()
        if cfg:
            return Path(cfg)
        if self.tracks:
            first = Path(self.tracks[0].path).parent
            return first / "converted"
        return Path.home() / "Music" / "converted"

    def out_dir_text(self) -> str:
        return str(self.out_dir())

    def pick_outdir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, T("选择输出目录"), str(self.out_dir()))
        if d:
            engine.set_config_value("out_dir", f'"{d}"')
            self.lbl_out.setFull(d)

    def open_outdir(self) -> None:
        d = self.out_dir()
        d.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(d))    # noqa: S606
            else:
                subprocess.Popen(["xdg-open", str(d)])
        except OSError as e:
            QMessageBox.warning(self, engine.APP_NAME, str(e))

    # ---------------- 导入 ----------------
    def pick_files(self) -> None:
        fs, _ = QFileDialog.getOpenFileNames(self, T("拖拽音频文件到这里，或点击选择"),
                                             str(Path.home()), AUDIO_FILTER)
        if fs:
            self.add_paths(fs)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.drop.setObjectName("dropHot")
            self.drop.style().unpolish(self.drop)
            self.drop.style().polish(self.drop)

    def dragLeaveEvent(self, e) -> None:
        self.drop.setObjectName("drop")
        self.drop.style().unpolish(self.drop)
        self.drop.style().polish(self.drop)

    def dropEvent(self, e) -> None:
        self.drop.setObjectName("drop")
        self.drop.style().unpolish(self.drop)
        self.drop.style().polish(self.drop)
        paths = []
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if not p:
                continue
            if Path(p).is_dir():
                paths += [str(x) for x in Path(p).iterdir()
                          if x.suffix.lower() in AUDIO_EXTS]
            else:
                paths.append(p)
        if paths:
            e.acceptProposedAction()
            self.add_paths(paths)

    def add_paths(self, paths: List[str]) -> None:
        if self.probe_thread and self.probe_thread.isRunning():
            return
        # 同一批里也要去重：用户一次拖 20 个文件可能带重名，
        # 而 self.tracks 要等探测结果回来才更新，跨批去重只挡得住已入库的。
        known = {t.path for t in self.tracks}
        new, seen = [], set()
        for p in paths:
            if p in known or p in seen:
                continue
            seen.add(p)
            new.append(p)
        if not new:
            return
        self.stage.setText(T("探测中…"))
        th = ProbeThread(new)
        th.one.connect(self._on_probe)
        th.all_done.connect(self._on_probe_done)
        self.probe_thread = th
        th.start()

    def _on_probe(self, tr: engine.Track) -> None:
        self.tracks.append(tr)

    def _on_probe_done(self) -> None:
        self.set_updates(True)
        self._render()
        self.stage.setText("")
        self.btn_go.setEnabled(any(t.ok for t in self.tracks))

    def clear_all(self) -> None:
        self.tracks.clear()
        self.rows.clear()
        self.pick.clear()
        self._render()
        self.btn_go.setEnabled(False)

    # ---------------- 渲染 ----------------
    def _render(self) -> None:
        # 先把旧行摘干净。之前 _on_conv_done 里手动 self.rows = [] 之后再调
        # _render()，结果 removeWidget 一个都没摘，列表里出现了两份。
        for r in self.rows:
            self.list_layout.removeWidget(r)
            r.deleteLater()
        self.rows = []
        self.placeholder.setVisible(not self.tracks)
        for tr in self.tracks:
            row = TrackRow(tr, tr.ok)
            row.toggled.connect(self._on_toggle)
            row.set_checked(tr.state == "pending" and tr.ok)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)
            self.rows.append(row)
        self.recalc()

    def recalc(self) -> None:
        sel = [t for t in self.tracks if t.path in self.pick and t.ok]
        s = engine.summary(sel)
        self.foot.setText(
            T(f"已选择 {len(sel)} 项 · 合计 {engine.human(s['in_bytes'])} · 总时长 {fmt_dur(s['duration'])}")
            if sel else "—")
        self.t_n.setText(str(len(self.tracks)))
        self.t_dur.setText(fmt_dur(sum(t.duration for t in self.tracks if t.ok)))
        done = [t for t in self.tracks if t.state == "done"]
        if done:
            d = sum(t.size for t in done) - sum(t.out_size for t in done)
            if d >= 0:
                self.t_save.setText(engine.human(d))
            else:
                # 变大了（如 FLAC->WAV）。tile 的标签是"可省下"，所以这里给 0
                # 并在 stage 里说明，不谎报成正数。
                self.t_save.setText("0 B")
                self.t_save.setToolTip(T("转换后变大"))
        else:
            self.t_save.setText("—")
            self.t_save.setToolTip("")
        self.btn_go.setEnabled(bool(sel) and not self._busy())

    def _busy(self) -> bool:
        return bool((self.conv_thread and self.conv_thread.isRunning())
                    or (self.probe_thread and self.probe_thread.isRunning()))

    def _on_toggle(self, path: str, on: bool) -> None:
        if on:
            self.pick.add(path)
        else:
            self.pick.discard(path)
        for r in self.rows:
            if r.path == path:
                r.set_checked(on)
        self.recalc()

    # ---------------- 转换 ----------------
    def start_convert(self) -> None:
        if self._busy():
            return
        tgt = engine.target_by_key(self.cb_target.currentData())
        if not tgt:
            return
        sel = [t for t in self.tracks if t.path in self.pick and t.ok]
        if not sel:
            return
        # 无损 -> 无损没有意义，跳过并说明，不白跑一遍
        run = []
        for t in sel:
            if t.lossless and tgt.lossless:
                t.state, t.err = "skipped", T("跳过无损转无损")
                self._mark(t)
            else:
                t.state = "pending"
                run.append(t)
        if not run:
            self.stage.setText(T("跳过无损转无损"))
            return
        out = self.out_dir()
        self.set_updates(False)
        self.btn_go.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)
        self.stage.setText(T("转换中…"))
        th = ConvertThread(run, out, tgt, self.cb_rate.currentData())
        th.item.connect(self._on_conv_item)
        th.progress.connect(self._on_progress)
        th.all_done.connect(self._on_conv_done)
        self.conv_thread = th
        th.start()

    def _mark(self, tr: engine.Track) -> None:
        for r in self.rows:
            if r.path == tr.path:
                r.refresh()

    def _on_conv_item(self, tr: engine.Track) -> None:
        self._mark(tr)

    def _on_progress(self, pct: float, path: str) -> None:
        pass      # 转换期不重绘，见 _on_conv_done

    def _on_conv_done(self) -> None:
        self.set_updates(True)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        # 转完回读产物元数据：转成 MP3 之后还显示 pcm_s16le / lossless 是错的，
        # 那是在说源文件，不是说产物。回读一次，行里显示的才是结果。
        for tr in self.tracks:
            if tr.state == "done" and tr.out_path:
                back = engine.probe(tr.out_path)
                if back.ok:
                    tr.codec = back.codec
                    tr.sample_rate = back.sample_rate
                    tr.channels = back.channels
                    tr.bitrate = back.bitrate
                    tr.duration = back.duration
                    tr.lossless = back.lossless
        # 不要在这里写 self.rows = []：_render() 靠 self.rows 摘旧行，
        # 提前清空会导致旧行摘不掉，列表里出现两份。
        self._render()
        ok = [t for t in self.tracks if t.state == "done"]
        bad = [t for t in self.tracks if t.state == "failed"]
        self.stage.setText(f"{T('转换完成')} · {len(ok)} ok"
                           + (f" · {len(bad)} {T('个文件失败')}" if bad else ""))
        self.recalc()
        if bad:
            detail = "\n".join(f"· {Path(t.path).name}: {t.err}" for t in bad[:10])
            QMessageBox.warning(self, engine.APP_NAME,
                                f"{len(bad)} {T('个文件失败')}\n\n{detail}")

    def do_cancel(self) -> None:
        if self.conv_thread and self.conv_thread.isRunning():
            self.conv_thread.cancel()
            self.btn_cancel.setEnabled(False)
            self.stage.setText(T("取消中…"))

    # ---------------- 主题 / 语言 ----------------
    def _switch_lang(self, idx: int) -> None:
        code = self.cb_lang.itemData(idx)
        if code == lang.LANG:
            return
        set_lang(code)
        engine.set_config_value("lang", f'"{code}"')
        if self._busy():
            return
        self.close()
        w = MainWindow()
        w.show()
        self._next = w

    def apply_theme(self, idx: int) -> None:
        key = self.cb_theme.itemData(idx)
        t = engine.THEMES.get(key)
        if not t:
            return
        qa = QApplication.instance()
        if qa is None:
            return
        check = _check_png_cache.get(t["onaccent"])
        if not check:
            check = _make_check_png(t["onaccent"])
            _check_png_cache[t["onaccent"]] = check
        qa.setStyleSheet(build_qss(t).replace("__CHECK__", check))
        self.theme = key
        global SEL_TINT
        SEL_TINT = t["sel"]
        for r in self.rows:
            r.set_checked(r.cb.isChecked())
        if self._remember:
            engine.set_config_value("theme", f'"{key}"')


AUDIO_EXTS = {".flac", ".wav", ".aiff", ".aif", ".alac", ".m4a", ".mp3", ".aac",
              ".opus", ".ogg", ".oga", ".wma", ".ape", ".wv", ".m4b", ".mp4"}


def main() -> int:
    def emit(msg: str) -> None:
        for name in ("stderr", "stdout"):
            try:
                getattr(sys, name).write(msg + "\n")
                getattr(sys, name).flush()
            except (OSError, ValueError, AttributeError):
                pass

    if "--version" in sys.argv or "-V" in sys.argv:
        emit(f"{engine.APP_NAME} {engine.__version__}")
        return 0
    if "--help" in sys.argv or "-h" in sys.argv:
        emit("AudioForge - 本地音频转码\n"
             "  AudioForge.exe            打开界面\n"
             "  AudioForge.exe --version  打印版本\n"
             "配置见 exe 同目录的 settings.yaml")
        return 0
    if "--probe" in sys.argv:
        # CLI 探测：AudioForge.exe --probe a.flac b.flac
        # 打印走 stderr：打包成 console=False 后 stdout 不可靠（见 emit 注释）
        for p in sys.argv[sys.argv.index("--probe") + 1:]:
            t = engine.probe(p)
            if t.ok:
                emit(f"{Path(p).name}\t{t.codec}\t{t.sample_rate}Hz\t{t.channels}ch\t"
                     f"{t.duration:.1f}s\t{engine.human(t.size)}\t"
                     f"{'lossless' if t.lossless else 'lossy'}")
            else:
                emit(f"{Path(p).name}\tFAIL\t{t.why}")
        return 0

    set_lang(str(engine.CFG.get("lang") or "zh"))
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    qa = QApplication(sys.argv)
    qa.setApplicationName(engine.APP_NAME)
    qa.setApplicationVersion(engine.__version__)
    qa.setStyle("Fusion")
    qa.setFont(QFont("Microsoft YaHei UI", 9))
    w = MainWindow()
    w._remember = False
    w.apply_theme(w.cb_theme.currentIndex())
    w._remember = True
    w.show()
    return qa.exec()


if __name__ == "__main__":
    sys.exit(main())
