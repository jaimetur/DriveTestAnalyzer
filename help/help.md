<p align="center">
  <img src="src/web_interface/static/img/brand-mark.png" alt="DriveTest Analyzer logo" width="320">
</p>

# DriveTest Analyzer Help

> [!TIP]
> **Start with your task.** Choose a guide below, then use its task index or the Page Sections navigation to reach the relevant workflow.

Use this Help centre for detailed workflows, examples and technical rules. For a shorter introduction and deployment quick start, open the **Readme** tab.

Help Navigation groups chapters under General, Main Modules, Administrative Modules and Reference; a chapter can list reports of its own below it, such as the compatibility reports of Benchmarking Providers, each shown in its own design. Help is available without signing in; only the PPT Reporting (old) chapter requires that feature.

## Presentations

Present DriveTest Analyzer with its presentations:

- **Overview**, the complete deck: the tool, the teams it serves and its platform, a slide for each module in the order of their tabs (two for Scoring & GAP Analysis) and the roadmap, closing with the one-slider.
- **Benchmarking Providers Roadmap**, in the design of its own deck: how the tool is being adapted to Umlaut and P3 CDRs and the status of each phase, how it is built inside and how it is deployed in the cloud (see [Benchmarking Providers](benchmarking-providers.md)).
- **One-slider**, on a single slide: the most important of the tool, with its figures, modules, teams, platform and what comes next.
- **Roadmap**, on a single slide: what comes next, such as Umlaut CDRs, the Active Tests community, scale-out and speed on AWS, PostgreSQL and health monitoring.

