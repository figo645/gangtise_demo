import unittest

from src.domain.watchlist_analysis_services import build_watchlist_kline_analysis


def candle(day, close, volume):
    return {
        "date": f"2026-01-{day:02d}",
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": volume,
    }


class WatchlistKlineAnalysisBddTest(unittest.TestCase):
    def test_insufficient_history_is_explicit_and_never_invents_250_day_trend(self):
        result = build_watchlist_kline_analysis([candle(index, 100 + index, 1000) for index in range(1, 31)])

        self.assertEqual(result["sample_size"], 30)
        self.assertEqual(result["trends"]["long"]["label"], "样本不足")
        self.assertEqual(result["trends"]["medium"]["label"], "样本不足")
        self.assertEqual(result["trends"]["short"]["label"], "上行")
        self.assertEqual(result["trends"]["long"]["window"], 90)

    def test_price_and_volume_signals_are_classified_as_strong_or_weak(self):
        rows = [candle(index, 100 + index * 0.1, 1000) for index in range(1, 25)]
        rows.append(candle(25, 150, 2500))
        result = build_watchlist_kline_analysis(rows)

        self.assertTrue(result["events"])
        self.assertEqual(result["events"][-1]["strength"], "强异动")
        self.assertEqual(result["events"][-1]["driver"], "待人工归因")

    def test_max_drawdown_and_missing_industry_baseline_are_reported(self):
        rows = [candle(1, 100, 1000), candle(2, 120, 1000), candle(3, 90, 1000)]
        result = build_watchlist_kline_analysis(rows)

        self.assertEqual(result["max_drawdown_pct"], -25.0)
        self.assertNotIn("relative_strength", result)

    def test_conclusion_and_limitations_use_plain_investor_language(self):
        result = build_watchlist_kline_analysis([candle(index, 100 + index, 1000) for index in range(1, 31)])

        self.assertIn("震荡为主", result["conclusion"])
        self.assertNotIn("趋势画像", result["conclusion"])
        self.assertNotIn("90日、60日、20日", result["conclusion"])
        self.assertIn("历史数据太少", result["limitations"][0])


if __name__ == "__main__":
    unittest.main()
