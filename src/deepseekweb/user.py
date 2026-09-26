"""用户：谁在用这个浏览器。

``DeepSeekUser`` 持有账号信息和浏览器连接。登录态由浏览器 profile（或附着上去的那个
Chrome）负责持久化，所以同一个 user 反复构造也只会连一次浏览器。
"""

from __future__ import annotations

from typing import Any

from .browser import DeepSeekBrowser
from .constants import DEFAULT_TIMEOUT
from .history import SessionInfo, parse_sessions
from .login import login as do_login
from .page import ChatPage
from .session import DeepSeekSession


class DeepSeekUser:
    """一个 DeepSeek 用户。

    Args:
        account: 手机号或邮箱。可选——浏览器里已经登录过时不需要。
        passwd: 密码。可选，同上。
        cdp_url: 附着到已经在跑的 Chrome，例如 ``"http://127.0.0.1:9222"``。
            不给就自己拉起一个持久化浏览器（``user_data_dir``）。
        user_data_dir: 自带浏览器的 profile 目录，默认 ``~/.deepseekweb/chrome-profile``。
        headless: 自带浏览器是否无头。默认有头，方便首次手动登录。
        timeout: 单轮问答超时（毫秒）。
    """

    def __init__(
        self,
        account: str | None = None,
        passwd: str | None = None,
        *,
        cdp_url: str | None = None,
        user_data_dir: str | None = None,
        headless: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
        browser: DeepSeekBrowser | None = None,
        auto_login: bool = True,
        **browser_kwargs: Any,
    ) -> None:
        self.account = account
        self.passwd = passwd
        self.timeout = timeout
        self.auto_login = auto_login
        self._browser = browser or DeepSeekBrowser(
            cdp_url=cdp_url,
            user_data_dir=user_data_dir,
            headless=headless,
            timeout=timeout,
            **browser_kwargs,
        )
        self._page: ChatPage | None = None
        self._prepared = False

    # ------------------------------------------------------------------ 资源

    @property
    def browser(self) -> DeepSeekBrowser:
        return self._browser.connect()

    @property
    def page(self) -> ChatPage:
        """本用户专用的页面（懒加载，第一次用时才真正建连）。"""
        if self._page is None:
            self._page = ChatPage(self.browser.page, timeout=self.timeout)
        return self._page

    def prepare(self) -> ChatPage:
        """确保浏览器已连接、已登录、停在可用的页面上。"""
        if self._prepared:
            return self.page
        page = self.page
        if not page.is_logged_in():
            page.open_home()
            if not page.is_logged_in() and self.auto_login and self.account and self.passwd:
                do_login(page.page, self.account, self.passwd, timeout=self.timeout)
                page.open_home()  # 登录完回到聊天页
        page.require_login()
        self._prepared = True
        return page

    # ------------------------------------------------------------------ 历史

    def list_sessions(self, limit: int | None = None) -> list[SessionInfo]:
        """列出历史会话，最近更新的排在最前面。

        拿到 id 就能用 :meth:`DeepSeekSession.get_messages` 读它的内容::

            for info in user.list_sessions(limit=10):
                print(info.id, info.title)

        Args:
            limit: 最多返回几条。接口一次只给一页，这里在客户端截断。
        """
        sessions, _has_more = parse_sessions(self.prepare().fetch_sessions())
        return sessions[:limit] if limit else sessions

    def get_session(self, id: str) -> DeepSeekSession:
        """按 id 拿一个会话对象，用来读历史或继续对话。"""
        return DeepSeekSession(user=self, id=id, timeout=self.timeout)

    def close(self) -> None:
        """断开浏览器连接。"""
        self._browser.close()
        self._page = None
        self._prepared = False

    def __enter__(self) -> "DeepSeekUser":
        self.prepare()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:  # pragma: no cover - 展示用
        who = self.account or "已登录浏览器"
        return f"DeepSeekUser(account={who!r}, cdp_url={self._browser.cdp_url!r})"
