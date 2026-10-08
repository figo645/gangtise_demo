"""Deterministic quantitative analysis for watchlist detail pages."""

from statistics import mean, stdev


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _returns(closes, window):
    result = []
    for index in range(window, len(closes)):
        base = closes[index - window]
        result.append((closes[index] / base - 1) * 100 if base else None)
    return [value for value in result if value is not None]


def _trend(closes, window):
    if len(closes) < window:
        return {"window": window, "label": "样本不足", "ma": None, "sample_size": len(closes)}
    ma = mean(closes[-window:])
    half = max(1, window // 2)
    earlier = mean(closes[-window:-half])
    recent = mean(closes[-half:])
    label = "上行" if closes[-1] > ma and recent > earlier else "下行" if closes[-1] < ma and recent < earlier else "震荡"
    return {"window": window, "label": label, "ma": round(ma, 4), "sample_size": len(closes)}


def build_watchlist_kline_analysis(candles=None):
    rows = []
    for item in candles or []:
        if not isinstance(item, dict):
            continue
        close = _number(item.get("close"))
        if close is None or close <= 0:
            continue
        rows.append({**item, "close": close, "high": _number(item.get("high")) or close,
                     "low": _number(item.get("low")) or close, "volume": _number(item.get("volume"))})
    rows.sort(key=lambda item: str(item.get("date") or ""))
    closes = [item["close"] for item in rows]
    daily = [((closes[index] / closes[index - 1]) - 1) * 100 for index in range(1, len(closes)) if closes[index - 1]]
    trends = {"long": _trend(closes, 90), "medium": _trend(closes, 60), "short": _trend(closes, 20)}
    labels = [item["label"] for item in trends.values() if item["label"] != "样本不足"]
    aligned = len(labels) >= 2 and len(set(labels)) == 1
    volatility = stdev(daily) if len(daily) > 1 else None
    profile = "题材脉冲型" if volatility is not None and volatility >= 4 else "趋势型" if aligned else "震荡型"

    events = []
    for index, row in enumerate(rows):
        if index < 2:
            continue
        change = (row["close"] / rows[index - 1]["close"] - 1) * 100
        prior = [((rows[pos]["close"] / rows[pos - 1]["close"]) - 1) * 100 for pos in range(max(1, index - 20), index)]
        volume_prior = [item["volume"] for item in rows[max(0, index - 20):index] if item.get("volume")]
        volume_avg = mean(volume_prior) if volume_prior else None
        price_signal = len(prior) > 1 and abs(change - mean(prior)) >= 2 * stdev(prior)
        volume_signal = bool(row.get("volume") and volume_avg and row["volume"] >= 2 * volume_avg)
        if price_signal or volume_signal:
            events.append({"date": row.get("date", ""), "candle_index": index, "change_pct": round(change, 2),
                           "volume_ratio": round(row["volume"] / volume_avg, 2) if row.get("volume") and volume_avg else None,
                           "strength": "强异动" if price_signal and volume_signal else "弱异动",
                           "driver": "待人工归因", "signal_validity": "待样本检验"})

    peak = None
    drawdowns = []
    for close in closes:
        peak = max(peak, close) if peak is not None else close
        drawdowns.append((close / peak - 1) * 100 if peak else 0)
    profile_text = {
        "趋势型": "趋势明确",
        "震荡型": "震荡为主",
        "题材脉冲型": "波动较大",
    }.get(profile, "暂时无法判断")
    direction_text = "不同时间段的走势方向基本一致" if aligned else "不同时间段的走势方向不完全一致"
    return {
        "sample_size": len(rows), "date_start": rows[0].get("date", "") if rows else "", "date_end": rows[-1].get("date", "") if rows else "",
        "profile": profile, "trend_alignment": aligned, "trends": trends,
        "rolling_returns": {"20d": [round(value, 2) for value in _returns(closes, 20)]},
        "volatility": {"daily_pct_std": round(volatility, 2) if volatility is not None else None},
        "events": events[-80:], "max_drawdown_pct": round(min(drawdowns), 2) if drawdowns else None,
        "conclusion": f"这只股票目前看起来是“{profile_text}”。{direction_text}，短期走势仍要结合后续行情观察。",
        "limitations": ["如果上市时间较短，历史数据太少，结论的参考价值会降低。", "看到突然大涨大跌，还要结合公告、新闻和行业变化判断原因。", "过去的走势只是参考，不能保证未来也会这样走。"],
    }
