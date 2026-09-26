"""解析 ``/api/v0/chat/completion`` 返回的 SSE 文本。

事件形如::

    event: ready
    data: {"request_message_id":1,"response_message_id":2}

    data: {"v":{"response":{"status":"WIP","fragments":[...]}}}

    data: {"v":"增量文本"}

    data: {"p":"response/status","o":"SET","v":"FINISHED"}

只需要从中取出结束状态、token 用量和会话标题，失败时静默返回空结果。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class StreamSummary:
    """SSE 里对调用方有用的那几个字段。"""

    status: str | None = None
    usage: int | None = None
    title: str | None = None
    response_message_id: int | None = None
    request_message_id: int | None = None


def _iter_events(raw: str):
    """把 SSE 文本切成 ``(event, data)`` 二元组。"""
    for block in raw.split("\n\n"):
        name = None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                payload = line[len("data:") :].strip()
                if payload:
                    yield name, payload


def parse_stream(raw: str | None) -> StreamSummary:
    """尽力解析 SSE，解析不了的部分直接忽略。"""
    summary = StreamSummary()
    if not raw:
        return summary

    for name, payload in _iter_events(raw):
        try:
            data: Any = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue

        if name == "title" and isinstance(data.get("content"), str):
            summary.title = data["content"]
            continue

        if isinstance(data.get("request_message_id"), int):
            summary.request_message_id = data["request_message_id"]
        if isinstance(data.get("response_message_id"), int):
            summary.response_message_id = data["response_message_id"]

        # 完整快照：{"v": {"response": {...}}}
        value = data.get("v")
        if isinstance(value, dict) and isinstance(value.get("response"), dict):
            response = value["response"]
            if response.get("status"):
                summary.status = response["status"]
            if isinstance(response.get("accumulated_token_usage"), int):
                summary.usage = response["accumulated_token_usage"]

        # 增量补丁：{"p": "response/status", "o": "SET", "v": "FINISHED"}
        path = data.get("p")
        value = data.get("v")
        if path == "response/status" and isinstance(value, str):
            summary.status = value
        elif path == "response" and data.get("o") == "BATCH" and isinstance(value, list):
            for patch in value:
                if isinstance(patch, dict):
                    if patch.get("p") == "accumulated_token_usage" and isinstance(
                        patch.get("v"), int
                    ):
                        summary.usage = patch["v"]
                    elif patch.get("p") == "quasi_status" and isinstance(patch.get("v"), str):
                        summary.status = patch["v"]
        elif isinstance(path, str) and path.startswith("response/") and isinstance(value, int):
            if path.endswith("accumulated_token_usage"):
                summary.usage = value

    return summary
