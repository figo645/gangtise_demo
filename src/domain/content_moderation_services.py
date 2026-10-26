import hashlib
import json


VALID_SOURCE_TYPES = {"insight", "comment", "kline_annotation"}
RISK_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _db():
    from src.domain.core_services import get_db

    return get_db()


def inspect_and_record_content(content, source_type, tenant_slug="", entity_id="", actor_user_id="", actor_name=""):
    """Record every content submission; a keyword hit is an alert, not a publish block."""
    normalized_type = str(source_type or "").strip().lower()
    if normalized_type not in VALID_SOURCE_TYPES:
        raise ValueError("content_moderation_source_type_invalid")
    text = str(content or "")
    normalized = text.casefold()
    db = _db()
    rules = db.execute(
        "SELECT id, keyword, category, risk_level FROM content_moderation_keywords WHERE enabled = TRUE ORDER BY id"
    ).fetchall()
    matches = []
    for rule in rules:
        keyword = str(rule.get("keyword") or "").strip()
        if keyword and keyword.casefold() in normalized:
            matches.append({
                "id": int(rule["id"]),
                "keyword": keyword,
                "category": str(rule.get("category") or ""),
                "risk_level": str(rule.get("risk_level") or "medium"),
            })
    risk = max((item["risk_level"] for item in matches), key=lambda item: RISK_ORDER.get(item, 0), default="none")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    db.execute(
        """INSERT INTO content_moderation_audits
           (tenant_slug, source_type, entity_id, actor_user_id, actor_name, result, risk_level, matched_keywords_json, content_sha256, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?, CURRENT_TIMESTAMP::text)""",
        (
            str(tenant_slug or "").strip().lower()[:80], normalized_type,
            str(entity_id or "").strip()[:180], str(actor_user_id or "").strip()[:120],
            str(actor_name or "").strip()[:120], "alert" if matches else "clear", risk,
            json.dumps(matches, ensure_ascii=False), digest,
        ),
    )
    db.commit()
    return {"result": "alert" if matches else "clear", "risk_level": risk, "matches": matches, "content_sha256": digest}


def list_content_moderation_keywords(include_disabled=True):
    where = "" if include_disabled else "WHERE enabled = TRUE"
    return [dict(row) for row in _db().execute(
        f"SELECT id, keyword, category, risk_level, enabled, description, created_by, updated_by, created_at, updated_at FROM content_moderation_keywords {where} ORDER BY category, keyword"
    ).fetchall()]


def save_content_moderation_keyword(keyword, category="金融合规", risk_level="medium", enabled=True, description="", actor="", keyword_id=None):
    text = str(keyword or "").strip()
    category = str(category or "金融合规").strip() or "金融合规"
    level = str(risk_level or "medium").strip().lower()
    if not text or len(text) > 120:
        raise ValueError("moderation_keyword_invalid")
    if level not in {"low", "medium", "high"}:
        raise ValueError("moderation_risk_level_invalid")
    db = _db()
    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if keyword_id:
        cursor = db.execute(
            """UPDATE content_moderation_keywords SET keyword = ?, category = ?, risk_level = ?, enabled = ?, description = ?, updated_by = ?, updated_at = ? WHERE id = ?""",
            (text, category[:80], level, bool(enabled), str(description or "")[:500], str(actor or "")[:120], now, int(keyword_id)),
        )
        if cursor.rowcount != 1:
            raise ValueError("moderation_keyword_not_found")
        saved_id = int(keyword_id)
    else:
        cursor = db.execute(
            """INSERT INTO content_moderation_keywords (keyword, category, risk_level, enabled, description, created_by, updated_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (text, category[:80], level, bool(enabled), str(description or "")[:500], str(actor or "")[:120], str(actor or "")[:120], now, now),
        )
        saved_id = int(cursor.fetchone()["id"])
    db.commit()
    return next((item for item in list_content_moderation_keywords() if item["id"] == saved_id), None)


def delete_content_moderation_keyword(keyword_id):
    cursor = _db().execute("DELETE FROM content_moderation_keywords WHERE id = ?", (int(keyword_id),))
    if cursor.rowcount != 1:
        raise ValueError("moderation_keyword_not_found")
    _db().commit()
    return int(keyword_id)


def get_content_moderation_audit_report(limit=100, offset=0, source_type="", result="", tenant_slug=""):
    db = _db()
    conditions, params = [], []
    normalized_tenant = str(tenant_slug or "").strip().lower()
    if normalized_tenant:
        conditions.append("tenant_slug = ?")
        params.append(normalized_tenant)
    if source_type in VALID_SOURCE_TYPES:
        conditions.append("source_type = ?")
        params.append(source_type)
    if result in {"clear", "alert"}:
        conditions.append("result = ?")
        params.append(result)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    summary = db.execute(
        f"SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE result = 'alert') AS alerts, COUNT(*) FILTER (WHERE risk_level = 'high') AS high_risk FROM content_moderation_audits{where}",
        tuple(params),
    ).fetchone()
    chart_rows = db.execute(
        f"SELECT source_type, result, COUNT(*) AS count FROM content_moderation_audits{where} GROUP BY source_type, result ORDER BY source_type, result",
        tuple(params),
    ).fetchall()
    trend_rows = db.execute(
        f"""SELECT SUBSTRING(created_at, 1, 10) AS day,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE result = 'alert') AS alerts
            FROM content_moderation_audits{where}
            AND created_at >= (CURRENT_DATE - INTERVAL '29 days')::text
            GROUP BY SUBSTRING(created_at, 1, 10)
            ORDER BY day""" if where else
        """SELECT SUBSTRING(created_at, 1, 10) AS day,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE result = 'alert') AS alerts
            FROM content_moderation_audits
            WHERE created_at >= (CURRENT_DATE - INTERVAL '29 days')::text
            GROUP BY SUBSTRING(created_at, 1, 10)
            ORDER BY day""",
        tuple(params),
    ).fetchall()
    recent = db.execute(
        f"SELECT id, tenant_slug, source_type, entity_id, actor_user_id, actor_name, result, risk_level, matched_keywords_json, content_sha256, created_at FROM content_moderation_audits{where} ORDER BY id DESC LIMIT ? OFFSET ?",
        tuple(params + [max(1, min(int(limit or 100), 500)), max(0, int(offset or 0))]),
    ).fetchall()
    return {
        "summary": {key: int(value or 0) for key, value in dict(summary or {}).items()},
        "distribution": [dict(row) for row in chart_rows],
        "trend": [dict(row) for row in trend_rows],
        "logs": [dict(row) for row in recent],
        "limit": max(1, min(int(limit or 100), 500)),
        "offset": max(0, int(offset or 0)),
    }
