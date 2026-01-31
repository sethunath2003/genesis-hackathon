import time
import os
import json
import threading
import shutil
import subprocess
import wmi
import pythoncom

try:
    import win32print
    PRINT_MONITORING_AVAILABLE = True
except ImportError:
    PRINT_MONITORING_AVAILABLE = False
    print("Warning: win32print not available. Print job monitoring disabled.")

class USBHandler:
    def __init__(self):
        self.config = self.load_config()
        self.running = True
        # Initialize quarantine path with a safe fallback if target drive isn't available
        default = self.config.get('quarantine_path', '~/Desktop/Quarantine')
        self.quarantine_path = self._ensure_quarantine_path(default)

    def _ensure_quarantine_path(self, candidate_path):
        """Ensure the quarantine path exists. If the configured drive (e.g., Z:) is not available,
        fall back to a local appdata folder. Returns a usable absolute path."""
        import logging
        from pathlib import Path

        logger = logging.getLogger(__name__)

        try:
            # Expand user and normalize
            p = os.path.expanduser(candidate_path)
            p = os.path.normpath(p)

            # If a drive letter is present, verify the drive root exists before attempting creation
            drive, _ = os.path.splitdrive(p)
            if drive:
                drive_root = drive + os.sep
                if not os.path.exists(drive_root):
                    logger.warning("Configured quarantine drive %s not available; falling back to local folder.", drive_root)
                    fallback = os.path.join(os.environ.get('LOCALAPPDATA', str(Path.home())), 'GenesisSecure', 'Quarantine')
                    os.makedirs(fallback, exist_ok=True)
                    return fallback

            # Try to create the desired path (handles both drive and local paths)
            try:
                os.makedirs(p, exist_ok=True)
                return p
            except (FileNotFoundError, OSError) as e:
                logger.warning("Could not create configured quarantine path %s (%s); using fallback.", p, e)
                fallback = os.path.join(os.environ.get('LOCALAPPDATA', str(Path.home())), 'GenesisSecure', 'Quarantine')
                os.makedirs(fallback, exist_ok=True)
                return fallback

        except Exception as e:
            logger.exception("Unexpected error ensuring quarantine path. Using fallback.")
            fallback = os.path.join(os.environ.get('LOCALAPPDATA', str(Path.home())), 'GenesisSecure', 'Quarantine')
            try:
                os.makedirs(fallback, exist_ok=True)
            except Exception:
                pass
            return fallback

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
        # Watch for creation of new LogicalDisks (Drive letters appearing)
        watcher = c.Win32_LogicalDisk.watch_for("creation")
        
        while self.running:
            try:
                # Timed wait to check self.running occasionally
                disk = watcher(timeout_ms=2000) 
                # DriveType 2 = Removable
                if disk.DriveType == 2:
                     print(f"USB Device Detected via WMI: {disk.DeviceID}")
                     self.handle_usb_arrival()
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
                            "📂 Opening folder now...\n"
                            "🖨️ Files will auto-delete after print jobs complete.",
                            parent=root
                        )
                        # Open quarantine folder and schedule deletion
                        self._open_folder_and_schedule_deletion(successful)
                        
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
                            "📂 Opening folder now...\n"
                            "🖨️ Imported files will auto-delete after print jobs complete.",
                            parent=root
                        )
                        # Open quarantine folder and schedule deletion for successful files
                        if successful:
                            self._open_folder_and_schedule_deletion(successful)
                
                root.destroy()
                
            except Exception as e:
                print(f"Dialog error: {e}")
            finally:
                # Clear the drive from detected set so it can be detected again after removal/reinsertion
                with self._detection_lock:
                    self._detected_drives.discard(drive_letter)

    def _open_folder_and_schedule_deletion(self, filenames):
        """Open quarantine folder and monitor print queue for file deletion."""
        # Open the quarantine folder in Windows Explorer
        try:
            # Normalize path (convert forward slashes to backslashes for Windows)
            folder_path = os.path.normpath(self.quarantine_path)
            os.startfile(folder_path)
            print(f"Opened quarantine folder: {folder_path}")
        except Exception as e:
            print(f"Failed to open folder: {e}")
        
        # Start print monitoring in background thread
        threading.Thread(
            target=self._monitor_print_and_delete,
            args=(filenames,),
            daemon=True
        ).start()

    def _monitor_print_and_delete(self, filenames):
        """Monitor print queue and delete files after jobs complete."""
        files_to_delete = {f: False for f in filenames}  # filename: printed_flag
        full_paths = {f: os.path.join(self.quarantine_path, f) for f in filenames}
        
        max_wait_time = 300  # 5 minutes max wait
        check_interval = 2  # Check every 2 seconds
        start_time = time.time()
        
        print(f"Monitoring print queue for {len(filenames)} file(s)...")
        
        if not PRINT_MONITORING_AVAILABLE:
            # Fallback to simple delay if win32print not available
            print("Print monitoring unavailable, using 30-second fallback...")
            time.sleep(30)
            self._delete_files(filenames)
            return
        
        # Initial delay to let user start printing
        time.sleep(5)
        
        while time.time() - start_time < max_wait_time:
            try:
                # Get all print jobs from all printers
                active_jobs = self._get_active_print_jobs()
                
                # Check if any of our files are still in the print queue
                files_still_printing = False
                for filename in filenames:
                    if not files_to_delete[filename]:  # Not yet marked as printed
                        # Check if file is in any active print job
                        file_in_queue = any(
                            filename.lower() in job_name.lower()
                            for job_name in active_jobs
                        )
                        
                        if file_in_queue:
                            files_still_printing = True
                            print(f"  Still printing: {filename}")
                        else:
                            # File not in queue - either printed or never queued
                            files_to_delete[filename] = True
                            print(f"  Print complete or not queued: {filename}")
                
                # If no files are in the print queue, we can check for deletion
                if not files_still_printing:
                    # Wait a bit more for the print job to fully flush
                    time.sleep(3)
                    
                    # Double-check no new jobs appeared
                    active_jobs = self._get_active_print_jobs()
                    still_has_jobs = any(
                        any(f.lower() in job.lower() for job in active_jobs)
                        for f in filenames
                    )
                    
                    if not still_has_jobs:
                        print("All print jobs completed. Deleting files...")
                        self._delete_files(filenames)
                        return
                
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"Print monitoring error: {e}")
                time.sleep(check_interval)
        
        # Timeout reached - delete anyway
        print(f"Timeout reached ({max_wait_time}s). Force deleting files...")
        self._delete_files(filenames)

    def _get_active_print_jobs(self):
        """Get list of document names in all print queues."""
        job_names = []
        try:
            # Enumerate all printers
            printers = win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
            
            for printer in printers:
                printer_name = printer[2]
                try:
                    # Open printer and get jobs
                    handle = win32print.OpenPrinter(printer_name)
                    try:
                        jobs = win32print.EnumJobs(handle, 0, 100, 1)  # Get up to 100 jobs
                        for job in jobs:
                            doc_name = job.get('pDocument', '')
                            if doc_name:
                                job_names.append(doc_name)
                    finally:
                        win32print.ClosePrinter(handle)
                except Exception:
                    pass  # Skip printers we can't access
                    
        except Exception as e:
            print(f"Error enumerating print jobs: {e}")
        
        return job_names

    def _delete_files(self, filenames):
        """Delete the specified files from quarantine."""
        for filename in filenames:
            file_path = os.path.join(self.quarantine_path, filename)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Deleted: {filename}")
            except Exception as e:
                print(f"Failed to delete {filename}: {e}")


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
