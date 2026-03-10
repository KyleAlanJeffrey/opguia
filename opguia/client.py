"""OPC UA client wrapper — connect, browse, read, write."""

import time
from asyncua import Client, ua
from .utils import NODE_CLASS_NAMES, access_level_str, format_timestamp, convert_value


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
        """Browse children with inline data type, value, and status."""
        if not self.client:
            raise RuntimeError("Not connected")

        node = self.client.nodes.objects if node_id is None else self.client.get_node(node_id)
        children = await node.get_children()
        results = []

        for child in children:
            try:
                cls = await child.read_node_class()
                name = await child.read_display_name()
                display_name = name.Text if name else str(child.nodeid)
                is_var = cls == ua.NodeClass.Variable

                try:
                    sub_children = await child.get_children()
                    has_children = len(sub_children) > 0
                except Exception:
                    has_children = False

                entry = {
                    "id": child.nodeid.to_string(),
                    "name": display_name,
                    "node_class": NODE_CLASS_NAMES.get(cls, str(cls)),
                    "node_class_raw": cls,
                    "is_variable": is_var,
                    "is_method": cls == ua.NodeClass.Method,
                    "has_children": has_children,
                    "value": None,
                    "data_type": "",
                    "writable": False,
                    "status": "good",
                }

                if is_var:
                    # Data type
                    try:
                        dt = await child.read_data_type_as_variant_type()
                        entry["data_type"] = dt.name
                    except Exception:
                        try:
                            dt_node = await child.read_data_type()
                            dt_name = await self.client.get_node(dt_node).read_display_name()
                            entry["data_type"] = dt_name.Text if dt_name else ""
                        except Exception:
                            pass

                    # Value + status code
                    try:
                        dv = await child.read_data_value()
                        entry["value"] = dv.Value.Value if dv.Value else None
                        sc = dv.StatusCode
                        if sc and not sc.is_good():
                            entry["status"] = "bad" if sc.value >= 0x80000000 else "warning"
                    except Exception:
                        entry["value"] = "?"
                        entry["status"] = "bad"

                    # Writable
                    try:
                        al = await child.read_attribute(ua.AttributeIds.UserAccessLevel)
                        entry["writable"] = bool(al.Value.Value & 0x02)
                    except Exception:
                        pass

                results.append(entry)
            except Exception:
                continue

        return results

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
                dt = await node.read_data_type_as_variant_type()
                details["data_type"] = str(dt)
            except Exception:
                try:
                    dt_node = await node.read_data_type()
                    dt_name = await self.client.get_node(dt_node).read_display_name()
                    details["data_type"] = dt_name.Text if dt_name else str(dt_node)
                except Exception:
                    details["data_type"] = "—"

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
