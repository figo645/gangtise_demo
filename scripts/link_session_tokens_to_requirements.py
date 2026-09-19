#!/usr/bin/env python3
"""Allocate visible Codex session-token estimates to requirement IDs by user intent.

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

from build_codex_session_token_estimate import HISTORY_DB, collect_turns, project_thread_ids


ROOT = Path(__file__).resolve().parents[1]
AUDIT_CSV = ROOT / "用户故事盘点_业务技术需求_审计更新_2026-09-18.csv"
DETAIL_CSV = ROOT / "Codex需求Token工时归因明细_2026-09-18.csv"
SUMMARY_CSV = ROOT / "Codex需求Token工时归因汇总_2026-09-18.csv"

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
    "US069": ("worker", "scheduler", "进程", "启动shell", "内存"), "US070": ("巨石模板",),
    "US071": ("架构", "容量", "性能", "速度很慢"), "US072": ("postgres", "sqlite"),
    "US073": ("会话",), "US074": ("记忆", "memory"), "US075": ("使用统计", "算力"),
    "US076": ("定时任务", "任务中心", "工作流更新"), "US078": ("复盘",),
    "US079": ("k线标注驱动",), "US080": ("echarts", "图表"),
    "US081": ("模型id", "模型绑定", "llm", "v4", "doubao"),
    "US082": ("bdd", "测试报告", "api清单"),
    "US083": ("行业", "市场一览", "热门行业", "宏观", "上证指数", "市场快照", "同步数据"),
}


def matches(text: str) -> list[str]:
    normalized = text.lower()
    matched = [
        requirement_id for requirement_id, keywords in REQUIREMENT_KEYWORDS.items()
        if any(keyword.lower() in normalized for keyword in keywords)
    ]
    return matched or ["UNCLASSIFIED"]


def timestamp(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000).strftime("%Y-%m-%d %H:%M:%S")


def main() -> None:
    connection = sqlite3.connect(HISTORY_DB)
    try:
        turns = collect_turns(connection, project_thread_ids(connection))
    finally:
        connection.close()

    aggregation: dict[str, dict[str, object]] = defaultdict(lambda: {
        "turns": 0, "input": 0.0, "output": 0.0, "duration_ms": 0.0, "first": None, "last": None,
    })
    with DETAIL_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        fields = ["序号", "开始时间", "结束时间", "命中需求ID", "归因数量", "分配上行Token估算", "分配下行Token估算", "分配Token总计", "分配运行分钟", "用户请求摘要"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for turn in turns:
            requirement_ids = matches(str(turn["input_text"]))
            divisor = len(requirement_ids)
            input_share = int(turn["input_tokens"]) / divisor
            output_share = int(turn["output_tokens"]) / divisor
            duration_ms = max(int(turn["completed_at"]) - int(turn["started_at"]), 0) / divisor
            for requirement_id in requirement_ids:
                item = aggregation[requirement_id]
                item["turns"] = int(item["turns"]) + 1
                item["input"] = float(item["input"]) + input_share
                item["output"] = float(item["output"]) + output_share
                item["duration_ms"] = float(item["duration_ms"]) + duration_ms
                item["first"] = min(item["first"], int(turn["started_at"])) if item["first"] else int(turn["started_at"])
                item["last"] = max(item["last"], int(turn["completed_at"])) if item["last"] else int(turn["completed_at"])
                writer.writerow({
                    "序号": turn["sequence"], "开始时间": timestamp(int(turn["started_at"])), "结束时间": timestamp(int(turn["completed_at"])),
                    "命中需求ID": requirement_id, "归因数量": divisor, "分配上行Token估算": round(input_share, 2),
                    "分配下行Token估算": round(output_share, 2), "分配Token总计": round(input_share + output_share, 2),
                    "分配运行分钟": round(duration_ms / 60000, 2), "用户请求摘要": turn["input_preview"],
                })

    rows = list(csv.DictReader(AUDIT_CSV.open("r", encoding="utf-8-sig", newline="")))
    fields = list(rows[0].keys())
    summary_rows = []
    for row in rows:
        item = aggregation.get(row["需求ID"])
        if item:
            hours = float(item["duration_ms"]) / 3_600_000
            row.update({
                "Codex Token 输入（会话估算）": str(round(float(item["input"]))),
                "Codex Token 输出（会话估算）": str(round(float(item["output"]))),
                "Codex Token 总计（会话估算）": str(round(float(item["input"]) + float(item["output"]))),
                "Codex 会话归因开始时间": timestamp(int(item["first"])),
                "Codex 会话归因结束时间": timestamp(int(item["last"])),
                "Codex 累计会话运行时长（小时）": f"{hours:.2f}",
                "会话归因人天（8小时）": f"{hours / 8:.3f}",
                "Token 数据质量": f"项目会话可见文本离线估算；{item['turns']}轮按用户请求关键词归因，多需求轮次均分；不是供应商账单。",
                "工时数据质量": "用户请求至可见助手回复的时长，按关键词归因并均分；不等同于连续人工工时。",
            })
        else:
            row.update({
                "Codex Token 输入（会话估算）": "0", "Codex Token 输出（会话估算）": "0", "Codex Token 总计（会话估算）": "0",
                "Codex 会话归因开始时间": "", "Codex 会话归因结束时间": "", "Codex 累计会话运行时长（小时）": "0",
                "会话归因人天（8小时）": "0",
            })
            row["Token 数据质量"] = "未命中项目会话需求关键词；0 表示未归因，不表示实际未消耗。"
            row["工时数据质量"] = "未命中项目会话需求关键词；0 表示未归因，不表示实际未耗时。"
        summary_rows.append({field: row.get(field, "") for field in [
            "需求ID", "需求标题", "Codex Token 输入（会话估算）", "Codex Token 输出（会话估算）", "Codex Token 总计（会话估算）",
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

    assigned = sum(float(item["input"]) + float(item["output"]) for key, item in aggregation.items() if key != "UNCLASSIFIED")
    unclassified = aggregation.get("UNCLASSIFIED", {})
    print(json.dumps({
        "requirements_with_allocations": len([key for key in aggregation if key != "UNCLASSIFIED"]),
        "assigned_token_estimate": round(assigned),
        "unclassified_token_estimate": round(float(unclassified.get("input", 0)) + float(unclassified.get("output", 0))),
        "audit_csv": str(AUDIT_CSV), "summary_csv": str(SUMMARY_CSV), "detail_csv": str(DETAIL_CSV),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
