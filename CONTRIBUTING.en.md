# Contributing

[中文](CONTRIBUTING.md)

Run the self-test first — it's the fastest feedback loop there is:

```powershell
python test_app.py
```

## Setup

```powershell
winget install ffmpeg      # required; the test suite exits without it
pip install -r requirements.txt
```

## Before opening an issue

Paste the output of `python test_app.py` — most problems are identifiable right there. Also include:

- Your ffmpeg version (first line of `ffmpeg -version`)
- The input file's **format and provenance** (self-recorded / purchased / converted)
- Which target format you picked

## Changing code

- **Write the test first.** Transcoding bugs are only catchable by actually transcoding.
  `t_convert_roundtrip` is the template: make a tone → convert → read back with `ffprobe` → assert.
- **Don't leave temp directories behind.** Use `tmpdir()`; it's swept at the end.
- **Palette changes must pass `t_theme_contrast`.** That's a hard gate, not advice.
- **New UI strings need a translation.** `t_i18n_complete` checks that every `T("中文")` in gui.py has an
  entry in `lang.py`.
- **Comment the *why*, not the *what*.** Why the GIL switch interval is 5 ms, why output goes to `.part`.

## Before you push

```powershell
python test_app.py         # must be ALL OK
cmd /c build.bat           # package, and confirm the exe starts
```

`build.bat` runs the self-test first and stops if it fails.

## Please don't

- **Don't hardcode an ffmpeg path.** Go through `ffmpeg_path()`; it searches PATH, the exe folder and
  common install locations.
- **Don't overwrite sources.** Always write via `unique_out()`.
- **Don't add a "delete source after converting" feature.** Same reason DevCleaner has no permanent delete.
- **Don't drop the `.part` file.** On failure it's the only thing standing between you and a truncated
  output.

## Code of Conduct

See [CODE_OF_CONDUCT.en.md](CODE_OF_CONDUCT.en.md).
