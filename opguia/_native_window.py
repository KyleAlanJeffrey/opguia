"""Wrapper for NiceGUI's _open_window that sets macOS icon + app name.

This module is pickled by reference when multiprocessing uses 'spawn'.
The child process imports this module, runs our wrapper, which sets up
AppKit BEFORE creating the pywebview window — no fork needed.
"""

import sys
from pathlib import Path

_STATIC = Path(__file__).parent / "static"
_ICON_PNG = str(_STATIC / "icon.png")
_APP_NAME = "OPGuia"


def _open_window_with_icon(*args, **kwargs):
    """Drop-in replacement for native_mode._open_window.

    Sets the macOS dock icon and menu bar app name, then delegates
    to the original NiceGUI _open_window implementation.
    """
    if sys.platform == "darwin":
        try:
            import AppKit

            ns_app = AppKit.NSApplication.sharedApplication()

            # Set dock icon
            ns_image = AppKit.NSImage.alloc().initByReferencingFile_(_ICON_PNG)
            if ns_image:
                ns_app.setApplicationIconImage_(ns_image)

            # Set menu bar app name
            bundle = AppKit.NSBundle.mainBundle()
            info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
            if info is not None:
                info["CFBundleName"] = _APP_NAME
        except Exception:
            pass

    # Delegate to the original NiceGUI implementation
    from nicegui.native.native_mode import _open_window

    return _open_window(*args, **kwargs)
