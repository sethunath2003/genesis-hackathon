<!-- Copilot / Agent instructions for the Genesis repo -->
# Agent Quickstart: Genesis Secure Environment

Purpose: Help code-generating agents be productive quickly in this repo.

**Big picture**
- `tray_app.py`: entry point — launches `CleanupService` and `USBHandler` in background threads and drives the system tray UI.
- `cleanup_service.py`: file-monitoring service using `watchdog.Observer`; watches `auto_print_path` and `monitored_paths` from `config.json` and enforces TTL-based deletion.
- `usb_handler.py`: Windows-only WMI-based USB monitor. Provides `secure_import()` which copies allowed extensions into the `quarantine_path`.
- `config.json`: single source of runtime configuration (paths, TTL, allowed extensions).

**Run / build / debug**
- Install deps: `pip install -r requirements.txt` (Windows required due to WMI).
- Run app (local dev): `python tray_app.py` — this starts the tray UI and both services.
- To run only the cleanup service: `python cleanup_service.py`.

**Repo-specific patterns & gotchas**
- Paths are stored in `config.json` and expanded with `os.path.expanduser(...)` — modify config defaults rather than hardcoding paths in code.
- Timers are implemented with `threading.Timer(...)` (TTL cleanup and delayed secure delete after print). Expect non-deterministic timing in tests.
- WMI usage: `USBHandler.monitor_usb()` calls `pythoncom.CoInitialize()` in-thread and uses `Win32_VolumeChangeEvent.watch_for(...)` with a small timeout loop — watcher can block; stopping threads requires careful handling (current `stop()` uses a short join timeout).
- Printing uses `os.startfile(file, 'print')` and assumes a Windows environment / configured printer.

**Integration points / external deps**
- `wmi` + `pythoncom` — Windows-only USB detection ([usb_handler.py](usb_handler.py#L1)).
- `watchdog` — file system events ([cleanup_service.py](cleanup_service.py#L1)).
- `pystray`, `Pillow` (PIL) — tray icon and image generation ([tray_app.py](tray_app.py#L1)).
- `requirements.txt` lists these dependencies; prefer adding new deps there.

**What to change and where (concrete examples)**
- Add a new monitored folder: update `config.json` -> `monitored_paths` and the `CleanupHandler` will pick it up on next start (uses `os.path.expanduser`).
- Extend upload policy: modify `file_upload_extensions` in `config.json`; `USBHandler.secure_import()` enforces this list.
- Improve stopping behavior: modify `USBHandler.stop()` to signal and join the WMI watcher more robustly (see `monitor_usb()` for `watcher(timeout_ms=...)`).

**Agent-generation rules (how AI should edit code here)**
- Prefer config changes over hard-coded path edits; reference `config.json` keys.
- When adding features that affect runtime behavior (timers, threads, WMI watchers), include tests or a small runnable example and ensure cross-thread COM initialization (`pythoncom.CoInitialize()`).
- Keep Windows-only APIs clearly gated — add a runtime check early (e.g., `if os.name != 'nt': raise RuntimeError('Windows only')`) when adding new WMI/`os.startfile` features.

Files to inspect first
- [cleanup_service.py](cleanup_service.py#L1-L200): TTL, AutoPrint handling, `secure_delete()`
- [usb_handler.py](usb_handler.py#L1-L200): WMI watcher, `secure_import()`, allowed extensions
- [tray_app.py](tray_app.py#L1-L200): app entry, tray menu callbacks, how services are started
- [config.json](config.json#L1-L40): runtime tunables

If unsure, ask the maintainer for which Windows environments to target (consumer kiosks vs managed estate) before adding persistent services or Windows Service wrappers.

Next step: ask the user which areas you should modify or prototype first (USB flow, AutoPrint reliability, or safer thread shutdown).
