"""最小可跑的例子。

    python examples/quickstart.py

需要一个已经登录 DeepSeek 的 Chrome。如果开了 --remote-debugging-port，
设一下 DEEPSEEKWEB_CDP_URL 就能直接用；否则本库会自己拉一个浏览器，
账号密码从环境变量 DSW_ACCOUNT / DSW_PASSWD 读（别写进代码里）。
"""

from __future__ import annotations

import os

from deepseekweb import DeepSeekSession, DeepSeekUser

user = DeepSeekUser(
    account=os.environ.get("DSW_ACCOUNT"),
    passwd=os.environ.get("DSW_PASSWD"),
    cdp_url=os.environ.get("DEEPSEEKWEB_CDP_URL"),
)

try:
    session, response = DeepSeekSession.new_session(
        user=user, input="hello", thinking=True
    )
    print("会话:", session.id)
    print("--- 推理 ---")
    print(response.reasoning)
    print("--- 回答 ---")
    print(response.answer)

    another = session.send(input="introduce your self.", thinking=True)
    print("--- 追问 ---")
    print(another.answer)
finally:
    user.close()
