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
    # 别用 set_config_value 改真实的 settings.yaml —— 那是用户的配置。
    # 之前这么写把临时路径写进了 dist/settings.yaml，用户第一次打开就看到一个
    # 指向 af_test_xxx 的输出目录。这里换成本次测试专用的配置文件。
    cfg = d / "settings.yaml"
    cfg.write_text('theme: "Tokyo Night"\nlang: "en"\nout_dir: ""\n', encoding="utf-8")
    saved_wc = engine._writable_config
    saved_cfg = dict(engine.CFG)
    engine._writable_config = lambda: cfg
    try:
        engine.set_config_value("out_dir", f'"{d / "out"}"')
        _run_gui_convert(w, d)
    finally:
        engine._writable_config = saved_wc
        # set_config_value 会顺手改内存里的 CFG，不还原的话测试值会漏给后面
        # 的检查（t_tests_dont_touch_real_settings 抓到过这个）
        engine.CFG.clear()
        engine.CFG.update(saved_cfg)
    w.close()


def _run_gui_convert(w, d) -> None:
    """界面端到端：导入 -> 渲染 -> 跳过无损转无损 -> 转 MP3 -> FLAC。"""
    from PySide6.QtCore import QCoreApplication
    w.lbl_out.setFull(str(d / "out"))
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
    打包后才暴露的 bug。

    关键：frozen / _MEIPASS / executable 必须在 import audioforge **之前**
    设好。audioforge 在 import 期就会 load_settings()，顺序反了测的就是
    另一个东西（本地能过、CI 上 KeyError 就是这么来的）。
    """
    script = r'''
import sys, tempfile
from pathlib import Path
me  = Path(tempfile.mkdtemp())     # _MEIPASS：只读模板
exe = Path(tempfile.mkdtemp())     # exe 同目录：用户可改
(me / "settings.yaml").write_text('theme: "FROM_MEIPASS"\nlang: "zh"\n', encoding="utf-8")
(exe / "settings.yaml").write_text('theme: "FROM_EXE_DIR"\nlang: "en"\n', encoding="utf-8")
sys.frozen = True                  # 必须在 import 之前
sys._MEIPASS = str(me)
sys.executable = str(exe / "AudioForge.exe")
sys.path.insert(0, __PROJ__)             # cwd 是干净临时目录，得自己指路
import audioforge as e              # import 期就会读配置
# 测的是 _writable_config()，不是 resource() —— 后者现在已经没人调用了
# （重构后 load_settings 走 ensure_settings -> _writable_config）。之前
# 一直在测一个死函数，CI 上 DIR_BAD 而本地 DIR_OK，两边都不算证据。
print("DIR_OK" if e._writable_config().parent == exe else "DIR_BAD")
print("THEME", e.CFG.get("theme", "<none>"))
print("LANG", e.CFG.get("lang", "<none>"))
'''
    # cwd 用干净的临时目录：否则子进程在源码目录跑，resource() 的兜底会找到
    # 仓库里那份 settings.yaml，测的就不是「用户自带配置」这个场景了。
    import tempfile as _tf
    # 用 repr() 双重保险：路径里有空格和反斜杠，直接拼进源码会被当转义序列
    script = script.replace("__PROJ__", repr(str(ROOT)))
    with _tf.TemporaryDirectory(prefix="af_cfgtest_") as _cwd:
        r = subprocess.run([sys.executable, "-c", script], capture_output=True,
                           text=True, errors="replace", timeout=120, cwd=_cwd)
    assert r.returncode == 0, f"子进程挂了: {r.stderr[-400:]}"
    out = r.stdout
    assert "DIR_OK" in out, f"没优先读 exe 同目录:\n{out}"
    assert "THEME FROM_EXE_DIR" in out, f"读到的是 _MEIPASS 的副本:\n{out}"
    assert "LANG en" in out, f"lang 也不是用户那份:\n{out}"


def t_ensure_settings_creates():
    """打包后第一次运行要在 exe 旁边放一份可改的配置。"""
    script = r'''
import sys, tempfile
from pathlib import Path
me  = Path(tempfile.mkdtemp())
exe = Path(tempfile.mkdtemp())          # 故意不放 settings.yaml
(me / "settings.yaml").write_text('theme: "T"\nlang: "zh"\n', encoding="utf-8")
sys.frozen = True                       # 必须在 import 之前
sys._MEIPASS = str(me)
sys.executable = str(exe / "AudioForge.exe")
sys.path.insert(0, __PROJ__)
import audioforge as e
p = e._writable_config()
print("DIR_OK" if p.parent == exe else "DIR_BAD")
print("EXISTS" if p.exists() else "MISSING")
print("THEMES", p.read_text(encoding="utf-8").count("theme"))
'''
    # cwd 用干净的临时目录：否则子进程在源码目录跑，resource() 的兜底会找到
    # 仓库里那份 settings.yaml，测的就不是「用户自带配置」这个场景了。
    import tempfile as _tf
    # 用 repr() 双重保险：路径里有空格和反斜杠，直接拼进源码会被当转义序列
    script = script.replace("__PROJ__", repr(str(ROOT)))
    with _tf.TemporaryDirectory(prefix="af_cfgtest_") as _cwd:
        r = subprocess.run([sys.executable, "-c", script], capture_output=True,
                           text=True, errors="replace", timeout=120, cwd=_cwd)
    assert r.returncode == 0, f"子进程挂了: {r.stderr[-400:]}"
    out = r.stdout
    assert "DIR_OK" in out, out
    assert "EXISTS" in out, f"打包后没在 exe 旁边生成可改配置:\n{out}"
    assert "THEMES 1" in out, out


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


def t_deps_declared():
    """requirements.txt 必须列全运行时依赖。

    漏了 PyYAML 时 load_settings() 的 import yaml 会失败，被 except 兜住静默
    返回 {}，表现是「配置怎么改都不生效」—— 本机有（别的包带的）所以一直绿，
    CI 全新环境才红。这个测试是防重蹈覆辙的。
    """
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for need, why in (("pyside6", "界面"),
                      ("pyyaml", "settings.yaml 解析，漏了配置静默失效"),
                      ("pyinstaller", "打包")):
        assert need in req, f"requirements.txt 漏了 {need}（{why}）"
    import importlib
    for mod in ("yaml", "PySide6.QtWidgets"):
        try:
            importlib.import_module(mod)
        except ImportError as e:
            raise AssertionError(f"{mod} 装了 requirements 也 import 不了: {e}")


def t_settings_actually_loaded():
    """配置真的被读到了 —— CFG 不能是空的。

    t_deps_declared 查依赖表，这条查运行时效果。
    """
    assert engine.CFG, "CFG 是空的：settings.yaml 没读到（多半是缺 PyYAML）"
    assert "theme" in engine.CFG, f"CFG 缺 theme: {engine.CFG}"


def t_windows_path_in_yaml():
    r"""Windows 路径写进 settings.yaml 后必须还能读回来。

    这是个真 bug：set_config_value 原来写的是 f'"{value}"'，而 YAML 双引号
    标量里反斜杠 + 大写字母是转义序列（\U 尤其致命）。safe_load 直接报
    ScannerError -> load_settings 兜底返回 {} -> **整个配置失效**，表现是
    「我在界面里换了输出目录之后，主题和语言也一起失效了」，症状离病因十万
    八千里。

    所以：写完必须用 yaml.safe_load 验一遍能读，且反斜杠完好。
    """
    import yaml
    d = tmpdir()
    p = d / "settings.yaml"
    p.write_text('theme: "Ink"\nlang: "zh"\nout_dir: ""\n', encoding="utf-8")

    saved = engine._writable_config
    engine._writable_config = lambda: p
    try:
        winpath = r"C:\Users\Administrator\My Music\out"
        engine.set_config_value("out_dir", f'"{winpath}"')
        engine.set_config_value("theme", '"Rosé Pine"')   # 带重音也不能坏

        back = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert back is not None, "写完就读不回来了"
        assert back["out_dir"] == winpath, \
            f"路径被 YAML 吃了转义: {back['out_dir']!r} != {winpath!r}"
        assert back["theme"] == "Rosé Pine", back["theme"]
        # 注释和别的键不能被这次写入弄丢
        assert "lang" in back, back
    finally:
        engine._writable_config = saved

    # 顺手确认 _yaml_quote 自己是对的
    q = engine._yaml_quote(r"C:\a\b")
    assert yaml.safe_load(f"k: {q}")["k"] == r"C:\a\b", q


def t_tests_dont_touch_real_settings():
    """自检跑完之后，用户的 settings.yaml 必须没被改过。

    踩过两次：端到端测试直接调 set_config_value("out_dir", ...)，把临时路径
    写进了真实的 settings.yaml（还因此产生了一个 YAML 语法坏掉的文件 ——
    未转义的 Windows 路径让 safe_load 报 ScannerError，exe 启动时读配置
    抛异常，界面就是一个白窗口）。

    注意这里**不再重跑 t_gui_end_to_end**（那会 close 掉窗口再重建，Qt 在
    同一个 QApplication 里会访问冲突，进程直接 0xC0000005）。只验证配置
    本身没被污染 —— 真正的防线是 t_gui_end_to_end 里已改用临时配置文件。
    """
    import audioforge as eng
    import yaml
    p = eng._writable_config()
    assert p.exists(), f"配置文件不在预期位置: {p}"
    raw = p.read_text(encoding="utf-8")

    # 必须能解析（未转义路径会让 safe_load 抛 ScannerError）
    d = yaml.safe_load(raw)
    assert isinstance(d, dict), "settings.yaml 解析不出字典"
    assert "theme" in d, f"settings.yaml 缺 theme: {d}"
    assert not d.get("out_dir"), \
        f"settings.yaml 的 out_dir 指向了临时目录: {d['out_dir']!r}（自检污染了它）"
    # 内存里的 CFG 是进程级缓存，各项测试改过它；只断言「文件没被污染」。
    # 文件才是用户下次启动时读的东西。
    assert "af_test_" not in raw, \
        "settings.yaml 里出现了测试临时路径，自检污染了用户的配置"


def t_drm_files_reported_honestly():
    """DRM 加密文件要**如实说它是加密的**，不能说「损坏」。

    之前对 KGM 文件报「读不到时长，可能是损坏或不完整的文件」—— 那是误导：
    文件是好的，只是有版权保护。用户会以为自己下载坏了、重新下一遍，
    或者以为工具坏了。

    这类文件还有个坑：喂给 ffprobe 不会干净报错，而是吐出半截乱码当元数据，
    json.loads 抛 `Invalid \\escape`，报错完全指不到真因。所以必须在调
    ffprobe **之前**按魔数拦下来。
    """
    d = tmpdir()
    magic = engine.KGM_MAGIC
    p = d / "song.kgm.flac"
    p.write_bytes(magic + b"\x00" * 1024 + os.urandom(4000))
    t = engine.probe(str(p))
    assert not t.ok, "DRM 文件不该探测成功"
    msg = t.why
    assert "KGM" in msg, f"没认出是 KGM: {msg!r}"
    assert "版权保护" in msg, f"没说清是版权保护: {msg!r}"
    assert "没有坏" in msg or "没坏" in msg, f"没说明文件本身完好: {msg!r}"
    for wrong in ("损坏", "不完整", "Invalid", "escape", "ffprobe"):
        assert wrong not in msg, f"错误信息里不该出现 {wrong!r}: {msg!r}"

    # 其它几种加密封装也要认得出
    for name, head in (("VPR", engine.VPR_MAGIC), ("QMC", b"QMC\x00\x00")):
        q = d / f"x.{name}"
        q.write_bytes(head + os.urandom(2000))
        m = engine.probe(str(q)).why
        assert name in m, f"{name} 没认出来: {m!r}"

    # 真的损坏的 FLAC 仍然该说损坏
    f = d / "broken.flac"
    f.write_bytes(b"fLaC" + b"\x00" * 40)     # 头合法但后面是垃圾
    m2 = engine.probe(str(f)).why
    assert "损坏" in m2 or "截断" in m2 or "读不出时长" in m2, m2


def t_audit_classifies_folder():
    """批量体检：能转 / DRM / 损坏 / 空文件，四类都要分对，且递归子目录。"""
    import os as _os
    d = tmpdir()
    engine.make_tone_wav(d / "ok1.wav", seconds=0.5)
    engine.make_tone_wav(d / "ok2.wav", seconds=0.5)
    (d / "enc.kgm.flac").write_bytes(engine.KGM_MAGIC + b"\x00" * 1024
                                      + _os.urandom(2000))
    (d / "broken.flac").write_bytes(b"fLaC" + b"\x00" * 40)
    (d / "empty.mp3").write_bytes(b"")
    (d / "readme.txt").write_text("hello", encoding="utf-8")
    sub = d / "sub"
    sub.mkdir()
    engine.make_tone_wav(sub / "nested.wav", seconds=0.3)   # 验证递归

    vs = engine.scan_folder(str(d))
    rep = engine.audit_report(vs)
    assert rep["total"] == 7, f"应扫到 7 个（含子目录），实际 {rep['total']}"
    assert rep["n_ok"] == 3, f"能转应为 3，实际 {rep['n_ok']}（子目录没递归？）"
    assert rep["n_drm"] == 1, f"DRM 应为 1，实际 {rep['n_drm']}"
    assert rep["n_broken"] == 2, f"损坏应为 2，实际 {rep['n_broken']}"
    assert rep["n_empty"] == 1, f"空文件应为 1，实际 {rep['n_empty']}"
    assert rep["total_bytes"] > 0
    assert rep["drm_bytes"] > 0

    # 文本报告要能给人看
    txt = engine.audit_lines(vs)
    for must in ("能转", "DRM", "损坏", "空文件", "共"):
        assert must in txt, f"报告里缺 {must!r}:\n{txt}"

    # DRM 文件不该混进可转列表
    ok_paths = {v.path for v in vs if v.verdict == engine.VERDICT_OK}
    assert not any("kgm" in p for p in ok_paths), "DRM 文件被误判成可转"


def t_audit_cli():
    """--audit 命令行能跑。"""
    d = tmpdir()
    engine.make_tone_wav(d / "a.wav", seconds=0.3)
    (d / "e.kgm.flac").write_bytes(engine.KGM_MAGIC + b"\x00" * 512)
    r = subprocess.run([sys.executable, str(ROOT / "gui.py"), "--audit", str(d)],
                       capture_output=True, text=True, errors="replace",
                       timeout=180, cwd=str(ROOT),
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-300:]
    assert "DRM" in out, out[:300]
    assert "a.wav" in out, out[:300]


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
    ("依赖声明完整", t_deps_declared),
    ("配置真的被读到", t_settings_actually_loaded),
    ("Windows 路径写进 YAML 不坏", t_windows_path_in_yaml),
    ("自检不碰用户配置", t_tests_dont_touch_real_settings),
    ("文档齐全", t_docs_present),
    ("中英文档成对", t_docs_bilingual),
    ("仓库链接用户名一致", t_repo_links),
    ("版本号语义化+变更日志", t_version_semver),
    ("无占位符残留", t_no_placeholders),
    ("非 UTF-8 控制台不崩", t_console_encoding_safe),
    ("打包后优先读 exe 同目录配置", t_resource_priority),
    ("打包后生成可改配置", t_ensure_settings_creates),
    ("DRM 文件如实报错", t_drm_files_reported_honestly),
    ("批量体检分类正确", t_audit_classifies_folder),
    ("--audit 命令行", t_audit_cli),
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
