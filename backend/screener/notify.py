"""定时选股变化日报的 Webhook 通知（企业微信 / 飞书 / 钉钉 / 通用 JSON）。

配置：
  SCREENER_WEBHOOK_URL      为空则禁用；支持群机器人完整 URL
  SCREENER_WEBHOOK_FORMAT   generic | wecom | feishu | dingtalk（默认 generic）
  SCREENER_WEBHOOK_TIMEOUT  请求超时秒数（默认 10）
  SCREENER_WEBHOOK_NOTIFY_ON changes | always（默认 changes：仅在有变化时发送）
"""

from __future__ import annotations

from datetime import datetime

import httpx

from core.config import settings
from core.logging import logger

_LIST_LIMIT = 8


def _fmt_ts(value) -> str:
    if value is None:
        return "-"
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value.astimezone().strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(value)


def _names(rows: list[dict] | None) -> str:
    rows = rows or []
    if not rows:
        return "无"
    shown = [f"{j.get('ticker')} {j.get('name') or ''}".strip() for j in rows[:_LIST_LIMIT]]
    more = len(rows) - len(shown)
    return "、".join(shown) + (f" 等 {len(rows)} 只" if more > 0 else "")


def format_diff_text(
    preset_name: str,
    run: dict,
    diff: dict,
    diff_path: str | None = None,
) -> str:
    """把变化日报压成一条适合群机器人阅读的纯文本。"""
    counts = (diff or {}).get("counts") or {}
    lines = [
        f"【智能选股】{preset_name} · {_fmt_ts(run.get('created_at'))}",
        (
            f"本轮：候选 {run.get('candidate_count', '-')}，"
            f"推荐 {run.get('result_count', '-')}"
        ),
        (
            f"变化：新推荐 {counts.get('new_recommended', 0)}｜"
            f"掉出推荐 {counts.get('dropped_recommended', 0)}｜"
            f"新进候选 {counts.get('new_candidates', 0)}｜"
            f"移出候选 {counts.get('dropped_candidates', 0)}"
        ),
    ]
    if counts.get("new_recommended"):
        lines.append(f"新推荐：{_names(diff.get('new_recommended'))}")
    if counts.get("dropped_recommended"):
        lines.append(f"掉出推荐：{_names(diff.get('dropped_recommended'))}")
    if diff_path:
        lines.append(f"日报：{diff_path}")
    return "\n".join(lines)


def format_failure_text(run: dict) -> str:
    """运行失败告警（手动/定时共用）。"""
    criteria = " ".join(str(run.get("criteria_text") or "").split())[:120] or "-"
    error = " ".join(str(run.get("error") or "未知原因").split())[:300]
    return "\n".join(
        [
            "【智能选股】运行失败",
            f"标准：{criteria}",
            f"Run：{str(run.get('id', '-'))[:8]}",
            f"时间：{_fmt_ts(run.get('finished_at'))}",
            f"错误：{error}",
        ]
    )


def build_webhook_payload(text: str, fmt: str = "generic", **meta) -> dict:
    """按机器人平台拼装请求体；未知格式回退通用 JSON。"""
    fmt = (fmt or "generic").lower()
    if fmt in ("wecom", "dingtalk"):
        return {"msgtype": "text", "text": {"content": text}}
    if fmt == "feishu":
        return {"msg_type": "text", "content": {"text": text}}
    return {"text": text, **meta}


def _webhook_error(fmt: str, data) -> str | None:
    """平台常在 HTTP 200 里返回业务错误码。"""
    if not isinstance(data, dict):
        return None
    if (fmt or "").lower() in ("wecom", "dingtalk"):
        code = data.get("errcode", 0)
        if code not in (0, None):
            return f"errcode={code} {data.get('errmsg', '')}"
    if (fmt or "").lower() == "feishu":
        code = data.get("code", data.get("StatusCode", 0))
        if code not in (0, None):
            return f"code={code} {data.get('msg', data.get('StatusMessage', ''))}"
    return None


async def send_screener_webhook(
    text: str,
    *,
    url: str | None = None,
    fmt: str | None = None,
    timeout: float | None = None,
    client: httpx.AsyncClient | None = None,
    **meta,
) -> dict:
    """发送通知；未配置 URL 时静默禁用，发送失败只记日志不抛异常。"""
    url = settings.SCREENER_WEBHOOK_URL if url is None else url
    fmt = (settings.SCREENER_WEBHOOK_FORMAT if fmt is None else fmt) or "generic"
    if not url:
        return {"enabled": False, "sent": False}

    timeout = settings.SCREENER_WEBHOOK_TIMEOUT if timeout is None else timeout
    payload = build_webhook_payload(text, fmt, **meta)
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        resp = await http.post(url, json=payload)
        try:
            data = resp.json()
        except ValueError:
            data = None
        error = None
        if resp.status_code >= 400:
            error = f"HTTP {resp.status_code}"
        else:
            error = _webhook_error(fmt, data)
        if error:
            logger.warning("选股 Webhook 发送失败: %s", error)
            return {
                "enabled": True,
                "sent": False,
                "status_code": resp.status_code,
                "error": error,
            }
        return {"enabled": True, "sent": True, "status_code": resp.status_code}
    except Exception as e:  # noqa: BLE001 — 通知失败不能影响定时任务
        logger.warning("选股 Webhook 请求异常: %s", e)
        return {"enabled": True, "sent": False, "error": str(e)[:200]}
    finally:
        if owns_client:
            await http.aclose()


def should_notify(diff: dict | None, has_previous: bool) -> bool:
    """默认仅在有上一轮基线且确有变化时推送。"""
    mode = (settings.SCREENER_WEBHOOK_NOTIFY_ON or "changes").lower()
    if mode == "always":
        return True
    if not has_previous or not diff:
        return False
    return any((diff.get("counts") or {}).values())
