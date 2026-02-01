# Print Job & File Lifecycle Workflow

## Overview
This document describes the enhanced file handling workflow when files are marked for printing, particularly for kiosk/internet cafe environments.

## Workflow Steps

### 1. **File Detection & Movement**
- **Trigger**: User drops a file into any monitored folder (Downloads, Quarantine on Z: drive)
- **Process**:
  - `CleanupHandler` detects the new file via `watchdog`
  - If file is printable (correct extension) → call `handle_auto_print()`
  - File is **moved** from C: (Downloads/Quarantine) to Z: (AutoPrint)
  - `print_monitor.move_file_to_autoprint()` handles the copy + delete

### 2. **Print Job Initiated**
- **Trigger**: File in Z: AutoPrint is sent to printer via `os.startfile(file_path, "print")`
- **Process**:
  - Windows spooler creates a `Win32_PrintJob` entry
  - `PrintJobMonitor` detects the job via WMI and tracks it
  - File remains in Z: AutoPrint until print completes

### 3. **Print Completion Detection**
- **Trigger**: Print spooler marks job as "Deleted" or "Error"
- **Process**:
  - `PrintJobMonitor.handle_print_event()` catches the completion event
  - Status changes to "Deleted" (success) or "Error" (failure)
  - **Timer scheduled**: Delete file after **7 seconds**
  - This delay allows safe finalization of print job

### 4. **Secure Deletion**
- **Trigger**: 7-second timer expires
- **Process**:
  - `PrintJobMonitor.delete_printed_file()` executes
  - Attempts up to 3 retries (1-second delays between retries)
  - File is removed from Z: AutoPrint
  - Log message confirms deletion

## File Paths (config.json)

```json
{
  "monitored_paths": ["Z:/Downloads", "Z:/Quarantine"],
  "auto_print_path": "Z:/AutoPrint",
  "quarantine_path": "Z:/Quarantine"
}
```

- **Z:/Downloads** → Initial drop location (monitored)
- **Z:/Quarantine** → Quarantine imported USB files (monitored)
- **Z:/AutoPrint** → Staging folder for printing (temporary storage)
- Files move from Downloads/Quarantine → AutoPrint → Deleted

## Timeline Example

```
T+0s    User places file in Z:/Downloads
        └─ CleanupHandler detects via watchdog

T+0.1s  File moved to Z:/AutoPrint
        └─ Original file deleted from Z:/Downloads

T+0.2s  User clicks "Print" (or system auto-triggers)
        └─ os.startfile(..., "print") called

T+0.5s  Print job added to spooler
        └─ Win32_PrintJob created
        └─ PrintJobMonitor tracks job ID

T+5s    Printer finishes printing
        └─ Spooler marks job status = "Deleted"
        └─ PrintJobMonitor.handle_print_event() called

T+5.1s  Deletion timer scheduled
        └─ 7-second countdown begins

T+12s   Timer expires
        └─ PrintJobMonitor.delete_printed_file() called
        └─ File securely removed from Z:/AutoPrint
```

## Key Classes

### `PrintJobMonitor` (print_monitor.py)
- Monitors Windows print spooler via WMI
- Tracks print job lifecycle
- Moves files from C:/Z: Downloads/Quarantine to Z: AutoPrint
- Schedules deletion 7 seconds after print completion
- **Methods**:
  - `move_file_to_autoprint(file_path)` – Move file to Z: AutoPrint
  - `monitor_print_jobs()` – WMI event loop (runs in thread)
  - `handle_print_event(event)` – React to print job status changes
  - `delete_printed_file(file_path, job_id)` – Delete with retries

### `CleanupService` (cleanup_service.py)
- Initializes and starts `PrintJobMonitor` in background thread
- Integrates file system monitoring with print job handling
- Manages service start/stop lifecycle

## Error Handling

### File Move Failures
- If file cannot be moved to Z: AutoPrint (e.g., Z: full or disconnected):
  - Print locally on C: drive
  - Schedule deletion after 60 seconds (fallback timeout)
  - Log error message

### Print Job Failures
- If print job errors or gets stuck:
  - `PrintJobMonitor` catches "Error" status
  - File still deleted after 7 seconds
  - Log captures error details

### Permission/Lock Issues
- If file is locked during deletion:
  - Retry up to 3 times with 1-second delays
  - Log final failure if all retries exhausted

## Configuration & Tuning

### Adjust Deletion Delay
Edit `print_monitor.py` line: `threading.Timer(7, self.delete_printed_file, ...)`
- Change `7` to desired seconds (e.g., `5` for faster deletion)

### Adjust Retry Logic
Edit `cleanup_service.py` `secure_delete()` method:
```python
for attempt in range(3):  # Change 3 to desired retry count
```

### Monitor Fallback Timeout
Edit `cleanup_service.py` `handle_auto_print()` method:
```python
threading.Timer(60, self.secure_delete, ...)  # Change 60 to desired seconds
```

## Logging

All operations log to console:
```
[PrintJobMonitor] Moved C:\Downloads\doc.pdf -> Z:\AutoPrint\doc.pdf
[PrintJobMonitor] Print Job 42: doc.pdf - Status: Deleted
[PrintJobMonitor] Deleted (job 42): Z:\AutoPrint\doc.pdf
```

Enable verbose logging by adding `logging` module for production deployments.
