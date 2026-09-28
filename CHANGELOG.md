# Changelog

All notable changes to AudioForge are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-09-28

First public release.

### Added

- **7 target formats** — MP3, AAC, Opus, Vorbis (lossy) and FLAC, ALAC, WAV (lossless). The self-test
  checks that each one's encoder actually exists in your ffmpeg, so the UI never offers a format it can't
  produce.
- **Drag-and-drop or browse** for input, with per-file `ffprobe` inspection: codec, sample rate, channels,
  duration, bitrate, and a lossless/lossy verdict.
- **Real transcoding via ffmpeg**, with progress reporting and a working Cancel button.
- **Sources are never modified.** Output goes to a separate folder; same-name files get `(2)`, `(3)`.
- **Verified round-trip** — every output is read back with `ffprobe` and checked for codec, duration and
  lossless-ness.
- **Clean failure** — output is written to `.part` and only renamed on success, so a failed run leaves
  nothing behind.
- **Lossless → lossless is skipped** with a stated reason instead of burning CPU.
- **6 colour themes** (Studio Dark / Studio Light / Paper / Ink / Rosé Pine / Tokyo Night), all verified
  against WCAG AA (4.5:1).
- **Chinese and English UI**, switchable, persisted to `settings.yaml`.
- **`--probe` CLI** for inspecting files without the GUI.
- **24 self-tests**, run in CI on Python 3.10–3.13.

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
