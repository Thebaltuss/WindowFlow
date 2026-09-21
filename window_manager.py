"""Windows and monitor discovery/manipulation through Win32."""

from __future__ import annotations

import os
import re
import uuid
import base64
import io
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover - dependency is declared in requirements.txt
    psutil = None

try:
    from PIL import Image, ImageGrab
except ImportError:  # pragma: no cover - dependency is declared in requirements.txt
    Image = ImageGrab = None

try:
    import win32api
    import win32con
    import win32gui
    import win32process
    WINDOWS_AVAILABLE = True
except ImportError:  # Allows the Flask UI to be inspected on non-Windows machines.
    win32api = win32con = win32gui = win32process = None
    WINDOWS_AVAILABLE = False


def _clean(value: Any) -> str:
    return str(value or "").strip().lower()


def _basename(value: str) -> str:
    return Path(value or "").name.lower()


class WindowManager:
    def __init__(self) -> None:
        self.available = WINDOWS_AVAILABLE

    def _process_info(self, pid: int) -> tuple[str, str]:
        if not psutil or not pid:
            return "", ""
        try:
            process = psutil.Process(pid)
            return process.name() or "", process.exe() or ""
        except (psutil.Error, OSError, PermissionError):
            return "", ""

    def _window_record(self, hwnd: int) -> dict[str, Any] | None:
        if not self.available:
            return None
        try:
            title = win32gui.GetWindowText(hwnd).strip()
            if not win32gui.IsWindowVisible(hwnd) or not title:
                return None
            # Never offer WindowFlow itself as a window to save or move.
            if title.lower().startswith(("windowflow", "windowcontrol")):
                return None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name, executable = self._process_info(pid)
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = max(1, right - left)
            height = max(1, bottom - top)
            return {
                "hwnd": int(hwnd),
                "title": title,
                "process_name": process_name,
                "executable": executable,
                "pid": int(pid),
                "x": int(left),
                "y": int(top),
                "width": int(width),
                "height": int(height),
            }
        except (OSError, RuntimeError, TypeError):
            return None

    def list_windows(self) -> list[dict[str, Any]]:
        if not self.available:
            return []
        result: list[dict[str, Any]] = []

        def callback(hwnd: int, _extra: Any) -> None:
            record = self._window_record(hwnd)
            if record:
                result.append(record)

        try:
            win32gui.EnumWindows(callback, None)
        except (OSError, RuntimeError):
            return []
        return sorted(result, key=lambda item: item["title"].lower())

    def get_monitors(self) -> list[dict[str, Any]]:
        if not self.available:
            return [{"id": "monitor-1", "name": "Primary monitor", "x": 0, "y": 0, "width": 1920, "height": 1080, "is_primary": True}]
        monitors: list[dict[str, Any]] = []
        try:
            for index, (handle, _dc, _rect) in enumerate(win32api.EnumDisplayMonitors(), start=1):
                info = win32api.GetMonitorInfo(handle)
                left, top, right, bottom = info["Monitor"]
                work_left, work_top, work_right, work_bottom = info.get("Work", info["Monitor"])
                monitors.append({
                    "id": f"monitor-{index}",
                    "name": info.get("Device", f"Monitor {index}"),
                    "x": int(left),
                    "y": int(top),
                    "width": int(right - left),
                    "height": int(bottom - top),
                    "work_x": int(work_left),
                    "work_y": int(work_top),
                    "work_width": int(work_right - work_left),
                    "work_height": int(work_bottom - work_top),
                    "is_primary": bool(info.get("Flags", 0) & 1),
                })
        except (OSError, RuntimeError):
            return []
        return monitors

    def monitor_for_rect(self, x: int, y: int, width: int, height: int) -> str:
        center_x = x + width / 2
        center_y = y + height / 2
        monitors = self.get_monitors()
        if not monitors:
            return "monitor-1"
        for monitor in monitors:
            if monitor["x"] <= center_x < monitor["x"] + monitor["width"] and monitor["y"] <= center_y < monitor["y"] + monitor["height"]:
                return monitor["id"]
        return min(monitors, key=lambda m: abs(center_x - (m["x"] + m["width"] / 2)) + abs(center_y - (m["y"] + m["height"] / 2)))["id"]

    def capture_by_hwnd(self, hwnd: int) -> dict[str, Any]:
        record = self._window_record(hwnd)
        if not record:
            raise LookupError("Window not found")
        record["monitor"] = self.monitor_for_rect(record["x"], record["y"], record["width"], record["height"])
        return record

    def preview_by_hwnd(self, hwnd: int) -> str:
        """Return a small PNG preview of the currently visible window."""
        if not self.available or ImageGrab is None:
            raise OSError("Window preview is unavailable")
        record = self._window_record(hwnd)
        if not record:
            raise LookupError("Window not found")
        bbox = (
            record["x"],
            record["y"],
            record["x"] + record["width"],
            record["y"] + record["height"],
        )
        try:
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
            image.thumbnail((440, 240))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            return base64.b64encode(buffer.getvalue()).decode("ascii")
        except (OSError, RuntimeError) as exc:
            raise OSError("Could not capture window preview") from exc

    def icon_by_executable(self, executable: str, size: int = 64) -> str:
        """Extract an application icon from its executable and return PNG base64."""
        if not self.available or Image is None or not executable or not os.path.isfile(executable):
            raise OSError("Application icon is unavailable")
        try:
            import win32ui

            hicon = win32gui.ExtractIcon(0, executable, 0)
            if not hicon:
                raise OSError("Application icon is unavailable")

            screen_dc = win32gui.GetDC(0)
            source_dc = win32ui.CreateDCFromHandle(screen_dc)
            memory_dc = source_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(source_dc, size, size)
            memory_dc.SelectObject(bitmap)
            memory_dc.FillSolidRect((0, 0, size, size), win32api.RGB(21, 29, 42))
            win32gui.DrawIconEx(memory_dc.GetSafeHdc(), 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL)

            info = bitmap.GetInfo()
            bits = bitmap.GetBitmapBits(True)
            image = Image.frombuffer(
                "RGB",
                (info["bmWidth"], info["bmHeight"]),
                bits,
                "raw",
                "BGRX",
                0,
                1,
            )
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)

            memory_dc.DeleteDC()
            source_dc.DeleteDC()
            win32gui.ReleaseDC(0, screen_dc)
            win32gui.DeleteObject(bitmap.GetHandle())
            win32gui.DestroyIcon(hicon)
            return base64.b64encode(buffer.getvalue()).decode("ascii")
        except (OSError, RuntimeError, TypeError, KeyError) as exc:
            raise OSError("Could not extract application icon") from exc

    def icon_by_hwnd(self, hwnd: int) -> str:
        record = self._window_record(hwnd)
        if not record:
            raise LookupError("Window not found")
        return self.icon_by_executable(record.get("executable", ""))

    def find_saved_window(self, saved: dict[str, Any]) -> dict[str, Any] | None:
        candidates = self.list_windows()
        if not candidates:
            return None
        target_process = _clean(saved.get("process_name"))
        target_executable = _clean(saved.get("executable"))
        target_exe_name = _basename(target_executable)
        title_match = _clean(saved.get("title_match") or saved.get("window_title"))
        best: tuple[int, dict[str, Any]] | None = None
        for candidate in candidates:
            score = 0
            candidate_process = _clean(candidate.get("process_name"))
            candidate_executable = _clean(candidate.get("executable"))
            process_match = bool(target_process and (candidate_process == target_process or _basename(candidate_process) == _basename(target_process)))
            executable_match = bool(target_executable and (candidate_executable == target_executable or _basename(candidate_executable) == target_exe_name))

            # Process/executable identify an application more reliably than its
            # title. Discord changes its title every time the server changes.
            if target_process or target_executable:
                if process_match:
                    score += 70
                if executable_match:
                    score += 80
                if not process_match and not executable_match:
                    continue
            if title_match and title_match in _clean(candidate.get("title")):
                score += 30
            elif title_match:
                score -= 1
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, candidate)
        return best[1] if best else None

    def apply_saved_window(self, saved: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            raise OSError("Win32 APIs are available only on Windows")
        match = self.find_saved_window(saved)
        if not match:
            raise LookupError("Window not found")
        hwnd = match["hwnd"]
        x = int(saved.get("x", 0))
        y = int(saved.get("y", 0))
        width = max(80, int(saved.get("width", match["width"])))
        height = max(60, int(saved.get("height", match["height"])))
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetWindowPos(hwnd, None, x, y, width, height, win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
        except (OSError, RuntimeError) as exc:
            raise OSError(str(exc)) from exc
        return {"hwnd": hwnd, "title": match["title"], "x": x, "y": y, "width": width, "height": height}

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def sanitize_process_name(name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._ -]", "", name or "")
