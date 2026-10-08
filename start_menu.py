"""The app's own shortcut in the Windows Start menu.

Every program released through Nexus keeps its own shortcut (Nexus release
contract, docs/CONTRATTO_RELEASE.md, section 6):
``%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Metessi\\<name>.lnk``,
checked at every start and written again only when it is missing or runs
another exe or another AppUserModelID, so a copy that was moved finds its
shortcut at its first start. The shortcut and the process declare the same
AppUserModelID, so the taskbar groups the windows under the shortcut's icon.
The shortcut an older Nexus made in ``Programs`` goes, but only when it runs
this very exe; nothing else in the Start menu is touched.

The decision (`ensure_start_menu_shortcut`) is plain Python, tested on any
system. The shell link itself is written through the Windows COM interfaces
(IShellLinkW, IPropertyStore, IPersistFile) with ctypes, so the app needs no
extra package; it is tested on the Windows runner of the build.
"""

from __future__ import annotations

import ntpath
import os
import sys
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

START_MENU_FOLDER = "Metessi"


@dataclass(frozen=True)
class Shortcut:
    target: str
    app_user_model_id: Optional[str] = None


@dataclass(frozen=True)
class ShortcutDetails:
    target: str
    cwd: str
    description: str
    icon: str
    app_user_model_id: str


@dataclass(frozen=True)
class ShortcutOutcome:
    file: str
    written: bool
    removed_old: Optional[str] = None


class StartMenuSystem(Protocol):
    def read(self, file: str) -> Optional[Shortcut]:
        """The shortcut at ``file``; None when there is none or it cannot be read."""

    def write(self, file: str, details: ShortcutDetails) -> None:
        """Writes or replaces the shortcut. Raises when it cannot."""

    def remove(self, file: str) -> None: ...


def _same_path(a: str, b: str) -> bool:
    return ntpath.normcase(ntpath.normpath(a)) == ntpath.normcase(ntpath.normpath(b))


def ensure_start_menu_shortcut(
    system: StartMenuSystem,
    app_data: Optional[str],
    name: str,
    exe: str,
    app_user_model_id: str,
    makedirs: Callable[[str], None] = lambda folder: os.makedirs(folder, exist_ok=True),
) -> ShortcutOutcome:
    """Makes sure the shortcut of the program ``name`` runs ``exe``. Raises when it cannot be written."""
    if not app_data:
        raise RuntimeError("%APPDATA% is not set: the Start menu is not known")
    programs = ntpath.join(app_data, "Microsoft", "Windows", "Start Menu", "Programs")
    folder = ntpath.join(programs, START_MENU_FOLDER)
    file = ntpath.join(folder, f"{name}.lnk")

    written = False
    now = system.read(file)
    if now is None or not _same_path(now.target, exe) or now.app_user_model_id != app_user_model_id:
        makedirs(folder)
        system.write(
            file,
            ShortcutDetails(target=exe, cwd=ntpath.dirname(exe), description=name, icon=exe, app_user_model_id=app_user_model_id),
        )
        written = True

    removed_old = None
    old = ntpath.join(programs, f"{name}.lnk")
    old_one = system.read(old)
    if old_one is not None and _same_path(old_one.target, exe):
        system.remove(old)
        removed_old = old
    return ShortcutOutcome(file=file, written=written, removed_old=removed_old)


# ---- Windows: the shell link through COM -------------------------------------------------------

