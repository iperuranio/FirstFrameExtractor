#!/usr/bin/env python3
"""First Frame Extractor

Drag & drop (or pick) an MP4/MOV video: the first frame is extracted
immediately, copied to the clipboard and saved to the Downloads folder.
Lossless PNG by default, 100% JPEG if the checkbox is ticked.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QImage, QGuiApplication, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".qt"}
DOWNLOADS = Path.home() / "Downloads"


def find_ffmpeg() -> str:
    """Find ffmpeg: first the static binary bundled in the package (standalone
    build), then the PATH or the usual Homebrew locations (running from source)."""
    # 1. Static ffmpeg bundled via imageio-ffmpeg (standalone executable)
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:  # noqa: BLE001
        pass
    # 2. PATH / Homebrew (running from source)
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if Path(candidate).exists():
            return candidate
    return "ffmpeg"


FFMPEG = find_ffmpeg()


# --- Frame-accurate duration + timecode ------------------------------------

# Rounded fps (as printed by ffmpeg) -> exact rational, so "seconds" is precise.
_FPS_RATIONALS = {
    23.98: 24000 / 1001,
    29.97: 30000 / 1001,
    47.95: 48000 / 1001,
    59.94: 60000 / 1001,
    119.88: 120000 / 1001,
}


def exact_fps(fps: float) -> float:
    """Map a rounded fps (e.g. 23.98) to its exact rational (24000/1001)."""
    for approx, real in _FPS_RATIONALS.items():
        if abs(fps - approx) < 0.03:
            return real
    return fps


def frames_to_tc(frames: int, fps: float) -> str:
    """Convert a frame count to a non-drop timecode HH:MM:SS:FF."""
    n = max(1, int(round(fps)))
    secs, ff = divmod(frames, n)
    return f"{secs // 3600:02d}:{secs // 60 % 60:02d}:{secs % 60:02d}:{ff:02d}"


def tc_to_frames(tc: str, fps: float) -> int:
    """Convert a HH:MM:SS:FF (or ;FF) timecode to a frame count."""
    n = max(1, int(round(fps)))
    h, m, s, f = (int(p) for p in re.split(r"[:;]", tc))
    return ((h * 60 + m) * 60 + s) * n + f


def _fmt_fps(fps: float) -> str:
    return f"{fps:.3f}".rstrip("0").rstrip(".")


def _fmt_secs(secs: float) -> str:
    return f"{secs:.3f}".rstrip("0").rstrip(".") + " s"


def _last_frame_count(text: str) -> int:
    matches = re.findall(r"frame=\s*(\d+)", text)
    return int(matches[-1]) if matches else 0


def probe_video(path: str) -> dict:
    """Read frame-accurate duration, fps and timecode using ffmpeg only.

    Returns a dict: duration_tc, frames, fps, seconds, start_tc, end_tc.
    The duration is the video stream's real length (its exact frame count),
    independent of any embedded start timecode. Raises RuntimeError if the
    essential data can't be read.
    """
    meta = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True).stderr

    fps_m = re.search(r",\s*([0-9]+(?:\.[0-9]+)?)\s*fps", meta)
    tbr_m = re.search(r",\s*([0-9]+(?:\.[0-9]+)?)\s*tbr", meta)
    fps = float(fps_m.group(1)) if fps_m else (float(tbr_m.group(1)) if tbr_m else 0.0)
    if fps <= 0:
        raise RuntimeError("frame rate not detected")

    tc_m = re.search(r"timecode\s*:\s*(\d{2}:\d{2}:\d{2}[:;]\d{2})", meta)
    start_tc = tc_m.group(1) if tc_m else None

    # Exact frame count: stream-copy first (fast, no decoding), decode as fallback.
    out = subprocess.run(
        [FFMPEG, "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    frames = _last_frame_count(out)
    if frames <= 0:
        out = subprocess.run(
            [FFMPEG, "-i", path, "-map", "0:v:0", "-f", "null", "-"],
            capture_output=True, text=True,
        ).stderr
        frames = _last_frame_count(out)
    if frames <= 0:
        raise RuntimeError("could not count frames")

    nominal = int(round(fps))
    data = {
        "duration_tc": frames_to_tc(frames, nominal),
        "frames": frames,
        "fps": fps,
        "seconds": frames / exact_fps(fps),
        "start_tc": start_tc,
        "end_tc": None,
    }
    if start_tc:
        # Last-frame timecode = start + (frames - 1). The headline duration
        # above is the full length (frames), i.e. the difference you want.
        data["end_tc"] = frames_to_tc(tc_to_frames(start_tc, nominal) + frames - 1, nominal)
    return data


class ProbeWorker(QThread):
    """Reads frame-accurate duration and timecode in a background thread."""

    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, video_path: str):
        super().__init__()
        self.video_path = video_path

    def run(self):
        try:
            self.done.emit(probe_video(self.video_path))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ExtractWorker(QThread):
    """Extracts the first frame in a separate thread so the GUI stays responsive."""

    done = Signal(str)        # path of the saved file
    failed = Signal(str)      # error message

    def __init__(self, video_path: str, as_jpeg: bool):
        super().__init__()
        self.video_path = video_path
        self.as_jpeg = as_jpeg

    def run(self):
        try:
            src = Path(self.video_path)
            ext = ".jpg" if self.as_jpeg else ".png"
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = DOWNLOADS / f"{src.stem}_frame_{stamp}{ext}"

            DOWNLOADS.mkdir(parents=True, exist_ok=True)

            # -map_metadata -1 + -bitexact: no metadata/comments added by ffmpeg
            # and no color tags or embedded ICC profile. The frame comes out as a
            # 1:1 copy of the video's pixels.
            if self.as_jpeg:
                # JPEG at maximum quality (qscale 1 = best)
                cmd = [
                    FFMPEG, "-y", "-i", str(src),
                    "-frames:v", "1",
                    "-qmin", "1", "-q:v", "1",
                    "-map_metadata", "-1", "-bitexact",
                    str(out),
                ]
            else:
                # Lossless PNG
                cmd = [
                    FFMPEG, "-y", "-i", str(src),
                    "-frames:v", "1",
                    "-compression_level", "0",
                    "-map_metadata", "-1", "-bitexact",
                    str(out),
                ]

            proc = subprocess.run(
                cmd, capture_output=True, text=True,
            )
            if proc.returncode != 0 or not out.exists():
                err = proc.stderr.strip().splitlines()
                msg = err[-1] if err else "ffmpeg failed to extract the frame"
                self.failed.emit(msg)
                return

            self.done.emit(str(out))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class DropZone(QFrame):
    """Central area that accepts drag & drop."""

    file_dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in VIDEO_EXTS:
                    event.acceptProposedAction()
                    self.setProperty("hover", True)
                    self._restyle()
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("hover", False)
        self._restyle()

    def dropEvent(self, event):
        self.setProperty("hover", False)
        self._restyle()
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in VIDEO_EXTS:
                self.file_dropped.emit(path)
                return

    def _restyle(self):
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("First Frame Extractor")
        self.setMinimumSize(560, 460)
        self.setAcceptDrops(False)
        self.worker: ExtractWorker | None = None
        self.probe: ProbeWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(18)

        title = QLabel("First Frame Extractor")
        title.setObjectName("title")

        subtitle = QLabel("Drag an MP4/MOV video — the first frame is copied "
                          "to the clipboard and saved to Downloads.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        # Drop zone
        self.drop = DropZone()
        drop_layout = QVBoxLayout(self.drop)
        drop_layout.setAlignment(Qt.AlignCenter)
        drop_layout.setSpacing(10)

        self.icon = QLabel("⬇")
        self.icon.setObjectName("dropicon")
        self.icon.setAlignment(Qt.AlignCenter)

        self.drop_text = QLabel("Drag your video here")
        self.drop_text.setObjectName("droptext")
        self.drop_text.setAlignment(Qt.AlignCenter)

        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.setObjectName("browse")
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.clicked.connect(self.choose_file)

        drop_layout.addStretch()
        drop_layout.addWidget(self.icon)
        drop_layout.addWidget(self.drop_text)
        drop_layout.addSpacing(6)
        drop_layout.addWidget(self.browse_btn, alignment=Qt.AlignCenter)
        drop_layout.addStretch()

        # Options row
        opts = QHBoxLayout()
        self.jpeg_check = QCheckBox("Save as 100% JPEG (instead of lossless PNG)")
        self.jpeg_check.setObjectName("jpegcheck")
        self.jpeg_check.setCursor(Qt.PointingHandCursor)
        opts.addWidget(self.jpeg_check)
        opts.addStretch()

        # Info panel: frame-accurate duration / timecode (monospace, aligned)
        self.info = QLabel()
        self.info.setObjectName("info")
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setPointSize(13)
        self.info.setFont(mono)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info.hide()

        # Status bar
        self.status = QLabel("Ready.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(self.drop, stretch=1)
        root.addLayout(opts)
        root.addWidget(self.info)
        root.addWidget(self.status)

        self.drop.file_dropped.connect(self.start_extraction)

    # ---- actions -------------------------------------------------------

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a video", str(Path.home()),
            "Video (*.mp4 *.mov *.m4v *.qt)",
        )
        if path:
            self.start_extraction(path)

    def start_extraction(self, path: str):
        if self.worker and self.worker.isRunning():
            return
        self.set_busy(True)
        name = Path(path).name
        self.set_status(f"Extracting from “{name}”…", "busy")

        self.worker = ExtractWorker(path, self.jpeg_check.isChecked())
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

        # Frame-accurate duration / timecode, in parallel with extraction.
        self.info.show()
        self.info.setText("Reading video info…")
        self.probe = ProbeWorker(path)
        self.probe.done.connect(self.on_probe_done)
        self.probe.failed.connect(self.on_probe_failed)
        self.probe.start()

    def on_done(self, out_path: str):
        # Copy to clipboard
        copied = self.copy_to_clipboard(out_path)
        self.set_busy(False)
        name = Path(out_path).name
        if copied:
            self.set_status(f"✓ Copied to clipboard and saved: {name}", "ok")
        else:
            self.set_status(f"✓ Saved: {name} (couldn't copy to clipboard)", "ok")

    def on_failed(self, msg: str):
        self.set_busy(False)
        self.set_status(f"✗ Error: {msg}", "err")

    def on_probe_done(self, d: dict):
        lines = [
            f"{'Duration':<10}{d['duration_tc']}",
            f"{'Frames':<10}{d['frames']}  @ {_fmt_fps(d['fps'])} fps",
            f"{'Seconds':<10}{_fmt_secs(d['seconds'])}",
        ]
        if d.get("start_tc"):
            lines.append(f"{'Timecode':<10}{d['start_tc']} → {d['end_tc']}")
        self.info.setText("\n".join(lines))

    def on_probe_failed(self, msg: str):
        self.info.setText(f"Video info unavailable: {msg}")

    def copy_to_clipboard(self, image_path: str) -> bool:
        img = QImage(image_path)
        if img.isNull():
            return False
        QGuiApplication.clipboard().setImage(img)
        return True

    # ---- ui helpers ----------------------------------------------------

    def set_busy(self, busy: bool):
        self.browse_btn.setEnabled(not busy)
        self.jpeg_check.setEnabled(not busy)
        self.drop_text.setText("Extracting…" if busy else "Drag your video here")

    def set_status(self, text: str, kind: str = ""):
        self.status.setText(text)
        self.status.setProperty("kind", kind)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)


STYLE = """
QWidget {
    background: #0f1115;
    color: #e6e8ec;
    font-family: -apple-system, "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 14px;
}
#title { font-size: 24px; font-weight: 700; color: #ffffff; }
#subtitle { color: #9aa0aa; font-size: 13px; }

