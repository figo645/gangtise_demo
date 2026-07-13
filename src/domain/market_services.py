from src.runtime import *
from src.domain.core_services import *

def gen_funnel_data():
    base = [68000, 5400, 1260, 128, 36]
    return [{"layer": FUNNEL_LAYERS[i], "count": base[i], "rate": round(base[i]/base[0]*100, 2)} for i in range(5)]

def gen_channel_data():
    data = [
        {"name": "微信社群", "users": 2100, "conversion": 6.4, "revenue": 28600, "color": "#07C160"},
        {"name": "内容合作", "users": 1400, "conversion": 4.8, "revenue": 19200, "color": "#FE2C55"},
        {"name": "小红书", "users": 980, "conversion": 3.6, "revenue": 13600, "color": "#FF2442"},
        {"name": "转介绍", "users": 620, "conversion": 12.1, "revenue": 24800, "color": "#E6162D"},
        {"name": "直接流量", "users": 300, "conversion": 15.0, "revenue": 16800, "color": "#C8A96E"},
    ]
    return data

def gen_kol_data():
    tenants = get_tenant_configs()
    tenant_rows = []
    for index, tenant in enumerate(tenants):
        tenant_rows.append(
            {
                "name": tenant["advisor"],
                "platform": "租户门户",
                "followers": 128000 - index * 18000,
                "gmv": 18600 - index * 2400,
                "commission": 2790 - index * 360,
                "tier": tenant["tier"],
                "tenant_name": tenant["name"],
                "tenant_slug": tenant["slug"],
            }
        )
    tenant_rows.extend(
        [
            {"name": "宏观策略师", "platform": "内容合作", "followers": 54000, "gmv": 9600, "commission": 1536, "tier": "观察"},
            {"name": "量化小白", "platform": "小红书", "followers": 32000, "gmv": 7800, "commission": 1170, "tier": "观察"},
            {"name": "港股研究员", "platform": "转介绍", "followers": 18000, "gmv": 5400, "commission": 810, "tier": "观察"},
        ]
    )
    return tenant_rows

def gen_market_data():
    indices = [
        {
            "code": "600519",
            "name": "贵州茅台",
            "market": "SH",
            "value": 1688.20,
            "change": 12.80,
            "change_pct": 0.76,
            "focus": "高端白酒",
            "board": "稳健配置",
            "alert_level": "normal",
            "alert_text": "估值回到中枢附近，当前无明显预警",
            "signal_summary": "盈利稳定，重点看消费修复持续性",
            "authors": ["财经老王", "量化老师陈明"],
        },
        {
            "code": "300750",
            "name": "宁德时代",
            "market": "SZ",
            "value": 212.36,
            "change": -3.84,
            "change_pct": -1.78,
            "focus": "动力电池",
            "board": "新能源",
            "alert_level": "warning",
            "alert_text": "价格竞争仍在，需继续跟踪利润率和海外出货",
            "signal_summary": "情绪回落，等待技术路线与订单验证",
            "authors": ["新能源猎手阿强", "全球宏观James"],
        },
        {
            "code": "00700",
            "name": "腾讯控股",
            "market": "HK",
            "value": 388.40,
            "change": 5.60,
            "change_pct": 1.46,
            "focus": "港股互联网",
            "board": "港股互联网",
            "alert_level": "attention",
            "alert_text": "财报前估值修复较快，关注南向资金是否继续放量",
            "signal_summary": "回购和财报兑现是两条主验证线",
            "authors": ["投资女神Lisa", "港股研究员"],
        },
        {
            "code": "688981",
            "name": "中芯国际",
            "market": "SH",
            "value": 46.52,
            "change": 1.18,
            "change_pct": 2.60,
            "focus": "半导体制造",
            "board": "科技成长",
            "alert_level": "attention",
            "alert_text": "景气恢复尚未完全兑现，需继续跟踪产能利用率",
            "signal_summary": "国产替代逻辑在，短期看盈利兑现",
            "authors": ["财经老王", "宏观策略师"],
        },
        {
            "code": "600036",
            "name": "招商银行",
            "market": "SH",
            "value": 41.86,
            "change": 0.22,
            "change_pct": 0.53,
            "focus": "银行",
            "board": "稳健配置",
            "alert_level": "normal",
            "alert_text": "股息和资产质量稳定，当前无明显报警",
            "signal_summary": "更适合作为组合稳定器跟踪",
            "authors": ["全球宏观James", "量化老师陈明"],
        },
    ]
    return indices


def gen_macro_indicators():
    return [
        {
            "name": "美联储年内降息预期",
            "value": "2次",
            "status": "good",
            "assessment": "偏利好风险资产",
            "alert": "当前无需报警",
            "hint": "市场已部分提前定价，后续看非农和通胀数据是否继续支持。",
        },
        {
            "name": "北向 / 南向资金",
            "value": "+28亿 / +41亿",
            "status": "attention",
            "assessment": "流入延续但未到强共振",
            "alert": "关注是否连续 3 日放量",
            "hint": "若资金只集中在单一主线，说明市场广度仍不够。",
        },
        {
            "name": "美元指数",
            "value": "103.4",
            "status": "good",
            "assessment": "偏回落，对港股与大宗更友好",
            "alert": "当前无需报警",
            "hint": "若美元重新走强，港股互联网和黄金链条都要重新评估。",
        },
        {
            "name": "国内信用脉冲",
            "value": "温和修复",
            "status": "warning",
            "assessment": "恢复力度偏弱",
            "alert": "需继续观察社融和中长期贷款",
            "hint": "若信用扩张迟迟不起来，顺周期与高弹性资产要谨慎。",
        },
    ]



def extract_quoted_payload(detail):
    text = str(detail or "").strip()
    if not text:
        return ""
    match = re.search(r'="(.*)"', text)
    if match:
        return match.group(1)
    return ""


def split_endpoint_url(api_url):
    text = str(api_url or "").strip()
    if not text:
        return "", "", {}
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"}:
        return "", "", {}
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or ""
    if parsed.query:
        path = f"{path}?{parsed.query}" if path else f"?{parsed.query}"
    return base_url, path, {key: value for key, value in parse_qsl(parsed.query, keep_blank_values=True)}


def discover_payload_paths(payload, prefix=""):
    paths = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (dict, list)):
                paths.extend(discover_payload_paths(value, next_prefix))
            else:
                paths.append(next_prefix)
    elif isinstance(payload, list):
        for index, value in enumerate(payload[:6]):
            next_prefix = f"{prefix}.{index}" if prefix else str(index)
            if isinstance(value, (dict, list)):
                paths.extend(discover_payload_paths(value, next_prefix))
            else:
                paths.append(next_prefix)
    elif prefix:
        paths.append(prefix)
    return paths


def build_source_sample_from_market_dashboard(raw):
    detail = str(raw.get("last_test_detail") or "").strip()
    extractor_type = str(raw.get("extractor_type") or "").strip().lower()
    last_tested_at = str(raw.get("last_tested_at") or "").strip()
    indicator_name = str(raw.get("indicator") or raw.get("id") or "指标").strip()
    sample = {
        "indicator": indicator_name,
        "provider": str(raw.get("provider") or "").strip(),
        "connector_type": "akshare" if str(raw.get("api_url") or "").startswith("akshare://") else ("http" if str(raw.get("api_url") or "").startswith(("http://", "https://")) else "manual"),
        "extractor_type": extractor_type or "sample",
        "status": "good" if "200" in str(raw.get("last_test_status") or "") else "attention",
        "timestamp": normalize_datetime_text(last_tested_at or now_ts()),
        "value": None,
        "raw_preview": detail[:600],
    }
    quoted = extract_quoted_payload(detail)
    if extractor_type == "text" and quoted:
        delimiter = "~" if "~" in quoted else ","
        fields = [part.strip() for part in quoted.split(delimiter)]
        sample["raw_delimiter"] = delimiter
        sample["raw_field_count"] = len(fields)
        sample["raw_fields"] = fields[:40]
        sample["timestamp"] = extract_timestamp_from_fields(fields, fallback=last_tested_at or now_ts())
        if delimiter == "~":
            sample["name"] = fields[1] if len(fields) > 1 else indicator_name
            sample["symbol"] = fields[2] if len(fields) > 2 else str(raw.get("id") or "")
            sample["value"] = coerce_float(fields[3], coerce_float(fields[0], 0.0))
            sample["prev_close"] = coerce_float(fields[4])
            sample["open"] = coerce_float(fields[5])
            sample["change"] = coerce_float(fields[31]) if len(fields) > 31 else None
            sample["change_pct"] = coerce_float(fields[32]) if len(fields) > 32 else None
            sample["high"] = coerce_float(fields[33]) if len(fields) > 33 else None
            sample["low"] = coerce_float(fields[34]) if len(fields) > 34 else None
        else:
            sample["name"] = fields[-1] if fields else indicator_name
            sample["symbol"] = str(raw.get("id") or "")
            sample["value"] = coerce_float(fields[0], 0.0)
            sample["change_pct"] = coerce_float(fields[1])
            sample["open"] = coerce_float(fields[2])
            sample["high"] = coerce_float(fields[4]) if len(fields) > 4 else None
            sample["low"] = coerce_float(fields[5]) if len(fields) > 5 else None
    elif extractor_type == "akshare":
        sample["record_summary"] = detail or f"{indicator_name} AKShare 样例"
        sample["value"] = coerce_float(re.search(r"(-?\\d+(?:\\.\\d+)?)", detail).group(1), None) if re.search(r"(-?\\d+(?:\\.\\d+)?)", detail) else None
    else:
        sample["record_summary"] = detail or f"{indicator_name} 样例预览"
    if sample["value"] is None:
        seeded_rng = random.Random(f"source-sample:{raw.get('id') or indicator_name}")
        sample["value"] = round(seeded_rng.uniform(80, 160), 2)
    change_pct = sample.get("change_pct")
    if isinstance(change_pct, (int, float)):
        if change_pct <= -1.5:
            sample["status"] = "warning"
        elif change_pct < 0:
            sample["status"] = "attention"
        else:
            sample["status"] = "good"
    return sample


def build_market_dashboard_response_mapping(raw, sample):
    return {
        "value_path": "value",
        "time_path": "timestamp",
        "status_path": "status",
        "connector_type": sample.get("connector_type") or "",
        "extractor_type": sample.get("extractor_type") or "",
        "extractor_path": str(raw.get("extractor_path") or "").strip(),
        "expected_contains": str(raw.get("expected_contains") or "").strip(),
        "request_blueprint": {
            "api_url": str(raw.get("api_url") or "").strip(),
            "request_method": str(raw.get("request_method") or "GET").strip().upper(),
            "notes": str(raw.get("notes") or "").strip(),
        },
        "discovered_paths": discover_payload_paths(sample),
    }


def build_indicator_source_seed_payload(raw, existing=None):
    api_url = str(raw.get("api_url") or "").strip()
    base_url, path, url_query = split_endpoint_url(api_url)
    headers = safe_json_loads(raw.get("headers_json"), {})
    body = safe_json_loads(raw.get("payload_json"), {})
    sample = build_source_sample_from_market_dashboard(raw)
    generated_mapping = build_market_dashboard_response_mapping(raw, sample)
    existing = existing or {}
    existing_mapping = existing.get("response_mapping") if isinstance(existing.get("response_mapping"), dict) else {}
    mapping = dict(generated_mapping)
    for key in ("value_path", "time_path", "status_path", "unit_override", "default_status", "transform_expr"):
        if existing_mapping.get(key):
            mapping[key] = existing_mapping[key]
    if existing_mapping.get("request_blueprint"):
        mapping["request_blueprint"] = existing_mapping["request_blueprint"]
    response_sample = existing.get("response_sample") if isinstance(existing.get("response_sample"), dict) and existing.get("response_sample") else sample
    source_code = slugify_code(raw.get("id") or f"{raw.get('indicator')}_source", "source")
    indicator_code = slugify_code(raw.get("id") or raw.get("indicator"), "lake_indicator")
    if api_url.startswith("akshare://"):
        base_url = existing.get("base_url") or ""
        path = existing.get("path") or ""
    return {
        "source_code": source_code,
        "indicator_code": indicator_code,
        "provider": str(raw.get("provider") or existing.get("provider") or "market_dashboard").strip(),
        "base_url": existing.get("base_url") or base_url,
        "path": existing.get("path") or path,
        "method": str(existing.get("method") or raw.get("request_method") or "GET").strip().upper(),
        "auth_type": str(existing.get("auth_type") or "none").strip(),
        "headers": existing.get("headers") if isinstance(existing.get("headers"), dict) and existing.get("headers") else headers,
        "query": existing.get("query") if isinstance(existing.get("query"), dict) and existing.get("query") else url_query,
        "body": existing.get("body") if isinstance(existing.get("body"), dict) and existing.get("body") else body,
        "response_mapping": mapping,
        "response_sample": response_sample,
        "source_status": str(existing.get("source_status") or raw.get("status") or "configured").strip(),
        "enabled": bool(existing.get("enabled", raw.get("enabled", True))),
        "last_test_status": str(existing.get("last_test_status") or raw.get("last_test_status") or "").strip(),
        "last_http_status": existing.get("last_http_status") if existing and existing.get("last_http_status") is not None else (200 if "200" in str(raw.get("last_test_status") or "") else None),
        "last_tested_at": str(existing.get("last_tested_at") or raw.get("last_tested_at") or "").strip(),
        "last_test_detail": str(existing.get("last_test_detail") or raw.get("last_test_detail") or raw.get("notes") or "").strip(),
    }


def suggest_mapping_from_payload(payload):
    paths = discover_payload_paths(payload)
    def pick(candidate_keys, fallback):
        for path in paths:
            tail = path.split(".")[-1].lower()
            if tail in candidate_keys:
                return path
        return fallback
    return {
        "value_path": pick({"value", "close", "price", "latest_value"}, "value"),
        "time_path": pick({"timestamp", "time", "date", "point_time"}, "timestamp"),
        "status_path": pick({"status", "state", "point_status"}, "status"),
    }


def build_indicator_source_preview(source_code):
    source = get_indicator_source_def(source_code)
    if not source:
        raise ValueError("indicator_source_not_found")
    sample_payload = source.get("response_sample") if isinstance(source.get("response_sample"), dict) else {}
    response_mapping = source.get("response_mapping") if isinstance(source.get("response_mapping"), dict) else {}
    suggested_mapping = suggest_mapping_from_payload(sample_payload)
    rules = list_indicator_mapping_rules(source_code=source["source_code"])
    current_rule = rules[0] if rules else None
    endpoint = f"{source.get('base_url') or ''}{source.get('path') or ''}".strip() or "未配置真实地址"
    return {
        "source_code": source["source_code"],
        "indicator_code": source["indicator_code"],
        "provider": source.get("provider") or "",
        "method": source.get("method") or "GET",
        "endpoint": endpoint,
        "connector_type": response_mapping.get("connector_type") or ("http" if str(source.get("base_url") or "").startswith(("http://", "https://")) else "sample"),
        "blueprint": {
            "extractor_type": response_mapping.get("extractor_type") or "",
            "extractor_path": response_mapping.get("extractor_path") or "",
            "expected_contains": response_mapping.get("expected_contains") or "",
            "request_blueprint": response_mapping.get("request_blueprint") if isinstance(response_mapping.get("request_blueprint"), dict) else {},
        },
        "sample_payload": sample_payload,
        "sample_payload_text": json.dumps(sample_payload, ensure_ascii=False, indent=2),
        "discovered_paths": discover_payload_paths(sample_payload)[:40],
        "suggested_mapping": {
            "value_path": response_mapping.get("value_path") or suggested_mapping["value_path"],
            "time_path": response_mapping.get("time_path") or suggested_mapping["time_path"],
            "status_path": response_mapping.get("status_path") or suggested_mapping["status_path"],
        },
        "mapping_rule": current_rule,
        "last_test_status": source.get("last_test_status") or "",
        "last_test_detail": source.get("last_test_detail") or "",
    }


def infer_source_connector_type(source):
    response_mapping = source.get("response_mapping") if isinstance(source.get("response_mapping"), dict) else {}
    connector_type = str(response_mapping.get("connector_type") or "").strip().lower()
    if connector_type:
        return connector_type
    request_blueprint = response_mapping.get("request_blueprint") if isinstance(response_mapping.get("request_blueprint"), dict) else {}
    api_url = str(request_blueprint.get("api_url") or "").strip()
    base_url = str(source.get("base_url") or "").strip()
    if api_url.startswith("akshare://"):
        return "akshare"
    if api_url.startswith(("http://", "https://")) or base_url.startswith(("http://", "https://")):
        return "http"
    return "manual"


