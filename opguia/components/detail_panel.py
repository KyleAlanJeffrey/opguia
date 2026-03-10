"""Node detail panel — shows full attributes, value, and write controls."""

import asyncio
from nicegui import ui
from opguia.client import OpcuaClient


def create_detail_panel(client: OpcuaClient, on_set_root=None):
    """Create the detail panel container and return (container, show_details_fn)."""
    container = ui.column().classes("w-full gap-2")
    with container:
        ui.label("Select a node").classes("text-xs text-gray-500")

    async def show_details(node_id: str):
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
            ui.label(info["display_name"]).classes("text-lg font-bold")
            if info["description"]:
                ui.label(info["description"]).classes("text-xs text-gray-400 italic")

            ui.separator().classes("my-1")

            # Attribute rows
            rows = [
                ("Node ID", info["node_id"]),
                ("Browse Name", info["browse_name"]),
                ("Node Class", info["node_class"]),
            ]

            if info["is_variable"]:
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
            else:
                rows.append(("Children", info.get("child_count", "—")))

            for label, val in rows:
                with ui.row().classes("items-start gap-2 w-full"):
                    ui.label(label).classes("text-xs text-gray-500 w-24 shrink-0 text-right")
                    ui.label(str(val)).classes("text-xs font-mono break-all")

            # Value display + write for variables
            if info["is_variable"]:
                ui.separator().classes("my-1")
                ui.label("Value").classes("text-xs text-gray-500")
                val_str = str(info.get("value", "—"))
                ui.label(val_str).classes("text-sm font-mono text-green-300 break-all")

                if info.get("writable"):
                    ui.separator().classes("my-1")
                    ui.label("Write Value").classes("text-xs text-gray-500")
                    write_input = ui.input(value=val_str).props("dense").classes("w-full font-mono text-sm")
                    write_status = ui.label("").classes("text-xs")

                    async def do_write(nid=node_id, inp=write_input, st=write_status):
                        st.text = "Writing..."
                        st.classes(remove="text-red-400 text-green-400")
                        try:
                            await client.write_value(nid, inp.value)
                            st.text = "Written successfully"
                            st.classes(add="text-green-400")
                            await asyncio.sleep(0.5)
                            await show_details(nid)
                        except Exception as e:
                            st.text = str(e)
                            st.classes(add="text-red-400")

                    ui.button("Write", on_click=do_write).props("dense size=sm").classes("mt-1")

                async def do_refresh(nid=node_id):
                    await show_details(nid)
                ui.button("Refresh", icon="refresh", on_click=do_refresh).props("flat dense size=sm").classes("mt-2")

            # Set as root for non-variable nodes
            if not info["is_variable"] and on_set_root:
                ui.separator().classes("my-1")

                async def set_root(nid=node_id, name=info["display_name"]):
                    await on_set_root(nid, name)

                ui.button("Set as tree root", icon="folder_open", on_click=set_root).props("flat dense size=sm")

    return container, show_details
