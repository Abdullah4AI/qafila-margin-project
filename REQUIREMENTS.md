# Delivery checklist

Read before implementation: `README.md`, `BRIEF.md`, the existing runner, dbt configuration and contract checker. The initial checkout was clean at `9d34e80` on `main`; `origin` is the requested Abdullah4AI repository. There were no nested Markdown files or applicable `AGENTS.md` files in the checkout or its parent directories.

## Build

- [x] Retain the supplied dependencies and catalog configuration; support both CLI paths.
- [x] Load the four required SQLite tables and every matching supplier CSV into `raw`, with source filenames, without duplicates on rerun.
- [x] Keep raw supplier text; handle BOM, column drift, Arabic digits, decimal commas and trimmed SKUs in staging.
- [x] Quarantine every rejected supplier row, with unknown SKU taking priority over invalid cost.
- [x] Resolve duplicate SKU/date quotes by filename, carry missing weeks forward and collapse unchanged costs into exclusive SCD2 intervals.
- [x] Apply delivered/positive-quantity/start-date eligibility using Riyadh order dates; cost each eligible line at its historical price.
- [x] Publish the exact three contracted tables with their required types and grains, retaining uncosted revenue separately.
- [x] Update Iceberg tables in place; leave identical reruns unchanged and retain readable pre-correction snapshots.
- [x] Add at least six meaningful passing dbt tests and independent numerical/integration coverage.

## Verify and deliver

- [x] Compare every output against an independent reference for the course seed, seed 11 and a third local seed.
- [x] Exercise baseline reruns, late corrections, corrected reruns and snapshot time travel.
- [x] Test edge cases: unchanged/missing quotes, correction precedence, invalid/unknown costs, time boundaries and uncosted lines.
- [x] Run the supplied contract checker, Python syntax/static checks and a fresh-checkout reproduction.
- [x] Replace README placeholders with design/grains, observed issue counts, exact test and snapshot evidence, scaling limits and truthful AI assistance disclosure.
- [x] Use only Abdullah AlRashoudi's name; include no personal identifier, secrets, generated data or warehouse files.
- [x] Review changes and staged files, commit real milestones, verify origin, push to the same repository and verify remote SHA/available CI.

No web UI is requested. Google Sheet submission and any public deployment are outside this task's authorization.

Validation on 2026-10-22: 40 dbt tests per build; 10 unit tests; independent comparisons across seeds 2026, 11 and 73; 18 integration builds including boundary and empty cases; corrected and original snapshots verified; supplied checker 22/22 on each generated dataset. A fresh tracked checkout passed the documented install/generate/run/check sequence. Python compilation, tabnanny, existing-system mypy and whitespace checks passed.

Delivery: fast-forwarded the tested implementation onto `main` and pushed to the original repository. Read back the remote commit successfully. GitHub reported no Actions runs, check runs or commit statuses; the repository has no CI workflow, so the test evidence above is local.
