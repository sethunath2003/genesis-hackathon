import os
import json
import shutil
import time

class RamDiskService:
    def __init__(self):
        self.config = self.load_config()
        # We keep the name "RamDisk" for compatibility, but it's now a local folder
        self.local_appdata = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        self.mount_path = os.path.join(self.local_appdata, 'GenesisSecure', 'SessionStorage')
        self.is_mounted = False

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def create_ramdisk(self):
        """Create the temporary storage directory."""
        try:
            if not os.path.exists(self.mount_path):
                os.makedirs(self.mount_path, exist_ok=True)
                print(f"Created secure storage at: {self.mount_path}")
            else:
                print(f"Secure storage ready at: {self.mount_path}")
            
            self.is_mounted = True
            self._ensure_folders()
            return True
        except Exception as e:
            print(f"ERROR creating storage: {e}")
            return False

    def _ensure_folders(self):
        """Create necessary folders in the storage location."""
        folders = [
            os.path.join(self.mount_path, "Downloads"),
            os.path.join(self.mount_path, "AutoPrint"),
            os.path.join(self.mount_path, "Quarantine")
        ]
        for folder in folders:
            if not os.path.exists(folder):
                try:
                    os.makedirs(folder, exist_ok=True)
                    print(f"Created folder: {folder}")
                except Exception as e:
                    print(f"Failed to create {folder}: {e}")

    def remove_ramdisk(self):
        """Clean up the storage directory."""
        # For a local folder, 'removing' might just mean wiping it, 
        # but we can leave the empty dir structure.
        return self.wipe_contents()

    def wipe_contents(self):
        """Delete all files in the storage location."""
        if not os.path.exists(self.mount_path):
            print("Storage path not available.")
            return False

        print(f"Wiping contents within {self.mount_path}...")
        folders = [
            os.path.join(self.mount_path, "Downloads"),
            os.path.join(self.mount_path, "AutoPrint"),
            os.path.join(self.mount_path, "Quarantine")
        ]
        
        for folder in folders:
            if os.path.exists(folder):
                for item in os.listdir(folder):
                    item_path = os.path.join(folder, item)
                    try:
                        if os.path.isfile(item_path):
                            os.remove(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        print(f"Deleted: {item_path}")
                    except Exception as e:
                        print(f"Failed to delete {item_path}: {e}")
        
        print("Storage wiped.")
        return True

    def start(self):
        """Start the storage service."""
        return self.create_ramdisk()

    def stop(self):
        """Stop the service."""
        print("Storage Service stopped.")

if __name__ == "__main__":
    service = RamDiskService()
    if service.start():
        print(f"Storage ready at {service.mount_path}")
        # input("Press Enter to wipe and exit...")
        # service.wipe_contents()
    else:
        print("Failed to start storage service.")

