from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.domain import market_services


def test_security_search_supports_documented_categories():
    assert market_services._normalize_security_search_categories("stock,index,fund") == ("stock", "index", "fund")
    assert market_services._normalize_security_search_categories(["dr", "invalid", "index"]) == ("dr", "index")


def test_remote_security_search_sends_categories_and_isolates_cache_key():
    response = {"code": "000000", "status": True, "data": {"list": [{"gtsCode": "000300.SH", "gtsName": "沪深300", "category": "index"}]}}
    with patch.object(market_services, "_load_watchlist_cache", return_value=None), \
         patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 1)) as call, \
         patch.object(market_services, "_save_security_master_candidates"), \
         patch.object(market_services, "_save_watchlist_cache") as save:
        items = market_services._search_remote_watchlist_candidates("沪深300", categories=("index",))

    assert items[0]["category"] == "index"
    assert call.call_args.args[1]["category"] == ["index"]
    assert save.call_args.args[1] == "index:source_hs300"