#dropzone {
    background: #161922;
    border: 2px dashed #2c3140;
    border-radius: 18px;
}
#dropzone[hover="true"] {
    background: #1b2030;
    border: 2px dashed #5b8cff;
}
#dropicon { font-size: 46px; color: #5b8cff; }
#droptext { font-size: 16px; color: #c4c9d4; font-weight: 600; }

#browse {
    background: #5b8cff;
    color: #0b0d12;
    border: none;
    border-radius: 10px;
    padding: 9px 22px;
    font-weight: 700;
    font-size: 14px;
}
#browse:hover { background: #6f9bff; }
#browse:disabled { background: #39414f; color: #8b919c; }

#jpegcheck { color: #c4c9d4; spacing: 8px; }
#jpegcheck::indicator {
    width: 18px; height: 18px;
    border-radius: 5px;
    border: 1px solid #3a4150;
    background: #161922;
}
#jpegcheck::indicator:checked {
    background: #5b8cff;
    border: 1px solid #5b8cff;
}

#info {
    background: #161922;
    border: 1px solid #232838;
    border-radius: 10px;
    padding: 12px 16px;
    color: #d7dbe4;
}

#status {
    background: #161922;
    border-radius: 10px;
    padding: 10px 14px;
    color: #9aa0aa;
    font-size: 13px;
}
#status[kind="ok"]   { color: #57d38c; }
#status[kind="err"]  { color: #ff6b6b; }
#status[kind="busy"] { color: #5b8cff; }
"""


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
