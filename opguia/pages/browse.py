"""Browse page — sidebar + full-width tree + detail dialog + status bar."""

import asyncio
from nicegui import ui
from opguia.client import OpcuaClient
from opguia.components.tree_view import create_tree_view
from opguia.components.detail_panel import create_detail_panel


def register(client: OpcuaClient):
    @ui.page("/browse")
    async def browse_page():
        ui.dark_mode().enable()
        if not client.connected:
            ui.navigate.to("/")
            return

        # -- Header --
        with ui.header().classes("items-center justify-between px-4 py-2 min-h-0 bg-gray-900 border-b border-gray-700"):
            ui.label("OPC UA Viewer").classes("text-base font-bold")

            with ui.row().classes("items-center gap-4"):
                if client.server_name:
                    ui.label(f"Server: {client.server_name}").classes("text-sm text-gray-300")
                ui.badge("Connected", color="green").props("rounded")

                async def do_disconnect():
                    await client.disconnect()
                    ui.navigate.to("/")

                ui.button(icon="settings", on_click=do_disconnect).props("flat dense round size=sm").classes("text-gray-400")

        # -- Main layout --
        with ui.row().classes("w-full h-screen pt-12 pb-8"):

            # -- Left sidebar --
            with ui.column().classes("w-72 shrink-0 h-full border-r border-gray-700 bg-gray-900/50 gap-0"):
                # Search
                with ui.row().classes("w-full p-3"):
                    ui.input(placeholder="Search").props('dense outlined').classes("w-full text-sm").style(
                        "font-size: 13px"
                    )

                ui.separator().classes("my-0")

                # Connections section
                with ui.column().classes("w-full gap-0 p-2"):
                    ui.label("Connections").classes("text-xs text-gray-500 uppercase tracking-wide px-2 py-1")

                    with ui.row().classes("items-center gap-2 px-2 py-2 bg-white/5 rounded w-full"):
                        ui.icon("dns", size="20px").classes("text-blue-400")
                        with ui.column().classes("gap-0"):
                            ui.label(client.server_name or "OPC UA Server").classes("text-sm font-medium")
                            ui.label(client.endpoint).classes("text-xs text-gray-500 font-mono")

            # -- Tree area --
            with ui.column().classes("flex-grow h-full overflow-auto gap-0"):
                tree_container, rebuild_tree, set_root = create_tree_view(
                    client, on_select_node=lambda nid: show_detail_dialog(nid)
                )

        # -- Status bar --
        with ui.footer().classes("items-center justify-start gap-6 px-4 py-1 min-h-0 bg-gray-900 border-t border-gray-700"):
            ui.label(f"Endpoint: {client.endpoint}").classes("text-xs text-gray-400 font-mono")
            ui.label(f"Security: {client.security_policy}").classes("text-xs text-gray-400")
            latency_label = ui.label("Latency: ...").classes("text-xs text-gray-400")

        # Measure latency periodically
        async def update_latency():
            while client.connected:
                ms = await client.measure_latency()
                if ms is not None:
                    latency_label.text = f"Latency: {ms} ms"
                await asyncio.sleep(5)

        asyncio.create_task(update_latency())

        # -- Detail dialog (shown on node click) --
        async def show_detail_dialog(node_id: str):
            with ui.dialog().classes("w-full max-w-lg") as dlg, ui.card().classes("w-full p-4"):
                _container, show_details = create_detail_panel(
                    client,
                    on_set_root=lambda nid, name: _set_root_and_close(dlg, nid, name),
                )
            dlg.open()
            await show_details(node_id)

        async def _set_root_and_close(dlg, nid, name):
            dlg.close()
            await set_root(nid, name)

        await rebuild_tree()
