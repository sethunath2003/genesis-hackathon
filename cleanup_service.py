import time
import os
import json
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class CleanupHandler(FileSystemEventHandler):
    def __init__(self, config):
        self.config = config
        self.auto_print_path = os.path.expanduser(config.get('auto_print_path', ''))
        self.monitored_paths = [os.path.expanduser(p) for p in config.get('monitored_paths', [])]
        self.ttl_minutes = config.get('cleanup_interval_minutes', 1)

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        print(f"File detected (created): {file_path}")

        # Ignore temporary download / partial files
        temp_exts = ('.crdownload', '.part', '.tmp', '.download')
        if file_path.lower().endswith(temp_exts):
            print(f"Ignoring temporary download file: {file_path}")
            return

        self._process_new_file(file_path)

    def on_moved(self, event):
        # Handle renames/moves (browsers often download to a temp file then move/rename)
        try:
            if event.is_directory:
                return
            dest = getattr(event, 'dest_path', None)
            if not dest:
                return
            print(f"File detected (moved): {dest} (from {getattr(event, 'src_path', '')})")

            # Ignore temp files as destination
            temp_exts = ('.crdownload', '.part', '.tmp', '.download')
            if dest.lower().endswith(temp_exts):
                print(f"Ignoring temporary download file (moved): {dest}")
                return

            self._process_new_file(dest)
        except Exception as e:
            print(f"Error handling moved event: {e}")

    def _process_new_file(self, file_path):
        # Check if file is in Auto-Print folder
        try:
            if self.auto_print_path and os.path.normcase(os.path.abspath(os.path.dirname(file_path))) == os.path.normcase(os.path.abspath(self.auto_print_path)):
                self.handle_auto_print(file_path)
                return
        except Exception:
            pass

        # Normalize file path for reliable comparisons
        normalized_file = os.path.normcase(os.path.abspath(file_path))

        # Check if file is in other monitored paths for TTL cleanup
        for path in self.monitored_paths:
            try:
                normalized_mon = os.path.normcase(os.path.abspath(path))
            except Exception:
                normalized_mon = path

            if normalized_file == normalized_mon or normalized_file.startswith(normalized_mon + os.sep):
                print(f"Scheduling from process_new_file: {file_path}")
                self.schedule_cleanup(file_path)
                break

    def handle_auto_print(self, file_path):
        print(f"Auto-printing: {file_path}")
        try:
            # Windows print command
            os.startfile(file_path, "print")
            # Wait a bit for spooling before delete (naive approach)
            threading.Timer(60, self.secure_delete, args=[file_path]).start()
        except Exception as e:
            print(f"Error printing {file_path}: {e}")

    def schedule_cleanup(self, file_path):
        print(f"Scheduling cleanup for {file_path} in {self.ttl_minutes} minutes")
        threading.Timer(self.ttl_minutes * 60, self.secure_delete, args=[file_path]).start()

    def secure_delete(self, file_path):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Deleted: {file_path}")
        except Exception as e:
            print(f"Error deleting {file_path}: {e}")

class CleanupService:
    def __init__(self):
        self.config = self.load_config()
        self.observer = Observer()
        # Keep a reference to the handler so we can update TTL at runtime
        self.handler = None

    def update_ttl(self, minutes: int):
        """Update the TTL used for scheduled cleanup at runtime."""
        try:
            if self.handler:
                print(f"Updating Cleanup TTL to {minutes} minutes")
                self.handler.ttl_minutes = minutes
            else:
                print("Cleanup handler not yet initialized; TTL will be picked up when service starts")
        except Exception as e:
            print(f"Error updating TTL: {e}")

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            print(f"Error parsing config.json: {e}")
            # Return empty config so service still starts with defaults
            return {}

    def _ensure_dir(self, path, fallback_name):
        """Ensure a directory exists. If the drive isn't available or creation fails,
        fall back to %LOCALAPPDATA%\GenesisSecure\<fallback_name> and return that path."""
        try:
            if not path:
                return None

            expanded = os.path.expanduser(path)
            normalized = os.path.normpath(expanded)

            # If a drive letter is present, ensure the drive root exists
            drive, _ = os.path.splitdrive(normalized)
            if drive:
                drive_root = drive + os.sep
                if not os.path.exists(drive_root):
                    print(f"Drive {drive_root} not available for path {path}; falling back to local folder.")
                    fallback = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'GenesisSecure', fallback_name)
                    os.makedirs(fallback, exist_ok=True)
                    return fallback

            # Try to create the requested directory
            os.makedirs(normalized, exist_ok=True)
            return normalized
        except Exception as e:
            print(f"Failed to create directory {path}: {e}")
            try:
                fallback = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'GenesisSecure', fallback_name)
                os.makedirs(fallback, exist_ok=True)
                return fallback
            except Exception as e2:
                print(f"Failed to create fallback directory: {e2}")
                return None

    def start(self, ramdisk_mount_path=None):
        print("Cleanup Service Started")
        # Store handler reference for runtime updates
        self.handler = CleanupHandler(self.config)
        handler = self.handler
        
        # Schedule Auto-Print Watcher
        auto_print_path = os.path.expanduser(self.config.get('auto_print_path', ''))
        if auto_print_path:
            safe_auto = self._ensure_dir(auto_print_path, 'AutoPrint')
            if safe_auto:
                self.observer.schedule(handler, path=safe_auto, recursive=False)
                print(f"Watching Auto-Print: {safe_auto}")
            else:
                print(f"Skipping Auto-Print watcher; could not create path for {auto_print_path}")

        # Schedule Monitored Paths
        monitored_paths = self.config.get('monitored_paths', [])
        for path in monitored_paths:
            full_path = os.path.expanduser(path)
            safe_path = self._ensure_dir(full_path, os.path.basename(full_path) or 'monitored')
            if safe_path:
                self.observer.schedule(handler, path=safe_path, recursive=False)
                print(f"Watching: {safe_path}")
            else:
                print(f"Skipping monitored path {full_path} - could not ensure directory")

        # ALSO watch RamDisk folders (if configured and available)
        # Use provided mount path or fallback to config
        drive_root = None
        if ramdisk_mount_path:
             drive_root = ramdisk_mount_path
        else:
            ram_letter = self.config.get('ramdisk_letter', '')
            if ram_letter:
                drive_root = f"{ram_letter}:/"

        if drive_root and os.path.exists(drive_root):
            for sub in ('Downloads', 'AutoPrint', 'Quarantine'):
                path = os.path.join(drive_root, sub)
                safe_path = self._ensure_dir(path, f"RamDisk_{sub}")
                if not safe_path:
                    print(f"Failed to ensure ramdisk folder {path}; skipping")
                    continue
                # Schedule watcher and add to monitored list so handler sees it
                try:
                    self.observer.schedule(handler, path=safe_path, recursive=False)
                    handler.monitored_paths.append(safe_path)
                    print(f"Watching RamDisk: {safe_path}")
                except Exception as e:
                    print(f"Error watching {safe_path}: {e}")
        else:
             if drive_root:
                 print(f"RamDisk root {drive_root} not available; skipping ramdisk watchers")

        self.observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            print(f"CleanupService error: {e}")
            self.stop()


    def stop(self):
        self.observer.stop()
        self.observer.join()
        print("Cleanup Service Stopped")

if __name__ == "__main__":
    service = CleanupService()
    service.start()
