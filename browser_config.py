import os
import json
import winreg
import ctypes

class BrowserConfig:
    def __init__(self):
        self.config = self.load_config()
        self.target_browsers = self.config.get('target_browsers', ['chrome', 'edge'])

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
            
    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def configure_all(self, base_path):
        """Configure all targeted browsers to download to base_path/Downloads."""
        download_path = os.path.join(base_path, "Downloads")
        print(f"Configuring browser download paths to: {download_path}")
        
        results = {}
        for browser in self.target_browsers:
            if browser.lower() == 'chrome':
                results['chrome'] = self.configure_chrome(download_path)
            elif browser.lower() == 'edge':
                results['edge'] = self.configure_edge(download_path)
            elif browser.lower() == 'firefox':
                results['firefox'] = self.configure_firefox(download_path)
        
        return results

    def _set_registry_value(self, start_key, sub_key, value_name, value_data):
        """Helper to safely set a registry value, creating keys as needed."""
        try:
            # winreg.CreateKey creates the key if it doesn't exist (recursively)
            key = winreg.CreateKey(start_key, sub_key)
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, value_data)
            winreg.CloseKey(key)
            return True
        except PermissionError:
            print(f"Permission denied creating registry key: {sub_key}")
            return False
        except Exception as e:
            print(f"Registry error {sub_key}: {e}")
            return False

    def _configure_chromium_json(self, name, local_appdata_path, download_path):
        """Fallback: Configure Chromium-based browsers by editing Preferences JSON."""
        try:
            local_appdata = os.environ.get('LOCALAPPDATA', '')
            if not local_appdata:
                return False
                
            prefs_path = os.path.join(local_appdata, local_appdata_path, 'User Data', 'Default', 'Preferences')
            
            if not os.path.exists(prefs_path):
                print(f"{name}: Preferences file not found (browser might not be installed or run yet).")
                return False
                
            with open(prefs_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Ensure download dict exists
            if 'download' not in data:
                data['download'] = {}
                
            # Set path
            data['download']['default_directory'] = download_path
            data['download']['directory_upgrade'] = True
            data['download']['prompt_for_download'] = False
            
            # Write back
            # Note: Browser must be closed for this to stick cleanly, but often works or updates on restart
            with open(prefs_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
                
            print(f"{name}: Download path set via Preferences JSON to {download_path}")
            return True
        except Exception as e:
            print(f"{name} JSON config failed: {e}")
            return False

    def configure_chrome(self, download_path):
        """Set Chrome download directory via registry policy, falling back to JSON prefs."""
        # Policy keys require Admin. If not admin, skip to JSON to avoid "Permission Denied" noise.
        if self.is_admin():
            key_path = r"Software\Policies\Google\Chrome"
            if self._set_registry_value(winreg.HKEY_CURRENT_USER, key_path, "DownloadDirectory", download_path):
                print(f"Chrome: Download path set via Registry to {download_path}")
                return True
            print("Chrome: Registry write failed. Falling back to Preferences (JSON)...")
        else:
            print("Chrome: Running in User Mode. Configuring via Preferences (JSON)...")
            
        return self._configure_chromium_json('Chrome', r'Google\Chrome', download_path)

    def configure_edge(self, download_path):
        """Set Edge download directory via registry policy, falling back to JSON prefs."""
        if self.is_admin():
            key_path = r"Software\Policies\Microsoft\Edge"
            if self._set_registry_value(winreg.HKEY_CURRENT_USER, key_path, "DownloadDirectory", download_path):
                print(f"Edge: Download path set via Registry to {download_path}")
                return True
            print("Edge: Registry write failed. Falling back to Preferences (JSON)...")
        else:
            print("Edge: Running in User Mode. Configuring via Preferences (JSON)...")
            
        return self._configure_chromium_json('Edge', r'Microsoft\Edge', download_path)

    def configure_firefox(self, download_path):
        """Set Firefox download directory by modifying prefs.js."""
        try:
            # Find Firefox profile folder
            appdata = os.environ.get('APPDATA', '')
            firefox_profiles = os.path.join(appdata, 'Mozilla', 'Firefox', 'Profiles')
            
            if not os.path.exists(firefox_profiles):
                # Only log as debug/warning since user might not have Firefox
                # print("Firefox: Profile folder not found.")
                return False

            # Find the default profile (usually ends with .default or .default-release)
            profile_dir = None
            for folder in os.listdir(firefox_profiles):
                if 'default' in folder.lower():
                    profile_dir = os.path.join(firefox_profiles, folder)
                    break

            if not profile_dir:
                # print("Firefox: Default profile not found.")
                return False

            prefs_file = os.path.join(profile_dir, 'user.js')
            
            # Write Firefox preferences
            prefs = [
                f'user_pref("browser.download.dir", "{download_path.replace(os.sep, "/")}");',
                'user_pref("browser.download.folderList", 2);',  # 2 = use custom folder
                'user_pref("browser.download.useDownloadDir", true);'
            ]
            
            # Append to user.js
            with open(prefs_file, 'a') as f:
                f.write('\n// Genesis Secure Environment Settings\n')
                for pref in prefs:
                    f.write(pref + '\n')

            print(f"Firefox: Download path set to {download_path}")
            return True
        except Exception as e:
            print(f"Firefox config failed: {e}")
            return False

    def verify_config(self, expected_path):
        """Check if browser configurations are in place."""
        results = {}
        
        # Check Chrome
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Policies\Google\Chrome", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "DownloadDirectory")
            results['chrome'] = value == expected_path
            winreg.CloseKey(key)
        except:
            # Check JSON if registry failed
            try:
                local_appdata = os.environ.get('LOCALAPPDATA', '')
                prefs_path = os.path.join(local_appdata, r'Google\Chrome\User Data\Default\Preferences')
                with open(prefs_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                results['chrome'] = data.get('download', {}).get('default_directory') == expected_path
            except:
                results['chrome'] = False

        # Check Edge
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Policies\Microsoft\Edge", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "DownloadDirectory")
            results['edge'] = value == expected_path
            winreg.CloseKey(key)
        except:
            # Check JSON if registry failed
            try:
                local_appdata = os.environ.get('LOCALAPPDATA', '')
                prefs_path = os.path.join(local_appdata, r'Microsoft\Edge\User Data\Default\Preferences')
                with open(prefs_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                results['edge'] = data.get('download', {}).get('default_directory') == expected_path
            except:
                results['edge'] = False

        return results


if __name__ == "__main__":
    config = BrowserConfig()
    # Test with CWD for now
    test_path = os.path.join(os.getcwd(), "TestDownloads")
    config.configure_all(test_path)
    print("\nVerification:")
    print(config.verify_config(os.path.join(test_path, "Downloads")))

