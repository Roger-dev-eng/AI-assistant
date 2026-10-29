import os
import subprocess
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AssistantDesktop"


def startup_command():
    args = [sys.executable]
    if not getattr(sys, "frozen", False):
        args += ["-m", "assistant"]
    return subprocess.list2cmdline([*args, "--gui", "--tray"])


def configure_startup(enabled):
    if os.name != "nt":
        if enabled:
            raise RuntimeError("Startup configuration requires Windows.")
        return
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, access=winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
