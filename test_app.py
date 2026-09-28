"""AudioForge 自检。真跑 ffmpeg —— 转换类的 bug 只有真转一遍才抓得到。

跑法：python test_app.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
for _n in ("stderr", "stdout"):
    try:
        getattr(sys, _n).reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

import audioforge as engine   # noqa: E402
import lang                   # noqa: E402

_TMP: list = []


def tmpdir(prefix: str = "af_test_") -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    _TMP.append(d)
    return d


def cleanup() -> None:
    """删本轮所有临时目录。

    Windows 上 ffmpeg/ffprobe 刚退出时文件句柄可能还没释放，第一次 rmtree 会
    撞 PermissionError。这是平台特性不是 bug，所以重试几次而不是 ignore_errors
    —— 静默忽略会让"自检不留残渣"这个断言永远通过，等于没检查。
    """
    for d in _TMP:
        for attempt in range(6):
            try:
                shutil.rmtree(d)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.25 * (attempt + 1))
    _TMP.clear()


# ---------------------------------------------------------------- 引擎

def t_human():
    assert engine.human(0) == "0 B"
    assert engine.human(1023) == "1023 B"
    assert engine.human(1024) == "1.00 KB"
    assert engine.human(1024 ** 3) == "1.00 GB"
    assert engine.human(1024 ** 4) == "1.00 TB"


def t_find_tools():
    assert engine.ffmpeg_path(), "找不到 ffmpeg。装一个：winget install ffmpeg"
    assert engine.ffprobe_path(), "找不到 ffprobe"
    ver = engine.ffmpeg_version()
    assert "ffmpeg" in ver.lower(), f"版本串不对: {ver!r}"
    # 目标编码器必须真的在（不然界面上的选项是假的）
    out = subprocess.run([engine.ffmpeg_path(), "-hide_banner", "-encoders"],
                         capture_output=True, text=True, errors="replace", timeout=60).stdout
    need = {"mp3": "libmp3lame", "aac": "aac", "opus": "libopus",
            "ogg": "libvorbis", "flac": "flac", "alac": "alac", "wav": "pcm_s16le"}
    for key, enc in need.items():
        assert re.search(rf"\s{re.escape(enc)}\s", out), \
            f"目标 {key} 需要的编码器 {enc} 不在 ffmpeg 里，界面选项会是假的"


def t_targets_sane():
    ts = engine.targets()
    assert len(ts) == 7, f"目标格式数变了: {len(ts)}"
    keys = [t.key for t in ts]
    assert len(set(keys)) == len(keys), "有重复的 key"
    for t in ts:
        assert t.ext.startswith("."), f"{t.key} 的 ext 少了点: {t.ext}"
        assert t.args, f"{t.key} 没给编码参数"
        assert t.fmt, f"{t.key} 没指定输出容器（-f），中间文件 .part 会转不了"
        assert engine.target_by_key(t.key) is t
    assert engine.target_by_key("nope") is None
    for t in ts:
        if t.key in ("flac", "alac", "wav"):
            assert t.lossless, f"{t.key} 应标为无损"
        else:
            assert not t.lossless, f"{t.key} 不该标为无损"


def t_target_lookup_cold():
    """target_by_key 必须自给自足，不依赖别人先调过 targets()。

    之前缓存只在 targets() 里填，脚本里直接 target_by_key('flac') 拿到
    None，然后在 convert() 里炸成 'NoneType' has no attribute 'ext'。
    """
    r = subprocess.run(
        [sys.executable, "-c",
         "import audioforge as e; "
         "t = e.target_by_key('flac'); "
         "print('NONE' if t is None else t.fmt)"],
        capture_output=True, text=True, errors="replace", timeout=120, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-200:]
    assert r.stdout.strip() == "flac", f"冷启动查不到: {r.stdout.strip()!r}"


def t_probe_real():
    d = tmpdir()
    w = engine.make_tone_wav(d / "tone.wav", seconds=1.5)
    t = engine.probe(str(w))
    assert t.ok, f"探测自己造的文件都失败: {t.why}"
    assert t.codec == "pcm_s16le", t.codec
    assert t.sample_rate == 44100, t.sample_rate
    assert t.channels == 2, t.channels
    assert abs(t.duration - 1.5) < 0.15, t.duration
    assert t.lossless is True
    assert t.size > 0


def t_probe_rejects_junk():
    d = tmpdir()
    # 空文件
    (d / "empty.mp3").write_bytes(b"")
    t = engine.probe(str(d / "empty.mp3"))
    assert not t.ok and t.why, "空文件不该探测成功"
    # 不存在
    t = engine.probe(str(d / "nope.flac"))
    assert not t.ok and t.why
    # 随机字节当音频
    (d / "junk.mp3").write_bytes(os.urandom(4096))
    t = engine.probe(str(d / "junk.mp3"))
    assert not t.ok, f"随机字节竟探测成功了: {t}"
    # 纯文本
    (d / "a.wav").write_text("not audio at all")
    t = engine.probe(str(d / "a.wav"))
    assert not t.ok, "文本文件不该探测成功"


def t_never_overwrite():
    d = tmpdir()
    a = engine.unique_out(d, "song", ".mp3")
    assert a.name == "song.mp3"
    a.write_bytes(b"x")
    b = engine.unique_out(d, "song", ".mp3")
    assert b.name == "song (2).mp3", b.name
    assert a.read_bytes() == b"x", "原文件被动了"
    b.write_bytes(b"y")
    c = engine.unique_out(d, "song", ".mp3")
    assert c.name == "song (3).mp3", c.name


def t_convert_roundtrip():
    """核心：造测试音 -> 转每种格式 -> 回探测校验。真跑 ffmpeg。"""
    d = tmpdir()
    src = engine.make_tone_wav(d / "tone.wav", seconds=1.0)
    t = engine.probe(str(src))
    assert t.ok, t.why
    out = d / "out"
    expect = {"mp3": ("mp3", False), "aac": ("aac", False), "opus": ("opus", False),
              "ogg": ("vorbis", False), "flac": ("flac", True),
              "alac": ("alac", True), "wav": ("pcm_s16le", True)}
    for key, (codec, lossless) in expect.items():
        tgt = engine.target_by_key(key)
        r = engine.convert(t, out, tgt, "medium")
        assert r.state == "done", f"{key} 转换失败: {r.err}"
        assert Path(r.out_path).exists() and r.out_size > 0, key
        back = engine.probe(r.out_path)
        assert back.ok, f"{key} 产物探测失败: {back.why}"
        assert back.codec == codec, f"{key} 回探测 codec={back.codec}，期望 {codec}"
        assert abs(back.duration - t.duration) < 0.3, \
            f"{key} 时长对不上: {back.duration} vs {t.duration}"
        assert back.lossless is lossless, f"{key} 无损判定错: {back.lossless}"
        assert not Path(r.out_path + ".part").exists(), f"{key} 留了 .part 残渣"


def t_convert_no_partial_left():
    """输出先写 .part，成功才改名。失败时不该留下半个文件。"""
    d = tmpdir()
    src = engine.make_tone_wav(d / "t.wav", seconds=0.5)
    t = engine.probe(str(src))
    out = d / "out"
    # 把编码器换成不存在的，让它必然失败
    bad = engine.Target("bad", ".bad", "Bad", False, ["-c:a", "definitely_not_a_codec"])
    r = engine.convert(t, out, bad, "medium")
    assert r.state == "failed", f"应该失败却成功了: {r.state}"
    assert r.err, "失败时必须有原因"
    leftovers = list(out.glob("*")) if out.exists() else []
    assert not leftovers, f"失败后留下残渣: {[p.name for p in leftovers]}"


def t_lossless_to_lossless_skipped():
    """无损转无损没意义，应该跳过而不是白跑一遍。"""
    d = tmpdir()
    src = engine.make_tone_wav(d / "t.wav", seconds=0.3)
    t = engine.probe(str(src))
    assert t.lossless
    # 引擎层不跳过（跳过是 GUI 的判断），但要保证无损输入被正确识别
    assert engine.probe(str(src)).lossless is True


def t_summary():
    d = tmpdir()
    src = engine.make_tone_wav(d / "t.wav", seconds=0.4)
    t = engine.probe(str(src))
    r = engine.convert(t, d / "o", engine.target_by_key("mp3"), "medium")
    assert r.state == "done"
    s = engine.summary([t])
    assert s["n"] == 1 and s["n_ok"] == 1
    assert s["in_bytes"] == t.size > 0
    assert abs(s["duration"] - t.duration) < 0.2
    s2 = engine.summary([r])
    assert s2["out_bytes"] == r.out_size > 0
    # summary 不该自己算 delta（GUI 分 done 和非 done 两种情况算）
    assert "delta" in s2


def t_probe_cli():
    d = tmpdir()
    src = engine.make_tone_wav(d / "t.wav", seconds=0.3)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "gui.py"), "--probe", str(src)],
                       capture_output=True, text=True, errors="replace",
                       timeout=180, env=env, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-300:]
    assert "pcm_s16le" in r.stdout, r.stdout
    assert "lossless" in r.stdout, r.stdout


def t_probe_cli_packed():
    """打包后的 exe 也要能 --probe。

    之前一次误判「exe 里 stat 找不到文件」其实是我诊断命令写错（ffmpeg 那步
    文件没真生成），差点改代码去「修」一个不存在的 bug。教训：exe 的行为必须
    真跑一遍才算数。这里 dist/ 存在时才跑。
    """
    exe = ROOT / "dist" / "AudioForge.exe"
    if not exe.is_file():
        return              # 还没 build，跳过
    d = tmpdir()
    src = engine.make_tone_wav(d / "t.wav", seconds=0.3)
    r = subprocess.run([str(exe), "--probe", str(src)],
                       capture_output=True, text=True, errors="replace", timeout=180)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-300:]
    assert "pcm_s16le" in out, f"打包后 --probe 没输出编码: {out[:300]!r}"
    assert "lossless" in out, out[:300]


# ---------------------------------------------------------------- 界面

def t_gui_builds():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    import gui
    qa = QApplication.instance() or QApplication([])
    w = gui.MainWindow()
    w._remember = False
    w.apply_theme(w.cb_theme.currentIndex())
    assert w.theme in engine.THEMES
    assert w.cb_target.count() == len(engine.targets())
    assert w.cb_lang.count() == 2
    assert w.cb_theme.count() == len(engine.THEME_ORDER)
    w.close()


def t_gui_end_to_end():
    """界面里真的导入 -> 渲染 -> 转换。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    import gui
    qa = QApplication.instance() or QApplication([])
    w = gui.MainWindow()
    w._remember = False
    w.apply_theme(w.cb_theme.currentIndex())
    d = tmpdir()
    for n in ("x", "y"):
        engine.make_tone_wav(d / f"{n}.wav", seconds=0.6)
    engine.set_config_value("out_dir", f'"{d / "out"}"')
    w.lbl_out.setText(str(d / "out"))
    w.add_paths([str(d / "x.wav"), str(d / "y.wav")])
    t0 = time.monotonic()
    while w.probe_thread and w.probe_thread.isRunning():
        QCoreApplication.processEvents()
        time.sleep(0.02)
    assert time.monotonic() - t0 < 120, "探测卡住了"
    QCoreApplication.processEvents()
    assert len(w.tracks) == 2, len(w.tracks)
    assert len(w.rows) == 2, "行没渲染出来"
    assert all(t.ok for t in w.tracks)

    w.cb_target.setCurrentIndex([t.key for t in engine.targets()].index("flac"))
    # 源是 WAV（无损），转 FLAC 应该被 GUI 判为「无损转无损」跳过
    w.pick = {t.path for t in w.tracks if t.ok}
    w.recalc()
    w.start_convert()
    QCoreApplication.processEvents()
    assert all(t.state == "skipped" for t in w.tracks), \
        f"无损转无损应被跳过: {[t.state for t in w.tracks]}"
    w.pick.clear()
    for t in w.tracks:
        t.state = "pending"

    # 源转成有损的 MP3，再转 FLAC —— 这才该真跑
    for t in w.tracks:
        assert t.lossless
    w.tracks = []
    w._render()
    w.add_paths([str(d / "x.wav"), str(d / "y.wav")])
    while w.probe_thread and w.probe_thread.isRunning():
        QCoreApplication.processEvents()
        time.sleep(0.02)
    QCoreApplication.processEvents()
    mid = d / "mid"
    for t in w.tracks:
        r = engine.convert(t, mid, engine.target_by_key("mp3"), "medium")
        assert r.state == "done", r.err
        t.path = r.out_path
        t.size = r.out_size
        t.lossless = False
    w._render()
    w.pick = {t.path for t in w.tracks}
    w.recalc()
    w.start_convert()
    t0 = time.monotonic()
    while w.conv_thread and w.conv_thread.isRunning():
        QCoreApplication.processEvents()
        time.sleep(0.02)
    assert time.monotonic() - t0 < 180, "转换卡住了"
    QCoreApplication.processEvents()
    done = [t for t in w.tracks if t.state == "done"]
    assert len(done) == 2, f"界面转换没全成功: {[t.state for t in w.tracks]} {done and done[0].err}"
    for t in done:
        assert Path(t.out_path).exists()
        back = engine.probe(t.out_path)
        assert back.codec == "flac"
        # 转换后必须回读产物元数据：转成 FLAC 还显示 pcm_s16le 是在说源文件
        assert t.codec == "flac", f"转换后元数据没刷新，仍是 {t.codec}"
        assert t.lossless is True
    # 重建行不能翻倍 —— _render 靠 self.rows 摘旧行，调用方提前清空就会漏
    assert len(w.rows) == 2, f"行数翻倍了: {len(w.rows)}"
    w.close()


