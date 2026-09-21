# Database Pipelines

Jenkins Job configuration uses these permanent repository paths:

```text
jenkinsfiles/database/Jenkinsfile.CI
jenkinsfiles/database/Jenkinsfile.CD
```

Do not put dates or product versions in either Jenkins Script Path. The paths
stay stable; the release identity is controlled by the fixed
`jenkinsfiles/database/release-manifest.json` location and its
`release_version`, migration names, and SHA-256 checksums.

The `migrations` array is also the execution order for that release. This
permits an explicitly reviewed metadata repair to run before a foreign-key
migration that depends on it; keep ordinary releases in numeric order.

For every production database release:

1. Add a new immutable `sql/postgres/NNN_description.sql` migration.
2. Update `release-manifest.json` with the release version and the exact file
   SHA-256. Do not edit a migration that has already reached production.
3. Run `Jenkinsfile.CI`; it validates the manifest before any production write.
4. Deploy the same Git commit to `/opt/devsource/gangtise_demo`.
5. Run `Jenkinsfile.CD` manually with the required confirmation text.

The Python runner validates the manifest before execution and verifies that
every listed migration is present in `schema_migrations` with the same checksum
after execution. A repeat run only verifies and skips ledgered migrations.
