#!/bin/bash
#
# Fix & Open.command
#
# Removes the "quarantine" attribute (com.apple.quarantine) that macOS applies
# to downloaded, unsigned apps, then opens the app. This avoids the
# "the app is damaged and can't be opened" message.
#
# INSTRUCTIONS:
#   1) First drag "First Frame Extractor" into your Applications folder.
#   2) Double-click this file.

set -e

APP_PATH="/Applications/First Frame Extractor.app"

echo ""
echo "==================================================="
echo "  Fix & Open - First Frame Extractor"
echo "==================================================="
echo ""

if [ -d "$APP_PATH" ]; then
    echo "  App found at:"
    echo "    ${APP_PATH}"
    echo ""
    echo "  Removing quarantine..."
    xattr -dr com.apple.quarantine "$APP_PATH"
    echo "  Done. Opening the app..."
    open "$APP_PATH"
    echo ""
    echo "  You can now open \"First Frame Extractor\" normally,"
    echo "  with a double-click, without security warnings."
else
    echo "  WARNING: could not find the app at:"
    echo "    ${APP_PATH}"
    echo ""
    echo "  First drag \"First Frame Extractor\" into your Applications"
    echo "  folder (use this same disk window), then double-click"
    echo "  this file again."
fi

echo ""
echo "  Press ENTER to close this window."
read -r _
