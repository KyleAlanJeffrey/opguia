"""Browse page — main screen after connecting.

Layout (all flexbox, no calc):
  ┌─────────────────────────────────┐
  │ Top bar (40px, shrink-0)        │
  ├────────┬────────────────────────┤
  │Sidebar │ Search bar (32px)      │  ← middle row (flex:1)
  │(200px) │ Tree (flex:1 scroll)   │
  ├────────┴────────────────────────┤
  │ Bottom bar (24px, shrink-0)     │
  └─────────────────────────────────┘
"""

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

        # Override NiceGUI defaults — full-height flex column, no padding
        ui.query("body").style("margin:0; overflow:hidden")
        ui.query(".nicegui-content").classes("w-full h-screen").style(
            "display:flex; flex-direction:column; padding:0; gap:0"
        )

        # ── Top bar ──
        with ui.row().classes(
            "w-full items-center justify-between px-4 bg-gray-900 border-b border-gray-700 shrink-0"
        ).style("height:40px; min-height:40px"):
            ui.label("OPC UA Browser").classes("text-sm font-bold")
            with ui.row().classes("items-center gap-3"):
                if client.server_name:
                    ui.label(f"Server: {client.server_name}").classes("text-xs text-gray-300")
                ui.badge("Connected", color="green").props("rounded").classes("text-xs")

        # ── Middle: sidebar + main content ──
        with ui.row().classes("w-full no-wrap overflow-hidden").style("flex:1; min-height:0"):

            # Sidebar (fixed width)
            with ui.column().classes(
                "border-r border-gray-700 bg-gray-900/50 gap-0 h-full shrink-0 overflow-hidden"
            ).style("width:200px; max-width:200px"):
                ui.label("Connection").classes(
                    "text-xs text-gray-500 uppercase tracking-wide px-3 pt-3 pb-1"
                )
                with ui.row().classes(
                    "items-center gap-2 px-2 py-2 mx-2 bg-white/5 rounded overflow-hidden"
                ).style("max-width:180px"):
                    ui.icon("dns", size="16px").classes("text-blue-400 shrink-0")
                    with ui.column().classes("gap-0 overflow-hidden min-w-0"):
                        ui.label(client.server_name or "OPC UA Server").classes(
                            "text-xs font-medium truncate"
                        )
                        ui.label(client.endpoint).classes(
                            "font-mono text-gray-500 truncate"
                        ).style("font-size:10px")

                ui.separator().classes("my-2 mx-2")

                async def do_disconnect():
                    await client.disconnect()
                    ui.navigate.to("/")

                ui.button(
                    "Disconnect", icon="power_settings_new", on_click=do_disconnect
                ).props("flat dense size=sm color=red").classes("mx-2")

            # Main content area (fills remaining width)
            with ui.column().classes("h-full gap-0 overflow-hidden min-w-0").style("flex:1"):
                # Search bar (fixed height)
                with ui.row().classes(
                    "w-full items-center px-3 border-b border-gray-700 shrink-0 gap-1"
                ).style("height:32px; min-height:32px"):
                    ui.icon("search", size="14px").classes("text-gray-500")
                    search_input = ui.input(placeholder="Filter nodes...").props(
                        "dense borderless"
                    ).classes("flex-grow").style("font-size:12px")

                # Tree (scrollable, fills remaining height)
                with ui.scroll_area().classes("w-full").style("flex:1; min-height:0"):
                    tree_container, rebuild_tree, set_root = create_tree_view(
                        client, on_select_node=lambda nid: show_detail_dialog(nid),
                    )

        # ── Bottom bar ──
        with ui.row().classes(
            "w-full items-center gap-6 px-4 bg-gray-900 border-t border-gray-700 shrink-0"
        ).style("height:24px; min-height:24px"):
            ui.label(client.endpoint).classes("text-xs text-gray-500 font-mono")
            ui.label(f"Security: {client.security_policy}").classes("text-xs text-gray-500")
            latency_label = ui.label("Latency: ...").classes("text-xs text-gray-500")

        # ── Event handlers ──

        # Search on Enter key
        search_input.on(
            "keydown.enter",
            lambda: rebuild_tree(filter_query=search_input.value.strip().lower()),
        )

        # Latency polling (every 5s)
        async def update_latency():
            while client.connected:
                ms = await client.measure_latency()
                if ms is not None:
                    latency_label.text = f"Latency: {ms} ms"
                await asyncio.sleep(5)

        asyncio.create_task(update_latency())

        # Detail dialog — opens when a node is clicked in the tree
        async def show_detail_dialog(node_id: str):
            with ui.dialog().classes("w-full max-w-lg") as dlg, ui.card().classes("w-full p-4"):
                _container, show_details = create_detail_panel(
                    client, on_set_root=lambda nid, name: _set_root_close(dlg, nid, name),
                )
            dlg.open()
            await show_details(node_id)

        async def _set_root_close(dlg, nid, name):
            dlg.close()
            await set_root(nid, name)

        # Initial tree load
        await rebuild_tree()
