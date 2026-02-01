# Print Job Workflow - Updated Implementation

## New Behavior

### File Lifecycle with Print Detection

```
PHASE 1: File Creation (Downloads/Quarantine)
├─ T+0s    File placed in Z:/Downloads or Z:/Quarantine
├─ T+0.1s  CleanupHandler detects file
├─ T+0.2s  TTL cleanup timer SCHEDULED (e.g., 15 minutes)
└─ State:  File in Z:/Downloads, waiting for print or TTL expiry

PHASE 2: Print Initiated (User clicks "Print to PDF")
├─ T+5m    User selects Print to PDF option
├─ T+5m+1s Print job CREATED in Windows spooler
├─ T+5m+2s PrintJobMonitor detects "creation" event
├─ T+5m+3s PrintJobMonitor finds file in Z:/Downloads
├─ T+5m+4s TTL timer CANCELLED for that file
├─ T+5m+5s File MOVED from Z:/Downloads → Z:/AutoPrint
├─ T+5m+6s Print job tracking begins
└─ State:  File in Z:/AutoPrint, "Print to PDF" dialog open

PHASE 3A: Print Dialog Cancelled/Closed (Without Saving)
├─ T+6m    User closes "Save As" dialog without saving
├─ T+6m+1s Print job DELETED from spooler
├─ T+6m+2s PrintJobMonitor detects deletion
├─ T+6m+3s PrintJobMonitor schedules 7-second deletion timer
├─ T+6m+10s File DELETED from Z:/AutoPrint
└─ State:  File removed

NOTE: If user closes dialog WITHOUT SAVING, file is deleted after 7 seconds.
      The assumption is: if not saved successfully, clean up immediately.

PHASE 3B: Print Dialog Completed (User Saves PDF Successfully)
├─ T+6m    User enters filename and clicks "Save"
├─ T+6m+1s "Save As" dialog closes
├─ T+6m+2s File unlocks (no longer held by save dialog)
├─ T+6m+3s Print spooler marks job DELETED (completed)
├─ T+6m+4s PrintJobMonitor detects deletion
├─ T+6m+5s NEW 7-second timer STARTS
├─ T+6m+12s File DELETED from Z:/AutoPrint
└─ State:  File removed from secure environment
```

## Key Differences from Previous Implementation

### Before:
- Files in Downloads/Quarantine got default TTL (15 min)
- When printed, they stayed in original location
- Deletion was unpredictable if dialog stayed open

### After:
- Files in Downloads/Quarantine get default TTL (15 min)
- When Print to PDF is clicked, TTL is CANCELLED
- File is MOVED to Z:/AutoPrint
- NEW 7-second timer starts (NOT 60 seconds)
- Handles file locks during "Save As" dialog
- If print cancelled, file still deleted after 7 seconds

## Implementation Details

### 1. CleanupHandler Tracks Timers

```python
class CleanupHandler:
    def __init__(self, config):
        self.pending_timers = {}  # {file_path: Timer object}
    
    def schedule_cleanup(self, file_path):
        # Cancel existing timer if any
        if file_path in self.pending_timers:
            self.pending_timers[file_path].cancel()
        # Schedule new timer and STORE it
        timer = threading.Timer(...)
        self.pending_timers[file_path] = timer
    
    def cancel_cleanup(self, file_path):
        # Called by PrintJobMonitor when print starts
        if file_path in self.pending_timers:
            self.pending_timers[file_path].cancel()
            del self.pending_timers[file_path]
```

### 2. PrintJobMonitor Detects Print Creation

