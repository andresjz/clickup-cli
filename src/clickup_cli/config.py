from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PATHS = [
    os.environ.get("CLICKUP_CONFIG"),
    ".clickup-cli.yaml",
    str(Path.home() / ".config" / "clickup-cli" / "config.yaml"),
]


class ConfigError(Exception):
    pass


def _strip_nones(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def load_config(path: str | None = None) -> dict[str, Any]:
    candidates = [path] if path else [p for p in DEFAULT_PATHS if p]
    for p in candidates:
        fp = Path(p).expanduser()
        if fp.is_file():
            with fp.open() as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                raise ConfigError(f"{fp}: top-level must be a mapping")
            data["_path"] = str(fp)
            return data
    return {}


def get_team_id(cfg: dict[str, Any]) -> str | None:
    t = cfg.get("team") or {}
    return str(t["id"]) if t.get("id") else None


def resolve_space(cfg: dict[str, Any], name_or_id: str) -> str:
    spaces = cfg.get("spaces") or {}
    if name_or_id in spaces:
        return str(spaces[name_or_id]["id"])
    for s in spaces.values():
        if str(s.get("id")) == name_or_id:
            return name_or_id
    raise ConfigError(f"Space not found in config: {name_or_id!r}")


def resolve_folder(cfg: dict[str, Any], space: str, name_or_id: str) -> str:
    spaces = cfg.get("spaces") or {}
    sp = spaces.get(space) or next((s for s in spaces.values() if str(s.get("id")) == space), None)
    if not sp:
        raise ConfigError(f"Space not found in config: {space!r}")
    folders = sp.get("folders") or {}
    if name_or_id in folders:
        return str(folders[name_or_id]["id"])
    for f in folders.values():
        if str(f.get("id")) == name_or_id:
            return name_or_id
    raise ConfigError(f"Folder {name_or_id!r} not found in space {space!r}")


def resolve_list(cfg: dict[str, Any], space: str, folder: str | None, name_or_id: str) -> str:
    spaces = cfg.get("spaces") or {}
    sp = spaces.get(space) or next((s for s in spaces.values() if str(s.get("id")) == space), None)
    if not sp:
        raise ConfigError(f"Space not found in config: {space!r}")
    if folder:
        folders = sp.get("folders") or {}
        fo = folders.get(folder) or next((f for f in folders.values() if str(f.get("id")) == folder), None)
        if not fo:
            raise ConfigError(f"Folder {folder!r} not found in space {space!r}")
        lists_ = fo.get("lists") or {}
    else:
        lists_ = sp.get("lists") or {}
    if name_or_id in lists_:
        v = lists_[name_or_id]
        return str(v["id"] if isinstance(v, dict) else v)
    for k, v in lists_.items():
        vid = v["id"] if isinstance(v, dict) else v
        if str(vid) == name_or_id:
            return name_or_id
    raise ConfigError(f"List {name_or_id!r} not found in {space}{'/' + folder if folder else ''}")


def template() -> str:
    return """# ClickUp CLI config
# Override location: $CLICKUP_CONFIG
# Token: set $CLICKUP_TOKEN (or use .env)

team:
  id: "<TEAM_ID>"          # required for custom task ID lookups
  name: "<WORKSPACE_NAME>"

defaults:
  space: <SPACE_NAME>      # default --space when omitted
  folder: <FOLDER_NAME>    # default --folder when omitted

spaces:
  <SPACE_NAME>:
    id: "<SPACE_ID>"
    folders:
      <FOLDER_NAME>:
        id: "<FOLDER_ID>"
        lists:
          <LIST_NAME>: "<LIST_ID>"
          # add more as you discover them
  <ANOTHER_SPACE>:
    id: "<ANOTHER_SPACE_ID>"
    # folders: {}
"""
