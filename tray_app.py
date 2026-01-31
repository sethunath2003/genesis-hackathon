import threading
import json
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

from cleanup_service import CleanupService
from usb_handler import USBHandler

class GenesisTrayApp:
    def __init__(self):
        self.config = self.load_config()
        self.cleanup_service = CleanupService()
        self.usb_handler = USBHandler()
        self.icon = None

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

    def on_secure_import(self):
        # Hidden Tkinter root
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(title="Select File to Securely Import")
        root.destroy()

        if file_path:
            # Simulate USB import or just copy
            # We use USBHandler's logic if possible, or just a direct safe copy
            # Here we assume local or mounted USB
            drive = os.path.splitdrive(file_path)[0]
            filename = os.path.basename(file_path)
            
            # Since we have the full path, we can just call secure_import with dirname
            success = self.usb_handler.secure_import(os.path.dirname(file_path), filename)
            
            if success:
                 self.show_notification("Import Successful", f"{filename} copied to Quarantine.")
            else:
                 self.show_notification("Import Failed", "File extension not allowed or error occurred.")

    def on_clean_now(self):
        # Trigger cleanup manually (naive implementation: just log for now)
        print("Manual Cleanup Triggered")
        # In a real app, we'd expose a method in CleanupService to sweep check all files
        # For now, we rely on the TTL of existing files or user action
        self.show_notification("Cleanup Started", "System is cleaning up secure zones...")

    def on_exit(self, icon, item):
        self.cleanup_service.stop()
        self.usb_handler.stop()
        icon.stop()

    def show_notification(self, title, message):
        if self.icon:
            self.icon.notify(message, title)

    def run(self):
        print("Genesis Tray App Starting...")
        
        # Start Services
        threading.Thread(target=self.cleanup_service.start, daemon=True).start()
        threading.Thread(target=self.usb_handler.start, daemon=True).start()

        # Setup Tray
        image = self.create_image()
        menu = pystray.Menu(
            item('Secure Import...', self.on_secure_import),
            item('Clean Now', self.on_clean_now),
            item('Exit', self.on_exit)
        )
        
        self.icon = pystray.Icon("Genesis", image, "Genesis Secure Env", menu)
        self.icon.run()

if __name__ == "__main__":
    app = GenesisTrayApp()
    app.run()
