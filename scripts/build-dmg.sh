#!/bin/bash
#
# build-dmg.sh - costruisce un DMG stilizzato per macOS.
#
# Prende dist/First Frame Extractor.app (gia' compilata con PyInstaller)
# e usa dmgbuild per produrre dist/FirstFrameExtractor-macos.dmg con:
#   - l'icona dell'app a sinistra
#   - il link "Applications" a destra (trascina-per-installare)
#   - il file "Open if blocked.txt" in basso al centro (istruzioni di sblocco)
#   - uno sfondo scuro che guida l'utente
#
# Requisiti: dmgbuild nel venv (pip install -r requirements-release-mac.txt). Non usa il Finder:
# create-dmg lo comandava via AppleScript, e senza il permesso di Automazione la build si fermava.

set -euo pipefail

# --- Percorsi ---------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

APP_NAME="First Frame Extractor.app"
APP_PATH="${REPO_ROOT}/dist/${APP_NAME}"
HELP_NAME="Open if blocked.txt"
HELP_SRC="${SCRIPT_DIR}/${HELP_NAME}"
BACKGROUND="${SCRIPT_DIR}/dmg-background.tiff"
VOLICON="${REPO_ROOT}/assets/icon.icns"

VOL_NAME="First Frame Extractor"
OUTPUT_DMG="${REPO_ROOT}/dist/FirstFrameExtractor-macos.dmg"

# --- Controlli preliminari --------------------------------------------------
PY="${PY:-${REPO_ROOT}/.venv/bin/python}"
if ! "${PY}" -c "import dmgbuild" >/dev/null 2>&1; then
    echo "ERRORE: dmgbuild non trovato in ${PY}. Installa con: ${PY} -m pip install -r requirements-release-mac.txt" >&2
    exit 1
fi

if [ ! -d "${APP_PATH}" ]; then
    echo "ERRORE: app non trovata in ${APP_PATH}" >&2
    echo "Compila prima con: pyinstaller --noconfirm FirstFrameExtractor.spec" >&2
    exit 1
fi

if [ ! -f "${HELP_SRC}" ]; then
    echo "ERRORE: file istruzioni non trovato: ${HELP_SRC}" >&2
    exit 1
fi

# Idempotenza: rimuovi eventuale DMG precedente.
rm -f "${OUTPUT_DMG}"

echo "Eseguo dmgbuild..."
"${PY}" -m dmgbuild \
    -s "${SCRIPT_DIR}/dmg_settings.py" \
    -D app="${APP_PATH}" \
    -D help="${HELP_SRC}" \
    -D background="${BACKGROUND}" \
    -D volicon="${VOLICON}" \
    "${VOL_NAME}" "${OUTPUT_DMG}"

echo ""
echo "DMG creato: ${OUTPUT_DMG}"
