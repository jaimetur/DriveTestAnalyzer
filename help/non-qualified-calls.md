# Non-Qualified Calls

Follow up every call and test that did not complete. Non-Qualified Calls brings the CDR Drive Test follow-up into DriveTest Analyzer as an **NQ Analysis Center**: an executive summary of every Non-Qualified call, a drill-down table of those calls and a shared follow-up of each one that every user of the workspace sees.

- **Each call** is followed through six sections — **General**, **RCA**, **Failure Details**, **Analysis**, **Implementation** and **Planning** — with a Root Category and Root Cause decided from four sources (the NetCheck RCA of the CDR, the Ericsson RCA, the DT Analyzer RCA and the analysts), an NQ Call Status that follows the phases by rules or is set by hand, a responsible team, an analyst and a comment thread.
- **The panels** show which calls to analyse first (the scoring points each one loses, the repeated issues and the strategy that fills their Priority and their Voice and Data queues), the lifecycle and phases of the calls, where they fail and how the root cause sources agree.

> [!NOTE]
> **The calls need no extra input.** Every ready Voice, Speech and Data CDR of the workspace is indexed in the background, and each call keeps its follow-up by its NetCheck `JOIN_ID`. The [DT Analyzer RCA](#dt-analyzer-rca) finds the root cause of every call from the data of its CDR; the Ericsson RCA results and the analyses of the previous tool are optional imports.

The module is in development, so its main tab can show a red **ALPHA** label (see Interface Settings). On a new deployment it is in the Non-Qualified Calls and All Modules profiles; super-admins choose who sees it in [Super Admin → Modules Profiles](super-admin.md#modules-profiles).

## Presentations

```presentations
non-qualified-calls
dt-analyzer-rca
```

## Choose your task

| I want to… | Go to |
| --- | --- |
| Set up the statuses, teams, rules and root cause catalog | [NQ Analysis Configuration](#nq-analysis-configuration) · [DT Analyzer RCA](#dt-analyzer-rca) |
| Bring in the Ericsson RCA results or the analyses of the previous tool | [Ericsson RCA results](#ericsson-rca-results) · [Previous NQ Analyses](#previous-nq-analyses) |
| Choose the campaigns, operators and services I work with | [Filters](#filters) |
| See how many calls fail and where | [Summary](#summary) · [NQ Maps](#nq-maps) |
| Find which calls to analyse first | [NQ Prioritization](#nq-prioritization) · [Strategies](#strategies) |
| Find out why the calls fail | [Root Cause Analysis](#root-cause-analysis) · [Root Cause Sources](#root-cause-sources) |
| Analyse one call: its details, map, Layer3 Logs and comments | [Call details and activity](#call-details-and-activity) · [Map of the call](#map-of-the-call) |
| Assign the calls and track the follow-up by team and analyst | [NQ Calls panel](#nq-calls-panel) · [Progress View](#progress-view) |
| Share the calls in Excel, PowerPoint or Word, also on a schedule | [Exports](#exports) · [Scheduled reports](#scheduled-reports) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Which calls are Non-Qualified

A Non-Qualified (NQ) call is any Voice or Speech call, or any Data test, whose result is not **Completed** (for example **Failed** and **Dropped** Voice calls, **Failed** and **Cutoff** Data tests).

- **Result:** read from the processed `status` field of the CDR, else from `Call_Status`, `Test_Result` or `Test_Status`. Rows without a result are left out.
- **Umlaut CDRs** (see [Benchmarking Providers](benchmarking-providers.md)): a call or test is Non-Qualified when its Umlaut qualifier (**Qualifier**, or the **Browsing**, **Datastream**, **File Transfer** or **YouTube Qualifier** of its service) is **NOT QUALIFIED**: failed, dropped or below the Umlaut quality thresholds. Ping and DNS tests have no qualifier. A Data test keeps its identity by its `Test_Key` (Filename, Task Name and start), a Voice call and its Speech samples by their `Sequence`.
- **RCA of the CDR:** named after the provider (**Umlaut RCA** instead of **NetCheck RCA**, also in the exported documents). Umlaut CDRs bring no RCA hierarchy, only the failure of each call (its **Failure Comment**, the Umlaut Failure Indication), so their root causes come from the [DT Analyzer RCA](#dt-analyzer-rca), the Ericsson RCA and the analysts.

### Indexing

Every ready Voice, Speech and Data CDR of the active workspace is indexed as a background task, shown in the floating background tasks card.

- **When:** the first time the page opens; then, after a CDR is imported, reprocessed, deleted, given another CDR type (Daily, Weekly, Final or Flex) or included in or left out of the combined tables, at night (00:00–07:00, server time) once nobody has used the application for fifteen minutes (pages refreshing themselves do not count) and no import, export, transfer, backup or CDR processing runs. The indexing can take minutes, so it never slows the tool during the day and the page never waits for it.
- **Meanwhile:** those CDRs show as waiting to be indexed and their calls keep the values of their last indexing.
- **How:** each CDR is read from its [columnar copy](workspace-management.md#columnar-copy-of-the-cdrs) when the copy holds it as it is (only its Non-Qualified rows for their calls), by several low-priority processes, so the users keep the processor. The calls are written at the end, in one go: until then the rest of the tool saves its changes as usual.
- **Its card** shows what it does (the CDR read or written, the indexes, the versions of the calls, the DT Analyzer RCA) and how far it is. **Stop** stops it before it writes the calls: they stay as they were. The CDRs it did not index wait for the night, and a stopped **Reindex** runs at night once the server is idle (the top of the **Filters** panel says so) unless launched again before.
- **After a restart:** a **Reindex** stopped while it replaced the calls is put right when the application starts and as the next indexing starts (the indexes of the calls it left out are built again).
- **Status:** the top of the **Filters** panel shows how many NQ calls and CDRs are indexed, when, and the CDRs waiting or the indexing in progress; the page reloads its calls when it ends.

> [!TIP]
> **Reindex** (admins and super-admins) indexes every CDR again at once, in the background, even when no CDR changed. The follow-up is kept, and only what changed is written again: the population of each CDR (every call, qualified or not, which the rates count) and its Non-Qualified calls, which keep their DT Analyzer RCA when they are the same. It prepares what it writes apart and holds the writes of the workspace (a Scoring calculation, a saved comment…) only a few seconds at a time.

Choosing CDR columns for a table layout (workspace or personal) does not index the CDRs again: only those columns of the Non-Qualified rows are read from the columnar copy and added to the calls in the background, in seconds; columns no layout keeps leave the calls the same way. A CDR that also changed otherwise gets them with its night indexing.

### Call identity

Each call keeps a stable identity: its NetCheck `JOIN_ID`, the same in the Daily and the Final CDRs. Without a `JOIN_ID`, it is its service, Operator, Campaign and test or session identifier (`Test_ID` or `Session_id` for Data tests, `Session_ID_A` for Voice and Speech; without one, its subscriber, test name and start and end times).

- Its status, team, analyst, root category and cause, fields and comments stay with it when its CDR is reprocessed or uploaded again, and when the Final CDR replaces the Daily ones.
- A call in several CDRs is listed once (see [Daily and Final CDRs](#daily-and-final-cdrs)).
- Speech CDRs list one row per speech sample: each Speech **call** is listed once (with its number of Non-Qualified samples), and each sample keeps its own follow-up in the call details.

### NetCheck RCA values

The NetCheck RCA values (Failure Classification, Category and Subcategory) are written differently from one campaign to another. Values with the same letters and digits, also with a word in singular or plural, are one value in the filters, the table, the panels and the exports, written with spaces for underscores and the words and capitals most of their calls use (RF_Problems, RF Problems and RF problems are RF Problems; E2E traces required is E2E Trace Required). The CDRs keep them as written, and a filter saved with another spelling still selects the value.

## Daily and Final CDRs

A call can be in a Daily CDR, in several cumulative Daily CDRs and in the Final CDR of its campaign (see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)).

- **Which version is shown:** that of the CDR the combined CDR tables include: the Final CDR before the Weekly and Daily ones, a Weekly before the Daily ones, then the CDR with the newest calls, unless the **Active?** choice of Workspace says otherwise (Yes first, No after the others). A change of that choice, or a Final CDR that replaces Daily CDRs, gives the calls their new version in the background without reading the CDRs again.
- **Choosing CDRs:** the **NR Mode** and **Campaign** filters say which CDRs the calls come from; with the **CDR** column shown (see [Columns](#columns)), its filter chooses CDRs too, and each call shows the data of the most recent of them.
- **One analysis:** the analysis of a call is shared by every CDR that contains it, whichever CDR is chosen.
- **Call Details** lists every CDR that contains the call, with the date of its newest calls and the call's result in it.

A badge below the result tells how the other CDRs see the call (hover it for the CDR shown and the latest one); the **CDR Version** filter selects each case (**Latest version** are the others):

- **Changed between CDRs:** its result or failure differs in another CDR.
- **Newer version in another CDR:** a more recent CDR not chosen in the CDR filter has the call.
- **Not in the Final CDR:** only in Weekly or Daily CDRs while a Final CDR covers its campaign.
- **Completed in a newer CDR:** the most recent CDR has it Completed. Listed only while that CDR is not chosen in the CDR filter, or when **CDR Version** selects them.

> [!IMPORTANT]
> The analysis of a call is lost from view only when no loaded CDR contains it any longer (for example, it is not in the Final CDR and its Daily CDRs are deleted). It stays in the database and comes back if a CDR with the call is loaded again.

## Filters

The **Filters** panel restricts the summary, the panels, the table and the exports together, each group of filters in a card of its own.

**NQ Calls in Scope Only**, a switch above the filters, leaves the calls [out of scope](#prioritization-rules) out of the whole module, as if they were not there: the table, every panel, count and share (the [NQ Rate](#nq-rate-by-campaign-and-operator) counts every call in scope, qualified or not), the exports and the values every filter offers. It replaces the Operator, Region and NR Mode filters you would otherwise apply.

- **Yours:** kept with your other filters; **Reset Filters** leaves it as it is.
- **Beside it:** a line tells what is out of scope (*Out of scope: Vendor B · Three (SA) · not Focus: EE, O2*), and **Out of Scope** opens the same settings as the Out of Scope card of the Prioritization Rules (**Save** applies them to every call at once).

| Group | Filters |
| --- | --- |
| **General Filters** | **NR Mode** (NSA or SA, first: with Campaign it says which CDRs the calls come from), **Campaign**, **Operator**, **Operator_Vendor**, **Vendor_Operator**, **Vendor**, **Region**, **Cluster**, **City**, **Service**, **Technology**, **Test Name**, **Result** and **CDR Version** (see [Daily and Final CDRs](#daily-and-final-cdrs)). |
| **CDR Fields Filters** (blue) | The values as the CDR gives them: list fields derived from the call (such as **Session Type**), **Last Cell ID** and, with NetCheck CDRs, **G_Level_1** to **G_Level_4** (location levels, such as Drive or Walk and City or Connecting Roads). |
| **RCA Classification Filters** (amber) | What each RCA found: **DT Analyzer RCA** (Root Domain, Root Category, Root Cause and Rule), the NetCheck RCA (**Failure Classification**, **Failure Category**, **Failure Subcategory**) and **Ericsson RCA** (its categories and subcategories). |
| **Automatic Fields Filters** (violet) | What DT Analyzer fills: **Global Status** (the team's *Analysis Finished*, set by the [Status Rules](#status-rules)), **Status Set** (**Automatic** or **By hand**), **Follow-up** (Attended, Not attended, Open, Stalled, Closed, With team, Assigned, Commented, With a root cause, RCA identified, RCA not identified; also set by the indicator cards) and the [NQ Prioritization](#nq-prioritization) values (**Prioritization**, **Prioritization Rule**, **Prioritization Queue**, **Scoring Impact**, **Repeated Issue**, **Hotspot ID**, **Time-Window ID**, **Cluster ID**…). |
| **Analysis Team Fields Filters** (green) | What the analysts fill: **Root Domain**, **Root Category** (*Final Failure Category*), **Root Cause** (*Final Failure Subcategory*), **Priority**, **Team** (*Responsible Stream*), **Analyst** and **Reviewer** (tagged **No account** without an account), every list and Yes / No field of the analysts (Failed Party, Host Network when Failure, Band when Failure, Analysis Status, Implementation Status, Planned FY…) and **Serving Cell when Failure**. |
| **Additional Columns Filters** | The optional columns of the table (see [Columns](#columns)). |
| **Search** | Text in the call fields (Operator, Vendor, Campaign, Region, City, Technology, test, result, failure fields, cell, `JOIN_ID` and the CDR columns of the table), the fields of the analysts and the comments. |
| **Flags** | **Open calls only**, **Assigned to me** and **Without comments**. |

- **Identities:** **Operator_Vendor** is `<Operator>_<Vendor>`, **Vendor_Operator** the same as `<Vendor>_<Operator>` (both in sync), **Vendor** the vendor alone. **City** offers the workspace **Main Cities** first.
- **Special values:** **Unassigned** (no team or analyst), **Not classified** (no root domain or category), **No cause** (no root cause), **Empty** (no value).
- **From the catalog:** each card takes the filters of the fields of [Fields & Sections](#fields-and-sections) of its source, in catalog order; a new field appears in its card, and a card without filters is hidden. The analysis team's name for a filter, when different, shows below it (*Responsible Stream* below **Team**).

> [!TIP]
> **Each filter lists only the values of the calls the other filters leave** (its own choice does not count), plus the values chosen in it. Choosing a Campaign leaves only its operators in Operator; choosing SA in NR Mode leaves only the SA campaigns and takes the other campaigns out of the Campaign filter (also in saved filters). The CDR filter offers the CDRs with some of those calls, CDR Version all its states, and the column funnels the same values. A filter with more than 300 values (cells, sites, group IDs) lists its first 300: type in its box to search all of them, or press **Show All**.

- **No restriction:** every value of a filter, or none (**Select All / None** also chooses the values hidden).
- **Chips:** the filters applied stand out in the colour of the module and show as chips at the top of every panel, also those set from charts and cards (NR Mode, Call Type, Period, Age of Open Calls, root domain and cause with suggestions, eNB/gNB, Repetition Place); click one to remove it. **NQ Calls in Scope Only** comes first, darker. The NQ Rate panel dims the chips it does not use.
- **Reset Filters** clears them all but **NQ Calls in Scope Only**.

> [!IMPORTANT]
> **The selection is yours.** Each user finds their own last filters, on any device, whatever the other users choose at the same time; a user who has saved none yet starts from the selection the workspace shared before. **Assigned to me** always means the user viewing the page. An Operator or Vendor saved with a name the [Operator Maps](workspace-config.md#operator-maps) now show differently keeps selecting its calls (Vodafone SM selects VF SM once mapped to it), as do NetCheck RCA values saved with another spelling.

## App Events of the module

App Events (in [App Logs](app-logs.md#app-events)) records every action of the users of Non-Qualified Calls, each read as a sentence naming the calls by their `JOIN_ID`, operator, campaign, call type and NR Mode:

- **Reading:** the module opened (`nq_page_opened`); the calls listed with their filters, sort and page (`nq_calls_listed`, the same list read again recorded once); a call opened with its status, team and analyst (`nq_call_opened`); a Layer3 Logs record viewed (`nq_call_l3_record_viewed`).
- **Maps:**
  - `nq_call_map`: each map of a call with its `JOIN_ID`, radius, samples chosen, what it found, the NQ calls of other campaigns left out, the Diagnosis hints to check and worth a look and how long it took; `nq_call_map_failed` with the error.
  - `nq_call_l3_layers`: the Layer3 layers read (call, UEs, points, datasets, time); `nq_call_l3_layers_failed`.
  - `nq_l3_maps`: NQ Maps opened and each change of what it shows (filters, layers, grid, routes, sites, samples), with the NQ calls and sessions found, zoom, points or cells and time (moving or zooming is not recorded again); scope *map of a site* with the site, its network, operator, campaigns, radius, page it was opened from, NQ calls and whether the Network Inventory places it. `nq_l3_maps_failed` always, with the filters, zoom, area, layers and error.
- **Follow-up:** each value changed, from what to what (`nq_call_update`, such as *Status Not Attended → Under Planning; Status Mode auto → manual*, also the Status the rules gave); bulk changes with how many calls went from each value and their `JOIN_ID`s (`nq_calls_bulk_update`); queue Take and Assign (`nq_queue_take`, `nq_queue_assign`); comments added, edited (text before and after) and deleted (text and author); history deleted.
- **Configuration:** what each save changed: statuses and teams (added, removed, renamed, colours, members), fields and sections (label, settings, list values), Status Rules, Root Cause Catalog and suggestion rule, columns and layouts, Map Levels, DT Analyzer RCA rules (also the learning switch), **NQ Calls in Scope Only** and the Out of Scope settings, NQ Prioritization (strategy before and after, each step with its fields before and after, strategies created, renamed or deleted, settings).
- **Background:** each night indexing and how long each phase of every indexing or **Reindex** took (`nq_calls_reindexed`); a stopped indexing (`nq_calls_index_stop_requested`, `nq_calls_index_stopped`); indexes rebuilt after a restart (`nq_population_indexes_restored`); each NQ Prioritization calculation.
- **Files:** exports with their filters (`nq_calls_export`, `nq_summary_export_powerpoint`, `nq_summary_export_word`), images (`export_nq_calls_image`), the catalog workbook exported, previewed and imported, templates (`nq_template_download`), Ericsson RCA results and previous analyses previewed and imported (`nq_analyses_import`), analysts linked (`nq_analysts_linked`).

## Sections bar

A bar above the Filters, sticky at the top of the window, jumps to the top of the page (its arrow) and to each panel: **Filters**, **NQ Hotspots** ([NQ Hotspots, Clustered & Time-Window Issues](#nq-hotspots-clustered-time-window-issues)), **NQ Queues** (NQ Prioritization & Queues), **NQ Maps**, **NQ Calls** (the [table](#nq-calls-panel), with the number of calls of the filters), **Summary**, **NQ Rate**, **Failures**, **RCA Sources**, **Root Causes**, **Lifecycle** and **Progress**. **NQ Analysis Configuration** is below it, at its right (beside it on a phone).

- **Jumping:** the chosen panel opens at the top, below the bar (unfolded if folded), and stays there while its data arrives; the bar marks the panel being read and, on a narrow window, scrolls sideways to keep it in sight.
- **Badges of every panel:** below its **Collapse** button, the calls of the filters (*774 Filtered Calls*) and, standing out, the calls the queues list (*316 In Queues*, the same count as the [Lifecycle & Phases](#lifecycle-phases) card), then the chips of the active filters. While it waits for data it shows an animated **Loading…** bar over its previous content.
- **Reloading** (also Back and Forward, or the bottom bar of a phone) returns to where the page was read, dimmed with a loading notice until every panel on screen is drawn; opening the page starts at the top.
- **Changing the filters** (a JOIN_ID, a chip, a card or chart value) or the page, order or rows of the list keeps the panel you use, or else the one you read, in place while the panels redraw, so the page never jumps; a panel left much shorter stays in view, and scrolling meanwhile leaves the page where you take it.

> [!TIP]
> **Folded panels are not calculated.** A folded panel is calculated when unfolded, so a change of the filters only waits for the open panels.

## Summary

The **Summary** panel is the executive view of the filtered calls: how many are Non-Qualified, open and closed, attended (followed up with a change other than assigning them, or commented), with a responsible team or with comments.

- **Breakdowns:** by Service, Result, Status, Team, Root Domain, Root Category, Root Cause, Failure Classification, Campaign, Operator, Vendor, Region, Cluster and City, six per row, in the colours of the one-slide Executive Summary of PowerPoint and Word (statuses, teams and root domains in their colour, root categories and causes in that of their domain, the rest in a fixed palette).
- **Campaigns** read as everywhere in the tool (*UK_Q2_SA_2026* reads *26-Q2-SA*; see [Campaign ordering](technical-considerations.md#campaign-ordering)) and still filter by the full campaign.
- **Drill down:** click a bar to show only that value; again to remove the filter.
- **Own breakdowns:** fields marked **Summary breakdown** add theirs, in the colours of their values (those of the analysts or derived also drill down).

## NQ Prioritization

The **NQ Prioritization & Queues** panel, below the NQ Hotspots, Clustered & Time-Window Issues, tells which of the filtered calls to analyse first, as the teams plan their analyses by service and NR Mode (for example every SA Voice call, and only the SA Data calls with a repeated issue or a high scoring impact). Every Non-Qualified call gets these values, also fields of the call, columns, filters and Summary breakdowns (see [Fields and sections](#fields-and-sections)):

| Value | What it says |
| --- | --- |
| **Scoring Impact** and **Scoring Points Lost** | The scoring points of its campaign the call loses, and their level: **High**, **Medium**, **Low** or **No impact**; **Not scored** when its campaign cannot be scored yet, **Excluded from Scoring** when it is in a list of [Scoring Excluded Calls](scoring-gap-analysis.md#excluded-calls). **Scoring KPIs Lost** lists the KPIs and environments, the most first (see [Scoring Impact](#scoring-impact)). |
| **Repeated Issue**, **Repetitions**, **Repeated Campaigns** and **Repetition Place** | Whether the call is in a [cluster](#repeated-issues), how many NQ calls of its operator failed near it or at its site (the call included) and in how many campaigns, and that place. |
| **Hotspot ID**, **Time-Window ID** and **Cluster ID** | The IDs of its [groups](#nq-hotspots-clustered-time-window-issues) (*H-3AFA56*), empty when it is in none of 2 calls or more. Not columns by default: choose them with **Columns**, also for Excel. |
| **Prioritization**, **Prioritization Rule** and **Prioritization Queue** | **Prioritized** or **Track only** by the [strategy](#strategies): the step whose conditions the call meets (*Campaign 1 · SA Voice · Cities*; **No rule** when none does or its operator is in no step), which gives its **Priority** and its **Voice** or **Data** queue (none when the step only tracks it). |
| **Expected Gain** | The scoring points its analysis is expected to recover, which orders the calls of one step: its Scoring Points Lost once the Final CDR of its campaign is scored, else the points its failure lost in the latest campaign of its NR Mode with a Final CDR (never a [Flex campaign](workspace-management.md#flex-campaigns)), localised in one region, cluster or city; empty when there is none (the oldest call then goes first). |

**Cards** on top: the **Prioritized** and **Track only** calls, those with a **High Scoring Impact** (and the points the filtered calls lose), the **Repeated Issues** (and their clusters) and **Next to analyse** (per queue). A click shows only those calls; again to remove the filter.

**Strategy** subpanel: a tab per list, with its filtered calls in a badge: **List 1 · Weekly CDRs** (blue; **Weekly & Final CDRs** when the strategy has no list 2), **List 2 · Final CDRs** (purple) and **Outside the lists** (grey: **Out of scope** and **No step**). It opens on the list with most calls and keeps the tab chosen. Each step shows, in their colours:

- its Priority, Step (number in a pill of its own colour, the same in the queues; a click shows its calls), NR Mode (SA purple, NSA green), Call Type (colour of its queue), Area (Cities raspberry, Connecting Roads indigo, Any grey), Condition (in full on hover), Operators and Queue (Voice blue, Data teal, Tracked grey);
- the filtered calls it took, their **Follow-up** in a stacked bar — **Waiting** (open, not attended yet, with their number), **In progress** (attended, open; amber), **Closed** (green), every number on hover — and their scoring points in a blue bar scaled to the step that loses most in the tab (PowerPoint and Word give the open and waiting calls and the points as numbers);
- a note with the calls waiting for their prioritization and the campaigns not scored yet, with the reason (also on hover of the badge at the top right).

**Next to analyse:** the **Voice queue** and the **Data queue** (the **Unique queue** alone for a strategy of one queue, such as Vodafone Proposal), one subpanel each in the colour of the queue, with its team and badges *48 waiting · 4 under analysis*.

- **Which calls:** a prioritized call is in its queue while its NQ Call Status is marked **In Queue** in [Statuses & Teams](#statuses-and-teams): first the calls under analysis, their status before their owner (*Under Analysis · User A.*), then the first calls waiting for somebody (20 by default) in the order the analysts take them (see [Strategies](#strategies)). An assigned call still waits until somebody attends it; a call set back to Not Attended or Assigned waits again.
- **Columns:** position, JOIN_ID (on one line), Priority, the step as the Strategy subpanel shows it (**Step**, **NR Mode**, **Call Type**, **Condition** with its list and what it takes on hover), operator, campaign (as the [Campaign Maps](workspace-config.md#campaign-maps) name it, *2026-Q3-SA*), **Owner**, Expected Gain, Scoring Impact, **Actions** (Take, Assign) and **Select**. Each table fits its card, other columns wrapping on two lines when narrow. A click on a call opens it.
- **Tracked**, the last subpanel, folded: the open calls only a tracked step takes, in no team queue. An empty queue says so (*No call is waiting in the Voice queue.*).
- **Queues by hotspots** (the Data queue by default) list **hotspots** instead of calls: each with at least the **Minimum hotspot size** of failures of the queue among the filtered calls (3 by default), up to Next to analyse (the badge then tells *20 of 29 hotspots* beside *143 calls in hotspots*), in the order of its first waiting call.
  - The calls of a hotspot are analysed together: its **Track only** calls go with it (they keep their Priority, count in its size and Waiting, are taken or assigned with it and leave the tracked list). A hotspot with prioritized calls in two such queues goes to the one with most of them.
  - Each row: position, Hotspot ID with its sites and period, the Priority, Step, NR Mode, Call Type and Condition of its first call, operator, campaign, **Waiting · Owner** (*3 of 5* waiting, who has them, each analyst else team with their calls, *2 · User A.*, two at most, the others in *+2 more* on hover, *No owner yet*; its *Track only* calls, and its calls *in progress* and *closed*), Expected Gain of its waiting calls, the highest Scoring Impact, Actions and Select. A click on its ID filters the calls and the queues by the hotspot.
  - **Individual failures**, folded below, lists the other waiting calls one by one.

**Who takes each call**, above the queues: four views with their waiting calls per queue (*All · 342 (Voice 117 · Data 225)*), remembered on this browser: **All**, **Unassigned** (no team and no analyst), **My team** (calls without an analyst of your teams: their team, or that of their queue when they have none) and **Assigned to me**.

- **Owner:** the analyst (bold), the team, or the team of its queue (italics) while it has none.
- **Take** (editors, green) asks, then makes you the analyst of a call without one (of every waiting call of a hotspot without one); the calls take your team (your only team, or the one you choose; a user of no team leaves each call its team). A call another analyst took a moment before is left as it is, and a message names them.
- **Assign** (admins, purple) gives a call, or the waiting calls of a hotspot, a team and / or an analyst (a team with members offers only them; *Keep* leaves what each has, *No team* / *No analyst* removes it). For several, tick them in **Select** (**All** in its header ticks the rows listed; its tooltip tells how many) and **Assign** them from the bar above the queues. An assigned call keeps waiting, **Assigned**, until somebody attends it.

**Scoring Impact** subpanel: the calls of each level, and the points lost in each KPI and environment.

**Recalculate** (`user-editor` and above) calculates every value again in the background; **Prioritization Rules** opens the rules. **Strategy**, above them, chooses the strategy of the module (admins and super-admins; greyed out for the others): after a confirmation every call takes its step, queue and Priority at once (the calls in analysis keep their Priority), the other settings stay as saved.

### NQ Hotspots, Clustered & Time-Window Issues

The **NQ Hotspots, Clustered & Time-Window Issues** panel, right below the Filters (**NQ Hotspots** in the sections bar), groups the filtered calls that fail close to each other (see [Repeated issues](#repeated-issues) for how the groups are made). It comes with the data of the NQ Prioritization, so unfolding either panel reads both.

- **On top:** the criteria of the [Prioritization Rules](#prioritization-rules) as chips (Time window, Time-window distance, Cluster distance, Hotspot join, Cluster size, Cluster period), then the call types.
- **NR Mode:** every group is of one NR Mode, whatever the filters: NSA and SA failures have other causes and are analysed apart.
- **Three tables** with the same columns and widths, each with its calls in a badge, the most calls first, scrolling inside the panel (also sideways when too narrow, so no word is split). Each lists its first 100 rows, with **Show All**; a column filter looks at every row. PowerPoint and Word keep the 25 with most calls of each.
  - **Hotspots (Clustered OR Time-Window Issues)** (*AND* with the AND join), **Time-Window Issues** and **Clustered Issues** (a long series of failures along a road makes several clusters, each one row).
- **Columns:**
  - **ID:** **Hotspot ID**, **Time-Window ID** or **Cluster ID**, a short code that stays the same whatever the filters (*H-*, *T-* or *C-* and the start of the key of its first call, *H-87BB7D*), with its sites (the site of most calls, *+N* when more) for a cluster, its period for a time-window issue, both for a hotspot. A click filters the calls of the group (**Hotspot**, **Time-Window Issue** or **Clustered Issue** filter, one group at a time) and takes the page to the [NQ Calls panel](#nq-calls-panel); another click removes the filter.
  - **Operator**, **NR Mode** and **Campaign** (each with its calls when several), **Site(s)**, **From** and **To** (*20 Nov 16:18*, the full date on hover; the time goes below the day when narrow), **Calls**, the **Voice / WhatsApp / Data** calls in a stacked bar (blue, aqua green, darker green), the points lost, the open calls and the main root category.
- **Column filters** work like Excel: **▾** lists the values (search, **Select all**, **Clear**; **From** and **To** by year, month and day), **Apply** keeps the rows checked and marks the header. They are kept in your browser per table and workspace, also when the panel is read again.
- **Order of the tables:** the more general first. With OR the Hotspots come first: each time-window issue and each cluster of a campaign falls within one hotspot (with one NR Mode filtered and a Cluster period of 0, hotspots hold exactly them), and a hotspot can hold several. With AND the Time-Window and Clustered Issues come first and the Hotspots last: every failure of a hotspot is in both (with a Cluster size of 2) and each hotspot falls within one time-window issue. Time-window and clustered issues never contain one another: the one with more calls goes first, and with the same calls the one with fewer rows.

### Scoring Impact

The points a call loses are those of the scoring of its campaign, as Scoring & GAP Analysis scores it (see [Points Lost](scoring-gap-analysis.md#points-lost)):

1. Each campaign of each NR Mode is scored from the Scoring History over the CDRs the combined CDR tables include, with the methodology of the campaign, split by operator.
2. For every KPI that counts tests (the ratios: call success, transfer success, POLQA below 1.6, throughput above a threshold…), the points the operator loses in the environment of the call (Drive - City, Drive - Connecting Roads…) are shared equally among the tests that miss it, as the Points Lost Map shares them.
3. A call holds the share of every KPI it misses (the samples of a Speech call add up). Averages, medians and 90th percentiles (setup time, POLQA MOS, P90 throughput) are not shared, as a failed call has no value in them.

- **Levels:** within its campaign, operator and service, the calls holding the first half of the points lost are **High**, those up to 80% **Medium**, the others **Low** (calls with the same points share their level); both shares are set in the rules and apply at once.
- **Out of scope:** the calls [out of scope](#prioritization-rules) are compared only among themselves and never change the levels of the calls in scope (in the Scoring Impact, the conditions of the steps and **#Calls**, which therefore agree).
- **Not scored:** while the Scoring History still indexes the CDRs of the campaign, when no CDR of it is in the combined CDR tables, or when the workspace has no methodology.

### Repeated issues

The calls that fail close to each other form three kinds of groups. Every group keeps to one NR Mode (as the steps of the strategies), and the Ping tests and the calls [out of scope](#prioritization-rules) are in none and make none.

- **Cluster** (a **Repeated Issue**; the condition **Cluster** of the steps): at least the **Cluster size** (2 by default, the call included) of NQ calls of one operator that started within a circle whose radius is the **Cluster distance**, in its campaign and the campaigns of the **Cluster period** before it, whatever their service (a Voice and a Data failure at the same site count), at any time.
  - **Cluster period:** none by default; the campaigns of a quarter, SA and NSA together, count as one, by the quarter their name gives (*UK_Q3_2026* is 2026 Q3 whenever the call ran; by the date of the call only when the name gives none); a quarter without a campaign is skipped. Calls without a date count in every period near them.
  - **How it joins:** nearest calls first, then the next nearest, while they still fit in the circle (not centred on any call): a cluster never chains along a road, a long series makes several clusters that meet at the widest gaps, and calls at one site join only within the Cluster distance too.
  - **Repetitions:** the calls within the Cluster distance of the call or at its site (its **Repetition Place**), which can be more than its cluster holds.
- **Time-window issue:** another failure of the same operator, NR Mode, campaign and drive started at most the **Time window** before or after it (6 minutes by default) and at most the **Time-window distance** from it, whatever its call type; each failure is within both of the one before.
  - **The drive is the car:** the measurement system of the CDR (`Measurement_System` of a data CDR, `System_A` of a voice CDR), else its file (`File_ID`, `File_ID_A`, one device). Failures of other cars measuring elsewhere at the same time never follow one another, and a failure of a CDR that gives neither is in none.
  - A failure without a position follows the one before.
- **Hotspot:** 2 or more failures of the same operator, NR Mode and campaign, whatever their call type (4 Data failures and 1 Voice failure make a hotspot of 5), that its clusters and time-window issues make together:
  - **Hotspot join** OR (default): every failure of a cluster or time-window issue that shares a failure with it, their envelope, so a hotspot holds the touching time-window issues and clusters of its campaign;
  - AND: the failures of the same cluster and the same time-window issue, where they meet.
  - A step with *Time-Window Issues OR Cluster* takes the failures of the OR hotspots and those whose cluster holds calls of the Cluster period before their campaign (exactly the same with a Cluster period of 0); one with *Time-Window Issues AND Cluster* takes a failure of a time-window issue that is in a cluster too, which an AND hotspot takes only when another failure shares both.

**Distances** follow the network: a city site serves a few hundred metres, a road site several kilometres. They are measured in **inter-site distances (ISD)** of the sites nearest to where the two calls started, the larger of the two (see [The network around the call](#the-network-around-the-call)); the calculation keeps the ISD of each call.

- **Cluster distance:** 0.5 ISD by default; without an ISD (no Network Inventory, or no site near), 250 m in cities and 1 km on connecting roads (when either call is on one).
- **Time-window distance:** 0.8 ISD by default, so a car that drove from one city to the next breaks the time-window issue; without an ISD, 500 m in cities and 2 km on connecting roads.

**Place of a call:** the site of the cell where it ended: the site ID and host network of its eNB or gNB in the [Network Inventories](workspace-management.md#network-inventories) and cell mappings of the workspace, in a network that serves its operator (its own first, as the [Serving Networks](workspace-config.md#serving-networks) say) within their maximum distance of the call, since an eNB or gNB number is only unique within its network (each node takes the sites of the newest snapshot that lists it). Else the site that served its start (the serving-cell [Vendor Mapping](workspace-management.md#vendor-mapping), with its host network), the same place when it is the same site; else the eNB or gNB of its last cell; else a spot of the cities Cluster distance around where it started (where the panel lists it).

### Strategies

The **Strategy** of the workspace orders the calls into queues; it is set in [Prioritization Rules](#prioritization-rules) (admins and super-admins).

- **Dual Queue (Cities first):** the default.
- **Dual Queue (Roads first):** SA Voice on Connecting Roads before Cities.
- **Dual Queue (Scoring Based)** (formerly Points Lost Based): orders every call by its impact level; its list 1 is list 2 below.
- **Vodafone Proposal:** SA before NSA and Voice before Data, in one **Unique queue**: (1) SA Voice and SA WhatsApp, every call, P1; (2) SA Data of a cluster, P2; (3) NSA Voice and NSA WhatsApp, every call, P3; (4) NSA Data of a cluster, P4; (5) every other call (Any NR Mode and Call Type), P5, in the Unique queue too; (6) Tracked: the Ping tests and the Excluded Calls, P8.
- **Strategies of your own:** copies of a strategy, edited the same way.

**Queues:** Voice and WhatsApp calls go to the **Voice queue**, Data calls to the **Data queue** (every call to the **Unique queue** in Vodafone Proposal), and each analyst takes the top call of the queue of their team.

**Two lists:** each call takes a step of one list.

- **List 1 (Weekly CDRs)** orders the calls of a campaign while its Final CDR is not scored, by what each call says about itself, which never changes as new Daily or Weekly CDRs arrive: its NR Mode, its call type (Voice, WhatsApp or Data) and where it failed (Connecting Roads and highways, else Cities, from its environment).
- **List 2 (Final CDRs)** orders them once the Final CDR of the campaign (a Final CDR of its type in the combined CDR tables, see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)) is scored, by their real impact, the same in the four strategies of the application.
- **Use List 2 for Final CDRs**, per strategy, is on by default and off for Dual Queue (Scoring Based) and Vodafone Proposal: off, list 1 orders every call, also once the Final CDR is scored.

Default steps of list 1:

| Priority | Dual Queue (Cities first) | Dual Queue (Roads first) | Queue |
| --- | --- | --- | --- |
| P1 | SA Voice in Cities | SA Voice on Connecting Roads | Voice |
| P2 | SA Data: Hotspots | SA Data: Hotspots | Data |
| P3 | SA Voice on Connecting Roads | SA Voice in Cities | Voice |
| P4 | SA WhatsApp | SA WhatsApp | Voice |
| P5 | NSA Voice | NSA Voice | Voice |
| P6 | NSA Data: Hotspots | NSA Data: Hotspots | Data |
| P7 | NSA WhatsApp | NSA WhatsApp | Voice |
| P8 | Tracked: the other data failures (no Data step takes them), Ping tests and Excluded Calls | the same | — |

Default steps of list 2:

| Priority | Steps |
| --- | --- |
| P1 | 1 · SA Voice with a High impact |
| P2 | 2 · SA Data with a High impact |
| P3 | 3 · SA WhatsApp with a High impact |
| P4 | 4 · SA Voice with a Medium impact · 5 · SA WhatsApp with a Medium impact · 6 · every other SA Voice call · 7 · every other SA WhatsApp call |
| P5 | 8 · NSA Voice |
| P6 | 9 · NSA Data with a High impact |
| P7 | 10 · NSA WhatsApp |
| P8 | Tracked: the other data failures (no Data step takes them), Ping tests and Excluded Calls |

**Order of a queue** (summed up in the **Queue order** card of the rules): by Priority, then the newest campaign (a call of a newer campaign goes before one of an older campaign whatever its step), then the step (the upper row first; a call meeting two steps takes the upper one), then the highest **Expected Gain**, then the oldest call.

- **Which step:** a call of an SA campaign takes its SA step when the step takes its operator; else (as the calls of an operator without SA such as Three) its NSA step when that one takes it. A call no step takes is tracked when a Tracked step takes it, and enters no queue otherwise (for example, SA steps with `VF` only and NSA steps with `VF & Three`).
- **Priority of the open calls:** with **Fill the Priority of the open calls** (beside the Strategy, on by default), the [Priority](#default-catalog) of each open call is filled with that of its step while it is empty or still the one the step gave. Once someone changes or clears it by hand, or the analysis starts (its NQ Call Status is no longer the first one), it is kept: a new strategy, or the Final CDR of its campaign, only re-orders the calls nobody has started. The history records each change.

### Prioritization Rules

**Prioritization Rules** (in the NQ Analysis Configuration menu and the NQ Prioritization & Queues panel) shows the strategies and settings to every user; only admins and super-admins change them.

- **Strategies:** **New Strategy** copies the strategy shown, with its **Name** ready to change; **Rename Strategy** renames any of them; **Delete Strategy** deletes one of your own (the four of the application cannot be deleted). Strategies of your own, names, steps and list 2 are saved with the other settings and travel in the NQ configuration.
- **Lists:** the dialog shows one list at a time: the switch above the table chooses **Weekly CDRs** (list 1) or **Final CDRs** (list 2), shown only while **Use List 2 for Final CDRs** is on (otherwise list 1, also after switching from the Final CDRs list of another strategy).

Each step has these columns:

| Column | What it sets |
| --- | --- |
| **Priority** | P1 (red) to P8 (grey); by default the step number is the Priority. The steps of one Priority are grouped under it, in the order they are tried. The ⠿ before it moves the whole group: dropped onto another Priority the two swap, keeping the order of their steps; onto a Priority without steps, the group takes it; the arrow keys swap it with the Priority above or below. |
| **Step** (⠿ n ×) | Its place in the list, which names its Prioritization Rule (*Campaign 3 · SA Voice · Connecting Roads*). Drag the handle (or the arrow keys) to move it, taking the Priority of the step it joins; while dragging, the empty Priorities show to drop it there. The red **×** deletes it (a default step comes back with **Default Rules**); **+ Add step** adds one at the end, at most 20 per list. |
| **NR Mode** | **SA**, **NSA** or **Any** (purple, green, grey). |
| **Operators** | By default the Focus operators of the [Operator Maps](workspace-config.md#operator-maps) by name: the SA steps take those that use SA, the NSA and Tracked steps those with NQ calls (in the UK, `VF` in the SA steps and `VF & Three` in the others). An operator uses SA when at least 10 % of its NQ calls of the SA campaigns ran on NR SA (NR SA or NE-DC); one without SA, such as Three, drives them on LTE. **Focused Operators** (every Focus operator, or every operator without any) comes first and stands alone, clearing the others; several operators show joined with ` & ` (*Focused* in the column, full values on hover). |
| **Call Type** | **Voice**, **WhatsApp**, **Data** or **Any** (Ping tests too), in the colour of its queue (a WhatsApp step of the Data queue is teal). |
| **Area** | **Cities**, **Connecting Roads** (roads and highways) or **Any**, from the environment of the call. |
| **Condition** | The conditions the calls meet, chosen one by one (see below). |
| **#Calls** | An estimate to design the steps and queues: how many calls the step would take in the latest closed campaign of each NR Mode with its Final CDR, counted again as you edit: list 1 as during the campaign, list 2 as once the Final CDR is scored (the impact levels of both by the own points of those calls; during a real campaign list 1 takes the estimate from the Final CDR before). Calls out of scope are left out; hover the title for the campaigns (as the [Campaign Maps](workspace-config.md#campaign-maps) name them). |
| **Queue** | **Voice**, **Data** or **Tracked** (only tracked): blue, teal, grey. |

**Conditions**, the same for every Call Type and both lists, each in its colour (also in the panel), with a tag of what it is based on; the **Conditions** card under the steps and each condition's tooltip explain them:

- **Every call** (green): stands alone, clearing the others.
- **Time-Window Issues** (cyan, *Time-based*), **Cluster** (grape, *Position-based*) and **Hotspots** (pink, *Position & time*): see [Repeated issues](#repeated-issues). During the campaign the repetitions are those known so far, from the CDRs indexed.
- **High impact**, **Medium impact**, **Low impact** (or none) (red, orange, blue, *Scoring-based*): the level of the call by its **Expected Gain** within its campaign, operator and service (the first High share, up to the Medium share, the rest). The Scoring Impact column keeps the points of the CDRs scored so far; the scoring of a campaign is not stable during it.
- **Drops** (brown: calls dropped, data tests cut off) and **Setup failures** (slate: failed before being established), *Result-based*.
- **Joining:** they follow one another on one line, each joined by **AND** or **OR** (**+** adds one, joined by OR until you choose AND; **×** removes it). AND goes first: *Time-Window Issues AND Hotspots OR High impact* takes the time-window issues of a hotspot and the High impact calls. **AND (** and **OR (** start a group of one level: *(High impact OR Medium impact) AND Cluster*.

**Calls per Queue** card (top right): a column per Priority of the Voice and Data queues (or the Unique queue) of the list shown, with the sum of the **#Calls** of its steps, in the colour of the Priority, grouped above its queue and total, and both queues in bold (*Voice + Data: 284 calls*); its note names the list and the campaigns estimated on; redrawn as you edit. **Calls outside the Voice and Data queues**, folded below, lists the **Tracked** calls by kind (Data calls no Data step takes, Ping tests, Excluded Calls) and by operator and NR Mode (*Three NSA*), those **Taken by no step** (in scope) by operator and NR Mode, and those **Out of scope** by region (`Vendor B`), by operator that is not Focus (*SA · EE*) and by NR Mode · operator pair (*SA · Three*).

**Queue order** and **Conditions**, under the table, are folded by default (click the ⓘ before their title).

**Out of Scope** card (above the steps; its **ⓘ** unfolds what it does) lists what is out of the responsibility of the team: those calls enter no queue and are not tracked, in every strategy, take no Priority and are counted apart as **Out of scope**, their Prioritization Rule saying why (*Out of scope · Vendor B*, *· No Region*, *· NSA · EE*, *· SA · Three*). The **Out of Scope** button above the filters edits the same settings, and **NQ Calls in Scope Only** leaves these calls out of the whole module (see [Filters](#filters)).

- **Regions:** `Vendor B` until the admins choose others (the others can see them). Calls without a Region are always out of scope when the calls of the workspace have Regions, shown as *No Region* beside the button.
- **Operators**, read only (chosen and grey, each with its NR Mode out of scope, a note that tells why and the reason on hover; the card links to the labels of the Operator Maps, whose **Role** chooses the Focus operators and **NR Modes** the NR Modes):
  - only the Focus operators can be in scope: the others are out in both NR Modes, with **All** (*SA · EE*, *NSA · O2*; a CDR name without a label is not a Focus operator either); without any Focus operator, every operator can be in scope;
  - an operator without a network in an NR Mode (the **NR Modes** of its label) is out of scope in that NR Mode in every module: Three has no SA, so its calls of the SA campaigns are NSA calls its NSA campaigns already have (*SA · Three*); the Operator Maps suggest it for an operator under 10 % of whose NQ calls of the SA campaigns ran on NR SA.
- **Excluded operators** of the Operator Maps (such as `Lebara`, `VF SA`, `VF VoNR`) are not listed: as in the rest of Non-Qualified Calls their calls count nowhere (no Scoring Impact, cluster, hotspot or step, nor **#Calls** and **Calls per Queue**).

**Scoring Impact, Clusters, Time-Window Issues and Hotspots**, on the right, are shared by every strategy (as are the Out of Scope card and Fill the Priority of the open calls), each choice on a line of its own below its name. They start with the configuration the NQ team recommends:

| Setting | Default | What it sets |
| --- | --- | --- |
| **High** and **Medium** shares | 50 % and 80 % | The [Scoring Impact](#scoring-impact) levels. |
| **Cluster size** and **Cluster period** | 2 calls, 0 campaigns | The calls and previous campaigns of a [cluster](#repeated-issues). |
| **Cluster distance** | 0.5 ISD (250 m in cities, 1,000 m on roads without an ISD) | How close the calls of a cluster are; the cities metres also place a call without a cell. |
| **Time window** and **Time-window distance** | 6 minutes, 0.8 ISD (500 m and 2,000 m) | The [time-window issues](#repeated-issues); with the Cluster distance they also link the failures of a hotspot. |
| **Hotspot join** | OR | How clusters and time-window issues make a hotspot. |
| **Next to analyse** | 20 | Calls listed per queue. |
| **Queues by hotspots** and **Minimum hotspot size** | Data queue, 3 failures | The queues that list hotspots, and the failures a hotspot needs. |
| **Voice queue team**, **Data queue team**, **Unique queue team** | None | The team of each queue: its waiting calls without a team go to the **My team** view of its members. |

The Queues by hotspots and the queue teams list only the queues the steps of the strategy shown use (list 2 only while Use List 2 for Final CDRs is on); the other queues keep their choice.

**Saving:**

- A change of the shares or of the cluster, hotspot and time-window settings counts **#Calls** again at once; **Save** applies it to every call at once, from the points and places already calculated.
- **Default Rules** shows the default strategy (Dual Queue (Cities first)), the default steps of the four strategies of the application and the default levels again (your strategies and names stay), and **Save** applies them.
- **Save** keeps the dialog open: the line left of its buttons says *The current configuration is saved* or *Unsaved changes* (also when the strategy shown changed, which Save applies). **Close** (or <kbd>Esc</kbd>) with unsaved changes asks: **Save**, **Discard** or **Continue Editing**.

### When it is calculated

The values are calculated in the background once the server is idle (after the indexing of the calls and the Scoring History), whenever what they depend on changes: the calls or CDRs indexed, the Scoring History, the methodologies, the Operator Maps, the Scoring Excluded Calls, the NR Mode and stage of the CDRs (a new Final CDR), the Network Inventories and cell mappings, the Serving Networks or the levels. The first time the panel opens they are calculated at once. The floating background tasks card shows the calculation, and the calls indexed since show their values once it ends.

## NQ Maps

See every filtered NQ call, and the Layer3 Logs of those that have them, on one map. The **NQ Maps** panel is below the NQ Prioritization & Queues.

- **What it draws:** every NQ call of the filters (but the Ping tests) and the [Layer3 Logs](workspace-management.md#layer3-logs) of those with a session in them; the map is read again when the filters change.
- **Like the map of a call:** it is the [map of a call](#map-of-the-call) for all of them, with the same information, cards, legend, controls and gestures (see [Tips & shortcuts](#tips-shortcuts)), without the groups of a call.
- **Its own way:** it opens where you left it (your browser keeps its place and zoom); **Fit** shows every NQ call with a log; opened larger, it takes the whole width of the window but 2 % on each side.
- **Controls above the map:** as on the map of a call, without Radius and And Group: **Colour NQ calls by** opens with *Call type* (the legend names the twelve values with most NQ calls), **Operators** with the Focus operators, and **Call types** with every type checked (**Every call type** checks them all again; at least one stays checked). A line then says how many NQ calls the filters have, how many have a log, and how many sessions.

**The cards over the map:**

- **CDR Info:**
  - **NQ calls:** diamonds where they failed, hollow without Layer3 Logs, those on one point as one mark with how many they are, drawn over the routes and the layers of the logs.
  - **Sites** of the networks that serve their operators, from zoom level 11.
  - **RSRP / SINR (from CDR samples)** of the CDRs of their campaigns in the area shown, from zoom level 13 (an even sample of 20,000 when there are more), each measure with its switch.
  - **Route** (off until switched on): **Drive of each CDR (estimated, between its tests)**, thin grey winding roads joining only its tests close in time and place (2 minutes and 2 km at most, at a speed a car can drive), below everything. The real way of each session is the route of its log.
- **LOGS Info**, with the layers of the logs, shared with the maps of the calls (a layer on in one is on in the other):
  - **Grid**, below zoom level 13: the average of the metric chosen in **Grid of** (RSRP, RSRQ, SINR or UE Tx Power of the LTE or NR PCell, SCell or neighbours; LTE PCell RSRP by default), each cell in the colour of its [Map Levels](#map-levels) level; hover it for its average, lowest value and points.
  - **Events** from zoom level 10, over the grid; **points of the layers on** from zoom level 13, in the area shown (the first 80,000), read again as the map moves; the **Route** of each session (the GPS of its log, with its direction).
- **A click** on an NQ call, a point or a route shows its values with **Open this call**, and the **Signalling timeline** of that call below the map (over the larger map), with its cursor (see [Layer3 Logs on the map](#layer3-logs-on-the-map)).

The map of each call shows the same information focused on it; **Logs of the NQ calls around**, in its LOGS Info, adds those of the NQ calls of its map, faded below its own.

### Map of a site

The **map of a site** shows the NQ calls of one site and of the sites around it.

- **Where it opens:** from a site of **Sites to review** in [Scoring & GAP Analysis](scoring-gap-analysis.md#points-lost), in a floating panel over that page, or from a link to Non-Qualified Calls (its **Open in Non-Qualified Calls** button opens the same map here).
- **How it works:** the larger map of NQ Maps centred on the site, with the same cards, legend and controls; the wheel zooms, a double-click zooms in, and <kbd>Esc</kbd> or a click outside closes it.
- **The site** is ringed where the Network Inventory places it (else where its tests were), with a dashed circle of the **Radius** (500 m to 10 km, 1 km the first time), which chooses the area whose NQ calls the table lists; the map fits it.
- **Its defaults:** **Colour NQ calls by** *Site* (the NQ calls whose CDR gives the site in burgundy); **Operators** the operator of the table only (*Focus operators only* or *Every operator* add the others); **Call types** every one checked, on the map and in the table. Your browser keeps the radius and these choices for the next site.
- **Its NQ calls** are those of the campaign of the table of the site (or of the campaigns of the scoring when the table has none); the line above the map says how many there are and how many have Layer3 Logs.

Below the map, a table lists the NQ calls, of the operators shown, **of the site** (wherever they failed) and of other sites or without a site **within the radius**: the site first, then the nearest.

- **Columns:** its mark on the map, `JOIN_ID`, site (*This site*), distance to the site, operator, call type, campaign, start, result, failure, status and root cause (decided, else that of the DT Analyzer RCA).
- **Sort:** click a column title (▲), again to reverse it (▼), a third time for the order above.
- **Show a call:** click its `JOIN_ID` for its mark, panel and **Signalling timeline**. **Open** opens it: from Scoring & GAP Analysis in a tab of its own, so the map stays open; here the map closes.
- **Copy the JOIN_IDs** copies them all, one per line; the map and the table download or copy as images.
- **Links:** `/non-qualified-calls#call=<call key>` opens that call.

## NQ Rate by Campaign and Operator

The **NQ Rate by Campaign and Operator** panel is the management view of the campaigns: for each campaign and operator, how many of **every** call of the CDRs (qualified or not) are Non-Qualified, and their share. Each call counts once, in the most recent CDR that has it (the Final before the Daily ones), so a call Completed in the Final CDR is no longer Non-Qualified.

- **Tabs:** one per service (Voice, Speech, Data; **All services** adds them up when there are several).
- **Cards:** the overall rate and the rate of each operator, named in its Operator Maps colour.
- **Heat map:** each cell shows the rate and *Non-Qualified / all calls*, in pastel tones from soft mint (none) through apricot to dusty rose (the highest rate); the Total column and row sum each campaign and operator.
- **Drill down:** a click on a cell or card filters the other panels; again to remove it.
- **Show operators out of scope** (with **NQ Calls in Scope Only** on, beside the tabs; remembered in the browser) also shows the operators that are not Focus operators (such as EE and O2), with their calls in the regions and NR Modes in scope, marked *Out of scope*: not clickable, and left out of **Overall**, the **Total in scope** column and the exports.

> [!NOTE]
> Only the **NR Mode**, **Campaign**, **Service**, **Operator** and **CDR** filters and **NQ Calls in Scope Only** apply: the other filters describe Non-Qualified Calls only, so they do not recalculate the panel, whose counts are reused until the CDRs are indexed again.

**In PowerPoint and Word** (and [Reporting](reporting.md)), after the Executive Summary: one heat map with a column per service (and **All services**) under each operator and the overall NQ rate at its top right (*Overall 0.9% · 992 NQ calls of 104,304 calls*), on one slide, or two with half the operators or campaigns each when they are many.

## Failures by Type, Technology & Serving Cell

The **Failures by Type, Technology & Serving Cell** panel shows how and where the filtered calls fail, one tab per service:

- **Failure type:** per operator and environment (City or Connecting Roads, from `G_Level_2`), the calls of each result (Failed, Dropped, Cutoff…; **Not reported** without one), as a share of every call of the operator there.
- **Technology and classification:** per operator, the technology at the failure (else of the call) against the NetCheck failure classification.
- **Serving Vendor and host network:** per operator, the calls and NQ calls on the cells of each Vendor and host network that served them, with shares and NQ rate; an NQ share well above the share of the calls is red.
- **Sites with the most Non-Qualified Calls:** per operator, the serving sites with 5 calls or more and the most NQ calls (up to 25), with host network, Vendor, city or route, calls and NQ rate.

The shares and rates divide by every call (qualified or not) of the CDR, Service, Campaign, Operator and NR Mode filters, as the NQ Rate does. The serving cell comes from the [Vendor Mapping](workspace-management.md#vendor-mapping) of the CDRs (`Vendor`, `Serving_Host_Network`, `Serving_Site_ID`). A click on a cell filters the other panels; again to remove it. PowerPoint, Word and Reporting show its tables after the NQ Rate.

## Root Cause Sources

The **Root Cause Sources** panel compares the root cause sources of the filtered calls: the **DT Analyzer RCA** first (as everywhere), then the RCA of the CDR (the **NetCheck RCA**, or the RCA named after the provider, such as the Umlaut RCA), the **Ericsson RCA** and the **Selected Cause** (the Root Category or Cause chosen by the analysts).

- **Indicators**, in three lines:
  - how many calls have a **DT Analyzer RCA** root cause, a **NetCheck RCA** classification and **Ericsson RCA** results;
  - how many have a Selected Cause and how often each RCA agrees with it (**Selected Cause ↔ DT Analyzer RCA**, **↔ NetCheck RCA**, **↔ Ericsson RCA**: the category, or the cause when the source maps to no category, proposed by the source on the catalog by its keywords);
  - how often each pair agrees (**DT Analyzer RCA ↔ NetCheck RCA**, **DT Analyzer RCA ↔ Ericsson RCA**, **NetCheck RCA ↔ Ericsson RCA**: the category, or with the DT Analyzer RCA the cause when one gives no category).
- **→ Root Domain** of each source and **Selected Root Domain**: the calls each covers in each domain, in its colour (**Not classified**: NetCheck or Ericsson values that map onto no domain).
- **→ Root Category** of each source and **Selected Root Category**: the categories on the [Root Cause Catalog](#root-cause-catalog), each with its domain in a tag (**No catalog category**: values with only a domain or nothing).
- **→ Root Cause**, four hierarchies side by side: **DT Analyzer RCA** (Root Category → Root Cause), **NetCheck RCA** (Failure Category → Subcategory), **Ericsson RCA** (Suggested Category → Cause) and **Selected Root Cause**. A category or cause filters by the source's own values (**Category · Cause** in the filters); the tag of a category, in the colour of its domain (the main one and how many more, all on hover), filters the calls of that domain for the source.
- **RCA → Selected Root Category:** a tab per RCA (DT Analyzer first) relating the categories the source maps to with those the analysts chose; the columns repeat the rows in their order (also those nobody selected) before the other selected categories, so the agreeing cells, outlined, run along the diagonal.
- A click filters by the domain, category or cause of that source; again to remove it.
- **Ericsson RCA:** the panel shows how many results are imported and how many match calls (import them from [Ericsson RCA results](#ericsson-rca-results)).

**In PowerPoint and Word**, two slides: the root domains and catalog categories of each source in two cards (the first categories that fit) under the calls each source covers; then its hierarchy (the first rows that fit) under the agreement indicators.

## Root Cause Analysis

The **Root Cause Analysis** panel shows where the filtered calls fail, by the root causes of one source chosen in its tabs:

| Tab | Root causes |
| --- | --- |
| **DT Analyzer RCA** (when the page opens) | The Root Category, Root Cause and domain the [DT Analyzer RCA](#dt-analyzer-rca) finds from the CDR. |
| **NetCheck RCA** | What the NetCheck RCA (Failure Classification, Category, Subcategory) gives each call on the [Root Cause Catalog](#root-cause-catalog), by names, keywords and the [suggestion rule](#suggestion-rule) (never the comments). |
| **Ericsson RCA** | What the [Ericsson RCA results](#ericsson-rca-results) give on the catalog: its subcategory, else its category, as the cause by name or keywords, with the category of that cause and the technology it names (*Poor Coverage LTE* → Coverage · DL coverage, *Mobility Issue NR · Missing or Late Handover NR* → Mobility · Missing or late handover; *Other LTE* matches no cause). |
| **Analysts** | The Root Category and Root Cause the analysts chose, with their domain. |

Each tab shows:

- **Indicators:** the calls, those with a root cause from the source (**Labelled** for the analysts, **With a Root Cause** for the others) and those **Not classified**.
- **By Root Domain**, **By Root Category** (the technology of the categories tells LTE, NR and 2G/3G apart) and **By Root Cause** bars, in the colour of each domain.
- **Root Domains by Call Type** (always **Voice**: Voice and Speech calls whose test name does not contain WhatsApp, formerly Classic; **WhatsApp**; **Data**) and **NSA vs SA**, each in a card under the legend they share: a donut per group with its calls in the centre, split by root domain, slices long enough showing their calls (calls and share on hover). On a narrow screen the donuts of a card stay on one row, smaller.
- **Root Domains by Technology:** a bar per technology split by root domain, with its total.
- **eNB / gNB with most calls:** the node of the last cell of each call's `Cell_ID` chain (where it ended): identities above 28 bits are NR cells (gNB = NCI / 16384, 22-bit gNodeB IDs), LTE cells give their eNB (ECI / 256), smaller ones are 2G/3G. The site ID, host network and vendor are those most of its calls have in the Network Inventories and cell mappings, found as the [place of a call](#repeated-issues); otherwise the vendor is the call's.
- **Drill down:** a click on a bar, the domain tag of a category bar, a group name, a donut slice, a domain of a technology bar or an eNB/gNB row filters the calls of the chosen source (the NSA calls of RF, the calls the Ericsson RCA puts in Coverage); again to remove it.

> [!TIP]
> **Show Not classified**, below the indicators, is unchecked by default: the charts count only the calls the source gives a root cause (shares and totals of those). Check it to add the Not classified calls. **Export PPT** and **Export Word** follow it, and the reports of [Reporting](reporting.md) have an option of their own, unchecked by default.

**In PowerPoint and Word** (and the Non-Qualified Calls section of [Reporting](reporting.md)), every source, the source in bold in the title (*Root Cause Analysis · **NetCheck RCA***) and what each slide shows in its subtitle: the tables, the donuts by call type and NSA vs SA under one legend, the bars by technology (every technology, thinner when many) and the eNB / gNB with Most Non-Qualified Calls that fit. The reports also choose whether the analysts count the calls without a root cause with their suggested one.

## Lifecycle & Phases

The **Lifecycle & Phases** panel follows the filtered calls through their follow-up.

**Indicators**, in the order a call goes through:

- **Calls:** how many are in a queue of the NQ Prioritization and how many are tracked, in no queue.
- **Automatic Status** (following the Status Rules) and **Status by Hand**.
- **In Queues:** the calls the queues list, in the statuses marked In Queue (by default the first status, Assigned and Under Analysis; the note gives each, *Not Attended 320 + Assigned 25 + Under Analysis 4*). The same number as the **In Queues** badge of every panel.
- **Not Attended** (named after the first status): the prioritized calls nobody has yet.
- **Open:** assigned or attended and not closed (Assigned plus the phase statuses).
- **Assigned:** given a team or an analyst, not attended yet.
- **Under Analysis:** attended and still in their queue; Not Attended, Assigned and Under Analysis add up to In Queues.
- **Attended:** the other prioritized calls, followed up, in any later status.
- **Stalled:** open without any change for 14 days or more, counted from today; a call leaves it as soon as it changes.
- **Closed:** in a closed status.

These cards and the pipeline count only the prioritized calls (their shares too) and add the tracked calls of each apart (*+12 tracked*), as they wait for nobody. A click on a card shows its calls (chips *Follow-up: In Queues*, *Not Attended*, *Assigned, not attended yet*, *Attended*, *Open*, *Closed*, *Stalled*).

- **NQ Call Status Pipeline:** a bar with the share of each status and a card per status (calls, share, average age): not attended, then **Open** (a frame around Assigned, Under Analysis, Analysis Finished, Under Implementation and Under Planning, its total their sum), then closed. The statuses the queues list are tagged **In Queue**. Each card shows, on one line below its figures, the [Status Rules](#status-rules) that set it (**Rule N** with the field and its values in their colours, *Rule 6 · Analysis Status · Ongoing*; *When no rule applies* on the first status). A click on a card filters by its status (on Open, *Follow-up: Open*), on a rule by the calls that meet it.
- **RCA Identification:** the calls with and without a root category or cause selected, each row drilling down.
- **Phases:** a card per list field of the **Analysis**, **Implementation** and **Planning** sections (Analysis Status, Implementation Status, Planned Status…), side by side: a bar with the share of each value and a row per value that drills down. They count only the calls in a queue (shares of those with a value, as the card tells). A field with more than 12 values (such as the Implementation Proposals) takes a row of its own across the panel, its values in columns from the most frequent. Values take the colours of [Fields & Sections](#fields-and-sections), else a palette.
- **Time in Each Status:** the average days in each status before moving, from the status history (by hand or by the rules).
- **Most Frequent Moves** between statuses.
- **Stalled Open Calls:** the open calls without changes for the longest, with status, Operator, Campaign, City and days; click one to open it.

> [!TIP]
> **Show Empty Status**, above the phase cards, is unchecked by default. Check it to add the calls without a value (**Empty**) and give the shares of every call in a queue; **Export PPT** and **Export Word** follow it, and the reports of [Reporting](reporting.md) have an option of their own, unchecked by default.

**Status Rules** opens the rules from the panel (for every user; admins and super-admins change them).

**In PowerPoint and Word** (and Reporting), as the page, each slide saying what it shows: the indicators and the pipeline (with the Open frame and the rules of each status), the **Phases** in one row (a field with more than 12 values on a slide of its own), **Time in Each Status and Most Frequent Moves**, and the **Stalled Open Calls** that fit.

## Progress View

The **Progress View**, the last panel, shows how the follow-up advances for the filtered calls in a queue. The tracked calls (Track only) wait for nobody: every statistic leaves them out and counts them apart.

- **Indicators:** **In Queues**, **Not Attended**, **Assigned**, **Under Analysis** (the three add up to In Queues) and **Attended**, as in [Lifecycle & Phases](#lifecycle-phases) (a call set back to Not Attended or Assigned is not attended again), with shares of the prioritized calls; then the average days from the call to its first follow-up (**First Follow-up**: its first change other than an assignment, or its first comment) and to its closure (**Time to Close**), the **Closure Rate**, the activity and, last, **Tracked** (the tracked calls left out, with how many are not attended and how many closed). A click on a card shows its calls (*Follow-up: In Queues*… and *Follow-up: Tracked (in no queue)*).
- **Donuts** **By Status**, **By Team**, **By Analyst** (first and last name), **By Service** and **By Result**: each legend gives the full name with count and share; hover a slice for its value, count and share.
- **Timeline** per **week** (default), **month**, **quarter** or **year** of the calls detected, attended, commented, closed and reopened (hover a period for all its values), with a table adding the moves to each open status (those to a closed status are the **Closed** column), the backlog at the end of each period of the calls in a queue (**Queue backlog**) and, apart, of the tracked calls (**Tracked backlog**, dashed grey), and the average days to close. Status changes, closures and reopenings count those by hand and those of the Status Rules (an imported analysis dated by its analysis).
- **Age** of the open calls, **workload** of each team and analyst (open, closed and total calls) and recent **activity** of each user by first and last name (informative only).
- **Drill down:** a slice or legend entry, a period (in the chart or its table: the calls detected then), an age bar (the open calls of that age) or a team or analyst row filters the calls; again to remove it.

**In PowerPoint and Word**, the period in bold in the titles (*Progress View · **Monthly***) and in the subtitles: Follow-up Overview (the cards of the page, its indicator table reading *In Queues (first status + Assigned + Under Analysis)*, *Not attended, nobody has them yet (first status)*, *Assigned, not attended yet (in a queue)*, *Attended (followed up, in any later status)*), Progress per Month, Age and Workload, Details per Month and User Activity.

## NQ Calls panel

Follow up the calls one by one. The **NQ Calls** panel lists one row per call, with these columns in this order:

- **Start time** (to the minute; hover it for the seconds) and **service** (for a Speech call, also its Non-Qualified samples).
- **Operator** and **Vendor**, **Region** and **Cluster**, **City** and **Campaign**, **test** and **technology**.
- **Result**, with the failure classification and category (hover it for its subcategory and comment) and the CDR version badge.
- **The RCA fields chosen as columns** (none by default). Ericsson RCA Suggested Cause and NetCheck RCA Suggested Cause show in italics the suggested category of their source, named below it, when the source gives no cause (as most Auto RCA results of the Ericsson RCA).
- **Root Category** and **Root Cause**.
- **The other fields chosen as columns** (by default Analysis Status and Implementation Status).
- **Global Status**, **team**, **analyst** and **comments** (how many, and the latest one; click to read the thread or add one). **›** beside them opens the call.

**Join ID** (**Call ID** when the CDRs also bring the IDs of the provider's tools), centred in the title bar, finds calls by their IDs:

- **Which IDs:** their `JOIN_ID`, or the IDs of the provider: with NetCheck CDRs, the `Session_ID_A` and `Session_ID_B` of a voice or Speech call and the `Test_ID` and `Session_id` of a data test, as NetCheck CloudNM identifies them.
- **How:** one or more, separated by commas, spaces or lines (any case), list the calls with exactly those IDs. Kept with your selection and shown among the active filters.
- **Recent JOIN_IDs:** below it, as below **Go to a JOIN_ID…** (**Go to a call ID…**) of an open call, a list offers the 10 last searched in either box (in your browser, per workspace), the latest first, narrowed while typing; here a choice replaces the JOIN_ID being typed.

### Follow up the calls

1. Narrow the calls with the [Filters](#filters), **Join ID** or the funnel of a column header.
2. Change the **Status**, **Team**, **Analyst**, **Root Category** and **Root Cause** of a call in its row, or accept its recommended root cause.
3. Click a row to open the call, fill the fields of its sections and comment it (see [Call details and activity](#call-details-and-activity)).
4. Select several rows to change them at once (see [Bulk changes](#bulk-changes)).

**Changing values in the row** (`user-editor`, `admin` and `super-admin`; `user-viewer` accounts see them read-only):

- **Lists:** each value is a pill in its colour (that of its status, team or root domain: a root category filled with it, a root cause outlined), with a search box for long lists. The status, team, analyst and root cause lists widen with the window.
- **List fields of the analysts** always have the search box; a value the list lacks is offered as **+ Add “…”**, which adds it to the field and chooses it.
- **Other list and Yes / No fields** of the analysts shown in the table are chosen in the row too; their other fields are filled in the call. Fields from the CDR, the Ericsson RCA or derived from the call are read only.
- **Root Category, Root Cause and Root Technology:** chosen from lists searched by name, the current value ticked, in the order of the [Root Cause Catalog](#root-cause-catalog) (choosing a cause gives its category). While a call has none, its [recommendation](#root-cause-recommendation) shows below them, small, with the RCA it comes from (every source in its tooltip) and a dot for its confidence (green high, amber medium, grey low); a click accepts it.

**Analysts** show by the first and last name of their account (else its username), sorted by it, in the table, the call, the bulk bar, the Analyst filter and the Progress View. The lists start with the default users of the application (super, admin and demo), tagged **default user**, then a line. An analyst without account (brought by the [Previous NQ Analyses](#previous-nq-analyses) until [Link Analysts to Accounts](#link-analysts-to-accounts) links it) shows in italics in a dashed pill, tagged **No account**: it counts in the filters and statistics, but only user accounts can be chosen.

> [!IMPORTANT]
> **Choosing a status sets it by hand.** The list then offers **↺ Back to automatic** to give it back to the Status Rules. Below the status, each row tells whether it is **Auto** or **By hand** and when its follow-up last changed and by whom (hover for the exact time).

### Columns

Choose and arrange the columns of the table.

- **Colours:** every header is topped with the colour of its group, as in Excel: the call (and the optional and CDR columns) that of the call, each field that of its section, and the follow-up columns (team, analyst, root category and cause, status, comments) that of the section of their follow-up field.
- **Fit:** the default columns fit screens of 1600 px and wider. Long values wrap on two lines or are shortened (whole on hover), and the time goes below the date. Related values share a column, one below the other; the **Prioritization** and the **Priority** share one when both are shown (Priority below, chosen in the row), each name of the header sorting and filtering its own field.
- **Default columns of a new workspace:** after the root category and cause, the Prioritization with the Priority, the Repeated Issue, the Scoring Points Lost, the Analysis Status and the Implementation Status. The Scoring Impact and the other fields are added with **Columns**.
- **Scroll position:** reloading the page returns to it.

**Order of the columns:** drag a header onto another to move it before or after it, in your own [layout](#table-layouts); columns added later take their default place. **Default column order**, shown while the order differs, puts them back.

**Order of the calls:**

- **By default:** by **Priority** (P1 first, in the order of the Priority values; the one set by hand, else the one the NQ Prioritization gives; calls without one last), then **Scoring Points Lost** (most first), then the most recent.
- **By a column:** click a header name to sort, again to reverse; **Default order**, shown while a column sorts, brings the default back.
- **Pages:** 10 (default), 25, 50 or 100 rows in **Rows per page**, also with All panels.

**Filter a column:** the funnel beside a header name opens that field's values below the header: search, tick them (**Select All / None** acts on the values shown; root categories and causes grouped by domain) and **Apply**. It is the same selection as the Filters panel and its chip; the funnel is filled while the field is filtered.

**Columns** (a button after **Default column order**, for every user) chooses the columns of your own [layout](#table-layouts), only for you:

- **Optional columns** (after Result / Failure; Session Type (CDR) before Test / Technology): `JOIN_ID`, NR Mode, Cell ID, Direction, Session Type (CDR) (the CDR's `Session_Type`), End Time, CDR and **Layer3 Logs** (the UEs of the call with a session in the [Layer3 Logs](workspace-management.md#layer3-logs), found by its `JOIN_ID`: `A, B` for a voice call, `Data` for a data test, empty without a log).
- **Fields of the Analysis Center**, by section: **Table** (the follow-up fields always have theirs) and **Excel**.
- **CDR columns** (such as `Cellname_A`, `Region_A`, `Auto_RCA_Category_A`), with the value of the CDR version shown: to the **Table** (up to 12, then also to Excel) or to **Excel** only (up to 100 more). A CDR column no layout showed before is added to the calls in the background (see [Indexing](#indexing)).
- **Default Columns** returns to the columns of a new workspace (no optional or CDR columns; the fields of the [default catalog](#default-catalog) as above in the table, every field in Excel); **Copy Workspace Layout** to the columns, Excel and order of the workspace layout; **Save** applies them to your layout.

**Filters of the optional columns:** each sorts the table and has its filter. **Region** and **Cluster** use those of the Filters panel; **`JOIN_ID`, NR Mode, Cell ID, Direction, Session Type, End Time, CDR** (which chooses CDRs) **and Layer3 Logs** (**Empty**: calls without a log) add theirs under **Additional Columns Filters**; the CDR columns filter from their header only; each offers **Empty**. The Filters panel shows the **General Filters**, then the **NQ Analysis Fields Filters** and the **Additional Columns Filters**.

### Table layouts

The columns of the table, those of the Excel export and their order make a **layout**. **Layout**, a switch beside **Columns**, shows **Mine** (left) or **Workspace** (right); click the switch or either name.

| Layout | Who sees it | Who changes it |
| --- | --- | --- |
| **Mine** | Only you. The first time it is a copy of the workspace layout. | You, whatever your role: dragging a header, **Columns** and **Default column order**. |
| **Workspace** | Every user who has not chosen Mine. | Admins and super-admins: **Save for the workspace**, shown with Mine, makes their layout that of the workspace once confirmed. |

- A change made while the workspace layout is shown makes it your own layout (confirming the replacement when you had one).
- Switching keeps both, and your choice is kept with the workspace, so every browser shows you the same layout.
- **Export Excel** exports the fields and CDR columns of the layout you see, the fields in catalog order.
- A field added to the catalog after you saved your layout follows the workspace layout until you choose it in **Columns**.

### Bulk changes

Change many calls at once.

1. Select rows with their checkboxes, or the whole page with the header checkbox.
2. In the bar above the table, set the status (or **↺ Back to automatic**), team, analyst, root category, root cause, or a list or Yes / No field of the analysts (**Set field…**) of all of them.
3. Apply more changes: the selection stays. **Clear selection** empties it.

- **The bar** shows the number of calls over the row (it does not move the table) and stays at the top of the window while you scroll.
- **Accept recommendations** gives the selected calls without a root category and cause their recommended ones.

## Call details and activity

Analyse one call: click a row to open its details beside the table.

**The header of the call:**

- **The call:** service, result, CDR version, Operator, Campaign, time and place.
- **`JOIN_ID`** and **the IDs of the call in the provider's tools** (— without them: `Session_ID_A` / `Session_ID_B` of a NetCheck voice or Speech call, `Test_ID` / `Session_id` of a data test, as in NetCheck CloudNM), each with a copy button.
- **Layer3 Logs:** the UEs of the call with a session in the [Layer3 Logs](workspace-management.md#layer3-logs).
- **Groups:** its hotspot, clusters and time-window issue (see below).
- **‹** and **›:** the previous and next call of the list, with the position (12 of 1,268), turning the pages of the table. When the filters change while a call is open, the table shows the page that holds it.
- **Go to a JOIN_ID…:** opens the call of a JOIN_ID pasted there, whatever the filters. It and **‹** / **›** ask first when there are [changes not saved](#tabs-of-the-call).
- **Map:** shows the [map of the call](#map-of-the-call).

**Groups of the call:** its hotspot, its clusters, then its time-window issue, of 2 calls or more, on a row across the header (on more rows when they do not fit), each a card in the colour of its group on the map (hotspot orange, cluster green, time window blue). A call is in one of each at most; see [Repeated issues](#repeated-issues).

- **Card:** what it is, its NR Mode and ID (*Hotspot SA H-0C1BCE*); the hotspot card is wider; hover a card for what it groups.
- **Sites:** where its calls failed, the most first: *2 sites:* / *11 at Site 1154 (Vodafone)* / *4 at Site 3522 (Vodafone)*, or *At Site 1154 (Vodafone)* when all failed there; the first three, all on hover.
- **Pills:** how far its calls reach (hotspot, cluster: *within 310 m*, the circle on the map), how long it lasted (hotspot, time window: *within 2 h 46 min*) and its period (*24 Sep 14:42–26 Sep 10:14*); its size over its top right corner (*17 calls*).
- **Filter by a group:** a click on a card filters the list by it after you confirm, replacing any other group filtered; the card is tinted and ringed with a *Filtering the list* tab. A click on it again removes the filter after you confirm.

**Scrolling:** the wheel scrolls only the details of the call. On a short screen (a laptop, or a large browser zoom) the whole panel scrolls, its tabs staying at the top; on a large screen the header and the follow-up fields stay and only the tab scrolls.

**Analyst fields**, across the bottom of the header, counts the fields the analysts fill that have a value: Team, Analyst, Reviewer, Root Category and Root Cause of the header and every field of the analysts of the tabs, with unsaved changes; not the Initial Classification of the RCA tab (**Analyst (Optional)**), the NQ Call Status or the Priority.

- **Complete:** a full bar with *Complete* and a gold trophy (**All fields filled**, popping in as the last one is filled); hover it for the empty ones.
- **Header** and **Tabs** (above the tabs, beside **Only the fields the analysts fill**) count those of the header and of every tab (dark green, with a check once complete), as each tab counts its own.

**The follow-up fields**, below the header, in this order:

1. **NQ Call Status** (**Auto** or **By hand**) and **Priority** (from the [NQ Prioritization](#nq-prioritization), **Auto**, until somebody chooses another, **By hand**).
2. **Team**, **Analyst** and **Reviewer**.
3. **The fields of the analysts added to the General section**, saved as soon as they change. The **Unique ID** of the Previous NQ Analyses is not shown, but kept and exported.
4. **Root Category** and **Root Cause**, with the domain they give the call, and the recommendation while it has none.
5. **Prioritization Info:** the fields *From the NQ Prioritization*, read only, in the order of Fields & Sections (Prioritization, Prioritization Rule, Prioritization Queue, Expected Gain, Scoring Impact, Scoring Points Lost, Scoring KPIs Lost, then Repeated Issue, Repetitions, Repeated Campaigns and Repetition Place on a row of their own); the group IDs are in the Groups. The **Prioritization Rule** (here and in the table) reads what its step takes (*SA Voice · Medium impact*) with tags of its list (**WEEKLY** for list 1, **FINAL** for list 2) and number (**STEP 3**).
6. **Phases:** a card per phase in the colour of its section, opening its tab: **Map Analysis** (where it failed, *Site 70086 (Vodafone)*, or *No position*), **RCA Identification** (the root category, *Recommended* or *Not started*), **Failure Details** (*Not started*, *In progress* or *Completed*, with the fields filled), and **Analysis**, **Implementation**, **Planning** (the first list field of each).
7. **Who changed the call last.**

**Where each value comes from:** every field shows its source below its name (beside it in the header), a dot of the colour of the [Filters](#filters) cards and the name of the source; its value takes that palette.

| Mark | Colour | Values |
| --- | --- | --- |
| **CDR** | Blue | The values of the CDR. |
| **DT Analyzer RCA**, **NetCheck RCA**, **Ericsson RCA** | Amber | What each RCA found (their fields drop the name of the RCA). |
| **DT Analyzer** | Violet | What the tool fills: the status of the Status Rules, and **Prioritization Info** (marked once). |
| **Analyst** | Green | What the analysts fill, also the fields the tool fills or proposes a value for (still their decision). Team, Analyst, Reviewer, Root Category · Root Cause and the Final Root Cause Decision are green; the NQ Call Status and the Priority keep the colour of their value. |
| **Analyst (Suggested)** | Green | The CDR proposes a value for the field of that call (such as Serving Cell when Failure); hover it for the value. |

- **Still to fill:** the fields of the analysts have a green pencil before their name and a dashed green border while empty.
- **Source**, above the tabs, lists the marks, each kind in a dashed frame of its colour.
- **Only the fields the analysts fill** leaves only their fields in the tabs, hiding the subpanels left empty, such as those of the RCA sources (remembered in the browser).

### Tabs of the call

The tabs follow the steps of the analysis, on one line below the follow-up fields: raised buttons in the colour of their section, numbered and joined by a line (**1 Activity**, **2 Map Analysis**, **3 RCA**, **4 Failure Details**, **5 Analysis**, **6 Implementation & Planning**), then **Call Details** after a separator, with an *i* (a reference, not a step). The open tab is tinted, its number filled. Each counts the fields of the analysts filled (*filled/total*, on hover); RCA shows ✓ once a root category or cause is chosen and ★ while a recommendation waits. Lists and Yes / No fields use the same coloured lists as the table.

| Tab | Content |
| --- | --- |
| **Activity** (General section) | The **Call Activity Log**: the comments with author (first and last name) and time, and every change of status, team, analyst, root category, root cause or field with the previous and new values (a status the rules moved reads *The status followed the Status Rules…* after the change that moved it); below it, the comment box. |
| **Map Analysis** | The [map of the call](#map-of-the-call). |
| **RCA** | The **Analysts** subpanel, then the **Values of the RCA sources** (see below). |
| **Failure Details**, **Analysis**, **Implementation & Planning** | The fields of each section (Implementation and Planning in their own subpanels), described on hover. Failure Details starts with **Map of the call** (the map larger) and shows the **Last Cell ID** (where the call ended) and the CDR **Failure Comment**. An empty field that proposes a CDR value (Failure Latitude and Longitude…) offers **Use the CDR value**; fields from the CDR, the RCAs or derived are read only. |
| **Call Details** (grey) | **Map of the call**, the CDRs that contain the call (when several), its main fields (`JOIN_ID`, root domain, category and cause), its location (opened in OpenStreetMap) and CDR, then every non-empty field of the original CDR row, filtered by name or value. For a Speech call it starts with its **Speech Samples**: open one to follow it up on its own (status, team, analyst, root cause, fields and comments); **‹ Back to the call** returns. |

**The RCA tab:**

- **Analysts** subpanel:
  - **Initial Classification:** fields such as Initial Root Category and Initial Root Cause, saved with **Save RCA**.
  - **Final Root Cause Decision:** the selected Root Category and Root Cause, and the [recommendation](#root-cause-recommendation) with its confidence and sources (**Accept** sets it).
  - **A card per source** (the DT Analyzer RCA rule first, then NetCheck category → subcategory, Ericsson RCA category → cause) with the catalog values it maps to and **Use as Final Decision** (green, at its foot). **See the evidence ↓**, just above the footer divider (aligned across the cards), scrolls to its evidence in the subpanel of the source and highlights it.
- **Values of the RCA sources:** a subpanel per source (**DT Analyzer RCA**, **NetCheck RCA**, **Ericsson RCA**, in the order of Fields & Sections), four read-only values per row (each Ericsson RCA pair on one row), last the other columns of the Ericsson RCA file of the call, named in its colour.

**Comment a call** (Activity tab): write in the box (it reaches the bottom of the panel when there is room) and press **Add Comment**, or <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Enter</kbd>, to share it with every user of the workspace. Up to 5000 characters, written as they read, in the Markdown of the [Ticket Center](ticket-center.md#writing-descriptions-and-comments) (keys in [Tips & shortcuts](#tips-shortcuts)); the table shows the latest one without its Markdown.

**Saving:** **Save** in any tab saves the changed fields of every tab together; the sections tell how many changes are unsaved. Unsaved changes are never lost without asking: leaving a tab with changes (or with a comment not posted or being edited), closing the call (**×**, <kbd>Esc</kbd>, a click outside) or going to another call (**‹**, **›**, **Go to a JOIN_ID…**, a Speech sample) asks what is pending: **Save** (also posts the comment) and go on, **Discard** and go on, or **Continue Editing** (or <kbd>Esc</kbd>).

> [!TIP]
> **Long texts read as bullets, also while edited.** The Description, the Findings, the Proposed Measure and the other long texts (also those from the CDR or the Ericsson RCA) are Markdown, as in [Ticket Center](ticket-center.md#writing-descriptions-and-comments).

- **Bullets:** each line is a bullet, nested as deep as it is indented (a dot, a circle, a square).
- **Titles:** a short line not indented that ends with a colon, or is followed by a list (*Problem Statement:*), titles the lines below it.
- **Dividers:** a line of dashes (*------Text------*) is a divider with its text.
- **More:** numbered lists at any level, headings, bold, italic, cards (`> [!TIP]`) and code.
- **Editing:** a click places the caret, the text staying as it reads; with the focus its toolbar shows and it grows (the Description and the Findings the tallest; the Proposed Measure two lines). <kbd>Tab</kbd> nests a line and <kbd>Enter</kbd> goes on at its level. An empty text shows a grey guide until you type.

### Map of the call

See where a call failed and what was around it, on OpenStreetMap.

- **Open it:** the **Map Analysis** step, or **Map** in the header, shows the map in place of the follow-up fields (taking their height); **Map** again returns to the tab shown before. **Map of the call** in Failure Details and Call Details opens it larger at once.
- **It follows the call shown:** **‹**, **›**, **Go to a JOIN_ID…** and **Open** of a call around it show the map of that call.
- **Gestures:** as the maps of [Network Insights](network-insights.md#coverage-and-interference-maps): drag, <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + wheel to zoom (the wheel alone scrolls the call, and a note says how to zoom), <kbd>Alt</kbd>/<kbd>Option</kbd> + drag to measure, double-click to open it larger; all of them in [Tips & shortcuts](#tips-shortcuts). **Fit** shows the whole radius, the shapes of its groups and every NQ call of its groups and site, wherever it is.
- **The larger map:** its call type as a pill (*Voice*, *WhatsApp*, *Data*, *Ping*) above the title (operator, campaign, `JOIN_ID`), also in the title of its images; the wheel alone zooms; the panel of the element chosen floats on the right, off the cards, where you drag it (it stays for the next element; on the map in the call it is below the map).
- **Elevation profile** (the ruler), as Google Earth shows it, over the bottom of the map: the elevation along the distance, start and end, lowest and highest point, climb, descent and steepest slope; hover it for each point, marked on the map; a click on its header folds it to its figures. The elevation comes from the Terrain Tiles of AWS Open Data.

**The panel of the element chosen** (a click; hovering reads it):

| Element | What its panel shows |
| --- | --- |
| **The call** | Its call type, operator, campaign, the sites where it started and ended, then its cells. |
| **A Non-Qualified Call** | Its call type, operator, campaign, how it relates to the call (its groups, a cluster or time-window issue of its hotspot, whether it joins a cluster to a time-window issue), its distance, the sites where it started and ended (of its first and last cells; for its start, else the serving site of the CDR), its cells and **Open this call**. |
| **A site** | Its operator (as the Operator Maps name the operator of its network) and vendor, its role in the call and every cell (technology, band, channel, PCI, azimuth, beamwidth, state, role). |
| **A cell** (hover its sector) | Its operator and vendor, role in the call, site, identity, technology and band, channel, PCI, azimuth, beamwidth, height and state; the same on NQ Maps. |
| **A test** | The campaign and CDR it comes from and its RSRP and SINR. |

The cells of a call are its **Start cell** and **End cell** (its **Serving cell** when one served all of it), its **Handover cells** on a line of their own and the NR cell of an NSA call. Those of the operator of the call are named by inventory name (*70002-L3 (LTE B3)*), the others by technology, band and identity (*LTE B20 · 30001001*, *GSM 900 · LAC 876 · CI 37171*).

**Above the map** (and the larger map), on one line; your choices but the radius are kept in your browser for the next calls:

| Control | What it does |
| --- | --- |
| **Radius** | 500 m to 10 km: the area. A call opens with the radius holding every NQ call of its hotspot and cluster (rounded up to 100 m, *(groups)* in the list), else 1 km; it holds while the call stays open. |
| **Colour NQ calls by** | *Site* (the default: the site their CDR gives, each in its colour, the site of the call in burgundy; the legend names the twelve sites with most NQ calls, that of the call first), *Call type*, *Root cause domain* (decided, else that of the DT Analyzer RCA), *Campaign* or *Operator* (in its [Operator Maps](workspace-config.md#operator-maps) colour). |
| **And Group** | When the call is of a group: an outline over that colour, in the shape of the NQ call, for each group of the call it is of: its **cluster** green innermost, its **time-window issue** blue outside it (never its hotspot, which every NQ call of its groups is of). Each is that of the call alone (the calls the counter card counts *in its cluster* and *in its time window*), unless another group filters the list. |
| **Operators** | Its operator only, the Focus operators (**Focus operators only**, the default when the workspace has some; its tooltip names them) or every operator. |
| **Call types** | The call types of the NQ calls around, every one checked by default: only those checked are drawn, counted and listed; the call itself always. |
| **Map** | The map under the layers: *OpenStreetMap (original)*, *OpenStreetMap in grey (light)* (the default, a white veil so the samples, events and calls stand out), *Plain (no labels)*, *Terrain (elevation)* (contour lines and hill shading, OpenTopoMap), *Topographic*, *Satellite* and *Dark* (Esri); the same on every map of the page. |

**This call:**

- **Pin:** where it failed (where it ended), taller than its NQ call mark with every outline of its groups, so it is seen first. The radius around it is dashed.
- **Its way (estimated)** (switch **Way of the call (estimated)**, section Route of **CDR Info**): a winding road in its colour, with a white edge, a dashed white centre line and an arrow, **START** (green) and **END** (red) beside its ends. Its bends are a sketch; hover it for how far it went, how long it lasted and which way.
  - **A Voice call** gives where it started (a green dot) and ended: its road joins them.
  - **A Data test** gives only where it started and its `Test_Distance`: its pin marks the start (*This test (where it started; it failed on its way)*) and its road is simulated, those metres along the way of its car (towards its next tests, else on from the one before, straight on past them), the arrow where it ended. When the way of its car is unknown, a dashed circle of that distance marks the zone.
- **The drive of its car (estimated)** (switch **Drive of its car (estimated, 15 min before and after)**): grey roads from test to test with arrows, through the tests of **Its drive** (below the map) a car could drive one after the other (up to about 145 km/h), leaving out another car measuring nearby. It joins the road of the call (from the test before to where it started, from where it ended to the next test); hover a road for from where to where, how long before or after and how far.

**Cells of the call:**

- **Its Cell ID trace, in order:** *Served the start*, *Handover*, *Served the end* or *Served the whole call*, with the PCI of the CDR. A cell the trace repeats in a row (a new TAC, or a moment on a cell without identity it came back from) is one cell, never a handover.
- **Placed at its site** of the Network Inventory: the cell of a network serving its operator ([Serving Networks](workspace-config.md#serving-networks), its own first) nearest to where it served the call, within the distance of the Serving Networks (30 km by default).
- **Far cells:** else, farther, the cell with the PCI and channel of the CDR (an identity alone farther may be another cell with that number, while a high mast can serve high ground from much farther). Its label says how far (*N54810231 (LTE B20) · 36.5 km away*) and the Diagnosis judges its serving distance. **Cells of the call** and its tooltips say why it is the real one: its ECI (NCI), PCI and EARFCN (NR-ARFCN) are those of the CDR and of the inventory, and, with Layer3 Logs, the logs measured that PCI and channel too.
- **Lines:** solid, from where the call started to its start cell (green) and from where it failed to its end cell, or that of the whole call (red).
- **Handover arrows:** cyan, from the cell before to the cell after, numbered with the order of that cell (as **Cells of the call** and the site badges): sector to sector when sectors are shown (zoom 14, **Sites** on), else from the side of each site where its cell points; arrows back and forth go side by side (hover the number for the cells and sites). Every line has a white edge, and two lines with the same ends go side by side.
- **Where each handover took place (estimated)** (switch **Handovers on its way (estimated)**, section Route): the CDR does not record it, so a dashed ring numbered as its arrow marks it beside the road (on its left, away from the arrows of the logs), and on the real way of the UE when its log draws it. Estimated by the time spent on each band (the RAT timeline of the A side of a Voice call, the PCell of a Data test; the cells of a band sharing its time at an even speed), else spread evenly; on a Data test along its simulated way, none without one.
- **Sites of the cells:** a badge with the order on the site and its sector in the colour of its role at every zoom; the start and end cells named at the tip of their sector. The site where it started is ringed green and where it ended (failed) red, both when one site served all of it.
- **Cells not in the inventory** (2G and 3G cells, or a cell missing within that distance): a dashed ring marks the nearest site of those networks to where it started or failed, an estimate the legend names as such, and a note above the map names the cells as the CDR gives them.
- **NR leg (by PCI):** an NSA call of a Data CDR adds the NR cell with its NR PCI (and NR-ARFCN) on the site of its LTE anchor, else the nearest within 5 km.
- **Sites around:** the inventory sites of the networks serving its operator within the radius (and those of its cells wherever they are), as triangles in the colour of their vendor ([Vendor Maps](workspace-config.md#vendor-maps)): sectors (azimuth, beamwidth) from zoom 14, Site ID from 15 (the start and end sites at every level). A dashed sector marks a cell with the PCI and channel of a cell of the call (a PCI collision or confusion to check).

**NQ calls around it**, as stars (larger than on NQ Maps; the diamonds are the PCIs and signalling of the logs), of their latest version:

- **Which ones:** those of its [groups](#nq-hotspots-clustered-time-window-issues) and of the other clusters and time-window issues of its hotspot; those of its operator at its **site**, always and wherever they are (the site counts every campaign, NR Mode and call type, while a hotspot and a time-window issue keep to its campaign and NR Mode, and a cluster to its NR Mode and the campaigns of the Cluster period, without Ping tests); and the others of the **Operators** chosen, from the campaigns of **Campaigns** (see the cards).
- **Left out:** Ping tests, and everything of the other NR Mode (its NQ calls and samples).
- **Stacked calls:** one mark with how many (*×11*), in the colour of the most related one; hover it for *At this point: N NQ calls*.
- **One group filtering the list** (by its card in the header or its ID in the panel): the map shows that group alone with its shape; the calls of its other groups, their shapes and the hotspot zone leave it, and the legend names the group.

**Groups and hotspot zone** (legend: **Groups of the call**), drawn as the Groups slide of the presentation:

- **Clusters:** a green circle around the NQ calls of each cluster (lighter than the green of the start site). **Time-window issues:** a blue ellipse along their calls.
- **Its own groups** are whole (a cluster with the campaigns of its Cluster period) and bolder; those of the other calls of its hotspot dashed. Each shape is the smallest that holds its calls, so every NQ call of its groups is inside one (a call of its hotspot in neither takes a circle of the whole hotspot).
- **Time-window paths:** a dashed line joins the failures of each time-window issue in order, numbered by a badge (1, 2, 3…): blue for its own, a colour of its own for each other one of its hotspot.
- **Hotspot:** the orange zone they make together, outlined by a wide orange edge between two white ones. The lines of the groups and the zone go over the sectors.
- **Counter card** (bottom left): the **NQ calls on the map** (the call too) and how many are **in its hotspot**, **in its cluster** and **in its time window**: their envelope with the **Hotspot join** OR, where its clusters and time-window issues meet with AND.
- **Legend:** its own shapes with calls and size (*Its cluster: 5 NQ calls within 134 m*, *Its time window: 4 NQ calls along 616 m*), the other calls of its hotspot and the zone.

**The cards over the map**, side by side over the top left (one below the other on a narrow map), switch what it shows by where it comes from. Each has a switch in its header for all of it and how many each layer shows:

- **CDR Info:**
  - **Campaigns**, at its top, for everything drawn from the CDRs (its NQ calls and their list, the samples, **Radio around the call**, the Diagnosis hints, the drive of its car and **Its drive**): *Selected campaigns* (default: the CDRs of the campaigns of the Campaign filter, all while none is chosen) or *Call campaign*. Always of the NR Mode of the call, Voice, Speech and Data CDRs together; the Diagnosis hints and the Decisions at its place count the NQ calls of every campaign.
  - **RSRP / SINR (from CDR samples):** the tests around, completed or not, with their LTE RSRP, LTE SINR, NR RSRP or NR SINR (the average of the test) in the [Map Levels](#map-levels), or their result; hidden at first, each measure with its switch and how many tests have it, in the shapes of the KMZ layers (circle RSRP, inverted triangle SINR, square result; NR with a black dot), several side by side at each test. The legend titles each with its unit (*LTE RSRP (dBm)*).
  - **NQ calls**, and its groups: **Hotspot zone**, **Clusters**, **Time windows** and **Time-window paths** (each switching its shapes and outlines; the browser remembers Time-window paths).
  - **Sites** (when a Network Inventory places them): **Sites**; **Start and end cells** (the solid lines, and the dotted one to the NR cell of an NSA call); **Cell path** (cells and handover arrows).
  - **Route:** its way, its handovers and the drive of its car.
- **LOGS Info:** the layers of its [Layer3 Logs](#layer3-logs-on-the-map), when it has some.
- **Behaviour:** folded each time a map opens; a click on the header folds or unfolds it, a click outside folds it; sections fold with a click on their header (remembered). Once unfolded they float: move, resize, **Restore**, pin (see [Tips & shortcuts](#tips-shortcuts)).
- **Legend** (bottom right), folded: it unfolds upwards over the map, below the zoom buttons, scrolling when longer, and is in the images while unfolded. It shows only what the map shows (a call served by one cell has no start line nor handover arrow), in boxes **CDR Info** and **LOGS Info** that open wide in a row below it (CDR Info in three columns: RSRP / SINR, Sites & Cells with Route, and NQ calls).

#### Layer3 Logs on the map

Follow the real way and the radio of the UE of a call from its Layer3 Logs.

A call with a session in the [Layer3 Logs](workspace-management.md#layer3-logs) of the workspace (found by its `JOIN_ID`; **Layer3 Logs** in its header names the UEs) shows on its map every layer of the KMZ files the NQ team opened in Google Earth, read from the imported logs (no KMZ file is imported). Checked against the 2,382 KMZ files of UK Q3 2026, every layer of every file has the same points by channel and PCI.

- **Its real way:** the GPS positions of the log replace the sketch of its way, a road in the colour of the logs from **START** to **END** of the log (the pin stays where the CDR says it failed; the green start dot and the handover rings stay, the rings along that way by their estimated time). The map fits the whole way. With the route of the logs off, the way of the CDR shows again.
- **LOGS Info** (beside CDR Info, and in its images) lists the layers by section, each with its switch, marker and points; its header switch shows or hides them all (routes too). Unfolded it is wider: Route, Signalling and RAN side by side, then a matrix per technology of the logs (LTE, NR; side by side when wide enough):
  - **Signalling timeline**, a switch at its top, shows or hides the timeline (below).
  - **Route:** **Route (GPS)** and **Direction of travel** (arrows on the right of the road, from its positions).
  - **Signalling:** **Events** (4G, 5G EN-DC, 5G NR, Other) and **L3 Signaling** (LTE-NAS, LTE-RRC, NR-NAS, NR-RRC, SIP, Other).
  - **LTE** and **NR:** a row per measure (EARFCN or NRARFCN, PCI, RSRP, RSRQ, SINR, UE Tx Power) and a column per kind of cell — **PCell**, **SCell**, **NCell** (neighbours) and, in NR, **LTE NCell** (LTE neighbours reported on NR) — each with its switch, points and **+**, a dash where there is no such measure (UE Tx Power is of the PCell alone; neighbours have no SINR). Both matrices share the columns with points in either, in that order and width.
  - **RAN:** **RAN Configuration** (every serving point by LTE, 5G EN-DC, 5G SA, GSM or UNKNOWN).
  - **+** unfolds a layer by channel (as the KMZ files name it, *EARFCN 1363 (B3, 1821.3 MHz)*, *NRARFCN 628032 (n78, 3420.48 MHz)*), each with its switch and its PCIs as chips, to follow one carrier or cell.
  - **Both**, **UE A** or **UE B** chooses the session of a voice call shown.
  - **Hide all** switches every layer off; **Default layers** returns to the route, the LTE and NR PCell RSRP (as the KMZ files open) and the events. The card keeps its layers for the next calls.
  - **Logs of the NQ calls around**, at its bottom, adds the logs of the other NQ calls of the map (its groups and area) with the same layers, faded below its own, as [NQ Maps](#nq-maps) shows them.
- **Markers** are those of the KMZ legend, NR points with a black dot: circle RSRP, triangle RSRQ, inverted triangle SINR, pentagon UE Tx Power, square a channel and the RAN Configuration, diamond a PCI and the L3 messages, hexagon an event, arrow the direction.
- **Colours:** RSRP, RSRQ, SINR and UE Tx Power take the [Map Levels](#map-levels), RSRP and SINR shared with the CDR samples in one legend (its **LOGS Info** box, each measure with its unit, *RSRQ (dB)*). A channel or a PCI keeps its colour on every map.
- **Points:** hover one for its values (time, UE, RAN Configuration, channel, PCI, RSRP, RSRQ, SINR, UE Tx Power, ECI or NCI; name, group and summary of an event; layer, direction and SIP response of an L3 message); a click shows them below the map, where **All the fields of this record** reads every value of the log record (never the IMSI of the test SIM).

**Signalling timeline**, below the map (and in its images; floating over the bottom of the larger map, below the elevation profile, the unfolded cards ending above these panels), for each UE shown:

- **RSRP** of its LTE PCell (blue) and NR PCell (purple, dashed) over its session, against the colour bands of the legend, with the seconds from its first record.
- **Messages:** its **Events**, **RRC**, **NAS** and **SIP** messages in the colours of their groups; failures, re-establishments, rejects, releases and SIP errors (4xx to 6xx) larger and ringed in red, and a dashed red line where the session ended with its status (*Failed*, *Dropped*, *Cutoff*).
- **Hover** a point for what it is and a ring at its place; **click** it to centre the map on it and show its values. The header folds it, its **×** hides it (the LOGS Info switch shows it again).
- **Cursor:** dragged along the timeline (or moved with the keys in [Tips & shortcuts](#tips-shortcuts)), it shows where each UE was at that moment, heading where it went, with its events and messages of the last 3 seconds ringed (the latest named); the map follows the UE, and above the chart the time, the LTE and NR PCell RSRP and its latest messages show.

**Below the map:**

- **This call:** its result, failure, phase, technology, times and serving site (of the cell that served its end, else its start), its cells in order with their site and distance (a click, or <kbd>Enter</kbd>, centres the map on the site), the radio of the call (Min, Avg and Max of each RSRP, RSRQ, SINR, transmit power, BLER, CQI… of the CDR row) and its other cell, handover and serving fields.
- **Non-Qualified Calls around:** those of its hotspot, cluster and time-window issue, at its site, and the others (of **Campaigns**), with how many each and within the radius (the call included, in a group of 2 calls or more); its groups and site first, then the nearest, each with its tags and **Open**; a click (or <kbd>Enter</kbd>) centres the map on one. The map brings every NQ call of its campaign within the radius, of its groups and its site, and the 600 nearest of the other campaigns (with **Every campaign**, the header tells how many more were left out).
- **Diagnosis hints:** what the map suggests, each marked *To check*, *Worth a look*, *Fine* or *Note* (the first ones first; a click on one about a site shows it). The ISD is that of [The network around the call](#the-network-around-the-call).
  - **Coverage** and **Interference:** the average RSRP and SINR against the levels of Network Insights (LTE weak below −110 dBm, interfering below 0 dB; NR below −115 dBm and −3 dB). A low SINR with a good RSRP points at interference, with a weak RSRP at coverage. A **Coverage hole** (to check): weak or no RSRP where the nearest serving site is at least 1.5 times its ISD away.
  - **Serving distance:** the site of the end cell flagged from twice its ISD and 1 km (overshooting), or beyond its ISD when a site three times nearer was there (a missing neighbour or overshooting); a site without others of its network within 40 km is judged by 5 km, or 1.5 km with a site three times nearer.
  - **Overshooting cells** (worth a look): a cell that served the call from at least twice the ISD of its site and 1 km (5 km without an ISD), pointing at the call (within half its beamwidth, at least 30°, of its azimuth): its tilt is worth a look.
  - **PCI collision:** cells around with the PCI and channel of a cell of the call.
  - **Cells in service:** cells locked, halted or disabled on the sites of the call (to check) or around it, and sites planned or in progress around.
  - **Other operators:** the share of tests not completed of its operator against the others around (at least 5 of each), with a two-proportion test and their median LTE RSRP: *Its network fails more here* (to check) when clearly higher (z of 2 or more), at least 1.5 times and 2 points above (such as 9% of 426 tests against 0% of 1,447); *Fails a little more than the others* when higher without enough tests; *Every operator fails here* when the others fail 5% or more of their tests (about five times the usual share), so the place may explain it.
  - **Repetition:** the NQ calls of its operator at its place (a repeated issue by the Cluster size, in one or several campaigns) and in its hotspot.
  - **Handovers:** **Ping-pong handovers** when the call went back to a cell it had left (how many in how much distance and time, the cells; to check when twice or more within 500 m, as no cell dominates there), many handovers (4 or more, with the cell it ended on), and the NR leg of an NSA call not found.
  - **Layer3 Logs** (teal edge, with a log): in its last seconds an **SCG failure**, an **RRC re-establishment**, a **SIP error** or a **reject** of the network (to check), a **stronger neighbour without a handover** (6 dB above the serving channel for 3 seconds: to check, worth a look with handover attempts), a **handover** right before the failure, LTE and NR **coverage** (RSRP below −115 dBm) or **interference** (SINR below −3 dB) at the failure, the **UE at maximum power**, a **high BLER** and records without measurements; *Fine* when none. A click shows that moment of the log on the map.
- **Decisions at its place:** the Root Category and Root Cause already chosen for the other NQ calls at its site and in its hotspot, the most frequent first, with calls, campaigns, statuses and some JOIN_IDs, and those still without one; **Use** gives this call the same (editors).
- **Its drive:** the tests of its operator 15 minutes before and after the call within 30 km (CDRs of **Campaigns**), to see whether the radio got worse before it and the next tests recovered: time from the call, test, result, RSRP, SINR and distance, the call marked and those not completed in red; a click on a row centres the map on it, and the map draws the way of the car through them.
- **Serving site health:** the calls that started on its serving site (ringed red, else green) per campaign and NR Mode (latest version) and how many were Non-Qualified, against the NQ rate of its operator on every site (orange from 1.5 times, red from twice) and that of every operator on the site, with the cells of the site.
- **Radio around the call:** per operator (its own first), the tests within the radius, how many did not complete, the median LTE and NR RSRP and SINR and the share below −110 dBm and 0 dB, then the sites around, the nearest one, the cells with the PCI and channel of a cell of the call and the Network Inventory used (the newest snapshot of each network).

The first map of a CDR reads its tests, a few seconds for a large Data CDR; the next calls of that CDR show at once.

### Comments and history

- **Comments:** authors edit and delete their own; admins and super-admins any. Edited comments show **edited**; deleted ones leave a note with who and when, and the history keeps the previous text.
- **History:** admins and super-admins delete one entry (its **×**), the whole history of a call (**Clear history** above the timeline) or that of the selected calls (**Clear history** in the bulk bar). Only the history goes: the status, team, analyst, root cause and comments stay, and the deletion is in the audit log.

> [!CAUTION]
> **A deleted history cannot be recovered** (importing an older NQ Call Tracking package adds back the entries it holds), and the Progress View counts only the remaining changes.

> [!NOTE]
> **Nobody overwrites a newer follow-up by mistake.** When another user changed a call after you loaded it, your change (also of the fields of the tabs) is refused and the list reloads. The open page refreshes the calls and the open call every minute.

## NQ Analysis Configuration

**NQ Analysis Configuration**, beside the [Sections bar](#sections-bar) (only its icon on a phone), opens on hover or click the configuration of the workspace, shared by every user. The sections menu of the Non-Qualified Calls tab lists it too, after a line, with every option (each with the same icon): choosing one opens it on the page.

> [!IMPORTANT]
> **Only admins and super-admins change the NQ Analysis Configuration.** The other roles open every option to see it: a card at the top says so, its controls are locked and there is no Save. `user-editor` accounts keep following up the calls (status, team, analyst, root category and cause, fields, comments and bulk changes), and every role arranges its own [table layout](#table-layouts).

| Option | What it configures |
| --- | --- |
| [Prioritization Rules](#prioritization-rules) | Which calls are analysed first: the [strategy](#strategies), its steps, queues and Priorities. |
| [Fields & Sections](#fields-and-sections) | The fields every call is followed up with, their lists and Excel order. |
| [Statuses & Teams](#statuses-and-teams) | The NQ Call Statuses and the teams with their members. |
| [Status Rules](#status-rules) | How the status follows the Analysis, Implementation and Planning fields. |
| [Root Cause Catalog](#root-cause-catalog) | Domains, Root Categories and Root Causes with their keywords, and the suggestion rule. |
| [DT Analyzer RCA Rules](#dt-analyzer-rca-rules) | How the DT Analyzer RCA finds the root cause of every call. |
| [Map Levels](#map-levels) | The RSRP, RSRQ, SINR and UE Tx Power levels of the maps. |
| **Import Ericsson RCA Results** | The Ericsson RCA results, by `JOIN_ID` (see [Ericsson RCA results](#ericsson-rca-results)). |
| **Import Previous NQ Analyses** | The analyses of the previous tool, by `JOIN_ID` (see [Previous NQ Analyses](#previous-nq-analyses)). |
| **Link Analysts to Accounts** | The user accounts of the analysts and reviewers without account (see [Link Analysts to Accounts](#link-analysts-to-accounts)). |

The imports and Link Analysts to Accounts come after a line.

> [!TIP]
> **Every configuration can go back to the values of a new workspace:** **Default Fields & Sections**, **Default Statuses** and **Default Teams**, **Default Rules** (Status Rules, DT Analyzer RCA Rules and Prioritization Rules), **Default Levels** (Map Levels), **Default Catalog** and **Default Rule** (Root Cause Catalog and its suggestion rule), **Default Columns** (table columns) and **Default Equivalences** (Previous NQ Analyses). Each fills its dialog and **Save** applies it, except Default Equivalences, which applies once confirmed; values still used by a call are never removed, nor the catalog values a DT Analyzer RCA rule gives.

## Fields and sections

**Fields & Sections** configures the catalog of fields every call is followed up with, in the order of the Excel export.

- **Sections:** **Sections** renames and recolours the six sections (their tabs and the colours of the table headers and Excel; by default General blue, RCA yellow, Failure Details red, Analysis purple, Implementation green, Planning a darker green). Chips above the fields show those of one section, and a filter finds them by name.
- **Each field** has a name, a **section**, a **source** and a **type**:

| Source | Fields |
| --- | --- |
| **Entered by the analysts** | A **List** of values, each with a colour, **Text** (up to 300 characters), **Long text**, **Number**, **Date** (YYYY-MM-DD) or **Yes / No**. **Propose the CDR value of** offers an empty field the value of a call field (*Use the CDR value*; such as Failure Latitude and Longitude, Serving Cell, Band and Vendor 1 when Failure, Host Network when Failure). |
| **Follow-up of the call** | The NQ Call Status, Team Responsible, Analyst, Date last modification, Comments, Selected Root Category and Selected Root Cause: renamed, moved and reordered, never removed. |
| **From the CDR** | A call field, the last cell of the Cell ID chain (`last_cell_id`) or a CDR column (`column:<name>`, indexed automatically), read only (such as the NetCheck RCA Failure Classification, Suggested Category and Suggested Cause, the Last Cell ID and the Failure Comment). |
| **From the Ericsson RCA** | A column of the [Ericsson RCA results](#ericsson-rca-results), read only (Ericsson RCA Category A … Ericsson RCA Evidence). |
| **From the DT Analyzer RCA** | Its Root Domain, Root Category, Root Cause, Rule or Evidence, read only. |
| **Derived from the call** | A list whose values have keywords looked for in some call fields; the first value whose keywords appear is the call's (Session Type: WhatsApp, MULTI-RAB, CALL, HTTP Transfer, Browsing & Streaming and Interactivity & Ping from the CDR `Session_Type` and Test Name). |
| **From the NQ Prioritization** | A value of the [NQ Prioritization](#nq-prioritization), read only, with its own type (the Prioritization Rule's values are the steps of the strategies), shown in the **Prioritization Info** of the call, not in the tab of its section (the group IDs in its header). |

- **Summary breakdown** (lists and Yes / No) adds a breakdown to the Summary.
- **Required to close** (fields of the analysts): a call cannot be closed, by hand or by a change of its fields, while it is empty.
- **Final** (a list value) ends its phase: by default Finished, Rejected and Invalidated of Analysis Status, Evaluated, Implemented and Not Applicable of Implementation Status, and Planned of Planned Status. Choosing a final value, or closing a call by hand, while fields of the analysts are empty shows them by section, with **Go back and fill them** or **Continue anyway**.
- **The status of each phase** (the first list of Analysis, Implementation and Planning) stands out with a darker control in its tab, as the NQ Call Status and the Priority in the header.
- **Description:** shown when hovering the field.
- **Order** (↑ ↓): in the section and in the Excel export. Whether a field is a table or Excel column is chosen in [Columns](#columns), per [table layout](#table-layouts) (a new field goes to Excel, not to the table).

> [!WARNING]
> Renaming a list value updates every call that uses it and the Status Rules; a value or field still used by a call cannot be removed, and the type and source of a field with values cannot change.

**Default Fields & Sections** leaves only the sections and fields of the [default catalog](#default-catalog), in their order, names, colours, settings and list values (a field keeps its values, a list value with the same name its calls); **Save** applies it, naming any other field or value still used by a call to clear or rename first.

### Default catalog

The 37 fields of the meeting workbook and those of the analyses of the previous tool (see [Previous NQ Analyses](#previous-nq-analyses)), in their order but with the DT Analyzer RCA first, then the NetCheck RCA and the Ericsson RCA:

| Section | Fields |
| --- | --- |
| **RCA** | DT Analyzer RCA Root Domain, Root Category, Root Cause, Rule and Evidence; NetCheck RCA Failure Classification, Suggested Category and Suggested Cause; Ericsson RCA Category A, Subcategory A, Category B, Subcategory B, Initial Category, Initial Subcategory, Suggested Category, Suggested Cause and Evidence; then Initial Root Category, Initial Root Cause, Selected Root Category, Selected Root Cause and Selected Root Technology. |
| **General** | NQ Call Status; Priority (P1 to P8, from red to grey as the queues and steps, filled by the [strategy](#strategies) while nobody chooses it); the [NQ Prioritization](#nq-prioritization) values (Prioritization, Prioritization Rule, Prioritization Queue, Expected Gain, Scoring Impact, Scoring Points Lost, Scoring KPIs Lost, Repeated Issue, Repetitions, Repeated Campaigns, Repetition Place, Hotspot ID, Time-Window ID, Cluster ID; Prioritization, Scoring Impact and Repeated Issue are Summary breakdowns); Team Responsible, Analyst, Reviewer, Unique ID, Date last modification, Comments. |
| **Failure Details** | Session Type, Failed Party (MOC/MTC) (UE1/UE2), Host Network when Failure, Last Cell ID, Serving Cell when Failure (proposing the Last Cell ID), Band when Failure, Vendor 1 when Failure, Vendor 2 when Failure (the second vendor when two are involved), Failure Comment. |
| **Analysis** | Analysis Status, Tunnel Failure, Needed Technology, Failure Latitude, Failure Longitude, Problem Location, Solution Location, Polygon Area, Description, Findings, Proposed Measure. |
| **Implementation** | Implementation Status (Not yet evaluated in red, Under evaluation, Evaluated, Implemented, Not Applicable), Implementation Team, Implementation Proposals, Implementation Site, Notice to VF3. |
| **Planning** | Planned Status, Planned Date, Planned FY. |

- **Analyst:** who analyses the call: a user account, or an analyst without account brought by the [Previous NQ Analyses](#previous-nq-analyses).
- **Reviewer:** who reviewed the analysis: any user account of the workspace (not only team members), or a reviewer without account from the Previous NQ Analyses, tagged **No account** and never offered for new calls.
- **Implementation Team:** the team that implements the measure, which can differ from the Team Responsible.
- **Planned FY:** the fiscal year a measure is planned for when it has no date, always written FY27: a year or quarter typed or imported becomes its fiscal year (2027 and Q3 2027 are FY27), new fiscal years take their place in order, and other values are refused (the import keeps them in the note).

### Catalog workbook

- **Export Catalog** downloads the whole catalog as an Excel workbook easy to edit and import again: **About** (how to edit it), **Sections** (key, name, colour), **Fields** (order, section, name, key, type, source, source reference, table, Excel, summary, required, CDR value proposed, description), **Lists** (a row per value with colour, keywords and **Final**), **Root Catalog** (domains with colour; categories with domain; causes with category and domain, empty when Auto; all with keywords), **Statuses and Teams** (closed statuses, team members) and **Status Rules** (a row per condition).
- **Import Catalog** reads that workbook, or the field list of the meeting workbook (sections in the first row, field names in the second, kind of values in the fourth, list values from the sixth), and previews what it adds before **Import**: new fields, list values, domains, categories, causes, statuses and teams are added, the sections and Status Rules of the workbook are taken, and nothing is removed.

## Statuses and teams

**Statuses & Teams** configures the statuses and teams of the workspace, each with a name, a colour and a position.

- **Closed** statuses count as closed in the summary and are left out by **Open calls only**.
- **In Queue** statuses: their prioritized calls are listed in their queue (**Next to analyse** of the [NQ Prioritization](#nq-prioritization)); a closed status is never In Queue.
- **The first status** is that of the calls no [Status Rule](#status-rules) matches, such as the calls nobody has followed up yet.
- **Default statuses:** Not Attended, Assigned and Under Analysis (In Queue), Analysis Finished, Under Implementation, Under Planning and Closed (closed). A call given a team or an analyst is Assigned while nobody attends it; an attended call is open, in one of the four phase statuses, until closed, and stays in its queue while Under Analysis (it leaves with Analysis Finished, Under Implementation, Under Planning or Closed).
- **Default teams:** E2E Team, RAN Planning Coverage, RAN Planning Capacity, RF OPT (Hot Spots) WP2a, Operations, Netcheck and PCI Planning Team.
- **Renaming** a status or team updates every call that uses it (and the Status Rules).
- **Removing:** a team still used by a call, or a status still set by hand on a call, cannot be removed: move those calls first, or merge the team into another with **⤳** (Merge into…): on **Save** its calls go to that team, its members join it (a team open to everyone stays so) and it is removed. Calls whose status the rules gave follow the rules again when their status is removed.
- **Default Statuses** and **Default Teams** leave only the defaults, in their order and colours (one with the same name is kept, with its calls and members, and recoloured); **Save** applies them, then **Default Rules** in [Status Rules](#status-rules) puts the default rules back.

### Team members

**Members** of each team (*Everyone* or the number of members) chooses the workspace users that belong to it, by first and last name (else username; the filter finds either), the default users first and tagged **default user**, with **Select All / None**; a user can be in several teams. **Save** saves them.

> [!IMPORTANT]
> **A team with members accepts only them as analysts.** Its **Analyst** list offers only them, and moving a call to a team its analyst does not belong to clears the analyst (an analyst without account stays). A team without members accepts every user.

Choosing only the analyst brings the call to their team (the first in the list when several) unless it already has a team they belong to or a team without members.

## Status Rules

The **NQ Call Status** is semi-automatic: it follows the **Status Rules** of the workspace until an analyst chooses it by hand. **Status Rules** (NQ Analysis Configuration menu and Lifecycle & Phases panel) lists the rules in order; each sets a status when every one of its conditions holds.

> [!IMPORTANT]
> **The first rule that matches gives the status of the call.**

> [!WARNING]
> **Change these rules with care** (the dialog warns too): without knowing the fields and statuses of the calls, a change can completely change how they are classified, since on **Save** every call with an automatic status takes the status the new rules give.

- **A condition** reads a list or Yes / No field entered by the analysts or derived from the call, the team, the analyst, the root category or cause, or **Attended** (a follow-up change other than assigning the call — its Team, Analyst, Reviewer or Priority — or a comment), and is **is one of** or **is not one of** some values, **is empty** or **is not empty**.
- **Values, not names:** renaming a list value or a status renames it in the rules, and a removed value or field leaves their conditions (a rule left without conditions is removed).

The default rules go from the end of the pipeline to its start, so the most advanced phase wins and the rules of each pipeline card follow one another:

1. **Closed** when Analysis Status is Rejected or Invalidated.
2. **Closed** when Implementation Status is Implemented or Not Applicable.
3. **Under Planning** when Planned Status is Planned.
4. **Under Implementation** when Implementation Status is Not yet evaluated, Under evaluation or Evaluated.
5. **Analysis Finished** when Analysis Status is Finished: the analysis is done and its implementation not decided; the call leaves its queue, and is closed once Implementation Status is Implemented or Not Applicable.
6. **Under Analysis** when Analysis Status is Ongoing.
7. **Under Analysis** when the call is attended (open, in its first phase).
8. **Assigned** when the call has an analyst.
9. **Assigned** when the call has a team.

Otherwise the call is **Not Attended**. **Default Rules** shows them again, with the conditions on the fields the workspace still has; a rule whose default status no longer exists (after a rename, say) is marked to choose its status, and the rules save once every rule has one.

- **When it applies:** as soon as a field, a comment, the team, the analyst or the root cause changes; saving the rules, fields or statuses applies them to every automatic call at once.
- **By hand:** a status chosen in the table, the call or the bulk bar stays until **↺ Back to automatic**. The history tells the automatic changes apart, and the Lifecycle & Phases panel, the **Status Set** filter and the Excel export show which calls are automatic.

## Root Cause Catalog

**Root Cause Catalog** configures the catalog the Root Category and Root Cause of each call are chosen from, in four tabs with a filter:

| Tab | Content |
| --- | --- |
| **Domains** (shown first) | Each with its colour: the technical ones (RF, RAN, Core, IMS/E2E, Protocol, Device, Operational) and those of the calls without a network root cause: **Indeterminate** (cause not known yet) and **Invalid** (not a failure). |
| **Root Categories** | 18 by default, which group the technologies and directions: Coverage, Interference and Radio Link Quality (RF); Mobility, Radio Signalling, Capacity, Configuration & Planning (RAN); Registration & Authentication, Session & Mobility Management, Fallback & Legacy (Core); Voice Core (IMS), End-to-End (IMS/E2E); Server & Protocol, Data Transport (Protocol); Device & Test Setup (Device); Network Operations (Operational); Indeterminate (Indeterminate: Unclear, Further investigation required) and Invalid (Invalid: Invalid, Normal release). |
| **Root Causes** | 80 by default, each mapped to its category: why coverage was poor (NLOS due to clutter or terrain profile, LOS but weak signal, Large distance to the nearest site, Coverage hole (no service), Weak signal with low SINR, UL coverage (UE at maximum power)…), the source of the interference (Lack of dominant cell, Overshooting or excessive cell overlap, PCI collision, External or Internal UL interference…), handover, signalling, core, IMS and protocol causes (Missing or late handover, No answer to RRC connection request, TAU reject, No QCI1 established, DNS…). When a source only says which link suffered: **DL coverage**, **DL interference**, **UL interference**. |
| **Mapping** | Every root cause with its category and domain, and every category with its domain, to map the whole catalog at once (the tab counts the causes mapped). **Apply to Calls** saves the catalog and, after confirming how many, gives the calls with a root cause and no root category the category of their cause (in their history). |

- **Root Technology** (5G - NR, 4G - LTE, 3G - UMTS or 2G - GSM) is chosen beside the Root Category and Root Cause (**Selected Root Technology** in fields, exports and filters), so categories and causes are the same for every technology. The sources propose it: the Ericsson RCA by its category (*Poor Coverage LTE*); the DT Analyzer RCA by its rule, else by the technology of the radio measured at the failure (the RSRP its rules read, from the Layer3 Log, the Ericsson RCA or the CDR), else the most recent technology the call failed in; NetCheck by the Failure Technology, the most recent when several (*5G/4G* and *EN-DC* → 5G - NR, *2G/4G* → 4G - LTE). **Use as Final Decision** and **Accept** set it with the category and cause.
- **Category follows cause:** choosing a cause gives the call its category (also over another category: a call never has a category and a cause of another one), and choosing another category clears a cause that is not one of its causes.
- **Order of the lists of a call:** first what its sources propose, then (for causes) the causes of its category, then every domain in catalog order, the causes of each domain under each of its categories (*RF · Coverage*, *RF · Interference*…).
- **Domain:** chosen by hand or **Auto**: a cause without one takes that of its category, otherwise the first domain whose keywords appear in its name or keywords (*Auto · RAN*); a domain chosen by hand ignores the keywords. It gives the colour, groups the lists and gives the call its **Root Domain** (that of its category, else of its cause); a change of the catalog changes the Root Domain of its calls.

> [!TIP]
> Each value has **keywords**, separated by commas, that map the NetCheck and Ericsson RCA values and the comments onto the catalog; `a+b` needs both words. A value that names a root cause takes the category of that cause (*DL interference problems* → Interference · DL interference; *DNS* → Server & Protocol · DNS); the keywords of the categories only count when no cause matches (*RRC layer* alone → Radio Signalling).

- **Order** (↑ ↓): values are tried from top to bottom, so it sets the priority when several match.
- **Add missing defaults** adds the default domains, categories and causes missing, keeping the existing ones with their keywords. **Default Catalog** leaves only the defaults, with their keywords and colours, and clears **Require a root category to close a call**; **Save** applies it (a value with the same name keeps its calls).
- **Renaming** a value updates every call that uses it; a value used by a call cannot be removed.
- **DT:** a value a [DT Analyzer RCA rule](#dt-analyzer-rca-rules) gives, enabled or not, shows **DT** in place of its remove button (hover it for the rules): it cannot be removed, nor a root category or cause renamed, until no rule gives it; such a domain can still be renamed.

> [!WARNING]
> **Require a root category to close a call** refuses closing a call without a root category, whether its status is chosen by hand or a change of its fields makes the rules close it.

### Suggestion rule

The suggestion rule translates the **NetCheck RCA** of the CDR onto the catalog, and only it: the DT Analyzer RCA follows its own rules, the Ericsson RCA is matched by name and keywords, and the decisions of the analysts never change. **NetCheck RCA Suggestion Rule** (named after the RCA of the provider), at the top of the catalog and in the Root Cause Analysis panel (while its source is NetCheck RCA), shows it to every user; admins and super-admins change:

- the call fields that choose the domain, and those that choose the category and cause (Failure Classification, Category, Subcategory, Comment, Phase and Technology, Result, Test Name, Technology and Direction);
- whether the category and cause are looked for only in the domain found (a cause the domain lacks is then looked for in the whole catalog: *RAN Problems · BLER Problems* → Radio Link Quality · High UL BLER);
- whether the comments are read when the CDR leaves them unresolved, and whether they can choose the domain;
- whether keywords match whole words or any part of the text (the Ericsson RCA follows this choice too).

**Default Rule**: a domain keyword in the Failure Classification chooses the domain (*RF Problems* → RF); category keywords in those fields, the Failure Category, Subcategory and Comment and the technology of the call choose the category; cause keywords in the Failure Category, Subcategory and Comment the cause (*DL interference problems* of an NR call → Interference · DL interference, 5G - NR); then the comments. The Failure Comment counts only when the Category and Subcategory give no category or cause, so its free text (a PCI or an RSRP it quotes) never outweighs them. *E2E Trace Required* is not a domain: its category (Packet Loss, Low Throughput, Coverage…) chooses the cause.

The rule applies at once to the suggestions, the Root Cause Analysis and the recommendations, and never changes the root causes already set.

## Root cause recommendation

Every call gets a recommended Root Category, Root Cause and Root Technology, merged from its sources:

| Source | Weight | What it reads |
| --- | --- | --- |
| **NetCheck RCA** | 3 | The Failure Classification, Category and Subcategory of the CDR, by the suggestion rule. |
| **Previous decisions** | 3 | The Root Category and Cause the analysts chose for at least two other calls with the same NetCheck, Ericsson RCA or DT Analyzer RCA values. |
| **Ericsson RCA** | 2 | The Suggested Category and Cause of its [Ericsson RCA results](#ericsson-rca-results) (else Category A and Subcategory A), by name or keywords. |
| **DT Analyzer RCA** | 2 | The Root Category and Cause the [DT Analyzer RCA](#dt-analyzer-rca) finds; its card shows the rule and evidence. A call only **Not identified** explains gets no proposal from it. |
| **Comments** | 1 | The comments of the call, when the CDR leaves the root cause unresolved. |

The category with most weight wins (NetCheck first when it ties with the previous decisions), then the best cause and technology among the sources that agree on it. The confidence is **high** when two or more sources agree, **medium** when only NetCheck, the previous decisions or the DT Analyzer RCA propose it, **low** otherwise.

> [!NOTE]
> The recommendation shows in the table, the RCA tab and the Excel export. **Accept** (one call) or **Accept recommendations** (selected calls) sets it; the analysts can also use one source or any other value, and their choices teach the next recommendations.

## DT Analyzer RCA

The **DT Analyzer RCA** finds the Root Category, Root Cause and root domain of every Non-Qualified call, test and Speech sample from the data of its CDR. It works in every workspace, whatever its CDR type and also when the provider brings an RCA of its own, and comes first wherever the RCA sources are listed: the [Root Cause Sources](#root-cause-sources) and [Root Cause Analysis](#root-cause-analysis) panels and filters, the RCA tab, the [recommendation](#root-cause-recommendation), the fields and the exports.

It reads every call through the field profile of the CDR type of the workspace, and the network around it in the Network Inventory:

| Values | What it reads |
| --- | --- |
| Call | Result, Test Name, Technology, Direction and Environment. |
| Failure | The **failure description** (the Failure Classification, Category, Subcategory and Comment of the provider's RCA, its failure events and SCG failures); the **signalling events** alone (failure events and SCG failures, without the provider's RCA); Failure Phase, Technology and Side; the **technology at the failure** (the Failure Technology, else of the call or those it used); the **RSRP** and **SINR at the failure** (of NR when it failed in NR alone, else of LTE, the anchor), from the most precise source: the Layer3 Log at the failure, else the Ericsson RCA before it, else the CDR average. |
| Failed side and other side | **UE A** calls (MO, Mobile Originated), **UE B** is called (MT, Mobile Terminated). The **failed side** is the one the Failure Side of the CDR names (MO = A, MT = B), else the failure description when it names MO or MT alone. For it and the **other side**: the LTE and NR PCell RSRP and SINR, UE Tx Power and how far the strongest LTE and NR neighbour was above the PCell (below when negative), from its Layer3 Log at the failure, else its Ericsson RCA (for the neighbour, the highest of both: the log measures the channel of the PCell, the Ericsson RCA other frequencies too). The RSRP and SINR at the failure are then those of the failed side when measured, else the worst of both. Without a known failed side, it stands for the worst of both sides (or the device of a Data test) and the other side has no values. |
| LTE and NR radio | Average and minimum RSRP, RSRQ, average and minimum SINR, maximum transmit power and BLER of the A side of a call or the playing side of a Speech sample; RSRP and SINR of its B side; the **DL resource blocks used** by a Data test (the average share of its primary LTE or NR carrier, from its bandwidth); and the **radio measured** (LTE, NR or both, when the CDR has their RSRP or SINR). |
| Mobility | The technologies used and their timeline, the handovers and their types, and the **ping-pong handovers** (back to a cell right after leaving it, A → B → A, a cell repeated in a row counted once). |
| Network Inventory | The **serving site distance** (from where the call ended to the site of its last cell), the **ISD** of that site and that distance in ISDs, the **nearest site distance** of the serving networks and that in its own ISDs, the **PCI collisions around** (cells within 2 km with the PCI and channel of a cell of the call) and the **cells out of service on its sites** (locked, halted or disabled); see [The network around the call](#the-network-around-the-call). |
| Layer3 Logs | For a call with a session in the [Layer3 Logs](workspace-management.md#layer3-logs) (by `JOIN_ID`, both UEs of a voice call), worked out once when the log is imported: the LTE and NR PCell RSRP and SINR in its last 5 seconds (**at the failure**) and their minimum, the RAN Configuration at the failure; in its last 10 seconds its RRC re-establishments, SCG failures, handover attempts, inter-RAT moves (IRAT, redirections) and RRC releases, LTE and NR BLER, UE Tx Power samples reaching 22 dBm, how far a neighbour of the serving channel rose above the serving cell (and for how many seconds by 3 dB or more); the rejects of its signalling, its worst **SIP error** (from 400, leaving out 401, 407, 487 and 489 of a normal call or registration), the records without measurements and the **signalling before the failure** (events and L3 messages of its last 10 seconds). The counts of the two UEs add up and the worst radio is kept; each UE's radio is also kept for the failed side and the evidence. |
| Ericsson RCA | For a call with [Ericsson RCA results](#ericsson-rca-results) (by `JOIN_ID`): the LTE and NR PCell RSRP and SINR, the UE Tx Power and how far a stronger neighbour was above the PCell (*RSRP diff*) it measured before the failure, read from its evidence (*LTE PCell RSRP=-82.8 dBm, SINR=5.24, TxPower=-13.0*); with both sides, the worst (lowest RSRP and SINR, highest power and neighbour), each side also kept for the failed side and the evidence. |
| KPIs | Throughput (Mbit/s), service access time (s), DNS time (ms) and success (%), TCP round-trip time (ms), packet loss (%), latency (ms), call setup time (s), duration (s), speech quality (MOS), RTP packet loss (%) and jitter (ms). |

The calls are calculated when indexed, and again when its rules, the [Root Cause Catalog](#root-cause-catalog), the Network Inventory or the [Serving Networks](workspace-config.md#serving-networks) change; importing or deleting Ericsson RCA results calculates their calls again, and a log imported, processed again or deleted those of its campaign.

The **evidence** of each call has a line per subject, so the values of each source never mix:

| Line | What it says |
| --- | --- |
| The rule | The values that met the rule (*LTE RSRP (average) −118.4 dBm (< −110 dBm)*); an RSRP or SINR at the failure names its technology and source (*RSRP at the failure (LTE, Ericsson RCA, before the failure) −112 dBm (< −105 dBm)*), a failure description only the word it contains. |
| Provider description | When the rule read it: the provider's Failure Classification, Category, Subcategory and Comment and the failure events, without the averages of its comment. |
| Radio | The radio before the failure of each source, a line each, the most precise first: the Layer3 Log at the failure (*Radio (Layer3 Log, at the failure): LTE PCell RSRP −82.79 dBm, SINR 5.24 dB · NR PCell RSRP −74.2 dBm, SINR 6.6 dB, UE Tx Power (maximum) −10 dBm*), else the Ericsson RCA (*Radio (Ericsson RCA, before the failure): …*). With both sides measured, or a known failed side, each side apart and the failed one marked (*A (failed side): LTE PCell RSRP −108.5 dBm; neighbour 15.5 dB above the PCell \| B: NR PCell RSRP −105.8 dBm, SINR −0.8 dB*). |
| Call average | The averages of the whole call: those of the provider's failure comment, each technology apart (*ENDC-5G mean RSRP −71.54 dBm, mean SINR 6.77 dB (RSRP ≤ −115 dBm in 0 %, SINR ≤ 0 dB in 12 % of the samples)*), else the CDR's LTE and NR averages. |
| Network and logs | The sites around the call and what the Layer3 Logs show before the failure (*Layer3 Logs: 5G EN-DC - SCG Failure NR SCG 2.1 s before the end on PCI 997*), when the rule read them (the logs also when it read the radio of the sides). |

In the RCA tab, the evidence of the DT Analyzer RCA and of the Ericsson RCA shows a bullet per subject and each side (**UE A**, the caller, MO; **UE B**, the called side, MT) in an indented block, the failed one marked **Failed side**.

**The radio of the sides** (rules 17–38): on the failed side, then on the other side of a voice call, they tell apart weak coverage, a stronger neighbour not handed over to, a weak signal limited by noise, no dominant cell, downlink interference and the UE at high power (uplink coverage or interference). They come after the rejects of the network and the network around the call, and before the identity, core, IMS and paging causes the provider reports: a radio this poor at the failure can bring those about, and the setup of a voice call needs both sides (the QCI1 bearer of the caller waits for the answer of the called side), so a poor radio on the other side explains the failure reported on the failed side. The evidence then also gives the provider's description.

> [!NOTE]
> The averages of the whole call and the radio the logs measured before the failure can differ by several dB: they cover different periods, and the provider's comment may give the NR leg of an EN-DC call while the Ericsson RCA gives the LTE PCell.

### Presentation

The DT Analyzer RCA is also a presentation, **DT Analyzer RCA**: its architecture (from the CDR to the Selected Cause), what it reads, how its rules decide, the lack of resources, the network around the call, handovers and service, the result and evidence of each call and how to change the rules. Select it to open it in the slide viewer, play it full screen or download its PowerPoint; it is also in [Product Presentations](presentations.md).

```presentations
dt-analyzer-rca
```

### The network around the call

With a Network Inventory of the networks that serve the operator of the call ([Serving Networks](workspace-config.md#serving-networks)), the DT Analyzer RCA finds, as the [Map of the call](#map-of-the-call) does, the inventory cell of each cell of its trace (its own network first, nearest to where it served the call) and the site of the cell where it ended.

**Inter-site distance (ISD):** a city site serves a few hundred metres, a rural or road site several kilometres, so distances are compared with the ISD of the site: the mean distance to its 3 nearest sites in service of the same network, from the positions of the newest snapshot of the Network Inventory. It needs neither neighbour lists (the inventories lack them) nor Timing Advance (the CDRs lack it). A site without other sites of its network within 40 km has no ISD, so no rule reads its distance. For example, the urban sites of a UK network are about 1 km apart and the rural ones about 3.4 km.

- **Overshooting:** the serving site is at least **twice its ISD** (and 1 km) from where the call ended, with interference (SINR below 3 dB) or weak coverage (RSRP below −105 dBm). The evidence names the serving site and the nearest one, a hint of a missing neighbour.
- **Coverage hole:** the nearest serving site in service is at least **1.5 times its own ISD** away, with weak coverage (RSRP below −110 dBm) or no radio measured: no cell covers the place.
- **PCI collision:** a cell within 2 km has the technology, PCI and channel of a cell of the call, with interference.
- **Cells out of service:** cells of the sites of the call are locked, halted or disabled in the inventory, with weak coverage or interference.

### Lack of resources

The DT Analyzer RCA finds a lack of resources in three ways:

- **What the provider reports:** insufficient resources of the core (a PDU Session Establishment Reject with the 5GSM cause *Insufficient resources*) or a congestion reject (a CM Service Reject for congestion) give **Session & Mobility Management · Insufficient resources**, before such a reject is taken for an authentication one. Only the provider's RCA tells these causes: the CDR has no NAS cause of its own.
- **The signalling of the CDR itself:** an access the network rejected (*RRCConnectionReject*, *RRCReject* or *Immediate Assignment Reject* in its failure events), or an RRC Connection Reject the provider reports, gives **Capacity · Access rejected (no resources)**.
- **The resource blocks of a Data test:** a Cutoff test with its radio measured and good (no radio rule took it) whose primary carrier gave it less than **25 %** of its resource blocks on average gives **Capacity · Cell overload**. A completed test usually gets about two thirds. A server or TCP connection sending little also leaves resource blocks unused, so these rules come after those of the protocols and servers.

### DT Analyzer RCA Rules

**DT Analyzer RCA Rules** shows the rules to every user; admins and super-admins change them.

- **How they apply:** tried from top to bottom, the first enabled rule of the service of the call (Voice, Speech, Data, or every service when none is checked) whose conditions hold — all of them, or any — gives its Root Category and Root Cause from the catalog, with their domain and the [evidence](#dt-analyzer-rca). A rule without conditions takes every call of its services that reaches it; a disabled rule is skipped. Each rule shows the NQ calls it explains.
- **Conditions:** a number compared (<, ≤, >, ≥, =, ≠) with a value in the unit shown; a text that contains, or does not contain, one of its words, separated by commas (`a+b` needs both); any value empty or not empty.
- **Default rules:** the same in every workspace, listed in [Default rules](#default-rules); **Default Rules** fills the dialog with them and **Save** applies them.
- **Saving** calculates every call again at once (while the CDRs are being indexed, when the indexing ends). The rules travel with the NQ Calls Configuration (export, import, transfers and backups). The values they give stay in the [Root Cause Catalog](#root-cause-catalog).

> [!WARNING]
> **The order of the rules matters.** A rule only takes the calls the rules above it leave, so a broad rule high in the list hides the rules below it.

**Learn from the decisions of the analysts**, at the top of the dialog and off by default, lets the DT Analyzer RCA learn from the Root Category and Root Cause the analysts choose.

- **Pattern:** calls explained by the same rule, of the same service, whose failure the provider describes the same way (Failure Classification, Category and Subcategory).
- **What it learns:** a call takes the Root Category and Cause the analysts gave most other calls of its pattern when at least 2 of them, and more than half of those decided, agree (its own decision never counts); also for the calls the rules leave Not identified. The other calls keep what their rule gives.
- **Shown:** the evidence says what was learned and from how many calls (*Learned from the analysts: 3 of the 3 other calls of the rule “Voice failure with good radio”…*), the card of the source says **Learned from the analysts**, and the dialog counts the calls that learned.
- **When:** after each new decision of the analysts and each indexing (also **Reindex**); turning it off gives every call the root cause of its rule again. The setting travels with the rules.

### Default rules

The default rules of the DT Analyzer RCA, in the order they are tried. *All* rules take every service. A text condition holds when the text contains one of its words (`a+b` needs both). *In NR alone* means the technology at the failure is NR without LTE (an SA call); *in 2G or 3G alone*, without LTE nor NR. The domain of each category is in the [Root Cause Catalog](#root-cause-catalog).

> [!NOTE]
> **Good radio** means that the radio was measured and no radio rule took the call: without radio values neither the Cutoff tests nor the Voice failures with good radio are given a cause.

| # | Rule | Services | When | Root Category · Root Cause (Root Technology) |
| --- | --- | --- | --- | --- |
| | **What the provider reports outside the radio, and the lack of resources** | | | |
| 1 | Device or test setup | All | Failure description contains `modem`, `device`, `test setup`, `ue crash`, `at command`, `script error`, `battery` | Device & Test Setup · Device or test setup |
| 2 | No measurements in the drivetest log | All | Records without measurements (log) ≥ 1 and LTE RSRP at the failure (log) is empty and NR RSRP at the failure (log) is empty | Device & Test Setup · No measurements in the log |
| 3 | Insufficient resources of the core | All | Failure description contains `insufficient resources`, `service reject+congestion` | Session & Mobility Management · Insufficient resources |
| 4 | Access rejected by the network | All | Signalling events contains `rrcconnectionreject`, `rrcreject`, `immediate assignment reject` or Failure description contains `rrc connection reject` or Signalling before the failure (log) contains `rrcconnectionreject`, `rrcreject` | Capacity · Access rejected (no resources) |
| 5 | Authentication or registration rejected | All | Failure description contains `authentication`, `authorization`, `registration reject`, `attach reject`, `pdu session establishment reject` or Signalling before the failure (log) contains `authentication reject`, `registration reject`, `attach reject`, `pdu session establishment reject` | Registration & Authentication · Authentication/Authorization |
| | **The network around the call (Network Inventory)** | | | |
| 6 | Cells out of service on its sites | All | Cells out of service on its sites ≥ 1 and RSRP at the failure < −105 dBm | Network Operations · Cell/Site Outage |
| 7 | Cells out of service on its sites with interference | All | Cells out of service on its sites ≥ 1 and SINR at the failure < 3 dB | Network Operations · Cell/Site Outage |
| 8 | NR coverage hole | All | Nearest site distance / its ISD ≥ 1.5 × and NR RSRP (average) < −110 dBm, in NR alone | Coverage · Large distance to the nearest site (5G - NR) |
| 9 | Coverage hole | All | Nearest site distance / its ISD ≥ 1.5 × and LTE RSRP (average) < −110 dBm | Coverage · Large distance to the nearest site (4G - LTE) |
| 10 | Coverage hole without service | All | Nearest site distance / its ISD ≥ 1.5 × and Radio measured is empty | Coverage · Coverage hole (no service) |
| 11 | NR overshooting | All | Serving site distance / its ISD ≥ 2 × and Serving site distance ≥ 1 km and NR SINR (average) < 3 dB, in NR alone | Interference · Overshooting or excessive cell overlap (5G - NR) |
| 12 | Overshooting | All | Serving site distance / its ISD ≥ 2 × and Serving site distance ≥ 1 km and LTE SINR (average) < 3 dB | Interference · Overshooting or excessive cell overlap (4G - LTE) |
| 13 | NR overshooting with weak coverage | All | Serving site distance / its ISD ≥ 2 × and Serving site distance ≥ 1 km and NR RSRP (average) < −105 dBm, in NR alone | Coverage · Served from a far site (overshooting) (5G - NR) |
| 14 | Overshooting with weak coverage | All | Serving site distance / its ISD ≥ 2 × and Serving site distance ≥ 1 km and LTE RSRP (average) < −105 dBm | Coverage · Served from a far site (overshooting) (4G - LTE) |
| 15 | NR PCI collision | All | PCI collisions around ≥ 1 and NR SINR (average) < 3 dB, in NR alone | Interference · PCI Collision/PCI MOD 3 Collision (5G - NR) |
| 16 | PCI collision | All | PCI collisions around ≥ 1 and LTE SINR (average) < 3 dB | Interference · PCI Collision/PCI MOD 3 Collision (4G - LTE) |
| | **The radio of the failed side, then of the other side of a voice call, at the failure (Layer3 Logs, else Ericsson RCA)** | | | |
| 17 | Weak LTE coverage on the failed side | All | LTE RSRP of the failed side < −110 dBm | Coverage · DL coverage (4G - LTE) |
| 18 | Weak NR coverage on the failed side | All | NR RSRP of the failed side < −110 dBm | Coverage · DL coverage (5G - NR) |
| 19 | Stronger LTE neighbour on the failed side | All | Strongest LTE neighbour above the PCell of the failed side ≥ 3 dB and LTE SINR of the failed side < 3 dB | Mobility · Missing or late handover (4G - LTE) |
| 20 | Weak LTE signal with a low SINR on the failed side | All | LTE RSRP of the failed side < −105 dBm and LTE SINR of the failed side < 0 dB | Coverage · Weak signal with low SINR (4G - LTE) |
| 21 | No dominant LTE cell on the failed side | All | LTE SINR of the failed side < 0 dB and Strongest LTE neighbour above the PCell of the failed side ≥ −3 dB and LTE RSRP of the failed side ≥ −105 dBm | Interference · Lack of dominant cell (4G - LTE) |
| 22 | LTE interference on the failed side | All | LTE SINR of the failed side < 0 dB and LTE RSRP of the failed side ≥ −105 dBm | Interference · DL interference (4G - LTE) |
| 23 | Stronger NR neighbour on the failed side | All | Strongest NR neighbour above the PCell of the failed side ≥ 3 dB and NR SINR of the failed side < 3 dB | Mobility · Missing or late handover (5G - NR) |
| 24 | Weak NR signal with a low SINR on the failed side | All | NR RSRP of the failed side < −105 dBm and NR SINR of the failed side < 0 dB | Coverage · Weak signal with low SINR (5G - NR) |
| 25 | No dominant NR cell on the failed side | All | NR SINR of the failed side < 0 dB and Strongest NR neighbour above the PCell of the failed side ≥ −3 dB and NR RSRP of the failed side ≥ −105 dBm | Interference · Lack of dominant cell (5G - NR) |
| 26 | NR interference on the failed side | All | NR SINR of the failed side < 0 dB and NR RSRP of the failed side ≥ −105 dBm | Interference · DL interference (5G - NR) |
| 27 | UE at high power with weak coverage on the failed side | All | UE Tx Power of the failed side ≥ 21 dBm and LTE RSRP of the failed side < −100 dBm | Coverage · UL coverage (UE at maximum power) (4G - LTE) |
| 28 | UE at high power with good coverage on the failed side | All | UE Tx Power of the failed side ≥ 21 dBm and LTE RSRP of the failed side ≥ −95 dBm | Interference · UL interference (4G - LTE) |
| 29 | Weak LTE coverage on the other side | Voice, Speech | LTE RSRP of the other side < −110 dBm | Coverage · DL coverage (4G - LTE) |
| 30 | Weak NR coverage on the other side | Voice, Speech | NR RSRP of the other side < −110 dBm | Coverage · DL coverage (5G - NR) |
| 31 | Stronger LTE neighbour on the other side | Voice, Speech | Strongest LTE neighbour above the PCell of the other side ≥ 3 dB and LTE SINR of the other side < 3 dB | Mobility · Missing or late handover (4G - LTE) |
| 32 | Weak LTE signal with a low SINR on the other side | Voice, Speech | LTE RSRP of the other side < −105 dBm and LTE SINR of the other side < 0 dB | Coverage · Weak signal with low SINR (4G - LTE) |
| 33 | No dominant LTE cell on the other side | Voice, Speech | LTE SINR of the other side < 0 dB and Strongest LTE neighbour above the PCell of the other side ≥ −3 dB and LTE RSRP of the other side ≥ −105 dBm | Interference · Lack of dominant cell (4G - LTE) |
| 34 | LTE interference on the other side | Voice, Speech | LTE SINR of the other side < 0 dB and LTE RSRP of the other side ≥ −105 dBm | Interference · DL interference (4G - LTE) |
| 35 | Stronger NR neighbour on the other side | Voice, Speech | Strongest NR neighbour above the PCell of the other side ≥ 3 dB and NR SINR of the other side < 3 dB | Mobility · Missing or late handover (5G - NR) |
| 36 | Weak NR signal with a low SINR on the other side | Voice, Speech | NR RSRP of the other side < −105 dBm and NR SINR of the other side < 0 dB | Coverage · Weak signal with low SINR (5G - NR) |
| 37 | No dominant NR cell on the other side | Voice, Speech | NR SINR of the other side < 0 dB and Strongest NR neighbour above the PCell of the other side ≥ −3 dB and NR RSRP of the other side ≥ −105 dBm | Interference · Lack of dominant cell (5G - NR) |
| 38 | NR interference on the other side | Voice, Speech | NR SINR of the other side < 0 dB and NR RSRP of the other side ≥ −105 dBm | Interference · DL interference (5G - NR) |
| | **The causes the provider reports that a poor radio can also bring about (identity, core, IMS, paging)** | | | |
| 39 | Subscriber identity | All | Failure description contains `imsi`, `ue identity cannot be derived` | Registration & Authentication · Subscriber identity (IMSI) |
| 40 | Tracking area update | All | Failure description contains `tracking area update` or Signalling before the failure (log) contains `tracking area update reject` | Session & Mobility Management · TAU reject |
| 41 | Bearer deactivated by the network | All | Failure description contains `bearer deactivation`, `deregistered`, `detach request` | Session & Mobility Management · EPS bearer deactivation |
| 42 | No QCI1 bearer for the call | Voice, Speech | Failure description contains `qci1`, `qci 1` | Voice Core (IMS) · No QCI1 established |
| 43 | VoLTE or IMS core | Voice, Speech | Failure description contains `volte core`, `ims core`, `ims registration`, `sip`, `server internal error` or SIP error (log) ≥ 400 | Voice Core (IMS) · VoLTE core |
| 44 | EPS fallback | Voice, Speech | Failure description contains `epsfb`, `eps fallback` | Fallback & Legacy · EPS fallback failure |
| 45 | Paging | All | Failure description contains `paging` | Radio Signalling · Paging |
| 46 | Session in GSM | All | Failure description contains `session in gsm` | Fallback & Legacy · WhatsApp session in GSM |
| | **What its Layer3 Logs show at the failure (calls with a log only)** | | | |
| 47 | SCG failure with weak NR coverage (drivetest log) | All | SCG failures before the failure (log) ≥ 1 and NR RSRP at the failure (log) < −110 dBm | Coverage · DL coverage (5G - NR) |
| 48 | Re-establishment with weak LTE coverage (drivetest log) | All | RRC re-establishments before the failure (log) ≥ 1 and LTE RSRP at the failure (log) < −110 dBm | Coverage · DL coverage (4G - LTE) |
| 49 | Stronger neighbour without a handover (drivetest log) | All | Neighbour of the serving channel above the serving cell (log) ≥ 6 dB and Seconds a neighbour was 3 dB above the serving cell (log) ≥ 3 s and Handovers before the failure (log) = 0 | Mobility · Missing or late handover (4G - LTE) |
| 50 | Weak LTE coverage at the failure (drivetest log) | All | LTE RSRP at the failure (log) < −115 dBm | Coverage · DL coverage (4G - LTE) |
| 51 | Weak NR coverage at the failure (drivetest log) | All | NR RSRP at the failure (log) < −115 dBm and RAN Configuration at the failure (log) contains `5g sa` | Coverage · DL coverage (5G - NR) |
| 52 | UE at maximum power before the failure (drivetest log) | All | UE Tx Power from 22 dBm before the failure (log) ≥ 50 % and LTE RSRP at the failure (log) < −100 dBm | Coverage · UL coverage (UE at maximum power) (4G - LTE) |
| 53 | LTE interference at the failure (drivetest log) | All | LTE SINR at the failure (log) < −3 dB and LTE RSRP at the failure (log) ≥ −105 dBm | Interference · DL interference (4G - LTE) |
| 54 | NR interference at the failure (drivetest log) | All | NR SINR at the failure (log) < −3 dB and NR RSRP at the failure (log) ≥ −105 dBm and RAN Configuration at the failure (log) contains `5g` | Interference · DL interference (5G - NR) |
| 55 | SCG failure before the failure (drivetest log) | All | SCG failures before the failure (log) ≥ 1 | Mobility · SCG failure (5G - NR) |
| 56 | RRC re-establishment before the failure (drivetest log) | All | RRC re-establishments before the failure (log) ≥ 1 | Radio Signalling · Radio link failure |
| 57 | High LTE BLER before the failure (drivetest log) | All | LTE BLER before the failure (log) > 30 % | Radio Link Quality · High DL BLER (4G - LTE) |
| 58 | High NR BLER before the failure (drivetest log) | All | NR BLER before the failure (log) > 30 % | Radio Link Quality · High DL BLER (5G - NR) |
| | **The radio of the call** | | | |
| 59 | Poor LTE coverage | All | LTE RSRP (average) < −110 dBm | Coverage · DL coverage (4G - LTE) |
| 60 | Poor NR coverage | All | NR RSRP (average) < −110 dBm | Coverage · DL coverage (5G - NR) |
| 61 | LTE uplink at maximum power | All | LTE transmit power (maximum) ≥ 23 dBm and LTE RSRP (average) < −100 dBm | Coverage · UL coverage (UE at maximum power) (4G - LTE) |
| 62 | LTE downlink interference | All | LTE SINR (average) < 0 dB | Interference · DL interference (4G - LTE) |
| 63 | NR downlink interference | All | NR SINR (average) < 0 dB | Interference · DL interference (5G - NR) |
| 64 | No dominant LTE cell | All | LTE RSRQ (average) < −15 dB | Interference · Lack of dominant cell (4G - LTE) |
| 65 | Poor LTE coverage of the B side | Voice, Speech | B side LTE RSRP (average) < −110 dBm | Coverage · DL coverage (4G - LTE) |
| 66 | Poor NR coverage of the B side | Voice, Speech | B side NR RSRP (average) < −110 dBm | Coverage · DL coverage (5G - NR) |
| 67 | LTE interference on the B side | Voice, Speech | B side LTE SINR (average) < 0 dB | Interference · DL interference (4G - LTE) |
| 68 | Fallback to 2G or 3G | All | Technologies used contains `gsm`, `umts`, `wcdma`, `hspa`, `2g`, `3g` | Mobility · Inter-RAT transition |
| 69 | High LTE BLER | All | LTE BLER > 10 % | Radio Link Quality · High DL BLER (4G - LTE) |
| 70 | High NR BLER | All | NR BLER > 10 % | Radio Link Quality · High DL BLER (5G - NR) |
| | **Its handovers and the radio link** | | | |
| 71 | NR ping-pong handovers | All | Ping-pong handovers ≥ 1, in NR alone | Mobility · Ping-pong handover (5G - NR) |
| 72 | Ping-pong handovers | All | Ping-pong handovers ≥ 1 | Mobility · Ping-pong handover (4G - LTE) |
| 73 | NR handover failure | All | Failure description contains `handover` and Failure Technology contains `5g`, `nr` | Mobility · Handover failure (5G - NR) |
| 74 | Handover failure | All | Failure description contains `handover` or Signalling before the failure (log) contains `handover failure` | Mobility · Handover failure (4G - LTE) |
| 75 | Radio link failure | All | Failure description contains `radio link failure`, `t310`, `reestablishment`, `random access`, `rach`, `scg failure`, `scgfailure`, `rrc` or Signalling before the failure (log) contains `radio link failure`, `rlf` | Radio Signalling · Radio link failure |
| 76 | Inter-RAT transition | All | Failure description contains `inter-rat`, `irat`, `redirection`, `4g -> 5g`, `5g -> 4g` or Inter-RAT moves before the failure (log) ≥ 1 | Mobility · Inter-RAT transition |
| | **The coverage and interference the provider reports** | | | |
| 77 | NR coverage reported by the provider | All | Failure description contains `coverage`, `plmn lost`, `no service`, `out of service`, in NR alone | Coverage · DL coverage |
| 78 | 2G or 3G coverage reported by the provider | All | Failure description contains `coverage`, `plmn lost`, `no service`, `out of service`, in 2G or 3G alone | Coverage · DL coverage |
| 79 | Coverage reported by the provider | All | Failure description contains `coverage`, `plmn lost`, `no service`, `out of service` | Coverage · DL coverage |
| 80 | NR uplink interference reported by the provider | All | Failure description contains `ul interference`, `uplink interference`, in NR alone | Interference · UL interference |
| 81 | Uplink interference reported by the provider | All | Failure description contains `ul interference`, `uplink interference` | Interference · UL interference |
| 82 | NR interference reported by the provider | All | Failure description contains `interference`, in NR alone | Interference · DL interference |
| 83 | 2G or 3G interference reported by the provider | All | Failure description contains `interference`, in 2G or 3G alone | Interference · DL interference |
| 84 | Interference reported by the provider | All | Failure description contains `interference` | Interference · DL interference |
| | **The service, once the radio is not the cause** | | | |
| 85 | DNS | Data | Failure description contains `dns` or DNS success < 100 % or DNS time > 1000 ms | Server & Protocol · DNS |
| 86 | HTTP or server error | Data | Failure description contains `http`, `server error`, `200 ok` | Server & Protocol · HTTP |
| 87 | TCP connection | Data | Failure description contains `tcp`, `handshake` or TCP round-trip time > 1000 ms | Server & Protocol · TCP connection errors |
| 88 | No downlink packets | Data | Failure description contains `no dl packets` | Data Transport · No DL packets |
| 89 | Packet loss | Data | Failure description contains `packet loss`, `no answer to ping`, `retransmission`, `no answer to hello` or Packet loss > 5 % | Data Transport · Packet loss |
| 90 | High latency | Data | Failure description contains `latency` or Latency (round-trip time) > 150 ms | Data Transport · Latency |
| 91 | Data transfer timeout | Data | Failure description contains `timeout` | Data Transport · Data transfer timeout |
| 92 | NR cell short of resource blocks | Data | Result contains `cutoff` and Radio measured is not empty and NR DL resource blocks used < 25 % | Capacity · Cell overload |
| 93 | Cell short of resource blocks | Data | Result contains `cutoff` and Radio measured is not empty and LTE DL resource blocks used < 25 % | Capacity · Cell overload |
| 94 | Low throughput reported by the provider | Data | Failure description contains `low throughput` | Capacity · Low throughput |
| 95 | Low throughput with good radio | Data | Result contains `cutoff` and Radio measured is not empty | Capacity · Low throughput |
| 96 | RTP packet loss | Speech | RTP packet loss > 5 % | Data Transport · Packet loss |
| 97 | Voice failure with good radio | Voice, Speech | Radio measured is not empty | End-to-End · Potential E2E Issue |
| 98 | End-to-end trace required | All | Failure description contains `e2e` | End-to-End · E2E trace required |
| | **The calls none of them explains** | | | |
| 99 | Not identified | All | Every call that reaches it | Indeterminate · Unclear |

## Map Levels

**Map Levels** shows every user the levels the [map of a call](#map-of-the-call) and [NQ Maps](#nq-maps) colour each measure by; admins and super-admins change them for the workspace. They colour the RSRP and SINR of the CDR samples and of the [Layer3 Logs](#layer3-logs-on-the-map), and the RSRQ and UE Tx Power of the logs (LTE and NR alike), in their points, grid, legend and signalling timeline.

- **A card per measure** — RSRP (dBm), RSRQ (dB), SINR (dB), UE Tx Power (dBm) — lists its levels, the best first (for UE Tx Power the highest power first), each with its colour, name and lowest value (**From**); it takes the values up to the level above, and the last one every value below. **Takes** shows its range as the legends write it (*−90 to −80 dBm*); a level without a name shows its range alone.
- **Add Level** adds one above the last, **×** removes one (2 to 10 levels per measure), **Default Levels** shows the levels every workspace starts with, and **Save** applies every card (each level must start below the one above, or Save says which does not).
- The maps take the levels when opened again.

| Measure | Default levels |
| --- | --- |
| RSRP | *Excellent* (≥ −80 dBm, dark green), *Good* (−90 to −80), *Fair* (−100 to −90), *Poor* (−110 to −100), *Very poor* (−120 to −110), *Extremely poor* (below −120, dark red): those of the [Network Insights maps](network-insights.md#coverage-and-interference-maps), with Extremely poor |
| RSRQ | *Excellent* (≥ −10 dB), *Good* (−14 to −10), *Fair* (−16 to −14), *Poor* (−20 to −16), *Very poor* (−24 to −20), *Extremely poor* (below −24): the ranges of the KMZ files in the six RSRP levels, with their names and colours |
| SINR | *Excellent* (≥ 20 dB), *Good* (13 to 20), *Fair* (5 to 13), *Poor* (0 to 5), *Bad* (below 0): those of Network Insights |
| UE Tx Power | ≥ 24 dBm, 22 to 24, 15 to 22, 5 to 15, 0 to 5, −10 to 0, below −10: the ranges and colours of the KMZ files, dark red to blue, named by their range |

The Map Levels travel with [NQ Calls Configuration](#nq-calls-configuration) and NQ Call Tracking: exports, transfers (the import preview tells the levels that change), backups and restores take those of the package, measure by measure.

## Ericsson RCA results

**Import Ericsson RCA Results** (admins and super-admins) imports the results of the Ericsson RCA: a CSV (comma, semicolon or tab separated) or Excel file with one row per call:

| Column | Content |
| --- | --- |
| `JOIN_ID` | The NetCheck identity of the call (required; any case). |
| `Auto_RCA_Category_A`, `Auto_RCA_Subcategory_A` | Root cause category and subcategory of the A side. |
| `Auto_RCA_Category_B`, `Auto_RCA_Subcategory_B` | The same for the B side. |
| `RCA_Category`, `RCA_Subcategory` | The first category and subcategory, before its final checks (**Ericsson RCA Initial Category** and **Initial Subcategory**). |
| `RCA_Suggested_Category`, `RCA_Suggested_Cause` | The root category and cause it suggests. |
| `RCA_Evidence` | Why it chose them (**Ericsson RCA Evidence**). |

- **Columns** are matched ignoring case, spaces and underscores, with the separator of the header row; at least one RCA column is needed, and any other column (a confidence, the cell measurements…, up to 80) is kept and shown with the call.
- **`RCA_Summary.csv`** of the Auto RCA output is read as it is: `JoinID` identifies the call, `Final_RCA_Category` and `Final_RCA_Subcategory` are the suggested category and cause, `RCA_Category` and `RCA_Subcategory` the Initial ones (and suggest when a row has no final values), `RCA_Evidence` the evidence, and `UE` puts the rows of the A and B sides in the fields of each side.
- **Several rows of one `JOIN_ID`** are combined: a row without a result (no category, or *UNKNOWN* without measurements of the session) is left out when its side has another; the suggestion is the first that names a cause (the A side first; *Other …* or *UNKNOWN* only when none does); the evidence and other columns keep each row's value, labelled with its side (or its number and category).

### Import the results

1. Open **NQ Analysis Configuration → Import Ericsson RCA Results**. **Download Template** gives an empty file with these columns and an example row.
2. **Choose File**. The preview tells how many results match a call, the columns found, the rows without a `JOIN_ID`, the `JOIN_IDs` with several rows and the categories and causes no Root Category or Root Cause of the [Root Cause Catalog](#root-cause-catalog) matches by name or keywords, with the domain proposed (*Other* results of a technology in RAN, *UNKNOWN* without a domain).
3. Keep **Add them to the Root Cause Catalog with the results** (on by default) so the recommendation can use them.
4. Press **Import**. A new file adds its results and replaces those of the same `JOIN_ID`; results whose `JOIN_ID` is not indexed yet apply as soon as it is.

The dialog lists the imported files with their results, date and user.

> [!WARNING]
> **Replace the previous results** forgets every result imported before, and **Delete every result** removes them all: the calls lose their Ericsson RCA values and recommendations, and keep their selected root cause.

## Previous NQ Analyses

**Import Previous NQ Analyses** brings the analyses made with the previous tool into the follow-up of the calls without losing any of them. Only admins and super-admins import: the other roles open it read-only (a card says so) and can download the template and the equivalences, but not choose a file, upload or forget equivalences, preview or import. The file is a CSV or an Excel workbook (`.xlsx`, `.xlsm`): every visible sheet with a `JOIN_ID` (or `Call Key`) column in its first three rows is read.

### Import the analyses

1. Open **NQ Analysis Configuration → Import Previous NQ Analyses** and **Choose File**. **Download Template** gives an empty file with the columns of the catalog in its order.
2. Optionally review the [equivalences](#equivalences): **Download Equivalences**, change **Maps to** and **Domain**, **Upload Equivalences**.
3. Press **Preview**: it reads the file without changing anything.
4. Choose what happens with the values the calls already have:
   - **Keep them: fill only the empty values (the import note keeps the others)** (default): the file's value goes to the note; a status is set only on calls that follow the Status Rules.
   - **Replace them with the values of the file** overwrites them (after a confirmation).
5. Press **Import Analyses** (the history, the Status Rules and the root domain follow) and read **Import completed**.

> [!IMPORTANT]
> **Preview the file first.** The preview enables the import and tells the sheets read and left out, the calls of the file, how many are found and how many not loaded yet, the columns imported and those kept in the note, the CDR columns before the analysis, the list values, teams, root categories and causes it would add, the domains it would change, the values that are not values of their field, the rows it cannot place, the calls in several rows, how many calls would change and how many comments and notes would be added.

- **Progress:** while previewing or importing, a panel over the dialog shows each step, how far it is and the time.
- **Import completed:** the calls of the file in a bar and cards with their share (updated, already up to date, imported for calls not in the workspace yet, left out), the comments and import notes added, the analyses dated by their analysis, the new catalog values and the values kept only in the note; **See the details** returns to the whole summary and **Done** closes both.

> [!TIP]
> **Importing a file again adds nothing.** A status from the file is set by hand, the catalog gets only the new values some call takes, and a comment or note the call already has is not added again.

### How the rows are read

- **One row, one analysis.** A cell with several `JOIN_IDs` (an analysis of an area) gives the analysis to each. A row without `JOIN_ID` that repeats the CDR is matched by the Operator, Campaign and session of the CDR, as the calls without `JOIN_ID` (the WhatsApp calls) are named.
- **Columns** are matched by the name or key of a field (ignoring case, spaces and underscores) or by the names of the previous workbooks: Final Category/Classification and Final Cause/Subcategory (or Sub Category) are the Selected Root Category and Root Cause; Initial Category/Classification and Initial Cause/Subcategory the Initial ones; Responsible Stream the Team Responsible; Team the Analyst; Analysis Finished the Analysis Status; Status the Planned Status; Evaluation the Implementation Status; Stream responsible the Implementation Team; Action proposal and Site the Implementation Proposals and Implementation Site; Serving Cell, Band and Vendor the fields *… when Failure* (two vendors in one cell, one per line or as Ericsson/Huawei, are Vendor 1 and Vendor 2); Problem / Solution Location the Problem Location; Findings_Bucketization the Findings.
- **CDR columns before the analysis:** a sheet that repeats the CDR export starts its analysis at its Unique ID, Priority or Item (Serial number) column (or the first that fills a field); the CDR columns before it are left out.
- **Comments:** each comment column (Comments, Comment, Comments (only to fill out by BNP NQ stream)…) becomes a comment of its own, after its column name in brackets (but Comments). Findings Comments and Proposed Measure Comments are added after the Findings and the Proposed Measure, after their column name.
- **Own fields:** the Unique ID and the Polygon Area of a data analysis fill their fields.
- **Dates:** **Date last modification** (the Date of a data analysis) dates what the import does to the call — its history, comments, note, the status the rules give it and its Date last modification, which never goes back before a later change made in the tool — so the Progress View shows each analysis in its week. Without it, a call takes its own date (from the CDR) a week later, else the time of the import; a cell that is not a date stays in the note.
- **Import note:** everything else goes to a comment that starts with *Imported from* the file, sheet and row: the other columns (the Item of a data analysis, the repeated NetCheck and Auto_RCA columns, Campaign, Region, City…), a second column for the same field, the values of another row of the same call, the values that are not values of their field, cells a field takes only part of, the values an equivalence renames and the values a call keeps. A column that repeats what the tool has of a call found is left out: Campaign, Region, Operator, City, Vendor and the NetCheck columns when they say what its CDR says (also written otherwise: Q3 for UK_Q3_2025, B for Vendor B, an Operator the Operator Maps name the same), the Auto_RCA columns when they say what its Ericsson RCA says, and a second column with the same value.
- **Calls not in the workspace yet** (a Completed call, or one of a CDR not loaded): the analysis is kept with the identity the call will have and shows as soon as its CDR is indexed.
- **The Excel export** of Non-Qualified Calls is read too (its first row names the sections; its CDR and Ericsson RCA columns are left out), so a file exported, completed elsewhere and imported again keeps its values.

### How the values are checked

Values are checked as if chosen in the call, after the reviewed equivalences:

- **Spellings:** a list value or team written another way (the same letters and digits, such as RF OPT (Hot Spots)_WP2a) takes the name of the catalog, and a new one the spelling most rows use (Not Planned and Not planned are one value).
- **Translations:** Yes and No in Analysis Status are Finished and Pending; No_Vendor_B and No_JoinID Missing in Analysis Status are Invalidated (the note keeps them as written); Solved and Closed in Implementation Status are Implemented and Invalidated is Not Applicable, while its Planned and Not Planned fill the Planned Status (a Status column of the row keeps its own value, the other going to the note); priorities 1 to 5 are P1 to P5; Successful Call-Excluded is No Team; E2E stream is E2E Team (and the domain Core 2G/4G/5G is Core); L800 and N3500 are LTE800 and NR3500; MOC and MTC in the Failed Party are the UE that called or was called, from the Call Direction of the row.
- **New values:** a value missing from a list is added (but to the Failed Party, which keeps its four values), and a missing team is created. A cell with several values (two bands, one per line) gives the first one.
- **Planned FY:** a Planned Date that is a fiscal year, year or quarter (FY28, 2027, Q3 2027) fills the **Planned FY** (FY28, FY27; the first when several), as does the Planned FY column.
- **Root causes:** a Root Category or Root Cause is taken when the catalog has it, or through an equivalence, which can add a new one. The **Domain** of the equivalence (existing, or a new name that becomes a domain) becomes its domain in the catalog, also for an existing value; without one, a new value takes its domain automatically. A call whose Root Category is *Invalidated* gets the Analysis Status *Invalidated* too, and a call with a Root Cause and no Root Category takes the category of the cause.
- **Analyst** (the Team or Analyst column; an Analyst column after it stays in the note) and **Reviewer:** the user account of the equivalence of the value (Analyst → username, Reviewer → username), else the account with that username, else the only account named as it by first and last name (the whole name, or its first part). Otherwise the name is kept, with the spelling most rows use (Raj Kumar and Rajkumar are one), as an **analyst** or **reviewer without account**, listed in the preview under **Analysts without account** (with their rows) or **Reviewers without account**, to be linked in the equivalences or later with [Link Analysts to Accounts](#link-analysts-to-accounts).

### Equivalences

The equivalences of the previous workbooks, as the analysts reviewed them, are built into the import (the **rules of the tool**: teams, root categories and causes with their domains, and the list values those workbooks write otherwise), so every workspace imports without uploading anything.

- **Download Equivalences** gives them as a workbook: without a file, every equivalence the import uses; with a file chosen, every value of its follow-up and list columns, its rows and what it becomes (**Maps to**). The workbook tells how each value was decided (a rule of the tool, reviewed in this workspace, the same value, a catalog value, by the direction of the call, a new value, a keyword suggestion to check, or a new Root Category or Root Cause whose **Domain** to choose), and its Maps to and Domain cells list the values available (a new name can be typed).
- **Upload Equivalences** after changing Maps to (empty leaves the value out of its field, in the note) and Domain: the rows that differ from the rules of the tool are kept in the workspace, before the rules, for its next imports, and travel with its configuration.
- **Default Equivalences** forgets, after confirming, every equivalence uploaded for the workspace.

## Link Analysts to Accounts

**Link Analysts to Accounts** (admins and super-admins apply it) gives the analysts and reviewers without account, brought by the [Previous NQ Analyses](#previous-nq-analyses), their user accounts: the account becomes the **Analyst** of the calls they analyse and the **Reviewer** of those they reviewed, all at once.

> [!TIP]
> **Create the accounts of the analysts and reviewers first**, with their first and last name: the dialog finds each one by username or name.

1. Open **NQ Analysis Configuration → Link Analysts to Accounts**. It lists every analyst and reviewer of the calls without an account, one row per person (names written with the same letters, such as Raj Kumar and Rajkumar, are one, shown with the spelling most calls use and the others below it), with their calls **As Analyst** and **As Reviewer**.
2. Check the **User account** of each person (the users by first and last name). It proposes the only user named as them by username or name (the whole name or its first part, as userb.test or UserB Test for UserB); **Keep without account** leaves their calls as they are.
3. Read **Calls that change** and the line below the list: the calls that will take each account and the teams the accounts will join.
4. Press **Link**. Each call records the change in its history and the Status Rules follow.

- Every call keeps its team: when the team has members and the account is not one of them, the account joins it.
- Every spelling of a person becomes one account in the filters, the table and the exports; the former name stays in the history.
- The calls whose CDR is not loaded yet change too (their imported analysis takes the account, with its history); the line below the list says how many wait for their CDR.
- Once everybody has an account, the list is empty.

## Exports

- **Export Excel**, in the NQ Calls panel, downloads every call of the filters, not only the current page.
- **Export PPT** and **Export Word**, right of the indexing badge and **Reindex** in the Filters panel, download the panels of the filtered calls with the look of the page, in this order: the Executive Summary (indicators and every breakdown on one slide), the NQ Prioritization (the calls next in each queue, the steps of the strategy, Scoring Impact by KPI and the repeated issues, each table on its slides), the NQ Hotspots, Clustered & Time-Window Issues, the NQ Rate by Campaign and Operator, the Failures by Type, Technology & Serving Cell, the Root Cause Sources, the Root Cause Analysis, the Lifecycle & Phases and the Progress Status, with the report selection on the cover (and the period of the Progress View). It is the same document as the Non-Qualified Calls section of a report of [Reporting](reporting.md), composed as [that section](reporting.md#how-a-report-is-composed): small charts and tables share a slide, and Word holds them on portrait pages after the cover and a **Contents** page, exactly as in PowerPoint, a view that does not fit in what is left of a page starting the next one (rendered with LibreOffice; without it, one page per slide). A progress dialog stays open meanwhile.
- **Images:** every panel and its KPIs, charts and tables (a table with its title is one image) download as PNG or copy as a screenshot from the floating buttons at its top right (see [Images of charts and tables](web-interface.md#images-of-charts-and-tables)). The [map of a call](#map-of-the-call), in the call and larger, too, with its legend and the panel of the element chosen, without its buttons.

### Excel workbook

Its **NQ Calls** sheet has two header rows coloured like the meeting workbook: the section of each column (merged, in the colour of the section) and the field (a lighter shade, also for the CDR, Ericsson RCA and derived fields). A darker shade marks the status of each block and the fields read most: NQ Call Status, Analysis Status, Implementation Status and Planned Status, the Selected Root Category and Root Cause, the Failure Comment, the Comments, the Description, the Findings and the Proposed Measure (these three wider), and the `JOIN_ID` and Call Key. The columns:

1. **Call:** `JOIN_ID`, Call Key and CDR first, then Service, Start and End Time, Operator, `Operator_Vendor`, `Vendor_Operator`, Vendor, Campaign, NR Mode, Region, Cluster, City, Technology, Test Name, Session Type (CDR), Direction, Result, Failure Phase, Failure Technology, Cell ID, Latitude, Longitude, CDR Version, Latest CDR and the Non-Qualified samples of Speech calls.
2. Every field marked **Excel** in the [layout](#table-layouts) you see, in the order of [Fields & Sections](#fields-and-sections), under its section (Failure Comment in Failure Details): NQ Call Status followed by **Status Set** (Automatic or By hand); the RCA block ending with the **Root Domain**, the **Recommended Root Category** and **Root Cause**, the **Recommendation Sources** and the **Selected Root Category** and **Root Cause**; **Comments** with every comment, one per line with date, time and author.
3. The CDR columns of that layout, then **Updated By** and **Updated At** (the last follow-up change).

The other sheets are **Speech Samples** (the follow-up of each Non-Qualified sample, when there are any), **Comments** (every comment with its author, edits and deletion) and **History** (every follow-up and field change). Each row starts with the `JOIN_ID` of its call, in the order of the NQ Calls sheet (a Speech sample with its call), then by date.

## Scheduled reports

The reports of [Reporting](reporting.md), generated on demand or on their schedule and emailed, include a **Non-Qualified Calls** section with the panels checked in it (those of [Export PPT and Export Word](#exports)), in PowerPoint and/or Word. Each report chooses its Campaigns and common filters (NR Mode, Operator, Vendor, Region, Cluster and City), the period of the progress timeline, whether to include only open calls and whether the Root Cause Analysis of the analysts counts the suggested root causes.

## Storage and portability

The module stores its data in the workspace database, visible in [Super Admin → Database Management](super-admin.md#database-management):

| Table | Content |
| --- | --- |
| NQ Calls | The indexed NQ rows of every CDR (rebuilt automatically), with their `JOIN_ID` and, for Speech samples, their sample identity. |
| NQ Call Sources | Which CDR revision each indexed CDR comes from, its stage (Final, Weekly or Daily) and the date of its newest call. |
| NQ Call Population | Every call of every CDR, qualified or not, for the NQ rates (rebuilt automatically). |
| NQ Call Population Counts | The latest version of the calls counted by Service, Campaign, Operator, NR Mode, environment, Vendor, host network, site, City and Region, for the panels of how and where the calls fail (rebuilt after the indexing, with a Parquet copy in the columnar store that the panels add up). |
| NQ Call Versions | Which CDR holds the latest version of each Non-Qualified call and how the CDRs differ (rebuilt automatically). |
| NQ Call Latest | The latest version of each Non-Qualified call with its mapped Operator and Vendor and its last cell, read by every panel (rebuilt after the indexing or a change of the Operator and Vendor Maps). |
| NQ Call Tracking | The status (automatic or by hand), team, analyst, root domain, category and cause, and version of each followed-up call and Speech sample. |
| NQ Analysis Fields | The field catalog: section, source, type, values, colours, keywords and options. |
| NQ Analysis Field Values | The value of each field of the analysts for each call and Speech sample. |
| NQ Call Comments | Every comment with author, time, edits and deletion. |
| NQ Call History | Every change of status (by hand or by the rules), team, analyst, root category or cause and field, and every comment edit or deletion. |
| NQ Call Options | The statuses and teams. |
| NQ Team Members | The users of each team. |
| NQ Root Catalog | The domains, root categories and causes with their domains, the category of each cause, colours and keywords. |
| NQ RCA Results | The imported Ericsson RCA results, by `JOIN_ID`, with file, date and user. |
| NQ DT Analyzer RCA Results | The [DT Analyzer RCA](#dt-analyzer-rca) of every indexed call, test and Speech sample: rule, root domain, Root Category, Root Cause and evidence (calculated again automatically). |
| NQ DT Analyzer RCA Learned | While the DT Analyzer RCA [learns from the analysts](#dt-analyzer-rca-rules), the root cause each row learned, with its evidence and the calls it learned from (calculated again automatically). |
| NQ User Table Layouts | The [table layout](#table-layouts) of each user (columns, Excel, column order) and whether they see it or the workspace layout. |
| NQ Call Priority | The [NQ Prioritization](#nq-prioritization) of each call: points lost with their KPIs and level, place, repetitions and campaigns, hotspot, drive (the car or file of its CDR), time-window issue and cluster, whether its failure is in a time-window issue, whether its campaign has its Final CDR scored, Expected Gain, prioritization, step or rule, queue, priority and the priority filled (calculated again automatically). |
| NQ Priority Campaigns | Each campaign and NR Mode of the calls, whether it could be scored (and why not), its methodology, calls and points lost. |

- **Workspace settings** keep the section names and colours, the Status Rules, the DT Analyzer RCA Rules and their learning setting, the Prioritization Rules, the workspace [layout](#table-layouts) and the reviewed equivalences of the [Previous NQ Analyses](#previous-nq-analyses).
- **Nothing stored:** the [map of a call](#map-of-the-call) reads the CDRs, the Network Inventory and the calls when it opens. Its samples, operators and layers are a view of each user, kept in their browser (the radius per call), so they do not travel with the packages.

### NQ Call Tracking

**NQ Call Tracking** — sections, the field catalog with its values, statuses, teams with their members, the root cause catalog with the Require setting and the suggestion rule, the Status Rules, the DT Analyzer RCA Rules, the Prioritization Rules and levels, the Map Levels, the equivalences of the Previous NQ Analyses, the Ericsson RCA results, the [table layouts](#table-layouts) (of the workspace and each user), tracking, comments and history — travels with Admin → Import / Export / Transfer, Full Workspace and Full Environment packages, workspace transfers, and backups and restores. Imports merge it into the destination workspace, so importing the same package again changes nothing and nothing the destination has is removed:

- **Added when missing:** statuses, teams, domains, root categories and causes, fields (and list values) and equivalences.
- **Taken from the package**, also where the destination had its own: the sections, Status Rules, DT Analyzer RCA Rules, Prioritization Rules and levels (the destination calculates its NQ Prioritization again), Map Levels, suggestion rule and Require setting; the section, order, Table, Excel and Summary breakdown of the fields it has (those only the destination has go after them); the workspace layout; and the layout of each user, by username, also of a user the destination does not have yet.
- **Follow-up:** a newer follow-up or field value replaces an older one; comments, history entries and RCA results are added once, and a comment with the text and author of one the call already has (the same analysis imported on both servers) is taken for it, so transfers back and forth never repeat it.

> [!NOTE]
> **The follow-up finds its calls by their identity**, so the destination may load the CDRs later: their calls show their follow-up as soon as they are indexed. Each call travels with its `JOIN_ID` and service, and the import finds the calls that have one by it, even when the package computed their identity otherwise; the calls without a `JOIN_ID`, and the analyses of calls whose CDR was not loaded in the source, keep their identity.

### NQ Calls Configuration

To copy only the configuration to another workspace or server, export or transfer **NQ Calls Configuration** (also a Backup component): everything of NQ Call Tracking but the Ericsson RCA results, follow-up, comments and history. Its import merges it like the configuration part of NQ Call Tracking. Statuses and teams of the destination that the package lacks stay: remove them in **Statuses & Teams** if no call uses them.

## Workspaces of earlier versions

Workspaces, packages and files of earlier versions are completed once, when the workspace first opens with the version that brought each change (App Events records them):

- **Call identity:** the follow-up of the indexed calls moves to their `JOIN_ID` identities, each Speech sample's staying with that sample. Packages exported before then use the former identities.
- **First Analysis Center:** the follow-up is kept and completed: analysis fields join the default catalog (a field named as a default field keeps its values and takes its section and place), root domains and causes become the catalog with the default categories, untouched first default statuses and teams are replaced (Under Investigation → Under Analysis, Pending Information → Open, Resolved and Not Applicable → Closed), statuses chosen before are kept by hand (only Open and the calls not followed up follow the rules), and the default Status Rules are added. Packages of the first version (domains and causes only) are imported into the new catalog.
- **Layout of the Analysis Center:** Failure Details (formerly Failure Event) red, Implementation and Planning green, the Last Cell ID and Failure Comment fields, Serving Cell when Failure proposing the last cell, the Analysis fields in the order of the call panel; the Findings after the Description.
- **Fields added after the field they follow:** the Ericsson RCA Auto RCA fields (Initial Category and Initial Subcategory before Suggested Category, Evidence after Suggested Cause), the NetCheck RCA fields moved before them (descriptions naming the RCA script renamed); the [Previous NQ Analyses](#previous-nq-analyses) fields (Initial Root Category and Cause before Selected Root Category, Priority after NQ Call Status, Analyst, Reviewer and Unique ID after Analyst, Polygon Area and Description before Findings, Implementation Team after Implementation Status, Planned FY after Planned Date); Vendor 2 when Failure after Vendor when Failure, which becomes Vendor 1 when Failure; the [NQ Prioritization](#nq-prioritization) fields after the Priority (Prioritization, Scoring Points Lost and Repeated Issue as columns), the **Prioritization Queue** and **Expected Gain** after the Prioritization Rule; the [DT Analyzer RCA](#dt-analyzer-rca) fields (Root Domain, Root Category, Root Cause, Rule, Evidence), moved before those of the NetCheck RCA once, with its default rules, the 8 Root Categories of its causes (those the catalog lacks, each default cause without a category mapped to its own), and the CDRs indexed again in the background.
- **Renamed:** the NetCheck RCA and Ericsson RCA fields take the name of their source unless renamed (Netcheck Suggested Cause → NetCheck RCA Suggested Cause, Auto_RCA_Category_A → Ericsson RCA Category A, RCA Category → Ericsson RCA Initial Category); priorities 1 to 4 → P1 to P4 (with P5; P6 to P8 added to a list with P1 to P5 when the strategies came); E2E stream → E2E Team (also in Implementation Team) and domain Core 2G/4G/5G → Core, with their calls; Implementation Stream → Implementation Team; Planned FY years and quarters → fiscal years (2030 is FY30), in order. Successful Call-Excluded is no longer a team or Implementation Team (its calls go to No Team).
- **Table columns:** NetCheck RCA Suggested Cause and Ericsson RCA Suggested Cause leave the table (**Columns** shows them again), the Implementation Status joins it after the Analysis Status, and the Priority joins the column of the Prioritization, below it. The column order each browser kept before the layouts becomes your own layout the first time you open the page.
- **Implementation Status** keeps implementation values only: its Planned and Not Planned move to the Planned Status (unless it has another), Invalidated → Not Applicable, Closed → Implemented, Not yet evaluated red.
- **Statuses:** Open is no longer a status but the group of the phase statuses (the rule of the attended calls gives Under Analysis, calls set to Open by hand become Under Analysis and follow the rules again); No_Vendor_B and No_JoinID Missing of the Analysis Status → Invalidated; Status Rules still equal to the old defaults take the new ones, numbered from the end of the pipeline. **Analysis Finished** is added after Under Analysis (In Queue only for Not Attended, Assigned and Under Analysis), and a workspace with the default closing rules takes rules 2 and 5: a call closed only because its Analysis Status was Finished becomes Analysis Finished (`nq_statuses_upgraded`). Assigning a call no longer attends it: the calls only given a team, analyst, reviewer or Priority since their last other change go back to their queues as **Assigned** (a call followed up before the history existed stays attended), Assigned comes after the first status, and the rules giving it are added after the others.
- **Reviewer:** once a text field, it moves to the follow-up: a Reviewer with the username or name of an account takes it, any other name stays a reviewer without account; history, saved filters and equivalences follow.
- **NQ Prioritization:** workspaces before it get the default Prioritization Rules, and their open calls without a Priority take that of their rule once first calculated. Before the strategies: the default strategy Dual Queue (Cities first), unless the Prioritization Rules were changed; Points Lost Based rules of their own (the Custom rules of the first version, also in an NQ configuration file) become steps of Dual Queue (Scoring Based), one per rule and Call Type in their order, with NR Mode, operators, criterion as conditions, Priority and queue (Tracked for Track only), and a last tracked step with the Priority of their tracked calls (the Region and City of a rule have no column; Regions out of scope leave regions out). A step that used **Biggest impact** takes **High impact** (the same calls); steps saved with Time-Window Issues and Cluster alone (AND or OR) took **Hotspots** once when the hotspots came. A list still saved with the default steps of an earlier version takes the current ones; a list you changed keeps its steps, and a new default step joins it only when it lacks the same step. Every workspace took the configuration the NQ team recommends once when it became the default, and the calls already calculated took it at once.
- **Out of scope pairs:** the NR Mode · operator pairs the NQ Prioritization left out before (SA · Three, saved or default) became the NR Modes of their label in the Operator Maps once, and an NQ configuration exported before then gives its pairs to the Operator Maps when imported.
- **DT Analyzer RCA rules:** a workspace whose rules were changed takes each new default rule once, after the default rule before it, and the new conditions of the default rules it kept as they were (a rule changed by hand stays).
- **Serving cell:** the CDRs indexed before the Failures by Type, Technology & Serving Cell panel are indexed again in the background to add it.
- **Comments repeated by transfers** of earlier versions were kept once, the first one.

### Catalog of before v0.12.4

Until v0.12.4 the categories joined the problem with its technology and direction (*Poor Coverage LTE*, *DL Interference NR*, *IMS / VoLTE*…) and some causes repeated them (*Coverage*, *DL interference*). Every workspace goes over to the current catalog once: its catalog takes the current domains, categories and causes (its own values stay), and the Root Category and Root Cause of its calls, their Initial Root Category and Cause, its [DT Analyzer RCA rules](#dt-analyzer-rca-rules), status rules, saved filters and reviewed equivalences take the current values, the technology a former category named becoming the Root Technology of the call:

| Former | Current |
| --- | --- |
| Poor Coverage LTE / NR / 2G/3G (cause Coverage) | Coverage · DL coverage · 4G - LTE / 5G - NR |
| DL Interference LTE / NR / 2G/3G (no cause) | Interference · DL interference · 4G - LTE / 5G - NR |
| UL Interference LTE / NR (no cause) | Interference · UL interference · 4G - LTE / 5G - NR |
| BLER LTE / NR (cause BLER) | Radio Link Quality · High DL BLER · 4G - LTE / 5G - NR |
| Mobility LTE / NR | Mobility · 4G - LTE / 5G - NR |
| Protocol / Server, RAN Performance, RAN Capacity, Core Network, Authentication & Registration, IMS / VoLTE, E2E | The category of their cause (*Packet loss* → Data Transport, *Paging* → Radio Signalling, *SIP 500 Server Internal Error* → Voice Core (IMS)…) |
| IMSI Issue, EPS Fallback, High PRB Utilization, Invalidated, Unclear, No Failure/ Drop, Procedure Overlap, Radio Configuration Inconsistency | Their category with the cause they named (Registration & Authentication · Subscriber identity (IMSI), Fallback & Legacy · EPS fallback failure, Capacity · Cell overload, Invalid · Invalid, Indeterminate · Unclear…) |
| Additional Investigation LTE / NR, Other LTE / NR / GSM | Indeterminate · Further investigation required / Unclear, with their technology |
| Validation (between the first and the second step of this change) | Indeterminate or Invalid, by its cause (*Invalidated* is now *Invalid*) |

The history of the calls keeps the values as written, and the former values are kept in **NQ Root Catalog Migration Backup** (Database Management) to undo it; App Events records how many calls changed. Exports, transfers and backups of before (NQ Calls Configuration, NQ Call Tracking, the catalog workbook and the Previous NQ Analyses) are translated the same way when imported or restored.

## On phones

On a phone the page fits the width of the screen:

- **Sections bar:** floats above the bar of the modules with the NQ Analysis Configuration beside it, showing the section being read between the arrows to the previous and next one (a tap lists every section).
- **Top of the page:** the introduction shows its first two lines (**More**, at its top right, shows it whole); the filters applied are small chips; the call count and **Reindex** share a row; filters and indicators go two per row; the tabs of the NQ Rate, the Root Cause Sources and the call scroll sideways, and the tables of the Designs keep their first column in view.
- **Table:** stays a table, scrolled sideways, with its header and pages, so a call is found at a glance.
- **Call details:** fill the screen and scroll as a whole with their tabs at the top (the chosen tab comes into view), the phases two per row and the names and values in two equal columns; the dialogs of the NQ Analysis Configuration fill the screen with their rows wrapped.
- **Maps:** the [map of the call](#map-of-the-call) and [NQ Maps](#nq-maps) take the width of the screen, the controls above them two per line and the zoom buttons always shown; **CDR Info** and **LOGS Info** go side by side below the zoom buttons (an unfolded card takes the width of the map). A double tap opens the map larger, filling the screen with its note in two lines and a lower signalling timeline, and zooms in there.

## Speed with large workspaces

The page stays quick with tens of thousands of calls, and never waits for the indexing or a CDR being processed:

- the latest version of every call (with its mapped Operator and Vendor) is kept in **NQ Call Latest**, rebuilt in the background after each indexing, so a filter change reads it with the current follow-up;
- the calls of a choice of CDRs are read once per request, the root cause suggestions matched once per combination of CDR values, and the filters counting the suggested root causes found once for all the panels of a filter change;
- only the panels on screen are calculated.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| The map of a call shows no sites | No Network Inventory lists the cells of the networks serving its operator (see [Serving Networks](workspace-config.md#serving-networks)): upload one in [Workspace Management](workspace-management.md). A cell without a site is not in that inventory, or its nearest site is beyond the maximum distance of the Serving Networks. |
| The map of a call has no streets | The tiles of the map chosen in **Map** could not load (no Internet access from the browser to OpenStreetMap, OpenTopoMap or Esri): the call, cells, sites, NQ calls and samples still show; another map type may load. |
| The elevation profile says the elevation could not be read | The browser could not reach the Terrain Tiles of AWS Open Data (`s3.amazonaws.com`): the distance and bearing still show. |
| The page shows no calls | Read the indexing badge of the Filters panel: CDRs may wait to be indexed, or the indexing may be running. Only ready Voice, Speech and Data CDRs are indexed. Then check the chips, or press **Reset Filters**. |
| A call I followed up is no longer listed | The most recent CDR may have it Completed, or no loaded CDR may contain it any longer. Choose its case in **CDR Version** (see [Daily and Final CDRs](#daily-and-final-cdrs)); its follow-up stays in the database. |
| A value is missing from a filter list | The other filters leave no call with it. Remove a filter or press **Reset Filters**. |
| The status of a call does not follow its fields | It was set by hand: choose **↺ Back to automatic**. Otherwise check the order of the [Status Rules](#status-rules): the first rule that matches wins. |
| A call cannot be closed | A field marked **Required to close** is empty, or **Require a root category to close a call** is on and the call has none. |
| My change was refused | Another user changed the call after you loaded it: the list reloads with the newer follow-up; make your change again if still needed. |
| A user is missing from the Analyst list | The team of the call has members and the user is not one of them: add the user in **Statuses & Teams → Members**, or move the call to another team. |
| Ericsson RCA results do not appear on a call | Its `JOIN_ID` is not indexed yet: the results apply as soon as it is. Check the import preview for the results that match calls. |
| The DT Analyzer RCA leaves many calls Not identified | Their CDRs may wait to be indexed again (read the indexing badge), or lack the radio and KPI values of its rules. Read the evidence in the RCA tab and adjust the [rules](#dt-analyzer-rca-rules): each shows the calls it explains. |
| An imported analysis does not appear on a call | The CDR of the call is not loaded yet: the analysis waits with the identity the call will have and appears when the CDR is indexed. |
| The NetCheck RCA values differ from the CDR | Spellings of one value are shown as one (see [NetCheck RCA values](#netcheck-rca-values)); the CDR keeps them as written. |
| The Scoring Impact of a call is Not scored | Hover the badge of the NQ Prioritization & Queues panel: its campaign waits for the Scoring History, has no CDR in the combined CDR tables, or the workspace has no methodology. It is scored once solved (or now with **Recalculate**). |
| The Priority of a call is not filled by its step | The call is closed, someone chose or cleared its Priority by hand, its analysis started with another Priority, it is out of scope or no step of the [strategy](#strategies) takes it, the Priority list lacks the value, or **Fill the Priority of the open calls** is off in the [Prioritization Rules](#prioritization-rules). |

## Tips & shortcuts

The gestures and keys that save time on this page. Use ⌘ instead of Ctrl and Option instead of Alt on a Mac.

**Maps** — the map of a call (in the call and larger), [NQ Maps](#nq-maps) and the [map of a site](#map-of-a-site) share them.

| To… | Do this |
| --- | --- |
| Move the map | Drag it, with the left or the middle button (the middle button moves it even while you hold <kbd>Ctrl</kbd>). On touch: one finger. |
| Zoom the map in the call or in the NQ Maps panel | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + wheel, or pinch the trackpad. The wheel alone scrolls the page, and a short note says how to zoom. On touch: pinch with two fingers (it also moves the map). |
| Zoom the larger map or the map of a site | The wheel alone zooms towards the pointer. |
| Zoom into an area | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + drag a rectangle. |
| Open the map larger | Double-click the map in the call or in NQ Maps (on touch: double tap), or **Map of the call** in the Failure Details and Call Details tabs. |
| Zoom in ×2 | Double-click the larger map or the map of a site (on touch: double tap). |
| Close the larger map or the map of a site | <kbd>Esc</kbd>, or click outside it. |
| See every place again | **Fit**; **−** and **+** zoom out and in. |
| Know which gesture is ready | Hold <kbd>Alt</kbd> and the pointer turns into a ruler; hold <kbd>Ctrl</kbd>/<kbd>⌘</kbd> and it turns into a crosshair. |
| Read an element | Hover it: up to 18 of its values. Where several NQ calls failed at one point, the first line reads *At this point: N NQ calls*. |
| Choose an element | Click it: its panel opens and the distance measured is cleared. A click beside every element keeps the chosen one; its **×** closes it. |
| Move the panel of the element chosen in the larger map | Drag its title. It stays there for the next elements. |
| Move, resize or keep open **CDR Info**, **LOGS Info** or **Legend** | Drag the header to move the card, and its corner to resize it (the bottom right one of CDR Info and LOGS Info, the top left one of Legend). **Restore** puts it back in its place with its own size; the **pin** keeps it open on every map (kept in your browser). A click on the header folds it; a click outside folds it unless it is pinned, keeping the size given while the map is open. |
| Change the map under the layers | **Map**, at the right of the controls above the map. |

**Elevation profile & ruler**

| To… | Do this |
| --- | --- |
| Measure a distance and its bearing | <kbd>Alt</kbd> + drag on the map. The **elevation profile** of the ground between both ends opens over the bottom of the map. Needs a keyboard. |
| Read a point of the profile | Hover the profile: the distance, elevation and slope of that point, marked on the map. |
| Keep only the figures of the profile | Click its header (again to unfold it). |
| Clear the ruler | <kbd>Esc</kbd>, a plain click on the map, the **×** of the profile, or <kbd>Alt</kbd> + click without moving. |

**Layer3 signalling timeline** — below the map of a call with [Layer3 Logs](#layer3-logs-on-the-map).

| To… | Do this |
| --- | --- |
| Follow the UE along the session | Drag along the timeline: the cursor shows where each UE was, and the map follows it. |
| Step through the session | Click the timeline (or reach it with <kbd>Tab</kbd>), then <kbd>←</kbd>/<kbd>→</kbd> for 0.5 s, <kbd>Shift</kbd> + <kbd>←</kbd>/<kbd>→</kbd> for 5 s. |
| Jump to the start or the end of the session | <kbd>Home</kbd> / <kbd>End</kbd>. |
| Remove the cursor | <kbd>Esc</kbd>, or the **×** of the cursor. |
| Find a message or event on the map | Hover its marker: a ring shows its place. Click it to centre the map on it and read its values. |
| Fold or hide the timeline | Click its header to fold it; its **×** hides it, and **Signalling timeline** in **LOGS Info** shows it again. |
| Follow one carrier or cell | **+** of a layer in **LOGS Info** lists it by channel, each with its switch and its PCIs as chips. |

**Call panel**

| To… | Do this |
| --- | --- |
| Close the call | <kbd>Esc</kbd>, a click outside it, or **×**. It asks first when changes are not saved. |
| Go to the previous or next call of the list | **‹** / **›** in the header. |
| Open any call | Paste its `JOIN_ID` (or call ID) in **Go to a JOIN_ID…**. In the **Recent JOIN_IDs** list: <kbd>↑</kbd>/<kbd>↓</kbd>, <kbd>Enter</kbd>, <kbd>Esc</kbd>. |
| Copy the `JOIN_ID` or the IDs of the provider | The copy button beside each one. |
| Show a cell of the call on the map | Click (or <kbd>Enter</kbd>) a cell in **Cells of the call**, below the map: the map centres on its site. |
| Show another NQ call on the map | Click (or <kbd>Enter</kbd>) it in **Non-Qualified Calls around**: the map centres on it. **Open** opens it. |
| Show a test of its drive on the map | Click its row in **Its drive**. |
| Show where a Diagnosis hint points | Click the hint (a site, or the moment of the Layer3 Logs). |
| Post a comment | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Enter</kbd>. |
| Leave only what the analysts fill | **Only the fields the analysts fill**, above the tabs (remembered in the browser). |

**NQ Calls table**

| To… | Do this |
| --- | --- |
| Find calls by their IDs | Paste one or more IDs in **Join ID**, separated by commas, spaces or lines. |
| Sort by a column | Click a header name (or <kbd>Enter</kbd> / <kbd>Space</kbd>); again to reverse it. **Default order** comes back. |
| Move a column | Drag its header onto another one. **Default column order** comes back. |
| Filter a column | The funnel beside its name. <kbd>Esc</kbd> or a click outside closes it. |
| Choose a value in the row (status, team, analyst, root cause…) | Type to search, <kbd>↑</kbd>/<kbd>↓</kbd> to move, <kbd>Enter</kbd> takes the first match (or **+ Add “…”** when nothing matches), <kbd>Esc</kbd> closes. |
| Read the seconds of a call, or the subcategory of a failure | Hover its start time, or its failure. |
| Change many calls at once | Tick their checkboxes, or the header checkbox for the whole page. |
| Open a call | Click its row, or **›** beside its comments. |

**Charts & indicators**

| To… | Do this |
| --- | --- |
| Filter by a card, bar, slice or legend entry | Click it (or <kbd>Enter</kbd> / <kbd>Space</kbd> on a card); click it again to remove the filter. |
| Filter by the root domain of a root category | Click the domain tag on its bar in **Root Cause Analysis**. |
| Read every value of a period | Hover the period in the Progress View timeline; click it to filter the calls detected then. |
| Open a stalled call | Click (or <kbd>Enter</kbd>) its row in **Stalled Open Calls**. |
| Reorder the Priority groups of a strategy | Drag the **⠿** handle, or focus it and press <kbd>↑</kbd>/<kbd>↓</kbd>. |
| Open the configuration | Hover **NQ Analysis Configuration** (<kbd>Esc</kbd> closes it). |
| Save or copy a panel, chart or table as an image | Hover it (on touch: tap it) and use its image buttons. |

**Text editors** — comments and long texts, as in [Ticket Center](ticket-center.md#writing-descriptions-and-comments).

| To… | Do this |
| --- | --- |
| Bold, italic, code, link | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>B</kbd>, <kbd>I</kbd>, <kbd>E</kbd>, <kbd>K</kbd> |
| Strikethrough, highlight | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Shift</kbd> + <kbd>X</kbd>, <kbd>H</kbd> |
| Numbered list, bullets, tasks | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Shift</kbd> + <kbd>7</kbd>, <kbd>8</kbd>, <kbd>9</kbd> |
| Heading 1 to 3, or back to text | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Alt</kbd> + <kbd>1</kbd>–<kbd>3</kbd>, or <kbd>0</kbd> |
| Nest a line or bring it back | <kbd>Tab</kbd> / <kbd>Shift</kbd> + <kbd>Tab</kbd>; <kbd>Enter</kbd> goes on at the same level. |
| Undo, redo | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Z</kbd>, <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Shift</kbd> + <kbd>Z</kbd> |
| Open a link in the text | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + click it. |
| Post the comment, or save the comment edited | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Enter</kbd> |
