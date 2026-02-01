# PDF Printing & File Lock Handling

## Overview

Updated the print job monitor to handle **Microsoft Print to PDF** which opens a "Save As" dialog. The system now:

1. **Detects file locks** - Checks if files are locked by the Save As dialog
2. **Waits for unlock** - Allows up to 30 seconds for the user to complete the save
3. **Extended retry logic** - Attempts deletion up to 10 times (vs. 3 previously)
4. **UI highlighting** - Shows active print jobs in the Genesis Monitor dashboard

## Changes Made

### 1. `print_monitor.py` - File Lock Detection

#### New Functions:

**`is_file_locked(file_path)`**
- Checks if a file is locked by another process (e.g., Save As dialog)
- Attempts to open file in r+b mode; fails silently if locked
- Returns `True` if locked, `False` if available

**`wait_for_file_unlock(file_path, timeout_secs=30)`**
- Polls file lock status every 0.5 seconds
- Returns `True` if file unlocks before timeout
- Times out after 30 seconds (default) but continues anyway
- Logs unlock time for debugging

#### Enhanced `delete_printed_file()` Method:

```python
def delete_printed_file(self, file_path, job_id):
    # 1. Wait for file unlock (e.g., Save As dialog closes) - 30 second timeout
    wait_for_file_unlock(file_path, timeout_secs=30)
    
    # 2. Retry deletion up to 10 times (instead of 3)
    # 3. Retry every 1 second on PermissionError
    # 4. Log all attempts for diagnosis
```

**Why this works for PDF:**
- User drops file in Z:/AutoPrint
- File sent to printer via `os.startfile(..., "print")`
- "Microsoft Print to PDF" opens "Save As" dialog
- File is **locked** while dialog is open
- Monitor detects lock and waits
- User saves PDF → file unlocks
- Deletion proceeds with extended retries

### 2. `genesis_monitor.py` - Print Job Highlighting

#### New Features:

**Active Job Tracking:**
- References `PrintJobMonitor` instance
- Polls `get_active_jobs()` to get {file_path: job_id} dict
- Updates every 1 second in UI refresh loop

**Visual Highlighting:**
- Shows `🖨️ PRINT` emoji when print job is active
- Highlights row with dark background (#2c3e50)
- Removes highlight and emoji when print completes
- Helps shopkeeper see which files are currently printing

#### UI Update Flow:
```
1. Refresh loop checks active jobs from monitor
2. For each file, checks if it has an active job
3. If job started (wasn't there before):
   - Shows "🖨️ PRINT" status indicator
   - Highlights row background
   - Logs highlighting event
4. If job completed (was there, now gone):
   - Clears status indicator
   - Removes row highlight
   - Logs completion
```

### 3. `tray_app.py` - Integration

**Passes PrintJobMonitor to UI:**
```python
self.gui = GenesisDashboard(
    on_save_callback=self._on_settings_saved,
    print_monitor=self.cleanup_service.print_monitor
)
```

Now the monitor dashboard can track active print jobs.

## Timing Example: PDF Print to PDF

```
T+0s      User drops file.pdf in Z:/AutoPrint
          └─ CleanupHandler detects via watchdog

T+0.1s    File detected as auto-print candidate
          └─ Triggers print via os.startfile(..., "print")

T+0.5s    "Microsoft Print to PDF" opens "Save As" dialog
          └─ File becomes LOCKED
          └─ PrintJobMonitor tracks job ID
          └─ GenesisMonitor shows "🖨️ PRINT" and highlights row

T+15s     User finishes entering filename and clicks "Save"
          └─ PDF is written to disk
          └─ File unlocks
          └─ Monitor detects unlock

T+20s     Print spooler marks job as "Deleted" (complete)
          └─ PrintJobMonitor.handle_print_event() called
          └─ Deletion timer scheduled for 7 seconds

T+20.1s   GenesisMonitor removes "🖨️ PRINT" highlight
          └─ Row background returns to normal

T+27s     7-second timer expires
          └─ delete_printed_file() executes
          └─ File already unlocked, deletion succeeds on first try
          └─ File.pdf is removed from Z:/AutoPrint
```

## Error Scenarios Handled

### Scenario 1: Save As Dialog Stays Open > 30s
```
- Monitor waits 30 seconds for unlock
- Timeout triggers but deletion proceeds anyway
- If file still locked, retry logic kicks in (10 attempts)
- File eventually deleted when dialog closes
- Log captures: "File still locked after 30s (continuing anyway)"
```

### Scenario 2: PDF File In Use By Reader
```
- User opens PDF after printing (viewer locks file)
- Deletion retry logic kicks in (10 attempts)
- Monitor retries every 1 second for up to 10 seconds total
- File deleted when viewer closes
```

### Scenario 3: Permission Denied
```
- Windows antivirus scanning file (rare)
- Retry logic handles this gracefully
- 10 retries × 1 second = up to 10 seconds wait
- Log captures all attempts: "PermissionError deleting, retrying (x/10)"
```

## Configuration

### Adjust Lock Wait Timeout
Edit `print_monitor.py`:
```python
wait_for_file_unlock(file_path, timeout_secs=30)  # Change 30 to desired seconds
```

### Adjust Retry Limit
Edit `print_monitor.py`:
```python
max_attempts = 10  # Change 10 to desired retry count
```

### Adjust Retry Delay
Edit `print_monitor.py`:
```python
retry_delay = 1  # Change 1 to desired seconds between retries
```

## Logging

All events logged to console with timestamps:

```
[PrintJobMonitor] Checking for file lock (job 42): Z:\AutoPrint\document.pdf
[PrintJobMonitor] File unlocked after 15s: Z:\AutoPrint\document.pdf
[PrintJobMonitor] PermissionError deleting, retrying (1/10)
[PrintJobMonitor] Deleted (job 42): Z:\AutoPrint\document.pdf

[GenesisMonitor] Highlighting document.pdf - print job active
[GenesisMonitor] Removed highlight from document.pdf - print completed
```

For production, enable file logging in `tray_app.py` (already configured):
```python
logging.basicConfig(filename='genesis.log', level=logging.DEBUG)
```

## Testing Print to PDF

1. Install "Microsoft Print to PDF" (built-in on Windows 10+)
2. Place a PDF or any printable file in Z:/AutoPrint
3. Trigger print: `python tray_app.py`
4. Monitor dashboard shows "🖨️ PRINT" with highlighted row
5. "Save As" dialog opens
6. Save the PDF to a location
7. Monitor removes highlight after print completes
8. File auto-deletes 7 seconds after save
