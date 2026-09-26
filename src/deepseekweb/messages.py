"""消息数据类型。

一轮问答由两种消息交替组成：用户发出去的 :class:`UserPrompt`，
和 DeepSeek 回的 :class:`DeepSeekResponse`。
"""

from __future__ import annotations

from dataclasses import dataclass

from .response import DeepSeekResponse

#: 用户消息里可能带附件的字段名（v0.1 不支持文件，只用于识别出来好让调用方自己报不支持）
FILE_KEYS = ("attachments", "files", "file_ids", "ref_file_ids")


@dataclass
class UserPrompt:
    """用户发出的一条提问。

    Attributes:
        content: 问题正文。
        file: 附件。v0.1 不支持文件，正常情况下是空元组；
            一旦 DeepSeek 返回了附件，这里会非空，调用方据此自行拒绝处理。
        id: 服务端的消息 id。
        parent_id: 父消息 id，串起对话的树。
        inserted_at: 创建时间（Unix 时间戳）。
        session_id: 所属会话 id。
    """

    content: str
    file: tuple = ()
    id: int | None = None
    parent_id: int | None = None
    inserted_at: float | None = None
    session_id: str | None = None

    @property
    def has_file(self) -> bool:
        return bool(self.file)

    def __str__(self) -> str:  # pragma: no cover - 展示用
        return self.content


#: 会话里一条消息的联合类型
Message = UserPrompt | DeepSeekResponse


def extract_files(fragment: dict) -> tuple:
    """从用户消息的 fragment 里把附件摘出来（v0.1 暂不支持，识别出来即可）。"""
    files: list = []
    for key in FILE_KEYS:
        value = fragment.get(key)
        if not value:
            continue
        if isinstance(value, list):
            files.extend(value)
        else:
            files.append(value)
    return tuple(files)
