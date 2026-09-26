"""浏览器接入层。

两种方式拿到一个"已经登录好 DeepSeek"的浏览器：

1. **附着到已经在跑的 Chrome**（推荐，浏览器里是什么状态就用什么状态）::

       "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
           --remote-debugging-port=9222 --user-data-dir=/path/to/profile

   然后 ``DeepSeekUser(cdp_url="http://127.0.0.1:9222")``。
2. **自己拉起一个持久化上下文**：``DeepSeekUser(user_data_dir="~/.deepseekweb/chrome-profile")``，
   首次手动登录一次，之后复用登录态。

两种方式都只开一个 Playwright 连接和一个页面，``DeepSeekSession`` 之间共用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .constants import CDP_URL_ENV, DEFAULT_READY_TIMEOUT, DEFAULT_USER_DATA_DIR
from .exceptions import BrowserError

CHROME_MAC = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_LINUX = "/usr/bin/google-chrome"
_CHAT_ORIGIN = "https://chat.deepseek.com"


def default_executable() -> str | None:
    """猜一个本机 Chrome 的可执行文件路径。"""
    from shutil import which

    for candidate in (CHROME_MAC, CHROME_LINUX):
        if Path(candidate).exists():
            return candidate
    return which("google-chrome") or which("chromium") or None


class DeepSeekBrowser:
    """Playwright 连接的薄封装，负责生命周期和页面复用。"""

    def __init__(
        self,
        *,
        cdp_url: str | None = None,
        user_data_dir: str | None = None,
        headless: bool = False,
        executable_path: str | None = None,
        viewport: tuple[int, int] | None = (1280, 900),
        slow_mo: int = 0,
        timeout: int = DEFAULT_READY_TIMEOUT,
        extra_args: list[str] | None = None,
    ) -> None:
        import os

        self.cdp_url = cdp_url or os.environ.get(CDP_URL_ENV) or None
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.executable_path = executable_path
        self.viewport = viewport
        self.slow_mo = slow_mo
        self.timeout = timeout
        self.extra_args = list(extra_args or [])

        self._playwright: Any = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._browser: Any = None  # CDP 模式下需要单独断开

    # ------------------------------------------------------------------ 连接

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            self.connect()
        assert self._context is not None
        return self._context

    @property
    def page(self) -> Page:
        """本库专用页面。

        附着模式（CDP）下优先复用已经打开的 DeepSeek 标签页，没有就新开一个——
        不去动用户别的标签页。自带浏览器模式下复用首屏。
        """
        if self._page is not None and not self._page.is_closed():
            return self._page
        context = self.context
        existing = next(
            (p for p in context.pages if p.url.startswith(_CHAT_ORIGIN)),
            None,
        )
        if existing is not None:
            self._page = existing
        elif not context.pages or self.cdp_url:
            self._page = context.new_page()
        else:
            self._page = context.pages[0]
        self._page.set_default_timeout(self.timeout)
        return self._page

    def connect(self) -> DeepSeekBrowser:
        """建立连接。已经连上过就直接返回。"""
        if self._context is not None:
            return self

        try:
            self._playwright = sync_playwright().start()
        except Exception as exc:
            raise BrowserError(f"无法启动 Playwright：{exc}") from exc

        try:
            if self.cdp_url:
                self._browser = self._playwright.chromium.connect_over_cdp(
                    self.cdp_url, timeout=self.timeout
                )
                if not self._browser.contexts:
                    raise BrowserError(f"{self.cdp_url} 上没有可用的浏览器上下文")
                self._context = self._browser.contexts[0]
            else:
                self._context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir or DEFAULT_USER_DATA_DIR,
                    headless=self.headless,
                    executable_path=self.executable_path or default_executable(),
                    viewport={"width": self.viewport[0], "height": self.viewport[1]}
                    if self.viewport
                    else None,
                    slow_mo=self.slow_mo,
                    timeout=self.timeout,
                    args=self.extra_args,
                )
        except BrowserError:
            self._teardown()
            raise
        except Exception as exc:
            self._teardown()
            raise BrowserError(f"浏览器连接失败：{exc}") from exc

        return self

    # ------------------------------------------------------------------ 清理

    def close(self) -> None:
        """断开连接。

        自带浏览器会被关掉；附着上去的 Chrome 只断连接，不动用户的窗口和标签页。
        """
        if self.cdp_url:
            try:
                self._browser and self._browser.close()
            except Exception as e:
                print(e)
        self._teardown()

    def _teardown(self) -> None:
        try:
            if self._context is not None and not self.cdp_url:
                self._context.close()
        except Exception as e:
            print(e)
        try:
            self._playwright and self._playwright.stop()
        except Exception as e:
            print(e)
        self._playwright = None
        self._context = None
        self._browser = None
        self._page = None

    def __enter__(self) -> DeepSeekBrowser:
        return self.connect()

    def __exit__(self, *exc_info: object) -> None:
        self.close()
