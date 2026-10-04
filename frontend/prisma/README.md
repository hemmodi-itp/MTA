# Database schema and migrations

`schema.prisma` is the single source of truth for the Postgres schema. The Python evaluation service
(`tools/agent_eval/run_store.py`) writes the same tables with raw SQL, so enum values and column names are a contract:
rename nothing without updating the Python side.

## Migrations (Prisma Migrate)

`prisma/migrations/` holds the history:

| Migration | What it does |
|---|---|
| `0_init` | Baseline: the schema as it was when the project still used `db push` |
| `20261003000000_run_control_status_indexes` | `RunStatus.cancelled`, `TestStatus.inconclusive`, `Run.heartbeatAt` and `Run.cancelRequested`, unique `(userId, githubUrl)` on Project, and the hot-path indexes |

| Command | Use |
|---|---|
| `npm run db:deploy` | Apply pending migrations (CI, production, a fresh checkout). Never resets data. |
| `npm run db:status` | Show which migrations are applied |
| `npm run db:migrate -- --name <change>` | Dev: create a migration from your schema edit and apply it (uses a shadow database) |
| `npm run db:migrate:create -- --name <change>` | Dev: create the migration SQL without applying it, to review or hand-edit it |
| `npm run db:push` | Dev only: sync a throwaway database without writing a migration. Don't use it on a database that has migrations |
| `npm run db:generate` | Regenerate the Prisma client (also runs on `npm install`) |
| `npm run db:seed` | Re-create the shared sample projects (users' own projects are never touched) |
| `npm run lint:schema` | Check that `PipelineStage` matches in `schema.prisma`, `src/lib/types.ts` and `api/pipeline.py` STEP_META |

### Existing database created with `db push`

If a database was set up before migrations existed, mark the baseline as applied once, then deploy the rest:

```sh
npx prisma migrate resolve --applied 0_init
npm run db:deploy
```

### Notes
- A new enum value (`ALTER TYPE ... ADD VALUE`) can't be used in the same migration that adds it. Put data changes
  that use it in a later migration.
- "One active run per project" is not a DB constraint: Prisma can't express a partial unique index. The API enforces it
  under a per-project `pg_advisory_xact_lock` (`src/lib/api/server/evaluation.ts`).
