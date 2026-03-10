"""Application entry point — wires up pages and runs NiceGUI."""

from nicegui import ui
from opguia.client import OpcuaClient
from opguia.pages import connection, browse


def _has_webview():
    try:
        import webview  # noqa: F401
        return True
    except ImportError:
        return False


def run():
    client = OpcuaClient()
    connection.register(client)
    browse.register(client)
    native = _has_webview()
    ui.run(
        title="OPGuia",
        favicon="🔌",
        port=8080,
        reload=False,
        storage_secret="opguia",
        native=native,
        **({"window_size": (1200, 800)} if native else {}),
    )
