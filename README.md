# deepseek-web

简单的python库，将deepseek 网页端暴露为可调用的程序接口。

底层是 Playwright 驱动一个真实的 Chrome：填输入框、拨"深度思考"开关、等这一轮生成结束，
然后把思考过程和回答读出来。所以拿到的就是网页端本身的能力，包括 R1 的推理过程。

## 安装

```bash
uv add deepseekweb          # 或 pip install deepseekweb
playwright install chromium  # 本机没装 Chrome 时才需要
```

## 先让浏览器登录上

### 方式一：附着到已经开着的 Chrome（推荐）

浏览器里是什么状态就用什么状态，不用重新登录。用这个方式启动 Chrome：

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --remote-debugging-port=9222 \
    --user-data-dir=/path/to/your/profile     # 平时登录 DeepSeek 用的那个 profile
```

然后 `DeepSeekUser(cdp_url="http://127.0.0.1:9222")`，或者设环境变量
`DEEPSEEKWEB_CDP_URL` 就不用每次都写。

> 注意：同一个 profile 同一时刻只能被一个 Chrome 占用，用之前先把原来的 Chrome 关掉。

### 方式二：让本库自己拉一个浏览器

```python
user = DeepSeekUser(account="13511112222", passwd="qwerty")  # 会自动登录
```

登录态存在 `~/.deepseekweb/chrome-profile`，第一次手动登录过之后就一直有效。
给了 `account`/`passwd` 就会自动填表登录；如果中途冒出验证码，窗口是可见的，
手动点一下即可，库会继续等着。

## v0.1

### usage

```python
from deepseekweb import DeepSeekUser, DeepSeekSession

user = DeepSeekUser(account="13511112222", passwd="qwerty")  # 已经登录的浏览器可以省略

session = DeepSeekSession(user=user, id="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                          thinking=False, search=False)

another_session, response = DeepSeekSession.new_session(user=user, input="hello", file=None,
                                                        thinking=True, search=False)
# search和file暂不支持，无论发送什么都视为None和False

print(response.reasoning)  # 推理内容
print(response.answer)  # 回答内容

another_response = session.send(input="introduce your self.", thinking=True)  # 可以在发送时指定thinking和search，否则复用上一次。

user.close()  # 用完记得断开
```

`DeepSeekResponse` 上还有几个顺带读到的东西：

| 字段 | 含义 |
| --- | --- |
| `answer` / `reasoning` | 回答正文、思考过程（**没有思考时是 `None`，判断请用 `is not None`**） |
| `question` | 本轮输入 |
| `session_id` | 会话 id |
| `thinking_enabled` / `search_enabled` | 本轮实际下发的开关 |
| `status` | 正常是 `FINISHED` |
| `usage` | 本轮 token 用量 |
| `title` | DeepSeek 自动生成的会话标题 |
| `id` / `parent_id` | 消息 id 与父消息 id，串起对话的树 |
| `raw` | `/api/v0/chat/completion` 的原始 SSE，排错用 |

### 过往对话

```python
for info in user.list_sessions(limit=10):   # 最近 10 个会话，最近更新的在前
    print(info.id, info.title, info.url)

session = user.get_session("7021d573-...")  # 或者直接 DeepSeekSession(user=user, id=...)
for message in session.get_messages():       # 这个会话的完整对话，按顺序
    if isinstance(message, UserPrompt):
        print("问>", message.content)
        if len(message.file):
            raise NotImplementedError()      # v0.1 不支持附件
    else:
        if message.reasoning is not None:
            print("想>", message.reasoning)
        print("答>", message.answer)
```

`get_messages()` 走服务端接口而不是页面 DOM，两个原因：长对话不会被虚拟列表的
渲染窗口截断（实测 DOM 里会少掉最早的一条用户消息，接口里是全的），也不用先把页面切到那个会话。
重新生成留下的旧分支不会出现，只返回当前这条分支。

### 命令行

```bash
deepseekweb "写一首关于秋天的诗" --reasoning
deepseekweb "继续" --session 7021d573-aa52-44c3-9802-bae27f7c759c --cdp http://127.0.0.1:9222
deepseekweb --list-sessions 10                       # 列最近 10 个会话
deepseekweb --session 7021d573-... --history         # 打印某个会话的完整对话
```

## 实现说明

- **怎么知道"这一轮说完了"**：等 `/api/v0/chat/completion` 这次请求的流式响应结束。
  比盯着 DOM 猜要稳，思考很久、中间停顿都不会误判。
- **内容从哪来**：思考过程取 `div.ds-think-content`，回答取 `div.ds-assistant-message-main-content`。
  只用 `ds-` 开头的设计系统类名，不用 `_74c0879` 这类构建期哈希类名。
- **历史从哪来**：`GET /api/v0/chat/history_messages`。这里有个坑——该接口认
  `cache_version` 参数，浏览器本地缓存过这个会话时服务端只回增量（`cache_control: MERGE`），
  缺的部分得靠前端从 IndexedDB 里补；**不传这个参数就是全量**（`REPLACE`），
  所以库里一律不传。请求在页面里用 `Authorization: Bearer <userToken>` 发，
  裸 `fetch` 会被判 `INVALID_TOKEN`。
- **一个 user 一个页面**：`DeepSeekSession` 只是"会话 id + 开关"，共用同一个浏览器页面，
  `send` 之前会先把页面切到对应的会话。

## 已知限制

- v0.1 不支持 `search` 和 `file`，传了会被忽略并给出 warning。
- 只能同步调用（Playwright 同步 API），单次调用会阻塞到这一轮结束。
- 依赖 DeepSeek 前端的 DOM 结构，前端改版可能要调 `constants.py` 里的选择器。
- 登录页的验证码（hCaptcha）不处理，需要手动点一下。
- `list_sessions()` 只取接口的一页（返回里带 `has_more` 表示还有更多），翻页暂未实现。

## 开发

```bash
python tests/test_sse.py       # 纯单元测试，不需要浏览器
python tests/test_history.py   # 历史解析的单元测试，不需要浏览器
python tests/smoke.py          # 端到端，需要一个已登录且开了调试端口的 Chrome
```
