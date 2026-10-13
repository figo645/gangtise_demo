#!/usr/bin/env python3
"""Build a provider-recorded Codex token audit for this project.

The audit reads local Codex JSONL session records without modifying them.
New-format sessions use one row per unique ``token_usage_record`` response.
Legacy sessions use deltas of cumulative ``event_msg.token_count`` values.
Visible-text counts are intentionally not mixed into this report.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SESSIONS_ROOT = Path.home() / ".codex" / "sessions"
AUDIT_DATE = "2026-10-13"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
AUDIT_CUTOFF = datetime(2026, 10, 12, 23, 59, 59, tzinfo=LOCAL_TZ)
PROJECT_CWD = str(ROOT)
DETAIL_CSV = ROOT / f"Codex项目Token实测明细_{AUDIT_DATE}.csv"
DAILY_CSV = ROOT / f"Codex项目Token每日实测_{AUDIT_DATE}.csv"
MONTHLY_CSV = ROOT / f"Codex项目月度Token消耗实测_{AUDIT_DATE}.csv"
RECONCILIATION_CSV = ROOT / f"Codex项目Token口径核验_{AUDIT_DATE}.csv"

TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(LOCAL_TZ)


def timestamp_text(value: str) -> str:
    return parse_timestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def before_cutoff(value: str) -> bool:
    try:
        return parse_timestamp(value) <= AUDIT_CUTOFF
    except (TypeError, ValueError):
        return False


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def project_files() -> list[tuple[Path, list[dict[str, object]], dict[str, object]]]:
    result = []
    for path in sorted(SESSIONS_ROOT.rglob("*.jsonl")):
        rows = read_jsonl(path)
        metadata = next(
            (
                row.get("payload", {})
                for row in rows
                if row.get("type") == "session_meta"
                and isinstance(row.get("payload"), dict)
            ),
            {},
        )
        if isinstance(metadata, dict) and metadata.get("cwd") == PROJECT_CWD:
            result.append((path, rows, metadata))
    return result


def usage_values(usage: object) -> dict[str, int]:
    usage = usage if isinstance(usage, dict) else {}
    return {field: int(usage.get(field) or 0) for field in TOKEN_FIELDS}


def user_text(payload: dict[str, object]) -> str:
    content = payload.get("content")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return ""


def legacy_deltas(rows: list[tuple[str, int, str, dict[str, int], str]]) -> list[dict[str, object]]:
    """Convert cumulative legacy token_count snapshots to usage increments."""
    by_thread: dict[str, list[tuple[str, int, str, dict[str, int]]]] = defaultdict(list)
    for row in rows:
        by_thread[row[0]].append(row)

    result: list[dict[str, object]] = []
    for thread_id, thread_rows in by_thread.items():
        thread_rows.sort(key=lambda row: (row[1], row[2]))
        previous = {field: 0 for field in TOKEN_FIELDS}
        for _, ordinal, timestamp, cumulative, user_input in thread_rows:
            delta = {
                field: max(cumulative[field] - previous[field], 0)
                for field in TOKEN_FIELDS
            }
            if delta["total_tokens"] > 0:
                result.append({
                    "source_format": "legacy_cumulative_delta",
                    "source_file": "",
                    "thread_id": thread_id,
                    "turn_id": "",
                    "response_id": f"legacy:{thread_id}:{ordinal}",
                    "timestamp": timestamp,
                    "usage": delta,
                    "user_input": user_input,
                })
            previous = cumulative
    return result


def collect_records() -> tuple[list[dict[str, object]], dict[str, int]]:
    files = project_files()
    new_thread_ids: set[str] = set()
    records: list[dict[str, object]] = []
    legacy_rows: list[tuple[str, int, str, dict[str, int]]] = []
    user_inputs: dict[str, str] = {}
    user_times: dict[str, str] = {}
    seen_response_ids: set[str] = set()

    for path, rows, metadata in files:
        file_new_records = []
        for row in rows:
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            if row.get("type") == "token_usage_record":
                if not before_cutoff(str(row.get("timestamp") or "")):
                    continue
                response_id = str(payload.get("response_id") or "")
                thread_id = str(payload.get("thread_id") or metadata.get("id") or "")
                if not response_id or response_id in seen_response_ids:
                    continue
                usage = usage_values(payload.get("usage"))
                if usage["total_tokens"] <= 0:
                    continue
                seen_response_ids.add(response_id)
                new_thread_ids.add(thread_id)
                file_new_records.append({
                    "source_format": "token_usage_record",
                    "source_file": str(path),
                    "thread_id": thread_id,
                    "turn_id": str(payload.get("turn_id") or ""),
                    "response_id": response_id,
                    "timestamp": str(row.get("timestamp") or ""),
                    "usage": usage,
                    "user_input": "",
                })
            elif row.get("type") == "response_item":
                if not before_cutoff(str(row.get("timestamp") or "")):
                    continue
                response_payload = payload
                if response_payload.get("role") == "user":
                    passthrough = response_payload.get("internal_chat_message_metadata_passthrough")
                    passthrough = passthrough if isinstance(passthrough, dict) else {}
                    turn_id = str(passthrough.get("turn_id") or "")
                    text = user_text(response_payload)
                    if turn_id and text:
                        user_inputs[turn_id] = text
                        user_times.setdefault(turn_id, str(row.get("timestamp") or ""))
        records.extend(file_new_records)

        # Old token_count events in a file that also contains new records are
        # duplicate UI snapshots of the same provider usage and must be ignored.
        if file_new_records:
            continue
        timeline: list[tuple[str, str]] = []
        for row in rows:
            payload = row.get("payload")
            if not isinstance(payload, dict) or row.get("type") != "response_item":
                continue
            if not before_cutoff(str(row.get("timestamp") or "")):
                continue
            if payload.get("role") != "user":
                continue
            passthrough = payload.get("internal_chat_message_metadata_passthrough")
            passthrough = passthrough if isinstance(passthrough, dict) else {}
            text = user_text(payload)
            if text:
                timeline.append((str(row.get("timestamp") or ""), text))
        for row in rows:
            payload = row.get("payload")
            if not isinstance(payload, dict) or row.get("type") != "event_msg":
                continue
            if not before_cutoff(str(row.get("timestamp") or "")):
                continue
            if payload.get("type") != "token_count" or not isinstance(payload.get("info"), dict):
                continue
            info = payload["info"]
            total_usage = info.get("total_token_usage")
            if not isinstance(total_usage, dict):
                continue
            thread_id = str(metadata.get("id") or metadata.get("session_id") or "")
            event_time = str(row.get("timestamp") or "")
            latest_input = ""
            for message_time, message_text in timeline:
                if message_time <= event_time:
                    latest_input = message_text
                else:
                    break
            legacy_rows.append((
                thread_id,
                int(row.get("ordinal") or 0),
                str(row.get("timestamp") or ""),
                usage_values(total_usage),
                latest_input,
            ))

    records.extend(legacy_deltas(legacy_rows))
    for record in records:
        turn_id = str(record["turn_id"])
        if turn_id and turn_id in user_inputs:
            record["user_input"] = user_inputs[turn_id]
            record["user_timestamp"] = user_times.get(turn_id, "")
        else:
            record["user_timestamp"] = ""
    records.sort(key=lambda record: (str(record["timestamp"]), str(record["response_id"])))
    metadata = {
        "project_files": len(files),
        "new_response_records": len([r for r in records if r["source_format"] == "token_usage_record"]),
        "legacy_delta_records": len([r for r in records if r["source_format"] == "legacy_cumulative_delta"]),
        "unique_response_ids": len(seen_response_ids),
        "new_threads": len(new_thread_ids),
        "audit_cutoff": AUDIT_CUTOFF.strftime("%Y-%m-%d %H:%M:%S%z"),
    }
    return records, metadata


def write_reports(records: list[dict[str, object]], metadata: dict[str, int]) -> None:
    detail_fields = [
        "时间", "月份", "日期", "来源格式", "线程ID", "TurnID", "ResponseID",
        "输入Token", "缓存输入Token", "缓存写入Token", "输出Token", "推理Token", "总Token",
        "用户提示词摘要",
    ]
    with DETAIL_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=detail_fields)
        writer.writeheader()
        for record in records:
            local_time = parse_timestamp(str(record["timestamp"]))
            usage = record["usage"]
            writer.writerow({
                "时间": local_time.strftime("%Y-%m-%d %H:%M:%S"),
                "月份": local_time.strftime("%Y-%m"),
                "日期": local_time.strftime("%Y-%m-%d"),
                "来源格式": record["source_format"],
                "线程ID": record["thread_id"],
                "TurnID": record["turn_id"],
                "ResponseID": record["response_id"],
                "输入Token": usage["input_tokens"],
                "缓存输入Token": usage["cached_input_tokens"],
                "缓存写入Token": usage["cache_write_input_tokens"],
                "输出Token": usage["output_tokens"],
                "推理Token": usage["reasoning_output_tokens"],
                "总Token": usage["total_tokens"],
                "用户提示词摘要": " ".join(str(record.get("user_input") or "").split())[:160],
            })

    def aggregate(key_fn):
        groups = defaultdict(lambda: {field: 0 for field in TOKEN_FIELDS} | {"records": 0, "turns": set(), "threads": set()})
        for record in records:
            key = key_fn(record)
            group = groups[key]
            usage = record["usage"]
            for field in TOKEN_FIELDS:
                group[field] += int(usage[field])
            group["records"] += 1
            if record["turn_id"]:
                group["turns"].add(record["turn_id"])
            group["threads"].add(record["thread_id"])
        return groups

    monthly = aggregate(lambda record: parse_timestamp(str(record["timestamp"])).strftime("%Y-%m"))
    daily = aggregate(lambda record: parse_timestamp(str(record["timestamp"])).strftime("%Y-%m-%d"))
    summary_fields = [
        "期间", "输入Token", "缓存输入Token", "缓存写入Token", "输出Token", "推理Token", "总Token",
        "响应记录数", "Turn数", "线程数",
    ]
    for target, groups in ((MONTHLY_CSV, monthly), (DAILY_CSV, daily)):
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=summary_fields)
            writer.writeheader()
            keys = sorted(groups)
            if target == MONTHLY_CSV and keys:
                first = datetime.strptime(keys[0], "%Y-%m")
                last = datetime.strptime(keys[-1], "%Y-%m")
                while first <= last:
                    key = first.strftime("%Y-%m")
                    groups.setdefault(key, {field: 0 for field in TOKEN_FIELDS} | {"records": 0, "turns": set(), "threads": set()})
                    first = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
                keys = sorted(groups)
            for key in keys:
                group = groups[key]
                writer.writerow({
                    "期间": key,
                    "输入Token": group["input_tokens"],
                    "缓存输入Token": group["cached_input_tokens"],
                    "缓存写入Token": group["cache_write_input_tokens"],
                    "输出Token": group["output_tokens"],
                    "推理Token": group["reasoning_output_tokens"],
                    "总Token": group["total_tokens"],
                    "响应记录数": group["records"],
                    "Turn数": len(group["turns"]),
                    "线程数": len(group["threads"]),
                })

    with RECONCILIATION_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["核验项", "数值", "说明"])
        writer.writerow(["项目会话文件数", metadata["project_files"], "session_meta.cwd 精确匹配项目目录"])
        writer.writerow(["新版响应记录数", metadata["new_response_records"], "按唯一 response_id 计数"])
        writer.writerow(["旧版累计增量记录数", metadata["legacy_delta_records"], "仅对没有新版记录的线程计算"])
        writer.writerow(["唯一响应ID数", metadata["unique_response_ids"], "重复 response_id 未重复计入"])
        writer.writerow(["Token口径", "provider_recorded", "来自 token_usage_record 或旧版累计 token_count 增量，不是可见文本估算"])
        writer.writerow(["旧版与新版关系", "mutually_exclusive", "同一文件含新版记录时忽略旧版 token_count 快照"])


def main() -> None:
    records, metadata = collect_records()
    write_reports(records, metadata)
    total = defaultdict(int)
    for record in records:
        for field in TOKEN_FIELDS:
            total[field] += int(record["usage"][field])
    print(json.dumps({
        **metadata,
        "records": len(records),
        "input_tokens": total["input_tokens"],
        "cached_input_tokens": total["cached_input_tokens"],
        "output_tokens": total["output_tokens"],
        "reasoning_output_tokens": total["reasoning_output_tokens"],
        "total_tokens": total["total_tokens"],
        "monthly_csv": str(MONTHLY_CSV),
        "daily_csv": str(DAILY_CSV),
        "detail_csv": str(DETAIL_CSV),
        "reconciliation_csv": str(RECONCILIATION_CSV),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
