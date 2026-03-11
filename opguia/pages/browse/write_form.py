"""Write form component — scalar and per-index array inputs for writable OPC UA nodes."""

from nicegui import ui
from opguia.client import OpcuaClient

_TYPE_HINTS = {
    "Boolean": "true or false",
    "Float": "decimal number",
    "Double": "decimal number",
    "Int16": "integer (-32768..32767)",
    "Int32": "integer",
    "Int64": "integer",
    "UInt16": "integer (0..65535)",
    "UInt32": "integer (0..4294967295)",
    "UInt64": "integer (0+)",
    "Byte": "integer (0..255)",
    "SByte": "integer (-128..127)",
    "String": "text",
}

_INT_TYPES = {"Int16", "Int32", "Int64", "UInt16", "UInt32", "UInt64", "Byte", "SByte"}
_FLOAT_TYPES = {"Float", "Double"}

_INT_RANGES = {
    "Int16": (-32768, 32767),
    "Int32": (-2147483648, 2147483647),
    "Int64": (-9223372036854775808, 9223372036854775807),
    "UInt16": (0, 65535),
    "UInt32": (0, 4294967295),
    "UInt64": (0, 18446744073709551615),
    "Byte": (0, 255),
    "SByte": (-128, 127),
}


def validate_write(raw: str, data_type: str) -> str | None:
    """Validate a write value string. Returns error string or None if valid."""
    if data_type in _INT_TYPES:
        try:
            v = int(raw)
        except ValueError:
            return f"Expected integer, got '{raw}'"
        lo, hi = _INT_RANGES.get(data_type, (None, None))
        if lo is not None and not (lo <= v <= hi):
            return f"Out of range for {data_type}: {lo}..{hi}"
    elif data_type in _FLOAT_TYPES:
        try:
            float(raw)
        except ValueError:
            return f"Expected number, got '{raw}'"
    elif data_type == "Boolean":
        if raw.lower() not in ("true", "false", "1", "0", "yes", "no"):
            return f"Expected true/false, got '{raw}'"
    return None


def _status_label() -> ui.label:
    return ui.label("").classes("text-xs")


def _set_err(st: ui.label, msg: str):
    st.text = msg
    st.classes(remove="text-green-400", add="text-red-400")


def _set_ok(st: ui.label, msg: str):
    st.text = msg
    st.classes(remove="text-red-400", add="text-green-400")


def _clear_status(st: ui.label):
    st.classes(remove="text-red-400 text-green-400")


def create_write_form(
    client: OpcuaClient,
    node_id: str,
    val,
    val_display: ui.label,
    data_type: str,
):
    """Render write controls for a writable node. Builds UI inline."""
    is_array = isinstance(val, list)
    st = _status_label()

    if is_array:
        _array_write_form(client, node_id, val, val_display, data_type, st)
    else:
        _scalar_write_form(client, node_id, str(val), val_display, data_type, st)


def _array_write_form(client, node_id, val, val_display, dt, st):
    with ui.column().classes("w-full gap-1"):
        for idx, elem in enumerate(val):
            with ui.row().classes("items-center gap-1 w-full"):
                ui.label(f"[{idx}]").classes("text-xs text-gray-500 w-8 text-right shrink-0")
                if dt == "Boolean":
                    _bool_index_input(client, node_id, idx, elem, val_display, st)
                else:
                    _scalar_index_input(client, node_id, idx, elem, val_display, dt, st)


def _bool_index_input(client, node_id, idx, elem, val_display, st):
    toggle = ui.toggle({True: "1", False: "0"}, value=elem).props("dense")

    async def on_toggle(new_val, nid=node_id, i=idx):
        st.text = f"Writing [{i}]…"
        _clear_status(st)
        try:
            arr = list(await client.read_value(nid))
            arr[i] = bool(new_val)
            await client.write_value(nid, arr)
            val_display.text = str(arr)
            _set_ok(st, f"OK — [{i}]={arr[i]}")
        except Exception as e:
            _set_err(st, str(e))

    toggle.on_value_change(lambda e, cb=on_toggle: cb(e.value))


def _scalar_index_input(client, node_id, idx, elem, val_display, dt, st):
    hint = _TYPE_HINTS.get(dt, "")
    inp = ui.input(value=str(elem), placeholder=hint).props("dense outlined").classes("flex-grow font-mono text-sm")
    elem_type = type(elem)

    async def on_write(nid=node_id, i=idx, et=elem_type):
        err = validate_write(inp.value, dt)
        if err:
            _set_err(st, err)
            return
        st.text = f"Writing [{i}]…"
        _clear_status(st)
        try:
            arr = list(await client.read_value(nid))
            arr[i] = et(inp.value)
            await client.write_value(nid, arr)
            new_val = list(await client.read_value(nid))
            val_display.text = str(new_val)
            _set_ok(st, f"OK — [{i}]={new_val[i]}")
        except Exception as e:
            _set_err(st, str(e))

    inp.on("keydown.enter", on_write)
    ui.button("Write", on_click=on_write).props("dense size=sm color=primary")


def _scalar_write_form(client, node_id, val_str, val_display, dt, st):
    hint = _TYPE_HINTS.get(dt, "")
    with ui.row().classes("items-center gap-2 w-full"):
        inp = ui.input(value=val_str, placeholder=hint).props("dense outlined").classes("flex-grow font-mono text-sm")
        if hint:
            inp.tooltip(f"Type: {dt} ({hint})")

        async def on_write(nid=node_id):
            err = validate_write(inp.value, dt)
            if err:
                _set_err(st, err)
                return
            st.text = "Writing..."
            _clear_status(st)
            try:
                await client.write_value(nid, inp.value)
            except Exception as e:
                _set_err(st, str(e))
                return
            try:
                new_val = await client.read_value(nid)
                val_display.text = str(new_val)
                _set_ok(st, f"OK — value: {new_val}")
            except Exception as e:
                _set_err(st, f"Written but read-back failed: {e}")

        inp.on("keydown.enter", on_write)
        ui.button("Write", on_click=on_write).props("dense size=sm color=primary")
