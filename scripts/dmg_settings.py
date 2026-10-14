# Layout of the FirstFrameExtractor dmg, for dmgbuild (scripts/build-dmg.sh passes app, help,
# background and volicon with -D). dmgbuild writes the window layout straight into the image,
# without asking Finder through AppleScript: no Automation permission, no GUI session needed.
# Coordinates match scripts/make-background.py.
import os.path

app = defines["app"]  # noqa: F821 (dmgbuild provides `defines`)
help_file = defines["help"]  # noqa: F821
background = defines.get("background")  # noqa: F821
volicon = defines.get("volicon")  # noqa: F821

format = "UDZO"
files = [app, help_file]
symlinks = {"Applications": "/Applications"}
if volicon and os.path.exists(volicon):
    icon = volicon
if background and os.path.exists(background):
    background = background
else:
    background = None

window_rect = ((200, 120), (620, 480))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
icon_size = 120
icon_locations = {
    os.path.basename(app): (165, 195),
    "Applications": (455, 195),
    os.path.basename(help_file): (310, 392),
}
