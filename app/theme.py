"""Windows theme detection utilities."""

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None


def windows_prefers_dark() -> bool:
    """Return True when Windows app theme preference is dark."""
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return int(value) == 0
    except Exception:
        return False
