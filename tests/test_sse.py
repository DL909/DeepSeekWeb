"""不依赖浏览器的单元测试：SSE 解析 + 开关归一化。

    python tests/test_sse.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from deepseekweb.session import _normalize  # noqa: E402
from deepseekweb.sse import parse_stream  # noqa: E402

SAMPLE = (
    'event: ready\ndata: {"request_message_id":1,"response_message_id":2,"model_type":"default"}\n\n'
    'data: {"v":{"response":{"message_id":2,"status":"WIP","accumulated_token_usage":0,'
    '"fragments":[{"id":2,"type":"THINK","content":"我们"}]}}}\n\n'
    'data: {"v":"需要"}\n\n'
    'data: {"p":"response/fragments","v":[{"id":4,"type":"TIP","content":"AI 生成"}]}\n\n'
    'data: {"p":"response","o":"BATCH","v":[{"p":"accumulated_token_usage","v":249},'
    '{"p":"quasi_status","v":"FINISHED"}]}\n\n'
    'data: {"p":"response/status","o":"SET","v":"FINISHED"}\n\n'
    'event: title\ndata: {"content":"量子纠缠简述"}\n\n'
    'event: close\ndata: {"click_behavior":"none","auto_resume":false}\n\n'
)


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    return ok


def main() -> int:
    results = []

    summary = parse_stream(SAMPLE)
    results.append(check("结束状态", summary.status == "FINISHED", str(summary.status)))
    results.append(check("token 用量取最后一次补丁", summary.usage == 249, str(summary.usage)))
    results.append(check("会话标题", summary.title == "量子纠缠简述", str(summary.title)))
    results.append(
        check(
            "消息 id",
            summary.request_message_id == 1 and summary.response_message_id == 2,
        )
    )

    results.append(check("空输入不炸", parse_stream(None).status is None))
    results.append(check("乱码不炸", parse_stream("!!! not json !!!").usage is None))

    thinking, search = _normalize(True, False)
    results.append(check("thinking 透传", thinking is True and search is False))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _normalize(True, True, file="x.pdf")
    results.append(
        check("file/search 被忽略时给出提示", len(caught) == 2, f"{len(caught)} 条 warning")
    )

    print()
    failed = results.count(False)
    if failed:
        print(f"{failed} 项失败")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
