# OPGuia — OPC UA Browser

## Stack

- **asyncua** — async OPC UA client
- **NiceGUI** — UI + server

## Design Principles

- **Tree dominates the screen.** No sidebars, no tabs, no cards. Just: top bar, search, tree, status bar.
- **Tree-table hybrid.** Each variable row shows: `Name | Value | Type | Status` in aligned columns. Hundreds of values scannable at a glance.
- **Compact dense rows.** ~26px row height. VSCode explorer density. Thousands of variables must fit.
- **Values shown inline.** No clicking to see values. The tree IS a live variable monitor.
- **Fast filtering.** Search bar filters nodes by name. Supports partial match (e.g. `motor`, `temp`, `drive.speed`).
- **Minimal chrome.** Top bar: server name + status. Search bar. Tree. Status bar: endpoint + latency.

## Layout

```
┌──────────────────────────────────────────────────────────────┐
│ OPC UA Browser                    Server: PLC-Line-1 ●       │
├──────────────────────────────────────────────────────────────┤
│ Search: [                                                  ] │
├──────────────────────────────────────────────────────────────┤
│  ▾ Objects                                                   │
│      ▾ Drive                                                 │
│          MotorSpeed         1520.3       Float          ●    │
│          ConveyorReady      TRUE         Bool           ●    │
│      ▾ Sensors                                               │
│          TempSensor1        68.4         Float          ●    │
│      ▾ Alarms                                                │
│          AlarmActive        FALSE        Bool           ⚠    │
├──────────────────────────────────────────────────────────────┤
│ Endpoint: opc.tcp://...  │ Latency: 28ms │ Security: None    │
└──────────────────────────────────────────────────────────────┘
```

## Node Icons

- `📁` Folder/Object
- `🔢` Variable (numeric)
- `🔘` Bool
- `📝` String
- `⚙` Method
- Status: `●` good, `●` warning (yellow), `●` bad (red)

## Project Structure

```
main.py
opguia/
  app.py              # wires pages + runs NiceGUI
  client.py           # OPC UA client wrapper
  scanner.py          # server discovery
  settings.py         # persistent profiles + preferences
  native.py           # platform-specific window config
  _native_window.py   # macOS icon/name (pywebview child)
  utils.py            # type conversion, formatting
  static/             # favicon.svg, icon.png, icon.ico
  pages/
    connection.py     # connect page
    browse.py         # main browse page
  components/
    tree_view.py      # tree-table rendering
    detail_panel.py   # node detail dialog + write
    watch_panel.py    # live variable watch panel
```
