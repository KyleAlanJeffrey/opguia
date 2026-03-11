"""Browse page — main screen after connecting.

Layout (all flexbox, no calc):
  ┌─────────────────────────────────┐
  │ Top bar (40px, shrink-0)        │
  ├────────┬────────────────────────┤
  │Sidebar │ Search bar (32px)      │  ← middle row (flex:1)
  │(200px) │ Tree (flex:1 scroll)   │
  │        │ Watch panel (bottom)   │
  ├────────┴────────────────────────┤
  │ Bottom bar (24px, shrink-0)     │
  └─────────────────────────────────┘
"""

import asyncio
import json
from pathlib import Path
from nicegui import app, ui
from opguia.client import OpcuaClient
from opguia.settings import Settings
from opguia.components.tree_view import create_tree_view
from opguia.components.detail_panel import create_detail_panel
from opguia.components.watch_panel import create_watch_panel


def register(client: OpcuaClient, settings: Settings):
    @ui.page("/browse")
    async def browse_page():
        ui.dark_mode().enable()
        if not client.connected:
            ui.navigate.to("/")
            return

        # Ensure profile exists and is active
        settings.ensure_profile(client.endpoint, client.server_name)
        settings.set_active(client.endpoint)

        # Override NiceGUI defaults — full-height flex column, no padding
        ui.query("body").style("margin:0; overflow:hidden")
        ui.query(".nicegui-content").classes("w-full h-screen").style(
            "display:flex; flex-direction:column; padding:0; gap:0"
        )

        # ── Top bar ──
        with ui.row().classes(
            "w-full items-center justify-between px-4 bg-gray-900 border-b border-gray-700 shrink-0"
        ).style("height:40px; min-height:40px"):
            with ui.row().classes("items-center gap-2"):
                ui.image("/static/favicon.svg").classes("w-5 h-5")
                ui.label("OPGuia").classes("text-sm font-bold")
            with ui.row().classes("items-center gap-3"):
                profile = settings.active_profile
                profile_name = profile["name"] if profile else client.server_name
                if profile_name:
                    ui.label(f"Profile: {profile_name}").classes("text-xs text-gray-300")
                ui.badge("Connected", color="green").props("rounded").classes("text-xs")

        # ── Middle: sidebar + main content ──
        with ui.row().classes("w-full no-wrap overflow-hidden").style("flex:1; min-height:0"):

            # Sidebar (fixed width, vertical scroll only)
            with ui.column().classes(
                "border-r border-gray-700 bg-gray-900/50 h-full shrink-0 gap-0"
            ).style("width:280px; min-width:280px; max-width:280px; overflow-y:auto; overflow-x:hidden"):
                ui.label("Connection").classes(
                    "text-xs text-gray-500 uppercase tracking-wide px-3 pt-3 pb-1"
                )
                with ui.row().classes(
                    "items-center gap-2 px-2 py-2 mx-2 bg-white/5 rounded overflow-hidden"
                ):
                    ui.icon("dns", size="16px").classes("text-blue-400 shrink-0")
                    with ui.column().classes("gap-0 overflow-hidden min-w-0"):
                        ui.label(client.server_name or "OPC UA Server").classes(
                            "text-xs font-medium truncate"
                        )
                        ui.label(client.endpoint).classes(
                            "font-mono text-gray-500 truncate"
                        ).style("font-size:10px")

                ui.separator().classes("my-2 mx-2")

                # Tree root
                ui.label("Tree Root").classes(
                    "text-xs text-gray-500 uppercase tracking-wide px-3 pt-2 pb-1"
                )
                root_ct = ui.column().classes("w-full gap-0 px-2")

                def render_root_section():
                    root_ct.clear()
                    path = settings.tree_root_path
                    with root_ct:
                        if path:
                            with ui.row().classes(
                                "items-center gap-1 w-full bg-white/5 rounded px-2 py-1"
                            ):
                                ui.icon("folder", size="12px").classes("text-yellow-500 shrink-0")
                                ui.label(" / ".join(path)).classes(
                                    "text-xs truncate flex-grow"
                                )

                                async def _reset_root():
                                    await set_root(None)
                                    render_root_section()

                                ui.button(icon="home", on_click=_reset_root).props(
                                    "flat dense round size=xs"
                                ).classes("text-gray-400 shrink-0").tooltip("Reset to Objects")
                        else:
                            ui.label("Objects (default)").classes("text-xs text-gray-600 px-1")

                render_root_section()

                ui.separator().classes("my-2 mx-2")

                # Settings
                ui.label("Settings").classes(
                    "text-xs text-gray-500 uppercase tracking-wide px-3 pt-2 pb-1"
                )
                with ui.row().classes("items-center gap-2 px-3"):
                    write_switch = ui.switch(
                        "Allow writes", value=settings.allow_writes,
                    ).props("dense size=sm color=orange").classes("text-xs")

                    def on_write_toggle(e):
                        settings.allow_writes = e.args

                    write_switch.on("update:model-value", on_write_toggle)

                ui.separator().classes("my-2 mx-2")

                # Watched variables
                ui.label("Watched").classes(
                    "text-xs text-gray-500 uppercase tracking-wide px-3 pt-2 pb-1"
                )
                watched_ct = ui.column().classes("w-full gap-0 px-1")

                def render_watched_sidebar():
                    watched_ct.clear()
                    watched = settings.watched
                    with watched_ct:
                        if not watched:
                            ui.label("No watched vars").classes("text-xs text-gray-600 px-2")
                        for item in watched:
                            with ui.row().classes(
                                "items-center gap-1 w-full hover:bg-white/5 rounded px-2 cursor-pointer"
                            ).style("height:24px") as wrow:
                                ui.icon("visibility", size="12px").classes("text-blue-400 shrink-0")
                                ui.label(item["name"]).classes("text-xs truncate flex-grow")

                                def remove_watch(nid=item["node_id"]):
                                    settings.remove_watched(nid)
                                    render_watched_sidebar()
                                    render_watch()

                                ui.button(icon="close", on_click=remove_watch).props(
                                    "flat dense round size=xs"
                                ).classes("text-gray-600 shrink-0").style("opacity:0.5")

                            async def open_watch(nid=item["node_id"]):
                                await show_detail_dialog(nid)
                            wrow.on("click", open_watch)

                render_watched_sidebar()

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
                    collapse_btn = ui.button(icon="unfold_less", on_click=lambda: collapse_all()).props(
                        "flat dense round size=sm"
                    ).classes("text-gray-400").tooltip("Collapse all")
                    expand_btn = ui.button(icon="unfold_more", on_click=lambda: expand_all()).props(
                        "flat dense round size=sm"
                    ).classes("text-gray-400").tooltip("Expand all (1 level)")
                    export_btn = ui.button(icon="download").props(
                        "flat dense round size=sm"
                    ).classes("text-gray-400").tooltip("Export tree as JSON")

                # Tree (scrollable, fills remaining height)
                def _on_root_changed(node_id, path):
                    settings.tree_root = node_id
                    settings.tree_root_path = path
                    settings.tree_expanded = []
                    render_root_section()

                def _on_expand_changed(node_id, expanded):
                    if expanded is False and node_id is None:
                        # Full clear from collapse_all
                        settings.tree_expanded = []
                    elif expanded:
                        settings.add_tree_expanded(node_id)
                    else:
                        settings.remove_tree_expanded(node_id)

                with ui.scroll_area().classes("w-full").style("flex:1; min-height:0"):
                    tree_container, rebuild_tree, set_root, poll_values, export_tree, collapse_all, expand_all = create_tree_view(
                        client, on_select_node=lambda nid: show_detail_dialog(nid),
                        on_root_changed=_on_root_changed,
                        initial_root=settings.tree_root,
                        initial_path=settings.tree_root_path,
                        initial_expanded=settings.tree_expanded,
                        on_expand_changed=_on_expand_changed,
                    )

                async def _do_export():
                    # Native save dialog via pywebview
                    result = await app.native.main_window.create_file_dialog(
                        dialog_type=30,  # SAVE
                        save_filename="tree.json",
                        file_types=("JSON files (*.json)",),
                    )
                    if not result:
                        return
                    path = result if isinstance(result, str) else result[0]
                    export_btn.props("loading")
                    try:
                        tree_data = await export_tree()
                        content = json.dumps(tree_data, indent=2, ensure_ascii=False)
                        Path(path).write_text(content, encoding="utf-8")
                        ui.notify(f"Saved to {path}", type="positive")
                    except Exception as e:
                        ui.notify(f"Export failed: {e}", type="negative")
                    finally:
                        export_btn.props(remove="loading")

                export_btn.on("click", _do_export)

                # Watch panel (bottom, collapsible)
                has_watched = bool(settings.watched)
                with ui.expansion(
                    "Watch", value=has_watched,
                ).classes("w-full border-t border-gray-700").props("dense header-class='text-xs bg-gray-900'"):
                    with ui.scroll_area().style("max-height:200px"):
                        watch_ct, render_watch, poll_watch = create_watch_panel(
                            client, settings,
                            on_select_node=lambda nid: show_detail_dialog(nid),
                            on_watch_changed=lambda: render_watched_sidebar(),
                        )

                render_watch()

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

        # Latency polling (every 5s) + value polling (every 2s)
        async def update_latency():
            while client.connected:
                ms = await client.measure_latency()
                if ms is not None:
                    latency_label.text = f"Latency: {ms} ms"
                await asyncio.sleep(5)

        async def update_values():
            while client.connected:
                await asyncio.sleep(2)
                try:
                    await poll_values()
                    await poll_watch()
                except Exception:
                    pass

        asyncio.create_task(update_latency())
        asyncio.create_task(update_values())

        # Pre-create detail dialog (avoids slot context issues on Windows)
        with ui.dialog().classes("w-full max-w-lg") as detail_dlg:
            with ui.card().classes("w-full p-4"):
                _detail_ct, show_details = create_detail_panel(
                    client,
                    on_set_root=lambda nid, name: _set_root_close(nid, name),
                    writes_enabled=lambda: settings.allow_writes,
                    on_favorite_toggle=lambda: _on_watch_changed(),
                    settings=settings,
                )

        async def show_detail_dialog(node_id: str):
            detail_dlg.open()
            await show_details(node_id)

        def _on_watch_changed():
            render_watched_sidebar()
            render_watch()

        async def _set_root_close(nid, name):
            detail_dlg.close()
            await set_root(nid, name)

        # Initial tree load
        await rebuild_tree()
