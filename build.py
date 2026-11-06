from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
ICON_PATH = ROOT / "quota_reset_notifier.ico"


def create_icon() -> None:
    image = Image.new("RGBA", (256, 256), (30, 30, 36, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 238, 238), radius=56, fill="#25252E", outline="#8B7CF6", width=8)
    draw.arc((58, 58, 198, 198), start=35, end=320, fill="#4ADE80", width=18)
    draw.line((128, 128, 128, 84), fill="#F4F4F5", width=14)
    draw.line((128, 128, 164, 150), fill="#F4F4F5", width=14)
    image.save(ICON_PATH, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])


def main() -> None:
    create_icon()
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--noconsole",
        "--name", "QuotaResetNotifier", "--icon", str(ICON_PATH),
        "--collect-all", "customtkinter",
        "--collect-all", "pystray",
        "--hidden-import", "PIL._tkinter_finder",
        str(ROOT / "main.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    print("Built:", ROOT / "dist" / "QuotaResetNotifier.exe")


if __name__ == "__main__":
    main()
