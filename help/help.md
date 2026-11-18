<p align="center">
  <img src="src/web_interface/static/img/brand-mark.png" alt="DriveTest Analyzer logo" width="320">
</p>

# DriveTest Analyzer Help

> [!TIP]
> **Start with your task.** Choose a guide below, then use its task index or the **Modules & Sections** tab to reach the relevant workflow.

Use this Help centre for detailed workflows, examples and technical rules. For a shorter introduction and deployment quick start, open the **Readme** tab.

Help Navigation groups chapters under General, Main Modules, Administrative Modules and Reference; a chapter can list reports of its own below it, such as the compatibility reports of Benchmarking Providers, each shown in its own design. Help is available without signing in.

## Presentations

Click a card to open it, **▶ Slideshow** to play it full screen or **Download PowerPoint** to keep it; [Product Presentations](presentations.md) tells how to use the slide viewer and share a slide.

```presentations
overview
architecture
benchmarking-providers
one-slider
roadmap
```

### Module presentations

```presentations
workspace
workspace-config
cdr-analysis
network-insights
ppt-designer
scoring-gap-analysis
non-qualified-calls
dt-analyzer-rca
reporting
builders
assistant
ticket-center
administration
```

### Full presentation

Every presentation above in one deck, each in a section of its own.

```presentations
full-presentation
```

## In this guide

| Task or topic | Go to |
| --- | --- |
| Presentations | [Open section](#presentations) |
| Module presentations | [Open section](#module-presentations) |
| Full presentation | [Open section](#full-presentation) |
| Choose where to start | [Open section](#choose-where-to-start) |
| Documentation map | [Open section](#documentation-map) |
| Fast troubleshooting | [Open section](#fast-troubleshooting) |

## Choose where to start

| Your task | Recommended guide |
| --- | --- |
| New to the product | [Product Overview](overview.md) |
| Comparing results with another tool | [Technical Considerations](technical-considerations.md) |
| Installing the service | [Deployment Configuration](configuration.md) and [Docker Deployment](docker-deployment.md) |
| Uploading data | the [Data Ingestion](workspace-management.md#data-ingestion) section in Workspace Management |
| Analysing one dataset | [CDR Analysis](datasets-analysis.md) |
| Exploring a complete template as a live design or generating its PowerPoint | [PPT Designer](ppt-designer.md) |
| Building one report from several modules, or scheduling reports and emailing them | [Reporting](reporting.md) |
| Calculating NetCheck scores or comparing operator gaps | [Scoring & GAP Analysis](scoring-gap-analysis.md) |
| Building ad-hoc SQL queries with guided controls | [Query Builder](query-builder.md) |
| Asking the workspace a question in your own words (scoring, Non-Qualified Calls, how the tool works) | [AI Assistant](assistant.md) |
| Reporting a bug, suggesting an improvement or asking for a new feature, and following it | [Ticket Center](ticket-center.md) |
| Authoring templates | [PPT Designer → PPT Templates](ppt-designer.md#ppt-templates), including the [Report Template reference](ppt-designer.md#report-template-reference) |
| Managing users, their access and the databases | [Super Admin](super-admin.md) |
| Importing, exporting and transferring packages and managing datasets | [Administrator Config](administrator-config.md) |
| Changing application-wide runtime settings | [Application Config](app-config.md) |
| Managing chart mappings for a workspace | [Workspace Config](workspace-config.md) |
| Managing the PPT Templates of a workspace | [PPT Designer → PPT Templates](ppt-designer.md#ppt-templates) |
| Reviewing application and workspace activity | [App Logs](app-logs.md) |
| Presenting the tool to an audience | [Presentations](#presentations) |
| Following the adaptation to Umlaut, P3 and RootMetrics CDRs | [Benchmarking Providers](benchmarking-providers.md) |

## Documentation map

- [Product Presentations](presentations.md) — every presentation of the tool, of the modules and the Full Presentation, in the slide viewer.
- [Product Overview](overview.md) — detailed tour of every module and panel.
- [Technical Considerations](technical-considerations.md) — normalisation, execution semantics, vendor mapping, storage, PPT caching and jobs.
- [Deployment Configuration](configuration.md) — runtime/rendering variables, storage roots, Docker settings and initial access.
- [Docker Deployment](docker-deployment.md) — production, development, persistence and upgrades.
- [Web Interfaces](web-interface.md) — shared navigation, dialogs, tables and responsive behaviour.
- [Workspace Management](workspace-management.md) — workspaces, data ingestion, processing, previews and mappings.
- [CDR Analysis](datasets-analysis.md) — interactive single-dataset analysis and exports.
- [PPT Designer](ppt-designer.md) — saved Designs, synchronized filters and slide layouts.
- [Non-Qualified Calls](non-qualified-calls.md) — the NQ Analysis Center: summary, NQ rate by campaign and operator, lifecycle and phases, root cause analysis and sources, drill-down and shared follow-up (status set by rules or by hand, team, analyst, root category and cause recommended from the DT Analyzer RCA, NetCheck, the Ericsson RCA and previous decisions, fields by section and comments) of every call and test that did not complete, across Daily and Final CDRs.
- [Reporting](reporting.md) — reports with parts of several modules, generated on demand or on their schedule and emailed, and the History of every report generated.
- [Chart Builder](chart-builder.md) — temporary ad-hoc chart construction.
- [Query Builder](query-builder.md) — guided query design, SQL editing, execution and saved queries.
- [AI Assistant](assistant.md) — a chat that answers questions about the workspace in natural language with the calculations of its modules, the names of operators, vendors, areas and campaigns sent to the AI engine as codes, every figure traced to its calculation, and a glossary of the workspace fed from the chat.
- [Ticket Center](ticket-center.md) — tickets of bugs, improvements and new features with screenshots and files, the version and date they were opened with, priorities, statuses, a timeline of comments and changes, and a design.
- [App Logs](app-logs.md) — workspace events and live server output.
- [Application Config](app-config.md) — application-wide runtime settings and their effect.
- [Workspace Config](workspace-config.md) — workspace-owned templates, Main Cities, chart mappings and scoring methodologies.
- [Administrator Config](administrator-config.md) — portability and datasets.
- [Super Admin](super-admin.md) — users and their access, Interface Settings and databases.
- [Project Structure](project-structure.md) — source/browser layers, database ownership, persistent storage, caches and generated output.
- [Roadmap](roadmap.md) — current limitations and planned work, also as a presentation.
- [Benchmarking Providers](benchmarking-providers.md) — the adaptation to Umlaut, P3 and RootMetrics CDRs: its status, time plan and the multi-provider model, and what is needed to finish it, also as a presentation, with the Umlaut CDR Compatibility and P3 CDR Compatibility reports below it.

## Fast troubleshooting

- A dataset is missing from a selector: verify that the correct workspace is open, its type is correct and processing finished successfully.
- Vendor Comparison is disabled: map every selected Data, Voice and Speech CDR first.
- A chart is empty: open **View filtered dataset** and check datasets, technology, filter values and sample counts.
- A template cannot be saved: use the `Slide: n - Chart: n` validation message to locate the invalid cell.
- A Docker update looks stale: verify the running image digest/tag and recreate the container after pulling.
- A server transfer does not start: confirm destination reachability, URL/port, destination super-admin session and offer status.
