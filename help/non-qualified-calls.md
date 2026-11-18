# Non-Qualified Calls

Follow up every call and test that did not complete. Non-Qualified Calls brings the CDR Drive Test follow-up into DriveTest Analyzer as an **NQ Analysis Center**: an executive summary of every Non-Qualified call, a drill-down table of those calls, and a shared follow-up of each one that every user of the workspace sees. Each call is followed through six sections — **General**, **RCA**, **Failure Details**, **Analysis**, **Implementation** and **Planning** — with a Root Category and Root Cause decided from four sources (the NetCheck RCA of the CDR, the Ericsson RCA, the DT Analyzer RCA and the analysts), an NQ Call Status that follows the phases by rules or is set by hand, a responsible team, an analyst and a comment thread. Its panels show which calls to analyse first (the points of the scoring each one loses, the repeated issues and the strategy that fills their Priority and their Voice and Data queues), the lifecycle of the calls, their phases, where they fail and how the root cause sources agree.

> [!NOTE]
> **The calls need no extra input.** Every ready Voice, Speech and Data CDR of the workspace is indexed in the background, and each call keeps its follow-up by its NetCheck `JOIN_ID`. The [DT Analyzer RCA](#dt-analyzer-rca) finds the root cause of every call from the data of its CDR; the Ericsson RCA results and the analyses of the previous tool are optional imports that complete the root causes and the follow-up.

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

A Non-Qualified (NQ) call is any Voice or Speech call, or any Data test, whose result is not **Completed**: for example **Failed** and **Dropped** Voice calls and **Failed** and **Cutoff** Data tests. The result is read from the processed `status` field of the CDR, or from `Call_Status`, `Test_Result` or `Test_Status` when it is missing. Rows without a result are not included.

In a workspace of Umlaut CDRs (see [Benchmarking Providers](benchmarking-providers.md)), a call or test is Non-Qualified when its Umlaut qualifier (**Qualifier**, or the **Browsing**, **Datastream**, **File Transfer** or **YouTube Qualifier** of its service) is **NOT QUALIFIED**: failed, dropped or below the quality thresholds of Umlaut. Ping and DNS tests have no qualifier. A Data test keeps its identity by its `Test_Key` (Filename, Task Name and start), a Voice call and its Speech samples by their `Sequence`. The page names the RCA of the CDR after the provider (**Umlaut RCA** instead of **NetCheck RCA**, also in the exported documents); Umlaut CDRs bring no RCA hierarchy of their own, only the failure of each call (its **Failure Comment**, the Failure Indication of Umlaut), so the root causes come from the [DT Analyzer RCA](#dt-analyzer-rca), the Ericsson RCA and the analysts.

### Indexing

Every ready Voice, Speech and Data CDR of the active workspace is indexed as a background task, shown in the floating background tasks card: the first time the page opens, and then, when a CDR is imported, reprocessed, deleted, given another CDR type (Daily, Weekly, Final or Flex) or included in or left out of the combined tables, at night (between 00:00 and 07:00, server time) once nobody has used the application for fifteen minutes (the pages refreshing themselves do not count) and no import, export, transfer, backup or CDR processing is running, so the indexing, which can take several minutes, never slows the tool down during the day and the page never waits for it. Until then those CDRs show as waiting to be indexed, and their calls keep the values of their last indexing. App Events records each indexing of the night (`nq_calls_reindexed`). Each CDR is read from its [columnar copy](workspace-management.md#columnar-copy-of-the-cdrs) when the copy holds it as it is, only its Non-Qualified rows for their calls, by several processes at once at a low priority, so the users of the application keep the processor.

The card of the indexing, in the floating background tasks card, shows what it does (the CDR it reads or writes, the indexes, the versions of the calls, the DT Analyzer RCA) and how far it is; App Events records how long each phase took (`nq_calls_reindexed`, also for every **Reindex**). **Stop**, on that card, stops it before it writes the indexed calls: they stay as they were, and App Events records the stop (`nq_calls_index_stop_requested`, `nq_calls_index_stopped`). A **Reindex** that a restart stopped while it replaced the indexed calls is put right once the application starts and as the next indexing starts: the indexes of the calls it left out are built again (`nq_population_indexes_restored` in App Events). The CDRs it did not index stay waiting for the night, and a stopped **Reindex** runs at night once the server is idle (the top of the **Filters** panel says so), unless it is launched again before. The indexing writes the calls at its end, in one go: until then the rest of the tool can save its changes as usual. The top of the **Filters** panel shows how many NQ calls and CDRs are indexed, when they were last indexed, and the CDRs waiting to be indexed or the indexing in progress, after which the page reloads its calls.

> [!TIP]
> **Reindex**, only for admins and super-admins, indexes the calls of every CDR again at once, in the background, even when no CDR has changed, without waiting for the night. Their follow-up is kept. Only what changed is written again: the population of the calls of each CDR (every call, qualified or not, which the rates count) and its Non-Qualified calls, which keep their DT Analyzer RCA when they are the same. The rest of the tool keeps working meanwhile: the Reindex prepares what it writes apart and holds the writes of the workspace (a Scoring calculation, a saved comment…) only a few seconds at a time, while the new calls replace the indexed ones.
>
> Choosing CDR columns for a table layout (of the workspace or personal, by any user) does not index the CDRs again: only those columns of the Non-Qualified rows are read from the [columnar copy](workspace-management.md#columnar-copy-of-the-cdrs) of each CDR and added to its calls at once, in the background, in seconds; the columns no layout keeps leave the calls the same way. A CDR that also changed otherwise gets them with its indexing of the night.

### Call identity

Each call keeps a stable identity: its NetCheck `JOIN_ID`, the identifier of each voice call and data test that is the same in the Daily and the Final CDRs. Without a `JOIN_ID`, the identity is its service, Operator, Campaign and test or session identifier (`Test_ID` or `Session_id` for Data tests, `Session_ID_A` for Voice and Speech calls; without one, its subscriber, test name and start and end times). Its status, team, analyst, root category and cause, fields and comments therefore stay with it when its CDR is reprocessed or uploaded again, and when the Final CDR of its campaign replaces the Daily ones. When the same call appears in several CDRs, it is listed once (see [Daily and Final CDRs](#daily-and-final-cdrs)).

Speech CDRs list one row per speech sample: Non-Qualified Calls lists each Speech **call** once (with the number of its Non-Qualified samples), and each sample keeps its own follow-up in the call details.

### NetCheck RCA values

The NetCheck RCA of the CDRs (Failure Classification, Failure Category and Failure Subcategory) is written differently from one campaign to another: the values with the same letters and digits, also with a word in singular or plural, are one value in the filters, the table, the panels and the exports, written with spaces for underscores and the words and capitals most of their calls use (RF_Problems, RF Problems and RF problems are RF Problems, and E2E traces required is E2E Trace Required). The CDRs keep them as written, and a filter saved with another spelling selects the value.

## Daily and Final CDRs

A call can be in a Daily CDR, in several cumulative Daily CDRs and in the Final CDR of its campaign (see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)). It is listed once, with the data of the CDR the combined CDR tables include: the Final CDR of its campaign before its Weekly and Daily CDRs, a Weekly CDR before the Daily ones, then the CDR with the newest calls, unless the **Active?** choice of Workspace says otherwise (a CDR set to Yes comes first, one set to No after the others). A change of that choice, or a Final CDR that replaces Daily CDRs, gives the calls their new version in the background without reading the CDRs again. The **NR Mode** and **Campaign** filters say which CDRs the calls come from; with the **CDR** column of the table shown (see [Columns](#columns)), its filter, among the Additional Columns Filters, chooses CDRs too, and each call then shows the data of the most recent of them.

> [!NOTE]
> **The analysis of a call is shared by every CDR that contains it.** Choosing a Daily CDR, a cumulative Daily CDR or the Final CDR in the **CDR** filter shows the same follow-up.

A badge below the result tells how the other CDRs see the call (hover it for the CDR shown and the latest one):

| Badge | Meaning |
| --- | --- |
| **Changed between CDRs** | Its result or failure is different in another CDR. |
| **Newer version in another CDR** | A more recent CDR that is not chosen in the CDR filter has the call. |
| **Not in the Final CDR** | The call is only in Weekly or Daily CDRs while a Final CDR covers its campaign. |
| **Completed in a newer CDR** | The most recent CDR has the call Completed. These calls are listed only while that CDR is not chosen in the CDR filter, or when **CDR Version** selects them. |

The **CDR Version** filter selects the calls of each case (**Latest version** are the others). **Call Details** lists every CDR that contains the call, Final, Weekly or Daily, with the date of its newest calls and the call's result in it.

> [!IMPORTANT]
> The analysis of a call is lost from view only when no loaded CDR contains it any longer (for example, it is not in the Final CDR and its Daily CDRs are deleted). It stays in the database and comes back if a CDR with the call is loaded again.

## Filters

The **Filters** panel restricts the summary, the panels, the table and the exports together, each group of filters in a card of its own.

Above the filters, **NQ Calls in Scope Only** (a switch) leaves the calls out of the scope of the team out of the whole module, as if they were not there: the table, every panel, chart, count and share (their totals and percentages count only the calls in scope; the [NQ Rate](#nq-rate-by-campaign-and-operator) counts every call in scope, qualified or not), the exports and the values every filter offers. It replaces the filters you would otherwise apply to get the calls in scope, such as Operator, Region and NR Mode. Out of scope are the regions, the operators that are not Focus operators of the [Operator Maps](workspace-config.md#operator-maps) and the operators in an NR Mode they have no network in (the **NR Modes** of their label in the Operator Maps, such as SA · Three), the same ones that leave calls out of the queues of the [NQ Prioritization](#prioritization-rules). The switch is kept with the other filters, shared by every user of the workspace, and **Reset Filters** leaves it as it is; App Events records each change. Beside it, a line tells what is out of scope (such as *Out of scope: Vendor B · Three (SA) · not Focus: EE, O2*), and **Out of Scope** opens those settings: **Regions** and **Operators**, as in the Out of Scope card of the Prioritization Rules (admins and super-admins change the regions; the others can see them). The operators are read only, chosen and grey with their NR Mode out of scope and the reason on hover: the operators that are not Focus operators (**All**) and those whose label has no network in an NR Mode (such as **SA** for Three, out of scope in every module); the dialog links to the Operator Maps, where their Role and NR Modes choose them. **Save** applies the rules to every call at once.


| Group | Filters |
| --- | --- |
| **General Filters** | **NR Mode** (NSA or SA, first: with Campaign it says which CDRs the calls come from), **Campaign**, **Operator**, **Operator_Vendor**, **Vendor_Operator**, **Vendor**, **Region**, **Cluster**, **City**, **Service**, **Technology**, **Test Name** and **Result**, from the indexed calls, and **CDR Version** (see [Daily and Final CDRs](#daily-and-final-cdrs)). |
| **CDR Fields Filters** (blue) | The values as they come in the CDR: the list fields derived from the call (such as **Session Type**), **Last Cell ID** and, in a workspace of NetCheck CDRs, **G_Level_1** to **G_Level_4** (its location levels, such as Drive or Walk and City or Connecting Roads). |
| **RCA Classification Filters** (amber) | What each RCA found, before the analysts, under the name of its RCA: the **DT Analyzer RCA** (Root Domain, Root Category, Root Cause and Rule), the NetCheck RCA of the CDR (**Failure Classification**, **Failure Category** and **Failure Subcategory**) and the **Ericsson RCA** (its categories and subcategories). |
| **Automatic Fields Filters** (violet) | What DT Analyzer fills: **Global Status** (the team's *Analysis Finished*, set by the [Status Rules](#status-rules)), **Status Set** (**Automatic** when the status follows the Status Rules, **By hand** when an analyst chose it), **Follow-up** (Attended, Not attended, Open, Stalled, Closed, With team, Assigned, Commented, With a root cause, RCA identified and RCA not identified: the calls in any of the chosen, also set by the indicator cards of the panels) and the values of the [NQ Prioritization](#nq-prioritization), such as **Prioritization**, **Prioritization Rule**, **Prioritization Queue**, **Scoring Impact**, **Repeated Issue**, **Hotspot ID**, **Time-Window ID** and **Cluster ID**. |
| **Analysis Team Fields Filters** (green) | What the analysts fill: **Root Domain**, **Root Category** (the team's *Final Failure Category*) and **Root Cause** (*Final Failure Subcategory*), **Priority**, **Team** (*Responsible Stream*), **Analyst** and **Reviewer** (an analyst or reviewer without account tagged **No account**) and every list and Yes / No field of the analysts (such as Failed Party, Host Network when Failure, Band when Failure, Analysis Status, Implementation Status or Planned FY), with **Serving Cell when Failure**. |
| **Additional Columns Filters** | The optional columns of the table (see [Columns](#columns)). |
| **Search** | Text in the call fields (Operator, Vendor, Campaign, Region, City, Technology, test, result, failure fields, cell, `JOIN_ID` and the CDR columns of the table), in the fields entered by the analysts and in the comments. |
| **Flags** | **Open calls only**, **Assigned to me** and **Without comments** (and **NQ Calls in Scope Only**, above the filters). |

**Operator_Vendor** is the `<Operator>_<Vendor>` identity, **Vendor_Operator** the same identity as `<Vendor>_<Operator>` (both stay in sync) and **Vendor** the vendor alone; **City** offers the workspace **Main Cities** first. **Unassigned** selects calls without a team or analyst, **Not classified** calls without a root domain or category, **No cause** calls without a root cause and **Empty** the calls without a value. Each card takes the filters of the fields of [Fields & Sections](#fields-and-sections) from their source, in the order of the catalog: a field added to the catalog appears in the card of its source, and a card without filters is hidden. The name the analysis team gives a filter, when it is another, is shown below its own (such as *Responsible Stream* below **Team**).

> [!TIP]
> **Each filter lists only the values of the calls the other filters leave** (its own choice does not count), and the values chosen in it even when no call has them any more: choosing a Campaign leaves in the Operator list only its operators, and the Campaign list still offers every campaign of those operators. Choosing SA in NR Mode leaves in Campaign only the SA campaigns, and takes the campaigns of the other NR Mode out of the Campaign filter (also in filters saved before). The CDR filter offers the CDRs with some of those calls, and CDR Version all its states. The funnels of the column headers list the same values. A filter with more than 300 values (the cells, the sites, the IDs of the hotspots, clusters and time-window issues) lists its first 300 when it opens: type in its filter box to find the others among all of them, or press **Show All** at the end of the list.

Selecting every value of a filter, or none, applies no restriction (**Select All / None** also chooses the values hidden). The filters with a value applied stand out in the colour of the module, their name and their list. Active filters appear as chips at the top of every panel (Filters, Summary, NQ Rate by Campaign and Operator, Root Cause Sources, Root Cause Analysis, Lifecycle & Phases, Progress View and the table), including those set from the Progress View, the Root Cause Analysis and the NQ Prioritization (NR Mode, Call Type, Period, Age of Open Calls, root domain and cause with suggestions, eNB/gNB, Repetition Place); click a chip to remove it. The chip of **NQ Calls in Scope Only** always comes first, darker than the others. The NQ Rate panel dims the chips of the filters it does not use. **Reset Filters** clears them all but **NQ Calls in Scope Only**.

> [!IMPORTANT]
> **The selection is shared.** It is saved in the workspace, so every user finds the last filters applied, in any session and on any device. **Assigned to me** always refers to the user viewing the page. An Operator or Vendor saved with a name the [Operator Maps](workspace-config.md#operator-maps) now show differently keeps selecting its calls with the new name (Vodafone SM selects VF SM once it is mapped to it), as do the NetCheck RCA values saved with another spelling.

## App Events of the module

App Events (in [App Logs](app-logs.md#app-events)) records every action of the users of Non-Qualified Calls, each read as a sentence that tells what was done and to which calls, named by their `JOIN_ID`, operator, campaign, call type and NR Mode:

- **Reading**: the module opened (`nq_page_opened`), the calls listed with their filters, sort and page (`nq_calls_listed`; the same list read again, as after a change of a call, is recorded once), a call opened with its status, team and analyst (`nq_call_opened`), a record of its Layer3 Logs viewed (`nq_call_l3_record_viewed`) and the maps (`nq_call_map`, `nq_call_l3_layers`, `nq_l3_maps`).
- **Follow-up**: each value a call changed, from what to what (`nq_call_update`, such as *Status Not Attended → Under Planning; Status Mode auto → manual*, the Status the rules gave included); the changes of several calls, with how many calls went from each value to the new one and their `JOIN_ID`s (`nq_calls_bulk_update`); the calls taken or assigned in the queues (`nq_queue_take`, `nq_queue_assign`); the comments added, edited (the text before and after) and deleted (with their text and author), and the history deleted.
- **Configuration**: what each save changed: the statuses and teams (added, removed, renamed, colours, members), the fields and sections (their label, settings and the values of their lists), the Status Rules (the rules added and removed), the Root Cause Catalog and its suggestion rule, the table columns and layouts, the Map Levels, the DT Analyzer RCA rules and the NQ Prioritization.
- **Files**: the exports with their filters (`nq_calls_export`, `nq_summary_export_powerpoint`, `nq_summary_export_word`), the catalog workbook exported, previewed and imported, the templates downloaded (`nq_template_download`), and the Ericsson RCA results and analyses of the previous tool previewed and imported.

## Images of the panels

Every panel, and its KPIs, charts and tables (a table with its title, such as a failure card or a section of Progress View, is one image), downloads as a PNG image or copies to the clipboard as a screenshot from the floating buttons at its top right corner (see [Images of charts and tables](web-interface.md#images-of-charts-and-tables)); App Events records each one as `export_nq_calls_image`. The [map of a call](#map-of-the-call), in the call and larger, downloads and copies the same way, with its legend and the panel of the element chosen, without its buttons.

## Sections bar

A bar above the Filters, which stays at the top of the window while you scroll, goes back to the top of the page with its first entry, an arrow, and to each panel of the page: **Filters**, **NQ Hotspots** ([NQ Hotspots, Clustered & Time-Window Issues](#nq-hotspots-clustered-time-window-issues)), **NQ Queues** (NQ Prioritization & Queues), **NQ Maps** ([NQ Maps](#nq-maps)), **NQ Calls** (the [NQ Calls](#nq-calls-panel) table, with the number of calls that match the filters), **Summary**, **NQ Rate** (NQ Rate by Campaign and Operator), **Failures** (Failures by Type, Technology & Serving Cell), **RCA Sources** (Root Cause Sources), **Root Causes** (Root Cause Analysis), **Lifecycle** (Lifecycle & Phases) and **Progress** (Progress View). Every panel stays on the page; the chosen one opens at the top, right below the bar (unfolded if it was folded), and stays there while its data arrives, and the bar marks the panel being read as you scroll. Every panel shows, in a badge below its **Collapse** button, how many calls match the filters (such as *774 Filtered Calls*) and, beside it and standing out, how many of them the queues of the NQ Prioritization list (such as *316 In Queues*: the prioritized calls in a status marked In Queue, by default Not Attended, Assigned and Under Analysis; the tracked calls left out), and the chips of the active filters as soon as they change; while a panel waits for its data it shows an animated **Loading…** bar below them, as Scoring & GAP Analysis while it calculates, over its previous content. A click on a chart filters the calls as usual, and the bar tells how many calls are left. On a narrow window the bar scrolls sideways, keeping the marked panel in sight. Below it, at its right (beside it on a phone), **NQ Analysis Configuration** opens the configuration of the workspace (see [NQ Analysis Configuration](#nq-analysis-configuration)).

Opening the page starts at its top; reloading it (or going Back and Forward, or opening it from the bar at the bottom of a phone) returns to where the page was being read, showing what was in view, dimmed with a loading notice in the colour of the module, until the calls and every panel on screen are drawn there, whatever order they arrive in. Changing the filters (typing a JOIN_ID, removing a chip, clicking a card or a value of a chart), or the page, order or rows of the list, keeps the panel you are using, or else the one you are reading, where it was while every panel on screen is drawn again, so the page never moves to another section; a panel left much shorter (a JOIN_ID leaves a few rows) stays in view, and scrolling meanwhile leaves the page where you take it.

> [!TIP]
> **Folded panels are not calculated.** A folded panel is calculated when it is unfolded, so a change of the filters only waits for the panels that are open.

## Summary

The **Summary** panel is the executive view of the filtered calls: the number of Non-Qualified Calls, how many are open and closed, how many are attended (followed up with a change other than assigning them, or commented), and how many have a responsible team or comments. Breakdowns by Service, Result, Status, Team, Root Domain, Root Category, Root Cause, Failure Classification, Campaign, Operator, Vendor, Region, Cluster and City show where the calls concentrate, six per row and with the same colours as in the one-slide Executive Summary of the PowerPoint and Word (each status, team and root domain in its colour, root categories and causes in the colour of their domain, the other values in a fixed palette). Campaigns read as everywhere in the tool (*UK_Q2_SA_2026* reads *26-Q2-SA*; see [Campaign ordering](technical-considerations.md#campaign-ordering)) and still filter by the full campaign.

Click any bar to drill down: the table shows only that value. Click the same bar again to remove that filter. Fields marked **Summary breakdown** add their own breakdown, in the colours of their values (those entered by the analysts or derived also drill down).

## NQ Prioritization

The **NQ Prioritization & Queues** panel, right below the NQ Hotspots, Clustered & Time-Window Issues, tells which of the filtered calls to analyse first, as the teams plan their analyses by service and NR Mode (for example every SA Voice call, and only the SA Data calls with a repeated issue or a high impact on the scoring). Every Non-Qualified call gets these values, also shown as fields of the call, columns of the table, filters and breakdowns of the Summary (see [Fields and sections](#fields-and-sections)):

| Value | What it says |
| --- | --- |
| **Scoring Impact** and **Scoring Points Lost** | The points of the scoring of its campaign the call loses, and its level: **High**, **Medium**, **Low** or **No impact**; **Not scored** when its campaign cannot be scored yet, **Excluded from Scoring** when it is in a list of [Scoring Excluded Calls](scoring-gap-analysis.md#excluded-calls). **Scoring KPIs Lost** lists the KPIs and environments it loses them in, the most first. |
| **Repeated Issue**, **Repetitions** and **Repeated Campaigns** | Whether the call is in a [cluster](#repeated-issues), and how many Non-Qualified Calls of its operator failed close to it (within the Cluster distance or at its site, **Repetition Place**) recently (the call included) and of how many campaigns. |
| **Hotspot ID**, **Time-Window ID** and **Cluster ID** | The IDs of its hotspot, its time-window issue and its cluster in the [NQ Hotspots, Clustered & Time-Window Issues](#nq-hotspots-clustered-time-window-issues) panel (such as *H-3AFA56*), as the Groups of its header show them; empty when it is in none of 2 calls or more. The Cluster ID is that of its cluster, of its NR Mode as every group, as the rules take it. They are not columns of the table by default: choose them with **Columns**, also for the Excel export. |
| **Prioritization**, **Prioritization Rule** and **Prioritization Queue** | **Prioritized** or **Track only** by the [strategy](#strategies) of the workspace: the step of its lists (such as *Campaign 1 · SA Voice · Cities*) whose conditions the call meets (**No rule** when none does, or when its operator is not one of the operators of the steps), which also gives its **Priority** and the **Voice** or **Data** queue of the team that analyses it (none when the step only tracks it). |
| **Expected Gain** | The scoring points the analysis of the call is expected to recover, which orders the calls of the same step: its Scoring Points Lost once the Final CDR of its campaign is scored, else the points its failure lost in the latest campaign of its NR Mode with a Final CDR, never a [Flex campaign](workspace-management.md#flex-campaigns), localised in one region, cluster or city (empty when there is none: the oldest call then goes first). |

The panel shows, for the filtered calls, a row of cards and three subpanels:

- Cards with the **Prioritized** and **Track only** calls, the calls with a **High Scoring Impact** (and the points the filtered calls lose), the **Repeated Issues** (and their clusters) and the calls **Next to analyse** (in each queue). A click on a card shows only those calls; a second click removes the filter.
- **Strategy**: a tab per list of the strategy, with the filtered calls of each in a badge: **List 1 · Weekly CDRs** (blue; **Weekly & Final CDRs** when the strategy has no list 2), **List 2 · Final CDRs** (purple) and **Outside the lists** (grey: the calls **Out of scope** and those no step takes, **No step**); it opens on the list with the most calls and keeps the tab chosen. Each step, in its order, shows its fields in their colours: its Priority, its Step (its number in a pill of a colour of its own, the same in the queues; a click shows its calls), its NR Mode (SA purple, NSA green), its Call Type (in the colour of its queue), its Area (Cities raspberry, Connecting Roads indigo, Any grey), its Condition (AND, OR and the parentheses in the colour of the module; what the step takes in full on hover), its Operators, the filtered calls it took (where the rules show #Calls), their **Follow-up** in a stacked bar over the calls of the step: **Waiting** (open and not attended yet, by their NQ Call Status; in the colour of the module, with their number beside the bar), **In progress** (attended, still open; amber) and **Closed** (green), with every number on hover, the scoring points they lose in a blue bar, as long as the points of the step against the step that loses the most in the tab (PowerPoint and Word show the open and waiting calls and the points as numbers) and, last, its Queue (Voice blue, Data teal, Tracked grey). A note tells the calls waiting for their prioritization and the campaigns not scored yet, with the reason (the badge at the top right gives it on hover too).
- **Next to analyse**: the **Voice queue** and the **Data queue**, each in a subpanel of its own, one above the other across the panel and in the colour of the queue, with its team, its waiting calls and its calls under analysis in badges (*48 waiting · 4 under analysis*) (the **Unique queue** alone for a strategy of one queue, such as Vodafone Proposal). A prioritized call is in its queue while its **NQ Call Status** is marked **In Queue** in [Statuses & Teams](#statuses-and-teams) (Not Attended, Assigned and Under Analysis by default): first the calls under analysis, with their status in its colour before their owner in **Owner** (such as *Under Analysis · User A.*), then the first calls waiting for somebody (20 by default, set in the rules) in the order its analysts take them (see [Strategies](#strategies)); a call given a team or an analyst (status **Assigned**) still waits in its queue until somebody attends it, an attended call stays while its status is In Queue and leaves the queue with the next one (Analysis Finished, Under Implementation, Under Planning or Closed by default), and a call whose status is set back to Not Attended or Assigned waits in its queue again. Each call is listed with their position, JOIN_ID, Priority (in its colour), its step right after it as the Strategy subpanel shows it, each in a column of its own and in its colours: **Step** (its number, in a pill of a colour of its own, as in the Strategy subpanel), **NR Mode**, **Call Type** and **Condition** (its list, Weekly or Final, and what it takes on hover), operator, campaign (as the [Campaign Maps](workspace-config.md#campaign-maps) name it, such as *2026-Q3-SA*), Owner, Expected Gain, Scoring Impact, **Actions** (Take and Assign) and, last, **Select**. **Tracked**, in the last subpanel and folded, lists the same way the open calls only a tracked step takes, in no team queue. An empty queue or list says so in a label (such as *No call is waiting in the Voice queue.*). Each table fits its card without scrolling sideways: the JOIN_ID always on one line, and when the card is narrow the other columns and the headers go on two lines. A click on a call opens it. The queues chosen in **Queues by hotspots** (the Data queue by default) list their **hotspots** instead of their calls: each hotspot with at least the **Minimum hotspot size** of failures of the queue among the filtered calls (3 by default; only the first ones up to Next to analyse are listed, and the badge then tells how many of them, such as *20 of 29 hotspots*, beside the waiting calls of all its hotspots, such as *143 calls in hotspots*; the calls of a hotspot are analysed together, so a hotspot with calls prioritized in the queue takes along its **Track only** calls, which keep their Priority, count in its size and Waiting, are taken or assigned with it and are no longer listed among the tracked calls; a hotspot with prioritized calls in two of these queues goes to the one with most of them), in the order of its first waiting call, with its position, Hotspot ID with its sites and period below it, Priority, Step, NR Mode, Call Type and Condition (of that first call), operator, campaign, **Waiting · Owner** (its calls waiting of its calls in the queue, such as *3 of 5*, and below who has the waiting ones, each analyst, else each team, with how many calls, such as *2 · User A.* (an analyst by first name and initial, the whole name on hover; two at most, the others in *+2 more* on hover, *No owner yet* when nobody has them), how many of its calls are *Track only*, and its calls in the queue that no longer wait: *in progress*, attended and still open, and *closed*), Expected Gain (of its waiting calls together), Scoring Impact (the highest), Actions and Select; a click on its ID filters the calls, and the queues, by the hotspot, as in [NQ Hotspots](#nq-hotspots-clustered-time-window-issues). The other waiting calls of the queue, out of such a hotspot, are listed one by one in **Individual failures**, folded below its hotspots.
- **Who takes each call**: above the queues, four views with their waiting calls, and how many of them are in each queue (such as *All · 342 (Voice 117 · Data 225)*): **All**, **Unassigned** (no team and no analyst), **My team** (the calls without an analyst of the teams you are a member of: their team, or the team of their queue when they have none) and **Assigned to me** (you are their analyst); the panel remembers the view on this browser. **Owner** tells who has each call: its analyst (in bold), its team, or the team of its queue (in italics) while it has none. **Take** (editors, a green button) asks first and then makes you the analyst of a call without one (on a hotspot, of every waiting call of it without an analyst), and the calls take your team: your only team, or the one you choose in the confirmation when you are a member of several (a user of no team leaves each call its team); a call another analyst took a moment before is left as it is and a message names them. **Assign** (admins, a purple button), beside Take, opens a dialog to give that call, or the waiting calls of that hotspot, a team and / or an analyst (a team with members offers only them; *Keep* leaves what each call has, *No team* / *No analyst* takes it away). To assign several at once, admins tick them in **Select**, the last column (**All** in its header ticks or clears every row of the table, only the calls of the rows listed: its tooltip tells how many), and **Assign** them from the bar above the queues. An assigned call keeps waiting, in the status **Assigned**, until somebody attends it. App Events records every Take and Assign.
- **Scoring Impact**: the calls of each level, and the scoring points the calls lose in each KPI and environment.

**Recalculate** (`user-editor` and above) calculates every value again in the background; **Prioritization Rules** opens the rules. Above them, **Strategy** chooses the strategy the module uses (admins and super-admins, as the Prioritization Rules; the others see it greyed out): after a confirmation every call takes its step, queue and Priority at once (the calls in analysis keep their Priority), the other settings stay as saved, and App Events records the change.

### NQ Hotspots, Clustered & Time-Window Issues

The **NQ Hotspots, Clustered & Time-Window Issues** panel, right below the Filters and before the NQ Prioritization & Queues (and in the sections bar as **NQ Hotspots**), groups the filtered calls that fail close to each other. It comes with the data of the NQ Prioritization, so unfolding either panel reads both. On top, the criteria of the [Prioritization Rules](#prioritization-rules) that make the groups, as chips: Time window, Time-window distance, Cluster distance, Hotspot join, Cluster size and Cluster period. Every group (hotspot, time-window issue and cluster) is of one NR Mode, whatever the filters: the failures of NSA and SA have other causes and are analysed apart. Then the call types, and three tables with the same columns and widths, each with the calls it holds in a badge beside its title (the most calls first, the table scrolling inside the panel, also sideways on screens too narrow for its columns, so that no word is split; when From and To are narrow, the time goes below the day; PowerPoint and Word keep the 25 with the most calls of each, in the same order):

- **ID**: **Hotspot ID**, **Time-Window ID** or **Cluster ID**, a short code that stays the same whatever the filters (*H-*, *T-* or *C-* and the start of the key of its first call, such as *H-87BB7D*), with what identifies the group: its sites (the site of most of its calls, *+N* when they are at more) for a cluster, its period for a time-window issue, both for a hotspot, the sites on the first line and the period below. A click on it shows the calls of the group (the **Hotspot**, **Time-Window Issue** or **Clustered Issue** filter, one group at a time: it replaces the group filtered before) and takes the page to the [NQ Calls panel](#nq-calls-panel), kept at the top while they load; another click removes the filter and stays where it is. Every call keeps the IDs of its groups in its **Hotspot ID**, **Time-Window ID** and **Cluster ID** fields (see [NQ Prioritization](#nq-prioritization)), to show as columns, filter and export to Excel.
- **Operator**, **NR Mode** and **Campaign** (each with its calls when there are several), **Site(s)**, **From** and **To** (when its first and last call started: the day, the month in letters and the time, *20 Nov 16:18*, the full date on hover), the filtered **Calls** of it, their **Voice / WhatsApp / Data** calls in a stacked bar (Voice blue, WhatsApp aqua green and Data a darker green) with their numbers, the scoring points lost, the open calls and the main root category.

Each column of the tables filters like Excel: its **▾** lists its values (with a search, **Select all** and **Clear**; **From** and **To** by year, month and day), **Apply** keeps the rows with the values checked, and the header of a filtered column is marked. The filters are kept in your browser for each table of the workspace, also when the data of the panel is read again.

The tables:

- **Hotspots (Clustered OR Time-Window Issues)** (*AND* with the AND join): every [hotspot](#strategies).
- **Time-Window Issues**: every [time-window issue](#strategies) (failures of the same operator, NR Mode, campaign and drive, each within the Time window and the Time-window distance of the one before).
- **Clustered Issues**: every [cluster](#repeated-issues): calls that fit in a circle whose radius is the Cluster distance (with the calls of the campaigns of its Cluster period), so that a long series of failures along a road makes several clusters, each one row.

Each table lists its first 100 rows, with **Show All** below them to list every one; the filter of a column lists every row too, as it looks at all of them.

The more general tables come first. With the OR join the Hotspots come first: they hold the time-window and the clustered issues together (with one NR Mode filtered and a Cluster period of 0, exactly those), each time-window issue and each cluster of a campaign falls within one hotspot, and a hotspot can hold several time-window issues and clusters. With AND the Time-Window and the Clustered Issues come first and the Hotspots last: every failure of a hotspot is in a time-window issue and in a cluster (with a Cluster size of 2), and each hotspot falls within one time-window issue. The Time-Window and the Clustered Issues never contain one another (a failure can be in a time-window issue without a cluster, and the other way round): the one with more calls goes first, and with the same calls the one that groups them in fewer rows.

### Scoring Impact

The points a call loses are those of the scoring of its campaign, as Scoring & GAP Analysis scores it (see [Points Lost](scoring-gap-analysis.md#points-lost)):

1. Each campaign of each NR Mode is scored from the Scoring History over the CDRs the combined CDR tables include, with the methodology that applies to the campaign, split by operator.
2. For every KPI that counts tests (the ratios: call success, transfer success, POLQA below 1.6, throughput above a threshold…), the points the operator loses in the environment of the call (Drive - City, Drive - Connecting Roads…) are shared equally among the tests that miss the KPI, as the Points Lost Map shares them.
3. A call holds the share of every KPI it misses (the samples of a Speech call add up). The averages, medians and 90th percentiles (setup time, POLQA MOS, P90 throughput) are not shared among the calls, as a failed call has no value in them.

Within its campaign, operator and service, the calls that hold the first half of the points lost are **High**, those up to 80% **Medium** and the others **Low** (calls with the same points share their level); both shares are set in the rules. The calls in scope are compared only with each other: those [out of scope](#strategies) (the Regions, the operators that are not Focus operators and the operators in an NR Mode their label in the Operator Maps has no network in) are compared among themselves and never change the levels of the calls in scope, in the Scoring Impact of the calls, in the conditions of the steps and in **#Calls**, which therefore agree. Changing the shares or the Out of Scope settings applies the levels at once. A campaign is **Not scored** while the Scoring History is still indexing its CDRs, when no CDR of it is in the combined CDR tables or when the workspace has no methodology.

### Repeated issues

A call is a **Repeated Issue** when it belongs to a cluster: at least two Non-Qualified Calls of its operator (the **Cluster size** of the rules, the call included) that started within a circle whose radius is the **Cluster distance**, in its campaign and the campaigns of the **Cluster period** before it (none by default; in campaigns: the campaigns of a quarter, SA and NSA together, count as one, by the quarter their name gives, *UK_Q3_2026* is 2026 Q3 whenever the call ran, and by the date of the call only when the campaign does not name it; a quarter without a campaign is skipped), whatever their service (a Voice and a Data failure at the same site count), of the NR Mode of the call (as the steps of the strategies, each of one NR Mode, take them, and as the hotspots and the time-window issues are counted: no group mixes two NR Modes), at any time. The clusters join the nearest calls first, then the next nearest, and so on, while the calls joined still fit in that circle (the circle is not centred on any call): a cluster never chains along a road, a long series of failures makes several clusters that meet at the widest gaps between their calls, and calls at the same site join only within the Cluster distance too. Its **Repetitions** count the calls within the Cluster distance of it or at its site (its Repetition Place), which can be more than its cluster holds. The Ping tests and the calls [out of scope](#strategies) (its regions, the operators that are not Focus operators and the NR Mode · operator pairs of the NR Modes of the Operator Maps) are left out of the clusters, the hotspots and the time-window issues: they are in none and make none. The place of a call is the site of the cell where it ended: the site ID and host network of its eNB or gNB in the [Network Inventories](workspace-management.md#network-inventories) and cell mappings of the workspace, in a network that serves its operator (its own first, as the [Serving Networks](workspace-config.md#serving-networks) of the Vendor Mapping say) and within their maximum distance of the call, since an eNB or gNB number is only unique within its network (each node takes the sites of the newest snapshot that lists it). Else it is the site that served its start (the serving-cell [Vendor Mapping](workspace-management.md#vendor-mapping), with its host network), the same place when it is the same site, else the eNB or gNB of its last cell, else a spot of the **Cluster distance** around where it started (where the panel lists it). Calls without a date count in every period near them. The steps of the strategies call this condition **Cluster**.

The **Cluster distance** follows the network: a city site serves a few hundred metres, a road site several kilometres. It is half (by default) the **inter-site distance (ISD)** of the sites nearest to where the two calls started, the larger of the two (the ISD of a site is the mean distance to its 3 nearest sites in service of its network, from the newest snapshot of the [Network Inventories](workspace-management.md#network-inventories) of the networks that serve the operator of the call, as [The network around the call](#the-network-around-the-call) measures it; the calculation keeps the ISD of each call). Without an ISD (no Network Inventory, or no site near), it is 250 m in cities and 1 km on connecting roads (when either call is on one), and a call without a cell is listed at a spot of the cities distance. The time-window issues take a distance of their own the same way (see [Strategies](#strategies)).

### Strategies

**Prioritization Rules** (in the NQ Analysis Configuration menu and the NQ Prioritization & Queues panel) sets the **Strategy** of the workspace; only admins and super-admins change it. **Dual Queue (Cities first)** is the default; **Dual Queue (Roads first)** differs from it in the place of SA Voice (Connecting Roads before Cities); **Dual Queue (Scoring Based)** (Points Lost Based before, the Custom rules of the first version) orders every call by its impact level, and **Vodafone Proposal** puts SA before NSA and Voice before Data with the Data calls of a cluster, then every other call, in one **Unique queue**, both with list 1 alone (see [Prioritization Rules](#prioritization-rules)). The four have steps, edited the same way. **New Strategy** adds a strategy of your own, a copy of the strategy shown, with its **Name** ready to change; **Rename Strategy** changes the name of the strategy shown, any of them; **Delete Strategy** deletes one of your own (the four strategies of the application cannot be deleted). Strategies of your own, the names, their steps and list 2 are saved with the other settings, travel in the NQ configuration and are recorded in App Events when they are created, renamed or deleted.

Every call takes a step of one of two lists and a queue: Voice and WhatsApp calls go to the **Voice queue**, Data calls to the **Data queue** (in Vodafone Proposal every call goes to its **Unique queue**, as its steps say), and each analyst takes the top call of the queue of their team. Admins and super-admins change every field of each step of every strategy, in the columns of the dialog, which shows one list at a time: the switch above the table chooses **Weekly CDRs** (list 1) or **Final CDRs** (list 2). **Use List 2 for Final CDRs** (on by default, off for Dual Queue (Scoring Based) and Vodafone Proposal) is chosen for each strategy: off, list 1 orders every call, also once the Final CDR of its campaign is scored, and the Final CDRs list is not used: the dialog then shows list 1, also when you switch to such a strategy from the Final CDRs list of another one.

| Column | What it sets |
| --- | --- |
| **Priority** | P1 to P8, each in its colour from red (P1) to grey (P8); by default the step is the Priority, as in the tables below. The steps of one Priority are grouped under it, in the order they are tried: changing it moves every step of the group. The ⠿ before it moves the whole group: dragged onto another Priority (its rows marked), the two swap, keeping the order of their steps (P2 dropped onto P3: the steps of P2 take P3 and those of P3 take P2); onto a Priority without steps, the group takes it; with the arrow keys, it swaps with the Priority above or below. |
| **Step** (⠿ n ×) | The place of the step in its list, filled from the order of the rows, which names its Prioritization Rule (such as *Campaign 3 · SA Voice · Connecting Roads*), between its handle and the red **×**, which deletes it (a default step comes back with **Default Rules**; **+ Add step**, under the table, adds one at the end of the list, at most 20 per list). The handle: drag it before or after another step (or move it one row with the arrow keys) to change its place, and its Priority when the other step has another one; while a step is dragged, the Priorities without steps show to drop it there. The place of a step gives the number of its Prioritization Rule (such as *Campaign 1 · SA Voice · Cities*). |
| **NR Mode** | **SA**, **NSA** or **Any**, each in its colour (SA purple, NSA green, Any grey). |
| **Operators** | By default, the Focus operators of the [Operator Maps](workspace-config.md#operator-maps) by name: the SA steps take those that use SA, the NSA and Tracked steps those with Non-Qualified Calls (in the UK, `VF` in the SA steps and `VF & Three` in the others). An operator uses SA when at least 10 % of its Non-Qualified Calls of the SA campaigns ran on NR SA (NR SA or NE-DC in their technology); an operator without SA, such as Three, drives them on LTE. The list offers **Focused Operators** first (every Focus operator, or every operator when the workspace has none), then the operators of the workspace. Focused Operators stands alone: while it is chosen, the other operators are cleared and cannot be chosen; several operators show joined with ` & ` (Focused Operators reads *Focused* in the column, the full values show on hover). |
| **Call Type** | **Voice**, **WhatsApp**, **Data** or **Any** (Ping tests too), in the colour of the queue of its step (a WhatsApp step of the Data queue is teal). |
| **Area** | Where the calls failed, from their environment: **Cities**, **Connecting Roads** (roads and highways) or **Any**. |
| **Condition** | The conditions the calls meet, chosen one by one, the same for every Call Type and both lists, each in a colour of its own (here, in the list of Conditions and in the steps of the panel: the impact levels as the Scoring Impact, High red, Medium orange and Low blue; Every call green; Cluster grape, Hotspots pink, Time-Window Issues cyan, Drops brown, Setup failures slate): **Every call**; **Time-Window Issues** (another failure of the same drive, the car, started within the Time window and the Time-window distance, whatever its call type); **Cluster** (a [repeated issue](#repeated-issues): the operator failed within the Cluster distance of the call or at its site in 2 or more calls of its campaign and those of the Cluster period before it, in any drive); **Hotspots** (2 or more failures close to each other in time and distance, whatever their call type); **High impact**, **Medium impact** and **Low impact** (or none), the level of the call by its **Expected Gain** within its campaign, operator and service (the first High share, up to the Medium share, the rest): during the campaign the Expected Gain is what its failure lost in the Final CDR of the latest campaign of its NR Mode, once the Final CDR of its campaign is scored its own points (the Scoring Impact column of the calls keeps the points of the CDRs scored so far); **Drops** (calls dropped, data tests cut off) and **Setup failures** (calls and tests that failed before being established). During the campaign the repetitions are those known so far, from the CDRs indexed; a step that used **Biggest impact** (of the first versions) takes **High impact**, which now takes the same calls. The conditions follow one another on one line while they fit, each joined to the one before by **AND** or **OR** (**+** adds one, joined by OR until you choose AND; **×** removes it). AND goes first: *Time-Window Issues AND Hotspots OR High impact* takes the time-window issues of a hotspot and the calls with a High impact. **AND (** and **OR (** start a group, one level of parentheses shown around its conditions: *(High impact OR Medium impact) AND Cluster* takes the calls with a High or Medium impact of a cluster. **Every call** stands alone: chosen, it clears the other conditions. The **Conditions** card, under the steps, explains each one, and so does a condition on hover. A tag tells what each condition is based on: **Scoring-based** (the impact levels; the scoring of the campaign itself is not stable during the campaign), **Position-based** (Cluster), **Position & time** (Hotspots), **Time-based** (Time-Window Issues) or **Result-based** (Drops, Setup failures). See [Strategies](#strategies) for how these conditions compare with the hotspots. |
| **#Calls** | An estimate for information, to design the steps and the Voice and Data queues: how many calls the step would take in the latest campaigns with their Final CDR (the latest closed campaign of each NR Mode), counted again as you edit the steps: list 1 as during the campaign, list 2 as once the Final CDR is scored (the impact levels of both by the own points of those calls, as their Final CDR is scored; during a real campaign list 1 takes the estimate from the Final CDR before). The calls out of scope are left out; hover the column title for the campaigns, named as the [Campaign Maps](workspace-config.md#campaign-maps) say (such as *2026-Q3-SA*). |
| **Queue** | **Voice**, **Data** or **Tracked** (its calls are only tracked), in a solid colour: Voice blue, Data teal, Tracked grey. |

The **Calls per Queue** card, at the top right above the levels, draws a column per Priority of the Voice and Data queues (or of the Unique queue of a strategy of one queue) (the Priorities of their steps in the list shown) with the calls its steps take, the sum of their **#Calls**, on top, in the colour of the Priority and grouped above the queue and its total; its note names the list and the latest closed campaigns it estimates on, the calls of both queues together follow in bold (*Voice + Data: 284 calls*), and it is drawn again as you edit the steps. **Calls outside the Voice and Data queues**, folded below the chart, lists them in bullets with their names: the **Tracked** calls by kind (such as the Data calls no Data step takes, the Ping tests and the Excluded Calls) and by operator and NR Mode (such as *Three NSA*), the calls **Taken by no step** by operator and NR Mode (calls in scope that no step takes) and those **Out of scope**, in no queue and not tracked, by region (such as `Vendor B`, every operator), by operator that is not a Focus operator (such as *SA · EE*) and by NR Mode · operator pair of the NR Modes of the Operator Maps (such as *SA · Three*, whose calls there are not real SA calls).

The steps of a list are tried by Priority and in their order. The **Queue order** card, under the table, and the **Conditions** card below it, which explains every condition, are folded by default, an ⓘ before their title (click it to unfold them). **Queue order** sums up how each queue takes its calls: by Priority, then the newest campaign, then the step (the row above first), then the highest Expected Gain, then the oldest call; a call of a newer campaign goes before one of an older campaign whatever its step, and a call that meets two steps takes the upper one. A call of an SA campaign takes its SA step when the step takes its operator; else, as the calls of an operator without SA such as Three, its NSA step when that one takes it; a call that no step takes is tracked when a Tracked step takes it, and enters no queue otherwise (for example, SA steps with `VF` only and NSA steps with `VF & Three`). App Events records each change of a step with its fields before and after.

The **Out of Scope** card, above the steps (admins and super-admins; the **ⓘ** beside its title unfolds what it does), lists what is out of the responsibility of the team: their calls enter no queue and are not tracked, in every strategy. **Regions**: `Vendor B` until the admins choose others; the calls without a Region are always out of scope when the calls of the workspace have Regions (nothing tells that they are in a region of the team), shown as *No Region* beside the **Out of Scope** button. **Operators**: the operators of the [Operator Maps](workspace-config.md#operator-maps) out of scope (by their label), read only: they show chosen and grey, each with its NR Mode out of scope under the list, a note below that tells why and the reason on hover, and they cannot be changed here. Only the Focus operators can be in scope: the other operators are always out of scope, in both NR Modes, with **All** (such as *SA · EE* and *NSA · O2*; a name of the CDRs without a label is not a Focus operator either); without any Focus operator, every operator can be in scope. An operator without a network in an NR Mode, as the **NR Modes** of its label in the Operator Maps say, is out of scope in that NR Mode, in every module of the workspace and not only here: Three has no SA, so its calls of the SA campaigns are not real SA calls but NSA calls its NSA campaigns already have (*SA · Three*); the Operator Maps suggest it for an operator under 10 % of whose Non-Qualified Calls of the SA campaigns ran on NR SA. The explanation of the card links to the labels of the Operator Maps, where their **Role** chooses the Focus operators and their **NR Modes** the NR Modes out of scope. The NR Mode · operator pairs the NQ Prioritization left out of scope before (SA · Three, saved or by default) became the NR Modes of their label once, and an NQ configuration exported before then gives its pairs to the NR Modes of the Operator Maps when it is imported. The operators excluded in the Operator Maps (such as `Lebara`, `VF SA` and `VF VoNR`) are not in the list: as in the rest of Non-Qualified Calls, their calls count nowhere, neither in the NQ Prioritization (they get no Scoring Impact, cluster, hotspot or step) nor in **#Calls** and **Calls per Queue**. Their Prioritization Rule tells why (*Out of scope · Vendor B*, *Out of scope · No Region*, *Out of scope · NSA · EE*, *Out of scope · SA · Three*), they take no Priority, and the panel counts them apart as **Out of scope**. The **Out of Scope** button above the filters edits the same settings, and **NQ Calls in Scope Only** leaves these calls out of the whole module (see [Filters](#filters)).

**List 1** orders the calls of a campaign while its Final CDR is not scored, by what each call says about itself, which never changes as new Daily or Weekly CDRs arrive: its NR Mode, whether it is a Voice, WhatsApp or Data call, and where it failed (Connecting Roads and highways, else Cities, from its environment).

| Priority (default) | Dual Queue (Cities first) | Dual Queue (Roads first) | Queue |
| --- | --- | --- | --- |
| P1 | SA Voice in Cities | SA Voice on Connecting Roads | Voice |
| P2 | SA Data: Hotspots (a failure of a hotspot: with the OR join, in a time-window issue or in a cluster) | SA Data: Hotspots | Data |
| P3 | SA Voice on Connecting Roads | SA Voice in Cities | Voice |
| P4 | SA WhatsApp | SA WhatsApp | Voice |
| P5 | NSA Voice | NSA Voice | Voice |
| P6 | NSA Data: Hotspots | NSA Data: Hotspots | Data |
| P7 | NSA WhatsApp | NSA WhatsApp | Voice |
| P8 | Tracked: the other data failures (not taken by a Data step), Ping tests and Excluded Calls | Tracked: the other data failures (not taken by a Data step), Ping tests and Excluded Calls | — |

A failure is in a **time-window issue** when another failure of the same operator, NR Mode, campaign and drive started at most the **Time window** before or after it (6 minutes by default) and at most the **Time-window distance** from it, whatever its call type (the Ping tests and the calls out of scope stay out). The Time-window distance is 0.8 times (by default) the inter-site distance (ISD) of the sites nearest to the two failures, the larger one, as the [Cluster distance](#repeated-issues) measures it, so that a car that drove far between two failures, from one city to the next, breaks the time-window issue; without an ISD it is 500 m in cities and 2 km on connecting roads (when either failure is on one), and a failure without a position follows the one before. The drive is the car: the measurement system of the CDR (`Measurement_System` of a data CDR, `System_A` of a voice CDR), else its file (`File_ID`, `File_ID_A`, one device); the failures of the other cars that measure at the same time elsewhere never follow one another, and a failure of a CDR that gives neither is never in one. A **hotspot** holds 2 or more failures of the same operator, NR Mode and campaign, whatever their call type (4 Data failures and 1 Voice failure make a hotspot of 5; the Ping tests and the calls out of scope stay out), that its [clusters](#repeated-issues) and time-window issues make together: with the **Hotspot join** OR (the default), every failure of a cluster or a time-window issue that shares a failure with it, their envelope, so a hotspot holds the time-window issues and the clusters of its campaign that touch each other; with AND, the failures of the same cluster and the same time-window issue, where they meet. A step with *Time-Window Issues OR Cluster* takes the failures of the hotspots of OR, and also those whose cluster holds calls of the Cluster period before their campaign (with a Cluster period of 0, the default, exactly the same); a step with *Time-Window Issues AND Cluster* takes a failure of a time-window issue that is in a cluster too, which a hotspot of AND takes only when another failure shares both.

**List 2** orders the calls of a campaign once its Final CDR (a Final CDR of its type in the combined CDR tables, see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)) is scored, by their real impact, the same in the four strategies of the application (Dual Queue (Scoring Based) and Vodafone Proposal use list 1 alone by default, until their **Use List 2 for Final CDRs** is on):

| Priority (default) | Steps |
| --- | --- |
| P1 | 1 · SA Voice with a High impact |
| P2 | 2 · SA Data with a High impact |
| P3 | 3 · SA WhatsApp with a High impact |
| P4 | 4 · SA Voice with a Medium impact · 5 · SA WhatsApp with a Medium impact · 6 · every other SA Voice call · 7 · every other SA WhatsApp call |
| P5 | 8 · NSA Voice |
| P6 | 9 · NSA Data with a High impact |
| P7 | 10 · NSA WhatsApp |
| P8 | Tracked: the other data failures (not taken by a Data step), Ping tests and Excluded Calls |

> [!IMPORTANT]
> **Inside a step, the calls with the highest Expected Gain go first, then the oldest.** The Expected Gain of a call of list 1 is what its failure lost in the Final CDR of the latest campaign of its NR Mode, never a [Flex campaign](workspace-management.md#flex-campaigns) (without one, the oldest call goes first); that of a call of list 2, its own Scoring Points Lost. Each queue takes its calls by Priority, the newest campaign first, then the step.

The Priority of the open calls is filled with the Priority of their step (see **Fill the Priority of the open calls** below) and never changes once the analysis of the call has started (its NQ Call Status is no longer the first one): a new strategy, or the Final CDR of its campaign, only re-orders the calls nobody has started. Changing the strategy is recorded in App Events with the one before and the new one.

### Prioritization Rules

**Dual Queue (Scoring Based)** and **Vodafone Proposal** have steps as the other Dual Queue strategies, changed in the same columns, and use list 1 for every call by default (**Use List 2 for Final CDRs** off). **Dual Queue (Scoring Based)** orders the calls by their impact level: its list 1 is list 2 of every strategy (see the table of list 2 above). **Vodafone Proposal** puts SA before NSA and Voice before Data, every step in its **Unique queue**, so its queue chart and the panel show one queue:

1. **SA Voice** and **SA WhatsApp**: every call, P1.
2. **SA Data**: the calls of a cluster (a repeated issue), P2.
3. **NSA Voice** and **NSA WhatsApp**: every call, P3.
4. **NSA Data**: the calls of a cluster, P4.
5. **Every other call** (Any NR Mode and Call Type): P5, in the Unique queue too.
6. **Tracked**: the Ping tests and the Excluded Calls, which no queue takes, P8.

A workspace or an NQ configuration file whose Points Lost Based (now Dual Queue (Scoring Based)) had rules of its own (the Custom rules of the first version) gets them as its steps: one per rule and Call Type, in their order, with its NR Mode, operators, criterion as conditions, Priority and queue (Tracked for Track only), and a last tracked step with the Priority of their tracked calls; the Region and City of a rule have no column (**Regions out of scope** leaves regions out).

On the right, under **Scoring Impact, Clusters, Time-Window Issues and Hotspots** (shared by every strategy, as the card says: a change there applies to all of them, as the Out of Scope card and Fill the Priority of the open calls), the dialog also sets the High and Medium shares of the Scoring Impact, the calls (**Cluster size**) and the previous campaigns (**Cluster period**) of a cluster, the **Cluster distance** (how close the calls of a cluster are, in ISDs, with the meters in cities and on connecting roads without an ISD below it; the cities meters also give the spot of a call without a cell), the **Time window** and the **Time-window distance** (in ISDs, with its meters without an ISD; they all also link the failures of a hotspot), the **Hotspot join** (OR or AND), how many calls **Next to analyse** lists (of each queue), the **Queues by hotspots** (those that list their hotspots instead of their calls, the Data queue by default) the **Minimum hotspot size** (the failures of the queue a hotspot needs to be listed, 3 by default) and the team of each queue (**Voice queue team**, **Data queue team**, **Unique queue team**, none by default: the waiting calls of the queue without a team of their own go to the **My team** view of its members, who take them). The Queues by hotspots and the queue teams list only the queues the steps of the strategy shown use (and of list 2 only while Use List 2 for Final CDRs is on): the Voice and Data queues for the Dual Queue strategies, the **Unique queue** (the single queue of a strategy such as Vodafone Proposal) for Vodafone Proposal; the other queues keep their choice. Each choice takes a line of its own below its name. They start with the configuration the NQ team recommends: High 50 % and Medium 80 %, a Cluster size of 2 calls with a Cluster period of 0 campaigns, a Cluster distance of 0.5 ISD (250 m in cities and 1,000 m on roads without an ISD), a Time window of 6 minutes, a Time-window distance of 0.8 ISD (500 m and 2,000 m), the Hotspot join OR and 20 calls Next to analyse; every workspace took it once when it became the default, whatever it had (App Events records each change), and the calls already calculated took it at once. A change of the High or Medium share (the impact levels) or of the cluster, hotspot and time-window settings counts the **#Calls** again at once, and **Save** applies it to every call at once, from the points and places already calculated. With **Fill the Priority of the open calls** (beside the Strategy, on by default), the [Priority](#default-catalog) of each open call is filled with the priority of its step while it is empty or still the one it gave: once someone changes or clears it by hand, they no longer change it, and once its analysis has started it keeps it; the history records each change. The steps saved with the conditions Time-Window Issues and Cluster alone (joined by AND or OR) took **Hotspots** once, in every strategy, when the hotspots came to join both (App Events records it); a step saved with them afterwards keeps them. A list still saved with the default steps of an earlier version takes the current ones when the application is updated; a list you changed keeps its steps, and a step added later to the defaults joins it only when it does not already have the same step. **Default Rules** shows the default strategy (Dual Queue (Cities first)), the default steps of the four strategies of the application and the levels again (the strategies of your own and the names stay as they are), and **Save** applies them to every call at once. **Save** keeps the dialog open: the line at the left of its buttons tells *The current configuration is saved*, or *Unsaved changes* as soon as something changes (also the strategy shown, which Save applies). **Close** (or Escape) with changes not saved asks first: **Save** them, **Discard** them or **Continue Editing**.

### When it is calculated

The values are calculated in the background once the server is idle (after the indexing of the calls and the Scoring History), whenever what they depend on changes: the calls or CDRs indexed, the Scoring History, the methodologies, the Operator Maps, the Scoring Excluded Calls, the NR Mode and the stage of the CDRs (a new Final CDR), the Network Inventories and cell mappings, the Serving Networks or the levels; the first time the panel opens they are calculated at once. The floating background tasks card shows the calculation, App Events records it, and the calls indexed since show their values once it ends.

## NQ Maps

See every filtered NQ call, and the Layer3 Logs of those that have them, on one map.

The **NQ Maps** panel is right below the NQ Prioritization & Queues (**NQ Maps** in the sections bar).

- **What it draws:** every NQ call of the filters (but the Ping tests) and the [Layer3 Logs](workspace-management.md#layer3-logs) of those that have a session in them.
- **Like the map of a call:** it is the [map of a call](#map-of-the-call) for all of them, with the same information, cards, legend, controls and navigation, without the groups of a call (hotspot, clusters, time windows).
- **Which calls:** the filters of the page choose them (a campaign, an operator, a root cause…), and the map is read again when they change.
- **Where it opens:** where you left it (your browser keeps its place and zoom).

**Navigation** (see [Tips & shortcuts](#tips-shortcuts)):

| To… | Do this |
| --- | --- |
| Move it | Drag it. |
| Zoom | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + wheel, or a pinch (the wheel alone in the larger map). |
| Zoom into an area | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + drag a rectangle. |
| Measure, with the elevation profile of the ground | <kbd>Alt</kbd>/<kbd>Option</kbd> + drag. |
| Zoom out, in, or show every NQ call with a log | **−**, **+**, **Fit**. |
| Open it larger | Double-click it (on a phone or tablet, double tap): it takes the whole width of the window but 2 % on each side. |
| Choose the map type, or download it | **Map** above it; the image buttons take its cards and legend too. |

**Above the map** (and above the larger map):

| Control | What it does |
| --- | --- |
| **Colour NQ calls by** | *Call type* (the default); *Root cause domain* (the one decided, else that of the DT Analyzer RCA); *Campaign*; *Operator*; or *Site* (the site their CDR gives). Each value takes a colour of its own; the legend names the twelve with most NQ calls. |
| **Operators** | The Focus operators of the [Operator Maps](workspace-config.md#operator-maps) (the default), or every operator. |
| **Call types** | A check box for each call type of the NQ calls (*Voice*, *WhatsApp*, *Data*…), every one checked by default. Only the NQ calls of the types checked are drawn, counted and listed. **Every call type** checks them all again; at least one stays checked. Your browser keeps the choice. |

Then a line says how many NQ calls the filters have, how many have a log and how many sessions.

**The cards over the map:**

- **CDR Info**, over the top left of the map:
  - **NQ calls:** the NQ calls of the filters as diamonds where they failed; hollow those without Layer3 Logs; those on one point make one mark with how many they are. They are drawn over the routes and the layers of the logs.
  - **Sites:** the sites of the networks that serve their operators, from zoom level 11.
  - **RSRP / SINR (from CDR samples):** the samples of the CDRs of their campaigns in the area shown, from zoom level 13 (an even sample of 20,000 when there are more), each measure with its switch.
  - **Route** (off until switched on), **Drive of each CDR (estimated, between its tests)**: the drive of each CDR, sketched as the map of a call sketches the drive of its car. Winding grey roads join only its tests close in time and place (2 minutes and 2 km at most, at a speed a car can drive), thin and below everything. The real way of each session is the route of its log.
- **LOGS Info**, beside it, with the layers of the logs:
  - **Grid**, zoomed out (below zoom level 13): the average of the metric chosen in **Grid of** (the RSRP, RSRQ, SINR or UE Tx Power of the LTE or NR PCell, SCell or neighbour cells; LTE PCell RSRP by default). Each cell takes the colour of its level in the [Map Levels](#map-levels); hover it for its average, its lowest value and how many points it has.
  - **Events** of the area, from zoom level 10, over the grid.
  - **Points of the layers on**, from zoom level 13, in the area shown (the first 80,000), read again as the map moves.
  - **Route** of each session: the GPS of its log drawn as a road with its direction.
  - **Shared with the maps of the calls:** a layer switched on in one is on in the other.
- **A click** on an NQ call, a point of a log or a route shows its values with **Open this call**, which opens it, and the **Signalling timeline** of that call below the map (over the larger map), with its cursor (see [Layer3 Logs on the map](#layer3-logs-on-the-map)).

The map of each call shows the same information focused on it: its own log, and, with **Logs of the NQ calls around** in its card **LOGS Info**, those of the NQ calls of its map (its groups and its area), faded below its own.

App Events records the map opened and each change of what it shows (`nq_l3_maps`: its filters, layers, grid, routes, sites or samples), with the filters, the NQ calls and sessions found, the zoom, the layers, the grid, the points or cells, the routes, sites and samples and how long it took; moving or zooming the map is not recorded again. A map that could not be read is always recorded (`nq_l3_maps_failed`, with the filters, the zoom, the area, the layers and the error).

### Map of a site

The **map of a site** shows the NQ calls of one site and of the sites around it.

- **Where it opens:** from a site of **Sites to review** in [Scoring & GAP Analysis](scoring-gap-analysis.md#points-lost), in a floating panel over that page, or from a link to Non-Qualified Calls (its **Open in Non-Qualified Calls** button opens the same map here).
- **How it works:** it is the larger map of NQ Maps, with the same cards, legend, controls and navigation, centred on the site. The wheel zooms, a double-click zooms in, and <kbd>Esc</kbd> or a click outside it closes it (see [Tips & shortcuts](#tips-shortcuts)).

What it shows and chooses:

- The site is ringed, where the Network Inventory places it (else where its tests were), with a dashed circle of the **Radius** around it.
- **Radius** (500 m to 10 km, 1 km the first time) chooses the area whose NQ calls the table below lists; the map fits it.
- **Colour NQ calls by** opens with *Site*: the NQ calls whose CDR gives the site are burgundy.
- **Operators** opens with the operator of the table only; *Focus operators only* or *Every operator* add the NQ calls of the other operators.
- **Call types** shows on the map and in the table only the NQ calls of the call types checked (every one by default). Your browser keeps the radius and these choices for the next site.
- Its NQ calls are those of the campaign of the table of the site (or of the campaigns of the scoring when the table has none); the line above the map says how many there are and how many have Layer3 Logs.

Below the map, a table lists, of the operators shown, the NQ calls **of the site**, wherever they failed, and those of other sites (or without a site) **within the radius**: the site first, then the nearest.

- **Columns:** its mark on the map, `JOIN_ID`, site (*This site* for those of the site), distance to the site, operator, call type, campaign, start, result, failure, status and root cause (the one decided, else that of the DT Analyzer RCA).
- **Sort:** click a column title (▲); again to reverse it (▼), a third time to go back to the order above.
- **Show a call:** click its `JOIN_ID` to show it on the map with its panel and its **Signalling timeline**.
- **Open a call:** **Open**. From Scoring & GAP Analysis it opens in a tab of its own, so the map stays open; here the map closes and the call opens.
- **Copy the JOIN_IDs:** copies the `JOIN_ID` of every call of the table, one per line.
- **Images:** the map and the table download as images or copy as screenshots with their image buttons.

App Events records each map of a site opened, and each change of what it shows, as `nq_l3_maps` (scope *map of a site*), with the site, its network, operator, campaigns, radius, the page it was opened from, how many NQ calls its CDRs give it and, when it opens, whether the Network Inventory places it. A link to a call (`/non-qualified-calls#call=<call key>`) opens that call.

## NQ Rate by Campaign and Operator

The **NQ Rate by Campaign and Operator** panel, below the NQ Prioritization, is the management view of the campaigns: for each campaign and operator, how many of **every** call of the CDRs (qualified or not) are Non-Qualified, and their share. Each call counts once, in the most recent CDR that has it (the Final CDR before the Daily ones), so a call Completed in the Final CDR is no longer Non-Qualified.

- One tab per service (Voice, Speech and Data; **All services** adds them up when there are several).
- Cards with the overall rate and the rate of each operator, each operator named in its Operator Maps colour.
- A heat map: each cell shows the rate and *Non-Qualified / all calls*, coloured in pastel tones from soft mint (none) through apricot to dusty rose (the highest rate of the table); the Total column and row sum each campaign and operator.
- A click on a cell or card shows only those calls in the other panels; a second click removes the filter.
- With **NQ Calls in Scope Only** on, the **Show operators out of scope** switch beside the service tabs also shows the operators that are not Focus operators of the [Operator Maps](workspace-config.md#operator-maps) (such as EE and O2), with their calls in the regions and NR Modes in scope, to compare them with the Focus operators. They are marked *Out of scope*, their cells and cards cannot be clicked, and **Overall** and the **Total in scope** column count only the operators in scope. The switch is remembered in the browser; the exports keep the operators in scope only.

> [!NOTE]
> Only the **NR Mode**, **Campaign**, **Service**, **Operator** and **CDR** filters and **NQ Calls in Scope Only** apply: the other filters describe Non-Qualified Calls only, so changing them does not recalculate the panel, and its counts are reused until the CDRs are indexed again.

The PowerPoint and Word exports and the reports of [Reporting](reporting.md) show it after the Executive Summary as one heat map with a column per service (and **All services**, their total) under each operator and the overall NQ rate of the selection at its top right (*Overall 0.9% · 992 NQ calls of 104,304 calls*), on one slide, or on two when the operators or campaigns are many (each slide with half of the operators or of the campaigns).

## Failures by Type, Technology & Serving Cell

The **Failures by Type, Technology & Serving Cell** panel, below the NQ Rate, shows how and where the filtered calls fail, with one tab per service:

- **Failure type**: per operator and environment (City or Connecting Roads, from `G_Level_2`), the calls of each result (Failed, Dropped, Cutoff…; **Not reported** when the CDR gives none), each as a share of every call of the operator in that environment.
- **Technology and classification**: per operator, the technology at the failure (else the technology of the call) against the NetCheck failure classification.
- **Serving Vendor and host network**: per operator, the calls and Non-Qualified Calls on the cells of each Vendor and host network that served them, with their shares and NQ rate; a share of the Non-Qualified Calls well above the share of the calls is red.
- **Sites with the most Non-Qualified Calls**: per operator, the serving sites (with 5 calls or more) with the most Non-Qualified Calls (up to 25), with their host network, Vendor, city or route, calls and NQ rate.

The shares and rates divide by every call (qualified or not) of the CDRs, Service, Campaign, Operator and NR Mode filters, as the NQ Rate does. The serving cell comes from the [Vendor Mapping](workspace-management.md#vendor-mapping) of the CDRs (`Vendor`, `Serving_Host_Network`, `Serving_Site_ID`); the CDRs indexed before this version are indexed again in the background to add it. A click on a cell shows only those calls in the other panels; a second click removes the filter. The PowerPoint and Word exports and the reports of [Reporting](reporting.md) show its tables after the NQ Rate.

## Root Cause Sources

The **Root Cause Sources** panel compares the four root cause sources of the filtered calls:

The DT Analyzer RCA comes first everywhere, then the RCA of the CDR (the **NetCheck RCA**, or the RCA named after the provider of the workspace's CDRs, such as the Umlaut RCA) and the **Ericsson RCA**:

- Indicators, in three lines: how many calls have a root cause of the **DT Analyzer RCA**, a **NetCheck RCA** classification and **Ericsson RCA** results; how many have a **Selected Cause** (a Root Category or Cause chosen by the analysts) and how often each RCA agrees with it, **Selected Cause ↔ DT Analyzer RCA**, **Selected Cause ↔ NetCheck RCA** and **Selected Cause ↔ Ericsson RCA** (the category, or the cause when the source maps to no category, the analysts selected is the one the source proposes, mapped onto the catalog by its keywords); and how often each pair of RCAs agrees, **DT Analyzer RCA ↔ NetCheck RCA**, **DT Analyzer RCA ↔ Ericsson RCA** and **NetCheck RCA ↔ Ericsson RCA** (the category, or with the DT Analyzer RCA the cause when one of them gives no category).
- **DT Analyzer RCA → Root Domain**, **NetCheck RCA → Root Domain**, **Ericsson RCA → Root Domain** and **Selected Root Domain**: the calls each source covers in each root domain, in its colour (**Not classified**: values of the NetCheck RCA or the Ericsson RCA that map onto no domain of the catalog); a domain shows only the calls the source puts in it.
- **DT Analyzer RCA → Root Category**, **NetCheck RCA → Root Category**, **Ericsson RCA → Root Category** and **Selected Root Category**, below the root domains: the categories of each source on the [Root Cause Catalog](#root-cause-catalog), each with its root domain in a tag (**No catalog category**: values the catalog knows no category for, only a domain or nothing); a category shows only the calls the source puts in it.
- Below them, the categories and causes of each source, four hierarchies side by side: **DT Analyzer RCA → Root Cause** (the Root Category → Root Cause it finds), **NetCheck RCA → Root Cause** (the Failure Category → Subcategory of the CDR), **Ericsson RCA → Root Cause** (its Suggested Category → Cause) and **Selected Root Cause** (the Root Category → Root Cause the analysts chose). A category or a cause shows only the calls the source gives it (for the RCAs, by their own category and cause, as the hierarchy shows them: **Category · Cause** in the filters), and the tag of a category, the root domain its calls fall in, only the calls of that domain for the source; a second click removes the filter. The tag is in the colour of the domain: the main one and how many more when the calls fall in several, all of them on hover.
- **RCA → Selected Root Category**: for the DT Analyzer RCA tab (the first), the NetCheck RCA tab or the Ericsson RCA tab, how the categories the source maps to relate to the categories the analysts chose; the columns repeat the rows in their order (also those nobody selected) before the other selected categories, so the cells where both agree, outlined, run along the diagonal.

The PowerPoint and Word show the same on two slides: the root domains and catalog categories of each source in two cards, one below the other (the first categories that fit), under the calls each source covers; then its own hierarchy (the first rows that fit), under the agreement of the Selected Cause with each RCA and of each pair of RCAs.

The panel shows how many Ericsson RCA results are imported and how many match calls; they are imported with **Import Ericsson RCA Results** in the **NQ Analysis Configuration** menu (see [Ericsson RCA results](#ericsson-rca-results)).

## Root Cause Analysis

The **Root Cause Analysis** panel shows where the filtered calls fail, by the root causes of one source chosen in its tabs:

| Tab | Root causes |
| --- | --- |
| **DT Analyzer RCA** (chosen when the page opens) | The Root Category and Root Cause the [DT Analyzer RCA](#dt-analyzer-rca) finds for each call from the data of its CDR, and their domain. |
| **NetCheck RCA** | What the NetCheck RCA of the CDR (Failure Classification, Category and Subcategory) gives each call on the [Root Cause Catalog](#root-cause-catalog), by its names and keywords and the suggestion rule (never the comments). |
| **Ericsson RCA** | What the imported [Ericsson RCA results](#ericsson-rca-results) give each call on the catalog: its subcategory, or else its category, as the cause by name or keywords, and the category of that cause (*Poor Coverage LTE* → Coverage · DL coverage, *Mobility Issue NR · Missing or Late Handover NR* → Mobility · Missing or late handover), with the technology it names (*Other LTE* matches no cause). |
| **Analysts** | The Root Category and Root Cause the analysts chose (with the domain they give the call). |

Each tab shows:

- Indicators: the calls, how many have a root cause from the source (**Labelled** for the analysts, **With a Root Cause** for the other sources) and how many are **Not classified** by it.
- **By Root Domain**, **By Root Category** (where the technology of the categories tells LTE, NR and 2G/3G apart) and **By Root Cause** bars, in the colour of each domain.
- **Root Domains by Call Type**, always in this order (**Voice**: the Voice and Speech calls whose test name does not contain WhatsApp, formerly Classic; **WhatsApp**: those whose test name contains it; **Data**: the Data tests) and **NSA vs SA**, each in its own card under the legend of the root domains they share: a donut for each group with its calls in the centre, split in the colours of its root domains, each slice long enough showing its calls (every slice shows its calls and share on hover). On a narrow screen the donuts of a card stay on one row, smaller, with larger values on the slices long enough for them (the others on hover).
- **Root Domains by Technology**: a bar for each technology split in the colours of its root domains (with their legend above; a part wide enough shows its calls) and its total.
- **eNB / gNB with most calls**: the node of the last cell of each call's `Cell_ID` chain (the cell where it ended): identities above 28 bits are NR cells (gNB = NCI / 16384, for 22-bit gNodeB IDs), LTE cells give their eNB (ECI / 256) and smaller identities are 2G/3G cells. The site ID, host network and vendor are those most of its calls have in the Network Inventories and cell mappings of the workspace, found as for the place of the [repeated issues](#repeated-issues) (in a network that serves the operator, near the call); otherwise the vendor is the call's.

A click on a bar, on the root domain tag of a category bar (the calls of that domain), on the name of a group, on the name or a slice of a donut, on a domain of a Technology bar, or on an eNB/gNB row shows only those calls (for example the NSA calls of RF), and a second click removes the filter. The domains, categories and causes filter the calls of the chosen source (for example the calls the Ericsson RCA puts in Coverage).

> [!TIP]
> **Show Not classified**, below the indicators, is unchecked by default for every source: the bars, donuts and technology bars count only the calls the source gives a root cause, their shares and totals being of those calls. Check it to add the Not classified calls. **Export PPT** and **Export Word** follow this checkbox, and the reports of [Reporting](reporting.md) have an option of their own, unchecked by default.

**Export PPT** and **Export Word** include the Root Cause Analysis of every source, each with its tables: the source in bold in their titles (*Root Cause Analysis · **NetCheck RCA***, ***Ericsson RCA***, ***DT Analyzer RCA*** or ***Analysts***) and what each slide shows in its subtitle: the Root Domains by Call Type and NSA vs SA donuts under one legend, the Root Domains by Technology bars (every technology, thinner when they are many) and the eNB / gNB with Most Non-Qualified Calls (only the first ones that fit), after the NQ Rate by Campaign and Operator and the Root Cause Sources, and before the Lifecycle & Phases and the Progress View. The Non-Qualified Calls section of the reports of [Reporting](reporting.md) includes them too, and its **Root Cause Analysis** option decides whether the analysts count the calls without a root cause with their suggested one.

## Lifecycle & Phases

The **Lifecycle & Phases** panel follows the filtered calls through their follow-up:

- Indicators (in the order a call goes through; the same **In Queues**, **Not Attended**, **Assigned** and **Attended** as Progress View, the By Status donut and the **In Queues** badge of the panels):
  - **Calls**: how many are in a queue of the NQ Prioritization and how many are tracked, in no queue.
  - **Automatic Status** (following the Status Rules) and **Status by Hand**.
  - **In Queues**: the calls the queues list, in the statuses marked In Queue: the first status, Assigned and Under Analysis (the note gives each, such as *Not Attended 320 + Assigned 25 + Under Analysis 4*). The same number as the badge of the panels.
  - **Not Attended** (the first status, named after it): the prioritized calls nobody has yet.
  - **Open**: assigned or attended and not closed (Assigned plus the phase statuses).
  - **Assigned**: the prioritized calls given a team or an analyst, not attended yet.
  - **Attended**: the other prioritized calls, followed up, in any later status.
  - **Stalled**: open without any change for 14 days or more, counted from today; a call becomes stalled on its own and leaves it as soon as it changes.
  - **Closed**: in a closed status.
  - These cards and the NQ Call Status Pipeline count only the prioritized calls, their shares too, and add the tracked calls of each one apart (*+12 tracked*), as they wait for nobody.
  - A click on a card shows only its calls (chips *Follow-up: In Queues*, *Follow-up: Not Attended*, *Follow-up: Assigned, not attended yet*, *Follow-up: Attended*, *Follow-up: Open*, *Follow-up: Closed*, *Follow-up: Stalled*).
- **NQ Call Status Pipeline**: a bar with the share of each status and one card per status, with its calls, share and average age: the calls not attended, then **Open** — a frame around the statuses an assigned or attended call goes through until it is closed (Assigned, Under Analysis, Analysis Finished, Under Implementation and Under Planning), its total being their sum — and then the closed ones; the statuses whose calls the queues list are tagged **In Queue**; a click on a card filters by that status, and a click on Open shows the open calls (the chip *Follow-up: Open*). The rules of every card start on the same line, below its status, calls and age. Each card shows the [Status Rules](#status-rules) that set it: **Rule N** (the order they are tried in) with the field and its values in their colours, for example *Rule 6 · Analysis Status · Ongoing* on Under Analysis, and *When no rule applies* on the first status. A click on a rule shows the calls that meet it.
- **RCA Identification**: how many calls have a root category or cause selected and how many not, each row drilling down into its calls.
- One card per list field of the **Analysis**, **Implementation** and **Planning** sections (for example Analysis Status, Implementation Status and Planned Status), side by side: a bar with the share of each value and a row per value that drills down into its calls. Like the pipeline, these cards and RCA Identification count only the calls in a queue (the tracked calls apart); the shares are of the calls in a queue with a value, as the card tells. A field with more than 12 values, such as the Implementation Proposals, takes a row of its own below them, across the panel, its values in columns from the most frequent. Each value has the colour chosen in [Fields & Sections](#fields-and-sections); when no value of a field has one, its values take a palette of different colours.
- **Time in Each Status**: the average days the calls stayed in each status before moving, from the history of their status (set by hand or by the rules).
- **Most Frequent Moves** between statuses.
- **Stalled Open Calls**: the open calls without changes for the longest, with their status, Operator, Campaign, City and days without change; click one to open it.

> [!TIP]
> **Show Empty Status**, above the phase cards, is unchecked by default. Check it to add the calls without a value (**Empty**) and give the shares of every call in a queue; **Export PPT** and **Export Word** follow it, and the reports of [Reporting](reporting.md) have an option of their own, unchecked by default.

**Status Rules** (for every user; only admins and super-admins change them) opens the rules from the panel.

The PowerPoint and Word exports and the reports of [Reporting](reporting.md) show the Lifecycle & Phases as the page does, each slide saying what it shows in its subtitle: the indicators and the **NQ Call Status Pipeline** (the Open frame around the phase statuses and the rules of each status), the **Phases** in one row (a field with more than 12 values on a slide of its own, its values in columns), the **Time in Each Status and Most Frequent Moves**, and the **Stalled Open Calls** that fit.

## Progress View

The **Progress View**, the last panel, shows how the follow-up advances for the filtered calls in a queue of the NQ Prioritization. The tracked calls (Track only, in no queue) wait for nobody: every statistic of the panel leaves them out and counts them apart, so they do not blur the follow-up.

- Indicators, by the NQ Call Status of each call, in the order a call goes through, with the names and numbers of Lifecycle & Phases and of the **In Queues** badge:
  - **In Queues**: the calls the queues list, in the statuses marked In Queue: the first status, Assigned and Under Analysis (attended and still in their queue), each in the note.
  - **Not Attended** (the first status, named after it): nobody has them yet.
  - **Assigned**: given a team or an analyst, not attended yet. A call set back to Not Attended or Assigned is not attended again.
  - **Attended**: the other prioritized calls, followed up, in any later status.
  - Their shares are of the prioritized calls (the tracked calls left out).
  - Then the average days from the call to its first follow-up (**First Follow-up**) and to its closure (**Time to Close**), the **Closure Rate**, the activity and, last, **Tracked**: the tracked calls left out, with how many are not attended and how many closed.
  - A click on a card shows only its calls (*Follow-up: In Queues*, *Follow-up: Not Attended*, *Follow-up: Assigned, not attended yet*, *Follow-up: Attended*, *Follow-up: Tracked (in no queue)*). The first follow-up times the answer from the history of the call (its first change other than an assignment, or its first comment).
- Donut charts **By Status**, **By Team**, **By Analyst** (by first and last name), **By Service** and **By Result**; each legend shows the full name with its count and share; hovering a slice shows its value, count and share, and a click on a slice or a legend entry filters the calls by that value.
- A timeline per **week** (the default), **month**, **quarter** or **year** of the calls detected, attended, commented, closed and reopened (hover a period to read all its values), with a table that adds the moves to each open status (those to a closed status are the **Closed** column), the backlog at the end of each period of the calls in a queue (**Queue backlog**) and, apart, of the tracked calls (**Tracked backlog**, a dashed grey line), and the average days from the call to its closure. The status changes, closures and reopenings count both the statuses chosen by hand and those the Status Rules set (as when importing analyses, dated by the analysis).
- The age of the open calls, the workload of each team and analyst (open, closed and total calls) and the recent activity of each user, by their first and last name.

As in the Summary, a click drills down into the calls: a slice or legend entry of a donut, a period of the timeline (in the chart or its table: the calls detected in that period), an age bar (the open calls of that age) or a team or analyst row shows only those calls; click it again to remove that filter. The User Activity table is informative only.

In the PowerPoint and Word, the Progress View slides show the period of the timeline in bold in their title (*Progress View · **Monthly***) and what each one shows in its subtitle: Follow-up Overview, Progress per Month, Age and Workload, Details per Month and User Activity. The Follow-up Overview has the same cards as the page; its table of indicators reads *In Queues (first status + Assigned + Under Analysis)*, *Not attended, nobody has them yet (first status)*, *Assigned, not attended yet (in a queue)* and *Attended (followed up, in any later status)*.

## NQ Calls panel

Follow up the calls one by one. The **NQ Calls** panel (named so in the sections bar too) lists one row per call, with these columns in this order:

- **Start time** (to the minute; hover it for the seconds) and **service** (for a Speech call, also its number of Non-Qualified samples).
- **Operator** and **Vendor**, **Region** and **Cluster**, **City** and **Campaign**, **test** and **technology**.
- **Result**, with the failure classification and category (hover a failure to read its subcategory and comment) and the CDR version badge.
- **The RCA fields chosen as columns** (none by default). Ericsson RCA Suggested Cause and NetCheck RCA Suggested Cause show in italics the suggested category of their source, named below it, when the source gives no cause, as most results of the Auto RCA output of the Ericsson RCA.
- Its **Root Category** and **Root Cause**.
- **The other fields chosen as columns** (by default Analysis Status and Implementation Status).
- Its **Global Status**, its **team** and **analyst**, and its **comments**.

**Join ID** (**Call ID** when the CDRs also bring the IDs of the calls in the provider's tools), centred in the title bar of the panel, finds calls by their IDs:

- **Which IDs:** their `JOIN_ID`, or the IDs of the provider. In NetCheck CDRs these are the `Session_ID_A` and `Session_ID_B` of a voice or Speech call and the `Test_ID` and `Session_id` of a data test, as NetCheck CloudNM identifies them.
- **How:** type or paste one or more, separated by commas, spaces or lines (whatever their case), to list the calls with exactly those IDs.
- **Kept:** with the shared selection, and shown among the active filters.
- **Recent JOIN_IDs:** below it, as below **Go to a JOIN_ID…** (**Go to a call ID…**) of an open call, which takes the same IDs, a list offers the 10 last searched in either box (in your browser, for each workspace), the latest first, narrowed while typing. A click, or the arrow keys and <kbd>Enter</kbd>, chooses one; here it takes the place of the JOIN_ID being typed.

### Follow up the calls

1. Narrow the calls with the [Filters](#filters), the **Join ID** box or the funnel of a column header.
2. Change the **Status**, **Team**, **Analyst**, **Root Category** and **Root Cause** of a call directly in its row, or accept its recommended root cause.
3. Click a row to open the call, fill the fields of its sections and comment it (see [Call details and activity](#call-details-and-activity)).
4. Select several rows to change all of them at once (see [Bulk changes](#bulk-changes)).

**Changing values in the row.** Users with the `user-editor`, `admin` or `super-admin` role change the **Status**, **Team**, **Analyst**, **Root Category** and **Root Cause** directly in the row; `user-viewer` accounts see the same information read-only.

- **The lists:** each value shows as a pill in its colour, with a search box for long lists and the arrow keys to move. <kbd>Enter</kbd> takes the first value found.
- **List fields of the analysts:** their list always has the search box. A value typed there that the list lacks is offered first as **+ Add “…”**, which adds it to the values of the field and chooses it.
- **Colours:** each value keeps the colour of its status, team or root domain. A root category is filled with the colour of its domain, a root cause outlined with it.
- **Width:** the status, team, analyst and root cause lists widen with the window.

**Analysts.** They are shown by the first and last name of their account (its username when it has none) in the table, the call, the bulk bar, the Analyst filter and the Progress View, sorted by that name.

- **Default users first:** the lists of analysts start with the default users of the application (super, admin and demo), tagged **default user**, with a line before the other users.
- **Analysts without account:** a name the [Previous NQ Analyses](#previous-nq-analyses) brought, until [Link Analysts to Accounts](#link-analysts-to-accounts) links it. It is shown with its name in italics in a dashed pill, tagged **No account** in the lists. It counts in the filters and the statistics, but only user accounts can be chosen as the Analyst of a call.

**Root Category, Root Cause and Root Technology.** Each is chosen from a list: search it by name; the current value is ticked.

- **Category follows cause:** choosing a cause gives the call its category, and choosing another category clears a cause that is not one of its causes.
- **Order of the lists:** grouped by domain. First the values the RCA sources of the call propose, then (in the list of causes) the causes of the chosen category, then every domain in the order of the catalog, the causes of each domain under each of its categories.
- **Recommendation:** while a call has no root category and cause, its recommended ones are shown below them, small, with the RCA they come from above them (every source in its tooltip) and a dot for the confidence (green high, amber medium, grey low). A click accepts them (see [Root cause recommendation](#root-cause-recommendation)).

> [!IMPORTANT]
> **Choosing a status sets it by hand.** The list then offers **↺ Back to automatic** to give it back to the Status Rules. Below the status, each row tells whether it is **Auto** or set **By hand** and when its follow-up last changed and who changed it (hover it for the exact time).

**Other fields in the row.**

- **List and Yes / No fields** entered by the analysts and shown in the table are chosen in the row too, from the same coloured lists.
- **Other fields of the analysts** are filled in the section of the call.
- **Fields from the CDR, the Ericsson RCA or derived from the call** are shown read only.
- **›**, beside the comments, opens the call.
- **Comments column:** how many comments a call has and its latest comment; click it to read the thread or add a comment.

### Columns

Choose and arrange the columns of the table.

**How the columns look.**

- **Colours:** every column header is topped with the colour of its group, as in the Excel export. The columns of the call (and the optional and CDR columns) take that of the call, each field that of its section, and the team and analyst, root category and cause, status and comments that of the section of their follow-up field.
- **Fit:** the default columns fit screens of 1600 px and wider without scrolling sideways. Long values wrap on two lines or are shortened and shown whole when you hover them, and the time of a call goes below its date.
- **Comments:** the Comments column shows the number of comments, and the latest one when you hover it (the cards of phones show it).
- **Shared columns:** related values share a column, one below the other, so the table fits in the panel. The **Prioritization** and the **Priority** of a call share a column too when both are shown, the Prioritization above the Priority (chosen in the row); each name of its header sorts and filters by its own field.
- **Default columns of a new workspace:** after the root category and cause, the workspace layout shows the Prioritization with the Priority, the Repeated Issue, the Scoring Points Lost, the Analysis Status and the Implementation Status. The Scoring Impact and the other fields are shown with **Columns**.
- **Scroll position:** reloading the page returns to the position it was scrolled to.

**Order of the columns.** Drag a column header onto another to move that column before or after it, in your own [layout](#table-layouts). Columns added later take their default place. **Default column order**, shown while the order differs from the default one, puts every column of your layout back.

**Order of the calls.**

- **By default:** by **Priority** (P1 first, in the order of the values of the Priority; the Priority set by hand, else the one the NQ Prioritization gives; the calls without one last), then by **Scoring Points Lost** (the calls that lose most first), then the most recent first.
- **By a column:** every name of a column header (for example *Service*, *Result*, *Team* or *Analyst*) sorts the table when clicked; again to reverse it. **Default order**, shown while a column sorts them, brings back the default order.
- **Pages:** 10 (by default), 25, 50 or 100 rows per page, chosen in **Rows per page**, also with All panels.

**Filter a column.** The funnel beside a header name opens, right below the header, that field's values: search them by name, tick them (**Select All / None** ticks or clears the values shown; root categories and causes are grouped under their domain) and **Apply**. A column filter is the same selection as the Filters panel and its chip: the funnel is filled while that field is filtered.

**Columns**, a button of the table after **Default column order** (for every user), chooses the columns of your own [layout](#table-layouts), only for you: the optional columns shown after Result / Failure (Session Type (CDR) before Test / Technology) and those of your Excel export:

- `JOIN_ID`, NR Mode, Cell ID, Direction, Session Type (CDR) (the CDR's `Session_Type`), End Time, CDR and **Layer3 Logs** (the UEs of the call with a session in the [Layer3 Logs](workspace-management.md#layer3-logs) of the workspace, found by its `JOIN_ID`: `A, B` for a voice call, `Data` for a data test, empty without a log).
- The fields of the Analysis Center, grouped by section, each one a column of the table (**Table**; the follow-up fields always have theirs) and of your Excel export (**Excel**).
- The columns of the CDRs (for example `Cellname_A`, `Region_A` or `Auto_RCA_Category_A`), which show the value of the CDR version shown for each call. Each CDR column can go to the **Table** (up to 12), and then also to the Excel export, or to **Excel** only (up to 100 more). A CDR column that no layout showed before indexes the calls again.

Its buttons:

| Button | What it does |
| --- | --- |
| **Default Columns** | Returns to the columns of a new workspace: no optional or CDR columns, and the Table and Excel of the fields of the [default catalog](#default-catalog) (Prioritization, Priority, Repeated Issue, Scoring Points Lost, Analysis Status and Implementation Status in the table, every field in Excel). |
| **Copy Workspace Layout** | Returns to the columns, Excel and column order of the workspace layout. |
| **Save** | Applies them to your layout. |

**Filters of the optional columns.** Every optional column sorts the table and has its filter:

- **Region and Cluster** use their filters of the Filters panel.
- **`JOIN_ID`, NR Mode, Cell ID, Direction, Session Type, End Time, CDR** (which chooses CDRs) **and Layer3 Logs** (**Empty** lists the calls without a log) add theirs under **Additional Columns Filters**.
- **The CDR columns** filter from their header only.
- **Every one** offers **Empty** for the calls without a value.

The Filters panel shows the **General Filters**, then the **NQ Analysis Fields Filters** and the **Additional Columns Filters**.

### Table layouts

The columns of the table, those of the Excel export and their order make a **layout**. **Layout**, a switch beside **Columns**, shows one of two: **Mine** with the switch to the left and **Workspace** with it to the right (click the switch or either name):

| Layout | Who sees it | Who changes it |
| --- | --- | --- |
| **Mine** | Only you. The first time it is a copy of the workspace layout. | You, whatever your role: dragging a column header, **Columns** and **Default column order**. |
| **Workspace** | Every user who has not chosen Mine. | Admins and super-admins: **Save for the workspace**, shown with Mine, makes their layout (columns, Excel and column order) that of the workspace once they confirm. |

A change made while the workspace layout is shown makes it your own layout (when you already had one, you confirm that it is replaced). Switching keeps both, and your choice is kept with the workspace, so every browser shows you the same layout. **Export Excel** exports the fields and CDR columns of the layout you see, the fields in the catalog order. A field added to the catalog after you saved your layout follows the workspace layout until you choose it in **Columns**. The column order each browser kept before the layouts becomes your own layout the first time you open the page, so the table looks the same.

### Bulk changes

Change many calls at once.

1. Select several rows with their checkboxes, or every row of the page with the header checkbox.
2. In the bar that appears above the table, set the status (or **↺ Back to automatic**), team, analyst, root category, root cause or a list or Yes / No field of the analysts (**Set field…**) of all of them.
3. Apply more changes if needed: the selection stays after each change. **Clear selection** empties it.

- **The bar** shows over the row with the number of calls (it does not move the table) and stays at the top of the window while you scroll the table.
- **Accept recommendations** gives the selected calls without a root category and cause their recommended ones and leaves the others as they are.

## Call details and activity

Analyse one call: click a row to open its details beside the table.

**The header of the call** shows:

- **The call:** its service, result, CDR version, Operator, Campaign, time and place.
- **`JOIN_ID`**, with a button that copies it.
- **The IDs of the call in the provider's tools**, each with a button that copies it (— when the call has none): the `Session_ID_A` and `Session_ID_B` of a NetCheck voice or Speech call and the `Test_ID` and `Session_id` of a data test, which identify it in NetCheck CloudNM.
- **Layer3 Logs:** the UEs of the call that have a session in the [Layer3 Logs](workspace-management.md#layer3-logs) of the workspace, when it has one.
- **Groups:** its hotspot, its clusters and its time-window issue (see below).
- **‹** and **›:** the previous and next call of the list, with the position of the call (such as 12 of 1,268), turning the pages of the table when needed. When the filters change while a call is open, the table shows the page that holds it, so that they keep going through the calls of the filters.
- **Go to a JOIN_ID…:** opens the call of a JOIN_ID pasted there, whatever the filters. It and **‹** / **›** ask first when the call has [changes not saved yet](#tabs-of-the-call).
- **Map:** shows the [map of the call](#map-of-the-call).

**Groups of the call.** Its hotspot, its clusters, then its time-window issue, of 2 calls or more, on a row of their own across the header: the three on one row when they fit (each card wrapping its text), else on as many rows as they need, in that order.

- **Each card:** what it is, its NR Mode and its ID in the [NQ Hotspots, Clustered & Time-Window Issues](#nq-hotspots-clustered-time-window-issues) panel (such as *Hotspot SA H-0C1BCE*), in the colour of its group on the map of the call (hotspot orange, cluster green, time window blue). The hotspot card, which tells more, is wider than the others; hovering a card also tells what it groups.
- **Its sites:** the places of its calls with how many failed at each, the most first: how many sites, then each one on a line of its own, indented (*2 sites:* / *11 at Site 1154 (Vodafone)* / *4 at Site 3522 (Vodafone)*), or *At Site 1154 (Vodafone)* when every call failed there. The first three show, and every one on hover.
- **Pills at its bottom:** how far its calls reach, for a hotspot and a cluster (*within 310 m*, the circle the map of the call draws around them); how long it lasted, for a hotspot and a time-window issue (*within 2 h 46 min*); and last its period, for a hotspot and a time-window issue (from its first to its last call: *24 Sep 14:42–26 Sep 10:14*). A pill that does not fit goes on the line above.
- **Size:** how many calls it holds, in a pill over its top right corner (*17 calls*).
- **Filter by a group:** a click on a card filters the list of calls by its group after you confirm it, in place of any other group filtered. The card stands out, tinted and ringed in its colour, with a *Filtering the list* tab on its top edge. A click on the group already filtered removes its filter after you confirm it.
- **Rules:** a call is in one of each at most. Every group keeps to one NR Mode, as the steps of the strategies take them; a hotspot and a time-window issue also to one campaign, and a cluster to its campaign and those of its Cluster period.

**Scrolling.**

- **The wheel** scrolls only the details of the open call, never the page below them.
- **On a short screen** (a laptop, or a large zoom of the browser), where the header and the follow-up fields leave the tabs little room, the whole panel scrolls, its tabs staying at the top.
- **On a large screen** the header and the follow-up fields stay in place and only the tab scrolls.

**Analyst fields**, across the bottom of the header, shows how many of the fields the analysts fill in the whole call have a value.

- **What it counts:** Team, Analyst, Reviewer, Root Category and Root Cause of the header and every field of the analysts of its tabs, with the changes not saved yet. It leaves out the Initial Classification of the RCA tab, marked **Analyst (Optional)**, and the NQ Call Status and the Priority, set automatically.
- **Complete:** once they all have a value the bar is full, with *Complete* and a gold trophy (**All fields filled**, popping in as the last one is filled). Hover it for the empty ones.
- **Header and Tabs:** below it, **Header** counts those of the header and **Tabs**, above the tabs beside **Only the fields the analysts fill**, those of every tab together (dark green labels, with a check once complete), as each tab counts its own. The counters follow the changes not saved yet.

**The follow-up fields**, below the header, in this order:

1. **NQ Call Status** (with **Auto** or **By hand**) and **Priority** (given by the [NQ Prioritization](#nq-prioritization), **Auto**, until somebody chooses another one, **By hand**), on one line.
2. **Team**, **Analyst** and **Reviewer**, on the next line.
3. **The fields of the analysts added to the General section** in Fields & Sections, saved as soon as they change. The **Unique ID** of the Previous NQ Analyses is not shown in the call, but kept and exported with it.
4. **Root Category** and **Root Cause**, with the domain they give the call, and the recommendation while it has none.
5. **Prioritization Info:** the values of the [NQ Prioritization](#nq-prioritization) of the call, read only (see below).
6. **Phases:** one card per phase, with its name above its value, each in the colour of its section; a click opens its tab (see below).
7. **Who changed the call last.**

**Prioritization Info** shows the fields *From the NQ Prioritization* of Fields & Sections, in their order: Prioritization, Prioritization Rule, Prioritization Queue, Expected Gain, Scoring Impact, Scoring Points Lost, Scoring KPIs Lost, Repeated Issue, Repetitions, Repeated Campaigns and Repetition Place.

- **Repeated issue:** its four fields are together on a row below the others.
- **Not shown here:** the Hotspot ID, Time-Window ID and Cluster ID, which its Groups show.
- **Prioritization Rule** (here and in the table): what its step takes, such as *SA Voice · Medium impact*, with the list of the step in a tag below it (**WEEKLY** for list 1, **FINAL** for list 2) and its number in another beside it, such as **STEP 3**.

**Phases:**

| Phase | Value |
| --- | --- |
| **Map Analysis** | The place where the call failed, such as *Site 70086 (Vodafone)*, or *No position*. |
| **RCA Identification** | The root category, or *Recommended* or *Not started*. |
| **Failure Details** | *Not started*, *In progress* or *Completed*, with how many of its fields of the analysts are filled in. |
| **Analysis**, **Implementation**, **Planning** | The first list field of each section. |

**Where each value comes from.** Every field of the call shows its source in a small mark below its name (beside it in the header): a dot of its colour, as the cards of the [Filters](#filters), and the name of the source.

| Mark | Colour | Values |
| --- | --- | --- |
| **CDR** | Blue | The values of the CDR. |
| **DT Analyzer RCA**, **NetCheck RCA**, **Ericsson RCA** | Amber | What each RCA found. Their fields drop the name of the RCA from their own. |
| **DT Analyzer** | Violet | What the tool fills: the NQ Call Status of the Status Rules, and once for the whole **Prioritization Info** subpanel. |
| **Analyst** | Green | What the analysts fill, also the fields the tool fills in or proposes a value for (filling them is still the analysts' decision). |
| **Analyst (Suggested)** | Green | The CDR proposes a value for the field of that call, such as Serving Cell when Failure; hover it for the proposed value. |

- **Value colours:** the value of every field takes the palette of its mark: a blue tint for the CDR, amber for the RCAs, violet for DT Analyzer and Prioritization Info, green for the analysts. Team, Analyst, Reviewer and Root Category · Root Cause of the header and the Final Root Cause Decision are green too; the NQ Call Status and the Priority keep the colour of their value.
- **Still to fill:** the fields the analysts fill have a green pencil before their name and a dashed green border while they are empty, so what is still to be filled stands out.
- **Source**, above the tabs, lists the marks, each kind in a dashed frame of its colour (the three RCAs, the CDR, DT Analyzer, the analysts).
- **Only the fields the analysts fill** leaves in the tabs only the fields of the analysts, hiding the subpanels left without them, such as those of the RCA sources (remembered in the browser).

### Tabs of the call

The tabs of the call follow the steps of its analysis, on one line below the follow-up fields.

- **Steps:** raised buttons, each in the colour of its section, numbered in their order and joined by a line: **1 Activity**, **2 Map Analysis**, **3 RCA**, **4 Failure Details**, **5 Analysis**, **6 Implementation & Planning**.
- **Call Details:** a reference rather than a step, closes the row after a separator, with an *i* instead of a number.
- **The tab open** is tinted in its colour, its number filled.
- **Counters:** each tab counts, as *filled/total*, the fields of the analysts that already have a value (hover it to read it). The RCA tab shows ✓ once a root category or cause is chosen and ★ while a recommendation waits.
- **Lists and Yes / No fields** are chosen from the same coloured lists as in the table, as tall as the text boxes.

| Tab | Content |
| --- | --- |
| **Activity** (the General section) | The **Call Activity Log**: a timeline of the comments of the call, with their author (by first and last name) and time, and every change of status, team, analyst, root category, root cause or field with the previous and new values. A status moved by the Status Rules reads *The status followed the Status Rules…* after the change that moved it. Below, the comment box (see below). |
| **Map Analysis** | The [map of the call](#map-of-the-call): where it failed, its cells and sites, the sites and Non-Qualified Calls around and the RSRP / SINR of the tests around. |
| **RCA** | The **Analysts** subpanel, then the **Values of the RCA sources** (see below). |
| **Failure Details**, **Analysis** and **Implementation & Planning** | The fields of each section (Implementation and Planning in one tab, each in its own subpanel), with their description when you hover them. Failure Details starts with **Map of the call**, which opens the [map of the call](#map-of-the-call) larger, and also shows the **Last Cell ID** (the last cell of the Cell ID chain of the CDR, where the call ended) and the **Failure Comment** NetCheck writes in the CDR. Editors change the fields of the analysts; an empty field that proposes a CDR value (for example Failure Latitude and Longitude) offers **Use the CDR value**. Fields from the CDR, the Ericsson RCA, the DT Analyzer RCA or derived from the call are shown read only, with their source. |
| **Call Details** (in grey) | **Map of the call**, which opens the [map of the call](#map-of-the-call) larger, then the CDRs that contain the call (when there are several), the main fields of the call (with its `JOIN_ID`, root domain, category and cause), its location (opened in OpenStreetMap) and its CDR, followed by every non-empty field of the original CDR row, which you can filter by name or value. |

**Comment a call** (Activity tab):

1. Write in the comment box. It reaches the bottom of the panel when the activity leaves room.
2. Press **Add Comment**, or <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Enter</kbd>, to share it with every user of the workspace.

- **Format:** comments are written as they read, in the Markdown of the [descriptions and comments of Ticket Center](ticket-center.md#writing-descriptions-and-comments) (bullets, numbered lists, titles, bold, cards…); see the keys in [Tips & shortcuts](#tips-shortcuts).
- **Length:** up to 5000 characters.
- **In the table:** the Comments column shows the latest one without its Markdown.

**The RCA tab:**

- **Analysts** subpanel:
  - **Initial Classification:** the fields of the analysts of the section, such as Initial Root Category and Initial Root Cause, saved with **Save RCA**.
  - **Final Root Cause Decision:** the selected Root Category and Root Cause, and the recommendation with its confidence and the sources that agree on it (**Accept** sets it).
  - **A card per source** with what it says (the rule of the DT Analyzer RCA first, then the NetCheck category → subcategory and the Ericsson RCA category → cause) and the catalog values it maps to, with **Use as Final Decision** (green, centred at its foot) to make them the final Root Category and Root Cause.
  - **See the evidence ↓**, on a source with evidence, centred just above the divider of that footer (the dividers of every card stay aligned): it scrolls to its evidence in the subpanel of the source below and highlights it, instead of repeating it.
- **Values of the RCA sources:** a subpanel per source, named after it: **DT Analyzer RCA** first, then the **NetCheck RCA** fields and the **Ericsson RCA**. A workspace moves its DT Analyzer RCA fields before the others once, and Fields & Sections can change their order.
  - Four values per row (each pair of the Ericsson RCA on one row), read only.
  - Last, the other columns of the Ericsson RCA file of the call, their names in the colour of the Ericsson RCA.

**Save** in any tab saves the changed fields of every tab together; the sections tell how many changes are unsaved.

**Changes not saved yet are never lost without asking.** These ask first, saying what is pending:

- Leaving a tab that has any (fields changed, or in Activity a comment not posted or being edited).
- Closing the call (with **×**, <kbd>Esc</kbd> or a click outside it).
- Going to another call (**‹**, **›**, **Go to a JOIN_ID…** or a Speech sample).

| Answer | What happens |
| --- | --- |
| **Save** | Saves it (and posts the comment) and goes on. |
| **Discard** | Drops it and goes on. |
| **Continue Editing** (or <kbd>Esc</kbd>) | Stays where you were. |

> [!TIP]
> **Long texts read as bullets, also while they are edited.** The Description, the Findings, the Proposed Measure and the other long texts are written in Markdown, as the [descriptions and comments of Ticket Center](ticket-center.md#writing-descriptions-and-comments).

- **Bullets:** each line shows as a bullet, nested under the line above it as deep as it is indented (a dot, then a circle, then a square).
- **Titles:** a short line that is not indented and ends with a colon, or is followed by a list (*Problem Statement:*), is the title of the lines below it.
- **Dividers:** a line of dashes (*------Text------*) is a divider with its text.
- **More formats:** numbered lists at any level, headings, bold, italic, cards (`> [!TIP]`) and code.
- **Editing:** a click places the caret in the text, which stays as it reads. While it has the focus its toolbar shows above it and it grows taller (the Description and the Findings, one below the other, the tallest; the Proposed Measure two lines). <kbd>Tab</kbd> nests a line and <kbd>Enter</kbd> goes on at its level.
- **Empty text:** shows a guide in grey of how to write it until you type.
- **From the CDR or the Ericsson RCA:** the long texts read the same way.

For a Speech call, **Call Details** starts with its **Speech Samples**: its Non-Qualified samples with their result, failure, status, root category and cause and comments; open one to follow it up on its own (status, team, analyst, root cause, fields and comments), and **‹ Back to the call** returns to the call.

### Map of the call

See where a call failed and what was around it, on OpenStreetMap.

- **Open it:** the **Map Analysis** step of the call, or **Map** in its header, shows the map in place of the follow-up fields above the tabs (so the map takes their height). **Map** pressed again returns to the tab shown before.
- **Open it larger at once:** **Map of the call** in Failure Details and Call Details.
- **It follows the call shown:** **‹**, **›**, **Go to a JOIN_ID…** and **Open** of a call around it show the map of that call.

**Navigation** — as the maps of [Network Insights](network-insights.md#coverage-and-interference-maps) (all the gestures in [Tips & shortcuts](#tips-shortcuts)):

| To… | Do this |
| --- | --- |
| Move the map | Drag it (also with the middle button). On a phone or tablet: one finger. |
| Zoom towards the pointer | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + wheel, or a pinch of the trackpad. The wheel alone scrolls the call, and a note says how to zoom. On a phone or tablet: pinch with two fingers, which zooms towards their middle and also moves the map. |
| Zoom into an area | <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + drag a rectangle. |
| Measure a distance and its bearing | <kbd>Alt</kbd>/<kbd>Option</kbd> + drag. It opens the **elevation profile** of the ground between its ends (see below). |
| Zoom out, in, or fit | **−**, **+** and **Fit**, at the top right. **Fit** shows the whole radius and the shapes of its groups, and every NQ call of its groups and of its site wherever it is. |
| Open it larger | Double-click it (on a phone or tablet, double tap). <kbd>Esc</kbd> or a click outside closes it. |
| Read an element | Hover it. |
| Choose an element | Click it: its panel opens (see below). A click beside every element keeps the one chosen; its **×** closes it. |

**The larger map:**

- **Title:** its call type (*Voice*, *WhatsApp*, *Data* or *Ping*) as a pill above the title (its operator, campaign and `JOIN_ID`); the title of its images names the call type too.
- **Zoom:** the wheel alone zooms too, and a double-click (or double tap) zooms in.
- **Panel of the element chosen:** it floats on the right, off the cards; drag its title anywhere over the map, where it stays for the next element chosen. On the map in the call it shows below the map.

**Elevation profile**, as Google Earth shows it, in a panel over the bottom of the map:

- **Figures:** the elevation along the distance, its start and end, lowest and highest point, its climb and descent and its steepest slope.
- **Hover it:** the distance, elevation and slope of each point, marked on the map.
- **Fold it:** a click anywhere on its header folds it to its figures or unfolds it.
- **Clear it:** a click on the map, <kbd>Esc</kbd>, its **×**, or <kbd>Alt</kbd>/<kbd>Option</kbd> + click without moving.
- **Source:** the elevation comes from the Terrain Tiles of AWS Open Data.

**The panel of the element chosen:**

| Element | What its panel shows |
| --- | --- |
| **The call** | Its call type, operator, campaign, the sites where it started and ended and, below them, its cells. |
| **A Non-Qualified Call** | Its call type (Voice, WhatsApp, Data or Ping), operator, campaign, how it relates to the call (its groups, a cluster or a time-window issue of its hotspot, and whether it joins a cluster to a time-window issue), how far it is, the sites where it started and ended (those of its first and last cells; for its start, else, the serving site the CDR gives) and, below them, its cells, and **Open this call**. |
| **A site** | Its operator (as the Operator Maps name the operator of its network) and its vendor first, then its role in the call and its cells, with every cell (technology, band, channel, PCI, azimuth, beamwidth, state and its role in the call). |
| **A cell** (hover its sector) | Its operator and vendor first, then its role in the call, site, identity, technology and band, channel, PCI, azimuth, beamwidth, height and state; the same order on NQ Maps. |
| **A test** | The campaign and CDR it comes from and its RSRP and SINR. |

The cells of the call and of each Non-Qualified Call are its **Start cell** and **End cell** (its **Serving cell** when one served all of it), its **Handover cells** on a line of their own and the NR cell of an NSA call. Those of the operator of the call are named by their inventory name (such as *70002-L3 (LTE B3)*), the others by technology, band and identity (*LTE B20 · 30001001*, *GSM 900 · LAC 876 · CI 37171*).

**Above the map** (and above the larger map), on one line:

| Control | What it does |
| --- | --- |
| **Radius** | 500 m to 10 km: chooses the area. A call opens with the radius that holds every NQ call of its hotspot and its cluster (rounded up to 100 m, marked *(groups)* in the list), or with 1 km when it is in neither. The radius chosen holds while the call stays open. |
| **Colour NQ calls by** | What their colour tells: *Site*, *Call type*, *Root cause domain*, *Campaign* or *Operator* (each operator in the colour the [Operator Maps](workspace-config.md#operator-maps) give it), as on NQ Maps. |
| **And Group** | A switch, when the call is of a group: the outlines of its groups. |
| **Operators** | The NQ calls of its operator only, of the Focus operators of the [Operator Maps](workspace-config.md#operator-maps) (**Focus operators only**, the default when the workspace has some; its tooltip names them) or of every operator. |
| **Call types** | The call types of the NQ calls around (*Voice*, *WhatsApp*, *Data*…), every one checked by default: only those checked are drawn, counted in the card over the map and listed; the call itself always. Your browser keeps the choice. |
| **Map** | The map under the layers (see below). |

Your choices (except the radius) are kept in your browser for the next calls.

**What the map shows:**

| On the map | What it shows |
| --- | --- |
| **This call** | A pin where it failed, its estimated way and the drive of its car (see below). The radius around it is dashed. |
| **Cells of the call** | Each cell of its Cell ID trace at its site, the lines to them and its handovers (see below). |
| **Sites** | The inventory sites of the networks that serve its operator within the radius (and those of its cells wherever they are), as triangles in the colour of their vendor ([Vendor Maps](workspace-config.md#vendor-maps)). The sites where the call started and ended are ringed (see below). Their sectors (azimuth and beamwidth) are drawn from zoom level 14 and their Site ID from level 15 (those where the call started and ended at every level). A dashed sector marks a cell with the PCI and channel of a cell of the call (a PCI collision or confusion to check). |
| **NQ calls** | The other Non-Qualified Calls around it, as stars (see below). |
| **Groups and hotspot zone** | Its clusters, time-window issues and hotspot, as the Groups slide of the presentation draws them (see below). |
| **RSRP / SINR (from CDR samples)** | The tests around it, completed or not, with their LTE RSRP, LTE SINR, NR RSRP or NR SINR (the average of the test) in the [Map Levels](#map-levels) of the workspace (by default the levels of the [Network Insights maps](network-insights.md#coverage-and-interference-maps), with *Extremely poor* below −120 dBm), the same as those of the [Layer3 Logs](#layer3-logs-on-the-map), or their result. The legend titles each measure shown with its unit (*LTE RSRP (dBm)*, *LTE SINR (dB)*, *NR RSRP (dBm)*, *NR SINR (dB)*) and gives its levels without it. They start hidden: each measure has its switch in the card **CDR Info**, with how many tests have it, in the shapes of the layers of the KMZ files (a circle for RSRP, an inverted triangle for SINR, a square for the result; NR with a black dot), several at once side by side at each test. Their CDRs are those of **Campaigns** (see below). |

**This call:**

- **Pin:** where it failed (where it ended), taller than its mark of NQ call with all the outlines of its groups, so that it is seen first.
- **Its way (estimated)** (switch **Way of the call (estimated)** in the section Route of **CDR Info**): a winding road in its colour, with a white edge, a dashed white centre line and an arrow towards where it went, with **START** (green) where it started and **END** (red) where it ended, beside them. Its bends are a sketch, not the streets it took; hovering it tells how far it went, how long it lasted and which way it took.
- **A Voice call** gives where it started (a green dot) and where it ended: its road joins them.
- **A Data test** gives only where it started and how far it went (its `Test_Distance`). Its pin marks where it started (*This test (where it started; it failed on its way)*), and its road is simulated: those metres from where it started along the way of its car (towards its tests after it, else on from the one before it, straight on past them), with the arrow where it ended. When the way of its car is unknown, a dashed circle of that distance around where it started marks the zone where it went.
- **The drive of its car (estimated)** (its own switch **Drive of its car (estimated, 15 min before and after)**, beside that of the way of the call): grey roads from test to test around it, each with an arrow towards where it was heading.
  - It goes through the tests of its drive (see *Its drive* below) that a car could have driven to one after the other, at up to about 145 km/h, so that those of another car measuring nearby at the same time are left out.
  - It joins the road of the call: the road from its test before ends where the call started, and the road to its next test starts where it ended.
  - Hovering a road tells from where to where, how long before or after and how far.

**Cells of the call:**

- **Each cell of its Cell ID trace, in order:** *Served the start*, *Handover*, *Served the end*, or *Served the whole call*, with the PCI the CDR gives it. A cell the trace repeats in a row (a new TAC, or a moment on a cell without identity it came back from) is one cell, never a handover.
- **Where each cell is placed:** at its site of the Network Inventory. It is the cell of a network that serves its operator ([Serving Networks](workspace-config.md#serving-networks), its own network first) nearest to where it served the call, within the distance of the Serving Networks (30 km by default).
- **Far cells:** else, farther, the cell with the PCI and channel the CDR gives it. An identity alone farther may be another cell with that number, while a cell on a high mast serves a call on high ground from much farther. Its label then says how far it is (*N54810231 (LTE B20) · 36.5 km away*) and the Diagnosis judges its serving distance.
  - **Why it is the real one:** **Cells of the call** and its tooltips (on its site, its sector and its handover arrows) say it: its ECI (NCI), PCI and EARFCN (NR-ARFCN) are those of the CDR and of that cell in the Network Inventory, and, when the call has Layer3 Logs, they measured that PCI and channel too.
- **Lines:** a solid line joins where the call started to the cell of its start (green), and where it failed to the cell of its end, or of the whole call (red).
- **Handover arrows:** each **handover** is a cyan arrow from the cell before it to the cell after it, numbered with the order of that cell (as the **Cells of the call** list and the badges of the sites).
  - From sector to sector when the map shows the sectors (from zoom level 14, with **Sites** on), else from the side of each site where its cell points.
  - The arrows between the same two cells (back and forth) go side by side; hovering the number of an arrow tells the cells and sites it joins.
  - Every line has a white edge, so it shows over the shapes of the groups, and two lines with the same ends go side by side.
- **Where each handover took place (estimated):** the CDR does not record it. A dashed ring numbered as its arrow marks it beside the road of the call (on its left, away from the direction arrows of the logs), with its own switch **Handovers on its way (estimated)** in the section Route of **CDR Info**, and on the real way of the UE when its log draws it.
  - It is estimated by the time the call spent on each band (its RAT timeline: that of the A side of a Voice call, the PCell one of a Data test; the cells of a band sharing its time, at an even speed), or spread evenly in their order when that timeline does not match its cells.
  - On a Data test they lie on its simulated way; it has none without one.
- **Sites of the cells:** a badge with its order marks the site, and its sector is drawn in the colour of its role, at every zoom level; the cells of its start and of its end are named at the tip of their sector. The site where it started is ringed in green and the one where it ended (where it failed) in red, both rings when one site served all of it.
- **Cells not in the inventory:** when the inventory does not hold the cell of its start or of its end near the call (the 2G and 3G cells, which the Network Inventory does not list, or a cell missing from it within that distance), the dashed ring marks the nearest site of those networks to where it started or failed, an estimate the legend names as such. A note above the map names its cells as the CDR gives them (such as *GSM 900 · LAC 876 · CI 37171*).
- **Legend:** it lists only the roles the cells of the call have; a call served by one cell has no start line nor handover arrow.
- **NR leg (by PCI):** an NSA call of a Data CDR adds the NR cell with its NR PCI (and NR-ARFCN) on the site of its LTE anchor, else the nearest within 5 km.

**NQ calls around it:**

- **Marks:** stars (the diamonds are the PCIs and signalling of the logs), larger than on NQ Maps, of their latest version.
- **Which ones:**
  - those of its [groups](#nq-hotspots-clustered-time-window-issues) and of the other clusters and time-window issues of its hotspot;
  - those of its operator at its **site**, always and wherever they are: the site counts every campaign, NR Mode and call type, while a hotspot and a time-window issue keep to its campaign and NR Mode, and a cluster to its NR Mode, its campaign and those of the Cluster period, without the Ping tests;
  - the others of the operators chosen in **Operators**.
- **Colour NQ calls by** chooses what their colour tells, as on [NQ Maps](#nq-maps):
  - *Site* (the default): the site their CDR gives, each in a colour of its own and those of the site of the call in burgundy; the legend names the twelve sites with most NQ calls, the site of the call first.
  - *Call type*, *Root cause domain* (the one decided, else that of the DT Analyzer RCA), *Campaign* or *Operator*.
- **And Group**, a switch beside it when the call is of a group, adds over that colour an outline in the shape of the NQ call (a star) for each group of the call it is of, in the colour of the group.
  - Its **cluster** green innermost, then its **time-window issue** blue outside it; a call of both has two outlines.
  - Each is that of the call alone: the calls the card over the map counts *in its cluster* and *in its time window*, not the other clusters and time-window issues of its hotspot, unless one of them filters the list. Never its hotspot, which every NQ call of its groups is of.
  - Each group has its own switch in **CDR Info**, which shows or hides its shapes on the map and its outlines.
- **One group filtering the list:** when the list of calls is filtered by its cluster or its time-window issue (with its card in the header or its ID in the panel), the map shows that group alone, with its shape. The calls of its other groups, their shapes and the hotspot zone leave it, and the legend names the group.
- **Stacked calls:** the calls on one point make one mark with how many they are (*×11*), its colour that of the most related one. Hovering it starts with *At this point: N NQ calls*.
- **Legend:** shows only what the map shows.
- **Campaigns:** those of **Campaigns**, at the top of the card **CDR Info** (see below).
- **Left out:** the Ping tests, as NQ Maps does, and everything of the other NR Mode (NSA and SA fail along different paths): its NQ calls and its samples (no group joins both NR Modes).

**Groups and hotspot zone** (in the legend under **Groups of the call**):

- **Clusters:** a green circle around the NQ calls of each cluster, lighter than the green of the site where the call started.
- **Time-window issues:** a blue ellipse along the NQ calls of each time-window issue that make its hotspot.
- **Its own groups:** whole (a cluster with the calls of the campaigns of its Cluster period) and bolder; those of the other calls of its hotspot with its calls, the other clusters and time windows dashed.
- **Size:** each shape is the smallest that holds its calls, so every NQ call of its groups is inside one (a call of its hotspot in neither takes a circle of the whole hotspot), the call itself too where it failed.
- **Time-window paths:** a dashed line joins the failures of each time-window issue in their order, each within the Time window and the Time-window distance of the one before, and a badge in its colour numbers them (1, 2, 3…). The line of its own time window is blue and that of each other one of its hotspot has a colour of its own, as the legend lists them, so that crossing lines can be told apart. **Time-window paths**, a switch of the card **CDR Info**, shows or hides the lines and their numbers (the browser remembers the choice).
- **Hotspot:** the zone in orange that they make together, outlined by a wide orange edge between two white ones so that its final area stands out. The lines of the groups and of the zone go over the sectors of the sites, so that none hides them.
- **Counter card** over the bottom left of the map: the **NQ calls on the map** (the call itself too) and how many are **in its hotspot**, **in its cluster** and **in its time window**: their envelope with the **Hotspot join** OR of the [Prioritization Rules](#prioritization-rules), where its clusters and its time-window issues meet with AND.
- **Legend:** its own shapes with their calls and size (*Its cluster: 5 NQ calls within 134 m*, *Its time window: 4 NQ calls along 616 m*), how many of the other calls of its hotspot, and the zone.

**The cards over the map.** Two cards side by side over the top left of the map (one below the other on a narrow map) switch what it shows by where it comes from:

- **CDR Info:**
  - **Campaigns**, at its top, chooses the campaigns of everything the map draws from the CDRs: its NQ calls and their list, the RSRP / SINR samples, the **Radio around the call**, the Diagnosis hints and its drive, the drive of its car and **Its drive**. *Selected campaigns* (the default) takes every CDR of the campaigns chosen in the Campaign filter of the page (of every campaign while none is chosen); *Call campaign* every CDR of its campaign. Always of the NR Mode of the call, and Voice, Speech and Data CDRs together. The Diagnosis hints and the Decisions at its place count the NQ calls of every campaign.
  - **RSRP / SINR:** the samples of the CDRs (see above).
  - **NQ calls:** the NQ calls around and its groups when it has them: **Hotspot zone**, **Clusters**, **Time windows** and **Time-window paths**, each switching its shapes on the map and its outlines on the NQ calls.
  - **Sites** (when a Network Inventory places them): **Sites**; **Start and end cells**, the solid lines from where it started and failed to the cells of its start and end, and the dotted one to the NR cell of an NSA call; and **Cell path**, its cells and handover arrows.
  - **Route:** its way and that of its car.
  - Each layer with its switch and how many it shows.
- **LOGS Info:** the layers of its [Layer3 Logs](#layer3-logs-on-the-map), when it has some.

How the cards behave:

- **Folded at first:** each time a map opens. Each has a switch in its header for all of it.
- **Fold or unfold:** a click anywhere on its header. A click outside it, on the map or on the other card, folds it.
- **Sections:** its layers are in sections, all unfolded at first, that fold with a click on their header (the browser remembers which).

**Legend.** It waits folded in the **Legend** card over the bottom right of the map.

- **Unfold it:** a click on its header unfolds it upwards over the map, above the panels over its bottom and below the zoom buttons, scrolling when it is longer. It is in the images of the map while it is unfolded.
- **Boxes:** **CDR Info** and **LOGS Info**. Unfolded, they open wide in a row of their own below the folded card, which stays where it was (CDR Info with its sections in three columns: RSRP / SINR, Sites & Cells with Route below it, and NQ calls).

**Floating cards.** **CDR Info**, **LOGS Info** and **Legend** float once unfolded:

| To… | Do this |
| --- | --- |
| Move a card over the map | Drag its header (a click on it still folds it). |
| Make it smaller or larger | Drag its corner: the bottom right one of CDR Info and LOGS Info, the top left one of Legend. |
| Put it back in its place with its own size | **Restore**, in its header, shown once it was moved or resized. |
| Fold it back | A click outside, keeping the size it was given while the map is open. |
| Keep it open, also on the next maps | The **pin** of its header (kept in your browser), until a click on its header folds it. |

**Map types.** **Map**, at the right end of the controls above the map, chooses the map under the layers, the same on every map of the page:

- *OpenStreetMap (original)*.
- *OpenStreetMap in grey (light)*, the default: its streets under a white veil, so that the samples, events and calls stand out.
- *Plain (no labels)*.
- *Terrain (elevation)*: contour lines and hill shading, OpenTopoMap.
- *Topographic*, *Satellite* and *Dark* (Esri).

#### Layer3 Logs on the map

Follow the real way and the radio of the UE of a call from its Layer3 Logs.

A call with a session in the [Layer3 Logs](workspace-management.md#layer3-logs) of the workspace (found by its `JOIN_ID`; **Layer3 Logs** in its header says which UEs) shows on its map every layer of the KMZ files the NQ team opened in Google Earth.

- **Read from the imported logs:** no KMZ file is imported.
- **Same points:** checked against the 2,382 KMZ files of UK Q3 2026, every layer of every file has the same points by channel and PCI.

On the map:

- **Its real way**: the GPS positions of the log of the UE replace the sketch of its way, drawn as a road in the colour of the logs, from **START**, where its log starts, to **END**, where it ends (the pin stays where the CDR says it failed); the green dot where the CDR says it started and the rings of its handovers stay, the rings along that way by their estimated time. The map fits the whole way of the UE. With the route of the logs off (or the card switched off), the map shows the way of the CDR again.
- **LOGS Info**, the card over the top left of the map beside **CDR Info** (and in its images), lists the layers by section, each with its switch, its marker and how many points it has. The switch of its header shows or hides them all (its routes too), and its title folds it. Unfolded it is wider: Route, Signalling and RAN side by side (their notes below their names, long names on two lines), then a matrix for each technology the logs have (LTE, NR; side by side when the card is wide enough, one below the other otherwise):
  - **Signalling timeline**, a switch at its top, shows or hides the timeline of the call (below); the **×** of the timeline hides it too, and this switch shows it again.
  - **Route**: **Route (GPS)** (the real way of the UE, from the GPS of its log) and **Direction of travel** (arrows beside the road of the way of the UE, on the right of where it went so that neither hides the other, worked out from its positions).
  - **Signalling**: **Events** (4G, 5G EN-DC, 5G NR, Other) and **L3 Signaling** (LTE-NAS, LTE-RRC, NR-NAS, NR-RRC, SIP, Other), each point a message or event with its details.
  - **LTE** and **NR**: a matrix with a row for each measure (EARFCN or NRARFCN, PCI, RSRP, RSRQ, SINR and UE Tx Power) and a column for each kind of cell — **PCell**, **SCell** (the secondary cells), **NCell** (the neighbour cells) and, in NR, **LTE NCell** (the LTE neighbours reported while on NR) — each cell with its switch, how many points it has and its **+**, and a dash where that kind of cell has no such measure (UE Tx Power is of the PCell alone, and the neighbours have no SINR). Both matrices have the columns of the kinds of cell with points in either, in that order and of the same width, so that those of LTE and NR line up.
  - **RAN**: **RAN Configuration** (every serving point by LTE, 5G EN-DC, 5G SA, GSM or UNKNOWN).
  - **+** unfolds a layer (below the matrix, for those of LTE and NR) by channel (as the KMZ files name it, such as *EARFCN 1363 (B3, 1821.3 MHz)* or *NRARFCN 628032 (n78, 3420.48 MHz)*), each with its own switch and its PCIs as chips, so one carrier or one cell can be followed along the way.
  - A voice call has a session for each end: **Both**, **UE A** or **UE B** chooses which one the map shows.
  - **Hide all** switches every layer off, **Default layers** comes back to the layers the map opens with (the route, the PCell RSRP of LTE and NR, as the KMZ files open, and the events). The card keeps its layers for the next calls.

**Markers** are those of the legend of the KMZ files; NR points have a black dot in the middle:

| Marker | Layer |
| --- | --- |
| Circle | RSRP |
| Triangle | RSRQ |
| Inverted triangle | SINR |
| Pentagon | UE Tx Power |
| Square | A channel and the RAN Configuration |
| Diamond | A PCI and the L3 messages |
| Hexagon | An event |
| Arrow | The direction |

**Colours:** RSRP, RSRQ, SINR and UE Tx Power take the [Map Levels](#map-levels) of the workspace; RSRP and SINR those of the RSRP / SINR samples of the CDRs, so both sources share one legend. A channel or a PCI keeps its colour on every map. By default:

| Measure | Levels |
| --- | --- |
| RSRP | *Excellent* (≥ −80 dBm, dark green), *Good* (−90 to −80), *Fair* (−100 to −90), *Poor* (−110 to −100), *Very poor* (−120 to −110), *Extremely poor* (below −120 dBm, dark red) |
| SINR | *Excellent* (≥ 20 dB), *Good* (13 to 20), *Fair* (5 to 13), *Poor* (0 to 5), *Bad* (below 0) |
| RSRQ | The ranges of the KMZ files in the six levels of the RSRP, with their names and colours: *Excellent* (≥ −10 dB), *Good* (−14 to −10), *Fair* (−16 to −14), *Poor* (−20 to −16), *Very poor* (−24 to −20), *Extremely poor* (below −24 dB) |
| UE Tx Power | The ranges and colours of the KMZ files, the other way round (blue below −10 dBm, dark red from 24 dBm), named by their range alone |

- **Legend:** its **LOGS Info** box shows the route and the ranges of the layers on, each measure with its unit in its title (*RSRQ (dB)*).
- Hovering a point tells its values (time, UE, RAN Configuration, channel, PCI, RSRP, RSRQ, SINR, UE Tx Power, ECI or NCI; the name, group and summary of an event; the layer, direction and SIP response of an L3 message); a click shows them below the map, where **All the fields of this record** reads every value of the record of the log (the IMSI of the test SIM is never shown).

- **Signalling timeline**, below the map (and in its images), for each UE shown:
  - **RSRP:** that of its LTE PCell (blue) and NR PCell (purple, dashed) over the time of its session, against the colour bands of the legend.
  - **Messages:** below them, its **Events**, **RRC**, **NAS** and **SIP** messages one after another, in the colours of their groups. The failures, re-establishments, rejects, releases and SIP errors (4xx to 6xx) are larger and ringed in red, and a dashed red line marks where the session ended with its status (*Failed*, *Dropped*, *Cutoff*).
  - **Axis:** the seconds from its first record.
  - **Hover a point:** what it is, and a ring at its place on the map. **Click it:** the map centres on it and shows its values below the map.
  - **Fold, hide:** a click anywhere on its header folds or unfolds it; its **×** hides it (the switch **Signalling timeline** of LOGS Info shows it again).
  - **Over the larger map:** it floats over the bottom of the map, below the elevation profile when there is one; the cards unfolded end above these panels and scroll there.
- **Cursor of the timeline:** it follows the session. The map shows where each UE was at that moment, heading where it went, with its events and messages of the last 3 seconds ringed where they happened (the latest named). The map moves to keep the UE on it, and above the chart the time, the RSRP of its LTE and NR PCell and its latest messages show.

| To… (cursor) | Do this |
| --- | --- |
| Move the cursor | Drag along the timeline. |
| Step 0.5 s or 5 s | Once the timeline has the focus, <kbd>←</kbd>/<kbd>→</kbd>, or <kbd>Shift</kbd> + <kbd>←</kbd>/<kbd>→</kbd>. |
| Go to the start or the end of the session | <kbd>Home</kbd> / <kbd>End</kbd>. |
| Remove the cursor | <kbd>Esc</kbd>, or its **×**. |

- **Logs of the NQ calls around**, a switch at the bottom of the card **LOGS Info**, adds the logs of the other NQ calls of its map (those of its groups and its area) with the same layers, faded below its own, as [NQ Maps](#nq-maps) shows them.

App Events records the layers read (`nq_call_l3_layers`, with the call, its JOIN_ID, its UEs, their points, the datasets and how long it took) or that could not be read (`nq_call_l3_layers_failed`).

Below the map:

- **This call**: its result, failure, phase, technology, times and serving site (that of the cell that served its end, else its start), its cells in order with their site and distance (a click, or <kbd>Enter</kbd>, centres the map on the site), the radio of the call (the Min, Avg and Max of each RSRP, RSRQ, SINR, transmit power, BLER, CQI… of the CDR row) and its other cell, handover and serving fields.
- **Non-Qualified Calls around**: those of its hotspot, cluster and time-window issue, at its site, and the others (of the campaigns chosen in **Campaigns**).
  - **Counts:** how many each, and how many within the radius, the call itself included (in its hotspot, cluster or time-window issue when they hold 2 calls or more).
  - **Order:** those of its groups and site first, nearest first, each with its tags and **Open**.
  - **Show one on the map:** click it (or <kbd>Enter</kbd>): the map centres on it.
  - **How many the map brings:** every NQ call of its campaign within the radius, and of its groups and its site, and the 600 nearest of the other campaigns. With **Every campaign**, the header tells how many more of the other campaigns were left out.
- **Diagnosis hints**: what the map suggests, each finding marked *To check*, *Worth a look*, *Fine* or *Note* (the first ones first; a click on one about a site shows it on the map):
  - **Coverage** and **Interference**: the average RSRP and SINR of the call against the levels of Network Insights (LTE weak below −110 dBm, interfering below 0 dB; NR below −115 dBm and −3 dB). A low SINR with a good RSRP points at interference, a low SINR with a weak RSRP at the coverage. A **Coverage hole** (to check) is a weak coverage, or no RSRP at all, where the nearest site of the networks serving the operator is at least 1.5 times its inter-site distance away.
  - **Serving distance**: the site of the cell where the call ended against its inter-site distance (ISD, the mean distance to its 3 nearest sites of its network; see [The network around the call](#the-network-around-the-call)): flagged from twice its ISD and 1 km (overshooting), or beyond its ISD when a site three times nearer was there (a missing neighbour or overshooting). A site without others of its network within 40 km is judged by fixed distances instead: 5 km, or 1.5 km with a site three times nearer.
  - **Overshooting cells** (worth a look): a cell of the call that served it from at least twice the inter-site distance of its site and 1 km (5 km for a site without an ISD), pointing at the call (within half its beamwidth, at least 30°, of its azimuth): it reaches the place of the call with its main beam, so its tilt is worth a look.
  - **PCI collision**: cells around with the PCI and channel of a cell of the call.
  - **Cells in service**: cells locked, halted or disabled on the sites of the call (to check) or around it, and sites planned or in progress around.
  - **Other operators**: the share of tests not completed of its operator against that of the others in the tests around (at least 5 of each), compared with a two-proportion test that weighs how many tests each did, with their median LTE RSRP. *Its network fails more here* (to check) when its share is clearly higher (z of 2 or more), at least 1.5 times and 2 points above the others — for example 9% of 426 tests against 0% of 1,447; *Fails a little more than the others* when it is higher without enough tests to be sure; *Every operator fails here* when the others do not complete 5% or more of their tests (about five times the usual share of a network), so the place may explain it.
  - **Repetition**: the NQ calls of its operator at its place (a repeated issue from the Cluster size of the [Prioritization Rules](#prioritization-rules), in one or several campaigns) and in its hotspot.
  - **Handovers**: **Ping-pong handovers** when the call went back to a cell it had left, with how many handovers in how much distance and time and the cells it went back to (to check when it went back twice or more within 500 m, as no cell dominates there), many handovers (4 or more), how many and the cell it ended on, and the NR leg of an NSA call not found.
  - **Layer3 Logs** (with a teal edge, for a call with a log): what its log shows in its last seconds — an **SCG failure**, an **RRC re-establishment**, a **SIP error** or a **reject** of the network (to check), a **stronger neighbour without a handover** (a neighbour of the serving channel 6 dB above it for 3 seconds: to check, worth a look when there were handover attempts), a **handover** right before the failure, the **coverage** (RSRP below −115 dBm) or **interference** (SINR below −3 dB) of LTE and NR at the failure, the **UE at maximum power** and a **high BLER**, and the records without measurements; *Fine* when it shows none of them. A click on one shows its moment of the log on the map (its point, centred and selected).
- **Decisions at its place**: the Root Category and Root Cause already chosen for the other NQ calls at its site and in its hotspot, the most frequent first, with their calls, campaigns, statuses and some of their JOIN_IDs; **Use** gives this call the same Root Category and Root Cause (editors). It also counts those still without a root cause.
- **Its drive**: the tests of its operator 15 minutes before and after the call and within 30 km (from the CDRs of **Campaigns**), to see whether the radio got worse before it and whether the next tests recovered.
  - **Each test:** its time from the call, test, result, RSRP, SINR and distance; the call itself marked and those not completed in red.
  - **Show one on the map:** click its row: the map centres on it.
  - The map draws the way of the car through them.
- **Serving site health**: the calls that started on its serving site (the site ringed in red, else in green) in each campaign and NR Mode (their latest version) and how many were Non-Qualified, against the NQ rate of its operator on every site (in orange from 1.5 times, in red from twice that rate) and that of every operator on the site, with the cells of the site.
- **Radio around the call**: per operator (its operator first), the tests within the radius, how many did not complete, the median LTE and NR RSRP and SINR and the share of values below −110 dBm and 0 dB, then the sites around, the nearest one, the cells with the PCI and channel of a cell of the call and the Network Inventory used (the newest snapshot of each network).

App Events records each map opened (`nq_call_map`, with the call, its JOIN_ID, the radius, the samples chosen, what it found and the NQ calls of other campaigns left out, the Diagnosis hints to check and worth a look and how long it took) or that could not be prepared (`nq_call_map_failed`, with the error). The first map of a CDR reads the tests of the CDR, a few seconds for a large Data CDR; the next calls of that CDR show at once.

### Comments and history

Authors can edit and delete their own comments, and admins and super-admins can edit or delete any comment. Edited comments show **edited**; deleted comments leave a note with who deleted them and when, and the history keeps the previous text of every edited or deleted comment.

Admins and super-admins can delete the history: the **×** of a change deletes that entry, **Clear history** above the timeline (shown when the call has a history) deletes the whole history of the call, and **Clear history** in the bar of the selected calls deletes the history of all of them. Only the history is deleted: the status, team, analyst, root cause and comments stay, and the deletion is recorded in the audit log.

> [!CAUTION]
> **A deleted history cannot be recovered** (importing an older NQ Call Tracking package adds back the entries it contains), and the Progress View counts only the remaining changes.

> [!NOTE]
> **Nobody overwrites a newer follow-up by mistake.** When another user changes a call after you loaded it, your change is refused and the list reloads; the same applies to the fields saved in the tabs. The open page refreshes the calls and the open call every minute.

## NQ Analysis Configuration

**NQ Analysis Configuration**, beside the [Sections bar](#sections-bar) (for every user; only its icon on a phone), opens on hover, or with a click, the configuration of the workspace, shared by every user, each option with the icon it has in the sections menu of the tab:

> [!IMPORTANT]
> **Only admins and super-admins change the NQ Analysis Configuration.** The other roles open every option to see it, from the button beside the Sections bar or the sections menu of the tab: a card at the top of the menu and of each option says that only admins and super-admins can change it, its controls are locked and there is no Save. `user-editor` accounts keep following up the calls (status, team, analyst, root category and cause, fields, comments and bulk changes), and every role arranges its own [table layout](#table-layouts).


| Option | What it configures |
| --- | --- |
| [Prioritization Rules](#prioritization-rules) | Which calls are analysed first: the [strategy](#strategies) of the workspace (Dual Queue (Cities first), Dual Queue (Roads first), Dual Queue (Scoring Based) by the impact levels, Vodafone Proposal in one queue, or strategies of your own), the queue and the Priority it gives. |
| [Fields & Sections](#fields-and-sections) | The fields every call is followed up with, their lists and Excel order. |
| [Statuses & Teams](#statuses-and-teams) | The NQ Call Statuses and the responsible teams with their members. |
| [Status Rules](#status-rules) | How the status follows the Analysis, Implementation and Planning fields. |
| [Root Cause Catalog](#root-cause-catalog) | Domains, Root Categories and Root Causes, with their keywords, and the suggestion rule. |
| [DT Analyzer RCA Rules](#dt-analyzer-rca-rules) | How the DT Analyzer RCA finds the root cause of every call from the data of its CDR. |
| [Map Levels](#map-levels) | The levels of RSRP, RSRQ, SINR and UE Tx Power the maps of the calls and NQ Maps colour the samples and the logs by. |
| **Import Ericsson RCA Results** | The results of the Ericsson RCA, by `JOIN_ID` (see [Ericsson RCA results](#ericsson-rca-results)). |
| **Import Previous NQ Analyses** | The analyses made with the previous tool, by `JOIN_ID`: admins and super-admins import them, and the other accounts open it read-only (see [Previous NQ Analyses](#previous-nq-analyses)). |
| **Link Analysts to Accounts** | Links each analyst and reviewer without account to their user account: the account becomes the Analyst of the calls they analyse and the Reviewer of those they reviewed (see [Link Analysts to Accounts](#link-analysts-to-accounts)). |

The imports and Link Analysts to Accounts come after a line. The sections menu of the Non-Qualified Calls tab lists the **NQ Analysis Configuration** too, after a line, with every option: choosing one opens it on the page.

> [!TIP]
> **Every configuration can go back to the values of a new workspace:** **Default Fields & Sections**, **Default Statuses** and **Default Teams**, **Default Rules** (Status Rules, DT Analyzer RCA Rules and Prioritization Rules), **Default Levels** (each measure of the Map Levels), **Default Catalog** and **Default Rule** (Root Cause Catalog and its Suggestion Rule), **Default Columns** (Columns of the table) and **Default Equivalences** (Previous NQ Analyses). Each one fills its dialog and **Save** applies it, except Default Equivalences, which applies once confirmed; values still used by a call are never removed, nor the catalog values a DT Analyzer RCA rule gives.

## Fields and sections

**Fields & Sections** (in the NQ Analysis Configuration menu; admins and super-admins change it) configures the catalog of fields every call is followed up with, shared by every user, in the order of the Excel export. **Sections** renames and recolours the six sections (their tabs, the colours of the table headers and of the Excel; by default General blue, RCA yellow, Failure Details red, Analysis purple, Implementation green and Planning a darker green); chips above the fields show the fields of one section, and a filter finds them by name.

Each field has a name, a **section**, a **source** and a **type**:

| Source | Fields |
| --- | --- |
| **Entered by the analysts** | A **List** of values, each with a colour, **Text** (up to 300 characters), **Long text**, **Number**, **Date** (YYYY-MM-DD) or **Yes / No**. **Propose the CDR value of** offers an empty field the value of a call field (*Use the CDR value* in the call; for example Failure Latitude and Longitude, Serving Cell, Band and Vendor 1 when Failure, Host Network when Failure). |
| **Follow-up of the call** | The NQ Call Status, Team Responsible, Analyst, Date last modification, Comments, Selected Root Category and Selected Root Cause. They can be renamed, moved to another section and reordered, but not removed. |
| **From the CDR** | A call field, the last cell of the Cell ID chain (`last_cell_id`) or a CDR column (`column:<name>`, indexed automatically), read only (for example the NetCheck RCA Failure Classification, Suggested Category and Suggested Cause, the Last Cell ID and the Failure Comment). |
| **From the Ericsson RCA** | A column of the [Ericsson RCA results](#ericsson-rca-results), read only (Ericsson RCA Category A … Ericsson RCA Evidence). |
| **From the DT Analyzer RCA** | A value of the [DT Analyzer RCA](#dt-analyzer-rca), read only: its Root Domain, Root Category, Root Cause, Rule or Evidence. |
| **Derived from the call** | A list whose values have keywords looked for in some call fields; the first value whose keywords appear is the value of the call (Session Type: WhatsApp, MULTI-RAB, CALL, HTTP Transfer, Browsing & Streaming and Interactivity & Ping from the CDR `Session_Type` and Test Name). |
| **From the NQ Prioritization** | A value of the [NQ Prioritization](#nq-prioritization), read only, with its own type: Scoring Impact, Scoring Points Lost, Scoring KPIs Lost, Repeated Issue, Repetitions, Repeated Campaigns, Repetition Place, Hotspot ID, Time-Window ID, Cluster ID, Prioritization, Prioritization Rule (whose values are the steps of the strategies), Prioritization Queue and Expected Gain. The call shows them in its **Prioritization Info** subpanel, above its phases, not in the tab of their section (the IDs of its groups in its header). |

Each field can be a **Summary breakdown** (lists and Yes / No) and, when the analysts enter it, be **Required to close**: a call cannot be closed, by hand or by a change of its fields, while a required field is empty. Each value of a list can be **Final**: it ends its phase (by default Finished, Rejected and Invalidated of Analysis Status, Evaluated, Implemented and Not Applicable of Implementation Status, and Planned of Planned Status). Choosing a final value in a call, or closing it by hand, while fields of the analysts are still empty shows them grouped by section, with **Go back and fill them** or **Continue anyway**. The status of each phase (the first list of Analysis, Implementation and Planning) stands out with a darker control in its tab, as the NQ Call Status and the Priority do in the header. A description is shown when hovering the field. The order of the list (↑ ↓) is the order of the fields in their section and in the Excel export; whether a field is a column of the table and of the Excel is chosen in [Columns](#columns), in the [table layout](#table-layouts) of each user and, with **Save for the workspace**, in that of the workspace (a new field goes to the Excel and not to the table).

> [!WARNING]
> Renaming a list value updates every call that uses it and the Status Rules; a value or a field still used by a call cannot be removed, and the type and source of a field with values cannot change.

**Default Fields & Sections** leaves only the sections and fields of the [default catalog](#default-catalog), in their order, names, colours, settings and list values (a field keeps its values and a list value with the same name its calls), and **Save** applies it; a field or a value that is not a default one and is still used by a call cannot be removed, so Save names it to clear or rename first.

### Default catalog

The default catalog is the 37 fields of the meeting workbook and those of the analyses of the previous tool (see [Previous NQ Analyses](#previous-nq-analyses)), in its order but with the DT Analyzer RCA first, then the NetCheck RCA and the Ericsson RCA, with the Ericsson RCA Initial Category, Initial Subcategory and Evidence, and the Last Cell ID and Failure Comment of the CDR in Failure Details:

| Section | Fields |
| --- | --- |
| **RCA** | The fields of each source named after it: DT Analyzer RCA Root Domain, DT Analyzer RCA Root Category, DT Analyzer RCA Root Cause, DT Analyzer RCA Rule, DT Analyzer RCA Evidence, NetCheck RCA Failure Classification, NetCheck RCA Suggested Category, NetCheck RCA Suggested Cause, Ericsson RCA Category A, Ericsson RCA Subcategory A, Ericsson RCA Category B, Ericsson RCA Subcategory B, Ericsson RCA Initial Category, Ericsson RCA Initial Subcategory, Ericsson RCA Suggested Category, Ericsson RCA Suggested Cause, Ericsson RCA Evidence; then Initial Root Category, Initial Root Cause, Selected Root Category, Selected Root Cause, Selected Root Technology. |
| **General** | NQ Call Status, Priority (P1 to P8, shown after the NQ Call Status at the top of the call, filled by the [strategy](#strategies) while nobody chooses it; each value in the colour of the queues and steps, from red P1 to grey P8, changed in its values), the values of the [NQ Prioritization](#nq-prioritization) (Prioritization, Prioritization Rule, Prioritization Queue, Expected Gain, Scoring Impact, Scoring Points Lost, Scoring KPIs Lost, Repeated Issue, Repetitions, Repeated Campaigns, Repetition Place, Hotspot ID, Time-Window ID and Cluster ID; Prioritization, Scoring Impact, Scoring Points Lost and Repeated Issue are columns of the table, and Prioritization, Scoring Impact and Repeated Issue breakdowns of the Summary), Team Responsible, Analyst, Reviewer, Unique ID, Date last modification, Comments. |
| **Failure Details** | Session Type, Failed Party (MOC/MTC) (UE1/UE2), Host Network when Failure, Last Cell ID, Serving Cell when Failure (proposing the Last Cell ID), Band when Failure, Vendor 1 when Failure, Vendor 2 when Failure (the second vendor when the failure involves two), Failure Comment. |
| **Analysis** | Analysis Status, Tunnel Failure, Needed Technology, Failure Latitude, Failure Longitude, Problem Location, Solution Location, Polygon Area, Description, Findings, Proposed Measure. |
| **Implementation** | Implementation Status (Not yet evaluated in red, Under evaluation, Evaluated, Implemented and Not Applicable), Implementation Team, Implementation Proposals, Implementation Site, Notice to VF3. |
| **Planning** | Planned Status, Planned Date, Planned FY. |

The **Analyst** (in the follow-up of the call, beside the Team Responsible) is who analyses the call: a user account, or an analyst without account that only the [Previous NQ Analyses](#previous-nq-analyses) bring; the **Reviewer** (beside it) is who reviewed the analysis: a user account of the workspace (any of them, not only the members of the team), or a reviewer without account that only the [Previous NQ Analyses](#previous-nq-analyses) bring, tagged **No account** and never offered for new calls; the **Implementation Team** is the team that implements the measure, which can differ from the Team Responsible; and the **Planned FY** is the fiscal year a measure is planned for when it has no date, always written FY27: a year or a quarter typed or imported becomes its fiscal year (2027 and Q3 2027 are FY27), the new fiscal years take their place in the list in order, and a value that is not a fiscal year is refused (the import keeps it in the note).

### Catalog workbook

**Export Catalog** downloads the whole catalog as an Excel workbook that is easy to edit and to import again: **About** (how to edit it), **Sections** (key, name and colour), **Fields** (order, section, name, key, type, source, source reference, table, Excel, summary, required, CDR value proposed and description), **Lists** (one row per list value with its colour, keywords and **Final**), **Root Catalog** (each domain with its colour, each root category with its domain and each root cause with its root category and domain, empty when it is Auto, all with their keywords), **Statuses and Teams** (with the closed statuses and the team members) and **Status Rules** (one row per condition).

**Import Catalog** reads that workbook, or the field list of the meeting workbook (the sections in the first row, the field names in the second, the kind of values in the fourth and the values of each list from the sixth), and previews what it adds before **Import**: new fields, list values, domains, root categories, causes, statuses and teams are added, the sections and Status Rules of the workbook are taken, and nothing is removed.

## Statuses and teams

**Statuses & Teams** (in the **NQ Analysis Configuration** menu; admins and super-admins change it) configures the values shared by the workspace. Each status and team has a name, a colour and a position; statuses marked **Closed** count as closed in the summary and are left out by **Open calls only**, and the prioritized calls of the statuses marked **In Queue** are listed in their queue (**Next to analyse** of the [NQ Prioritization](#nq-prioritization); a closed status is never In Queue). The first status is the one of the calls that no [Status Rule](#status-rules) matches, such as the calls nobody has followed up yet.

The defaults are the statuses Not Attended, Assigned and Under Analysis (In Queue), Analysis Finished, Under Implementation, Under Planning and Closed (closed) — a call given a team or an analyst is Assigned while nobody attends it, and an attended call is open, in one of the four phase statuses, until it is closed; it stays in its queue while it is Under Analysis — and the teams E2E Team, RAN Planning Coverage, RAN Planning Capacity, RF OPT (Hot Spots) WP2a, Operations, Netcheck and PCI Planning Team.

- Renaming a status or team updates every call that uses it, and a renamed status is renamed in the Status Rules.
- A team that is still used by a call, or a status still set by hand on a call, cannot be removed; move those calls first, or merge the team into another one with **⤳** (Merge into…): on **Save** its calls go to that team, its members join it (a team open to everyone stays so) and it is removed. The calls whose status the Status Rules gave follow the rules again when their status is removed.
- **Default Statuses** and **Default Teams** leave only the defaults, in their order and colours (a status or team with the same name is kept, with its calls and members, and recoloured), and **Save** applies the change; then **Default Rules** in [Status Rules](#status-rules) puts the default rules back.

### Team members

The **Members** button of each team (*Everyone* or the number of members) opens a dialog to choose the workspace users that belong to it, by their first and last name (their username when they have none; the filter finds them by either), the default users first and tagged **default user**, with a filter and **Select All / None**; a user can belong to several teams. The members are saved with **Save**.

> [!IMPORTANT]
> **A team with members accepts only them as analysts.** When a call has a team with members, its **Analyst** list offers only them, and moving the call to a team its analyst does not belong to clears the analyst (an analyst without account stays). A team without members accepts every user of the workspace.

Choosing only the analyst brings the call to their team (the first one in the list when they are in several) unless the call already has a team they belong to or a team without members.

## Status Rules

The **NQ Call Status** of each call is semi-automatic: it follows the **Status Rules** of the workspace until an analyst chooses it by hand. **Status Rules** (in the NQ Analysis Configuration menu and the Lifecycle & Phases panel; admins and super-admins change them) lists the rules in order; each sets a status when every one of its conditions holds.

> [!IMPORTANT]
> **The first rule that matches gives the status of the call.** The order of the rules is the order they are tried in, so a call that meets several rules gets the status of the first one.

> [!WARNING]
> **Change these rules with care.** Modifying them without the necessary knowledge of the fields and statuses of the calls can completely change how the calls are classified: on **Save**, every call with an automatic status takes the status the new rules give it. The dialog shows this warning above the rules.

A condition reads a list or Yes / No field entered by the analysts or derived from the call, the team, the analyst, the root category or cause, or **Attended** (the call has a follow-up change other than assigning it — its Team, Analyst, Reviewer or Priority — or a comment), and is **is one of** or **is not one of** some values, **is empty** or **is not empty**. The rules do not name fixed values: they choose among the values of each list, so renaming a list value or a status renames it in the rules, and a removed value or field is taken out of their conditions (a rule left without conditions is removed).

The default rules, for the default fields and statuses, go from the end of the pipeline to its start, so the most advanced phase of a call wins and the rules of each pipeline card follow one another:

1. **Closed** when Analysis Status is Rejected or Invalidated.
2. **Closed** when Implementation Status is Implemented or Not Applicable.
3. **Under Planning** when Planned Status is Planned.
4. **Under Implementation** when Implementation Status is Not yet evaluated, Under evaluation or Evaluated.
5. **Analysis Finished** when Analysis Status is Finished: the analysis is done and its implementation not decided yet; the call leaves its queue and is closed once Implementation Status is Implemented or Not Applicable.
6. **Under Analysis** when Analysis Status is Ongoing.
7. **Under Analysis** when the call is attended (it is open, in its first phase).
8. **Assigned** when the call has an analyst.
9. **Assigned** when the call has a team.

Otherwise the call is **Not Attended**. **Default Rules** shows them again, with the conditions on the fields the workspace still has; a rule whose default status is no longer one of the statuses (for example after renaming it) is marked to choose the status it sets, and the rules are saved once every rule has a status.

The automatic status changes as soon as a field, a comment, the team, the analyst or the root cause of the call changes, and saving the rules, the fields or the statuses applies them to every automatic call at once. Choosing a status by hand, in the table, the call or the bulk bar, keeps it until **↺ Back to automatic**. The history tells the automatic changes apart, and the Lifecycle & Phases panel, the **Status Set** filter and the Excel export show which calls are automatic.

## Root Cause Catalog

**Root Cause Catalog** (in the NQ Analysis Configuration menu; admins and super-admins change it) configures the catalog the Root Category and the Root Cause of each call are chosen from, in four tabs with a filter:

| Tab | Content |
| --- | --- |
| **Domains** (shown when the catalog opens) | The domains with their colour: the technical ones (RF, RAN, Core, IMS/E2E, Protocol, Device and Operational) and those of the calls without a root cause of the network: **Indeterminate** (its cause is not known yet) and **Invalid** (the call does not count as a failure). |
| **Root Categories** | The generic categories of the analysts, 18 by default, which group the technologies and the directions: Coverage, Interference and Radio Link Quality (RF); Mobility, Radio Signalling, Capacity and Configuration & Planning (RAN); Registration & Authentication, Session & Mobility Management and Fallback & Legacy (Core); Voice Core (IMS) and End-to-End (IMS/E2E); Server & Protocol and Data Transport (Protocol); Device & Test Setup (Device); Network Operations (Operational); Indeterminate (Indeterminate: Unclear and Further investigation required) and Invalid (Invalid: Invalid and Normal release). |
| **Root Causes** | The specific causes, 80 by default, each mapped to its category: why the coverage was poor (NLOS due to clutter or terrain profile, LOS but weak signal, Large distance to the nearest site, Coverage hole (no service), Weak signal with low SINR, UL coverage (UE at maximum power)…), the source of the interference (Lack of dominant cell, Overshooting or excessive cell overlap, PCI collision, External or Internal UL interference…), the handover, signalling, core, IMS and protocol causes (Missing or late handover, No answer to RRC connection request, TAU reject, No QCI1 established, DNS…). When a source only says which link suffered, the cause says it: **DL coverage**, **DL interference**, **UL interference**. |
| **Mapping** | One table with every root cause, the root category it is mapped to and its domain, and one with every root category and its domain, to map the whole catalog at once (the tab counts the causes mapped to a category). **Apply to Calls** saves the catalog and, after confirming how many, gives the calls that have a root cause and no root category the category of their cause (recorded in their history). |

The **Root Technology** of a call (5G - NR, 4G - LTE, 3G - UMTS or 2G - GSM) is a value of its own, chosen beside its Root Category and Root Cause in the table and in the call (**Selected Root Technology** in the fields, the exports and the filters), so the categories and causes are the same for every technology. The sources propose it: the Ericsson RCA by its category (*Poor Coverage LTE*), the DT Analyzer RCA by its rule, else by the technology of the radio measured at the failure (the RSRP its rules read, from the Layer3 Log, the Ericsson RCA or the CDR), else by the most recent technology the call failed in, and NetCheck by the Failure Technology of the call, the most recent one when it names several (*5G/4G* and *EN-DC* → 5G - NR, *2G/4G* → 4G - LTE); **Use as Final Decision** and **Accept** set it with the category and cause.

Each root cause can be mapped to its root category: choosing a cause gives the call that category (also over another category already chosen: a call never has a category and a cause of another category), and the lists of a call show first what its sources propose and, in the list of causes, the causes of its category, then every domain in the order of the catalog, the same for every call, the causes of each domain under each of its categories (*RF · Coverage*, *RF · Interference*…). Each category and cause has a domain, chosen by hand or **Auto**: a cause without a domain of its own takes that of its root category, and otherwise a category or cause takes the first domain whose keywords appear in its name or keywords (*Auto · RAN*); a domain chosen by hand ignores the keywords. The domain gives them their colour, groups their lists and gives the call its **Root Domain** (the domain of its category, else of its cause), so the statistics by domain and the hierarchies of the RCA sources stay; a change of the catalog changes the Root Domain of its calls.

> [!TIP]
> Each value has **keywords**, separated by commas, that map the NetCheck and Ericsson RCA values and the comments onto the catalog; `a+b` needs both words. A value that names a root cause takes the category of that cause (*DL interference problems* → Interference · DL interference; *DNS* → Server & Protocol · DNS); the keywords of the categories only count when no cause matches (*RRC layer* alone → Radio Signalling).

Values are tried from top to bottom, so their order (↑ ↓) sets the priority when several match. **Add missing defaults** adds the default domains, categories and causes that are not in the catalog and keeps the existing ones with their keywords. **Default Catalog** leaves only the default domains, categories and causes, with their keywords and colours, and clears **Require a root category to close a call**; **Save** applies it (a value with the same name keeps its calls). Renaming a value updates every call that uses it; a value still used by a call cannot be removed. A value a [DT Analyzer RCA rule](#dt-analyzer-rca-rules) gives, enabled or not, shows **DT** in place of its remove button (pointing at it names the rules): it cannot be removed, nor a root category or cause renamed (its name is read-only), until no rule gives it; such a domain can still be renamed, as its categories and causes follow it.

> [!WARNING]
> **Require a root category to close a call** refuses closing a call while it has no root category, whether its status is chosen by hand or a change of its fields makes the rules close it.

### Suggestion rule

The suggestion rule translates the **NetCheck RCA** of the CDR onto the catalog, and only it: the DT Analyzer RCA follows its own rules, the Ericsson RCA is matched by name and keywords, and the decisions of the analysts never change. It is described at the top of the catalog. **NetCheck RCA Suggestion Rule** (named after the RCA of the provider of the workspace), there and in the Root Cause Analysis panel (enabled while its source is NetCheck RCA), shows it to every user; **admins and super-admins** change the call fields that choose the domain and those that choose the category and cause (Failure Classification, Category, Subcategory, Comment, Phase and Technology, Result, Test Name, Technology and Direction), whether the category and cause are looked for only in the domain found (a cause the domain has none of is then looked for in the whole catalog: *RAN Problems · BLER Problems* → Radio Link Quality · High UL BLER), whether the comments are read when the CDR leaves them unresolved and whether they can choose the domain, and whether keywords match whole words or any part of the text.

**Default Rule** returns to the default: a domain keyword in the Failure Classification chooses the domain (*RF Problems* → RF), category keywords in those fields, the Failure Category, Subcategory and Comment and the technology of the call choose the root category, and cause keywords in the Failure Category, Subcategory and Comment the root cause (*DL interference problems* of an NR call → Interference · DL interference, with 5G - NR as its Root Technology), then the comments. The Failure Comment counts only when the Failure Category and Subcategory give no category or cause: its free text (a PCI or an RSRP it quotes) never outweighs them. *E2E Trace Required* is not a domain: its category (Packet Loss, Low Throughput, Coverage…) chooses the cause.

The rule applies at once to the suggestions, the Root Cause Analysis and the recommendations, and never changes the root causes already set. Its fields and comments concern the NetCheck RCA of the CDR; the Ericsson RCA results only follow its choice of whole words or any part of the text, since their category and subcategory are matched by name, then by the keywords of the catalog.

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

The history of the calls keeps the values as they were written, and the former values are kept in **NQ Root Catalog Migration Backup** (Database Management) to undo it; App Events records how many calls changed. Exports, transfers and backups of before (NQ Calls Configuration, NQ Call Tracking, the catalog workbook and the Previous NQ Analyses) are translated the same way when imported or restored.

## Root cause recommendation

Every call gets a recommended Root Category, Root Cause and Root Technology, merged from its sources:

| Source | Weight | What it reads |
| --- | --- | --- |
| **NetCheck RCA** | 3 | The Failure Classification, Category and Subcategory of the CDR, mapped by the suggestion rule. |
| **Previous decisions** | 3 | The Root Category and Cause the analysts chose for at least two other calls with the same NetCheck, Ericsson RCA or DT Analyzer RCA values. |
| **Ericsson RCA** | 2 | The Suggested Category and Cause of the [Ericsson RCA results](#ericsson-rca-results) of its `JOIN_ID` (else its Ericsson RCA Category A and Subcategory A), mapped onto the catalog by name or keywords. |
| **DT Analyzer RCA** | 2 | The Root Category and Cause the [DT Analyzer RCA](#dt-analyzer-rca) finds from the data of the CDR; its card shows the rule and the evidence. A call only its last rule, **Not identified**, explains gets no proposal from it. |
| **Comments** | 1 | The comments of the call, when the CDR leaves the root cause unresolved. |

The category with most weight wins (NetCheck goes first when it ties with the previous decisions), then the best cause and the best technology among the sources that agree on it, with the same weights. The confidence is **high** when two or more sources agree, **medium** when only NetCheck, the previous decisions or the DT Analyzer RCA propose it and **low** otherwise.

> [!NOTE]
> The recommendation is shown in the table, the RCA tab of the call and the Excel export, and **Accept** (one call) or **Accept recommendations** (the selected calls) sets it; the analysts can also use what one source proposes or choose any other value, and their choices teach the next recommendations.

## DT Analyzer RCA

The **DT Analyzer RCA** finds the Root Category, the Root Cause and the root domain of every Non-Qualified Call, test and Speech sample from the data of its CDR. It works in every workspace, whatever its CDR type, also when the provider brings an RCA of its own such as the NetCheck RCA, and it comes first, before the NetCheck RCA and the Ericsson RCA, wherever the RCA sources are listed: the [Root Cause Sources](#root-cause-sources) and [Root Cause Analysis](#root-cause-analysis) panels and their filters, the RCA tab of the call, the [recommendation](#root-cause-recommendation), the fields of the catalog and the exports.

It reads every call through the field profile of the CDR type of the workspace, and the network around it in the Network Inventory:

| Values | What it reads |
| --- | --- |
| Call | Result, Test Name, Technology, Direction and Environment. |
| Failure | The **failure description**: the Failure Classification, Category, Subcategory and Comment of the CDR (the RCA of the provider), its failure events and SCG failures; the **signalling events** alone (the failure events and SCG failures of the CDR, without the RCA of the provider); the Failure Phase, Failure Technology and Failure Side; the **technology at the failure** (the Failure Technology, else the technology of the call or the technologies it used) and the **RSRP** and **SINR at the failure** (those of NR when it failed in NR alone, else those of LTE, the anchor), each from the most precise source that measured it: the Layer3 Log of the call at the failure, else the Ericsson RCA before the failure, else the average of the CDR. With a known **failed side** (the Failure Side of the CDR, MO = A and MT = B, else the failure description when it names MO or MT alone) they are those of that side when the Layer3 Logs or the Ericsson RCA measured it, else the worst of both sides. |
| LTE and NR radio | The average and minimum RSRP, the RSRQ, the average and minimum SINR, the maximum transmit power and the BLER of the test, of the A side of a call or of the playing side of a Speech sample; the RSRP and SINR of its B side; the **DL resource blocks used** by a Data test (the share of the resource blocks of its primary LTE or NR carrier it was given on average, from its bandwidth); and the **radio measured** (LTE, NR or both, when the CDR has their RSRP or SINR). |
| Mobility | The technologies used and their timeline, the handovers and their types, and the **ping-pong handovers** (each time the call went back to a cell right after leaving it, A → B → A, in its cell trace, a cell repeated in a row counted once). |
| Network Inventory | The **serving site distance** (from where the call ended to the site of its last cell), the **ISD** of that site and how many ISDs that distance is, the **nearest site distance** of the networks serving its operator and how many of its own ISDs it is, the **PCI collisions around** (cells within 2 km with the PCI and channel of a cell of the call) and the **cells out of service on its sites** (locked, halted or disabled); see [The network around the call](#the-network-around-the-call). |
| Layer3 Logs | For a call with a session in the [Layer3 Logs](workspace-management.md#layer3-logs) of the workspace (found by its `JOIN_ID`, both UEs of a voice call): the RSRP and SINR of its LTE and NR PCell in the last 5 seconds of its log (**at the failure**) and their minimum, the RAN Configuration at the failure and, in its last 10 seconds, its RRC re-establishments, SCG failures, handover attempts, inter-RAT moves (IRAT, redirections) and RRC releases, its LTE and NR BLER, how many of its UE Tx Power samples reached 22 dBm, and how far a neighbour of the serving channel rose above the serving cell (and for how many seconds by 3 dB or more); the rejects of its signalling, its worst **SIP error** (from 400, leaving out the answers of a normal call or registration: 401, 407, 487 and 489), the records without measurements and its **signalling before the failure** (the events and L3 messages of its last 10 seconds). The counts of the two UEs of a call add up and its worst radio is kept; the radio of each UE is also kept apart for the side that failed and the evidence. These values are worked out once, when the log is imported. |
| Ericsson RCA | For a call with [Ericsson RCA results](#ericsson-rca-results) (found by its `JOIN_ID`): the RSRP and SINR of its LTE and NR PCell, the UE Tx Power and how far a stronger neighbour was above the PCell (*RSRP diff*) the Ericsson RCA measured in the logs before the failure, read from its evidence (*LTE PCell RSRP=-82.8 dBm, SINR=5.24, TxPower=-13.0*); with both sides, the worst one (the lowest RSRP and SINR, the highest power and neighbour), and each side (A, B) also apart for the side that failed and the evidence. |
| Failed side and other side | The two sides of a voice call: **UE A** is the device that calls (MO, Mobile Originated) and **UE B** the device it calls (MT, Mobile Terminated). The **failed side** is the side the Failure Side of the CDR names (MO = A, MT = B), else the one the failure description names when it names MO or MT alone. For the failed side and the **other side**: the LTE and NR RSRP and SINR of its PCell, its UE Tx Power and how far its strongest LTE and NR neighbour was above its PCell (below when negative), each from its Layer3 Log at the failure, else its Ericsson RCA (the neighbour, the highest both found: the log measures the channel of the PCell, the Ericsson RCA the other frequencies too). Without a known failed side, the failed side stands for the worst of both sides (or the device of a Data test) and the other side has no values. |
| KPIs | Throughput (Mbit/s), service access time (s), DNS time (ms) and success (%), TCP round-trip time (ms), packet loss (%), latency (ms), call setup time (s), duration (s), speech quality (MOS), RTP packet loss (%) and jitter (ms). |

The calls are calculated when they are indexed, and again whenever its rules, the [Root Cause Catalog](#root-cause-catalog), the Network Inventory or the [Serving Networks](workspace-config.md#serving-networks) change; importing or deleting Ericsson RCA results calculates again the calls they belong to.

The **evidence** of each call has a line per subject, so the values of each source are never mixed up:

| Line | What it says |
| --- | --- |
| The rule | The values of the call that met the rule (*LTE RSRP (average) −118.4 dBm (< −110 dBm)*); a value of the RSRP or SINR at the failure names its technology and source (*RSRP at the failure (LTE, Ericsson RCA, before the failure) −112 dBm (< −105 dBm)*), and a description of the failure only the word it contains. |
| Provider description | When the rule read it: the Failure Classification, Category, Subcategory and Comment of the provider and the failure events, without the averages of its comment. |
| Radio | The radio before the failure from each source that measured it, a line each, the most precise first, named in brackets: the Layer3 Log of the call at the failure, with the LTE and NR PCell and the highest UE Tx Power of its last seconds (*Radio (Layer3 Log, at the failure): LTE PCell RSRP −82.79 dBm, SINR 5.24 dB · NR PCell RSRP −74.2 dBm, SINR 6.6 dB, UE Tx Power (maximum) −10 dBm*), else the Ericsson RCA (*Radio (Ericsson RCA, before the failure): LTE PCell RSRP −82.8 dBm, SINR 5.24 dB, UE Tx Power −13 dBm*). When the source measured both sides of the call, or the side that failed is known, each side is given apart and the failed one is marked (*A (failed side): LTE PCell RSRP −108.5 dBm; neighbour 15.5 dB above the PCell \| B: NR PCell RSRP −105.8 dBm, SINR −0.8 dB*). |
| Call average | The averages of the whole call: those of the failure comment of the provider, each technology on its own (*ENDC-5G mean RSRP −71.54 dBm, mean SINR 6.77 dB (RSRP ≤ −115 dBm in 0 %, SINR ≤ 0 dB in 12 % of the samples)*), else the average LTE and NR RSRP and SINR of the CDR. |
| Network and logs | The sites of the network around the call and what the Layer3 Logs show before the failure, when the rule read them (the Layer3 Logs also when it read the radio of the sides). |

The rules of the radio of the sides read these values to tell apart, on the failed side and then on the other side of a voice call: a weak coverage (RSRP below −110 dBm), a stronger neighbour it was not handed over to (3 dB or more above its PCell with a SINR below 3 dB: a missing or late handover), a weak signal (below −105 dBm) with a SINR below 0 dB (limited by the noise: coverage), and with a good signal (−105 dBm or more) a neighbour about as strong as its PCell with a SINR below 0 dB (within 3 dB: no dominant cell) or a SINR below 0 dB without such a neighbour (downlink interference) and the UE at high power (uplink coverage or interference). They come after the rejects of the network and the network around the call, and before the identity, core, IMS and paging causes the provider reports: a radio this poor at the failure can bring those about, and the setup of a voice call needs both sides (the QCI1 bearer of the caller waits for the answer of the called side), so a poor radio on the other side explains the failure the provider reports on the failed side. The evidence then gives the provider's description too.

In the RCA tab of the call, the evidence of the DT Analyzer RCA and of the Ericsson RCA shows a bullet per subject and each side of the call (**UE A**, the caller, MO; **UE B**, the called side, MT) in an indented block of its own, its findings as bullets one below the other, the side that failed marked **Failed side**.

> [!NOTE]
> The averages of the whole call and the radio the logs measured before the failure can differ by several dB: they cover different periods, and the comment of the provider may give the NR leg of an EN-DC call while the Ericsson RCA gives the LTE PCell.

### Presentation

The DT Analyzer RCA is also a presentation, **DT Analyzer RCA**: its architecture (from the CDR to the Selected Cause), what it reads, how its rules decide, the lack of resources, the network around the call (coverage holes, overshooting, PCI collisions and cells out of service), handovers and service, the result and evidence of each call and how to change the rules. Select it to open it in the slide viewer, play it full screen or download its PowerPoint; it is also in [Product Presentations](presentations.md).

```presentations
dt-analyzer-rca
```

### The network around the call

With a Network Inventory of the networks that serve the operator of the call ([Serving Networks](workspace-config.md#serving-networks)), the DT Analyzer RCA finds, as the [Map of the call](#map-of-the-call) does, the inventory cell of each cell of its trace (of its own network first, the nearest to where it served the call) and the site of the cell where it ended. Whether a site served from too far away depends on where it is: a city site serves a few hundred metres, a rural or road site several kilometres. So distances are compared with the **inter-site distance (ISD)** of the site: the mean distance to its 3 nearest sites in service of the same network, from the positions of the Network Inventory. The ISD does not need the neighbour lists of the cells (the inventories do not have them) nor the Timing Advance (the CDRs do not have it).

- **Overshooting**: the serving site is at least **twice its ISD** (and 1 km) from where the call ended, with interference (SINR below 3 dB) or weak coverage (RSRP below −105 dBm). The evidence names the serving site and the nearest one, a hint of a missing neighbour.
- **Coverage hole**: the nearest site in service of the networks serving the operator is at least **1.5 times its own ISD** away, with weak coverage (RSRP below −110 dBm) or no radio measured at all: no cell covers the place.
- **PCI collision**: a cell within 2 km has the technology, PCI and channel of a cell of the call, with interference.
- **Cells out of service**: cells of the sites of the call are locked, halted or disabled in the inventory, with weak coverage or interference.

A site without other sites of its network within 40 km has no ISD, so no rule reads its distance. For example, the urban sites of a UK network are about 1 km apart and the rural ones about 3.4 km.

### Lack of resources

The DT Analyzer RCA finds a lack of resources in three ways:

- **What the provider reports**: insufficient resources of the core (for example a PDU Session Establishment Reject with the 5GSM cause *Insufficient resources*) or a congestion reject (a CM Service Reject for congestion) give **Session & Mobility Management · Insufficient resources**, before such a reject is taken for an authentication one. Only the RCA of the provider tells these causes: the CDR has no NAS cause of its own.
- **The signalling of the CDR itself**, without the RCA of the provider: an access the network rejected (*RRCConnectionReject*, *RRCReject* or *Immediate Assignment Reject* in its failure events), or an RRC Connection Reject the provider reports, gives **Capacity · Access rejected (no resources)**.
- **The resource blocks of a Data test**: a test cut off by time (Cutoff) with its radio measured and good (no radio rule took it) whose primary carrier gave it less than **25 %** of its resource blocks on average gives **Capacity · Cell overload**. A completed test usually gets about two thirds of them. A server or a TCP connection that sends little also leaves resource blocks unused, so these rules come after those of the protocols and servers.

### DT Analyzer RCA Rules

**DT Analyzer RCA Rules**, in the **NQ Analysis Configuration** menu, shows the rules to every user; admins and super-admins change them. The rules are tried from top to bottom: the first enabled rule of the service of the call (Voice, Speech, Data, or every service when none is checked) whose conditions hold — all of them, or any of them — gives its Root Category and Root Cause, chosen from the catalog, with their domain and the [evidence](#dt-analyzer-rca): the values of the call that met it (*LTE RSRP (average) −118.43 dBm (< −110 dBm)*) and the radio of the call. A rule without conditions takes every call of its services that reaches it, and a disabled rule is skipped. A number is compared (<, ≤, >, ≥, =, ≠) with a value in the unit shown; a text contains, or does not contain, one of its words, separated by commas (`a+b` needs both); any value can be empty or not empty. Each rule shows the Non-Qualified Calls it explains.

The default rules, the same in every workspace, are listed one by one in [Default rules](#default-rules). In short, in this order:

1. What the provider reports outside the radio, and the lack of resources: the device or the test setup, the subscriber identity, insufficient resources of the core and accesses rejected by the network, rejected authentication or registration, tracking area updates, bearers deactivated by the network, the QCI1 bearer of a call, the VoLTE or IMS core, EPS fallback, paging and sessions in GSM.
2. The network around the call (Network Inventory): cells out of service on its sites, coverage holes, overshooting and PCI collisions, before the coverage and interference they bring.
3. What the Layer3 Logs of the call show at its failure, for the calls with a log (more precise than the averages of the CDR, so before the rules of its radio): an SCG failure with a weak NR coverage and a re-establishment with a weak LTE coverage, a neighbour of the serving channel 6 dB above the serving cell for 3 seconds without a handover (a missing or late handover), the weak LTE and NR coverage (below −115 dBm) and the interference (SINR below −3 dB with a good RSRP) at the failure, the UE at its maximum power, then the SCG failures and re-establishments with a good radio and a high BLER (above 30 %). The rules of what the provider reports read the log too: the rejects of its signalling, its SIP errors, its handover and radio link failures and its inter-RAT moves.
4. The radio of the call: poor LTE and NR coverage (average RSRP below −110 dBm), the LTE uplink at its maximum power (23 dBm, with an RSRP below −100 dBm), LTE and NR downlink interference (average SINR below 0 dB), no dominant LTE cell (RSRQ below −15 dB), the coverage and interference of the B side, fallbacks to 2G or 3G and a high BLER (above 10 %).
5. Its handovers and the radio link: ping-pong handovers, handover and radio link failures and inter-RAT transitions; then the coverage and interference (downlink or uplink) the provider reports, in the category of the technology at the failure (LTE, the anchor, unless it is NR alone or 2G or 3G alone).
6. The service, once the radio is not the cause: DNS, HTTP or server errors, TCP, no downlink packets, packet loss (above 5 %), high latency (above 150 ms), data transfer timeouts, Cutoff tests given few resource blocks (a loaded cell), the low throughput the provider reports and that of the Cutoff tests with good radio, the RTP loss of Speech samples, the Voice failures with good radio (a potential E2E issue) and the end-to-end traces the provider asks for. Good radio means that the radio was measured and no radio rule took the call: without radio values neither the Cutoff tests nor the Voice failures are given a cause.
7. **Not identified** (Unclear) for the calls none of them explains.

A workspace whose rules were changed before a version added default rules takes the new ones once, each after the default rule before it, and the new conditions of the default rules it kept as they were (a rule changed by hand stays as it is); App Events lists them. A log imported, processed again or deleted calculates again the calls of its campaign, and the evidence of a rule that read the log tells what the log shows before the failure (such as *Layer3 Logs: 5G EN-DC - SCG Failure NR SCG 2.1 s before the end on PCI 997*).

The values the rules give stay in the [Root Cause Catalog](#root-cause-catalog), which refuses to remove them, or to rename those root categories and causes, until no rule gives them.

**Default Rules** fills the dialog with them and **Save** applies them. Saving calculates every call again at once (while the CDRs are being indexed, when the indexing ends), and App Events records what changed in the rules. The rules travel with the NQ Calls configuration (export, import, transfers and backups).

> [!WARNING]
> **The order of the rules matters.** A rule only takes the calls the rules above it leave, so a broad rule high in the list hides the rules below it.

**Learn from the decisions of the analysts**, at the top of the dialog and off by default, lets the DT Analyzer RCA learn from the Root Category and Root Cause the analysts choose. Calls share a pattern when the same rule explains them, they belong to the same service and the provider describes their failure the same way (its Failure Classification, Category and Subcategory). A call takes the Root Category and Cause the analysts gave most of the other calls of its pattern when at least 2 of them, and more than half of those decided, agree; its own decision never counts. It also learns for the calls the rules leave Not identified, and the other calls keep what their rule gives. The evidence says what was learned and from how many calls (*Learned from the analysts: 3 of the 3 other calls of the rule “Voice failure with good radio”…*), the card of the source in the call says **Learned from the analysts**, and the dialog counts the calls that learned. What it learns follows each new decision of the analysts and each indexing of the CDRs (also **Reindex**); turning it off gives every call the root cause of its rule again. The setting travels with the rules, and App Events records when it is turned on or off.

### Default rules

The default rules of the DT Analyzer RCA, the same in every workspace, in the order they are tried. The first rule of the service of the call whose conditions hold gives its Root Category and Root Cause; *All* rules take every service. A text condition holds when the text contains one of its words (`a+b` needs both). *In NR alone* means that the technology at the failure is NR without LTE (an SA call); *in 2G or 3G alone*, without LTE nor NR. Admins change them in [DT Analyzer RCA Rules](#dt-analyzer-rca-rules).

| # | Rule | Services | When | Root Category · Root Cause (Root Technology) | Domain |
| --- | --- | --- | --- | --- | --- |
| | **What the provider reports outside the radio, and the lack of resources** | | | | |
| 1 | Device or test setup | All | Failure description contains `modem`, `device`, `test setup`, `ue crash`, `at command`, `script error`, `battery` | Device & Test Setup · Device or test setup | Device |
| 2 | No measurements in the drivetest log | All | Records without measurements (log) ≥ 1 and LTE RSRP at the failure (log) is empty and NR RSRP at the failure (log) is empty | Device & Test Setup · No measurements in the log | Device |
| 3 | Insufficient resources of the core | All | Failure description contains `insufficient resources`, `service reject+congestion` | Session & Mobility Management · Insufficient resources | Core |
| 4 | Access rejected by the network | All | Signalling events contains `rrcconnectionreject`, `rrcreject`, `immediate assignment reject` or Failure description contains `rrc connection reject` or Signalling before the failure (log) contains `rrcconnectionreject`, `rrcreject` | Capacity · Access rejected (no resources) | RAN |
| 5 | Authentication or registration rejected | All | Failure description contains `authentication`, `authorization`, `registration reject`, `attach reject`, `pdu session establishment reject` or Signalling before the failure (log) contains `authentication reject`, `registration reject`, `attach reject`, `pdu session establishment reject` | Registration & Authentication · Authentication/Authorization | Core |
| | **The network around the call (Network Inventory)** | | | | |
| 6 | Cells out of service on its sites | All | Cells out of service on its sites ≥ 1 and RSRP at the failure < −105 dBm | Network Operations · Cell/Site Outage | Operational |
| 7 | Cells out of service on its sites with interference | All | Cells out of service on its sites ≥ 1 and SINR at the failure < 3 dB | Network Operations · Cell/Site Outage | Operational |
| 8 | NR coverage hole | All | Nearest site distance / its ISD ≥ 1.5 × and NR RSRP (average) < −110 dBm, in NR alone | Coverage · Large distance to the nearest site (5G - NR) | RF |
| 9 | Coverage hole | All | Nearest site distance / its ISD ≥ 1.5 × and LTE RSRP (average) < −110 dBm | Coverage · Large distance to the nearest site (4G - LTE) | RF |
| 10 | Coverage hole without service | All | Nearest site distance / its ISD ≥ 1.5 × and Radio measured is empty | Coverage · Coverage hole (no service) | RF |
| 11 | NR overshooting | All | Serving site distance / its ISD ≥ 2 × and Serving site distance ≥ 1 km and NR SINR (average) < 3 dB, in NR alone | Interference · Overshooting or excessive cell overlap (5G - NR) | RF |
| 12 | Overshooting | All | Serving site distance / its ISD ≥ 2 × and Serving site distance ≥ 1 km and LTE SINR (average) < 3 dB | Interference · Overshooting or excessive cell overlap (4G - LTE) | RF |
| 13 | NR overshooting with weak coverage | All | Serving site distance / its ISD ≥ 2 × and Serving site distance ≥ 1 km and NR RSRP (average) < −105 dBm, in NR alone | Coverage · Served from a far site (overshooting) (5G - NR) | RF |
| 14 | Overshooting with weak coverage | All | Serving site distance / its ISD ≥ 2 × and Serving site distance ≥ 1 km and LTE RSRP (average) < −105 dBm | Coverage · Served from a far site (overshooting) (4G - LTE) | RF |
| 15 | NR PCI collision | All | PCI collisions around ≥ 1 and NR SINR (average) < 3 dB, in NR alone | Interference · PCI Collision/PCI MOD 3 Collision (5G - NR) | RF |
| 16 | PCI collision | All | PCI collisions around ≥ 1 and LTE SINR (average) < 3 dB | Interference · PCI Collision/PCI MOD 3 Collision (4G - LTE) | RF |
| | **The radio of the failed side, then of the other side of a voice call, at the failure (Layer3 Logs, else Ericsson RCA)** | | | | |
| 17 | Weak LTE coverage on the failed side | All | LTE RSRP of the failed side < −110 dBm | Coverage · DL coverage (4G - LTE) | RF |
| 18 | Weak NR coverage on the failed side | All | NR RSRP of the failed side < −110 dBm | Coverage · DL coverage (5G - NR) | RF |
| 19 | Stronger LTE neighbour on the failed side | All | Strongest LTE neighbour above the PCell of the failed side ≥ 3 dB and LTE SINR of the failed side < 3 dB | Mobility · Missing or late handover (4G - LTE) | RAN |
| 20 | Weak LTE signal with a low SINR on the failed side | All | LTE RSRP of the failed side < −105 dBm and LTE SINR of the failed side < 0 dB | Coverage · Weak signal with low SINR (4G - LTE) | RF |
| 21 | No dominant LTE cell on the failed side | All | LTE SINR of the failed side < 0 dB and Strongest LTE neighbour above the PCell of the failed side ≥ −3 dB and LTE RSRP of the failed side ≥ −105 dBm | Interference · Lack of dominant cell (4G - LTE) | RF |
| 22 | LTE interference on the failed side | All | LTE SINR of the failed side < 0 dB and LTE RSRP of the failed side ≥ −105 dBm | Interference · DL interference (4G - LTE) | RF |
| 23 | Stronger NR neighbour on the failed side | All | Strongest NR neighbour above the PCell of the failed side ≥ 3 dB and NR SINR of the failed side < 3 dB | Mobility · Missing or late handover (5G - NR) | RAN |
| 24 | Weak NR signal with a low SINR on the failed side | All | NR RSRP of the failed side < −105 dBm and NR SINR of the failed side < 0 dB | Coverage · Weak signal with low SINR (5G - NR) | RF |
| 25 | No dominant NR cell on the failed side | All | NR SINR of the failed side < 0 dB and Strongest NR neighbour above the PCell of the failed side ≥ −3 dB and NR RSRP of the failed side ≥ −105 dBm | Interference · Lack of dominant cell (5G - NR) | RF |
| 26 | NR interference on the failed side | All | NR SINR of the failed side < 0 dB and NR RSRP of the failed side ≥ −105 dBm | Interference · DL interference (5G - NR) | RF |
| 27 | UE at high power with weak coverage on the failed side | All | UE Tx Power of the failed side ≥ 21 dBm and LTE RSRP of the failed side < −100 dBm | Coverage · UL coverage (UE at maximum power) (4G - LTE) | RF |
| 28 | UE at high power with good coverage on the failed side | All | UE Tx Power of the failed side ≥ 21 dBm and LTE RSRP of the failed side ≥ −95 dBm | Interference · UL interference (4G - LTE) | RF |
| 29 | Weak LTE coverage on the other side | Voice, Speech | LTE RSRP of the other side < −110 dBm | Coverage · DL coverage (4G - LTE) | RF |
| 30 | Weak NR coverage on the other side | Voice, Speech | NR RSRP of the other side < −110 dBm | Coverage · DL coverage (5G - NR) | RF |
| 31 | Stronger LTE neighbour on the other side | Voice, Speech | Strongest LTE neighbour above the PCell of the other side ≥ 3 dB and LTE SINR of the other side < 3 dB | Mobility · Missing or late handover (4G - LTE) | RAN |
| 32 | Weak LTE signal with a low SINR on the other side | Voice, Speech | LTE RSRP of the other side < −105 dBm and LTE SINR of the other side < 0 dB | Coverage · Weak signal with low SINR (4G - LTE) | RF |
| 33 | No dominant LTE cell on the other side | Voice, Speech | LTE SINR of the other side < 0 dB and Strongest LTE neighbour above the PCell of the other side ≥ −3 dB and LTE RSRP of the other side ≥ −105 dBm | Interference · Lack of dominant cell (4G - LTE) | RF |
| 34 | LTE interference on the other side | Voice, Speech | LTE SINR of the other side < 0 dB and LTE RSRP of the other side ≥ −105 dBm | Interference · DL interference (4G - LTE) | RF |
| 35 | Stronger NR neighbour on the other side | Voice, Speech | Strongest NR neighbour above the PCell of the other side ≥ 3 dB and NR SINR of the other side < 3 dB | Mobility · Missing or late handover (5G - NR) | RAN |
| 36 | Weak NR signal with a low SINR on the other side | Voice, Speech | NR RSRP of the other side < −105 dBm and NR SINR of the other side < 0 dB | Coverage · Weak signal with low SINR (5G - NR) | RF |
| 37 | No dominant NR cell on the other side | Voice, Speech | NR SINR of the other side < 0 dB and Strongest NR neighbour above the PCell of the other side ≥ −3 dB and NR RSRP of the other side ≥ −105 dBm | Interference · Lack of dominant cell (5G - NR) | RF |
| 38 | NR interference on the other side | Voice, Speech | NR SINR of the other side < 0 dB and NR RSRP of the other side ≥ −105 dBm | Interference · DL interference (5G - NR) | RF |
| | **The causes the provider reports that a poor radio can also bring about (identity, core, IMS, paging)** | | | | |
| 39 | Subscriber identity | All | Failure description contains `imsi`, `ue identity cannot be derived` | Registration & Authentication · Subscriber identity (IMSI) | Core |
| 40 | Tracking area update | All | Failure description contains `tracking area update` or Signalling before the failure (log) contains `tracking area update reject` | Session & Mobility Management · TAU reject | Core |
| 41 | Bearer deactivated by the network | All | Failure description contains `bearer deactivation`, `deregistered`, `detach request` | Session & Mobility Management · EPS bearer deactivation | Core |
| 42 | No QCI1 bearer for the call | Voice, Speech | Failure description contains `qci1`, `qci 1` | Voice Core (IMS) · No QCI1 established | IMS/E2E |
| 43 | VoLTE or IMS core | Voice, Speech | Failure description contains `volte core`, `ims core`, `ims registration`, `sip`, `server internal error` or SIP error (log) ≥ 400 | Voice Core (IMS) · VoLTE core | IMS/E2E |
| 44 | EPS fallback | Voice, Speech | Failure description contains `epsfb`, `eps fallback` | Fallback & Legacy · EPS fallback failure | Core |
| 45 | Paging | All | Failure description contains `paging` | Radio Signalling · Paging | RAN |
| 46 | Session in GSM | All | Failure description contains `session in gsm` | Fallback & Legacy · WhatsApp session in GSM | Core |
| | **What its Layer3 Logs show at the failure (calls with a log only)** | | | | |
| 47 | SCG failure with weak NR coverage (drivetest log) | All | SCG failures before the failure (log) ≥ 1 and NR RSRP at the failure (log) < −110 dBm | Coverage · DL coverage (5G - NR) | RF |
| 48 | Re-establishment with weak LTE coverage (drivetest log) | All | RRC re-establishments before the failure (log) ≥ 1 and LTE RSRP at the failure (log) < −110 dBm | Coverage · DL coverage (4G - LTE) | RF |
| 49 | Stronger neighbour without a handover (drivetest log) | All | Neighbour of the serving channel above the serving cell (log) ≥ 6 dB and Seconds a neighbour was 3 dB above the serving cell (log) ≥ 3 s and Handovers before the failure (log) = 0 | Mobility · Missing or late handover (4G - LTE) | RAN |
| 50 | Weak LTE coverage at the failure (drivetest log) | All | LTE RSRP at the failure (log) < −115 dBm | Coverage · DL coverage (4G - LTE) | RF |
| 51 | Weak NR coverage at the failure (drivetest log) | All | NR RSRP at the failure (log) < −115 dBm and RAN Configuration at the failure (log) contains `5g sa` | Coverage · DL coverage (5G - NR) | RF |
| 52 | UE at maximum power before the failure (drivetest log) | All | UE Tx Power from 22 dBm before the failure (log) ≥ 50 % and LTE RSRP at the failure (log) < −100 dBm | Coverage · UL coverage (UE at maximum power) (4G - LTE) | RF |
| 53 | LTE interference at the failure (drivetest log) | All | LTE SINR at the failure (log) < −3 dB and LTE RSRP at the failure (log) ≥ −105 dBm | Interference · DL interference (4G - LTE) | RF |
| 54 | NR interference at the failure (drivetest log) | All | NR SINR at the failure (log) < −3 dB and NR RSRP at the failure (log) ≥ −105 dBm and RAN Configuration at the failure (log) contains `5g` | Interference · DL interference (5G - NR) | RF |
| 55 | SCG failure before the failure (drivetest log) | All | SCG failures before the failure (log) ≥ 1 | Mobility · SCG failure (5G - NR) | RAN |
| 56 | RRC re-establishment before the failure (drivetest log) | All | RRC re-establishments before the failure (log) ≥ 1 | Radio Signalling · Radio link failure | RAN |
| 57 | High LTE BLER before the failure (drivetest log) | All | LTE BLER before the failure (log) > 30 % | Radio Link Quality · High DL BLER (4G - LTE) | RF |
| 58 | High NR BLER before the failure (drivetest log) | All | NR BLER before the failure (log) > 30 % | Radio Link Quality · High DL BLER (5G - NR) | RF |
| | **The radio of the call** | | | | |
| 59 | Poor LTE coverage | All | LTE RSRP (average) < −110 dBm | Coverage · DL coverage (4G - LTE) | RF |
| 60 | Poor NR coverage | All | NR RSRP (average) < −110 dBm | Coverage · DL coverage (5G - NR) | RF |
| 61 | LTE uplink at maximum power | All | LTE transmit power (maximum) ≥ 23 dBm and LTE RSRP (average) < −100 dBm | Coverage · UL coverage (UE at maximum power) (4G - LTE) | RF |
| 62 | LTE downlink interference | All | LTE SINR (average) < 0 dB | Interference · DL interference (4G - LTE) | RF |
| 63 | NR downlink interference | All | NR SINR (average) < 0 dB | Interference · DL interference (5G - NR) | RF |
| 64 | No dominant LTE cell | All | LTE RSRQ (average) < −15 dB | Interference · Lack of dominant cell (4G - LTE) | RF |
| 65 | Poor LTE coverage of the B side | Voice, Speech | B side LTE RSRP (average) < −110 dBm | Coverage · DL coverage (4G - LTE) | RF |
| 66 | Poor NR coverage of the B side | Voice, Speech | B side NR RSRP (average) < −110 dBm | Coverage · DL coverage (5G - NR) | RF |
| 67 | LTE interference on the B side | Voice, Speech | B side LTE SINR (average) < 0 dB | Interference · DL interference (4G - LTE) | RF |
| 68 | Fallback to 2G or 3G | All | Technologies used contains `gsm`, `umts`, `wcdma`, `hspa`, `2g`, `3g` | Mobility · Inter-RAT transition | RAN |
| 69 | High LTE BLER | All | LTE BLER > 10 % | Radio Link Quality · High DL BLER (4G - LTE) | RF |
| 70 | High NR BLER | All | NR BLER > 10 % | Radio Link Quality · High DL BLER (5G - NR) | RF |
| | **Its handovers and the radio link** | | | | |
| 71 | NR ping-pong handovers | All | Ping-pong handovers ≥ 1, in NR alone | Mobility · Ping-pong handover (5G - NR) | RAN |
| 72 | Ping-pong handovers | All | Ping-pong handovers ≥ 1 | Mobility · Ping-pong handover (4G - LTE) | RAN |
| 73 | NR handover failure | All | Failure description contains `handover` and Failure Technology contains `5g`, `nr` | Mobility · Handover failure (5G - NR) | RAN |
| 74 | Handover failure | All | Failure description contains `handover` or Signalling before the failure (log) contains `handover failure` | Mobility · Handover failure (4G - LTE) | RAN |
| 75 | Radio link failure | All | Failure description contains `radio link failure`, `t310`, `reestablishment`, `random access`, `rach`, `scg failure`, `scgfailure`, `rrc` or Signalling before the failure (log) contains `radio link failure`, `rlf` | Radio Signalling · Radio link failure | RAN |
| 76 | Inter-RAT transition | All | Failure description contains `inter-rat`, `irat`, `redirection`, `4g -> 5g`, `5g -> 4g` or Inter-RAT moves before the failure (log) ≥ 1 | Mobility · Inter-RAT transition | RAN |
| | **The coverage and interference the provider reports** | | | | |
| 77 | NR coverage reported by the provider | All | Failure description contains `coverage`, `plmn lost`, `no service`, `out of service`, in NR alone | Coverage · DL coverage | RF |
| 78 | 2G or 3G coverage reported by the provider | All | Failure description contains `coverage`, `plmn lost`, `no service`, `out of service`, in 2G or 3G alone | Coverage · DL coverage | RF |
| 79 | Coverage reported by the provider | All | Failure description contains `coverage`, `plmn lost`, `no service`, `out of service` | Coverage · DL coverage | RF |
| 80 | NR uplink interference reported by the provider | All | Failure description contains `ul interference`, `uplink interference`, in NR alone | Interference · UL interference | RF |
| 81 | Uplink interference reported by the provider | All | Failure description contains `ul interference`, `uplink interference` | Interference · UL interference | RF |
| 82 | NR interference reported by the provider | All | Failure description contains `interference`, in NR alone | Interference · DL interference | RF |
| 83 | 2G or 3G interference reported by the provider | All | Failure description contains `interference`, in 2G or 3G alone | Interference · DL interference | RF |
| 84 | Interference reported by the provider | All | Failure description contains `interference` | Interference · DL interference | RF |
| | **The service, once the radio is not the cause** | | | | |
| 85 | DNS | Data | Failure description contains `dns` or DNS success < 100 % or DNS time > 1000 ms | Server & Protocol · DNS | Protocol |
| 86 | HTTP or server error | Data | Failure description contains `http`, `server error`, `200 ok` | Server & Protocol · HTTP | Protocol |
| 87 | TCP connection | Data | Failure description contains `tcp`, `handshake` or TCP round-trip time > 1000 ms | Server & Protocol · TCP connection errors | Protocol |
| 88 | No downlink packets | Data | Failure description contains `no dl packets` | Data Transport · No DL packets | Protocol |
| 89 | Packet loss | Data | Failure description contains `packet loss`, `no answer to ping`, `retransmission`, `no answer to hello` or Packet loss > 5 % | Data Transport · Packet loss | Protocol |
| 90 | High latency | Data | Failure description contains `latency` or Latency (round-trip time) > 150 ms | Data Transport · Latency | Protocol |
| 91 | Data transfer timeout | Data | Failure description contains `timeout` | Data Transport · Data transfer timeout | Protocol |
| 92 | NR cell short of resource blocks | Data | Result contains `cutoff` and Radio measured is not empty and NR DL resource blocks used < 25 % | Capacity · Cell overload | RAN |
| 93 | Cell short of resource blocks | Data | Result contains `cutoff` and Radio measured is not empty and LTE DL resource blocks used < 25 % | Capacity · Cell overload | RAN |
| 94 | Low throughput reported by the provider | Data | Failure description contains `low throughput` | Capacity · Low throughput | RAN |
| 95 | Low throughput with good radio | Data | Result contains `cutoff` and Radio measured is not empty | Capacity · Low throughput | RAN |
| 96 | RTP packet loss | Speech | RTP packet loss > 5 % | Data Transport · Packet loss | Protocol |
| 97 | Voice failure with good radio | Voice, Speech | Radio measured is not empty | End-to-End · Potential E2E Issue | IMS/E2E |
| 98 | End-to-end trace required | All | Failure description contains `e2e` | End-to-End · E2E trace required | IMS/E2E |
| | **The calls none of them explains** | | | | |
| 99 | Not identified | All | Every call that reaches it | Indeterminate · Unclear | Indeterminate |

### Root domains, categories and causes

The values the default rules give, by root domain of the [Root Cause Catalog](#root-cause-catalog). The catalog keeps them: they cannot be removed, nor a category or cause renamed, while a rule gives them.

| Domain | Root Categories | Root Causes |
| --- | --- | --- |
| RF | Coverage, Interference, Radio Link Quality | Coverage hole (no service), DL coverage, DL interference, High DL BLER, Lack of dominant cell, Large distance to the nearest site, Overshooting or excessive cell overlap, PCI Collision/PCI MOD 3 Collision, Served from a far site (overshooting), UL coverage (UE at maximum power), UL interference, Weak signal with low SINR |
| RAN | Capacity, Mobility, Radio Signalling | Access rejected (no resources), Cell overload, Handover failure, Inter-RAT transition, Low throughput, Missing or late handover, Paging, Ping-pong handover, Radio link failure, SCG failure |
| Core | Fallback & Legacy, Registration & Authentication, Session & Mobility Management | Authentication/Authorization, EPS bearer deactivation, EPS fallback failure, Insufficient resources, Subscriber identity (IMSI), TAU reject, WhatsApp session in GSM |
| IMS/E2E | End-to-End, Voice Core (IMS) | E2E trace required, No QCI1 established, Potential E2E Issue, VoLTE core |
| Protocol | Data Transport, Server & Protocol | DNS, Data transfer timeout, HTTP, Latency, No DL packets, Packet loss, TCP connection errors |
| Device | Device & Test Setup | Device or test setup, No measurements in the log |
| Operational | Network Operations | Cell/Site Outage |
| Indeterminate | Indeterminate | Unclear |

## Map Levels

**Map Levels**, in the **NQ Analysis Configuration** menu, shows every user the levels the [map of a call](#map-of-the-call) and [NQ Maps](#nq-maps) colour each measure by; admins and super-admins change them for the workspace. They colour the RSRP and SINR of the samples of the CDRs and of the [Layer3 Logs](#layer3-logs-on-the-map), and the RSRQ and the UE Tx Power of the logs (LTE and NR alike), in their points, grid, legend and signalling timeline.

- **A card for each measure** — RSRP (dBm), RSRQ (dB), SINR (dB) and UE Tx Power (dBm) — lists its levels, the best one first (for UE Tx Power the highest power first): each with its colour, its name and the lowest value it takes (**From**); it takes the values up to the level above it, and the last one every value below. **Takes** shows its range as the legends write it (*−90 to −80 dBm*), and a level without a name shows its range alone.
- **Add Level** adds a level above the last one, **×** removes one (each measure keeps from 2 to 10 levels) and **Default Levels** shows the levels every workspace starts with; **Save** applies every card. Each level starts below the one above it, or Save says which one does not.
- The maps take the levels when they are opened again. App Events keeps each change with the levels saved.

| Measure | Default levels |
| --- | --- |
| RSRP | *Excellent* (≥ −80 dBm), *Good* (−90 to −80), *Fair* (−100 to −90), *Poor* (−110 to −100), *Very poor* (−120 to −110), *Extremely poor* (below −120): those of Network Insights, with Extremely poor |
| RSRQ | *Excellent* (≥ −10 dB), *Good* (−14 to −10), *Fair* (−16 to −14), *Poor* (−20 to −16), *Very poor* (−24 to −20), *Extremely poor* (below −24): the ranges of the KMZ files in the six RSRP levels |
| SINR | *Excellent* (≥ 20 dB), *Good* (13 to 20), *Fair* (5 to 13), *Poor* (0 to 5), *Bad* (below 0): those of Network Insights |
| UE Tx Power | ≥ 24 dBm, 22 to 24, 15 to 22, 5 to 15, 0 to 5, −10 to 0, below −10: the ranges and colours of the KMZ files, from dark red to blue |

The Map Levels travel with [NQ Calls Configuration](#nq-calls-configuration) and NQ Call Tracking: exports, transfers (the import preview tells the levels that change), backups and restores take those of the package, measure by measure.

## Ericsson RCA results

**Import Ericsson RCA Results**, in the **NQ Analysis Configuration** menu (admins and super-admins), imports the results of the Ericsson RCA: a CSV (comma, semicolon or tab separated) or Excel file with one row per call and the columns

| Column | Content |
| --- | --- |
| `JOIN_ID` | The NetCheck identity of the call (required; any case). |
| `Auto_RCA_Category_A`, `Auto_RCA_Subcategory_A` | Root cause category and subcategory found for the A side. |
| `Auto_RCA_Category_B`, `Auto_RCA_Subcategory_B` | The same for the B side. |
| `RCA_Category`, `RCA_Subcategory` | The first category and subcategory of the Ericsson RCA, before its final checks (**Ericsson RCA Initial Category** and **Ericsson RCA Initial Subcategory** fields). |
| `RCA_Suggested_Category`, `RCA_Suggested_Cause` | The root category and cause the Ericsson RCA suggests. |
| `RCA_Evidence` | Why the Ericsson RCA chose them (shown in the **Ericsson RCA Evidence** field). |

Column names are matched ignoring case, spaces and underscores, the separator is the one of the header row, at least one RCA column is needed, and any other column (for example a confidence or the cell measurements, up to 80) is kept and shown with the call.

The `RCA_Summary.csv` of the Auto RCA output of the Ericsson RCA is read as it is: `JoinID` identifies the call, `Final_RCA_Category` and `Final_RCA_Subcategory` are the suggested category and cause, `RCA_Category` and `RCA_Subcategory` fill the Ericsson RCA Initial Category and Initial Subcategory fields (and suggest when a row has no final values), `RCA_Evidence` the evidence, and the `UE` column puts the rows of the A and B sides in the fields of each side. The rows of one `JOIN_ID` are combined: a row without a result (no category, or *UNKNOWN* when the Ericsson RCA had no measurements of the session) is left out when its side has another one, the suggestion is the first one that names a cause (the A side first; an *Other …* or *UNKNOWN* result only when no row names one), and the evidence and the other columns keep the value of each row, labelled with its side (or its number and category).

### Import the results

1. Open **NQ Analysis Configuration → Import Ericsson RCA Results**. **Download Template** gives an empty file with these columns and an example row.
2. **Choose File**. The preview tells how many results match a call of the workspace, the columns found, the rows left out without a `JOIN_ID`, the `JOIN_IDs` with several rows and the Ericsson RCA categories and causes that no Root Category or Root Cause of the [Root Cause Catalog](#root-cause-catalog) matches by name or keywords, with the domain proposed for each one (*Other* results of a technology in RAN, *UNKNOWN* without a domain).
3. Keep **Add them to the Root Cause Catalog with the results** (on by default) to add those values, so the recommendation can use them.
4. Press **Import**. A new file adds its results and replaces those of the same `JOIN_ID`. Results whose `JOIN_ID` is not indexed yet apply as soon as the call is.

The dialog lists the imported files with their results, date and user.

> [!WARNING]
> **Replace the previous results** forgets every result imported before, and **Delete every result** removes them all: the calls lose their Ericsson RCA values and recommendations, and their selected root cause stays.

## Previous NQ Analyses

**Import Previous NQ Analyses**, in the **NQ Analysis Configuration** menu, brings the analyses made with the previous tool into the follow-up of the calls of the workspace without losing any of them. Only admins and super-admins import them: the other roles open it read-only, under a card that says so, and can download the template and the equivalences the import uses, but not choose a file, upload or forget equivalences, preview or import. The file is a CSV or an Excel workbook (`.xlsx` or `.xlsm`): every visible sheet with a `JOIN_ID` (or `Call Key`) column in its first three rows is read; hidden sheets and sheets without it are left out.

### Import the analyses

1. Open **NQ Analysis Configuration → Import Previous NQ Analyses** and **Choose File**. **Download Template** gives an empty file with the columns of the catalog in its order.
2. Optionally review the equivalences: **Download Equivalences**, change **Maps to** and the **Domain**, and **Upload Equivalences** (see [Equivalences](#equivalences)).
3. Press **Preview**: it reads the file without changing anything.
4. Choose what happens with the values the calls already have:
   - **Keep them: fill only the empty values (the import note keeps the others)** (by default) leaves every value a call already has and writes the value of the file in the note; a status is set only on calls that follow the Status Rules.
   - **Replace them with the values of the file** overwrites them (it asks for confirmation).
5. Press **Import Analyses** (the history, the Status Rules and the root domain follow) and read the summary in **Import completed**.

> [!IMPORTANT]
> **Preview the file first.** The preview enables the import and tells the sheets read and left out, how many calls it has, how many are found in the workspace and how many are not loaded yet, the columns it imports and those it keeps in the note, the CDR columns before the analysis, the list values, teams, root categories and causes it would add, the domains it would change, the values that are not values of their field, the rows it cannot place, the calls in several rows, how many calls would change and how many comments and notes would be added.

While the file is previewed or imported, a panel over the dialog shows each step, how far it is and the time. When the import ends, **Import completed** shows what the file brought: its calls in a bar and in cards with their share (updated, already up to date, imported for calls not in the workspace yet, and left out), and the comments and import notes added, the analyses dated by their analysis, the new catalog values and the values kept only in the note; **See the details** returns to the whole summary of the import and **Done** closes both.

> [!TIP]
> **Importing a file again adds nothing.** A status from the file is set by hand, the catalog gets only the new values some call takes, and a comment or note the call already has is not added again. Every import is written to App Logs (`nq_analyses_import`).

### How the rows are read

- Each row is the analysis of its call. A cell with several `JOIN_IDs` (an analysis of an area) gives the analysis to each of them. A row without `JOIN_ID` that repeats the CDR is its call by the Operator, Campaign and session of the CDR, as the tool names the calls without `JOIN_ID` (the WhatsApp calls).
- The columns are matched by the name or key of a field (ignoring case, spaces and underscores) or by the names of the analysis workbooks of the previous tool: Final Category/Classification and Final Cause/Subcategory (or Sub Category) are the Selected Root Category and Root Cause, Initial Category/Classification and Initial Cause/Subcategory the Initial Root Category and Cause, Responsible Stream the Team Responsible, Team the Analyst, Analysis Finished the Analysis Status, Status the Planned Status, Evaluation the Implementation Status, Stream responsible the Implementation Team, Action proposal and Site the Implementation Proposals and Implementation Site, Serving Cell, Band and Vendor the fields *… when Failure* (two vendors in one cell, one per line or as Ericsson/Huawei, are Vendor 1 and Vendor 2), Problem / Solution Location the Problem Location and Findings_Bucketization the Findings.
- A sheet that repeats the CDR export before the analysis starts its analysis at its Unique ID, Priority or Item (Serial number) column (or the first column that fills a field): the CDR columns before it are left out, as the tool has them.
- Each comment column (Comments, Comment, Comments (only to fill out by BNP NQ stream)…) becomes a comment of its own, after the name of its column in brackets (but Comments). Findings Comments and Proposed Measure Comments are added after the Findings and the Proposed Measure, after the name of their column.
- The Unique ID of the analysis and the Polygon Area of a data analysis fill their own fields. **Date last modification** (the Date of a data analysis) dates what the import does to the call — its changes in the history, its comments, its note, the status the Status Rules give it and its Date last modification, which never goes back before a later change made in the tool — so the Progress View shows each analysis in its week; a call without it takes its own date (from the CDR) a week later, else the time of the import, and a cell that is not a date stays in the note.
- Everything else goes to the **import note** of the call, a comment that starts with *Imported from* the file, sheet and row: the other columns of the analysis (the Item of a data analysis, the NetCheck and Auto_RCA columns repeated in the analysis, Campaign, Region, City…), a second column for the same field, the values of another row of the same call, the values that are not values of their field, the cells a field takes only part of, the values an equivalence renames and the values a call keeps. A column that repeats what the tool already has of a call found in the workspace is left out: Campaign, Region, Operator, City, Vendor and the NetCheck columns when they say what its CDR says (also written otherwise, such as Q3 for UK_Q3_2025, B for Vendor B or an Operator the Operator Maps name the same), the Auto_RCA columns when they say what its Ericsson RCA says, and a second column of a value with the same value.
- The analysis of a call that is not in the workspace yet (a Completed call, or a call of a CDR not loaded) is kept with the identity the call will have, and the call shows it as soon as its CDR is indexed.

The Excel export of Non-Qualified Calls is read too (its first row names the sections; its columns from the CDR or the Ericsson RCA are left out), so a file exported, completed elsewhere and imported again keeps its values.

### How the values are checked

Values are checked as if they were chosen in the call, after the reviewed equivalences:

- A list value or team written another way (the same letters and digits, such as RF OPT (Hot Spots)_WP2a) takes the name of the catalog, and a new one the spelling most rows use (Not Planned and Not planned are one value). Yes and No in Analysis Status are Finished and Pending, No_Vendor_B and No_JoinID Missing in Analysis Status are Invalidated (the note keeps them as written), Solved and Closed in Implementation Status are Implemented and Invalidated is Not Applicable, while its Planned and Not Planned fill the Planned Status (a Status column of the row keeps its own value, the other one going to the note), the priorities 1 to 5 are P1 to P5, Successful Call-Excluded is No Team, E2E stream is E2E Team (and the domain Core 2G/4G/5G is Core), L800 and N3500 are LTE800 and NR3500, and MOC and MTC in the Failed Party are the UE that called or was called, from the Call Direction of the row.
- A value missing from a list is added to it (but to the Failed Party, which keeps its four values), and a missing team is created. A cell with several values of a list (two bands, one per line) gives the field the first one.
- A Planned Date that is a fiscal year, a year or a quarter (FY28, 2027, Q3 2027) fills the **Planned FY** as a fiscal year (FY28, FY27; the first one when the cell lists several), and so does the Planned FY column.
- A Root Category or Root Cause is taken when the catalog has it, or through an equivalence, which can add a new one. The **Domain** of the equivalence (an existing domain or a new name, which becomes a domain) becomes its domain in the catalog, also for a value the catalog has; without one, a new value takes its domain automatically. A call whose Root Category is *Invalidated* gets the Analysis Status *Invalidated* too, and a call with a Root Cause and no Root Category takes the category the cause is mapped to.
- The **Analyst** of each call (the Team or Analyst column of the workbooks; an Analyst column after it stays in the note) is the user account named as it: the equivalence of the value (Analyst → username), else the account with that username, else the only account named as it by its first and last name (the whole name, or its first part). An analyst no account is named as keeps their name, with the spelling most rows use (Raj Kumar and Rajkumar are one analyst), as an **analyst without account**: the preview lists them under **Analysts without account** with their rows, so their accounts can be given in the equivalences before importing or later with [Link Analysts to Accounts](#link-analysts-to-accounts).
- The **Reviewer** of each call is matched to a user account the same way (the equivalence of the value, Reviewer → username, else its username, else the only account named as it). A reviewer no account is named as keeps their name, with the spelling most rows use, as a **reviewer without account**, listed in the preview under **Reviewers without account**.

### Equivalences

The equivalences of the analysis workbooks of the previous tool, as the analysts reviewed them, are built into the import (the **rules of the tool**: the teams, root categories and causes with their domains, and the values of the lists those workbooks write otherwise), so every workspace imports them without uploading anything. **Download Equivalences** gives them as a workbook: without a file, every equivalence the import uses; with a file chosen, every value of its follow-up and list columns, its rows and what it becomes (**Maps to**).

The workbook tells how each value was decided (a rule of the tool, reviewed in this workspace, the same value, a value of the catalog, by the direction of the call, a new value, a suggestion of the keywords of the catalog to check, or a new Root Category or Root Cause whose **Domain** to choose), and its Maps to and Domain cells list the values each one takes (those of the catalog and those the equivalences add; a new name can be typed). Change Maps to (empty leaves the value out of its field, in the note) and the Domain, then **Upload Equivalences**: the rows that differ from the rules of the tool are kept in the workspace, before the rules, for its next imports, and travel with its configuration. **Default Equivalences** forgets, after confirming, every equivalence uploaded for the workspace, so the import uses only the rules of the tool again.

## Link Analysts to Accounts

**Link Analysts to Accounts** (in the **NQ Analysis Configuration** menu; admins and super-admins apply it) gives the analysts and reviewers without account, which the [Previous NQ Analyses](#previous-nq-analyses) bring, their user accounts: the account becomes the **Analyst** of the calls they analyse and the **Reviewer** of the calls they reviewed, all at once.

> [!TIP]
> **Create the accounts of the analysts and reviewers first**, with their first and last name: the dialog finds each one by the username or by the name of their account.

1. Open **NQ Analysis Configuration → Link Analysts to Accounts**. It lists every analyst and reviewer of the calls of the workspace without a user account, one row per person also when they analysed some calls and reviewed others (the names written with the same letters, such as Raj Kumar and Rajkumar, are one person, shown with the spelling most calls use and the others below it), with their calls **As Analyst** and **As Reviewer**.
2. Check the **User account** of each person, a list of the users of the workspace by their first and last name. It proposes the only user named as them by username or by first and last name (the whole name, or its first part, as in userb.test or UserB Test for UserB); **Keep without account** leaves their calls as they are.
3. Read **Calls that change** and the line below the list: they count, as you choose, the calls that will take the account as their Analyst or Reviewer and the teams the accounts will join.
4. Press **Link**. Each call records the change in its history, the Status Rules follow, and the change is written to App Events (`nq_analysts_linked`).

- Every call keeps its team: when the team has members and the account is not one of them, the account joins it.
- Every spelling of a person becomes one account in the filters, the table and the exports. The former name stays in the history of each call.
- Once everybody has an account, the list is empty.

> [!NOTE]
> The calls whose CDR is not loaded yet (their analysis imported and waiting for it) change too: their imported analysis takes the account, with its history, and the line below the list says how many of the calls that change wait for their CDR.

## Exports

**Export Excel**, in the NQ Calls panel, downloads every call that matches the filters, not only the current page. **Export PPT** and **Export Word**, on the right of the indexing badge and **Reindex** in the Filters panel, download the Executive Summary (its indicators and every breakdown on one slide), the NQ Prioritization (the calls to analyse next in each queue, the steps of the strategy, Scoring Impact by KPI and the repeated issues, in the order of the page, each table on its slides), the NQ Hotspots, Clustered & Time-Window Issues, the NQ Rate by Campaign and Operator, the Failures by Type, Technology & Serving Cell, the Root Cause Sources, the Root Cause Analysis, the Lifecycle & Phases and the Progress Status of the filtered calls with the look of the page (indicator cards, breakdowns, donuts, timeline, age and workload, root domains, categories and causes, root domains by call type, and the detail tables), with the report selection on the cover (and the period chosen in the Progress View): the same document as the Non-Qualified Calls section of a report of [Reporting](reporting.md). Both formats are composed as [that section](reporting.md#how-a-report-is-composed): small charts and tables share a slide, and Word holds them on portrait pages after the cover and a **Contents** page, exactly as in PowerPoint, a view that does not fit whole in what is left of a page starting the next one (rendered with LibreOffice; without it, one page per slide). A progress dialog stays open while it is prepared.

### Excel workbook

Its **NQ Calls** sheet has two header rows coloured like the meeting workbook: the first names the section of each column (merged over its columns, in the colour of the section) and the second the field, every field of a section in the same lighter shade of it (also those from the CDR, the Ericsson RCA or derived). The status of each block and the fields read most stand out in a shade darker than their section: NQ Call Status in General, Analysis Status, Implementation Status and Planned Status (the first list of each phase), the Selected Root Category and Root Cause, the Failure Comment, the Comments, the Description, the Findings and the Proposed Measure (these three in wider columns), and the `JOIN_ID` and Call Key of the call. The columns are:

1. **Call**: `JOIN_ID`, the Call Key and the CDR of the call first, to find a call at once, then Service, Start and End Time, Operator, `Operator_Vendor`, `Vendor_Operator`, Vendor, Campaign, NR Mode, Region, Cluster, City, Technology, Test Name, Session Type (CDR), Direction, Result, Failure Phase, Failure Technology, Cell ID, Latitude, Longitude, its CDR Version, the Latest CDR and the Non-Qualified samples of Speech calls.
2. Every field of the Analysis Center marked **Excel** in the [layout](#table-layouts) you see, in the order of [Fields & Sections](#fields-and-sections), under its section (Failure Comment in Failure Details): NQ Call Status is followed by **Status Set** (Automatic or By hand); the RCA block ends with the **Root Domain**, the **Recommended Root Category** and **Root Cause**, the **Recommendation Sources** and the **Selected Root Category** and **Root Cause**; and **Comments** holds every comment of the call, one per line with its date, time and author.
3. The CDR columns of that layout, for the table or for Excel only, then **Updated By** and **Updated At** (when the follow-up of the call last changed).

The other sheets are **Speech Samples** with the follow-up of each Non-Qualified sample of the Speech calls (when there are any), **Comments** with every comment and its author, edits and deletion, and **History** with every follow-up and field change. Each of their rows starts with the `JOIN_ID` of its call, as the NQ Calls sheet does, and the comments and changes of each call come together, in the order of the NQ Calls sheet (a Speech sample with its call) and then by date.

## Scheduled reports

The reports of [Reporting](reporting.md), generated on demand or on their schedule and emailed, include a **Non-Qualified Calls** section with the panels checked in it, such as the Executive Summary, the NQ Prioritization, the NQ Hotspots, Clustered & Time-Window Issues, the NQ Rate by Campaign and Operator, the Failures by Type, Technology & Serving Cell, the Root Cause Sources, the Root Cause Analysis of each source, the Lifecycle & Phases and the Progress Status of the calls, in PowerPoint and/or Word. Each report chooses its Campaigns and common filters (NR Mode, Operator, Vendor, Region, Cluster and City), the period of the progress timeline, whether to include only open calls and whether the Root Cause Analysis of the analysts counts the suggested root causes.

## Storage and portability

The module stores its data in the workspace database, visible in [Super Admin → Database Management](super-admin.md#database-management):

| Table | Content |
| --- | --- |
| NQ Calls | The indexed NQ rows of every CDR (rebuilt automatically), with their `JOIN_ID` and, for Speech samples, their sample identity. |
| NQ Call Sources | Which CDR revision each indexed CDR comes from, whether it is a Final, Weekly or Daily CDR and the date of its newest call. |
| NQ Call Population | Every call of every CDR, qualified or not, for the NQ rates (rebuilt automatically). |
| NQ Call Population Counts | The latest version of the calls counted by Service, Campaign, Operator, NR Mode, environment, Vendor, host network, site, City and Region, read by the panels of how and where the calls fail (rebuilt automatically after the indexing, with a Parquet copy in the columnar store of the workspace that the panels add up). |
| NQ Call Versions | Which CDR holds the latest version of each Non-Qualified call and how the CDRs differ (rebuilt automatically). |
| NQ Call Latest | The latest version of each Non-Qualified call with its mapped Operator and Vendor and its last cell, read by every panel (rebuilt automatically after the indexing or a change of the Operator and Vendor Maps). |
| NQ Call Tracking | The status (and whether it is automatic or set by hand), team, analyst, root domain, category and cause, and version of each followed-up call and Speech sample. |
| NQ Analysis Fields | The field catalog: each field with its section, source, type, values, colours, keywords and options. |
| NQ Analysis Field Values | The value of each field entered by the analysts for each call and Speech sample. |
| NQ Call Comments | Every comment with its author, time, edits and deletion. |
| NQ Call History | Every change of status (by hand or by the rules), team, analyst, root category or cause and field, and every comment edit or deletion. |
| NQ Call Options | The configured statuses and teams. |
| NQ Team Members | The users that belong to each team. |
| NQ Root Catalog | The domains, root categories and root causes with the domains chosen for them, the root category of each cause, colours and keywords. |
| NQ RCA Results | The imported Ericsson RCA results, by `JOIN_ID`, with their file, date and user. |
| NQ DT Analyzer RCA Results | The [DT Analyzer RCA](#dt-analyzer-rca) of every indexed call, test and Speech sample: its rule, root domain, Root Category, Root Cause and evidence (calculated again automatically). |
| NQ DT Analyzer RCA Learned | While the DT Analyzer RCA [learns from the analysts](#dt-analyzer-rca-rules), the root cause each row learned instead of that of its rule, with its evidence and the calls it was learned from (calculated again automatically). |
| NQ User Table Layouts | The [table layout](#table-layouts) of each user: their columns, Excel and column order, and whether they see it or the workspace layout. |
| NQ Call Priority | The [NQ Prioritization](#nq-prioritization) of each call: its scoring points lost with their KPIs and level, its place, repetitions and campaigns, its hotspot, its drive (the car or the file of its CDR), its time-window issue and its cluster, and whether its failure is in a time-window issue, whether its campaign has its Final CDR scored, its Expected Gain, its prioritization, step or rule, queue and priority, and the priority filled (calculated again automatically). |
| NQ Priority Campaigns | Each campaign and NR Mode of the calls, whether it could be scored (and why not), its methodology, calls and scoring points lost. |

The section names and colours, the Status Rules, the DT Analyzer RCA Rules and its learning setting, the Prioritization Rules, the columns and column order of the workspace [layout](#table-layouts) and the reviewed equivalences of the [Previous NQ Analyses](#previous-nq-analyses) are kept in the workspace settings.

The [map of a call](#map-of-the-call) stores nothing in the workspace: it reads the CDRs, the Network Inventory and the calls when it opens. Its samples, operators and layers are a view of each user, kept in their browser (the radius is chosen for each call), so they do not travel with the packages.

### NQ Call Tracking

The follow-up — sections, the field catalog with its values, statuses, teams with their members, the root cause catalog with the Require setting and the suggestion rule, the Status Rules, the DT Analyzer RCA Rules, the Prioritization Rules and levels, the Map Levels, the equivalences of the Previous NQ Analyses, the Ericsson RCA results, the [table layouts](#table-layouts) (that of the workspace and that of each user), tracking, comments and history — travels as **NQ Call Tracking** with Admin → Import / Export / Transfer, Full Workspace and Full Environment packages, workspace transfers, and backups and restores. Imports merge it into the destination workspace: missing statuses, teams, domains, root categories and causes, fields (and list values) and equivalences are added; the sections, Status Rules, DT Analyzer RCA Rules, Prioritization Rules and levels, Map Levels, suggestion rule and Require setting of the package are taken, also where the destination had its own (the destination calculates the NQ Prioritization of its calls again), and so are the section, order, Table column, Excel and Summary breakdown of the fields it has (those only the destination has go after them); the workspace layout of the package (its columns, those for Excel only and the column order) replaces that of the destination, and the layout of each user replaces the one of the same username, also of a user the destination does not have yet; a call's newer follow-up or field value replaces an older one, and comments, history entries and RCA results are added once, so importing the same package again changes nothing; nothing the destination has is removed, and a comment with the text and author of one its call already has (the same analysis imported on both servers, for example) is taken for that one, so transfers back and forth never repeat it (the comments repeated so by earlier versions were kept once, the first one, when the workspace opened with this version). Packages of the first version, with domains and causes only, are imported into the new catalog.

> [!NOTE]
> **The follow-up finds its calls by their identity.** It applies to the destination calls with the same identity, so the destination may load the CDRs later: their calls show their follow-up as soon as they are indexed. Each call travels with its `JOIN_ID` and service, and the import finds the calls that have one by it, even when the package computed their identity otherwise; the calls without a `JOIN_ID`, and the analyses of calls whose CDR was not loaded in the source, keep their identity. Packages exported before calls were identified by their `JOIN_ID` use the former identities.

### NQ Calls Configuration

To copy only the configuration to another workspace or server, export or transfer **NQ Calls Configuration** (also a Backup component): the sections, the field catalog with its lists, the statuses, the teams with their members, the Status Rules, the DT Analyzer RCA Rules, the Prioritization Rules and levels, the Map Levels, the root cause catalog with the Require setting and the suggestion rule, the equivalences of the Previous NQ Analyses and the [table layouts](#table-layouts), without Ericsson RCA results, follow-up, comments or history. Its import merges it like the configuration part of NQ Call Tracking: missing statuses, teams, fields, list values, domains, root categories, causes and equivalences are added, and the sections, Status Rules, DT Analyzer RCA Rules, Prioritization Rules and levels, Map Levels, field settings, table layouts, suggestion rule and Require setting of the package are taken, also where the destination had its own. Statuses and teams of the destination that the package does not have stay: remove them in **Statuses & Teams** if no call uses them.

### Workspaces of earlier versions

When a workspace is first opened with this version, the follow-up of its indexed calls moves once to their `JOIN_ID` identities, and the follow-up of each Speech sample stays with that sample of its call.

The first time a workspace opens with the Analysis Center, its follow-up is kept and completed: its analysis fields join the default catalog (a field with the name of a default field keeps its values and takes its section and place), its root domains and causes become the catalog with the default categories, the first default statuses and teams are replaced while nobody had changed them (Under Investigation becomes Under Analysis, Pending Information Open, and Resolved and Not Applicable Closed), the statuses chosen before are kept by hand (only Open and the calls not yet followed up follow the Status Rules), and the default Status Rules are added.

Workspaces of earlier layouts are completed once:

- Workspaces that kept the first layout of the Analysis Center take Failure Details (formerly Failure Event) in red and Implementation and Planning in green, the Last Cell ID and Failure Comment fields, Serving Cell when Failure proposing the last cell, and the Analysis fields in the order of the call panel.
- Workspaces created before the fields of the Auto RCA output of the Ericsson RCA get them: Ericsson RCA Initial Category and Initial Subcategory before Ericsson RCA Suggested Category, and Ericsson RCA Evidence after Ericsson RCA Suggested Cause. Their NetCheck RCA fields move before those of the Ericsson RCA, and the descriptions of the default fields that named the RCA script take the new name.
- Workspaces created before the fields of the [Previous NQ Analyses](#previous-nq-analyses) get them, each after the field it follows: Initial Root Category and Initial Root Cause before Selected Root Category, Priority after NQ Call Status, Analyst, Reviewer and Unique ID after Analyst, Polygon Area and Description before Findings, Implementation Team after Implementation Status and Planned FY after Planned Date.
- Workspaces created before Vendor 2 when Failure get it after Vendor when Failure, which becomes Vendor 1 when Failure; their priorities 1 to 4 become P1 to P4 (followed by P5), the team E2E stream (and that value of Implementation Team) becomes E2E Team and the domain Core 2G/4G/5G becomes Core, with their calls; Successful Call-Excluded is no longer a team or an Implementation Team, and its calls go to No Team; their Implementation Stream becomes the Implementation Team, with its values; and the years and quarters of their Planned FY become fiscal years (2030 is FY30), in order, with their calls.
- The NetCheck RCA Suggested Cause and Ericsson RCA Suggested Cause columns leave the table (**Columns** shows them again) and the Implementation Status joins it after the Analysis Status; the Findings move after the Description.
- The Implementation Status keeps implementation values only: its Planned and Not Planned move to the Planned Status of the call, which keeps its own when it has another, Invalidated becomes Not Applicable and Closed Implemented, and Not yet evaluated turns red.
- The NQ Call Status decides which calls are in the queues: **Analysis Finished** is added after Under Analysis (In Queue only for Not Attended, Assigned and Under Analysis), and a workspace that still has the default closing rules takes the new ones (rules 2 and 5 above): a call closed only because its Analysis Status was Finished becomes Analysis Finished. App Events records it (`nq_statuses_upgraded`).
- Open is no longer a status but the group of the phase statuses: the rule of the attended calls gives Under Analysis, the calls set to Open by hand are Under Analysis, and the statuses follow the rules again. No_Vendor_B and No_JoinID Missing of the Analysis Status become Invalidated, and Status Rules still equal to the defaults of before take the new defaults, numbered from the end of the pipeline (they give every call the same status).
- The fields of the NetCheck RCA and of the Ericsson RCA take the name of their source (Netcheck Suggested Cause becomes NetCheck RCA Suggested Cause, Auto_RCA_Category_A Ericsson RCA Category A and RCA Category Ericsson RCA Initial Category), unless they were renamed.
- Workspaces created before the [NQ Prioritization](#nq-prioritization) get its fields after the Priority (Prioritization, Scoring Points Lost and Repeated Issue as columns of the table) and the default Prioritization Rules; their open calls without a Priority take that of their rule once the prioritization is first calculated.
- Workspaces created before the [strategies](#strategies) get the **Prioritization Queue** and **Expected Gain** fields after the Prioritization Rule, P6, P7 and P8 in a Priority list that still has P1 to P5, and the default strategy Dual Queue (Cities first), unless they had changed the Prioritization Rules (they keep them as the steps of Dual Queue (Scoring Based)).
- The Priority becomes a column of the workspace layout, in the column of the Prioritization, below it.
- Workspaces created when the Reviewer was a text field move it to the follow-up of the call: a Reviewer with the username or the first and last name of an account takes that account, any other name stays as a reviewer without account; its history, saved filters and equivalences follow.
- Workspaces created before the [DT Analyzer RCA](#dt-analyzer-rca) get its fields (Root Domain, Root Category, Root Cause, Rule and Evidence), which are then moved before those of the NetCheck RCA, and its default rules, the 8 Root Categories of its causes (those the catalog lacks, with each default cause still without a category mapped to its own), and their CDRs are indexed again in the background to read its values.
- Assigning a call no longer attends it: the calls only given a team, an analyst, a reviewer or a Priority since their last other change go back to their queues as **Assigned** (a call followed up before the history existed stays attended), the status Assigned comes after the first status and the rules giving it are added after the others.

## On phones

On a phone the page fits the width of the screen:

- The [Sections bar](#sections-bar) floats above the bar of the modules with the NQ Analysis Configuration beside it and shows the section being read between the arrows to the previous and the next one (a tap on it lists every section), the filters and the indicators go two per row, the tabs of the NQ Rate, the Root Cause Sources and the call scroll sideways, and the tables of the Designs keep their first column in view while they scroll.
- The table of the calls stays a table, scrolled sideways, with its header and its pages as on a larger screen, so a call is found at a glance.
- The call details fill the screen and scroll as a whole with their tabs at the top (the chosen tab comes into view), the phases two per row and the names and values of the call in two equal columns, and the dialogs of the NQ Analysis Configuration fill the screen with their rows wrapped.
- The introduction at the top of the page shows its first two lines: **More**, at its top right, shows it whole. The filters applied are small chips, and the count of the calls and **Reindex** share a row.
- The [map of the call](#map-of-the-call) and [NQ Maps](#nq-maps) take the width of the screen with their controls two per row and their zoom buttons always shown. The controls above the map take two per line, and over the map the cards **CDR Info** and **LOGS Info** go side by side below the zoom buttons (an unfolded card takes the width of the map). A double tap opens the map larger, filling the screen with its note in two lines and a lower signalling timeline, and zooms in there.

## Speed with large workspaces

The page stays quick with tens of thousands of calls: the latest version of every call (with its mapped Operator and Vendor) is kept in the **NQ Call Latest** table and rebuilt in the background after each indexing, so a filter change reads it with the current follow-up instead of working out every call again; the calls of a choice of CDRs are read once per request; the root cause suggestions are matched once for each combination of CDR values; the filters that count the suggested root causes are found once for all the panels of a filter change; and only the panels on screen are calculated. The pages never wait for the indexing or for a CDR being processed to read the calls.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| The map of a call shows no sites | No Network Inventory of the workspace lists the cells of the networks that serve its operator (see [Serving Networks](workspace-config.md#serving-networks)): upload one in [Workspace Management](workspace-management.md). A cell of the call without a site is not in that inventory, or its nearest site is farther than the maximum distance of the Serving Networks. |
| The map of a call has no streets | The tiles of the map chosen in **Map** could not be loaded (no Internet access from the browser to OpenStreetMap, OpenTopoMap or Esri): the call, its cells, sites, NQ calls and samples still show; another map type may load. |
| The elevation profile says the elevation could not be read | The browser could not reach the Terrain Tiles of AWS Open Data (`s3.amazonaws.com`): the distance and bearing still show. |
| The page shows no calls | Read the indexing badge of the Filters panel: the CDRs may be waiting to be indexed, or the indexing may be in progress. Only ready Voice, Speech and Data CDRs are indexed. Then check the chips of the active filters, or press **Reset Filters**. |
| A call I followed up is no longer listed | The most recent CDR may have it Completed, or no loaded CDR may contain it any longer. Choose its case in **CDR Version** (see [Daily and Final CDRs](#daily-and-final-cdrs)); its follow-up stays in the database. |
| A value is missing from a filter list | The other filters leave no call with it: each list offers only the values of the calls the other filters leave. Remove a filter or press **Reset Filters**. |
| The status of a call does not follow its fields | It was set by hand: choose **↺ Back to automatic**. Otherwise check the order of the [Status Rules](#status-rules): the first rule that matches wins. |
| A call cannot be closed | A field marked **Required to close** is empty, or **Require a root category to close a call** is on and the call has no root category. |
| My change was refused | Another user changed the call after you loaded it: the list reloads with the newer follow-up; make your change again if it is still needed. |
| A user is missing from the Analyst list | The team of the call has members and the user is not one of them: add the user in **Statuses & Teams → Members**, or move the call to another team. |
| Ericsson RCA results do not appear on a call | Its `JOIN_ID` is not indexed yet: the results apply as soon as the call is. Check the preview of the import for the results that match calls. |
| The DT Analyzer RCA leaves many calls Not identified | Their CDRs may wait to be indexed again with this version (read the indexing badge of the Filters panel), or their CDRs lack the radio and KPI values of its rules. Read the evidence in the RCA tab of a call and adjust the [rules](#dt-analyzer-rca-rules): each one shows the calls it explains. |
| An imported analysis does not appear on a call | The CDR of the call is not loaded yet: the analysis waits with the identity the call will have and appears when the CDR is indexed. |
| The NetCheck RCA values differ from the CDR | Spellings of one value are shown as one (see [NetCheck RCA values](#netcheck-rca-values)); the CDR keeps them as written. |
| The Scoring Impact of a call is Not scored | Hover the badge of the NQ Prioritization & Queues panel: its campaign waits for the Scoring History, has no CDR in the combined CDR tables, or the workspace has no methodology. It is scored once the reason is solved (or now with **Recalculate**). |
| The Priority of a call is not filled by its step | The call is closed, someone chose or cleared its Priority by hand (the strategy then keeps it), its analysis started with another Priority, the call is out of scope or no step of the [strategy](#strategies) takes it, the Priority list lacks the value, or **Fill the Priority of the open calls** is off in the [Prioritization Rules](#prioritization-rules). |

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
| Move, resize or keep open **CDR Info**, **LOGS Info** or **Legend** | Drag the header to move the card and its corner to resize it. **Restore** puts it back; the **pin** keeps it open on every map. A click on the header folds it; a click outside folds it unless it is pinned. |
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
