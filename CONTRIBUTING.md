# 参与贡献 / Contributing

[English](CONTRIBUTING.en.md)

先跑一遍自检，它是最快的反馈方式：

```powershell
python test_app.py
```

## 环境

```powershell
winget install ffmpeg      # 必需，没有它测试直接退出
pip install -r requirements.txt
```

## 提 issue 之前

`python test_app.py` 的输出贴上来 —— 大部分问题在这一步就能定位。同时说明：

- 你的 ffmpeg 版本（`ffmpeg -version` 第一行）
- 输入文件的**格式和来源类型**（自己录的 / 买的 / 转出来的）
- 你选了哪个目标格式

## 改代码

- **先加测试。** 转码相关的 bug 只有真转一遍才抓得到，`t_convert_roundtrip` 是模板：造测试音 → 转 →
  `ffprobe` 回读 → 校验。
- **不要在自检里留下临时目录。** 用 `tmpdir()`，它在结束时统一清。
- **改配色要过 `t_theme_contrast`。** 那是硬门槛，不是建议。
- **加界面文案要同时加翻译。** `t_i18n_complete` 会查 gui.py 里每个 `T("中文")` 都有对应条目。
- **注释写「为什么」，不写「是什么」。** 比如为什么 GIL 切换间隔是 5ms、为什么输出要写 `.part`。

## 提交前

```powershell
python test_app.py         # 必须 ALL OK
cmd /c build.bat           # 打包，确认 exe 能起来
```

`build.bat` 会先跑自检，不过就停。

## 不要做的事

- **不要在代码里塞 ffmpeg 路径。** 走 `ffmpeg_path()`，它会按 PATH / exe 同目录 / 常见位置找。
- **不要覆盖源文件。** 写输出永远用 `unique_out()`。
- **不要加「转换完删除源文件」这种功能。** 同理于 DevCleaner 为什么没有「永久删除」。
- **不要把 `.part` 去掉。** 失败时它是你唯一的保护。

## Code of Conduct

见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
