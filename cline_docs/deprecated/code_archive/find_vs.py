# DEPRECATED: Legacy one-off environment probe script retained for reference only. Not part of Gen 3 pipeline/runtime.
import subprocess, os

# Try where command to find Vintagestory.exe on C: drive
try:
    result = subprocess.run(
        ['where', '/R', 'C:\\', 'Vintagestory.exe'],
        capture_output=True, text=True, timeout=120
    )
    if result.stdout.strip():
        print("Found via where:")
        print(result.stdout.strip())
    else:
        print("where command found nothing on C:")
except Exception as e:
    print(f"where search error: {e}")

# Also check D: drive
for drive in ['D:\\', 'E:\\']:
    if os.path.isdir(drive):
        try:
            result = subprocess.run(
                ['where', '/R', drive, 'Vintagestory.exe'],
                capture_output=True, text=True, timeout=60
            )
            if result.stdout.strip():
                print(f"\nFound on {drive}:")
                print(result.stdout.strip())
        except:
            pass

# Also check via registry
try:
    import winreg
    for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
        for path in [
            r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
            r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
        ]:
            try:
                key = winreg.OpenKey(hive, path)
                for i in range(256):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)
                        try:
                            name, _ = winreg.QueryValueEx(subkey, 'DisplayName')
                            if 'vintage' in name.lower():
                                loc, _ = winreg.QueryValueEx(subkey, 'InstallLocation')
                                print(f"Registry: {name} -> {loc}")
                        except:
                            pass
                    except OSError:
                        break
            except:
                pass
except Exception as e:
    print(f"Registry search error: {e}")
