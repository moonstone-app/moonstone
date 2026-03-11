"""
Create OS-native desktop shortcuts for Moonstone.

Usage:
    moonstone --install-shortcut
    moonstone --uninstall-shortcut
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

APP_NAME = "Moonstone"
APP_ID = "moonstone"
APP_COMMENT = "Headless PKM Server"
ICON_FILENAME = "moonstone.svg"


def _get_icon_source() -> Path:
    """Return path to the bundled SVG icon."""
    return Path(__file__).parent / "data" / ICON_FILENAME


def _find_executable() -> str:
    """Find the moonstone executable path."""
    exe = shutil.which("moonstone")
    if exe:
        return exe
    # pipx puts it in ~/.local/bin
    local_bin = Path.home() / ".local" / "bin" / "moonstone"
    if local_bin.exists():
        return str(local_bin)
    return "moonstone"  # fallback


# ── Linux ────────────────────────────────────────────────────────────


def _install_linux():
    apps_dir = Path.home() / ".local" / "share" / "applications"
    icons_dir = (
        Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
    )

    apps_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)

    # Copy icon
    icon_src = _get_icon_source()
    icon_dst = icons_dir / ICON_FILENAME
    if icon_src.exists():
        shutil.copy2(icon_src, icon_dst)
        print(f"  Icon → {icon_dst}")
    else:
        print(f"  ⚠ Icon not found: {icon_src}")

    # Create .desktop file
    exe = _find_executable()
    desktop_content = f"""[Desktop Entry]
Name={APP_NAME}
Comment={APP_COMMENT}
Exec={exe}
Icon={APP_ID}
Type=Application
Categories=Utility;Office;
Terminal=false
StartupNotify=false
"""
    desktop_file = apps_dir / f"{APP_ID}.desktop"
    desktop_file.write_text(desktop_content)
    desktop_file.chmod(0o755)
    print(f"  Shortcut → {desktop_file}")

    # Update desktop database (optional, non-fatal)
    try:
        subprocess.run(
            ["update-desktop-database", str(apps_dir)],
            capture_output=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    print(f"✓ {APP_NAME} added to application menu.")


def _uninstall_linux():
    desktop_file = (
        Path.home() / ".local" / "share" / "applications" / f"{APP_ID}.desktop"
    )
    icon_file = (
        Path.home()
        / ".local"
        / "share"
        / "icons"
        / "hicolor"
        / "scalable"
        / "apps"
        / ICON_FILENAME
    )

    for f in (desktop_file, icon_file):
        if f.exists():
            f.unlink()
            print(f"  Removed {f}")
        else:
            print(f"  Not found: {f}")

    print(f"✓ {APP_NAME} removed from application menu.")


# ── Windows ──────────────────────────────────────────────────────────


def _install_windows():
    exe = _find_executable()
    start_menu = (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
    )

    if not start_menu.exists():
        print(f"✗ Start Menu folder not found: {start_menu}")
        return

    lnk_path = start_menu / f"{APP_NAME}.lnk"

    # Use PowerShell to create .lnk (no extra dependencies)
    ps_script = (
        f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut("{lnk_path}");'
        f'$s.TargetPath = "{exe}";'
        f'$s.Description = "{APP_COMMENT}";'
        f"$s.Save()"
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            timeout=10,
            check=True,
        )
        print(f"  Shortcut → {lnk_path}")
        print(f"✓ {APP_NAME} added to Start Menu.")
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as e:
        print(f"✗ Failed to create shortcut: {e}")


def _uninstall_windows():
    start_menu = (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
    )
    lnk_path = start_menu / f"{APP_NAME}.lnk"

    if lnk_path.exists():
        lnk_path.unlink()
        print(f"  Removed {lnk_path}")
    else:
        print(f"  Not found: {lnk_path}")

    print(f"✓ {APP_NAME} removed from Start Menu.")


# ── macOS ────────────────────────────────────────────────────────────


def _install_macos():
    exe = _find_executable()
    app_dir = Path.home() / "Applications"
    app_dir.mkdir(exist_ok=True)

    wrapper = app_dir / f"{APP_NAME}.command"
    wrapper.write_text(f'#!/bin/sh\nexec "{exe}" "$@"\n')
    wrapper.chmod(0o755)

    print(f"  Wrapper → {wrapper}")
    print(f"✓ {APP_NAME} added to ~/Applications.")
    print(f"  (Double-click {APP_NAME}.command to launch)")


def _uninstall_macos():
    wrapper = Path.home() / "Applications" / f"{APP_NAME}.command"
    if wrapper.exists():
        wrapper.unlink()
        print(f"  Removed {wrapper}")
    else:
        print(f"  Not found: {wrapper}")

    print(f"✓ {APP_NAME} removed from ~/Applications.")


# ── Public API ───────────────────────────────────────────────────────


def install_shortcut():
    """Create an OS-native desktop shortcut for Moonstone."""
    print(f"Installing {APP_NAME} shortcut...")
    if sys.platform.startswith("linux"):
        _install_linux()
    elif sys.platform == "win32":
        _install_windows()
    elif sys.platform == "darwin":
        _install_macos()
    else:
        print(f"✗ Unsupported platform: {sys.platform}")
        sys.exit(1)


def uninstall_shortcut():
    """Remove the OS-native desktop shortcut for Moonstone."""
    print(f"Removing {APP_NAME} shortcut...")
    if sys.platform.startswith("linux"):
        _uninstall_linux()
    elif sys.platform == "win32":
        _uninstall_windows()
    elif sys.platform == "darwin":
        _uninstall_macos()
    else:
        print(f"✗ Unsupported platform: {sys.platform}")
        sys.exit(1)
