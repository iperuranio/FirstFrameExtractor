#!/bin/bash
#
# Ripara e Apri.command
#
# Rimuove l'attributo di "quarantena" (com.apple.quarantine) che macOS
# applica alle app scaricate e non firmate, poi apre l'app.
# Questo evita il messaggio "l'app e' danneggiata e non puo' essere aperta".
#
# ISTRUZIONI:
#   1) Trascina prima "First Frame Extractor" nella cartella Applicazioni.
#   2) Fai doppio clic su questo file.

set -e

APP_PATH="/Applications/First Frame Extractor.app"

echo ""
echo "==================================================="
echo "  Ripara e Apri - First Frame Extractor"
echo "==================================================="
echo ""

if [ -d "$APP_PATH" ]; then
    echo "  App trovata in:"
    echo "    ${APP_PATH}"
    echo ""
    echo "  Rimozione della quarantena in corso..."
    xattr -dr com.apple.quarantine "$APP_PATH"
    echo "  Fatto. Avvio dell'app..."
    open "$APP_PATH"
    echo ""
    echo "  Ora puoi aprire \"First Frame Extractor\" normalmente,"
    echo "  con un doppio clic, senza avvisi di sicurezza."
else
    echo "  ATTENZIONE: non ho trovato l'app in:"
    echo "    ${APP_PATH}"
    echo ""
    echo "  Trascina prima \"First Frame Extractor\" nella cartella"
    echo "  Applicazioni (usa questa stessa finestra del disco),"
    echo "  poi fai di nuovo doppio clic su questo file."
fi

echo ""
echo "  Premi INVIO per chiudere questa finestra."
read -r _
