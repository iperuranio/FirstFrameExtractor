#!/usr/bin/env python3
"""First Frame Extractor

Drag & drop (o seleziona) un video MP4/MOV: il primo frame viene estratto
immediatamente, copiato negli appunti e salvato nella cartella Download.
PNG lossless di default, JPEG 100% se la spunta è attiva.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QImage, QGuiApplication, QFont
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
    """Trova ffmpeg: prima il binario statico incluso nel pacchetto (build
    standalone), poi il PATH o i percorsi tipici di Homebrew (da sorgente)."""
    # 1. ffmpeg statico incluso via imageio-ffmpeg (eseguibile standalone)
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:  # noqa: BLE001
        pass
    # 2. PATH / Homebrew (esecuzione da sorgente)
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if Path(candidate).exists():
            return candidate
    return "ffmpeg"


FFMPEG = find_ffmpeg()


class ExtractWorker(QThread):
    """Estrae il primo frame in un thread separato per non bloccare la GUI."""

    done = Signal(str)        # percorso del file salvato
    failed = Signal(str)      # messaggio di errore

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

            # -map_metadata -1 + -bitexact: nessun metadato/commento aggiunto da
            # ffmpeg e nessun tag di colore o profilo ICC incorporato.
            # Il frame esce come copia 1:1 dei pixel del video.
            if self.as_jpeg:
                # JPEG alla massima qualità (qscale 1 = migliore)
                cmd = [
                    FFMPEG, "-y", "-i", str(src),
                    "-frames:v", "1",
                    "-qmin", "1", "-q:v", "1",
                    "-map_metadata", "-1", "-bitexact",
                    str(out),
                ]
            else:
                # PNG lossless senza perdite
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
                msg = err[-1] if err else "ffmpeg ha fallito l'estrazione"
                self.failed.emit(msg)
                return

            self.done.emit(str(out))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class DropZone(QFrame):
    """Area centrale che accetta il drag & drop."""

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

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(18)

        title = QLabel("First Frame Extractor")
        title.setObjectName("title")

        subtitle = QLabel("Trascina un video MP4/MOV — il primo frame viene "
                          "copiato negli appunti e salvato in Download.")
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

        self.drop_text = QLabel("Trascina qui il video")
        self.drop_text.setObjectName("droptext")
        self.drop_text.setAlignment(Qt.AlignCenter)

        self.browse_btn = QPushButton("Sfoglia…")
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
        self.jpeg_check = QCheckBox("Salva come JPEG 100% (invece di PNG lossless)")
        self.jpeg_check.setObjectName("jpegcheck")
        self.jpeg_check.setCursor(Qt.PointingHandCursor)
        opts.addWidget(self.jpeg_check)
        opts.addStretch()

        # Status bar
        self.status = QLabel("Pronto.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(self.drop, stretch=1)
        root.addLayout(opts)
        root.addWidget(self.status)

        self.drop.file_dropped.connect(self.start_extraction)

    # ---- actions -------------------------------------------------------

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona un video", str(Path.home()),
            "Video (*.mp4 *.mov *.m4v *.qt)",
        )
        if path:
            self.start_extraction(path)

    def start_extraction(self, path: str):
        if self.worker and self.worker.isRunning():
            return
        self.set_busy(True)
        name = Path(path).name
        self.set_status(f"Estrazione da “{name}”…", "busy")

        self.worker = ExtractWorker(path, self.jpeg_check.isChecked())
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_done(self, out_path: str):
        # Copia negli appunti
        copied = self.copy_to_clipboard(out_path)
        self.set_busy(False)
        name = Path(out_path).name
        if copied:
            self.set_status(f"✓ Copiato negli appunti e salvato: {name}", "ok")
        else:
            self.set_status(f"✓ Salvato: {name} (copia negli appunti non riuscita)", "ok")

    def on_failed(self, msg: str):
        self.set_busy(False)
        self.set_status(f"✗ Errore: {msg}", "err")

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
        self.drop_text.setText("Estrazione in corso…" if busy else "Trascina qui il video")

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
