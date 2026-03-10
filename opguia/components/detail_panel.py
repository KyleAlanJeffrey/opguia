"""Node detail panel — write-focused popup with collapsible details.

Clicking a variable opens this panel in a dialog. The layout prioritizes
writing: value + write input at top, full attribute details collapsed below.
"""

import asyncio
from nicegui import ui
from opguia.client import OpcuaClient
from opguia.settings import Settings


def create_detail_panel(
    client: OpcuaClient,
    on_set_root=None,
    writes_enabled=None,
    on_favorite_toggle=None,
    settings: Settings | None = None,
):
    """Create the detail panel. Returns (container, show_details_fn).

    writes_enabled: callable returning bool — write form only appears when True.
    on_favorite_toggle: callback when a favorite is added/removed.
    settings: Settings instance for favorite management.
    """
    container = ui.column().classes("w-full gap-2")

    async def show_details(node_id: str):
        """Fetch node info and render the panel contents."""
        container.clear()
        with container:
            ui.spinner(size="sm")

        try:
            info = await client.get_node_details(node_id)
        except Exception as e:
            container.clear()
            with container:
                ui.label(f"Error: {e}").classes("text-red-400 text-xs")
            return

        container.clear()
        with container:
            # ── Header: name + node class + favorite toggle ──
            with ui.row().classes("items-center gap-2 w-full"):
                ui.label(info["display_name"]).classes("text-lg font-bold")
                ui.label(info.get("node_class", "")).classes("text-xs text-gray-500")
                if settings:
                    is_fav = settings.is_favorite(node_id)
                    fav_icon = "star" if is_fav else "star_border"
                    fav_color = "text-yellow-500" if is_fav else "text-gray-500"

                    async def toggle_fav(nid=node_id, name=info["display_name"]):
                        if settings.is_favorite(nid):
                            settings.remove_favorite(nid)
                        else:
                            settings.add_favorite(name, nid)
                        if on_favorite_toggle:
                            on_favorite_toggle()
                        await show_details(nid)

                    ui.button(icon=fav_icon, on_click=toggle_fav).props(
                        "flat dense round size=sm"
                    ).classes(fav_color + " ml-auto")

            is_var = info["is_variable"]
            is_complex = info.get("is_complex", False)

            # ── Variable-specific content ──
            if is_var:
                val = info.get("value", "—")
                val_str = str(val)
                is_error = isinstance(val, str) and val.startswith("Error:")
                writes_ok = writes_enabled() if writes_enabled else True
                can_write = info.get("writable") and not is_error and not is_complex and writes_ok

                # Current value + data type
                with ui.row().classes("items-center gap-2 w-full"):
                    ui.label("Value:").classes("text-xs text-gray-500 shrink-0")
                    if is_error:
                        ui.label(val_str).classes("text-sm font-mono text-red-400 break-all")
                    elif is_complex and val is None:
                        ui.label("(complex — browse children)").classes(
                            "text-sm font-mono text-gray-400 italic"
                        )
                    elif is_complex and val is not None:
                        ui.label(info.get("data_type", "Struct")).classes(
                            "text-sm font-mono text-blue-300"
                        )
                    else:
                        ui.label(val_str).classes("text-sm font-mono text-green-300 break-all")
                    if info.get("data_type"):
                        ui.label(info["data_type"]).classes("text-xs text-gray-500 ml-auto shrink-0")

                # Show decoded struct fields
                if is_complex and val is not None and not isinstance(val, (bytes, str)):
                    try:
                        fields = vars(val)
                    except TypeError:
                        fields = {}
                    if fields:
                        with ui.column().classes("w-full gap-0 ml-4 border-l border-gray-700 pl-3"):
                            for fname, fval in fields.items():
                                if fname.startswith("_"):
                                    continue
                                fval_str = str(fval)
                                if len(fval_str) > 80:
                                    fval_str = fval_str[:80] + ".."
                                with ui.row().classes("items-start gap-2 w-full"):
                                    ui.label(fname).classes("text-xs text-gray-400 shrink-0")
                                    ui.label(fval_str).classes("text-xs font-mono text-gray-200 break-all")

                # Write form (only for writable, non-error, non-complex variables)
                if can_write:
                    write_status = ui.label("").classes("text-xs")
                    with ui.row().classes("items-center gap-2 w-full"):
                        write_input = ui.input(value=val_str).props(
                            "dense outlined"
                        ).classes("flex-grow font-mono text-sm")

                        async def do_write(nid=node_id, inp=write_input, st=write_status):
                            st.text = "Writing..."
                            st.classes(remove="text-red-400 text-green-400")
                            try:
                                await client.write_value(nid, inp.value)
                                st.text = "OK"
                                st.classes(add="text-green-400")
                                await asyncio.sleep(0.5)
                                await show_details(nid)  # refresh after write
                            except Exception as e:
                                st.text = str(e)
                                st.classes(add="text-red-400")

                        ui.button("Write", on_click=do_write).props("dense size=sm color=primary")

                # Refresh for read-only variables
                if not can_write and not is_complex:
                    async def do_refresh(nid=node_id):
                        await show_details(nid)
                    ui.button("Refresh", icon="refresh", on_click=do_refresh).props("flat dense size=sm")

            # ── Folder: set as root ──
            if not is_var and on_set_root:
                with ui.row().classes("items-center gap-2"):
                    ui.label(f"{info.get('child_count', '?')} children").classes("text-xs text-gray-500")

                    async def set_root(nid=node_id, name=info["display_name"]):
                        await on_set_root(nid, name)

                    ui.button("Set as tree root", icon="folder_open", on_click=set_root).props(
                        "flat dense size=sm"
                    )

            # ── Collapsible details ──
            with ui.expansion("Details").classes("w-full").props("dense"):
                rows = [
                    ("Node ID", info["node_id"]),
                    ("Browse Name", info["browse_name"]),
                ]
                if is_var:
                    rows += [
                        ("Data Type", info.get("data_type", "—")),
                        ("Variant Type", info.get("variant_type", "—")),
                        ("Value Rank", info.get("value_rank", "—")),
                        ("Access Level", info.get("access_level", "—")),
                        ("User Access", info.get("user_access_level", "—")),
                        ("Status", info.get("status_code", "—")),
                        ("Source Time", info.get("source_timestamp", "—")),
                        ("Server Time", info.get("server_timestamp", "—")),
                    ]
                if info.get("description"):
                    rows.append(("Description", info["description"]))

                for label, val in rows:
                    with ui.row().classes("items-start gap-2 w-full"):
                        ui.label(label).classes("text-xs text-gray-500 w-24 shrink-0 text-right")
                        ui.label(str(val)).classes("text-xs font-mono break-all")

    return container, show_details
