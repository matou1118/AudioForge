"""閲嶆媿 docs/ 涓嬬殑鐣岄潰鎴浘銆?
绂诲睆娓叉煋鐪熺獥鍙ｏ紝杞崲鐪熻窇 鈥斺€?鎴浘閲岀殑浣撶Н鍜屾潯鏁伴兘鏄湡鏁版嵁銆?涓嶈鐢?QT_QPA_PLATFORM=offscreen锛氱灞忓钩鍙版嬁涓嶅埌绯荤粺瀛椾綋锛屾瘡涓瓧绗︿細鐢绘垚
璞嗚厫鍧楋紝鎴浘鐪嬬潃"甯冨眬瀵?鍏跺疄鏄簾鍥俱€傝鐪熺獥鍙ｆ墠鏈夊瓧銆?
    python docs/shoot.py         # 涓枃
    python docs/shoot.py en      # 鑻辨枃
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# 娉ㄦ剰锛氭晠鎰忎笉璁?offscreen 鈥斺€?瑙佹ā鍧?docstring銆?
import audioforge as engine      # noqa: E402
import lang                      # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication    # noqa: E402
import gui                                   # noqa: E402


def pump(seconds: float = 0.4) -> None:
    QCoreApplication.processEvents()
    time.sleep(seconds)
    QCoreApplication.processEvents()


def wait_until_done(w, limit: float = 300.0) -> None:
    t0 = time.monotonic()
    while (w.probe_thread and w.probe_thread.isRunning()) or \
          (w.conv_thread and w.conv_thread.isRunning()):
        QCoreApplication.processEvents()
        time.sleep(0.02)
        if time.monotonic() - t0 > limit:
            raise TimeoutError("thread did not finish")
    pump(0.3)


def shot(w, name: str) -> None:
    pump()
    out = ROOT / "docs" / f"{name}.png"
    w.grab().save(str(out))
    print(f"  {out.relative_to(ROOT)}  {out.stat().st_size // 1024} KB")


def make_samples(d: Path) -> list:
    """Make samples of differing size and length so the list looks real."""
    specs = [("01 Original Soundtrack", 6.0, 44100),
             ("02 Field Recording - Rain", 9.0, 48000),
             ("03 Piano Trio - Take 3", 12.0, 44100),
             ("04 Interview (mono)", 7.0, 44100),
             ("05 Podcast Episode 128", 15.0, 32000)]
    out = []
    for name, secs, rate in specs:
        p = d / f"{name}.wav"
        engine.make_tone_wav(p, seconds=secs, rate=rate)
        out.append(p)
    return out


def main() -> int:
    code = sys.argv[1] if len(sys.argv) > 1 else "zh"
    suffix = "" if code == "zh" else f".{code}"
    work = Path(tempfile.mkdtemp(prefix="af_shot_"))
    # 截图要改配置（语言、输出目录），但绝不能写进仓库里的 settings.yaml：
    # 上一版就是这么把 af_shot_xxxx 的临时路径提交上去的，还会作为模板打进
    # exe，新用户首次运行就拿到一个死路径。这里把配置重定向到临时目录。
    # ponytail: 改 engine 加 AUDIOFORGE_CONFIG 环境变量更彻底，但要重打包 +
    # 重新确认；截图脚本这个场景不值得，等有第二个调用方再说。
    engine._writable_config = lambda: work / "settings.yaml"
    (work / "settings.yaml").write_text(engine.DEFAULT_SETTINGS, encoding="utf-8")
    lang.set_lang(code)
    engine.set_config_value("lang", f'"{code}"')

    qa = QApplication(sys.argv[:1])
    qa.setStyle("Fusion")
    from PySide6.QtGui import QFont
    qa.setFont(QFont("Microsoft YaHei UI", 9))

    try:
        samples = make_samples(work)
        # 鍏堣浆鎴愭湁鎹燂紝璁╁垪琛ㄩ噷涓ょ閮芥湁
        pre = work / "pre"
        for p in samples:
            t = engine.probe(str(p))
            engine.convert(t, pre, engine.target_by_key("flac"), "medium")

        w = gui.MainWindow()
        w._remember = False
        w.apply_theme(w.cb_theme.currentIndex())
        w.resize(1120, 820)
        w.show()
        engine.set_config_value("out_dir", f'"{work / "out"}"')
        w.lbl_out.setFull(str(work / "out"))
        w.cb_target.setCurrentIndex([t.key for t in engine.targets()].index("mp3"))

        w.add_paths([str(p) for p in samples])
        wait_until_done(w)
        shot(w, f"01-main{suffix}")

        w.pick = {t.path for t in w.tracks if t.ok}
        w.recalc()
        w.start_convert()
        wait_until_done(w)
        shot(w, f"02-done{suffix}")

        # 涓婚鎷煎浘锛氬叚濂楀悇娓蹭竴涓彧鐣欏ご閮ㄧ殑绐勭獥
        strip = QApplication.instance()
        del strip
        tiles = []
        for key in engine.THEME_ORDER:
            tw = gui.MainWindow()
            tw._remember = False
            # apply_theme 鏀剁殑鏄笅鎷夋绱㈠紩锛屼笉鏄?key
            tw.apply_theme(engine.THEME_ORDER.index(key))
            tw.resize(1120, 210)
            tw.show()
            tw.add_paths([str(p) for p in samples[:2]])
            wait_until_done(tw)
            tiles.append(tw)
        for _ in range(3):
            pump(0.2)
        # 纵向拼起来。QPixmap.copy() 在 PySide6 里签名不一样，用 QPainter 更直白。
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPainter, QPixmap
        h = 210
        total = QPixmap(1120, h * len(tiles))
        total.fill(Qt.GlobalColor.black)
        painter = QPainter(total)
        y = 0
        for tw in tiles:
            pm = tw.grab()
            painter.drawPixmap(0, y, pm)
            y += pm.height()
        painter.end()
        out = ROOT / "docs" / f"03-themes{suffix}.png"
        total.save(str(out))
        print(f"  {out.relative_to(ROOT)}  {out.stat().st_size // 1024} KB")
        for tw in tiles:
            tw.close()
        w.close()
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)
        # 鎴浘鑴氭湰鑷繁鍒暀鍨冨溇
        import glob
        for d in glob.glob(os.path.join(tempfile.gettempdir(), "af_shot_*")):
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

