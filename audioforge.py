"""AudioForge —— 本地音频转码。核心逻辑全在这里，gui.py 只管显示。

设计原则照 DevCleaner：不猜、不覆盖、不联网。
- 不覆盖源文件，永远输出到单独目录，重名自动加序号
- 源文件先探测再转码，拿不到时长/采样率就不转（不做盲转）
- ffmpeg / ffprobe 走 PATH 或用户配置；找不到就明说，不静默失败
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

APP_NAME = "AudioForge"
__version__ = "0.1.0"
REPO_OWNER = "matou1118"
REPO_NAME = "AudioForge"
REPO = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"

# 打包成 console=False 的 GUI exe 后没有可靠 stdout，版本/帮助走 stderr。
for _n in ("stderr", "stdout"):
    try:
        getattr(sys, _n).reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def resource(name: str) -> Path:
    """找资源。

    打包后（frozen）：exe 同目录优先，其次 _MEIPASS，最后源码目录。
    源码运行：exe 同目录不参与（那是 python.exe 的目录），直接用源码目录。

    exe 同目录必须排第一。onefile 会把打包的 datas 解到 _MEIPASS，那是只读的
    一次性副本 —— 优先读它的话，用户放在 exe 旁边的 settings.yaml 永远不生效，
    改了配置跟没改一样。_MEIPASS 只作「用户还没建配置文件」时的兜底。
    """
    frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        p = Path(sys.executable).parent / name
        if p.exists():
            return p
        base = getattr(sys, "_MEIPASS", None)
        if base:
            p = Path(base) / name
            if p.exists():
                return p
    return Path(__file__).parent / name


# ---------------------------------------------------------------- 配置

DEFAULT_SETTINGS = """\
# AudioForge 配置 / Configuration
# 改完重启生效；界面里切换主题/语言会自动写回这里。
# Edits take effect on restart; switching theme or language writes back here.

theme: "Tokyo Night"
lang: "zh"
ffmpeg_path: ""
out_dir: ""
"""


def _writable_config() -> Path:
    """用户可写的配置文件位置：打包后是 exe 同目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "settings.yaml"
    return Path(__file__).parent / "settings.yaml"


def ensure_settings() -> Path:
    """保证用户手边有一份可改的 settings.yaml。

    打包后 _MEIPASS 里那份是只读的，只作模板用。第一次运行时复制到 exe 旁边，
    否则用户改了配置也没地方改 —— 「放个配置在 exe 旁边」是文档里承诺的用法。
    """
    target = _writable_config()
    if target.exists():
        return target
    base = getattr(sys, "_MEIPASS", None)
    src = Path(base) / "settings.yaml" if base else Path(__file__).parent / "settings.yaml"
    text = src.read_text(encoding="utf-8") if src.exists() else DEFAULT_SETTINGS
    try:
        target.write_text(text, encoding="utf-8")
    except OSError:
        return src          # 没写权限（Program Files 之类），退回只读那份
    return target


def load_settings() -> dict:
    p = ensure_settings()
    if not p.exists():
        return {}
    try:
        import yaml
    except ImportError:
        # 不能静默兜底。漏装 PyYAML 时以前这里会 return {}，表现是
        # "配置怎么改都不生效" —— 排查成本极高。直接说清楚缺什么。
        raise SystemExit(
            "PyYAML 没装，settings.yaml 读不了。\n"
            "PyYAML is missing, settings.yaml cannot be read.\n"
            "  pip install -r requirements.txt") from None
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}
    except Exception as e:
        # 配置坏了不该让程序起不来，但要留下线索
        CFG_ERROR = f"settings.yaml 解析失败（{p}）: {e}"
        return {}


CFG = load_settings()


