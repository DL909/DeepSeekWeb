"""模型回复的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DeepSeekResponse:
    """一轮问答里 DeepSeek 的回复。

    Attributes:
        answer: 正文内容。
        reasoning: 思考过程；**没有思考过程时是 ``None``**（不是空串），
            所以判断要写 ``if response.reasoning is not None``。
        question: 本轮用户输入；从历史里读出来时为空。
        session_id: 所属会话 id。
        thinking_enabled / search_enabled: 本轮实际下发的开关状态。
        status: 服务端记录的结束状态，正常为 ``FINISHED``。
        usage: 本轮累计 token 数。
        title: DeepSeek 自动生成的会话标题（仅新建会话那轮有）。
        id / parent_id: 服务端消息 id 与父消息 id，串起对话的树。
        inserted_at: 创建时间（Unix 时间戳）。
        raw: ``/api/v0/chat/completion`` 的原始 SSE 文本，便于调试。
    """

    answer: str
    reasoning: str | None = None
    question: str = ""
    session_id: str | None = None
    thinking_enabled: bool = False
    search_enabled: bool = False
    status: str | None = None
    usage: int | None = None
    title: str | None = None
    id: int | None = None
    parent_id: int | None = None
    inserted_at: float | None = None
    raw: str | None = field(default=None, repr=False)

    def __str__(self) -> str:  # pragma: no cover - 展示用
        return self.answer

    def __repr__(self) -> str:
        return (
            f"DeepSeekResponse(answer={self.answer[:40]!r}, "
            f"reasoning_len={len(self.reasoning or '')}, status={self.status!r})"
        )
