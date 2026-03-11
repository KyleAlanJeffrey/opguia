"""Headless CLI — query, read, and write OPC UA nodes without the GUI.

Usage:
    opguia --headless <endpoint> browse [node_id]
    opguia --headless <endpoint> tree [node_id] [--depth N]
    opguia --headless <endpoint> read <node_id> [node_id ...]
    opguia --headless <endpoint> write <node_id> <value>
    opguia --headless <endpoint> info <node_id>

SSH tunnel support:
    opguia --headless <endpoint> --ssh user@host browse

Examples:
    opguia --headless opc.tcp://localhost:4840 browse
    opguia --headless opc.tcp://localhost:4840 tree --depth 3
    opguia --headless opc.tcp://localhost:4840 read 'ns=2;s=MyVar'
    opguia --headless opc.tcp://localhost:4840 write 'ns=2;s=MyVar' 42
    opguia --headless opc.tcp://192.168.1.100:4840 --ssh default@gateway browse

The standalone `opguia-cli` command is also available as an alias.
"""

import argparse
import asyncio
import json
import sys

from loguru import logger

from opguia.client import OpcuaClient
from opguia.tunnel import SSHTunnel


def _json_default(obj):
    """Handle non-serializable types."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.hex()
    try:
        return str(obj)
    except Exception:
        return repr(obj)


def _print_json(data):
    print(json.dumps(data, indent=2, default=_json_default, ensure_ascii=False))


def _parse_ssh(ssh_str: str) -> tuple[str, str, int]:
    """Parse 'user@host' or 'user@host:port' into (user, host, port)."""
    port = 22
    if ":" in ssh_str.split("@")[-1]:
        base, port_str = ssh_str.rsplit(":", 1)
        port = int(port_str)
        ssh_str = base
    if "@" in ssh_str:
        user, host = ssh_str.split("@", 1)
    else:
        user, host = "", ssh_str
    return user, host, port


async def _run(args):
    client = OpcuaClient()
    tunnel = SSHTunnel()
    connect_url = args.endpoint

    try:
        # Set up SSH tunnel if requested
        if args.ssh:
            user, host, port = _parse_ssh(args.ssh)
            connect_url = await tunnel.start(
                args.endpoint, ssh_host=host, ssh_user=user, ssh_port=port,
            )
            logger.info("Tunnel up: {}", connect_url)

        await client.connect(connect_url, timeout=args.timeout)
        logger.info("Connected to {}", client.server_name or args.endpoint)

        if args.command == "browse":
            node_id = args.node_id
            children = await client.browse_children(node_id)
            rows = []
            for c in children:
                row = {
                    "node_id": c["id"],
                    "name": c["name"],
                    "node_class": c["node_class"],
                }
                if c["is_variable"]:
                    row["value"] = c["value"]
                    row["data_type"] = c.get("data_type", "")
                    row["writable"] = c.get("writable", False)
                rows.append(row)
            _print_json(rows)

        elif args.command == "tree":
            await _tree(client, args.node_id, args.depth)

        elif args.command == "read":
            results = {}
            for nid in args.node_ids:
                try:
                    val = await client.read_value(nid)
                    results[nid] = val
                except Exception as e:
                    results[nid] = f"Error: {e}"
            if len(results) == 1:
                val = next(iter(results.values()))
                _print_json(val)
            else:
                _print_json(results)

        elif args.command == "write":
            await client.write_value(args.node_id, args.value)
            # Read back to verify
            readback = await client.read_value(args.node_id)
            logger.info("Written. Read-back: {}", readback)
            _print_json(readback)

        elif args.command == "info":
            details = await client.get_node_details(args.node_id)
            _print_json(details)

    finally:
        await client.disconnect()
        await tunnel.stop()


async def _tree(client: OpcuaClient, root_id: str | None, max_depth: int):
    """Recursively browse and print the node tree."""

    async def _walk(node_id, depth, prefix=""):
        children = await client.browse_children(node_id)
        for i, c in enumerate(children):
            is_last = i == len(children) - 1
            connector = "└── " if is_last else "├── "
            val_str = ""
            if c["is_variable"] and c["value"] is not None and c["value"] != "?":
                val_str = f" = {c['value']}"
                dt = c.get("data_type", "")
                if dt:
                    val_str += f" ({dt})"
            print(f"{prefix}{connector}{c['name']}{val_str}")
            if c.get("has_children") and depth < max_depth:
                ext = "    " if is_last else "│   "
                await _walk(c["id"], depth + 1, prefix + ext)

    root_name = "Objects" if root_id is None else root_id
    print(root_name)
    await _walk(root_id, 1)


def main():
    # Use the correct prog name depending on invocation
    prog = sys.argv[0] if sys.argv[0] != "opguia" else "opguia --headless"
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Headless OPC UA client — query, read, write nodes.",
    )
    parser.add_argument("endpoint", help="OPC UA endpoint (e.g. opc.tcp://localhost:4840)")
    parser.add_argument("--ssh", metavar="[user@]host[:port]",
                        help="SSH tunnel through this host before connecting")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="Connection timeout in seconds (default: 5)")

    sub = parser.add_subparsers(dest="command", required=True)

    # browse
    p_browse = sub.add_parser("browse", help="List children of a node")
    p_browse.add_argument("node_id", nargs="?", default=None,
                          help="Node ID to browse (default: Objects folder)")

    # tree
    p_tree = sub.add_parser("tree", help="Recursive tree view")
    p_tree.add_argument("node_id", nargs="?", default=None,
                        help="Root node ID (default: Objects folder)")
    p_tree.add_argument("--depth", type=int, default=2,
                        help="Max recursion depth (default: 2)")

    # read
    p_read = sub.add_parser("read", help="Read node value(s)")
    p_read.add_argument("node_ids", nargs="+", metavar="node_id",
                        help="One or more node IDs to read")

    # write
    p_write = sub.add_parser("write", help="Write a value to a node")
    p_write.add_argument("node_id", help="Node ID to write")
    p_write.add_argument("value", help="Value to write (auto-converted to match node type)")

    # info
    p_info = sub.add_parser("info", help="Full node attributes")
    p_info.add_argument("node_id", help="Node ID to inspect")

    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
