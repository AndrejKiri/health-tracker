# Database migrations

## When to add a migration

Add a numbered SQL file here whenever you need to change the schema
**after the initial deployment** (adding a column, adding an index,
altering a type, etc.).  The `db/init.sql` script only runs once, on
the very first `docker compose up` when the postgres volume is empty.
Subsequent schema changes must be applied as migrations.

## Naming convention

```
NNN_short_description.sql
```

| Part | Rule |
|------|------|
| `NNN` | Zero-padded three-digit sequence, starting at `001`. |
| `short_description` | Snake-case, describes what changes. |

Examples:
- `001_add_sex_column_to_reference_ranges.sql`
- `002_add_events_source_index.sql`
- `003_lab_results_add_raw_value_column.sql`

## File format

Each migration file must be **idempotent** — safe to run twice without
error.  Use `IF NOT EXISTS`, `IF EXISTS`, and `ON CONFLICT` guards.

```sql
-- Migration 001: add sex column to reference_ranges
-- Applied: manually via psql or a migration tool

ALTER TABLE reference_ranges
    ADD COLUMN IF NOT EXISTS sex TEXT DEFAULT 'any'
        CHECK (sex IN ('any', 'male', 'female'));

-- Update existing rows to the current default
UPDATE reference_ranges SET sex = 'any' WHERE sex IS NULL;
```

## Applying migrations

Migrations are **not** applied automatically.  Run them manually:

```bash
# Apply a single migration
docker compose exec postgres psql \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -f /dev/stdin < db/migrations/001_add_sex_column_to_reference_ranges.sql

# Or copy the file in first
docker compose cp db/migrations/001_…sql postgres:/tmp/001.sql
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/001.sql
```

Keep a record in version control of which migrations have been applied
to each environment (e.g. a `migrations_applied.txt` per env, or use a
lightweight tool such as [Flyway](https://flywaydb.org/) or
[golang-migrate](https://github.com/golang-migrate/migrate) when the
number of migrations grows beyond a handful).

## Priority migration: sex-specific reference ranges

The current `reference_ranges` table stores a single row per measurement.
Several hematology values (Hematocrit, Hemoglobin, RBC, Ferritin) use
male-specific bounds — see the comment in `db/init.sql` for exact values.

Suggested migration once sex is tracked:

```sql
-- 001_add_sex_column_to_reference_ranges.sql
ALTER TABLE reference_ranges
    ADD COLUMN IF NOT EXISTS sex TEXT DEFAULT 'any'
        CHECK (sex IN ('any', 'male', 'female'));

-- The PRIMARY KEY is currently just (measurement).  To hold separate rows
-- per sex the constraint must be widened:
ALTER TABLE reference_ranges DROP CONSTRAINT IF EXISTS reference_ranges_pkey;
ALTER TABLE reference_ranges ADD PRIMARY KEY (measurement, sex);

-- Re-seed female ranges for the affected measurements after applying this.
```
