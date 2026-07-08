# First Frame Extractor

A minimal desktop app (macOS + Windows) that extracts the **first frame** of a video.
Drag an MP4/MOV video onto the window (or click **Browse…**): the first frame is
**copied to the clipboard** and **saved to your Downloads folder**. Lossless PNG by
default, or 100% JPEG when the checkbox is ticked.

The executables are **standalone**: they bundle the Python interpreter, PySide6 and a
static `ffmpeg` binary. Nothing to install.

## Download

Grab the latest build from the **[Releases](../../releases)** page:

- **macOS** — `FirstFrameExtractor-macos.dmg` → open the `.dmg` and **drag the app into
  your Applications folder**. Because the app is unsigned, macOS (Gatekeeper) will block
  it on first launch with *"Apple could not verify … is free of malware"*. To fix it once:

  ```bash
  xattr -dr com.apple.quarantine "/Applications/First Frame Extractor.app"
  ```

  Open the **Terminal** app (Cmd-Space → type `Terminal`), paste the line above, press
  Enter, then open the app normally. The same instructions ship inside the `.dmg` as
  **`Open if blocked.txt`**.

  *No Terminal?* Double-click the app, then go to **System Settings → Privacy & Security**,
  scroll down and click **Open Anyway**.
- **Windows** — `FirstFrameExtractor-windows.zip` → extract and run `FirstFrameExtractor.exe`.
  SmartScreen will warn you: choose **More info → Run anyway**.

> ⚠️ The binaries are **unsigned** (removing the warnings entirely requires paid Apple
> notarization / a code-signing certificate), so security prompts on first launch are
> expected.

## Supported formats

`.mp4`, `.mov`, `.m4v`, `.qt`

## Build from source

Requirements: Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run from source
python main.py

# Build the standalone executable
pip install pyinstaller
pyinstaller --noconfirm FirstFrameExtractor.spec
# output in dist/
```

## CI / distribution

The [`.github/workflows/build.yml`](.github/workflows/build.yml) workflow builds the
executables automatically on **macOS** and **Windows** runners on every push to `main`.
Pushing a `v*` tag (e.g. `git tag v1.0.0 && git push --tags`) attaches both archives to a
**Release**.

## Stack

- [PySide6](https://doc.qt.io/qtforpython/) — GUI
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) — bundled static ffmpeg binary
- [PyInstaller](https://pyinstaller.org/) — standalone packaging
