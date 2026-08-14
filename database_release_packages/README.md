# Database Release Packages

All database changes created after this rule must be packaged here:

```text
database_release_packages/YYYY-MM-DD/vX.Y.Z/
```

Each package must contain `release.env` and exactly one SQL payload:

```text
release.env
master_data.sql   # package_type=master_data
```

or:

```text
release.env
data.sql          # package_type=data
```

or:

```text
release.env
schema.sql        # package_type=schema
```

`master_data` may update fixed catalogues, configurations, mapping rules and
seed records. It must not write user-created records. `data` is for a reviewed
business-data correction or import and must include idempotent SQL. `schema`
contains only non-destructive, idempotent DDL such as `CREATE TABLE IF NOT
EXISTS`, `ADD COLUMN IF NOT EXISTS` and indexes.

## Release Modes

The Admin database-release page provides two top-level choices:

- `全部剩余增量`: executes every allow-listed package in ascending version
  order. The package ledger skips versions already applied to the target.
- `当前完整数据库`: creates a full pre-release replacement and preserves the
  previous target database as a rollback database.

Individual packages remain selectable for controlled repair. Each package has
its own checksum and cannot be silently changed after it has been released.

Example `release.env`:

```bash
RELEASE_VERSION=v1.0.0
PACKAGE_TYPE=master_data
TITLE=Market catalog refresh
```

Packages are immutable after release. Create a new dated version folder for
every correction. The release controller records the version, type, checksum,
target, execution time and status in `database_release_packages`.
