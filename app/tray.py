# -*- coding: utf-8 -*-
"""
系统托盘支持。

依赖 pystray + pillow（可选）。若环境中缺少这些包，自动降级：
关闭窗口时直接退出程序，并向用户提示可安装 pystray 获得托盘功能。

托盘菜单：
  - 打开主界面
  - 切换置顶状态
  - 退出程序
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

try:  # 可选依赖，缺失时优雅降级
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
    TRAY_ERROR = ""
except Exception as exc:  # pragma: no cover - 取决于运行环境
    pystray = None
    Image = None
    ImageDraw = None
    TRAY_AVAILABLE = False
    TRAY_ERROR = str(exc)


class TrayManager:
    """封装 pystray 托盘图标。"""

    def __init__(self, on_open: Callable[[], None],
                 on_toggle_topmost: Callable[[], None],
                 on_quit: Callable[[], None]):
        self.on_open = on_open
        self.on_toggle_topmost = on_toggle_topmost
        self.on_quit = on_quit
        self.icon = None
        self._thread: Optional[threading.Thread] = None
        self.available = TRAY_AVAILABLE

    # ------------------------------------------------------------ 资源图标 ----
    @staticmethod
    def _make_image():
        """用 Pillow 画一个简洁的日历图标（蓝底白格）。"""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((4, 10, 60, 60), radius=8, fill=(0, 72, 157, 255))
        draw.rectangle((4, 10, 60, 26), fill=(255, 255, 255, 255))
        draw.rectangle((16, 4, 22, 14), fill=(0, 72, 157, 255))
        draw.rectangle((42, 4, 48, 14), fill=(0, 72, 157, 255))
        for row in range(3):
            for col in range(4):
                x = 12 + col * 12
                y = 32 + row * 9
                draw.rectangle((x, y, x + 7, y + 5), fill=(255, 255, 255, 255))
        return img

    # ------------------------------------------------------------ 生命周期 ----
    def start(self, title: str = "日程备忘") -> bool:
        """启动托盘图标（在独立线程中运行）。"""
        if not TRAY_AVAILABLE:
            return False
        try:
            image = self._make_image()
            menu = pystray.Menu(
                pystray.MenuItem("打开主界面", self._open, default=True),
                pystray.MenuItem("切换置顶状态", self._toggle),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出程序", self._quit),
            )
            self.icon = pystray.Icon("calmemo", image, title, menu)
            self._thread = threading.Thread(target=self.icon.run, daemon=True)
            self._thread.start()
            return True
        except Exception as exc:
            print(f"[tray] 托盘启动失败：{exc}")
            self.available = False
            return False

    def stop(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None

    def notify(self, title: str, message: str) -> None:
        """发送 Windows 气泡通知（托盘可用时）。"""
        if self.icon is not None:
            try:
                self.icon.notify(message, title)
                return
            except Exception:
                pass
        print(f"[tray-notify] {title}: {message}")

    # ------------------------------------------------------------ 菜单回调 ----
    def _open(self, icon=None, item=None) -> None:
        self.on_open()

    def _toggle(self, icon=None, item=None) -> None:
        self.on_toggle_topmost()

    def _quit(self, icon=None, item=None) -> None:
        self.on_quit()
