#!/usr/bin/env python3
"""Estimate visible user/assistant token flow for local Gangtise project sessions.

This is intentionally an estimate: Codex local history does not retain provider
usage. It measures only visible userMessage and agentMessage text using o200k_base.
"""

from __future__ import annotations

import csv
import html
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY_DB = Path.home() / ".codex/thread_history_1.sqlite"
OUTPUT_CSV = ROOT / "Codex项目会话Token估算明细_2026-09-18.csv"
OUTPUT_DAILY_CSV = ROOT / "Codex项目会话Token估算曲线_2026-09-18.csv"
OUTPUT_HTML = ROOT / "tests/reports/codex_project_token_estimate_2026-09-18.html"
WORKSPACE_MARKER = "/Users/xuchenfei/PycharmProjects/gangtise_demo"
TOKENIZER_METHOD = "offline_cjk_heuristic"
try:
    import tiktoken

    ENCODING = tiktoken.get_encoding("o200k_base")
    TOKENIZER_METHOD = "tiktoken_o200k_base"
except Exception:
    ENCODING = None


def visible_text(value: object) -> str:
    """Extract human-visible text content, excluding tool payloads and reasoning."""
    if not isinstance(value, dict):
        return ""
    if isinstance(value.get("text"), str):
        return value["text"]
    blocks = value.get("content")
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts)


def tokens(text: str) -> int:
    if not text:
        return 0
    if ENCODING is not None:
        return len(ENCODING.encode(text))
    # Offline fallback for Chinese-heavy conversation text. It is deliberately
    # labeled as an estimate and is not a provider billing token count.
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in text)
    ascii_word_chars = sum(char.isascii() and (char.isalnum() or char == "_") for char in text)
    other = max(len(text) - cjk - ascii_word_chars, 0)
    return max(1, round(cjk * 1.25 + ascii_word_chars / 3.8 + other * 0.35))


def iso_time(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000).strftime("%Y-%m-%d %H:%M:%S")


def project_thread_ids(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT DISTINCT thread_id FROM thread_items WHERE item_json LIKE ?",
        (f"%{WORKSPACE_MARKER}%",),
    ).fetchall()
    return {row[0] for row in rows}


def collect_turns(connection: sqlite3.Connection, thread_ids: set[str]) -> list[dict[str, object]]:
    placeholders = ",".join("?" for _ in thread_ids)
    query = f"""
        SELECT thread_id, turn_id, created_at_ms, item_type, item_json
        FROM thread_items
        WHERE thread_id IN ({placeholders})
          AND item_type IN ('userMessage', 'agentMessage')
        ORDER BY created_at_ms, rollout_ordinal
    """
    rows = connection.execute(query, tuple(thread_ids)).fetchall()
    turns: list[dict[str, object]] = []
    active_by_thread: dict[str, dict[str, object]] = {}
    sequence = 0
    for thread_id, turn_id, created_at_ms, item_type, raw_json in rows:
        try:
            item = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        text = visible_text(item)
        if not text:
            continue
        if item_type == "userMessage":
            active = active_by_thread.get(thread_id)
            if active:
                turns.append(active)
            sequence += 1
            active_by_thread[thread_id] = {
                "sequence": sequence,
                "thread_id": thread_id,
                "turn_id": turn_id,
                "started_at": created_at_ms,
                "completed_at": created_at_ms,
                "input_tokens": tokens(text),
                "output_tokens": 0,
                "input_text": text,
                "input_preview": " ".join(text.split())[:140],
            }
        elif thread_id in active_by_thread:
            active = active_by_thread[thread_id]
            active["output_tokens"] = int(active["output_tokens"]) + tokens(text)
            active["completed_at"] = created_at_ms
    turns.extend(active_by_thread.values())
    turns.sort(key=lambda item: int(item["started_at"]))
    for sequence, turn in enumerate(turns, start=1):
        turn["sequence"] = sequence
    return turns


