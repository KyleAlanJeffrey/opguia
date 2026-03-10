"""Application entry point — wires up pages and runs NiceGUI."""

from pathlib import Path
from nicegui import app, ui
from opguia.client import OpcuaClient
from opguia.settings import Settings
from opguia.pages import connection, browse
from opguia.native import configure_native

_STATIC = Path(__file__).parent / "static"
_FAVICON = (_STATIC / "favicon.svg").read_text()


def run():
    client = OpcuaClient()
    settings = Settings()
    app.add_static_files("/static", _STATIC)
    configure_native()
    connection.register(client, settings)
    browse.register(client, settings)
    ui.run(
        title="OPGuia — OPC UA Browser",
        favicon=_FAVICON,
        port=8080,
        reload=False,
        storage_secret="opguia",
        native=True,
        window_size=(1200, 800),
    )
