# Product roadmap

## In this guide

| Task or topic | Go to |
| --- | --- |
| Roadmap presentation | [Open section](#roadmap-presentation) |
| Available now | [Open section](#available-now) |
| Planned product work | [Open section](#planned-product-work) |
| Architecture considerations | [Open section](#architecture-considerations) |

## Roadmap presentation

The roadmap is also a slide of its own, in the Overview deck (before the one-slider) and alone, in [Product Presentations](presentations.md): select it to open it in the slide viewer or download its PowerPoint.

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
- Template-driven NSA/SA Designs and PPT Reports.
- NetCheck City/Road Scoring & GAP Analysis with persistent jobs, aggregation controls and CSV/PPT exports.
- Shared Interactive Preview and filtered-data viewer.
- Report Template management and validation.
- Unified background jobs.
- App Logs with user/system execution identity.
- Portable and server-to-server environment transfer.
- Responsive layouts for compact mobile screens.
- Network Insights, Non-Qualified Calls (Beta) and the Ticket Center.
- Bundle Report Templates and scheduled Reporting Jobs, with their Run History.
- Users, Modules Profiles, Workspace Groups and scheduled backups.
- The DT Analyzer RCA of Non-Qualified Calls, in every workspace, with rules each workspace can change.
- The CDR Field Dictionary of Workspace Config, and the Umlaut reader and field profile (Umlaut CDR stays coming soon until a multi-operator export validates it).
- The columnar store of the CDRs: Parquet copies read with the DuckDB engine by every module, with durable analytical caches (Network Insights 79 times faster, the Points Lost Map more than 300 times, a workspace database 10 times lighter).
- Tableau connected to the data of the workspace, through PostgreSQL with pg_duckdb.
- PPT Designer, whose charts are built as in Tableau, and slide comments written by rules or by GenAI (Kiro or Claude).
- The Layer 3 - DT Logs: the parsed drive test logs of each campaign, whose layers and signalling the maps of the Non-Qualified Calls and NQ Maps draw and the DT Analyzer RCA reads.

## Planned product work

- Germany pilot: a first test campaign in Germany.
- Umlaut and P3 CDRs: workspaces of each provider that keep its field names and values, with its own Scoring methodologies, PPT templates and Non-Qualified Calls rules. [Benchmarking Providers](benchmarking-providers.md) describes the status of each phase and what each module will have with Umlaut CDRs.
- Active Tests community: build with the tool the KPI and Scoring reports it generates today.
- Non-Qualified Calls: confirm the NQ definition (currently every result other than Completed in NetCheck CDRs; in Umlaut CDRs, the calls and tests marked NOT QUALIFIED), the Umlaut and P3 values of the DT Analyzer RCA, and take the module out of Beta.
- Configuration datasets ingestion to enrich CDR dataset and combine them to extract combined info using SQL Queries or Report Templates.
- Additional validated KPI/chart contracts.
- Network Insights improvements.
- Automatic emails.
- TEMS logs, with their reports.

## Architecture considerations

Potential future scaling work:

- health monitoring: stronger observability for long-running processing, with alerts on runs that take too long;
- automated end-to-end deployment verification.

Roadmap items are intentions, not commitments for a specific release. Refer to the Changelog for delivered behaviour.