def t_gui_duplicate_import_ignored():
    """同一文件重复导入只留一条。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    import gui
    qa = QApplication.instance() or QApplication([])
    w = gui.MainWindow()
    d = tmpdir()
    f = engine.make_tone_wav(d / "one.wav", seconds=0.2)
    # 探测结果是信号投递的，add_paths 返回时还没进 self.tracks。
    # 所以先把路径攒起来一次性导入，这才是"用户重复拖同一个文件"的真实语义。
    w.add_paths([str(f), str(f), str(f)])
    t0 = time.monotonic()
    while w.probe_thread and w.probe_thread.isRunning():
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert time.monotonic() - t0 < 60
    QCoreApplication.processEvents()
    assert len(w.tracks) == 1, f"同一文件重复导入 {len(w.tracks)} 次"
    assert len(w.rows) == 1
    w.close()


def t_resource_priority():
    """打包后必须优先读 exe 同目录的 settings.yaml，不能读 _MEIPASS。

    onefile 会把打包的 datas 解到 _MEIPASS（只读的一次性副本）。如果优先读
    它，用户放在 exe 旁边的配置永远不生效 —— 改了跟没改一样。这是个只有
    打包后才暴露的 bug，用模拟 frozen 环境来测。
    """
    script = r'''
import sys, tempfile, os
from pathlib import Path
me   = Path(tempfile.mkdtemp())          # _MEIPASS: 只读模板
exe  = Path(tempfile.mkdtemp())          # exe 同目录: 用户可改
(me / "settings.yaml").write_text('theme: "FROM_MEIPASS"\nlang: "zh"\n', encoding="utf-8")
(exe / "settings.yaml").write_text('theme: "FROM_EXE_DIR"\nlang: "en"\n', encoding="utf-8")
sys.frozen = True
sys._MEIPASS = str(me)
sys.executable = str(exe / "AudioForge.exe")
import audioforge as e
got = e.resource("settings.yaml")
print(got.parent == exe, e.CFG["theme"], e.CFG["lang"])
'''
    r = subprocess.run([sys.executable, "-c", script], capture_output=True,
                       text=True, errors="replace", timeout=120, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-300:]
    out = r.stdout.strip()
    assert out.startswith("True"), f"没优先读 exe 同目录: {out!r}"
    assert "FROM_EXE_DIR" in out, f"读到的是 _MEIPASS 的副本: {out!r}"
    assert "en" in out.split()[-1], f"lang 也不是用户那份: {out!r}"


def t_ensure_settings_creates():
    """打包后第一次运行要在 exe 旁边放一份可改的配置。"""
    script = r'''
import sys, tempfile
from pathlib import Path
me  = Path(tempfile.mkdtemp())
exe = Path(tempfile.mkdtemp())
(me / "settings.yaml").write_text('theme: "T"\nlang: "zh"\n', encoding="utf-8")
sys.frozen = True
sys._MEIPASS = str(me)
sys.executable = str(exe / "AudioForge.exe")
import audioforge as e
p = e._writable_config()
print(p.parent == exe, p.exists(), p.read_text(encoding="utf-8").count("theme"))
'''
    r = subprocess.run([sys.executable, "-c", script], capture_output=True,
                       text=True, errors="replace", timeout=120, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-300:]
    assert r.stdout.strip() == "True True 1", r.stdout.strip()


# ---------------------------------------------------------------- 主题 / i18n

def t_themes():
    assert len(engine.THEMES) == 6, len(engine.THEMES)
    assert len(engine.THEME_ORDER) == 6
    for name, t in engine.THEMES.items():
        for k in ("bg", "panel", "panel2", "fg", "accent", "safe", "caution",
                  "line", "line2", "fg2", "fg3", "onaccent", "accent2", "sel"):
            assert k in t and t[k], f"{name} 缺 {k}"
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", t["bg"]), f"{name} bg 格式错"
        assert t["sel"].startswith("rgba("), f"{name} sel 要是 rgba 半透明"


def t_theme_contrast():
    bad = []
    for name, t in engine.THEMES.items():
        for fg in ("fg", "fg2", "fg3", "accent", "safe", "caution"):
            r = engine._contrast(t[fg], t["bg"])
            if r < 4.5:
                bad.append(f"{name}.{fg} {r:.2f}:1")
    assert not bad, "对比度不达 AA (4.5:1): " + "; ".join(bad)


def t_theme_onaccent():
    bad = []
    for name, t in engine.THEMES.items():
        r = engine._contrast(t["onaccent"], t["accent"])
        if r < 4.5:
            bad.append(f"{name} onaccent {r:.2f}:1")
    assert not bad, "按钮文字对比度不足: " + "; ".join(bad)


def t_i18n_complete():
    lang.set_lang("en")
    try:
        for k, v in lang._EN.items():
            if not re.search(r"[\u4e00-\u9fff]", k):
                continue
            assert v.strip(), f"译文为空: {k!r}"
            assert lang.T(k) != k, f"没翻: {k!r}"
            assert not re.search(r"[\u4e00-\u9fff]", v), f"译文里还有中文: {k!r} -> {v!r}"
        for t in engine.targets():
            # label/格式名是英文标识，不参与
            assert t.key and t.ext
        # 界面上每句都得有对应的 T()
        src = (ROOT / "gui.py").read_text(encoding="utf-8")
        for _q, lit in set(re.findall(r'T\((?:f?)([rf]?)"([^"]*)"', src)):
            if not re.search(r"[\u4e00-\u9fff]", lit):
                continue
            miss = [g for g in lang._EN if g in lit and lang.T(g) == g]
            assert not miss, f"这句有词没翻: {lit!r} 缺 {miss}"
        # 组合句拼完不能残留中文
        for probe in ("已选择 3 项 · 合计 1.2 GB · 总时长 4:56",
                      "可省下 1.2 GB", "转换完成 · 5 ok"):
            out = lang.T(probe)
            assert not re.search(r"[\u4e00-\u9fff]", out), f"没翻干净: {probe!r} -> {out!r}"
    finally:
        lang.set_lang("zh")
    assert lang.T("开始转换") == "开始转换", "中文模式必须是恒等"


# ---------------------------------------------------------------- 文档 / 仓库

def t_docs_present():
    need = ["README.md", "README.en.md", "CHANGELOG.md", "CHANGELOG.en.md",
            "LICENSE", "CONTRIBUTING.md", "CONTRIBUTING.en.md",
            "SECURITY.md", "SECURITY.en.md", "CODE_OF_CONDUCT.md",
            "CODE_OF_CONDUCT.en.md", "settings.yaml", "requirements.txt",
            "build.bat", "AudioForge.spec", ".gitignore",
            "docs/usage.md", "docs/usage.en.md",
            "docs/Screenshots.md", "docs/Screenshots.en.md"]
    for f in need:
        p = ROOT / f
        assert p.is_file(), f"缺 {f}"
        assert p.stat().st_size > 20, f"{f} 是空的"


def t_docs_bilingual():
    pairs = [("README.md", "README.en.md"), ("CHANGELOG.md", "CHANGELOG.en.md"),
             ("CONTRIBUTING.md", "CONTRIBUTING.en.md"),
             ("SECURITY.md", "SECURITY.en.md"),
             ("CODE_OF_CONDUCT.md", "CODE_OF_CONDUCT.en.md"),
             ("docs/usage.md", "docs/usage.en.md"),
             ("docs/Screenshots.md", "docs/Screenshots.en.md")]
    for zh, en in pairs:
        e = (ROOT / en).read_text(encoding="utf-8")
        body = "\n".join(ln for ln in e.splitlines()
                         if not ln.lstrip().startswith(("|", ">", "!", "```")))
        cjk = len(re.findall(r"[\u4e00-\u9fff]", body))
        ratio = cjk / max(1, len(body))
        assert ratio < 0.02, f"{en} 还有 {ratio:.1%} 中文，翻译没跟上"
        assert "TODO" not in e.upper().replace("TODO:", ""), f"{en} 有占位符"


def t_repo_links():
    for f in ("README.md", "README.en.md", "CHANGELOG.md", "audioforge.py"):
        t = (ROOT / f).read_text(encoding="utf-8")
        for m in re.findall(r"github\.com/([\w.\-]+)/", t):
            assert m == engine.REPO_OWNER, f"{f} 里的仓库用户名不对: {m}"


def t_version_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", engine.__version__), engine.__version__
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert engine.__version__ in cl, "CHANGELOG 里没这个版本"


def t_no_placeholders():
    for f in list(ROOT.glob("*.py")) + list(ROOT.glob("*.md")) + [ROOT / "settings.yaml"]:
        if f.name in ("test_app.py",):
            continue
        t = f.read_text(encoding="utf-8", errors="replace")
        for bad in ("FIXME", "XXX_TODO", "your-username", "YOUR_NAME", "<占位>"):
            assert bad not in t, f"{f.name} 还有占位符 {bad}"


def t_console_encoding_safe():
    """非 UTF-8 控制台不能崩（GitHub Actions 的 cp1252）。"""
    env = dict(os.environ, PYTHONIOENCODING="", PYTHONUTF8="0")
    r = subprocess.run([sys.executable, str(ROOT / "gui.py"), "--version"],
                       capture_output=True, text=True, errors="replace",
                       timeout=120, env=env, cwd=str(ROOT))
    assert r.returncode == 0, f"退出码 {r.returncode}: {r.stderr[-200:]}"
    assert engine.__version__ in (r.stdout + r.stderr)


# ---------------------------------------------------------------- 主流程

CHECKS = [
    ("human 字节格式化", t_human),
    ("找到 ffmpeg 且编码器齐全", t_find_tools),
    ("目标格式定义自洽", t_targets_sane),
    ("target_by_key 冷启动可用", t_target_lookup_cold),
    ("ffprobe 真探测", t_probe_real),
    ("探测拒掉垃圾文件", t_probe_rejects_junk),
    ("绝不覆盖同名输出", t_never_overwrite),
    ("七种格式真转真回探测", t_convert_roundtrip),
    ("失败不留 .part 残渣", t_convert_no_partial_left),
    ("无损判定", t_lossless_to_lossless_skipped),
    ("统计汇总", t_summary),
    ("--probe 命令行", t_probe_cli),
    ("--probe 命令行（打包后）", t_probe_cli_packed),
    ("界面构建+主题", t_gui_builds),
    ("界面端到端转换", t_gui_end_to_end),
    ("重复导入被忽略", t_gui_duplicate_import_ignored),
    ("六套主题定义完整", t_themes),
    ("主题对比度达 AA", t_theme_contrast),
    ("按钮文字对比度达 AA", t_theme_onaccent),
    ("界面文案英译无遗漏", t_i18n_complete),
    ("文档齐全", t_docs_present),
    ("中英文档成对", t_docs_bilingual),
    ("仓库链接用户名一致", t_repo_links),
    ("版本号语义化+变更日志", t_version_semver),
    ("无占位符残留", t_no_placeholders),
    ("非 UTF-8 控制台不崩", t_console_encoding_safe),
    ("打包后优先读 exe 同目录配置", t_resource_priority),
    ("打包后生成可改配置", t_ensure_settings_creates),
]


def main() -> int:
    print(f"\n> {engine.APP_NAME} {engine.__version__} self-test")
    if not engine.ffmpeg_path():
        print("!! 找不到 ffmpeg，先装：winget install ffmpeg")
        return 1
    failed = []
    t_all = time.monotonic()
    for name, fn in CHECKS:
        t0 = time.monotonic()
        try:
            fn()
            print(f"  ok   {name}  ({time.monotonic() - t0:.1f}s)")
        except Exception as e:
            failed.append(name)
            print(f"  FAIL {name}  -> {type(e).__name__}: {e}")
            for ln in traceback.format_exc().splitlines()[-4:]:
                print(f"       {ln}")
    secs = time.monotonic() - t_all
    print()
    if failed:
        print(f"{len(failed)} FAILED: {'; '.join(failed)}  ({secs:.1f}s)")
        return 1
    print(f"ALL OK — {len(CHECKS)} checks in {secs:.1f}s")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        cleanup()
        # 真正的不留残渣检查放在 cleanup 之后
        stragglers = list(Path(tempfile.gettempdir()).glob("af_test_*"))
        if stragglers:
            print(f"!! cleanup 没清干净: {[p.name for p in stragglers[:5]]}")
            code = 1
    sys.exit(code)
