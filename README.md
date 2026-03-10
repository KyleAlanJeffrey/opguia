# OPGuia

Dead simple OPC UA browser built with Python.

## Install

```bash
pip install opguia
```

## Usage

```bash
opguia
```

Opens a browser at `http://localhost:8080`. Enter an OPC UA endpoint or let it scan for local servers.

## Features

- Auto-scan for OPC UA servers on standard ports
- Tree-table view with inline values, types, and status
- Compact 26px rows — scan hundreds of variables at a glance
- Filter nodes by name
- Click to write writable variables
- Collapsible detail view for full node attributes

## Development

```bash
git clone https://github.com/kyle/opguia
cd opguia
python -m venv .venv
source .venv/bin/activate
pip install -e .
opguia
```
