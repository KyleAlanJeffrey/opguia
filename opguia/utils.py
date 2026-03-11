"""Shared helpers — type conversion, formatting, constants.

These are used by both client.py (OPC UA operations) and
UI components (display formatting).
"""

from asyncua import ua
from datetime import datetime

# Standard OPC UA port and ephemeral port range for tunnels
DEFAULT_OPC_PORT = 4840
EPHEMERAL_PORT_RANGE = (49152, 65000)

# Human-readable names for OPC UA node classes
NODE_CLASS_NAMES = {
    ua.NodeClass.Object: "Object",
    ua.NodeClass.Variable: "Variable",
    ua.NodeClass.Method: "Method",
    ua.NodeClass.ObjectType: "ObjectType",
    ua.NodeClass.VariableType: "VariableType",
    ua.NodeClass.ReferenceType: "ReferenceType",
    ua.NodeClass.DataType: "DataType",
    ua.NodeClass.View: "View",
}

# OPC UA AccessLevel bit flags
ACCESS_LEVEL_BITS = {
    0x01: "Read",
    0x02: "Write",
    0x04: "HistoryRead",
    0x08: "HistoryWrite",
    0x10: "SemanticChange",
    0x20: "StatusWrite",
    0x40: "TimestampWrite",
}


def access_level_str(level: int) -> str:
    """Convert an AccessLevel bitmask to a comma-separated string."""
    parts = [name for bit, name in ACCESS_LEVEL_BITS.items() if level & bit]
    return ", ".join(parts) if parts else "None"


def format_timestamp(ts) -> str:
    """Format an OPC UA timestamp for display."""
    if ts is None:
        return "—"
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return str(ts)


def convert_scalar(raw: str, vtype: ua.VariantType):
    """Convert a single string token to the correct Python type."""
    if vtype in (ua.VariantType.Float, ua.VariantType.Double):
        return float(raw)
    if vtype in (
        ua.VariantType.Int16, ua.VariantType.Int32, ua.VariantType.Int64,
        ua.VariantType.UInt16, ua.VariantType.UInt32, ua.VariantType.UInt64,
        ua.VariantType.Byte, ua.VariantType.SByte,
    ):
        return int(raw)
    if vtype == ua.VariantType.Boolean:
        return raw.strip().lower() in ("true", "1", "yes")
    if vtype == ua.VariantType.String:
        return str(raw)
    return raw


def convert_value(raw: str, vtype: ua.VariantType):
    """Convert a string input to the correct Python type for writing."""
    return convert_scalar(raw, vtype)
