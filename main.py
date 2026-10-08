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
from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QImage, QGuiApplication, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from start_menu import keep_start_menu_shortcut

# The name of the manifest (.nexus/products.json) and the AppUserModelID, for good: the shortcut in
# Start > Metessi and the taskbar group hang on them.
APP_NAME = "First Frame Extractor"
APP_USER_MODEL_ID = "dev.metessi.first-frame-extractor"
# The icon of the windows: the same file the build gives the exe and the bundle.
ICON = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets" / "icon.png"

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
    """Map a rounded NTSC fps (e.g. 23.98) to its exact rational (24000/1001).

    The threshold is tight on purpose: 23.98 and 24.00 differ by only 0.02, so
    a true 24.000 fps must NOT be turned into 23.976.
    """
    for approx, real in _FPS_RATIONALS.items():
        if abs(fps - approx) < 0.01:
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


def duration_bucket(frames: int, fps: float) -> int:
    """Whole-seconds class, rounded UP: exactly N s -> N, N s + 1 frame -> N+1."""
    n = max(1, int(round(fps)))
    whole, extra = divmod(frames, n)
    return whole + (1 if extra else 0)


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
    """Self-contained drop area for videos. Emits the list of dropped videos."""

    files_dropped = Signal(list)

    def __init__(self, caption: str, button_text: str | None = None):
        super().__init__()
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)

        icon = QLabel("⬇")
        icon.setObjectName("dropicon")
        icon.setAlignment(Qt.AlignCenter)

        self._caption = QLabel(caption)
        self._caption.setObjectName("droptext")
        self._caption.setAlignment(Qt.AlignCenter)
        self._caption.setWordWrap(True)

        lay.addStretch()
        lay.addWidget(icon)
        lay.addWidget(self._caption)

        self.button: QPushButton | None = None
        if button_text:
            self.button = QPushButton(button_text)
            self.button.setObjectName("browse")
            self.button.setCursor(Qt.PointingHandCursor)
            lay.addSpacing(6)
            lay.addWidget(self.button, alignment=Qt.AlignCenter)

        lay.addStretch()

    def set_caption(self, text: str):
        self._caption.setText(text)

    @staticmethod
    def _videos(event) -> list:
        out = []
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if Path(path).suffix.lower() in VIDEO_EXTS:
                    out.append(path)
        return out

    def dragEnterEvent(self, event):
        if self._videos(event):
            event.acceptProposedAction()
            self.setProperty("hover", True)
            self._restyle()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("hover", False)
        self._restyle()

    def dropEvent(self, event):
        self.setProperty("hover", False)
        self._restyle()
        videos = self._videos(event)
        if videos:
            self.files_dropped.emit(videos)

    def _restyle(self):
        self.style().unpolish(self)
        self.style().polish(self)


