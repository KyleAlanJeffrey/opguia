# OPGuia

OPC UA browser built with Python, asyncua, and NiceGUI.

## Quick Start

```bash
source .venv/bin/activate
python main.py
# Opens at http://localhost:8080
```

## Architecture

- `main.py` is the entry point, calls `opguia.app.run()`
- `opguia/client.py` — async wrapper around asyncua (connect, browse, read, write, latency)
- `opguia/scanner.py` — probes common OPC UA ports for server discovery
- `opguia/pages/connection.py` — connection page with endpoint input + auto-scan
- `opguia/pages/browse.py` — main browse page: sidebar + tree + status bar + detail dialog
- `opguia/components/tree_view.py` — tree rendering with typed icons, inline values, status dots
- `opguia/components/detail_panel.py` — full node attributes + write form (used in dialog)
- `opguia/utils.py` — shared constants and helpers (type conversion, timestamp formatting, access level bits)

## Conventions

- All OPC UA communication goes through `OpcuaClient` in `client.py` — UI code never touches asyncua directly
- Pages register themselves via `register(client)` called from `app.py`
- Components are factory functions returning UI containers + callback functions
- NiceGUI dark mode is always enabled
- Standard OPC UA port is 4840; scanner also checks 4841-4843, 48400-48401, 48010, 53530
