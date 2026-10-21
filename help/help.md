<p align="center">
  <img src="src/web_interface/static/img/brand-mark.png" alt="DriveTest Analyzer logo" width="320">
</p>

# DriveTest Analyzer Help

> [!TIP]
> **Start with your task.** Choose a guide below, then use its task index or the Page Sections navigation to reach the relevant workflow.

Use this Help centre for detailed workflows, examples and technical rules. For a shorter introduction and deployment quick start, open the **Readme** tab.

Help Navigation groups chapters under General, Main Modules, Administrative Modules and Reference. Help is available without signing in; only the PPT Reporting (old) chapter requires that feature.

## In this guide

| Task or topic | Go to |
| --- | --- |
| Choose where to start | [Open section](#choose-where-to-start) |
| Presentations | [Open section](#presentations) |
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
| Exploring a complete template as a live dashboard or generating its PowerPoint | [PPT Dashboards](ppt-dashboards.md) |
| Building one report from several modules, or scheduling reports and emailing them | [Reporting](reporting.md) |
| Generating persistent Reports or Chart Sets | [PPT Reporting (old)](ppt-reporting-old.md) |
| Calculating NetCheck scores or comparing operator gaps | [Scoring & GAP Analysis](scoring-gap-analysis.md) |
| Building ad-hoc SQL queries with guided controls | [Query Builder](query-builder.md) |
| Reporting a bug, suggesting an improvement or asking for a new feature, and following it | [Ticket Center](ticket-center.md) |
| Authoring templates | [Workspace Config](workspace-config.md), including the [Report Template reference](workspace-config.md#report-template-reference) |
| Managing users, their access and the databases | [Super Admin](super-admin.md) |
| Importing, exporting and transferring packages and managing datasets | [Administrator Config](administrator-config.md) |
| Changing application-wide runtime settings | [Application Config](app-config.md) |
| Managing templates and chart mappings for a workspace | [Workspace Config](workspace-config.md) |
| Reviewing application and workspace activity | [App Logs](app-logs.md) |
| Presenting the tool to an audience | [Presentations](#presentations) |

## Presentations

Present DriveTest Analyzer with its presentations, in the Ericsson style: the **Overview** deck (the tool, its eight modules with a slide for each one, two for Scoring & GAP Analysis, in the order of their tabs, the teams it serves, its platform and its roadmap, closing with the one-slider), the **one-slider**, with the most important of the tool on a single slide, and the **roadmap**. Select a presentation to open it in the slide viewer: its sections and slides on the left and the chosen slide on the right, which zooms with the wheel (towards the pointer), by dragging a rectangle over it or with **+**, **−** and **⤢** (the whole slide, also with a double click), and moves with Shift+drag or the middle button; **‹ ›**, the arrow keys, Page Up and Page Down go through the slides, and Escape closes the viewer. **▶ Slideshow**, in the tools of the viewer, plays the presentation full screen from the slide shown, as the presentation mode of [PPT Dashboards](ppt-dashboards.md): choose the seconds per slide, the duration and the effect of the transition (one of thirteen, Random or None) and whether it starts again after the last slide; each slide enters over the previous one, a line at the bottom shows the time left on it, Space pauses and resumes it, the arrow keys or a click move through the slides, and Escape ends it (without Start again it pauses on the last slide). **Download PowerPoint**, on each presentation and in the viewer, downloads it. Their figures are live: those of the workspaces chosen in [Super Admin → Presentations](super-admin.md#presentations), and when they change (or a new version of the application draws them otherwise) the presentations are generated again in the background, in a few seconds, the first time a signed-in user opens them; meanwhile the Help shows the last ones, saying so above them.

```presentations
overview
one-slider
roadmap
```

## Documentation map

- [Product Overview](overview.md) — detailed tour of every module and panel.
- [Technical Considerations](technical-considerations.md) — normalisation, execution semantics, vendor mapping, storage, Dashboard caching and jobs.
- [Deployment Configuration](configuration.md) — runtime/rendering variables, storage roots, Docker settings and initial access.
- [Docker Deployment](docker-deployment.md) — production, development, persistence and upgrades.
- [Web Interfaces](web-interface.md) — shared navigation, dialogs, tables and responsive behaviour.
- [Workspace Management](workspace-management.md) — workspaces, data ingestion, processing, previews and mappings.
- [CDR Analysis](datasets-analysis.md) — interactive single-dataset analysis and exports.
- [PPT Dashboards](ppt-dashboards.md) — saved Dashboards, synchronized filters and slide layouts.
- [PPT Reporting (old)](ppt-reporting-old.md) — classic Reports, Chart Sets, interactive previews and jobs.
- [Non-Qualified Calls](non-qualified-calls.md) — the NQ Analysis Center: summary, NQ rate by campaign and operator, lifecycle and phases, root cause analysis and sources, drill-down and shared follow-up (status set by rules or by hand, team, assignee, root category and cause recommended from NetCheck, the Ericsson RCA and previous decisions, fields by section and comments) of every call and test that did not complete, across Daily and Final CDRs.
- [Reporting](reporting.md) — bundle reports with parts of several modules (Bundle Report Templates), and scheduled Reporting Jobs that email CDR Analysis, Network Insights, Dashboard and Scoring artifacts.
- [Chart Builder](chart-builder.md) — temporary ad-hoc chart construction.
- [Query Builder](query-builder.md) — guided query design, SQL editing, execution and saved queries.
- [Ticket Center](ticket-center.md) — tickets of bugs, improvements and new features with screenshots, the version and date they were opened with, priorities, statuses, a timeline of comments and changes, and a dashboard.
- [App Logs](app-logs.md) — workspace events and live server output.
- [Application Config](app-config.md) — application-wide runtime settings and their effect.
- [Workspace Config](workspace-config.md) — workspace-owned templates, Main Cities, chart mappings and scoring methodologies.
- [Administrator Config](administrator-config.md) — portability and datasets.
- [Super Admin](super-admin.md) — users and their access, Interface Settings and databases.
- [Project Structure](project-structure.md) — source/browser layers, database ownership, persistent storage, caches and generated output.
- [Roadmap](roadmap.md) — current limitations and planned work, also as a presentation.

## Fast troubleshooting

- A dataset is missing from a selector: verify that the correct workspace is open, its type is correct and processing finished successfully.
- Vendor Comparison is disabled: map every selected Data, Voice and Speech CDR first.
- A chart is empty: open **View filtered dataset** and check datasets, technology, filter values and sample counts.
- A template cannot be saved: use the `Slide: n - Chart: n` validation message to locate the invalid cell.
- A Docker update looks stale: verify the running image digest/tag and recreate the container after pulling.
- A server transfer does not start: confirm destination reachability, URL/port, destination super-admin session and offer status.
