"""获取对话的历史信息

    python examples/previous_messages.py <会话id>

不传 id 就先列出最近 10 个会话，照着挑一个。也可以用环境变量
DEEPSEEKWEB_SESSION_ID 代替命令行参数。

需要一个已经登录 DeepSeek 的 Chrome。如果开了 --remote-debugging-port，
设一下 DEEPSEEKWEB_CDP_URL 就能直接用；否则本库会自己拉一个浏览器，
账号密码从环境变量 DSW_ACCOUNT / DSW_PASSWD 读（别写进代码里）。
"""

from __future__ import annotations

import os
import sys

from deepseekweb import DeepSeekSession, DeepSeekUser, UserPrompt
from deepseekweb.response import DeepSeekResponse

user = DeepSeekUser(
    account=os.environ.get("DSW_ACCOUNT"),
    passwd=os.environ.get("DSW_PASSWD"),
    cdp_url=os.environ.get("DEEPSEEKWEB_CDP_URL"),
)

id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DEEPSEEKWEB_SESSION_ID")

try:
    if not id:
        print("没指定会话 id，先列出最近 10 个：\n")
        for info in user.list_sessions(limit=10):
            print(f"{info.id}  {info.title}")
        print("\n用法：python examples/previous_messages.py <上面某个 id>")
        sys.exit(0)

    session = DeepSeekSession(user=user, id=id)

    for message in (
        session.get_messages()
    ):  # 在DeepSeekSession上调用get_messages返回Sequence[UserPrompt|DeepSeekResponse]
        if isinstance(message, UserPrompt):
            if len(message.file):
                raise NotImplementedError()
            print("===问题===\n")
            print(message.content)
        elif isinstance(message, DeepSeekResponse):
            if message.reasoning is not None:
                print("===思考===\n")
                print(message.reasoning)
            print("===回答===\n")
            print(message.answer)

finally:
    user.close()
