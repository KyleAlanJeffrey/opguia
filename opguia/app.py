"""Application entry point — wires up pages and runs NiceGUI."""

import sys
from pathlib import Path


def run():
    # Check for --headless before importing NiceGUI (heavy import)
    if "--headless" in sys.argv:
        sys.argv.remove("--headless")
        sys.argv[0] = "opguia"
        from opguia.cli import main
        main()
        return

    from nicegui import app, ui
    from opguia.client import OpcuaClient
    from opguia.storage import Settings
    from opguia.tunnel import SSHTunnel
    from opguia.pages import connection, browse
    from opguia.native import configure_native

    static = Path(__file__).parent / "static"
    favicon = (static / "favicon.svg").read_text()

    client = OpcuaClient()
    settings = Settings()
    tunnel = SSHTunnel()
    app.add_static_files("/static", static)
    configure_native()
    connection.register(client, settings, tunnel)
    browse.register(client, settings, tunnel)
    ui.run(
        title="OPGuia — OPC UA Browser",
        favicon=favicon,
        port=8080,
        reload=False,
        storage_secret="opguia",
        native=True,
        window_size=(1200, 800),
    )
