-- Master data: the nine Market Overview indices and their AKShare collectors.
INSERT INTO app_settings (setting_key, setting_value, updated_at)
VALUES (
    'master_data:market_index_catalog:standard',
    $$
    {
      "version": "2026-08-12",
      "catalog_name": "市场一览标准指数",
      "quote_provider": "AKShare",
      "items": [
        {"indicator_code":"source_shanghai_index","name":"上证指数","security_code":"000001.SH","collector":"stock_zh_index_daily","symbol":"sh000001","market":"CN"},
        {"indicator_code":"source_shenzhen_index","name":"深证指数","security_code":"399001.SZ","collector":"stock_zh_index_daily","symbol":"sz399001","market":"CN"},
        {"indicator_code":"source_hsi","name":"恒生指数","collector":"stock_hk_index_daily_sina","symbol":"HSI","market":"HK"},
        {"indicator_code":"source_hscei","name":"国企指数","collector":"stock_hk_index_daily_sina","symbol":"HSCEI","market":"HK"},
        {"indicator_code":"source_hscci","name":"红筹指数","collector":"stock_hk_index_daily_sina","symbol":"HSCCI","market":"HK"},
        {"indicator_code":"source_dji","name":"道琼斯指数","collector":"index_us_stock_sina","symbol":".DJI","market":"US"},
        {"indicator_code":"source_nasdaq","name":"纳斯达克指数","collector":"index_us_stock_sina","symbol":".IXIC","market":"US"},
        {"indicator_code":"source_sp500","name":"标普500指数","collector":"index_us_stock_sina","symbol":".INX","market":"US"},
        {"indicator_code":"source_nikkei","name":"日经指数","collector":"index_global_hist_sina","symbol":"日经225指数","market":"JP"}
      ]
    }
    $$,
    CURRENT_TIMESTAMP::TEXT
)
ON CONFLICT (setting_key) DO UPDATE SET
    setting_value = EXCLUDED.setting_value,
    updated_at = EXCLUDED.updated_at;
