"""Connection page — endpoint input, server scan, connect."""

import asyncio
from nicegui import ui
from opguia.client import OpcuaClient
from opguia.scanner import scan_servers


def register(client: OpcuaClient):
    @ui.page("/")
    async def connection_page():
        ui.dark_mode().enable()
        with ui.column().classes("w-full items-center justify-center min-h-screen gap-4"):
            ui.label("OPGuia").classes("text-3xl font-bold")

            with ui.card().classes("w-96 p-4"):
                endpoint = ui.input("Endpoint", value="opc.tcp://localhost:4840").classes("w-full")
                status = ui.label("").classes("text-xs")

                async def do_connect():
                    status.text = "Connecting..."
                    status.classes(remove="text-red-400 text-green-400")
                    try:
                        await client.connect(endpoint.value)
                        status.text = "Connected"
                        status.classes(add="text-green-400")
                        await asyncio.sleep(0.3)
                        ui.navigate.to("/browse")
                    except Exception as e:
                        status.text = str(e)
                        status.classes(add="text-red-400")

                ui.button("Connect", on_click=do_connect).classes("w-full")

            # Discovered servers
            with ui.card().classes("w-96 p-4"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Discovered Servers").classes("text-sm font-bold")
                    scan_spinner = ui.spinner(size="sm")
                scan_list = ui.column().classes("w-full gap-1 mt-2")

            async def run_scan():
                servers = await scan_servers()
                scan_spinner.visible = False
                with scan_list:
                    if not servers:
                        ui.label("No servers found").classes("text-xs text-gray-500")
                    for srv in servers:
                        with ui.row().classes(
                            "items-center gap-2 w-full hover:bg-gray-800 rounded px-2 py-1 cursor-pointer"
                        ) as row:
                            ui.icon("dns", size="14px").classes("text-green-400")
                            with ui.column().classes("gap-0"):
                                ui.label(srv["name"] or "OPC UA Server").classes("text-xs font-bold")
                                ui.label(srv["url"]).classes("text-xs text-gray-400 font-mono")

                            def pick(url=srv["url"]):
                                endpoint.value = url
                            row.on("click", pick)

            asyncio.create_task(run_scan())

            if client.connected:
                with ui.row().classes("items-center gap-1"):
                    ui.icon("check_circle", size="xs").classes("text-green-400")
                    ui.label(client.endpoint).classes("text-xs text-green-400")
                    ui.button("Browse", on_click=lambda: ui.navigate.to("/browse")).props("flat dense size=sm")