if sys.platform == "win32":
    import ctypes
    from ctypes import POINTER, Structure, Union, byref, c_int, c_ulong, c_ushort, c_void_p, c_wchar_p, wintypes

    class _GUID(Structure):
        _fields_ = [("Data1", c_ulong), ("Data2", c_ushort), ("Data3", c_ushort), ("Data4", ctypes.c_ubyte * 8)]

        def __init__(self, text: Optional[str] = None):
            super().__init__()
            if text is not None:
                ctypes.oledll.ole32.CLSIDFromString(c_wchar_p(text), byref(self))

    class _PROPERTYKEY(Structure):
        _fields_ = [("fmtid", _GUID), ("pid", c_ulong)]

    class _PROPVARIANT_VALUE(Union):
        _fields_ = [("pwszVal", c_void_p), ("pad", ctypes.c_ulonglong * 2)]

    class _PROPVARIANT(Structure):
        _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort), ("value", _PROPVARIANT_VALUE)]

    _CLSID_ShellLink = "{00021401-0000-0000-C000-000000000046}"
    _IID_IShellLinkW = "{000214F9-0000-0000-C000-000000000046}"
    _IID_IPersistFile = "{0000010b-0000-0000-C000-000000000046}"
    _IID_IPropertyStore = "{886d8eeb-8cf2-4446-8d02-cdba1dbdcf99}"
    _CLSCTX_INPROC_SERVER = 1
    _COINIT_APARTMENTTHREADED = 2
    _VT_LPWSTR = 31
    _STGM_READ = 0
    _SLGP_RAWPATH = 4

    def _key_app_user_model_id() -> _PROPERTYKEY:
        key = _PROPERTYKEY()
        key.fmtid = _GUID("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}")
        key.pid = 5
        return key

    def _call(pointer: c_void_p, index: int, *types_and_args):
        """Calls method ``index`` of the COM interface at ``pointer``; a failed HRESULT raises OSError."""
        types = types_and_args[0::2]
        args = types_and_args[1::2]
        vtable = ctypes.cast(pointer, POINTER(POINTER(c_void_p))).contents
        prototype = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *types)
        return prototype(vtable[index])(pointer, *args)

    def _release(pointer: c_void_p) -> None:
        if pointer:
            vtable = ctypes.cast(pointer, POINTER(POINTER(c_void_p))).contents
            ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtable[2])(pointer)

    def _query(pointer: c_void_p, iid: str) -> c_void_p:
        out = c_void_p()
        _call(pointer, 0, POINTER(_GUID), byref(_GUID(iid)), POINTER(c_void_p), byref(out))
        return out

    class _Com:
        """COM for this thread, released on exit when this call is the one that started it."""

        def __enter__(self):
            result = ctypes.windll.ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
            # S_OK and S_FALSE both need a CoUninitialize; a thread in another apartment can still use the link.
            self.started = result in (0, 1)
            return self

        def __exit__(self, *_):
            if self.started:
                ctypes.windll.ole32.CoUninitialize()

    def _new_link() -> c_void_p:
        link = c_void_p()
        ctypes.oledll.ole32.CoCreateInstance(
            byref(_GUID(_CLSID_ShellLink)), None, _CLSCTX_INPROC_SERVER, byref(_GUID(_IID_IShellLinkW)), byref(link)
        )
        return link

    class WindowsShellLinks:
        """The real shortcuts, through IShellLinkW."""

        def read(self, file: str) -> Optional[Shortcut]:
            if not os.path.exists(file):
                return None
            with _Com():
                link = _new_link()
                persist, store = c_void_p(), c_void_p()
                try:
                    persist = _query(link, _IID_IPersistFile)
                    _call(persist, 5, c_wchar_p, file, c_ulong, _STGM_READ)  # Load
                    buffer = ctypes.create_unicode_buffer(32768)
                    _call(link, 3, c_wchar_p, buffer, c_int, len(buffer), c_void_p, None, c_ulong, _SLGP_RAWPATH)  # GetPath
                    store = _query(link, _IID_IPropertyStore)
                    value = _PROPVARIANT()
                    _call(store, 5, POINTER(_PROPERTYKEY), byref(_key_app_user_model_id()), POINTER(_PROPVARIANT), byref(value))  # GetValue
                    aumid = ctypes.wstring_at(value.value.pwszVal) if value.vt == _VT_LPWSTR and value.value.pwszVal else None
                    ctypes.windll.ole32.PropVariantClear(byref(value))
                    return Shortcut(target=buffer.value, app_user_model_id=aumid)
                except OSError:
                    return None
                finally:
                    _release(store)
                    _release(persist)
                    _release(link)

        def write(self, file: str, details: ShortcutDetails) -> None:
            with _Com():
                link = _new_link()
                persist, store = c_void_p(), c_void_p()
                try:
                    _call(link, 20, c_wchar_p, details.target)  # SetPath
                    _call(link, 9, c_wchar_p, details.cwd)  # SetWorkingDirectory
                    _call(link, 7, c_wchar_p, details.description)  # SetDescription
                    _call(link, 17, c_wchar_p, details.icon, c_int, 0)  # SetIconLocation
                    store = _query(link, _IID_IPropertyStore)
                    text = ctypes.create_unicode_buffer(details.app_user_model_id)
                    value = _PROPVARIANT()
                    value.vt = _VT_LPWSTR
                    value.value.pwszVal = ctypes.cast(text, c_void_p)
                    _call(store, 6, POINTER(_PROPERTYKEY), byref(_key_app_user_model_id()), POINTER(_PROPVARIANT), byref(value))  # SetValue
                    _call(store, 7)  # Commit
                    persist = _query(link, _IID_IPersistFile)
                    _call(persist, 6, c_wchar_p, file, wintypes.BOOL, True)  # Save
                finally:
                    _release(store)
                    _release(persist)
                    _release(link)

        def remove(self, file: str) -> None:
            os.remove(file)

    def set_app_user_model_id(app_user_model_id: str) -> None:
        ctypes.oledll.shell32.SetCurrentProcessExplicitAppUserModelID(c_wchar_p(app_user_model_id))


def keep_start_menu_shortcut(name: str, app_user_model_id: str) -> Optional[ShortcutOutcome]:
    """Windows, packaged app: the process takes the AppUserModelID and the shortcut runs this exe.
    A failure is reported on stderr and the app goes on. Elsewhere it does nothing."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None
    try:
        set_app_user_model_id(app_user_model_id)
        return ensure_start_menu_shortcut(WindowsShellLinks(), os.environ.get("APPDATA"), name, sys.executable, app_user_model_id)
    except Exception as error:  # noqa: BLE001
        print(f"[start-menu] cannot write the shortcut in the Start menu: {error}", file=sys.stderr)
        return None
