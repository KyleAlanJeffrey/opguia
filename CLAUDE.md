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
- `opguia/pages/browse.py` — main browse page: sidebar + tree + watch panel + status bar + detail dialog
- `opguia/components/tree_view.py` — tree rendering with typed icons, inline values, status dots
- `opguia/components/detail_panel.py` — full node attributes + write form (used in dialog)
- `opguia/components/watch_panel.py` — live-updating watched variable values (bottom panel)
- `opguia/settings.py` — persistent settings with connection profiles (JSON in OS config dir)
- `opguia/native.py` — platform-specific native window config (dock icon, app name, taskbar)
- `opguia/_native_window.py` — pywebview child process wrapper for macOS icon/name (spawn-safe)
- `opguia/utils.py` — shared constants and helpers (type conversion, timestamp formatting, access level bits)
- `opguia/static/` — favicon (SVG), icon (PNG for macOS, ICO for Windows)

## Conventions

- All OPC UA communication goes through `OpcuaClient` in `client.py` — UI code never touches asyncua directly
- Pages register themselves via `register(client, settings)` called from `app.py`
- Components are factory functions returning UI containers + callback functions
- NiceGUI dark mode is always enabled
- Standard OPC UA port is 4840; scanner also checks 4841-4843, 48400-48401, 48010, 53530
- Settings persist via `Settings` class in `settings.py` — passed to pages from `app.py`

## Releasing

Version is in `opguia/__init__.py` (`__version__`), read by hatch from `pyproject.toml`.

Use the release script:

```bash
./release.sh patch   # 1.1.0 → 1.1.1
./release.sh minor   # 1.1.0 → 1.2.0
./release.sh major   # 1.1.0 → 2.0.0
./release.sh 1.2.3   # explicit version
```

The script auto-bumps the version, builds, generates release notes from git log, commits, tags (annotated with notes), and pushes.

Releases also trigger automatically via GitHub Actions when a commit is pushed to `main` with:
- Commit title matching `vX.Y.Z` (e.g. the version commit from `release.sh`)
- Commit message containing `#release`

The `release.yml` workflow auto-generates release notes, creates a GitHub release, and publishes to PyPI.
