# First Frame Extractor

App desktop minimale (macOS + Windows) per estrarre il **primo frame** di un video.
Trascina un video MP4/MOV nella finestra (o usa **Sfoglia…**): il primo frame viene
**copiato negli appunti** e **salvato nella cartella Download**. PNG lossless di
default, oppure JPEG 100% con l'apposita spunta.

Gli eseguibili sono **standalone**: includono l'interprete Python, PySide6 e un binario
`ffmpeg` statico. Non serve installare nulla.

## Download

Prendi l'ultima versione dalla pagina **[Releases](../../releases)**:

- **macOS** — `FirstFrameExtractor-macos.dmg` → apri il `.dmg` e **trascina l'app nella
  cartella Applicazioni**. Se al primo avvio macOS blocca l'app (non è firmata), fai
  doppio clic su **`Ripara e Apri.command`** presente nella stessa finestra del disco:
  rimuove la quarantena e avvia l'app.
- **Windows** — `FirstFrameExtractor-windows.zip` → estrai e avvia `FirstFrameExtractor.exe`.
  SmartScreen mostrerà un avviso: scegli **Ulteriori informazioni → Esegui comunque**.

> ⚠️ I binari **non sono firmati** (la firma del codice richiede certificati a pagamento
> e non è inclusa), quindi gli avvisi di sicurezza al primo avvio sono attesi.

## Formati supportati

`.mp4`, `.mov`, `.m4v`, `.qt`

## Build da sorgente

Requisiti: Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Esecuzione da sorgente
python main.py

# Build eseguibile standalone
pip install pyinstaller
pyinstaller --noconfirm FirstFrameExtractor.spec
# output in dist/
```

## CI / distribuzione

Il workflow [`.github/workflows/build.yml`](.github/workflows/build.yml) builda
automaticamente gli eseguibili su runner **macOS** e **Windows** a ogni push su `main`.
Un push di un tag `v*` (es. `git tag v1.0.0 && git push --tags`) allega entrambi gli
archivi a una **Release**.

## Stack

- [PySide6](https://doc.qt.io/qtforpython/) — GUI
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) — binario ffmpeg statico incluso
- [PyInstaller](https://pyinstaller.org/) — packaging standalone
