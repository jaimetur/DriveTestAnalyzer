# Scoring & GAP Analysis

Calculate KPI scores from processed Data, Voice and Speech CDRs, then compare each operator with a reference operator. Results belong to the workspace and do not require a Design or Report Template.

Each calculation gives the NetCheck **Best Network** scoring, which rates every KPI of the methodology. When the methodology has Most Reliable points, it also gives the **Most Reliable** scoring of a subset of KPIs with its own maximum points, with the same CDRs, filters, aggregation and GAP reference (see [Most Reliable Network scoring](#most-reliable-network-scoring)).

> [!NOTE]
> **Start with a saved methodology.** It defines the environments, KPI formulas, thresholds and maximum points. Each result keeps a snapshot of the rules it was calculated with.

## Presentation & Guide

```presentations
scoring-gap-analysis
guide:scoring-gap-analysis.md
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Calculate the scoring of a campaign | [Calculate and review](#calculate-and-review) |
| <span class="guide-sub">↳ Choose the NR Mode and the campaign</span> | <span class="guide-sub">↳ [Choose the NR Mode and Campaign](#choose-the-nr-mode-and-campaign)</span> |
| <span class="guide-sub">↳ Set the filters, Break down by and reference</span> | <span class="guide-sub">↳ [Set filters, Break down by and reference](#set-filters-break-down-by-and-reference)</span> |
| <span class="guide-sub">↳ Reuse a saved or favourite scoring</span> | <span class="guide-sub">↳ [Reuse Saved Scorings](#reuse-saved-scorings)</span> |
| Understand filters, Break down by and the GAP reference | [Filters and Break down by](#filters-and-break-down-by) |
| <span class="guide-sub">↳ Filter by vendor</span> | <span class="guide-sub">↳ [Vendor filtering](#vendor-filtering)</span> |
| Read the results and choose the scoring settings | [Results and workspace settings](#results-and-workspace-settings) |
| <span class="guide-sub">↳ Read the summary of the scores</span> | <span class="guide-sub">↳ [Summary](#summary)</span> |
| <span class="guide-sub">↳ Read the GAPs to the competition</span> | <span class="guide-sub">↳ [GAP Analysis](#gap-analysis)</span> |
| <span class="guide-sub">↳ Find where and why points are lost</span> | <span class="guide-sub">↳ [Points Lost](#points-lost)</span> |
| <span class="guide-sub">↳ Follow the scoring across campaigns</span> | <span class="guide-sub">↳ [Scoring Trends](#scoring-trends)</span> |
| <span class="guide-sub">↳ Score each city and road with its NNS sites</span> | <span class="guide-sub">↳ [NNS Break-down](#nns-break-down)</span> |
| <span class="guide-sub">↳ Compare two methodologies on the same tests</span> | <span class="guide-sub">↳ [Methodology Impact](#methodology-impact)</span> |
| Leave calls out of the scoring | [Excluded Calls](#excluded-calls) |
| Change the methodology and its KPIs | [Methodology](#methodology) |
| <span class="guide-sub">↳ Use named methodologies and portable JSON</span> | <span class="guide-sub">↳ [Named methodologies and portable JSON](#named-methodologies-and-portable-json)</span> |
| <span class="guide-sub">↳ Configure the environments</span> | <span class="guide-sub">↳ [Configure environments](#configure-environments)</span> |
| <span class="guide-sub">↳ Edit, add or remove KPIs</span> | <span class="guide-sub">↳ [Editing, replacing, adding and removing KPIs](#editing-replacing-adding-and-removing-kpis)</span> |
| Find a scoring calculated earlier | [Scoring History](#scoring-history) |
| Save and share the results | [Persistence and exports](#persistence-and-exports) |
| <span class="guide-sub">↳ Export to PowerPoint, Word or Excel</span> | <span class="guide-sub">↳ [Results exports](#results-exports)</span> |
| <span class="guide-sub">↳ Know what the PowerPoint contains</span> | <span class="guide-sub">↳ [What is in the PowerPoint?](#what-is-in-the-powerpoint)</span> |
| Fix a missing or unexpected score | [Troubleshooting](#troubleshooting) |
| Look up the methodology JSON and calculation | [Methodology reference](#methodology-reference) |
| Check the KPI allocation of each methodology | [Supported KPI allocation](#supported-kpi-allocation) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Calculate and review

Set what to score, calculate it once, and open it again at once as a Saved Scoring.

### The Scoring & GAP Analysis panel

Everything happens in the **Scoring & GAP Analysis** panel, with the results below the configuration.

- **Favourite Scorings** (top right, with how many there are): opens the [Filter Navigator](#filter-navigator).
- **Context Filters:** opens the NR Mode, Campaign, CDRs used and filters.
- **While no scoring is shown,** a guide says where to start: a Favourite Scoring (recommended; its button pulses) or, when there is none, the Context Filters (then that button pulses) and **Calculate Scoring**.

**Showing** sums up the scoring shown on one line:

- **Star:** **☆** keeps it as a Favourite Scoring, **★** takes it out.
- **Name:** the one given, else what it filters (*Nationwide · NSA · Latest campaign*). A click opens the Filter Navigator.
- **Status:** *Calculated* with the date, *Calculating* with its progress, *Changed · not calculated*, or *Opening…*.
- **Details:** unfolds its whole card (labels, filters, **CDRs**, **✎**, **⧉**, **☆**).

**Buttons below the steps** (on phones, these and the main buttons go two by two):

- **Update Favourite:** gives the changes not calculated yet to the Favourite Scoring shown (same name, star and place) and calculates it again, after a confirmation, since it changes it for every user of the workspace.
- **Save as new Favourite:** asks for a name and keeps the changes as a new Favourite Scoring right after the one shown, which stays as it is.
- Both need changes not calculated yet and the user-editor role or above.
- **Calculate Scoring** (or **Open Scoring**) calculates the changes, or opens the Saved Scoring that already has them; **Recalculate** calculates the scoring shown again. Only one of them is offered at a time.

**One numbered block per step,** with the values of the scoring shown. Each dialog names its step.

| Block | What it holds |
| --- | --- |
| **1 Scoring Setup** | Scoring Methodology (with a link to **Scoring Methodologies**), GAP reference operator, **KPI order** of the GAP tables and KPI GAP Profile (applied at once, see [GAP Analysis](#gap-analysis)) and Postal Codes in the Points Lost Map |
| **2 Context** | NR Mode, Campaign, CDRs used and filters |
| **3 Break down by** | The levels that split the results |
| **4 Country Areas** | The areas of the Country Areas tab, always scored on the whole country |
| **5 Trends** | Campaigns, Time split and areas of the Scoring Trends tab |
| **6 NNS Break-down** | Campaigns, Regions and connecting roads of the NNS Break-down tab (off by default) |

- **Environment** is not a block: it is a view option beside **Scoring** above the results, applied without calculating.
- **Switching Country Areas or Trends off:** each card has a switch in its top right corner (on by default). Off, it is not calculated (with both off, the rows of the whole country are not read either), its card says *Off* and its tab hides from that scoring. When the same scoring with them on is already calculated and up to date, its result is used at once (without the tabs switched off), nothing is calculated again; switched on again, a part already calculated for the same scoring (the Favourite Scoring with the other part off, up to date) is taken from it and only the other part is calculated. See [Country Areas & Scoring Trends](#country-areas-scoring-trends).
- **NNS Break-down:** off by default; switched on with the switch of its card, it is calculated with the scoring and its tab shows (see [NNS Break-down](#nns-break-down)).
- **What each optional part shows:** the **i** beside the switch of the Country Areas, Trends and NNS Break-down cards opens a panel with what its tab shows, its settings and what to know.
- **Layout:** cards in three rows on large screens (the NNS Break-down on a row of its own); one-line pills on phones and narrow windows.
- **View:** Best Network or Most Reliable, NSA vs SA, NSA & SA charts and the KPI and GAP values, then **Report (PPT/Word)** with **Export this scoring** and **Custom report…** (see [Results exports](#results-exports)).

#### Change a block

1. Click a block. Its dialog starts with the values of the scoring shown (and the changes not calculated yet) and marks with **changed** what differs.
2. Choose how to apply:
   - **Apply (calculate later):** keeps the changes; the block is marked and the strip counts the blocks not calculated yet. The results keep the previous selection until **Calculate Scoring** or **Discard changes** (back to the scoring shown).
   - **Apply & Calculate:** calculates at once, once their CDRs are chosen, or opens the Saved Scoring that already has them.
   - **Cancel**, **×** or <kbd>Esc</kbd>: gives the block back its values (<kbd>Esc</kbd> closes an open list first).

**A Favourite Scoring is never changed by a calculation.** The scoring calculated, without a star, reads *from ★ <the Favourite Scoring>* beside its name until **Update Favourite** or **Save as new Favourite**.

### Prepare the inputs

1. Open the correct workspace and finish processing the required CDRs.
2. If no methodology is configured, import one under **Workspace Config → Scoring & GAP Analysis Setup**.
3. Open **Scoring & GAP Analysis** and press **Context Filters** (or choose a Favourite Scoring).
4. Choose **NSA**, **SA** or **NSA vs SA** in **NR Mode** (see [NSA vs SA](#nsa-vs-sa)).

> [!IMPORTANT]
> Every campaign of the calculation needs at least one ready **Data**, **Voice** and **Speech** CDR. Complete CDRs do not guarantee complete KPI measurements: inspect Calculation notes after processing.

### Choose the NR Mode and Campaign

There is no CDR selector: the **NR Mode** and the **Campaign** filter choose the CDRs of the calculation, those of that NR Mode in the combined CDR tables for the chosen campaigns:

- the **Final** CDR of a campaign before its **Weekly** and **Daily** CDRs, and a Weekly CDR before the Daily ones it contains;
- or, when it was changed, the **Active?** choice of the CDR in Workspace (see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)).

**Automatic choices**, listed first, are resolved whenever they are used, so they take campaigns that arrive later:

- **Latest campaign:** the newest campaign of the NR Mode with Data, Voice and Speech CDRs; **Latest 2 campaigns** … **Latest 4 campaigns:** the newest two to four.
- **Previous campaign:** the one before the latest. **All available campaigns:** every one.
- **Left out of them** (scored only when checked by hand): the [Flex campaigns](workspace-management.md#flex-campaigns) (complete but localised in one region, cluster or city, with Flex in the campaign or Campaign Maps label, such as `UK_Flex_2026` or `26-Q2-Flex`) and the [campaigns in progress](workspace-management.md#campaigns-in-progress) (Weekly or Daily CDRs only, tagged **In progress**).
- **Each stands alone:** checking one clears the other and the campaigns; checking a campaign clears it. **Select All / None** affects the campaigns only.
- **Kept as a choice:** the panel, a calculation and a Saved Scoring use the campaigns it stands for at that time.

**Other rules:**

- **Every campaign is listed,** whatever the other filters. One they leave no test of is greyed and tagged **No tests with these filters**; a calculation that includes it says in its warnings that it adds nothing (*26-Q4: no tests with the City filter of this calculation*).
- **No Campaign (All complete campaigns):** every campaign with Data, Voice and Speech CDRs but the Flex ones; those that lack a type are named in a note and left out.
- **CDRs used:** the CDRs of the calculation by type, newest campaign first, with stage and campaigns (Weekly and Daily outlined; four of each type in sight, the rest scroll). It follows every change at once, and the badge above the panel counts them.
- **Starting values:** **Latest campaign** on first use and when another NR Mode is chosen. A selection saved when CDRs were chosen by hand opens with the campaigns of its CDRs. An opened Saved Scoring shows its own CDRs (**CDRs of the opened Saved Scoring**, with **Use automatic CDRs**), only those of its campaigns, until the NR Mode or a filter changes.

#### NSA vs SA

When the workspace has NSA and SA CDRs, **NR Mode** also offers **NSA vs SA**: the NSA and SA CDRs of the chosen campaigns are scored together and every results tab shows its tables and charts twice, once per NR Mode, each as an NSA or SA calculation of the same campaigns would.

**View options** beside **Environment** (remembered by the browser and followed by **Export this scoring** and **Custom report…**):

- **NSA vs SA:** **Each panel: NSA then SA** (the default) puts each NSA panel right above the same SA panel, tagged **NSA** or **SA**, with their filters (such as the operator buttons) once above both under **NSA & SA** (operators only SA has join them). **All NSA, then all SA** shows every NSA panel under **NSA · Non-Standalone**, then every SA panel under **SA · Standalone**, each with its own filters.
- **NSA & SA charts:** **NSA & SA in the same chart** (the default) shows the NSA and SA bars of each operator in each Scoring Chart, and in the Scoring Trends one line per operator and NR Mode (SA dashed) on one axis of quarters, where 2026-Q2 and 2026-Q2-SA are one point. **NSA & SA in separate charts** draws each NR Mode on its own.
- **In the documents:** each slide of one NR Mode has **NSA ·** or **SA ·** before its title. NSA (blue) and SA (magenta) keep their colours in every tab and theme.
- **Summary:** starts with **How the measurements ran** of both NR Modes; its **Campaigns** shows the latest NSA and SA campaigns in large, with the tests of each operator in each.

**How the NR Modes are scored:**

- **Each campaign keeps its NR Mode,** so the NSA and SA tests of an operator are never added together, even under the same operator names. With the default [Campaign Maps](workspace-config.md#campaign-maps), `UK_Q3_NSA_2026` reads 2026-Q3 and `UK_Q3_SA_2026` reads 2026-Q3-SA. An SA campaign that does not name SA gets it (`UK_Q2_2026 SA`), and so does each period of a Daily to Yearly time split (`2026-W07 SA`).
- **Always broken down by Campaign:** Campaign cannot be cleared in **Break down by**, and the time split **All selected CDRs** is not offered.
- **Latest campaign is a quarter:** the automatic choices count quarters, each with its NSA and SA campaigns (Latest campaign compares 2026-Q3 NSA with 2026-Q3 SA). A quarter without SA CDRs shows NSA only.
- **Each NR Mode is scored on its own:** KPIs scored against the best operator and GAPs compare each operator with those of its own NR Mode and campaign. **By campaign** scores both campaigns of a quarter with the methodology of that quarter.
- **Same operator in NSA**, an extra **GAP reference operator** choice: the GAP of each operator in an SA campaign is its points minus its own points in the NSA campaign of the same quarter (or period), KPI by KPI and in total. Only SA campaigns have GAPs; an operator without an NSA campaign of its quarter has none, and the notes say so. It shows once in GAP Analysis (*EE vs Same operator in NSA*), the Scoring Tables, the insights and the documents.
- **Operator names:** an operator lines up in one row for NSA and SA only when both names have the same label in the [Operator Maps](workspace-config.md#operator-maps) (such as *Vodafone UK* and *Vodafone SM*).
- **Campaign Map:** it must tell NSA and SA campaigns apart; when its label leaves SA out, NSA vs SA asks to show it.
- **Where it is kept:** Saved Scorings with their exports, transfers and backups, and the Scoring section of [Reporting](reporting.md#the-report-editor) reports (**Compare NSA vs SA**, whatever the report's NR Mode, with its own **NSA vs SA** and **NSA & SA charts**). Documents and file names read **NSA vs SA** (`NSA-vs-SA`).

### Set filters, Break down by and reference

1. **Filters:** restrict **Operators**, **Vendors**, **Regions**, **Clusters** or **Cities** if needed (see [Filters and Break down by](#filters-and-break-down-by)).
2. **Break down by:** choose the levels Operator, Vendor, Region, **Cluster**, City and Campaign, in the order of the [aggregation hierarchy](#aggregation-hierarchy). **Operator** is always included and **Campaign** is checked initially; Cluster needs CDRs with a `Cluster` column, from the source CDR or a Cluster mapping.
3. **Country Areas & Scoring Trends** (always included, see below).
4. **GAP reference operator** and **Scoring Methodology**, in **Scoring Setup** (see below).

#### Country Areas & Scoring Trends

These blocks choose the Country Areas and Scoring Trends tabs, which are **always scored on the whole country**: the Region, Cluster and City filters do not apply to them, the other filters (Operator, Vendor…) do.

| Setting | Choices |
| --- | --- |
| **Breakdown** | **Region** (the default), Cluster, City or None (only the Cities on their own; needs one). **City** scores every city or, with a **City** filter, only those and the Cities on their own, which is quicker |
| **Cities on their own** | Each scored on its own; **London** by default. **Main Cities** stays as such: the Main Cities of the workspace at each calculation, which calculates again when they change |
| **Postal Codes in the Points Lost Map** | Adds the [Maps per Postal Code](#maps-per-postal-code) (off by default) |
| **Trends: Campaigns** | **All available campaigns** (the default), **Latest campaign**, **Latest 2**–**4 campaigns** or **Previous campaign** (resolved at each calculation), or chosen campaigns. Without any, the Campaign filter |
| **Trends: Time split** | **All selected CDRs** (one value, such as 24 weekly CDRs scored as those 24 weeks), **Campaign**, or **Daily**, **Weekly** (ISO weeks, `2026-W07`), **Monthly**, **Quarterly** or **Yearly** by the start time of each test, whatever the CDRs are (28 daily CDRs give four weekly points) |

- **Trends campaigns stand apart:** the Scoring Trend and the National & Country Areas Trends use the Data, Voice and Speech CDRs of their campaigns, whatever the Campaign filter, with the same filters, methodology (By campaign: each campaign with its own) and GAP reference.
- **Areas shared by both tabs:** **Same as Country Areas**, ticked in Trends, keeps the trends on the areas of Country Areas. Untick it to give them their own (for example every Region in Country Areas, only London and Manchester in the trends). With Country Areas off, the trends always have their own, starting from those of Country Areas.
- **Own measurements per area:** the National scoring, each value of the breakdown and each city are scored on their own measurements. KPI values (rates, medians, P90…) are not additive and points come from non-linear thresholds, so an area score is not a share of the National points.
- **Notice:** with Region, Cluster or City filters, both tabs start with **Not filtered by area**, naming the filters they leave out; their tab buttons always show a crossed-out filter icon that says so on hover.
- **Cost:** a couple of seconds from the [Scoring History](#scoring-history). From the CDR rows, the whole country is read too (about as long as the scoring), unless the calculation (without area filters, same levels) or its trends already scored it.

#### GAP reference, Focus and excluded operators

- **GAP reference operator:** **EE** initially. An operator the Operator Maps exclude is never offered. See [How the GAP reference is matched](#how-the-gap-reference-is-matched).
- **Focus operators:** the Operator labels with the **Focus** role in [Workspace Config → Operator Maps](workspace-config.md#operator-maps), with every name of the CDRs they stand for. They change no calculation.
  - **On the page:** they are the default operators of every operator choice; the others are offered too, under **Other operators** (beside **Focus operators**, as two subpanels for the operator buttons). The Operator filter and the operator choices stand out in the blue of the Operators.
  - **In the documents:** the panels set to **Focus Operators** in [Scoring Export Panels](workspace-config.md#scoring-export-panels) show them (see [What is in the PowerPoint?](#what-is-in-the-powerpoint)). Without Focus labels, every operator is shown.
- **Excluded operators:** the **Exclude** role leaves them out of every calculation, filter and result, as if every Operator filter did.
- **Operators without a network in an NR Mode** (the **NR Modes** of their label, such as Three, which has no SA): their tests of that NR Mode are left out of scores, GAPs, Scoring Trends and Country Areas; with NSA vs SA they keep their NSA results. Each panel heading names the pairs left out (*Out of scope: SA · Three*), and so does the foot of **Scoring per Service**, **Scoring per Category** and its **Breakdown**, on the page and in the documents (*Out of scope: SA · Three: no network in that NR Mode…*).
- **Reports:** the Scoring section of [Reporting](reporting.md) shows the GAP reference and methodology in the same order beside its campaigns, and its **Country Areas** and **Scoring Trends** side by side.

#### Scoring Methodology

- **By campaign (each campaign with its methodology)**, the initial choice: each campaign is scored with the methodology whose campaigns include it, the others with the default one (see [Methodologies by campaign](#methodologies-by-campaign)). With campaigns of different methodologies it needs **Campaign** in Break down by, and the job names the methodology of each campaign.
- **One saved methodology** for every campaign.
- **Scoring Methodologies** link: opens the methodology editor of Workspace Config in a panel over the page (96 % of its width). **Open in Workspace Config**, or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+click (or <kbd>Shift</kbd>+click) on the link, opens the whole page in another tab.

#### Aggregation hierarchy

It sets the order of the filter controls and of the Break down by levels and headers.

- **Shared** by every workspace and methodology (an application setting, not part of a methodology). **Aggregation hierarchy**, right of the Break down by levels, reorders it; editors save it for everyone.
- **Initial order:** **Operator → Vendor → Region → Cluster → City → Campaign**. Saved results keep their order until calculated again.
- **Operator is always a level,** since each operator is scored, compared and coloured on its own. It need not be first: with **City** above Operator, the tables and charts group every operator and campaign of each city.

### Calculate or recalculate

Every selection you calculate becomes a **Saved Scoring**: its CDRs, NR Mode, filters, Break down by levels, GAP reference, methodology and Scoring Trends.

- **Only Favourite Scorings** (starred **☆**) are kept and listed. An unstarred one shows only in the Showing card while you look at it, and goes when you calculate or open another, unless it is still calculating or drawing its Points Lost Map.
- **No duplicates:** the same selection (whatever its CDRs or methodology hold today) reuses its Saved Scoring.
- **Never calculated:** **Calculate Scoring** calculates and saves it. Meanwhile the strip says which blocks changed, and the card and results of the scoring shown stay (or *No Saved Scoring matches the configuration*).
- **Used before:** with its result up to date, the button reads **Open Scoring** (folder icon). When its CDRs were reprocessed or its methodology or Operator Maps changed, **Calculate Scoring** calculates it again first. **Recalculate** calculates it again anyway.
- **Sent:** at the click the results show **Starting the Scoring…** (or **Starting the Recalculation…**) with the seconds waited, while the server answers; there is no need to click again (another click while it is sent asks for nothing).
- **Waiting in the queue:** while other calculations or CDRs of the server go first, the results show **Waiting to Calculate…** with how many tasks go first; it starts on its own.
- **Queued or running:** both actions are disabled; the yellow notice says *Calculating* (or *Recalculating*) *the scoring of the selected CDRs and filters…*, the results show an animated **Calculating Scoring…** bar in the colour of the tab with its progress and step (per methodology of a calculation by campaign: checking the Scoring History of its CDRs, then calculating from it or from the CDR rows) and the time waited since the click, and the background tasks card shows the elapsed time.
- **Opening a Favourite Scoring:** the results show **Loading Scoring Results…** with the seconds waited until its tables, charts and maps arrive.
- **Always one open:** the one in use, else the first calculated Favourite Scoring.

> [!TIP]
> Read the **yellow message at the foot of the strip** when an action is unavailable. It tells whether the selection was used before and explains incomplete selections and other calculation conditions.

### Reuse Saved Scorings

**Open a Favourite Scoring** from the [Filter Navigator](#filter-navigator), with **Use Filter** on its card in **Manage Favourite Scorings** (the page then goes to its results; recorded in App Events), or by setting a selection in the blocks that is a Saved Scoring with its result up to date.

- **At once:** it becomes the scoring shown, its configuration fills the blocks and its saved result loads (*Opening…* and a **Loading Scoring Results…** bar meanwhile).
- **Results kept ready** on disk in the workspace's Scoring cache (the idle server prepares those Favourite Scorings lack), so they open at once, also after a restart. They are prepared in a process of their own, so the other users working at the same time are not slowed down.
- **Out of date** (CDRs reprocessed, methodology or Operator Maps changed): calculated again on its own, usually in a moment from the [Scoring History](#scoring-history).
- **Missing CDRs or methodology:** the saved result is shown as it was and the yellow notice says why.
- **Automatic campaign choices** (Latest campaign…, All available campaigns) are kept: the card shows the campaigns it stood for last time, and each opening takes the campaigns and CDRs it stands for then, calculating again when they changed.

#### Manage Favourite Scorings

The **Manage Favourite Scorings** panel, below the results, lists every Favourite Scoring as a card. It starts folded and stays as you leave it; **Manage Favourite Scorings** at the foot of the Filter Navigator opens it.

- **Order:** fixed and the same for every user; a newly starred one goes first, opening one does not move it.
- **Reorder:** drag a card by the tab on its left (the cursor becomes a hand; a line shows where it goes). The order travels with exports and transfers, and each move is recorded in App Events.
- **Unstar** a Saved Scoring to take it out of the lists.

**Act on several:** check cards with the checkbox on their tab (**Select all** on top checks them all). The bar stays at the top of the window while the panel scrolls:

- **Move Up** / **Move Down** (not for readers): one place, those side by side together; moved cards light up amber and the page follows the leading one.
- **Use newer CDRs** (with how many have them): updates and calculates them again in the background, while the one shown stays open.
- **Delete** (with the count; not for readers): after one confirmation, deletes them and their results, keeping their CDRs and the Scoring History; each is recorded in App Events.

**Folded cards** show the name with **Use Filter** (**In Use** for the one shown), the blue box of its filters, labels of its filtered fields besides Campaign and NR Mode (the Region, Cluster or City, such as **London** or **Vendor A**, or **Nationwide**; then the Operator or Vendor, such as **-Three** for every operator but Three; Region pink, Cluster green, City amber, Operator blue, Vendor purple, Nationwide slate) and an outlined NR Mode tab (**NSA** blue, **SA** pink, **NSA vs SA** both, also on the Showing card). A click unfolds or folds a card; unfolded cards stay so while the page is open.

**Unfolded, each card shows:**

- **Name** badge (its **Filter ID** when it has none). The Showing card shows only a given name and unfolds with **Details**.
- **Filters** (blue box with status): date last used, NR Mode, Regions, **Clusters**, Cities, Operators, Vendors and Campaigns.
- **Settings as pills:** the ordered **Break down by**, **GAP Reference**, **Scoring Methodology** (By campaign: the methodology of each campaign), **Country Areas** (Breakdown and Cities on their own; each Region and London for one saved without them) and **Scoring Trends** (its campaigns, or those of the Saved Scoring, an automatic choice with the campaigns it stood for last, and the time split).
- **Calculation time** (or **Elapsed** while it runs); **Used** (each Calculate Scoring or Recalculate of its selection, report scenario using it and **Use Filter**) and **Calculated** (each finished calculation).
- **Newer CDRs available:** when a Final CDR of the same campaign (or a newer cumulative Weekly or Daily CDR) replaces one of its CDRs. **Use newer CDRs** swaps them in the same Saved Scoring (name, star and place kept; one that already had that selection is merged into it) and calculates it again. It needs the user-editor role or above.
- **Waiting for its CDRs:** imported from another workspace before they are processed here. It finds them by file, whatever their name; one with an automatic Campaign choice (like the Favourite Scorings a new workspace starts with) takes the CDRs it stands for here.
- **Buttons:** **CDRs** (hover or click for the source files), its **Filter ID** (as App Events name it, also on the Showing card), **✎** (rename and edit), **⧉** (duplicate), **☆** (starred, it joins the list first) and **×** (delete).

**PowerPoint file name:** `yyyymmdd_hhmmss - Scoring & GAP Analysis - <NR Mode> - <Regions> - <Clusters> - <Cities> - <Operators> - <Vendors> - <Campaigns>.pptx` (`NSA-vs-SA`; a complete vendor selection reads **All Vendors**).

#### Rename, edit, duplicate or delete

**✎ Rename or edit** shows the filters above the name field.

- **Save Name** (or <kbd>Enter</kbd>) names it; <kbd>Esc</kbd> cancels.
- **Edit Filters** opens every block together in one dialog under an **Editing Saved Scoring** notice, the CDRs following its NR Mode and Campaign. Change what is needed, then **Save Changes** gives it that selection and calculates it again, keeping name, star and place (a Saved Scoring that already had that selection is merged into it). **Cancel Editing** or <kbd>Esc</kbd> leaves it and the blocks unchanged.
- It cannot be edited while it is being calculated.

**⧉ Duplicate** saves a variant (for example the same filters with Latest 3 campaigns):

1. Name the copy (its name followed by *(copy)*).
2. **Edit Filters of the Copy** opens the same dialog under a **Duplicating Saved Scoring** notice.
3. **Save as New Filter** (enabled once the selection is no Saved Scoring yet) saves and calculates it as a new Favourite Scoring right after the original (first when that one is not starred). **Cancel Editing** or <kbd>Esc</kbd> makes no copy.

**× Delete** removes it and its result after confirmation; its CDRs and the Scoring History stay. A running calculation stops at a checkpoint or discards its result.

**Who can do what:**

- **Viewers** open Saved Scorings but cannot name, edit, star or delete them.
- **Editors** delete only those they starred, or unstarred ones they calculated last. **Admins and super-admins** delete any. Deleting several deletes none when one belongs to another user.
- **Unstarring:** only admins, super-admins and whoever starred it (locked for others), since an unstarred one goes once another is opened.

#### Filter Navigator

Find a Favourite Scoring without reading every card. Open it with **Favourite Scorings** at the top, a click on the Showing card or its **Navigator** button (icon only on a phone), or the button beside the title of **Manage Favourite Scorings**.

**The tree** is built from the filters, not the names:

- **Area:** the Region, Cluster or City filtered, in the colour of its field, or **Nationwide**.
- **NR Mode:** **NSA**, **SA** and **NSA vs SA**, outlined in their colours.
- **Leaves:** each Favourite Scoring with its Campaign (an automatic choice with the campaigns it stood for last, or its campaigns), the Operator or Vendor filtered, its status when not calculated, **In Use** and its name. Look-alike leaves show what tells them apart (**GAP Reference: EE** / **GAP Reference: BT**), or their Filter ID.
- **Branches** count their Favourite Scorings; those of the one in use open with it, and opened ones stay open while the page is open.
- **Choosing one** uses it as **Use Filter** does (the one in use only closes the dialog); from a dropdown the page stays, from the panel it goes to its results. App Events record it was opened from the Filter Navigator.

**Search** keeps, as you type, the Favourite Scorings that have every word, in any order, at the start of a word, whatever capitals and accents, in name, areas, operators and vendors, NR Mode, Campaign and its campaigns, GAP reference, methodology and Filter ID. It marks the words found and counts the matches.

- `man sa lat 2` finds the *Latest 2 campaigns* of SA (and NSA vs SA) in Manchester.
- A number of one or two digits is a whole word (`2` finds *Latest 2 campaigns*, not 2026-Q3); words typed in a row stay together when a scoring has them together (`latest camp` finds *Latest campaign*, not *Latest 2 campaigns*).
- **Keys:** see [Tips & shortcuts](#tips-shortcuts). With a mouse the search is ready to type in; on a phone the dialog takes the whole screen and the keyboard waits for a tap on the search.

### What is remembered?

- **For each user, in every browser:** CDRs, NR Mode, methodology, filters (Cluster, Operator_Vendor and Vendor_Operator included), Break down by, Scoring Trends and GAP reference, saved automatically per workspace. One user's selection never changes another's; a user without one starts from the default (Latest campaign).
- **Within the browser session:** result tab, environment, scoring, display controls, comparison selection and scroll position.
- **In each Saved Scoring:** its selection, name, star, uses and calculations, and the source metadata, rules, grouping, result and warnings of its last calculation.
- **Automatic refreshes** do not overwrite edits to the controls; **removed or unready inputs** produce a notice when a selection is restored.

## Filters and Break down by

Filters choose which test rows are scored; Break down by chooses how the results are split.

### Filtering chooses rows; Break down by chooses groups

- **Filter** (City = Leeds and London): includes the rows of either city. Values within a filter combine with **OR**, different filters with **AND**; an empty selection means all values.
- **Break down by** (Operator → City → Campaign): a separate result for each operator/city/campaign combination.
- **A level left out** (Campaign not selected): the rows of the selected campaigns are pooled before calculating ratios, averages, medians and P90, never by averaging KPI results of separate files.
- **Lists:** the values of every CDR of the NR Mode (with the Operator and Vendor Maps labels) that the other filters leave: Operator Vodafone leaves only its Vendors and the Campaigns of its CDRs. A filter's own choice does not narrow its list. They come from the **CDR Filter Facets** table (read once per CDR), never from the rows; reprocess an older CDR that lacks expected choices.
- **New values:** a filter with every value checked keeps new values checked; a value no CDR has any longer is named in a warning.
- **Main Cities** selects the configured workspace cities found in the CDRs; **City** offers it first, and **Cluster** follows Region.

> [!TIP]
> Select **Campaign** when you want a separate column or bar for each campaign. Filtering two campaigns alone does not separate their results.

### Vendor filtering

Three selectors filter vendors from cached per-CDR values: **Operator_Vendor** (`<Operator>_<Vendor>`), **Vendor_Operator** (the same identity as `<Vendor>_<Operator>`, kept in sync with it) and **Vendor** alone. Their choices list real vendors, Ericsson (Mixed) (and the former Mixed Vendor), the former Other Vendor, All Vendor(s), operators without vendors as **Operator - All**, then Mixed (non-Ericsson).

- **Ericsson and Huawei** include only those identities of the selected operators. To include an operator without a vendor, also select its **Operator - All**, or leave Vendor unrestricted.
- **Vendor applies to every operator left:** Ericsson alone leaves out the other vendors of every operator.
- **Some vendors of one operator:** choose the operator in **Operator** and the vendors in **Vendor**; the other operators, and the GAP to the reference, are left out. **To keep the other operators whole,** choose those vendors in **Operator_Vendor** (or **Vendor_Operator**) with the values of the other operators, as the note under the Context filters says.
- **Compatibility:** Vendor mapping stores the suffix in `Operator_Vendor` and `Vendor`; legacy operator-only values remain supported and legacy operator-prefixed selections are normalized to vendor names. **Operator** stays independent.
- **Vendor as a level:** operators without a vendor show **All**; comparisons and the reference behave as before.

### How the GAP reference is matched

Each comparison keeps the selected environment and Break down by context.

- **Vendor comparisons** try the same vendor first, then the reference operator's **All** vendor group: **EE / All can be the reference for Ericsson, Huawei and other vendor groups.** Campaign, City, Region and the other levels must still match; the fallback never compares different cities or campaigns.
- **No match,** or no common valid environment contribution, gives **N/A***.

## Results and workspace settings

Read the results of the scoring shown, tab by tab, and choose how they look.

### Choose a scoring

The **Scoring** selector, beside Environment, switches the tables, charts, GAP analysis, notes and CSV exports between **Best Network** and **Most Reliable**. It appears when the methodology of the result has Most Reliable points.

### Choose an environment

The **Environment** selector applies to every result tab and export: one environment shows its own contribution, **All Environments** combines them (NetCheck 2026 initially: Drive - City 650, Drive - Connecting Roads 350 and Walk 0 points, 1,000 in all; custom methodologies can change it).

- **Incomplete coverage:** when the combined result is incomplete, opening a result prefers an environment with complete coverage; All Environments can still be selected.
- **Cards keep their place:** each block of results is a card whose top bar has the colours of its tab. Changing an operator, the environment, the scoring or the maps keeps the card being looked at in its place; reloading returns to the same place once everything, maps included, is drawn.

### Choose a theme

The **Theme** selector, at the start of the floating section bar, colours every chart and table of the results, designs the Scoring and GAP cells and styles the PowerPoint and Word exports.

- **Default:** **Ericsson**. Every theme is light except **Midnight**.
- **One theme for every themed module** (Scoring & GAP Analysis, Network Insights, CDR Analysis and PPT Designer): choosing it in one chooses it in all. Each user keeps it per workspace; the choice is registered in App Events. [Network Insights](network-insights.md#theme) offers the same themes.
- **Exports:** **Export this scoring** uses the theme of the page; the report editor has its own **Theme** (see [Report scenarios](#report-scenarios)).

| Theme | Colours | Scoring and GAP cells | Slide titles: font, accent of the part that tells the slide apart (subtitles) |
| --- | --- | --- | --- |
| **NetCheck** | As the NetCheck reports: blue titles, white lists with thin rules, operators on strips in their colour, amber Voice and teal Data, a bold total | Excel-like data bars as long as the share of the maximum, in the colour of the score band | Montserrat blue, first part in light capitals, accent bold (*BEST NETWORK SCORING* **per Category**) (blue, first part bold) |
| **Umlaut** | As the umlaut reports: bold dark titles over a red headline, white lists with thin rules, light grey panels, quality classes from red to green | Bars as long as the share of the maximum, in the colour of the band | Arial bold dark (red) |
| **Ericsson** | The brand guide: its greys, table headers in its deep blue (Scoring and GAP tables headed in white, each operator in dark ink), light tints for fills and deep shades for the ends of each scale; dark grey rules opening sections and closing the table, each operator ruled in its colour across its columns | Square cells filled as far as the share of the maximum, in the colour of the legend; GAPs in dark grey after a small ▲ or ▼ in their colour, over a bar either side of zero | Ericsson Hilda Light black, not bold; accent Ericsson Hilda bold deep blue (grey) |
| **Vodafone** | Vodafone red and anthracite, operators as pills in their colour, the total label on a dark grey pill and each figure on a white pill ringed in that grey | Rounded pills in the colour of the band | Vodafone Rg bold anthracite, accent red (anthracite) |
| **Midnight** | Night-blue panels, light text, neon accents; in the exports the content slides are night blue with white logos and every table, card, panel and chart dark | Dark cards with a glowing bar of the share of the maximum | Segoe UI bold and light, accent cyan (cyan) |
| **Paper** | A typeset report: serif type, black rules, italic small-capital sections | Scores underlined in the colour of their band | Georgia black, accent dark red italics (dark red italics) |
| **Heatmap** | Light panels, a red, amber, green and teal heat scale, outlined subtotals | Soft tiles tinted by the share of the maximum on the scale of their band | Segoe UI bold, accent teal (grey) |

- **Slide titles** style every content slide (covers and transitions keep the template's Vodafone-Three style); without the font, a similar one is used. A chart or table split over slides (*· 1/2*) keeps the plain heading with its part in bold.
- **GAP bars:** either side of zero as long as the GAP, in the loss colour (red in NetCheck) to the left when behind the reference and the gain colour (green) to the right when ahead, also in the KPI GAP Profile and the insight tables; points lost always grow from the left. Where a bar runs behind its value (every theme in the documents, NetCheck and Umlaut on the page, and the KPI GAP Profile everywhere), the value sits on the free side of the zero line.
- **Column headers** align like their values (right for numbers).
- **Also themed:** the National & Country Areas table, the tables of the exports, the band legend, the best and worst operators of the Summary, Voice and Data (teal Data and amber Voice in NetCheck), points behind and ahead, positions, the allocation donuts (the outer ring of environments never repeats a colour of the inner ring), and the Points Lost Map scale: yellow to red in NetCheck, blues in Ericsson, reds in Vodafone, cyan to pink in Midnight, sepia to oxblood in Paper, teal to red in Heatmap.
- **Operator colours** always come from the [Operator Maps](workspace-config.md#operator-maps).

### Area, operators and vendors of each chart and table

The title of every chart and table of the results tabs ends with three pills, so a copied chart or table (or its larger view) still tells what it shows. The documents name them at the end of each chart and table slide's subtitle (smaller when it would not fit on one line).

| Pill | From… | For example |
| --- | --- | --- |
| **Area** | The City, Cluster or Region of the comparison context or of the location chosen in the section (KPI GAP Profile, Points Lost Map, Summary…); else the most specific area filter of the Saved Scoring; else `National` | `City: London`, `Cities: Leeds & London`, `Cities: Bristol, Cardiff & 2 more`, `Region: Wales`, `National` |
| **Operators** | The Operator filter, else `All Operators` | `Operator: EE`, `Operators: EE, O2 UK & 2 more` |
| **Vendors** | The Vendor of the comparison context, else the Vendor filter (without the operator), else `All Vendors` | `Vendor: Nokia`, `Vendors: Nokia & Ericsson` |

- Lists of more than three values keep two and count the rest; hover a pill for all.
- A KPI GAP Profile or Points Lost Map slide that already names its location (`City: London · Campaign: 2026-Q2`) does not repeat it. The National & Country Areas card shows every area and has no pills.

### Results tabs

| Tab | What it holds |
| --- | --- |
| [**Summary**](#summary) | Where each operator stands, its position in every environment and service, the biggest levers and how the measurements ran |
| [**Scoring Charts**](#scoring-charts) | The scoring per Service, per Category and its Breakdown, and the maximum score allocation |
| [**Scoring Tables**](#scoring-tables) | The Summary and Breakdown tables and the Campaign Comparison |
| [**Country Areas**](#country-areas) | The scoring Nationwide and per City, Cluster or Region, the locations ranked and each operator against the reference per location |
| [**Scoring Trends**](#scoring-trends) | The Scoring Trend and the National & Country Areas Trends |
| [**NNS Break-down**](#nns-break-down) | Each city and the connecting roads campaign by campaign with their NNS and eMOCN sites, and the latest campaign by city size and scenario (when switched on) |
| [**GAP Analysis**](#gap-analysis) | The GAP tables, the GAP by part and the KPI GAP Profile |
| [**Points Lost**](#points-lost) | Where the points go, per KPI, on the map, per Vendor, kind of site, RAN Vendor, site type (Legacy, eMOCN, NNS), site and along the Connecting Roads |
| [**Methodology Impact**](#methodology-impact) | What two methodologies change in the scoring, categories, KPIs, areas, GAPs and points lost of each operator |

**Moving between tabs:**

- **Opening the page** starts at the top of **Summary**. **Reloading** (or Back and Forward, or the bar at the bottom of a phone) keeps the tab and place; what was in view stays dimmed with a loading notice until drawn.
- **Menus:** the Scoring & GAP Analysis tab menu and the sections bar list the eight tabs. A link ending in `#scoring-results-summary`, `-charts`, `-tables`, `-geographical-areas` (Country Areas), `-trends`, `-gap`, `-points-lost` or `-methodology-impact` opens that tab.
- **Sticky tab bar:** stays below the sections bar while the results scroll; a tab chosen there opens at its start.

**Operators chips** (in each section with several operators):

- The Focus operators are on by default (every operator without them). A click turns a chip on or off (its tooltip says so); one always stays on. Every section, also those drawn later, follows the last click.
- Sections comparing with the reference show it too when it is a Focus operator or enabled. Four operators go two above two; GAP by part shows two per row.
- **In the documents:** the operators chosen on the page, else those of each panel in [Scoring Export Panels](workspace-config.md#scoring-export-panels); *<Route>: where the points are*, the individual GAP comparisons and the Campaign Comparison always show those of their panel.

**Other selectors:** with several locations or Vendors, a selector chooses the one shown (**City: London**; the first by default). Sections per campaign list them chronologically, the latest chosen. These choices survive a reload; opening the page again starts from the defaults.

#### Larger view, zoom and images

These work on every chart, map and table of every results tab (gestures in [Tips & shortcuts](#tips-shortcuts)).

- **Larger view:** double-click (or <kbd>Enter</kbd>/<kbd>Space</kbd> on a focused chart card) opens it over the whole screen but 5% on each side; <kbd>Esc</kbd>, a click outside or **×** closes it.
- **Zoom:** drag a rectangle over a chart or map, or use the zoom buttons (zoom in, zoom out, whole view) shown while the pointer is over it, also in the larger view; on touch, a tap shows them for a few seconds. On a chart narrowed to fit, at the whole view **+** and **−** first widen or narrow it step by step. Cards that are not drawn charts zoom up to 8×.
- **Tooltips:** hover bars, segments, totals or donut sectors for their values.

**Download and copy buttons** (described in [Images of charts and tables](web-interface.md#images-of-charts-and-tables), the same in Network Insights, Non-Qualified Calls, Chart Builder and PPT Designer) show while the pointer is over a card, beside its zoom buttons:

- **Card button** (blue, on the top edge at the right; *Download this chart as an image (PNG)*): the whole card, such as the Best Network Scoring chart with its Maximum score per environment & service. **Inner button** (light blue, lined up with the card's or below it): only the chart or table under the pointer.
- **Screenshot button** (camera, left of each): copies the same image to the clipboard; where the browser does not allow it, the image opens in a window to copy or download.
- **The image:** a PNG of what is shown (theme, operators, choices and zoom), whole however it scrolls, named after the title and environment (`Best Network Scoring per Service - All Environments.png`). In the larger view it keeps its title and pills (a trend of one area is titled with it, such as *Best Network Trends — London*).
- **App Events** record each download or copy (`export_scoring_image`, with `destination: clipboard` or `copy-dialog`, or `export_scoring_image_failed` with the reason; *(larger view)* for the larger view).

### Summary

The Summary tab tells where each operator stands and where to act first.

| Section | What it shows |
| --- | --- |
| **How the measurements ran** | The campaigns (the latest, the reference, and the others below it, such as *+2 campaigns: 26-Q2, 26-Q1*, newest first); the first and last day and the days with tests; the cities and Connecting Roads routes; the environments with their points; and per operator the Data tests, calls and Speech samples scored in each environment of the latest campaign |
| **Where to act** | For the operator chosen in **Operator**: a headline, the themes of its points lost, then **Sites to review** (the first to review) and **Route stretches** (the route that loses most and its first stretch) |
| **Where to act, by performance owner** | A card per performance owner (see below) |
| **Where each operator stands** | Latest campaign: every operator ranked, a bar of its Data and Voice points with its total and change since the previous campaign. Per chosen operator: score and position, GAP to the reference split into Data and Voice, distance to the operators above and below, the GAP in every part of the scoring (as [GAP by part](#gap-by-part)) and a summary sentence |
| **Position in every environment and service** | Per chosen operator, a matrix of every environment and All Environments by Voice, Data and Overall: each tile is its position (green first, light green second, light red in between, red last) and share of the points available, the bar under it the points missed. All Environments is scaled as the scoring per location |
| **Biggest levers** | Per chosen operator, up to 8 KPIs where matching the reference wins most, with both values and the points to win |
| **Cities**, **Towns**, **Roads**, **Railways ranked** | Per operator, the places of the latest campaign ranked by share of the points. Needs City in Break down by |
| **<Route>: where the points are** | One card per operator on the route that loses most among theirs, or the one chosen in **Route** |

**Where to act:**

- **Operator:** buttons in Focus and Other operators subpanels; the first Focus operator by default, else the first compared one. It also chooses the performance owner cards.
- **Themes** (Voice calls, Failed data tests, Below-par data tests, most first): what to do (the points of the failed tests and the KPIs that lose most, each against its maximum, every figure in bold in the loss colour), and in **Deep-dive** a link to the section of **Points Lost** to open (Points lost per KPI of Voice or Data, Sites to review or Route stretches).

**Performance owner cards:** the owners are the Regions of the CDRs (such as Vendor A, Vendor B, VMO2 North and VMO2 South), each in a theme colour kept on every view and slide (VMO2 North, VMO2 South, Vendor B and Vendor A take the first four; others the next ones by name). Each card shows its **National points lost** (its part of the operator's National loss, in the tests of its Region; not the Region's own score, which the [Scoring Trends](#scoring-trends) give), its main issue (the setting holding most of them, with the points of each environment), its two biggest areas, its High priority sites and where its points are (Cities, Towns, Roads and railways; older Saved Scorings ask for **Recalculate**).

**Places ranked:** big cities, medium and small cities, connecting roads and train routes (from `G_Level_3` and `G_Level_2`), ranked by share of the points: 85% or more High, 75–85% Medium, under 75% Low. Columns: performance owners, share of the tests (*(drive + walk)* when both were measured), change since the previous campaign, Voice and Data shares and points lost, on one bar scale for every ranking.

**<Route>: where the points are:** a map of its stretches drawn as those of [Connecting Roads](#points-lost-per-vendor-kind-of-site-site-and-stretch) (circles sized and coloured yellow to red by points lost, the five worst numbered with their nearest city, measured cities named, each ringed in its owner's colour). Below it: the points of each owner with its share of the tests (and those whose start cell has no Region), the five worst stretches with their main owner, and what to review first.

**Operators:** the places ranked and the route have their own **Operators** buttons (the Focus operators by default, whatever the operator of Where to act); the documents follow the page for the places, and the panel's operators for the route.

**About these figures:** points lost are those lost against the maximum of each KPI, not the GAP to the reference. Split by City, Cluster or Region, each place is scored on the whole maximum and counts by its share of the tests. Towns, owners, the cities around a route, days and test counts need results of this version; older ones rank places as Cities and routes as Roads and count KPI samples instead of tests.

### Scoring Tables

The Scoring Tables tab shows the scores as a scorecard: **Summary** (category totals and the weighted total) and **Breakdown** (each category with its subtotal, then its KPIs). **Show KPI values** adds the measured values before the Score columns of Breakdown; **Show GAP values** (unchecked initially, also in the PowerPoint tables) adds GAP columns at the end or next to each compared operator's score.

**How the Scoring and GAP tables read** (the same in PowerPoint and Word):

- The header starts with the operators in their colour. Each group below (a route, city or campaign, with more than one level) is ruled under its name and set apart by a gap (a line in the documents).
- Each category opens a section with its subtotal (its number of KPIs in the GAP tables). Each KPI shows its type badge (**R** Reliable, **D** Diff) with its weight and maximum points, instead of separate columns; ordered by GAP, each KPI carries its category instead. The weighted total closes the table.
- **Summary** highlights the highest and lowest valid scores across each row, boxed in their cell (ties can highlight several; equal scores or fewer than two stay neutral).
- **Breakdown** scores take the colour of their **Low**, **Medium**, **High** or **UltraHigh** band and show their share of the maximum as the theme draws it; the band legend shows them the same way. Category totals stay neutral, and raw measurements are not summed across KPIs.
- Each GAP bar is as long as the GAP against the largest of its table, so only large GAPs stand out.
- Tables with many columns (four operators of four campaigns) narrow their columns to fit.

#### Campaign Comparison

Shown below the tables when Campaign is a Break down by level with at least two campaigns.

1. Choose the **Operator** (Focus and Other operators buttons; the first Focus operator by default) and, with several combinations of the other levels, its **Group**.
2. Choose the **Baseline campaign** and **Compared campaign** (by default the previous and the latest).

- **The table** lists every KPI with its value and points in both campaigns and **Δ Points** (compared − baseline), from the largest loss to the largest gain on a red–green scale, closed by the **Scoring Points Gap** (their sum: the change of the operator's score when every KPI is measured in both). A KPI measured in only one keeps **N/A** and stays out of the sum.
- **Different methodologies** (see [Methodologies by campaign](#methodologies-by-campaign)): a category whose KPIs changed (a KPI added or removed, or other maximum points, such as VIDEO STREAM when 2026-Q3 shares the YouTube points with TikTok) is compared as a whole, as **<category> · methodology changed** with its KPIs below without a Δ of their own (**—**); a note names those categories and the methodology of each campaign.
- The documents compare the two latest campaigns the same way.

### GAP Analysis

**GAP = compared operator weighted points − reference operator weighted points**: positive (green) leads, negative (red) trails, zero is equal and **N/A*** means no valid comparison (see [How the GAP reference is matched](#how-the-gap-reference-is-matched)).

- **GAP comparison** offers **All vs reference** and each operator. Individual comparisons order the KPIs from lowest to highest GAP in the latest campaign (other campaigns break ties), unavailable KPIs last, also in the documents.
- **KPI order:** **Within each category** (the default; All Operators in KPI definition order) or **Across all categories** (one list, lowest GAP first, each KPI with its category; All Operators by the mean GAP of its operators in the latest campaign). It is one shared choice with **Scoring Setup** and the KPI GAP Profile, applied at once without calculating, kept on reload and followed by **Export this scoring**. Saved GAP priorities do not control this order.
- **Total KPI GAP** ends every GAP table: the sum of the valid KPI GAPs of each column. Individual PowerPoint slides add the **Average KPI GAP** and **Average total KPI GAP** (see [GAP calculations and aggregates](#gap-calculations-and-aggregates)).

> [!IMPORTANT]
> **Do not apply KPI weights again to GAP points.** Each KPI GAP already subtracts weighted scoring points. Totals sum those points; averages use them directly.

#### GAP by part

**GAP by part of the scoring over the campaigns**, below the GAP tables, gives per chosen operator its GAP to the reference in every part of the scoring, for the latest campaigns (up to six) with the total and, with several, a bar of the latest; red behind, green ahead. With NetCheck methodologies the parts are the **reliability** of Voice and Data (calls and tests that complete, POLQA below 1.6, the lowest throughputs) and their **quality** (speeds, times, speech quality and higher thresholds); otherwise each category.

#### KPI GAP Profile

**KPI GAP Profile**, below it, shows each operator's GAP to the reference KPI by KPI.

- **Choices:** the **Location** (such as **City: London**; campaigns chronologically, the latest chosen) and **Operators** (Focus by default). Choosing an operator in **GAP comparison** shows it until an operator is clicked here, and GAP comparison follows a single chosen operator. Location and operators are shared with [Points lost per KPI](#points-lost-per-kpi) and the [Points Lost Map](#points-lost-map).
- **One table per chosen operator** other than the reference, two side by side: **GAP to <reference>** per KPI and environment (each environment of the selected one) and **Total**, closed by **Total KPI GAP**, with a note of each operator's total GAP.
- **Order:** by category, the furthest behind first with subtotals, or one list with **KPI order** **Across all categories**.
- **Look:** an Excel-like data bar per column (red below zero, green above) and the **R**/**D** badge of each KPI (Reliable KPIs are those of the Most Reliable scoring).
- **All Environments:** each column holds its part of the All Environments points ([scaled](#incomplete-coverage-and-achievable-scoring) when needed), so the columns add up to the Total and to the GAP of the Scoring and GAP tables.

### Points Lost

The Points Lost tab shows how many points each operator loses against the maximum, how, and where:

- **Where the points go:** for the latest campaign, the points each operator loses per [kind](#kinds-of-points-lost), as bars and a table, with what each kind counts and its KPIs (hover a bar for the KPIs that lose most).
- [**Points lost per KPI**](#points-lost-per-kpi), the [**Points Lost Map**](#points-lost-map) and [**per Vendor, kind of site, site and stretch**](#points-lost-per-vendor-kind-of-site-site-and-stretch).
- **Points counted:** those of the environment chosen, also in Where to act. In All Environments, every view gives each operator the points of **Where the points go** ([scaled](#incomplete-coverage-and-achievable-scoring) when needed). Every table closes with a **Total** row (of those listed for the map, sites and stretches).

#### Kinds of points lost

Each KPI loses its points in one kind, from its formula and Type:

| Kind | What it counts | KPIs (NetCheck) |
| --- | --- | --- |
| **Not completed (NQ)** | Calls and tests whose result is not Completed (failed, dropped, cut off…), counted by the success ratios: the Non-Qualified Calls of [Non-Qualified Calls](non-qualified-calls.md), plus Multi RAB data transfers that did not succeed (whose call may have completed) | Call success ratio (classic and WhatsApp), FDFS DL and UL success ratio, browsing success ratio, YouTube and TikTok success ratio, Multi RAB data transfer success ratio |
| **Below the minimum** | Completed calls and tests under the minimum quality of the other Reliable KPIs; not Non-Qualified Calls | POLQA < 1.6, FDTT DL throughput > 2 Mbit/s, FDTT UL throughput > 1 Mbit/s |
| **Below the threshold** | Completed above that minimum but missing the threshold of another ratio KPI (Diff); not Non-Qualified Calls | Call setup time > 10 s, disturbed and impaired calls (classic and WhatsApp), FDTT DL throughput > 5, 20 and 100 Mbit/s, FDTT UL throughput > 3, 10 and 20 Mbit/s, video TTFP ≥ 10 s and irritating playout |
| **Quality shortfall** | What averages, medians, 90th percentiles and the packet error ratio miss of their best score; not per test | Call setup time, POLQA, FDFS transfer times, FDTT P90 throughput, browsing time to 1 MB, interactivity packet error ratio and median RTT |

- **Reliable KPIs** lose their points as **Not completed (NQ)** or **Below the minimum** (the failed tests of Where to act and Sites to review), so the Most Reliable scoring shows only those two kinds.
- **A failed test counts in every KPI it misses,** each in its kind: a 1 Mbit/s download misses the 2, 5, 20 and 100 Mbit/s ratios.

#### Points lost per KPI

Per chosen operator, the reference included, the points it loses per KPI (maximum − points scored, per environment and in total), by category (those that lose most first), two operators side by side with red data bars and the **R**/**D** badges, closed by **Total points lost** and a note of each operator's total. In All Environments, each column holds its part, so the Total is that of **Where the points go**. It shares the location and **Operators** of the KPI GAP Profile and the Points Lost Map.

#### Points Lost Map

**Points Lost Map**, below the points lost per KPI of All Environments and of each environment, shows where each operator loses its scoring points.

- **Location and Operators:** shared with the KPI GAP Profile and points lost per KPI. Several operators show their maps side by side (the reference among them), each headed by its operator, large and in its colour.
- **Maps per:** **City**, **Region**, **Cluster** or **Postal Code** (disabled without data, such as Cluster without Clusters).
- **Zoom and larger view** as in [Larger view, zoom and images](#larger-view-zoom-and-images); choosing rows and areas in [Tips & shortcuts](#tips-shortcuts). Clicking a ranking row centres and zooms the map on its areas; colours stay while rows or areas are chosen (the others are dimmed), also when **Colour areas by** changes, so both colourings compare.

**National points.** The figures are the part of the operator's National loss in the tests of each place, so the places add up to the National points lost and a region with most of the tests carries most of them even when it scores best. They are not the score of the place on its own (see the [National & Country Areas Trends](#scoring-trends)); the note above each map and the **National points lost** column say so, also in the documents.

| **Rank by** | Ranks and colours by |
| --- | --- |
| **National points lost** (default) | The National points each place loses, so places measured most (London, the longest routes) tend to rank first |
| **Points lost per 1,000 tests** | Those points per 1,000 tests of the place (Voice calls and Data tests, not Speech samples), only for places with 500 tests or more. Disabled for results calculated before this version until calculated again |

The ranking shows both figures (hover **Per 1,000 tests** for the tests of the place), with the bars on the one chosen.

| **Colour areas by** (Maps per City) | Each area takes… |
| --- | --- |
| **Points of the city or route that loses most in each area** (default) | The whole points of the city or Connecting Roads route that loses most among those measured in it. A city or route belongs to every area holding at least 2% of its tests, so a whole route takes its colour and London colours every London area |
| **Points lost in each area by the city or route that loses most there** | What that city or route really loses in it: a route shows where along its way it loses, and London colours each small area with what it loses there. Not offered with **Points lost per 1,000 tests** (only the first, with the rate of each city or route), nor for results calculated before this version |

- **Type column** (All Environments, City maps): the environments where each city or route, and beside each area, loses points, most first (short names such as City or Roads; hover for the full name). Not per Region or Cluster, which hold every environment.
- **Map areas (per City):** the [Map Areas](workspace-config.md#map-areas) of the workspace or those shipped for the main markets (the UK **ITL3 areas**, NUTS3 level, provinces of Spain, counties of the USA), coloured yellow to red; any other country is one area, named in a note above the maps. Hover an area for its points, cities and routes. The ranking lists the cities (`City`, or `G_Level_4`) and routes (*Sheffield to Leeds*) that lose most with points and share. Sources and licences (such as the ONS ITL3 boundaries) are in `assets/map-areas/README.md`.
- **Per Cluster / Region:** the polygons of the workspace's **Clusters** or **Regions** dataset applied to the CDRs, ranked the same way. For your own clusters, import a Clusters GeoJSON in Workspace Management and apply it before calculating; the job keeps a simplified copy.

**How the points are placed:**

- Each KPI loses its maximum minus the points scored, shared among the tests that cause it: one per test that misses a ratio KPI (failed call, POLQA below 1.6, transfer below its threshold…), what each test misses the High threshold by for averages, medians and P90, and the packets lost for packet loss.
- Each test is placed by the City of its CDR row (a Connecting Roads route is a City value such as *Manchester to Sheffield*, with every test between both cities) and the map area containing its coordinates (kept in its CDR rows, see [Map Areas](workspace-config.md#map-areas)). The map uses the points of the selected scoring (Best Network or Most Reliable). Recalculate after adding Map Areas.

##### Maps per Postal Code

For the Saved Scorings calculated with **Postal Codes in the Points Lost Map** (Country Areas of Scoring Setup; off by default, to run when needed, such as once per quarter on the latest campaign). Their card says which map they use in **Postal Codes**; other Saved Scorings neither read nor keep postal codes.

- **Postal Codes map:** chooses among those of [Workspace Config → Map Areas](workspace-config.md#postal-codes): **Full postcodes** (default), **One point per place**, or **Own file** once the workspace has one. Another map is the same Saved Scoring: **Calculate** replaces its result, and a map drawn before with the same CDRs and methodology comes back at once. The note under the maps names the map.
- **Table and map:** **Postal Code**, **Type**, **National points lost**, **Per 1,000 tests** (postal codes with 100 tests or more) and **Share**, and the map coloured per postal code. The table lists the first 30; **Download all … postal codes (CSV)** saves every one (recorded in App Events).
- **Few tests per code** (some tens per operator and quarter in the UK): use it to rank and locate losses, not as a score per code.
- **Missing maps:** a calculation downloads the chosen map for the countries of its tests that lack it. When unavailable (failed download, no Own file), another map of the country stands in, or the copy shipped with the application (as for the United Kingdom), and a note says so. A country without any is named and its tests left out until its postal codes are downloaded or imported and the scoring calculated again.
- **In transfers:** the option and its map travel with the Favourite Scorings; with or without them it is the same filter, so the destination takes the option and map and draws its postal codes at the next calculation, without adding a filter. A filter keeps its option and map when the package does not bring them.

> [!NOTE]
> **The areas are approximate**, not official borders. They are worked out from the postal code points of GeoNames, so a test near a border can fall in the neighbouring code. With **One point per place**, codes that share their only point, usually in a city centre, are one area (`28070, 28071 +6 · Madrid`).

#### Points lost per Vendor, kind of site, site and stretch

The points lost of each test are also shared among the cells that served its start, from the [Vendor Mapping](workspace-management.md#vendor-mapping) with Network Inventories (`Vendor`, `Serving_Network`, `Serving_Host_Network`, `Serving_eMOCN_Scenario`, `Serving_Site_ID`). Each section has its own scope and **Operators**; **Not identified** gathers tests without a serving cell in the inventories.

| Section | What it shows |
| --- | --- |
| **Points lost per Vendor of the serving cell** | Per operator, the points lost on the cells of each RAN Vendor with their share of the points lost and of the tests, the environments, and the cities and routes that lose most |
| **Points lost per kind of serving site** | The same per network owning the site and, when another network hosts its RAN, *on* that network (Beacon, MORAN), NNS sites apart |
| **Points lost per RAN Vendor (host and vendor)** | For the multivendor analysis: **Host network** (`VF_Hosted`, `VMO2_Hosted`, `3UK_Hosted`; one cell for its Vendors, the network that loses most first), then its Vendors (`VF_Hosted_Ericsson`, `VMO2_Hosted_Nokia`, `3UK_Hosted_Huawei`…), with their share of points lost, calls and tests, points lost per 1,000 calls and tests (from 100), environments and worst cities and routes. Only Operators that receive a Vendor ([Multivendor Mappings](workspace-management.md#multivendor-mappings)) |
| **Points lost per site type (Legacy, eMOCN, NNS)** | The same per network owning the serving site with its eMOCN scenario (`VF_eMOCN_S1`, `3UK_eMOCN_S0_CWP`…), `<network>_NNS`, or `<network>_Legacy` (VF, 3UK and VMO2 for Vodafone, Three and Telefonica) |
| **Sites to review** | Per operator, up to 25 sites that lose most |
| **Connecting Roads: where along each route the points are** | A map per route with a circle per stretch of about 20 km |

- **Class of each call or test** (RAN Vendor, site type): that of all its serving cells (first, changed to and last), **MIX** when they differ (no Vendor for **MIX** and **Not identified**).
- **With the scoring split by Vendor:** each Vendor is scored on its own tests, so each operator's table holds every Vendor (no selector), the costliest first: **Points lost** (what it costs the operator, its own points lost weighted by its share of the tests) with **Share of points**, **Own scoring** (its points lost on its own tests, comparable between Vendors), share of tests and where it loses (Unknown and Mixed Vendors in grey). The rows add up to **All vendors (weighted by tests)**, close to but not always the points lost scored on all tests at once (scoring is not linear); for that exact figure use the Saved Scoring without the Vendor split and its RAN Vendor section. An operator without a Vendor (EE, or one left out of the Multivendor Mappings) has one row **All**.

**Sites to review:**

- **Columns:** network, Vendor, city or route, points lost, failed tests (calls and tests that missed the Reliable KPIs) and points lost in earlier campaigns.
- **Priority:** **High** with 1 point or more lost and losses on the site in an earlier campaign; **Medium** with one of the two; **Low** with neither.
- An operator none of whose serving cells is in the inventories has no sites; a note gives its points lost that cannot be assigned.
- **Site Area Map:** for users of Non-Qualified Calls, each site is a link to the [map of the site](non-qualified-calls.md#map-of-a-site) in a floating panel, with its NQ calls and those of the sites around it and the table of their `JOIN_ID`s. It navigates as the [map of a call](non-qualified-calls.md#map-of-the-call) (see [Tips & shortcuts](#tips-shortcuts)).

**Connecting Roads:** every chosen operator at once, two per row. **Route** chooses among the six worst routes of each (the worst first). The route is drawn on the map areas (ITL3 in the UK) with the measured cities named and a circle per stretch whose area and colour (yellow to red on the theme scale) tell its points lost; up to eight worst stretches are numbered with the nearest city (*14 km north-east of Leeds*) and listed with their main Vendor. The Route stretches slides draw the same map.

**Route maps** (Connecting Roads and *<Route>: where the points are*): choosing a stretch in the table (click, or <kbd>Enter</kbd>/<kbd>Space</kbd> on a focused row) zooms on it and rings its circle; again, or **Whole route**, shows the whole route.

**Shared rules:**

- Every **Operator** selector and list follows the order of the Operator Maps. The geography is that of the Saved Scoring: split it by Region (in the UK, the performance owners), City or route and choose it in the section's selector.
- **Linked selectors:** choosing a Vendor, Region or City in one section of Points Lost (Where the points go, per Vendor, kind of site, RAN Vendor, site type, Sites to review, Route stretches) chooses it in the others (a section without Vendors follows the Region or City). Split by Vendor, **Ericsson** is chosen by default.
- A share of the points lost well above the share of the tests is red.
- **Older results:** these sections need results calculated with this version from CDRs with serving cells, else a note asks to calculate again. RAN Vendor and site type need CDRs whose Vendor was mapped with this version; until then they ask to map the Vendor again and recalculate.

### Scoring Charts

The Scoring Charts tab compares the operators' points as bars and shows how the maximum is allocated:

- **Best Network / Most Reliable Network Scoring per Service:** total points with Data (below) and Voice stacked. Voice and Speech KPIs count as **Voice**, Data KPIs as **Data**, whatever the category names.
- **… per Category:** category contributions in each operator/context stack. **… per Category (Breakdown):** the operators side by side within each category.
- **Maximum score allocation donuts:** the configured environment, service and category maxima and shares (the maximum available, not earned scores).
- Titles and donuts follow the selected scoring. The Operator Mapping gives labels, order and colours; campaigns read year-quarter (**2026-Q1**) while stored names and CSV identifiers are unchanged. One Break down by level uses normal axis labels, several use separate header rows, and the Service and Category charts leave a gap between the bars of each operator or, when a level above Operator has several values (such as City), of each of its values.

**Many bars:** the three charts fit every bar in the card width at their ten-bar height, never scrolling sideways, so no first-level label is cut. More bars narrow the bars and gaps, shrink or turn totals 90°, make part labels a little smaller (turned, or left to the tooltip) and keep level labels one size in up to two lines, or turn them all 90° in a taller row. Zoom to read labels that still overlap.

### Country Areas

The Country Areas tab scores the whole country and each area of **Country Areas** ([Country Areas & Scoring Trends](#country-areas-scoring-trends)), whatever the area filters; its pills say **National** with the Operator and Vendor filters.

| Section | What it shows |
| --- | --- |
| **Scoring Nationwide** | First, the scoring of the whole country (its own calculation of every test), on a card across the panel with larger bars and text |
| **Scoring per City / Cluster / Region** | With 2 to 12 values, a card per area of the breakdown and per City on its own (with tests there): operators from the highest score, each a bar of Data (teal) and Voice (amber) points with rank, total and distance to the first (hover for points) |
| **Cities ranked** (**Cities and routes ranked**, Clusters, Regions) | Per chosen operator, every location of the latest campaign from its highest **Points %**, with its change since the previous campaign, Voice % and Data %, points lost and the Vendors that served its tests. **Country Areas** chooses the level (the largest by default; it heads the first column and names the notes) and **Group** the combination of the other levels |
| **Each operator against the reference per region** (city, city or route, cluster) | Per chosen operator other than the reference, its GAP in each location, overall, Voice and Data, in points of percentage of the points available, as bars left (behind) or right (ahead), the furthest behind first |

- **Split by Vendor:** the Nationwide card has a column per operator (Operator Maps order) and a row per Vendor (**All** first for operators without one such as EE, then by name, Mixed and Unknown), each cell with its bar, its position among the operators of the Vendor and its points behind the first; the per-area cards come in a set per Vendor (**Vendor: Ericsson**).
- **Order:** Nationwide, then Region, Cluster and City, also in the documents; with several campaigns, the latest one's set of cards. The title of each card names the campaign it scores (for example *Most Reliable Network Scoring per Region — 26-Q3*).
- **All Environments:** each card adds the environments measured there and scales them to the full maximum (1,000 points in NetCheck 2026), so a city measured only in Drive - City compares with the others as in the NetCheck per-city rankings; the note above the cards gives the maximum and its Voice and Data parts. A single environment shows its own points.
- **Older results:** a Saved Scoring calculated before is calculated again when opened; older results show a note.

### Scoring Trends

The Scoring Trends tab follows each operator's score over the campaigns or periods of the **Trends** block, on its areas ([Country Areas & Scoring Trends](#country-areas-scoring-trends)). With fewer than two campaigns or periods, it says how to get them.

**Best Network / Most Reliable Network Scoring Trend** (two campaigns or more):

- One line per operator ending in its name and latest score (the reference thicker), the score beside every other point (below it when too close to the one above), the latest campaign shaded.
- **With campaigns of its own** it is the **Scoring Trend Nationwide** (pill **National**): the National scoring of those campaigns or periods on the whole country, as a note says. **Otherwise** one series per combination of the other Break down by levels, chosen in its selector.

**Trends — National & Country Areas:**

- **Table:** the National scoring, each area of the breakdown, then the cities, each group's names in its own colour (as its chart titles) with a thick rule between groups. Per area, the operators from the highest score with their score in the latest campaign or period, change from the previous one and GAP to the best operator of the area (**Δ vs best**, the best tagged **Best**, whatever the GAP reference).
- **Charts:** one per area on the same scale, as tall as the table (labels tilted when needed), with pills, the score of every point and end scores kept apart. A double-click enlarges a chart or the table alone.
- An area not measured in the latest campaign or period is listed without a score; its chart shows the earlier ones.

### NNS Break-down

The NNS Break-down tab scores each city and the connecting roads over several campaigns, with the sites that serve them, reconciles them with the scoring of each Region (as Country Areas), scores the latest campaign by the kind of site that served each test and projects the points as the planned NNS sites roll out: the tables to project the scoring improvement of the NNS upgrade. It is **off by default**; switch it on in block **6 NNS Break-down**.

| Setting | Choices |
| --- | --- |
| **Campaigns** | **Latest 4 campaigns** (the default), another automatic choice or chosen campaigns, whatever the Campaign filter (the complete campaigns of each NR Mode: Weekly, Daily and Flex CDRs are left out) |
| **Regions** | The Regions it covers, such as Vendor A, VMO2 North and VMO2 South (it lists the Regions of the CDRs of its own campaigns, whatever the CDRs of the selection); none: every Region |
| **Connecting roads** | **Grouped by Region** (a row for the Roads and one for the Highway of each Region, the default) or **Each road on its own** |
| **Reference growth (%/year)** | How much the reference operator grows a year in the Projection sheet (**0.5 %** by default) |

- **Scored like the trends:** the CDRs of its campaigns with the filters of the scoring but Region, Cluster, City and Campaign, its methodology (By campaign: each campaign with its own) and GAP reference. **NSA vs SA** scores each NR Mode apart (an **NR Mode** selector in the tab).
- **Areas:** a test is in a city when its `G_Level_2` is City (the city is `G_Level_4`, its size `G_Level_3`: Big, Medium or Small Cities), else on a connecting road (`G_Level_3`: Roads or Highway). Each area is scored on its own tests, scaled to the full points as in Country Areas.
- **One Region per city:** the Region of a test is where it was measured, so a city near a Region border, or with tests of a wrong position (a GPS fix frozen elsewhere), would fall in two Regions. Each city belongs to the Region that holds most of its tests over the campaigns of the break-down, with all its tests; the connecting roads keep the Region of each test. The few tests of a city that Country Areas counts in another Region go to the adjustment of the Regions.
- **Scenario of a test:** the kind of site that served it, from the newest **Multivendor Mapping** of Workspace (such as the VF3 QGIS All Vendor table, its eMOCN Scenario; a site with an NNS cell is NNS); without one, or for a site it does not list, the `Serving_eMOCN_Scenario` of the CDR row. An NNS site carries the capacity of the **Master Grid** (its High/Med/Low config); the others their eMOCN scenario (S0, S1, S1_CWP…).
- **Master Grid:** the newest one uploaded in [Workspace Management](workspace-management.md#master-grid). A serving site is found by its own number or by the number of the site it pairs with: Vodafone sites by `Site ID`, `SiteRef2` (`<n>vf`) or `SITE ID + Pairing` (theirs or of a 3 site), 3 sites by `SITE ID + Pairing`, O2 sites by `SiteRef2` (`<n>o2`) or the number of the Vodafone site they share. Without one, the NNS sites have no capacity and no NNS site is planned (a warning says so); a new Master Grid calculates the NNS Break-down again.

**Cities and connecting roads** (one table per NR Mode):

- **Rows:** each Region, then its cities (big to small) and roads, each with a row per operator, from the highest points of the latest campaign (#1 first, then the smallest GAP).
- **Points:** Best Network or Most Reliable (the **Scoring** selector) of each campaign, with its tests, tinted by their share of the maximum points.
- **GAP to #1** (latest campaign): the points of the operator minus those of the operator with the most points in the area (**#1** on its row).
- **Weighted GAP to #1** (latest campaign): what the area adds to the GAP of its Region to the **#1 of the Region**, weighted as the methodology weighs the areas: its points in its environment and category (Data, Voice) times its share of the tests of the Region there, minus those of the #1 of the Region. Below it, the weight of the area in the Region and the same over every chosen Region (**all**).
- **Sites:** the serving sites of the tests of the latest campaign: **NNS sites** by capacity (High · Med · Low, plus those not in the Master Grid), the **eMOCN / other sites** by scenario, and the **Planned NNS**: the Keep sites among them, not NNS yet, that the Master Grid plans, by financial year (`Target Deployment FY`).

**GAP to #1 of each Region** (latest campaign): each Region, and all the chosen Regions, scored as Country Areas scores it (every test of the Region with its own Region), with the points of each operator and its GAP to the #1 of the Region; below, the weighted GAPs of its areas summed and the **adjustment** that closes them to that GAP (the scoring is not additive: the rates, medians and thresholds of a Region are not those of its areas).

**Latest campaign by city size and scenario:** each city size (and road type) with a row per scenario (NNS High, Medium and Low capacity, then each eMOCN scenario) and the operators side by side, each with its points and tests.

- **Export to Excel:** every table of every NR Mode with both scorings, its file name ending with the scoring chosen in the tab (`-nns-breakdown-best_network.xlsx` or `-nns-breakdown-most_reliable.xlsx`); **About** tells every column of every sheet and where it comes from.
  - **Areas:** each Region with its own scoring, then its areas, then its **Adjustment** row; each campaign under a band of its own colour with its tests, then its Best Network and its Most Reliable points, #1 and GAP to #1 of the area, weight in its Region and weighted GAPs to the #1 of the Region and of all the Regions. Filtered to a Region, its weighted GAPs plus its adjustment are its GAP in Country Areas.
  - **GAP Totals:** each Region and all the chosen Regions per campaign and scoring: points, #1, GAP to #1, weighted GAP of its areas, adjustment and weighted points of its areas.
  - **Sites:** every capacity, scenario and planned financial year.
  - **Scenarios:** the latest campaign by city size and scenario.
  - **Projection:** each area and operator of the latest campaign over the financial years the Master Grid plans: the share of NNS sites once the planned sites up to that year are NNS, and the points of the year before plus the rise of that share times the NNS points minus the area points (cumulative); the same by the share of tests served by those sites; the reference operator growing its points by **Reference growth** a year, and the GAPs to it. Areas with fewer than 30 NNS tests are not projected. It is not part of the PowerPoint and Word documents, so it has no Scoring Export Panels.
- **Cost:** it reads the CDRs of its campaigns (about as long as a scoring of them); the same CDRs, methodology, options and Master Grid are taken from the cache of the workspace.

### Methodology Impact

**Methodology Impact** scores the same tests with two methodologies, so every difference comes from the methodology and none from the network. It keeps the scope of the open Saved Scoring (NR Mode, filters, GAP reference) and follows the **Scoring**, **Environment** and **Operators** of the page; Break down by does not matter and every operator starts enabled.

**Choose what to compare:**

- **The methodologies of two campaigns:** **From campaign** and **To campaign** only choose the methodologies that apply to them (named in the selectors); the tests are those of the To campaign. It starts with the latest campaign and the nearest earlier one with another methodology. When both have the same, the tab says there is nothing to compare.
- **Two methodologies:** the tests of **Tests of the campaign** with any **First methodology** and **Second methodology** of the workspace.
- **NSA vs SA** Saved Scorings add **NR Mode** (one at a time); with **Same operator in NSA**, the reference is EE.
- The first methodology is **A**, the second **B**, and every difference is B − A.

**Calculation:** the first time in the background with its progress, from the Scoring History when it can, else from the CDR rows (maps always read the rows); then kept in the workspace cache until its CDRs, methodologies, filters or Operator Maps change. On failure the tab says why and **Calculate again** retries; if only the maps fail, the rest shows. App Events register each request, calculation, failure and export.

| Panel | What it shows |
| --- | --- |
| **The comparison** | A and B with the tests they score, a headline of how much the scoring moves, and cards (who gains and loses, positions, sides changed against the reference, the category and KPI that move most, where it hits most, areas with a new leader) linking to each panel |
| **What changed in the methodology** | How many KPIs are new, removed, with other points, thresholds, formula or filters, score mapping or definition, or the same (**click a count** to see only those; again to undo); points of each category and environment in A and B; every KPI that changes, per category, with each changed value side by side and its environments; the general settings. KPIs keep their identity by code and name, so a renamed KPI is changed, not removed and added |
| **Scoring of each operator** | Difference, points and position in A and B (All Environments, then per environment); **Who is ahead of whom** (both rankings joined, crossing lines are position changes); **Why each operator moves** (points moved between KPIs at the same score, other thresholds, formula or filters, new and removed KPIs) |
| **Impact per category** | A card per category that moves, most first: per operator a bar for A and for B, each as long as the category maximum in that methodology, and the difference; unaffected categories named |
| **KPIs affected** | The KPIs that give and take most points from each operator, and every KPI with each operator's difference and points in A and B (hover for value and score) |
| **Maps** | **Map per** City and route, Region, Cluster, map area or Postal Code; **Measure**: **National points** (adding up to the operator's difference), **National points per 1,000 tests** or **Scoring of the area**. A map per operator, with how many areas are better and worse with B and those that gain and lose most |
| **Impact per area** | Each Region, Cluster or City with each operator's difference and scoring in A and B, most moved first, and its leader, marking leader changes; on the whole country, All Environments scaled as in Country Areas |
| **GAP** | Each operator's GAP to the reference with A and B as two bars from the reference and how much it moves, then per category and KPI; **Changes side** marks an operator that goes from ahead to behind or back |
| **Points Lost** | Points lost with A and B by [kind](#kinds-of-points-lost), then per category and KPI; more points lost in red |

- **Colours:** B − A, green gains and red losses, stronger when larger, with A and B below. A KPI or category one methodology lacks counts as **none** there, so differences add up. Long lists expand with **Show all N**; maps zoom like the others.
- **Export to CSV** (every value of every panel and environment, maps included), **Export to PowerPoint** and **Export to Word** (the panels [Scoring Export Panels](workspace-config.md#scoring-export-panels) exports, for the Environment and Operators of the page, map areas of up to four operators per slide), in the theme of the page. These panels are only in this tab's documents, not in other Scoring documents or [Reporting](reporting.md).

### Incomplete coverage and achievable scoring

The pale yellow **Calculation notes** card lists the affected combinations, missing KPIs and the **exact maximum achievable score** without their contributions (for example **VF_UK / Samsung / Q1: maximum 583.2645 of 650 points**; each campaign can differ).

> [!WARNING]
> **Missing points are not redistributed.** An incomplete result keeps the original weights and configured benchmark maximum. Available contributions are not scaled up to a complete score.

- Incomplete values are **bold red with `*`**, unavailable ones **N/A*** in the same style; Total KPI GAP carries `*` when a contribution is missing or partial.
- All Environments GAP uses valid environment contributions common to both sides (a subset is partial, none is unavailable). Tooltips and PowerPoint slide notes explain partial coverage.

**Environments without results in any series are scaled.** When the filters leave an environment without results for every operator and series (City = London only covers Drive - City):

- The Combined scores scale the environments with results to the full maximum: the empty one gets 0 and the others share its points in proportion, the same for every operator, so GAPs stay comparable. Scaled values are not marked incomplete.
- An orange **Scaled results** card (and the first page of the documents) names the environments and factor; with a methodology per campaign, once, or once per methodology with its campaigns when they scale differently. The *Maximum score per environment* donuts strike through the configured points beside those allocated.
- Every All Environments view counts in these scaled points, also in the documents; each environment on its own keeps its own.
- An environment with results in any series is never scaled; series without it keep their partial score and notes. Saved results are scaled when opened, without recalculating.

**All Environments raw KPI values** come from pooled source rows, not averages of environment values (older results show N/A until recalculated); weighted points still sum the separate environment contributions.

## Excluded Calls

Keep lists of calls that every scoring of the workspace leaves out, such as the calls of a faulty test phone.

- **Where:** the **Excluded Calls** panel, between the Scoring & GAP Analysis panel and Manage Favourite Scorings (and after it in the section bar and menus). Its header counts the lists switched on and their calls.
- **What it leaves out:** the calls of the lists from every scoring of the workspace (Saved Scorings with their Country Areas, Scoring Trends and Points Lost, the scoring reports and the reports of [Reporting](reporting.md)).
- **How a call is identified:** by its NetCheck **JOIN_ID**; its rows are left out of the CDRs of the list (the Voice call with its Speech samples, or the Data test).

| Action | How |
| --- | --- |
| Import a list | **Import Excluded Calls (CSV/Excel)**, then **Choose File**: CSV (comma, semicolon or tab), TXT or Excel with a **JOIN_ID** column (**JOINT_ID** or **Call Key** too) and optionally **Reason** (or Comment or Note); a single column without header is a list of JOIN_IDs. The dialog counts the JOIN_IDs read and the repeated or empty ones left out. Give a **Name** (the file name by default), a **Reason** and its **CDRs**. **Download Template** gives the columns. Up to 100,000 calls per list |
| Choose its CDRs | Without CDRs (**All CDRs**), every CDR of the workspace, also those processed later. Assigned to CDRs, those and, for a Voice or Speech CDR, the Speech or Voice CDR of the same campaign, stage and NR Mode (listed with a **+**). CDRs are kept by file name, so they follow the list to other workspaces |
| Switch it on or off | **On**: off, it keeps its calls but leaves nothing out, to compare scorings with and without them |
| Edit, download or delete | **✎** name, reason and CDRs (import another list to change its calls), **⇩** its calls (CSV), **🗑** delete after confirmation |

- **Finding the calls:** **Found in the CDRs** gives the calls and rows found (per CDR under **By CDR**); **N not found** downloads the JOIN_IDs found nowhere. They are found in the background, one reading per CDR, when a list is imported or changed and when a CDR is processed (**Scoring History indexing** says *Finding the Excluded Calls in <CDR>*); meanwhile the panel says *Finding the calls in N CDRs…* and the scorings leave the calls out all the same.
- **Effect:** the scorings follow the lists at once: the Saved Scorings of the CDRs whose calls change are calculated again when opened (Favourite Scorings also while idle); the others keep their results. Result warnings, and the notes of the PowerPoint slides, name the lists, calls and rows left out (*Excluded Calls: 4 calls (20 CDR rows) are left out of this scoring by the list “Faulty test phone Q3”.*). In [NQ Prioritization](non-qualified-calls.md#nq-prioritization), an excluded call loses no points (Excluded from Scoring).
- **Rights:** everyone with the workspace sees the lists; those who can edit the Scoring Methodologies (editors and administrators) import, change and delete them, each action recorded in App Events.
- **Storage and transfers:** the **Scoring Exclusion Lists**, **Scoring Excluded Calls** and **Scoring Exclusion Matches** tables of Database Management; transferred as described in [Save, export and backup are different](#save-export-and-backup-are-different).

## Methodology

A methodology contains the complete environment, KPI, weighting, threshold and priority setup. Edit it in **Workspace Config → Scoring & GAP Analysis Setup** (or from the **Scoring Methodologies** link of [Scoring Setup](#scoring-methodology)). The [aggregation hierarchy](#aggregation-hierarchy) is not part of it.

### Named methodologies and portable JSON

Select a methodology, or prepare another with **Create Methodology** / **Duplicate Methodology**. Its **Name** identifies it; **Methodology title** is an optional description kept in transfers.

- **Save Methodology,** from the toolbar or any panel (**Methodology Environments**: environments, allocations, KPI specifications and thresholds; **Methodology KPIs Priorities for GAP analysis**: the priority order), commits every pending setting together; the status above the panels says saved or pending.
- **Set Default** chooses the methodology offered first for new calculations (selecting one does not); each calculation can use another. The default cannot be deleted until another is default.
- **Deleting:** only admins, super-admins and the user who created or imported it; for others **Delete Methodology** is disabled and a save or import that would remove it is refused.
- **Saved results** keep their captured rules: opened after an edit they are calculated with the new rules; after a deletion they are shown as they were.

#### Methodologies by campaign

**Applies to campaigns** gives the campaigns a methodology was made for: choose its first in **From** and last in **To** among the quarters of the workspace's campaigns (**No start (every earlier campaign)** and **No end (every later campaign)** leave an end open), then **Save Methodology**.

- Campaigns of two methodologies cannot overlap. With no start and no end it is tied to no campaign. Example: **NetCheck 2026** No start to 2026-Q2, **NetCheck 2026-Q3** 2026-Q3 to No end.
- **By campaign** scores each campaign (by year and quarter) with its methodology and the others with the default one; with a single methodology, every campaign uses it. Each campaign totals the full score of its methodology, and a KPI only some have (TikTok from 2026-Q3) appears only in their campaigns. See [Campaign Comparison](#campaign-comparison).
- The campaigns travel with the methodology in exports, transfers and backups.

#### Save versus export

- **Export Methodology (JSON)** downloads the selected saved methodology (save pending edits first). **Import Methodology (JSON)** takes one or a collection and merges by methodology ID: it adds new IDs and replaces matching ones after confirmation, keeping the other methodologies and the default; duplicate names with different IDs are rejected.
- **Admin Import / Transfer and backup restores** replace the methodologies with the same ID (or their original ID, or else the same name), add the others and keep those only the workspace has and its default (see [Matching and creators](administrator-config.md#matching-and-creators)).
- Methodologies whose campaigns overlap are refused, so nothing is imported until one changes.
- Other saves, exports and backups: [Save, export and backup are different](#save-export-and-backup-are-different). The JSON format: [Portable JSON reference](#portable-json-reference).

> [!TIP]
> Duplicate a methodology before revising a benchmark, and export or back up the collection before replacing it through Admin.

### Configure environments

An environment defines **which CDR rows to include** and **how many points its KPIs can contribute**, in the selected methodology.

**Source-row matching** (**CDR filters**): **G_Level_1** (required, such as Drive) and **G_Level_2** (optional, such as City). With Drive and City only rows matching **both** are included; an empty G_Level_2 includes every second-level value. These source values differ from the Region/City filters, and renaming an environment does not change its rule.

> [!WARNING]
> **Environment source rules cannot overlap.** Two environments cannot select the same first/second-level combination. An unrestricted second level also conflicts with a narrower environment using the same first level.

- Choices come from the ready CDR catalogues of the workspace; saved values stay selectable when absent. Configuration exports carry the values; the destination offers those of its own CDRs.
- **Create Environment:** enter its name, reference environment, points and source filters; it copies the KPI thresholds and relative shares of the reference. Review them, then **Save Methodology**.
- **Rename Environment** keeps KPI contexts, weights, thresholds and filters; historical numbers are unchanged, and supported views can show the new name. **Delete Environment** removes its contexts from the draft; keep at least one environment and a positive allocation. Names are unique ignoring case; **Combined** is reserved.
- **Allocation:** **Points** sets its absolute allocation; **Weight (%)** changes its share keeping the grand total and redistributing the others proportionally; **Distribute points keeping percentages** allocates a total with a reference environment's relative KPI shares. Distribution changes points only, not formulas or thresholds; relative shares are kept even at zero points.

> [!WARNING]
> **Copied thresholds need review for their new context.** The initial Walk environment has zero points and City-derived rules. Validate it before assigning benchmark points.

### Editing, replacing, adding and removing KPIs

#### Edit a definition

1. Select the environment and expand the pastel red **KPI Definitions, Scoring & Thresholds** subpanel.
2. Edit the definition and its environment-specific settings.
3. Save the methodology, then calculate or recalculate.

| Setting | What it controls |
| --- | --- |
| **Code** | Stable identity and priority references |
| **KPI / Category** | Display labels and grouping |
| **Source** | Data, Voice or Speech CDR rows |
| **Formula / filters** | Measurement and eligible source rows |
| **Direction** | Whether higher or lower measurements are better |
| **Mapping** | Linear, Quadratic or Smooth curve interpolation |
| **KPI Type** | Reliable / Diff; only decides which KPIs form the Most Reliable scoring (not the formula, mapping or GAP) |
| **Max points / weight** | The KPI's contribution to the environment in Best Network |
| **Most Reliable points** | Its maximum in the Most Reliable scoring; editable on Reliable KPIs only |
| **Thresholds / score anchors** | Measurement boundaries and the normalized score at each |

- **Calculation basis** is read-only, derived from the formula; it does not set the denominator.
- **Points** sets a KPI's absolute maximum; **Weight (%)** its environment share (the total stays, other KPIs adjust). **Global weight** (read-only) is its points over the total of all environments. Category totals follow; zero points keep the definition without a contribution.

#### Add, move, replace or remove

- **Category controls** move whole categories or insert one below; **KPI row controls** insert a definition below, move it within its category or delete it.
- **To replace a KPI,** revise its label, formula, filters, source, thresholds and points. A replacement added as a new row needs the old one removed, so both are not counted. Example: replace `PCT90(Mean_Data_Rate)` with `AVG(Mean_Data_Rate)`, rename it to mean throughput, review its thresholds and keep or change its FDTT/DL/Completed filters intentionally.
- **Codes** stay when rows move; new KPIs take the next unused K number and deleted codes are not recycled. Renaming a code in the editor remaps its priority reference; in hand-edited JSON update `gap_priority` too.

#### Priorities

The priority editor moves a KPI up/down, to the first/last or to a given position, with its category visible.

> [!NOTE]
> **GAP priorities are saved settings.** They do not change the display order of the GAP tables (see [GAP Analysis](#gap-analysis)).

#### Supported expression language and limits

| Operation | Example |
| --- | --- |
| Average | `AVG(Call_Setup_Time)` |
| Median | `MEDIAN(field)` |
| 90th percentile | `PCT90(Mean_Data_Rate)` |
| Sum / count | `SUM(field)` / `COUNT(field)` |
| Supported conditional ratio | `100 * SUM(Call_Status == "Completed") / COUNT(Call_Status)` |

- **Conditions** support the implemented comparisons, `AND`, `CONTAINS(...)` and `IS NOT NULL`.
- **Filters** are JSON objects whose values select the permitted source values of each field:

```json
{
  "Session_Type": ["CALL", "MultiRAB CALL"],
  "Call_Status": ["Completed", "Dropped"]
}
```

- **Interactivity packet-error formula:** explicit IFNULL for lost, discarded, corrupted and unsent packets (missing optional components count as zero). `Packets_Sent` is required and its sum must be positive; missing or zero gives N/A.

> [!CAUTION]
> **Formulas use a supported expression allowlist.** Arbitrary Python, SQL or Tableau expressions are not executed. Other absent source fields do not become optional because the packet-loss formula supports IFNULL.

**Limits:** **256 KPIs**, **32 environments** per methodology and **64 methodologies** per workspace. New fields or unsupported operations require engine support, not just a JSON edit.

### Most Reliable Network scoring

NetCheck publishes two rankings: **Best Network** rates every KPI; **Most Reliable** only the reliability KPIs (marked `*` in the NetCheck reports, KPI Type **Reliable**), with its own maximum points. Each KPI keeps its normalized score; only its maximum changes.

| | Best Network | Most Reliable |
| --- | --- | --- |
| KPIs | Every KPI with Max points | Only KPIs whose **KPI Type** is **Reliable** |
| Points of a KPI | Normalized score × Max points | Normalized score × Most Reliable points |
| Thresholds, anchors, mapping | The methodology's | The same |
| GAP | Compared − reference Best Network points | Compared − reference Most Reliable points |

#### Configure it

1. In **Workspace Config → Scoring & GAP Analysis Setup**, open the methodology.
2. In **KPI Definitions, Scoring & Thresholds**, set **Type** to **Reliable** for its KPIs (NetCheck 2026 already does) and enter their **Most Reliable points** in each environment (see [Most Reliable reference points](#most-reliable-reference-points)). The line above the table counts the Reliable KPIs and their points in the selected and all environments, and warns about Reliable KPIs without points.
3. **Save Methodology**, then calculate or recalculate.

- **Part of the methodology:** changing these points gives it a new identity, so the Saved Scorings using it are calculated again when opened. The results are derived from the saved KPI scores, without reading the CDRs again.
- New environments and KPIs start without Most Reliable points; a KPI that is not Reliable never takes part (its points are dropped on save).
- **Rounding:** when an environment's Most Reliable total is within 0.1 points of its Best Network total (650.02 for 650), its points are scaled to match exactly.

> [!NOTE]
> **Environments without Most Reliable points contribute nothing to it.** The Most Reliable maximum of an environment is the sum of its KPIs' Most Reliable points; All Environments adds them, and [environments without results are scaled](#incomplete-coverage-and-achievable-scoring) as in Best Network.

## Scoring History

The **Scoring History** keeps, in the workspace database, the components of every scoring KPI of every ready Data, Voice and Speech CDR, so a calculation does not read the CDR rows again.

- **What it keeps:** per group of tests (start day, campaign, operator, vendor, environment, Region, Cluster and every City) and KPI of the workspace methodologies, what the KPI needs over any groups: sums and counts, and a mergeable sketch of medians and 90th percentiles (within a quarter of a percent). Never scores or points, so any methodology, period (days to years, campaigns) and area can be scored from it.
- **When it is filled** (**Scoring History indexing** in the background tasks card, after other background work): when a CDR finishes processing, when the workspace opens (for CDRs it lacks) and after two minutes without use (self-refreshing pages do not count). Processing CDRs calculates no scoring on its own.
- **Each CDR is read once,** and again only when processed again (or its Vendor, Region or Cluster mapping changes), when a methodology adds a KPI it has not indexed, or when an [Excluded Calls](#excluded-calls) list affecting it changes. The history leaves out the calls of the lists switched on, so a CDR is indexed once they are found in it.
- **Before it is ready:** a calculation reads the CDR rows and says why (*(from the CDR rows: the Scoring History is still indexing 3 of its 18 CDRs)*, or *the Excluded Calls are still being found in 2 of its 18 CDRs*).
- **CDR identity:** the SHA-256 of its whole source file (about half a second per GB, kept until the file changes, also when it moves with a renamed or duplicated workspace, an import or a transfer) and its processing signature, never its name or ID, so renaming, reordering IDs or transferring keeps the history. A deleted CDR's history stays as a record; a reprocessed CDR replaces it. Each source records its stage, campaigns and days, so a Final CDR supersedes the Daily and Weekly CDRs it contains.
- **Calculated in seconds from it,** with the National & Country Areas Trends (from the CDRs of their own campaigns), when all its CDRs are indexed at their current processing, **Break down by** uses only Operator, Vendor, Region, Cluster, City, Campaign or Dataset Type, and its filters are only Region, Cluster, City, Operator, Vendor, Operator_Vendor or Campaign. Any other job reads the CDR rows.

**The Points Lost Map** needs the rows of each test, so it is drawn next in a job of its own (**Points Lost Map #N**); the results say *Preparing the Points Lost Map…* and update themselves.

- **Queue:** after the calculations waiting, giving way after each CDR or group of tests to work queued before it; the Saved Scoring being looked at goes first.
- **Own processes,** so the application keeps answering and gets its memory back: each CDR type is read at once from the [columnar copies](workspace-management.md#columnar-copy-of-the-cdrs) and every group of tests mapped at once (each KPI weighs every test once); per methodology, Data in one process and Voice and Speech in another, up to four at a time, most tests first, joined in CDR type order (the same map as drawn one after the other). 9 campaigns with a methodology per campaign take about 10 to 12 seconds. It reads only what the map needs from the rows, without scoring again.
- **Its card:** progress bar and step (*CDR 3 of 18*, then the CDR type and KPI, and the methodology), and the time left once it has advanced enough.
- **Stop** ends it at once; scores, tables and charts stay and the results say the map was stopped. It is drawn again after three minutes without use (stopped maps of the open workspace one after another, logged in App Events).

**Shared calculations:**

- The National & Country Areas Trends and the Points Lost Map of each methodology are cached in `.cache/scoring` of the workspace (most recently used, up to 1 GB). Any Saved Scoring with the same CDRs and processing, methodology, options, Operator Maps and Map Areas reuses them; those sharing their Scoring Trends (*All available campaigns*) calculate them once; with a methodology per campaign each campaign keeps its map (*Latest 2 campaigns* takes those of *Latest campaign* and *Previous campaign*), and each methodology reads only the CDRs of its campaigns. A map drawn before is added as soon as the scores are saved.
- **Idle calculation:** after three minutes without use, the Favourite Scorings of the open workspace whose result no longer matches their CDRs, methodology or Operator Maps (such as *Latest campaign* after a new campaign), or that have none, are calculated one after another with their maps (App Events: calculations of `system`).
- **What makes them recalculate:** a change of CDR, methodology, Operator Maps, Map Areas or application version.

**Where it is:** the **Scoring History**, **Scoring History Sources** and **Scoring History Files** tables of Database Management, in the workspace database, so it travels with workspace exports, transfers and database backups. It has no export of its own: the application rebuilds it from the CDRs.

## Persistence and exports

Export the results as CSV, images, PowerPoint or Word, and know what each save, export and backup keeps.

### Results exports

- **Export to CSV** above the Scoring table or the GAP table: the table shown (expanded results with category subtotals and totals, or expanded GAP results and their numeric fields) of the selected Saved Scoring, scoring and environment.
- **Images:** the download and screenshot buttons of each card, chart and table (see [Larger view, zoom and images](#larger-view-zoom-and-images)).
- **Report (PPT/Word) → Export this scoring:** the selected Saved Scoring as calculated, with editable tables and charts, covers and environment transitions, without the editor. Its dialog (**Export Selected Scoring Report**) asks for the scorings (**Best Network**, and **Most Reliable** when it has it), the environments (**All Environments** and each one; Best Network and All Environments ticked), **Export All Operators in Focus panels** (off by default) and PowerPoint or Word. Only the exportable panels of [Scoring Export Panels](workspace-config.md#scoring-export-panels) are included.
- **Report (PPT/Word) → Custom report…:** the [report editor](#report-scenarios) with one scenario that takes the CDRs, NR Mode, filters, Break down by, Country Areas & Scoring Trends, GAP reference, methodology and theme of the page, and only chooses its content (scorings, environments and sections, remembered for the next time); no saved configurations, theme or JSON files. The reports of [Reporting](reporting.md) keep their own filters.
- **Methodology Impact** has its own [exports](#methodology-impact).
- **NNS Break-down → Export to Excel:** its tables as an Excel workbook (see [NNS Break-down](#nns-break-down)).
- A progress dialog stays open while a document is generated.

**Word** documents (and the PowerPoint, which ends with the closing slide) are composed as the Scoring section of a report of [Reporting](reporting.md#how-a-report-is-composed): portrait pages rendered exactly as the PowerPoint with LibreOffice (in the Docker image), under the title of each scoring and environment. Without LibreOffice, one page per slide with the tables and charts rebuilt.

**CSV:**

- Exports use the saved results without recalculating; both buttons export the selected Saved Scoring. They keep stored names, numeric values and the schema, with a `cluster` column after `region` for results split by Cluster.
- The Most Reliable CSV has the same columns with its points (`scoring=most_reliable` in the export address).
- Category/final GAP aggregates remain valid-KPI means; the **Total KPI GAP** footer is a web/PowerPoint display total that does not redefine them. `gap_partial` and `gap_environments` identify partial coverage.

### Report scenarios

The report editor (from **Custom report…** or the Scoring section of [Reporting](reporting.md)) builds a report of one or more **scenarios**, in order: for example *National*, then *London*, then the *Main Cities*, then by Vendor.

- **Up to 20,** reordered with **↑** and **↓**, duplicated and removed.
- **Shared by every scenario:** the CDRs, NR Mode, methodology and GAP reference of the strip.
- **Own to each:** its **filters** (Operator, Operator_Vendor, Vendor_Operator, Vendor, Region, Cluster, City with **Main Cities**, Campaign), **Break down by** levels and Country Areas & Scoring Trends.
- **Filter lists:** a search box and **Select All / None** for the listed values; a list closes on a click outside or when another opens. **All** keeps no restriction, so later values (a new Operator) are included; **Main Cities** uses the workspace list when generated. Values stay editable with either checked, and changing one keeps exactly the values checked. A closed list shows one value by name or a count (`2/4 selected`, `Main Cities (5/12)`; hover for the values). Campaigns show with the [Campaign Maps](workspace-config.md#campaign-maps).
- **Country Areas & Scoring Trends** as in the [strip](#country-areas-scoring-trends), always included and on the whole country (also for scenarios saved without it). Its trend campaigns also offer **Same as the scenario** and **Chosen campaigns** (scenarios saved before keep All available campaigns); the automatic ones are resolved at each report.
- **Generating:** each scenario reuses its Saved Scoring when up to date or calculates it, so the first time can take longer. A Break down by level with a single value (one campaign, one city) splits nothing and is left out, as in every chart, table and document of the module.
- **Differences highlighted:** with several scenarios, each setting whose value is not the same in all (a filter, level, Scoring Trends, scoring, environments or option) is highlighted in amber, following every change.

**Content of each scenario,** for each scoring (**Best Network** and **Most Reliable Network**, each can be left out):

- **Environments:** **All Environments only** (default) or All Environments and each environment.
- **Panels** of each results tab, all on by default except **Show KPI values** and **Show GAP values** of the Scoring Tables; the Summary names *Standings* and *The route that loses most*, and Points Lost includes the City / Region maps (by points and per 1,000 tests) and the Postal Code map (Saved Scorings with Postal Codes).
- The editor lists only the panels the workspace exports ([Scoring Export Panels](workspace-config.md#scoring-export-panels)), those showing the Focus operators tagged **Focus**. **Export All Operators in Focus panels**, beside the editor title, shows every operator in them; it is saved with the configuration (off in those saved before) and is also an option of the reports of [Reporting](reporting.md).
- **Older configurations** saved before the Summary, Country Areas (formerly Locations), Scoring Trends and Points Lost groups keep their choices: cards and the Scoring Trend follow the former Scoring Charts options, the map the former GAP Analysis option and the points lost per KPI the former KPI GAP Profile option.

**Structure of the document:** the cover lists the scenarios. With several, each opens with its transition (01 National, 02 London…, with its NR Mode and the filters choosing part of the country or operators), then each scoring (1.1 Best Network Scoring, 1.2 Most Reliable Network Scoring) and environment block (1.1.1…) has its own, and subtitles name the scenario and scoring. With one scenario, scorings are 01, 02 and environments 1.1, 1.2…. With **All Environments only**, subtitles omit it. **Show KPI values** adds a **Value** column before each Score of the Breakdown tables.

**Theme:** the editor's **Theme** selector (see [Choose a theme](#choose-a-theme)); a saved configuration keeps its theme, and Default takes the page's.

**Saved configurations:**

- The editor opens with the scenarios of the last report generated (remembered when **Generate PowerPoint** or **Generate Word** is pressed, in any later session).
- **Selector:** names the saved configuration (or **Default**) whose scenarios are shown, or **<Not saved configuration>**, following every change; choosing one loads it at once. **Default** is one scenario with the filters and levels of the selected Saved Scoring plus **Campaign** (unless there is one campaign); it is always listed, cannot be deleted or used as a name.
- **Unsaved changes:** choosing another asks first: **Cancel** keeps them, **Discard changes** loads it, **Save as…** saves them first.
- The toolbar saves (**Save as…**) and deletes **named configurations** of the workspace and exports or imports them as JSON. Only admins, super-admins and the user who saved one (or imported it, when its creator is not a user here) delete it; for others **Delete** is disabled.

### What is in the PowerPoint?

Each scenario has a **Best Network Scoring** section and, when the result has Most Reliable points, a **Most Reliable Network Scoring** section. Each block follows the order of the results tabs (Campaign Comparison at its end) with the panels chosen in the scenario that [Scoring Export Panels](workspace-config.md#scoring-export-panels) exports. Slide notes carry the notes of that scoring.

**Operators of each panel:** every operator, or the **Focus operators** (every operator when none of the results is one; the reference when it is one). By default the Focus operators are used in Where to act (both), the places ranked and the route, Campaign Comparison, the locations ranked and *<operator> against <reference> per <location>*, the individual GAP comparisons, *GAP by part*, the KPI GAP Profile, the points lost per KPI, the points-lost maps, per Vendor, kind of site, RAN Vendor and site type, *Sites to review* and *Route stretches*; the other slides show every operator. **Export All Operators in Focus panels** shows every operator in all of them. Choices made on the page are kept, except in the route, the individual GAP comparisons and Campaign Comparison.

**What the slides add to the page:**

- **Summary:** after the scoring cover. *Where to act* (both) for the operator chosen on the page, else each Focus operator (the reference when it is one; every operator but the reference without them). *Standings*, *Position — per environment*, *Biggest levers — vs <reference>*, the places ranked (18 per slide, *(1 of 2)*…) and *<Route>: where the points are* on one slide.
- **Several operators per slide** (Position per environment, Biggest levers, GAP by part, Points Lost per Vendor, kind of site, RAN Vendor and site type): up to three side by side, four in two rows of two, five or six in two rows of three; more share slides of four, never one alone.
- **Latest campaign only:** KPI GAP Profile, Points Lost, Points lost per KPI, per City, per Vendor and per kind of site, Sites to review (High priority first) and Route stretches (the two worst routes of each Focus operator).
- **Country Areas:** for every level from the largest (each combination of the other levels), *<Regions> ranked* and *<operator> against <reference> per <region>* for each Focus operator (up to four). Per City / Cluster / Region: a note with the maximum points and up to 12 cards of the latest campaign.
- **Scoring Trends:** the Scoring Trend (per combination of the other levels, up to six, without trend campaigns of its own) and the National & Country Areas Trends table (six areas per slide, Δ vs with two or more campaigns), each environment block its own with **All Environments and each environment**.
- **GAP Analysis:** All Operators, then each Focus operator, *GAP by part — vs <reference>*, and the KPI GAP Profile of two Focus operators per slide for each combination of the other levels (up to twelve; the latest campaign's when there are more), its note naming the operators in their colour and totals in bold. GAP tables follow the Scoring Tables GAP visibility and placement; individual slides add the Priority arrow, mean KPI GAP and column-averaged total; every GAP table has its column totals and its colour scale on one line under it, filling the slide height with the largest text that fits (KPIs wider when GAP columns are few).
- **Points Lost:** *Points Lost — where the points go* (with what each kind counts and its KPIs), the points lost per KPI (reference included when a Focus operator), then **Points Lost per City** per operator chosen on the page with the KPI GAP Profile (else per Focus operator): headed by the operator, its figures in National points, the map coloured as the page by default with the worst cities and routes labelled once over the grey outline of their countries, and up to 30 places as bars with their environments and share. Each is followed by **Points Lost per City, per 1,000 tests** (places with 500 tests or more; not for older results). Workspaces with Clusters or Region polygons add **Points Lost per Cluster** or **per Region** slides with theirs; a single exported environment gets its own maps; without Map Areas, cities are bubbles over the test locations. Every table closes with its total row.
- **Campaign Comparison:** the Focus operators (every operator without them, whatever the page), up to eight operator and level combinations, two per slide.
- **Details:** each operator's rule under the table headers spans its campaigns; the names at the end of the Scoring Trend lines stand apart (a line ending early is named where clearest); Campaign Comparison names each operator in its colour over a rule of its colour.

**Titles, covers and transitions:**

- **Slide titles** follow the [theme](#choose-a-theme), the part that tells consecutive slides apart in bold and in its accent: the focus (*Best Network Scoring **per City***) or what follows the dash (*GAP Analysis — **3 vs EE***). **Subtitles** name the scoring, environment (*Most Reliable Network — Drive - City*), area, operators and vendors in bold, smaller when they would not fit on one line.
- **Covers and transitions** use the Vodafone-Three red of `Template_VodafoneThree.pptx` with the Ericsson mark in outline behind and the Vodafone-Three and Ericsson logos top right. Covers use 54/24 pt title/subtitle and transitions 40/20 pt in every module; the subtitle starts below the room of two title lines; titles wider than the slide shrink to one line. Transitions show their counter (01, 02…; 2.1, 2.1.1…). A scoring cover or transition has the NR Mode as subtitle and, under the layout line, the **Campaigns**, Break down by and each filter, white labels with **bold yellow values** (long lists can be shortened visually only).

### Dense-chart options

- **Scoring per Service** and **per Category** are split by the export above 20 bars, keeping complete category groups and a common Best Network scale, and the bars of each operator together (3, EE and Vodafone first), or of each value of a level above Operator (every operator and campaign of a City); they are divided by the next level only when they do not fit.
- **Scoring per Category (Breakdown)** keeps every category on one slide up to 50 bars; above, it spreads them over as few slides as possible with similar numbers of bars (*Page 1 of 2*), in PowerPoint and Word.
- **Labels:** smaller integers above 40 bars, hidden above 70; small stacked segments may omit labels, whose values stay in the editable chart.

> [!TIP]
> Narrow filters or split charts when many combinations make labels too small. Dense tables keep their combinations together, so reducing the scope also improves table readability.

### Save, export and backup are different

| Element | Kept, exported or transferred by |
| --- | --- |
| **Methodologies** (with their campaigns) | **Save Methodology** (workspace database), **Export / Import Methodology (JSON)** (see [Save versus export](#save-versus-export)), Admin → Import / Export → **Scoring & GAP Analysis Methodologies** (the collection and its default), configuration backup / restore |
| **Favourite Scorings** | **Scoring & GAP Favourite Scorings** element of Admin's Import / Export / Transfer, Full Workspace transfers and backups: without results or the local CDR selection, with their name and order. Each finds its CDRs by the SHA-256 of their files (or, with an automatic Campaign choice, takes those it stands for) and waits until they are processed there |
| **Report editor configurations** | **Scoring & GAP Report Templates** element (one JSON file; importing replaces the configurations found by identity or name and adds the others, see [Matching and creators](administrator-config.md#matching-and-creators)), with Full Workspace transfers and backups, besides the editor's **Export JSON** / **Import JSON** |
| **Excluded Calls lists** | **Scoring Excluded Calls** element, with Full Workspace transfers and backups, with their CDRs by file name. Importing or restoring replaces the lists found by identity (renames follow) or name and adds the others; each belongs to its creator when active in the destination, else to the importer |
| **Saved Scorings with their results**, shared selections, Scoring History | The workspace database: workspace duplication, database exports, transfers and ZIP database backups |

- **One format everywhere:** JSON import/export, ZIP configuration packages, transfers and configuration backup/restore use the same methodology format.
- **Older backups** of the Methodologies, which carried the Saved Scorings and report configurations, still restore them; imports and transfers of their packages leave them out.
- **After a restart,** interrupted calculations are kept as failed and can be recalculated.

## Troubleshooting

| Symptom | Check or action |
| --- | --- |
| No CDRs used | Verify workspace, NR Mode, the Campaign (each needs Data, Voice and Speech CDRs), ready processing status and the Active? choice in Workspace |
| Calculate is disabled | Read the yellow notice; complete each campaign's three source types, or wait for the running calculation of the same selection |
| Expected vendor/city choices are missing | Check mappings, the Campaign and the other filters (each lists the values they leave); reprocess older incomplete catalogues |
| GAP is N/A* | Verify the reference and matching context, including common valid environment coverage |
| Maximum achievable points differ between columns | Read the excluded KPI list of each combination |
| Results differ from another report | Compare methodology revision, filters, Break down by levels, thresholds and coverage |
| CDR changed during calculation | Wait for processing/mapping to finish and recalculate |
| Older All Environments KPI values are N/A | Recalculate to save pooled global measurements |
| A calculation failed after an interruption | Recalculate the Saved Scoring; delete it only if no longer needed |

> [!NOTE]
> **NR Mode selects the dataset universe.** It does not supply a different SA methodology automatically. Validate copied or customized environment rules before using them for a new benchmark.
## Methodology reference

Detailed reference for methodology files and the calculation engine.

### Portable JSON reference

#### Envelope and required content

- **Format:** exchange format **version 3** uses the same envelope for one methodology or a complete collection.
- **Older files:** files exported before the rename to DriveTest Analyzer, with the format `dashboard-analytic-scoring-configuration`, are still accepted. A version-1 file with a single methodology is still accepted. Version-2 exchange envelopes must be replaced with a new export.
- **One or many:** a one-methodology export has one item in `profiles`; Admin exports can contain all items.
- **Names:** the internal JSON names `profiles` and `active_profile_id` remain format identifiers. In the interface, these entities are called **methodologies**, and the active ID identifies the default.

The following minimal example contains one KPI. A complete benchmark must include all intended KPI definitions and a context for every configured environment.

```json
{
  "format": "drivetest-analyzer-scoring-configuration",
  "version": 3,
  "active_profile_id": "netcheck-2026",
  "profiles": [
    {
      "id": "netcheck-2026",
      "name": "Netcheck 2026",
      "configuration": {
        "version": "2026Q2",
        "title": "NetCheck 2026 scoring",
        "scope": {
          "environments": {
            "Drive - City": {
              "source_filters": {"G_Level_1": "Drive", "G_Level_2": "City"}
            }
          }
        },
        "metrics": [{
          "code": "K1",
          "category": "CLASSIC CALLS",
          "kpi": "CALL SUCCESS RATIO [%]",
          "source_kind": "voice",
          "direction": "higher_is_better",
          "kpi_type": "Reliable",
          "calculation": {
            "formula": "100 * SUM(Call_Status == \"Completed\") / COUNT(Call_Status)",
            "filters": {"Session_Type": ["CALL"]}
          },
          "contexts": {
            "Drive - City": {
              "max_points": 650,
              "most_reliable_points": 650,
              "thresholds": {"low": 85, "medium": 98, "high": 100, "ultra": null}
            }
          }
        }],
        "gap_priority": []
      }
    }
  ]
}
```

#### What is stored or derived?

| Field | Meaning |
| --- | --- |
| `configuration.version` | Methodology revision; separate from exchange format version |
| `title` | Optional editable description |
| `scope.environments` | Names, explicit source filters and optional display names |
| `metrics` | Nonempty collection of identified KPI definitions |
| Metric `calculation` | Formula and source filters; the formula determines the denominator |
| Metric `mapping_method` | `piecewise_linear`, `piecewise_quadratic` or `piecewise_smoothstep` |
| Metric `contexts` | Each environment's thresholds, maximum points, optional score anchors and optional `most_reliable_points` |
| `interpolation` | Optional default score anchors |
| `gap_priority` | KPI code order; removed codes are dropped and new codes appended |
| `next_kpi_number` | High-water mark for generated codes |

- **Derived, not exported:** environment totals and positive-point relative weights are derived from KPI maximum points, so exports do not duplicate them. Relative shares for zero-point environments are retained.
- **`most_reliable_points`** is optional; omitted or 0 leaves the KPI out of the Most Reliable scoring of that environment. Files without it are still imported and keep their identity.
- **Omitted on purpose:** reference filenames, workbook cells, denominator descriptions and Tableau grouping keys are not needed for an operational methodology.
- **Defaults:** optional mapping/anchor settings use supported defaults when omitted; retain explicit settings when customized.
- **Normalization:** existing supported workspace records are normalized on read; this is different from accepting an obsolete exchange envelope.

Favourite Scorings, report configurations and Excluded Calls travel apart from the methodologies (see [Save, export and backup are different](#save-export-and-backup-are-different)).

### Reference Prep flow and implemented calculation

#### From raw rows to points

1. Apply environment source selectors and the selected filters.
2. Group raw rows by the selected Operator/Vendor/Region/City/Campaign levels.
3. Calculate each KPI from its formula and source filters.
4. Map the measurement to a normalized score between 0 and 1.
5. Multiply by the KPI's configured maximum points.
6. Sum weighted points for categories, environments and total scoring.

- Operator aliases use the mapping snapshot saved with the result; levels left out of Break down by (such as Campaign) are pooled before the KPI calculation.
- Unlike the source Prep flow's inner joins, groups with missing measurements stay as N/A with their incomplete coverage reported.

#### Mapping methods and anchors

For normalized position `t` between adjacent measurement thresholds:

| Method | Interpolation fraction |
| --- | --- |
| **Linear** | `t` |
| **Quadratic** | `t²` |
| **Smooth curve** | `3t² − 2t³` |

- All methods preserve the configured threshold anchors, direction and score limits. Mapping and Direction are separate settings. The original NetCheck definitions use Linear.
- **Default NetCheck anchors without Ultra:** **Low = 0%**, **Medium = 80%**, **High = 100%**.
- **With Ultra:** K20/K25 use **High = 90%** and other supported mappings use **95%**; **Ultra = 100%**. Per-context anchors are editable.
- **Dynamic best-value Ultra thresholds** use all operators in the selected comparison context. Selecting a different operator scope can therefore change a dynamic threshold.

#### Combined environments and coverage

All Environments sums the configured maxima and the separately calculated environment points; global raw KPI values come from pooled source rows (see [Incomplete coverage and achievable scoring](#incomplete-coverage-and-achievable-scoring)). Zero-point environments can contribute raw measurements without weighted points.

> [!WARNING]
> **A zero-point environment does not cause incomplete weighted scoring.** A missing positive-point contribution does. Older results without saved global raw measurements require recalculation to display those values.

#### GAP calculations and aggregates

GAP subtracts **reference weighted points** from **compared operator weighted points** within the same context (see [How the GAP reference is matched](#how-the-gap-reference-is-matched)).

| Result | Calculation |
| --- | --- |
| KPI GAP | Operator KPI points − reference KPI points |
| Scoring category/final GAP | Mean of valid original KPI comparisons |
| GAP table footer | Sum of valid KPI GAPs in each column |
| Individual PPT Average KPI GAP | Mean of valid displayed KPI GAP cells |
| Individual PPT Average total KPI GAP | Mean of the displayed columns' KPI sums |

- Columns are the combinations of the selected levels (such as City and Campaign); columns without valid GAPs are left out of the mean of totals. Example: Q1 totals −51.64 and Q2 −87.08 points, so the Average total KPI GAP is `(−51.64 − 87.08) / 2 = −69.36 points`, unlike the mean per KPI.
- The overall KPI mean uses original KPI rows, not an unweighted mean of category means. No aggregate applies KPI weights a second time.
- For All Environments, only valid environment contributions common to both sides are compared; disjoint coverage or a missing reference gives N/A.

## Supported KPI allocation

The initial NetCheck 2026 methodology contains 32 KPIs. The following source notes and allocation table describe the original rules; customized methodologies can change them.

### NetCheck 2026 workbook verification

#### Source documents

| Reference | Role |
| --- | --- |
| `Netcheck_Score_Mapping_2026Q2_BestNetwork_Drive_City_Road.xlsx` | Thresholds, mapping anchors and maximum points |
| `Join_NC_CDR_KPIsv3_all_UK.tfl` | Source formulas, filters and aggregation reference |
| `20260416 NET CHECK Press Benchmarking Package for Mobile Networks.pdf` | Benchmark methodology context |
| Earlier example PPT | Presentation layout reference |

The Git-ignored local `assets/scoring/netcheck_2026.json` is an optional reference import. It is not distributed or loaded automatically. Workspace rules remain authoritative.

#### Initial allocation and matching

- **Workbook:** 32 KPI definitions in each of DriveCity and DriveConnectionroad, rows 4–35. Its maximum allocations were checked against the extracted rules: City totals **650** and Road **350** points.
- **Road selector:** the current Road selector uses **G_Level_1 = Drive**, **G_Level_2 = Connecting Roads**. The workbook sheet name is provenance, not the current source selector. Known legacy Road definitions are corrected without changing their points; explicit customized names/selectors are preserved.
- **Walk** is a zero-point extension with City-derived starting thresholds. It needs validation before assigning points.

#### Documented differences

> [!NOTE]
> **Reference documents are not interchangeable numerical baselines.** Match raw inputs, revision, filters, operator scope, aggregation and coverage before comparing results.

- Dynamic City best-value Ultra ranges in the workbook exclude some operators; the application uses all selected operators, following the best-achieved definition.
- Two City P90 operator formulas use High = 95% while the common formulas and Road use 90%. The application consistently uses 90% for K20/K25.
- The PDF's Drive/Walk allocation totals 675 points; this mapping uses the workbook's 1,000-point City/Road allocation.
- The earlier example PPT uses different Q4 weights; it supplies layout guidance, not a numeric golden for the current mapping.
- POLQA low-quality calculation uses **LQ <= 1.6**, despite the source label. Call setup threshold uses **> 10 seconds**, rather than the older example PPT's > 15 seconds.
- The source Prep flow has 18 aggregation steps and 17 inner joins. The application calculates the supported formulas directly from processed rows and retains missing comparisons visibly.
- Regression fixtures cover representative formulas and mapping examples. Full numerical parity with an external Prep/Excel output still requires matching source data and an independently verified result.

### Per-KPI reference points

This is the **original NetCheck 2026 reference**, not a promise that a customized saved methodology uses these weights. Point values are shown to four decimal places.

| Code | Category | KPI | City points | Road points |
|---|---|---|---:|---:|
| K1 | CLASSIC CALLS | CALL SUCCESS RATIO [%] | 73.4825 | 39.5675 |
| K2 | CLASSIC CALLS | CALL SETUP TIME [s] | 8.6450 | 4.6550 |
| K3 | CLASSIC CALLS | CALL SETUP TIME > 10 s [%] | 4.3225 | 2.3275 |
| K4 | CLASSIC CALLS | POLQA < 1.6 [%] | 22.7500 | 12.2500 |
| K5 | CLASSIC CALLS | POLQA [MOS] | 7.5855 | 4.0845 |
| K6 | CLASSIC CALLS | DISTURBED & IMPAIRED CALL [%] | 15.1645 | 8.1655 |
| K7 | WHATSAPP CALLS | CALL SUCCESS RATIO [%] | 56.8750 | 30.6250 |
| K8 | WHATSAPP CALLS | POLQA < 1.6 [%] | 14.7875 | 7.9625 |
| K9 | WHATSAPP CALLS | POLQA [MOS] | 4.9270 | 2.6530 |
| K10 | WHATSAPP CALLS | DISTURBED & IMPAIRED CALL [%] | 9.8605 | 5.3095 |
| K11 | MULTI RAB | MULTI RAB DATA TRANSFER SUCCESS RATIO [%] | 9.1000 | 4.9000 |
| K12 | TRANSFER | FDFS DL SUCCESS RATIO [%] | 30.4200 | 16.3800 |
| K13 | TRANSFER | FDFS DL TRANSFER TIME [s] | 20.2800 | 10.9200 |
| K14 | TRANSFER | FDFS UL SUCCESS RATIO [%] | 15.2100 | 8.1900 |
| K15 | TRANSFER | FDFS UL TRANSFER TIME [s] | 10.1400 | 5.4600 |
| K16 | TRANSFER | FDTT DL THROUGHPUT > 2Mbit/s [%] | 20.2800 | 10.9200 |
| K17 | TRANSFER | FDTT DL THROUGHPUT > 5Mbit/s [%] | 25.3500 | 13.6500 |
| K18 | TRANSFER | FDTT DL THROUGHPUT > 20Mbit/s [%] | 25.3500 | 13.6500 |
| K19 | TRANSFER | FDTT DL THROUGHPUT > 100Mbit/s [%] | 15.2100 | 8.1900 |
| K20 | TRANSFER | FDTT DL THROUGHPUT P90 [Mbit/s] | 15.2100 | 8.1900 |
| K21 | TRANSFER | FDTT UL THROUGHPUT > 1Mbit/s [%] | 10.1400 | 5.4600 |
| K22 | TRANSFER | FDTT UL THROUGHPUT > 3Mbit/s [%] | 12.6750 | 6.8250 |
| K23 | TRANSFER | FDTT UL THROUGHPUT > 10Mbit/s [%] | 12.6750 | 6.8250 |
| K24 | TRANSFER | FDTT UL THROUGHPUT > 20Mbit/s [%] | 7.6050 | 4.0950 |
| K25 | TRANSFER | FDTT UL THROUGHPUT P90 [Mbit/s] | 7.6050 | 4.0950 |
| K26 | HTTP/HTTPS BROWSING | BROWSING TIME TO 1MB [ms] | 33.8000 | 18.2000 |
| K27 | HTTP/HTTPS BROWSING | BROWSING SUCCESS RATIO [%] | 50.7000 | 27.3000 |
| K28 | VIDEO STREAM | VIDEO STREAMING SUCCESS RATIO [%] | 54.0800 | 29.1200 |
| K29 | VIDEO STREAM | VIDEO STREAMING TTFP >= 10 s [%] | 3.3800 | 1.8200 |
| K30 | VIDEO STREAM | VIDEO STREAMING IRRITATING EXPERIENCE [%] | 27.0400 | 14.5600 |
| K31 | INTERACTIVITY | INTERACTIVITY PACKET ERROR RATIO [%] | 5.0700 | 2.7300 |
| K32 | INTERACTIVITY | INTERACTIVITY MEDIAN RTT [MS] | 20.2800 | 10.9200 |

### Most Reliable reference points

The NetCheck 2026 Most Reliable scoring rates 10 KPIs.

- **Points:** **650** in Drive - City and **350** in Drive - Connecting Roads (Voice 350, Data 650, **1,000** in total). The KPIs underlined in the NetCheck Q2 2026 report are the same.
- **Split:** each KPI has global points (for example 141.75 for the classic call success ratio) split 65% City and 35% Road, as in Best Network.
- **Source:** `Netcheck_Score_Mapping_2026Q2_Mostreliable_Drive_City_Road.xlsx` writes these points by hand, rounded to two decimals, which adds up to 1,000.04. Neither the workbooks nor the reports give a formula to derive them, so they are part of the methodology.
- **Thresholds and score anchors** are the Best Network ones.

Enter these values in the Most Reliable points column:

| Code | Category | KPI | City points | Road points |
|---|---|---|---:|---:|
| K1 | CLASSIC CALLS | CALL SUCCESS RATIO [%] | 92.1375 | 49.6125 |
| K4 | CLASSIC CALLS | POLQA < 1.6 [%] | 44.3625 | 23.8875 |
| K7 | WHATSAPP CALLS | CALL SUCCESS RATIO [%] | 61.4250 | 33.0750 |
| K8 | WHATSAPP CALLS | POLQA < 1.6 [%] | 29.5750 | 15.9250 |
| K12 | TRANSFER | FDFS DL SUCCESS RATIO [%] | 63.3750 | 34.1250 |
| K14 | TRANSFER | FDFS UL SUCCESS RATIO [%] | 38.0250 | 20.4750 |
| K16 | TRANSFER | FDTT DL THROUGHPUT > 2Mbit/s [%] | 101.4000 | 54.6000 |
| K21 | TRANSFER | FDTT UL THROUGHPUT > 1Mbit/s [%] | 50.7000 | 27.3000 |
| K27 | HTTP/HTTPS BROWSING | BROWSING SUCCESS RATIO [%] | 84.5000 | 45.5000 |
| K28 | VIDEO STREAM | VIDEO STREAMING SUCCESS RATIO [%] | 84.5000 | 45.5000 |

Regression tests reproduce the workbook's City and Road totals for each operator from its KPI values, within the 0.05 points of its rounding.

### NetCheck 2025

The campaigns up to Q1 2026 follow the NET CHECK 2025/26 Benchmarking Methodology. The **NetCheck 2025** methodology, shipped with the application beside NetCheck 2026, has the KPIs, thresholds and Data points of NetCheck 2026 with two differences, from its drive test ranking (Drive - City 65 %, Drive - Connecting Roads 35 %):

- **K3** is **CALL SETUP TIME > 15 s [%]** (calls whose setup takes more than 15 s, with the same thresholds 3 % / 0.6 % / 0 %) instead of > 10 s.
- **Voice points:** the classic calls get 252 points and WhatsApp calls 84 (NetCheck 2026: 203 and 133).

Its Most Reliable points are those of NetCheck 2026.

| Code | KPI | City points | Road points |
|---|---|---:|---:|
| K1 | CALL SUCCESS RATIO [%] | 92.8200 | 49.9800 |
| K2 | CALL SETUP TIME [s] | 10.9200 | 5.8800 |
| K3 | CALL SETUP TIME > 15 s [%] | 5.4600 | 2.9400 |
| K4 | POLQA < 1.6 [%] | 27.3000 | 14.7000 |
| K5 | POLQA [MOS] | 9.1000 | 4.9000 |
| K6 | DISTURBED & IMPAIRED CALL [%] | 18.2000 | 9.8000 |
| K7 | WHATSAPP CALL SUCCESS RATIO [%] | 36.4000 | 19.6000 |
| K8 | WHATSAPP POLQA < 1.6 [%] | 9.1000 | 4.9000 |
| K9 | WHATSAPP POLQA [MOS] | 3.0333 | 1.6333 |
| K10 | WHATSAPP DISTURBED & IMPAIRED CALL [%] | 6.0667 | 3.2667 |

- **Campaigns of the shipped methodologies:** they say the campaigns they apply to, so **By campaign** scores each campaign with its own: NetCheck 2025 up to 2026-Q1, NetCheck 2026 for 2026-Q2 and NetCheck 2026-Q3 from 2026-Q3.
- **New workspace:** starts with NetCheck 2026 as its active methodology.
- **Existing workspace:** receives NetCheck 2025 once, with its campaigns unless they overlap those of one of its methodologies (then without them: set them in **Applies to campaigns**).

### NetCheck 2026-Q3

From Q3 2026 NetCheck adds TikTok to Video Streaming. The **NetCheck 2026-Q3** methodology is shipped with the application beside NetCheck 2026:

- **Video Streaming:** keeps its 20 % but divides it between YouTube (13 %) and TikTok (7 %), following the NetCheck Q3 ranking templates (Best Network and Most Reliable, National and City).
- **KPIs:** K28, K29 and K30 become the YouTube KPIs (`Test_Name` = `YouTube`, as every Video Streaming test of the earlier campaigns), and K33, K34 and K35 the same KPIs for TikTok (`Test_Name` = `TikTok`), with the same thresholds.
- **Everything else:** every other KPI and the 650 City and 350 Road points of both scorings are those of NetCheck 2026.
- **Use:** choose it in the Scoring & GAP Analysis strip for the Q3 campaigns.

| Code | KPI | City points | Road points | Most Reliable City / Road |
|---|---|---:|---:|---:|
| K28 | YOUTUBE VIDEO STREAMING SUCCESS RATIO [%] | 35.1520 | 18.9280 | 54.9250 / 29.5750 |
| K29 | YOUTUBE VIDEO STREAMING TTFP >= 10 s [%] | 2.1970 | 1.1830 | |
| K30 | YOUTUBE VIDEO STREAMING IRRITATING EXPERIENCE [%] | 17.5760 | 9.4640 | |
| K33 | TIK TOK VIDEO STREAMING SUCCESS RATIO [%] | 18.9280 | 10.1920 | 29.5750 / 15.9250 |
| K34 | TIK TOK VIDEO STREAMING TTFP >= 10 s [%] | 1.1830 | 0.6370 | |
| K35 | TIK TOK VIDEO STREAMING IRRITATING EXPERIENCE [%] | 9.4640 | 5.0960 | |

## Tips & shortcuts

Gestures and keys that save time in the module, gathered here from the sections above.

**Charts, tables and maps of the results**

| To… | Do this |
| --- | --- |
| Open a chart, map or table larger | Double-click it, on every results tab; or focus a chart card (<kbd>Tab</kbd>) and press <kbd>Enter</kbd> or <kbd>Space</kbd> |
| Close the larger view | <kbd>Esc</kbd>, a click outside it or **×**. While it is open, <kbd>Tab</kbd> stays inside it |
| Zoom into part of a chart or map | Drag a rectangle over it (also in the larger view) |
| Zoom with buttons | Point at the chart or map for **+**, **−** and **⤢** (whole view). On touch: tap it to show them for a few seconds |
| See the values of a bar, segment, cell or donut | Hover or focus it. On touch: not available; read the tables |
| Save or copy a card as an image | Point at the card for its download (PNG) and camera (copy) buttons, and a pair for the chart or table under the pointer. On touch: tap the card |
| Copy an image when the browser blocks the clipboard | Right-click the image in its window (on touch: keep it pressed) and choose **Copy Image** |

**Results tabs**

| To… | Do this |
| --- | --- |
| Open a results tab from a link or bookmark | End the address with `/scoring#scoring-results-summary`, `-charts`, `-tables`, `-geographical-areas` (Country Areas), `-trends`, `-gap`, `-points-lost` or `-methodology-impact` |
| Jump from Where to act to the details | Click a link of the **Deep-dive** column |
| Show or hide an operator in every section | Click its **Operators** chip (one always stays on) |
| Choose the operator of Campaign Comparison or Where to act | Click its button in **Focus operators** or **Other operators** |

**Points Lost Map and route maps**

| To… | Do this |
| --- | --- |
| Show only the areas of one place | Click its row in the ranking (the map centres and zooms on them); again for all |
| Add or remove single rows | <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+click a row |
| Choose a range of rows | <kbd>Shift</kbd>+click: every row from the last one clicked (<kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Shift</kbd>+click adds them) |
| Light the places measured in an area | Click the area (<kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+click adds areas), or <kbd>Shift</kbd>+drag a rectangle to choose every area it touches (a plain drag zooms) |
| Show everything again | Click the same choice again, click outside every area, or press <kbd>Esc</kbd> after a click on the map |
| See the tests of a place, or the full environment name | Hover a **Per 1,000 tests** or **Type** cell |
| Zoom a route map onto a stretch | Click its row (or focus it and press <kbd>Enter</kbd>/<kbd>Space</kbd>); again, or **Whole route**, for the whole route |

**Site Area Map** (from a site of **Sites to review**; every control is described in [Non-Qualified Calls](non-qualified-calls.md#map-of-the-call))

| To… | Do this |
| --- | --- |
| Zoom in the floating panel | <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+wheel, or pinch (a plain wheel only shows a hint, so the page still scrolls) |
| Open the larger map | Double-click (on touch: double-tap). Inside it, a double-click zooms in and the plain wheel zooms towards the pointer |
| Zoom into a rectangle | <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+drag (the pointer becomes a crosshair) |
| Measure a distance with the elevation profile | <kbd>Alt</kbd>/<kbd>Option</kbd>+drag: distance, bearing and ground profile. <kbd>Esc</kbd> clears it |
| Move or resize a floating card | Drag its header or corner; pin it to keep it open, restore it to put it back |
| Move along the timeline chart | Drag it, or <kbd>←</kbd>/<kbd>→</kbd> (<kbd>Shift</kbd> for 5 s steps), <kbd>Home</kbd>/<kbd>End</kbd>; <kbd>Esc</kbd> leaves it |

**Scoring Trends and Methodology Impact**

| To… | Do this |
| --- | --- |
| Enlarge a single area trend, or the table | Double-click it in **National & Country Areas Trends** |
| See only the KPIs of one kind of change | Click a count in **What changed in the methodology** (again to undo) |
| See every row of a long list | **Show all N** (**Show the first N** shortens it again) |

**Favourite Scorings and Filter Navigator**

| To… | Do this |
| --- | --- |
| Keep or remove a Favourite Scoring | Click its star: **☆** keeps it, **★** takes it out |
| Open the Filter Navigator | Click the scoring name, or anywhere on the **Showing** summary |
| Move between the search and the tree | <kbd>↓</kbd> from the search; <kbd>↑</kbd> on the first item goes back |
| Move in the tree | <kbd>↑</kbd> <kbd>↓</kbd> <kbd>Home</kbd> <kbd>End</kbd>; <kbd>→</kbd>/<kbd>←</kbd> open and close a branch, or go into it and back to its parent; <kbd>Enter</kbd> or <kbd>Space</kbd> use the focused item |
| Use the only match of a search | <kbd>Enter</kbd> in the search |
| Close the list of Favourite Scorings | <kbd>Esc</kbd> (it clears the search first) or a click outside it, as **Close** |
| Reorder Favourite Scorings | Drag a card by the tab on its left in **Manage Favourite Scorings** (not for readers) |
| See the CDR files of a scoring | Hover or click its **CDRs** button |
| Close a dialog of the configuration | <kbd>Esc</kbd> closes an open list first, then cancels the dialog |
| Open the methodology editor in its own tab | <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+click (or <kbd>Shift</kbd>+click) **Scoring Methodologies** |
