# SQL 备份说明

当前目录按 `20260805` 这一轮备份拆成 3 类文件：

- `20260805_current_schema.sql`
  当前 SQLite 库的表结构备份。

- `20260805_master_data.sql`
  主数据备份，当前包含：
  `app_settings`
  `users`
  `indicator_definitions`
  `indicator_source_defs`
  `indicator_mapping_rules`

- `20260805_business_data.sql`
  业务数据备份，当前包含：
  `access_logs`
  `indicator_source_tests`
  `indicator_load_batches`
  `indicator_latest_values`
  `indicator_series`
  `indicator_kline_points`
  `indicator_anomalies`
  `indicator_raw_records`
  `indicator_clean_jobs`

恢复顺序建议：

1. 先执行 `20260805_current_schema.sql`
2. 再执行 `20260805_master_data.sql`
3. 最后执行 `20260805_business_data.sql`

重新生成方式：

```bash
./scripts/export_sql_backups.sh
```

如需指定数据库文件或输出目录：

```bash
./scripts/export_sql_backups.sh /path/to/db.sqlite /path/to/output
```
