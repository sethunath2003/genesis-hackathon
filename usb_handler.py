import time
import os
import json
import threading
import shutil
import wmi
import pythoncom
import tkinter as tk
from tkinter import filedialog, messagebox
from queue import Queue, Empty

class USBHandler:
    def __init__(self):
        self.config = self.load_config()
        self.running = True
        self.quarantine_path = os.path.expanduser(self.config.get('quarantine_path', 'Z:/Quarantine'))
        self.on_usb_detected_callback = None  # Callback to tray app
        
        # Thread-safety for USB detection
        self._detected_drives = set()  # Track already-detected drives
        self._detection_lock = threading.Lock()
        self._dialog_lock = threading.Lock()  # Prevent concurrent dialogs
        self._gui_queue = Queue()  # Queue for GUI operations
        self._tk_root = None  # Persistent Tk root
        
        if not os.path.exists(self.quarantine_path):
            os.makedirs(self.quarantine_path)

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def set_usb_callback(self, callback):
        """Set callback function to be called when USB is detected."""
        self.on_usb_detected_callback = callback

    def _get_tk_root(self):
        """Get or create a Tk root window for dialogs."""
        if self._tk_root is None or not self._tk_root.winfo_exists():
            self._tk_root = tk.Tk()
            self._tk_root.withdraw()
        return self._tk_root

    def monitor_usb(self):
        print("Monitoring for USB devices...")
        pythoncom.CoInitialize()
        c = wmi.WMI()
        watcher = c.Win32_LogicalDisk.watch_for("creation")
        
        while self.running:
            try:
                disk = watcher(timeout_ms=2000) 
                # DriveType 2 = Removable
                if disk.DriveType == 2:
                    drive_id = disk.DeviceID
                    
                    # Debounce: Skip if already being handled
                    with self._detection_lock:
                        if drive_id in self._detected_drives:
                            print(f"USB {drive_id} already being handled, skipping...")
                            continue
                        self._detected_drives.add(drive_id)
                    
                    print(f"USB Device Detected: {drive_id}")
                    self.handle_usb_arrival(drive_id)
            except wmi.x_wmi_timed_out:
                pass
            except Exception as e:
                print(f"WMI Error: {e}")

    def handle_usb_arrival(self, drive_letter):
        """Show warning and auto-launch Secure Import."""
        print(f"USB detected at {drive_letter} - Launching Secure Import...")
        
        # Launch in a new thread to not block WMI monitoring
        threading.Thread(target=self._show_usb_dialog, args=(drive_letter,), daemon=True).start()

    def _show_usb_dialog(self, drive_letter):
        """Show warning popup and open Secure Import dialog."""
        # Use lock to prevent concurrent dialog displays
        with self._dialog_lock:
            try:
                # Create a fresh Tk root for this dialog session
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)  # Bring to front
                
                # Show warning message
                messagebox.showwarning(
                    "USB Detected - Genesis Security",
                    f"USB drive detected at {drive_letter}\n\n"
                    "⚠️ Direct file access is BLOCKED for security.\n\n"
                    "Please use 'Secure Import' to:\n"
                    "1. Select files from the USB\n"
                    "2. Files will be copied to the secure zone\n"
                    "3. Print from the secure zone\n\n"
                    "Click OK to open Secure Import...",
                    parent=root
                )
                
                # Auto-open file picker pointing to USB (multiple selection enabled)
                file_paths = filedialog.askopenfilenames(
                    title="Secure Import - Select Files from USB (Ctrl+Click for multiple)",
                    initialdir=drive_letter,
                    filetypes=[
                        ("Allowed Files", "*.pdf *.docx *.doc *.jpg *.png *.xlsx *.xls *.ppt *.pptx"),
                        ("All Files", "*.*")
                    ],
                    parent=root
                )
                
                if file_paths:
                    # Import all selected files
                    successful = []
                    failed = []
                    
                    for file_path in file_paths:
                        filename = os.path.basename(file_path)
                        source_dir = os.path.dirname(file_path)
                        if self.secure_import(source_dir, filename):
                            successful.append(filename)
                        else:
                            failed.append(filename)
                    
                    # Show summary result
                    if successful and not failed:
                        # All succeeded
                        files_list = "\n".join(f"  • {f}" for f in successful)
                        messagebox.showinfo(
                            "Import Successful",
                            f"✅ {len(successful)} file(s) imported to:\n{self.quarantine_path}\n\n"
                            f"{files_list}\n\n"
                            "You can now print these files from the secure zone.",
                            parent=root
                        )
                    elif failed and not successful:
                        # All failed
                        files_list = "\n".join(f"  • {f}" for f in failed)
                        messagebox.showerror(
                            "Import Failed",
                            f"❌ Could not import {len(failed)} file(s):\n\n"
                            f"{files_list}\n\n"
                            "File types may not be allowed.",
                            parent=root
                        )
                    else:
                        # Mixed results
                        success_list = "\n".join(f"  • {f}" for f in successful)
                        fail_list = "\n".join(f"  • {f}" for f in failed)
                        messagebox.showwarning(
                            "Import Partially Successful",
                            f"✅ Imported ({len(successful)}):\n{success_list}\n\n"
                            f"❌ Failed ({len(failed)}):\n{fail_list}\n\n"
                            "Failed files may have disallowed extensions.",
                            parent=root
                        )
                
                root.destroy()
                
            except Exception as e:
                print(f"Dialog error: {e}")
            finally:
                # Clear the drive from detected set so it can be detected again after removal/reinsertion
                with self._detection_lock:
                    self._detected_drives.discard(drive_letter)

    def get_removable_drives(self):
        pythoncom.CoInitialize()
        c = wmi.WMI()
        drives = []
        for disk in c.Win32_LogicalDisk(DriveType=2):
            drives.append(disk.DeviceID)
        return drives

    def secure_import(self, source_dir, filename):
        """Safely copies a file from USB to Quarantine."""
        source = os.path.join(source_dir, filename)
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
        self.thread = threading.Thread(target=self.monitor_usb, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.thread.join(timeout=1)

if __name__ == "__main__":
    handler = USBHandler()
    handler.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handler.stop()

