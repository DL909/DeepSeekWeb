"""deepseekweb 的异常定义。"""

from __future__ import annotations


class DeepSeekWebError(Exception):
    """本库所有异常的基类。"""


class BrowserError(DeepSeekWebError):
    """浏览器连接/启动失败。"""


class LoginRequired(DeepSeekWebError):
    """浏览器里没有有效的 DeepSeek 登录态。"""


class ElementNotFound(DeepSeekWebError):
    """页面上找不到预期的元素，通常意味着 DeepSeek 前端改版了。"""


class ResponseTimeout(DeepSeekWebError):
    """等待模型回复超时。"""


class GenerationFailed(DeepSeekWebError):
    """请求被中断或以失败告终（例如用户主动停止、页面报错）。"""
