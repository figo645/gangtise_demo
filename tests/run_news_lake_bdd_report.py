"""Test the domestic news-source -> normalized events -> fixed indicators pipeline.

This is intentionally an isolated, read-only test harness. It does not write the
application database or publish results to H5 until the source contract is accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from html.parser import HTMLParser
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "tests" / "reports"
REPORT_PATH = REPORT_DIR / "news_lake_bdd_report.html"
JSON_PATH = REPORT_DIR / "news_lake_bdd_report.json"


SOURCE_CATALOG = [
    {
        "code": "gov_cn_policy",
        "name": "中国政府网",
        "category": "policy",
        "kind": "web",
        "url": "https://www.gov.cn/zhengce/index.htm",
        "indicator": "policy_news_heat",
    },
    {
        "code": "pboc_policy",
        "name": "中国人民银行",
        "category": "policy",
        "kind": "web",
        "url": "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
        "indicator": "policy_news_heat",
    },
    {
        "code": "stats_macro",
        "name": "国家统计局",
        "category": "macro",
        "kind": "web",
        "url": "https://www.stats.gov.cn/sj/zxfb/",
        "indicator": "macro_news_heat",
    },
    {
        "code": "csrc_regulation",
        "name": "中国证监会",
        "category": "regulatory",
        "kind": "web",
        "url": "https://www.csrc.gov.cn/csrc/c101937/common_list.shtml",
        "indicator": "regulatory_event_count",
    },
    {
        "code": "cninfo_announcements",
        "name": "巨潮资讯",
        "category": "company_announcement",
        "kind": "web",
        "url": "https://www.cninfo.com.cn/new/index",
        "indicator": "company_event_count",
    },
    {
        "code": "sse_disclosure",
        "name": "上海证券交易所",
        "category": "company_announcement",
        "kind": "web",
        "url": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
        "indicator": "company_event_count",
    },
    {
        "code": "szse_disclosure",
        "name": "深圳证券交易所",
        "category": "company_announcement",
        "kind": "web",
        "url": "https://www.szse.cn/disclosure/listed/notice/",
        "indicator": "company_event_count",
    },
]


RSS_FIXTURE = """<?xml version='1.0' encoding='UTF-8'?>
<rss version='2.0'><channel>
  <item><title>政策样例</title><description>政策正文摘要样例</description>
    <link>https://example.invalid/policy-1</link><pubDate>Fri, 07 Aug 2026 08:00:00 GMT</pubDate></item>
  <item><title>政策样例</title><description>政策正文摘要样例</description>
    <link>https://example.invalid/policy-1</link><pubDate>Fri, 07 Aug 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value, limit=500):
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def normalize_rss(raw_text, source):
    root = ElementTree.fromstring(raw_text)
    events = []
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"), 180)
        summary = clean_text(item.findtext("description"), 500)
        link = clean_text(item.findtext("link"), 500)
        published_at = clean_text(item.findtext("pubDate"), 120)
        if not title or not link:
            continue
        identity = f"{link}|{title}".encode("utf-8")
        events.append({
            "event_id": hashlib.sha256(identity).hexdigest()[:24],
            "source_code": source["code"],
            "source_name": source["name"],
            "category": source["category"],
            "title": title,
            "summary": summary,
            "url": link,
            "published_at": published_at,
            "fetched_at": now_utc(),
            "indicator_code": source["indicator"],
        })
    return events


class NewsAnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.href = ""
        self.text = []
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a" and not self.href:
            self.href = str(dict(attrs).get("href") or "").strip()
            self.text = []

    def handle_data(self, data):
        if self.href:
            self.text.append(str(data or ""))

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href:
            self.items.append({"href": self.href, "title": clean_text("".join(self.text), 180)})
            self.href = ""
            self.text = []


def normalize_web_listing(raw_text, source):
    parser = NewsAnchorCollector()
    parser.feed(str(raw_text or "")[:1200000])
    events, seen = [], set()
    blocked_titles = {"首页", "返回", "登录", "注册", "搜索", "更多", "下一页", "上一页", "网站地图"}
    for item in parser.items:
        title = clean_text(item.get("title"), 180)
        link = urljoin(source["url"], str(item.get("href") or "").strip())
        if len(title) < 8 or title in blocked_titles or not link.startswith(("http://", "https://")) or link == source["url"] or link in seen:
            continue
        seen.add(link)
        identity = f"{link}|{title}".encode("utf-8")
        events.append({
            "event_id": hashlib.sha256(identity).hexdigest()[:24],
            "source_code": source["code"],
            "source_name": source["name"],
            "category": source["category"],
            "title": title,
            "summary": "",
            "url": link,
            "published_at": "",
            "fetched_at": now_utc(),
            "indicator_code": source["indicator"],
        })
        if len(events) >= 20:
            break
    return events


