# Changelog

All notable changes to AudioForge are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-09-28

First public release.

### Added

- **Batch audit**: drop a folder in (recurses the whole tree) or run
  `AudioForge.exe --audit <dir>`. You get a table grouping files into
  convertible / DRM-encrypted / damaged / empty, with counts and sizes. It answers
  "how much of this pile is actually unusable". The status bar shows the same
  summary; hover it for per-file detail.
- **Honest DRM detection**: KGM / VPR / QMC / NCM are caught by magic number
  *before* ffprobe runs, and grouped as "DRM-encrypted". Nothing is unpacked.

### Fixed

- **White screen**: `__init__` called `set_updates(False)` (originally for
  "don't repaint while converting"), so every widget was built but never painted
  and the window came up blank. Removing it took the colour count from 1 to 181.
  The self-test never caught this - it inspects widget attributes, not pixels.
- **Misleading error text**: telling the user a perfectly intact encrypted file
  might be "damaged or incomplete" makes them re-download it.
- **ffprobe's English errors leaked to the UI**: `Invalid data found when
  processing input` says neither what's broken nor what to try. Now translated by
  file header (truncated / not audio / no permission / broken MP4 index / empty).
- **Folder drop only went one level deep**: files in subdirectories were silently
  missed. Now uses `rglob`.
- **The packaged exe now reads settings.yaml from beside itself** rather than the
  read-only copy in `_MEIPASS` - otherwise user config edits did nothing.
- **requirements.txt was missing PyYAML**: without it `import yaml` failed, got
  swallowed by the except, and silently returned `{}` - presenting as "config
  changes do nothing".
- **Tests wrote to the user's settings.yaml**, and the unescaped Windows path made
  the YAML unparseable, so the exe raised while reading config at startup - which
  is *another* white window.
- **spec had empty hiddenimports**: PySide6.QtCore/QtGui/QtWidgets weren't listed,
  so the Qt platform plugin may not be bundled.

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
