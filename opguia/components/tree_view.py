"""Address space tree view — matches the visual design reference."""

from nicegui import ui
from opguia.client import OpcuaClient

# Status dot colors
_STATUS_COLORS = {"good": "text-green-400", "warning": "text-yellow-400", "bad": "text-red-400"}

# Variable icon color based on data type
_TYPE_ICON_COLORS = {
    "Boolean": "text-green-500",
    "Float": "text-blue-400",
    "Double": "text-blue-400",
    "Int16": "text-orange-400",
    "Int32": "text-orange-400",
    "Int64": "text-orange-400",
    "UInt16": "text-orange-400",
    "UInt32": "text-orange-400",
    "UInt64": "text-orange-400",
    "Byte": "text-orange-400",
    "String": "text-teal-400",
}

_TYPE_ICONS = {
    "Boolean": "check_box_outline_blank",
    "Float": "bar_chart",
    "Double": "bar_chart",
    "String": "text_fields",
}


def _var_icon(data_type: str) -> tuple[str, str]:
    icon = _TYPE_ICONS.get(data_type, "data_object")
    color = _TYPE_ICON_COLORS.get(data_type, "text-gray-400")
    return icon, color


def create_tree_view(client: OpcuaClient, on_select_node):
    """Create tree view. Returns (container, rebuild_fn, set_root_fn)."""
    root_state = {"node_id": None, "path": []}
    tree_container = ui.column().classes("w-full gap-0")

    async def set_root(node_id: str | None, name: str | None = None):
        if node_id is None:
            root_state["node_id"] = None
            root_state["path"] = []
        else:
            root_state["node_id"] = node_id
            if name:
                root_state["path"].append(name)
        await rebuild_tree()

    async def rebuild_tree():
        tree_container.clear()
        with tree_container:
            with ui.column().classes("w-full gap-0"):
                root_row = ui.row().classes("items-center gap-2 py-1.5 px-3 cursor-pointer w-full")
                with root_row:
                    root_arrow = ui.icon("expand_more", size="18px").classes("text-gray-400")
                    ui.icon("folder", size="18px").classes("text-blue-300")
                    ui.label("Objects").classes("text-sm")
                    if root_state["path"]:
                        ui.label(" / ".join(root_state["path"])).classes("text-xs text-gray-500 ml-1")

                root_children = ui.column().classes("w-full gap-0")
                root_expanded = {"value": True}

                async def toggle_root():
                    if root_expanded["value"]:
                        root_expanded["value"] = False
                        root_arrow.props("name=chevron_right")
                        root_children.clear()
                    else:
                        root_expanded["value"] = True
                        root_arrow.props("name=expand_more")
                        await _load_children(root_children, root_state["node_id"], 1)

                root_row.on("click", lambda: toggle_root())

            await _load_children(root_children, root_state["node_id"], 1)

    async def _load_children(container, node_id: str | None = None, depth: int = 0):
        with container:
            spinner = ui.spinner(size="sm").classes("ml-8")
        try:
            children = await client.browse_children(node_id)
        except Exception as e:
            container.clear()
            with container:
                ui.label(f"Error: {e}").classes("text-red-400 text-xs ml-8")
            return

        spinner.delete()

        if not children:
            with container:
                ui.label("(empty)").classes("text-gray-600 text-xs").style(f"padding-left:{depth * 24 + 40}px")
            return

        for node in children:
            with container:
                _render_node(node, depth)

    def _render_node(node: dict, depth: int):
        indent = depth * 24
        has_children = node.get("has_children", False)

        if node["is_variable"]:
            icon_name, icon_color = _var_icon(node.get("data_type", ""))
            status_color = _STATUS_COLORS.get(node.get("status", "good"), "text-gray-500")

            with ui.column().classes("w-full gap-0"):
                row = ui.row().classes(
                    "items-center gap-2 py-1 px-3 hover:bg-white/5 rounded cursor-pointer w-full"
                ).style(f"padding-left:{indent}px")

                with row:
                    if has_children:
                        arrow = ui.icon("chevron_right", size="18px").classes("text-gray-500 transition-transform")
                    else:
                        ui.element("div").style("width:18px")

                    ui.icon(icon_name, size="18px").classes(icon_color)
                    ui.label(node["name"]).classes("text-sm font-medium")

                    if node.get("data_type"):
                        ui.label(node["data_type"]).classes("text-xs text-gray-500")

                    if node["value"] is not None and node["value"] != "?":
                        val_text = str(node["value"])
                        if len(val_text) > 40:
                            val_text = val_text[:40] + "..."
                        ui.label(val_text).classes("text-sm text-gray-300 font-mono")

                    if node.get("status") != "good":
                        ui.icon("circle", size="10px").classes(status_color)
                    elif node["value"] is not None and node["value"] != "?":
                        ui.icon("circle", size="8px").classes("text-green-500 ml-auto opacity-70")

                if has_children:
                    child_container = ui.column().classes("w-full gap-0")
                    expanded = {"value": False}

                    async def toggle(nid=node["id"], cont=child_container, arr=arrow, exp=expanded, d=depth):
                        if not exp["value"]:
                            exp["value"] = True
                            arr.classes(add="rotate-90")
                            await _load_children(cont, nid, d + 1)
                        else:
                            exp["value"] = False
                            arr.classes(remove="rotate-90")
                            cont.clear()

                    row.on("click", lambda nid=node["id"]: toggle(nid))

                    async def detail(nid=node["id"]):
                        await on_select_node(nid)
                    row.on("dblclick", lambda nid=node["id"]: detail(nid))
                else:
                    async def on_click(nid=node["id"]):
                        await on_select_node(nid)
                    row.on("click", lambda nid=node["id"]: on_click(nid))

        elif node.get("is_method"):
            with ui.row().classes(
                "items-center gap-2 py-1 px-3 hover:bg-white/5 rounded w-full"
            ).style(f"padding-left:{indent}px"):
                ui.element("div").style("width:18px")
                ui.icon("functions", size="18px").classes("text-purple-400")
                ui.label(node["name"]).classes("text-sm text-gray-500")

        else:
            expanded = {"value": False}
            with ui.column().classes("w-full gap-0"):
                row = ui.row().classes(
                    "items-center gap-2 py-1 px-3 hover:bg-white/5 rounded cursor-pointer w-full"
                ).style(f"padding-left:{indent}px")
                with row:
                    arrow = ui.icon("chevron_right", size="18px").classes("text-gray-400 transition-transform")
                    ui.icon("folder", size="18px").classes("text-yellow-500")
                    ui.label(node["name"]).classes("text-sm font-medium")

                child_container = ui.column().classes("w-full gap-0")

                async def toggle_folder(nid=node["id"], cont=child_container, arr=arrow, exp=expanded, d=depth):
                    if not exp["value"]:
                        exp["value"] = True
                        arr.classes(add="rotate-90")
                        await _load_children(cont, nid, d + 1)
                    else:
                        exp["value"] = False
                        arr.classes(remove="rotate-90")
                        cont.clear()

                async def folder_detail(nid=node["id"]):
                    await on_select_node(nid)

                row.on("click", lambda nid=node["id"]: toggle_folder(nid))
                row.on("dblclick", lambda nid=node["id"]: folder_detail(nid))

    return tree_container, rebuild_tree, set_root
