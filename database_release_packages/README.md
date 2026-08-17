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
  order only after the target release ledger has been verified. The package
  ledger skips versions already applied to the target. If the target ledger is
  empty, historical packages are marked `unverified` rather than assumed to be
  pending, and batch execution is blocked to prevent replaying old data.
- `当前完整数据库`: creates a full pre-release replacement and preserves the
  previous target database as a rollback database.

Individual packages remain selectable for controlled repair. Each package has
its own checksum and cannot be silently changed after it has been released.

## Local-To-Target Delta

The 5051 controller can scan the local database against Staging or Production
and generate a new versioned package from the current difference. Generated
packages include `DELTA_TARGET=staging` or `DELTA_TARGET=production`; this
allows a newly scanned delta to be released without replaying historical
packages whose target ledger is missing. The generated SQL is additive only:
it upserts local new or changed rows, retains target-only rows, and generates
only additive DDL. Destructive or incompatible schema changes are reported as
manual blockers and are never generated automatically.

Example `release.env`:

```bash
RELEASE_VERSION=v1.0.0
PACKAGE_TYPE=master_data
TITLE=Market catalog refresh
```

Packages are immutable after release. Create a new dated version folder for
every correction. The release controller records the version, type, checksum,
target, execution time and status in `database_release_packages`.
