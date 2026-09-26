"""自动登录 DeepSeek。

DeepSeek 的登录页默认是短信验证码，密码登录在"密码登录"标签页里。
如果登录过程中冒出验证码（hCaptcha），本库不会去破解它——浏览器窗口是可见的，
请手动点一下，:meth:`login` 会继续等着。
"""

from __future__ import annotations

import time

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from .constants import HOME_URL
from .exceptions import LoginRequired

PASSWORD_TAB = 'div.ds-button:has-text("密码登录")'
ACCOUNT_INPUT = 'input[placeholder="请输入手机号/邮箱地址"]'
PASSWORD_INPUT = 'input[placeholder="请输入密码"]'
SUBMIT_BUTTON = 'div.ds-button--primary.ds-button--filled:has-text("登录")'

_ERROR_TEXT_JS = """
() => {
  const candidates = [
    ...document.querySelectorAll('[role="alert"], [class*="error"], [class*="Error"], .ds-form-item-explain'),
  ];
  for (const el of candidates) {
    const text = (el.innerText || '').trim();
    if (text && text.length < 80) return text;
  }
  return '';
}
"""


def is_signed_in(page: Page) -> bool:
    """判断当前页面是否处于登录态。

    未登录时首页会跳到 ``/sign_in``，且 ``localStorage.userToken`` 里没有 token。
    """
    try:
        path = page.evaluate("() => location.pathname")
        if path and path.startswith("/sign_in"):
            return False
        token = page.evaluate(
            """() => {
                const raw = localStorage.getItem('userToken');
                if (!raw) return '';
                try {
                    const parsed = JSON.parse(raw);
                    const value = parsed && 'value' in parsed ? parsed.value : parsed;
                    return value == null ? '' : String(value);
                } catch (e) {
                    return raw;
                }
            }"""
        )
        return bool(token) and len(token) > 8
    except Exception:
        return False


def error_text(page: Page) -> str:
    """抓取登录页上的错误提示，便于把失败原因报给调用方。"""
    try:
        return page.evaluate(_ERROR_TEXT_JS)
    except Exception:
        return ""


def login(page: Page, account: str, passwd: str, timeout: int = 90_000) -> bool:
    """用账号密码登录，成功返回 ``True``。

    已经登录时直接返回 ``True``。超时未登录成功则抛 :class:`LoginRequired`，
    提示里会带上页面上看到的错误信息。
    """
    if is_signed_in(page):
        return True

    page.goto(HOME_URL, wait_until="domcontentloaded")
    if is_signed_in(page):
        return True

    # 切到密码登录标签
    try:
        tab = page.locator(PASSWORD_TAB).first
        if tab.count() and tab.is_visible():
            tab.click(timeout=10_000)
    except (PlaywrightTimeout, Exception):
        pass  # 已经是密码表单，或者结构变了，交给下面找输入框时报错

    account_input = page.locator(ACCOUNT_INPUT).first
    password_input = page.locator(PASSWORD_INPUT).first
    try:
        account_input.wait_for(state="visible", timeout=15_000)
        password_input.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeout as exc:
        raise LoginRequired(
            "没找到登录表单（可能是 DeepSeek 登录页改版，或需要先手动登录一次）。"
        ) from exc

    account_input.fill(account)
    password_input.fill(passwd)
    page.locator(SUBMIT_BUTTON).first.click(timeout=10_000)

    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        if is_signed_in(page):
            return True
        page.wait_for_timeout(1000)

    raise LoginRequired(
        "登录超时，浏览器窗口仍然开着——请在里面完成登录"
        "（例如拖动验证码滑块），之后重新调用即可。"
        + (f" 页面提示：{error_text(page)}" if error_text(page) else "")
    )
