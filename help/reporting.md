# Reporting

Use **Reporting** to design **reports**, each one PowerPoint and Word document with the parts you choose of Scoring & GAP Analysis, Network Insights, Non-Qualified Calls, PPT Designer and CDR Analysis, to generate them whenever you want or on their schedule, to email them, and to find every report generated in **History**.

> [!NOTE]
> **Module access.** **Reporting** is in every Modules Profile of a new deployment. Super-admins choose who sees it in **Super Admin → Modules Profiles**. Every user who sees it generates the reports, previews and downloads them, uses History and stops the runs they started; creating, editing, duplicating, renaming and deleting reports and their schedules, and rerunning, stopping any run and deleting runs, requires `user-editor`, `admin` or `super-admin`. A report only includes the sections of the modules activated for the account that generates it (for a run on its schedule, the owner of the schedule).

## Presentation & Guide

```presentations
reporting
guide:reporting.md
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Find and manage the reports | [Reports](#reports) |
| Create or edit a report | [The report editor](#the-report-editor) |
| <span class="guide-sub">↳ Choose the campaigns of each module</span> | <span class="guide-sub">↳ [Campaigns of each module](#campaigns-of-each-module)</span> |
| <span class="guide-sub">↳ Set the options of each module</span> | <span class="guide-sub">↳ [Options of each module](#options-of-each-module)</span> |
| <span class="guide-sub">↳ Choose the theme and iPhone pictures</span> | <span class="guide-sub">↳ [Theme and iPhone pictures](#theme-and-iphone-pictures)</span> |
| Generate a report and preview it | [Generate and preview](#generate-and-preview) |
| Know what the PowerPoint and Word documents contain | [How a report is composed](#how-a-report-is-composed) |
| Send a report on a schedule by email | [Schedule and email](#schedule-and-email) |
| Know how the emails are delivered | [Email delivery](#email-delivery) |
| Find a report generated earlier | [History](#history) |
| Export, import and transfer the reports | [Portability](#portability) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Reports

The page has two tabs, **Reports** and **History**, one shown at a time: the address names it (`#reports` or `#history`) and the browser remembers the one chosen. **Reports** lists the reports of the workspace by name, each on a card with:

