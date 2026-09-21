"""Persistent JSON configuration for WindowFlow."""

from __future__ import annotations

import copy
import json
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "active_layout": "Default",
    "apply_on_startup": False,
    "auto_apply_windows": False,
    "hotkey": "Ctrl+Alt+W",
    "language": "en",
    "minimize_to_tray": False,
    "layouts": {"Default": {"windows": []}},
}


class ConfigManager:
    """Load, validate and atomically save the application's JSON config."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            data = copy.deepcopy(DEFAULT_CONFIG)
            self._write(data)
            return data

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            return self._normalize(raw)
        except (OSError, ValueError, TypeError):
            backup = self.path.with_name(
                f"{self.path.stem}.corrupt.{datetime.now():%Y%m%d-%H%M%S}{self.path.suffix}"
            )
            try:
                shutil.copy2(self.path, backup)
            except OSError:
                pass
            data = copy.deepcopy(DEFAULT_CONFIG)
            self._write(data)
            return data

    @staticmethod
    def _normalize(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("Configuration root must be an object")

        result = copy.deepcopy(DEFAULT_CONFIG)
        result["active_layout"] = str(raw.get("active_layout") or "Default")
        result["apply_on_startup"] = bool(raw.get("apply_on_startup", False))
        result["auto_apply_windows"] = bool(raw.get("auto_apply_windows", False))
        result["hotkey"] = str(raw.get("hotkey") or "Ctrl+Alt+W")
        result["language"] = "ru" if str(raw.get("language") or "en").lower() == "ru" else "en"
        result["minimize_to_tray"] = bool(raw.get("minimize_to_tray", False))
        layouts = raw.get("layouts")
        if isinstance(layouts, dict):
            result["layouts"] = {}
            for name, layout in layouts.items():
                clean_name = str(name).strip()
                if not clean_name:
                    continue
                windows = layout.get("windows", []) if isinstance(layout, dict) else []
                result["layouts"][clean_name] = {
                    "windows": windows if isinstance(windows, list) else []
                }

        if not result["layouts"]:
            result["layouts"] = {"Default": {"windows": []}}
        if result["active_layout"] not in result["layouts"]:
            result["active_layout"] = next(iter(result["layouts"]))
        return result

    def _write(self, data: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, self.path)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self.data)

    def save(self) -> None:
        with self._lock:
            self._write(self.data)

    def active_layout_name(self) -> str:
        with self._lock:
            return self.data["active_layout"]

    def active_layout(self) -> dict[str, Any]:
        with self._lock:
            return self.data["layouts"][self.data["active_layout"]]

    def set_active_layout(self, name: str) -> None:
        with self._lock:
            if name not in self.data["layouts"]:
                raise KeyError(name)
            self.data["active_layout"] = name
            self.save()

    def get_layout(self, name: str | None = None) -> dict[str, Any]:
        with self._lock:
            layout_name = name or self.data["active_layout"]
            if layout_name not in self.data["layouts"]:
                raise KeyError(layout_name)
            return copy.deepcopy(self.data["layouts"][layout_name])

    def create_layout(self, name: str, source: str | None = None) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Layout name cannot be empty")
        with self._lock:
            if clean_name in self.data["layouts"]:
                raise ValueError("A layout with this name already exists")
            source_layout = self.data["layouts"].get(source or self.data["active_layout"], {"windows": []})
            self.data["layouts"][clean_name] = copy.deepcopy(source_layout)
            self.data["active_layout"] = clean_name
            self.save()

    def rename_layout(self, old_name: str, new_name: str) -> None:
        clean_name = new_name.strip()
        with self._lock:
            if old_name not in self.data["layouts"]:
                raise KeyError(old_name)
            if not clean_name:
                raise ValueError("Layout name cannot be empty")
            if clean_name != old_name and clean_name in self.data["layouts"]:
                raise ValueError("A layout with this name already exists")
            self.data["layouts"][clean_name] = self.data["layouts"].pop(old_name)
            if self.data["active_layout"] == old_name:
                self.data["active_layout"] = clean_name
            self.save()

    def delete_layout(self, name: str) -> None:
        with self._lock:
            if len(self.data["layouts"]) == 1:
                raise ValueError("At least one layout must remain")
            if name not in self.data["layouts"]:
                raise KeyError(name)
            del self.data["layouts"][name]
            if self.data["active_layout"] == name:
                self.data["active_layout"] = next(iter(self.data["layouts"]))
            self.save()

    def update_settings(self, values: dict[str, Any]) -> None:
        with self._lock:
            for key in ("apply_on_startup", "auto_apply_windows", "minimize_to_tray"):
                if key in values:
                    self.data[key] = bool(values[key])
            if "hotkey" in values and str(values["hotkey"]).strip():
                self.data["hotkey"] = str(values["hotkey"]).strip()
            if "language" in values:
                self.data["language"] = "ru" if str(values["language"]).lower() == "ru" else "en"
            self.save()

    def windows(self, layout_name: str | None = None) -> list[dict[str, Any]]:
        return self.get_layout(layout_name).get("windows", [])

    def add_window(self, record: dict[str, Any], layout_name: str | None = None) -> None:
        with self._lock:
            layout = self.data["layouts"][layout_name or self.data["active_layout"]]
            layout.setdefault("windows", []).append(copy.deepcopy(record))
            self.save()

    def update_window(self, window_id: str, updates: dict[str, Any], layout_name: str | None = None) -> dict[str, Any]:
        with self._lock:
            layout = self.data["layouts"][layout_name or self.data["active_layout"]]
            for record in layout.get("windows", []):
                if record.get("id") == window_id:
                    record.update(copy.deepcopy(updates))
                    self.save()
                    return copy.deepcopy(record)
            raise KeyError(window_id)

    def remove_window(self, window_id: str, layout_name: str | None = None) -> None:
        with self._lock:
            layout = self.data["layouts"][layout_name or self.data["active_layout"]]
            before = len(layout.get("windows", []))
            layout["windows"] = [item for item in layout.get("windows", []) if item.get("id") != window_id]
            if len(layout["windows"]) == before:
                raise KeyError(window_id)
            self.save()
