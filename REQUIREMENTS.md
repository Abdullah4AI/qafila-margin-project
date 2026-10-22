# Delivery checklist

Read before implementation: `README.md`, `BRIEF.md`, the existing runner, dbt configuration and contract checker. The initial checkout was clean at `9d34e80` on `main`; `origin` is the requested Abdullah4AI repository. There were no nested Markdown files or applicable `AGENTS.md` files in the checkout or its parent directories.

## Build

- [ ] Retain the supplied dependencies and catalog configuration; support both CLI paths.
- [ ] Load the four required SQLite tables and every matching supplier CSV into `raw`, with source filenames, without duplicates on rerun.
- [ ] Keep raw supplier text; handle BOM, column drift, Arabic digits, decimal commas and trimmed SKUs in staging.
- [ ] Quarantine every rejected supplier row, with unknown SKU taking priority over invalid cost.
- [ ] Resolve duplicate SKU/date quotes by filename, carry missing weeks forward and collapse unchanged costs into exclusive SCD2 intervals.
- [ ] Apply delivered/positive-quantity/start-date eligibility using Riyadh order dates; cost each eligible line at its historical price.
- [ ] Publish the exact three contracted tables with their required types and grains, retaining uncosted revenue separately.
- [ ] Update Iceberg tables in place; leave identical reruns unchanged and retain readable pre-correction snapshots.
- [ ] Add at least six meaningful passing dbt tests and independent numerical/integration coverage.

## Verify and deliver

- [ ] Compare every output against an independent reference for the course seed, seed 11 and a third local seed.
- [ ] Exercise baseline reruns, late corrections, corrected reruns and snapshot time travel.
- [ ] Test edge cases: unchanged/missing quotes, correction precedence, invalid/unknown costs, time boundaries and uncosted lines.
- [ ] Run the supplied contract checker, Python syntax/static checks and a fresh-checkout reproduction.
- [ ] Replace README placeholders with design/grains, observed issue counts, exact test and snapshot evidence, scaling limits and truthful AI assistance disclosure.
- [ ] Use only Abdullah AlRashoudi's name; include no personal identifier, secrets, generated data or warehouse files.
- [ ] Review changes and staged files, commit real milestones, verify origin, push to the same repository and verify remote SHA/available CI.

No web UI is requested. Google Sheet submission and any public deployment are outside this task's authorization.
