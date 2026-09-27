"""端到端冒烟测试：真的连浏览器、真的发消息。

    DEEPSEEKWEB_CDP_URL=http://127.0.0.1:9222 python tests/smoke.py

需要一个已经登录 DeepSeek 的 Chrome（带 --remote-debugging-port 启动）。
"""

from __future__ import annotations

import os
import sys

from deepseekweb import DeepSeekResponse, DeepSeekSession, DeepSeekUser, UserPrompt

CDP = os.environ.get("DEEPSEEKWEB_CDP_URL", "http://127.0.0.1:9222")
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


def main() -> int:
    user = DeepSeekUser(cdp_url=CDP)
    try:
        user.prepare()
        check("连接并确认登录态", user.page.is_logged_in())

        session, response = DeepSeekSession.new_session(
            user=user, input="用一句话介绍你自己", thinking=True
        )
        check("new_session 拿到会话 id", bool(session.id), session.id)
        check("回答非空", bool(response.answer), repr(response.answer[:30]))
        check("思考过程非空", bool(response.reasoning), f"{len(response.reasoning)} 字")
        check("状态 FINISHED", response.status == "FINISHED", str(response.status))
        check("token 用量可读", isinstance(response.usage, int), str(response.usage))
        check("会话标题可读", bool(response.title), str(response.title))
        check("search 始终为 False", response.search_enabled is False)

        second = session.send(input="再补充一句你的能力", thinking=False)
        check("send 复用同一会话", second.session_id == session.id)
        check("关闭 thinking 后无推理内容", second.reasoning is None, repr(second.reasoning))
        check("第二次回答非空", bool(second.answer), repr(second.answer[:30]))

        # 开关沿用上一次的设置
        third = session.send(input="这次沿用刚才的设置")
        check("未指定时沿用 thinking=False", third.thinking_enabled is False)

        # ---- 过往对话 ----
        sessions = user.list_sessions(limit=5)
        check("列出历史会话", len(sessions) == 5, f"{len(sessions)} 条")
        check("会话带标题和链接", all(s.title and s.url for s in sessions), sessions[0].title)
        check("新会话出现在列表里", session.id in {s.id for s in user.list_sessions(limit=20)})

        history = session.get_messages()
        check("三轮问答共 6 条消息", len(history) == 6, f"{len(history)} 条")
        check("第一条是用户提问",
              isinstance(history[0], UserPrompt) and history[0].content == "用一句话介绍你自己")
        check("用户消息带 session_id", history[0].session_id == session.id)
        check("普通提问没有附件", history[0].file == ())
        check("首轮有推理内容",
              isinstance(history[1], DeepSeekResponse) and history[1].reasoning is not None)
        check("关闭思考那轮 reasoning 为 None",
              isinstance(history[3], DeepSeekResponse) and history[3].reasoning is None)
        check("历史里的回答非空",
              all(m.answer for m in history if isinstance(m, DeepSeekResponse)))
        check("历史消息 id 递增", [m.id for m in history] == sorted(m.id for m in history))
        check("读历史不把页面切走", user.page.page.url.startswith("https://chat.deepseek.com"))
        # ---- 正文必须是原文（markdown），不是渲染后的纯文本 ----
        md = session.send(input="用 markdown 给一个加粗短语和一个 python 代码块。")
        check("answer 保留代码围栏", "```" in md.answer, repr(md.answer[:40]))
        check("answer 保留加粗标记", "**" in md.answer)
        check("answer 不含界面文案", "复制" not in md.answer and "下载" not in md.answer)
        check("send 与 get_messages 文本一致",
              [m for m in session.get_messages()
               if isinstance(m, DeepSeekResponse) and m.id == md.id][0].answer == md.answer)
        check("消息 id 与父 id 可关联", md.id is not None and md.parent_id is not None,
              f"id={md.id} parent={md.parent_id}")
    finally:
        user.close()

    print()
    if failures:
        print(f"{len(failures)} 项失败：{', '.join(failures)}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
