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
        print(f"File detected: {file_path}")

        # Check if file is in Auto-Print folder
        if self.auto_print_path and os.path.dirname(file_path) == self.auto_print_path:
            self.handle_auto_print(file_path)
            return

        # Check if file is in other monitored paths for TTL cleanup
        for path in self.monitored_paths:
            if file_path.startswith(path):
                self.schedule_cleanup(file_path)

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
                os.makedirs(full_path)
            self.observer.schedule(handler, path=full_path, recursive=False)
            print(f"Watching: {full_path}")

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
