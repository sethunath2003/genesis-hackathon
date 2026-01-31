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

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def start(self):
        print("Cleanup Service Started")
        handler = CleanupHandler(self.config)
        
        # Schedule Auto-Print Watcher
        auto_print_path = os.path.expanduser(self.config.get('auto_print_path', ''))
        if auto_print_path:
             if not os.path.exists(auto_print_path):
                 os.makedirs(auto_print_path)
             self.observer.schedule(handler, path=auto_print_path, recursive=False)
             print(f"Watching Auto-Print: {auto_print_path}")

        # Schedule Monitored Paths
        monitored_paths = self.config.get('monitored_paths', [])
        for path in monitored_paths:
            full_path = os.path.expanduser(path)
            if not os.path.exists(full_path):
                try:
                    os.makedirs(full_path)
                except Exception as e:
                    print(f"Failed to create monitored path {full_path}: {e}")
            self.observer.schedule(handler, path=full_path, recursive=False)
            print(f"Watching: {full_path}")

        # ALSO watch RamDisk folders (if configured and available)
        ram_letter = self.config.get('ramdisk_letter', '')
        if ram_letter:
            drive_root = f"{ram_letter}:/"
            if os.path.exists(drive_root):
                for sub in ('Downloads', 'AutoPrint', 'Quarantine'):
                    path = os.path.join(drive_root, sub)
                    if not os.path.exists(path):
                        try:
                            os.makedirs(path)
                        except Exception as e:
                            print(f"Failed to ensure ramdisk folder {path}: {e}")
                            continue
                    # Schedule watcher and add to monitored list so handler sees it
                    self.observer.schedule(handler, path=path, recursive=False)
                    handler.monitored_paths.append(path)
                    print(f"Watching RamDisk: {path}")
            else:
                print(f"RamDisk {drive_root} not available; skipping ramdisk watchers")

        self.observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.observer.stop()
        self.observer.join()
        print("Cleanup Service Stopped")

if __name__ == "__main__":
    service = CleanupService()
    service.start()
