"""Tree-table view — compact rows with inline Name | Value | Type | Status.

Each row is 26px tall (VSCode explorer density). Folders expand/collapse
on click, variables open the detail dialog on click. Variables with
children (complex structs) expand on click, detail on double-click.
"""

import datetime

from nicegui import ui
from opguia.client import OpcuaClient


def _serialize(value):
    """Convert a value to a JSON-serializable form."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, bytes):
        return value.hex()
    return str(value)

# Status dot colors
_STATUS_COLORS = {"good": "text-green-500", "warning": "text-yellow-400", "bad": "text-red-500"}

# Per-type icon and color for variable rows
_TYPE_ICONS = {
    "Boolean": "toggle_on",
    "Float": "tag", "Double": "tag",
    "Int16": "tag", "Int32": "tag", "Int64": "tag",
    "UInt16": "tag", "UInt32": "tag", "UInt64": "tag",
    "Byte": "tag", "SByte": "tag",
    "String": "text_fields",
}
_TYPE_COLORS = {
    "Boolean": "text-green-500",
    "Float": "text-blue-400", "Double": "text-blue-400",
    "Int16": "text-orange-400", "Int32": "text-orange-400", "Int64": "text-orange-400",
    "UInt16": "text-orange-400", "UInt32": "text-orange-400", "UInt64": "text-orange-400",
    "Byte": "text-orange-400", "SByte": "text-orange-400",
    "String": "text-teal-400",
}

_ROW_H = "26px"


def create_tree_view(client: OpcuaClient, on_select_node, on_root_changed=None,
                     initial_root=None, initial_path=None,
                     initial_expanded=None, on_expand_changed=None):
    """Create the tree view. Returns (container, rebuild_fn, set_root_fn, poll_values_fn)."""

    # Current root node for the tree (None = Objects folder)
    root_state = {"node_id": initial_root, "path": list(initial_path or [])}
    # Set of node IDs that should be expanded on rebuild
    _expanded: set[str] = set(initial_expanded or [])
    tree_container = ui.column().classes("w-full gap-0 select-none")

    # Track rendered variable value labels for polling: {node_id: label_element}
    _value_labels: dict[str, ui.label] = {}

    async def set_root(node_id: str | None, name: str | None = None):
        """Change the tree root to a specific node (or reset to Objects)."""
        _expanded.clear()
        if node_id is None:
            root_state["node_id"] = None
            root_state["path"] = []
        else:
            root_state["node_id"] = node_id
            if name:
                root_state["path"].append(name)
        if on_root_changed:
            on_root_changed(root_state["node_id"], list(root_state["path"]))
        await rebuild_tree()

    async def poll_values():
        """Re-read all visible variable values and update their labels."""
        if not _value_labels or not client.connected:
            return
        node_ids = list(_value_labels.keys())
        for nid in node_ids:
            lbl = _value_labels.get(nid)
            if lbl is None:
                continue
            try:
                val = await client.read_value(nid)
                val_text = str(val) if val is not None else ""
                if len(val_text) > 30:
                    val_text = val_text[:30] + ".."
                lbl.text = val_text
            except Exception:
                pass

    async def rebuild_tree(filter_query: str = ""):
        """Clear and rebuild the entire tree from the current root."""
        _value_labels.clear()
        tree_container.clear()
        with tree_container:
            # Root row — always starts expanded
            root_expanded = {"value": True}
            root_row = _make_row(0)
            with root_row:
                root_arrow = ui.icon("expand_more", size="14px").classes("text-gray-500")
                ui.icon("folder", size="14px").classes("text-blue-300")
                label = "Objects"
                if root_state["path"]:
                    label += " / " + " / ".join(root_state["path"])
                ui.label(label).classes("text-xs font-medium")

            root_children = ui.column().classes("w-full gap-0")

            async def toggle_root():
                if root_expanded["value"]:
                    root_expanded["value"] = False
                    root_arrow.props("name=chevron_right")
                    root_children.clear()
                else:
                    root_expanded["value"] = True
                    root_arrow.props("name=expand_more")
                    await _load(root_children, root_state["node_id"], 1, filter_query)

            root_row.on("click", lambda: toggle_root())
            # Load children immediately
            await _load(root_children, root_state["node_id"], 1, filter_query)

    async def _load(container, node_id, depth, fq):
        """Load children of a node into a container element."""
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

        # Apply name filter
        if fq:
            children = [c for c in children if _matches(c, fq)]

        if not children:
            with container:
                ui.label("(empty)").classes("text-gray-600").style(
                    f"font-size:11px; padding-left:{depth * 20 + 30}px; height:{_ROW_H}; line-height:{_ROW_H}"
                )
            return

        for node in children:
            with container:
                _render_node(node, depth, fq)

    def _matches(node, fq):
        """Filter match: supports dot-separated partial matching (e.g. 'drive.speed')."""
        name = node["name"].lower()
        return all(part in name for part in fq.split("."))

    def _render_node(node, depth, fq):
        """Render a single tree row based on node type."""
        indent = depth * 20
        has_ch = node.get("has_children", False)

        if node["is_variable"]:
            _render_variable(node, indent, has_ch, depth, fq)
        elif node.get("is_method"):
            _render_method(node, indent)
        else:
            _render_folder(node, indent, depth, fq)

    def _render_variable(node, indent, has_ch, depth, fq):
        """Render a variable row: Name | Value | Type | Status dot."""
        dt = node.get("data_type", "")
        icon = _TYPE_ICONS.get(dt, "data_object")
        icon_color = _TYPE_COLORS.get(dt, "text-gray-400")
        st_color = _STATUS_COLORS.get(node.get("status", "good"), "text-gray-500")

        row = _make_row(indent)
        with row:
            # Expand arrow (if has children) or spacer
            if has_ch:
                arrow = ui.icon("chevron_right", size="14px").classes("text-gray-500 transition-transform")
            else:
                ui.element("div").style("width:14px; flex-shrink:0")

            # Type icon
            ui.icon(icon, size="14px").classes(icon_color)

            # Name (flexible width)
            ui.label(node["name"]).classes("text-xs font-medium truncate").style("min-width:120px; flex:1")

            # Inline value (fixed width) — tracked for polling
            val = node["value"]
            if val is not None and val != "?":
                val_text = str(val)
                if len(val_text) > 30:
                    val_text = val_text[:30] + ".."
                val_lbl = ui.label(val_text).classes(
                    "text-xs font-mono text-gray-200 text-right truncate"
                ).style("width:140px; flex-shrink:0")
                _value_labels[node["id"]] = val_lbl
            else:
                ui.element("div").style("width:140px; flex-shrink:0")

            # Data type label (fixed width)
            if dt:
                ui.label(dt).classes("text-xs text-gray-500 text-right truncate").style(
                    "width:100px; flex-shrink:0"
                )
            else:
                ui.element("div").style("width:100px; flex-shrink:0")

            # Status dot
            ui.icon("circle", size="8px").classes(st_color).style("width:20px; flex-shrink:0")

        # Click behavior depends on whether the variable has expandable children
        if has_ch:
            nid = node["id"]
            should_expand = nid in _expanded
            child_ct = ui.column().classes("w-full gap-0")
            exp = {"v": should_expand}

            if should_expand:
                arrow.classes(add="rotate-90")

            async def toggle(nid=nid, ct=child_ct, ar=arrow, ex=exp, d=depth):
                if not ex["v"]:
                    ex["v"] = True
                    ar.classes(add="rotate-90")
                    _expanded.add(nid)
                    if on_expand_changed:
                        on_expand_changed(nid, True)
                    await _load(ct, nid, d + 1, fq)
                else:
                    ex["v"] = False
                    ar.classes(remove="rotate-90")
                    _expanded.discard(nid)
                    if on_expand_changed:
                        on_expand_changed(nid, False)
                    ct.clear()

            row.tooltip("Double-click for details")
            row.on("click", lambda nid=nid: toggle(nid))
            row.on("dblclick", lambda nid=nid: on_select_node(nid))

            if should_expand:
                async def auto_load_var(ct=child_ct, nid_=nid, d=depth):
                    await _load(ct, nid_, d + 1, fq)
                ui.timer(0, auto_load_var, once=True)
        else:
            # Simple variable — click opens detail dialog
            row.on("click", lambda nid=node["id"]: on_select_node(nid))

    def _render_method(node, indent):
        """Render a method row (non-interactive, dimmed)."""
        row = _make_row(indent)
        with row:
            ui.element("div").style("width:14px; flex-shrink:0")
            ui.icon("settings", size="14px").classes("text-purple-400")
            ui.label(node["name"]).classes("text-xs text-gray-500")

    def _render_folder(node, indent, depth, fq):
        """Render a folder/object row with expand/collapse."""
        nid = node["id"]
        should_expand = nid in _expanded
        exp = {"v": should_expand}
        row = _make_row(indent)
        with row:
            arrow = ui.icon(
                "chevron_right" if not should_expand else "expand_more",
                size="14px",
            ).classes("text-gray-500 transition-transform")
            if should_expand:
                arrow.classes(add="rotate-90")
            ui.icon("folder", size="14px").classes("text-yellow-500")
            ui.label(node["name"]).classes("text-xs font-medium")
        row.tooltip("Double-click for details")

        child_ct = ui.column().classes("w-full gap-0")

        async def toggle(nid=nid, ct=child_ct, ar=arrow, ex=exp, d=depth):
            if not ex["v"]:
                ex["v"] = True
                ar.classes(add="rotate-90")
                _expanded.add(nid)
                if on_expand_changed:
                    on_expand_changed(nid, True)
                await _load(ct, nid, d + 1, fq)
            else:
                ex["v"] = False
                ar.classes(remove="rotate-90")
                _expanded.discard(nid)
                if on_expand_changed:
                    on_expand_changed(nid, False)
                ct.clear()

        row.on("click", lambda nid=nid: toggle(nid))
        row.on("dblclick", lambda nid=nid: on_select_node(nid))

        # Auto-expand if this node was previously expanded
        if should_expand:
            async def auto_load(ct=child_ct, nid_=nid, d=depth):
                await _load(ct, nid_, d + 1, fq)
            ui.timer(0, auto_load, once=True)

    async def collapse_all():
        """Collapse all expanded nodes — just rebuild the tree from scratch."""
        _expanded.clear()
        if on_expand_changed:
            on_expand_changed(None, False)  # signal full clear
        await rebuild_tree()

    async def expand_all():
        """Expand all nodes one level deep from the current root."""
        _value_labels.clear()
        tree_container.clear()
        try:
            children = await client.browse_children(root_state["node_id"])
        except Exception:
            await rebuild_tree()
            return
        expandable_ids = [c["id"] for c in children if c.get("has_children")]
        for nid in expandable_ids:
            _expanded.add(nid)
            if on_expand_changed:
                on_expand_changed(nid, True)
        await rebuild_tree()

    async def export_tree() -> dict:
        """Export the full tree recursively as a JSON-serializable dict."""
        import asyncio as _aio

        async def _export_node(node_id, name="Objects"):
            entry = {"name": name, "node_id": node_id, "children": []}
            try:
                children = await client.browse_children(node_id)
            except Exception:
                return entry

            # Build child entries and kick off sub-tree fetches in parallel
            expandable = []  # (index, cid, child_name)
            for child in children:
                cid = child["id"]
                child_entry = {
                    "name": child["name"],
                    "node_id": cid,
                    "node_class": child.get("node_class", ""),
                }
                if child["is_variable"]:
                    child_entry["data_type"] = child.get("data_type", "")
                    child_entry["value"] = _serialize(child.get("value"))
                    child_entry["status"] = child.get("status", "")
                    child_entry["writable"] = child.get("writable", False)
                entry["children"].append(child_entry)
                if child.get("has_children"):
                    expandable.append((len(entry["children"]) - 1, cid, child["name"]))

            if expandable:
                subs = await _aio.gather(
                    *[_export_node(cid, cname) for _, cid, cname in expandable]
                )
                for (idx, _, _), sub in zip(expandable, subs):
                    entry["children"][idx]["children"] = sub["children"]

            return entry

        root_name = "Objects"
        if root_state["path"]:
            root_name += " / " + " / ".join(root_state["path"])
        return await _export_node(root_state["node_id"], root_name)

    return tree_container, rebuild_tree, set_root, poll_values, export_tree, collapse_all, expand_all


def _make_row(indent: int):
    """Create a compact tree row container with proper indentation."""
    return ui.row().classes(
        "items-center gap-1.5 px-3 hover:bg-white/5 cursor-pointer w-full"
    ).style(f"height:{_ROW_H}; padding-left:{indent}px")
