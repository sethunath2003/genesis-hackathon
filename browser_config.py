import os
import json
import winreg

class BrowserConfig:
    def __init__(self):
        self.config = self.load_config()
        self.drive_letter = self.config.get('ramdisk_letter', 'Z')
        self.download_path = f"{self.drive_letter}:\\Downloads"
        self.target_browsers = self.config.get('target_browsers', ['chrome', 'edge'])

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def configure_all(self):
        """Configure all targeted browsers."""
        print("Configuring browser download paths...")
        
        results = {}
        for browser in self.target_browsers:
            if browser.lower() == 'chrome':
                results['chrome'] = self.configure_chrome()
            elif browser.lower() == 'edge':
                results['edge'] = self.configure_edge()
            elif browser.lower() == 'firefox':
                results['firefox'] = self.configure_firefox()
        
        return results

    def configure_chrome(self):
        """Set Chrome download directory via registry policy."""
        try:
            key_path = r"Software\Policies\Google\Chrome"
            
            # Create the key if it doesn't exist
            try:
                key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            except Exception:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            winreg.SetValueEx(key, "DownloadDirectory", 0, winreg.REG_SZ, self.download_path)
            winreg.CloseKey(key)
            
            print(f"Chrome: Download path set to {self.download_path}")
            return True
        except Exception as e:
            print(f"Chrome config failed: {e}")
            return False

    def configure_edge(self):
        """Set Edge download directory via registry policy."""
        try:
            key_path = r"Software\Policies\Microsoft\Edge"
            
            try:
                key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            except Exception:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            winreg.SetValueEx(key, "DownloadDirectory", 0, winreg.REG_SZ, self.download_path)
            winreg.CloseKey(key)
            
            print(f"Edge: Download path set to {self.download_path}")
            return True
        except Exception as e:
            print(f"Edge config failed: {e}")
            return False

    def configure_firefox(self):
        """Set Firefox download directory by modifying prefs.js."""
        try:
            # Find Firefox profile folder
            appdata = os.environ.get('APPDATA', '')
            firefox_profiles = os.path.join(appdata, 'Mozilla', 'Firefox', 'Profiles')
            
            if not os.path.exists(firefox_profiles):
                print("Firefox: Profile folder not found.")
                return False

            # Find the default profile (usually ends with .default or .default-release)
            profile_dir = None
            for folder in os.listdir(firefox_profiles):
                if 'default' in folder.lower():
                    profile_dir = os.path.join(firefox_profiles, folder)
                    break

            if not profile_dir:
                print("Firefox: Default profile not found.")
                return False

            prefs_file = os.path.join(profile_dir, 'user.js')
            
            # Write Firefox preferences
            prefs = [
                f'user_pref("browser.download.dir", "{self.download_path.replace(chr(92), "/")}");',
                'user_pref("browser.download.folderList", 2);',  # 2 = use custom folder
                'user_pref("browser.download.useDownloadDir", true);'
            ]
            
            with open(prefs_file, 'a') as f:
                f.write('\n// Genesis Secure Environment Settings\n')
                for pref in prefs:
                    f.write(pref + '\n')

            print(f"Firefox: Download path set to {self.download_path}")
            return True
        except Exception as e:
            print(f"Firefox config failed: {e}")
            return False

    def verify_config(self):
        """Check if browser configurations are in place."""
        results = {}
        
        # Check Chrome
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Policies\Google\Chrome", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "DownloadDirectory")
            results['chrome'] = value == self.download_path
            winreg.CloseKey(key)
        except:
            results['chrome'] = False

        # Check Edge
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Policies\Microsoft\Edge", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "DownloadDirectory")
            results['edge'] = value == self.download_path
            winreg.CloseKey(key)
        except:
            results['edge'] = False

        return results


if __name__ == "__main__":
    config = BrowserConfig()
    config.configure_all()
    print("\nVerification:")
    print(config.verify_config())
