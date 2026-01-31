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

from cleanup_service import CleanupService
from usb_handler import USBHandler
from ramdisk_service import RamDiskService
from browser_config import BrowserConfig

class GenesisTrayApp:
    def __init__(self):
        self.config = self.load_config()
        
        # Start RAM Disk FIRST (before other services that depend on Z:)
        self.ramdisk_service = RamDiskService()
        print("Initializing Virtual Drive...")
        if not self.ramdisk_service.start():
            print("WARNING: Virtual Drive failed to start. Using fallback paths.")
        
        self.browser_config = BrowserConfig()
        self.cleanup_service = CleanupService()
        self.usb_handler = USBHandler()
        self.icon = None
        self.app_name = "GenesisTrayApp"

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
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
        print("Exiting Genesis...")
        self.cleanup_service.stop()
        self.usb_handler.stop()
        
        # Wipe all files and remove the virtual drive
        print("Wiping and removing Virtual Drive...")
        self.ramdisk_service.wipe_contents()
        self.ramdisk_service.remove_ramdisk()
        
        icon.stop()

    def show_notification(self, title, message):
        if self.icon:
            self.icon.notify(message, title)

    def run(self):
        print("Genesis Tray App Starting...")
        
        # Configure Browsers (once)
        print("Configuring browser download paths...")
        self.browser_config.configure_all()
        
        # Start other services
        threading.Thread(target=self.cleanup_service.start, daemon=True).start()
        threading.Thread(target=self.usb_handler.start, daemon=True).start()

        # Setup Tray
        image = self.create_image()
        menu = pystray.Menu(
            item('Secure Import...', self.on_secure_import),
            item('Wipe Now', self.on_clean_now),
            item('Run on Startup', self.toggle_startup, checked=lambda item: self.is_startup_enabled()),
            item('Exit', self.on_exit)
        )
        
        self.icon = pystray.Icon("Genesis", image, "Genesis Secure Env", menu)
        self.icon.run()

if __name__ == "__main__":
    app = GenesisTrayApp()
    app.run()
