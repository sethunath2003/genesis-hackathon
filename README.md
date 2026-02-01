# Genesis - Secure Software Environment

Genesis is a secure software layer designed for internet cafes and public service centers. It mitigates data privacy risks by automating file cleanup, securely handling external media (USB), and providing safe workflow automation like "Auto-Print".

## Features

- **🛡️ Secure USB Import**: Automatically detects USB insertion (via WMI) and provides a safe "Quarantine" import workflow to prevent autorun malware.
- **🧹 Intelligent Cleanup**: Background service monitors `Downloads` and `Desktop` to enforce deletion policies (TTL) after customer sessions.
- **🖨️ Auto-Print Workflow**: Drag-and-drop folder that automatically prints documents and securely deletes them immediately after.
- **🖥️ Non-Intrusive UI**: Runs as a system tray application, respecting the shopkeeper's existing workflow.
- **⚡ Efficient**: Uses event-driven monitoring (`watchdog`) for near-zero idle CPU usage.

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/genesis.git
   cd genesis
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *Requires Windows OS (due to WMI dependecy).*

## Configuration

Edit `config.json` to customize:
- `monitored_paths`: Directories to clean up.
- `cleanup_interval_minutes`: Time-to-Live for files.
- `auto_print_path`: Location of the drag-and-drop print folder.

## Usage

### Manual Start
Start the application:
```bash
python tray_app.py
```

- **System Tray**: Right-click the Genesis icon to "Secure Import" or "Clean Now".
- **USB**: Insert a drive, and you will be prompted (or use the menu) to import specific files safely.
- **Printing**: Drop files into the `AutoPrint` folder on your desktop.

### Auto-Start on Windows Boot
To make Genesis launch automatically in the background on every Windows startup:

1. **Open Command Prompt as Administrator** (right-click → "Run as administrator")
2. **Navigate to the Genesis folder**:
   ```powershell
   cd C:\project\genesis-hackathon
   ```
3. **Run the setup script**:
   ```bash
   python setup_startup.py
   ```
4. **Restart your computer** — Genesis will launch silently in the background

**To disable auto-start later**:
```bash
python setup_startup.py remove
```

## Technologies

- Python 3.x
- `watchdog` (File monitoring)
- `wmi` (Windows Hardware integration)
- `pystray` (System Tray UI)
- `tkinter` (File Dialogs)