def build_source_payload_from_text(source, raw_text):
    response_mapping = source.get("response_mapping") if isinstance(source.get("response_mapping"), dict) else {}
    base_sample = copy.deepcopy(source.get("response_sample")) if isinstance(source.get("response_sample"), dict) else {}
    payload = base_sample if isinstance(base_sample, dict) else {}
    payload.setdefault("indicator", source.get("indicator_code") or source.get("source_code") or "指标")
    payload.setdefault("provider", source.get("provider") or "")
    payload.setdefault("status", "attention")
    payload.setdefault("timestamp", now_ts())
    payload["raw_preview"] = str(raw_text or "")[:1200]
    quoted = extract_quoted_payload(raw_text)
    extractor_type = str(response_mapping.get("extractor_type") or payload.get("extractor_type") or "").strip().lower()
    text = quoted or str(raw_text or "").strip()
    delimiter = "~" if "~" in text else ("," if "," in text else "")
    if extractor_type == "text" and delimiter:
        fields = [part.strip() for part in text.split(delimiter)]
        payload["raw_delimiter"] = delimiter
        payload["raw_field_count"] = len(fields)
        payload["raw_fields"] = fields[:40]
        payload["timestamp"] = extract_timestamp_from_fields(fields, fallback=payload.get("timestamp") or now_ts())
        if delimiter == "~":
            payload["name"] = fields[1] if len(fields) > 1 else payload.get("indicator")
            payload["symbol"] = fields[2] if len(fields) > 2 else source.get("source_code")
            if coerce_float(fields[3] if len(fields) > 3 else None, None) is not None:
                payload["value"] = coerce_float(fields[3], payload.get("value"))
            payload["change"] = coerce_float(fields[31] if len(fields) > 31 else None, payload.get("change"))
            payload["change_pct"] = coerce_float(fields[32] if len(fields) > 32 else None, payload.get("change_pct"))
            payload["high"] = coerce_float(fields[33] if len(fields) > 33 else None, payload.get("high"))
            payload["low"] = coerce_float(fields[34] if len(fields) > 34 else None, payload.get("low"))
        else:
            if coerce_float(fields[0] if len(fields) > 0 else None, None) is not None:
                payload["value"] = coerce_float(fields[0], payload.get("value"))
            payload["change_pct"] = coerce_float(fields[1] if len(fields) > 1 else None, payload.get("change_pct"))
            payload["open"] = coerce_float(fields[2] if len(fields) > 2 else None, payload.get("open"))
            payload["high"] = coerce_float(fields[4] if len(fields) > 4 else None, payload.get("high"))
            payload["low"] = coerce_float(fields[5] if len(fields) > 5 else None, payload.get("low"))
            payload["name"] = fields[-1] if fields else payload.get("indicator")
    elif text:
        payload["record_summary"] = text[:240]
    if payload.get("value") is None:
        payload["value"] = round(random.Random(f"landing:{source.get('source_code')}").uniform(80, 160), 2)
    change_pct = coerce_float(payload.get("change_pct"), None)
    if change_pct is not None:
        payload["status"] = "warning" if change_pct <= -1.5 else ("attention" if change_pct < 0 else "good")
    return payload


def build_source_payload_from_live_response(source, raw_text):
    text = str(raw_text or "").strip()
    if text.startswith("{") or text.startswith("["):
        parsed = safe_json_loads(text, {})
        if isinstance(parsed, dict):
            parsed.setdefault("timestamp", now_ts())
            parsed.setdefault("status", "attention")
            return parsed
    return build_source_payload_from_text(source, text)


