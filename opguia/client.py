"""OPC UA client wrapper — connect, browse, read, write.

All OPC UA communication goes through this class. UI code never
touches asyncua directly.
"""

import asyncio
import time
from asyncua import Client, ua
from .utils import NODE_CLASS_NAMES, access_level_str, format_timestamp, convert_value

# Standard OPC UA base data type NodeId -> friendly name.
# Namespace 0, integer identifiers only. Avoids a network round trip.
_BASE_DATA_TYPES = {
    1: "Boolean", 2: "SByte", 3: "Byte", 4: "Int16", 5: "UInt16",
    6: "Int32", 7: "UInt32", 8: "Int64", 9: "UInt64",
    10: "Float", 11: "Double", 12: "String", 13: "DateTime",
    14: "Guid", 15: "ByteString", 16: "XmlElement",
    17: "NodeId", 19: "StatusCode", 22: "ExtensionObject",
    26: "Number", 27: "Integer", 28: "UInteger",
}

# NodeClasses that always have browsable children (folders, object types, views).
_CONTAINER_CLASSES = {ua.NodeClass.Object, ua.NodeClass.ObjectType, ua.NodeClass.View}


async def _resolve_data_type(client: Client, dt_nodeid) -> tuple[str, bool]:
    """Resolve a DataType NodeId to (friendly_name, is_complex).

    Returns the human-readable type name and whether it's a complex/struct type
    that can't be read as a simple value (i.e. needs child browsing).
    """
    # Try the fast local lookup first (covers all standard ns=0 types)
    dt_id = getattr(dt_nodeid, "Identifier", None)
    ns = getattr(dt_nodeid, "NamespaceIndex", 0)

    if ns == 0 and isinstance(dt_id, int) and dt_id in _BASE_DATA_TYPES:
        name = _BASE_DATA_TYPES[dt_id]
        return name, (dt_id == 22)  # id 22 = ExtensionObject base type

    # Custom type (vendor namespace) — read the type node's DisplayName
    try:
        dn = await client.get_node(dt_nodeid).read_display_name()
        name = dn.Text if dn and dn.Text else str(dt_nodeid)
    except Exception:
        name = str(dt_nodeid)

    # Custom struct types that inherit from Structure/ExtensionObject are complex.
    # Heuristic: if it's not a known primitive, it's likely a struct.
    is_complex = name not in _BASE_DATA_TYPES.values()
    return name, is_complex


