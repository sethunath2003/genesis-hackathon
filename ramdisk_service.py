import os
import json
import subprocess
import time

class RamDiskService:
    def __init__(self):
        self.config = self.load_config()
        self.drive_letter = self.config.get('ramdisk_letter', 'Z')
        self.size_mb = self.config.get('ramdisk_size_mb', 512)
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
        """Create a RAM disk using ImDisk."""
        if self.is_drive_available():
            print(f"RAM Disk {self.drive_letter}: already exists.")
            self.is_mounted = True
            self._ensure_folders()
            return True

        print(f"Creating RAM Disk {self.drive_letter}: ({self.size_mb}MB)...")
        
        try:
            # ImDisk command to create a RAM disk
            # Format: imdisk -a -s <size>M -m <drive>: -p "/fs:ntfs /q /y"
            cmd = [
                "imdisk",
                "-a",                           # Add virtual disk
                "-s", f"{self.size_mb}M",       # Size in MB
                "-m", f"{self.drive_letter}:",  # Mount point (drive letter)
                "-p", "/fs:ntfs /q /y"          # Format as NTFS, quick, no prompt
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print(f"RAM Disk {self.drive_letter}: created successfully.")
                self.is_mounted = True
                # Give Windows a moment to recognize the drive
                time.sleep(2)
                self._ensure_folders()
                return True
            else:
                print(f"Failed to create RAM Disk: {result.stderr}")
                return False
                
        except FileNotFoundError:
            print("ERROR: ImDisk not found. Please install ImDisk Toolkit.")
            print("Download from: http://www.ltr-data.se/opencode.html/")
            return False
        except subprocess.TimeoutExpired:
            print("ERROR: ImDisk command timed out.")
            return False
        except Exception as e:
            print(f"ERROR creating RAM Disk: {e}")
            return False

    def _ensure_folders(self):
        """Create necessary folders on the RAM disk."""
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
        """Remove the RAM disk."""
        if not self.is_drive_available():
            print(f"RAM Disk {self.drive_letter}: not mounted.")
            return True

        print(f"Removing RAM Disk {self.drive_letter}:...")
        
        try:
            cmd = ["imdisk", "-D", "-m", f"{self.drive_letter}:"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                print(f"RAM Disk {self.drive_letter}: removed.")
                self.is_mounted = False
                return True
            else:
                print(f"Failed to remove RAM Disk: {result.stderr}")
                return False
        except Exception as e:
            print(f"ERROR removing RAM Disk: {e}")
            return False

    def wipe_contents(self):
        """Delete all files in the RAM disk without removing the disk itself."""
        if not self.is_drive_available():
            print("RAM Disk not available.")
            return False

        print("Wiping RAM Disk contents...")
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
        
        print("RAM Disk wiped.")
        return True

    def start(self):
        """Start the RAM disk service."""
        return self.create_ramdisk()

    def stop(self):
        """Stop the RAM disk service (optionally remove the disk)."""
        # We do NOT remove the disk on stop, as it would lose data
        # The disk is volatile and will be cleared on reboot anyway
        print("RAM Disk Service stopped (disk remains mounted until reboot).")


if __name__ == "__main__":
    service = RamDiskService()
    if service.start():
        print(f"RAM Disk ready at {service.drive_letter}:\\")
        input("Press Enter to wipe and exit...")
        service.wipe_contents()
    else:
        print("Failed to start RAM Disk service.")
