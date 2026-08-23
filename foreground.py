import ctypes
from ctypes import wintypes

import psutil

_user32 = ctypes.windll.user32

# Explicit argtypes/restype - without these, ctypes defaults to 32-bit c_int for
# the return value, which can silently truncate a pointer-sized HWND on 64-bit
# Windows. Works by luck most of the time (handles are usually small values),
# but not guaranteed.
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD


def get_foreground_info():
    """Returns (process_name_lower_or_None, window_title_or_None) for whatever
    window currently has focus."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None, None

    length = _user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buff, length + 1)
    title = buff.value or None

    pid = ctypes.c_ulong()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process_name = None
    if pid.value:
        try:
            process_name = psutil.Process(pid.value).name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            process_name = None

    return process_name, title


def is_distracting(process_name, title, config):
    distracting_processes = {p.lower() for p in config.get("distracting_processes", [])}
    if process_name and process_name.lower() in distracting_processes:
        return True
    if title:
        title_lower = title.lower()
        for kw in config.get("distracting_title_keywords", []):
            if kw.lower() in title_lower:
                return True
    return False