def persist_indicator_raw_record(source, raw_payload, fetch_mode, http_status=None, success=True, summary=""):
    timestamp = now_ts()
    batch_code = f"raw_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    db = get_db()
    payload_text = raw_payload if isinstance(raw_payload, str) else json.dumps(raw_payload, ensure_ascii=False)
    db.execute(
        """
        INSERT INTO indicator_raw_records (
            source_code, indicator_code, fetch_mode, raw_payload, http_status, success, fetched_at, batch_code, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source["source_code"],
            source["indicator_code"],
            fetch_mode,
            payload_text,
            http_status,
            1 if success else 0,
            timestamp,
            batch_code,
            timestamp,
        ),
    )
    db.execute(
        """
        INSERT INTO indicator_load_batches (
            batch_code, load_type, source_code, summary, total_points, total_indicators, success, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_code,
            "raw_landing",
            source["source_code"],
            (summary or f"已执行 {fetch_mode} 接入，原始数据已落地区。")[:240],
            1,
            1,
            1 if success else 0,
            timestamp,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM indicator_raw_records ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def execute_indicator_source_landing(source_code, prefer_live=False):
    source = get_indicator_source_def(source_code)
    if not source:
        raise ValueError("indicator_source_not_found")
    connector_type = infer_source_connector_type(source)
    response_mapping = source.get("response_mapping") if isinstance(source.get("response_mapping"), dict) else {}
    if connector_type == "http" and prefer_live and str(source.get("base_url") or "").strip():
        url = source["base_url"].rstrip("/") + "/" + source["path"].lstrip("/")
        query = source["query"] if isinstance(source["query"], dict) else {}
        if query:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}" + "&".join(f"{key}={value}" for key, value in query.items())
        body_data = None
        if source["method"] != "GET":
            body_data = json.dumps(source["body"], ensure_ascii=False).encode("utf-8")
        headers = source["headers"] if isinstance(source["headers"], dict) else {}
        if body_data is not None:
            headers = {**headers, "Content-Type": "application/json"}
        try:
            with urlopen(Request(url, data=body_data, method=source["method"], headers=headers), timeout=8) as resp:
                raw_text = resp.read().decode("utf-8", errors="ignore")
                payload = build_source_payload_from_live_response(source, raw_text)
                status_code = getattr(resp, "status", 200)
                record = persist_indicator_raw_record(
                    source,
                    payload,
                    fetch_mode="http_live",
                    http_status=status_code,
                    success=True,
                    summary=f"HTTP 实时接入成功，状态码 {status_code}。",
                )
                return {
                    "record": record,
                    "connector_type": connector_type,
                    "fetch_mode": "http_live",
                    "detail": "HTTP 实时接入成功。",
                    "used_sample": False,
                }
        except Exception as exc:
            fallback_payload = source.get("response_sample") if isinstance(source.get("response_sample"), dict) else {}
            fallback_payload = fallback_payload or {
                "value": round(random.uniform(80, 160), 2),
                "timestamp": now_ts(),
                "status": "attention",
                "fallback_reason": str(exc),
            }
            record = persist_indicator_raw_record(
                source,
                fallback_payload,
                fetch_mode="http_fallback_sample",
                http_status=None,
                success=False,
                summary=f"HTTP 实时接入失败，已回退样例：{str(exc)[:120]}",
            )
            return {
                "record": record,
                "connector_type": connector_type,
                "fetch_mode": "http_fallback_sample",
                "detail": f"HTTP 实时接入失败，已回退样例：{exc}",
                "used_sample": True,
            }
    sample_payload = source.get("response_sample") if isinstance(source.get("response_sample"), dict) else {}
    sample_payload = copy.deepcopy(sample_payload) if sample_payload else {
        "value": round(random.uniform(80, 160), 2),
        "timestamp": now_ts(),
        "status": "attention",
    }
    sample_payload.setdefault("timestamp", now_ts())
    sample_payload.setdefault("status", "attention")
    if connector_type == "http":
        fetch_mode = "http_blueprint_sample"
        summary = "HTTP Source 当前按蓝图样例入湖，可在下一步切换到真实实时接入。"
    elif connector_type == "akshare":
        sample_payload.setdefault("record_summary", str(source.get("last_test_detail") or "AKShare 蓝图样例"))
        fetch_mode = "akshare_blueprint"
        summary = "AKShare Source 当前按蓝图样例入湖，后续接真实执行器。"
    else:
        fetch_mode = "manual_blueprint"
        summary = "Manual Source 已按样例原始数据落地区。"
    record = persist_indicator_raw_record(source, sample_payload, fetch_mode=fetch_mode, http_status=200, success=True, summary=summary)
    return {
        "record": record,
        "connector_type": connector_type,
        "fetch_mode": fetch_mode,
        "detail": summary,
        "used_sample": True,
    }


def parse_numeric_indicator_value(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        value = float(raw_value)
        return value if math.isfinite(value) else None
    text = str(raw_value or "").strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        value = float(match.group(0))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def normalize_selected_indicator_refs(raw_selected):
    items = raw_selected if isinstance(raw_selected, list) else []
    normalized = []
    seen = set()
    for raw in items:
        if isinstance(raw, dict):
            indicator_code = slugify_code(raw.get("indicator_code") or raw.get("code"), "indicator")
            indicator_name = str(raw.get("indicator_name") or raw.get("name") or indicator_code).strip() or indicator_code
        else:
            indicator_code = slugify_code(raw, "indicator")
            indicator_name = indicator_code
        if not indicator_code or indicator_code in seen:
            continue
        seen.add(indicator_code)
        normalized.append({"indicator_code": indicator_code, "indicator_name": indicator_name})
    return normalized


def extract_json_payload_from_text(raw_text):
    text = str(raw_text or "").strip()
    if not text:
        return {}
    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced_match:
        text = fenced_match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_smart_indicator_expression_fallback(prompt_text, selected_indicators):
    prompt = str(prompt_text or "").strip()
    items = normalize_selected_indicator_refs(selected_indicators)
    if not items:
        raise ValueError("selected_indicators_required")
    expression = prompt.replace("（", "(").replace("）", ")").replace("【", "[[").replace("】", "]]")
    expression = expression.replace("×", "*").replace("÷", "/")
    replaced = False
    for item in sorted(items, key=lambda current: len(current["indicator_name"]), reverse=True):
        code = item["indicator_code"]
        name = item["indicator_name"]
        token = f'Number(inputs["{code}"] || 0)'
        bracket_token = f"[[{name}]]"
        if bracket_token in expression:
            expression = expression.replace(bracket_token, token)
            replaced = True
        plain_pattern = re.compile(re.escape(name))
        if plain_pattern.search(expression):
            expression = plain_pattern.sub(token, expression)
            replaced = True
    if not replaced:
        first_token = f'Number(inputs["{items[0]["indicator_code"]}"] || 0)'
        if re.match(r"^[\+\-\*\/]", expression):
            expression = f"{first_token}{expression}"
        elif len(items) == 1:
            expression = first_token
        elif "/" in expression:
            second_token = f'Number(inputs["{items[1]["indicator_code"]}"] || 0)'
            expression = f"{first_token} / ({second_token} + 0.000001)"
        else:
            second_token = f'Number(inputs["{items[1]["indicator_code"]}"] || 0)'
            expression = f"{first_token} + {second_token}"
    expression = expression.strip()
    if not expression:
        raise ValueError("smart_indicator_expression_empty")
    if re.search(r"[^0-9A-Za-z_\.\+\-\*\/\(\)\[\]\"'\s|]", expression):
        raise ValueError("smart_indicator_expression_unsafe")
    return expression


def build_smart_indicator_js_fallback(prompt_text, selected_indicators):
    return f"return {build_smart_indicator_expression_fallback(prompt_text, selected_indicators)};"


def validate_smart_indicator_js(js_code, selected_indicators):
    code = str(js_code or "").strip()
    if not code:
        return ""
    if not code.startswith("return "):
        code = f"return {code.lstrip(';')}"
    if not code.endswith(";"):
        code = f"{code};"
    normalized = code.replace("\n", " ").strip()
    allowed_codes = {item["indicator_code"] for item in normalize_selected_indicator_refs(selected_indicators)}
    for token in re.findall(r'inputs\[(?:"|\')([^"\']+)(?:"|\')\]', normalized):
        if slugify_code(token, "indicator") not in allowed_codes:
            raise ValueError("smart_indicator_js_contains_unknown_indicator")
    if re.search(r"[^0-9A-Za-z_\.\+\-\*\/\(\)\[\]\"'\s|;]", normalized):
        raise ValueError("smart_indicator_js_unsafe")
    return normalized


def generate_smart_indicator_js(indicator_name, prompt_text, selected_indicators, tenant_slug=""):
    normalized_selected = normalize_selected_indicator_refs(selected_indicators)
    fallback_js = build_smart_indicator_js_fallback(prompt_text, normalized_selected)
    model = get_default_llm_config(purpose="general")
    if not model:
        return {"formula_js": fallback_js, "generator": "fallback", "llm_used": False}
    try:
        raw = call_openai_compatible_llm(
            model,
            (
                "你是金融指标公式编译器。"
                "只返回 JSON。字段必须包含 formula_js。"
                "formula_js 必须是单行 JavaScript return 语句，只能使用 Number(inputs[\"indicator_code\"] || 0) 和 + - * / ()。"
            ),
            json.dumps(
                {
                    "indicator_name": indicator_name,
                    "tenant_slug": tenant_slug,
                    "prompt_text": str(prompt_text or "").strip(),
                    "selected_indicators": normalized_selected,
                    "fallback_formula_js": fallback_js,
                },
                ensure_ascii=False,
            ),
            feature_code="smart_indicator_formula_generation",
            feature_label="智能指标公式生成",
            tenant_slug=tenant_slug,
            entry_point="dashboard_smart_indicator",
            metadata={"indicator_name": indicator_name, "selected_indicator_count": len(normalized_selected)},
            request_timeout_seconds=45,
        )
        parsed = extract_json_payload_from_text(raw)
        formula_js = validate_smart_indicator_js(parsed.get("formula_js"), normalized_selected)
        if not formula_js:
            raise ValueError("llm_formula_js_missing")
        return {"formula_js": formula_js, "generator": "llm", "llm_used": True}
    except Exception:
        return {"formula_js": fallback_js, "generator": "fallback", "llm_used": False}


def evaluate_smart_indicator_formula_js(formula_js, selected_indicators, latest_value_map):
    code = validate_smart_indicator_js(formula_js, selected_indicators)
    expression = re.sub(r"^\s*return\s+", "", code).rstrip(" ;")
    for item in normalize_selected_indicator_refs(selected_indicators):
        indicator_code = item["indicator_code"]
        latest = latest_value_map.get(indicator_code) or {}
        numeric_value = parse_numeric_indicator_value(latest.get("latest_value"))
        numeric_text = str(0.0 if numeric_value is None else numeric_value)
        expression = expression.replace(f'Number(inputs["{indicator_code}"] || 0)', numeric_text)
        expression = expression.replace(f"inputs[\"{indicator_code}\"]", numeric_text)
        expression = expression.replace(f"inputs['{indicator_code}']", numeric_text)
    expression = expression.replace("|| 0", "").replace("||0", "")
    if re.search(r"[^0-9\.\+\-\*\/\(\)\s]", expression):
        raise ValueError("smart_indicator_expression_eval_unsafe")
    result = eval(expression, {"__builtins__": {}}, {})
    value = float(result)
    if not math.isfinite(value):
        raise ValueError("smart_indicator_expression_not_finite")
    return round(value, 4)


def normalize_indicator_definition(payload, existing=None):
    base = dict(existing or {})
    base.update(payload or {})
    tenant_slug = str(base.get("tenant_slug") or "").strip().lower()
    source_type = str(base.get("source_type") or "mock").strip() or "mock"
    code_seed = base.get("indicator_code") or base.get("indicator_name")
    if tenant_slug and source_type == "smart" and not base.get("indicator_code"):
        code_seed = f"{tenant_slug}_{code_seed or 'smart_indicator'}"
    code = slugify_code(code_seed, "indicator")
    selected_indicators = normalize_selected_indicator_refs(
        base.get("selected_indicators")
        if isinstance(base.get("selected_indicators"), list)
        else safe_json_loads(base.get("selected_indicators_json"), [])
    )
    return {
        "indicator_code": code,
        "tenant_slug": tenant_slug,
        "indicator_name": str(base.get("indicator_name") or code).strip(),
        "category": str(base.get("category") or "未分类指标").strip(),
        "description": str(base.get("description") or "").strip(),
        "unit": str(base.get("unit") or "").strip(),
        "owner": str(base.get("owner") or "平台研究运营").strip(),
        "source_type": source_type,
        "source_type_label": str(base.get("source_type_label") or "模拟指标").strip() or "模拟指标",
        "provider": str(base.get("provider") or "平台数据层").strip(),
        "status_hint": str(base.get("status_hint") or "attention").strip() or "attention",
        "assessment_template": str(base.get("assessment_template") or "").strip(),
        "alert_template": str(base.get("alert_template") or "").strip(),
        "prompt_text": str(base.get("prompt_text") or "").strip(),
        "formula_js": str(base.get("formula_js") or "").strip(),
        "selected_indicators_json": json.dumps(selected_indicators, ensure_ascii=False),
        "display_order": int(base.get("display_order") or 0),
        "watchers_json": json.dumps(base.get("watchers") if isinstance(base.get("watchers"), list) else safe_json_loads(base.get("watchers_json"), []), ensure_ascii=False),
        "display_config_json": json.dumps(base.get("display_config") if isinstance(base.get("display_config"), dict) else safe_json_loads(base.get("display_config_json"), {}), ensure_ascii=False),
        "enabled": 1 if bool(base.get("enabled", True)) else 0,
    }


def normalize_indicator_source_def(payload, existing=None):
    base = dict(existing or {})
    base.update(payload or {})
    indicator_code = slugify_code(base.get("indicator_code"), "indicator")
    source_code = slugify_code(base.get("source_code") or f"{indicator_code}_source", "source")
    method = str(base.get("method") or "GET").strip().upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        method = "GET"
    return {
        "source_code": source_code,
        "indicator_code": indicator_code,
        "provider": str(base.get("provider") or "待配置").strip(),
        "base_url": str(base.get("base_url") or "").strip(),
        "path": str(base.get("path") or "").strip(),
        "method": method,
        "auth_type": str(base.get("auth_type") or "none").strip(),
        "headers_json": json.dumps(base.get("headers") if isinstance(base.get("headers"), dict) else safe_json_loads(base.get("headers_json"), {}), ensure_ascii=False),
        "query_json": json.dumps(base.get("query") if isinstance(base.get("query"), dict) else safe_json_loads(base.get("query_json"), {}), ensure_ascii=False),
        "body_json": json.dumps(base.get("body") if isinstance(base.get("body"), dict) else safe_json_loads(base.get("body_json"), {}), ensure_ascii=False),
        "response_mapping_json": json.dumps(base.get("response_mapping") if isinstance(base.get("response_mapping"), dict) else safe_json_loads(base.get("response_mapping_json"), {}), ensure_ascii=False),
        "response_sample_json": json.dumps(base.get("response_sample") if isinstance(base.get("response_sample"), dict) else safe_json_loads(base.get("response_sample_json"), {}), ensure_ascii=False),
        "source_status": str(base.get("source_status") or "draft").strip() or "draft",
        "enabled": 1 if bool(base.get("enabled", True)) else 0,
        "last_test_status": str(base.get("last_test_status") or "").strip(),
        "last_http_status": base.get("last_http_status"),
        "last_tested_at": str(base.get("last_tested_at") or "").strip(),
        "last_test_detail": str(base.get("last_test_detail") or "").strip(),
    }


def row_to_indicator_definition(row):
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    item["watchers"] = safe_json_loads(item.get("watchers_json"), [])
    item["display_config"] = safe_json_loads(item.get("display_config_json"), {})
    item["selected_indicators"] = normalize_selected_indicator_refs(safe_json_loads(item.get("selected_indicators_json"), []))
    return item


def row_to_indicator_source_def(row):
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    item["headers"] = safe_json_loads(item.get("headers_json"), {})
    item["query"] = safe_json_loads(item.get("query_json"), {})
    item["body"] = safe_json_loads(item.get("body_json"), {})
    item["response_mapping"] = safe_json_loads(item.get("response_mapping_json"), {})
    item["response_sample"] = safe_json_loads(item.get("response_sample_json"), {})
    return item


def list_indicator_definitions(source_type=None, tenant_slug=None, include_shared=True):
    db = get_db()
    query = "SELECT * FROM indicator_definitions"
    params = []
    filters = []
    if source_type:
        filters.append("source_type = ?")
        params.append(source_type)
    normalized_tenant_slug = str(tenant_slug or "").strip().lower()
    if normalized_tenant_slug:
        if include_shared:
            filters.append("(tenant_slug = ? OR tenant_slug = '')")
        else:
            filters.append("tenant_slug = ?")
        params.append(normalized_tenant_slug)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY category ASC, indicator_name ASC"
    return [row_to_indicator_definition(row) for row in db.execute(query, params).fetchall()]


def get_indicator_definition(indicator_code):
    if not indicator_code:
        return None
    db = get_db()
    row = db.execute(
        "SELECT * FROM indicator_definitions WHERE indicator_code = ?",
        (slugify_code(indicator_code, "indicator"),),
    ).fetchone()
    return row_to_indicator_definition(row) if row else None


def save_indicator_definition(payload):
    normalized = normalize_indicator_definition(payload)
    db = get_db()
    existing = get_indicator_definition(normalized["indicator_code"])
    timestamp = now_ts()
    db.execute(
        """
        INSERT INTO indicator_definitions (
            indicator_code, indicator_name, tenant_slug, category, description, unit, owner, source_type,
            source_type_label, provider, status_hint, assessment_template, alert_template, prompt_text,
            formula_js, selected_indicators_json, display_order, watchers_json, display_config_json,
            enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(indicator_code) DO UPDATE SET
            indicator_name = excluded.indicator_name,
            tenant_slug = excluded.tenant_slug,
            category = excluded.category,
            description = excluded.description,
            unit = excluded.unit,
            owner = excluded.owner,
            source_type = excluded.source_type,
            source_type_label = excluded.source_type_label,
            provider = excluded.provider,
            status_hint = excluded.status_hint,
            assessment_template = excluded.assessment_template,
            alert_template = excluded.alert_template,
            prompt_text = excluded.prompt_text,
            formula_js = excluded.formula_js,
            selected_indicators_json = excluded.selected_indicators_json,
            display_order = excluded.display_order,
            watchers_json = excluded.watchers_json,
            display_config_json = excluded.display_config_json,
            enabled = excluded.enabled,
            updated_at = excluded.updated_at
        """,
        (
            normalized["indicator_code"],
            normalized["indicator_name"],
            normalized["tenant_slug"],
            normalized["category"],
            normalized["description"],
            normalized["unit"],
            normalized["owner"],
            normalized["source_type"],
            normalized["source_type_label"],
            normalized["provider"],
            normalized["status_hint"],
            normalized["assessment_template"],
            normalized["alert_template"],
            normalized["prompt_text"],
            normalized["formula_js"],
            normalized["selected_indicators_json"],
            normalized["display_order"],
            normalized["watchers_json"],
            normalized["display_config_json"],
            normalized["enabled"],
            existing["created_at"] if existing else timestamp,
            timestamp,
        ),
    )
    db.commit()
    invalidate_indicator_hub_cache()
    return get_indicator_definition(normalized["indicator_code"])


def delete_indicator_definition(indicator_code):
    db = get_db()
    normalized_code = slugify_code(indicator_code, "indicator")
    db.execute("DELETE FROM indicator_definitions WHERE indicator_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_source_defs WHERE indicator_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_latest_values WHERE indicator_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_series WHERE indicator_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_anomalies WHERE indicator_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_kline_points WHERE indicator_code = ?", (normalized_code,))
    db.commit()
    invalidate_indicator_hub_cache()


def list_indicator_source_defs(indicator_code=None):
    db = get_db()
    query = "SELECT * FROM indicator_source_defs"
    params = []
    if indicator_code:
        query += " WHERE indicator_code = ?"
        params.append(slugify_code(indicator_code, "indicator"))
    query += " ORDER BY updated_at DESC, source_code ASC"
    return [row_to_indicator_source_def(row) for row in db.execute(query, params).fetchall()]


def get_indicator_source_def(source_code):
    if not source_code:
        return None
    db = get_db()
    row = db.execute(
        "SELECT * FROM indicator_source_defs WHERE source_code = ?",
        (slugify_code(source_code, "source"),),
    ).fetchone()
    return row_to_indicator_source_def(row) if row else None


def save_indicator_source_def(payload):
    normalized = normalize_indicator_source_def(payload)
    db = get_db()
    existing = get_indicator_source_def(normalized["source_code"])
    timestamp = now_ts()
    db.execute(
        """
        INSERT INTO indicator_source_defs (
            source_code, indicator_code, provider, base_url, path, method, auth_type,
            headers_json, query_json, body_json, response_mapping_json, response_sample_json,
            source_status, enabled, last_test_status, last_http_status, last_tested_at,
            last_test_detail, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_code) DO UPDATE SET
            indicator_code = excluded.indicator_code,
            provider = excluded.provider,
            base_url = excluded.base_url,
            path = excluded.path,
            method = excluded.method,
            auth_type = excluded.auth_type,
            headers_json = excluded.headers_json,
            query_json = excluded.query_json,
            body_json = excluded.body_json,
            response_mapping_json = excluded.response_mapping_json,
            response_sample_json = excluded.response_sample_json,
            source_status = excluded.source_status,
            enabled = excluded.enabled,
            last_test_status = excluded.last_test_status,
            last_http_status = excluded.last_http_status,
            last_tested_at = excluded.last_tested_at,
            last_test_detail = excluded.last_test_detail,
            updated_at = excluded.updated_at
        """,
        (
            normalized["source_code"],
            normalized["indicator_code"],
            normalized["provider"],
            normalized["base_url"],
            normalized["path"],
            normalized["method"],
            normalized["auth_type"],
            normalized["headers_json"],
            normalized["query_json"],
            normalized["body_json"],
            normalized["response_mapping_json"],
            normalized["response_sample_json"],
            normalized["source_status"],
            normalized["enabled"],
            normalized["last_test_status"],
            normalized["last_http_status"],
            normalized["last_tested_at"],
            normalized["last_test_detail"],
            existing["created_at"] if existing else timestamp,
            timestamp,
        ),
    )
    db.commit()
    invalidate_indicator_hub_cache()
    saved = get_indicator_source_def(normalized["source_code"])
    ensure_indicator_mapping_rule_for_source(saved)
    return saved


def delete_indicator_source_def(source_code):
    db = get_db()
    normalized_code = slugify_code(source_code, "source")
    db.execute("DELETE FROM indicator_source_defs WHERE source_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_source_tests WHERE source_code = ?", (normalized_code,))
    db.commit()
    invalidate_indicator_hub_cache()


def record_indicator_source_test(source_code, success, http_status=None, latency_ms=None, response_sample="", error_message=""):
    db = get_db()
    timestamp = now_ts()
    normalized_code = slugify_code(source_code, "source")
    db.execute(
        """
        INSERT INTO indicator_source_tests (
            source_code, tested_at, success, http_status, latency_ms, response_sample, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_code,
            timestamp,
            1 if success else 0,
            http_status,
            latency_ms,
            response_sample[:4000],
            error_message[:1000],
        ),
    )
    db.execute(
        """
        UPDATE indicator_source_defs
        SET last_test_status = ?, last_http_status = ?, last_tested_at = ?, last_test_detail = ?, updated_at = ?
        WHERE source_code = ?
        """,
        (
            f"HTTP {http_status}" if http_status else ("SUCCESS" if success else "FAILED"),
            http_status,
            timestamp,
            (error_message or response_sample or "测试完成")[:240],
            timestamp,
            normalized_code,
        ),
    )
    db.commit()
    invalidate_indicator_hub_cache()


def list_indicator_source_tests(source_code=None, limit=20):
    db = get_db()
    limit = max(1, min(int(limit or 20), 100))
    if source_code:
        rows = db.execute(
            """
            SELECT * FROM indicator_source_tests
            WHERE source_code = ?
            ORDER BY tested_at DESC, id DESC
            LIMIT ?
            """,
            (slugify_code(source_code, "source"), limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM indicator_source_tests
            ORDER BY tested_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def test_indicator_source(source_code):
    source = get_indicator_source_def(source_code)
    if not source:
        raise ValueError("indicator_source_not_found")
    start = time.time()
    if not source["base_url"]:
        sample = source["response_sample"] or {"message": "未配置真实地址，使用样例响应作为测试结果。"}
        latency_ms = int((time.time() - start) * 1000)
        sample_text = json.dumps(sample, ensure_ascii=False)
        record_indicator_source_test(source["source_code"], True, 200, latency_ms, sample_text, "")
        return {
            "success": True,
            "http_status": 200,
            "latency_ms": latency_ms,
            "response_sample": sample,
            "detail": "当前未配置真实接口地址，已使用样例响应完成测试。",
        }
    url = source["base_url"].rstrip("/") + "/" + source["path"].lstrip("/")
    query = source["query"] if isinstance(source["query"], dict) else {}
    if query:
        separator = "&" if "?" in url else "?"
        query_string = "&".join(f"{key}={value}" for key, value in query.items())
        url = f"{url}{separator}{query_string}"
    body_data = None
    if source["method"] != "GET":
        body_data = json.dumps(source["body"], ensure_ascii=False).encode("utf-8")
    headers = source["headers"] if isinstance(source["headers"], dict) else {}
    if body_data is not None:
        headers = {**headers, "Content-Type": "application/json"}
    request_obj = Request(url, data=body_data, method=source["method"], headers=headers)
    try:
        with urlopen(request_obj, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            latency_ms = int((time.time() - start) * 1000)
            status_code = getattr(resp, "status", 200)
            record_indicator_source_test(source["source_code"], True, status_code, latency_ms, raw, "")
            sample = safe_json_loads(raw, {}) if raw.strip().startswith(("{", "[")) else {"raw": raw[:1200]}
            return {
                "success": True,
                "http_status": status_code,
                "latency_ms": latency_ms,
                "response_sample": sample,
                "detail": "接口测试成功。",
            }
    except HTTPError as exc:
        latency_ms = int((time.time() - start) * 1000)
        error_text = f"HTTP {exc.code}: {exc.reason}"
        record_indicator_source_test(source["source_code"], False, exc.code, latency_ms, "", error_text)
        return {
            "success": False,
            "http_status": exc.code,
            "latency_ms": latency_ms,
            "response_sample": {},
            "detail": error_text,
        }
    except URLError as exc:
        latency_ms = int((time.time() - start) * 1000)
        error_text = f"NETWORK ERROR: {exc.reason}"
        record_indicator_source_test(source["source_code"], False, None, latency_ms, "", error_text)
        return {
            "success": False,
            "http_status": None,
            "latency_ms": latency_ms,
            "response_sample": {},
            "detail": error_text,
        }
    except Exception as exc:
        latency_ms = int((time.time() - start) * 1000)
        error_text = f"UNEXPECTED ERROR: {exc}"
        record_indicator_source_test(source["source_code"], False, None, latency_ms, "", error_text)
        return {
            "success": False,
            "http_status": None,
            "latency_ms": latency_ms,
            "response_sample": {},
            "detail": error_text,
        }


def normalize_indicator_mapping_rule(payload, existing=None):
    base = dict(existing or {})
    base.update(payload or {})
    indicator_code = slugify_code(base.get("indicator_code"), "indicator")
    source_code = slugify_code(base.get("source_code"), "source")
    rule_code = slugify_code(base.get("rule_code") or f"{indicator_code}_{source_code}_rule", "rule")
    return {
        "rule_code": rule_code,
        "indicator_code": indicator_code,
        "source_code": source_code,
        "value_path": str(base.get("value_path") or "").strip(),
        "time_path": str(base.get("time_path") or "").strip(),
        "status_path": str(base.get("status_path") or "").strip(),
        "unit_override": str(base.get("unit_override") or "").strip(),
        "default_status": str(base.get("default_status") or "attention").strip() or "attention",
        "transform_expr": str(base.get("transform_expr") or "").strip(),
        "enabled": 1 if bool(base.get("enabled", True)) else 0,
    }


def row_to_indicator_mapping_rule(row):
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    return item


def list_indicator_mapping_rules(indicator_code=None, source_code=None):
    db = get_db()
    query = "SELECT * FROM indicator_mapping_rules WHERE 1=1"
    params = []
    if indicator_code:
        query += " AND indicator_code = ?"
        params.append(slugify_code(indicator_code, "indicator"))
    if source_code:
        query += " AND source_code = ?"
        params.append(slugify_code(source_code, "source"))
    query += " ORDER BY updated_at DESC, rule_code ASC"
    return [row_to_indicator_mapping_rule(row) for row in db.execute(query, params).fetchall()]


def get_indicator_mapping_rule(rule_code):
    if not rule_code:
        return None
    db = get_db()
    row = db.execute(
        "SELECT * FROM indicator_mapping_rules WHERE rule_code = ?",
        (slugify_code(rule_code, "rule"),),
    ).fetchone()
    return row_to_indicator_mapping_rule(row) if row else None


def save_indicator_mapping_rule(payload):
    normalized = normalize_indicator_mapping_rule(payload)
    db = get_db()
    existing = get_indicator_mapping_rule(normalized["rule_code"])
    timestamp = now_ts()
    db.execute(
        """
        INSERT INTO indicator_mapping_rules (
            rule_code, indicator_code, source_code, value_path, time_path, status_path,
            unit_override, default_status, transform_expr, enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rule_code) DO UPDATE SET
            indicator_code = excluded.indicator_code,
            source_code = excluded.source_code,
            value_path = excluded.value_path,
            time_path = excluded.time_path,
            status_path = excluded.status_path,
            unit_override = excluded.unit_override,
            default_status = excluded.default_status,
            transform_expr = excluded.transform_expr,
            enabled = excluded.enabled,
            updated_at = excluded.updated_at
        """,
        (
            normalized["rule_code"],
            normalized["indicator_code"],
            normalized["source_code"],
            normalized["value_path"],
            normalized["time_path"],
            normalized["status_path"],
            normalized["unit_override"],
            normalized["default_status"],
            normalized["transform_expr"],
            normalized["enabled"],
            existing["created_at"] if existing else timestamp,
            timestamp,
        ),
    )
    db.commit()
    invalidate_indicator_hub_cache()
    return get_indicator_mapping_rule(normalized["rule_code"])


def ensure_indicator_mapping_rule_for_source(source):
    if not source:
        return None
    existing_rules = list_indicator_mapping_rules(source_code=source["source_code"])
    if existing_rules:
        return existing_rules[0]
    response_mapping = source.get("response_mapping") if isinstance(source.get("response_mapping"), dict) else {}
    return save_indicator_mapping_rule(
        {
            "rule_code": f"{source['indicator_code']}_{source['source_code']}_rule",
            "indicator_code": source["indicator_code"],
            "source_code": source["source_code"],
            "value_path": str(response_mapping.get("value_path") or response_mapping.get("value") or "value").strip(),
            "time_path": str(response_mapping.get("time_path") or response_mapping.get("timestamp") or "timestamp").strip(),
            "status_path": str(response_mapping.get("status_path") or response_mapping.get("status") or "status").strip(),
            "unit_override": str(response_mapping.get("unit_override") or "").strip(),
            "default_status": str(response_mapping.get("default_status") or "attention").strip() or "attention",
            "transform_expr": str(response_mapping.get("transform_expr") or "").strip(),
            "enabled": True,
        }
    )


def delete_indicator_mapping_rule(rule_code):
    db = get_db()
    db.execute("DELETE FROM indicator_mapping_rules WHERE rule_code = ?", (slugify_code(rule_code, "rule"),))
    db.commit()
    invalidate_indicator_hub_cache()


def list_indicator_raw_records(source_code=None, limit=20):
    db = get_db()
    limit = max(1, min(int(limit or 20), 200))
    if source_code:
        rows = db.execute(
            """
            SELECT * FROM indicator_raw_records
            WHERE source_code = ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT ?
            """,
            (slugify_code(source_code, "source"), limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM indicator_raw_records
            ORDER BY fetched_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_indicator_raw_record_from_source(source_code, use_last_test_sample=True):
    source = get_indicator_source_def(source_code)
    if not source:
        raise ValueError("indicator_source_not_found")
    if not use_last_test_sample:
        result = execute_indicator_source_landing(source_code, prefer_live=False)
        return result.get("record")
    tests = list_indicator_source_tests(source_code=source["source_code"], limit=1)
    test_record = tests[0] if tests else None
    if use_last_test_sample and test_record and test_record.get("response_sample"):
        raw_payload = test_record["response_sample"]
        http_status = test_record.get("http_status")
        fetch_mode = "last_test_sample"
        success = bool(test_record.get("success"))
    else:
        result = execute_indicator_source_landing(source_code, prefer_live=False)
        return result.get("record")
    return persist_indicator_raw_record(
        source,
        raw_payload,
        fetch_mode=fetch_mode,
        http_status=http_status,
        success=success,
        summary="已使用最近测试样例写入原始落地区。",
    )


def extract_path_value(payload, path):
    if not path:
        return payload
    current = payload
    for token in [part for part in str(path).split(".") if part]:
        if isinstance(current, dict):
            current = current.get(token)
        elif isinstance(current, list):
            try:
                current = current[int(token)]
            except Exception:
                return None
        else:
            return None
    return current


def run_indicator_clean_job(source_code=None, rule_code=None, raw_record_id=None):
    db = get_db()
    if raw_record_id:
        row = db.execute("SELECT * FROM indicator_raw_records WHERE id = ?", (raw_record_id,)).fetchone()
    else:
        row = None
    raw_record = dict(row) if row else None
    resolved_source_code = source_code
    if not resolved_source_code and raw_record:
        resolved_source_code = raw_record.get("source_code")
    source = get_indicator_source_def(resolved_source_code)
    if not source:
        raise ValueError("indicator_source_not_found")
    ensure_indicator_mapping_rule_for_source(source)
    rules = list_indicator_mapping_rules(source_code=source["source_code"])
    rule = get_indicator_mapping_rule(rule_code) if rule_code else (rules[0] if rules else None)
    if not rule:
        raise ValueError("mapping_rule_not_found")
    if raw_record is None:
        row = db.execute(
            "SELECT * FROM indicator_raw_records WHERE source_code = ? ORDER BY fetched_at DESC, id DESC LIMIT 1",
            (source["source_code"],),
        ).fetchone()
    if not row:
        raise ValueError("raw_record_not_found")
    raw_record = dict(row)
    payload = safe_json_loads(raw_record.get("raw_payload"), {})
    if not payload and isinstance(raw_record.get("raw_payload"), str):
        payload = {"raw": raw_record["raw_payload"]}
    job_code = f"clean_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    timestamp = now_ts()
    value = extract_path_value(payload, rule["value_path"]) if rule["value_path"] else payload.get("value", random.randint(70, 150))
    point_time = extract_path_value(payload, rule["time_path"]) if rule["time_path"] else payload.get("timestamp", timestamp)
    status = extract_path_value(payload, rule["status_path"]) if rule["status_path"] else payload.get("status", rule["default_status"])
    try:
        numeric_value = float(value)
    except Exception:
        numeric_value = float(random.randint(70, 150))
    status = str(status or rule["default_status"] or "attention")
    result_payload = {
        "indicator_code": source["indicator_code"],
        "source_code": source["source_code"],
        "point_time": str(point_time)[:19].replace("T", " "),
        "point_value": numeric_value,
        "point_status": status,
    }
    db.execute(
        """
        INSERT INTO indicator_clean_jobs (
            job_code, source_code, indicator_code, raw_record_id, mapping_rule_code,
            job_status, cleaned_points, result_summary, result_payload, error_message,
            created_at, finished_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_code,
            source["source_code"],
            source["indicator_code"],
            raw_record["id"],
            rule["rule_code"],
            "success",
            1,
            "已将原始响应标准化为单点指标数据。",
            json.dumps(result_payload, ensure_ascii=False),
            "",
            timestamp,
            timestamp,
        ),
    )
    batch_code = f"clean_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    db.execute(
        """
        INSERT INTO indicator_series (
            indicator_code, point_time, point_value, point_status, is_simulated, source_code, batch_code, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source["indicator_code"],
            result_payload["point_time"],
            numeric_value,
            status,
            0,
            source["source_code"],
            batch_code,
            timestamp,
        ),
    )
    definition = get_indicator_definition(source["indicator_code"])
    assessment = definition.get("assessment_template") if definition else "已完成标准化入湖。"
    alert = definition.get("alert_template") if definition else "已进入指标湖。"
    db.execute(
        """
        INSERT INTO indicator_latest_values (
            indicator_code, latest_value, latest_status, latest_assessment, latest_alert,
            updated_at, is_simulated, source_code, batch_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(indicator_code) DO UPDATE SET
            latest_value = excluded.latest_value,
            latest_status = excluded.latest_status,
            latest_assessment = excluded.latest_assessment,
            latest_alert = excluded.latest_alert,
            updated_at = excluded.updated_at,
            is_simulated = excluded.is_simulated,
            source_code = excluded.source_code,
            batch_code = excluded.batch_code
        """,
        (
            source["indicator_code"],
            f"{numeric_value:.2f}",
            status,
            assessment,
            alert,
            timestamp,
            0,
            source["source_code"],
            batch_code,
        ),
    )
    db.execute(
        """
        INSERT INTO indicator_load_batches (
            batch_code, load_type, source_code, summary, total_points, total_indicators, success, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_code,
            "clean_job",
            source["source_code"],
            "已从原始记录经映射规则清洗后写入指标湖。",
            1,
            1,
            1,
            timestamp,
        ),
    )
    db.commit()
    invalidate_indicator_hub_cache()
    job_row = db.execute("SELECT * FROM indicator_clean_jobs WHERE job_code = ?", (job_code,)).fetchone()
    return dict(job_row) if job_row else None


def list_indicator_clean_jobs(source_code=None, limit=20):
    db = get_db()
    limit = max(1, min(int(limit or 20), 200))
    if source_code:
        rows = db.execute(
            """
            SELECT * FROM indicator_clean_jobs
            WHERE source_code = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (slugify_code(source_code, "source"), limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM indicator_clean_jobs
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def build_indicator_lake_trace(indicator_code, limit=12):
    normalized_code = slugify_code(indicator_code, "indicator")
    definition = get_indicator_definition(normalized_code)
    if not definition:
        raise ValueError("indicator_not_found")
    db = get_db()
    latest_row = db.execute(
        "SELECT * FROM indicator_latest_values WHERE indicator_code = ?",
        (normalized_code,),
    ).fetchone()
    latest = dict(latest_row) if latest_row else None
    series_rows = db.execute(
        """
        SELECT point_time, point_value, point_status, source_code, batch_code, is_simulated
        FROM indicator_series
        WHERE indicator_code = ?
        ORDER BY point_time DESC, id DESC
        LIMIT ?
        """,
        (normalized_code, limit),
    ).fetchall()
    series = [dict(row) for row in series_rows]
    source_defs = list_indicator_source_defs(indicator_code=normalized_code)
    source_codes = [item["source_code"] for item in source_defs]
    raw_records = []
    clean_jobs = []
    for source_code in source_codes[:6]:
        raw_records.extend(list_indicator_raw_records(source_code=source_code, limit=max(4, limit // 2)))
        clean_jobs.extend(list_indicator_clean_jobs(source_code=source_code, limit=max(4, limit // 2)))
    raw_records = sorted(raw_records, key=lambda item: (item.get("fetched_at") or "", item.get("id") or 0), reverse=True)[:limit]
    clean_jobs = sorted(clean_jobs, key=lambda item: (item.get("created_at") or "", item.get("id") or 0), reverse=True)[:limit]
    recent_batches = [
        dict(row)
        for row in db.execute(
            """
            SELECT * FROM indicator_load_batches
            WHERE source_code IN ({})
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """.format(",".join("?" for _ in source_codes) or "''"),
            [*source_codes, limit] if source_codes else [limit],
        ).fetchall()
    ] if source_codes else []
    timeline = []
    if latest:
        timeline.append(
            {
                "time": latest.get("updated_at") or "",
                "type": "latest",
                "summary": f"最新值 {latest.get('latest_value') or '--'} · {latest.get('latest_status') or '--'}",
            }
        )
    for item in raw_records[:6]:
        timeline.append(
            {
                "time": item.get("fetched_at") or "",
                "type": "raw",
                "summary": f"原始落地 {item.get('fetch_mode') or '--'} · {'成功' if item.get('success') else '失败'}",
            }
        )
    for item in clean_jobs[:6]:
        timeline.append(
            {
                "time": item.get("finished_at") or item.get("created_at") or "",
                "type": "clean",
                "summary": f"清洗任务 {item.get('job_status') or '--'} · 规则 {item.get('mapping_rule_code') or '--'}",
            }
        )
    timeline = sorted(timeline, key=lambda item: item.get("time") or "", reverse=True)[:12]
    return {
        "definition": definition,
        "latest": latest,
        "series": series,
        "source_defs": source_defs,
        "raw_records": raw_records,
        "clean_jobs": clean_jobs,
        "recent_batches": recent_batches,
        "timeline": timeline,
    }


def ensure_default_indicator_sources():
    existing = {item["source_code"] for item in list_indicator_source_defs()}
    imported = 0
    for raw in load_market_dashboard_indicators():
        indicator_name = str(raw.get("indicator", "")).strip()
        if not indicator_name:
            continue
        indicator_code = slugify_code(raw.get("id") or indicator_name, "lake_indicator")
        if not get_indicator_definition(indicator_code):
            save_indicator_definition(
                {
                    "indicator_code": indicator_code,
                    "indicator_name": indicator_name,
                    "category": str(raw.get("category") or "数据湖指标").strip(),
                    "description": str(raw.get("notes") or "用于市场与平台统一分析的外部指标源。").strip(),
                    "unit": "",
                    "owner": "market_dashboard 数据湖",
                    "source_type": "lake",
                    "source_type_label": "数据湖指标",
                    "provider": str(raw.get("provider") or "market_dashboard").strip(),
                    "status_hint": "attention",
                    "assessment_template": str(raw.get("notes") or "该指标来自 market_dashboard 数据湖，可用于平台与工作台统一分析。").strip(),
                    "alert_template": "需关注数据源刷新与连通状态",
                    "watchers": ["market_dashboard", "Admin 指标专区", "大V 工作台"],
                    "display_config": {"show_in_admin": True, "show_in_h5": False},
                    "enabled": bool(raw.get("enabled", True)),
                }
            )
        source_code = slugify_code(raw.get("id") or f"{indicator_code}_source", "source")
        existing_source = get_indicator_source_def(source_code)
        if source_code in existing and existing_source:
            seed_payload = build_indicator_source_seed_payload(raw, existing=existing_source)
            seed_payload["source_code"] = existing_source["source_code"]
            save_indicator_source_def(seed_payload)
            ensure_indicator_mapping_rule_for_source(get_indicator_source_def(source_code))
            continue
        save_indicator_source_def(build_indicator_source_seed_payload(raw))
        existing.add(source_code)
        ensure_indicator_mapping_rule_for_source(get_indicator_source_def(source_code))
        imported += 1
    for source in list_indicator_source_defs():
        ensure_indicator_mapping_rule_for_source(source)
    return imported


def invalidate_indicator_hub_cache():
    _indicator_hub_cache["expires_at"] = 0.0
    _indicator_hub_cache["value"] = None


def prepare_indicator_hub_store(force=False):
    imported = ensure_default_indicator_sources()
    real_sync = sync_real_indicator_history_from_market_cache(force=force)
    derived_sync = sync_derived_smart_indicator_history(force=force)
    mock_seed = seed_mock_indicator_lake(force=force)
    invalidate_indicator_hub_cache()
    return {
        "imported_sources": imported,
        "real_sync": real_sync,
        "derived_sync": derived_sync,
        "mock_seed": mock_seed,
    }


DEFAULT_ADMIN_TASKS = [
    {
        "task_code": "indicator_prepare",
        "task_name": "指标中心预处理",
        "task_group": "indicator",
        "task_type": "prepare_indicator_hub",
        "description": "补齐指标源定义，并同步真实历史、推导智能指标和模拟底仓。",
        "schedule_type": "interval",
        "schedule_value": "1800",
        "enabled": 1,
        "timeout_seconds": 900,
    },
    {
        "task_code": "indicator_market_cache_sync",
        "task_name": "市场缓存同步",
        "task_group": "indicator",
        "task_type": "sync_real_indicator_history",
        "description": "从 market_dashboard 本地缓存同步真实因子历史到指标湖。",
        "schedule_type": "interval",
        "schedule_value": "3600",
        "enabled": 1,
        "timeout_seconds": 600,
    },
    {
        "task_code": "indicator_mock_seed",
        "task_name": "模拟指标补种",
        "task_group": "indicator",
        "task_type": "seed_mock_indicator_lake",
        "description": "当真实数据缺失时补齐模拟指标底仓，避免前台空白。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 0,
        "timeout_seconds": 600,
    },
    {
        "task_code": "indicator_raw_landing",
        "task_name": "指标原始数据落地",
        "task_group": "indicator",
        "task_type": "indicator_source_landing",
        "description": "按 source 配置把样例或实时响应落到原始记录区。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 0,
        "timeout_seconds": 600,
    },
    {
        "task_code": "indicator_clean_pipeline",
        "task_name": "指标清洗入湖",
        "task_group": "indicator",
        "task_type": "indicator_clean_pipeline",
        "description": "把原始记录按映射规则标准化并写入指标湖。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 0,
        "timeout_seconds": 600,
    },
    {
        "task_code": "knowledge_sync_manual",
        "task_name": "知识库同步入向量",
        "task_group": "knowledge",
        "task_type": "knowledge_manual_sync",
        "description": "把文本知识同步到租户知识库和向量库，支持批量补录。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 0,
        "timeout_seconds": 1200,
    },
    {
        "task_code": "review_publish_embed",
        "task_name": "纪要文本向量补录",
        "task_group": "knowledge",
        "task_type": "review_publish_embed",
        "description": "把已有文本纪要补录到向量库，用于搜索和知识召回。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 0,
        "timeout_seconds": 1200,
    },
    {
        "task_code": "knowledge_query_batch",
        "task_name": "知识检索批处理",
        "task_group": "knowledge",
        "task_type": "knowledge_query_batch",
        "description": "按任务参数批量执行知识检索与可选的大模型回答，用于验证召回效果。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 0,
        "timeout_seconds": 1200,
    },
]


def normalize_admin_task_config(payload, existing=None):
    base = dict(existing or {})
    base.update(payload or {})
    task_code = slugify_code(base.get("task_code"), "task")
    schedule_type = str(base.get("schedule_type") or "manual").strip().lower()
    if schedule_type not in {"manual", "interval"}:
        schedule_type = "manual"
    schedule_value = str(base.get("schedule_value") or "").strip()
    try:
        timeout_seconds = int(base.get("timeout_seconds") or 600)
    except Exception:
        timeout_seconds = 600
    timeout_seconds = max(30, timeout_seconds)
    return {
        "task_code": task_code,
        "task_name": str(base.get("task_name") or task_code).strip() or task_code,
        "task_group": str(base.get("task_group") or "system").strip() or "system",
        "task_type": str(base.get("task_type") or "manual").strip() or "manual",
        "description": str(base.get("description") or "").strip(),
        "task_params_json": json.dumps(base.get("task_params") if isinstance(base.get("task_params"), dict) else (safe_json_loads(base.get("task_params_json"), {}) if base.get("task_params_json") else {}), ensure_ascii=False),
        "schedule_type": schedule_type,
        "schedule_value": schedule_value,
        "enabled": 1 if bool(base.get("enabled", True)) else 0,
        "timeout_seconds": timeout_seconds,
    }


def parse_task_interval_seconds(task):
    if not isinstance(task, dict):
        return None
    if str(task.get("schedule_type") or "").strip().lower() != "interval":
        return None
    try:
        seconds = int(str(task.get("schedule_value") or "0").strip() or "0")
    except Exception:
        return None
    return seconds if seconds > 0 else None


def build_simulated_indicator_series(indicator_id, status="good", points=8):
    rng = random.Random(f"indicator-series:{indicator_id}:{status}")
    base = round(rng.uniform(82, 128), 2)
    values = []
    current = base
    for _ in range(points):
        jump = rng.uniform(-5.8, 5.8)
        if status == "good":
            jump += rng.uniform(0.2, 1.8)
        elif status == "warning":
            jump -= rng.uniform(0.2, 1.8)
        current = round(max(18, current + jump), 2)
        values.append(current)
    start_date = datetime(2026, 5, 28)
    series = []
    for index, value in enumerate(values):
        point_status = "good"
        if status == "warning" and (index >= points - 2 or value <= min(values) + 1.2):
            point_status = "warning"
        elif status == "attention" and (index >= points - 2 or abs(value - values[max(0, index - 1)]) >= 3.5):
            point_status = "attention"
        series.append(
            {
                "date": (start_date + timedelta(days=index * 3)).strftime("%Y-%m-%d"),
                "value": value,
                "status": point_status,
            }
        )
    anomalies = []
    ranked_indexes = sorted(range(len(values)), key=lambda idx: abs(values[idx] - (values[idx - 1] if idx > 0 else values[idx])), reverse=True)
    anomaly_indexes = ranked_indexes[:1] if ranked_indexes else [0]
    if status == "warning" and len(ranked_indexes) >= 2:
        anomaly_indexes = ranked_indexes[:2]
    for idx in anomaly_indexes:
        point = series[idx]
        anomalies.append(
            {
                "date": point["date"],
                "value": point["value"],
                "status": point["status"],
                "label": "异常放大" if point["status"] == "warning" else "波动抬升",
            }
        )
    return series, anomalies


def build_simulated_indicator_kline(indicator_id, status="good", points=24):
    rng = random.Random(f"indicator-kline:{indicator_id}:{status}")
    current = round(rng.uniform(28, 68), 2)
    start_date = datetime(2026, 5, 18)
    candles = []
    for _ in range(points):
        open_price = round(current + rng.uniform(-1.6, 1.6), 2)
        close_delta = rng.uniform(-2.8, 2.8)
        if status == "good":
            close_delta += rng.uniform(0.1, 0.7)
        elif status == "warning":
            close_delta -= rng.uniform(0.1, 0.7)
        close_price = round(max(8, open_price + close_delta), 2)
        wick_high = rng.uniform(0.35, 1.6)
        wick_low = rng.uniform(0.35, 1.6)
        high_price = round(max(open_price, close_price) + wick_high, 2)
        low_price = round(max(5, min(open_price, close_price) - wick_low), 2)
        candles.append(
            {
                "date": (start_date + timedelta(days=len(candles))).strftime("%Y-%m-%d"),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
            }
        )
        current = close_price

    def moving_average(window):
        line = []
        for index, candle in enumerate(candles):
            if index + 1 < window:
                continue
            subset = candles[index - window + 1:index + 1]
            avg = round(sum(item["close"] for item in subset) / window, 2)
            line.append({"date": candle["date"], "value": avg})
        return line

    ranked_indexes = sorted(
        range(len(candles)),
        key=lambda idx: abs(candles[idx]["close"] - candles[idx]["open"]) + (candles[idx]["high"] - candles[idx]["low"]),
        reverse=True,
    )
    anomaly_indexes = ranked_indexes[:1] if ranked_indexes else [0]
    if status == "warning" and len(ranked_indexes) >= 2:
        anomaly_indexes = ranked_indexes[:2]
    anomalies = [
        {
            "date": candles[idx]["date"],
            "value": candles[idx]["close"],
            "status": status,
            "label": "波动抬升" if status != "warning" else "异常放大",
        }
        for idx in anomaly_indexes
    ]
    return {
        "candles": candles,
        "ma5": moving_average(5),
        "ma10": moving_average(10),
        "ma20": moving_average(20),
        "anomalies": anomalies,
    }


REAL_HISTORY_FACTOR_NAME_MAP = {
    "source_shanghai_index": "上证指数",
    "source_shenzhen_index": "深证指数",
    "source_hs300": "沪深300",
    "source_sse50": "上证50",
    "source_kc50": "科创50",
    "source_cyb": "创业板指",
    "source_hsi": "恒生指数",
    "source_dji": "道琼斯",
    "source_sp500": "标普500",
    "source_nasdaq": "纳斯达克",
    "source_gold": "黄金",
    "source_oil": "原油",
    "source_brent": "布伦特原油",
    "source_silver": "白银",
    "source_cpi": "CPI",
    "source_bdi": "BDI",
}


def load_market_dashboard_factor_history():
    cache_db = MARKET_DASHBOARD_CACHE_DB_PATH
    if not cache_db.exists():
        return {}
    try:
        conn = sqlite3.connect(str(cache_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT name, trade_date, close, volume
            FROM factor_history
            ORDER BY name ASC, trade_date ASC
            """
        ).fetchall()
    except Exception:
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass
    grouped = {}
    for row in rows:
        item = dict(row)
        grouped.setdefault(str(item["name"] or "").strip(), []).append(item)
    return grouped


def calc_moving_average(values, window):
    points = []
    if window <= 0:
        return points
    for index, item in enumerate(values):
        if index + 1 < window:
            continue
        subset = values[index - window + 1:index + 1]
        avg = round(sum(NumberLike(point.get("close")) for point in subset) / window, 2)
        points.append({"date": item["date"], "value": avg})
    return points


def NumberLike(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def build_real_indicator_status(latest_value, prev_value):
    if prev_value in {None, 0}:
        return "attention"
    change_ratio = (latest_value - prev_value) / abs(prev_value)
    if abs(change_ratio) >= 0.05:
        return "warning"
    if abs(change_ratio) >= 0.02:
        return "attention"
    return "good"


def build_real_indicator_anomalies(series):
    anomalies = []
    if len(series) < 2:
        return anomalies
    deltas = []
    for index in range(1, len(series)):
        prev_value = NumberLike(series[index - 1]["close"])
        current_value = NumberLike(series[index]["close"])
        if prev_value == 0:
            continue
        change_ratio = (current_value - prev_value) / abs(prev_value)
        deltas.append((index, change_ratio))
    ranked = sorted(deltas, key=lambda item: abs(item[1]), reverse=True)
    for index, change_ratio in ranked[:2]:
        point = series[index]
        status = "warning" if abs(change_ratio) >= 0.05 else "attention"
        anomalies.append(
            {
                "date": point["date"],
                "value": point["close"],
                "status": status,
                "severity": "高" if status == "warning" else "中",
                "label": "异常放大" if status == "warning" else "波动抬升",
            }
        )
    return anomalies


def build_real_indicator_kline_payload(series):
    candles = []
    for index, item in enumerate(series):
        close_value = round(NumberLike(item["close"]), 2)
        prev_close = round(NumberLike(series[index - 1]["close"]), 2) if index > 0 else close_value
        open_value = round(NumberLike(item.get("open")) or prev_close, 2)
        high_value = round(max(NumberLike(item.get("high")) or close_value, open_value, close_value), 2)
        low_value = round(min(NumberLike(item.get("low")) or close_value, open_value, close_value), 2)
        candles.append(
            {
                "date": item["date"],
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
            }
        )
    return {
        "candles": candles,
        "ma5": calc_moving_average(candles, 5),
        "ma10": calc_moving_average(candles, 10),
        "ma20": calc_moving_average(candles, 20),
        "anomalies": build_real_indicator_anomalies(candles),
    }


def sync_real_indicator_history_from_market_cache(force=False):
    history_map = load_market_dashboard_factor_history()
    if not history_map:
        return {"synced": False, "reason": "market_cache_unavailable", "updated": 0}
    db = get_db()
    definitions = list_indicator_definitions()
    timestamp = now_ts()
    batch_code = f"real_history_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    updated = 0
    total_points = 0
    active_sources = {item["indicator_code"]: item for item in list_indicator_source_defs()}
    for definition in definitions:
        indicator_code = definition["indicator_code"]
        factor_name = REAL_HISTORY_FACTOR_NAME_MAP.get(indicator_code)
        if not factor_name:
            continue
        source_rows = history_map.get(factor_name) or []
        if len(source_rows) < 2:
            continue
        rows = []
        for item in source_rows:
            trade_date = str(item.get("trade_date") or "").strip()
            if not trade_date:
                continue
            close_value = NumberLike(item.get("close"))
            rows.append(
                {
                    "date": trade_date,
                    "close": close_value,
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                }
            )
        rows = sorted(rows, key=lambda item: item["date"])
        if len(rows) < 2:
            continue
        source = active_sources.get(indicator_code)
        source_code = source["source_code"] if source else indicator_code
        if force:
            db.execute("DELETE FROM indicator_series WHERE indicator_code = ? AND source_code = ?", (indicator_code, source_code))
            db.execute("DELETE FROM indicator_kline_points WHERE indicator_code = ?", (indicator_code,))
            db.execute("DELETE FROM indicator_anomalies WHERE indicator_code = ?", (indicator_code,))
        else:
            existing_real = db.execute(
                "SELECT COUNT(*) AS c FROM indicator_series WHERE indicator_code = ? AND is_simulated = 0",
                (indicator_code,),
            ).fetchone()["c"]
            if existing_real:
                continue
            db.execute("DELETE FROM indicator_series WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
            db.execute("DELETE FROM indicator_kline_points WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
            db.execute("DELETE FROM indicator_anomalies WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
        prev_close = NumberLike(rows[-2]["close"])
        latest_close = NumberLike(rows[-1]["close"])
        latest_status = build_real_indicator_status(latest_close, prev_close)
        for row in rows:
            point_status = build_real_indicator_status(NumberLike(row["close"]), prev_close if row["date"] == rows[-1]["date"] else NumberLike(row["close"]))
            db.execute(
                """
                INSERT INTO indicator_series (
                    indicator_code, point_time, point_value, point_status, is_simulated, source_code, batch_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    f"{row['date']} 00:00:00",
                    NumberLike(row["close"]),
                    point_status,
                    0,
                    source_code,
                    batch_code,
                    timestamp,
                ),
            )
            total_points += 1
        kline = build_real_indicator_kline_payload(rows[-60:])
        ma_lookup = {}
        for line_name in ("ma5", "ma10", "ma20"):
            for point in kline.get(line_name, []):
                ma_lookup.setdefault(point["date"], {})[line_name] = point["value"]
        for candle in kline.get("candles", []):
            ma_entry = ma_lookup.get(candle["date"], {})
            db.execute(
                """
                INSERT INTO indicator_kline_points (
                    indicator_code, point_date, open_value, high_value, low_value, close_value,
                    ma5, ma10, ma20, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    candle["date"],
                    candle["open"],
                    candle["high"],
                    candle["low"],
                    candle["close"],
                    ma_entry.get("ma5"),
                    ma_entry.get("ma10"),
                    ma_entry.get("ma20"),
                    batch_code,
                    0,
                    timestamp,
                ),
            )
        for anomaly in kline.get("anomalies", []):
            db.execute(
                """
                INSERT INTO indicator_anomalies (
                    indicator_code, anomaly_time, anomaly_value, severity, anomaly_status, anomaly_label, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    f"{anomaly['date']} 00:00:00",
                    anomaly["value"],
                    anomaly["severity"],
                    anomaly["status"],
                    anomaly["label"],
                    batch_code,
                    0,
                    timestamp,
                ),
            )
        assessment = definition.get("assessment_template") or f"{factor_name} 历史数据已从 market_dashboard 本地缓存同步入湖。"
        alert = definition.get("alert_template") or "已按真实历史数据更新。"
        db.execute(
            """
            INSERT INTO indicator_latest_values (
                indicator_code, latest_value, latest_status, latest_assessment, latest_alert,
                updated_at, is_simulated, source_code, batch_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(indicator_code) DO UPDATE SET
                latest_value = excluded.latest_value,
                latest_status = excluded.latest_status,
                latest_assessment = excluded.latest_assessment,
                latest_alert = excluded.latest_alert,
                updated_at = excluded.updated_at,
                is_simulated = excluded.is_simulated,
                source_code = excluded.source_code,
                batch_code = excluded.batch_code
            """,
            (
                indicator_code,
                f"{latest_close:.2f}",
                latest_status,
                assessment,
                alert,
                timestamp,
                0,
                source_code,
                batch_code,
            ),
        )
        updated += 1
    if updated:
        db.execute(
            """
            INSERT INTO indicator_load_batches (
                batch_code, load_type, source_code, summary, total_points, total_indicators, success, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_code,
                "market_cache_sync",
                "",
                "已从 market_dashboard 本地历史缓存同步真实指标历史，优先替代模拟序列。",
                total_points,
                updated,
                1,
                timestamp,
            ),
        )
        db.commit()
    return {"synced": bool(updated), "updated": updated, "total_points": total_points, "batch_code": batch_code if updated else ""}


def load_real_indicator_series_map(indicator_codes):
    if not indicator_codes:
        return {}
    db = get_db()
    placeholders = ",".join("?" for _ in indicator_codes)
    rows = db.execute(
        f"""
        SELECT indicator_code, point_time, point_value
        FROM indicator_series
        WHERE indicator_code IN ({placeholders}) AND is_simulated = 0
        ORDER BY point_time ASC, id ASC
        """,
        indicator_codes,
    ).fetchall()
    grouped = {}
    for row in rows:
        item = dict(row)
        grouped.setdefault(item["indicator_code"], []).append(
            {
                "date": str(item["point_time"] or "")[:10],
                "value": NumberLike(item["point_value"]),
            }
        )
    return grouped


def normalize_to_base(series, base=100.0):
    if not series:
        return []
    first = NumberLike(series[0]["value"])
    if first == 0:
        first = 1.0
    return [
        {"date": item["date"], "value": round((NumberLike(item["value"]) / first) * base, 2)}
        for item in series
    ]


def rolling_average(values, window):
    result = []
    if not values:
        return result
    for index, item in enumerate(values):
        if index + 1 < window:
            subset = values[:index + 1]
        else:
            subset = values[index - window + 1:index + 1]
        avg = round(sum(NumberLike(point["value"]) for point in subset) / max(len(subset), 1), 2)
        result.append({"date": item["date"], "value": avg})
    return result


def derive_smart_indicator_series():
    source_map = load_real_indicator_series_map([
        "source_cpi",
        "source_nasdaq",
        "source_sp500",
        "source_hsi",
        "source_hs300",
        "source_shanghai_index",
        "source_cyb",
        "source_kc50",
        "source_sse50",
        "source_gold",
    ])
    derived = {}

    nasdaq = normalize_to_base(source_map.get("source_nasdaq", []))
    sp500 = normalize_to_base(source_map.get("source_sp500", []))
    if nasdaq and sp500:
        series = []
        for left, right in zip(nasdaq, sp500):
            value = round(left["value"] * 0.6 + right["value"] * 0.4, 2)
            series.append({"date": left["date"], "value": value})
        derived["fed_rate_path"] = series

    hs300 = normalize_to_base(source_map.get("source_hs300", []))
    hsi = normalize_to_base(source_map.get("source_hsi", []))
    if hs300 and hsi:
        series = []
        for left, right in zip(hs300, hsi):
            value = round((left["value"] * 0.45 + right["value"] * 0.55), 2)
            series.append({"date": left["date"], "value": value})
        derived["southbound_flow"] = series

    sh_index = normalize_to_base(source_map.get("source_shanghai_index", []))
    cpi = normalize_to_base(source_map.get("source_cpi", []))
    if sh_index and cpi:
        series = []
        for left, right in zip(sh_index, cpi):
            value = round(left["value"] * 0.7 + (200 - right["value"]) * 0.3, 2)
            series.append({"date": left["date"], "value": value})
        derived["credit_pulse"] = rolling_average(series, 5)

    cyb = normalize_to_base(source_map.get("source_cyb", []))
    kc50 = normalize_to_base(source_map.get("source_kc50", []))
    sse50 = normalize_to_base(source_map.get("source_sse50", []))
    if cyb and kc50 and sse50:
        series = []
        for cyb_item, kc_item, sse_item in zip(cyb, kc50, sse50):
            value = round(cyb_item["value"] * 0.35 + kc_item["value"] * 0.45 + sse_item["value"] * 0.20, 2)
            series.append({"date": cyb_item["date"], "value": value})
        derived["ai_order_signal"] = rolling_average(series, 5)
    return derived


def sync_derived_smart_indicator_history(force=False):
    derived_map = derive_smart_indicator_series()
    if not derived_map:
        return {"synced": False, "reason": "real_factor_inputs_missing", "updated": 0}
    db = get_db()
    timestamp = now_ts()
    batch_code = f"derived_smart_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    updated = 0
    total_points = 0
    for indicator_code, series in derived_map.items():
        if len(series) < 2:
            continue
        if force:
            db.execute("DELETE FROM indicator_series WHERE indicator_code = ?", (indicator_code,))
            db.execute("DELETE FROM indicator_kline_points WHERE indicator_code = ?", (indicator_code,))
            db.execute("DELETE FROM indicator_anomalies WHERE indicator_code = ?", (indicator_code,))
        else:
            existing_real = db.execute(
                "SELECT COUNT(*) AS c FROM indicator_series WHERE indicator_code = ? AND is_simulated = 0",
                (indicator_code,),
            ).fetchone()["c"]
            if existing_real:
                continue
            db.execute("DELETE FROM indicator_series WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
            db.execute("DELETE FROM indicator_kline_points WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
            db.execute("DELETE FROM indicator_anomalies WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
        last_prev = NumberLike(series[-2]["value"])
        last_value = NumberLike(series[-1]["value"])
        latest_status = build_real_indicator_status(last_value, last_prev)
        status_series = []
        prev_value = None
        for item in series:
            current_value = NumberLike(item["value"])
            point_status = build_real_indicator_status(current_value, prev_value if prev_value not in {None, 0} else current_value)
            prev_value = current_value
            status_series.append({"date": item["date"], "close": current_value, "status": point_status})
            db.execute(
                """
                INSERT INTO indicator_series (
                    indicator_code, point_time, point_value, point_status, is_simulated, source_code, batch_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    f"{item['date']} 00:00:00",
                    current_value,
                    point_status,
                    0,
                    "derived_real_factors",
                    batch_code,
                    timestamp,
                ),
            )
            total_points += 1
        kline = build_real_indicator_kline_payload(status_series[-60:])
        ma_lookup = {}
        for line_name in ("ma5", "ma10", "ma20"):
            for point in kline.get(line_name, []):
                ma_lookup.setdefault(point["date"], {})[line_name] = point["value"]
        for candle in kline.get("candles", []):
            ma_entry = ma_lookup.get(candle["date"], {})
            db.execute(
                """
                INSERT INTO indicator_kline_points (
                    indicator_code, point_date, open_value, high_value, low_value, close_value,
                    ma5, ma10, ma20, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    candle["date"],
                    candle["open"],
                    candle["high"],
                    candle["low"],
                    candle["close"],
                    ma_entry.get("ma5"),
                    ma_entry.get("ma10"),
                    ma_entry.get("ma20"),
                    batch_code,
                    0,
                    timestamp,
                ),
            )
        for anomaly in kline.get("anomalies", []):
            db.execute(
                """
                INSERT INTO indicator_anomalies (
                    indicator_code, anomaly_time, anomaly_value, severity, anomaly_status, anomaly_label, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    f"{anomaly['date']} 00:00:00",
                    anomaly["value"],
                    anomaly["severity"],
                    anomaly["status"],
                    anomaly["label"],
                    batch_code,
                    0,
                    timestamp,
                ),
            )
        definition = get_indicator_definition(indicator_code)
        assessment = definition.get("assessment_template") if definition else "已由真实底层因子推导生成。"
        alert = definition.get("alert_template") if definition else "已由真实底层因子推导生成。"
        db.execute(
            """
            INSERT INTO indicator_latest_values (
                indicator_code, latest_value, latest_status, latest_assessment, latest_alert,
                updated_at, is_simulated, source_code, batch_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(indicator_code) DO UPDATE SET
                latest_value = excluded.latest_value,
                latest_status = excluded.latest_status,
                latest_assessment = excluded.latest_assessment,
                latest_alert = excluded.latest_alert,
                updated_at = excluded.updated_at,
                is_simulated = excluded.is_simulated,
                source_code = excluded.source_code,
                batch_code = excluded.batch_code
            """,
            (
                indicator_code,
                f"{last_value:.2f}",
                latest_status,
                assessment,
                alert,
                timestamp,
                0,
                "derived_real_factors",
                batch_code,
            ),
        )
        updated += 1
    if updated:
        db.execute(
            """
            INSERT INTO indicator_load_batches (
                batch_code, load_type, source_code, summary, total_points, total_indicators, success, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_code,
                "derived_smart_sync",
                "derived_real_factors",
                "已由真实底层因子推导智能指标历史，替代原模拟序列。",
                total_points,
                updated,
                1,
                timestamp,
            ),
        )
        db.commit()
    return {"synced": bool(updated), "updated": updated, "total_points": total_points, "batch_code": batch_code if updated else ""}


def seed_mock_indicator_lake(force=False):
    ensure_default_indicator_sources()
    definitions = list_indicator_definitions()
    db = get_db()
    existing_latest_codes = {
        row["indicator_code"]
        for row in db.execute("SELECT indicator_code FROM indicator_latest_values").fetchall()
    }
    if existing_latest_codes and not force and len(existing_latest_codes) >= len(definitions):
        return {"seeded": False, "reason": "already_seeded"}
    if force:
        db.execute("DELETE FROM indicator_latest_values")
        db.execute("DELETE FROM indicator_series")
        db.execute("DELETE FROM indicator_anomalies")
        db.execute("DELETE FROM indicator_kline_points")
    batch_code = f"mock_seed_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    timestamp = now_ts()
    total_points = 0
    active_sources = {item["indicator_code"]: item for item in list_indicator_source_defs()}
    for definition in definitions:
        if not force and definition["indicator_code"] in existing_latest_codes:
            continue
        status = definition.get("status_hint") or "attention"
        series, anomalies = build_simulated_indicator_series(definition["indicator_code"], status=status)
        kline = build_simulated_indicator_kline(definition["indicator_code"], status=status)
        latest_point = series[-1] if series else {"value": 0, "status": status, "date": datetime.now().strftime("%Y-%m-%d")}
        latest_assessment = definition.get("assessment_template") or "当前已接入模拟指标数据。"
        latest_alert = definition.get("alert_template") or "已纳入指标监测。"
        source = active_sources.get(definition["indicator_code"])
        source_code = source["source_code"] if source else ""
        latest_value_text = f"{latest_point['value']:.2f}" if definition.get("unit") else f"{latest_point['value']:.2f}"
        db.execute(
            """
            INSERT INTO indicator_latest_values (
                indicator_code, latest_value, latest_status, latest_assessment, latest_alert,
                updated_at, is_simulated, source_code, batch_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(indicator_code) DO UPDATE SET
                latest_value = excluded.latest_value,
                latest_status = excluded.latest_status,
                latest_assessment = excluded.latest_assessment,
                latest_alert = excluded.latest_alert,
                updated_at = excluded.updated_at,
                is_simulated = excluded.is_simulated,
                source_code = excluded.source_code,
                batch_code = excluded.batch_code
            """,
            (
                definition["indicator_code"],
                latest_value_text,
                latest_point["status"],
                latest_assessment,
                latest_alert,
                timestamp,
                1,
                source_code,
                batch_code,
            ),
        )
        for point in series:
            total_points += 1
            db.execute(
                """
                INSERT INTO indicator_series (
                    indicator_code, point_time, point_value, point_status, is_simulated, source_code, batch_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    definition["indicator_code"],
                    f"{point['date']} 00:00:00",
                    point["value"],
                    point["status"],
                    1,
                    source_code,
                    batch_code,
                    timestamp,
                ),
            )
        for entry in anomalies:
            db.execute(
                """
                INSERT INTO indicator_anomalies (
                    indicator_code, anomaly_time, anomaly_value, severity, anomaly_status, anomaly_label, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    definition["indicator_code"],
                    f"{entry['date']} 00:00:00",
                    entry["value"],
                    "高" if entry["status"] == "warning" else "中",
                    entry["status"],
                    entry["label"],
                    batch_code,
                    1,
                    timestamp,
                ),
            )
        ma_lookup = {}
        for line_name in ("ma5", "ma10", "ma20"):
            for point in kline.get(line_name, []):
                ma_lookup.setdefault(point["date"], {})[line_name] = point["value"]
        for candle in kline.get("candles", []):
            ma_entry = ma_lookup.get(candle["date"], {})
            db.execute(
                """
                INSERT INTO indicator_kline_points (
                    indicator_code, point_date, open_value, high_value, low_value, close_value,
                    ma5, ma10, ma20, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    definition["indicator_code"],
                    candle["date"],
                    candle["open"],
                    candle["high"],
                    candle["low"],
                    candle["close"],
                    ma_entry.get("ma5"),
                    ma_entry.get("ma10"),
                    ma_entry.get("ma20"),
                    batch_code,
                    1,
                    timestamp,
                ),
            )
    db.execute(
        """
        INSERT INTO indicator_load_batches (
            batch_code, load_type, source_code, summary, total_points, total_indicators, success, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_code,
            "mock_seed",
            "",
            "首阶段使用模拟随机数据写入指标湖骨架，供 Admin / 工作台 / H5 统一读取。",
            total_points,
            len(definitions),
            1,
            timestamp,
        ),
    )
    db.commit()
    return {"seeded": True, "batch_code": batch_code, "total_indicators": len(definitions), "total_points": total_points}


def build_indicator_kline_from_rows(rows, anomalies):
    candles = []
    ma5 = []
    ma10 = []
    ma20 = []
    for row in rows:
        item = dict(row)
        candles.append(
            {
                "date": item["point_date"],
                "open": item["open_value"],
                "high": item["high_value"],
                "low": item["low_value"],
                "close": item["close_value"],
            }
        )
        if item["ma5"] is not None:
            ma5.append({"date": item["point_date"], "value": item["ma5"]})
        if item["ma10"] is not None:
            ma10.append({"date": item["point_date"], "value": item["ma10"]})
        if item["ma20"] is not None:
            ma20.append({"date": item["point_date"], "value": item["ma20"]})
    return {
        "candles": candles,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "anomalies": anomalies,
    }


def build_indicator_kline_from_series_points(series_points, anomalies, status="attention", indicator_code=""):
    points = [dict(item) for item in (series_points or []) if isinstance(item, dict) and item.get("date")]
    if not points:
        return build_simulated_indicator_kline(indicator_code or "indicator_fallback", status=status or "attention")
    rows = []
    previous_close = None
    for index, point in enumerate(points):
        close_value = round(NumberLike(point.get("value")), 2)
        if previous_close is None:
            previous_close = close_value * 0.994 if close_value else 0.0
        open_value = round(previous_close, 2)
        base_high = max(open_value, close_value)
        base_low = min(open_value, close_value)
        spread = max(abs(close_value - open_value) * 0.38, max(close_value * 0.0035, 0.12))
        rows.append(
            {
                "date": str(point.get("date") or "").strip(),
                "open": round(open_value, 2),
                "high": round(base_high + spread, 2),
                "low": round(max(0.01, base_low - spread), 2),
                "close": close_value,
            }
        )
        previous_close = close_value
    return build_real_indicator_kline_payload(rows[-60:])


def build_indicator_hub_from_store():
    definitions = list_indicator_definitions()
    source_map = {}
    for source in list_indicator_source_defs():
        source_map.setdefault(source["indicator_code"], []).append(source)
    db = get_db()
    latest_map = {
        row["indicator_code"]: dict(row)
        for row in db.execute("SELECT * FROM indicator_latest_values").fetchall()
    }
    series_map = {}
    for row in db.execute(
        """
        SELECT indicator_code, point_time, point_value, point_status
        FROM indicator_series
        ORDER BY point_time ASC, id ASC
        """
    ).fetchall():
        item = dict(row)
        series_map.setdefault(item["indicator_code"], []).append(
            {
                "date": item["point_time"][:10],
                "value": item["point_value"],
                "status": item["point_status"],
            }
        )
    anomaly_map = {}
    for row in db.execute(
        """
        SELECT indicator_code, anomaly_time, anomaly_value, severity, anomaly_status, anomaly_label
        FROM indicator_anomalies
        ORDER BY anomaly_time DESC, id DESC
        """
    ).fetchall():
        item = dict(row)
        anomaly_map.setdefault(item["indicator_code"], []).append(
            {
                "date": item["anomaly_time"][:10],
                "value": item["anomaly_value"],
                "status": item["anomaly_status"],
                "label": item["anomaly_label"],
                "severity": item["severity"],
            }
        )
    kline_map = {}
    for row in db.execute(
        """
        SELECT indicator_code, point_date, open_value, high_value, low_value, close_value, ma5, ma10, ma20
        FROM indicator_kline_points
        ORDER BY point_date ASC, id ASC
        """
    ).fetchall():
        item = dict(row)
        kline_map.setdefault(item["indicator_code"], []).append(item)
    items = []
    for definition in definitions:
        latest = latest_map.get(definition["indicator_code"], {})
        anomalies = anomaly_map.get(definition["indicator_code"], [])
        sources = source_map.get(definition["indicator_code"], [])
        primary_source = sources[0] if sources else None
        latest_source_code = latest.get("source_code") or ""
        latest_is_simulated = bool(latest.get("is_simulated", 1))
        if latest_is_simulated:
            data_mode = "simulated"
            data_mode_label = "模拟数据"
        elif latest_source_code == "derived_real_factors":
            data_mode = "derived"
            data_mode_label = "真实因子推导"
        else:
            data_mode = "real"
            data_mode_label = "真实数据"
        history_series = series_map.get(definition["indicator_code"], [])
        raw_kline_rows = kline_map.get(definition["indicator_code"], [])
        history_kline = build_indicator_kline_from_rows(raw_kline_rows, anomalies) if raw_kline_rows else build_indicator_kline_from_series_points(
            history_series,
            anomalies,
            status=latest.get("latest_status") or definition.get("status_hint") or "attention",
            indicator_code=definition["indicator_code"],
        )
        item = {
            "id": definition["indicator_code"],
            "name": definition["indicator_name"],
            "tenant_slug": str(definition.get("tenant_slug") or "").strip().lower(),
            "category": definition["category"],
            "unit": definition.get("unit") or "",
            "description": definition.get("description") or "",
            "owner": definition["owner"],
            "value": latest.get("latest_value") or "--",
            "numeric_value": parse_numeric_indicator_value(latest.get("latest_value")),
            "assessment": latest.get("latest_assessment") or definition.get("assessment_template") or "暂无说明",
            "status": latest.get("latest_status") or definition.get("status_hint") or "attention",
            "alert": latest.get("latest_alert") or definition.get("alert_template") or "暂无预警说明",
            "enabled": bool(definition.get("enabled")),
            "last_updated": latest.get("updated_at") or definition.get("updated_at") or "未记录",
            "watchers": definition.get("watchers", []),
            "prompt_text": str(definition.get("prompt_text") or "").strip(),
            "formula_js": str(definition.get("formula_js") or "").strip(),
            "selected_indicators": normalize_selected_indicator_refs(definition.get("selected_indicators")),
            "display_order": int(definition.get("display_order") or 0),
            "history": [
                {
                    "date": point["date"],
                    "value": f"{point['value']:.2f}",
                    "status": point["status"],
                    "event": data_mode == "real" and "真实指标点已写入指标湖" or (data_mode == "derived" and "已由真实因子推导写入指标湖" or "模拟指标点已写入指标湖"),
                }
                for point in history_series[-6:]
            ],
            "history_series": history_series,
            "history_anomalies": anomalies,
            "history_kline": history_kline,
            "source_type": definition.get("source_type") or "mock",
            "source_type_label": definition.get("source_type_label") or "模拟指标",
            "provider": definition.get("provider") or (primary_source["provider"] if primary_source else "平台数据层"),
            "source_count": len(sources),
            "source_defs": sources,
            "latest_source_test": primary_source and {
                "status": primary_source.get("last_test_status") or "",
                "detail": primary_source.get("last_test_detail") or "",
                "tested_at": primary_source.get("last_tested_at") or "",
            } or None,
            "data_mode": data_mode,
            "data_mode_label": data_mode_label,
        }
        items.append(item)
    smart_items = [item for item in items if item["source_type"] == "smart"]
    lake_items = [item for item in items if item["source_type"] != "smart"]
    anomalies = []
    for item in items:
        for anomaly in anomaly_map.get(item["id"], [])[:2]:
            anomalies.append(
                {
                    "id": f"anomaly_{item['id']}_{anomaly['date']}",
                    "level": anomaly["severity"],
                    "title": f"{item['name']} 指标异动",
                    "summary": f"{anomaly['label']} · {item['alert']}",
                    "time": anomaly["date"],
                    "related_indicator_id": item["id"],
                }
            )
    summary = {
        "total": len(items),
        "smart_total": len(smart_items),
        "lake_total": len(lake_items),
        "enabled": sum(1 for item in items if item["enabled"]),
        "warnings": sum(1 for item in items if item["status"] == "warning"),
        "attention": sum(1 for item in items if item["status"] == "attention"),
        "anomalies": len(anomalies),
    }
    batches = [dict(row) for row in db.execute("SELECT * FROM indicator_load_batches ORDER BY created_at DESC, id DESC LIMIT 20").fetchall()]
    tests = list_indicator_source_tests(limit=20)
    raw_records = list_indicator_raw_records(limit=20)
    mapping_rules = list_indicator_mapping_rules()
    clean_jobs = list_indicator_clean_jobs(limit=20)
    return {
        "summary": summary,
        "items": items,
        "smart_items": smart_items,
        "lake_items": lake_items,
        "anomalies": anomalies,
        "definitions": definitions,
        "source_defs": list_indicator_source_defs(),
        "recent_tests": tests,
        "load_batches": batches,
        "raw_records": raw_records,
        "mapping_rules": mapping_rules,
        "clean_jobs": clean_jobs,
    }


def get_indicator_hub_from_store_cached(force_refresh=False):
    now = time.time()
    cached_value = _indicator_hub_cache.get("value")
    expires_at = float(_indicator_hub_cache.get("expires_at") or 0.0)
    if not force_refresh and cached_value is not None and now < expires_at:
        return copy.deepcopy(cached_value)
    hub = build_indicator_hub_from_store()
    _indicator_hub_cache["value"] = copy.deepcopy(hub)
    _indicator_hub_cache["expires_at"] = now + INDICATOR_HUB_CACHE_TTL_SECONDS
    return copy.deepcopy(hub)


def get_indicator_hub_snapshot():
    try:
        return get_indicator_hub_from_store_cached()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while loading indicator hub snapshot, using fallback data")
        return build_indicator_hub_fallback()


def build_watchlist_indicator_context(indicator_hub=None):
    hub = indicator_hub or get_indicator_hub_snapshot()
    items = list(hub.get("smart_items") or []) + list(hub.get("lake_items") or [])
    by_id = {item.get("id"): item for item in items if item.get("id")}
    item_names = {str(item.get("name") or ""): item for item in items if item.get("name")}
    return {
        "hub": hub,
        "items": items,
        "by_id": by_id,
        "by_name": item_names,
        "warnings": [item for item in items if item.get("status") == "warning"],
        "attentions": [item for item in items if item.get("status") == "attention"],
        "anomalies": hub.get("anomalies") or [],
    }


def build_watchlist_signal_bundle(stock_code, stock_name, industry, context):
    normalized_code = str(stock_code or "").strip().upper()
    normalized_name = str(stock_name or "").strip()
    industry_text = str(industry or "").strip()
    items = context.get("items") or []
    warnings = context.get("warnings") or []
    attentions = context.get("attentions") or []
    anomalies = context.get("anomalies") or []

    board_signal_map = {
        "半导体制造": ["ai_order_signal", "credit_pulse", "source_hs300"],
        "动力电池": ["credit_pulse", "source_oil", "source_brent"],
        "港股互联网": ["southbound_flow", "fed_rate_path", "source_hsi"],
        "高端白酒": ["credit_pulse", "source_cpi", "source_shanghai_index"],
        "银行": ["credit_pulse", "fed_rate_path", "source_shanghai_index"],
    }
    related_ids = board_signal_map.get(industry_text, ["credit_pulse", "fed_rate_path", "southbound_flow"])
    related_items = [context["by_id"].get(item_id) for item_id in related_ids if context["by_id"].get(item_id)]
    if not related_items:
        related_items = warnings[:2] + attentions[:1]
    warning_count = sum(1 for item in related_items if item and item.get("status") == "warning")
    attention_count = sum(1 for item in related_items if item and item.get("status") == "attention")
    dominant_item = related_items[0] if related_items else (warnings[0] if warnings else (attentions[0] if attentions else None))
    board_alert_level = "warning" if warning_count else ("attention" if attention_count else "normal")

    def _sanitize_summary_text(text):
        cleaned = re.sub(r"[A-Za-z_][A-Za-z0-9_]*\(\)", "", str(text or "")).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"^[：:;\-，,\s]+", "", cleaned)
        cleaned = cleaned.replace("宏观接口", "宏观信号")
        return cleaned.strip("：:;，, ")

    board_summary_templates = {
        "半导体制造": {
            "warning": "景气验证仍有压力，优先盯产能利用率和盈利兑现。",
            "attention": "国产替代逻辑仍在，短期继续跟踪盈利兑现。",
            "normal": "产业趋势还在，当前按盈利兑现节奏继续观察。",
        },
        "动力电池": {
            "warning": "价格竞争仍在，先看利润率和海外出货是否稳住。",
            "attention": "情绪回落后更适合继续看技术路线和订单验证。",
            "normal": "行业主线未破坏，重点跟踪新技术和出货节奏。",
        },
        "港股互联网": {
            "warning": "估值修复放缓，先看财报兑现和资金延续。",
            "attention": "回购和财报兑现仍是两条主验证线。",
            "normal": "当前更适合围绕回购、利润率和南向资金继续跟踪。",
        },
        "高端白酒": {
            "warning": "消费修复仍需验证，先看需求和估值承接。",
            "attention": "盈利稳定但弹性有限，继续看消费修复持续性。",
            "normal": "品牌力和现金流仍稳，当前按消费修复节奏跟踪。",
        },
        "银行": {
            "warning": "防守价值还在，但要继续跟踪息差压力。",
            "attention": "适合作为组合稳定器，继续看股息和资产质量。",
            "normal": "股息和资产质量稳定，更适合稳健跟踪。",
        },
    }

    if dominant_item:
        default_summary = _sanitize_summary_text(dominant_item.get("assessment") or dominant_item.get("alert") or "需继续观察")
        board_summary = (
            board_summary_templates.get(industry_text, {}).get(board_alert_level)
            or default_summary
            or "当前需继续观察价格、行业位置和验证节点。"
        )
        board_alert_text = dominant_item.get("alert") or dominant_item.get("assessment") or "当前无明显预警"
    else:
        board_summary = "当前未匹配到高优先级指标，继续观察价格、行业位置和验证节点。"
        board_alert_text = "当前无明显预警"
    relevant_anomalies = [
        item for item in anomalies
        if any(signal and item.get("related_indicator_id") == signal.get("id") for signal in related_items)
    ][:2]
    anomaly_text = "；".join(item.get("summary") or item.get("title") or "" for item in relevant_anomalies if (item.get("summary") or item.get("title")))
    thesis = []
    for item in related_items[:3]:
        if not item:
            continue
        thesis.append(
            sanitize_user_facing_source_text(
                f"{item.get('name')}: {item.get('assessment') or item.get('alert') or '继续观察'}",
                fallback=f"{item.get('name')}: 继续观察",
            )
        )
    while len(thesis) < 3:
        thesis.append("当前需结合个股盈利、估值和行业位置继续判断。")
    metrics = []
    for item in related_items[:4]:
        if not item:
            continue
        metrics.append(
            {
                "label": item.get("name") or "指标",
                "value": item.get("value") or "--",
                "note": sanitize_user_facing_source_text(
                    item.get("assessment") or item.get("alert") or "当前无说明",
                    fallback="当前无说明",
                ),
            }
        )
    return {
        "stock_code": normalized_code,
        "stock_name": normalized_name,
        "industry": industry_text,
        "board_alert_level": board_alert_level,
        "board_alert_text": board_alert_text,
        "board_summary": board_summary,
        "anomaly_text": anomaly_text,
        "related_indicator_ids": [item.get("id") for item in related_items if item],
        "related_indicator_names": [item.get("name") for item in related_items if item],
        "thesis": thesis[:3],
        "metrics": metrics[:4],
        "warning_count": warning_count,
        "attention_count": attention_count,
    }


def build_fundamental_column_payload(tenant=None):
    tenant = tenant or get_tenant_by_slug()
    indicator_hub = build_indicator_hub(tenant=tenant, admin_view=False)
    return build_fundamental_column_payload_from_hub(tenant, indicator_hub)


def build_indicator_dashboard_seed_cards(tenant=None, count=8):
    tenant = tenant or get_tenant_by_slug()
    indicator_hub = build_indicator_hub(tenant=tenant, admin_view=False)
    return build_indicator_dashboard_seed_cards_from_hub(indicator_hub, count=count)


def build_data_lake_indicator_items():
    items = []
    for raw in load_market_dashboard_indicators():
        indicator_name = str(raw.get("indicator", "")).strip()
        if not indicator_name:
            continue
        enabled = bool(raw.get("enabled", True))
        source_status = str(raw.get("status", "")).strip().lower()
        test_status = str(raw.get("last_test_status", "")).strip()
        updated_at = str(raw.get("updated_at", "")).strip()
        tested_at = str(raw.get("last_tested_at", "")).strip()
        if not enabled:
            status = "warning"
        elif "200" in test_status or source_status == "configured":
            status = "good"
        elif test_status:
            status = "attention"
        else:
            status = "attention"
        current_value = test_status or ("已接入" if enabled else "未启用")
        if not enabled:
            assessment = "该数据湖指标当前被关闭，不会进入平台指标展示与异动监测。"
            alert = "需确认是否重新启用该指标"
        else:
            assessment = str(raw.get("notes", "")).strip() or "该指标来自 market_dashboard 数据湖，可用于平台与工作台统一分析。"
            alert = "已纳入数据湖指标监测" if status == "good" else "需关注数据源刷新与连通状态"
        simulated_series, simulated_anomalies = build_simulated_indicator_series(raw.get("id") or indicator_name, status=status)
        simulated_kline = build_simulated_indicator_kline(raw.get("id") or indicator_name, status=status)
        history = []
        if updated_at:
            history.append(
                {
                    "date": updated_at[:10],
                    "value": current_value,
                    "status": status,
                    "event": "数据湖源配置已同步到指标专区",
                }
            )
        if tested_at:
            history.append(
                {
                    "date": tested_at[:10],
                    "value": test_status or current_value,
                    "status": "good" if "200" in test_status else "attention",
                    "event": str(raw.get("last_test_detail", "")).strip()[:120] or "最近一次连通性测试已完成",
                }
            )
        items.append(
            {
                "id": f"lake_{raw.get('id') or indicator_name}",
                "name": indicator_name,
                "category": str(raw.get("category", "")).strip() or "数据湖指标",
                "owner": "market_dashboard 数据湖",
                "value": current_value,
                "assessment": assessment,
                "status": status,
                "alert": alert,
                "enabled": enabled,
                "last_updated": updated_at or tested_at or "未记录",
                "watchers": ["market_dashboard", "Admin 指标专区", "大V 工作台"],
                "history": history or [
                    {
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "value": current_value,
                        "status": status,
                        "event": "已从数据湖源注册表导入",
                    }
                ],
                "history_series": simulated_series,
                "history_anomalies": simulated_anomalies,
                "history_kline": simulated_kline,
                "source_type": "lake",
                "source_type_label": "数据湖指标",
                "provider": str(raw.get("provider", "")).strip() or "数据湖",
            }
        )
    return items


def build_indicator_hub(tenant=None, admin_view=False):
    tenant = tenant or get_tenant_by_slug()
    try:
        hub = get_indicator_hub_from_store_cached()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while building indicator hub, using fallback data")
        return build_indicator_hub_fallback(tenant=tenant, admin_view=admin_view)
    hub = copy.deepcopy(hub)
    tenant_slug = str((tenant or {}).get("slug") or "").strip().lower()
    if not admin_view and tenant_slug:
        smart_items = [
            item for item in (hub.get("smart_items") or [])
            if str(item.get("tenant_slug") or "").strip().lower() in {"", tenant_slug}
        ]
        lake_items = list(hub.get("lake_items") or [])
        items = smart_items + lake_items
        smart_ids = {item.get("id") for item in smart_items if item.get("id")}
        hub["smart_items"] = smart_items
        hub["items"] = items
        hub["anomalies"] = [
            item for item in (hub.get("anomalies") or [])
            if item.get("related_indicator_id") in smart_ids or item.get("related_indicator_id") in {lake.get("id") for lake in lake_items}
        ]
        hub["summary"] = {
            "total": len(items),
            "smart_total": len(smart_items),
            "lake_total": len(lake_items),
            "enabled": sum(1 for item in items if item.get("enabled")),
            "warnings": sum(1 for item in items if item.get("status") == "warning"),
            "attention": sum(1 for item in items if item.get("status") == "attention"),
            "anomalies": len(hub["anomalies"]),
        }
    advisor_name = tenant.get("advisor") if isinstance(tenant, dict) else ""
    for item in hub.get("smart_items", []):
        if advisor_name and item.get("owner") in {"平台研究运营", "平台宏观组", ""}:
            item["owner"] = advisor_name
    return hub


def gen_feed_boards(market_items):
    boards = []
    board_map = {}
    for item in market_items:
        board_name = item.get("board") or "自选股"
        if board_name not in board_map:
            board_map[board_name] = {
                "name": board_name,
                "warning_count": 0,
                "items": [],
            }
            boards.append(board_map[board_name])
        if item.get("alert_level") in {"warning", "attention"}:
            board_map[board_name]["warning_count"] += 1
        board_map[board_name]["items"].append(
            {
                "code": item["code"],
                "name": item["name"],
                "market": item["market"],
                "value": item["value"],
                "change": item["change"],
                "change_pct": item["change_pct"],
                "focus": item["focus"],
                "alert_level": item.get("alert_level", "normal"),
                "alert_text": item.get("alert_text", "当前无明显预警"),
                "signal_summary": item.get("signal_summary", ""),
            }
        )
    return boards


def gen_feed_boards_from_watchlist_details(watchlist_details):
    board_map = {}
    boards = []
    for item in (watchlist_details or {}).values():
        board_name = item.get("industry") or item.get("focus") or "自选股"
        if board_name not in board_map:
            board_map[board_name] = {
                "name": board_name,
                "warning_count": 0,
                "items": [],
            }
            boards.append(board_map[board_name])
        if item.get("alert_level") in {"warning", "attention"}:
            board_map[board_name]["warning_count"] += 1
        board_map[board_name]["items"].append(
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "market": item.get("market"),
                "value": item.get("price", 0),
                "change": item.get("change", 0),
                "change_pct": item.get("change_pct", 0),
                "focus": item.get("focus") or item.get("industry") or "个股跟踪",
                "alert_level": item.get("alert_level", "normal"),
                "alert_text": item.get("alert_text", "当前无明显预警"),
                "signal_summary": item.get("signal_summary", ""),
            }
        )
    return boards


def gen_watchlist_details():
    def build_kline_series(stock_code, base_price):
        rng = random.Random(f"kline:{stock_code}")
        close = float(base_price) * (0.9 + rng.random() * 0.2)
        current_date = datetime.now() - timedelta(days=33)
        series = []
        while len(series) < 24:
            current_date += timedelta(days=1)
            if current_date.weekday() >= 5:
                continue
            open_price = close * (1 + rng.uniform(-0.018, 0.018))
            close_price = open_price * (1 + rng.uniform(-0.035, 0.035))
            high_price = max(open_price, close_price) * (1 + rng.uniform(0.004, 0.022))
            low_price = min(open_price, close_price) * (1 - rng.uniform(0.004, 0.022))
            series.append({
                "date": current_date.strftime("%m-%d"),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
            })
            close = close_price
        return series

    details = {
        "600519": {
            "code": "600519",
            "name": "贵州茅台",
            "market": "SH",
            "price": 1688.20,
            "change": 12.80,
            "change_pct": 0.76,
            "industry": "高端白酒",
            "kline": build_kline_series("600519", 1688.20),
            "authors": [
                {"id": 1, "name": "财经老王", "avatar": "👑", "tier": "种子作者", "angle": "消费龙头的现金流韧性仍在，核心要看估值是否已经反映需求修复。"},
                {"id": 3, "name": "量化老师陈明", "avatar": "📊", "tier": "成长作者", "angle": "从历史分位看，当前更适合做中期配置跟踪，不建议把短期波动当趋势。"},
            ],
            "fundamental": {
                "summary": "品牌力和现金流仍是最大护城河，当前争议主要集中在增速放缓后的估值承受力。",
                "metrics": [
                    {"label": "收入增速", "value": "15.2%", "note": "较去年同期放缓但仍稳健"},
                    {"label": "净利率", "value": "52.4%", "note": "维持高位"},
                    {"label": "ROE", "value": "31.8%", "note": "资本效率仍强"},
                    {"label": "估值分位", "value": "43%", "note": "回到中枢附近"},
                ],
                "thesis": [
                    "品牌定价权和渠道控制能力仍强。",
                    "若消费修复延续，盈利稳定性会继续支撑估值。",
                    "风险在于市场对高端消费增速放缓的容忍度下降。",
                ],
            },
            "forecast": {
                "label": "基本面判断",
                "verdict": "稳健跟踪",
                "confidence": "中高",
                "band": "未来 1-2 个季度更像利润兑现验证，而不是高弹性重估。",
                "drivers": [
                    {"label": "盈利稳定性", "score": "+2.4", "note": "现金流和利润率支撑强"},
                    {"label": "估值弹性", "score": "+0.8", "note": "缺少强扩张催化"},
                    {"label": "行业景气", "score": "+1.2", "note": "消费修复温和"},
                ],
            },
        },
        "300750": {
            "code": "300750",
            "name": "宁德时代",
            "market": "SZ",
            "price": 212.36,
            "change": -3.84,
            "change_pct": -1.78,
            "industry": "动力电池",
            "kline": build_kline_series("300750", 212.36),
            "authors": [
                {"id": 5, "name": "新能源猎手阿强", "avatar": "⚡", "tier": "观察作者", "angle": "更重要的是看新技术路线和海外出货，而不是单日股价波动。"},
                {"id": 4, "name": "全球宏观James", "avatar": "🌐", "tier": "成长作者", "angle": "海外需求和原材料价格波动会持续影响预期。"},
            ],
            "fundamental": {
                "summary": "核心变量不在于短期情绪，而在于全球份额、技术迭代和海外市场进度。",
                "metrics": [
                    {"label": "收入增速", "value": "18.6%", "note": "出口拉动明显"},
                    {"label": "毛利率", "value": "24.1%", "note": "原材料波动后修复"},
                    {"label": "研发占比", "value": "7.8%", "note": "维持高投入"},
                    {"label": "估值分位", "value": "36%", "note": "低于行业乐观期"},
                ],
                "thesis": [
                    "全球动力电池龙头地位仍稳固。",
                    "技术升级和海外布局决定中期估值空间。",
                    "要警惕行业价格竞争压缩利润率。",
                ],
            },
            "forecast": {
                "label": "基本面判断",
                "verdict": "继续观察",
                "confidence": "中",
                "band": "未来 1-2 个季度需要继续看价格战和新技术兑现。",
                "drivers": [
                    {"label": "技术路线", "score": "+2.0", "note": "新产品是正向变量"},
                    {"label": "价格竞争", "score": "-1.6", "note": "盈利承压"},
                    {"label": "海外出货", "score": "+1.5", "note": "中期支撑项"},
                ],
            },
        },
        "00700": {
            "code": "00700",
            "name": "腾讯控股",
            "market": "HK",
            "price": 388.40,
            "change": 5.60,
            "change_pct": 1.46,
            "industry": "港股互联网",
            "kline": build_kline_series("00700", 388.40),
            "authors": [
                {"id": 2, "name": "投资女神Lisa", "avatar": "💎", "tier": "种子作者", "angle": "广告、游戏和回购共同支撑估值修复，关键还是财报兑现。"},
                {"id": 2, "name": "港股研究员", "avatar": "🏙️", "tier": "观察作者", "angle": "这类资产更适合中期配置，而不是追逐情绪高点。"},
            ],
            "fundamental": {
                "summary": "估值修复逻辑仍在，核心看广告恢复、游戏流水和资本回报延续。",
                "metrics": [
                    {"label": "收入增速", "value": "9.8%", "note": "恢复中"},
                    {"label": "经营利润率", "value": "32.1%", "note": "效率改善"},
                    {"label": "回购强度", "value": "高", "note": "资本回报积极"},
                    {"label": "估值分位", "value": "28%", "note": "修复但未过热"},
                ],
                "thesis": [
                    "现金流和资产质量在港股互联网中仍属头部。",
                    "回购与业务恢复共同支撑估值中枢。",
                    "风险在于监管和宏观消费修复不及预期。",
                ],
            },
            "forecast": {
                "label": "基本面判断",
                "verdict": "偏积极",
                "confidence": "中高",
                "band": "若财报继续兑现，估值还有温和修复空间。",
                "drivers": [
                    {"label": "业务恢复", "score": "+2.1", "note": "广告与游戏改善"},
                    {"label": "股东回报", "score": "+1.9", "note": "回购支撑明确"},
                    {"label": "政策扰动", "score": "-0.8", "note": "仍需观察"},
                ],
            },
        },
        "688981": {
            "code": "688981",
            "name": "中芯国际",
            "market": "SH",
            "price": 46.52,
            "change": 1.18,
            "change_pct": 2.60,
            "industry": "半导体制造",
            "kline": build_kline_series("688981", 46.52),
            "authors": [
                {"id": 1, "name": "财经老王", "avatar": "👑", "tier": "种子作者", "angle": "要拆开看产能利用率、成熟制程景气和国产替代订单，不要只看情绪。"},
                {"id": 4, "name": "宏观策略师", "avatar": "🎯", "tier": "成长作者", "angle": "产业政策和资本开支周期决定中期想象空间。"},
            ],
            "fundamental": {
                "summary": "国产替代逻辑稳固，但盈利释放节奏仍依赖景气和产能利用率改善。",
                "metrics": [
                    {"label": "收入增速", "value": "14.1%", "note": "受益国产订单"},
                    {"label": "产能利用率", "value": "82%", "note": "仍在恢复"},
                    {"label": "资本开支", "value": "高位", "note": "扩产持续"},
                    {"label": "估值分位", "value": "49%", "note": "预期已反映部分利好"},
                ],
                "thesis": [
                    "国产替代是长期逻辑，订单确定性高。",
                    "短中期要看景气恢复与盈利兑现速度。",
                    "资本开支高、回报兑现慢会压制市场耐心。",
                ],
            },
            "forecast": {
                "label": "基本面判断",
                "verdict": "积极跟踪",
                "confidence": "中",
                "band": "更像中期产业趋势资产，短期波动会比较大。",
                "drivers": [
                    {"label": "国产替代", "score": "+2.6", "note": "长期主逻辑"},
                    {"label": "盈利兑现", "score": "+0.9", "note": "恢复中"},
                    {"label": "资本开支", "score": "-1.1", "note": "拖累利润释放"},
                ],
            },
        },
        "600036": {
            "code": "600036",
            "name": "招商银行",
            "market": "SH",
            "price": 41.86,
            "change": 0.22,
            "change_pct": 0.53,
            "industry": "银行",
            "kline": build_kline_series("600036", 41.86),
            "authors": [
                {"id": 4, "name": "全球宏观James", "avatar": "🌐", "tier": "成长作者", "angle": "利率环境和资产质量是银行股的核心框架。"},
                {"id": 3, "name": "量化老师陈明", "avatar": "📊", "tier": "成长作者", "angle": "这类资产更适合放在组合稳定器角色里看。"},
            ],
            "fundamental": {
                "summary": "核心看息差、资产质量与分红能力，作为组合稳定器价值仍在。",
                "metrics": [
                    {"label": "ROE", "value": "14.8%", "note": "银行中仍具优势"},
                    {"label": "不良率", "value": "0.96%", "note": "资产质量稳"},
                    {"label": "股息率", "value": "5.1%", "note": "防守价值明显"},
                    {"label": "估值分位", "value": "33%", "note": "偏低区间"},
                ],
                "thesis": [
                    "资产质量和零售能力构成核心护城河。",
                    "在低利率阶段，分红和稳健性更受重视。",
                    "息差继续承压会影响估值弹性。",
                ],
            },
            "forecast": {
                "label": "基本面判断",
                "verdict": "稳健配置",
                "confidence": "高",
                "band": "适合作为组合中的防守资产，预期收益更平稳。",
                "drivers": [
                    {"label": "股息支撑", "score": "+2.2", "note": "分红确定性强"},
                    {"label": "资产质量", "score": "+1.8", "note": "风险可控"},
                    {"label": "息差压力", "score": "-0.9", "note": "估值弹性有限"},
                ],
            },
        },
    }
    indicator_context = build_watchlist_indicator_context()
    for detail in details.values():
        signal_bundle = build_watchlist_signal_bundle(detail["code"], detail["name"], detail.get("industry"), indicator_context)
        detail["indicator_context"] = signal_bundle
        detail["focus"] = detail.get("industry") or detail.get("focus") or "个股跟踪"
        detail["alert_level"] = signal_bundle["board_alert_level"]
        detail["alert_text"] = sanitize_user_facing_source_text(signal_bundle["board_alert_text"], fallback="当前无明显预警")
        detail["signal_summary"] = signal_bundle["board_summary"]
        detail["anomaly_text"] = signal_bundle["anomaly_text"]
        detail["related_indicator_ids"] = signal_bundle["related_indicator_ids"]
        detail["related_indicator_names"] = signal_bundle["related_indicator_names"]
        fundamental = detail.get("fundamental") if isinstance(detail.get("fundamental"), dict) else {}
        base_summary = str(fundamental.get("summary") or "").strip()
        fundamental["summary"] = f"{base_summary} 当前关联指标信号：{signal_bundle['board_summary']}" if base_summary else signal_bundle["board_summary"]
        base_metrics = fundamental.get("metrics") if isinstance(fundamental.get("metrics"), list) else []
        metric_labels = {str(item.get('label') or '') for item in base_metrics if isinstance(item, dict)}
        for metric in signal_bundle["metrics"]:
            if metric["label"] not in metric_labels:
                base_metrics.append(metric)
        for metric in base_metrics:
            if not isinstance(metric, dict):
                continue
            metric["note"] = sanitize_user_facing_source_text(metric.get("note") or "", fallback=str(metric.get("note") or "").strip())
        fundamental["metrics"] = base_metrics[:6]
        base_thesis = fundamental.get("thesis") if isinstance(fundamental.get("thesis"), list) else []
        normalized_thesis = []
        seen_thesis = set()
        for item in base_thesis + [item for item in signal_bundle["thesis"] if item not in base_thesis]:
            text = sanitize_user_facing_source_text(item, fallback=str(item or "").strip())
            if not text or text in seen_thesis:
                continue
            seen_thesis.add(text)
            normalized_thesis.append(text)
        fundamental["thesis"] = normalized_thesis[:5]
        detail["fundamental"] = fundamental
        forecast = detail.get("forecast") if isinstance(detail.get("forecast"), dict) else {}
        if signal_bundle["board_alert_level"] == "warning":
            forecast["verdict"] = "重点观察"
            forecast["confidence"] = "中"
            forecast["band"] = f"{forecast.get('band') or ''} 当前行业关联指标存在预警，优先核查 {signal_bundle['related_indicator_names'][0] if signal_bundle['related_indicator_names'] else '核心信号'}。".strip()
        elif signal_bundle["board_alert_level"] == "attention":
            forecast["band"] = f"{forecast.get('band') or ''} 当前行业关联指标进入关注区间，建议跟踪 {signal_bundle['related_indicator_names'][0] if signal_bundle['related_indicator_names'] else '核心信号'}。".strip()
        drivers = forecast.get("drivers") if isinstance(forecast.get("drivers"), list) else []
        if signal_bundle["related_indicator_names"]:
            drivers = [
                {
                    "label": "指标湖联动",
                    "score": "+0.6" if signal_bundle["board_alert_level"] == "normal" else ("-0.9" if signal_bundle["board_alert_level"] == "warning" else "-0.3"),
                    "note": f"当前主要受 {signal_bundle['related_indicator_names'][0]} 影响",
                }
            ] + drivers
        forecast["drivers"] = drivers[:4]
        detail["forecast"] = forecast
    return details


def strip_watchlist_forecast_payload(detail):
    normalized = copy.deepcopy(detail or {})
    normalized.pop("forecast", None)
    return normalized


def apply_watchlist_feature_flags(detail, site_config=None):
    normalized = copy.deepcopy(detail or {})
    if not is_feature_enabled("stock_forecast", site_config):
        normalized = strip_watchlist_forecast_payload(normalized)
    return normalized

def gen_news_feed():
    news = [
        {
            "title": "美联储6月议息会议前瞻：降息预期升温，市场如何定价？",
            "tag": "全球要闻",
            "time": "10分钟前",
            "hot": True,
            "source_group": "全球要闻",
            "why": "它会直接影响美元、港股互联网和大宗商品的估值锚，是当前最核心的宏观变量之一。",
        },
        {
            "title": "【深度】新能源车渗透率突破50%，产业链投资机会梳理",
            "tag": "自选股相关",
            "time": "32分钟前",
            "hot": True,
            "source_group": "自选股",
            "why": "你的自选股里有动力电池样本，且当前预警点正集中在价格竞争和技术路线验证。",
        },
        {
            "title": "高盛最新报告：A股估值修复空间测算",
            "tag": "全球要闻",
            "time": "1小时前",
            "hot": False,
            "source_group": "全球要闻",
            "why": "它决定科技成长板块当前估值是不是已经提前反映乐观预期，影响面广。",
        },
        {
            "title": "专家会议纪要：某头部消费品牌Q2经营数据点评",
            "tag": "大V关注趋势",
            "time": "2小时前",
            "hot": False,
            "source_group": "大V趋势",
            "why": "与大V近期关注的消费修复和高端白酒判断高度相关，适合作为租户知识延伸阅读。",
        },
        {
            "title": "另类数据：卫星图像显示主要港口吞吐量环比回升8%",
            "tag": "全球要闻",
            "time": "3小时前",
            "hot": False,
            "source_group": "全球要闻",
            "why": "它是宏观修复是否真正落地的交叉验证项，不是普通资讯，而是影响顺周期判断的旁证。",
        },
        {
            "title": "DeepSeek最新研究：AI算力需求2026年增速预测上调至180%",
            "tag": "大V关注趋势",
            "time": "4小时前",
            "hot": True,
            "source_group": "大V趋势",
            "why": "它和当前科技成长板块的核心主线一致，也会被大V方法模板优先引用为趋势依据。",
        },
    ]
    return news

def gen_revenue_trend():
    months = []
    base_date = datetime(2025, 7, 1)
    for i in range(12):
        d = base_date + timedelta(days=30*i)
        months.append({
            "month": d.strftime("%Y-%m"),
            "revenue": int(18000 + i * 5200 + random.randint(-1800, 2600)),
            "users": int(180 + i * 58 + random.randint(-12, 26)),
        })
    return months

def gen_user_segments():
    return [
        {"segment": "免费用户", "count": 880, "pct": 69.4},
        {"segment": "基础会员", "count": 214, "pct": 16.9},
        {"segment": "专业会员", "count": 128, "pct": 10.1},
        {"segment": "机构试点", "count": 34, "pct": 2.7},
        {"segment": "种子KOL", "count": 12, "pct": 0.9},
    ]
