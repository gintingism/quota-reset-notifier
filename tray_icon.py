from __future__ import annotations

import threading
from typing import Callable

import pystray
from PIL import Image, ImageDraw


class TrayIcon:
    def __init__(self, on_open: Callable[[], None], on_settings: Callable[[], None],
                 on_refresh: Callable[[], None], on_mode: Callable[[], None],
                 on_exit: Callable[[], None]) -> None:
        self.callbacks = on_open, on_settings, on_refresh, on_mode, on_exit
        self.icon: pystray.Icon | None = None

    def start(self) -> None:
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill="#7C3AED")
        draw.ellipse((18, 18, 46, 46), fill="#F9FAFB")
        menu = pystray.Menu(
            pystray.MenuItem("Open", lambda: self.callbacks[0]()),
            pystray.MenuItem("Refresh Now", lambda: self.callbacks[2]()),
            pystray.MenuItem("Re-auth / Ganti Token", lambda: self.callbacks[1]()),
            pystray.MenuItem("Mode Docked/Floating", lambda: self.callbacks[3]()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda: self.callbacks[4]()),
        )
        self.icon = pystray.Icon("QuotaResetNotifier", image, "Quota Reset Notifier", menu)
        self.icon.run()

    def stop(self) -> None:
        if self.icon:
            self.icon.stop()

    def run_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.start, name="system-tray", daemon=True)
        thread.start()
        return thread
