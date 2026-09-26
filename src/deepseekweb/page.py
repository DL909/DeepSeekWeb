"""对 DeepSeek 单个页面的一切底层操作。

这一层只关心 DOM 与网络事件，不涉及"会话""用户"这些概念。
"""

from __future__ import annotations

import re
import time
from contextlib import contextmanager
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from .constants import (
    ANSWER_READY_JS,
    API_FETCH_JS,
    CHAT_ORIGIN,
    COMPLETION_API,
    DEFAULT_TIMEOUT,
    DISABLED_CLASS,
    EXTRACT_LAST_MESSAGE_JS,
    HISTORY_API,
    HOME_URL,
    INPUT_BOX,
    READY_SELECTOR,
    SEND_BUTTON,
    SESSIONS_API,
    SESSION_ID_RE,
    SESSION_URL,
    START_GRACE_TIMEOUT,
    TOKEN_JS,
    TOGGLE_BUTTON,
    TOGGLE_LABELS,
)
from .exceptions import (
    ElementNotFound,
    GenerationFailed,
    LoginRequired,
    ResponseTimeout,
)
from .login import is_signed_in


class ChatPage:
    """把 Playwright 的 Page 包成 DeepSeek 会话页的操作集合。"""

    def __init__(self, page: Page, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.page = page
        self.timeout = timeout

    # ------------------------------------------------------------------ 导航

    def open_home(self) -> None:
        self.page.goto(HOME_URL, wait_until="domcontentloaded")
        self._wait_ready()

    def open_session(self, session_id: str) -> None:
        self.page.goto(SESSION_URL.format(session_id=session_id), wait_until="domcontentloaded")
        self._wait_ready()

    def current_session_id(self) -> str | None:
        match = SESSION_ID_RE.search(self.page.url)
        return match.group(1) if match else None

    def is_logged_in(self) -> bool:
        return is_signed_in(self.page)

    def require_login(self) -> None:
        if not self.is_logged_in():
            raise LoginRequired(
                "当前浏览器没有 DeepSeek 登录态。请在该 Chrome 窗口里登录一次"
                "（登录态会随 user-data-dir 保留），或改用 account/passwd 自动登录。"
            )

    def _wait_ready(self) -> None:
        """等页面就绪：要么是聊天页的输入框，要么是登录页的密码框。"""
        try:
            self.page.wait_for_selector(READY_SELECTOR, timeout=self.timeout)
        except PlaywrightTimeout as exc:
            raise ElementNotFound(
                f"页面上找不到输入框，DeepSeek 前端可能改版了：{self.page.url}"
            ) from exc

    # ------------------------------------------------------------------ 开关

    def _find_toggle(self, name: str):
        label = TOGGLE_LABELS[name]
        toggles = self.page.locator(TOGGLE_BUTTON)
        for index in range(toggles.count()):
            item = toggles.nth(index)
            try:
                if label in (item.inner_text(timeout=2_000) or ""):
                    return item
            except PlaywrightError:
                continue
        return None

    def get_toggle(self, name: str) -> bool:
        """读取"深度思考"/"智能搜索"的开关状态。"""
        toggle = self._find_toggle(name)
        if toggle is None:
            raise ElementNotFound(f"找不到开关：{TOGGLE_LABELS[name]}")
        return toggle.get_attribute("aria-pressed") == "true"

    def set_toggle(self, name: str, value: bool) -> bool:
        """把开关拨到指定状态，返回最终状态。"""
        toggle = self._find_toggle(name)
        if toggle is None:
            raise ElementNotFound(f"找不到开关：{TOGGLE_LABELS[name]}")
        if self.get_toggle(name) != value:
            toggle.click()
            self._wait_toggle(name, value)
        return self.get_toggle(name)

    def _wait_toggle(self, name: str, value: bool, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.get_toggle(name) == value:
                    return
            except ElementNotFound:
                pass
            self.page.wait_for_timeout(100)
        raise ElementNotFound(f"开关 {TOGGLE_LABELS[name]} 没能拨到 {value}")

    # ------------------------------------------------------------------ 发送

    def send(self, text: str, timeout: int | None = None) -> str | None:
        """输入并发送一条消息，等到本轮生成结束。

        返回 ``/api/v0/chat/completion`` 的原始 SSE 文本（拿不到时为 ``None``）。
        """
        timeout = timeout or self.timeout
        composer = self.page.locator(INPUT_BOX).first
        composer.wait_for(state="visible", timeout=timeout)
        composer.click()
        composer.fill(text)
        self._wait_send_ready(timeout=10_000)

        raw = self._click_and_wait(timeout=timeout)
        if raw is None:
            # 有些情况下按钮点击会被吞掉，补一次回车
            raw = self._press_enter_and_wait(timeout=timeout)
        return raw

    def _send_button(self):
        return self.page.locator(f"{SEND_BUTTON}:not(.{DISABLED_CLASS})").first

    def _wait_send_ready(self, timeout: int) -> None:
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            button = self.page.locator(SEND_BUTTON).first
            if button.count() and DISABLED_CLASS not in (
                button.get_attribute("class") or ""
            ):
                return
            self.page.wait_for_timeout(100)
        raise ElementNotFound("发送按钮一直是禁用状态")

    def _click_and_wait(self, timeout: int) -> str | None:
        with self._watch_completion() as state:
            try:
                self._send_button().click(timeout=10_000)
            except PlaywrightError:
                return None
            return self._wait_generation(state, timeout)

    def _press_enter_and_wait(self, timeout: int) -> str | None:
        with self._watch_completion() as state:
            self.page.locator(INPUT_BOX).first.press("Enter")
            return self._wait_generation(state, timeout)

    @contextmanager
    def _watch_completion(self):
        """盯住 ``/api/v0/chat/completion`` 这一次请求。

        监听器必须在点击发送**之前**挂上，否则极快的回复可能在挂好之前就结束了。
        """
        state: dict[str, Any] = {"response": None, "done": False, "failed": None, "seen": 0}
        marker = re.compile(re.escape(COMPLETION_API))

        def matches(url: str) -> bool:
            return bool(marker.search(url))

        def on_response(response: Any) -> None:
            if matches(response.url):
                state["response"] = response

        def on_request(request: Any) -> None:
            if matches(request.url):
                state["seen"] += 1

        def on_finished(request: Any) -> None:
            if matches(request.url):
                state["done"] = True

        def on_failed(request: Any) -> None:
            if matches(request.url):
                state["failed"] = request.failure

        self.page.on("request", on_request)
        self.page.on("response", on_response)
        self.page.on("requestfinished", on_finished)
        self.page.on("requestfailed", on_failed)
        try:
            yield state
        finally:
            self.page.remove_listener("request", on_request)
            self.page.remove_listener("response", on_response)
            self.page.remove_listener("requestfinished", on_finished)
            self.page.remove_listener("requestfailed", on_failed)

    def _wait_generation(self, state: dict[str, Any], timeout: int) -> str | None:
        """先等请求发出去，再等这一轮生成结束。

        返回 SSE 原文；如果压根没发出去（比如按钮点击被吞了），返回 ``None``，
        由调用方换个方式再试一次。
        """
        started = self._pump_until(
            lambda: state["done"] or state["failed"] or state["seen"] > 0,
            START_GRACE_TIMEOUT,
        )
        if not started:
            return None

        finished = self._pump_until(
            lambda: state["done"] or state["failed"], timeout
        )
        if state["failed"]:
            raise GenerationFailed(f"生成请求失败：{state['failed']}")
        if not finished:
            raise ResponseTimeout(f"等待回复超过 {timeout / 1000:.0f}s")

        self._wait_answer_rendered(timeout=15_000)
        response = state["response"]
        if response is None:
            return None
        try:
            return response.body().decode("utf-8", errors="replace")
        except PlaywrightError:
            return None

    def _pump_until(self, predicate, timeout_ms: int) -> bool:
        """一边等条件一边转事件循环（sync Playwright 的事件靠 wait_for_timeout 驱动）。"""
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if predicate():
                return True
            self.page.wait_for_timeout(100)
        return False

    def _wait_answer_rendered(self, timeout: int) -> None:
        try:
            self.page.wait_for_function(ANSWER_READY_JS, timeout=timeout)
        except PlaywrightTimeout:
            pass  # 空回复或页面异常，交给上层按"没解析到内容"处理

    # ------------------------------------------------------------------ 读取

    def last_message(self) -> dict[str, str]:
        data = self.page.evaluate(EXTRACT_LAST_MESSAGE_JS)
        if not data:
            raise ElementNotFound("页面上没有可读取的消息")
        return data

    # ------------------------------------------------------------------ 接口

    def ensure_origin(self) -> None:
        """确保页面停在 chat.deepseek.com 上——接口请求是同源的，还依赖这里的登录态。"""
        if self.page.evaluate("() => location.origin") != CHAT_ORIGIN:
            self.open_home()

    def api_get(self, path: str, params: dict[str, str] | None = None) -> dict:
        """在页面里发一个带 token 的同源 GET，返回解析好的 JSON。"""
        self.ensure_origin()
        query = "&".join(f"{key}={value}" for key, value in (params or {}).items())
        url = f"{path}?{query}" if query else path
        token = self.page.evaluate(TOKEN_JS)
        if not token:
            raise LoginRequired("没有拿到登录 token，请确认浏览器处于登录态")
        return self.page.evaluate(API_FETCH_JS, {"url": url, "token": token})

    def fetch_history(self, session_id: str) -> dict:
        """某个会话的完整消息。

        刻意**不传** ``cache_version``：传了服务端只回增量，缺的部分得靠浏览器
        本地缓存补，程序上不可靠；不传则稳定返回全量。
        """
        return self.api_get(HISTORY_API, {"chat_session_id": session_id})

    def fetch_sessions(self) -> dict:
        """会话列表（接口一次只给一页，是否还有更多看返回里的 ``has_more``）。"""
        return self.api_get(SESSIONS_API, {"lte_cursor.pinned": "false"})