def set_config_value(key: str, literal: str) -> None:
    r"""就地改配置并落盘。

    literal 是已序列化的 YAML 标量（含引号）。

    Windows 路径必须转义反斜杠：YAML 双引号里 `C:\\Users\\...` 的 \U 是
    非法转义，safe_load 直接报 ScannerError。写 `C:\Users` 会让**整个
    settings.yaml 解析失败**，load_settings 兜底返回 {}，于是「改输出目录
    之后所有配置都失效了」—— 症状离病因十万八千里。必须 yaml.safe_dump 那一
    层的转义。
    """
    p = _writable_config()
    if not p.exists():
        return
    try:
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        out, hit = [], False
        for ln in lines:
            m = re.match(rf"^(\s*){re.escape(key)}\s*:", ln)
            if m:
                out.append(f"{m.group(1)}{key}: {_yaml_quote(literal.strip())}\n")
                hit = True
            else:
                out.append(ln)
        if not hit:
            out.append(f"{key}: {_yaml_quote(literal.strip())}\n")
        p.write_text("".join(out), encoding="utf-8")
    except OSError:
        return          # 只读就只更新内存里的值，不报错打扰用户
    CFG[key] = literal.strip().strip('"')


def _yaml_quote(value: str) -> str:
    r"""给 YAML 值加引号，反斜杠保持字面量。

    手写 f'"{value}"' 是不够的：Windows 路径里满地反斜杠，而 YAML 双引号
    标量里反斜杠 + 大写字母/数字都被当转义序列（U/T/N 这几个尤其致命）。
    用单引号更省事 —— 单引号里只有单引号本身需要转义，反斜杠是字面量。
    """
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1]        # 调用方可能已经带了引号，别套两层
    return "'" + v.replace("'", "''") + "'"


# ---------------------------------------------------------------- 颜色

