"""Shared node row rendering — reusable tree-style rows for OPC UA nodes.

Provides render_node_list() which renders a list of browse_children results
as expandable tree rows. Used by both the main tree view and the watch panel.
"""

import datetime
from nicegui import ui
from opguia.client import OpcuaClient

# Status dot colors
STATUS_COLORS = {"good": "text-green-500", "warning": "text-yellow-400", "bad": "text-red-500"}

# Per-type icon and color for variable rows
TYPE_ICONS = {
    "Boolean": "toggle_on",
    "Float": "tag", "Double": "tag",
    "Int16": "tag", "Int32": "tag", "Int64": "tag",
    "UInt16": "tag", "UInt32": "tag", "UInt64": "tag",
    "Byte": "tag", "SByte": "tag",
    "String": "text_fields",
}
TYPE_COLORS = {
    "Boolean": "text-green-500",
    "Float": "text-blue-400", "Double": "text-blue-400",
    "Int16": "text-orange-400", "Int32": "text-orange-400", "Int64": "text-orange-400",
    "UInt16": "text-orange-400", "UInt32": "text-orange-400", "UInt64": "text-orange-400",
    "Byte": "text-orange-400", "SByte": "text-orange-400",
    "String": "text-teal-400",
}

ROW_H = "26px"


def format_val(val, max_len=30) -> str:
    """Format a value for inline display, handling complex types."""
    if val is None:
        return ""
    if hasattr(val, "ua_types"):
        parts = []
        for field_name, _ in val.ua_types:
            fv = getattr(val, field_name, None)
            parts.append(f"{field_name}={fv}")
        text = "{" + ", ".join(parts) + "}"
    elif hasattr(val, "Body") and not isinstance(val, (str, bytes)):
        text = f"[{type(val).__name__}]"
    elif isinstance(val, list):
        text = f"[{len(val)} items]" if len(val) > 3 else str(val)
    else:
        text = str(val)
    if len(text) > max_len:
        text = text[:max_len] + ".."
    return text


