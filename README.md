# AudioForge

**本地音频转码。源文件永不改动，输出到单独目录。**

[![CI](https://github.com/matou1118/AudioForge/actions/workflows/ci.yml/badge.svg)](https://github.com/matou1118/AudioForge/actions/workflows/ci.yml)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-9ece6a.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-7aa2f7.svg)

[English](README.en.md) · [使用说明](docs/usage.md) · [截图](docs/Screenshots.md) · [变更日志](CHANGELOG.md)

---

拖一堆音频进来，选目标格式，按一下。**没有编码格式被发明，没有设置要配，没有账号要登。**

- **源文件只读** —— 输出永远写到独立目录，同名自动加 `(2)` `(3)`
- **先探测再转码** —— 拿不到时长/采样率就不转，不做盲转
- **真·往返验证** —— 每次转换后用 `ffprobe` 回读产物，时长、采样率、无损判定全部校验
- **失败不留残渣** —— 输出先写 `.part`，成功才改名，失败当场清掉
- **6 套配色主题** + **中英双语**，全部离线，不联网

## 快速开始

1. 下载 `AudioForge.exe`（单文件，不需要装 Python）
2. 需要系统里有 `ffmpeg` 和 `ffprobe` —— 没有的话界面会明确告诉你
3. 把音频拖进窗口，选格式，点「开始转换」

装 ffmpeg：

```powershell
winget install ffmpeg        # 或 choco install ffmpeg
```

## 支持的格式

| 目标 | 封装 | 编码 | 类型 |
|---|---|---|---|
| MP3 | `.mp3` | libmp3lame | 有损 |
| AAC | `.m4a` | aac | 有损 |
| Opus | `.opus` | libopus | 有损 |
| Vorbis | `.ogg` | libvorbis | 有损 |
| FLAC | `.flac` | flac | **无损** |
| ALAC | `.m4a` | alac | **无损** |
| WAV | `.wav` | pcm_s16le | **无损** |

输入不限容器 —— 凡是 `ffprobe` 认得出来的音频都行（FLAC / WAV / AIFF / M4A / MP3 / AAC / Opus / OGG / WMA / APE / WavPack …）。

**无损转无损会自动跳过**：FLAC 转 WAV 只是换了个容器还平白涨一倍，没有意义。它会标成「已跳过」并说明原因，不白跑一遍。

## 界面

六套主题：Studio Dark / Studio Light / Paper / Ink / Rosé Pine / Tokyo Night。全部按 WCAG AA（4.5:1）校验过对比度 —— 这条线在自检里盯着，改色板过不了就不让过。

右上角切中英文，选择写回 `settings.yaml`，重启还在。

## 命令行

```powershell
AudioForge.exe --version
python gui.py --probe song.flac album.mp3
```

`--probe` 打印每个文件的编码、采样率、声道、时长、体积、有损/无损。

## 配置

exe 同目录的 `settings.yaml`：

```yaml
theme: "Tokyo Night"     # 界面里切换会自动写回
lang: "zh"               # zh / en
ffmpeg_path: ""          # 留空 = 按 PATH 找
out_dir: ""              # 留空 = 源文件目录\converted
```

## 自检

```powershell
python test_app.py
```

**24 项**，`t_find_tools` 会先检查 ffmpeg 在不在、7 种目标格式需要的编码器齐不齐 —— 少一个就报「界面选项是假的」，不会让你选一个转不了的格式。

关键的几项：

- `t_convert_roundtrip` —— 造一段测试音，**真转 7 种格式**，每一种都用 `ffprobe` 回读产物，校验 codec / 时长（±0.3s）/ 无损判定
- `t_convert_no_partial_left` —— 故意用一个不存在的编码器让转换失败，断言 `.part` 和输出目录都干净
- `t_never_overwrite` —— 同名输出加序号，原文件字节不变
- `t_gui_end_to_end` —— 界面里真的导入、渲染、转换，并验证「无损转无损被跳过」
- `t_theme_contrast` —— 六套主题 × 6 个前景色全部 ≥ 4.5:1

## 为什么做成这样

**为什么不自己写解码器。** FLAC / MP3 / AAC / Opus 的编解码是几十年的成果，自己写一个只会得到一个更差的。直接用 ffmpeg —— 它是这件事的行业标准，而且每个人的系统里大概率已经有了。

**为什么探测那么啰嗦。** 一个「转码器」最恶心的失败模式是：转完了，看着成功，其实文件是坏的。所以每次转换后都回读产物。宁可多花 10 毫秒。

**为什么不覆盖源文件。** 没有「覆盖源文件」这个选项，因为一旦有了就会有人点。输出目录和源目录分开，重名加序号。

## 已知限制

- **必须有 ffmpeg**。界面会检测并明确告知，但它不会自带一份（ffmpeg 是 LGPL/GPL，再分发有合规成本，体积也大）
- **WAV 输出固定 16-bit**。要 24/32-bit 得加目标格式，目前没做
- **不处理多音轨**。视频容器里的第 2 条音轨会跳过（`-map_metadata 0` 但只取 `a:0`）
- **标签只搬运不编辑**。`title` / `artist` 会被带过去，但界面里不能改
- **界面文案的中英切换靠重建窗口**，扫描/转换中切换要等当前任务结束

## 参与

见 [CONTRIBUTING.md](CONTRIBUTING.md)。报 bug 用 [issue 模板](.github/ISSUE_TEMPLATE/bug_report.yml)。

## 支持这个项目

- ⭐ Star 一下，让更多人看到
- 🐛 [提 Issue 报 bug](https://github.com/matou1118/AudioForge/issues)
- 💰 [爱发电](https://afdian.com/a/matou1118) 支持维护

## 许可证

## 许可证

**[CC BY-NC 4.0](LICENSE) — 署名（Matou1118）· 禁商用**

- **可以**改、可以二次开发、可以做成自己的版本
- **必须**署名原作者 Matou1118，保留许可声明，注明是否修改
- **不能**商用 —— 不收费的修改版随便用；收费、打包进付费产品、接广告都不行
- 拿不准就[开个 issue 问](https://github.com/matou1118/AudioForge/issues)

本项目不包含任何音频编解码器 —— ffmpeg 由你自己安装，不在这里分发。
