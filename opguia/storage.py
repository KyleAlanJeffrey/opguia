"""Persistent storage — app directories, settings, connection profiles.

Uses platformdirs for OS-appropriate directory paths:
  Config:  ~/Library/Application Support/opguia  (macOS)
  Data:    ~/Library/Application Support/opguia  (macOS)
  Cache:   ~/Library/Caches/opguia               (macOS)
  Log:     ~/Library/Logs/opguia                  (macOS)
  (Linux/Windows: XDG / AppData equivalents)

Settings are stored as JSON in the config directory.
"""

import json
from pathlib import Path
from platformdirs import user_config_dir, user_data_dir, user_cache_dir, user_log_dir

_APP_NAME = "opguia"

# ── App directories ──

def config_dir() -> Path:
    """OS-appropriate config directory (settings, profiles)."""
    return Path(user_config_dir(_APP_NAME, ensure_exists=True))

def data_dir() -> Path:
    """OS-appropriate data directory (exports, saved state)."""
    return Path(user_data_dir(_APP_NAME, ensure_exists=True))

def cache_dir() -> Path:
    """OS-appropriate cache directory (temporary files)."""
    return Path(user_cache_dir(_APP_NAME, ensure_exists=True))

def log_dir() -> Path:
    """OS-appropriate log directory."""
    return Path(user_log_dir(_APP_NAME, ensure_exists=True))


# ── Profile schema ──

def _new_profile(name: str, url: str) -> dict:
    return {
        "name": name,
        "url": url,
        "allow_writes": False,
        "watched": [],
        "tree_root": None,
        "tree_root_path": [],
        "tree_expanded": [],
        "tunnel_enabled": False,
        "tunnel_ssh_host": "",
        "tunnel_ssh_user": "",
        "tunnel_ssh_port": 22,
    }


# ── Settings ──

class Settings:
    """Read/write persistent JSON settings with connection profiles."""

    def __init__(self):
        self._path = config_dir() / "settings.json"
        self._data: dict = {}
        self._active_url: str | None = None
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}
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

    # ── Active profile ──

    def set_active(self, url: str):
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

    # ── Tree root ──

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

    # ── Tree expanded state ──

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

    # ── Watched variables ──

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

    # ── Aliases ──

    @property
    def favorites(self) -> list[dict]:
        return self.watched

    def add_favorite(self, name: str, node_id: str):
        self.add_watched(name, node_id)

    def remove_favorite(self, node_id: str):
        self.remove_watched(node_id)

    def is_favorite(self, node_id: str) -> bool:
        return self.is_watched(node_id)
