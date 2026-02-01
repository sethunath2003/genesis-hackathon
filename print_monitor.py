"""
Print Job Monitor: Tracks print completion and manages file lifecycle.
- Monitors Windows print spooler for job completion
- Moves files from Z:/Downloads/Quarantine to Z:/AutoPrint when printing starts
- Detects file locks (for PDF 'Save As' dialogs) and waits for unlock
- Deletes files 7 seconds after print job completes (with extended retry for locks)
- Uses multiple deletion methods for permanent removal
"""

import time
import os
import shutil
import threading
import json
from pathlib import Path
import wmi
import pythoncom
import subprocess


def is_file_locked(file_path):
    """Check if a file is locked by another process (e.g., Save As dialog)."""
    if not os.path.exists(file_path):
        return False
    
    try:
        # Try to open file in write mode; if locked, this will fail
        with open(file_path, 'r+b') as f:
            f.seek(0)
        return False
    except IOError:
        # File is locked
        return True
    except Exception:
        return False


def secure_delete_file(file_path):
    """Attempt permanent deletion of file using multiple methods.
    
    Methods tried (in order):
    1. Standard os.remove()
    2. pathlib.Path.unlink()
    3. os.replace() with temp location
    4. Windows del command via subprocess
    
    Returns True if successful, False otherwise.
    """
    file_path = os.path.normcase(os.path.abspath(file_path))
    
    if not os.path.exists(file_path):
        print(f"[PrintJobMonitor] File already gone: {file_path}")
        return True
    
    # Method 1: Standard os.remove()
    try:
        os.remove(file_path)
        print(f"[PrintJobMonitor] ✓ Deleted via os.remove(): {file_path}")
        return True
    except Exception as e:
        print(f"[PrintJobMonitor] os.remove() failed: {e}")
    
    # Method 2: pathlib.Path.unlink()
    try:
        Path(file_path).unlink()
        print(f"[PrintJobMonitor] ✓ Deleted via Path.unlink(): {file_path}")
        return True
    except Exception as e:
        print(f"[PrintJobMonitor] Path.unlink() failed: {e}")
    
    # Method 3: Move to temp and delete (works for locked files)
    try:
        temp_path = file_path + ".tmp_delete"
        os.rename(file_path, temp_path)
        os.remove(temp_path)
        print(f"[PrintJobMonitor] ✓ Deleted via rename+remove: {file_path}")
        return True
    except Exception as e:
        print(f"[PrintJobMonitor] Rename+remove failed: {e}")
    
    # Method 4: Use Windows command line for aggressive deletion
    try:
        # Use /F to force delete, /S for subdirs, /Q for quiet
        subprocess.run(['cmd', '/c', f'del /F /Q "{file_path}"'], 
                      check=True, 
                      capture_output=True,
                      timeout=5)
        print(f"[PrintJobMonitor] ✓ Deleted via Windows del command: {file_path}")
        return True
    except Exception as e:
        print(f"[PrintJobMonitor] Windows del command failed: {e}")
    
    print(f"[PrintJobMonitor] ✗ PERMANENT DELETION FAILED: {file_path}")
    return False


def wait_for_file_unlock(file_path, timeout_secs=30):
    """Wait for file to be unlocked (e.g., user finishes Save As dialog).
    
    Returns True if file becomes unlocked, False if timeout.
    """
    elapsed = 0
    while elapsed < timeout_secs:
        if not is_file_locked(file_path):
            print(f"[PrintJobMonitor] File unlocked after {elapsed}s: {file_path}")
            return True
        time.sleep(0.5)
        elapsed += 0.5
    
    print(f"[PrintJobMonitor] File still locked after {timeout_secs}s (continuing anyway): {file_path}")
    return False