def serialize(value):
    """Convert a value to a JSON-serializable form."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): serialize(v) for k, v in value.items()}
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def make_row(indent: int):
    """Create a compact tree row container with proper indentation."""
    return ui.row().classes(
        "items-center gap-1.5 px-3 hover:bg-white/5 cursor-pointer w-full"
    ).style(f"height:{ROW_H}; padding-left:{indent}px")


def render_node_list(
    client: OpcuaClient,
    container,
    children: list[dict],
    depth: int = 0,
    on_select_node=None,
    value_labels: dict | None = None,
):
    """Render a list of OPC UA nodes as tree-style rows inside a container.

    Args:
        client: OPC UA client for browsing children on expand.
        container: NiceGUI container element to render into.
        children: List of node dicts from browse_children().
        depth: Indentation depth (each level = 20px).
        on_select_node: Callback(node_id) for clicking a node.
        value_labels: Optional dict to track {node_id: label} for polling.
    """
    if value_labels is None:
        value_labels = {}

    for node in children:
        with container:
            _render_node(client, node, depth, on_select_node, value_labels)


def _render_node(client, node, depth, on_select_node, value_labels):
    """Render a single node row."""
    indent = depth * 20
    has_ch = node.get("has_children", False)

    if node["is_variable"]:
        _render_variable(client, node, indent, has_ch, depth, on_select_node, value_labels)
    elif node.get("is_method"):
        _render_method(node, indent)
    else:
        _render_folder(client, node, indent, depth, on_select_node, value_labels)


def _render_variable(client, node, indent, has_ch, depth, on_select_node, value_labels):
    """Render a variable row: Name | Value | Type | Status dot."""
    dt = node.get("data_type", "")
    icon = TYPE_ICONS.get(dt, "data_object")
    icon_color = TYPE_COLORS.get(dt, "text-gray-400")
    st_color = STATUS_COLORS.get(node.get("status", "good"), "text-gray-500")

    row = make_row(indent)
    with row:
        if has_ch:
            arrow = ui.icon("chevron_right", size="14px").classes("text-gray-500 transition-transform")
        else:
            ui.element("div").style("width:14px; flex-shrink:0")

        ui.icon(icon, size="14px").classes(icon_color)
        ui.label(node["name"]).classes("text-xs font-medium truncate").style("min-width:120px; flex:1")

        val = node.get("value")
        if val is not None and val != "?":
            val_text = format_val(val, 30)
            val_lbl = ui.label(val_text).classes(
                "text-xs font-mono text-gray-200 text-right truncate"
            ).style("width:140px; flex-shrink:0")
            value_labels[node["id"]] = val_lbl
        else:
            ui.element("div").style("width:140px; flex-shrink:0")

        if dt:
            ui.label(dt).classes("text-xs text-gray-500 text-right truncate").style(
                "width:100px; flex-shrink:0"
            )
        else:
            ui.element("div").style("width:100px; flex-shrink:0")

        ui.icon("circle", size="8px").classes(st_color).style("width:20px; flex-shrink:0")

    if has_ch:
        nid = node["id"]
        child_ct = ui.column().classes("w-full gap-0")
        exp = {"v": False}

        async def toggle(nid=nid, ct=child_ct, ar=arrow, ex=exp, d=depth):
            if not ex["v"]:
                ex["v"] = True
                ar.classes(add="rotate-90")
                await _load(client, ct, nid, d + 1, on_select_node, value_labels)
            else:
                ex["v"] = False
                ar.classes(remove="rotate-90")
                # Remove child value labels from tracking
                ct.clear()

        row.tooltip("Double-click for details")
        row.on("click", lambda nid=nid: toggle(nid))
        if on_select_node:
            row.on("dblclick", lambda nid=nid: on_select_node(nid))
    else:
        if on_select_node:
            row.on("click", lambda nid=node["id"]: on_select_node(nid))


def _render_method(node, indent):
    """Render a method row (non-interactive, dimmed)."""
    row = make_row(indent)
    with row:
        ui.element("div").style("width:14px; flex-shrink:0")
        ui.icon("settings", size="14px").classes("text-purple-400")
        ui.label(node["name"]).classes("text-xs text-gray-500")


def _render_folder(client, node, indent, depth, on_select_node, value_labels):
    """Render a folder/object row with expand/collapse."""
    nid = node["id"]
    exp = {"v": False}
    row = make_row(indent)
    with row:
        arrow = ui.icon("chevron_right", size="14px").classes("text-gray-500 transition-transform")
        ui.icon("folder", size="14px").classes("text-yellow-500")
        ui.label(node["name"]).classes("text-xs font-medium")
    row.tooltip("Double-click for details")

    child_ct = ui.column().classes("w-full gap-0")

    async def toggle(nid=nid, ct=child_ct, ar=arrow, ex=exp, d=depth):
        if not ex["v"]:
            ex["v"] = True
            ar.classes(add="rotate-90")
            await _load(client, ct, nid, d + 1, on_select_node, value_labels)
        else:
            ex["v"] = False
            ar.classes(remove="rotate-90")
            _remove_child_labels(ct, value_labels)
            ct.clear()

    row.on("click", lambda nid=nid: toggle(nid))
    if on_select_node:
        row.on("dblclick", lambda nid=nid: on_select_node(nid))


async def _load(client, container, node_id, depth, on_select_node, value_labels):
    """Load children of a node into a container."""
    with container:
        spinner = ui.spinner(size="xs").classes("ml-6")
    try:
        children = await client.browse_children(node_id)
    except Exception as e:
        container.clear()
        with container:
            ui.label(f"Error: {e}").classes("text-red-400 text-xs ml-6")
        return
    try:
        spinner.delete()
    except (ValueError, Exception):
        pass

    if not children:
        with container:
            ui.label("(empty)").classes("text-gray-600").style(
                f"font-size:11px; padding-left:{depth * 20 + 30}px; height:{ROW_H}; line-height:{ROW_H}"
            )
        return

    for node in children:
        with container:
            _render_node(client, node, depth, on_select_node, value_labels)


