"""OPC UA client wrapper — connect, browse, read, write."""

import time
from asyncua import Client, ua
from .utils import NODE_CLASS_NAMES, access_level_str, format_timestamp, convert_value

# Common OPC UA base data type NodeId identifiers -> friendly names
# Avoids a network round trip to resolve these
_COMMON_DATA_TYPES = {
    1: "Boolean", 2: "SByte", 3: "Byte", 4: "Int16", 5: "UInt16",
    6: "Int32", 7: "UInt32", 8: "Int64", 9: "UInt64",
    10: "Float", 11: "Double", 12: "String", 13: "DateTime",
    14: "Guid", 15: "ByteString", 16: "XmlElement",
    17: "NodeId", 19: "StatusCode", 22: "ExtensionObject",
    26: "Number", 27: "Integer", 28: "UInteger",
}


class OpcuaClient:
    def __init__(self):
        self.client: Client | None = None
        self.endpoint: str = ""
        self.server_name: str = ""
        self.security_policy: str = "None"

    async def connect(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self.client = Client(url=endpoint)
        await self.client.connect()
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
        """Measure round-trip latency in ms."""
        if not self.client:
            return None
        try:
            t0 = time.monotonic()
            await self.client.nodes.server.read_browse_name()
            return round((time.monotonic() - t0) * 1000, 1)
        except Exception:
            return None

    async def resolve_path(self, path: list[str]) -> str | None:
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

    async def browse_children(self, node_id: str | None = None) -> list[dict]:
        """Browse children with inline data type, value, and status.

        Optimized: one batched read_attributes call per node instead of 3-6
        sequential calls. No get_children check (objects assumed expandable,
        variables checked on expand).
        """
        if not self.client:
            raise RuntimeError("Not connected")

        node = self.client.nodes.objects if node_id is None else self.client.get_node(node_id)
        children = await node.get_children()

        # Common attrs for all nodes (2 attrs)
        base_attrs = [ua.AttributeIds.NodeClass, ua.AttributeIds.DisplayName]
        # Extra attrs for variables (+3 = 5 total)
        var_attrs = base_attrs + [
            ua.AttributeIds.Value,
            ua.AttributeIds.DataType,
            ua.AttributeIds.UserAccessLevel,
        ]

        # Phase 1: read NodeClass + DisplayName for all children in parallel
        import asyncio as _aio
        base_reads = [c.read_attributes(base_attrs) for c in children]
        base_results = await _aio.gather(*base_reads, return_exceptions=True)

        # Identify which children are variables for phase 2
        var_indices = []
        entries = []
        for i, (child, result) in enumerate(zip(children, base_results)):
            if isinstance(result, Exception):
                entries.append(None)
                continue

            cls_dv, name_dv = result
            cls = cls_dv.Value.Value if cls_dv.Value else None
            name = name_dv.Value.Value
            display_name = name.Text if name else str(child.nodeid)
            is_var = cls == ua.NodeClass.Variable

            entry = {
                "id": child.nodeid.to_string(),
                "name": display_name,
                "node_class": NODE_CLASS_NAMES.get(cls, str(cls)) if cls else "?",
                "node_class_raw": cls,
                "is_variable": is_var,
                "is_method": cls == ua.NodeClass.Method,
                # Objects/folders are always expandable, variables may be
                "has_children": cls in (ua.NodeClass.Object, ua.NodeClass.ObjectType, ua.NodeClass.View),
                "value": None,
                "data_type": "",
                "writable": False,
                "status": "good",
            }
            entries.append(entry)

            if is_var:
                var_indices.append(i)

        # Phase 2: batch read Value + DataType + AccessLevel for variables in parallel
        if var_indices:
            var_reads = [children[i].read_attributes(var_attrs[2:]) for i in var_indices]
            var_results = await _aio.gather(*var_reads, return_exceptions=True)

            for idx, vr in zip(var_indices, var_results):
                entry = entries[idx]
                if isinstance(vr, Exception):
                    entry["value"] = "?"
                    entry["status"] = "bad"
                    continue

                val_dv, dt_dv, al_dv = vr

                # Value + status
                if val_dv.Value is not None:
                    entry["value"] = val_dv.Value.Value
                    sc = val_dv.StatusCode
                    if sc and not sc.is_good():
                        entry["status"] = "bad" if sc.value >= 0x80000000 else "warning"
                else:
                    entry["value"] = "?"

                # Data type — resolve NodeId to name
                if dt_dv.Value and dt_dv.Value.Value:
                    dt_nodeid = dt_dv.Value.Value
                    entry["data_type"] = _COMMON_DATA_TYPES.get(
                        dt_nodeid.Identifier if hasattr(dt_nodeid, "Identifier") else dt_nodeid,
                        "",
                    )
                    # If not in common cache, try variant type from value
                    if not entry["data_type"] and val_dv.Value:
                        entry["data_type"] = val_dv.Value.VariantType.name

                # Writable
                if al_dv.Value and al_dv.Value.Value is not None:
                    entry["writable"] = bool(al_dv.Value.Value & 0x02)

                # Variables with complex values may have children
                if entry["data_type"] == "ExtensionObject":
                    entry["has_children"] = True
                elif val_dv.Value and val_dv.Value.VariantType == ua.VariantType.ExtensionObject:
                    entry["has_children"] = True

        return [e for e in entries if e is not None]

    async def get_node_details(self, node_id: str) -> dict:
        """Get comprehensive details about a node."""
        if not self.client:
            raise RuntimeError("Not connected")
        node = self.client.get_node(node_id)
        details: dict = {"node_id": node_id}

        try:
            dn = await node.read_display_name()
            details["display_name"] = dn.Text if dn else "—"
        except Exception:
            details["display_name"] = "—"

        try:
            bn = await node.read_browse_name()
            details["browse_name"] = f"{bn.NamespaceIndex}:{bn.Name}" if bn else "—"
        except Exception:
            details["browse_name"] = "—"

        try:
            cls = await node.read_node_class()
            details["node_class"] = NODE_CLASS_NAMES.get(cls, str(cls))
            details["node_class_raw"] = cls
        except Exception:
            details["node_class"] = "—"
            details["node_class_raw"] = None

        try:
            desc = await node.read_description()
            details["description"] = desc.Text if desc and desc.Text else ""
        except Exception:
            details["description"] = ""

        is_var = details.get("node_class_raw") == ua.NodeClass.Variable
        details["is_variable"] = is_var

        if is_var:
            # Resolve data type FIRST so we can skip value read for complex types
            is_complex = False
            try:
                dt = await node.read_data_type_as_variant_type()
                details["data_type"] = dt.name  # e.g. "ExtensionObject", "Float"
                if dt == ua.VariantType.ExtensionObject:
                    is_complex = True
            except Exception:
                try:
                    dt_node = await node.read_data_type()
                    dt_id = dt_node.Identifier if hasattr(dt_node, "Identifier") else None
                    if dt_id and dt_id in _COMMON_DATA_TYPES:
                        details["data_type"] = _COMMON_DATA_TYPES[dt_id]
                        is_complex = dt_id == 22
                    else:
                        dt_name = await self.client.get_node(dt_node).read_display_name()
                        details["data_type"] = dt_name.Text if dt_name else str(dt_node)
                except Exception:
                    details["data_type"] = "—"

            if is_complex:
                details["value"] = None
                details["variant_type"] = "ExtensionObject"
                details["status_code"] = "—"
                details["source_timestamp"] = "—"
                details["server_timestamp"] = "—"
            else:
                try:
                    dv = await node.read_data_value()
                    details["value"] = dv.Value.Value if dv.Value else None
                    details["variant_type"] = str(dv.Value.VariantType) if dv.Value else "—"
                    details["status_code"] = str(dv.StatusCode)
                    details["source_timestamp"] = format_timestamp(dv.SourceTimestamp)
                    details["server_timestamp"] = format_timestamp(dv.ServerTimestamp)
                except Exception as e:
                    details["value"] = f"Error: {e}"
                    details["variant_type"] = "—"
                    details["status_code"] = "—"
                    details["source_timestamp"] = "—"
                    details["server_timestamp"] = "—"

            try:
                al = await node.read_attribute(ua.AttributeIds.AccessLevel)
                details["access_level"] = access_level_str(al.Value.Value)
            except Exception:
                details["access_level"] = "—"

            try:
                ual = await node.read_attribute(ua.AttributeIds.UserAccessLevel)
                details["user_access_level"] = access_level_str(ual.Value.Value)
                details["writable"] = bool(ual.Value.Value & 0x02)
            except Exception:
                details["user_access_level"] = "—"
                details["writable"] = False

            try:
                vr = await node.read_attribute(ua.AttributeIds.ValueRank)
                details["value_rank"] = vr.Value.Value
            except Exception:
                details["value_rank"] = "—"
        else:
            details["writable"] = False

        try:
            ch = await node.get_children()
            details["child_count"] = len(ch)
        except Exception:
            details["child_count"] = "—"

        return details

    async def read_value(self, node_id: str):
        if not self.client:
            raise RuntimeError("Not connected")
        return await self.client.get_node(node_id).read_value()

    async def write_value(self, node_id: str, value, data_type: ua.VariantType | None = None) -> None:
        if not self.client:
            raise RuntimeError("Not connected")
        node = self.client.get_node(node_id)
        if data_type:
            await node.write_value(ua.DataValue(ua.Variant(value, data_type)))
        else:
            current = await node.read_data_value()
            vtype = current.Value.VariantType if current.Value else None
            if vtype:
                await node.write_value(ua.DataValue(ua.Variant(convert_value(value, vtype), vtype)))
            else:
                await node.write_value(value)
