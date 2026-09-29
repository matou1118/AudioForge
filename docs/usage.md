# 使用说明 / Usage

[English](usage.en.md) · [截图](Screenshots.md)

## 它做什么

把音频文件从一种格式转成另一种。**只有这一件事。**

不做：不切歌、不改标签、不抓取在线音乐、不合并、不做播放器。

## 前置条件：ffmpeg

AudioForge **不含任何编解码器**，它调用你系统里的 ffmpeg。

```powershell
winget install ffmpeg
# 或
choco install ffmpeg
```

验证：

```powershell
ffmpeg -version
ffprobe -version
```

界面的状态标签会显示 `ffmpeg 已就绪`（绿）或 `找不到 ffmpeg`（红）。找不到时按 `ffmpeg_path` 配置走。

## 导入文件

三种方式：

1. **拖拽** —— 把文件或整个文件夹拖进窗口
2. **点击** —— 点虚线框，弹文件选择框
3. **命令行** —— `python gui.py --probe <文件>`

每次导入都跑一次 `ffprobe`，显示：编码、采样率、声道、码率、时长、有损/无损。

探测失败的（空文件、随机字节、文本改名成 `.mp3`）会显示具体原因，**不转**。

## 选目标格式

下拉框里 7 个选项，有损的标 `MP3 / AAC / Opus / Vorbis`，无损的带「无损」标记。

选好之后，如果你勾选的文件里有无损的，又选了无损目标，**会被跳过**并标「已跳过」—— FLAC 转 WAV 只是
换容器还平白涨一倍。混合列表里，有损的照转。

## 码率

只对有损目标生效：

| 档 | 参数 | 实际 |
|---|---|---|
| 小 | `-b:a 128k` | 128 kbps |
| 中 | 预设 | MP3 V2（~190k）、AAC 192k、Opus 160k、Vorbis q5 |
| 高 | `-b:a 320k` | 320 kbps |

无损目标忽略这个设置（FLAC 有自己的 `-compression_level 5`）。

## 输出目录

默认：源文件所在目录下的 `converted\`。点「选择输出目录」改，配置写回 `settings.yaml`。

**同名自动加序号**：`song.mp3` 已存在 → `song (2).mp3` → `song (3).mp3`。源文件永远不动。

## 转换

点「开始转换」。转换期间可以随时按「取消」——已完成的保留，正在转的杀掉并清掉 `.part`。

转换完如果有任何失败，会弹窗列出前 10 条失败原因。

## 中文界面看不到某些英文

界面和条目说明的中英切换靠重建窗口。**转换/探测进行中切换会等当前任务结束才生效。**

条目级信息（文件名、路径、编码名）是数据不是文案，本来就不翻译。

## 批量体检

拖一个**文件夹**进来（会递归整个目录树），或者：

```powershell
python gui.py --audit D:\Music
```

给出一张表，回答「这堆文件里有多少是废的」：

```
共 7 个文件，607.15 KB

== 能转  3 个  603.16 KB
   ok1.wav  172.34 KB
   ok2.wav  344.61 KB
   ... 还有 1 个

== DRM 加密（解不开）  1 个  3.95 KB
   enc.kgm.flac  3.95 KB   (KGM（KuGou 加密格式），带版权保护，解不开)

== 损坏 / 不是音频  2 个  49 B
   broken.flac  44 B   (是 FLAC，但文件被截断或头信息损坏)
   readme.txt  5 B     (文件内容 ffprobe 认不出来：可能已损坏，或不是音频文件)

== 空文件  1 个  0 B
   empty.mp3  0 B   (空文件（0 字节）)
```

界面底部也会显示汇总：能转 N · DRM N · 损坏 N · 空 N，鼠标悬停看明细。

### 关于 DRM 加密文件

本工具**不破解版权保护**。KGM / VPR / QMC / NCM 这类加密文件会被**如实识别并单独归类**，
而不是报「文件损坏」—— 说它损坏是误导，文件是好的，只是有 DRM，解不开。

要能直接播放的版本，请从提供方购买无 DRM 的格式（QQ 音乐 / 酷狗的部分专辑购买后
本身即无 DRM；独立音乐人可在 Bandcamp 直接买 FLAC）。

识别 DRM 只是为了**把话说准**，不做任何解包。

---

## 命令行

```powershell
AudioForge.exe --version        # 打印版本
AudioForge.exe --help           # 用法
python gui.py --probe a.flac    # 只探测不转换
```

`--probe` 输出：

```
song.flac	flac	44100Hz	2ch	245.3s	38.12 MB	lossless
track.mp3	mp3	44100Hz	2ch	180.0s	5.40 MB	lossy
```

## 排障

**界面显示「找不到 ffmpeg」**
`ffmpeg -version` 在命令行能跑，但界面找不到 —— 可能是 GUI 进程的 PATH 和你终端不同（从开始菜单启动
的程序会继承系统 PATH，不含 Chocolatey 的 shims）。在 `settings.yaml` 里填绝对路径：

```yaml
ffmpeg_path: "C:/ffmpeg/bin"
```

**转换全部失败，报 `Error opening output files: Invalid argument`**
你的 ffmpeg 太老，不支持该格式的编码器。`ffmpeg -encoders | findstr libopus` 确认一下。

**输出比源文件还大**
正常。FLAC 转 WAV 一定变大，无损转有损才可能变小。界面会显示「转换后变大」。

**源是视频文件，只转了第一条音轨**
`a:0`。多音轨提取没做。

**中文文件名乱码**
不会。Windows 上路径以列表参数传给 ffmpeg，不经 shell，也不做编码转换。
