"""Node detail panel — write-focused popup with collapsible details.

Clicking a variable opens this panel in a dialog. The layout prioritizes
writing: value + write input at top, full attribute details collapsed below.
"""

import asyncio
import pyperclip
from nicegui import ui
from opguia.client import OpcuaClient
from opguia.storage import Settings
from opguia.pages.browse.write_form import create_write_form


def _copy_btn(label: ui.label):
    """Small copy-to-clipboard button."""
    btn = ui.button(icon="content_copy").props("flat dense round size=xs").classes("text-gray-600").tooltip("Copy")

    async def _copy():
        pyperclip.copy(label.text)
        btn.props("icon=check color=green")
        await asyncio.sleep(1.5)
        btn.props("icon=content_copy color=")

    btn.on("click", _copy)


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
        container.clear()
        with container:
            ui.spinner(size="sm")

        try:
            info = await client.get_node_details(node_id)
            try:
                info["_path"] = await client.get_node_path(node_id)
            except Exception:
                info["_path"] = None
        except Exception as e:
            container.clear()
            with container:
                ui.label(f"Error: {e}").classes("text-red-400 text-xs")
            return

        container.clear()
        with container:
            _render_header(info, node_id, settings, on_favorite_toggle, show_details)

            is_var = info["is_variable"]
            is_complex = info.get("is_complex", False)

            if is_var:
                _render_variable_section(info, node_id, client, writes_enabled, is_complex, show_details)

            if not is_var and on_set_root:
                _render_folder_section(info, node_id, on_set_root)

            _render_details_section(info, is_var)

    return container, show_details


def _render_header(info, node_id, settings, on_favorite_toggle, show_details):
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


def _render_variable_section(info, node_id, client, writes_enabled, is_complex, show_details):
    val = info.get("value", "—")
    val_str = str(val)
    is_error = isinstance(val, str) and val.startswith("Error:")
    writes_ok = writes_enabled() if writes_enabled else True
    can_write = info.get("writable") and not is_error and not is_complex and writes_ok

    # Current value row
    with ui.row().classes("items-center gap-2 w-full"):
        ui.label("Value:").classes("text-xs text-gray-500 shrink-0")
        if is_error:
            val_display = ui.label(val_str).classes("text-sm font-mono text-red-400 break-all")
        elif is_complex and val is None:
            val_display = ui.label("(complex — browse children)").classes(
                "text-sm font-mono text-gray-400 italic"
            )
        elif is_complex and val is not None:
            val_display = ui.label(info.get("data_type", "Struct")).classes(
                "text-sm font-mono text-blue-300"
            )
        else:
            val_display = ui.label(val_str).classes("text-sm font-mono text-green-300 break-all")
        if info.get("data_type"):
            ui.label(info["data_type"]).classes("text-xs text-gray-500 ml-auto shrink-0")

    # Decoded struct fields
    if is_complex and val is not None and not isinstance(val, (bytes, str)):
        _render_struct_fields(val)

    # Write status hints
    if not can_write and info.get("writable") and not writes_ok:
        ui.label("Enable 'Allow writes' in sidebar to write").classes("text-xs text-orange-400 italic")
    elif not can_write and not info.get("writable") and not is_complex:
        ui.label("Node is read-only (server)").classes("text-xs text-gray-600 italic")

    # Write form
    if can_write:
        create_write_form(client, node_id, val, val_display, info.get("data_type", ""))

    # Refresh button for read-only variables
    if not can_write and not is_complex:
        async def do_refresh(nid=node_id):
            await show_details(nid)
        ui.button("Refresh", icon="refresh", on_click=do_refresh).props("flat dense size=sm")


def _render_struct_fields(val):
    try:
        fields = vars(val)
    except TypeError:
        fields = {}
    if not fields:
        return
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


def _render_folder_section(info, node_id, on_set_root):
    with ui.row().classes("items-center gap-2"):
        ui.label(f"{info.get('child_count', '?')} children").classes("text-xs text-gray-500")

        async def set_root(nid=node_id, name=info["display_name"]):
            await on_set_root(nid, name)

        ui.button("Set as tree root", icon="folder_open", on_click=set_root).props("flat dense size=sm")


def _render_details_section(info, is_var):
    with ui.expansion("Details").classes("w-full").props("dense"):
        rows = [
            ("Node ID", info["node_id"]),
            ("Browse Name", info["browse_name"]),
            ("Path", " / ".join(info["_path"]) if info.get("_path") else "—"),
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

        for row_label, val in rows:
            with ui.row().classes("items-start gap-2 w-full"):
                ui.label(row_label).classes("text-xs text-gray-500 w-24 shrink-0 text-right")
                val_lbl = ui.label(str(val)).classes("text-xs font-mono break-all")
                _copy_btn(val_lbl)
