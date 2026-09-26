"""历史消息解析的单元测试：不需要浏览器。

    python tests/test_history.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from deepseekweb.exceptions import DeepSeekWebError  # noqa: E402
from deepseekweb.history import parse_messages, parse_sessions  # noqa: E402
from deepseekweb.messages import UserPrompt, extract_files  # noqa: E402
from deepseekweb.response import DeepSeekResponse  # noqa: E402

results: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    results.append(ok)


def envelope(messages: list[dict], current: int | None = None, session: dict | None = None) -> dict:
    return {
        "code": 0,
        "msg": "",
        "data": {
            "biz_code": 0,
            "biz_msg": "",
            "biz_data": {
                "chat_session": {"id": "sess-1", "current_message_id": current, **(session or {})},
                "chat_messages": messages,
                "cache_control": "REPLACE",
            },
        },
    }


def user(mid: int, parent: int | None, text: str) -> dict:
    return {
        "message_id": mid,
        "parent_id": parent,
        "role": "USER",
        "status": "FINISHED",
        "inserted_at": 1790425374.0 + mid,
        "fragments": [{"id": mid, "type": "REQUEST", "content": text}],
    }


def assistant(
    mid: int, parent: int | None, answer: str, think: str | None = None
) -> dict:
    frags = []
    if think is not None:
        frags.append({"id": mid * 10, "type": "THINK", "content": think})
    frags.append({"id": mid * 10 + 1, "type": "RESPONSE", "content": answer})
    frags.append({"id": mid * 10 + 2, "type": "TIP", "content": "本回答由 AI 生成"})
    return {
        "message_id": mid,
        "parent_id": parent,
        "role": "ASSISTANT",
        "status": "FINISHED",
        "thinking_enabled": think is not None,
        "search_enabled": False,
        "accumulated_token_usage": 42,
        "inserted_at": 1790425375.0 + mid,
        "fragments": frags,
    }


def main() -> int:
    # 1) 正常链：问题/回答交替
    msgs = [
        user(1, None, "用一句话介绍你自己"),
        assistant(2, 1, "我是 DeepSeek。", think="用户要一句话，简洁"),
        user(3, 2, "再补充一句"),
        assistant(4, 3, "我能帮你写作和编程。"),
    ]
    parsed = parse_messages(envelope(msgs, current=4))
    check("条数正确", len(parsed) == 4, str(len(parsed)))
    check("类型交替", [type(m).__name__ for m in parsed] ==
          ["UserPrompt", "DeepSeekResponse", "UserPrompt", "DeepSeekResponse"])
    check("首条是问题", parsed[0].content == "用一句话介绍你自己")
    check("有 THINK 时 reasoning 有内容", parsed[1].reasoning == "用户要一句话，简洁")
    check("无 THINK 时 reasoning 是 None", parsed[3].reasoning is None, repr(parsed[3].reasoning))
    check("TIP 不混进正文", parsed[1].answer == "我是 DeepSeek。", parsed[1].answer)
    check("回答带上开关与用量", parsed[1].thinking_enabled is True and parsed[1].usage == 42)
    check("session_id 落到每条上", all(m.session_id == "sess-1" for m in parsed))
    check("消息 id 与父 id 保留", parsed[2].id == 3 and parsed[2].parent_id == 2)

    # 2) 重新生成产生的分叉：只走当前分支
    branched = [
        user(1, None, "问题"),
        assistant(2, 1, "第一次生成", think="旧思路"),
        assistant(3, 1, "第二次生成"),  # 同一父节点 = 重新生成
        assistant(4, 3, "追问你一句的回复"),
    ]
    parsed = parse_messages(envelope(branched, current=4))
    answers = [m.answer for m in parsed if isinstance(m, DeepSeekResponse)]
    check("分叉只保留当前分支", answers == ["第二次生成", "追问你一句的回复"], str(answers))
    check("旧分支的思考不出现", all(m.reasoning is None for m in parsed if isinstance(m, DeepSeekResponse)))

    # 3) 没有 current_message_id 时退化成按 id 排序
    parsed = parse_messages(envelope([user(2, 1, "b"), assistant(1, None, "a", think="t")], current=None))
    check("缺 current_message_id 不崩且按 id 排序", len(parsed) == 2 and parsed[0].answer == "a")

    # 4) 空会话 / 异常响应
    check("空消息返回空列表", parse_messages(envelope([], current=None)) == [])
    try:
        parse_messages({"code": 40003, "msg": "INVALID_TOKEN", "data": None})
        check("错误码会抛异常", False)
    except DeepSeekWebError as exc:
        check("错误码会抛异常", "INVALID_TOKEN" in str(exc), str(exc))

    # 5) 附件识别
    frag = {"type": "REQUEST", "content": "看这个", "attachments": [{"id": 1}]}
    check("能认出附件", extract_files(frag) == ({"id": 1},))
    check("没附件时是空元组", extract_files({"type": "REQUEST", "content": "x"}) == ())
    with_file = parse_messages(envelope([{**user(1, None, "看这个"), "fragments": [frag]}], current=1))
    check("带附件的提问 file 非空", with_file[0].has_file is True)
    check("普通提问 file 为空", parse_messages(envelope([user(1, None, "你好")], current=1))[0].file == ())

    # 6) 会话列表
    payload = {
        "code": 0, "data": {"biz_code": 0, "biz_data": {"chat_sessions": [
            {"id": "a", "title": "初次问候", "updated_at": 1790425398.5, "pinned": True,
             "model_type": "default", "current_message_id": 2},
        ], "has_more": True}},
    }
    sessions, more = parse_sessions(payload)
    check("会话列表解析", len(sessions) == 1 and sessions[0].title == "初次问候" and sessions[0].pinned)
    check("has_more 透传", more is True)
    check("会话 url 可拼", sessions[0].url.endswith("/a/chat/s/a"), sessions[0].url)

    print()
    failed = results.count(False)
    if failed:
        print(f"{failed} 项失败")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
