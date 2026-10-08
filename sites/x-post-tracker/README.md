# X Post Tracker — Sites dashboard

The hosted dashboard is publicly readable following the owner's explicit request on 2026-10-08.

This is a static adaptation of the user's existing rendered Mac dashboard.
It retains its stock timelines, source links, classification explanations,
public disclosure events and coverage warnings. It also displays fetch,
classification, render and export timestamps, current known gaps, and age.

Collection and Codex inference remain in the existing Mac launchd job.
Publishing this site does not migrate X authentication or collection to a cloud
worker. There is no automatic Mac-to-Sites sync in this version.

## Refresh and verify

Create a consistent SQLite backup of the live runtime, render it with the existing
tracker modules, and run `snapshot_metrics.py` against that same frozen database.
Run `python3 export_snapshot.py --runtime FROZEN_RUNTIME --metrics METRICS_JSON
--history-progress HISTORY_JSON --baseline BASELINE_JSON`. The metrics must describe
the rendered database; latest per-account run receipts must be copied into its
`data/runs`, and the corresponding price refresh receipt must be copied into
`data/prices/last_status.json`. Export refuses an opinion backlog mismatch or a newer fetch receipt.
Health shows cumulative classification counts and explicitly separates overlapping
fetch snapshots from unique historical additions. Calendar-old prices are shown
without assuming that exchange holidays are missing sessions.
Then run `python3 verify_snapshot.py` and `node --check site.js`.
Use the Sites source workflow, save the exact verified source/archive, and
deploy its saved version with `deploy_site_version` for the public audience. Reuse `.openai/hosting.json`'s project identity.

The exporter is deliberately an explicit operation. It changes only this Site
checkout, never the Mac job, live database or launchd settings. Inspect a new
snapshot before publishing. Persistent credentials and unattended syncing have
not been created or configured.

Only `dist/index.html`, `dist/health.json`, and `dist/report.txt` are web assets.
No database, raw payloads, session cookies, model execution logs, backup files,
personal investment holdings or authentication metadata are exported.

## Read the data carefully

The 26-hour opinion report may have unclassified posts even when the most recent
10-hour scheduled run succeeds. Unknown stance and missing history are not
neutral. Trade directions and emotional tone do not count as opinion votes.
Trader weights and return figures use priors/closing-price proxies; they are not
validated real investor performance. A stale badge is computed from elapsed
time since the last successful fetch (7 hours), not from a browser refresh.
