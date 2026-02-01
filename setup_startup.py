"""
Setup script to configure Genesis to auto-start on Windows boot.
Run this once with admin privileges: python setup_startup.py
"""

import os
import sys
import subprocess
import winreg
from pathlib import Path

def setup_startup():
    """Add Genesis app to Windows startup registry."""
    
    # Get the full path to tray_app.py
    repo_dir = Path(__file__).parent
    tray_app_path = repo_dir / "tray_app.py"
    python_exe = sys.executable
    
    if not tray_app_path.exists():
        print(f"Error: {tray_app_path} not found.")
        return False
    
    # Create a batch file to run the app silently in the background
    batch_file = repo_dir / "genesis_autostart.bat"
    batch_content = f"""@echo off
REM Run Genesis in background (invisible window)
pythonw "{python_exe}" "{tray_app_path}"
"""
    
    try:
        with open(batch_file, 'w') as f:
            f.write(batch_content)
        print(f"✓ Created startup batch file: {batch_file}")
    except Exception as e:
        print(f"✗ Error creating batch file: {e}")
        return False
    
    # Add to Windows Registry (HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run)
    try:
        registry_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path, 0, winreg.KEY_WRITE)
        
        # Set the registry value to run the batch file
        winreg.SetValueEx(registry_key, "Genesis", 0, winreg.REG_SZ, str(batch_file))
        winreg.CloseKey(registry_key)
        
        print(f"✓ Added Genesis to Windows startup registry")
        print(f"  Registry key: HKEY_CURRENT_USER\\{registry_path}\\Genesis")
        print(f"  Value: {batch_file}")
        return True
    except PermissionError:
        print("✗ Permission denied. Run this script as Administrator.")
        print("  Right-click Command Prompt and select 'Run as administrator'")
        return False
    except Exception as e:
        print(f"✗ Error modifying registry: {e}")
        return False

def remove_startup():
    """Remove Genesis from Windows startup."""
    try:
        registry_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path, 0, winreg.KEY_WRITE)
        winreg.DeleteValue(registry_key, "Genesis")
        winreg.CloseKey(registry_key)
        print("✓ Removed Genesis from Windows startup")
        return True
    except FileNotFoundError:
        print("✓ Genesis was not in startup registry")
        return True
    except PermissionError:
        print("✗ Permission denied. Run this script as Administrator.")
        return False
    except Exception as e:
        print(f"✗ Error removing registry entry: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "remove":
        print("Removing Genesis from Windows startup...")
        remove_startup()
    else:
        print("Setting up Genesis to auto-start on Windows boot...")
        print("(This requires Administrator privileges)")
        if setup_startup():
            print("\n✓ Setup complete! Genesis will now start automatically on next boot.")
        else:
            print("\n✗ Setup failed. See errors above.")
            sys.exit(1)
