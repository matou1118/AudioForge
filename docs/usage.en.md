# Usage

[中文](usage.md) · [Screenshots](Screenshots.en.md)

## What it does

Converts audio files from one format to another. **That is the entire job.**

It does not: cut tracks, edit tags, download music, merge files, or act as a player.

## Prerequisite: ffmpeg

AudioForge **contains no codecs**. It calls the ffmpeg on your system.

```powershell
winget install ffmpeg
# or
choco install ffmpeg
```

Verify:

```powershell
ffmpeg -version
ffprobe -version
```

The status label in the UI reads `ffmpeg ready` (green) or `ffmpeg not found` (red). If it's missing, point
`ffmpeg_path` in `settings.yaml` at the install directory.

## Importing files

Three ways:

1. **Drag** — drop files or a whole folder into the window
2. **Click** — click the dashed box, get a file picker
3. **CLI** — `python gui.py --probe <file>`

Every import runs `ffprobe` and shows codec, sample rate, channels, bitrate, duration and a
lossless/lossy verdict.

Files that fail to probe (empty, random bytes, a text file renamed `.mp3`) show the specific reason and
are **not** converted.

## Picking a target

Seven options in the dropdown. Lossless ones are tagged 无损 / lossless.

Once you've chosen a lossless target, any **lossless** sources in your selection are **skipped** and marked
*skipped* — turning FLAC into WAV just swaps the container and doubles the size. Lossy sources in the same
batch still convert.

## Bitrate

Applies to lossy targets only:

| Preset | Argument | Effective |
|---|---|---|
| small | `-b:a 128k` | 128 kbps |
| medium | preset | MP3 V2 (~190k), AAC 192k, Opus 160k, Vorbis q5 |
| high | `-b:a 320k` | 320 kbps |

Lossless targets ignore it (FLAC uses its own `-compression_level 5`).

## Output folder

Default: `converted\` next to the source file. Use "Choose output folder" to change it; the choice is
written back to `settings.yaml`.

**Same names are numbered**: `song.mp3` exists → `song (2).mp3` → `song (3).mp3`. Sources are never
touched.

## Converting

Press Start. You can press Cancel at any time — finished files are kept, the in-flight one is killed and
its `.part` removed.

If anything failed, a dialog lists the first ten reasons.

## Some entries stay English when the UI is Chinese

The language switch rebuilds the window, so **switching during a conversion waits for the task to finish.**

File-level data (names, paths, codec names) isn't translated — it's data, not copy.

## Command line

```powershell
AudioForge.exe --version        # print version
AudioForge.exe --help           # usage
python gui.py --probe a.flac    # inspect only
```

`--probe` output:

```
song.flac	flac	44100Hz	2ch	245.3s	38.12 MB	lossless
track.mp3	mp3	44100Hz	2ch	180.0s	5.40 MB	lossy
```

## Troubleshooting

**The UI says "ffmpeg not found" but it works in my terminal**
A GUI process inherits the system PATH, not your terminal's — Chocolatey shims are a common cause. Put the
absolute path in `settings.yaml`:

```yaml
ffmpeg_path: "C:/ffmpeg/bin"
```

**Every conversion fails with `Error opening output files: Invalid argument`**
Your ffmpeg is too old for that encoder. Check with `ffmpeg -encoders | findstr libopus`.

**The output is bigger than the source**
Expected. FLAC → WAV always grows; only lossy → lossless can shrink. The UI says "grows after converting".

**The source is a video and only one track came out**
That's `a:0`. Multi-track extraction isn't implemented.

**Chinese filenames come out garbled**
They won't. On Windows the path is passed to ffmpeg as a list argument, never through a shell, and no
encoding conversion happens.
