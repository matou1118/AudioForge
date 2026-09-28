# Security Policy

[中文](SECURITY.md)

## Supported versions

| Version | Fixed |
|---|---|
| 0.1.0 | ✅ |

## Reporting a vulnerability

**Don't open a public issue.** Use GitHub's
[private vulnerability reporting](https://github.com/matou1118/AudioForge/security/advisories/new).

## What AudioForge does not do

These are design constraints, not unfixed bugs:

- **Never writes to sources.** Transcoded output always goes through `unique_out()` into a separate
  directory with numbered collisions. No code path overwrites an input.
- **No network access.** No telemetry, no update check, no crash reporting. `ffprobe` and `ffmpeg` are
  local subprocesses.
- **Never executes anything from an input file.** Inputs are passed to ffmpeg purely as the `-i` argument,
  outside any shell.
- **No permanent deletion.** There's no "delete source after converting", and there won't be.
- **Ships no codecs.** You install ffmpeg; this project redistributes nothing and therefore isn't
  responsible for its vulnerabilities.

## Dependencies

- **ffmpeg / ffprobe** — installed by you, your choice of version. When parsing untrusted files, treat them
  as data only; avoid batch-processing files of unknown provenance on a machine holding sensitive data.
- **PySide6** — interface only; it never touches audio data.

## Trust boundary

The only place untrusted input is handled is `probe()`: it hands the file path to `ffprobe` as a list
argument, never through a shell, so quotes and spaces in paths can't cause command injection. The
**output directory**, though, is yours to confirm — the default is `converted` next to the source.