Select a presentation to open it in the slide viewer (its slides on the left and, below the slide, the zoom buttons and **▶ Slideshow**, the arrows of the previous and next slide, **Close** and **Download PowerPoint**; the wheel and the arrow keys also change slide, Ctrl/Cmd+wheel zooms and Escape closes it; on a phone or tablet, swipe the slide to change it, pinch it to zoom and double-tap it for the whole slide, and the viewer fits the part of the screen the browser leaves visible, with the arrows of the slides first), play it full screen with **▶ Slideshow**, choosing the seconds per slide and the transition, or download it with **Download PowerPoint**. **Copy link**, on each card and beside **Close** in the viewer, copies the short link of the presentation (in the viewer, of the slide shown), such as `/presentations/full-presentation?slide=3`, to send it: opening it opens the presentation at that slide in the slide viewer of [Product Presentations](presentations.md), also without signing in. The link has the **Public address** of the server when [Application Config](app-config.md) has one, otherwise the address the application was opened with. Where the link is shared (WhatsApp, Teams, Slack, Outlook…), its preview shows the title of the presentation, its description and the picture of that slide (the link of [Product Presentations](presentations.md), the cover of the Full Presentation), when the app can reach the server; WhatsApp on Android opens no link with an IP address (nor shows its preview), so give the server a name and save it as its public address. While a presentation is open, the address of the page is that link too. The server generates every presentation, with the pictures of its slides, always in the background, so the application never waits for them: at its start when one is missing (until it is ready, the Help says it is coming), again when their figures or the generator change, and on demand with **Regenerate Presentations** in [Super Admin → Presentations](super-admin.md#presentations). The figures of the Overview, the One-slider and the Roadmap are live: those of the workspaces chosen there.

```presentations
overview
benchmarking-providers
one-slider
roadmap
```

### Module presentations

Each main module also has a presentation of its own, in a design of its own, at the start of its chapter: [Workspace Management](workspace-management.md), with **Workspace Config** after it (everything to set up in a new workspace: how operators, vendors and campaigns are named, coloured and ordered, the map areas of its countries, its networks and its methodology; see [Workspace Config](workspace-config.md)), [CDR Analysis](datasets-analysis.md), [Network Insights](network-insights.md), [PPT Designer](ppt-designer.md), [Scoring & GAP Analysis](scoring-gap-analysis.md), [Non-Qualified Calls](non-qualified-calls.md) with the **DT Analyzer RCA** beside it (how it finds the root cause of every Non-Qualified Call: what it reads, its rules, the lack of resources, the network around the call and the evidence it gives), [Reporting](reporting.md), [Builders](chart-builder.md) and [Ticket Center](ticket-center.md), and **Administration** after them (Admin and Super Admin: users and access, the databases, backups, packages and transfers, the configuration of the application at every level and App Events; see [Super Admin](super-admin.md)). They open in the same slide viewer and download as PowerPoint.

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
ticket-center
administration
```

### Full presentation

The **Full Presentation** joins every presentation in one deck, with their slides as they are, each in a section named after it: the Overview, the Benchmarking Providers Roadmap, the presentation of every main module (with Workspace Config after Workspace and Network Insights after CDR Analysis) and of Administration, the DT Analyzer RCA and the Roadmap. It opens in the same slide viewer and downloads as PowerPoint.

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
| Following the adaptation to Umlaut and P3 CDRs | [Benchmarking Providers](benchmarking-providers.md) |

## Documentation map

- [Product Presentations](presentations.md) — every presentation of the tool, of the modules and the Full Presentation, in the slide viewer.
- [Product Overview](overview.md) — detailed tour of every module and panel.
- [Technical Considerations](technical-considerations.md) — normalisation, execution semantics, vendor mapping, storage, Design caching and jobs.
- [Deployment Configuration](configuration.md) — runtime/rendering variables, storage roots, Docker settings and initial access.
- [Docker Deployment](docker-deployment.md) — production, development, persistence and upgrades.
- [Web Interfaces](web-interface.md) — shared navigation, dialogs, tables and responsive behaviour.
- [Workspace Management](workspace-management.md) — workspaces, data ingestion, processing, previews and mappings.
- [CDR Analysis](datasets-analysis.md) — interactive single-dataset analysis and exports.
- [PPT Designer](ppt-designer.md) — saved Designs, synchronized filters and slide layouts.
- [PPT Reporting (old)](ppt-reporting-old.md) — classic Reports, Chart Sets, interactive previews and jobs.
- [Non-Qualified Calls](non-qualified-calls.md) — the NQ Analysis Center: summary, NQ rate by campaign and operator, lifecycle and phases, root cause analysis and sources, drill-down and shared follow-up (status set by rules or by hand, team, assignee, root category and cause recommended from the DT Analyzer RCA, NetCheck, the Ericsson RCA and previous decisions, fields by section and comments) of every call and test that did not complete, across Daily and Final CDRs.
- [Reporting](reporting.md) — bundle reports with parts of several modules (Bundle Report Templates), and scheduled Reporting Jobs that email CDR Analysis, Network Insights, Design and Scoring artifacts.
- [Chart Builder](chart-builder.md) — temporary ad-hoc chart construction.
- [Query Builder](query-builder.md) — guided query design, SQL editing, execution and saved queries.
- [Ticket Center](ticket-center.md) — tickets of bugs, improvements and new features with screenshots, the version and date they were opened with, priorities, statuses, a timeline of comments and changes, and a design.
- [App Logs](app-logs.md) — workspace events and live server output.
- [Application Config](app-config.md) — application-wide runtime settings and their effect.
- [Workspace Config](workspace-config.md) — workspace-owned templates, Main Cities, chart mappings and scoring methodologies.
- [Administrator Config](administrator-config.md) — portability and datasets.
- [Super Admin](super-admin.md) — users and their access, Interface Settings and databases.
- [Project Structure](project-structure.md) — source/browser layers, database ownership, persistent storage, caches and generated output.
- [Roadmap](roadmap.md) — current limitations and planned work, also as a presentation.
- [Benchmarking Providers](benchmarking-providers.md) — the adaptation to Umlaut and P3 CDRs: its status and the multi-provider model, also as a presentation, with the Umlaut CDR Compatibility and P3 CDR Compatibility reports below it.

## Fast troubleshooting

- A dataset is missing from a selector: verify that the correct workspace is open, its type is correct and processing finished successfully.
- Vendor Comparison is disabled: map every selected Data, Voice and Speech CDR first.
- A chart is empty: open **View filtered dataset** and check datasets, technology, filter values and sample counts.
- A template cannot be saved: use the `Slide: n - Chart: n` validation message to locate the invalid cell.
- A Docker update looks stale: verify the running image digest/tag and recreate the container after pulling.
- A server transfer does not start: confirm destination reachability, URL/port, destination super-admin session and offer status.
