#!/usr/bin/env python3
"""Allocate recorded Codex response tokens to requirement IDs by user intent.

The mapping is a reviewable keyword classifier. A turn matching multiple requirements
is split equally so requirement totals reconcile to the conversation total.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from build_codex_session_token_estimate import HISTORY_DB, collect_turns, project_thread_ids
from build_codex_token_audit import collect_records


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DATE = "2026-10-13"
CURRENT_AUDIT_CSV = ROOT / f"用户故事盘点_业务技术需求_审计更新_{AUDIT_DATE}.csv"
SOURCE_AUDIT_CSV = CURRENT_AUDIT_CSV
if not SOURCE_AUDIT_CSV.exists():
    SOURCE_AUDIT_CSV = ROOT / "用户故事盘点_业务技术需求_审计更新_2026-10-12.csv"
AUDIT_CSV = ROOT / f"用户故事盘点_业务技术需求_审计更新_{AUDIT_DATE}.csv"
DETAIL_CSV = ROOT / f"Codex需求Token实测归因明细_{AUDIT_DATE}.csv"
SUMMARY_CSV = ROOT / f"Codex需求Token实测归因汇总_{AUDIT_DATE}.csv"
AUDIT_CUTOFF = datetime(2026, 10, 12, 23, 59, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
AUDIT_CUTOFF_MS = int(AUDIT_CUTOFF.timestamp() * 1000)

# Keep this dictionary explicit and reviewable. More specific phrases win only
# through multi-match splitting; totals are never duplicated.
REQUIREMENT_KEYWORDS = {
    "US001": ("门户", "tenant portal"), "US004": ("富文本", "粘贴图片", "上传图片"),
    "US007": ("基本面",), "US008": ("k线", "日k", "分时", "分钟线"),
    "US009": ("自选股", "watchlist"), "US010": ("k线标注", "标注"),
    "US011": ("阅读复盘",), "US012": ("发布复盘", "复盘草稿", "复盘编辑"),
    "US013": ("语音转",), "US014": ("上传文件", "文件生成复盘"),
    "US015": ("消息", "站内信"), "US018": ("个股分析", "分析下今天上证"),
    "US019": ("小金智能体", "hermes", "智能体"), "US021": ("知识库", "知识条目"),
    "US024": ("管理租户",), "US025": ("用户", "账户", "粉丝管理", "大v账户"),
    "US026": ("功能开关",), "US027": ("访问审计",), "US030": ("互动洞察", "用户活动分布", "统计图表"),
    "US032": ("盲盒", "问答", "做题", "quiz"), "US033": ("二维码", "扫码注册", "扫码"),
    "US034": ("h5", "大v工作台", "admin后台"), "US035": ("品牌", "门户配置"),
    "US036": ("知识数据",), "US037": ("智能体工作流", "agent工作流"),
    "US040": ("共性问题",), "US041": ("水印", "盗版"), "US043": ("gangtise", "午报", "晚报", "晨报", "财经播报"),
    "US044": ("合规", "免责声明"), "US045": ("研究板块",), "US046": ("预警",),
    "US047": ("指标格子", "展示指标", "指标配置"), "US048": ("akshare", "sina", "数据源", "光大银行"),
    "US051": ("dashboard草稿",), "US052": ("复盘内容库",), "US054": ("个股详情页留言",),
    "US057": ("token", "模型消耗"), "US058": ("证据链", "过滤提示词"),
    "US059": ("批量导入", "导入用户", "新增用户", "用户名"), "US060": ("执行进度", "实时进度"),
    "US061": ("用户详情", "编辑用户"), "US062": ("菜单", "模块归属"),
    "US067": ("app.py", "路由", "领域层"), "US068": ("连接池", "外部依赖"),
    "US069": ("worker", "scheduler", "进程", "启动shell", "内存"),
    "US070": ("巨石模板", "h5前端资源", "前端资源拆分", "h5-app.js", "h5-shell.css", "工作台和admin模板"),
    "US071": ("架构", "容量", "性能", "速度很慢"), "US072": ("postgres", "sqlite"),
    "US073": ("会话",), "US074": ("记忆", "memory"), "US075": ("使用统计", "算力"),
    "US076": ("定时任务", "任务中心", "工作流更新"), "US078": ("复盘",),
    "US079": ("k线标注驱动",), "US080": ("echarts", "图表"),
    "US081": ("模型id", "模型绑定", "llm", "v4", "doubao"),
    "US082": ("bdd", "测试报告", "api清单"),
    "US083": ("行业", "市场一览", "热门行业", "宏观", "上证指数", "市场快照", "同步数据"),
    "US084": ("etf", "交易所交易基金"),
    "US085": ("gangtise凭证", "gangtise api的key", "数据库中已经有凭证", "数据库凭证", "凭证读取", "行情api凭证"),
    "US086": ("首页体积", "首页 html", "首屏载荷", "资源拆分", "h5-app.js", "h5-shell.css", "5.48 mb"),
    "US087": ("twitter", "硅谷大佬", "elon musk", "硅谷人物"),
    "US088": ("本地credential文件", "本地 credential 文件", "credential文件操作", "本地凭证文件", "本地 credential"),
}

# These requirements were introduced during the October audit. A matching word
# in an older turn must not retroactively allocate that turn to a requirement
# that did not exist in the audited scope yet.
REQUIREMENT_START_DATES = {
    "US084": "2026-10-08",
    "US085": "2026-10-11",
    "US086": "2026-10-12",
    "US087": "2026-10-12",
    "US088": "2026-10-11",
}


def matches(text: str, started_at_ms: int | None = None) -> list[str]:
    normalized = text.lower()
    matched = [
        requirement_id for requirement_id, keywords in REQUIREMENT_KEYWORDS.items()
        if (
            requirement_id not in REQUIREMENT_START_DATES
            or started_at_ms is None
            or timestamp(started_at_ms)[:10] >= REQUIREMENT_START_DATES[requirement_id]
        )
        and any(keyword.lower() in normalized for keyword in keywords)
    ]
    return matched or ["UNCLASSIFIED"]


def timestamp(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000).strftime("%Y-%m-%d %H:%M:%S")


def main() -> None:
    records, audit_metadata = collect_records()

    # Keep the staffing-time metric on the historical 12 October basis. It is
    # deliberately independent from provider token records: a provider usage
    # event has no reliable start/end duration, while the local thread history
    # retains the user-turn to visible-response interval used by the audit.
    connection = sqlite3.connect(HISTORY_DB, timeout=30)
    try:
        session_turns = collect_turns(connection, project_thread_ids(connection))
    finally:
        connection.close()
    duration_aggregation: dict[str, dict[str, object]] = defaultdict(lambda: {
        "turns": 0, "duration_ms": 0.0, "first": None, "last": None,
    })
    for turn in session_turns:
        started_at = int(turn["started_at"])
        if started_at > AUDIT_CUTOFF_MS:
            continue
        completed_at = min(int(turn["completed_at"]), AUDIT_CUTOFF_MS)
        requirement_ids = matches(str(turn["input_text"]), started_at)
        duration_share = max(completed_at - started_at, 0) / len(requirement_ids)
        for requirement_id in requirement_ids:
            item = duration_aggregation[requirement_id]
            item["turns"] = int(item["turns"]) + 1
            item["duration_ms"] = float(item["duration_ms"]) + duration_share
            item["first"] = min(item["first"], started_at) if item["first"] else started_at
            item["last"] = max(item["last"], completed_at) if item["last"] else completed_at

    aggregation: dict[str, dict[str, object]] = defaultdict(lambda: {
        "turns": 0, "input": 0.0, "output": 0.0, "duration_ms": 0.0, "first": None, "last": None,
    })
    last_matches_by_thread: dict[str, list[str]] = {}
    with DETAIL_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        fields = ["序号", "时间", "月份", "来源格式", "线程ID", "TurnID", "ResponseID", "命中需求ID", "归因数量", "分配输入Token", "分配缓存输入Token", "分配输出Token", "分配推理Token", "分配Token总计", "用户请求摘要"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for sequence, record in enumerate(records, start=1):
            usage = record["usage"]
            input_text = str(record.get("user_input") or "")
            timestamp_value = str(record.get("timestamp") or "")
            started_at = int(datetime.fromisoformat(timestamp_value.replace("Z", "+00:00")).timestamp() * 1000)
            requirement_ids = matches(input_text, started_at)
            # Short follow-ups such as “请修复” or “提交到 GitHub” carry the
            # immediately preceding business context in the same Codex thread.
            # Apply this only to the new October requirements so historical
            # allocations remain stable.
            if requirement_ids == ["UNCLASSIFIED"]:
                previous = last_matches_by_thread.get(str(record["thread_id"]), [])
                if previous and all(item in REQUIREMENT_START_DATES for item in previous):
                    requirement_ids = previous
            direct_matches = [item for item in requirement_ids if item != "UNCLASSIFIED"]
            if direct_matches:
                last_matches_by_thread[str(record["thread_id"])] = direct_matches
            divisor = len(requirement_ids)
            for requirement_id in requirement_ids:
                item = aggregation[requirement_id]
                item["turns"] = int(item["turns"]) + 1
                item["input"] = float(item["input"]) + int(usage["input_tokens"]) / divisor
                item["cached_input"] = float(item.get("cached_input", 0)) + int(usage["cached_input_tokens"]) / divisor
                item["output"] = float(item["output"]) + int(usage["output_tokens"]) / divisor
                item["reasoning"] = float(item.get("reasoning", 0)) + int(usage["reasoning_output_tokens"]) / divisor
                item["total"] = float(item.get("total", 0)) + int(usage["total_tokens"]) / divisor
                item["first"] = min(item["first"], started_at) if item["first"] else started_at
                item["last"] = max(item["last"], started_at) if item["last"] else started_at
                writer.writerow({
                    "序号": sequence, "时间": timestamp(started_at), "月份": timestamp(started_at)[:7],
                    "来源格式": record["source_format"], "线程ID": record["thread_id"], "TurnID": record["turn_id"],
                    "ResponseID": record["response_id"], "命中需求ID": requirement_id, "归因数量": divisor,
                    "分配输入Token": round(int(usage["input_tokens"]) / divisor, 2),
                    "分配缓存输入Token": round(int(usage["cached_input_tokens"]) / divisor, 2),
                    "分配输出Token": round(int(usage["output_tokens"]) / divisor, 2),
                    "分配推理Token": round(int(usage["reasoning_output_tokens"]) / divisor, 2),
                    "分配Token总计": round(int(usage["total_tokens"]) / divisor, 2),
                    "用户请求摘要": " ".join(input_text.split())[:160],
                })

    rows = list(csv.DictReader(SOURCE_AUDIT_CSV.open("r", encoding="utf-8-sig", newline="")))
    fields = list(rows[0].keys())
    for field in [
        "Codex Token 输入（provider实测）", "Codex Token 缓存输入（provider实测）",
        "Codex Token 输出（provider实测）", "Codex Token 推理（provider实测）",
        "Codex Token 总计（provider实测）",
    ]:
        if field not in fields:
            fields.append(field)
    summary_rows = []
    for row in rows:
        item = aggregation.get(row["需求ID"])
        duration_item = duration_aggregation.get(row["需求ID"])
        if item or duration_item:
            item = item or {"input": 0, "cached_input": 0, "output": 0, "reasoning": 0, "total": 0, "turns": 0}
            duration_item = duration_item or {"duration_ms": 0, "first": None, "last": None, "turns": 0}
            hours = float(duration_item["duration_ms"]) / 3_600_000
            row.update({
                "Codex Token 输入（会话估算）": "",
                "Codex Token 输出（会话估算）": "",
                "Codex Token 总计（会话估算）": "",
                "Codex Token 输入（provider实测）": str(round(float(item["input"]))),
                "Codex Token 缓存输入（provider实测）": str(round(float(item["cached_input"]))),
                "Codex Token 输出（provider实测）": str(round(float(item["output"]))),
                "Codex Token 推理（provider实测）": str(round(float(item["reasoning"]))),
                "Codex Token 总计（provider实测）": str(round(float(item["total"]))),
                "Codex 会话归因开始时间": timestamp(int(duration_item["first"])) if duration_item["first"] else "",
                "Codex 会话归因结束时间": timestamp(int(duration_item["last"])) if duration_item["last"] else "",
                "Codex 累计会话运行时长（小时）": f"{hours:.2f}",
                "会话归因人天（8小时）": f"{hours / 8:.3f}",
                "Token 数据质量": f"Codex provider_recorded 实测；{item['turns']}条响应记录按用户请求关键词归因，多需求记录均分；缓存输入单独列出；旧的会话估算列已废弃。",
                "工时数据质量": f"沿用 2026-10-12 算法：{duration_item['turns']} 个会话轮次按关键词归因并均分；截止 {AUDIT_CUTOFF.strftime('%Y-%m-%d %H:%M:%S')}；不等同于连续人工工时。",
            })
        else:
            row.update({
                "Codex Token 输入（会话估算）": "", "Codex Token 输出（会话估算）": "", "Codex Token 总计（会话估算）": "",
                "Codex Token 输入（provider实测）": "0", "Codex Token 缓存输入（provider实测）": "0",
                "Codex Token 输出（provider实测）": "0", "Codex Token 推理（provider实测）": "0", "Codex Token 总计（provider实测）": "0",
                "Codex 会话归因开始时间": "", "Codex 会话归因结束时间": "", "Codex 累计会话运行时长（小时）": "0",
                "会话归因人天（8小时）": "0",
            })
            row["Token 数据质量"] = "未命中项目会话需求关键词；0 表示未归因，不表示实际未消耗。"
            row["工时数据质量"] = "未命中项目会话需求关键词；0 表示未归因，不表示实际未耗时。"
        summary_rows.append({field: row.get(field, "") for field in [
            "需求ID", "需求标题", "Codex Token 输入（provider实测）", "Codex Token 缓存输入（provider实测）",
            "Codex Token 输出（provider实测）", "Codex Token 推理（provider实测）", "Codex Token 总计（provider实测）",
            "Codex 会话归因开始时间", "Codex 会话归因结束时间", "Codex 累计会话运行时长（小时）", "会话归因人天（8小时）",
        ]})

    with AUDIT_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with SUMMARY_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    assigned = sum(float(item["total"]) for key, item in aggregation.items() if key != "UNCLASSIFIED")
    unclassified = aggregation.get("UNCLASSIFIED", {})
    print(json.dumps({
        "requirements_with_allocations": len([key for key in aggregation if key != "UNCLASSIFIED"]),
        "assigned_provider_tokens": round(assigned),
        "unclassified_provider_tokens": round(float(unclassified.get("total", 0))),
        "source_records": len(records),
        "source_metadata": audit_metadata,
        "audit_csv": str(AUDIT_CSV), "summary_csv": str(SUMMARY_CSV), "detail_csv": str(DETAIL_CSV),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
