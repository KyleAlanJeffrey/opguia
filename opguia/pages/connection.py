"""Connection page — endpoint input, server scan, connect.

Landing page at "/". Two-column layout: left has manual input + discovered
servers, right has saved profiles with status pings and connect buttons.
"""

import asyncio
from nicegui import ui
from opguia.client import OpcuaClient
from opguia.scanner import scan_servers
from opguia.settings import Settings


async def _ping(url: str, timeout: float = 2.0) -> bool:
    """Quick TCP check to see if an OPC UA endpoint is reachable."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 4840
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


def register(client: OpcuaClient, settings: Settings):
    @ui.page("/")
    async def connection_page():
        ui.dark_mode().enable()
        ui.query("body").style("margin:0; overflow:hidden")
        ui.query(".nicegui-content").classes("w-full h-screen").style(
            "display:flex; flex-direction:column; padding:0; gap:0"
        )

        # ── Header ──
        with ui.row().classes("w-full items-center justify-center gap-3 py-6 shrink-0"):
            ui.image("/static/favicon.svg").classes("w-10 h-10")
            with ui.column().classes("gap-0"):
                ui.label("OPGuia").classes("text-3xl font-bold")
                ui.label("OPC UA Browser").classes("text-xs text-gray-400 -mt-1")

        # ── Two-column layout ──
        with ui.row().classes(
            "w-full justify-center no-wrap gap-6 px-6"
        ).style("flex:1; min-height:0; overflow:hidden"):

            # ── Left column: manual + discovered ──
            with ui.column().classes("gap-4").style("width:400px; overflow-y:auto"):

                # Manual endpoint input
                with ui.card().classes("w-full p-4"):
                    ui.label("Manual Connection").classes("text-sm font-bold")
                    endpoint = ui.input(
                        "Endpoint", value="opc.tcp://localhost:4840"
                    ).classes("w-full mt-2")
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

                # Discovered servers
                with ui.card().classes("w-full p-4"):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label("Discovered Servers").classes("text-sm font-bold")
                        scan_spinner = ui.spinner(size="sm")
                    scan_list = ui.column().classes("w-full gap-1 mt-2")

                    _discovered_urls: set[str] = set()

                    async def run_scan():
                        scan_spinner.visible = True
                        servers = await scan_servers()
                        scan_spinner.visible = False
                        # Only update if the set of URLs actually changed
                        new_urls = {s["url"] for s in servers}
                        if new_urls == _discovered_urls:
                            return
                        _discovered_urls.clear()
                        _discovered_urls.update(new_urls)
                        scan_list.clear()
                        with scan_list:
                            if not servers:
                                ui.label("No servers found").classes("text-xs text-gray-500")
                            for srv in servers:
                                with ui.row().classes(
                                    "items-center gap-2 w-full hover:bg-gray-800 rounded px-2 py-1 cursor-pointer"
                                ) as row:
                                    ui.icon("dns", size="14px").classes("text-green-400")
                                    with ui.column().classes("gap-0"):
                                        ui.label(srv["name"] or "OPC UA Server").classes(
                                            "text-xs font-bold"
                                        )
                                        ui.label(srv["url"]).classes(
                                            "text-xs text-gray-400 font-mono"
                                        )

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
                        ui.button(
                            "Browse", on_click=lambda: ui.navigate.to("/browse")
                        ).props("flat dense size=sm")

            # ── Right column: saved profiles ──
            with ui.column().classes("gap-0").style("width:400px; overflow-y:auto"):
                saved_card = ui.card().classes("w-full p-4")

                async def connect_profile(url: str, name: str):
                    try:
                        await client.connect(url)
                        settings.ensure_profile(url, name)
                        settings.set_active(url)
                        ui.navigate.to("/browse")
                    except Exception as e:
                        ui.notify(str(e), type="negative")

                def render_saved():
                    saved_card.clear()
                    with saved_card:
                        ui.label("Saved Profiles").classes("text-sm font-bold mb-2")
                        profiles = settings.profiles
                        if not profiles:
                            ui.label("No saved profiles yet").classes(
                                "text-xs text-gray-500 mt-1"
                            )
                            ui.label(
                                "Connect to a server and click the bookmark icon to save."
                            ).classes("text-xs text-gray-600 mt-1")
                        else:
                            with ui.column().classes("w-full gap-2"):
                                for prof in profiles:
                                    _render_profile_row(prof)

                def _render_profile_row(prof):
                    with ui.card().classes("w-full p-3").props("flat bordered"):
                        with ui.row().classes("items-start gap-3 w-full"):
                            # Status dot
                            dot = ui.icon("circle", size="10px").classes(
                                "text-gray-600 shrink-0 mt-1"
                            )

                            with ui.column().classes("gap-1 min-w-0 flex-grow"):
                                ui.label(prof["name"]).classes("text-sm font-medium truncate")
                                ui.label(prof["url"]).classes(
                                    "font-mono text-gray-500 truncate"
                                ).style("font-size:11px")

                                # Stats row
                                with ui.row().classes("items-center gap-3 mt-1"):
                                    watched_count = len(prof.get("watched", []))
                                    if watched_count:
                                        with ui.row().classes("items-center gap-1"):
                                            ui.icon("visibility", size="12px").classes(
                                                "text-blue-400"
                                            )
                                            ui.label(
                                                f"{watched_count} watched"
                                            ).classes("text-xs text-gray-400")

                                    root_path = prof.get("tree_root_path", [])
                                    if root_path:
                                        with ui.row().classes("items-center gap-1"):
                                            ui.icon("folder", size="12px").classes(
                                                "text-yellow-500"
                                            )
                                            ui.label(
                                                " / ".join(root_path[-2:])
                                            ).classes("text-xs text-gray-400 truncate")

                                    status_label = ui.label("Checking...").classes(
                                        "text-xs text-gray-600"
                                    )

                        with ui.row().classes("w-full justify-end gap-1 mt-2"):
                            connect_btn = ui.button(
                                "Connect",
                                on_click=lambda u=prof["url"], n=prof["name"]: connect_profile(u, n),
                            ).props("dense size=sm color=primary")

                            def remove(u=prof["url"]):
                                settings.remove_profile(u)
                                render_saved()

                            ui.button(
                                icon="delete", on_click=remove,
                            ).props("flat dense size=sm color=red").tooltip("Remove profile")

                    # Ping in background
                    async def update_dot(url=prof["url"], d=dot, btn=connect_btn, lbl=status_label):
                        reachable = await _ping(url)
                        if reachable:
                            d.classes(remove="text-gray-600", add="text-green-500")
                            lbl.text = "Online"
                            lbl.classes(remove="text-gray-600", add="text-green-500")
                        else:
                            d.classes(remove="text-gray-600", add="text-red-500")
                            lbl.text = "Unreachable"
                            lbl.classes(remove="text-gray-600", add="text-red-500")
                            btn.props("disable")

                    asyncio.create_task(update_dot())

                render_saved()

                def save_profile(url: str, name: str = ""):
                    settings.add_profile(name or url, url)
                    render_saved()
