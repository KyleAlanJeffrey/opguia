"""Application entry point — wires up pages and runs NiceGUI."""

from nicegui import ui
from opguia.client import OpcuaClient
from opguia.pages import connection, browse


def run():
    client = OpcuaClient()
    connection.register(client)
    browse.register(client)
    ui.run(
        title="OPGuia",
        favicon="🔌",
        port=8080,
        reload=False,
        storage_secret="opguia",
        native=True,
        window_size=(1200, 800),
    )
