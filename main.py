"""WindowFlow entry point and Flask API."""

from __future__ import annotations

import os
import ctypes
import re
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file

from config_manager import ConfigManager
from window_manager import WindowManager


BASE_DIR = Path(__file__).resolve().parent
IS_FROZEN = bool(getattr(sys, "frozen", False))
if IS_FROZEN:
    APP_DATA_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "WindowFlow"
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH = APP_DATA_DIR / "config.json"
else:
    APP_DATA_DIR = Path.cwd()
    CONFIG_PATH = Path.cwd() / "config.json"
config = ConfigManager(CONFIG_PATH)
window_manager = WindowManager()
desktop_window = None
tray_icon = None
tray_thread = None
hotkey_thread = None
hotkey_stop = threading.Event()


def ok(data: Any = None, message: str | None = None, status: int = 200):
    payload: dict[str, Any] = {"ok": True}
    if data is not None:
        payload["data"] = data
    if message:
        payload["message"] = message
    return jsonify(payload), status


def fail(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def active_windows() -> list[dict[str, Any]]:
    return config.windows()


def status_payload() -> dict[str, Any]:
    saved = active_windows()
    statuses = []
    running = 0
    for item in saved:
        match = window_manager.find_saved_window(item)
        is_running = match is not None
        running += int(is_running)
        statuses.append({
            "id": item.get("id"),
            "status": "running" if is_running else "missing",
            "hwnd": match.get("hwnd") if match else None,
            "current_title": match.get("title") if match else None,
        })
    return {
        "windows": statuses,
        "running": running,
        "missing": len(saved) - running,
        "saved": len(saved),
        "monitors": len(window_manager.get_monitors()),
        "active_layout": config.active_layout_name(),
    }


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/icon.png")
    def app_icon():
        return send_file(BASE_DIR / "icon.png", mimetype="image/png", max_age=86400)

    @app.get("/api/windows")
    def api_windows():
        return ok(window_manager.list_windows())

    @app.get("/api/windows/preview/<int:hwnd>")
    def api_window_preview(hwnd: int):
        try:
            image = window_manager.preview_by_hwnd(hwnd)
            return ok({"image": f"data:image/png;base64,{image}"})
        except (LookupError, OSError) as exc:
            return fail(str(exc), 404)

    @app.get("/api/windows/icon/by-hwnd/<int:hwnd>")
    def api_window_icon_by_hwnd(hwnd: int):
        try:
            icon = window_manager.icon_by_hwnd(hwnd)
            return ok({"image": f"data:image/png;base64,{icon}"})
        except (LookupError, OSError) as exc:
            return fail(str(exc), 404)

    @app.get("/api/monitors")
    def api_monitors():
        return ok(window_manager.get_monitors())

    @app.get("/api/layouts")
    def api_layouts():
        return ok(config.snapshot())

    @app.post("/api/layouts")
    def api_create_layout():
        payload = request.get_json(silent=True) or {}
        try:
            config.create_layout(str(payload.get("name", "")), payload.get("source"))
            return ok(config.snapshot(), "Layout created", 201)
        except (ValueError, KeyError) as exc:
            return fail(str(exc))

    @app.post("/api/layouts/<path:name>/rename")
    def api_rename_layout(name: str):
        payload = request.get_json(silent=True) or {}
        try:
            config.rename_layout(name, str(payload.get("name", "")))
            return ok(config.snapshot(), "Layout renamed")
        except (ValueError, KeyError) as exc:
            return fail(str(exc))

    @app.post("/api/layouts/<path:name>/duplicate")
    def api_duplicate_layout(name: str):
        payload = request.get_json(silent=True) or {}
        try:
            config.create_layout(str(payload.get("name", "")), name)
            return ok(config.snapshot(), "Layout duplicated")
        except (ValueError, KeyError) as exc:
            return fail(str(exc))

    @app.delete("/api/layouts/<path:name>")
    def api_delete_layout(name: str):
        try:
            config.delete_layout(name)
            return ok(config.snapshot(), "Layout deleted")
        except (ValueError, KeyError) as exc:
            return fail(str(exc))

    @app.post("/api/layouts/<path:name>/select")
    def api_select_layout(name: str):
        try:
            config.set_active_layout(name)
            return ok(config.snapshot())
        except KeyError:
            return fail("Layout not found", 404)

    @app.post("/api/layouts/<path:name>/apply")
    def api_apply_named_layout(name: str):
        try:
            config.set_active_layout(name)
            return apply_layout_response()
        except KeyError:
            return fail("Layout not found", 404)

    @app.post("/api/layouts/<path:name>/capture")
    def api_capture_named_layout(name: str):
        try:
            if name != config.active_layout_name():
                config.set_active_layout(name)
            count = capture_all()
            return ok(config.snapshot(), f"Captured {count[0]}/{count[1]} windows")
        except KeyError:
            return fail("Layout not found", 404)

    @app.post("/api/windows/add")
    def api_add_window():
        payload = request.get_json(silent=True) or {}
        try:
            hwnd = int(payload.get("hwnd"))
            current = window_manager.capture_by_hwnd(hwnd)
            title = current["title"]
            record = {
                "id": window_manager.new_id(),
                "display_name": str(payload.get("display_name") or title),
                "window_title": title,
                "title_match": str(payload.get("title_match") or title),
                "process_name": current.get("process_name", ""),
                "executable": current.get("executable", ""),
                "x": current["x"], "y": current["y"],
                "width": current["width"], "height": current["height"],
                "monitor": current["monitor"],
            }
            config.add_window(record)
            return ok(record, "Window added", 201)
        except (TypeError, ValueError, LookupError, OSError) as exc:
            return fail(str(exc))

    def find_record(window_id: str) -> dict[str, Any]:
        for item in config.windows():
            if item.get("id") == window_id:
                return item
        raise KeyError(window_id)

    @app.get("/api/windows/<window_id>/icon")
    def api_saved_window_icon(window_id: str):
        try:
            saved = find_record(window_id)
            icon = window_manager.icon_by_executable(saved.get("executable", ""))
            return ok({"image": f"data:image/png;base64,{icon}"})
        except (KeyError, OSError) as exc:
            return fail(str(exc), 404)

    @app.put("/api/windows/<window_id>")
    def api_update_window(window_id: str):
        payload = request.get_json(silent=True) or {}
        allowed = {"display_name", "window_title", "title_match", "process_name", "executable", "monitor", "x", "y", "width", "height"}
        updates: dict[str, Any] = {key: payload[key] for key in allowed if key in payload}
        for key in ("x", "y", "width", "height"):
            if key in updates:
                try:
                    updates[key] = int(updates[key])
                except (TypeError, ValueError):
                    return fail(f"{key} must be a number")
        try:
            return ok(config.update_window(window_id, updates), "Window updated")
        except KeyError:
            return fail("Window not found", 404)

    @app.delete("/api/windows/<window_id>")
    def api_delete_window(window_id: str):
        try:
            config.remove_window(window_id)
            return ok(message="Window deleted")
        except KeyError:
            return fail("Window not found", 404)

    @app.post("/api/windows/<window_id>/capture")
    def api_capture_window(window_id: str):
        try:
            saved = find_record(window_id)
            match = window_manager.find_saved_window(saved)
            if not match:
                return fail("Window not found", 404)
            current = window_manager.capture_by_hwnd(match["hwnd"])
            updated = config.update_window(window_id, {key: current[key] for key in ("x", "y", "width", "height", "monitor")})
            return ok(updated, f"{updated.get('display_name', 'Window')} position captured")
        except KeyError:
            return fail("Window not found", 404)
        except (LookupError, OSError) as exc:
            return fail(str(exc), 404)

    @app.post("/api/windows/<window_id>/apply")
    def api_apply_window(window_id: str):
        try:
            saved = find_record(window_id)
            result = window_manager.apply_saved_window(saved)
            return ok(result, f"{saved.get('display_name', 'Window')} moved successfully")
        except KeyError:
            return fail("Window not found", 404)
        except (LookupError, OSError) as exc:
            return fail(str(exc), 404)

    @app.post("/api/layout/apply")
    def api_apply_layout():
        return apply_layout_response()

    @app.post("/api/layout/capture-all")
    def api_capture_all():
        captured, total = capture_all()
        return ok(config.snapshot(), f"Captured {captured}/{total} windows")

    @app.post("/api/layout/save")
    def api_save_layout():
        config.save()
        return ok(config.snapshot(), "Layout saved")

    @app.get("/api/status")
    def api_status():
        return ok(status_payload())

    @app.post("/api/settings")
    def api_settings():
        values = request.get_json(silent=True) or {}
        config.update_settings(values)
        if "hotkey" in values:
            start_hotkey_listener()
        return ok(config.snapshot(), "Settings saved")

    @app.post("/api/tray/hide")
    def api_tray_hide():
        if not start_tray():
            return fail("System tray is unavailable. Install pystray and Pillow.", 503)
        if desktop_window is not None:
            desktop_window.hide()
        return ok(message="WindowFlow is running in the system tray")

    return app


def apply_layout_response():
    results = []
    for saved in active_windows():
        try:
            window_manager.apply_saved_window(saved)
            results.append({"id": saved.get("id"), "status": "applied", "name": saved.get("display_name")})
        except (LookupError, OSError) as exc:
            results.append({"id": saved.get("id"), "status": "missing", "name": saved.get("display_name"), "error": str(exc)})
    applied = sum(item["status"] == "applied" for item in results)
    total = len(results)
    return ok({"results": results}, f"Synchronized: {applied}/{total} windows")


def capture_all() -> tuple[int, int]:
    records = active_windows()
    captured = 0
    for saved in records:
        match = window_manager.find_saved_window(saved)
        if not match:
            continue
        try:
            current = window_manager.capture_by_hwnd(match["hwnd"])
            config.update_window(saved["id"], {key: current[key] for key in ("x", "y", "width", "height", "monitor")})
            captured += 1
        except (LookupError, OSError):
            continue
    return captured, len(records)


def auto_apply_worker() -> None:
    """Apply a saved position when a previously missing app appears."""
    previous: dict[str, bool] = {}
    while True:
        try:
            if not config.snapshot().get("auto_apply_windows", False):
                time.sleep(2)
                continue
            for saved in active_windows():
                window_id = str(saved.get("id"))
                is_running = window_manager.find_saved_window(saved) is not None
                was_running = previous.get(window_id)
                if is_running and was_running is False:
                    try:
                        window_manager.apply_saved_window(saved)
                    except (LookupError, OSError):
                        pass
                previous[window_id] = is_running
            time.sleep(2)
        except Exception:
            time.sleep(2)


def show_window() -> None:
    if desktop_window is not None:
        desktop_window.show()
        desktop_window.restore()


def start_tray() -> bool:
    """Start the WindowFlow tray icon once and keep it available."""
    global tray_icon, tray_thread
    if tray_icon is not None:
        return True
    try:
        import pystray
        from PIL import Image
        image = Image.open(BASE_DIR / "icon.png").convert("RGBA")
    except (ImportError, OSError):
        return False

    def open_ui(_icon, _item):
        show_window()

    def apply(_icon, _item):
        apply_layout_response()

    def exit_app(icon, _item):
        icon.stop()
        if desktop_window is not None:
            desktop_window.destroy()

    tray_icon = pystray.Icon("WindowFlow", image, "WindowFlow", menu=pystray.Menu(
        pystray.MenuItem("Open WindowFlow", open_ui),
        pystray.MenuItem("Synchronize windows", apply),
        pystray.MenuItem("Exit", exit_app),
    ))
    tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
    tray_thread.start()
    return True


def parse_hotkey(value: str) -> tuple[int, int] | None:
    parts = [part.strip().upper() for part in re.split(r"\+", value or "") if part.strip()]
    if not parts:
        return None
    modifiers = 0
    modifier_values = {"CTRL": 0x0002, "CONTROL": 0x0002, "ALT": 0x0001, "SHIFT": 0x0004, "WIN": 0x0008, "WINDOWS": 0x0008}
    for part in parts[:-1]:
        if part not in modifier_values:
            return None
        modifiers |= modifier_values[part]
    key = parts[-1]
    if len(key) == 1:
        return modifiers, ord(key)
    if key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        return modifiers, 0x70 + int(key[1:]) - 1
    return None


def start_hotkey_listener() -> None:
    """Register the configured global hotkey used to restore the hidden window."""
    global hotkey_thread, hotkey_stop
    hotkey_stop.set()
    hotkey_stop = threading.Event()
    hotkey_thread = threading.Thread(target=hotkey_worker, args=(hotkey_stop,), daemon=True)
    hotkey_thread.start()


def hotkey_worker(stop_event: threading.Event) -> None:
    if os.name != "nt":
        return
    parsed = parse_hotkey(str(config.snapshot().get("hotkey", "Ctrl+Alt+W")))
    if parsed is None:
        return
    modifiers, virtual_key = parsed
    user32 = ctypes.windll.user32
    hotkey_id = 9182
    if not user32.RegisterHotKey(None, hotkey_id, modifiers, virtual_key):
        return
    try:
        message = wintypes.MSG()
        while not stop_event.is_set():
            while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                if message.message == 0x0312:
                    show_window()
            time.sleep(0.08)
    finally:
        user32.UnregisterHotKey(None, hotkey_id)


def main() -> None:
    global desktop_window
    app = create_app()
    port = int(os.environ.get("WINDOWCONTROL_PORT", "5000"))
    server_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    server_thread.start()
    time.sleep(0.8)
    if config.snapshot().get("apply_on_startup"):
        threading.Thread(target=lambda: (time.sleep(2), apply_layout_response()), daemon=True).start()
    threading.Thread(target=auto_apply_worker, daemon=True).start()
    try:
        import webview
    except ImportError as exc:
        raise SystemExit("pywebview is required. Run: pip install -r requirements.txt") from exc

    desktop_window = webview.create_window(
        "WindowFlow — Window Layout Manager",
        f"http://127.0.0.1:{port}",
        width=430,
        height=650,
        min_size=(360, 480),
        resizable=True,
        text_select=True,
    )
    start_hotkey_listener()
    if config.snapshot().get("minimize_to_tray"):
        start_tray()
        desktop_window.hide()
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
