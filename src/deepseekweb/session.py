"""会话：一个 DeepSeek 对话窗口。"""

from __future__ import annotations

import warnings
from typing import Any

from .constants import DEFAULT_TIMEOUT, SESSION_URL
from .exceptions import DeepSeekWebError
from .history import parse_messages
from .messages import Message, UserPrompt
from .page import ChatPage
from .response import DeepSeekResponse
from .sse import parse_stream


def _pick_assistant(
    messages: list[Message], message_id: int | None
) -> DeepSeekResponse | None:
    """在历史里定位本轮的助手消息：优先按 id，定位不到就用最后一条。"""
    answers = [m for m in messages if isinstance(m, DeepSeekResponse)]
    if not answers:
        return None
    for message in answers:
        if message_id is not None and message.id == message_id:
            return message
    return answers[-1]


def _question_before(messages: list[Message], answer: DeepSeekResponse) -> UserPrompt | None:
    """取这条助手消息对应的上一条用户提问。"""
    for index, item in enumerate(messages):
        if item is answer:
            for previous in reversed(messages[:index]):
                if isinstance(previous, UserPrompt):
                    return previous
            return None
    return None

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

    # ------------------------------------------------------------------ 读历史

    def get_messages(self) -> list[Message]:
        """读出这个会话的完整对话，按对话顺序返回。

        返回 :class:`~deepseekweb.messages.UserPrompt` 与
        :class:`~deepseekweb.response.DeepSeekResponse` 交替的列表::

            for message in session.get_messages():
                if isinstance(message, UserPrompt):
                    print(message.content)
                else:
                    print(message.answer)

        走的是服务端接口而不是页面 DOM：长对话不会被虚拟列表的渲染窗口截断，
        也不需要先把页面切到这个会话。重新生成留下的旧分支不会出现——
        只返回当前这条分支。
        """
        return parse_messages(self._page.fetch_history(self.id), session_id=self.id)

    # ------------------------------------------------------------------ 内部

    def _build_response(self, raw: str | None, question: str) -> DeepSeekResponse:
        """组装本轮回复。

        正文取自 ``history_messages`` 里的 RESPONSE fragment，那是**未经渲染的原文**
        （通常就是 markdown）。不用 DOM 是因为 DOM 拿到的是渲染后的纯文本：`**` 会被
        去掉、列表会摊成一段段、代码块的围栏会消失，连"复制""下载"这种界面文案都会
        混进来。顺带的好处是 ``send()`` 与 :meth:`get_messages` 对同一条消息给出的
        文本完全一致。
        """
        summary = parse_stream(raw)
        messages = self._safe_history()
        source = _pick_assistant(messages, summary.response_message_id)
        if source is not None:
            answer, reasoning = source.answer, source.reasoning
            parent = _question_before(messages, source)
            question = question or (parent.content if parent else "")
        else:
            # 拿不到原文时退回 DOM，但那是渲染后的文本，必须让人知道
            warnings.warn(
                "读取消息原文失败，answer 退回页面渲染后的纯文本（会丢掉 markdown 标记）",
                stacklevel=3,
            )
            text = self._page.last_message()
            answer, reasoning = text.get("answer", ""), text.get("reasoning") or None
            question = question or text.get("question", "")

        return DeepSeekResponse(
            answer=answer,
            reasoning=reasoning,
            question=question,
            session_id=self.id,
            thinking_enabled=self.thinking,
            search_enabled=self.search,
            status=summary.status,
            usage=summary.usage,
            title=summary.title,
            id=summary.response_message_id or getattr(source, "id", None),
            parent_id=getattr(source, "parent_id", None),
            raw=raw,
        )

    def _safe_history(self) -> list[Message]:
        """读历史；读不到就返回空列表，让调用方走 DOM 兜底。"""
        try:
            return self.get_messages()
        except DeepSeekWebError:
            return []

    def __repr__(self) -> str:  # pragma: no cover - 展示用
        return f"DeepSeekSession(id={self.id!r}, thinking={self.thinking}, search={self.search})"