```python
class PrintJobMonitor:
    def monitor_print_jobs(self):
        # Watch for "creation" events (when user clicks Print to PDF)
        watcher_creation = c.Win32_PrintJob.watch_for(notification_type="creation")
        
        # Watch for "deletion" events (when print completes)
        watcher_deletion = c.Win32_PrintJob.watch_for(notification_type="deletion")
    
    def handle_print_job_created(self, job_id, doc_name):
        # 1. Find file by document name in Z:/Downloads or Z:/Quarantine
        file_path = self.find_file_by_name(doc_name)
        
        # 2. Cancel TTL timer
        self.cleanup_handler.cancel_cleanup(file_path)
        
        # 3. Move to Z:/AutoPrint
        shutil.move(file_path, dest_path)
        
        # 4. Track for UI highlighting
        self.active_jobs[dest_path] = job_id
```

### 3. File Lock Handling

```python
def delete_printed_file(self, file_path, job_id):
    # Wait up to 30 seconds for file unlock (Save As dialog)
    wait_for_file_unlock(file_path, timeout_secs=30)
    
    # Extended retry logic (10 attempts)
    for attempt in range(10):
        try:
            os.remove(file_path)
            return  # Success
        except PermissionError:
            time.sleep(1)  # Retry after 1 second
```

## Testing

### Test Case 1: Print to PDF and Save

```
1. Place file.pdf in Z:/Downloads
2. Start tray app
3. Right-click file → Print to PDF
4. Save As dialog opens
5. EXPECTED: File moved to Z:/AutoPrint immediately
6. EXPECTED: "🖨️ PRINT" indicator shown in dashboard
7. Enter filename and click Save
8. File saves, dialog closes
9. EXPECTED: 7-second timer starts
10. EXPECTED: After 7 seconds, file deleted from Z:/AutoPrint
```

### Test Case 2: Print to PDF and Cancel

```
1. Place file.pdf in Z:/Downloads
2. Start tray app
3. Right-click file → Print to PDF
4. Save As dialog opens
5. EXPECTED: File moved to Z:/AutoPrint
6. EXPECTED: "🖨️ PRINT" indicator shown
7. Click Cancel (don't save)
8. EXPECTED: File stays in Z:/AutoPrint
9. EXPECTED: 7-second timer starts immediately
10. EXPECTED: After 7 seconds, file deleted (print was cancelled)
```

### Test Case 3: Original TTL (No Print)

```
1. Place file.pdf in Z:/Downloads
2. Set TTL to 1 minute in config
3. Start tray app
4. Do NOT print
5. EXPECTED: After 1 minute, file deleted from Z:/Downloads
6. EXPECTED: File never moves to Z:/AutoPrint
```

## Debugging

### Enable Logging

Add to `print_monitor.py`:
```python
import logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s [%(name)s] %(message)s')
```

### Monitor Console Output

Look for these messages:

**Print Detected:**
```
[PrintJobMonitor] Print job CREATED (job 42): document.pdf
[PrintJobMonitor] Found file for job 42: z:\downloads\document.pdf
[PrintJobMonitor] Cancelled TTL timer for z:\downloads\document.pdf
[PrintJobMonitor] Moved z:\downloads\document.pdf -> z:\autoprint\document.pdf
```

**Print Completed:**
```
[PrintJobMonitor] Print Job 42 DELETED (completed/cancelled): document.pdf
[PrintJobMonitor] Scheduling deletion of z:\autoprint\document.pdf in 7 seconds
```

**File Lock Detection:**
```
[PrintJobMonitor] Checking for file lock (job 42): z:\autoprint\document.pdf
[PrintJobMonitor] File unlocked after 5s: z:\autoprint\document.pdf
[PrintJobMonitor] PermissionError deleting, retrying (3/10)
[PrintJobMonitor] Deleted (job 42): z:\autoprint\document.pdf
```

### Check Timer States

Add logging in CleanupHandler:
```python
def cancel_cleanup(self, file_path):
    if file_path in self.pending_timers:
        print(f"BEFORE: {len(self.pending_timers)} timers pending")
        self.pending_timers[file_path].cancel()
        del self.pending_timers[file_path]
        print(f"AFTER: {len(self.pending_timers)} timers pending")
```
