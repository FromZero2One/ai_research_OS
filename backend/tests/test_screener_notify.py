"""定时选股变化日报 Webhook 通知单测。"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from core.config import settings
from screener.notify import (
    build_webhook_payload,
    format_diff_text,
    send_screener_webhook,
    should_notify,
)

_RUN = {
    "id": "run-1",
    "created_at": datetime(2026, 10, 24, 8, 30, tzinfo=UTC),
    "candidate_count": 13,
    "result_count": 5,
}


def _diff() -> dict:
    return {
        "new_recommended": [
            {"ticker": "600000", "name": "浦发银行"},
            {"ticker": "600036", "name": "招商银行"},
        ],
        "dropped_recommended": [{"ticker": "000001", "name": "平安银行"}],
        "new_candidates": [],
        "dropped_candidates": [],
        "counts": {
            "new_recommended": 2,
            "dropped_recommended": 1,
            "new_candidates": 0,
            "dropped_candidates": 0,
        },
    }


def test_format_diff_text_contains_counts_and_names():
    text = format_diff_text("核心资产", _RUN, _diff(), "reports/x.md")
    assert "【智能选股】核心资产" in text
    assert "候选 13，推荐 5" in text
    assert "新推荐 2｜掉出推荐 1" in text
    assert "600000 浦发银行" in text
    assert "000001 平安银行" in text
    assert "日报：reports/x.md" in text


def test_format_diff_text_handles_empty_diff():
    text = format_diff_text("核心资产", _RUN, {"counts": {}})
    assert "新推荐 0｜掉出推荐 0" in text
    assert "新推荐：" not in text


def test_build_webhook_payload_formats():
    assert build_webhook_payload("hi", "wecom") == {
        "msgtype": "text", "text": {"content": "hi"}
    }
    assert build_webhook_payload("hi", "dingtalk")["msgtype"] == "text"
    assert build_webhook_payload("hi", "feishu") == {
        "msg_type": "text", "content": {"text": "hi"}
    }
    generic = build_webhook_payload("hi", "generic", run_id="r1")
    assert generic["text"] == "hi" and generic["run_id"] == "r1"


def test_should_notify_modes(monkeypatch):
    monkeypatch.setattr(settings, "SCREENER_WEBHOOK_NOTIFY_ON", "changes")
    assert should_notify(None, False) is False
    assert should_notify({"counts": {"new_recommended": 0}}, True) is False
    assert should_notify(_diff(), True) is True

    monkeypatch.setattr(settings, "SCREENER_WEBHOOK_NOTIFY_ON", "always")
    assert should_notify(None, False) is True


async def test_send_disabled_without_url():
    result = await send_screener_webhook("hi", url="")
    assert result == {"enabled": False, "sent": False}


async def test_send_success_and_business_error():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.read().decode())
        if "fail" in seen[-1]:
            return httpx.Response(200, json={"errcode": 40058, "errmsg": "invalid"})
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ok = await send_screener_webhook(
        "hi", url="https://example.test/hook", fmt="wecom", client=client
    )
    assert ok["sent"] is True
    bad = await send_screener_webhook(
        "fail", url="https://example.test/hook", fmt="wecom", client=client
    )
    assert bad["sent"] is False
    assert "errcode=40058" in bad["error"]
    await client.aclose()
