# Changelog

All notable changes to AudioForge are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-09-28

First public release.

### Added

- **批量体检**：拖文件夹进来（递归整个目录树），或
  \AudioForge.exe --audit <目录>\uff0c输出分类表：能转 / DRM 加密 /
  损坏 / 空文件，各多少个、多大。回答的是「这堆
  文件里有多少是废的」。界面底栏也显示汇总，悬停看逐条明细。
- **DRM 文件如实识别**：KGM / VPR / QMC / NCM 会在调 ffprobe **之前**
  按魔数拦下，归为「DRM 加密（解不开）」。本工具不做任何解包。

### Fixed

- **白屏**：构造期调了 \set_updates(False)\uff08原本是给「转换时不重绘」用的），
  控件全部建好但永远不绘制，窗口起来一片空白。删掉后色彩数从 1 变成 181。
- **报错文案误导**：对着完好的加密文件说「可能损坏或不完整」，用户会以为下载坏了。
- **拖文件夹只取一层**：子目录里的文件漏了，改成 glob\ 递归。
- **打包后优先读 exe 同目录的 settings.yaml**，不是 _MEIPASS 里那份只读副本。
- **requirements.txt 漏了 PyYAML**：缺它时 \import yaml\ 失败被 except 吞掉，静默返回 \{}\uff0c
  表现是「配置怎么改都不生效」。
- **自检污染用户配置**：端到端测试直接写真实的 settings.yaml，未转义的 Windows 路径还让 YAML 解析失败——
  又一个白窗口。

### Design decisions
- **ffmpeg is a dependency, not a bundled blob.** It is LGPL/GPL, and redistributing it adds compliance
  cost and ~80 MB. The app detects it and tells you how to get it.
- **The output container is declared explicitly with `-f`.** Intermediate files are named `song.mp3.part`,
  and ffmpeg picks the muxer from the extension — `.part` is meaningless to it, so all seven formats
  failed with `Error opening output files: Invalid argument` until `-f` was added.
- **Palette contrast is a test, not a review comment.** Two palettes shipped below AA (Paper's tertiary
  text at 3.13:1, Studio Dark's accent at 4.24:1) and were corrected. `fg3` is mixed at 0.68 rather than
  0.52 for the same reason.
- **No "overwrite source" option.** It would eventually be clicked by someone.

### Known limits

- ffmpeg must be installed separately.
- WAV output is 16-bit only.
- Single audio track; a second stream in a video container is ignored.
- Tags are copied through but not editable in the UI.

[0.1.0]: https://github.com/matou1118/AudioForge/releases/tag/v0.1.0
