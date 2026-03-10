"""Connection page — endpoint input, server scan, connect.

Landing page at "/". Shows an endpoint input field, saved connection
profiles, and auto-scans for local OPC UA servers on common ports.
"""

import asyncio
from nicegui import ui
from opguia.client import OpcuaClient
from opguia.scanner import scan_servers
from opguia.settings import Settings


def register(client: OpcuaClient, settings: Settings):
    @ui.page("/")
    async def connection_page():
        ui.dark_mode().enable()
        with ui.column().classes("w-full items-center justify-center min-h-screen gap-4"):
            with ui.row().classes("items-center gap-3"):
                ui.image("/static/favicon.svg").classes("w-10 h-10")
                with ui.column().classes("gap-0"):
                    ui.label("OPGuia").classes("text-3xl font-bold")
                    ui.label("OPC UA Browser").classes("text-xs text-gray-400 -mt-1")

            # Manual endpoint input
            with ui.card().classes("w-96 p-4"):
                endpoint = ui.input("Endpoint", value="opc.tcp://localhost:4840").classes("w-full")
                profile_name = ui.input("Profile name", value="").props("dense").classes(
                    "w-full"
                ).style("font-size:12px")
                profile_name.props('placeholder="Optional — uses server name"')
                status = ui.label("").classes("text-xs")

                async def do_connect():
                    status.text = "Connecting..."
                    status.classes(remove="text-red-400 text-green-400")
                    try:
                        await client.connect(endpoint.value)
                        # Ensure profile exists for this endpoint
                        name = profile_name.value.strip() or client.server_name or endpoint.value
                        settings.ensure_profile(endpoint.value, name)
                        settings.set_active(endpoint.value)
                        status.text = "Connected"
                        status.classes(add="text-green-400")
                        await asyncio.sleep(0.3)
                        ui.navigate.to("/browse")
                    except Exception as e:
                        status.text = str(e)
                        status.classes(add="text-red-400")

                with ui.row().classes("w-full gap-2"):
                    ui.button("Connect", on_click=do_connect).classes("flex-grow")
                    ui.button(
                        icon="bookmark_add",
                        on_click=lambda: save_profile(endpoint.value, profile_name.value.strip()),
                    ).props("flat dense").tooltip("Save profile")

            # Saved profiles
            saved_card = ui.card().classes("w-96 p-4")

            def render_saved():
                saved_card.clear()
                with saved_card:
                    ui.label("Saved Profiles").classes("text-sm font-bold")
                    profiles = settings.profiles
                    if not profiles:
                        ui.label("No saved profiles").classes("text-xs text-gray-500 mt-1")
                    else:
                        with ui.column().classes("w-full gap-1 mt-2"):
                            for prof in profiles:
                                with ui.row().classes(
                                    "items-center gap-2 w-full hover:bg-gray-800 rounded px-2 py-1"
                                ):
                                    pick_row = ui.row().classes(
                                        "items-center gap-2 flex-grow cursor-pointer min-w-0"
                                    )
                                    with pick_row:
                                        ui.icon("bookmark", size="14px").classes("text-blue-400 shrink-0")
                                        with ui.column().classes("gap-0 min-w-0"):
                                            ui.label(prof["name"]).classes("text-xs font-medium truncate")
                                            ui.label(prof["url"]).classes(
                                                "font-mono text-gray-500 truncate"
                                            ).style("font-size:10px")
                                        watched_count = len(prof.get("watched", []))
                                        if watched_count:
                                            ui.badge(str(watched_count), color="blue").props(
                                                "rounded"
                                            ).classes("text-xs").tooltip(
                                                f"{watched_count} watched variable{'s' if watched_count != 1 else ''}"
                                            )

                                    def pick(u=prof["url"], n=prof["name"]):
                                        endpoint.value = u
                                        profile_name.value = n
                                    pick_row.on("click", pick)

                                    def remove(u=prof["url"]):
                                        settings.remove_profile(u)
                                        render_saved()

                                    ui.button(
                                        icon="close", on_click=remove,
                                    ).props("flat dense round size=xs").classes("text-gray-500 shrink-0")

            def save_profile(url: str, name: str = ""):
                settings.add_profile(name or url, url)
                render_saved()

            render_saved()

            # Auto-discovered servers
            with ui.card().classes("w-96 p-4"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Discovered Servers").classes("text-sm font-bold")
                    scan_spinner = ui.spinner(size="sm")
                scan_list = ui.column().classes("w-full gap-1 mt-2")

            async def run_scan():
                scan_list.clear()
                scan_spinner.visible = True
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

                            def pick(url=srv["url"], name=srv["name"]):
                                endpoint.value = url
                                if name:
                                    profile_name.value = name
                            row.on("click", pick)

            asyncio.create_task(run_scan())
            ui.timer(5.0, run_scan)

            # Show existing connection if already connected
            if client.connected:
                with ui.row().classes("items-center gap-1"):
                    ui.icon("check_circle", size="xs").classes("text-green-400")
                    ui.label(client.endpoint).classes("text-xs text-green-400")
                    ui.button("Browse", on_click=lambda: ui.navigate.to("/browse")).props("flat dense size=sm")
