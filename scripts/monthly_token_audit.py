#!/usr/bin/env python3
"""Monthly token-size audit for Gangtise Demo Codex activity.

Writes only to the repository tmp/ directory; does not mutate session history.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HISTORY_DB = Path.home() / ".codex/thread_history_1.sqlite"
STATE_DB = Path.home() / ".codex/state_5.sqlite"
TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)

PROJECT_CWD = str(ROOT)
PROJECT_MARKER = str(ROOT)

USER_ITEMS = ("userMessage", "agentMessage", "reasoning", "commandExecution", "fileChange", "mcpToolCall")


def text_of(item: dict[str, object]) -> str:
    if item.get("text") is not None:
        return str(item["text"])
    if item.get("content") is not None:
        return str(item["content"])
    if item.get("summary") is not None:
        return str(item["summary"])
    if item.get("command") is not None:
        return str(item["command"])
    if item.get("arguments") is not None:
        return json.dumps(item["arguments"], ensure_ascii=False)
    if item.get("result") is not None:
        return json.dumps(item["result"], ensure_ascii=False)
    return ""


def tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in text)
    words = sum(char.isascii() and (char.isalnum() or char == "_") for char in text)
    other = max(len(text) - cjk - words, 0)
    return max(1, round(cjk * 1.25 + words / 3.8 + other * 0.35))


def month_of(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m")


connection = sqlite3.connect(HISTORY_DB.as_uri() + "?mode=ro", uri=True)
rows = connection.execute(
    """
    SELECT thread_id, created_at_ms, item_type, item_json
    FROM thread_items
    WHERE item_json LIKE ?
    ORDER BY created_at_ms
    """,
    (f"%{PROJECT_MARKER}%",),
).fetchall()
connection.close()

monthly: dict[str, dict[str, int]] = defaultdict(lambda: {
    "visible_input": 0, "visible_output": 0, "reasoning": 0,
    "commands_and_files": 0, "tools": 0, "full_estimate": 0, "turns": 0,
})
daily: dict[str, dict[str, int]] = defaultdict(lambda: {
    "visible": 0, "full_estimate": 0, "turns": 0,
})
seen_turns: set[tuple[str, str]] = set()

for thread_id, created_ms, item_type, raw_json in rows:
    try:
        item = json.loads(raw_json)
    except json.JSONDecodeError:
        item = {}
    text = text_of(item)
    size = tokens(text)
    month = month_of(int(created_ms))
    day = datetime.fromtimestamp(int(created_ms) / 1000).strftime("%Y-%m-%d")
    turn_key = (thread_id, str(item.get("turnId") or item.get("turn_id") or ""))
    if item_type == "userMessage" and turn_key not in seen_turns:
        seen_turns.add(turn_key)
        monthly[month]["turns"] += 1
        daily[day]["turns"] += 1

    if item_type in ("userMessage", "agentMessage"):
        if item_type == "userMessage":
            monthly[month]["visible_input"] += size
        else:
            monthly[month]["visible_output"] += size
    elif item_type == "reasoning":
        # Empty reasoning summaries must still be counted as internal model
        # activity; use 1 token/event floor instead of pretending they are 0.
        monthly[month]["reasoning"] += max(size, 1)
    elif item_type in ("commandExecution", "fileChange"):
        monthly[month]["commands_and_files"] += size
    elif item_type == "mcpToolCall":
        monthly[month]["tools"] += size

    monthly[month]["full_estimate"] = (
        monthly[month]["visible_input"] + monthly[month]["visible_output"]
        + monthly[month]["reasoning"] + monthly[month]["commands_and_files"]
        + monthly[month]["tools"]
    )
    daily[day]["visible"] = daily[day]["visible"] + size if item_type in USER_ITEMS else daily[day]["visible"]
    daily[day]["full_estimate"] += size

with (TMP / "monthly_token_audit.csv").open("w", encoding="utf-8-sig", newline="") as f:
    fields = ["月份", "用户提示Token", "助手回复Token", "可见合计", "推理事件Token", "命令与文件Token", "工具Token", "全活动估算", "轮次"]
    writer = csv.writer(f)
    writer.writerow(fields)
    for month in sorted(monthly):
        m = monthly[month]
        writer.writerow([
            month, m["visible_input"], m["visible_output"], m["visible_input"] + m["visible_output"],
            m["reasoning"], m["commands_and_files"], m["tools"], m["full_estimate"], m["turns"],
        ])

with (TMP / "daily_token_audit.csv").open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["日期", "项目相关活动Token估算", "可见文本Token估算", "轮次"])
    for day in sorted(daily):
        d = daily[day]
        writer.writerow([day, d["full_estimate"], d["visible"], d["turns"]])

state = sqlite3.connect(STATE_DB.as_uri() + "?mode=ro", uri=True)
state_rows = state.execute(
    "SELECT id,created_at_ms,updated_at_ms,tokens_used,title FROM threads WHERE cwd=? ORDER BY created_at_ms",
    (PROJECT_CWD,),
).fetchall()
state.close()
with (TMP / "project_threads_state.csv").open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["thread_id", "created_at_ms", "updated_at_ms", "tokens_used", "title"])
    writer.writerows(state_rows)

print(json.dumps({
    "items": len(rows),
    "project_state_threads": len(state_rows),
    "state_tokens_used_total": sum(int(row[3] or 0) for row in state_rows),
    "monthly_csv": str(TMP / "monthly_token_audit.csv"),
}, ensure_ascii=False))
