# Reporting

Use **Reporting** to build a **Complete Report**, one PowerPoint or Word document with the parts you choose of PPT Dashboards, Scoring & GAP Analysis, Network Insights and Non-Qualified Calls, and to collect artifacts from several modules in one **Reporting Job**, run it on demand or on a schedule, and email the artifacts with a clear description of each one and its filters.

> [!NOTE]
> **Module access.** **Reporting** is in every Modules Profile of a new deployment. Admins and super-admins choose who sees it in **Admin → Modules Profiles**. Creating, editing and running jobs, and saving or deleting favourite Complete Reports, requires `user-editor`, `admin` or `super-admin`. A Complete Report only includes the sections of the modules activated for the account that generates it.

## In this guide

| Task or topic | Go to |
| --- | --- |
| One report from several modules | [Open section](#complete-report) |
| Artifacts a job can include | [Open section](#artifacts) |
| Create, edit and run a job | [Open section](#reporting-jobs) |
| Email delivery | [Open section](#email-delivery) |
| Schedules | [Open section](#schedules) |
| Run history and downloads | [Open section](#run-history) |
| Portability | [Open section](#portability) |

## Complete Report

The **Complete Report** panel, above the Reporting Jobs, builds one document from four sections: **PPT Dashboards**, **Scoring & GAP Analysis**, **Network Insights** and **Non-Qualified Calls** (each with the title its module has in Interface Settings).

| Part | What it chooses |
| --- | --- |
| **Common filters** | The **NR Mode**, on its own row, then Operators, Operator_Vendor, Vendor_Operator, Vendors, Regions, Clusters and Cities (with **Main Cities**, the Main Cities of the workspace at each export), as in Scoring & GAP Analysis. They apply to every section and replace the saved filters of the Dashboards; empty filters include every value |
| **Campaigns** | Each section has its own, at the top of its card: **Latest campaign**, **Previous campaign**, **Latest 2 campaigns**, **All available campaigns** (which follow the newest campaigns at each export) or chosen campaigns of the NR Mode, every campaign when none is chosen. They choose the CDRs of the section, so for example Scoring can compare the latest two campaigns while Network Insights shows only the latest one; in PPT Dashboards they replace the Campaign filter of every Dashboard |
| **Sections** | Each section with its checkbox and its sub-modules: the saved Dashboards of the NR Mode (each Dashboard is made for one NR Mode, shown beside its name), the results tabs of Scoring & GAP Analysis (Summary, Scoring Charts, Scoring Tables, Locations, Scoring Trends, GAP Analysis and Points Lost) and the panels of Network Insights and Non-Qualified Calls. **Charts & tables** unfolds the charts and tables of a sub-module to include the whole sub-module or only some of them |
| **Order** | Drag a section or a sub-module by its handle (⋮⋮), or focus the handle and use the arrow keys, to order the sections and the sub-modules inside each section |
| **Scoring & GAP Analysis options** | Best Network and/or Most Reliable Network; All Environments (all of them combined) and/or each environment; the methodology (**By campaign** by default) and the GAP reference; the operators compared in GAP Analysis (all when none is chosen); **Show KPI values** and **Show GAP values** in the scoring tables; the colour theme; and the **Scoring Trends**: their **Campaigns** (**All available campaigns** by default, Latest campaign, Previous campaign, Latest 2 campaigns or campaigns; none, **Same as the section**, takes the campaigns of the section), with which the Scoring Trend and, inside the panel, **Include National & Areas Trends** (their rows and time split, when no area filter is chosen) are calculated. An identical completed calculation (a Saved Filter with the same CDRs, filters, methodology and GAP reference, and the same Scoring Trends campaigns when they have some) is reused; otherwise the scoring is calculated |
| **Network Insights options** | Technology, Split by, the LTE and NR coverage and interference thresholds, the overshooting distance, the map grid and the Environments |
| **Non-Qualified Calls options** | The period of the progress timeline, every call or open calls only, whether the Root Cause Analysis counts the suggested root causes, and whether its charts show the Not classified calls and the Lifecycle the calls without a value |

**Generate** creates the report in the background, in PowerPoint and in Word with the preview of both, and opens a dialog with its progress and its processing time. **Cancel** stops it; **Hide** (or Escape, or ×) closes the dialog while the report keeps being generated, so you can go on using the application: **Generate** then shows its progress and time and opens the dialog again, and when the report is ready a dialog on any page of the application offers to open its preview in Reporting (**Later** leaves **Open last report** beside **Generate**). Ready, the dialog takes almost the whole screen to preview it before **Download**: **PowerPoint** and **Word**, at its top, choose the format previewed and downloaded (the PowerPoint slide by slide, the Word document page by page, in portrait), and switching between them is immediate and keeps the section shown; on the left, every section with its slides or pages (select a section or a page to go to it); on the right, the chosen page, which zooms with the wheel (towards the pointer), by dragging a rectangle over it or with **+**, **−** and **⤢** (the whole page, also with a double click), and moves with Shift+drag or the middle button; **‹ ›** or the arrow keys show the other pages. Sections that cannot be generated (for example Scoring without a campaign with Data, Voice and Speech CDRs) are listed in the dialog and left out; the others stay in the report. A Word page never repeats the title of a component: one that follows on the same page another with the same title and context goes without it. The preview needs LibreOffice; without it the list on the left shows the title of each slide.

Each section generated is kept for the next exports: **Reuse generated sections** (checked by default) uses it again while its options, the common filters and the data it reads have not changed (the CDRs, the Operator and Vendor Maps, the Main Cities and, per section, the Dashboards, the methodologies, the inventory of the analysis or the follow-up of the calls), so exporting the same report in the other format only composes and renders it, and exporting it again in the same format also uses the document composed (and the Word pages packed) by the earlier export and its preview; the dialog names the sections reused and whether the document was too. Uncheck it to generate every section again. Two exports that need the same section at once generate it once. Scoring & GAP Analysis uses the Saved Filter of the same CDRs, filters, methodology and GAP reference when there is one (a Favourites Filter first), with its own Split by and National & Area Summary, and Network Insights the analysis already made for the same selection and inputs, so neither is calculated again.

The document starts with a cover with a large title (**Title on the cover**, else the name of the favourite), the optional **Subtitle** under it and every common filter (All for those without a value), and each section starts with its own cover: its name, its Campaigns, the common filters and the options chosen for it. Covers and transition slides show the Ericsson logo in white, as every report of the application does on its dark slides. Each chart or table is a component that never spans two slides or two pages:

- **PowerPoint.** A table spread over several slides becomes one table on one slide: its rows joined under one header, and the parts of a table too wide for one slide (each repeating its first column) joined into one table with all its columns. A long table continues in up to four tables side by side, each under the header, so its text stays readable, and its columns are as wide as their values need; when even so its values would be smaller than 6 pt, it continues on two or more slides (its title ending in *· 1/2*, *· 2/2*…), each under the header (in Word, smaller than 6 pt on the page). Tables side by side spread over several slides (such as one per network in the Network Deployment views) are joined each with its continuation and go on together on as few slides as keep them legible, each slide with the same rows of every table (a table that has run out of rows leaves its place empty). Other charts or tables spread over several slides share one slide, made smaller to fit down to 60 % of their size; smaller, they continue on more slides, as few as keep them at that size. Small consecutive components of a section share a slide when they fit almost at their size, each under its own title (its subtitle when its title is the title of the slide).
- **Word.** Portrait pages: the report cover and the cover of each section fill a page each, and the components of the section follow it. Each page holds as many components of its section as fit, in their order: a page takes the next components while they fit (made a little smaller when needed), and only reorders them inside the page, for example to put two narrow components side by side, so a component never goes after one that follows it. A component larger than a page fills a page on its own, made smaller. The covers of the scorings and of the Dashboards become headings. A title too long for one line is made smaller, in PowerPoint and in Word, so it never covers the chart or table under it.

The PowerPoint and Word exports of [Scoring & GAP Analysis](scoring-gap-analysis.md), [Network Insights](network-insights.md) and [Non-Qualified Calls](non-qualified-calls.md) (on their page and as Reporting Jobs artifacts) are composed in the same way from the same slides, each starting with the cover of its module and ending with the closing slide, so they always look like their section of a Complete Report.

Save the panel as a **favourite** to use it again: enter its **Name** and select **★ Save as favourite** (a name that a favourite already has overwrites it once you confirm it; another name saves a new favourite). **Favourite** loads a saved report and **Delete** removes it. The panel remembers the last report edited in this browser. Favourites are kept in the workspace (the Complete Reports table of Database Management) and every save, deletion, export and download is recorded in App Events. Generated documents are kept in `output/reports/complete-reports/` of the workspace for a day.

## Artifacts

A job includes any combination of these artifacts. A user can only include artifacts of the modules activated for their account, and each run checks it again with the permissions of the job's author.

| Artifact | Content | Options |
| --- | --- | --- |
| **CDR Analysis** | The CDR Analysis export of every CDR its NR Mode and Campaigns choose: global KPIs, metric cards, CDF and comparison charts, grouped percentiles and the processed metrics table | PowerPoint and/or Word; **NR Mode** and **Campaigns** (which choose the CDRs, see below); in a **Metrics** row, the metrics of each CDR type (CDR Data, Voice and Speech; all by default); in a **Filters** row, the Operator, Operator_Vendor, Vendor, Region, Cluster and City (with Main Cities) filters of Network Insights, with the values of the CDRs of the NR Mode; and two single-choice rows, **Global Comparison** for the charts' grouping and **Global CDF Comparison** for the CDF curves (Operator by default) |
| **Network Insights** | RF quality overview with campaign deltas, RSRP and SINR CDFs, coverage and interference maps with their weakest areas (LTE and NR separately for LTE+NR), observed and licensed spectrum (with the NR sites by duplex mode, the bandwidth per band and the total bandwidth of the download tests) and network deployment | One report per entry, in PowerPoint and/or Word: NR Mode, technology, LTE/NR thresholds, grouping (Operator, Vendor, Region, Cluster, City, Environment, CDR type, Campaign; Operator stays checked unless Vendor is checked, as in the module), **Campaigns** (which choose the CDRs, see below) and the Operator/Operator_Vendor/Vendor/Region/Cluster/City filters in one row |
| **Dashboard** | One new Dashboard PowerPoint per entry, generated at each run | NR Mode first, which lists its Dashboards, then the Dashboard's own options, prefilled with its saved definition: Scope and Vendor comparison, date range and every Adaptative Filter, the **Campaigns** first (they choose the CDRs, see below), then Operator, Operator_Vendor, Vendor, Market, Region, Cluster, City (with **Main Cities** first: the Main Cities of the workspace at each run), RAT, Session Type, Call Status and the Dashboard's Auto-calculated Fields. Filter values are those of the CDRs of the NR Mode that the other filters leave; empty filters include every value |
| **Scoring** | One Scoring & GAP Analysis report per entry, in PowerPoint and/or Word (both composed as its section of a [Complete Report](#complete-report), see [Scoring & GAP Analysis](scoring-gap-analysis.md)), with the Best Network scoring and, when the methodology has Most Reliable points, the Most Reliable Network scoring in the same document. **Configure report…** chooses its scenarios (each with its filters, Main Cities included, and Split by levels) and the content of each scoring with the same editor as Scoring & GAP Analysis, where saved report configurations can be loaded, and its colour **Theme** (NetCheck by default). The report content is required: until it is configured the entry shows *Not configured* and the job cannot be saved | NR Mode, **Campaigns** (which choose the CDRs, see below; without them, every campaign with Data, Voice and Speech CDRs), methodology (**By campaign**, each campaign with its methodology as in Scoring & GAP Analysis, by default), GAP reference and the report content. An identical completed calculation is reused |

Add Network Insights, the same Dashboard or Scoring several times to include several configurations, for example a Network Insights report for NSA and another for SA, one for LTE and one for NR, or three Dashboards with two filter configurations each. Jobs saved with a single Network Insights selection show it as one entry. Modules that provide their own reports appear as additional artifacts: **Non-Qualified Calls** adds its Executive Summary, Progress Status, Lifecycle & Phases, Root Cause Analysis and Root Cause Sources in PowerPoint, Word and/or Excel (PowerPoint and Word show the indicator cards, breakdowns, donuts, timeline, workload, status pipeline, phases, root causes, RCA sources and detail tables with the look of the page; PowerPoint or Word is always generated, and Excel is an optional extra with only the calls detail by section, their comments and history), with the filters of its Filters panel (Status Set, Root Domain, Root Category and Root Cause included), the period of the progress timeline, an open-calls-only option and whether the Root Cause Analysis counts the suggested root causes. **Complete Report** adds the favourite Complete Reports (every favourite, or those chosen) in PowerPoint and/or Word, each generated at the run as the Complete Report panel generates it.

Filter and metric dropdowns open one at a time and close when clicking elsewhere. Each selector shows its name above it and reads **All** when every value or none is selected (no restriction, the default) or **N of M**; **Select All / None** selects or clears the listed values. The values listed are those of the CDRs of the entry's NR Mode (or of the CDRs it uses), and they update when the NR Mode changes; every City selector offers **Main Cities** first.

CDR Analysis, Network Insights, Dashboards and Scoring have no CDR list: their **Campaigns**, right after **NR Mode** in the first row of the entry, choose the CDRs, made again at each run so the CDRs and campaigns added later are included. **Campaigns** is one list: first **Latest campaign**, **Previous campaign** (the one before it), **Latest 2 campaigns** and **All available campaigns** (the newest campaigns, the one before the newest, or every campaign, of the NR Mode at each run, so the campaigns that arrive after the job is saved are included), each one alone (checking it clears the other one and the campaigns, checking a campaign clears it), then the campaigns (every campaign when all or none are checked). Below that row the entry lists, by type, the CDRs it uses now, with their stage and campaigns. The CDRs are those of the entry's NR Mode that the combined CDR tables include for those campaigns: the Final CDR of a campaign before its Weekly and Daily CDRs, or the **In Combined?** choice of Workspace (see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)); Scoring leaves out the campaigns without Data, Voice and Speech CDRs. **Non-Qualified Calls** offers **NR Mode** first among its filters, instead of the CDRs, and **Campaign** after it, listing only the campaigns of the NR Modes chosen, with the same four choices first, made again at each run among the campaigns of its calls for those NR Modes.

**CDR Analysis** analyses each CDR its NR Mode and Campaigns choose on its own (a campaign does not need every CDR type). The [CDR Analysis](datasets-analysis.md) module itself keeps choosing the CDR to analyse.

Jobs saved before choose their CDRs by campaign when they open in the editor and when they run: the newest complete set becomes **Latest campaign**, every complete set every campaign, CDRs chosen by hand the campaigns they hold (CDR Analysis takes the NR Mode of its CDRs, NSA when they mixed both, and the campaigns of its Campaign filter when it had one), a Dashboard entry that used the Dashboard's own CDRs keeps its Campaign filter, and a Non-Qualified Calls artifact filtered by CDRs takes their NR Mode and campaigns.

Every artifact file is named `yyyymmdd_hhmmss - <Module> - <report name>` with the run timestamp, for example `20261006_093000 - Network Insights - NSA LTE.pptx`; artifacts with the same name get ` (2)`, ` (3)`… The ZIP of a run is named `yyyymmdd_hhmmss - Reporting - <job name>.zip`.

The same summaries are available directly: **Export PowerPoint** and **Export Word** in [CDR Analysis](datasets-analysis.md) ask which datasets to include (or export the open CDR as on screen), and **Export PowerPoint** and **Export Word** in [Network Insights](network-insights.md) export the current selection.

## Reporting Jobs

The **Reporting Jobs** table lists every job with its name, artifacts (each module in bold, with its entries indented below it when it has several), next run, recurrence, whether it sends email, the time of its last run and its status, followed by its actions in one row.

| Action | Result |
| --- | --- |
| ▶ Run now | Starts a run immediately, whatever the schedule |
| ⬇ Download | Downloads the artifacts of the last run as a ZIP |
| ✎ Edit | Opens the job in the editor |
| ⧉ Duplicate | Creates a disabled copy named "(copy)" |
| ⏸ / ⏵ | Disables or enables the schedule |
| × Delete | Deletes the job, its run history and artifacts |

Select **New Reporting Job** (or ✎ Edit on a job) to unfold the **Job Editor** inside the jobs table: right below the job being edited (highlighted), above the other jobs, or at the top for a new job. **Cancel**, the red **Close** button in its corner or **Save Reporting Job** folds it away again; with unsaved changes, Cancel, Close and opening another job ask before discarding them. The open editor is kept in the browser while you work, so reloading the page reopens it on the same job with its unsaved values, unless the job has changed on the server since then (imported, transferred, saved from another browser or updated by a rename in the Operator or Vendor Maps): then its saved version opens and the unsaved values are discarded. Enter a name, set the **Job enabled** switch beside it (a disabled job keeps its configuration but never runs on its schedule; ▶ Run now works either way), choose the schedule and the delivery, choose each artifact in its tab (the tabs sit on the artifact's panel; the selected one joins it) — CDR Analysis, Network Insights, PPT Dashboards, Scoring & GAP Analysis and Non-Qualified Calls, each in the colour of its module and with a check after its name when it is included — check it to include it and configure its entries, then **Save Reporting Job**. Each tab shows the icon of its module after the check, and the browser keeps the selected tab when the page is reloaded. An unchecked type keeps its configuration in the editor but is not generated. Each type offers its output formats as chips (at least one stays selected). Each artifact type and each entry has **Collapse/Expand**, remembered by the browser after reloading the page, and an entry's header names its NR Mode, technology or Dashboard. The fields of each entry share one row on wide screens, and CDRs appear in one card per type (CDR Data, Voice and Speech) with **Select All/None**, as in Network Insights.

## Email delivery

Enable **Send the artifacts by email** and enter the recipients separated by commas, semicolons or lines. Without email, a run only keeps its artifacts for download.

The email subject is the job name with the run time. Its body lists every attached file with its content and filters (datasets, Dashboard Scope and filters, Scoring CDRs, Split by levels and filters, Network Insights selection) and every artifact that could not be generated with its reason.

Configure the SMTP server in **Config → Application Config → Email Delivery**; see [Application Config](app-config.md#email-delivery). A run whose attachments exceed the configured size limit fails with a clear message.

## Schedules

| Recurrence | Runs |
| --- | --- |
| Manual only | Only with ▶ Run now |
| Once | On the chosen date and time |
| Daily | Every day at the chosen time |
| Weekly | On the chosen weekdays at the chosen time |
| Monthly | On the chosen day of the month (the last day in shorter months) |

Times use the application timezone set in Application Config. The scheduler checks every 30 seconds.

> [!IMPORTANT]
> **Jobs run whenever the application is running.** The scheduler checks the jobs of every workspace, also when their workspace is closed or another workspace is open; jobs of the open workspace run in the server and the others in a separate worker that does not change the workspace open for users. Runs appear in the background tasks window with their progress. A run that fell due while the application was stopped starts at the next check; several missed runs become a single run.

## Run history

**Run History** shows each run with its trigger, start time, status (with how long the run took once it finishes), email result and artifacts, grouped by module as in the jobs table: one line per entry with its formats, such as `NSA LTE (PPT/Word)`, where each format links to its file. A run lists only the files it generated that still exist; a file that could not be kept appears with its error instead of a link. ⬇ downloads them all as a ZIP.

| Status | Meaning |
| --- | --- |
| Queued, Running | The run is waiting or generating; progress and the current step are shown |
| Sent | Every artifact was generated and emailed |
| Completed | Every artifact was generated; the job does not send email |
| Partial | Some artifacts failed; the others were emailed |
| Failed | No artifact was generated, or the email could not be sent |

Runs interrupted by an application restart are marked as failed. Artifacts are stored in `output/reports/reporting-jobs/` of the workspace, one folder per run.

## Portability

Reporting Jobs and the favourite Complete Reports travel with **Admin → Import / Export / Transfer** (each as an element of its own, **Reporting Jobs** and **Complete Report Favourites**, and with Full Workspace), workspace transfers and backups; a favourite finds its Dashboards by name and NR Mode in the destination workspace (Dashboards of the same name in NSA and SA are told apart), with the same ones checked and in the same order, and when a transfer also carries the Dashboards the favourites are imported after them; and Reporting Jobs packages made before, which carried the favourites, still restore them. Imports add new jobs and replace jobs with the same name; dataset references are matched by file name in the destination workspace. Run history and artifacts are generated output and are not exported.
