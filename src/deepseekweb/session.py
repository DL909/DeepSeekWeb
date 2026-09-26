"""会话：一个 DeepSeek 对话窗口。"""

from __future__ import annotations

import warnings
from typing import Any

from .constants import DEFAULT_TIMEOUT, SESSION_URL
from .page import ChatPage
from .response import DeepSeekResponse
from .sse import parse_stream

#: v0.1 明确不支持的能力，传什么都当作"关"
UNSUPPORTED = ("file", "search")


def _normalize(thinking: Any, search: Any, file: Any = None) -> tuple[bool, bool]:
    """把开关收敛成 v0.1 真正支持的形态。

    README 里写明：``search`` 和 ``file`` 暂不支持，无论发送什么都视为 ``None`` 和 ``False``。
    这里照做，但会对被忽略的取值给一次提示，免得以为搜索真的生效了。
    """
    if file is not None:
        warnings.warn(
            "v0.1 暂不支持 file，已忽略", UserWarning, stacklevel=3
        )
    if search:
        warnings.warn(
            "v0.1 暂不支持 search，已按 False 处理", UserWarning, stacklevel=3
        )
    return bool(thinking), False


class DeepSeekSession:
    """一个 DeepSeek 会话。

    构造已有会话::

        session = DeepSeekSession(user=user, id="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                                  thinking=False, search=False)

    或新建并直接发第一条消息::

        session, response = DeepSeekSession.new_session(user=user, input="hello")

    之后用 :meth:`send` 继续对话。``thinking`` 可以每次单独指定，不指定就沿用上一次的设置。
    """

    def __init__(
        self,
        user: Any,
        id: str,
        thinking: bool = False,
        search: bool = False,
        timeout: int | None = None,
    ) -> None:
        self.user = user
        self.id = id
        self.thinking, self.search = _normalize(thinking, search)
        self.timeout = timeout or getattr(user, "timeout", DEFAULT_TIMEOUT)

    # ------------------------------------------------------------------ 属性

    @property
    def url(self) -> str:
        return SESSION_URL.format(session_id=self.id)

    @property
    def _page(self) -> ChatPage:
        return self.user.prepare()

    # ------------------------------------------------------------------ 发消息

    @classmethod
    def new_session(
        cls,
        user: Any,
        input: str,
        file: Any = None,
        thinking: bool = True,
        search: bool = False,
        timeout: int | None = None,
    ) -> tuple["DeepSeekSession", DeepSeekResponse]:
        """开一个新会话并发第一条消息，返回 ``(session, response)``。"""
        page = user.prepare()
        page.open_home()
        page.require_login()
        thinking, search = _normalize(thinking, search, file)
        page.set_toggle("thinking", thinking)
        page.set_toggle("search", search)

        raw = page.send(input, timeout=timeout or user.timeout)
        session_id = page.current_session_id()
        if not session_id:
            raise RuntimeError("发送成功但没有拿到会话 id，请检查地址栏是否跳转到 /a/chat/s/...")

        session = cls(user=user, id=session_id, thinking=thinking, search=search, timeout=timeout)
        return session, session._build_response(raw, question=input)

    def send(
        self,
        input: str,
        thinking: bool | None = None,
        search: bool | None = None,
        file: Any = None,
    ) -> DeepSeekResponse:
        """在当前会话里继续问一句。

        ``thinking``/``search`` 不传就沿用上一次的值。``file`` 与 ``search`` 在 v0.1 里
        会被忽略（见 :data:`UNSUPPORTED`）。
        """
        thinking = self.thinking if thinking is None else thinking
        search = self.search if search is None else search
        thinking, search = _normalize(thinking, search, file)

        page = self._page
        if page.current_session_id() != self.id:
            page.open_session(self.id)
            page.require_login()
        page.set_toggle("thinking", thinking)
        page.set_toggle("search", search)
        self.thinking, self.search = thinking, search

        raw = page.send(input, timeout=self.timeout)
        return self._build_response(raw, question=input)

    # ------------------------------------------------------------------ 内部

    def _build_response(self, raw: str | None, question: str) -> DeepSeekResponse:
        summary = parse_stream(raw)
        text = self._page.last_message()
        return DeepSeekResponse(
            answer=text.get("answer", ""),
            reasoning=text.get("reasoning", ""),
            question=question or text.get("question", ""),
            session_id=self.id,
            thinking_enabled=self.thinking,
            search_enabled=self.search,
            status=summary.status,
            usage=summary.usage,
            title=summary.title,
            raw=raw,
        )

    def __repr__(self) -> str:  # pragma: no cover - 展示用
        return f"DeepSeekSession(id={self.id!r}, thinking={self.thinking}, search={self.search})"
