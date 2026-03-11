"""Watch panel — always-visible live variable values.

Displays watched variables in a compact table at the bottom of the browse
page. Values are polled every 2s alongside the tree view polling.
Complex/struct types can be expanded to browse children using the same
tree-style rows as the main tree view.
"""

from nicegui import ui
from opguia.client import OpcuaClient
from opguia.storage import Settings
from opguia.components.node_rows import format_val, _load as load_children


def create_watch_panel(
    client: OpcuaClient,
    settings: Settings,
    on_select_node=None,
    on_watch_changed=None,
):
    """Create the watch panel. Returns (container, render_fn, poll_fn).

    render_fn: call to rebuild the watch list from settings.
    poll_fn:   call periodically to update values.
    """
    container = ui.column().classes("w-full gap-0")

    # {node_id: value_label} for live polling
    _labels: dict[str, ui.label] = {}
    # {node_id: {child_nid: label}} for expanded child value polling
    _child_labels: dict[str, dict[str, ui.label]] = {}

    def render():
        container.clear()
        _labels.clear()
        _child_labels.clear()
        watched = settings.watched
        with container:
            if not watched:
                ui.label("No watched variables — star a variable to add it here").classes(
                    "text-xs text-gray-600 px-3 py-2"
                )
                return

            # Header row
            with ui.row().classes(
                "items-center gap-2 w-full px-3 border-b border-gray-700"
            ).style("height:22px"):
                ui.label("Name").classes("text-xs text-gray-500 font-medium").style(
                    "width:180px; flex-shrink:0"
                )
                ui.label("Value").classes("text-xs text-gray-500 font-medium flex-grow")
                ui.label("Node ID").classes("text-xs text-gray-500 font-medium").style(
                    "width:200px; flex-shrink:0"
                )
                ui.element("div").style("width:28px; flex-shrink:0")

            for item in watched:
                _render_watch_row(item)

    def _render_watch_row(item):
        nid = item["node_id"]
        name = item["name"]

        with ui.row().classes(
            "items-center gap-2 w-full px-3 hover:bg-white/5 cursor-pointer"
        ).style("height:24px") as row:
            # Name
            ui.label(name).classes("text-xs font-medium truncate").style(
                "width:160px; flex-shrink:0"
            )
            # Value (polled)
            val_lbl = ui.label("...").classes(
                "text-xs font-mono text-green-300 truncate flex-grow"
            )
            _labels[nid] = val_lbl
            # Node ID
            ui.label(nid).classes("text-xs font-mono text-gray-600 truncate").style(
                "width:200px; flex-shrink:0"
            )
            # Remove button

            def remove(node_id=nid):
                settings.remove_watched(node_id)
                render()
                if on_watch_changed:
                    on_watch_changed()

            ui.button(icon="close", on_click=remove).props(
                "flat dense round size=xs"
            ).classes("text-gray-600 shrink-0").style("opacity:0.5")

        # Child container — used when expanding complex nodes
        child_ct = ui.column().classes("w-full gap-0")
        child_value_labels: dict[str, ui.label] = {}
        _child_labels[nid] = child_value_labels
        exp = {"v": False, "bound": False, "arrow": None}

        async def toggle(nid_=nid, ct=child_ct, ex=exp, cvl=child_value_labels):
            ar = ex["arrow"]
            if not ex["v"]:
                ex["v"] = True
                if ar:
                    ar.classes(add="rotate-90")
                await load_children(client, ct, nid_, 1, on_select_node, cvl)
            else:
                ex["v"] = False
                if ar:
                    ar.classes(remove="rotate-90")
                ct.clear()
                cvl.clear()

        def _bind_expand(ex=exp, r=row):
            """Make the row expandable (called once when complex type detected)."""
            if ex["bound"]:
                return
            ex["bound"] = True
            # Inject arrow as first child of the row
            with r:
                ar = ui.icon("chevron_right", size="14px").classes(
                    "text-gray-500 transition-transform shrink-0"
                )
                ar.move(r, 0)
                ex["arrow"] = ar
            r.on("click", lambda: toggle())

        # Stash ref for poll to access
        val_lbl._watch_bind_expand = _bind_expand

        if on_select_node:
            row.on("dblclick", lambda n=nid: on_select_node(n))

    async def poll():
        if not client.connected:
            return
        # Poll top-level watched values
        for nid, lbl in list(_labels.items()):
            try:
                val = await client.read_value(nid)
                val_text = format_val(val, 40)
                lbl.text = val_text
                lbl.classes(remove="text-red-400 text-gray-500", add="text-green-300")
            except Exception:
                # Complex/struct — can't read simple value
                lbl.text = "(complex — click to expand)"
                lbl.classes(remove="text-green-300 text-red-400", add="text-gray-500")
                bind = getattr(lbl, "_watch_bind_expand", None)
                if bind:
                    bind()

        # Poll expanded child values
        for nid, cvl in list(_child_labels.items()):
            for cid, clbl in list(cvl.items()):
                try:
                    val = await client.read_value(cid)
                    clbl.text = format_val(val, 30)
                except Exception:
                    pass

    return container, render, poll
