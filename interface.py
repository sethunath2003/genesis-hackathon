import customtkinter as ctk
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import logging
import threading
import sys
import os
import json  # Added for config management

logger = logging.getLogger(__name__)

class GenesisDashboard(ctk.CTk):
    def __init__(self, on_save_callback=None):
        super().__init__()

        # Optional callback invoked after saving settings (signature: callback(minutes))
        self.on_save_callback = on_save_callback

        # --- Data Persistence Logic ---
        self.config_file = 'config.json'
        self.current_saved_value = self.load_current_timer()

        # --- Window Configuration ---
        self.title("Genesis Secure Environment Settings")
        self.geometry("450x380")
        self.resizable(False, False)
        
        # Windows Native feel: Set to system theme
        ctk.set_appearance_mode("system") 
        ctk.set_default_color_theme("blue")

        # Handle the "X" button to hide instead of close
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        # --- App Status Header ---
        self.status_frame = ctk.CTkFrame(self, corner_radius=10)
        self.status_frame.pack(pady=20, padx=20, fill="x")
        
        self.status_dot = ctk.CTkLabel(self.status_frame, text="●", text_color="#2ecc71", font=("Arial", 20))
        self.status_dot.grid(row=0, column=0, padx=(15, 5), pady=10)
        
        self.status_text = ctk.CTkLabel(self.status_frame, text="System Active: Monitoring Z:\\ Drive", font=("Segoe UI", 14, "bold"))
        self.status_text.grid(row=0, column=1, pady=10)

        # --- Time Management Section ---
        self.settings_label = ctk.CTkLabel(self, text="Auto-Delete Unprinted Files", font=("Segoe UI", 13))
        self.settings_label.pack(anchor="w", padx=30)

        self.control_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.control_frame.pack(pady=10, padx=20, fill="x")

        # Slider (1 to 60)
        self.time_slider = ctk.CTkSlider(self.control_frame, from_=1, to=60, number_of_steps=59, command=self.sync_from_slider)
        self.time_slider.set(self.current_saved_value)
        self.time_slider.pack(side="left", padx=(10, 20), expand=True, fill="x")

        # Dropdown
        self.options = ["1 min", "10 min", "20 min", "30 min", "40 min", "50 min", "60 min"]
        self.time_dropdown = ctk.CTkOptionMenu(self.control_frame, values=self.options, width=100, command=self.sync_from_dropdown)
        self.time_dropdown.set(f"{self.current_saved_value} min")
        self.time_dropdown.pack(side="right", padx=10)

        self.display_label = ctk.CTkLabel(self, text=f"Files will be purged after: {self.current_saved_value} minutes", font=("Segoe UI", 12, "italic"))
        self.display_label.pack(pady=(0, 20))

        # --- Footer ---
        self.separator = ctk.CTkFrame(self, height=2, fg_color="gray")
        self.separator.pack(fill="x", padx=20, pady=10)

        self.button_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.button_frame.pack(side="bottom", padx=30, pady=20, fill="x")

        self.cancel_button = ctk.CTkButton(
            self.button_frame, 
            text="Cancel", 
            width=100, 
            fg_color="#808080", 
            command=self.on_cancel_click
        )
        self.cancel_button.pack(side="right", padx=(10, 0))

        self.ok_button = ctk.CTkButton(self.button_frame, text="OK", width=100, command=self.on_ok_click)
        self.ok_button.pack(side="right", padx=(0, 10))

    # --- Logic Methods ---

    def load_current_timer(self):
        """Loads the saved timer from config.json."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    return data.get('cleanup_interval_minutes', 15)
        except Exception as e:
            print(f"Error loading config: {e}")
        return 15

    def sync_from_slider(self, value):
        minutes = int(value)
        self.display_label.configure(text=f"Files will be purged after: {minutes} minutes")
        self.time_dropdown.set(f"{minutes} min")

    def sync_from_dropdown(self, choice):
        minutes = int(choice.split()[0])
        self.time_slider.set(minutes)
        self.display_label.configure(text=f"Files will be purged after: {minutes} minutes")

    def hide_window(self):
        self.withdraw()

    def on_ok_click(self):
        """Saves changes to config.json and provides terminal feedback."""
        new_time = int(self.time_slider.get())
        self.current_saved_value = new_time
        
        try:
            config_data = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
            
            config_data['cleanup_interval_minutes'] = new_time
            
            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=4)
            
            logger.info(f"[SETTING SAVED] Termination time: {new_time} minutes.")
            print(f"\n[SETTING SAVED] Termination time: {new_time} minutes.")
            logger.info(f"[STATUS] {self.config_file} updated successfully.")

            # Notify running backend (if a callback was provided)
            if getattr(self, 'on_save_callback', None):
                try:
                    self.on_save_callback(new_time)
                    logger.info(f"[CALLBACK] Notified backend of new TTL: {new_time} minutes")
                except Exception as e:
                    logger.exception("Error calling on_save_callback")
                    print(f"Error calling on_save_callback: {e}")
        except Exception as e:
            print(f"Error saving to {self.config_file}: {e}")

        self.hide_window()

    def on_cancel_click(self):
        """Reverts the UI to the last saved value and hides."""
        print("Settings cancelled. Reverting UI to last saved value.")
        self.time_slider.set(self.current_saved_value)
        self.sync_from_slider(self.current_saved_value)
        self.hide_window()

class TrayAppWrapper:
    def __init__(self):
        self.gui = None
        self.icon = None

    def create_tray_icon(self):
        # Create square green icon
        image = Image.new('RGB', (64, 64), "black")
        draw = ImageDraw.Draw(image)
        draw.rectangle((16, 16, 48, 48), fill="green")
        
        menu = pystray.Menu(
            item('Settings', self.open_settings, default=True),
            item('Exit', self.exit_app)
        )
        self.icon = pystray.Icon("Genesis", image, "Genesis Secure Env", menu)
        
        # Pre-initialize GUI in background thread
        threading.Thread(target=self.initialize_gui, daemon=True).start()
        
        self.icon.run()

    def initialize_gui(self):
        self.gui = GenesisDashboard()
        self.gui.withdraw()
        self.gui.mainloop()

    def open_settings(self, icon=None, item=None):
        if self.gui:
            self.gui.after(0, self.gui.deiconify)
            self.gui.after(0, self.gui.focus_force)

    def exit_app(self, icon, item):
        self.icon.stop()
        if self.gui:
            self.gui.after(0, self.gui.quit)
        os._exit(0)

if __name__ == "__main__":
    app = TrayAppWrapper()
    app.create_tray_icon()