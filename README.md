# Is The Port Open (ITPO)

A simple desktop app to quickly check whether a TCP port is reachable (OPEN/CLOSED/TIMEOUT/DNS_FAIL) across multiple targets with a clean UI, fast concurrent checks, and persistent saved targets.

## Features

- Check many hosts/ports at once using a thread pool
- Status chips: `OPEN (latency)`, `CLOSED`, `TIMEOUT`, `DNS_FAIL`, `ERROR`
- Add targets in-app with **+**
- Remove targets with **✕**
- Settings UI:
  - Timeout (seconds)
  - Max workers (concurrency)
  - Auto refresh (seconds; `0` disables)
- Automatically saves targets + settings to an ini file

## Download (Windows)

Grab the latest `IsThePortOpen.exe` from the GitHub Releases page.

> **Windows-only:** The `.exe` build runs only on Windows.

## Config File Location

The app stores its config in:

- **Windows:** `%APPDATA%\IsThePortOpen\itpo.ini`

This file contains:

- `[SETTINGS]` — timeout, max workers, auto refresh  
- `[TARGETS]` — saved targets in `Name = host:port` format

## Building From Source (Windows)

### Requirements
- Python 3.10+ recommended
- `customtkinter`

Install dependencies:

```bash
pip install customtkinter
```

### Run the app:
python main.py

### Building the EXE (Windows)
Install PyInstaller:
```bash
pip install pyinstaller
```
Build:
```bash
pyinstaller --onefile --windowed --name "IsThePortOpen" main.py
```
The executable will be located at:
- ```dist\IsThePortOpen.exe```

### Usage
1. Launch the app
2. Click + to add a target (Name, Host, Port)
3. Upon adding, list should auto refresh
4. Manually refresh with the 'Refresh' button
5. Use Settings to adjust timeout/concurrency/auto-refresh




