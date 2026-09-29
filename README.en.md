# AudioForge

**Local audio transcoding. Your source files are never touched — output goes to its own folder.**

[![CI](https://github.com/matou1118/AudioForge/actions/workflows/ci.yml/badge.svg)](https://github.com/matou1118/AudioForge/actions/workflows/ci.yml)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-9ece6a.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-7aa2f7.svg)

[中文](README.md) · [Usage](docs/usage.en.md) · [Screenshots](docs/Screenshots.en.md) · [Changelog](CHANGELOG.en.md)

---

Drop in a pile of audio, pick a target format, press one button. **No format invented, no settings to
configure, no account to create.**

- **Sources are read-only** — output always lands in a separate folder; same-name files get `(2)`, `(3)`
- **Probe before transcoding** — no duration or sample rate, no conversion. No blind guesses.
- **Verified round-trip** — every output is read back with `ffprobe` and checked for codec, duration and
  lossless-ness
- **Failures leave nothing behind** — output is written to `.part` first and only renamed on success
- **6 colour themes** and **two languages**, entirely offline

## Quick start

1. Download `AudioForge.exe` (single file, no Python needed)
2. Make sure `ffmpeg` and `ffprobe` are on your system — if they aren't, the UI says so plainly
3. Drop audio into the window, choose a format, press Start

Installing ffmpeg:

```powershell
winget install ffmpeg        # or: choco install ffmpeg
```

## Supported targets

| Target | Container | Codec | Type |
|---|---|---|---|
| MP3 | `.mp3` | libmp3lame | lossy |
| AAC | `.m4a` | aac | lossy |
| Opus | `.opus` | libopus | lossy |
| Vorbis | `.ogg` | libvorbis | lossy |
| FLAC | `.flac` | flac | **lossless** |
| ALAC | `.m4a` | alac | **lossless** |
| WAV | `.wav` | pcm_s16le | **lossless** |

Input containers are not restricted — anything `ffprobe` recognises works (FLAC / WAV / AIFF / M4A / MP3 /
AAC / Opus / OGG / WMA / APE / WavPack …).

**Lossless to lossless is skipped automatically.** Turning FLAC into WAV just swaps the container and doubles
the size. It's marked *skipped* with the reason, rather than burning CPU for nothing.

## Interface

Six themes: Studio Dark / Studio Light / Paper / Ink / Rosé Pine / Tokyo Night. Every foreground colour is
checked against WCAG AA (4.5:1) — that threshold is enforced by the self-test, so a palette change that
breaks it fails the build.

Chinese and English, switchable top-right, written back to `settings.yaml`, survives a restart.

## Command line

```powershell
AudioForge.exe --version
python gui.py --probe song.flac album.mp3
```

`--probe` prints codec, sample rate, channels, duration, size and lossless/lossy for each file.

## Configuration

`settings.yaml` next to the exe:

```yaml
theme: "Tokyo Night"     # written automatically when you switch in the UI
lang: "en"               # zh / en
ffmpeg_path: ""          # empty = search PATH
out_dir: ""              # empty = <source folder>\converted
```

## Self-test

```powershell
python test_app.py
```

**24 checks.** `t_find_tools` verifies ffmpeg is present and that all seven target formats have their
encoders — a missing one is reported as "this UI option would be a lie", so you're never offered a format
that can't be produced.

The important ones:

- `t_convert_roundtrip` — generates a test tone, **really transcodes all seven formats**, reads each output
  back with `ffprobe`, and checks codec / duration (±0.3 s) / lossless detection
- `t_convert_no_partial_left` — deliberately fails with a nonexistent encoder and asserts the output
  directory is left clean
- `t_never_overwrite` — same-name outputs get numbered, source bytes unchanged
- `t_gui_end_to_end` — imports, renders and converts through the real UI, and verifies that
  lossless-to-lossless is skipped
- `t_theme_contrast` — six themes × six foreground colours, all ≥ 4.5:1

## Why it's built this way

**Why not write our own codecs.** FLAC / MP3 / AAC / Opus are decades of work. Anything hand-rolled would
simply be worse. We call ffmpeg — it's the industry standard for this and most machines already have it.

**Why probing is so insistent.** The worst failure mode of a "transcoder" is finishing successfully and
producing a broken file. So every output is read back. Ten milliseconds is cheap insurance.

**Why there's no "overwrite source" option.** The moment that option exists, someone will click it. The
output folder is separate from the source folder and same names get numbered.

## Known limits

- **ffmpeg is required.** The UI detects it and tells you plainly, but it does not bundle a copy (ffmpeg is
  LGPL/GPL, redistributing it has compliance cost and it's large)
- **WAV output is fixed at 16-bit.** 24/32-bit would need more targets; not implemented
- **Single audio track only.** A second audio stream in a video container is ignored
- **Tags are carried, not edited.** `title` / `artist` survive the trip but you can't edit them here
- **Switching language rebuilds the window**, so it waits for the running task to finish

## Contributing

See [CONTRIBUTING.en.md](CONTRIBUTING.en.md). Bugs go through the
[issue template](.github/ISSUE_TEMPLATE/bug_report.yml).

## Support this project

- ⭐ Star it so more people find it
- 🐛 [Open an issue](https://github.com/matou1118/AudioForge/issues) for bugs
- 💰 [Afdian](https://afdian.com/a/matou1118) to support maintenance

## License

## License

**[CC BY-NC 4.0](LICENSE) — attribution (Matou1118), non-commercial**

- **You may** modify it, build on it, ship your own version
- **You must** credit Matou1118, keep the licence notice, and say whether you changed it
- **You may not** use it commercially - a free fork is fine; selling it, bundling it
  into a paid product, or monetising it with ads is not
- If unsure, [open an issue](https://github.com/matou1118/AudioForge/issues) and ask

This project ships no audio codecs - ffmpeg is yours to install and is not redistributed here.
here.