class PrintJobMonitor:
    def __init__(self, config, cleanup_handler=None):
        self.config = config
        self.cleanup_handler = cleanup_handler  # Reference to cancel TTL timers
        self.running = True
        self.print_jobs = {}  # Track {job_id: {'file_path': ..., 'status': ..., 'doc_name': ...}}
        self.active_jobs = {}  # Track {file_path: job_id} for UI highlighting
        
        # Paths from config
        self.auto_print_path = os.path.normcase(
            os.path.abspath(os.path.expanduser(config.get('auto_print_path', '')))
        )
        self.monitored_paths = [os.path.normcase(os.path.abspath(os.path.expanduser(p))) 
                                for p in config.get('monitored_paths', [])]
        
        # Callback for UI highlighting
        self.on_job_status_changed = None
        
        print(f"[PrintJobMonitor] Initialized:")
        print(f"  AutoPrint (Z:): {self.auto_print_path}")
        print(f"  Monitored paths for move: {self.monitored_paths}")

    def find_file_by_name(self, doc_name):
        """Search Z:/Downloads and Z:/Quarantine for a file matching doc_name."""
        for monitored_path in self.monitored_paths:
            if not os.path.exists(monitored_path):
                continue
            
            # Search for exact filename or partial match
            for file in os.listdir(monitored_path):
                file_path = os.path.join(monitored_path, file)
                if os.path.isfile(file_path):
                    # Check if filename matches document name
                    if file.lower() == doc_name.lower() or doc_name.lower() in file.lower():
                        return file_path
        
        return None

    def handle_print_job_created(self, job_id, doc_name):
        """Handle when a print job is created (user clicks Print to PDF).
        
        Moves the file from Z:/Downloads/Quarantine to Z:/AutoPrint and starts 7-second timer.
        """
        print(f"[PrintJobMonitor] Print job CREATED (job {job_id}): {doc_name}")
        
        # Find the file in monitored paths
        file_path = self.find_file_by_name(doc_name)
        
        if not file_path:
            print(f"[PrintJobMonitor] Could not find file for job {job_id}: {doc_name}")
            return
        
        file_path = os.path.normcase(os.path.abspath(file_path))
        print(f"[PrintJobMonitor] Found file for job {job_id}: {file_path}")
        
        # Cancel TTL timer for this file
        if self.cleanup_handler:
            self.cleanup_handler.cancel_cleanup(file_path)
            print(f"[PrintJobMonitor] Cancelled TTL timer for {file_path}")
        
        # Move file to AutoPrint
        try:
            if not os.path.exists(self.auto_print_path):
                os.makedirs(self.auto_print_path)
            
            dest_path = os.path.join(self.auto_print_path, os.path.basename(file_path))
            shutil.copy2(file_path, dest_path)
            os.remove(file_path)
            print(f"[PrintJobMonitor] Moved {file_path} -> {dest_path}")
            
            # Track this print job with file path
            self.print_jobs[job_id] = {
                'file_path': dest_path,
                'doc_name': doc_name,
                'status': 'printing'
            }
            
            # Add to active jobs for UI highlighting
            self.active_jobs[dest_path] = job_id
            print(f"[PrintJobMonitor] Print job {job_id} tracking file: {dest_path}")
            
            # START 7-SECOND TIMER IMMEDIATELY (new timer, not waiting for completion)
            print(f"[PrintJobMonitor] STARTING 7-second deletion timer for {dest_path}")
            threading.Timer(7, self.delete_printed_file, args=[dest_path, job_id]).start()
            
        except Exception as e:
            print(f"[PrintJobMonitor] Error handling print job creation: {e}")
        """Move a file from Z:/Downloads or Z:/Quarantine to Z:/AutoPrint."""
        file_path = os.path.normcase(os.path.abspath(file_path))
        
        # Check if file is in monitored locations (Z:/Downloads, Z:/Quarantine)
        is_in_monitored = False
        for monitored_path in self.monitored_paths:
            try:
                if os.path.commonpath([file_path, monitored_path]) == monitored_path:
                    is_in_monitored = True
                    break
            except ValueError:
                # Different drives, skip
                continue
        
        if not is_in_monitored:
            print(f"[PrintJobMonitor] File not in monitored paths (Z:/Downloads, Z:/Quarantine): {file_path}")
            return False
        
        # Ensure AutoPrint exists
        if not os.path.exists(self.auto_print_path):
            os.makedirs(self.auto_print_path)
        
        dest_path = os.path.join(self.auto_print_path, os.path.basename(file_path))
        
        try:
            # Move (copy then delete) to Z:/AutoPrint
            shutil.copy2(file_path, dest_path)
            os.remove(file_path)
            print(f"[PrintJobMonitor] Moved {file_path} -> {dest_path}")
            return True
        except Exception as e:
            print(f"[PrintJobMonitor] Error moving file: {e}")
            return False

    def monitor_print_jobs(self):
        """Monitor Windows print spooler for job creation, modification, and completion."""
        print("[PrintJobMonitor] Starting print job monitor...")
        pythoncom.CoInitialize()
        
        try:
            c = wmi.WMI()
            # Watch for creation events when user clicks "Print to PDF"
            watcher_creation = c.Win32_PrintJob.watch_for(notification_type="creation")
            
            while self.running:
                try:
                    # Check for new print jobs (creation events)
                    event = watcher_creation(timeout_ms=2000)
                    if event:
                        job_id = event.JobId
                        doc_name = event.Document
                        self.handle_print_job_created(job_id, doc_name)
                except wmi.x_wmi_timed_out:
                    pass
                except Exception as e:
                    print(f"[PrintJobMonitor] WMI Creation watcher error: {e}")
            
            # Also watch for deletion (completion) events
            watcher_deletion = c.Win32_PrintJob.watch_for(notification_type="deletion")
            
            while self.running:
                try:
                    event = watcher_deletion(timeout_ms=2000)
                    if event:
                        self.handle_print_event(event)
                except wmi.x_wmi_timed_out:
                    pass
                except Exception as e:
                    print(f"[PrintJobMonitor] WMI Deletion watcher error: {e}")
                    
        except Exception as e:
            print(f"[PrintJobMonitor] Failed to initialize WMI: {e}")
        finally:
            pythoncom.CoUninitialize()

    def handle_print_event(self, event):
        """Handle a print job deletion event (print completed or cancelled).
        
        Note: 7-second timer already started in handle_print_job_created().
        This just logs completion for debugging.
        """
        try:
            job_id = event.JobId
            doc_name = event.Document
            
            print(f"[PrintJobMonitor] Print Job {job_id} DELETED (completed/cancelled): {doc_name}")
            
            # If this job was tracked, log it
            if job_id in self.print_jobs:
                file_info = self.print_jobs[job_id]
                file_path = file_info['file_path']
                print(f"[PrintJobMonitor] Print job {job_id} finished. 7-second deletion timer already running for {file_path}")
                del self.print_jobs[job_id]
        except Exception as e:
            print(f"[PrintJobMonitor] Error handling print event: {e}")

    def delete_printed_file(self, file_path, job_id):
        """Delete a file 7 seconds after print completion.
        
        For PDF Print to PDF, waits for file unlock (Save As dialog closes)
        before attempting deletion. Uses multiple deletion methods for 
        permanent removal. Retries up to 15 times with increasing delays.
        """
        file_path = os.path.normcase(os.path.abspath(file_path))
        
        print(f"[PrintJobMonitor] Starting deletion sequence (job {job_id}): {file_path}")
        print(f"[PrintJobMonitor] Checking for file lock...")
        
        # Wait for file to be unlocked (e.g., Save As dialog closes)
        # Timeout of 30 seconds to allow user to save PDF
        wait_for_file_unlock(file_path, timeout_secs=30)
        
        # Extended retry logic with multiple deletion methods
        max_attempts = 15
        
        for attempt in range(max_attempts):
            print(f"[PrintJobMonitor] Deletion attempt {attempt + 1}/{max_attempts}...")
            
            # Try secure deletion
            if secure_delete_file(file_path):
                print(f"[PrintJobMonitor] ✓✓✓ FILE PERMANENTLY DELETED (job {job_id}): {file_path}")
                return
            
            # File still exists, wait before retry
            if os.path.exists(file_path):
                wait_time = min(2, attempt + 1)  # Increasing delays: 1s, 2s, 2s, 2s...
                print(f"[PrintJobMonitor] File still present, waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                print(f"[PrintJobMonitor] File disappeared during retry cycle")
                return
        
        # Final check
        if os.path.exists(file_path):
            print(f"[PrintJobMonitor] ✗✗✗ CRITICAL: File still exists after all attempts: {file_path}")
            print(f"[PrintJobMonitor] File may be locked by antivirus, disk checker, or other process")
        else:
            print(f"[PrintJobMonitor] ✓ File eventually deleted (job {job_id})")

    def start(self):
        """Start the print monitor in a background thread."""
        thread = threading.Thread(target=self.monitor_print_jobs, daemon=True)
        thread.start()
        return thread

    def stop(self):
        """Stop the print monitor."""
        self.running = False
        print("[PrintJobMonitor] Stopping...")

    def get_active_jobs(self):
        """Return dict of {file_path: job_id} for currently printing files."""
        return self.active_jobs.copy()


# Standalone test
if __name__ == "__main__":
    config = {
        'auto_print_path': '~/Desktop/AutoPrint',
        'quarantine_path': '~/Desktop/Quarantine',
    }
    
    monitor = PrintJobMonitor(config)
    thread = monitor.start()
    
    try:
        print("Print monitor running (Ctrl+C to stop)...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
        thread.join(timeout=2)
        print("Done.")