class OpcuaClient:
    def __init__(self):
        self.client: Client | None = None
        self.endpoint: str = ""
        self.server_name: str = ""
        self.security_policy: str = "None"

    # ── Connection ──

    async def connect(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self.client = Client(url=endpoint)
        await self.client.connect()
        # Read server metadata from the first endpoint descriptor
        try:
            endpoints = await self.client.get_endpoints()
            if endpoints:
                ep = endpoints[0]
                self.server_name = ep.Server.ApplicationName.Text or ""
                policy = str(ep.SecurityPolicyUri or "").rsplit("#", 1)[-1]
                mode = str(ep.SecurityMode).replace("MessageSecurityMode.", "")
                self.security_policy = f"{mode}" + (f" ({policy})" if policy and policy != "None" else "")
        except Exception:
            self.server_name = ""
            self.security_policy = "None"

    async def disconnect(self) -> None:
        if self.client:
            await self.client.disconnect()
            self.client = None
            self.endpoint = ""
            self.server_name = ""

    @property
    def connected(self) -> bool:
        return self.client is not None

    async def measure_latency(self) -> float | None:
        """Round-trip latency in ms (reads Server node's browse name)."""
        if not self.client:
            return None
        try:
            t0 = time.monotonic()
            await self.client.nodes.server.read_browse_name()
            return round((time.monotonic() - t0) * 1000, 1)
        except Exception:
            return None

    # ── Path resolution ──

    async def resolve_path(self, path: list[str]) -> str | None:
        """Walk a display-name path from Objects and return the final NodeId string."""
        if not self.client:
            return None
        node = self.client.nodes.objects
        for segment in path:
            children = await node.get_children()
            found = None
            for child in children:
                name = await child.read_display_name()
                if name and name.Text == segment:
                    found = child
                    break
            if found is None:
                return None
            node = found
        return node.nodeid.to_string()

    # ── Browse children (tree population) ──

    async def browse_children(self, node_id: str | None = None) -> list[dict]:
        """Browse immediate children with inline value, type, and status.

        Uses batched parallel reads for performance:
          Phase 1 — NodeClass + DisplayName for all children
          Phase 2 — Value + DataType + UserAccessLevel for variables only
          Phase 3 — Resolve custom DataType NodeIds to display names
        """
        if not self.client:
            raise RuntimeError("Not connected")

        # Get child node references
        root = self.client.nodes.objects if node_id is None else self.client.get_node(node_id)
        children = await root.get_children()

        # ── Phase 1: classify all children (NodeClass + DisplayName) ──
        base_attrs = [ua.AttributeIds.NodeClass, ua.AttributeIds.DisplayName]
        base_results = await asyncio.gather(
            *[c.read_attributes(base_attrs) for c in children],
            return_exceptions=True,
        )

        entries: list[dict | None] = []
        var_indices: list[int] = []  # indices into `children` that are Variables

        for i, (child, result) in enumerate(zip(children, base_results)):
            if isinstance(result, Exception):
                entries.append(None)
                continue

            cls_dv, name_dv = result
            cls = cls_dv.Value.Value if cls_dv.Value else None
            raw_name = name_dv.Value.Value
            display_name = raw_name.Text if raw_name else str(child.nodeid)
            is_var = cls == ua.NodeClass.Variable

            entry = {
                "id": child.nodeid.to_string(),
                "name": display_name,
                "node_class": NODE_CLASS_NAMES.get(cls, str(cls)) if cls else "?",
                "is_variable": is_var,
                "is_method": cls == ua.NodeClass.Method,
                "has_children": cls in _CONTAINER_CLASSES,  # objects always expandable
                "value": None,
                "data_type": "",
                "writable": False,
                "status": "good",
            }
            entries.append(entry)

            if is_var:
                var_indices.append(i)

        # ── Phase 2: read variable attributes (Value + DataType + UserAccessLevel) ──
        if var_indices:
            var_attrs = [ua.AttributeIds.Value, ua.AttributeIds.DataType, ua.AttributeIds.UserAccessLevel]
            var_results = await asyncio.gather(
                *[children[i].read_attributes(var_attrs) for i in var_indices],
                return_exceptions=True,
            )

            # Track which entries need custom type name resolution
            needs_type_resolve: list[tuple[int, object]] = []  # (entry_index, dt_nodeid)

            for idx, vr in zip(var_indices, var_results):
                entry = entries[idx]
                if isinstance(vr, Exception):
                    entry["value"] = "?"
                    entry["status"] = "bad"
                    continue

                val_dv, dt_dv, al_dv = vr

                # Value + StatusCode
                if val_dv.Value is not None:
                    entry["value"] = val_dv.Value.Value
                    sc = val_dv.StatusCode
                    if sc and not sc.is_good():
                        entry["status"] = "bad" if sc.value >= 0x80000000 else "warning"
                else:
                    entry["value"] = "?"

                # DataType — try local lookup, queue unknowns for phase 3
                if dt_dv.Value and dt_dv.Value.Value:
                    dt_nodeid = dt_dv.Value.Value
                    dt_id = getattr(dt_nodeid, "Identifier", None)
                    ns = getattr(dt_nodeid, "NamespaceIndex", 0)

                    if ns == 0 and isinstance(dt_id, int) and dt_id in _BASE_DATA_TYPES:
                        entry["data_type"] = _BASE_DATA_TYPES[dt_id]
                        # Base ExtensionObject (id=22) — try to refine from decoded value
                        if dt_id == 22:
                            entry["has_children"] = True
                            val = entry["value"]
                            if val is not None and val != "?":
                                real = type(val).__name__
                                if real not in ("ExtensionObject", "NoneType", "bytes"):
                                    entry["data_type"] = real
                    else:
                        # Custom type — queue for batch name resolution
                        needs_type_resolve.append((idx, dt_nodeid))

                # UserAccessLevel — bit 0x02 = CurrentWrite
                if al_dv.Value and al_dv.Value.Value is not None:
                    entry["writable"] = bool(al_dv.Value.Value & 0x02)

            # ── Phase 3: batch-resolve custom DataType names ──
            if needs_type_resolve and self.client:
                name_results = await asyncio.gather(
                    *[self.client.get_node(nid).read_display_name() for _, nid in needs_type_resolve],
                    return_exceptions=True,
                )
                for (idx, _nid), nr in zip(needs_type_resolve, name_results):
                    entry = entries[idx]
                    if isinstance(nr, Exception) or not nr or not nr.Text:
                        # Couldn't resolve — fall back to VariantType if available
                        entry["data_type"] = "Unknown"
                    else:
                        entry["data_type"] = nr.Text
                    # Custom/non-primitive types are struct-like — mark expandable
                    entry["has_children"] = True

        return [e for e in entries if e is not None]

    # ── Node details (detail dialog) ──

    async def get_node_details(self, node_id: str) -> dict:
        """Full attribute details for a single node (used by detail dialog)."""
        if not self.client:
            raise RuntimeError("Not connected")

        node = self.client.get_node(node_id)
        info: dict = {"node_id": node_id}

        # Basic attributes (always available)
        try:
            dn = await node.read_display_name()
            info["display_name"] = dn.Text if dn else "—"
        except Exception:
            info["display_name"] = "—"

        try:
            bn = await node.read_browse_name()
            info["browse_name"] = f"{bn.NamespaceIndex}:{bn.Name}" if bn else "—"
        except Exception:
            info["browse_name"] = "—"

        try:
            cls = await node.read_node_class()
            info["node_class"] = NODE_CLASS_NAMES.get(cls, str(cls))
            info["node_class_raw"] = cls
        except Exception:
            info["node_class"] = "—"
            info["node_class_raw"] = None

        try:
            desc = await node.read_description()
            info["description"] = desc.Text if desc and desc.Text else ""
        except Exception:
            info["description"] = ""

        is_var = info.get("node_class_raw") == ua.NodeClass.Variable
        info["is_variable"] = is_var

        if is_var:
            # Resolve data type FIRST — determines if we can safely read the value.
            # Complex types (structs/ExtensionObjects) throw BadNotSupported on value read.
            info["data_type"], info["is_complex"] = await self._resolve_detail_data_type(node)

            # Always try to read the value — even complex types may be decodable
            try:
                dv = await node.read_data_value()
                val = dv.Value.Value if dv.Value else None
                info["value"] = val
                info["variant_type"] = dv.Value.VariantType.name if dv.Value else "—"
                info["status_code"] = str(dv.StatusCode)
                info["source_timestamp"] = format_timestamp(dv.SourceTimestamp)
                info["server_timestamp"] = format_timestamp(dv.ServerTimestamp)
                # Refine type name from decoded value
                if val is not None and info["is_complex"]:
                    real = type(val).__name__
                    if real not in ("ExtensionObject", "NoneType", "bytes"):
                        info["data_type"] = real
                        info["variant_type"] = real
            except Exception as e:
                if info["is_complex"]:
                    info["value"] = None
                    info["variant_type"] = info["data_type"]
                else:
                    info["value"] = f"Error: {e}"
                    info["variant_type"] = "—"
                info["status_code"] = "—"
                info["source_timestamp"] = "—"
                info["server_timestamp"] = "—"

            # Access levels
            try:
                al = await node.read_attribute(ua.AttributeIds.AccessLevel)
                info["access_level"] = access_level_str(al.Value.Value)
            except Exception:
                info["access_level"] = "—"

            try:
                ual = await node.read_attribute(ua.AttributeIds.UserAccessLevel)
                info["user_access_level"] = access_level_str(ual.Value.Value)
                info["writable"] = bool(ual.Value.Value & 0x02)
            except Exception:
                info["user_access_level"] = "—"
                info["writable"] = False

            try:
                vr = await node.read_attribute(ua.AttributeIds.ValueRank)
                info["value_rank"] = vr.Value.Value
            except Exception:
                info["value_rank"] = "—"
        else:
            info["writable"] = False
            info["is_complex"] = False

        # Child count (useful for folders)
        try:
            ch = await node.get_children()
            info["child_count"] = len(ch)
        except Exception:
            info["child_count"] = "—"

        return info

    async def _resolve_detail_data_type(self, node) -> tuple[str, bool]:
        """Resolve a variable node's DataType for the detail view.

        Returns (type_name, is_complex). Uses the shared _resolve_data_type helper.
        """
        try:
            dt_nodeid = await node.read_data_type()
            return await _resolve_data_type(self.client, dt_nodeid)
        except Exception:
            # Fallback: try asyncua's built-in variant type resolver
            try:
                dt = await node.read_data_type_as_variant_type()
                return dt.name, (dt == ua.VariantType.ExtensionObject)
            except Exception:
                return "—", False

    # ── Read / Write ──

    async def read_value(self, node_id: str):
        """Read and return the current value of a variable node."""
        if not self.client:
            raise RuntimeError("Not connected")
        return await self.client.get_node(node_id).read_value()

    async def write_value(self, node_id: str, value, data_type: ua.VariantType | None = None) -> None:
        """Write a value to a variable node.

        If data_type is given, uses it directly. Otherwise reads the current
        VariantType and converts the string value to match.
        """
        if not self.client:
            raise RuntimeError("Not connected")
        node = self.client.get_node(node_id)
        if data_type:
            await node.write_value(ua.DataValue(ua.Variant(value, data_type)))
        else:
            # Read current type so we can convert the string value correctly
            current = await node.read_data_value()
            vtype = current.Value.VariantType if current.Value else None
            if vtype:
                await node.write_value(ua.DataValue(ua.Variant(convert_value(value, vtype), vtype)))
            else:
                await node.write_value(value)