def _hx(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hs(r: int, g: int, b: int) -> str:
    return "#%02X%02X%02X" % (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def _mix(a: str, b: str, t: float) -> str:
    A, B = _hx(a), _hx(b)
    return _hs(*[round(A[i] + (B[i] - A[i]) * t) for i in range(3)])


def _lum(h: str) -> float:
    def ch(v: int) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _hx(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


def _theme(name: str, bg: str, panel: str, panel2: str, fg: str, accent: str,
           safe: str, caution: str, line: str) -> Dict[str, str]:
    on = bg if _contrast(bg, accent) >= _contrast("#FFFFFF", accent) else "#FFFFFF"
    return {
        "n": name, "bg": bg, "panel": panel, "panel2": panel2, "fg": fg,
        "accent": accent, "safe": safe, "caution": caution, "line": line,
        "line2": _mix(line, fg, 0.22),
        "fg2": _mix(bg, fg, 0.66),
        # fg3 用 0.68 而不是 0.52：0.52 时 Paper 只有 3.13:1、Tokyo Night
        # 3.82:1，说明/标签这类文字在浅底上太淡。0.68 是让六套全部达 AA 的
        # 最小值（测试里 t_theme_contrast 会盯着这条线）。
        "fg3": _mix(bg, fg, 0.68),
        "onaccent": on,
        "accent2": _mix(accent, bg, 0.16),
        "sel": "rgba(%d,%d,%d,26)" % _hx(accent),
    }


_PALETTES = [
    # accent / safe / caution 是在底色上做彩色文字，全部按 WCAG AA(4.5:1) 校过
    # —— 见 test_app.t_theme_contrast。Studio Dark 的 #5E6AD2 在近黑底上只有
    # 4.24:1，同色相提亮到 #8891E6；Paper 三个在浅底上偏淡，分别压深。
    _theme("Studio Dark", "#08090A", "#0E0F11", "#16171A", "#F7F8F8",
           "#8891E6", "#3FB950", "#D29922", "#1E1F22"),
    _theme("Studio Light", "#FBFBFA", "#FFFFFF", "#F4F4F2", "#1A1A1A",
           "#5E6AD2", "#1A7F37", "#9A6700", "#E5E5E3"),
    _theme("Paper", "#F5F1EA", "#FFFCF6", "#EFE9DD", "#2B2722",
           "#B15238", "#58763B", "#906623", "#DDD5C7"),
    _theme("Ink", "#1C1A17", "#252320", "#2D2A26", "#F0EBE0",
           "#C77B5C", "#8FB06A", "#D9A85C", "#3A3631"),
    _theme("Rosé Pine", "#191724", "#1F1D2E", "#26233A", "#E0DEF4",
           "#EBBCBA", "#9CCFD8", "#F6C177", "#403D52"),
    _theme("Tokyo Night", "#1A1B26", "#16161E", "#1F2335", "#C0CAF5",
           "#7AA2F7", "#9ECE6A", "#E0AF68", "#2D2F40"),
]

THEMES: Dict[str, Dict[str, str]] = {t["n"]: t for t in _PALETTES}
THEME_ORDER: List[str] = [t["n"] for t in _PALETTES]
DEFAULT_THEME = str(CFG.get("theme") or "Tokyo Night")

# ---------------------------------------------------------------- ffmpeg


def _tool(name: str) -> Optional[str]:
    """按 配置 -> PATH -> 常见安装位置 的顺序找可执行文件。"""
    override = str(CFG.get("ffmpeg_path") or "").strip()
    if override:
        cand = Path(override) / (name + ".exe")
        if cand.exists():
            return str(cand)
        if override.lower().endswith(".exe") and Path(override).exists():
            return override
    found = shutil.which(name)
    if found:
        return found
    for base in (Path(sys.executable).parent, Path(__file__).parent,
                 Path("C:/ProgramData/chocolatey/bin"), Path("C:/ffmpeg/bin")):
        cand = base / (name + ".exe")
        if cand.exists():
            return str(cand)
    return None


def ffmpeg_path() -> Optional[str]:
    return _tool("ffmpeg")


def ffprobe_path() -> Optional[str]:
    return _tool("ffprobe")


def ffmpeg_version() -> str:
    exe = ffmpeg_path()
    if not exe:
        return ""
    try:
        r = subprocess.run([exe, "-hide_banner", "-version"],
                           capture_output=True, text=True, errors="replace", timeout=20)
        first = (r.stdout or r.stderr or "").strip().splitlines()
        return first[0] if first else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# 输入容器/编码 -> 展示名。用于「这是不是已经无损」这类判断。
LOSSLESS_CODECS = {"flac", "alac", "pcm_s16le", "pcm_s24le", "pcm_s32le",
                   "pcm_f32le", "wavpack", "ape", "tta", "shorten"}
LOSSLESS_EXTS = {".flac", ".wav", ".aiff", ".aif", ".ape", ".wv", ".tta"}


@dataclass
class Track:
    path: str
    ok: bool = False
    why: str = ""            # 探测失败的原因（直接显示给用户）
    size: int = 0
    fmt: str = ""            # 容器，如 flac / mp4
    codec: str = ""          # 编码名，如 flac / aac / libmp3lame
    duration: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    bitrate: int = 0
    lossless: bool = False
    title: str = ""
    artist: str = ""
    # 转换状态
    state: str = "pending"   # pending / working / done / failed / skipped
    out_path: str = ""
    out_size: int = 0
    err: str = ""


def probe(path: str) -> Track:
    t = Track(path=path)
    p = Path(path)
    if not p.exists():
        t.why = "文件不存在"
        return t
    try:
        t.size = p.stat().st_size
    except OSError as e:
        t.why = f"读不了: {e}"
        return t
    if t.size == 0:
        t.why = "空文件"
        return t

    exe = ffprobe_path()
    if not exe:
        t.why = "找不到 ffprobe"
        return t
    try:
        r = subprocess.run(
            [exe, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", "-select_streams", "a:0", path],
            capture_output=True, text=True, errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        t.why = f"ffprobe 失败: {e}"
        return t
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        t.why = err[:120] if err else "ffprobe 报错，文件可能已损坏"
        return t
    try:
        import json
        d = json.loads(r.stdout or "{}")
    except Exception as e:
        t.why = f"ffprobe 输出解析不了: {e}"
        return t

    st = (d.get("streams") or [None])[0]
    if not st:
        t.why = "没有音频轨（可能不是音频文件）"
        return t
    fmt = d.get("format") or {}
    t.fmt = (fmt.get("format_name") or "").split(",")[0]
    t.codec = st.get("codec_name") or ""
    try:
        t.duration = float(fmt.get("duration") or st.get("duration") or 0)
    except (TypeError, ValueError):
        t.duration = 0.0
    try:
        t.sample_rate = int(st.get("sample_rate") or 0)
    except (TypeError, ValueError):
        t.sample_rate = 0
    t.channels = int(st.get("channels") or 0)
    try:
        t.bitrate = int(fmt.get("bit_rate") or 0)
    except (TypeError, ValueError):
        t.bitrate = 0

    tags = {**(fmt.get("tags") or {}), **(st.get("tags") or {})}
    t.title = tags.get("title") or ""
    t.artist = tags.get("artist") or tags.get("album_artist") or ""
    t.lossless = (t.codec in LOSSLESS_CODECS) or (p.suffix.lower() in LOSSLESS_EXTS)
    if t.duration <= 0:
        t.why = "读不到时长，可能是损坏或不完整的文件"
        return t
    t.ok = True
    return t


# ---------------------------------------------------------------- 目标格式

@dataclass
class Target:
    key: str
    ext: str
    label: str
    lossless: bool
    # ffmpeg -c:a 之后的参数
    args: List[str] = field(default_factory=list)
    # 输出容器名（-f）。中间文件叫 xxx.mp3.part，ffmpeg 从扩展名认不出容器，
    # 必须显式给 -f，否则报 "Error opening output files: Invalid argument"。
    # 这就是为什么它得是字段而不是 convert() 里的硬编码字典。
    fmt: str = ""


# 码率档：给三种，界面上选。VBR 用 -q:a（ lame 0-9 越高越差，opus 0-10 相反）
BITS = [
    ("small", 96, "小"),
    ("medium", 192, "中"),
    ("high", 320, "高"),
]


_TARGET_CACHE: Dict[str, "Target"] = {}


def _TARGET_DEFS() -> List["Target"]:
    return [
        Target("mp3", ".mp3", "MP3", False, ["-c:a", "libmp3lame", "-q:a", "2"], "mp3"),
        Target("aac", ".m4a", "AAC", False, ["-c:a", "aac", "-b:a", "192k"], "ipod"),
        Target("opus", ".opus", "Opus", False, ["-c:a", "libopus", "-b:a", "160k"], "opus"),
        Target("ogg", ".ogg", "Vorbis", False, ["-c:a", "libvorbis", "-q:a", "5"], "ogg"),
        Target("flac", ".flac", "FLAC", True,
               ["-c:a", "flac", "-compression_level", "5"], "flac"),
        Target("alac", ".m4a", "ALAC", True, ["-c:a", "alac"], "ipod"),
        Target("wav", ".wav", "WAV", True, ["-c:a", "pcm_s16le"], "wav"),
    ]


def targets() -> List["Target"]:
    if not _TARGET_CACHE:
        for t in _TARGET_DEFS():
            _TARGET_CACHE[t.key] = t
    return list(_TARGET_CACHE.values())


def target_by_key(k: str) -> Optional["Target"]:
    """按 key 找目标格式，返回缓存的同一实例。

    这里必须自己保证缓存已填 —— 之前只在 targets() 里填，任何不先调 targets()
    的路径（脚本、文档示例）都会拿到 None，然后在 convert() 里炸成
    'NoneType' object has no attribute 'ext'。
    """
    if not _TARGET_CACHE:
        targets()
    return _TARGET_CACHE.get(k)


def unique_out(out_dir: Path, base: str, ext: str) -> Path:
    """绝��覆盖：同名就加 (2) (3)…"""
    cand = out_dir / (base + ext)
    n = 2
    while cand.exists():
        cand = out_dir / f"{base} ({n}){ext}"
        n += 1
    return cand


def build_cmd(src: str, dst: Path, tgt: Target, bitrate_key: str = "medium",
              sample_rate: Optional[int] = None) -> List[str]:
    """拼 ffmpeg 命令。convert() 走的是它，保持一处逻辑。"""
    exe = ffmpeg_path()
    cmd = [exe, "-hide_banner", "-nostdin", "-loglevel", "error", "-n",
           "-i", src, "-vn", "-map_metadata", "0"]
    cmd += list(tgt.args)
    # 有损目标且选了具体码率时，用 -b:a 覆盖掉预设的 -q:a
    if not tgt.lossless and bitrate_key in ("small", "high"):
        q = "-q:a"
        if q in cmd:
            i = cmd.index(q)
            del cmd[i:i + 2]
        cmd += ["-b:a", {"small": "128k", "high": "320k"}[bitrate_key]]
    if sample_rate and sample_rate != 44100:
        cmd += ["-ar", str(sample_rate)]
    cmd += [str(dst)]
    return cmd


def convert(t: Track, out_dir: Path, tgt: Target, bitrate_key: str = "medium",
            on_line=None, cancel: Optional[callable] = None) -> Track:
    """转单个文件。返回同一条 Track，state/out_path/out_size/err 被填好。"""
    exe = ffmpeg_path()
    if not exe:
        t.state, t.err = "failed", "找不到 ffmpeg"
        return t
    src = Path(t.path)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = unique_out(out_dir, src.stem, tgt.ext)
    dst_partial = dst.with_name(dst.name + ".part")
    # 中间文件叫 xxx.mp3.part，ffmpeg 认不出容器，显式 -f 指定封装。
    # -f 和 -map_metadata 都是输出选项，必须排在输出文件之前。
    fmt = tgt.fmt
    if not fmt:
        t.state, t.err = "failed", f"目标格式 {tgt.key} 没指定输出容器"
        return t
    cmd = build_cmd(str(src), dst_partial, tgt, bitrate_key)
    out_opts = ["-f", fmt, "-map_metadata", "0"]
    # build_cmd 末尾是输出路径，把它摘掉，输出选项插到它前面
    cmd, last = cmd[:-1], cmd[-1]
    cmd = cmd[:2] + ["-progress", "pipe:1"] + cmd[2:] + out_opts + [last]
    t.state = "working"
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors="replace", bufsize=1,
                                encoding="utf-8")
        pct = 0.0
        while proc.stdout:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith("out_time_ms=") and t.duration > 0:
                try:
                    us = float(line.split("=", 1)[1])
                    pct = max(0.0, min(100.0, us / 1000.0 / t.duration * 100.0))
                except ValueError:
                    pass
            if on_line:
                on_line(pct, t.path)
            if cancel and cancel():
                proc.kill()
                t.state, t.err = "failed", "已取消"
                dst_partial.unlink(missing_ok=True)
                return t
        proc.wait()
        err = (proc.stderr.read() if proc.stderr else "") or ""
        if proc.returncode != 0:
            t.state = "failed"
            t.err = err.strip().splitlines()[-1] if err.strip() else f"ffmpeg 退出码 {proc.returncode}"
            dst_partial.unlink(missing_ok=True)
            return t
        if not dst_partial.exists() or dst_partial.stat().st_size == 0:
            t.state, t.err = "failed", "输出为空"
            dst_partial.unlink(missing_ok=True)
            return t
        dst_partial.replace(dst)
        t.out_path = str(dst)
        t.out_size = dst.stat().st_size
        t.state = "done"
    except (OSError, subprocess.SubprocessError) as e:
        t.state, t.err = "failed", str(e)
        dst_partial.unlink(missing_ok=True)
    finally:
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
    return t


# ---------------------------------------------------------------- 统计

def summary(tracks: List[Track]) -> dict:
    ok = [t for t in tracks if t.ok]
    tot_in = sum(t.size for t in ok)
    done = [t for t in tracks if t.state == "done"]
    tot_out = sum(t.out_size for t in done)
    return {
        "n": len(tracks),
        "n_ok": len(ok),
        "n_failed": sum(1 for t in tracks if t.state == "failed"),
        "n_lossless": sum(1 for t in ok if t.lossless),
        "duration": sum(t.duration for t in ok),
        "in_bytes": tot_in,
        "out_bytes": tot_out,
        "delta": tot_in - tot_out,
    }


def make_tone_wav(path: Path, seconds: float = 1.0, rate: int = 44100) -> Path:
    """自检用：ffmpeg 造一段测试音。"""
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("no ffmpeg")
    subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-ar", str(rate), "-ac", "2", str(path)],
                   check=True, capture_output=True, timeout=120)
    return path
