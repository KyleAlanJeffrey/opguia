# OPGuia — OPC UA Browser

## Overview

A clean OPC UA browser built with Python. Connect to a server, browse the address space as a tree with inline data types, values, and status indicators. Click nodes to see full details or write values.

## Stack

- **asyncua** — OPC UA client (async)
- **NiceGUI** — Full UI + server in one

## UI

### Connection Page (/)
- Endpoint URL input, pre-filled with `opc.tcp://localhost:4840`
- Auto-scans common OPC UA ports for active servers
- Connect button → navigates to browse page on success

### Browse Page (/browse)
- **Header**: App name, server name, connected badge
- **Left sidebar**: Search box, active connections list
- **Main area**: Full-width lazy-loaded tree
  - Color-coded icons per data type (Bool=green, Float=blue, Int=orange, String=teal)
  - Inline data type label + current value + status dots (green/yellow/red)
  - Click to expand folders/complex variables, click leaf variables for detail dialog
  - Double-click any node for full detail dialog with all OPC UA attributes
  - "Set as tree root" to re-root the tree at any object node
- **Status bar**: Endpoint, security policy, live latency
- **Detail dialog**: Node ID, browse name, class, data type, access level, timestamps, value, write form for writable variables

## Project Structure

```
main.py                       # entry point
opguia/
  app.py                      # wires pages + runs NiceGUI
  client.py                   # OPC UA client wrapper
  scanner.py                  # port scanning / server discovery
  utils.py                    # shared helpers (type conversion, formatting)
  pages/
    connection.py             # connect page
    browse.py                 # main browse page
  components/
    tree_view.py              # tree rendering with icons/types/values
    detail_panel.py           # node detail + write controls
```