- its **name** (for editors, it opens the report in the [editor](#the-report-editor)) and its **star**: each user marks the reports they want at hand, which **★ Favourites** shows, in each workspace (App Events records it);
- its **labels**, in three rows:
  - its checked sections, abbreviated in the colours of their modules (**SCO** Scoring & GAP Analysis, **NI** Network Insights, **NQ** Non-Qualified Calls, **PPT** PPT Designer and **CDR** CDR Analysis);
  - the Region, Cluster or City its common filters choose, for example **London** (**Nationwide** when none), then its NR Mode and the Operator or Vendor they filter, for example **-Three** (every operator but Three), coloured as on the cards of the Favourite Scorings;
  - its campaigns, each choice once (its tooltip names the modules that make it), for example **Latest 2 campaigns** and **Latest campaign**;
- its **schedule**: *Only with Generate*, its recurrence and next run (*Weekly · Mon · 08:00 · next …*) or, when it does not generate on its own, *Paused · …*, followed by *emailed to N* when it is emailed;
- its **last result**: the status and time of its last run (its progress while generated), or *Not generated yet*;
- its buttons: **Generate** (**Follow** while it is generated), **Preview** (its last run), **Edit** (editors) and **⋯** with **Duplicate** (a copy without its schedule, named `<name> (copy)`), **Rename** (its schedule takes the new name; its runs keep theirs) and **Delete** (the report, its schedule and its runs with their files, after confirmation; admins, super-admins and its creator, otherwise disabled with a tooltip that says why).

Above the list: a search by name; the chips **All**, **★ Favourites**, **NSA**, **SA** and **Scheduled** (the chip chosen stays in the browser); **Reuse generated sections** (see [Generate and preview](#generate-and-preview)); and **+ New report** (editors), which opens an empty report in the editor.

Report names are unique in the workspace, which keeps up to 100 reports. A new workspace starts with the reports shipped with the application, without a schedule (see [Workspace Management](workspace-management.md#workspace-lifecycle)). Reports are kept in the workspace (the Bundle Report Templates table of Database Management, their schedules in Report Tasks and their runs in Report Task Runs), and every save (with its schedule), rename, deletion, generation, download, stop, rerun and deletion of a run is recorded in App Events.

## The report editor

**+ New report**, **Edit** or the name of a report opens the editor beside the list on a wide screen, and over the whole page on a phone (900 px wide or less).

- **Header:** the name of the report.
- **Footer:** **Back** and **Next** go through its four steps; **Close** closes it (asking first when changes are not saved, as does opening another report); **Save and generate** saves it and [generates](#generate-and-preview) it at once; **Save** saves the report with its schedule and leaves the editor open (a name another report has is refused).
- Opening another report keeps the step shown. The report being edited is kept in the browser, so reloading the page reopens it on the same step with its changes (a report deleted meanwhile, as a new one).

The four steps:

1. **Cover:** the **Name**, the **Title on the cover** (the name when empty), the **Subtitle** under it, the **Theme** and **Chart Pictures for the iPhone Preview** (see below).
2. **Filters:** the common filters, which apply to every module: the **NR Mode**, on its own row, then Operators, Operator_Vendor, Vendor_Operator, Vendors, Regions, Clusters and Cities (with **Main Cities**, those of the workspace at each generation), as in Scoring & GAP Analysis. They replace the saved filters of the Designs and give a field-values [parameter](ppt-designer.md#template-parameters) of a Design's template on one of their fields (a City Report template's Cities) the values chosen. Empty filters include every value; Operators take [patterns](web-interface.md#operator-patterns) such as `VF*`.
3. **Modules:** the five sections, by default **Scoring & GAP Analysis**, **Network Insights**, **Non-Qualified Calls**, **PPT Designer** and **CDR Analysis** (each with the title of its module in Interface Settings; a saved report keeps its own order, and reports saved before CDR Analysis was a section have it unchecked). Each has its checkbox, its **Campaigns**, its **Options** and its **Sub-modules** (its **Designs** in PPT Designer), each in a subpanel; **Charts & tables** unfolds the charts and tables of a sub-module to include all of it or only some. Drag a module or sub-module by its handle (⋮⋮), or focus the handle and use the arrow keys, to order them.
4. **Schedule:** whether and when it is generated on its own, its formats and whom it is emailed to (see [Schedule and email](#schedule-and-email)).

### Campaigns of each module

Each module has its own, at the top of its card and in amber so they stand out (as are the Campaigns of the Scoring Trends): **Latest campaign**, **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns**, **Previous campaign**, **All available campaigns** (following the newest campaigns at each generation) or chosen campaigns of the NR Mode, every campaign when none is chosen.

- They choose the CDRs of the module, so Scoring can compare the latest two campaigns while Network Insights shows only the latest one; in PPT Designer they replace the Campaign filter of every Design.
- Network Insights has one **Campaign**: **Latest campaign** (default), **Previous campaign** or one campaign (a section saved with several keeps the newest).
- None of these choices counts the [Flex campaigns](workspace-management.md#flex-campaigns) or the [campaigns in progress](workspace-management.md#campaigns-in-progress) (Weekly or Daily CDRs only, without a Final CDR yet), which are used only when checked by hand.
- When the NR Mode of a module leaves operators out of scope (the **NR Modes** of their labels in the [Operator Maps](workspace-config.md#operator-maps), such as Three, which has no SA), its CDRs used now name them (*Out of scope: SA · Three*) and their tests are left out of the report.

### Sub-modules

- **PPT Designer:** every saved Design, each reading the CDRs of the NR Mode of the common filters (its template serves every NR Mode). A Design of [NSA & SA](ppt-designer.md#nsa-sa-in-one-design) keeps reading both, the Campaigns choosing the CDRs of each NR Mode; a Design generated in an NR Mode other than its own goes without its saved comments; reports saved before keep checked only the Designs of their NR Mode, as they generated.
- **Scoring & GAP Analysis:** Summary, Scoring Charts, Scoring Tables, Country Areas, Scoring Trends, GAP Analysis and Points Lost.
- **Network Insights** and **Non-Qualified Calls:** their panels.
- **CDR Analysis:** CDR Data, CDR Voice and CDR Speech, each with CDR Summary, Selected Metric Cards, Visual Analytics of each metric and Processed Metrics.

### Options of each module

**Scoring & GAP Analysis:**

- Best Network and/or Most Reliable Network; All Environments (combined) and/or each environment.
- Beside its Campaigns, the **GAP reference** and the **Methodology** (**By campaign** by default). Its recommendations, individual GAP comparisons and Points Lost views focus on the Focus operators of the [Operator Maps](workspace-config.md#operator-maps).
- **Show KPI values** and **Show GAP values** in the scoring tables.
- **Export All Operators in Focus panels:** every operator in the panels that show the Focus operators. The components list the exportable panels of [Scoring Export Panels](workspace-config.md#scoring-export-panels), those of the Focus operators tagged **Focus**.
- **Compare NSA vs SA**, offered when the workspace has NSA and SA CDRs: the module scores the NSA and SA CDRs of its campaigns side by side whatever the NR Mode of the report, its Campaigns list those of both NR Modes, and its GAP reference can be **Same operator in NSA** (see [NSA vs SA](scoring-gap-analysis.md#nsa-vs-sa)). Below it, as on the page:
  - **NSA vs SA:** **Each panel: NSA then SA** (default) or **All NSA, then all SA**, the slides of each NR Mode tagged **NSA** or **SA**;
  - **NSA & SA charts:** **NSA & SA in the same chart** (default: the Scoring Charts show the NSA and SA bars of each operator, the Scoring Trends and National & Country Areas Trends an NSA line and a dashed SA line per operator on one axis of quarters) or **NSA & SA in separate charts**.
- **Country Areas & Scoring Trends**, always included and scored on the whole country (the Region, Cluster and City filters do not apply):
  - **Country Areas:** the **Breakdown** (Region by default, Cluster, City or None) and the **Cities on their own** (London by default, or the **Main Cities** of the workspace at each generation) of the Country Areas and the National & Country Areas Trends;
  - **Scoring Trends:** their **Campaigns** (**All available campaigns** by default, Latest campaign, Latest 2, 3 or 4 campaigns, Previous campaign or chosen campaigns; none, **Same as the module**, takes the campaigns of the module), used for the Scoring Trend and the National & Country Areas Trends, and their **Time split**.

**Network Insights:** Technology, Split by, the LTE and NR coverage and interference thresholds, the overshooting distance, the map grid and the Environments.

**Non-Qualified Calls:** the period of the progress timeline, every call or open calls only, whether the Root Cause Analysis counts the suggested root causes, and whether its charts show the Not classified calls and the Lifecycle the calls without a value.

**CDR Analysis:** the **Global Comparison** (Auto by default) and **Global CDF Comparison** (Operator by default) of the charts, and the metrics of each CDR type (every metric, also those added later, when none is chosen). Its Campaigns choose the CDRs of the NR Mode of the report that the combined CDR tables include (the Final CDR of a campaign before its Weekly and Daily CDRs, or the **Active?** choice, see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)), the common filters filter their rows, and each CDR starts with a cover named after it, followed by the parts chosen for its type.

### Theme and iPhone pictures

**Theme** is the one colour theme of the whole report: the charts, tables and slide titles of every section that supports themes (Scoring & GAP Analysis, Network Insights, PPT Designer and CDR Analysis; Ericsson by default, see [Theme](network-insights.md#theme)). Reports saved when their Scoring and Network Insights sections kept their own theme keep only the theme of their Scoring section, set the first time the application opens their workspace.

**Chart Pictures for the iPhone Preview** (unchecked by default) is for reports read on an iPhone, iPad or Mac without PowerPoint.

- **Why:** their preview (Quick Look, also in Mail and Files, and Keynote) draws charts with its own engine, which gets many wrong: doughnuts and pies lose their colours and rings, multi-level categories lose their levels (operators missing or stacked), stacked bars get a wrong scale, hidden axes and legend entries show up, and the tables of a group, such as the category labels and keys around the Scoring charts, are left out.
- **What it does:** the PowerPoint also keeps a picture of each of those charts and groups, drawn by LibreOffice as the Word version is, that only that preview shows. PowerPoint (on a computer, Android, iPhone or the web) and LibreOffice keep showing and editing the native charts and tables and do not show the pictures. The pictures are the charts as generated: they do not follow changes made in PowerPoint.
- **Cost:** the report takes longer and its PowerPoint is bigger (a Scoring & GAP Analysis section of 300 charts takes about 80 seconds and 4 MB more); the Word version does not change. The report keeps the option for its schedule too, so its emails carry the pictures.

## Generate and preview

**Generate**, on a card, or **Save and generate**, in the editor, starts a run now, as the user who pressed it and in the formats of its schedule (PowerPoint and Word without one), listed at once in [History](#history).

- **Its dialog** shows its progress and processing time: **Stop** stops it after the step it is on (every user stops the runs they started, editors any run), and **Hide** (or Escape, or ×) closes the dialog while the report keeps being generated.
- **Following it:** meanwhile its card, and its row in History, show **Follow** to open the dialog again; when it is ready, a dialog on any other page offers to open its preview in **Reporting**.
- **Several at once:** **Generate** on other reports meanwhile queues them, without a dialog: they are generated one after another in the order asked, their cards say **Queued** (with **Follow**) until their turn, and a dialog tells when each one is ready (one after another when several finish together), also on other pages.

Ready, the report opens by itself in the [slide viewer](presentations.md#using-the-slide-viewer), to read it online without downloading it: its sections with their slides or pages on the left, the one chosen in the middle (change it and zoom as in any presentation), and at the top **PowerPoint** and **Word** (the format shown and downloaded among those generated, keeping the section shown), **Slideshow**, **Copy link** (the direct link of the slide shown, which opens the viewer for the users of the module) and **Download**.

- **Later:** **Preview**, on a card or in History, opens the same viewer on the run, also after a restart, while the run is kept.
- **Warnings** are listed above the slides, such as sections that could not be generated and those reused. A section that cannot be generated (for example Scoring without a campaign with Data, Voice and Speech CDRs) is left out and the others stay; a Design of PPT Designer or a CDR of CDR Analysis that cannot be generated is left out of its section, whose cover names it.
- **LibreOffice** is needed for the preview; without it the dialog says so and the files are downloaded from History.

**Reuse generated sections** (checked by default, above the list of reports) keeps each section generated for the next generations, by hand and on a schedule alike. A section is reused while the application has not been updated and its options, the common filters and the data it reads have not changed: the CDRs, the Operator and Vendor Maps, the Main Cities and, per section, the Designs, the methodologies and the Saved Scorings calculated, the inventory of the analysis, the follow-up of the calls or the CDRs the Campaigns of CDR Analysis choose.

- A Saved Scoring calculated again makes the Scoring & GAP Analysis section be generated again by itself.
- Generating the same report in the other format only composes and renders it; in the same format it also reuses the composed document (and the packed Word pages) and its preview.
- The dialog names the sections reused and whether the document was too, and so do the files of the run in its email (*Reused from an earlier export*). Uncheck it to generate every section again. Two runs that need the same section at once generate it once.
- Even unchecked, Scoring & GAP Analysis uses the Saved Scoring of the same CDRs, filters, methodology and GAP reference (and the same Scoring Trends campaigns when they have some) when there is one, a Favourite Scoring first, with its own Split by and National & Area Summary, and Network Insights the analysis already made for the same selection and inputs, so neither is calculated again; otherwise they are calculated.

## How a report is composed

The document starts with a cover with a large title (**Title on the cover**, else the name of the report), the optional **Subtitle** and every common filter (All for those without a value). Each section starts with its own cover: its name, its Campaigns, the common filters and its options.

- **Covers and transitions** use the Vodafone-Three red of the template (`Template_VodafoneThree.pptx`) with the Ericsson mark in outline behind them and the Vodafone-Three and Ericsson logos at the top right. Every cover has the same title and subtitle sizes (54 and 24 pt) and every transition smaller ones (40 and 20 pt), whatever the module; the subtitle starts below the room of two title lines, so a long title wraps into it.
- **Numbering:** each transition shows its counter above its title, 01, 02… for the first level and 2.1, 2.1.1… below it. Each section cover is a first-level transition (01 Scoring & GAP Analysis, 02 Network Insights…), and the transitions of its module are numbered below it: each scoring (1.1) and environment (1.1.1), each Design (4.1) and the transitions of its PPT Template (4.1.1). In Word they head their pages with the same counter.
- **Components:** each chart or table never spans two slides or pages. A title too long for one line is made smaller, in PowerPoint and in Word, so it never covers its chart or table.

**PowerPoint:**

- A table spread over several slides becomes one table on one slide: its rows joined under one header, and the parts of a table too wide for one slide (each repeating its first column) joined into one table with all its columns.
- A long table continues in up to four tables side by side, each under the header, so its text stays readable, with columns as wide as their values need; when its values would still be smaller than 6 pt, it continues on two or more slides (its title ending in *· 1/2*, *· 2/2*…), each under the header (in Word, smaller than 6 pt on the page).
- A table under charts (such as the RF Quality table under its CDFs in Network Insights) shares their slide while they keep at least 60 % of their size; longer, the charts keep its first rows and the rest continues on the next slides as a long table does. A legend under a table (such as the RSRP and SINR classes of the Network Insights class bars) stays under it on every slide.
- Tables side by side spread over several slides (such as one per network in the Network Deployment views) are each joined with their continuation and go on together on as few slides as keep them legible, each slide with the same rows of every table (a table out of rows leaves its place empty).
- Other charts or tables spread over several slides share one slide, made smaller down to 60 % of their size; smaller, they continue on as few more slides as keep that size.
- Small consecutive components of a section share a slide when they fit almost at their size, each under its own title (its subtitle when its title is the title of the slide).

**Word** (portrait pages):

- The report cover fills a page and is followed by a **Contents** page in the fonts and colours of the report theme (on its dark background for a dark theme): each section with its number, its parts and the topics of their components (such as Where to act or GAP Analysis, the components of every operator together), each with its page and a link; a long one continues on more pages. The cover of each section fills a page, followed by its components; the covers of the scorings and of the Designs become headings.
- Each page holds as many components of its section as fit, in their order: a page takes the next components while they fit (a little smaller when needed) and only reorders them inside the page, for example to put two narrow ones side by side, so a component never goes after one that follows it.
- A part, a topic, a component or a group of its pages that does not fit whole in what is left of a page starts the next one; one larger than a page starts a page and continues on the next ones, and a component larger than a page fills a page on its own, made smaller.
- A page never repeats the title of a component: one that follows another with the same title and context on the same page goes without it.

The PowerPoint and Word exports of [Scoring & GAP Analysis](scoring-gap-analysis.md), [Network Insights](network-insights.md) and [Non-Qualified Calls](non-qualified-calls.md) from their pages are composed the same way from the same slides, each starting with the cover of its module and ending with the closing slide, so they look like their section of a report.

## Schedule and email

The **Schedule** step gives the report its schedule; a report has at most one, saved with it.

- **Generate on its own:** off, the report is paused: it keeps its schedule but is only generated with **Generate**, and its card says *Paused*.
- **Recurrence** and **Time**, in the application timezone of [Application Config](app-config.md#runtime-settings) (shown below them): **Only with Generate**; **Once**, on a date and time in the future; **Daily**; **Weekly**, on the chosen weekdays (buttons, at least one); **Monthly**, on the chosen day (the last day in shorter months).
- **Formats:** **PowerPoint** and/or **Word** (both by default), the files of each generation, by hand or on the schedule, and of each email.
- **Email it** with its **Recipients**, separated by commas, semicolons, spaces or new lines (at least one while it is on); see [Email delivery](#email-delivery). **Add users** lists the active users with an email address, filtered by name, user or email: checking one adds its address at once and unchecking takes it out; **Select all** and **None** act on the users listed; those who could not open the links (without Reporting in their Modules Profile or access to the workspace) say *Cannot open the links*.

A run on the schedule generates the report as the owner of its schedule (the user who gave it the schedule) and is listed in History as *Scheduled*. The scheduler checks every 30 seconds.

> [!IMPORTANT]
> **Reports are generated on their schedule whenever the application is running.** The scheduler checks the schedules of every workspace, also when their workspace is closed or another one is open; the reports of the open workspace are generated in the server and the others in a separate worker that does not change the workspace open for users. Runs appear in the background tasks window as `Report: <name>` with their progress. A run that fell due while the application was stopped starts at the next check; several missed runs become a single run.

The Reporting Jobs of earlier versions became the schedules of their reports, once per workspace, the first time the application started with this version: each job that generated one report became its schedule, named after the report (when several jobs generated the same report, the one that ran on its own or emailed, else the first, was kept, and the runs of the others moved to it), and the jobs of artifacts designed in the job, of every favourite or of a report that no longer existed were deleted with their runs and files. App Events records it (`reporting_jobs_became_report_schedules`).

## Email delivery

With **Email it** on, each generation emails its recipients; without it, a run only keeps its files in History. The tool sends through the SMTP server or Power Automate flow of [Email Delivery](app-config.md#email-delivery) in Application Config, which must be configured.

- **Subject:** `DT Analyzer - ` followed by the name of the report and the time of the run.
- **Body:** every file on a card of its own, under a heading of its format in the colour of its application (**PowerPoint** or **Word**, so the two versions are told apart at a glance) that also holds its **View Online** and **Download** links and its size, with its title, the name of the report, its filters, its sections, those reused from an earlier generation and those that could not be generated with their reason.
- **Links:** with the **Public address of the server** set, the email gives a download link of each file with its size and, for a PowerPoint or Word with its preview, a **View Online** link that opens the run in the slide viewer in that format (the workspace of the report opens first when another one is open), so reports of any size reach their readers. Both work for the days set in Email Delivery (60 by default) and ask to sign in (the sign-in page returns to the link); only users with access to the workspace and Reporting in their Modules Profile open them.
- **Through SMTP**, the files are also attached while they fit the **Attachment Size Limit**; larger ones are only linked, and without the public address a run whose attachments exceed the limit fails with a clear message.
- **Through a Power Automate flow**, which carries no attachments, the files are only linked (the public address is required). An email that would not fit in a flow request leaves out the content and filters of each file and then its card, keeping the format before each title.

The Email column of [History](#history) says how it went: *Sent to … (attached)* or *(as links)*. An expired link opens a page that says so; the files stay in History while the run is kept, and a deleted run takes its links with it. App Events records who downloaded or viewed each file from a link (`download_reporting_file_link`, `view_reporting_file_link`) and each link refused for lack of access to the workspace (`report_email_link_denied`).

## History

**History** lists every run of every report, by hand or on its schedule, the latest first, under the heading of its day. Its columns: **Run** (its number); **Report** (its labels, as on its card, and name); **Trigger** (*Scheduled*, or *Generated by* the user who pressed Generate or reran it, by first and last name); **Started**; **Status** (with its progress and step while it runs, how long it took once finished, who stopped it and after how many steps, or its error); **Email** (how it went, or *No email*); **Files** (each in the colour of its format, PowerPoint orange and Word blue, with its size and a download link; a file that could not be kept shows its error); **Size** (all its files on disk); and the actions **Preview**, **Follow**, **⇣** (its files in one ZIP), **↻ Rerun**, **■ Stop** and **× Delete**.

| Status | Meaning |
| --- | --- |
| Queued, Running | The run is waiting or generating; progress and the current step are shown |
| Stopping | A user stopped the run, which finishes the step it is on |
| Ready | Every file was generated; the report is not emailed |
| Sent | Every file was generated and emailed |
| Partial | Some files failed; the others were emailed |
| Failed | No file was generated, or the email could not be sent |
| Stopped | A user stopped the run: it shows who and after how many of its steps |

- **■ Stop** (Queued or Running; editors, while other users stop their own runs from the **Follow** dialog): a queued run does not start; a running one becomes **Stopping**, stops after its step (a PPT it waits for stops with it, and the report stops as soon as it can) and keeps the files it generated, without sending its email.
- **↻ Rerun** (Failed, also interrupted, or Stopped; editors): the run starts again from the beginning in its own row, as generated by the user who reran it, with what its report includes now; what it generated before is deleted.
- **× Delete** (a run not queued, running or stopping; editors): deletes the run and its files after confirmation.
- **Filters:** every column but the actions filters as in Excel: its **▾** lists its values (the reports, the formats of **Files**, the statuses, the days of **Started** by year and month…) with a search, **Select all** and **Clear**, and **Apply** shows only the runs with a value checked. Filtered columns are highlighted, a line counts the runs shown (*Showing 4 of 15 runs*), and the filters are kept in the browser for each workspace and user.
- **Several runs:** editors check runs with the box before their number (or **Select all**, which checks the runs shown) and use **Rerun**, **Stop**, **Download** (the files of the checked runs in one ZIP, a folder per run) and **Delete** above the table, each on, with the number of runs, only when every checked run has that button on.

A run interrupted by a restart goes on at the first check of the scheduler after the application starts again: it keeps what it generated and continues from its step (it starts again when what it generates changed meanwhile), and a run being stopped ends as stopped. A run interrupted by more than three restarts fails instead, so that a run that brings the application down does not run again and again; **Rerun** runs it again. Every stop, rerun, deletion and resumption is recorded in App Events.

Runs are kept in `output/reports/reporting-jobs/` of the workspace, one folder per run with its files and the preview, until the run is deleted. Files are named `yyyymmdd_hhmmss - DT Analyzer Bundle Report - <report name>` with the time of the run, for example `20261006_093000 - DT Analyzer Bundle Report - Weekly PPT.pptx`; the ZIP of a run `yyyymmdd_hhmmss - Reporting - <report name>.zip`.

## Portability

Reports travel with **Admin → Import / Export / Transfer** as **Report Definitions** (also within Full Workspace and Full Environment), with workspace transfers and with backups, each with everything the editor saves for it:

- **What it includes**, with every option of its sections (such as the GAP reference, methodology and Country Areas & Scoring Trends of Scoring, Main Cities kept as such). Packages of Bundle Report Template Favourites, and of Complete Reports before them, still import. A report replaces the report of the destination with its identity or name (one renamed on the source server is renamed there too, with its schedule) and finds its Designs by ID, or by name and NR Mode, in the destination workspace (Designs of the same name in NSA and SA are told apart), with the same ones checked and in the same order; a transfer that also carries the Designs imports the reports after them.
- **Its schedule and email** replace those of the report in the destination (a report without a schedule leaves the one the destination has). The schedule belongs to its owner on the source server when that user is active in the destination, otherwise to the importer, and a single execution already past becomes *Only with Generate*.
- **Its stars:** each user who starred reports in the source workspace and has an account in the destination gets the star they have in the source, added or taken away, while other users' stars stay (packages of earlier versions never take a star away).

Packages and backups of earlier versions with a **Report Schedules** element (formerly Reporting Jobs) still import, after the reports: each schedule goes to the report of the same name, as above; the schedules of reports the destination does not have, and the Reporting Jobs whose artifacts were designed in the job, are left out, and the import summary says how many.

The import preview compares each report as its import would save it (its PPT Designs those of the destination): one that would stay the same counts as unchanged, and one that would change says what it includes and what would change, as the editor names it, also in its schedule (*Schedule · Recurrence: Weekly on Monday at 08:00 → Daily at 08:00*, *Schedule · Recipients: +user@example.com*) and stars (*Stars: +User A, −User B*). History and its files are generated output and travel only in a Full Workspace or Full Environment with **Include generated designs and reports**.

## Tips & shortcuts

These keys and gestures speed up the reports. The shortcuts that work everywhere are in [Web Interfaces](web-interface.md#tips-shortcuts).

| To… | Do this |
| --- | --- |
| Switch between **Reports** and **History** | Click the tab, or focus a tab and press <kbd>←</kbd> / <kbd>→</kbd> |
| Order the modules and sub-modules of a report | Drag them by their handle (⋮⋮); the window scrolls when you drag near its top or bottom edge. Or focus the handle and press <kbd>↑</kbd> / <kbd>↓</kbd> |
| Add an Operator pattern to the common filters | Type it in the search of **Operators** (`VF*`, `-Three`) and press <kbd>Enter</kbd> |
| Close an open list of the editor | <kbd>Esc</kbd>, or click outside it |
| Keep working while a report is generated | **Hide**, <kbd>Esc</kbd> or **×** closes its dialog; **Follow** opens it again |
| Read a generated report | In its preview, the wheel or <kbd>←</kbd> / <kbd>→</kbd> change the slide (a swipe on a phone); <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+wheel, a pinch or a rectangle dragged over the slide zoom (see [the slide viewer](presentations.md#using-the-slide-viewer)) |
