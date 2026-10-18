# Sony RAW to JPG Converter

A Windows 10/11 (64-bit) desktop app that converts Sony Alpha **.ARW** RAW photos into high-quality JPGs.
You can convert hundreds of files in one batch. Everything runs on your own computer: no internet, no account, no uploads.

## Download and install (no Python needed)

1. Open the repository's **Actions** tab → **Build Windows app** → the latest successful run.
2. Download one of these:
   * **SonyRawConverter-Setup** – a zip containing `SonyRawConverter-Setup-1.0.0.exe`. Double-click it to install. You don't need admin rights. You get a Start Menu entry, an optional desktop shortcut and an uninstaller in *Settings → Apps*.
   * **SonyRawConverter-portable** – unzip it anywhere and double-click `SonyRawConverter.exe`. No installation.
3. If you push a tag such as `v1.0.0`, the same files are attached to a GitHub Release.

> Windows SmartScreen may say "Windows protected your PC" because the app isn't code-signed.
> Click **More info → Run anyway**. Signing it needs a paid code-signing certificate (see *Future work*).

## Using the app

1. **Add Photos…** (Ctrl+O) or **Add Folder…** (Ctrl+Shift+O). You can also drag files or folders onto the window.
   Ctrl/Shift multi-select works in the file dialog. A file that is already in the queue isn't added again.
2. Choose an **output folder**. It's created if it doesn't exist. The default is `Pictures\Converted JPG`.
3. Adjust the settings if you want to. The defaults are good:
   * **JPEG quality** 1–100 (default 95). This sets compression and file size only. It can't recover detail that was lost during RAW development.
   * **Chroma** 4:4:4 (default, full colour detail) / 4:2:2 / 4:2:0 (smallest files).
   * **Size**: original (default), percentage, or fit-within W×H. The aspect ratio is always kept, and images are never enlarged.
   * **If file exists**: *Skip* (default), *Save with a new name* (`DSC01234_1.jpg`), *Ask me*, or *Overwrite*.
     Two sources with the same name (for example, from two memory cards) never overwrite each other.
   * **RAW development**: white balance (as shot / auto / daylight), exposure −2…+3 EV, highlight clip/blend, sharpening, auto brightness.
   * **Settings** (top right): include subfolders, parallel conversions (1–4), open the log folder.
4. Click **Convert to JPG** (Ctrl+Enter). You can follow progress for each file and **Cancel** at any time.
   If one file fails, the rest of the batch keeps going.
5. **Open Output Folder** shows the results in Explorer.

Your original .ARW files are only ever read. They are never modified, renamed or deleted.

## How conversion works

Each file goes through these steps: validate the file (extension, size, TIFF/ARW header) → decode with LibRaw (AHD demosaic, camera white balance, sRGB output, camera orientation applied) → optional resize (Lanczos) and sharpening → JPEG encode with an sRGB ICC profile and EXIF → write to a hidden `.partial` temp file in the destination → check that the result is a real JPEG of the expected size → atomically rename it to the final name.
A file is only marked **Completed** after that check passes. If a conversion is interrupted, no half-written JPG is left behind.

### Metadata

The app copies these fields: camera make/model, capture date/time (including sub-seconds and time-zone offsets), exposure time, aperture, ISO, exposure program/bias, metering, flash, focal length (and 35 mm equivalent), lens make/model/specification, white balance, body serial, artist and copyright.
The Orientation tag is set to 1 because the pixels are already rotated.
Sony MakerNotes, RAW strip/tile data and GPS are **not** copied, because copying them blindly can produce invalid JPEGs. (GPS could be added later if you want it.)

### Colour

The JPGs are rendered by **LibRaw** (through rawpy), not by Sony's own engine. Colours and contrast may differ slightly from Sony Imaging Edge or the camera's built-in JPEGs. The output is always sRGB with an embedded sRGB ICC profile.

## Logs and settings

* Logs: `%LOCALAPPDATA%\SonyRawConverter\logs\converter.log`. The logs rotate (3 × 2 MB) and record only file names, not full paths.
* Settings: saved per user in the registry (`HKCU\Software\Starcima\Sony RAW to JPG Converter`).
* There is no telemetry and no network access.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Could not read RAW data … Unsupported file format" | The file is damaged, or it comes from a camera newer than LibRaw 0.21. Try again with a newer app build. |
| "Not enough memory" | Set **Parallel conversions** to 1 in Settings, then close other applications. |
| A file shows **Skipped** | A JPG with that name already exists. Change **If file exists**. |
| The output folder isn't writable | Choose a folder inside your user profile, such as Pictures or Desktop. |
| SmartScreen warning | Click **More info → Run anyway** (the app is unsigned). |
| You need diagnostics | Open Settings → **Open log folder**, or run `SonyRawConverter.exe --self-test C:\temp\st` and read `self_test.json`. |

## Building from source (Windows)

```powershell
# Requires Python 3.12 x64 and Inno Setup 6 (winget install JRSoftware.InnoSetup)
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

The script creates `.venv`, installs the pinned dependencies, runs the tests, builds `dist\SonyRawConverter\SonyRawConverter.exe` with PyInstaller (one-folder, no console window), self-tests the packaged exe, and then builds `installer_output\SonyRawConverter-Setup-<version>.exe`.

For development: `pip install -r requirements-dev.txt`, `python -m pytest`, `python main.py`.
To release a new version, change `APP_VERSION` in `src/version.py` (and `packaging/version_info.txt`), then push a tag `vX.Y.Z`.

### Project layout

```
main.py                 entry point
src/bootstrap.py        logging, Qt start-up, --self-test
src/app/                GUI: main_window.py, theme.py, settings.py
src/core/               engine (no Qt): raw_decoder, converter, batch_processor,
                        output_manager, metadata, validation, errors
src/workers/            QThread / QThreadPool workers
src/models/             dataclasses and enums
tests/                  pytest suite (unit + offscreen GUI + optional real-ARW integration)
packaging/              PyInstaller spec, version info, Inno Setup script, build script
.github/workflows/      Windows CI: test → package → self-test → installer → install/uninstall test
```

### Pinned stack

Python 3.12 · PySide6 6.9.2 · rawpy 0.25.1 (LibRaw 0.21.4) · Pillow 11.3.0 · numpy 2.3.3 · PyInstaller 6.16.0 · Inno Setup 6.
All of these ship Windows x64 wheels for CPython 3.12.

## Future work

* Code-sign the exe and installer to remove the SmartScreen warning.
* Optional GPS copy, and an Adobe RGB output option (this needs a redistributable ICC profile).