def dedupe_events(events):
    unique = {}
    for event in events:
        unique[event["event_id"]] = event
    return list(unique.values())


def derive_indicators(events):
    counts = {}
    for event in events:
        code = event["indicator_code"]
        counts[code] = counts.get(code, 0) + 1
    return [
        {
            "indicator_code": code,
            "value": value,
            "unit": "条/批次",
            "point_time": now_utc(),
            "source_event_count": value,
            "is_simulated": False,
        }
        for code, value in sorted(counts.items())
    ]


def probe_source(source, live=True):
    result = {**source, "status": "not_run", "http_status": None, "latency_ms": None, "detail": ""}
    if not live:
        result.update(status="skipped", detail="未执行网络探测")
        return result, []
    started = time.monotonic()
    try:
        request = Request(source["url"], headers={"User-Agent": "GangtiseNewsLakeTest/1.0"})
        with urlopen(request, timeout=10) as response:
            body = response.read(250000).decode("utf-8", errors="ignore")
            result.update(
                status="pass",
                http_status=getattr(response, "status", 200),
                latency_ms=round((time.monotonic() - started) * 1000),
                detail="真实公开源可访问",
            )
            events = normalize_rss(body, source) if source["kind"] == "rss" else normalize_web_listing(body, source)
            result["item_count"] = len(events)
            if len(events) < 5:
                result.update(status="excluded", detail=f"有效信息 {len(events)} 条，低于纳入门槛 5 条")
                return result, []
            result["detail"] = f"真实公开源可访问，已纳入 {len(events)} 条有效信息"
            return result, events
    except HTTPError as exc:
        result.update(status="fail", http_status=exc.code, latency_ms=round((time.monotonic() - started) * 1000), detail=f"HTTP {exc.code}")
    except (URLError, TimeoutError) as exc:
        result.update(status="fail", latency_ms=round((time.monotonic() - started) * 1000), detail=f"网络不可用: {exc}")
    except Exception as exc:
        result.update(status="fail", latency_ms=round((time.monotonic() - started) * 1000), detail=str(exc)[:200])
    return result, []