class ExtractTab(QWidget):
    """First-frame extractor: one video -> saved frame + clipboard + info panel."""

    def __init__(self):
        super().__init__()
        self.worker: ExtractWorker | None = None
        self.probe: ProbeWorker | None = None
        # Keep a reference to every running thread until it truly finishes, so a
        # QThread is never destroyed while still running (which aborts the app).
        self._live: set = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 22)
        root.setSpacing(16)

        subtitle = QLabel("Drag an MP4/MOV video — the first frame is copied "
                          "to the clipboard and saved to Downloads.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        self.drop = DropZone("Drag your video here", button_text="Browse…")
        self.drop.button.clicked.connect(self.choose_file)
        self.drop.files_dropped.connect(self.on_files)

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

        self.status = QLabel("Ready.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)

        root.addWidget(subtitle)
        root.addWidget(self.drop, stretch=1)
        root.addLayout(opts)
        root.addWidget(self.info)
        root.addWidget(self.status)

    def _track(self, worker):
        """Hold a reference until the thread's finished() fires (run() returned),
        then release it — so it is never garbage-collected while running."""
        self._live.add(worker)
        worker.finished.connect(lambda w=worker: self._live.discard(w))

    def stop_threads(self):
        for worker in list(self._live):
            worker.wait(5000)

    def on_files(self, paths: list):
        self.start_extraction(paths[0])

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
        self._track(self.worker)
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

        # Frame-accurate duration / timecode, in parallel with extraction.
        self.info.show()
        self.info.setText("Reading video info…")
        self.probe = ProbeWorker(path)
        self._track(self.probe)
        self.probe.done.connect(self.on_probe_done)
        self.probe.failed.connect(self.on_probe_failed)
        self.probe.start()

    def on_done(self, out_path: str):
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

    def set_busy(self, busy: bool):
        if self.drop.button:
            self.drop.button.setEnabled(not busy)
        self.jpeg_check.setEnabled(not busy)
        self.drop.set_caption("Extracting…" if busy else "Drag your video here")

    def set_status(self, text: str, kind: str = ""):
        self.status.setText(text)
        self.status.setProperty("kind", kind)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)


class _DurationRow(QWidget):
    """One list row: a prominent seconds-bucket badge + the technical detail."""

    def __init__(self, name: str, mono):
        super().__init__()
        self.setObjectName("row")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(12)

        self.badge = QLabel("…")
        self.badge.setObjectName("badge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedWidth(58)
        self.badge.setProperty("state", "loading")

        self.text = QLabel(name)
        self.text.setObjectName("rowtext")
        self.text.setFont(mono)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)

        lay.addWidget(self.badge)
        lay.addWidget(self.text, stretch=1)

    def _restyle(self):
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    def set_result(self, bucket: int, exact: bool, text: str):
        self.badge.setText(f"{bucket}s")
        self.badge.setProperty("state", "exact" if exact else "round")
        self._restyle()
        self.text.setText(text)

    def set_error(self, name: str, err: str):
        self.badge.setText("—")
        self.badge.setProperty("state", "error")
        self._restyle()
        self.text.setText(f"{name}   (error: {err})")


class DurationsTab(QWidget):
    """Durations only: accepts multiple videos, lists each one's exact duration.

    Each row carries a prominent seconds-bucket badge (rounded up: 4 s -> 4s,
    4 s + 1 frame -> 5s). No frame is extracted, copied or saved. Files are
    probed one at a time so the list fills in drop order.
    """

    def __init__(self):
        super().__init__()
        self._queue: deque = deque()
        self._active: ProbeWorker | None = None
        # Keep running threads referenced until finished() (see _released).
        self._live: set = set()

        self._mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._mono.setPointSize(13)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 22)
        root.setSpacing(16)

        subtitle = QLabel("Drop one or more videos — nothing is extracted, you only "
                          "get each clip's exact duration, in drop order.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        self.drop = DropZone("Drop videos here (multiple allowed)",
                             button_text="Add videos…")
        self.drop.setMinimumHeight(130)
        self.drop.button.clicked.connect(self.choose_files)
        self.drop.files_dropped.connect(self.add_files)

        self.list = QListWidget()
        self.list.setObjectName("durlist")
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setUniformItemSizes(True)

        # Legend for the badge colours.
        legend = QLabel("Badge = duration rounded up to whole seconds   ·   "
                        "green = exact,  blue = rounded up")
        legend.setObjectName("subtitle")

        bar = QHBoxLayout()
        self.count = QLabel("No files yet.")
        self.count.setObjectName("status")
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("ghost")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_list)
        bar.addWidget(self.count)
        bar.addStretch()
        bar.addWidget(self.clear_btn)

        root.addWidget(subtitle)
        root.addWidget(self.drop)
        root.addWidget(self.list, stretch=1)
        root.addWidget(legend)
        root.addLayout(bar)

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select videos", str(Path.home()),
            "Video (*.mp4 *.mov *.m4v *.qt)",
        )
        if paths:
            self.add_files(paths)

    def add_files(self, paths: list):
        for path in paths:
            item = QListWidgetItem()
            self.list.addItem(item)
            row = _DurationRow(Path(path).name, self._mono)
            item.setSizeHint(row.sizeHint())
            self.list.setItemWidget(item, row)
            self._queue.append((row, path))
        self._update_count()
        self._pump()

    def _pump(self):
        if self._active is not None or not self._queue:
            return
        row, path = self._queue.popleft()
        worker = ProbeWorker(path)
        self._active = worker
        self._live.add(worker)
        worker.done.connect(lambda d, r=row, p=path: self._apply(r, p, d, None))
        worker.failed.connect(lambda m, r=row, p=path: self._apply(r, p, None, m))
        worker.finished.connect(lambda w=worker: self._released(w))
        worker.start()

    def _apply(self, row, path, d, err):
        # Update the row only. The worker is released on finished() (below),
        # never here — dropping a still-running QThread would abort the app.
        try:
            if err:
                row.set_error(Path(path).name, err)
            else:
                nominal = max(1, int(round(d["fps"])))
                exact = d["frames"] % nominal == 0
                row.set_result(duration_bucket(d["frames"], d["fps"]), exact,
                               self._row_text(path, d))
                row.setToolTip(self._tooltip(path, d))
        except RuntimeError:
            pass  # the row was cleared while probing

    def _released(self, worker):
        # QThread.finished(): run() has returned, so releasing it is safe.
        self._live.discard(worker)
        if self._active is worker:
            self._active = None
        self._pump()

    def stop_threads(self):
        self._queue.clear()
        for worker in list(self._live):
            worker.wait(5000)

    @staticmethod
    def _row_text(path, d) -> str:
        name = Path(path).name
        parts = [f"{d['frames']}f @ {_fmt_fps(d['fps'])} fps", _fmt_secs(d['seconds'])]
        if d.get("start_tc"):
            parts.append(f"TC {d['start_tc']}→{d['end_tc']}")
        return f"{d['duration_tc']:<11}  {name}   ({' · '.join(parts)})"

    @staticmethod
    def _tooltip(path, d) -> str:
        lines = [
            f"Duration  {d['duration_tc']}",
            f"Frames    {d['frames']} @ {_fmt_fps(d['fps'])} fps",
            f"Seconds   {_fmt_secs(d['seconds'])}",
        ]
        if d.get("start_tc"):
            lines.append(f"Timecode  {d['start_tc']} → {d['end_tc']}")
        lines += ["", str(path)]
        return "\n".join(lines)

    def clear_list(self):
        self.list.clear()
        self._queue.clear()
        self._update_count()

    def _update_count(self):
        n = self.list.count()
        self.count.setText("No files yet." if n == 0 else f"{n} file(s)")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("First Frame Extractor")
        self.setMinimumSize(600, 540)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title = QLabel("First Frame Extractor")
        title.setObjectName("title")
        title.setContentsMargins(24, 20, 24, 10)

        self._extract = ExtractTab()
        self._durations = DurationsTab()
        tabs = QTabWidget()
        tabs.addTab(self._extract, "Extract")
        tabs.addTab(self._durations, "Durations")

        root.addWidget(title)
        root.addWidget(tabs, stretch=1)

    def closeEvent(self, event):
        # Let running probe/extract threads finish before teardown, otherwise a
        # QThread destroyed mid-run would abort on quit.
        for tab in (self._extract, self._durations):
            tab.stop_threads()
        super().closeEvent(event)


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

