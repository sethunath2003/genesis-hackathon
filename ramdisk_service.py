import os
import json
import subprocess
import time

class RamDiskService:
    def __init__(self):
        self.config = self.load_config()
        self.drive_letter = self.config.get('ramdisk_letter', 'Z')
        self.base_folder = os.path.join(os.environ.get('TEMP', 'C:\\Temp'), 'GenesisSecure')
        self.is_mounted = False

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def is_drive_available(self):
        """Check if the drive letter is already in use."""
        return os.path.exists(f"{self.drive_letter}:\\")

    def create_ramdisk(self):
        """Create a virtual drive using SUBST command (no external tools needed)."""
        if self.is_drive_available():
            print(f"Virtual Drive {self.drive_letter}: already exists.")
            self.is_mounted = True
            self._ensure_folders()
            return True

        print(f"Creating Virtual Drive {self.drive_letter}: using SUBST...")
        
        try:
            # Create the base folder if it doesn't exist
            if not os.path.exists(self.base_folder):
                os.makedirs(self.base_folder)
                print(f"Created base folder: {self.base_folder}")

            # SUBST command to create a virtual drive letter
            cmd = ["subst", f"{self.drive_letter}:", self.base_folder]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"Virtual Drive {self.drive_letter}: created successfully.")
                print(f"  -> Points to: {self.base_folder}")
                self.is_mounted = True
                self._ensure_folders()
                return True
            else:
                print(f"Failed to create Virtual Drive: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"ERROR creating Virtual Drive: {e}")
            return False

    def _ensure_folders(self):
        """Create necessary folders on the virtual drive."""
        folders = [
            f"{self.drive_letter}:/Downloads",
            f"{self.drive_letter}:/AutoPrint",
            f"{self.drive_letter}:/Quarantine"
        ]
        for folder in folders:
            if not os.path.exists(folder):
                try:
                    os.makedirs(folder)
                    print(f"Created folder: {folder}")
                except Exception as e:
                    print(f"Failed to create {folder}: {e}")

    def remove_ramdisk(self):
        """Remove the virtual drive."""
        if not self.is_drive_available():
            print(f"Virtual Drive {self.drive_letter}: not mounted.")
            return True

        print(f"Removing Virtual Drive {self.drive_letter}:...")
        
        try:
            cmd = ["subst", f"{self.drive_letter}:", "/d"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"Virtual Drive {self.drive_letter}: removed.")
                self.is_mounted = False
                return True
            else:
                print(f"Failed to remove Virtual Drive: {result.stderr}")
                return False
        except Exception as e:
            print(f"ERROR removing Virtual Drive: {e}")
            return False

    def wipe_contents(self):
        """Delete all files in the virtual drive without removing the drive itself."""
        if not self.is_drive_available():
            print("Virtual Drive not available.")
            return False

        print("Wiping Virtual Drive contents...")
        folders = [
            f"{self.drive_letter}:/Downloads",
            f"{self.drive_letter}:/AutoPrint",
            f"{self.drive_letter}:/Quarantine"
        ]
        
        import shutil
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
        
        print("Virtual Drive wiped.")
        return True

    def start(self):
        """Start the virtual drive service."""
        return self.create_ramdisk()

    def stop(self):
        """Stop the virtual drive service."""
        print("Virtual Drive Service stopped (drive remains mounted until removed).")


if __name__ == "__main__":
    service = RamDiskService()
    if service.start():
        print(f"Virtual Drive ready at {service.drive_letter}:\\")
        input("Press Enter to wipe and exit...")
        service.wipe_contents()
    else:
        print("Failed to start Virtual Drive service.")
