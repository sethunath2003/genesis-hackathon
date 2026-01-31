import time
import os
import json
import threading
import shutil
import wmi
import pythoncom

class USBHandler:
    def __init__(self):
        self.config = self.load_config()
        self.running = True
        self.quarantine_path = os.path.expanduser(self.config.get('quarantine_path', '~/Desktop/Quarantine'))
        if not os.path.exists(self.quarantine_path):
            os.makedirs(self.quarantine_path)

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def monitor_usb(self):
        print("Monitoring for USB devices...")
        pythoncom.CoInitialize() # Required for WMI in thread
        c = wmi.WMI()
        watcher = c.Win32_VolumeChangeEvent.watch_for("ConfigurationChanged")
        
        while self.running:
            try:
                # Timed wait to check self.running occasionally
                event = watcher(timeout_ms=2000) 
                if event.EventType == 2: # Device Arrival
                     print("USB Device Detected via WMI")
                     self.handle_usb_arrival()
            except wmi.x_wmi_timed_out:
                pass
            except Exception as e:
                print(f"WMI Error: {e}")

    def handle_usb_arrival(self):
        # Notify Tray App (In a real app, use callbacks or signals)
        print("Triggering USB Scan options...")
        # For prototype, we just find the drive letter
        drives = self.get_removable_drives()
        for drive in drives:
            print(f"Found removable drive: {drive}")
            # Potentially mount read-only or prompt user

    def get_removable_drives(self):
        c = wmi.WMI()
        drives = []
        for disk in c.Win32_LogicalDisk(DriveType=2): # 2 = Removable
            drives.append(disk.DeviceID)
        return drives

    def secure_import(self, drive_letter, filename):
        """Safely copies a file from USB to Quarantine"""
        source = os.path.join(drive_letter, filename)
        dest = os.path.join(self.quarantine_path, os.path.basename(filename))
        
        # Extension check
        ext = os.path.splitext(filename)[1].lower()
        allowed = self.config.get('file_upload_extensions', [])
        if ext not in allowed:
            print(f"Blocked: Extension {ext} not allowed.")
            return False

        try:
            shutil.copy2(source, dest)
            print(f"Securely imported {filename} to {dest}")
            return True
        except Exception as e:
            print(f"Import failed: {e}")
            return False

    def start(self):
        self.thread = threading.Thread(target=self.monitor_usb)
        self.thread.start()

    def stop(self):
        self.running = False
        # WMI watcher might block, needs forceful termination in prototype
        self.thread.join(timeout=1)

if __name__ == "__main__":
    handler = USBHandler()
    handler.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handler.stop()
