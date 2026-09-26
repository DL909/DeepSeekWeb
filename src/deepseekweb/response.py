"""模型回复的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DeepSeekResponse:
    """一轮问答的结果。

    Attributes:
        answer: 正文内容（渲染后的纯文本）。
        reasoning: 思考过程内容；未开启深度思考时为空字符串。
        question: 本轮用户输入。
        session_id: 所属会话 id。
        thinking_enabled / search_enabled: 本轮实际下发的开关状态。
        status: 前端上报的结束状态，正常为 ``FINISHED``。
        usage: 本轮累计 token 数（若能从接口流里读到）。
        title: DeepSeek 自动生成的会话标题（若接口下发）。
        raw: ``/api/v0/chat/completion`` 的原始 SSE 文本，便于调试。
    """

    answer: str
    reasoning: str = ""
    question: str = ""
    session_id: str | None = None
    thinking_enabled: bool = False
    search_enabled: bool = False
    status: str | None = None
    usage: int | None = None
    title: str | None = None
    raw: str | None = field(default=None, repr=False)

    def __str__(self) -> str:  # pragma: no cover - 展示用
        return self.answer

    def __repr__(self) -> str:
        return (
            f"DeepSeekResponse(answer={self.answer[:40]!r}, "
            f"reasoning_len={len(self.reasoning)}, status={self.status!r})"
        )
