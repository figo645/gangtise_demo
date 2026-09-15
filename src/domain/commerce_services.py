"""Tenant-scoped subscription, payment and QR fan-acquisition services."""

import base64
import copy
import io
import json
import secrets
from datetime import datetime, timedelta

from src.runtime import app
from src.domain.core_services import (
    get_current_authenticated_user,
    get_tenant_by_slug,
    get_user_by_id,
    has_role_capability,
    is_feature_enabled,
    now_ts,
    get_db,
)

FAN_COMMERCE_SETTINGS_PREFIX = "tenant_fan_commerce_settings:"
_ORDER_TTL_MINUTES = 30
QR_REGISTRATION_TYPES_ENABLED = {"free"}


def _now():
    return datetime.now()


def _format_time(value):
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _load_setting(key, fallback=None):
    row = get_db().execute("SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)).fetchone()
    raw = (row or {}).get("setting_value") if isinstance(row, dict) else None
    try:
        decoded = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        decoded = None
    return decoded if isinstance(decoded, dict) else (fallback if isinstance(fallback, dict) else {})


def _save_setting(key, value):
    now = now_ts()
    get_db().execute(
        """
        INSERT INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value, updated_at = excluded.updated_at
        """,
        (key, json.dumps(value, ensure_ascii=False), now),
    )
    get_db().commit()


def _commerce_key(tenant_slug):
    return f"{FAN_COMMERCE_SETTINGS_PREFIX}{str(tenant_slug or '').strip().lower()}"


def normalize_commerce_settings(payload=None):
    raw = payload if isinstance(payload, dict) else {}
    provider = str(raw.get("payment_provider") or "manual_transfer").strip().lower()
    if provider not in {"manual_transfer", "wechat_native", "alipay"}:
        provider = "manual_transfer"
    return {
        "paywall_enabled": bool(raw.get("paywall_enabled", False)),
        "payment_provider": provider,
        "payment_instructions": str(raw.get("payment_instructions") or "提交订单后，请按收款说明完成支付；大V核验到账后自动开通订阅。").strip()[:1000],
        "collection_qr_url": str(raw.get("collection_qr_url") or "").strip()[:1000],
        # A paywall without a protected content policy is misleading. New
        # commerce configurations therefore default to subscriber-only reviews;
        # the DAv can explicitly keep reviews free when using subscriptions
        # only as a voluntary support product.
        "default_review_access": "free" if str(raw.get("default_review_access") or "subscriber").strip().lower() == "free" else "subscriber",
        "updated_at": str(raw.get("updated_at") or "").strip(),
    }


def load_tenant_commerce_settings(tenant_slug):
    return normalize_commerce_settings(_load_setting(_commerce_key(tenant_slug), {}))


def save_tenant_commerce_settings(tenant_slug, payload):
    slug = str(tenant_slug or "").strip().lower()
    if not slug:
        raise ValueError("tenant_slug_required")
    normalized = normalize_commerce_settings(payload)
    normalized["updated_at"] = now_ts()
    _save_setting(_commerce_key(slug), normalized)
    return normalized


def _product_dict(row):
    item = dict(row or {})
    return {
        "id": int(item.get("id") or 0),
        "tenant_slug": str(item.get("tenant_slug") or ""),
        "product_code": str(item.get("product_code") or ""),
        "name": str(item.get("name") or ""),
        "description": str(item.get("description") or ""),
        "price_cents": max(0, int(item.get("price_cents") or 0)),
        "price_yuan": round(max(0, int(item.get("price_cents") or 0)) / 100, 2),
        "billing_period_days": max(1, int(item.get("billing_period_days") or 30)),
        "status": str(item.get("status") or "draft"),
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
    }


def list_tenant_subscription_products(tenant_slug, include_archived=False):
    slug = str(tenant_slug or "").strip().lower()
    sql = "SELECT * FROM tenant_subscription_products WHERE tenant_slug = ?"
    params = [slug]
    if not include_archived:
        sql += " AND status = 'active'"
    sql += " ORDER BY updated_at DESC, id DESC"
    return [_product_dict(row) for row in get_db().execute(sql, tuple(params)).fetchall()]


def save_tenant_subscription_product(tenant_slug, payload, actor_user_id=None):
    slug = str(tenant_slug or "").strip().lower()
    raw = payload if isinstance(payload, dict) else {}
    product_id = raw.get("id")
    name = str(raw.get("name") or "").strip()[:80]
    description = str(raw.get("description") or "").strip()[:500]
    status = str(raw.get("status") or "active").strip().lower()
    if status not in {"draft", "active", "archived"}:
        raise ValueError("subscription_product_status_invalid")
    try:
        price_cents = int(round(float(raw.get("price_yuan", raw.get("price_cents", 0))) * (1 if "price_cents" in raw and "price_yuan" not in raw else 100)))
        period_days = int(raw.get("billing_period_days") or 30)
    except (TypeError, ValueError):
        raise ValueError("subscription_product_price_invalid")
    if not slug or not name or price_cents < 1 or period_days < 1 or period_days > 3660:
        raise ValueError("subscription_product_invalid")
    db = get_db()
    now = now_ts()
    if product_id:
        row = db.execute("SELECT * FROM tenant_subscription_products WHERE id = ? AND tenant_slug = ?", (int(product_id), slug)).fetchone()
        if not row:
            raise ValueError("subscription_product_not_found")
        db.execute(
            "UPDATE tenant_subscription_products SET name=?, description=?, price_cents=?, billing_period_days=?, status=?, updated_at=? WHERE id=?",
            (name, description, price_cents, period_days, status, now, int(product_id)),
        )
        db.commit()
        return _product_dict(db.execute("SELECT * FROM tenant_subscription_products WHERE id = ?", (int(product_id),)).fetchone())
    code = f"sub_{secrets.token_urlsafe(9).replace('-', '').replace('_', '')[:14].lower()}"
    row = db.execute(
        """INSERT INTO tenant_subscription_products
           (tenant_slug, product_code, name, description, price_cents, billing_period_days, status, created_by_user_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *""",
        (slug, code, name, description, price_cents, period_days, status, actor_user_id, now, now),
    ).fetchone()
    db.commit()
    return _product_dict(row)


def _subscription_dict(row):
    item = dict(row or {})
    return {
        "id": int(item.get("id") or 0),
        "tenant_slug": str(item.get("tenant_slug") or ""),
        "product_id": int(item.get("product_id") or 0),
        "product_name": str(item.get("product_name") or ""),
        "status": str(item.get("status") or ""),
        "starts_at": str(item.get("starts_at") or ""),
        "expires_at": str(item.get("expires_at") or ""),
    }


def list_active_fan_subscriptions(tenant_slug, user_id):
    now = now_ts()
    rows = get_db().execute(
        """SELECT s.*, p.name AS product_name FROM fan_subscriptions s
           JOIN tenant_subscription_products p ON p.id = s.product_id
           WHERE s.tenant_slug = ? AND s.user_id = ? AND s.status = 'active' AND s.expires_at > ?
           ORDER BY s.expires_at DESC""",
        (str(tenant_slug or "").strip().lower(), int(user_id or 0), now),
    ).fetchall()
    return [_subscription_dict(row) for row in rows]


def has_tenant_subscription_access(tenant_slug, user=None):
    actor = user or get_current_authenticated_user() or {}
    if has_role_capability(str(actor.get("role") or "").lower(), "dav") or has_role_capability(str(actor.get("role") or "").lower(), "admin"):
        return True
    actor_tenant = str(actor.get("tenant_slug") or "").strip().lower()
    if actor_tenant != str(tenant_slug or "").strip().lower() or not actor.get("id"):
        return False
    return bool(list_active_fan_subscriptions(tenant_slug, actor.get("id")))


def _expire_pending_orders():
    now = now_ts()
    db = get_db()
    db.execute("UPDATE fan_payment_orders SET status='expired', updated_at=? WHERE status='pending' AND expires_at <= ?", (now, now))
    db.commit()


def _order_dict(row):
    item = dict(row or {})
    return {
        "id": int(item.get("id") or 0), "order_no": str(item.get("order_no") or ""),
        "tenant_slug": str(item.get("tenant_slug") or ""), "product_id": int(item.get("product_id") or 0),
        "product_name": str(item.get("product_name") or ""), "amount_cents": int(item.get("amount_cents") or 0),
        "amount_yuan": round(int(item.get("amount_cents") or 0) / 100, 2), "currency": str(item.get("currency") or "CNY"),
        "payment_channel": str(item.get("payment_channel") or "manual_transfer"), "status": str(item.get("status") or "pending"),
        "payment_reference": str(item.get("payment_reference") or ""), "created_at": str(item.get("created_at") or ""),
        "expires_at": str(item.get("expires_at") or ""), "paid_at": str(item.get("paid_at") or ""),
    }


def create_fan_payment_order(tenant_slug, user, product_id):
    slug = str(tenant_slug or "").strip().lower()
    actor = user or {}
    if not actor.get("id") or str(actor.get("role") or "").lower() != "investor" or str(actor.get("tenant_slug") or "").lower() != slug:
        raise ValueError("subscription_purchase_forbidden")
    settings = load_tenant_commerce_settings(slug)
    if not is_feature_enabled("fan_commerce") or not settings.get("paywall_enabled"):
        raise ValueError("fan_commerce_disabled")
    product = get_db().execute("SELECT * FROM tenant_subscription_products WHERE id=? AND tenant_slug=? AND status='active'", (int(product_id), slug)).fetchone()
    if not product:
        raise ValueError("subscription_product_not_found")
    _expire_pending_orders()
    now = _now()
    order_no = f"FC{now.strftime('%Y%m%d%H%M%S')}{secrets.randbelow(900000) + 100000}"
    reference = f"{slug[:8].upper()}-{order_no[-8:]}"
    row = get_db().execute(
        """INSERT INTO fan_payment_orders
           (order_no, tenant_slug, user_id, product_id, amount_cents, currency, payment_channel, status, payment_reference, created_at, expires_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'CNY', ?, 'pending', ?, ?, ?, ?) RETURNING *""",
        (order_no, slug, int(actor["id"]), int(product["id"]), int(product["price_cents"]), settings["payment_provider"], reference, _format_time(now), _format_time(now + timedelta(minutes=_ORDER_TTL_MINUTES)), _format_time(now)),
    ).fetchone()
    get_db().commit()
    result = _order_dict(row)
    result["product_name"] = str(product["name"])
    result["payment_instructions"] = settings["payment_instructions"]
    result["collection_qr_url"] = settings["collection_qr_url"]
    return result


def list_fan_payment_orders(tenant_slug, user=None, limit=50):
    _expire_pending_orders()
    slug = str(tenant_slug or "").strip().lower()
    actor = user or {}
    is_operator = has_role_capability(str(actor.get("role") or "").lower(), "dav") or has_role_capability(str(actor.get("role") or "").lower(), "admin")
    sql = """SELECT o.*, p.name AS product_name, u.username FROM fan_payment_orders o
             JOIN tenant_subscription_products p ON p.id=o.product_id JOIN users u ON u.id=o.user_id
             WHERE o.tenant_slug=?"""
    params = [slug]
    if not is_operator:
        sql += " AND o.user_id=?"
        params.append(int(actor.get("id") or 0))
    sql += " ORDER BY o.created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit or 50), 200)))
    results = []
    for row in get_db().execute(sql, tuple(params)).fetchall():
        item = _order_dict(row)
        if is_operator:
            item["username"] = str(row.get("username") or "")
        results.append(item)
    return results


def confirm_fan_payment_order(tenant_slug, order_no, operator):
    slug = str(tenant_slug or "").strip().lower()
    role = str((operator or {}).get("role") or "").lower()
    if not (has_role_capability(role, "dav") or has_role_capability(role, "admin")):
        raise ValueError("dav_required")
    if not has_role_capability(role, "admin") and str((operator or {}).get("tenant_slug") or "").lower() != slug:
        raise ValueError("tenant_scope_forbidden")
    _expire_pending_orders()
    db = get_db()
    row = db.execute("""SELECT o.*, p.billing_period_days, p.name AS product_name FROM fan_payment_orders o
                      JOIN tenant_subscription_products p ON p.id=o.product_id WHERE o.order_no=? AND o.tenant_slug=?""", (str(order_no or ""), slug)).fetchone()
    if not row:
        raise ValueError("payment_order_not_found")
    if row.get("status") == "paid":
        return _order_dict(row)
    if row.get("status") != "pending":
        raise ValueError("payment_order_not_confirmable")
    now = _now()
    db.execute("UPDATE fan_payment_orders SET status='paid', paid_at=?, confirmed_by_user_id=?, confirmed_at=?, updated_at=? WHERE id=?", (_format_time(now), int(operator.get("id") or 0) or None, _format_time(now), _format_time(now), int(row["id"])))
    previous = db.execute("SELECT expires_at FROM fan_subscriptions WHERE tenant_slug=? AND user_id=? AND status='active' ORDER BY expires_at DESC LIMIT 1", (slug, int(row["user_id"]))).fetchone()
    start = now
    if previous and str(previous.get("expires_at") or "") > _format_time(now):
        try:
            start = datetime.strptime(str(previous["expires_at"]), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            start = now
    expires = start + timedelta(days=int(row["billing_period_days"]))
    db.execute("""INSERT INTO fan_subscriptions (tenant_slug, user_id, product_id, order_id, status, starts_at, expires_at, created_at, updated_at)
                  VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)""", (slug, int(row["user_id"]), int(row["product_id"]), int(row["id"]), _format_time(start), _format_time(expires), _format_time(now), _format_time(now)))
    db.commit()
    return _order_dict(db.execute("SELECT o.*, p.name AS product_name FROM fan_payment_orders o JOIN tenant_subscription_products p ON p.id=o.product_id WHERE o.id=?", (int(row["id"]),)).fetchone())


def _invite_dict(row, include_token=True):
    item = dict(row or {})
    result = {
        "id": int(item.get("id") or 0), "tenant_slug": str(item.get("tenant_slug") or ""),
        "source_label": str(item.get("source_label") or "扫码导入"), "note": str(item.get("note") or ""),
        "status": str(item.get("status") or "active"), "max_uses": int(item.get("max_uses") or 0),
        "used_count": int(item.get("used_count") or 0), "expires_at": str(item.get("expires_at") or ""),
        "qr_image_data": str(item.get("qr_image_data") or ""),
        "registration_type": str(item.get("registration_type") or "free"),
        "created_at": str(item.get("created_at") or ""),
    }
    if include_token:
        result["invite_token"] = str(item.get("invite_token") or "")
    return result


def _invite_available(invite):
    if not invite or str(invite.get("status") or "") != "active":
        return False
    if int(invite.get("max_uses") or 0) and int(invite.get("used_count") or 0) >= int(invite.get("max_uses") or 0):
        return False
    expires = str(invite.get("expires_at") or "").strip()
    return not expires or expires > now_ts()


def create_tenant_fan_qr_invite(tenant_slug, payload, actor_user_id=None):
    slug = str(tenant_slug or "").strip().lower()
    raw = payload if isinstance(payload, dict) else {}
    source = str(raw.get("source_label") or "扫码导入").strip()[:80] or "扫码导入"
    note = str(raw.get("note") or "").strip()[:240]
    qr_image_data = str(raw.get("qr_image_data") or "").strip()
    registration_type = str(raw.get("registration_type") or "free").strip().lower()
    if registration_type not in QR_REGISTRATION_TYPES_ENABLED:
        raise ValueError("fan_qr_registration_type_invalid")
    if qr_image_data and (not qr_image_data.startswith("data:image/") or len(qr_image_data) > 3 * 1024 * 1024):
        raise ValueError("fan_qr_image_invalid")
    try:
        max_uses = max(0, int(raw.get("max_uses") or 0))
        expiry_days = max(0, min(3650, int(raw.get("expiry_days") or 0)))
    except (TypeError, ValueError):
        raise ValueError("fan_qr_invite_invalid")
    now = _now()
    expires = _format_time(now + timedelta(days=expiry_days)) if expiry_days else ""
    token = secrets.token_urlsafe(18).replace("-", "").replace("_", "")
    row = get_db().execute(
        """INSERT INTO tenant_fan_qr_invites (invite_token, tenant_slug, source_label, note, status, max_uses, expires_at, qr_image_data, registration_type, created_by_user_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?) RETURNING *""",
        (token, slug, source, note, max_uses, expires, qr_image_data, registration_type, actor_user_id, _format_time(now), _format_time(now)),
    ).fetchone()
    get_db().commit()
    return _invite_dict(row)


def list_tenant_fan_qr_invites(tenant_slug, limit=30):
    rows = get_db().execute("SELECT * FROM tenant_fan_qr_invites WHERE tenant_slug=? ORDER BY created_at DESC LIMIT ?", (str(tenant_slug or "").strip().lower(), max(1, min(int(limit or 30), 100)))).fetchall()
    return [_invite_dict(row) for row in rows]


def get_tenant_fan_qr_invite(token):
    row = get_db().execute("SELECT * FROM tenant_fan_qr_invites WHERE invite_token=?", (str(token or "").strip(),)).fetchone()
    if not row or not _invite_available(row):
        return None
    return _invite_dict(row)


def claim_tenant_fan_qr_invite(token, user):
    invite = get_tenant_fan_qr_invite(token)
    if not invite:
        raise ValueError("fan_qr_invite_unavailable")
    actor = user or {}
    if str(actor.get("role") or "").lower() != "investor" or not actor.get("id"):
        raise ValueError("fan_qr_investor_required")
    if str(actor.get("tenant_slug") or "").lower() != invite["tenant_slug"]:
        raise ValueError("fan_qr_tenant_mismatch")
    db = get_db()
    exists = db.execute("SELECT id FROM tenant_fan_qr_invite_claims WHERE invite_id=? AND user_id=?", (invite["id"], int(actor["id"]))).fetchone()
    if not exists:
        db.execute("INSERT INTO tenant_fan_qr_invite_claims (invite_id, user_id, tenant_slug, claimed_at) VALUES (?, ?, ?, ?)", (invite["id"], int(actor["id"]), invite["tenant_slug"], now_ts()))
        db.execute("UPDATE tenant_fan_qr_invites SET used_count=used_count+1, updated_at=? WHERE id=?", (now_ts(), invite["id"]))
        db.execute("UPDATE users SET source_label=?, updated_at=? WHERE id=?", (f"扫码导入：{invite['source_label']}", now_ts(), int(actor["id"])))
        db.commit()
    return {"tenant_slug": invite["tenant_slug"], "source_label": invite["source_label"], "claimed": True}


def build_fan_commerce_payload(tenant_slug, user=None):
    slug = str(tenant_slug or "").strip().lower()
    actor = user or get_current_authenticated_user() or {}
    settings = load_tenant_commerce_settings(slug)
    subscriptions = list_active_fan_subscriptions(slug, actor.get("id")) if actor.get("id") else []
    return {
        "tenant_slug": slug,
        "enabled": bool(is_feature_enabled("fan_commerce") and settings.get("paywall_enabled")),
        "settings": {key: settings[key] for key in ("paywall_enabled", "payment_provider", "payment_instructions", "collection_qr_url", "default_review_access")},
        "products": list_tenant_subscription_products(slug),
        "subscriptions": subscriptions,
        "has_subscription": bool(subscriptions) or has_tenant_subscription_access(slug, actor),
        "can_view_paid_content": fan_can_view_paid_content(slug, actor),
        "orders": list_fan_payment_orders(slug, actor, limit=10) if actor.get("id") else [],
    }


def fan_can_view_paid_content(tenant_slug, user=None, access_mode="subscriber"):
    """Return whether the authenticated actor may receive protected fan content."""
    slug = str(tenant_slug or "").strip().lower()
    actor = user or get_current_authenticated_user() or {}
    normalized_access_mode = str(access_mode or "subscriber").strip().lower()
    if normalized_access_mode != "subscriber":
        return True
    if str(actor.get("role") or "").strip().lower() in {"admin", "dav"}:
        return True
    settings = load_tenant_commerce_settings(slug)
    if not (is_feature_enabled("fan_commerce") and settings.get("paywall_enabled")):
        return True
    return has_tenant_subscription_access(slug, actor)


def protect_tenant_review_snapshots(tenant_slug, snapshots, user=None):
    """Strip protected review bodies before they cross the server boundary."""
    protected = []
    for snapshot in snapshots if isinstance(snapshots, list) else []:
        item = copy.deepcopy(snapshot) if isinstance(snapshot, dict) else {}
        access_mode = str(item.get("access_mode") or "public").strip().lower()
        if access_mode not in {"public", "subscriber"}:
            access_mode = "public"
        item["access_mode"] = access_mode
        item["access_label"] = "订阅专享" if access_mode == "subscriber" else "常规笔记"
        if fan_can_view_paid_content(tenant_slug, user, access_mode=access_mode):
            protected.append(item)
            continue
        item["access_required"] = True
        item["access_notice"] = "订阅后查看完整洞见内容"
        item["summary"] = "该洞见内容面向订阅用户开放。"
        item["content_text"] = ""
        item["content"] = ""
        item["body_text"] = ""
        item["polished_input_text"] = ""
        item["selected_cards"] = []
        item["llm_models"] = []
        item["user_input_section"] = {}
        item["watchlist_analysis_section"] = {}
        item["evidence_chain_section"] = {}
        item["knowledge_attachments"] = []
        item["data_sources"] = []
        item["news_sources"] = []
        protected.append(item)
    return protected


def build_fan_safe_site_config(site_config, user=None):
    """Return a browser-safe site-config copy with paid review bodies removed."""
    config = copy.deepcopy(site_config if isinstance(site_config, dict) else {})
    role = str((user or {}).get("role") or "").strip().lower()
    if role in {"admin", "dav"}:
        return config
    tenants = config.get("tenants") if isinstance(config.get("tenants"), list) else []
    for tenant in tenants:
        if not isinstance(tenant, dict) or not isinstance(tenant.get("review_snapshots"), list):
            continue
        tenant["review_snapshots"] = protect_tenant_review_snapshots(
            tenant.get("slug"), tenant.get("review_snapshots"), user
        )
    return config


def build_qr_png_data_uri(content):
    """Render QR locally; no tracking URL or third-party QR generator is used."""
    try:
        import qrcode
    except ImportError as exc:
        raise RuntimeError("qrcode_dependency_missing") from exc
    image = qrcode.make(str(content or ""), border=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
