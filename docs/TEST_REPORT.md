# Test report

## Automated (pytest): 49 passed, 1 skipped

Run on Linux (Python 3.13, the same pinned PySide6/rawpy/Pillow). CI runs the same suite on `windows-latest` with Python 3.12.

| Area | Tests |
|---|---|
| Validation | supported extensions (case-insensitive), header/size checks, renamed JPEG, truncated file, missing file, Unicode + spaces in paths |
| Folder scanning | flat and recursive |
| Queue | duplicate entries ignored (including `.\` path variants); GUI add/remove/clear; unsupported files ignored |
| Output naming | `.jpg` extension, prefix/suffix, preserve folder structure |
| Collisions | skip (default) / unique `_1`, `_2` / overwrite / ask (per-job override); same file name from different folders never collide, under every policy |
| Atomic writes | an invalid temp output is removed and no final file is created |
| Conversion | single file, output dimensions, valid JPEG signature, Pillow opens it, source bytes unchanged |
| Resizing | percent, max W×H, aspect ratio kept, no upscale, invalid values rejected |
| JPEG quality | higher quality gives a larger file; quality 0 rejected |
| Metadata | Make, Model, DateTimeOriginal, ISO, FNumber, LensModel copied from an Exif sub-IFD; Orientation reset to 1; sRGB ICC embedded; both can be turned off |
| Batch | 25 files; failure isolation (1 and 3 workers); MemoryError isolation; cancellation mid-batch; unwritable output folder |
| Real LibRaw | a corrupted ARW is rejected cleanly by the real decoder, and no output is left behind |
| GUI (offscreen) | a 30-file background batch completes while the Qt event loop keeps ticking (responsiveness); cancel from the GUI |
| Packaged build | the PyInstaller bundle's `--self-test` passes (LibRaw loads, corrupt file rejected, Unicode-path pipeline, main window builds) |

## Skipped / requires manual verification

* **Real Sony ARW conversion.** This environment had no network access to a sample ARW, so `test_real_arw_conversion` was **skipped**.
  To run it: `set SONY_ARW_SAMPLE=C:\path\DSC01234.ARW` and then `python -m pytest`. The packaged exe self-test also uses this variable.
  No successful real-ARW conversion is claimed here.
* **Visual check of colour rendering** against a camera JPEG.
* **Installing on a clean Windows 10/11 machine** and using the real file dialogs and drag-and-drop by hand. CI does a silent install → self-test → uninstall on a fresh `windows-latest` VM with Python removed from PATH, but that is not the same as testing on a real desktop by hand.
