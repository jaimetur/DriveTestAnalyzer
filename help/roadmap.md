# Product roadmap

## In this guide

| Task or topic | Go to |
| --- | --- |
| Roadmap presentation | [Open section](#roadmap-presentation) |
| Available now | [Open section](#available-now) |
| Planned product work | [Open section](#planned-product-work) |
| Architecture considerations | [Open section](#architecture-considerations) |

## Roadmap presentation

The roadmap is also a slide of its own, in the Overview deck (before the one-slider) and alone, in [Presentations](help.md#presentations): select it to open it in the slide viewer or download its PowerPoint.

```presentations
roadmap
```

## Available now

> [!NOTE]
> **Available versus planned.** The first section describes existing capabilities. Planned items are future work, not features available in the current release.

- Named, access-controlled workspaces.
- CDR ingestion, profiling, preview
- Vendor mapping datasets support.
- Region mapping polygon shapes support.
- CDR Analysis analysis and exports.
- Ad-hoc Chart Builder.
- Ad-hoc Query Builder.
- Template-driven NSA/SA Dashboards and PPT Reports.
- NetCheck City/Road Scoring & GAP Analysis with persistent jobs, aggregation controls and CSV/PPT exports.
- Shared Interactive Preview and filtered-data viewer.
- Report Template management and validation.
- Unified background jobs.
- App Logs with user/system execution identity.
- Portable and server-to-server environment transfer.
- Responsive layouts for compact mobile screens.
- Network Insights, Non-Qualified Calls (Alpha) and the Ticket Center.
- Bundle Report Templates and scheduled Reporting Jobs, with their Run History.
- Users, Modules Profiles, Workspace Groups and scheduled backups.

## Planned product work

- Umlaut CDRs: ingest, score and report them next to the NetCheck CDRs.
- Active Tests community: build with the tool the KPI and Scoring reports it generates today.
- Non-Qualified Calls: confirm the NQ definition (currently every result other than Completed) and take the module out of Alpha.
- Configuration datasets ingestion to enrich CDR dataset and combine them to extract combined info using SQL Queries or Report Templates.
- Additional validated KPI/chart contracts.
- Smart Orchestrator Logs Reports.

## Architecture considerations

Potential future scaling work:

- scale-out on AWS with an external background-worker queue;
- durable analytical caches;
- PostgreSQL instead of SQLite, a database for hundreds of concurrent users;
- stronger observability for long-running processing;
- automated end-to-end deployment verification.

Roadmap items are intentions, not commitments for a specific release. Refer to the Changelog for delivered behaviour.
