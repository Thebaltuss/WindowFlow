# WindowFlow

**[Русский](README.md) | English**

WindowFlow is a compact Windows desktop application for people who work with multiple monitors and want to restore their applications to the right places quickly.

After restarting a computer, windows often open on the wrong monitor or with the wrong size. Discord, a browser, Spotify, and a code editor may all need to be arranged manually again. WindowFlow remembers the position and size of each window and restores the workspace with one button or automatically.

## Why WindowFlow exists

If you use two or more monitors, you have probably seen this after restarting your PC:

- windows open on the wrong monitor;
- window sizes are reset;
- Discord, the browser, and Spotify must be arranged manually;
- the workspace has to be rebuilt every time;
- useful time is lost before work can begin.

WindowFlow solves this by saving the coordinates and sizes of your applications once and restoring them whenever you need them.

## Features

- Save Windows application positions and sizes.
- Support for multiple monitors.
- Support for negative coordinates when a monitor is placed to the left or above the primary monitor.
- Restore all windows with **Synchronize windows**.
- Automatically restore the workspace when WindowFlow starts.
- Automatically restore saved applications when they appear.
- Match applications by process name and executable path instead of relying only on the window title.
- Discord matching continues to work when the server or window title changes.
- Display real application icons.
- Show **Running** and **Not running** states.
- Capture the current position of an individual window.
- Run in the Windows system tray.
- Reopen WindowFlow with a global shortcut.
- Compact modern dark interface.
- English and Russian interface languages.
- JSON configuration with automatic backups for damaged files.
- Build a Windows `.exe` without a console window.

## How it works

1. Open WindowFlow.
2. Click **Add window**.
3. Select a running application.
4. Add it to the saved list.
5. Arrange your applications across the monitors.
6. Click the capture icon on the required cards.
7. Click **Synchronize windows**.

WindowFlow will remember the workspace. When the PC or the applications are started again, the saved layout can be restored automatically.

## Example workspace

You can save a workspace like this:

| Application | Monitor | Purpose |
|---|---:|---|
| Discord | 2 | Communication and voice chat |
| Spotify | 2 | Music |
| Google Chrome | 1 | Work and browsing |
| Visual Studio Code | 1 | Development |

WindowFlow remembers the coordinates and dimensions of every saved window and restores them after startup.

## Settings

The Settings panel includes:

- **Synchronize on WindowFlow startup** — restore saved positions when WindowFlow opens.
- **Synchronize when saved apps start** — move a saved application as soon as it appears.
- **Global shortcut** — click the shortcut field and press a key combination. It is saved automatically.
- **Language** — switch the interface between English and Russian.
- **Send to tray** — use the tray icon button on the main screen.

The default shortcut is:

```text
Ctrl+Alt+W
```

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer
- `pip`
- Microsoft Edge WebView2 Runtime

WebView2 is normally already installed on Windows 10 and Windows 11. If the interface does not open, install the official Microsoft Edge WebView2 Runtime.

## Installation

Open PowerShell in the project directory and run:

```powershell
python -m venv .venv
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the dependencies:

```powershell
pip install -r requirements.txt
```

If PowerShell blocks activation, use the included batch file:

```bat
start.bat
```

## Run from source

```powershell
python main.py
```

WindowFlow opens as a native desktop application window, not as a regular browser tab.

## Build the EXE

Run:

```bat
build.bat
```

The executable is created at:

```text
dist\WindowFlow.exe
```

The EXE is built without a console window. The Windows icon is generated from `icon.png` and saved as `icon.ico`.

## Configuration location

When running from source, the configuration is stored in the current working directory:

```text
./config.json
```

When running the compiled executable, it is stored at:

```text
%APPDATA%\WindowFlow\config.json
```

Settings survive application and computer restarts. If the JSON file becomes corrupted, WindowFlow creates a timestamped backup and starts with a fresh configuration instead of crashing.

## Why changing window titles does not break matching

WindowFlow does not use HWND as a permanent identifier because Windows can assign a new HWND after an application restart.

Applications are matched using a combination of:

- process name;
- executable path;
- optional title matching.

Changing a Discord server, Chrome tab, YouTube page, or document name therefore does not prevent WindowFlow from finding the application.

## Project structure

```text
window-control/
├── main.py                  # Flask API, native window, tray and hotkey
├── window_manager.py        # Win32 window and monitor operations
├── config_manager.py        # JSON configuration and backups
├── config.json              # Source-mode configuration
├── requirements.txt         # Python dependencies
├── build.bat                # Windows EXE build script
├── windowflow.spec          # PyInstaller configuration
├── icon.png                 # Application logo
├── icon.ico                 # Windows EXE icon
├── templates/
│   └── index.html            # Interface markup
└── static/
    ├── css/
    │   ├── style.css
    │   └── overrides.css
    └── js/
        └── app.js
```

## Local API

The local Flask API provides endpoints for:

- listing running windows;
- retrieving application icons;
- retrieving monitor information;
- adding, editing, and deleting saved windows;
- capturing current coordinates;
- applying one window or the complete workspace;
- managing startup, tray, and hotkey settings.

The server is intended for the local WindowFlow interface and is not configured as a public internet service.

## Creator

Created by **Thebaltusss**.

- Telegram: [t.me/owleo](https://t.me/owleo)
- GitHub: [github.com/Thebaltusss](https://github.com/Thebaltusss)

## License

This project is provided for personal and educational use. Add an appropriate license file, such as the MIT License, before publishing it as an open-source repository.