QTabWidget::pane { border: none; }
QTabWidget::tab-bar { left: 22px; }
QTabBar::tab {
    background: transparent;
    color: #9aa0aa;
    padding: 8px 14px;
    margin-right: 6px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 14px;
    font-weight: 600;
}
QTabBar::tab:hover { color: #c4c9d4; }
QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #5b8cff; }

#durlist {
    background: #12151d;
    border: 1px solid #232838;
    border-radius: 10px;
    padding: 6px;
    color: #d7dbe4;
    outline: none;
}
#durlist::item { border-radius: 6px; }
#durlist::item:selected { background: #22314f; }

#row, #rowtext { background: transparent; }
#rowtext { color: #d7dbe4; }
#badge {
    border-radius: 10px;
    padding: 4px 0;
    font-size: 15px;
    font-weight: 800;
}
#badge[state="loading"] { background: #2c3140; color: #8b919c; }
#badge[state="exact"]   { background: #57d38c; color: #08130c; }
#badge[state="round"]   { background: #5b8cff; color: #0b0d12; }
#badge[state="error"]   { background: #ff6b6b; color: #2a0a0a; }

#ghost {
    background: transparent;
    color: #9aa0aa;
    border: 1px solid #2c3140;
    border-radius: 8px;
    padding: 6px 14px;
    font-weight: 600;
}
#ghost:hover { color: #e6e8ec; border-color: #3a4150; }
"""


def main():
    # Before any window: the windows group under the shortcut, which this start checks.
    keep_start_menu_shortcut(APP_NAME, APP_USER_MODEL_ID)
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ICON)))
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