def write_csv(turns: list[dict[str, object]]) -> list[dict[str, object]]:
    total_input = total_output = 0
    daily: dict[str, dict[str, int]] = defaultdict(lambda: {"input": 0, "output": 0, "turns": 0})
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        fields = [
            "序号", "开始时间", "结束时间", "线程ID", "TurnID", "上行Token估算", "下行Token估算",
            "本轮Token估算", "累计上行Token估算", "累计下行Token估算", "累计Token估算", "用户请求摘要",
        ]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for turn in turns:
            total_input += int(turn["input_tokens"])
            total_output += int(turn["output_tokens"])
            day = iso_time(int(turn["started_at"]))[:10]
            daily[day]["input"] += int(turn["input_tokens"])
            daily[day]["output"] += int(turn["output_tokens"])
            daily[day]["turns"] += 1
            writer.writerow({
                "序号": turn["sequence"], "开始时间": iso_time(int(turn["started_at"])),
                "结束时间": iso_time(int(turn["completed_at"])), "线程ID": turn["thread_id"],
                "TurnID": turn["turn_id"], "上行Token估算": turn["input_tokens"],
                "下行Token估算": turn["output_tokens"],
                "本轮Token估算": int(turn["input_tokens"]) + int(turn["output_tokens"]),
                "累计上行Token估算": total_input, "累计下行Token估算": total_output,
                "累计Token估算": total_input + total_output, "用户请求摘要": turn["input_preview"],
            })

    cumulative_input = cumulative_output = 0
    daily_rows: list[dict[str, object]] = []
    with OUTPUT_DAILY_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        fields = ["日期", "轮次", "上行Token估算", "下行Token估算", "当日Token估算", "累计上行Token估算", "累计下行Token估算", "累计Token估算"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for day in sorted(daily):
            item = daily[day]
            cumulative_input += item["input"]
            cumulative_output += item["output"]
            row = {
                "日期": day, "轮次": item["turns"], "上行Token估算": item["input"], "下行Token估算": item["output"],
                "当日Token估算": item["input"] + item["output"], "累计上行Token估算": cumulative_input,
                "累计下行Token估算": cumulative_output, "累计Token估算": cumulative_input + cumulative_output,
            }
            writer.writerow(row)
            daily_rows.append(row)
    return daily_rows


def write_html(turns: list[dict[str, object]], daily_rows: list[dict[str, object]]) -> None:
    total_input = sum(int(turn["input_tokens"]) for turn in turns)
    total_output = sum(int(turn["output_tokens"]) for turn in turns)
    values = [int(row["累计Token估算"]) for row in daily_rows]
    max_value = max(values, default=1)
    width, height, pad = 980, 320, 46
    points = []
    for index, value in enumerate(values):
        x = pad + (width - 2 * pad) * index / max(len(values) - 1, 1)
        y = height - pad - (height - 2 * pad) * value / max_value
        points.append(f"{x:.1f},{y:.1f}")
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row[field]))}</td>" for field in [
            "日期", "轮次", "上行Token估算", "下行Token估算", "当日Token估算", "累计Token估算"
        ]) + "</tr>"
        for row in daily_rows
    )
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Codex 项目会话 Token 估算</title>
<style>body{{margin:0;background:#f5f7fb;color:#152033;font:14px -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}}main{{max-width:1100px;margin:32px auto;padding:0 22px}}.hero{{background:linear-gradient(135deg,#0d2740,#165b79);color:white;border-radius:18px;padding:28px}}.metrics{{display:flex;gap:12px;flex-wrap:wrap;margin-top:20px}}.metric{{background:#fff;border-radius:12px;padding:15px;min-width:180px;color:#182b3d}}.metric b{{display:block;font-size:24px;margin-top:5px}}section{{background:#fff;border-radius:16px;padding:22px;margin-top:20px;box-shadow:0 5px 20px #16305512}}svg{{width:100%;height:auto;background:#f8fbfd;border-radius:12px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e7edf3;text-align:right}}th:first-child,td:first-child{{text-align:left}}.note{{color:#5f6f80;line-height:1.7}}</style></head>
<body><main><div class="hero"><h1>Codex 项目会话 Token 估算曲线</h1><p>范围：{len(turns)} 个可见用户请求轮次；项目相关本地会话，2026-05-20 至 2026-09-18。</p></div>
<div class="metrics"><div class="metric">上行估算<b>{total_input:,}</b></div><div class="metric">下行估算<b>{total_output:,}</b></div><div class="metric">总计估算<b>{total_input + total_output:,}</b></div><div class="metric">下行占比<b>{(total_output / max(total_input + total_output, 1)):.1%}</b></div></div>
<section><h2>累计 Token 曲线</h2><svg viewBox="0 0 {width} {height}" role="img" aria-label="累计 Token 估算曲线"><line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#cbd7e2"/><line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}" stroke="#cbd7e2"/><polyline fill="none" stroke="#ed7d31" stroke-width="4" points="{' '.join(points)}"/><text x="{pad}" y="{pad-12}" fill="#526577">累计总 Token：{max_value:,}</text></svg></section>
<section><h2>按日汇总</h2><table><thead><tr><th>日期</th><th>轮次</th><th>上行</th><th>下行</th><th>当日</th><th>累计</th></tr></thead><tbody>{rows}</tbody></table></section>
<section class="note"><h2>口径与限制</h2><p>Tokenizer：<code>{TOKENIZER_METHOD}</code>。仅对本地线程历史内可见 <code>userMessage</code> 和 <code>agentMessage</code> 文本计数。该数值不含系统提示、隐藏上下文、上下文压缩、模型推理、工具原始输入输出、图片和文件内容；因此用于会话规模趋势与上下行对比，不用于供应商计费对账。</p></section></main></body></html>""", encoding="utf-8")


def main() -> None:
    if not HISTORY_DB.exists():
        raise SystemExit(f"history database not found: {HISTORY_DB}")
    connection = sqlite3.connect(HISTORY_DB)
    try:
        ids = project_thread_ids(connection)
        turns = collect_turns(connection, ids)
    finally:
        connection.close()
    daily_rows = write_csv(turns)
    write_html(turns, daily_rows)
    print(json.dumps({
        "project_threads": len(ids), "turns": len(turns),
        "tokenizer_method": TOKENIZER_METHOD,
        "input_tokens_estimate": sum(int(turn["input_tokens"]) for turn in turns),
        "output_tokens_estimate": sum(int(turn["output_tokens"]) for turn in turns),
        "detail_csv": str(OUTPUT_CSV), "daily_csv": str(OUTPUT_DAILY_CSV), "report": str(OUTPUT_HTML),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
