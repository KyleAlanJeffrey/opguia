"""Shared helpers — type conversion, formatting, constants."""

from asyncua import ua
from datetime import datetime


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
    parts = [name for bit, name in ACCESS_LEVEL_BITS.items() if level & bit]
    return ", ".join(parts) if parts else "None"


def format_timestamp(ts) -> str:
    if ts is None:
        return "—"
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return str(ts)


def convert_value(raw: str, vtype: ua.VariantType):
    """Convert a string input to the appropriate Python type for the given VariantType."""
    if vtype in (ua.VariantType.Float, ua.VariantType.Double):
        return float(raw)
    if vtype in (
        ua.VariantType.Int16, ua.VariantType.Int32, ua.VariantType.Int64,
        ua.VariantType.UInt16, ua.VariantType.UInt32, ua.VariantType.UInt64,
        ua.VariantType.Byte, ua.VariantType.SByte,
    ):
        return int(raw)
    if vtype == ua.VariantType.Boolean:
        return raw.lower() in ("true", "1", "yes")
    if vtype == ua.VariantType.String:
        return str(raw)
    return raw
