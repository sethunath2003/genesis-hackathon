import customtkinter as ctk
import os
import time
import json
import threading
from interface import GenesisDashboard # Importing your current UI
from print_monitor import PrintJobMonitor

class GenesisLiveMonitor(GenesisDashboard):
    def __init__(self, on_save_callback=None, print_monitor=None):
        super().__init__(on_save_callback=on_save_callback)
        
        self.print_monitor = print_monitor  # Reference to PrintJobMonitor for job tracking
        
        # --- New UI: Live File Queue ---
        self.geometry("450x600") # Making window taller for the list
        
        self.queue_label = ctk.CTkLabel(self, text="Live Secure Vault (Z: Drive)", font=("Segoe UI", 14, "bold"))
        self.queue_label.pack(pady=(10, 5))

        # Scrollable frame for file items
        self.scroll_frame = ctk.CTkScrollableFrame(self, width=400, height=180, corner_radius=10)
        self.scroll_frame.pack(pady=10, padx=20, fill="both", expand=True)

        # To keep track of UI labels and their print job status
        self.file_widgets = {} 
        
        # Start the background refresh loop
        self.update_thread_running = True
        threading.Thread(target=self.refresh_file_list, daemon=True).start()

    def refresh_file_list(self):
        """Background loop that now scans all subdirectories."""
        while self.update_thread_running:
            try:
                ttl_mins = self.load_current_timer()
                ttl_secs = ttl_mins * 60
                
                with open('config.json', 'r') as f:
                    conf = json.load(f)
                    # We look at the root of the secure drive (e.g., 'Z:/')
                    base_path = conf.get('secure_drive', 'Z') + ":/"

                if os.path.exists(base_path):
                    all_files = []
                    # WALK through all subfolders (Downloads, Quarantine, etc.)
                    for root, dirs, files in os.walk(base_path):
                        for name in files:
                            full_path = os.path.join(root, name)
                            all_files.append({
                                'name': name,
                                'path': full_path,
                                'folder': os.path.basename(root)
                            })
                    
                    current_time = time.time()
                    self.after(0, self.sync_ui_list, all_files, current_time, ttl_secs)
                else:
                    self.after(0, self.show_empty_msg, f"Drive {base_path} Not Found")
                    
            except Exception as e:
                print(f"Monitor Error: {e}")
            
            time.sleep(1)

    def sync_ui_list(self, file_data_list, current_time, ttl_secs):
        # Get active print jobs from monitor if available
        active_jobs = {}
        if self.print_monitor:
            active_jobs = self.print_monitor.get_active_jobs()
        
        # 1. Clean up UI for files that were deleted
        existing_names = [f['name'] for f in file_data_list]
        for f_name in list(self.file_widgets.keys()):
            if f_name not in existing_names:
                self.file_widgets[f_name]['frame'].destroy()
                del self.file_widgets[f_name]

        # 2. Add or update files from ALL subfolders
        for f_data in file_data_list:
            f_name = f_data['name']
            f_path = f_data['path']
            f_folder = f_data['folder']
            
            creation_time = os.path.getctime(f_path)
            elapsed = current_time - creation_time
            remaining = max(0, ttl_secs - elapsed)
            
            mins, secs = divmod(int(remaining), 60)
            time_str = f"{mins:02d}:{secs:02d}"
            
            # Check if file has an active print job
            has_active_job = f_path in active_jobs

            if f_name not in self.file_widgets:
                row = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
                row.pack(fill="x", pady=2)
                
                # Show which folder it's in (e.g., [Downloads] file.pdf)
                display_text = f"[{f_folder}] {f_name[:20]}"
                name_lbl = ctk.CTkLabel(row, text=display_text, font=("Segoe UI", 11), anchor="w")
                name_lbl.pack(side="left", padx=5)
                
                # Status indicator for print job
                status_lbl = ctk.CTkLabel(row, text="", font=("Segoe UI", 10, "bold"), text_color="#f39c12", width=40)
                status_lbl.pack(side="right", padx=2)
                
                time_lbl = ctk.CTkLabel(row, text=time_str, font=("Consolas", 12, "bold"), text_color="#e74c3c")
                time_lbl.pack(side="right", padx=10)
                
                self.file_widgets[f_name] = {
                    'frame': row,
                    'label': time_lbl,
                    'status_label': status_lbl,
                    'path': f_path,
                    'has_job': False
                }
            
            # Update time
            self.file_widgets[f_name]['label'].configure(text=time_str)
            
            # Update print job status indicator
            if has_active_job and not self.file_widgets[f_name]['has_job']:
                # Print job started - highlight
                self.file_widgets[f_name]['status_label'].configure(text="🖨️  PRINT")
                self.file_widgets[f_name]['frame'].configure(fg_color="#2c3e50")  # Highlight row
                self.file_widgets[f_name]['has_job'] = True
                print(f"[GenesisMonitor] Highlighting {f_name} - print job active")
            elif not has_active_job and self.file_widgets[f_name]['has_job']:
                # Print job completed - remove highlight
                self.file_widgets[f_name]['status_label'].configure(text="")
                self.file_widgets[f_name]['frame'].configure(fg_color="transparent")
                self.file_widgets[f_name]['has_job'] = False
                print(f"[GenesisMonitor] Removed highlight from {f_name} - print completed")

    def show_empty_msg(self, msg):
        if not self.file_widgets:
            self.display_label.configure(text=msg)

if __name__ == "__main__":
    # For standalone testing of the new UI
    app = GenesisLiveMonitor()
    app.mainloop()