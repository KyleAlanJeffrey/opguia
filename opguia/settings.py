"""Persistent settings — connection profiles, preferences.

Settings are stored as JSON in an OS-appropriate config directory:
  macOS:   ~/Library/Application Support/opguia/settings.json
  Linux:   ~/.config/opguia/settings.json
  Windows: %APPDATA%/opguia/settings.json

Each connection profile stores:
  - name:         display name for the profile
  - url:          OPC UA endpoint URL
  - allow_writes: whether writes are enabled for this connection
  - watched:      list of {name, node_id} for the watch window
  - tree_expanded: list of node_id strings for expanded tree nodes
"""

import json
import sys
from pathlib import Path

_APP_NAME = "opguia"


def _config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_NAME
    elif sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming"
        return base / _APP_NAME
    else:
        return Path.home() / ".config" / _APP_NAME


def _new_profile(name: str, url: str) -> dict:
    return {
        "name": name,
        "url": url,
        "allow_writes": False,
        "watched": [],
        "tree_root": None,      # node_id string or None (Objects)
        "tree_root_path": [],   # breadcrumb path list
        "tree_expanded": [],    # list of expanded node_id strings
        "tunnel_enabled": False,
        "tunnel_ssh_host": "",
        "tunnel_ssh_user": "",
        "tunnel_ssh_port": 22,
    }


class Settings:
    """Read/write persistent JSON settings with connection profiles."""

    def __init__(self):
        self._path = _config_dir() / "settings.json"
        self._data: dict = {}
        self._active_url: str | None = None  # set when connected
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}
            # Wipe old format — no migration, just start fresh
            if "profiles" in data and isinstance(data["profiles"], list):
                self._data = data
            else:
                self._data = {}
        self._data.setdefault("profiles", [])

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    def _find_profile(self, url: str) -> dict | None:
        for p in self._data["profiles"]:
            if p["url"] == url:
                return p
        return None

    # ── Active profile (set by browse page on connect) ──

    def set_active(self, url: str):
        """Set which profile is active based on the connected endpoint."""
        self._active_url = url

    @property
    def active_profile(self) -> dict | None:
        if self._active_url:
            return self._find_profile(self._active_url)
        return None

    # ── Profile CRUD ──

    @property
    def profiles(self) -> list[dict]:
        return self._data.get("profiles", [])

    def add_profile(self, name: str, url: str) -> dict:
        existing = self._find_profile(url)
        if existing:
            # Only update name if explicitly provided (don't overwrite user edits)
            if name and name != url:
                existing["name"] = name
            self._save()
            return existing
        p = _new_profile(name, url)
        self._data["profiles"].append(p)
        self._save()
        return p

    def remove_profile(self, url: str):
        self._data["profiles"] = [p for p in self.profiles if p["url"] != url]
        self._save()

    def rename_profile(self, url: str, new_name: str):
        p = self._find_profile(url)
        if p:
            p["name"] = new_name
            self._save()

    def ensure_profile(self, url: str, server_name: str = ""):
        """Ensure a profile exists for the given URL (creates if missing)."""
        if not self._find_profile(url):
            name = server_name or url
            self.add_profile(name, url)

    # ── Per-profile preferences ──

    @property
    def allow_writes(self) -> bool:
        p = self.active_profile
        return p.get("allow_writes", False) if p else False

    @allow_writes.setter
    def allow_writes(self, value: bool):
        p = self.active_profile
        if p:
            p["allow_writes"] = value
            self._save()

    # ── Tree root (per-profile) ──

    @property
    def tree_root(self) -> str | None:
        p = self.active_profile
        return p.get("tree_root") if p else None

    @tree_root.setter
    def tree_root(self, value: str | None):
        p = self.active_profile
        if p:
            p["tree_root"] = value
            self._save()

    @property
    def tree_root_path(self) -> list[str]:
        p = self.active_profile
        return p.get("tree_root_path", []) if p else []

    @tree_root_path.setter
    def tree_root_path(self, value: list[str]):
        p = self.active_profile
        if p:
            p["tree_root_path"] = value
            self._save()

    # ── Tree expanded state (per-profile) ──

    @property
    def tree_expanded(self) -> list[str]:
        p = self.active_profile
        return p.get("tree_expanded", []) if p else []

    @tree_expanded.setter
    def tree_expanded(self, value: list[str]):
        p = self.active_profile
        if p:
            p["tree_expanded"] = value
            self._save()

    def add_tree_expanded(self, node_id: str):
        p = self.active_profile
        if not p:
            return
        expanded = p.setdefault("tree_expanded", [])
        if node_id not in expanded:
            expanded.append(node_id)
            self._save()

    def remove_tree_expanded(self, node_id: str):
        p = self.active_profile
        if not p:
            return
        expanded = p.get("tree_expanded", [])
        if node_id in expanded:
            expanded.remove(node_id)
            self._save()

    # ── Watched variables (per-profile) ──

    @property
    def watched(self) -> list[dict]:
        p = self.active_profile
        return p.get("watched", []) if p else []

    def add_watched(self, name: str, node_id: str):
        p = self.active_profile
        if not p:
            return
        w = p.setdefault("watched", [])
        if not any(item["node_id"] == node_id for item in w):
            w.append({"name": name, "node_id": node_id})
            self._save()

    def remove_watched(self, node_id: str):
        p = self.active_profile
        if not p:
            return
        p["watched"] = [item for item in p.get("watched", []) if item["node_id"] != node_id]
        self._save()

    def is_watched(self, node_id: str) -> bool:
        return any(item["node_id"] == node_id for item in self.watched)

    # ── Backward compat aliases ──

    @property
    def favorites(self) -> list[dict]:
        return self.watched

    def add_favorite(self, name: str, node_id: str):
        self.add_watched(name, node_id)

    def remove_favorite(self, node_id: str):
        self.remove_watched(node_id)

    def is_favorite(self, node_id: str) -> bool:
        return self.is_watched(node_id)
