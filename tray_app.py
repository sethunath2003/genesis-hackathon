import logging
import threading
import json
import os
import sys
import time
import winreg
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

# Simple file logging for diagnostic info
logging.basicConfig(
    filename='genesis.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s [%(threadName)s] %(message)s'
)
logger = logging.getLogger(__name__)

from cleanup_service import CleanupService
from usb_handler import USBHandler
from ramdisk_service import RamDiskService
from browser_config import BrowserConfig
#from interface import GenesisDashboard
from genesis_monitor import GenesisLiveMonitor as GenesisDashboard

class GenesisTrayApp:
    def __init__(self):
        self.config = self.load_config()
        self.ramdisk_service = RamDiskService()
        self.browser_config = BrowserConfig()
        self.cleanup_service = CleanupService()
        self.usb_handler = USBHandler()
        self.icon = None
        self.app_name = "GenesisTrayApp"
        # GUI will be initialized in background
        self.gui = None
        self._gui_thread = None
        self.gui_init_error = None

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            print(f"Error parsing config.json: {e}")
            logger.exception("Config parse error")
            # Keep running with defaults
            return {}

    def create_image(self):
        # Generate an icon
        width = 64
        height = 64
        color1 = "black"
        color2 = "green"
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle((width // 4, height // 4, width * 3 // 4, height * 3 // 4), fill=color2)
        return image

    def is_startup_enabled(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, self.app_name)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            print(f"Error checking startup: {e}")
            return False

    def toggle_startup(self, icon, item):
        current_state = self.is_startup_enabled()
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if current_state:
                # Remove
                try:
                    winreg.DeleteValue(key, self.app_name)
                    self.show_notification("Startup Disabled", "Genesis will no longer start automatically.")
                except FileNotFoundError:
                    pass
            else:
                # Add
                exe = sys.executable
                script = os.path.abspath(__file__)
                cmd = f'"{exe}" "{script}"'
                winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, cmd)
                self.show_notification("Startup Enabled", "Genesis will now run correctly on boot.")
            
            winreg.CloseKey(key)
        except Exception as e:
            self.show_notification("Error", f"Failed to modify registry: {e}")

    def on_secure_import(self):
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(title="Select File to Securely Import")
        root.destroy()

        if file_path:
            drive = os.path.splitdrive(file_path)[0]
            filename = os.path.basename(file_path)
            
            success = self.usb_handler.secure_import(os.path.dirname(file_path), filename)
            
            if success:
                 self.show_notification("Import Successful", f"{filename} copied to Quarantine.")
            else:
                 self.show_notification("Import Failed", "File extension not allowed or error occurred.")

    def on_clean_now(self):
        print("Manual Cleanup Triggered")
        if self.ramdisk_service.wipe_contents():
            self.show_notification("Cleanup Complete", "All files in RAM disk have been wiped.")
        else:
            self.show_notification("Cleanup Failed", "Could not wipe RAM disk contents.")

    def on_exit(self, icon, item):
        self.cleanup_service.stop()
        self.usb_handler.stop()
        self.ramdisk_service.stop()
        icon.stop()

    def show_notification(self, title, message):
        if self.icon:
            self.icon.notify(message, title)

    def _on_settings_saved(self, minutes: int):
        """Callback from the interface when the user saves a new TTL."""
        try:
            print(f"Received settings save: update TTL to {minutes} minutes")
            # Update running cleanup service immediately
            self.cleanup_service.update_ttl(minutes)
        except Exception as e:
            print(f"Failed to apply settings to backend: {e}")

    def _initialize_gui(self):
        try:
            # Create GUI with callback and pass print monitor reference
            logger.debug("Initializing Settings GUI...")
            self.gui = GenesisDashboard(
                on_save_callback=self._on_settings_saved,
                print_monitor=self.cleanup_service.print_monitor
            )
            self.gui.withdraw()
            logger.info("Settings GUI initialized")
            self.gui.mainloop()
        except Exception as e:
            # Record the error so callers know why GUI isn't ready
            self.gui_init_error = str(e)
            logger.exception("Failed to initialize GUI")
            # Notify the user if the tray icon is already present
            try:
                if self.icon:
                    self.show_notification("Settings Error", "Failed to initialize settings window. Check logs.")
            except Exception:
                pass

    def _open_settings(self, icon=None, item=None):
        # Start GUI thread if it wasn't started yet
        if not self.gui:
            if not self._gui_thread or not self._gui_thread.is_alive():
                print("Starting Settings GUI thread...")
                self._gui_thread = threading.Thread(target=self._initialize_gui, daemon=True)
                self._gui_thread.start()

            # Wait briefly for GUI initialization
            wait_seconds = 5
            interval = 0.2
            waited = 0.0
            while self.gui is None and waited < wait_seconds:
                time.sleep(interval)
                waited += interval

            if not self.gui:
                logger.warning("Settings GUI still not ready after waiting")
                if self.gui_init_error:
                    logger.error(f"GUI init error: {self.gui_init_error}")
                    self.show_notification("Settings Error", f"Settings initialization failed: {self.gui_init_error}")
                else:
                    self.show_notification("Settings", "Initializing settings window, please try again shortly.")
                return

        # Deiconify the already-initialized GUI
        try:
            self.gui.after(0, self.gui.deiconify)
            self.gui.after(0, self.gui.focus_force)
        except Exception as e:
            logger.exception("Error opening settings window:")
            self.show_notification("Settings Error", "Failed to open settings window. See logs.")

    def run(self):
        print("Genesis Tray App Starting...")
        
        # Step 1: Start RAM Disk FIRST
        print("Initializing RAM Disk...")
        if not self.ramdisk_service.start():
            print("WARNING: RAM Disk failed to start. Files may be saved to fallback location.")
        
        # Step 2: Configure Browsers (once)
        print("Configuring browser download paths...")
        self.browser_config.configure_all()
        
        # Step 3: Start other services
        threading.Thread(target=self.cleanup_service.start, daemon=True).start()
        threading.Thread(target=self.usb_handler.start, daemon=True).start()

        # Start GUI in background (pass callback to update TTL at runtime)
        self._gui_thread = threading.Thread(target=self._initialize_gui, daemon=True)
        self._gui_thread.start()

        # Setup Tray
        image = self.create_image()
        menu = pystray.Menu(
            item('Secure Import...', self.on_secure_import),
            item('Wipe Now', self.on_clean_now),
            item('Settings', self._open_settings),
            item('Run on Startup', self.toggle_startup, checked=lambda item: self.is_startup_enabled()),
            item('Exit', self.on_exit)
        )
        
        self.icon = pystray.Icon("Genesis", image, "Genesis Secure Env", menu)
        self.icon.run()

if __name__ == "__main__":
    app = GenesisTrayApp()
    app.run()
