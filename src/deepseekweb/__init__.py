"""deepseek-web：把 DeepSeek 网页端当成一个可调用的程序接口。

    from deepseekweb import DeepSeekUser, DeepSeekSession

    user = DeepSeekUser(account="13511112222", passwd="qwerty")

    session, response = DeepSeekSession.new_session(user=user, input="hello")
    print(response.reasoning)   # 推理内容
    print(response.answer)      # 回答内容

    another = session.send(input="introduce your self.", thinking=True)

过往对话也能读：

    for info in user.list_sessions(limit=10):     # 最近 10 个会话
        print(info.id, info.title)

    for message in session.get_messages():         # 某个会话的完整对话
        print(message)

浏览器可以直接用已经在跑的 Chrome（``cdp_url="http://127.0.0.1:9222"``），
也可以让本库自己拉起一个带持久化 profile 的浏览器。
"""

from __future__ import annotations

import argparse
import importlib.metadata
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
from .history import SessionInfo
from .messages import Message, UserPrompt
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
    "Message",
    "ResponseTimeout",
    "SessionInfo",
    "UserPrompt",
    "main",
]

# 版本号只有 pyproject.toml 一个来源，避免和发布出去的元数据对不上
try:
    __version__ = importlib.metadata.version("deepseekweb")
except importlib.metadata.PackageNotFoundError:  # 源码目录里直接跑，没装成包
    __version__ = "0.0.0.dev0"


def main(argv: Sequence[str] | None = None) -> int:
    """``deepseekweb`` —— 命令行问一句、列会话、看历史。"""
    parser = argparse.ArgumentParser(
        prog="deepseekweb", description="问 DeepSeek，或翻它的历史"
    )
    parser.add_argument("prompt", nargs="?", default=None, help="要问的内容")
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
    parser.add_argument(
        "--list-sessions", type=int, metavar="N", default=None, help="列出最近 N 个会话后退出"
    )
    parser.add_argument("--history", action="store_true", help="打印 --session 的历史对话")
    args = parser.parse_args(argv)

    if args.history and not args.session:
        print("--history 需要配合 --session 使用", file=sys.stderr)
        return 1
    if not args.prompt and args.list_sessions is None and not args.history:
        parser.print_help()
        return 1

    user = DeepSeekUser(
        account=args.account,
        passwd=args.passwd,
        cdp_url=args.cdp,
        timeout=DEFAULT_TIMEOUT,
    )
    try:
        if args.list_sessions is not None:
            for info in user.list_sessions(limit=args.list_sessions or None):
                print(f"{info.id}\t{info.title}")
            return 0

        if args.history:
            session = user.get_session(args.session)
            for message in session.get_messages():
                if isinstance(message, UserPrompt):
                    print(f"问> {message.content}")
                else:
                    if message.reasoning is not None and args.reasoning:
                        print(f"想> {message.reasoning}")
                    print(f"答> {message.answer}")
                print()
            return 0

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

    if args.reasoning and response.reasoning is not None:
        print("--- 推理 ---", file=sys.stderr)
        print(response.reasoning, file=sys.stderr)
    print(response.answer)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