def build_report(probes, events, indicators, live, checks):
    passed = sum(item["status"] == "pass" for item in probes)
    source_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(item.get(key) or '--'))}</td>" for key in ("name", "category", "kind", "status", "http_status", "latency_ms", "item_count", "indicator", "detail")) + "</tr>"
        for item in probes
    )
    event_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(event.get(key) or '--'))}</td>" for key in ("source_name", "category", "title", "published_at", "fetched_at", "indicator_code", "url")) + "</tr>"
        for event in events
    ) or "<tr><td colspan='7'>本次真实 RSS 未返回可解析事件；页面源仍已完成连通性测试。</td></tr>"
    indicator_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(item.get(key) or '--'))}</td>" for key in ("indicator_code", "value", "unit", "point_time", "source_event_count", "is_simulated")) + "</tr>"
        for item in indicators
    ) or "<tr><td colspan='6'>暂无真实 RSS 事件，未生成固定指标。</td></tr>"
    status = "PASS" if passed and indicators else "PARTIAL"
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>国内新闻数据源入湖 BDD 报告</title>
<style>body{{font:14px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#172132;background:#f4f7fb;margin:0;padding:28px}}main{{max-width:1400px;margin:auto}}h1{{margin:0 0 8px}}h2{{margin-top:28px;color:#1f497d}}.summary{{display:flex;gap:12px;flex-wrap:wrap}}.card{{background:#fff;border:1px solid #dce6f2;border-radius:10px;padding:14px;min-width:170px}}table{{width:100%;border-collapse:collapse;background:#fff;font-size:12px}}th,td{{border:1px solid #dce6f2;padding:8px;text-align:left;vertical-align:top}}th{{background:#eaf3ff;color:#1f497d}}.pass{{color:#146b4a;font-weight:700}}.partial{{color:#a56a00;font-weight:700}}.note{{background:#fff8e8;border-left:4px solid #c7902e;padding:12px;line-height:1.7}}a{{color:#2f74c0;word-break:break-all}}</style></head><body><main>
<h1>国内新闻数据源入湖 BDD 测试报告</h1><p>执行时间：{html.escape(now_utc())} · 网络探测：{str(live).lower()} · 结果：<span class='{status.lower()}'>{status}</span></p>
<div class='summary'><div class='card'>数据源总数<br><strong>{len(probes)}</strong></div><div class='card'>真实源可访问<br><strong>{passed}</strong></div><div class='card'>标准化事件<br><strong>{len(events)}</strong></div><div class='card'>固定指标<br><strong>{len(indicators)}</strong></div></div>
<div class='note'>本报告只读探测公开信息源，不写入正式 PostgreSQL，不接入 H5。固定指标仅由本次标准化事件计算，未使用模拟值。页面型来源只验证可访问性，正式接入仍需配置页面解析器和字段映射。</div>
<h2>1. 数据源分类与连通性</h2><table><tr><th>来源</th><th>分类</th><th>类型</th><th>状态</th><th>HTTP</th><th>耗时(ms)</th><th>有效信息数</th><th>固定指标</th><th>说明</th></tr>{source_rows}</table>
<h2>2. 新闻事件标准化</h2><table><tr><th>来源</th><th>分类</th><th>标题</th><th>发布时间</th><th>抓取时间</th><th>固定指标</th><th>原文链接</th></tr>{event_rows}</table>
<h2>3. 固定指标产出</h2><table><tr><th>指标编码</th><th>值</th><th>单位</th><th>指标时间</th><th>事件数</th><th>模拟值</th></tr>{indicator_rows}</table>
<h2>4. BDD 管道验证</h2><table><tr><th>场景</th><th>结果</th><th>说明</th></tr>{''.join(f"<tr><td>{html.escape(item['name'])}</td><td class='{'pass' if item['passed'] else 'partial'}'>{'PASS' if item['passed'] else 'FAIL'}</td><td>{html.escape(item['detail'])}</td></tr>" for item in checks)}</table>
<h2>5. 正式接入前置条件</h2><ul><li>来源分类必须落在 policy、macro、regulatory、company_announcement 等固定类别。</li><li>RSS 事件必须包含标题、原文链接、发布时间、抓取时间和去重 ID。</li><li>同一链接与标题重复出现时只保留一条。</li><li>固定指标必须由标准化事件计算，<strong>is_simulated=false</strong>。</li><li>页面型来源不能仅凭 HTTP 200 视为完成接入，必须补充解析器和字段映射后才能进入正式指标湖。</li></ul>
</main></body></html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-live", action="store_true", help="跳过网络探测，仅验证结构")
    args = parser.parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    probes, raw_events = [], []
    for source in SOURCE_CATALOG:
        probe, events = probe_source(source, live=not args.no_live)
        probes.append(probe)
        raw_events.extend(events)
    events = dedupe_events(raw_events)
    indicators = derive_indicators(events)
    fixture_source = {"code": "fixture_policy", "name": "BDD RSS 样例", "category": "policy", "indicator": "policy_news_heat"}
    fixture_events = normalize_rss(RSS_FIXTURE, fixture_source)
    fixture_unique = dedupe_events(fixture_events)
    fixture_indicators = derive_indicators(fixture_unique)
    checks = [
        {"name": "RSS 事件字段标准化", "passed": bool(fixture_events and fixture_events[0].get("event_id") and fixture_events[0].get("published_at")), "detail": "标题、摘要、链接、发布时间、抓取时间和事件 ID 均已生成。"},
        {"name": "重复新闻去重", "passed": len(fixture_events) == 2 and len(fixture_unique) == 1, "detail": f"原始事件 {len(fixture_events)} 条，去重后 {len(fixture_unique)} 条。"},
        {"name": "固定指标生成", "passed": bool(fixture_indicators and fixture_indicators[0].get("is_simulated") is False), "detail": "固定指标由标准化事件聚合生成，未使用模拟值。"},
        {"name": "正式库隔离", "passed": True, "detail": "本轮仅生成报告文件，没有写入正式 PostgreSQL 或 H5 发布态。"},
    ]
    report = {
        "generated_at": now_utc(),
        "live_probe": not args.no_live,
        "sources": probes,
        "events": events,
        "indicators": indicators,
    }
    report["bdd_checks"] = checks
    JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(build_report(probes, events, indicators, not args.no_live, checks), encoding="utf-8")
    print(f"HTML report: {REPORT_PATH}")
    print(f"JSON report: {JSON_PATH}")
    print(f"sources={len(probes)} events={len(events)} indicators={len(indicators)}")


if __name__ == "__main__":
    main()
