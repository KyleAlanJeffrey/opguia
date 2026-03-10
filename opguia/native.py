"""Platform-specific native window configuration.

Sets the application icon and name for macOS dock / Windows taskbar.
Must be called before ui.run().
"""

import sys


def configure_native():
    """Apply platform-specific icon and app name. Call before ui.run()."""
    if sys.platform == "darwin":
        _configure_macos()
    elif sys.platform == "win32":
        _configure_windows()


def _configure_macos():
    """Set macOS dock icon and menu bar app name.

    Replaces NiceGUI's _open_window with our wrapper that sets up AppKit
    in the child process. With 'spawn' (Python 3.13+ default on macOS),
    the wrapper function is pickled by module path. The child process
    imports opguia._native_window, runs our setup code, then delegates
    to the original _open_window. No fork required.
    """
    try:
        from nicegui.native import native_mode
        from opguia._native_window import _open_window_with_icon

        native_mode._open_window = _open_window_with_icon
    except ImportError:
        pass


def _configure_windows():
    """Set Windows taskbar grouping so the app gets its own icon."""
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "opguia.browser.app"
        )
    except Exception:
        pass
