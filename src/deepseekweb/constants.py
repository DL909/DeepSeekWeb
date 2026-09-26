"""页面地址与选择器。

只依赖 DeepSeek 设计系统的 ``ds-`` 前缀类名和 ``role``/``aria-*`` 属性，
不使用 ``_74c0879`` 这类构建期哈希类名，前端改版时更耐受。
"""

from __future__ import annotations

import os
import re

HOME_URL = "https://chat.deepseek.com/"
SESSION_URL = "https://chat.deepseek.com/a/chat/s/{session_id}"

#: 会话 id 出现在地址栏路径里
SESSION_ID_RE = re.compile(r"/a/chat/s/([0-9a-fA-F-]{8,})")

#: 前端真正发请求的接口，用来判断"这一轮生成结束了"
COMPLETION_API = "/api/v0/chat/completion"

#: 消息容器：一条消息一个 div，用户和助手消息都在里面
MESSAGE = "div.ds-message"
#: 思考过程容器
THINK_CONTENT = "div.ds-think-content"
#: 助手正文容器
ANSWER_CONTENT = "div.ds-assistant-message-main-content"

#: 输入框
INPUT_BOX = "textarea"
#: 登录页两种表单（验证码 / 密码）的输入框都带这个类，用来判断"登录页渲染好了"
LOGIN_INPUT = "input.ds-input__input"
#: 页面就绪判据：聊天页有输入框，登录页有表单输入框
READY_SELECTOR = f"{INPUT_BOX}, {LOGIN_INPUT}"
#: 发送按钮（圆形主按钮），输入为空时带 ds-button--disabled
SEND_BUTTON = 'div[role="button"].ds-button--primary.ds-button--circle'
DISABLED_CLASS = "ds-button--disabled"

#: 开关按钮，"深度思考"/"智能搜索"
TOGGLE_LABELS = {"thinking": "深度思考", "search": "智能搜索"}
TOGGLE_BUTTON = "div.ds-toggle-button"

DEFAULT_TIMEOUT = 180_000  # 单轮问答超时（毫秒）
DEFAULT_READY_TIMEOUT = 45_000  # 等页面就绪
START_GRACE_TIMEOUT = 15_000  # 点发送后多久还没看到请求发出，就换个方式重试
DEFAULT_USER_DATA_DIR = os.path.join(
    os.path.expanduser("~"), ".deepseekweb", "chrome-profile"
)

#: 允许用环境变量直接连上已开着的 Chrome：
#: ``/Applications/Google Chrome.app/Contents/MacOS/Google Chrome \
#:     --remote-debugging-port=9222 --user-data-dir=/path/to/profile``
CDP_URL_ENV = "DEEPSEEKWEB_CDP_URL"

# 在页面里执行的提取脚本：取最后一条消息的思考过程与正文
EXTRACT_LAST_MESSAGE_JS = """
() => {
  const msgs = [...document.querySelectorAll('div.ds-message')];
  const last = msgs[msgs.length - 1];
  if (!last) return null;
  const think = last.querySelector('div.ds-think-content');
  const answer = last.querySelector('div.ds-assistant-message-main-content');
  const prev = msgs[msgs.length - 2];
  return {
    reasoning: think ? (think.innerText || '').trim() : '',
    answer: answer ? (answer.innerText || '').trim() : '',
    question: prev ? (prev.innerText || '').trim() : '',
  };
}
"""

# 正文是否已经渲染出来（生成结束的兜底判据）
ANSWER_READY_JS = """
() => {
  const msgs = [...document.querySelectorAll('div.ds-message')];
  const last = msgs[msgs.length - 1];
  if (!last) return false;
  const answer = last.querySelector('div.ds-assistant-message-main-content');
  return !!(answer && (answer.innerText || '').trim());
}
"""
