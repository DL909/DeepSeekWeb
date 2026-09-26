"""deepseek-web：把 DeepSeek 网页端当成一个可调用的程序接口。

    from deepseekweb import DeepSeekUser, DeepSeekSession

    user = DeepSeekUser(account="13511112222", passwd="qwerty")

    session, response = DeepSeekSession.new_session(user=user, input="hello")
    print(response.reasoning)   # 推理内容
    print(response.answer)      # 回答内容

    another = session.send(input="introduce your self.", thinking=True)

浏览器可以直接用已经在跑的 Chrome（``cdp_url="http://127.0.0.1:9222"``），
也可以让本库自己拉起一个带持久化 profile 的浏览器。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .browser import DeepSeekBrowser
from .constants import DEFAULT_TIMEOUT
from .exceptions import (
    BrowserError,
    DeepSeekWebError,
    ElementNotFound,
    GenerationFailed,
    LoginRequired,
    ResponseTimeout,
)
from .page import ChatPage
from .response import DeepSeekResponse
from .session import DeepSeekSession
from .user import DeepSeekUser

__all__ = [
    "BrowserError",
    "ChatPage",
    "DeepSeekBrowser",
    "DeepSeekResponse",
    "DeepSeekSession",
    "DeepSeekUser",
    "DeepSeekWebError",
    "ElementNotFound",
    "GenerationFailed",
    "LoginRequired",
    "ResponseTimeout",
    "main",
]

__version__ = "0.1.0"


def main(argv: Sequence[str] | None = None) -> int:
    """``deepseekweb "问点什么"`` —— 命令行问一句。"""
    parser = argparse.ArgumentParser(
        prog="deepseekweb", description="问 DeepSeek 一句话"
    )
    parser.add_argument("prompt", help="要问的内容")
    parser.add_argument(
        "--account", default=None, help="手机号或邮箱（浏览器已登录时可省）"
    )
    parser.add_argument("--passwd", default=None, help="密码（同上）")
    parser.add_argument(
        "--cdp", default=None, help="附着到已打开的 Chrome，如 http://127.0.0.1:9222"
    )
    parser.add_argument("--session", default=None, help="复用已有会话 id")
    parser.add_argument("--no-thinking", action="store_true", help="关闭深度思考")
    parser.add_argument("--reasoning", action="store_true", help="一并打印推理内容")
    args = parser.parse_args(argv)

    user = DeepSeekUser(
        account=args.account,
        passwd=args.passwd,
        cdp_url=args.cdp,
        timeout=DEFAULT_TIMEOUT,
    )
    try:
        if args.session:
            session = DeepSeekSession(
                user=user, id=args.session, thinking=not args.no_thinking
            )
            response = session.send(args.prompt)
        else:
            session, response = DeepSeekSession.new_session(
                user=user, input=args.prompt, thinking=not args.no_thinking
            )
    except DeepSeekWebError as exc:
        print(f"出错了：{exc}", file=sys.stderr)
        return 1
    finally:
        user.close()

    if args.reasoning and response.reasoning:
        print("--- 推理 ---", file=sys.stderr)
        print(response.reasoning, file=sys.stderr)
    print(response.answer)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
