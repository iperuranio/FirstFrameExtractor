#!/bin/bash
#
# build-dmg.sh - costruisce un DMG stilizzato per macOS.
#
# Prende dist/First Frame Extractor.app (gia' compilata con PyInstaller)
# e usa create-dmg per produrre dist/FirstFrameExtractor-macos.dmg con:
#   - l'icona dell'app a sinistra
#   - il link "Applications" a destra (trascina-per-installare)
#   - lo script "Ripara e Apri.command" in basso al centro
#   - uno sfondo scuro che guida l'utente
#
# Requisiti: create-dmg (brew install create-dmg).

set -euo pipefail

# --- Percorsi ---------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

APP_NAME="First Frame Extractor.app"
APP_PATH="${REPO_ROOT}/dist/${APP_NAME}"
COMMAND_NAME="Ripara e Apri.command"
COMMAND_SRC="${SCRIPT_DIR}/${COMMAND_NAME}"
BACKGROUND="${SCRIPT_DIR}/dmg-background.tiff"
VOLICON="${REPO_ROOT}/assets/icon.icns"

VOL_NAME="First Frame Extractor"
OUTPUT_DMG="${REPO_ROOT}/dist/FirstFrameExtractor-macos.dmg"

# --- Controlli preliminari --------------------------------------------------
if ! command -v create-dmg >/dev/null 2>&1; then
    echo "ERRORE: create-dmg non trovato. Installa con: brew install create-dmg" >&2
    exit 1
fi

if [ ! -d "${APP_PATH}" ]; then
    echo "ERRORE: app non trovata in ${APP_PATH}" >&2
    echo "Compila prima con: pyinstaller --noconfirm FirstFrameExtractor.spec" >&2
    exit 1
fi

if [ ! -f "${COMMAND_SRC}" ]; then
    echo "ERRORE: script non trovato: ${COMMAND_SRC}" >&2
    exit 1
fi

# --- Staging ---------------------------------------------------------------
# STAGING contiene SOLO l'app (diventa il contenuto principale del DMG).
# Lo script .command viene aggiunto a parte con --add-file, da una cartella
# dove possiamo garantirne il bit di esecuzione (git/CI potrebbe non
# preservare i permessi).
STAGING="$(mktemp -d)"
EXTRA="$(mktemp -d)"
trap 'rm -rf "${STAGING}" "${EXTRA}"' EXIT

echo "Staging in ${STAGING}"
cp -R "${APP_PATH}" "${STAGING}/"

COMMAND_STAGED="${EXTRA}/${COMMAND_NAME}"
cp "${COMMAND_SRC}" "${COMMAND_STAGED}"
chmod +x "${COMMAND_STAGED}"

# Idempotenza: rimuovi eventuale DMG precedente.
rm -f "${OUTPUT_DMG}"

# --- Layout finestra --------------------------------------------------------
# Coordinate coerenti con scripts/make-background.py.
WINDOW_W=620
WINDOW_H=480
ICON_SIZE=120

ARGS=(
    --volname "${VOL_NAME}"
    --window-pos 200 120
    --window-size "${WINDOW_W}" "${WINDOW_H}"
    --icon-size "${ICON_SIZE}"
    --icon "${APP_NAME}" 165 195
    --app-drop-link 455 195
    --add-file "${COMMAND_NAME}" "${COMMAND_STAGED}" 310 392
    --hdiutil-quiet
    --no-internet-enable
)

if [ -f "${BACKGROUND}" ]; then
    ARGS+=(--background "${BACKGROUND}")
fi

if [ -f "${VOLICON}" ]; then
    ARGS+=(--volicon "${VOLICON}")
fi

echo "Eseguo create-dmg..."
# create-dmg puo' fallire per timing di Finder/AppleScript: alcuni retry.
attempt=1
max_attempts=4
until create-dmg "${ARGS[@]}" "${OUTPUT_DMG}" "${STAGING}"; do
    status=$?
    if [ "${attempt}" -ge "${max_attempts}" ]; then
        echo "ERRORE: create-dmg fallito dopo ${attempt} tentativi (exit ${status})." >&2
        exit "${status}"
    fi
    echo "create-dmg fallito (tentativo ${attempt}/${max_attempts}), riprovo..." >&2
    rm -f "${OUTPUT_DMG}"
    attempt=$((attempt + 1))
    sleep 3
done

echo ""
echo "DMG creato: ${OUTPUT_DMG}"
