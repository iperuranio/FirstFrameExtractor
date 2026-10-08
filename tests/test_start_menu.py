import ntpath
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import start_menu  # noqa: E402
from start_menu import Shortcut, ensure_start_menu_shortcut  # noqa: E402

APP_DATA = "C:\\Users\\claudio\\AppData\\Roaming"
PROGRAMS = APP_DATA + "\\Microsoft\\Windows\\Start Menu\\Programs"
NAME = "First Frame Extractor"
LINK = PROGRAMS + "\\Metessi\\" + NAME + ".lnk"
OLD_LINK = PROGRAMS + "\\" + NAME + ".lnk"
EXE = "F:\\SOFTWARES\\First Frame Extractor\\FirstFrameExtractor.exe"
ID = "dev.metessi.first-frame-extractor"


class FakeStartMenu:
    """The Start menu, faked: the shortcuts by file, and what was asked of it."""

    def __init__(self, links=None, writes=True):
        self.links = dict(links or {})
        self.writes = writes
        self.asked = []
        self.written = {}

    def read(self, file):
        return self.links.get(file)

    def write(self, file, details):
        self.asked.append(f"write {file}")
        if not self.writes:
            raise OSError("access denied")
        self.written[file] = details
        self.links[file] = Shortcut(details.target, details.app_user_model_id)

    def remove(self, file):
        self.asked.append(f"remove {file}")
        del self.links[file]

    def makedirs(self, folder):
        self.asked.append(f"mkdir {folder}")


def ensure(menu, app_data=APP_DATA):
    return ensure_start_menu_shortcut(menu, app_data, NAME, EXE, ID, makedirs=menu.makedirs)


class EnsureTest(unittest.TestCase):
    def test_writes_it_in_metessi_when_missing(self):
        menu = FakeStartMenu()
        outcome = ensure(menu)
        self.assertEqual((outcome.file, outcome.written, outcome.removed_old), (LINK, True, None))
        self.assertEqual(menu.asked, [f"mkdir {PROGRAMS}\\Metessi", f"write {LINK}"])
        details = menu.written[LINK]
        self.assertEqual((details.target, details.cwd, details.icon, details.app_user_model_id), (EXE, ntpath.dirname(EXE), EXE, ID))

    def test_leaves_it_alone_when_it_runs_this_exe(self):
        menu = FakeStartMenu({LINK: Shortcut(EXE.upper(), ID)})
        self.assertFalse(ensure(menu).written)
        self.assertEqual(menu.asked, [])

    def test_writes_it_again_for_another_exe_or_no_app_user_model_id(self):
        moved = FakeStartMenu({LINK: Shortcut("D:\\Old\\FirstFrameExtractor.exe", ID)})
        self.assertTrue(ensure(moved).written)
        self.assertEqual(moved.links[LINK].target, EXE)
        self.assertTrue(ensure(FakeStartMenu({LINK: Shortcut(EXE)})).written)

    def test_removes_the_old_shortcut_only_when_it_runs_this_exe(self):
        own = FakeStartMenu({OLD_LINK: Shortcut(EXE)})
        self.assertEqual(ensure(own).removed_old, OLD_LINK)
        self.assertNotIn(OLD_LINK, own.links)
        other = FakeStartMenu({OLD_LINK: Shortcut("D:\\Somewhere\\FirstFrameExtractor.exe")})
        self.assertIsNone(ensure(other).removed_old)
        self.assertNotIn(f"remove {OLD_LINK}", other.asked)

    def test_says_so_when_it_cannot(self):
        with self.assertRaises(OSError):
            ensure(FakeStartMenu(writes=False))
        with self.assertRaisesRegex(RuntimeError, "APPDATA"):
            ensure(FakeStartMenu(), app_data=None)


@unittest.skipUnless(sys.platform == "win32", "the shell link is a Windows thing")
class WindowsShellLinkTest(unittest.TestCase):
    """The real COM calls: a shortcut written, read back, and kept as it is the second time."""

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as app_data:
            links = start_menu.WindowsShellLinks()
            exe = sys.executable
            first = ensure_start_menu_shortcut(links, app_data, NAME, exe, ID)
            self.assertTrue(first.written)
            self.assertTrue(os.path.isfile(first.file))
            read = links.read(first.file)
            self.assertIsNotNone(read)
            self.assertEqual(ntpath.normcase(read.target), ntpath.normcase(exe))
            self.assertEqual(read.app_user_model_id, ID)
            self.assertFalse(ensure_start_menu_shortcut(links, app_data, NAME, exe, ID).written)
            self.assertTrue(ensure_start_menu_shortcut(links, app_data, NAME, exe, ID + ".other").written)
            self.assertIsNone(links.read(os.path.join(app_data, "missing.lnk")))

    def test_process_takes_the_app_user_model_id(self):
        start_menu.set_app_user_model_id(ID)


if __name__ == "__main__":
    unittest.main()
