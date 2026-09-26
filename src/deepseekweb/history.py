"""读取过往对话。

直接调 DeepSeek 自己的两个接口，而不是去 DOM 里刨：

- ``GET /api/v0/chat/history_messages?chat_session_id=...`` —— 某个会话的完整消息
- ``GET /api/v0/chat_session/fetch_page`` —— 会话列表

这里有个坑值得记一笔：``history_messages`` 支持 ``cache_version`` 参数，
浏览器本地缓存着这个会话时，服务端只回**增量**（``cache_control: MERGE``），
差的那几条要靠前端自己从 IndexedDB 里补上。**不带这个参数调用会拿到全量**
（``REPLACE``），所以下面一律不带，免得读到半截历史。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .constants import HISTORY_API, SESSIONS_API
from .exceptions import DeepSeekWebError
from .messages import Message, UserPrompt, extract_files
from .response import DeepSeekResponse

_ROLE_USER = "USER"
_ROLE_ASSISTANT = "ASSISTANT"
_FRAG_REQUEST = "REQUEST"
_FRAG_THINK = "THINK"
_FRAG_RESPONSE = "RESPONSE"


@dataclass
class SessionInfo:
    """一条历史会话的摘要。"""

    id: str
    title: str
    updated_at: float | None = None
    inserted_at: float | None = None
    pinned: bool = False
    model_type: str | None = None
    current_message_id: int | None = None
    is_empty: bool = False

    @property
    def url(self) -> str:
        return f"https://chat.deepseek.com/a/chat/s/{self.id}"

    def __repr__(self) -> str:  # pragma: no cover - 展示用
        return f"SessionInfo(id={self.id!r}, title={self.title!r})"


def _biz_data(payload: dict, what: str) -> dict:
    """从 ``{code, msg, data:{biz_code, biz_msg, biz_data}}`` 里取出业务数据。"""
    if not isinstance(payload, dict):
        raise DeepSeekWebError(f"{what} 返回了非 JSON 内容")
    if payload.get("code") != 0:
        raise DeepSeekWebError(f"{what} 失败：code={payload.get('code')} msg={payload.get('msg')}")
    data = payload.get("data") or {}
    if data.get("biz_code") not in (0, None):
        raise DeepSeekWebError(
            f"{what} 失败：biz_code={data.get('biz_code')} biz_msg={data.get('biz_msg')}"
        )
    return data.get("biz_data") or {}


def parse_messages(payload: dict, session_id: str | None = None) -> list[Message]:
    """把 ``history_messages`` 的响应解析成 :class:`UserPrompt` / :class:`DeepSeekResponse` 列表。

    消息在服务端是一棵树（``parent_id`` 指上一条，重新生成会分叉）。
    这里从 ``current_message_id`` 沿父指针回溯到根，得到当前这条分支的完整对话，
    顺序即对话顺序；被放弃的旧分支不会混进来。
    """
    biz = _biz_data(payload, "读取历史消息")
    session = biz.get("chat_session") or {}
    session_id = session_id or session.get("id")
    raw_messages = biz.get("chat_messages") or []
    if not raw_messages:
        return []

    by_id = {m.get("message_id"): m for m in raw_messages if m.get("message_id") is not None}
    chain: list[dict] = []
    leaf = session.get("current_message_id")
    if leaf in by_id:
        cursor: dict | None = by_id[leaf]
        while cursor is not None:
            chain.append(cursor)
            parent = cursor.get("parent_id")
            cursor = by_id.get(parent) if parent is not None else None
        chain.reverse()
    else:  # 服务端没给当前叶子节点，退化成按 id 排序
        chain = sorted(raw_messages, key=lambda m: m.get("message_id") or 0)

    return [_build_message(m, session_id) for m in chain]


def _build_message(raw: dict, session_id: str | None) -> Message:
    fragments = raw.get("fragments") or []
    if raw.get("role") == _ROLE_USER:
        request = next((f for f in fragments if f.get("type") == _FRAG_REQUEST), None)
        if request is None:  # 纯文件消息之类的边角情况，退化成整条文本
            content = "".join(f.get("content") or "" for f in fragments)
            request = {"content": content}
        return UserPrompt(
            content=request.get("content") or "",
            file=extract_files(request),
            id=raw.get("message_id"),
            parent_id=raw.get("parent_id"),
            inserted_at=raw.get("inserted_at"),
            session_id=session_id,
        )

    think = next((f for f in fragments if f.get("type") == _FRAG_THINK), None)
    answer = "".join(f.get("content") or "" for f in fragments if f.get("type") == _FRAG_RESPONSE)
    reasoning = (think.get("content") or "") if think else None
    return DeepSeekResponse(
        answer=answer,
        reasoning=reasoning or None,
        question="",
        session_id=session_id,
        thinking_enabled=bool(raw.get("thinking_enabled")),
        search_enabled=bool(raw.get("search_enabled")),
        status=raw.get("status"),
        usage=raw.get("accumulated_token_usage"),
        id=raw.get("message_id"),
        parent_id=raw.get("parent_id"),
        inserted_at=raw.get("inserted_at"),
    )


def parse_sessions(payload: dict) -> tuple[list[SessionInfo], bool]:
    """解析会话列表，返回 ``(会话列表, 是否还有更多)``。"""
    biz = _biz_data(payload, "读取会话列表")
    sessions = [
        SessionInfo(
            id=s.get("id", ""),
            title=s.get("title") or "",
            updated_at=s.get("updated_at"),
            inserted_at=s.get("inserted_at"),
            pinned=bool(s.get("pinned")),
            model_type=s.get("model_type"),
            current_message_id=s.get("current_message_id"),
            is_empty=bool(s.get("is_empty")),
        )
        for s in (biz.get("chat_sessions") or [])
        if s.get("id")
    ]
    return sessions, bool(biz.get("has_more"))


def merge_text(fragments: list[dict], kind: str) -> str:  # pragma: no cover - 备用
    return "".join(f.get("content") or "" for f in fragments if f.get("type") == kind)


__all__: list[Any] = [
    "HISTORY_API",
    "SESSIONS_API",
    "Message",
    "SessionInfo",
    "UserPrompt",
    "parse_messages",
    "parse_sessions",
]
