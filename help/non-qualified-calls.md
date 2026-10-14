# Non-Qualified Calls

Follow up every call and test that did not complete. Non-Qualified Calls brings the CDR Drive Test follow-up into DriveTest Analyzer as an **NQ Analysis Center**: an executive summary of every Non-Qualified call, a drill-down table of those calls, and a shared follow-up of each one that every user of the workspace sees. Each call is followed through six sections — **General**, **RCA**, **Failure Details**, **Analysis**, **Implementation** and **Planning** — with a Root Category and Root Cause decided from three sources (the NetCheck RCA of the CDR, the Ericsson RCA and the analysts), an NQ Call Status that follows the phases by rules or is set by hand, a responsible team, an assignee and a comment thread. Its panels show the lifecycle of the calls, their phases, where they fail and how the root cause sources agree.

> [!NOTE]
> **The calls need no extra input.** Every ready Voice, Speech and Data CDR of the workspace is indexed in the background, and each call keeps its follow-up by its NetCheck `JOIN_ID`. The Ericsson RCA results and the analyses of the previous tool are optional imports that complete the root causes and the follow-up.

The module is in development, so its main tab can show a red **ALPHA** label (see Interface Settings). On a new deployment it is in the Non-Qualified Calls and All Modules profiles; admins and super-admins choose who sees it in [Admin → Modules Profiles](administrator-config.md#modules-profiles).

## Choose your task

| I want to… | Go to |
| --- | --- |
| Know which calls are listed and how they are indexed | [Which calls are Non-Qualified](#which-calls-are-non-qualified) |
| Understand Daily, cumulative and Final CDRs of the same call | [Daily and Final CDRs](#daily-and-final-cdrs) |
| Choose the calls I work with | [Filters](#filters) |
| Show one panel or every panel | [NQ Calls, one panel or every panel](#nq-calls-one-panel-or-every-panel) |
| See how many calls fail and where they concentrate | [Summary](#summary) |
| Compare the NQ rate of campaigns and operators | [NQ Rate by Campaign and Operator](#nq-rate-by-campaign-and-operator) |
| Compare the NetCheck RCA, the Ericsson RCA and the analysts | [Root Cause Sources](#root-cause-sources) |
| See where the calls fail by root domain, category and cause | [Root Cause Analysis](#root-cause-analysis) |
| Follow the calls through their statuses and phases | [Lifecycle & Phases](#lifecycle-phases) |
| Track the follow-up over time, by team and by assignee | [Progress View](#progress-view) |
| Set the status, team, assignee or root cause of calls | [Non-Qualified Calls panel](#non-qualified-calls-panel) |
| Analyse one call, comment it or read its history | [Call details and activity](#call-details-and-activity) |
| Configure fields, statuses, teams, rules and the root cause catalog | [NQ Analysis Configuration](#nq-analysis-configuration) |
| Import the Ericsson RCA results | [Ericsson RCA results](#ericsson-rca-results) |
| Import the analyses of the previous tool | [Previous NQ Analyses](#previous-nq-analyses) |
| Give the calls of each analyst to their user account | [Analysts → Asignees](#analysts-asignees) |
| Export the calls to Excel, PowerPoint or Word | [Exports](#exports) |
| Send the reports on a schedule | [Reporting Jobs](#reporting-jobs) |
| Copy the follow-up to another workspace or server | [Storage and portability](#storage-and-portability) |
| Solve a problem | [Troubleshooting](#troubleshooting) |

## Which calls are Non-Qualified

A Non-Qualified (NQ) call is any Voice or Speech call, or any Data test, whose result is not **Completed**: for example **Failed** and **Dropped** Voice calls and **Failed** and **Cutoff** Data tests. The result is read from the processed `status` field of the CDR, or from `Call_Status`, `Test_Result` or `Test_Status` when it is missing. Rows without a result are not included.

### Indexing

Every ready Voice, Speech and Data CDR of the active workspace is indexed as a background task, shown in the floating background tasks card: the first time the page opens, and then, when a CDR is added, reprocessed or deleted, once nobody has used the application for two minutes (the pages refreshing themselves do not count), so the page never waits for the indexing. The top of the **Filters** panel shows how many NQ calls and CDRs are indexed, when they were last indexed, and the CDRs waiting to be indexed or the indexing in progress, after which the page reloads its calls.

> [!TIP]
> **Reindex** indexes the calls of every CDR again at once, in the background, even when no CDR has changed. Their follow-up is kept.

### Call identity

Each call keeps a stable identity: its NetCheck `JOIN_ID`, the identifier of each voice call and data test that is the same in the Daily and the Final CDRs. Without a `JOIN_ID`, the identity is its service, Operator, Campaign and test or session identifier (`Test_ID` or `Session_id` for Data tests, `Session_ID_A` for Voice and Speech calls; without one, its subscriber, test name and start and end times). Its status, team, assignee, root category and cause, fields and comments therefore stay with it when its CDR is reprocessed or uploaded again, and when the Final CDR of its campaign replaces the Daily ones. When the same call appears in several CDRs, it is listed once (see [Daily and Final CDRs](#daily-and-final-cdrs)).

Speech CDRs list one row per speech sample: Non-Qualified Calls lists each Speech **call** once (with the number of its Non-Qualified samples), and each sample keeps its own follow-up in the call details.

### NetCheck RCA values

The NetCheck RCA of the CDRs (Failure Classification, Failure Category and Failure Subcategory) is written differently from one campaign to another: the values with the same letters and digits, also with a word in singular or plural, are one value in the filters, the table, the panels and the exports, written with spaces for underscores and the words and capitals most of their calls use (RF_Problems, RF Problems and RF problems are RF Problems, and E2E traces required is E2E Trace Required). The CDRs keep them as written, and a filter saved with another spelling selects the value.

## Daily and Final CDRs

A call can be in a Daily CDR, in several cumulative Daily CDRs and in the Final CDR of its campaign (see [CDR Type](workspace-management.md#cdr-type-final-weekly-and-daily)). It is listed once, with the data of its most recent CDR: the Final CDR before the Daily ones, then the CDR with the newest calls. With CDRs chosen in the **CDRs** filter, each call shows the data of the most recent of them.

> [!NOTE]
> **The analysis of a call is shared by every CDR that contains it.** Choosing a Daily CDR, a cumulative Daily CDR or the Final CDR in the **CDRs** filter shows the same follow-up.

A badge below the result tells how the other CDRs see the call (hover it for the CDR shown and the latest one):

| Badge | Meaning |
| --- | --- |
| **Changed between CDRs** | Its result or failure is different in another CDR. |
| **Newer version in another CDR** | A more recent CDR that is not chosen in the CDRs filter has the call. |
| **Not in the Final CDR** | The call is only in Weekly or Daily CDRs while a Final CDR covers its campaign. |
| **Completed in a newer CDR** | The most recent CDR has the call Completed. These calls are listed only while that CDR is not chosen in the CDRs filter, or when **CDR Version** selects them. |

The **CDR Version** filter selects the calls of each case (**Latest version** are the others). **Call Details** lists every CDR that contains the call, Final, Weekly or Daily, with the date of its newest calls and the call's result in it.

> [!IMPORTANT]
> The analysis of a call is lost from view only when no loaded CDR contains it any longer (for example, it is not in the Final CDR and its Daily CDRs are deleted). It stays in the database and comes back if a CDR with the call is loaded again.

## Filters

The **Filters** panel restricts the summary, the panels, the table and the exports together:

| Group | Filters |
| --- | --- |
| **General Filters** | **CDRs**, **Campaign**, **Operator**, **Operator_Vendor**, **Vendor_Operator**, **Vendor**, **Region**, **Cluster**, **City**, **Service**, **Technology**, **Test Name** and **Result**, from the indexed calls, and **CDR Version** (see [Daily and Final CDRs](#daily-and-final-cdrs)). |
| **NQ Analysis Fields Filters** | The fields of [Fields & Sections](#fields-and-sections) in their order: **Failure Classification** and **Failure Category** (the NetCheck RCA of the CDR), **Root Domain**, **Root Category** and **Root Cause**, **Global Status** and **Status Set** (**Automatic** when the status follows the [Status Rules](#status-rules), **By hand** when an analyst chose it), **Team** and **Assignee** from the follow-up, every list and Yes / No field entered by the analysts or derived from the call (for example Session Type, Analysis Status or Planned Status), and **Analyst** and **Reviewer** with every name the calls hold. |
| **Additional Columns Filters** | The optional columns of the table (see [Columns](#columns)). |
| **Search** | Text in the call fields (Operator, Vendor, Campaign, Region, City, Technology, test, result, failure fields, cell, `JOIN_ID` and the CDR columns of the table), in the fields entered by the analysts and in the comments. |
| **Flags** | **Open calls only**, **Assigned to me** and **Without comments**. |

**Operator_Vendor** is the `<Operator>_<Vendor>` identity, **Vendor_Operator** the same identity as `<Vendor>_<Operator>` (both stay in sync) and **Vendor** the vendor alone; **City** offers the workspace **Main Cities** first. **Unassigned** selects calls without a team or assignee, **Not classified** calls without a root domain or category, **No cause** calls without a root cause and **Empty** the calls without a value.

> [!TIP]
> **Each filter lists only the values of the calls the other filters leave** (its own choice does not count), and the values chosen in it even when no call has them any more: choosing a Campaign leaves in the Operator list only its operators, and the Campaign list still offers every campaign of those operators. The CDRs list offers the CDRs with some of those calls, and CDR Version all its states. The funnels of the column headers list the same values.

Selecting every value of a filter, or none, applies no restriction (**Select All / None** also chooses the values hidden). Active filters appear as chips at the top of every panel (Filters, Summary, NQ Rate by Campaign and Operator, Root Cause Sources, Root Cause Analysis, Lifecycle & Phases, Progress View and the table), including those set from the Progress View and the Root Cause Analysis (NR Mode, Call Type, Period, Age of Open Calls, root domain and cause with suggestions, eNB/gNB); click a chip to remove it. The NQ Rate panel dims the chips of the filters it does not use. **Reset Filters** clears them all.

> [!IMPORTANT]
> **The selection is shared.** It is saved in the workspace, so every user finds the last filters applied, in any session and on any device. **Assigned to me** always refers to the user viewing the page.

## NQ Calls, one panel or every panel

A bar above the Filters, which stays at the top of the window while you scroll, chooses what the page shows below them:

- **NQ Calls**: the [Non-Qualified Calls](#non-qualified-calls-panel) table, with the number of calls that match the filters.
- One panel at a time: **Summary**, **NQ Rate** (NQ Rate by Campaign and Operator), **RCA Sources** (Root Cause Sources), **Root Causes** (Root Cause Analysis), **Lifecycle** (Lifecycle & Phases) and **Progress** (Progress View).
- **All panels**: the Filters, the Non-Qualified Calls table with ten calls a page, and then every other panel; **Rows** sets the calls a page of NQ Calls.

The chosen panel (the first one with All panels) opens at the top of the page, right below the bar, and stays there while its data arrives, and each browser remembers the choice for each workspace. Every panel shows, in a badge below its **Collapse** button, how many calls match the filters. A panel chosen in the sections menu of the module opens with its own view. A click on a chart filters the calls as usual, and the bar tells how many calls are left. On a narrow window the bar scrolls sideways, keeping the chosen view in sight. Beside it, **NQ Analysis Configuration** opens the configuration of the workspace (see [NQ Analysis Configuration](#nq-analysis-configuration)).

> [!TIP]
> **Only the panels on screen are calculated.** A panel of the other view, or a folded one, is calculated when it is shown, so a change of the filters only waits for what you are looking at.

## Summary

The **Summary** panel is the executive view of the filtered calls: the number of Non-Qualified Calls, how many are open and closed, how many are attended (followed up with a change or commented), and how many have a responsible team or comments. Breakdowns by Service, Result, Status, Team, Root Domain, Root Category, Root Cause, Failure Classification, Campaign, Operator, Vendor, Region, Cluster and City show where the calls concentrate, six per row and with the same colours as in the one-slide Executive Summary of the PowerPoint and Word (each status, team and root domain in its colour, root categories and causes in the colour of their domain, the other values in a fixed palette). Campaigns read as everywhere in the tool (*UK_Q2_SA_2026* reads *2026-Q2-SA*; see [Campaign ordering](technical-considerations.md#campaign-ordering)) and still filter by the full campaign.

Click any bar to drill down: the table shows only that value. Click the same bar again to remove that filter. Fields marked **Summary breakdown** add their own breakdown, in the colours of their values (those entered by the analysts or derived also drill down).

## NQ Rate by Campaign and Operator

The **NQ Rate by Campaign and Operator** panel, below the Summary, is the management view of the campaigns: for each campaign and operator, how many of **every** call of the CDRs (qualified or not) are Non-Qualified, and their share. Each call counts once, in the most recent CDR that has it (the Final CDR before the Daily ones), so a call Completed in the Final CDR is no longer Non-Qualified.

- One tab per service (Voice, Speech and Data; **All services** adds them up when there are several).
- Cards with the overall rate and the rate of each operator, each operator named in its Operator Maps colour.
- A heat map: each cell shows the rate and *Non-Qualified / all calls*, coloured in pastel tones from soft mint (none) through apricot to dusty rose (the highest rate of the table); the Total column and row sum each campaign and operator.
- A click on a cell or card shows only those calls in the other panels; a second click removes the filter.

> [!NOTE]
> Only the **CDRs**, **Service**, **Campaign**, **Operator** and **NR Mode** filters apply: the other filters describe Non-Qualified Calls only, so changing them does not recalculate the panel, and its counts are reused until the CDRs are indexed again.

The PowerPoint and Word exports and the Reporting artifact show it after the Executive Summary as one heat map with a column per service (and **All services**, their total) under each operator and the overall NQ rate of the selection at its top right (*Overall 0.9% · 992 NQ calls of 104,304 calls*), on one slide, or on two when the operators or campaigns are many (each slide with half of the operators or of the campaigns).

## Root Cause Sources

The **Root Cause Sources** panel compares the three root cause sources of the filtered calls:

- Indicators: how many calls have a **NetCheck RCA** classification, **Ericsson RCA** results and a **Selected** Root Category or Cause, and how often the sources agree: **NetCheck ↔ Selected** and **Ericsson RCA ↔ Selected** (the category, or the cause when the source maps to no category, the analysts selected is the one the source proposes, mapped onto the catalog by its keywords) and **NetCheck ↔ Ericsson RCA**.
- **NetCheck RCA → Root Domain**, **Ericsson RCA → Root Domain** and **Selected Root Domain**, each in the column of its source: the calls the source covers in each root domain, in its colour (**Not classified**: values of the NetCheck RCA or the Ericsson RCA that map onto no domain of the catalog); a domain shows only the calls the source puts in it.
- **NetCheck RCA → Root Category**, **Ericsson RCA → Root Category** and **Selected Root Category**, below the root domains: the categories of each source translated onto the [Root Cause Catalog](#root-cause-catalog), each with its root domain in a tag (**No catalog category**: values the catalog knows no category for, only a domain or nothing); a category shows only the calls the source puts in it.
- Below them, the categories and causes of each source in its own words, three hierarchies side by side: the **NetCheck RCA** Failure Category → Subcategory of the CDR, the **Ericsson RCA** Suggested Category → Cause and the Root Category → Root Cause **Selected by the Analysts**; a category or cause of the analysts drills down into its calls. Each category shows the root domain its calls fall in, in a small tag in its colour: the main one and how many more when they fall in several, all of them on hover.
- **RCA → Selected Root Category**: for the NetCheck RCA tab (the first) or the Ericsson RCA tab, how the categories the source maps to relate to the categories the analysts chose; the cells where both agree are outlined.

The PowerPoint and Word show the same on two slides, each under the indicators: the root domains and catalog categories of each source in two cards, one below the other (the first categories that fit), and then its own hierarchy (the first rows that fit).

The panel shows how many Ericsson RCA results are imported and how many match calls; they are imported with **Import Ericsson RCA Results** in the **NQ Analysis Configuration** menu (see [Ericsson RCA results](#ericsson-rca-results)).

## Root Cause Analysis

The **Root Cause Analysis** panel shows where the filtered calls fail, by the root causes of one source chosen in its tabs:

| Tab | Root causes |
| --- | --- |
| **NetCheck RCA** (chosen when the page opens) | What the NetCheck RCA of the CDR (Failure Classification, Category and Subcategory) gives each call on the [Root Cause Catalog](#root-cause-catalog), by its names and keywords and the suggestion rule (never the comments). |
| **Ericsson RCA** | What the imported [Ericsson RCA results](#ericsson-rca-results) give each call on the catalog: its category by name or keywords (*Poor Coverage LTE*, *Mobility Issue NR* → Mobility NR, *Other LTE*), and its subcategory, or else its category, as the cause. |
| **Analysts** | The Root Category and Root Cause the analysts chose (with the domain they give the call). |

Each tab shows:

- Indicators: the calls, how many have a root cause from the source (**Labelled** for the analysts, **With a Root Cause** for the other sources) and how many are **Not classified** by it.
- **By Root Domain**, **By Root Category** (where the technology of the categories tells LTE, NR and 2G/3G apart) and **By Root Cause** bars, in the colour of each domain.
- **Root Domains by Call Type** (**Classic**: the Voice and Speech calls whose test name does not contain WhatsApp; **WhatsApp**: those whose test name contains it; **Data**: the Data tests) and **NSA vs SA**, each in its own card under the legend of the root domains they share: a donut for each group with its calls in the centre, split in the colours of its root domains, each slice long enough showing its calls (every slice shows its calls and share on hover). On a narrow screen the donuts of a card stay on one row, smaller, with larger values on the slices long enough for them (the others on hover).
- **Root Domains by Technology**: a bar for each technology split in the colours of its root domains (with their legend above; a part wide enough shows its calls) and its total.
- **eNB / gNB with most calls**: the node of the last cell of each call's `Cell_ID` chain (the cell where it ended): identities above 28 bits are NR cells (gNB = NCI / 4096), LTE cells give their eNB (ECI / 256) and smaller identities are 2G/3G cells. The site, host (OSS) and vendor come from the workspace **Vodafone** and **Three** cell mapping datasets when they list the node; otherwise the vendor is the call's.

A click on a bar, on the name of a group, on the name or a slice of a donut, on a domain of a Technology bar, or on an eNB/gNB row shows only those calls (for example the NSA calls of RF), and a second click removes the filter. The domains, categories and causes filter the calls of the chosen source (for example the calls the Ericsson RCA puts in Poor Coverage LTE).

> [!TIP]
> **Show Not classified**, below the indicators, is unchecked by default for every source: the bars, donuts and technology bars count only the calls the source gives a root cause, their shares and totals being of those calls. Check it to add the Not classified calls. **Export PPT** and **Export Word** follow this checkbox, and the Reporting artifact leaves them out.

**Export PPT** and **Export Word** include the Root Cause Analysis of every source, each with its tables: the source in bold in their titles (*Root Cause Analysis · **NetCheck RCA***, ***Ericsson RCA*** or ***Analysts***) and what each slide shows in its subtitle: the Root Domains by Call Type and NSA vs SA donuts under one legend, the Root Domains by Technology bars (every technology, thinner when they are many) and the eNB / gNB with Most Non-Qualified Calls (only the first ones that fit), after the NQ Rate by Campaign and Operator and the Root Cause Sources, and before the Lifecycle & Phases and the Progress View. The Non-Qualified Calls artifact of the Reporting Jobs includes them too, and its **Root Cause Analysis** option decides whether the analysts count the calls without a root cause with their suggested one.

## Lifecycle & Phases

The **Lifecycle & Phases** panel follows the filtered calls through their follow-up:

- Indicators: the calls, how many have an **Automatic Status** (following the Status Rules) and a **Status by Hand**, how many are **Open** (attended and not closed: the sum of the phase statuses) and closed, and how many are **Stalled** (open without any change for 14 days or more). A click on Automatic, By Hand, Open or Closed shows only those calls.
- **NQ Call Status Pipeline**: a bar with the share of each status and one card per status, with its calls, share and average age: the calls not attended, then **Open** — a frame around the statuses an attended call goes through until it is closed (Under Analysis, Under Implementation and Under Planning), its total being their sum — and then the closed ones; a click on a card filters by that status, and a click on Open by all of its statuses. The rules of every card start on the same line, below its status, calls and age. Each card shows the [Status Rules](#status-rules) that set it: **Rule N** (the order they are tried in) with the field and its values in their colours, for example *Rule 6 · Analysis Status · Ongoing* on Under Analysis, and *When no rule applies* on the first status. A click on a rule shows the calls that meet it.
- **RCA Identification**: how many calls have a root category or cause selected and how many not, each row drilling down into its calls.
- One card per list field of the **Analysis**, **Implementation** and **Planning** sections (for example Analysis Status, Implementation Status and Planned Status): a bar with the share of each value and a row per value that drills down into its calls. The shares are of the calls with a value, as the card tells.
- **Time in Each Status**: the average days the calls stayed in each status before moving, from the history of their status (set by hand or by the rules).
- **Most Frequent Moves** between statuses.
- **Stalled Open Calls**: the open calls without changes for the longest, with their status, Operator, Campaign, City and days without change; click one to open it.

> [!TIP]
> **Show Empty Status**, above the phase cards, is unchecked by default. Check it to add the calls without a value (**Empty**) and give the shares of every call; **Export PPT** and **Export Word** follow it, and the Reporting artifact leaves them out.

**Status Rules** (for `user-editor` accounts and above) opens the rules from the panel.

The PowerPoint, Word and Reporting artifact show the Lifecycle & Phases as the page does, each slide saying what it shows in its subtitle: the indicators and the **NQ Call Status Pipeline** (the Open frame around the phase statuses and the rules of each status), the **Phases** in one row, the **Time in Each Status and Most Frequent Moves**, and the **Stalled Open Calls** that fit.

## Progress View

The **Progress View**, the last panel, shows how the follow-up advances for the filtered calls:

- Indicators: calls, open and closed calls, calls attended (with a follow-up change or a comment), commented, with a team and assigned, and the average days from the call to its closure (**Time to Close**).
- Donut charts **By Status**, **By Team**, **By Assignee**, **By Service** and **By Result**; each legend shows the full name with its count and share; hovering a slice shows its value, count and share, and a click on a slice or a legend entry filters the calls by that value.
- A timeline per **week**, **month** (the default), **quarter** or **year** of the calls detected, attended, commented, closed and reopened (hover a period to read all its values), with a table that adds the moves to each open status (those to a closed status are the **Closed** column), the open backlog at the end of each period and the average days from the call to its closure. The status changes, closures and reopenings count both the statuses chosen by hand and those the Status Rules set (as when importing analyses, dated by the analysis).
- The age of the open calls, the workload of each team and assignee (open, closed and total calls) and the recent activity.

As in the Summary, a click drills down into the calls: a slice or legend entry of a donut, a period of the timeline (in the chart or its table: the calls detected in that period), an age bar (the open calls of that age) or a team or assignee row shows only those calls; click it again to remove that filter. The User Activity table is informative only.

In the PowerPoint and Word, the Progress View slides show the period of the timeline in bold in their title (*Progress View · **Monthly***) and what each one shows in its subtitle: Follow-up Overview, Progress per Month, Age and Workload, Details per Month and User Activity.

## Non-Qualified Calls panel

The **Non-Qualified Calls** table lists one row per call with its start time (to the minute; hover it for the seconds) and service (and, for a Speech call, its number of Non-Qualified samples), Operator and Vendor, Region and Cluster, City and Campaign, test and technology, result with the failure classification and category (hover a failure to read its subcategory and comment) and the CDR version badge, then the RCA fields chosen as columns (none by default; Ericsson RCA Suggested Cause and NetCheck RCA Suggested Cause show in italics the suggested category of their source, named below it, when the source gives no cause, as most results of the Auto RCA output of the Ericsson RCA), its Root Category and Root Cause, the other fields chosen as columns (by default Analysis Status and Implementation Status), its **Global Status**, its team and assignee and its comments.

**Join ID**, centred in the title bar of the panel, finds calls by their `JOIN_ID`: type or paste one or more, separated by commas, spaces or lines (whatever their case), to list the calls with exactly those IDs; it is kept with the shared selection and shown among the active filters.

### Follow up the calls

1. Narrow the calls with the [Filters](#filters), the **Join ID** box or the funnel of a column header.
2. Change the **Status**, **Team**, **Assignee**, **Root Category** and **Root Cause** of a call directly in its row, or accept its recommended root cause.
3. Click a row to open the call, fill the fields of its sections and comment it (see [Call details and activity](#call-details-and-activity)).
4. Select several rows to change all of them at once (see [Bulk changes](#bulk-changes)).

Users with the `user-editor`, `admin` or `super-admin` role change the **Status**, **Team**, **Assignee**, **Root Category** and **Root Cause** directly in the row, each from a list that shows every value as a pill in its colour (with a search box for long lists, and the arrow keys to move; the list of a list field of the analysts always has the search box, and a value typed there that the list lacks is offered first as **+ Add “…”**, which adds it to the values of the field and chooses it); each value keeps the colour of its status, team or root domain (a root category is filled with the colour of its domain, a root cause outlined with it). The status, team, assignee and root cause lists widen with the window. `user-viewer` accounts see the same information read-only.

The assignees are shown by the first and last name of their account (its username when it has none) in the table, the call, the bulk bar, the Assignee filter and the Progress View, sorted by that name; the lists of assignees start with the default users of the application (super, admin and demo), tagged **default user**, with a line before the other users.

The Root Category and the Root Cause are chosen independently, each from a list grouped by domain (search it by name; the current value is ticked): the values the RCA sources of the call propose come first, and the root causes of the domain of the chosen category come before the other domains (and the categories of the domain of the chosen cause). While a call has no root category and cause, its recommended ones are shown below them, small, with the RCA they come from above them (every source in its tooltip) and a dot for the confidence of the recommendation (green high, amber medium, grey low), and a click accepts them (see [Root cause recommendation](#root-cause-recommendation)).

> [!IMPORTANT]
> **Choosing a status sets it by hand.** The list then offers **↺ Back to automatic** to give it back to the Status Rules. Below the status, each row tells whether it is **Auto** or set **By hand** and when its follow-up last changed and who changed it (hover it for the exact time).

List and Yes / No fields entered by the analysts and shown in the table are chosen in the row too, from the same coloured lists; the other fields entered by the analysts are filled in the section of the call, and the fields from the CDR, the Ericsson RCA or derived from the call are shown read only. The **›** button beside the comments opens the call. The Comments column shows how many comments a call has and its latest comment; click it to read the thread or add a comment.

### Columns

Every column header is topped with the colour of its group, as in the Excel export: the columns of the call (and the optional and CDR columns) with that of the call, each field with that of its section, and the team and assignee, root category and cause, status and comments with that of the section of their follow-up field. The default columns fit screens of 1440 px and wider without scrolling sideways: long values wrap on two lines or are shortened and shown whole when you hover them; on screens narrower than 1600 px the Comments column shows the number of comments and the latest one when you hover it. Related values share a column, one below the other, so the table fits in the panel. Drag a column header onto another to move that column before or after it; each browser remembers the order for each workspace, columns added later take their default place, and **Default column order** puts every column back. Reloading the page returns to the position it was scrolled to. The table is paginated with 25, 50, 100 or 200 rows per page.

Every name of a column header (for example *Service*, *Result*, *Team* or *Assignee*) sorts the table when clicked, and the funnel beside it opens, right below the header, that field's values to filter by them: search them by name, tick them (**Select All / None** ticks or clears the values shown; root categories and causes are grouped under their domain) and **Apply**. A column filter is the same selection as the Filters panel and its chip: the funnel is filled while that field is filtered.

**Columns**, a button of the table before **Default column order** (for `user-editor` accounts and above), chooses, for every user of the workspace, the optional columns shown after Result / Failure (Session Type (CDR) before Test / Technology):

- `JOIN_ID`, NR Mode, Cell ID, Direction, Session Type (CDR) (the CDR's `Session_Type`), End Time and CDR.
- The fields of the Analysis Center, grouped by section (the same choice as **Table column** in Fields & Sections).
- The columns of the CDRs (for example `Cellname_A`, `Region_A` or `Auto_RCA_Category_A`), which show the value of the CDR version shown for each call. Each CDR column can go to the **Table** (up to 12), and then also to the Excel export, or to **Excel** only (up to 100 more). Choosing CDR columns indexes the calls again.

Every optional column sorts the table and has its filter: Region, Cluster and CDR use their filters of the Filters panel, `JOIN_ID`, NR Mode, Cell ID, Direction, Session Type and End Time add theirs under **Additional Columns Filters**, and the CDR columns filter from their header only; every one offers **Empty** for the calls without a value. The Filters panel shows the **General Filters**, then the **NQ Analysis Fields Filters** and the **Additional Columns Filters**.

### Bulk changes

Select several rows with their checkboxes, or every row of the page with the header checkbox, to set the status (or **↺ Back to automatic**), team, assignee, root category, root cause or a list or Yes / No field of the analysts (**Set field…**) of all of them at once from the bar that appears above the table, over the row with the number of calls (it does not move the table) and stays at the top of the window while you scroll the table. The selection stays after each change, so several changes can be applied to the same calls; **Clear selection** empties it. **Accept recommendations** gives the selected calls without a root category and cause their recommended ones and leaves the others as they are.

## Call details and activity

Click a row to open its details beside the table. The header shows the service, result, CDR version, Operator, Campaign, time and place of the call and its `JOIN_ID` with a button that copies it; beside them, **‹** and **›** go to the previous and next call of the list (with the position of the call, such as 12 of 1,268, turning the pages of the table when needed), and **Go to a JOIN_ID…** opens the call of a JOIN_ID pasted there, whatever the filters (both ask first when the call has changes not saved yet). The header is followed by its **NQ Call Status** (with **Auto** or **By hand**), **Priority**, team, assignee, Root Category and Root Cause (with the domain they give the call, and the recommendation while it has none), its phases in a **Phases** subpanel, one card per phase with its name above its value — **RCA Identification** (the root category, or *Recommended* or *Not started*) and the first list field of the Analysis, Implementation and Planning sections, each in the colour of its section (a click opens its tab) — and who changed the call last.

### Tabs of the call

Below, the tabs of the call on one line, each in the colour of its section. Each tab counts, as *filled/total*, the fields of the analysts that already have a value (hover it to read it); the RCA tab shows ✓ once a root category or cause is chosen and ★ while a recommendation waits. Lists and Yes / No fields are chosen from the same coloured lists as in the table, as tall as the text boxes.

| Tab | Content |
| --- | --- |
| **Activity** (the General section) | The fields of the analysts placed in General (if any), then the activity of the call — a timeline of its comments with their author and time and every change of status, team, assignee, root category, root cause or field with the previous and new values; a status moved by the Status Rules reads *The status followed the Status Rules…* after the change that moved it. Write in the comment box and press **Add Comment** or Ctrl+Enter to share a comment with every user of the workspace. Comments keep line breaks and accept up to 5000 characters. |
| **RCA** | The **Root Cause Decision** — the selected Root Category and Root Cause, the recommendation with its confidence and the sources that agree on it (**Accept** sets it), and a card per source with what it says (the NetCheck category → subcategory first, then the Ericsson RCA category → cause) and the catalog values it maps to, with **Use** to take them. Then the values of the RCA sources (the NetCheck fields, then those of the Ericsson RCA), read only, and last the other columns of the Ericsson RCA file of the call, their names in the colour of the Ericsson RCA. |
| **Failure Details**, **Analysis** and **Implementation & Planning** | The fields of each section (Implementation and Planning in one tab, each in its own subpanel), with their description when you hover them; Failure Details also shows the **Last Cell ID** (the last cell of the Cell ID chain of the CDR, where the call ended) and the **Failure Comment** NetCheck writes in the CDR. Editors change the fields of the analysts; an empty field that proposes a CDR value (for example Failure Latitude and Longitude) offers **Use the CDR value**. Fields from the CDR, the Ericsson RCA or derived from the call are shown read only, with their source. |
| **Call Details** (in grey) | The CDRs that contain the call (when there are several), the main fields of the call (with its `JOIN_ID`, root domain, category and cause), its location (opened in OpenStreetMap) and its CDR, followed by every non-empty field of the original CDR row, which you can filter by name or value. |

**Save** in any tab saves the changed fields of every tab together; the sections tell how many changes are unsaved.

> [!TIP]
> **Long texts read as bullets.** The Description, the Findings, the Proposed Measure and the other long texts show each line as a bullet (without the `-`, `•` or `*` typed before it), nested under the line above it as deep as it is indented with spaces or tabs (a dot, then a circle, then a square), a short line ending with a colon that is not indented nor a bullet (*Problem Statement:*) as the heading of the lines below it and a line of dashes (*------Jorge------*) as a divider with its text. A click, Enter or Space opens the text to write in, tall enough for it (the Description and the Findings, one below the other, the tallest; the Proposed Measure two lines), and leaving it shows the bullets again; an empty text is open to write in, with a guide in grey that shows how to write each of them and disappears as soon as you type. The text is saved as written, and the long texts from the CDR or the Ericsson RCA read the same way.

For a Speech call, **Call Details** starts with its **Speech Samples**: its Non-Qualified samples with their result, failure, status, root category and cause and comments; open one to follow it up on its own (status, team, assignee, root cause, fields and comments), and **‹ Back to the call** returns to the call.

### Comments and history

Authors can edit and delete their own comments, and admins and super-admins can edit or delete any comment. Edited comments show **edited**; deleted comments leave a note with who deleted them and when, and the history keeps the previous text of every edited or deleted comment.

Admins and super-admins can delete the history: the **×** of a change deletes that entry, **Clear history** above the timeline (shown when the call has a history) deletes the whole history of the call, and **Clear history** in the bar of the selected calls deletes the history of all of them. Only the history is deleted: the status, team, assignee, root cause and comments stay, and the deletion is recorded in the audit log.

> [!CAUTION]
> **A deleted history cannot be recovered** (importing an older NQ Call Tracking package adds back the entries it contains), and the Progress View counts only the remaining changes.

> [!NOTE]
> **Nobody overwrites a newer follow-up by mistake.** When another user changes a call after you loaded it, your change is refused and the list reloads; the same applies to the fields saved in the tabs. The open page refreshes the calls and the open call every minute.

## NQ Analysis Configuration

**NQ Analysis Configuration**, beside the floating bar of the views (for `user-editor` accounts and above; only its icon on a phone), opens the configuration of the workspace, shared by every user:

| Option | What it configures |
| --- | --- |
| [Fields & Sections](#fields-and-sections) | The fields every call is followed up with, their lists, columns and Excel order. |
| [Statuses & Teams](#statuses-and-teams) | The NQ Call Statuses and the responsible teams with their members. |
| [Status Rules](#status-rules) | How the status follows the Analysis, Implementation and Planning fields. |
| [Root Cause Catalog](#root-cause-catalog) | Domains, Root Categories and Root Causes, with their keywords, and the suggestion rule. |
| **Import Ericsson RCA Results** | The results of the Ericsson RCA, by `JOIN_ID` (see [Ericsson RCA results](#ericsson-rca-results)). |
| **Import Previous NQ Analyses** | The analyses made with the previous tool, by `JOIN_ID`, for admins and super-admins only; the other accounts see it dimmed, with the reason as its tooltip (see [Previous NQ Analyses](#previous-nq-analyses)). |
| **Analysts → Asignees** | The user account of each Analyst as the Asignee of their calls (see [Analysts → Asignees](#analysts-asignees)). |

The imports and Analysts → Asignees come after a line. The sections menu of the Non-Qualified Calls tab lists the **NQ Analysis Configuration** too, after a line, with every option: choosing one opens it on the page.

## Fields and sections

**Fields & Sections** (for `user-editor` accounts and above, in the NQ Analysis Configuration menu) configures the catalog of fields every call is followed up with, shared by every user, in the order of the Excel export. **Sections** renames and recolours the six sections (their tabs, the colours of the table headers and of the Excel; by default General blue, RCA yellow, Failure Details red, Analysis purple, Implementation green and Planning a darker green); chips above the fields show the fields of one section, and a filter finds them by name.

Each field has a name, a **section**, a **source** and a **type**:

| Source | Fields |
| --- | --- |
| **Entered by the analysts** | A **List** of values, each with a colour, **Text** (up to 300 characters), **Long text**, **Number**, **Date** (YYYY-MM-DD) or **Yes / No**. **Propose the CDR value of** offers an empty field the value of a call field (*Use the CDR value* in the call; for example Failure Latitude and Longitude, Serving Cell, Band and Vendor 1 when Failure, Host Network when Failure). |
| **Follow-up of the call** | The NQ Call Status, Team Responsible, Asignee, Date last modification, Comments, Selected Root Category and Selected Root Cause. They can be renamed, moved to another section and reordered, but not removed. |
| **From the CDR** | A call field, the last cell of the Cell ID chain (`last_cell_id`) or a CDR column (`column:<name>`, indexed automatically), read only (for example the NetCheck RCA Failure Classification, Suggested Category and Suggested Cause, the Last Cell ID and the Failure Comment). |
| **From the Ericsson RCA** | A column of the [Ericsson RCA results](#ericsson-rca-results), read only (Ericsson RCA Category A … Ericsson RCA Evidence). |
| **Derived from the call** | A list whose values have keywords looked for in some call fields; the first value whose keywords appear is the value of the call (Session Type: WhatsApp, MULTI-RAB, CALL, HTTP Transfer, Browsing & Streaming and Interactivity & Ping from the CDR `Session_Type` and Test Name). |

Each field can be a **Table column**, go to **Excel** (every field by default), be a **Summary breakdown** (lists and Yes / No) and, when the analysts enter it, be **Required to close**: a call cannot be closed, by hand or by a change of its fields, while a required field is empty. A description is shown when hovering the field. The order of the list (↑ ↓) is the order of the fields in their section and in the Excel export.

> [!WARNING]
> Renaming a list value updates every call that uses it and the Status Rules; a value or a field still used by a call cannot be removed, and the type and source of a field with values cannot change.

### Default catalog

The default catalog is the 37 fields of the meeting workbook and those of the analyses of the previous tool (see [Previous NQ Analyses](#previous-nq-analyses)), in its order but with the NetCheck RCA before the Ericsson RCA, with the Ericsson RCA Initial Category, Initial Subcategory and Evidence and the Last Cell ID and Failure Comment of the CDR in Failure Details:

| Section | Fields |
| --- | --- |
| **RCA** | The fields of each source named after it: NetCheck RCA Failure Classification, NetCheck RCA Suggested Category, NetCheck RCA Suggested Cause, Ericsson RCA Category A, Ericsson RCA Subcategory A, Ericsson RCA Category B, Ericsson RCA Subcategory B, Ericsson RCA Initial Category, Ericsson RCA Initial Subcategory, Ericsson RCA Suggested Category, Ericsson RCA Suggested Cause, Ericsson RCA Evidence; then Initial Root Category, Initial Root Cause, Selected Root Category, Selected Root Cause. |
| **General** | NQ Call Status, Priority (P1 to P5, shown after the NQ Call Status at the top of the call), Team Responsible, Asignee, Analyst, Reviewer, Unique ID, Date last modification, Comments. |
| **Failure Details** | Session Type, Failed Party (MOC/MTC) (UE1/UE2), Host Network when Failure, Last Cell ID, Serving Cell when Failure (proposing the Last Cell ID), Band when Failure, Vendor 1 when Failure, Vendor 2 when Failure (the second vendor when the failure involves two), Failure Comment. |
| **Analysis** | Analysis Status, Tunnel Failure, Needed Technology, Failure Latitude, Failure Longitude, Problem Location, Solution Location, Polygon Area, Description, Findings, Proposed Measure. |
| **Implementation** | Implementation Status (Not yet evaluated in red, Under evaluation, Evaluated, Implemented and Not Applicable), Implementation Team, Implementation Proposal, Implementation Site, Notice to VF3. |
| **Planning** | Planned Status, Planned Date, Planned FY. |

**Analyst** and **Reviewer** keep who analysed and reviewed the call, also when they are not users of the tool, beside the **Asignee** (the user responsible for the call now); the **Implementation Team** is the team that implements the measure, which can differ from the Team Responsible; and the **Planned FY** is the fiscal year a measure is planned for when it has no date, always written FY27: a year or a quarter typed or imported becomes its fiscal year (2027 and Q3 2027 are FY27), the new fiscal years take their place in the list in order, and a value that is not a fiscal year is refused (the import keeps it in the note).

### Catalog workbook

**Export Catalog** downloads the whole catalog as an Excel workbook that is easy to edit and to import again: **About** (how to edit it), **Sections** (key, name and colour), **Fields** (order, section, name, key, type, source, source reference, table, Excel, summary, required, CDR value proposed and description), **Lists** (one row per list value with its colour and keywords), **Root Catalog** (each domain with its colour, each root category with its domain and each root cause with its root category and domain, empty when it is Auto, all with their keywords), **Statuses and Teams** (with the closed statuses and the team members) and **Status Rules** (one row per condition).

**Import Catalog** reads that workbook, or the field list of the meeting workbook (the sections in the first row, the field names in the second, the kind of values in the fourth and the values of each list from the sixth), and previews what it adds before **Import**: new fields, list values, domains, root categories, causes, statuses and teams are added, the sections and Status Rules of the workbook are taken, and nothing is removed.

## Statuses and teams

**Statuses & Teams** (for `user-editor` accounts and above, in the **NQ Analysis Configuration** menu) configures the values shared by the workspace. Each status and team has a name, a colour and a position; statuses marked **Closed** count as closed in the summary and are left out by **Open calls only**. The first status is the one of the calls that no [Status Rule](#status-rules) matches, such as the calls nobody has followed up yet.

The defaults are the statuses Not Attended, Under Analysis, Under Implementation, Under Planning and Closed (closed) — an attended call is open, in one of the three phase statuses, until it is closed — and the teams E2E Team, RAN Planning Coverage, RAN Planning Capacity, RF OPT (Hot Spots) WP2a, Operations, Netcheck and PCI Planning Team.

- Renaming a status or team updates every call that uses it, and a renamed status is renamed in the Status Rules.
- A team that is still used by a call, or a status still set by hand on a call, cannot be removed; move those calls first, or merge the team into another one with **⤳** (Merge into…): on **Save** its calls go to that team, its members join it (a team open to everyone stays so) and it is removed. The calls whose status the Status Rules gave follow the rules again when their status is removed.
- **Default Statuses** and **Default Teams** leave only the defaults, in their order and colours (a status or team with the same name is kept, with its calls and members, and recoloured), and **Save** applies the change; then **Default Rules** in [Status Rules](#status-rules) puts the default rules back.

### Team members

The **Members** button of each team (*Everyone* or the number of members) opens a dialog to choose the workspace users that belong to it, with a filter and **Select All / None**; a user can belong to several teams. The members are saved with **Save**.

> [!IMPORTANT]
> **A team with members accepts only them as assignees.** When a call has a team with members, its **Assignee** list offers only them, and moving the call to a team its assignee does not belong to clears the assignee. A team without members accepts every user of the workspace.

Choosing only the assignee brings the call to their team (the first one in the list when they are in several) unless the call already has a team they belong to or a team without members.

## Status Rules

The **NQ Call Status** of each call is semi-automatic: it follows the **Status Rules** of the workspace until an analyst chooses it by hand. **Status Rules** (for `user-editor` accounts and above, in the NQ Analysis Configuration menu and the Lifecycle & Phases panel) lists the rules in order; each sets a status when every one of its conditions holds.

> [!IMPORTANT]
> **The first rule that matches gives the status of the call.** The order of the rules is the order they are tried in, so a call that meets several rules gets the status of the first one.

A condition reads a list or Yes / No field entered by the analysts or derived from the call, the team, the assignee, the root category or cause, or **Attended** (the call has a follow-up change or a comment), and is **is one of** or **is not one of** some values, **is empty** or **is not empty**. The rules do not name fixed values: they choose among the values of each list, so renaming a list value or a status renames it in the rules, and a removed value or field is taken out of their conditions (a rule left without conditions is removed).

The default rules, for the default fields and statuses, go from the end of the pipeline to its start, so the most advanced phase of a call wins and the rules of each pipeline card follow one another:

1. **Closed** when Analysis Status is Rejected or Invalidated.
2. **Closed** when Implementation Status is Implemented.
3. **Closed** when Analysis Status is Finished, Planned Status is not Planned and Implementation Status is not Not yet evaluated, Under evaluation or Evaluated.
4. **Under Planning** when Planned Status is Planned.
5. **Under Implementation** when Implementation Status is Not yet evaluated, Under evaluation or Evaluated.
6. **Under Analysis** when Analysis Status is Ongoing.
7. **Under Analysis** when the call is attended (it is open, in its first phase).

Otherwise the call is **Not Attended**. **Default Rules** shows them again, with the conditions on the fields the workspace still has; a rule whose default status is no longer one of the statuses (for example after renaming it) is marked to choose the status it sets, and the rules are saved once every rule has a status.

The automatic status changes as soon as a field, a comment, the team, the assignee or the root cause of the call changes, and saving the rules, the fields or the statuses applies them to every automatic call at once. Choosing a status by hand, in the table, the call or the bulk bar, keeps it until **↺ Back to automatic**. The history tells the automatic changes apart, and the Lifecycle & Phases panel, the **Status Set** filter and the Excel export show which calls are automatic.

## Root Cause Catalog

**Root Cause Catalog** (for `user-editor` accounts and above, in the NQ Analysis Configuration menu) configures the catalog the Root Category and the Root Cause of each call are chosen from, in four tabs with a filter:

| Tab | Content |
| --- | --- |
| **Root Categories** | The categories of the analysts (by default the 22 of the meeting workbook: E2E, Poor Coverage LTE / NR / 2G/3G, DL and UL Interference LTE / NR / 2G/3G, UE / Test Setup Issue, Unclear, Operational, Invalidated, Procedure Overlap, Radio Configuration Inconsistency, High PRB Utilization, Mobility LTE / NR, No Failure/ Drop, IMSI Issue and VONR not Enabled in Source/Neighbor Site). |
| **Root Causes** | The causes, those of the meeting workbook (NLOS due to clutter or terrain profile, LOS but weak signal, Potential E2E Issue…) together with the technical causes of the first catalog (DL interference, Handover failure, No QCI1 established, DNS…), 47 by default. |
| **Domains** | The technical domains with their colour: RF, RAN, Core, Core EPSFB, IMS/E2E, AAA, Protocol, Device and Operational. |
| **Mapping** | One table with every root cause, the root category it is mapped to and its domain, and one with every root category and its domain, to map the whole catalog at once (the tab counts the causes mapped to a category). **Apply to Calls** saves the catalog and, after confirming how many, gives the calls that have a root cause and no root category the category of their cause (recorded in their history). |

Each root cause can be mapped to its root category: choosing a cause for a call without root category gives the call that category (a category already chosen stays), and the lists of a call show first the causes of its category (and the category of its cause). Each category and cause has a domain, chosen by hand or **Auto**: a cause without a domain of its own takes that of its root category, and otherwise a category or cause takes the first domain whose keywords appear in its name or keywords (*Auto · RAN*); a domain chosen by hand ignores the keywords. The domain gives them their colour, groups their lists (with the causes of the chosen category, then those of its domain, first) and gives the call its **Root Domain** (the domain of its category, else of its cause), so the statistics by domain and the hierarchies of the RCA sources stay; a change of the catalog changes the Root Domain of its calls.

> [!TIP]
> Each value has **keywords**, separated by commas, that map the NetCheck and Ericsson RCA values and the comments onto the catalog; `a+b` needs both words (`coverage+lte` matches *DL coverage problems* of an LTE call, not of an NR one).

Values are tried from top to bottom, so their order (↑ ↓) sets the priority when several match. **Add missing defaults** adds the default domains, categories and causes that are not in the catalog and keeps the existing ones with their keywords. Renaming a value updates every call that uses it; a value still used by a call cannot be removed.

> [!WARNING]
> **Require a root category to close a call** refuses closing a call while it has no root category, whether its status is chosen by hand or a change of its fields makes the rules close it.

### Suggestion rule

The suggestion rule of the workspace is described at the top. **Suggestion Rule**, there and in the Root Cause Analysis panel, shows it to every user; **admins and super-admins** change the call fields that choose the domain and those that choose the category and cause (Failure Classification, Category, Subcategory, Comment, Phase and Technology, Result, Test Name, Technology and Direction), whether the category and cause are looked for only in the domain found, whether the comments are read when the CDR leaves them unresolved and whether they can choose the domain, and whether keywords match whole words or any part of the text.

**Default Rule** returns to the default: a domain keyword in the Failure Classification chooses the domain (*RF Problems* → RF), category keywords in those fields, the Failure Category, Subcategory and Comment and the technology of the call choose the root category, and cause keywords in the Failure Category, Subcategory and Comment the root cause (*DL interference problems* of an NR call → DL Interference NR · DL interference), then the comments. *E2E Trace Required* is not a domain: its category (Packet Loss, Low Throughput, Coverage…) chooses the cause.

The rule applies at once to the suggestions, the Root Cause Analysis and the recommendations, and never changes the root causes already set. Its fields and comments concern the NetCheck RCA of the CDR; the Ericsson RCA results only follow its choice of whole words or any part of the text, since their category and subcategory are matched by name, then by the keywords of the catalog.

## Root cause recommendation

Every call gets a recommended Root Category and Root Cause, merged from its sources:

| Source | Weight | What it reads |
| --- | --- | --- |
| **NetCheck RCA** | 3 | The Failure Classification, Category and Subcategory of the CDR, mapped by the suggestion rule. |
| **Previous decisions** | 3 | The Root Category and Cause the analysts chose for at least two other calls with the same NetCheck or Ericsson RCA values. |
| **Ericsson RCA** | 2 | The Suggested Category and Cause of the [Ericsson RCA results](#ericsson-rca-results) of its `JOIN_ID` (else its Ericsson RCA Category A and Subcategory A), mapped onto the catalog by name or keywords. |
| **Comments** | 1 | The comments of the call, when the CDR leaves the root cause unresolved. |

The category with most weight wins (NetCheck goes first when it ties with the previous decisions), then the best cause among the sources that agree on it, with the same weights. The confidence is **high** when two or more sources agree, **medium** when only NetCheck or the previous decisions propose it and **low** otherwise.

> [!NOTE]
> The recommendation is shown in the table, the RCA tab of the call and the Excel export, and **Accept** (one call) or **Accept recommendations** (the selected calls) sets it; the analysts can also use what one source proposes or choose any other value, and their choices teach the next recommendations.

## Ericsson RCA results

**Import Ericsson RCA Results**, in the **NQ Analysis Configuration** menu, imports the results of the Ericsson RCA: a CSV (comma, semicolon or tab separated) or Excel file with one row per call and the columns

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

**Import Previous NQ Analyses**, in the **NQ Analysis Configuration** menu for admins and super-admins, brings the analyses made with the previous tool into the follow-up of the calls of the workspace without losing any of them. The file is a CSV or an Excel workbook (`.xlsx` or `.xlsm`): every visible sheet with a `JOIN_ID` (or `Call Key`) column in its first three rows is read; hidden sheets and sheets without it are left out.

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
- The columns are matched by the name or key of a field (ignoring case, spaces and underscores) or by the names of the analysis workbooks of the previous tool: Final Category/Classification and Final Cause/Subcategory (or Sub Category) are the Selected Root Category and Root Cause, Initial Category/Classification and Initial Cause/Subcategory the Initial Root Category and Cause, Responsible Stream the Team Responsible, Team the Analyst, Analysis Finished the Analysis Status, Status the Planned Status, Evaluation the Implementation Status, Stream responsible the Implementation Team, Action proposal and Site the Implementation Proposal and Site, Serving Cell, Band and Vendor the fields *… when Failure* (two vendors in one cell, one per line or as Ericsson/Huawei, are Vendor 1 and Vendor 2), Problem / Solution Location the Problem Location and Findings_Bucketization the Findings.
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
- The analysts and reviewers, who may not be users of the tool, are kept in **Analyst** and **Reviewer**, each name with the spelling most rows use (Raj Kumar and Rajkumar are one analyst); the **Asignee** stays for the users of the tool, and [Analysts → Asignees](#analysts-asignees) gives it, once the analysts have an account.

### Equivalences

The equivalences of the analysis workbooks of the previous tool, as the analysts reviewed them, are built into the import (the **rules of the tool**: the teams, root categories and causes with their domains, and the values of the lists those workbooks write otherwise), so every workspace imports them without uploading anything. **Download Equivalences** gives them as a workbook: without a file, every equivalence the import uses; with a file chosen, every value of its follow-up and list columns, its rows and what it becomes (**Maps to**).

The workbook tells how each value was decided (a rule of the tool, reviewed in this workspace, the same value, a value of the catalog, by the direction of the call, a new value, a suggestion of the keywords of the catalog to check, or a new Root Category or Root Cause whose **Domain** to choose), and its Maps to and Domain cells list the values each one takes (those of the catalog and those the equivalences add; a new name can be typed). Change Maps to (empty leaves the value out of its field, in the note) and the Domain, then **Upload Equivalences**: the rows that differ from the rules of the tool are kept in the workspace, before the rules, for its next imports, and travel with its configuration.

## Analysts → Asignees

**Analysts → Asignees** (for `user-editor` accounts and above, in the **NQ Analysis Configuration** menu) makes the user account of each analyst the **Asignee** of the calls they analysed, all at once.

> [!TIP]
> **Create the accounts of the analysts first**, with their first and last name: the dialog finds each analyst by the username or by the name of their account.

1. Open **NQ Analysis Configuration → Analysts → Asignees**. It lists every **Analyst** of the calls of the workspace (the names written with the same letters, such as Raj Kumar and Rajkumar, are one analyst, shown with the spelling most calls use and the others below it) with their calls and how many have no Asignee.
2. Check the **User account** of each analyst, a list of the users of the workspace by their first and last name. It proposes the only user named as the analyst by username or by first and last name (the whole name, or its first part, as in anudeep.kumar or Anudeep Reddy for Anudeep), or else the Asignee most of their calls have; **Leave unchanged** leaves their calls out.
3. Read **Calls that change** and the line below the list: they count, as you choose, the calls that will get a new Asignee and the teams the users will join.
4. Press **Apply**. Each call records the change in its history, the Status Rules follow, and the change is written to App Events (`nq_analyst_assignees`).

- By default only the calls without an Asignee get one; **Replace the Asignee the calls already have** changes the others too (it asks for confirmation).
- Every call keeps its team: when the team has members and the user is not one of them, the user joins it.

> [!NOTE]
> The calls whose CDR is not loaded yet keep their Analyst and are counted apart: open the dialog again once they are indexed.

## Exports

**Export Excel**, in the Non-Qualified Calls panel, downloads every call that matches the filters, not only the current page. **Export PPT** and **Export Word**, on the right of the indexing badge and **Reindex** in the Filters panel, download the Executive Summary (its indicators and every breakdown on one slide), the Progress Status and the Root Cause Analysis of the filtered calls with the look of the page (indicator cards, breakdowns, donuts, timeline, age and workload, root domains, categories and causes, root domains by call type, and the detail tables), with the report selection on the cover (and the period chosen in the Progress View): the same document as the [Reporting](reporting.md) artifact. A progress dialog stays open while it is prepared.

### Excel workbook

Its **NQ Calls** sheet has two header rows coloured like the meeting workbook: the first names the section of each column (merged over its columns, in the colour of the section) and the second the field, every field of a section in the same lighter shade of it (also those from the CDR, the Ericsson RCA or derived). The status of each block and the fields read most stand out in a shade darker than their section: NQ Call Status in General, Analysis Status, Implementation Status and Planned Status (the first list of each phase), the Selected Root Category and Root Cause, the Failure Comment, the Comments, the Description, the Findings and the Proposed Measure (these three in wider columns), and the `JOIN_ID` and Call Key of the call. The columns are:

1. **Call**: `JOIN_ID`, the Call Key and the CDR of the call first, to find a call at once, then Service, Start and End Time, Operator, `Operator_Vendor`, `Vendor_Operator`, Vendor, Campaign, NR Mode, Region, Cluster, City, Technology, Test Name, Session Type (CDR), Direction, Result, Failure Phase, Failure Technology, Cell ID, Latitude, Longitude, its CDR Version, the Latest CDR and the Non-Qualified samples of Speech calls.
2. Every field of the Analysis Center marked **Excel**, in the order of [Fields & Sections](#fields-and-sections), under its section (Failure Comment in Failure Details): NQ Call Status is followed by **Status Set** (Automatic or By hand); the RCA block ends with the **Root Domain**, the **Recommended Root Category** and **Root Cause**, the **Recommendation Sources** and the **Selected Root Category** and **Root Cause**; and **Comments** holds every comment of the call, one per line with its date, time and author.
3. The CDR columns chosen for the table or for Excel in **Columns**, then **Updated By** and **Updated At** (when the follow-up of the call last changed).

The other sheets are **Speech Samples** with the follow-up of each Non-Qualified sample of the Speech calls (when there are any), **Comments** with every comment and its author, edits and deletion, and **History** with every follow-up and field change. Each of their rows starts with the `JOIN_ID` of its call, as the NQ Calls sheet does, and the comments and changes of each call come together, in the order of the NQ Calls sheet (a Speech sample with its call) and then by date.

## Reporting Jobs

Reporting Jobs include a **Non-Qualified Calls** artifact with the Executive Summary, the NQ Rate by Campaign and Operator, the Root Cause Sources, the Root Cause Analysis of each source, the Lifecycle & Phases and the Progress Status of the calls in PowerPoint, Word and/or Excel (the Excel export of the page). Each job chooses its own filters (the same as the Filters panel, including **CDR Version**), the period of the progress timeline, whether to include only open calls and whether the Root Cause Analysis of the analysts counts the suggested root causes. See [Reporting](reporting.md).

## Storage and portability

The module stores its data in the workspace database, visible in [Admin → Database Management](administrator-config.md):

| Table | Content |
| --- | --- |
| NQ Calls | The indexed NQ rows of every CDR (rebuilt automatically), with their `JOIN_ID` and, for Speech samples, their sample identity. |
| NQ Call Sources | Which CDR revision each indexed CDR comes from, whether it is a Final, Weekly or Daily CDR and the date of its newest call. |
| NQ Call Population | Every call of every CDR, qualified or not, for the NQ rates (rebuilt automatically). |
| NQ Call Versions | Which CDR holds the latest version of each Non-Qualified call and how the CDRs differ (rebuilt automatically). |
| NQ Call Latest | The latest version of each Non-Qualified call with its mapped Operator and Vendor and its last cell, read by every panel (rebuilt automatically after the indexing or a change of the Operator and Vendor Maps). |
| NQ Call Tracking | The status (and whether it is automatic or set by hand), team, assignee, root domain, category and cause, and version of each followed-up call and Speech sample. |
| NQ Analysis Fields | The field catalog: each field with its section, source, type, values, colours, keywords and options. |
| NQ Analysis Field Values | The value of each field entered by the analysts for each call and Speech sample. |
| NQ Call Comments | Every comment with its author, time, edits and deletion. |
| NQ Call History | Every change of status (by hand or by the rules), team, assignee, root category or cause and field, and every comment edit or deletion. |
| NQ Call Options | The configured statuses and teams. |
| NQ Team Members | The users that belong to each team. |
| NQ Root Catalog | The domains, root categories and root causes with the domains chosen for them, the root category of each cause, colours and keywords. |
| NQ RCA Results | The imported Ericsson RCA results, by `JOIN_ID`, with their file, date and user. |

The section names and colours, the Status Rules and the reviewed equivalences of the [Previous NQ Analyses](#previous-nq-analyses) are kept in the workspace settings.

### NQ Call Tracking

The follow-up — sections, the field catalog with its values, statuses, teams with their members, the root cause catalog with the Require setting and the suggestion rule, the Status Rules, the equivalences of the Previous NQ Analyses, the Ericsson RCA results, the optional table columns, tracking, comments and history — travels as **NQ Call Tracking** with Admin → Import / Export / Transfer, Full Workspace and Full Environment packages, workspace transfers, and backups and restores. Imports merge it into the destination workspace: missing statuses, teams, domains, root categories and causes, fields (and list values) and equivalences are added, the sections and Status Rules of the package are taken, a call's newer follow-up or field value replaces an older one, and comments, history entries and RCA results are added once, so importing the same package again changes nothing. Packages of the first version, with domains and causes only, are imported into the new catalog.

> [!NOTE]
> **The follow-up finds its calls by their identity.** It applies to the destination calls with the same identity, so the destination may load the CDRs later: their calls show their follow-up as soon as they are indexed. Each call travels with its `JOIN_ID` and service, and the import finds the calls that have one by it, even when the package computed their identity otherwise; the calls without a `JOIN_ID`, and the analyses of calls whose CDR was not loaded in the source, keep their identity. Packages exported before calls were identified by their `JOIN_ID` use the former identities.

### NQ Calls Configuration

To copy only the configuration to another workspace or server, export or transfer **NQ Calls Configuration** (also a Backup component): the sections, the field catalog with its lists, the statuses, the teams with their members, the Status Rules, the root cause catalog with the Require setting and the suggestion rule, the equivalences of the Previous NQ Analyses and the optional table columns, without Ericsson RCA results, follow-up, comments or history. Its import merges it like the configuration part of NQ Call Tracking: missing statuses, teams, fields, list values, domains, root categories, causes and equivalences are added, the sections and Status Rules of the package are taken, and the table columns, suggestion rule and Require setting are taken only where the destination has none. Statuses and teams of the destination that the package does not have stay: remove them in **Statuses & Teams** if no call uses them.

### Workspaces of earlier versions

When a workspace is first opened with this version, the follow-up of its indexed calls moves once to their `JOIN_ID` identities, and the follow-up of each Speech sample stays with that sample of its call.

The first time a workspace opens with the Analysis Center, its follow-up is kept and completed: its analysis fields join the default catalog (a field with the name of a default field keeps its values and takes its section and place), its root domains and causes become the catalog with the default categories, the first default statuses and teams are replaced while nobody had changed them (Under Investigation becomes Under Analysis, Pending Information Open, and Resolved and Not Applicable Closed), the statuses chosen before are kept by hand (only Open and the calls not yet followed up follow the Status Rules), and the default Status Rules are added.

Workspaces of earlier layouts are completed once:

- Workspaces that kept the first layout of the Analysis Center take Failure Details (formerly Failure Event) in red and Implementation and Planning in green, the Last Cell ID and Failure Comment fields, Serving Cell when Failure proposing the last cell, and the Analysis fields in the order of the call panel.
- Workspaces created before the fields of the Auto RCA output of the Ericsson RCA get them: Ericsson RCA Initial Category and Initial Subcategory before Ericsson RCA Suggested Category, and Ericsson RCA Evidence after Ericsson RCA Suggested Cause. Their NetCheck RCA fields move before those of the Ericsson RCA, and the descriptions of the default fields that named the RCA script take the new name.
- Workspaces created before the fields of the [Previous NQ Analyses](#previous-nq-analyses) get them, each after the field it follows: Initial Root Category and Initial Root Cause before Selected Root Category, Priority after NQ Call Status, Analyst, Reviewer and Unique ID after Asignee, Polygon Area and Description before Findings, Implementation Team after Implementation Status and Planned FY after Planned Date.
- Workspaces created before Vendor 2 when Failure get it after Vendor when Failure, which becomes Vendor 1 when Failure; their priorities 1 to 4 become P1 to P4 (followed by P5), the team E2E stream (and that value of Implementation Team) becomes E2E Team and the domain Core 2G/4G/5G becomes Core, with their calls; Successful Call-Excluded is no longer a team or an Implementation Team, and its calls go to No Team; their Implementation Stream becomes the Implementation Team, with its values; and the years and quarters of their Planned FY become fiscal years (2030 is FY30), in order, with their calls.
- The NetCheck RCA Suggested Cause and Ericsson RCA Suggested Cause columns leave the table (**Columns** shows them again) and the Implementation Status joins it after the Analysis Status; the Findings move after the Description.
- The Implementation Status keeps implementation values only: its Planned and Not Planned move to the Planned Status of the call, which keeps its own when it has another, Invalidated becomes Not Applicable and Closed Implemented, and Not yet evaluated turns red.
- Open is no longer a status but the group of the phase statuses: the rule of the attended calls gives Under Analysis, the calls set to Open by hand are Under Analysis, and the statuses follow the rules again. No_Vendor_B and No_JoinID Missing of the Analysis Status become Invalidated, and Status Rules still equal to the defaults of before take the new defaults, numbered from the end of the pipeline (they give every call the same status).
- The fields of the NetCheck RCA and of the Ericsson RCA take the name of their source (Netcheck Suggested Cause becomes NetCheck RCA Suggested Cause, Auto_RCA_Category_A Ericsson RCA Category A and RCA Category Ericsson RCA Initial Category), unless they were renamed.

## On phones

On a phone the page fits the width of the screen:

- The bar of [NQ Calls, one panel or every panel](#nq-calls-one-panel-or-every-panel) stays on one row (scrolling sideways), the filters and the indicators go two per row, the tabs of the NQ Rate, the Root Cause Sources and the call scroll sideways, and the tables of the Dashboards keep their first column in view while they scroll.
- Each call of the table is a card with the name of every value above it, its start time and service at the top and its select box in the corner; the header of the table stays above the cards as a row of chips that sort and filter, and the cards are shown one at a time with the pager of every card list of the application (first, previous, next and last, and *Call N of total*), which moves to the next or previous page of calls by itself and keeps its card when the calls are refreshed after a change.
- The call details fill the screen and scroll as a whole with their tabs at the top (the chosen tab comes into view), the phases two per row and the names and values of the call in two equal columns, and the dialogs of the NQ Analysis Configuration fill the screen with their rows wrapped.

## Speed with large workspaces

The page stays quick with tens of thousands of calls: the latest version of every call (with its mapped Operator and Vendor) is kept in the **NQ Call Latest** table and rebuilt in the background after each indexing, so a filter change reads it with the current follow-up instead of working out every call again; the calls of a choice of CDRs are read once per request; the root cause suggestions are matched once for each combination of CDR values; the filters that count the suggested root causes are found once for all the panels of a filter change; and only the panels on screen are calculated. The pages never wait for the indexing or for a CDR being processed to read the calls.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| The page shows no calls | Read the indexing badge of the Filters panel: the CDRs may be waiting to be indexed, or the indexing may be in progress. Only ready Voice, Speech and Data CDRs are indexed. Then check the chips of the active filters, or press **Reset Filters**. |
| A call I followed up is no longer listed | The most recent CDR may have it Completed, or no loaded CDR may contain it any longer. Choose its case in **CDR Version** (see [Daily and Final CDRs](#daily-and-final-cdrs)); its follow-up stays in the database. |
| A value is missing from a filter list | The other filters leave no call with it: each list offers only the values of the calls the other filters leave. Remove a filter or press **Reset Filters**. |
| The status of a call does not follow its fields | It was set by hand: choose **↺ Back to automatic**. Otherwise check the order of the [Status Rules](#status-rules): the first rule that matches wins. |
| A call cannot be closed | A field marked **Required to close** is empty, or **Require a root category to close a call** is on and the call has no root category. |
| My change was refused | Another user changed the call after you loaded it: the list reloads with the newer follow-up; make your change again if it is still needed. |
| A user is missing from the Assignee list | The team of the call has members and the user is not one of them: add the user in **Statuses & Teams → Members**, or move the call to another team. |
| Ericsson RCA results do not appear on a call | Its `JOIN_ID` is not indexed yet: the results apply as soon as the call is. Check the preview of the import for the results that match calls. |
| An imported analysis does not appear on a call | The CDR of the call is not loaded yet: the analysis waits with the identity the call will have and appears when the CDR is indexed. |
| The NetCheck RCA values differ from the CDR | Spellings of one value are shown as one (see [NetCheck RCA values](#netcheck-rca-values)); the CDR keeps them as written. |
