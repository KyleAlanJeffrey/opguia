"""Tree-table view — compact rows with inline Name | Value | Type | Status.

Each row is 26px tall (VSCode explorer density). Folders expand/collapse
on click, variables open the detail dialog on click. Variables with
children (complex structs) expand on click, detail on double-click.
"""

from nicegui import ui
from opguia.client import OpcuaClient

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


def create_tree_view(client: OpcuaClient, on_select_node):
    """Create the tree view. Returns (container, rebuild_fn, set_root_fn)."""

    # Current root node for the tree (None = Objects folder)
    root_state = {"node_id": None, "path": []}
    tree_container = ui.column().classes("w-full gap-0 select-none")

    async def set_root(node_id: str | None, name: str | None = None):
        """Change the tree root to a specific node (or reset to Objects)."""
        if node_id is None:
            root_state["node_id"] = None
            root_state["path"] = []
        else:
            root_state["node_id"] = node_id
            if name:
                root_state["path"].append(name)
        await rebuild_tree()

    async def rebuild_tree(filter_query: str = ""):
        """Clear and rebuild the entire tree from the current root."""
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

        spinner.delete()

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

            # Inline value (fixed width)
            val = node["value"]
            if val is not None and val != "?":
                val_text = str(val)
                if len(val_text) > 30:
                    val_text = val_text[:30] + ".."
                ui.label(val_text).classes(
                    "text-xs font-mono text-gray-200 text-right truncate"
                ).style("width:140px; flex-shrink:0")
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
            child_ct = ui.column().classes("w-full gap-0")
            exp = {"v": False}

            async def toggle(nid=node["id"], ct=child_ct, ar=arrow, ex=exp, d=depth):
                if not ex["v"]:
                    ex["v"] = True
                    ar.classes(add="rotate-90")
                    await _load(ct, nid, d + 1, fq)
                else:
                    ex["v"] = False
                    ar.classes(remove="rotate-90")
                    ct.clear()

            row.on("click", lambda nid=node["id"]: toggle(nid))
            row.on("dblclick", lambda nid=node["id"]: on_select_node(nid))
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
        exp = {"v": False}
        row = _make_row(indent)
        with row:
            arrow = ui.icon("chevron_right", size="14px").classes("text-gray-500 transition-transform")
            ui.icon("folder", size="14px").classes("text-yellow-500")
            ui.label(node["name"]).classes("text-xs font-medium")

        child_ct = ui.column().classes("w-full gap-0")

        async def toggle(nid=node["id"], ct=child_ct, ar=arrow, ex=exp, d=depth):
            if not ex["v"]:
                ex["v"] = True
                ar.classes(add="rotate-90")
                await _load(ct, nid, d + 1, fq)
            else:
                ex["v"] = False
                ar.classes(remove="rotate-90")
                ct.clear()

        row.on("click", lambda nid=node["id"]: toggle(nid))
        row.on("dblclick", lambda nid=node["id"]: on_select_node(nid))

    return tree_container, rebuild_tree, set_root


def _make_row(indent: int):
    """Create a compact tree row container with proper indentation."""
    return ui.row().classes(
        "items-center gap-1.5 px-3 hover:bg-white/5 cursor-pointer w-full"
    ).style(f"height:{_ROW_H}; padding-left:{indent}px")
