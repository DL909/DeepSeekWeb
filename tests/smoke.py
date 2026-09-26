"""端到端冒烟测试：真的连浏览器、真的发消息。

    DEEPSEEKWEB_CDP_URL=http://127.0.0.1:9222 python tests/smoke.py

需要一个已经登录 DeepSeek 的 Chrome（带 --remote-debugging-port 启动）。
"""

from __future__ import annotations

import os
import sys

from deepseekweb import DeepSeekSession, DeepSeekUser

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
        check("关闭 thinking 后无推理内容", second.reasoning == "", repr(second.reasoning[:20]))
        check("第二次回答非空", bool(second.answer), repr(second.answer[:30]))

        # 开关沿用上一次的设置
        third = session.send(input="这次沿用刚才的设置")
        check("未指定时沿用 thinking=False", third.thinking_enabled is False)
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
