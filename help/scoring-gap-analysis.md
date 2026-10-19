# Scoring & GAP Analysis

Calculate KPI scores from processed Data, Voice and Speech CDRs, then compare each operator with a reference operator. Results belong to the workspace and do not require a Dashboard or Report Template.

Each calculation gives the NetCheck **Best Network** scoring, which rates every KPI of the methodology. When the methodology has Most Reliable points, it also shows the **Most Reliable** scoring, which rates a subset of KPIs with its own maximum points, with the same CDRs, filters, aggregation and GAP reference (see [Most Reliable Network scoring](#most-reliable-network-scoring)).

> [!NOTE]
> **Start with a saved methodology.** It defines the environments, KPI formulas, thresholds and maximum points. Each result keeps a snapshot of the rules it was calculated with.

## Choose your task

| I want to… | Go to |
| --- | --- |
| Calculate or recalculate a comparison | [Calculate and review](#calculate-and-review) |
| Understand filters and Split by | [Filters and Split by](#filters-and-split-by) |
| Read scores, GAPs and coverage warnings | [Results and workspace settings](#results-and-workspace-settings) |
| Change the colours of the charts, tables and exports | [Choose a theme](#choose-a-theme) |
| Show or configure the Most Reliable scoring | [Most Reliable Network scoring](#most-reliable-network-scoring) |
| Change environments, KPIs or weights | [Methodology](#methodology) |
| Edit formulas and scoring rules | [KPI definitions](#editing-replacing-adding-and-removing-kpis) |
| Understand methodology JSON | [Portable JSON reference](#portable-json-reference) |
| Inspect original KPI weights and sources | [Supported KPI allocation](#supported-kpi-allocation) |
| Understand the Scoring History and fast calculations | [Scoring History](#scoring-history) |
| Share results or preserve a workspace | [Persistence and exports](#persistence-and-exports) |
| Resolve missing results | [Troubleshooting](#troubleshooting) |

## Calculate and review

### 1. Prepare the inputs

1. Open the correct workspace and finish processing the required CDRs.
2. If no methodology is configured, import one under **Workspace Config → Scoring & GAP Analysis Setup**.
3. Open **Scoring & GAP Analysis** and expand **Select NR Mode, Campaign, filters, Split by & GAP reference**.
4. Choose **NSA** or **SA** in **NR Mode**. A calculation cannot mix both modes.

> [!IMPORTANT]
> Every campaign of the calculation needs at least one ready **Data**, **Voice** and **Speech** CDR. Complete CDRs do not guarantee complete KPI measurements: inspect Calculation notes after processing.

### 2. Choose the NR Mode and Campaign

There is no CDR selector: the **NR Mode** and the **Campaign** filter beside it choose the CDRs of the calculation. They are the CDRs of that NR Mode that the combined CDR tables include, for the chosen campaigns:

- the **Final** CDR of a campaign before its **Weekly** and **Daily** CDRs, and a Weekly CDR before the Daily ones it contains;
- or, when it was changed, the **In Combined?** choice of the CDR in Workspace (see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)).

The Campaign filter offers first **Latest campaign**, **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns**, **Previous campaign** (the one before the latest) and **All available campaigns**: the newest one to four campaigns of the NR Mode with Data, Voice and Speech CDRs, the one before the newest, or every one of them, whenever it is used (also those that arrive later). Each one stands alone (checking it clears the other one and the campaigns, checking a campaign clears it; **Select All / None** checks or clears the campaigns only). The panel keeps the choice, so it follows the newest campaigns the next time it opens, and a calculation or Saved Filter uses the campaigns it stands for then. Without a Campaign (**All complete campaigns**), every campaign with Data, Voice and Speech CDRs is scored; the campaigns that lack a type are named in a note below the CDRs and left out. **CDRs used** lists the CDRs of the calculation by type, with their stage and campaigns (Weekly and Daily CDRs outlined), follows every change of the NR Mode or a filter at once, and the badge above the panel counts them.

On first use, and when another NR Mode is chosen, the Campaign is **Latest campaign**: the newest campaign of the NR Mode with Data, Voice and Speech CDRs, also when newer ones arrive. A selection saved before (when CDRs were chosen by hand) opens with the campaigns of its CDRs. Opening a Saved Filter shows its own CDRs (**CDRs of the opened Saved Filter**, with **Use automatic CDRs** to choose them again) until the NR Mode or a filter changes: only those with its campaigns, since the rows of its CDRs of other campaigns are left out by its Campaign filter.

### 3. Set filters, Split by and reference

1. Restrict **Operators**, **Vendors**, **Regions**, **Clusters** or **Cities** if needed. Every filter lists the values of every CDR of the NR Mode, with the labels of the Operator and Vendor Maps, and only those the other filters leave: choosing Vodafone as Operator leaves in Vendor only the Vendors of Vodafone, and the Campaign the values of its CDRs. A filter's own choice does not narrow its list, a filter with every value checked keeps every new value checked, and a value no CDR has any longer with the other filters is named in a warning. The lists come from the combinations of values each CDR keeps (the **CDR Filter Facets** table, read once per CDR), so they never read the rows of the CDRs.
2. Choose the **Split by** levels (Operator, Vendor, Region, **Cluster**, City and Campaign, in the order of the aggregation hierarchy). **Operator** is always included and **Campaign** is checked initially; additional levels split the results into separate combinations. Cluster needs CDRs with a `Cluster` column, filled by the source CDR or by a Cluster mapping.
3. In the **Geographical Areas & Scoring Trends** panel, below Split by (always included), choose in **Geographical Areas** the areas of the Geographical Areas and Scoring Trends tabs: the **Breakdown** (**Region** by default, Cluster, City or None, which leaves only the Separate cities and needs at least one of them) and the **Separate cities**, each scored on its own (**London** by default; **Main Cities** is kept as such, the Main Cities of the workspace each time the Saved Filter is calculated, which then calculates again when they change). In **Scoring Trends** choose the **Campaigns** of the Scoring Trends tab: **All available campaigns** (the default), **Latest campaign**, **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns** or **Previous campaign**, which stand alone and follow the newest campaigns each time the Saved Filter is calculated, or campaigns; whatever the Campaign filter of the rest of the scoring, the Scoring Trend and the National & Geographical Areas Trends are calculated with the Data, Voice and Speech CDRs of those campaigns, with the same filters, methodology (By campaign, each campaign with its own) and GAP reference (without campaigns they follow the Campaign filter), with their own **Time split** (All selected CDRs, Campaign, Daily, Weekly, Monthly, Quarterly or Yearly by the start time of each test). Both tabs are always scored on the whole country: with Region, Cluster or City filters, the other tabs show the part of the country they choose while Geographical Areas and Scoring Trends score the whole country with the other filters (from the Scoring History this adds a couple of seconds; from the CDR rows, the rows of the whole country are read and scored too, which takes longer than the filtered scoring). The document exports of the job show their slides.
4. In **GAP reference operator**, beside the Campaign in the **NR Mode, Campaign, GAP reference & Methodology** panel, select the operator to compare against. The initial reference is **EE** (an operator the Operator Maps exclude is never offered). The **Focus operators** are the Operator labels with the **Focus** role in [Workspace Config → Operator Maps](workspace-config.md#operator-maps) (with every name of the CDRs they stand for): the recommendations and comparisons of the PowerPoint and Word exports focus on them (see [Slides of the export](#persistence-and-exports): Where to act, the locations ranked, the individual GAP comparisons, GAP by part, the KPI GAP Profile and the Points Lost views; every operator when no label has it; they change no calculation). The page itself offers every operator: in the operator choices of those sections the Focus operators come first (chosen by default), under **Focus** and a line before the others. The operators with the **Exclude** role are left out of every calculation, filter and result, as if every Operator filter left them out. (The Scoring artifacts of Reporting Jobs and the Scoring section of the Bundle Report Templates show the GAP reference and the methodology in the same order beside their campaigns, and their **Geographical Areas** and **Scoring Trends** side by side.)
5. Choose the **Scoring Methodology**, after the GAP reference: **By campaign (each campaign with its methodology)**, the initial choice, scores each campaign with the methodology whose campaigns include it and the others with the default methodology (see [Methodologies by campaign](#methodologies-by-campaign)), so campaigns measured with different rules are compared with their own rules and, with a single methodology, every campaign uses it; or choose one saved methodology for every campaign. With campaigns of different methodologies it needs **Campaign** in the Split by, and the job names the methodology of each campaign.

The aggregation hierarchy determines the order of the filter controls and of the Split by levels and headers. It is an application setting shared by every workspace and methodology. **Aggregation hierarchy**, at the right of the Split by levels, opens a dialog to reorder it; editors save it for everyone. The initial order is **Operator → Vendor → Region → Cluster → City → Campaign**, and saved results keep the order they were calculated with.

### 4. Calculate or recalculate

Every selection you calculate becomes a **Saved Filter**: its CDRs, NR Mode, filters, Split by levels, GAP reference, methodology and Scoring Trends. Only the Saved Filters marked with the star (**☆**), the Favourites Filters, are kept and listed: an unstarred one shows only in the selected card of the **Scoring Results** dropdown (where **☆** stars it) while it is the one you are looking at, and goes when you calculate or open another (unless it is still calculating or drawing its Points Lost Map). Calculating the same selection again reuses it instead of adding another one.

| Situation | Action |
| --- | --- |
| The selection was never calculated | **Calculate Scoring** calculates it and saves it in **Saved Filters**; until then, the **Scoring Results** dropdown says *No Saved Filter matches the Calculation panel's filters* (choose a Favourites Filter, or calculate the selection) instead of showing the card and the results of the Saved Filter opened before, which come back when the selection is a Saved Filter again |
| The selection was used before | With its result up to date, the button reads **Open Scoring** (with a folder open) and opens its Saved Filter; when its CDRs, methodology or Operator Maps changed since its result was saved, **Calculate Scoring** calculates it again first; **Recalculate** calculates it again anyway |
| Its calculation is queued or running | Both actions are disabled until it finishes, and the yellow notice says *Calculating* (or *Recalculating*) *the scoring of the selected CDRs and filters…* until then; while it runs, the results show an animated **Calculating Scoring…** bar, in the colour of the result tab, with its progress and step (for each methodology of a calculation by campaign: checking the Scoring History of its CDRs, then calculating from it or from the rows of the CDRs), and the floating background tasks card shows the calculation with its elapsed time |

A selection is the same when it has the same CDRs, NR Mode, filters, Split by levels, GAP reference, methodology and Scoring Trends, whatever its CDRs or methodology hold today. Its result, instead, is identified by what it was calculated with: reprocessing a CDR, editing the methodology or changing the Operator Maps makes it out of date.

> [!TIP]
> Read the **yellow message below the methodology selector** when an action is unavailable. It tells whether the selection was used before and explains incomplete selections and other calculation conditions.

### 5. Reuse Saved Filters

Choose a Saved Filter in the **Scoring Results** dropdown or in the **Favourites Filters** panel. The module restores its selection in the Calculation panel and loads its saved result, with an animated **Loading Scoring Results…** bar meanwhile (the results are kept ready on the server, so opening them again is quick). A saved result that is out of date (its CDRs were reprocessed, or the methodology or the Operator Maps changed) is calculated again on its own, usually in a moment from the [Scoring History](#scoring-history). When its CDRs or its methodology no longer exist, the saved result is shown as it was and the yellow notice says why.

The lists show the Favourites Filters in a fixed order: a newly starred one goes first, opening one does not move it, and dragging a card by the tab on its left (the cursor becomes a hand) in the **Favourites Filters** panel moves it, a horizontal line showing where it will go until it is dropped (the order is the same for every user of the workspace, travels with the Saved Filters in exports and transfers, and each move is recorded in App Events). Unstarring a Saved Filter takes it out of the lists. The panel shows ten of them before it scrolls, and is only as tall as fewer ones. Each card of the panel has a checkbox on top of the tab on its left: **Select all** on top of the panel checks them all, and **Use newer CDRs** beside it (with the number of checked Saved Filters that have newer CDRs) updates each of them with its newer CDRs and calculates them again in the background, while the Saved Filter being looked at stays open, and **Delete** (with the number of checked Saved Filters; not for readers) deletes every checked Saved Filter and its result after one confirmation, keeping their CDRs and the Scoring History, and records each one in App Events. Each card shows:

- its **name**, when it has one, as a badge on top of the card (**✎** edits it in a dialog that shows the filters of the Saved Filter above the name field: **Save Name** names or renames it, **Enter** saves it and **Escape** cancels, and **Edit Filters** opens it for editing in a dialog, as described below), and, in a blue box with its status, its filters: the date it was last used, NR Mode, Regions, **Clusters** (in their own colour), Cities, Operators, Vendors and Campaigns;
- the ordered **Split by** levels, the **GAP Reference**, the **Scoring Methodology** (for **By campaign**, the methodology of each campaign follows the pill), its **Geographical Areas** (Breakdown and Separate cities; each Region and London for one saved without them) and its **Scoring Trends** (the campaigns, those of the Saved Filter when its trends have none of their own and an automatic choice with the campaigns it stood for last time, and the time split), their values as pills, each in its own colour, the **Calculation time** (or the time **Elapsed** while it runs), and on one line how many times it was **Used** (each Calculate Scoring or Recalculate of its selection, each report scenario that uses it, and each opening from its card) and **Calculated** (each calculation that finished);
- **Newer CDRs available** when a Final CDR of the same campaign (or a newer cumulative Weekly or Daily CDR) replaces one of its CDRs: **Use newer CDRs** replaces those CDRs with the newer ones in the same Saved Filter, which keeps its name, star and place, and calculates it again (a Saved Filter that already had that selection is merged into it);
- **Waiting for its CDRs** for a Saved Filter imported from another workspace whose CDRs are not processed here yet (it finds them by file, whatever their name; one with a Campaign choice such as Latest campaign, like the Favourites Filters a new workspace starts with, takes the CDRs that choice stands for here);
- the **CDRs** button (hover or click it to inspect the source files) and, in the bottom right corner, its **Filter ID** (the identifier App Events give it, also on the selected card of the Scoring Results dropdown) before **✎**, **⧉** to duplicate it (described below), **☆** to keep it (starred, it joins the list first) and **×** to delete it.

The generated PowerPoint is named `yyyymmdd_hhmmss - Scoring & GAP Analysis - <NR Mode> - <Regions> - <Clusters> - <Cities> - <Operators> - <Vendors> - <Campaigns>.pptx`. A complete vendor selection appears as **All Vendors**.

A Saved Filter calculated with **Latest campaign**, **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns**, **Previous campaign** or **All available campaigns** keeps that choice instead of the campaigns of that moment: its card shows the choice with the campaigns it stood for last time, and whenever it is opened it takes the campaigns and CDRs the choice stands for then, and is calculated again when they changed.

**Edit Filters** opens the Calculation panel in a dialog with the selection of the Saved Filter, under an **Editing Saved Filter** notice, and the CDRs of its NR Mode and Campaign chosen automatically. Change its NR Mode, Campaign, filters, Split by, GAP reference, Scoring Trends or methodology; the CDRs follow the NR Mode and Campaign. **Save Changes** (in place of Calculate Scoring and Recalculate) gives the Saved Filter that selection and calculates it again, keeping its name, star and place; a Saved Filter that already had that selection is merged into it. **Cancel Editing**, next to Save Changes, or **Escape** closes the dialog without changing it, and the Calculation panel keeps the selection it had before. A Saved Filter cannot be edited while it is being calculated.

**⧉** duplicates a Saved Filter to save a variant of it as a new one (for example the same filters with Latest 3 campaigns): it asks for the name of the copy (its own name followed by *(copy)*, shown above the filters of the Saved Filter) and **Edit Filters of the Copy** opens the Calculation panel in the same dialog with its selection, under a **Duplicating Saved Filter** notice. Change what the copy needs; **Save as New Filter** (enabled once the selection is no Saved Filter yet) saves it as a new Favourites Filter with that name, right after the one copied (first when that one is not starred), and calculates it, while the Saved Filter copied stays as it was. **Cancel Editing** or **Escape** closes the dialog without a copy.

Deleting a Saved Filter removes it and its saved result after confirmation; its CDRs and the Scoring History stay. A running calculation stops at a processing checkpoint or discards its pending result. Viewers can open Saved Filters but not name, edit, pin or delete them.

### What is remembered?

- **Shared across workspace users and browsers:** CDRs, NR Mode, methodology, filters, Split by levels, Scoring Trends and GAP reference. These calculation selections save automatically.
- **Within the browser session:** result tab, environment, display controls, comparison selection and scroll position.
- **In each Saved Filter:** its selection, name, pin, uses and calculations, and the source metadata, rules, grouping, result and warnings of its last calculation.

Automatic refreshes of the Saved Filters do not overwrite edits to the calculation controls. Removed or unready inputs produce a notice when a saved selection is restored.

## Filters and Split by

### Filtering chooses rows; Split by chooses groups

| Control | Example | Effect |
| --- | --- | --- |
| Filter | City = Leeds and London | Include rows from either city |
| Split by | Operator → City → Campaign | Calculate separate results for each operator/city/campaign combination |
| Omit a Split by level | Campaign not selected | Pool the selected campaigns' raw rows before calculating KPIs |

Values within a filter combine with **OR**. Different filter fields combine with **AND**. An empty selection means all values. **Main Cities** selects configured workspace cities that exist in the selected CDRs.

The engine pools raw rows before calculating ratios, averages, medians and P90. It does not average KPI results already calculated from separate files.

> [!TIP]
> Select **Campaign** when you want a separate column or bar for each campaign. Filtering two campaigns alone does not separate their results.

### Vendor filtering

The **Operator_Vendor** selector filters the `<Operator>_<Vendor>` identity, **Vendor_Operator** the same identity as `<Vendor>_<Operator>` and the **Vendor** selector the vendor alone, using cached per-CDR values; **Cluster** follows Region and **City** offers **Main Cities** first. Choices appear in this order: real vendors, Ericsson (Mixed) (and the former Mixed Vendor), the former Other Vendor, All Vendor(s), operators without assigned vendors labelled **Operator - All**, and finally Mixed (non-Ericsson).

**Operator_Vendor** and **Vendor_Operator** stay in sync: selecting values in one selects the same identities in the other. The Scoring report scenarios of Reporting Jobs follow the same rule.

Selecting **Ericsson** and **Huawei** includes only those vendor identities from the selected operators. To include an operator with no assigned vendor, also select its **Operator - All** choice, or leave the Vendor filter unrestricted. Vendor mapping stores the suffix in `Operator_Vendor` and `Vendor`; legacy operator-only values without it remain supported.

Legacy saved operator-prefixed selections are normalized to vendor names. The **Operator** filter remains independent. When Vendor is a Split by level, operators without a vendor still display **All** in that level; web and PowerPoint retain the existing comparison and reference behavior.

### How the GAP reference is matched

Each comparison retains the selected environment and Split by context. For vendor comparisons, the engine tries the same vendor first, then the reference operator's **All** vendor group.

> [!NOTE]
> **EE / All can be the reference for Ericsson, Huawei and other vendor groups.** Campaign, City, Region and other selected levels must still match. The fallback does not compare different cities or campaigns.

No matching reference or no common valid environment contribution produces **N/A***.

Filter choices use cached CDR catalogues. If an older CDR lacks expected choices, reprocess it to refresh its catalogue.

## Results and workspace settings

### Choose a scoring

The **Scoring** selector, beside Environment, switches the tables, charts, GAP analysis, notes and CSV exports between **Best Network** and **Most Reliable**. It appears when the methodology of the result has Most Reliable points; otherwise the result shows only Best Network. The browser remembers the choice for the session.

### Choose an environment

The **Environment** selector applies to all result tabs and exports. An individual environment shows its own contribution; **All Environments** combines the configured environments.

Each block of results is a card whose top bar has the colours of its tab (see [Results tabs](#results-tabs)). Changing a result option (an operator, the environment, the scoring or the maps) keeps the card being looked at in its place on the screen, and reloading the page returns to the same place once the results, maps included, are drawn.

For the initial NetCheck 2026 allocation:

| Environment | Configured maximum |
| --- | ---: |
| Drive - City | 650 points |
| Drive - Connecting Roads | 350 points |
| Walk | 0 initial points |
| All Environments | 1,000 points |

Custom methodologies can change these allocations. When the combined result has incomplete coverage, opening a result prefers an available environment with complete coverage. You can still select All Environments.

### Choose a theme

The **Theme** selector, at the start of the floating section bar of the page (always in sight while reading it), gives every chart and table of the results its colours and the design of its Scoring and GAP cells, and the PowerPoint and Word exports with them. **Ericsson** is the default. One theme serves every themed module (Scoring & GAP Analysis, Network Insights, CDR Analysis and PPT Dashboards): choosing it in one module chooses it in all of them, each from the start of its floating section bar. Every theme is light except **Midnight**:

| Theme | Colours | Scoring and GAP cells |
| --- | --- | --- |
| **NetCheck** | As the NetCheck reports: blue titles, white lists with thin rules, operators on strips in their colour, amber Voice and teal Data, a bold total | Excel-like data bars as long as the share of the maximum, in the colour of the score band |
| **Umlaut** | As the umlaut benchmark reports: bold dark titles over a red headline, white lists with thin rules, light grey panels and quality classes from red to green | Bars as long as the share of the maximum, in the colour of the score band |
| **Ericsson** | The colours of the Ericsson brand guide: its greys, table headers in its deep blue (the Scoring and GAP tables headed in white, each operator in dark ink), the light tints of its colours for the fills and its deep shades for the ends of each scale; dark grey rules opening the sections and closing the table, each operator ruled in its colour across all its columns | Square cells filled as far as the share of the maximum, in the colour of the band in the legend; GAPs in dark grey after a small ▲ or ▼ in their colour, over a bar either side of zero |
| **Vodafone** | Vodafone red and anthracite, operators as pills in their colour, a dark grey total | Rounded pills in the colour of the score band in the legend |
| **Midnight** | The dark theme: night-blue panels with light text and neon accents; in the PowerPoint and Word exports the content slides are night blue with the logos in white, and every table, card, panel and chart on them is dark | Dark cards with a glowing bar of the share of the maximum |
| **Paper** | A typeset report: serif type, black rules, italic small-capital sections | Scores underlined in the colour of their band |
| **Heatmap** | Light panels with a red, amber, green and teal heat scale and outlined subtotals | Soft tiles tinted by the share of the maximum on the scale of their band |

Each theme also styles the titles and subtitles of every content slide of the PowerPoint and Word exports (the covers and transitions keep the Vodafone-Three style of the template):

| Theme | Titles | Subtitles |
| --- | --- | --- |
| **NetCheck** | Montserrat, blue, the first part in light capitals and what tells the slide apart in bold (*BEST NETWORK SCORING* **per Category**) | Blue, their first part in bold |
| **Umlaut** | Arial, bold, dark | Red |
| **Ericsson** | Ericsson Hilda Light in black, not bold; only what tells the slide apart from the next ones in Ericsson Hilda, bold and in the deep Ericsson blue | Grey |
| **Vodafone** | Vodafone Rg, bold anthracite, what tells the slide apart in red | Anthracite |
| **Midnight** | Segoe UI, bold and light on the night-blue slide, what tells the slide apart in cyan | Cyan |
| **Paper** | Georgia, black, what tells the slide apart in dark red italics | Dark red italics |
| **Heatmap** | Segoe UI, bold, what tells the slide apart in teal | Grey |

A computer without the font of a theme shows its titles in a similar font. A chart or table on several slides of a composed document (*· 1/2*) keeps the plain heading and its part in bold.

In every theme a GAP is a bar either side of zero as long as the GAP: red (or the loss colour of the theme) to the left when the operator is behind the reference, green (or its gain colour) to the right when it is ahead; the GAP bars of the KPI GAP Profile and the other insight tables grow the same way, and points lost always grow from the left. In every table the header of a column is aligned like its values (right for numbers), so each column visibly ends where its header does. The National & Geographical Areas table, the scale of the Points Lost Map (yellow to red in NetCheck, blues in Ericsson, reds in Vodafone, cyan to pink in Midnight, sepia to oxblood in Paper, teal to red in Heatmap) and the tables of the exports follow the theme too. A theme also colours the best and worst operators of the Summary, Voice and Data, the points behind and ahead of the reference, positions, the maximum score allocation donuts (whose outer ring of environments never repeats a colour of the inner ring of Voice and Data or KPI categories) and the slide titles. Operator colours always come from the [Operator Maps](workspace-config.md#operator-maps). The page keeps the theme each user chooses in each workspace, and the choice is registered in App Events. **Export Selected Scoring Report (PPT/Word)** uses the theme of the page; the report editor has its own **Theme** selector (see [Report scenarios](#report-scenarios)). [Network Insights](network-insights.md#theme) offers the same themes, chosen apart.

### Area, operators and vendors of each chart and table

The title of every chart and table of the results tabs (Campaign Comparison, the KPI GAP Profile and the Points Lost Map included) ends with three pills: the **area** it shows, its **operators** and its **vendors**, so a copied chart or table still tells them, also in its larger view. The PowerPoint and Word reports name them at the end of the subtitle of each chart and table slide (smaller when the subtitle would not fit on one line).

| Pill | From… | For example |
| --- | --- | --- |
| **Area** | The City, Cluster or Region of the comparison context, or of the location chosen in the section (such as the KPI GAP Profile, the Points Lost Map or the Summary); else the City filter of the Saved Filter (or else its Cluster or Region filter, the most specific one); else `National` | `City: London`, `Cities: Leeds & London`, `Cities: Bristol, Cardiff & 2 more`, `Region: Wales`, `National` |
| **Operators** | The Operator filter, else `All Operators` | `Operator: EE`, `Operators: EE, O2 UK & 2 more` |
| **Vendors** | The Vendor of the comparison context, else the Vendor filter (vendors without their operator, as on the Saved Filter cards), else `All Vendors` | `Vendor: Nokia`, `Vendors: Nokia & Ericsson` |

A list of more than three values keeps the first two and counts the others; hover a pill for all of them. In the PowerPoint, a KPI GAP Profile or Points Lost Map slide that already names its location (for example `City: London · Campaign: 2026-Q2`) does not repeat it. The National & Geographical Areas card shows every area and has no pills.

### Results tabs

| Tab | What it holds |
| --- | --- |
| [**Summary**](#summary) | Where each operator stands, its position in every environment and service, the biggest levers and how the measurements ran |
| [**Scoring Charts**](#scoring-charts) | The scoring per Service, per Category and per Category (Breakdown) and the maximum score allocation |
| [**Scoring Tables**](#scoring-tables) | The Summary and Breakdown tables and the Campaign Comparison |
| [**Geographical Areas**](#geographical-areas) | The scoring per City, Cluster or Region (of the Breakdown and Separate cities of the Geographical Areas & Scoring Trends, on the whole country), the locations ranked and each operator against the reference per location |
| [**Scoring Trends**](#scoring-trends) | The Scoring Trend and the National & Geographical Areas Trends, with the campaigns of the Scoring Trends |
| [**GAP Analysis**](#gap-analysis) | The GAP tables, the GAP by part of the scoring and the KPI GAP Profile |
| [**Points Lost**](#points-lost) | Where the points go, the points lost per KPI, the Points Lost Map and the points lost per Vendor, per kind of site, per site and along the Connecting Roads |

Opening the page starts on **Summary**; reloading it keeps the tab shown. The menu of the Scoring & GAP Analysis tab lists the seven tabs beside Scoring & GAP Results, and the sections bar of the page does too.

A section with several operators has **Operators** chips: every operator compared with the reference is chosen by default (in the Summary, every operator, the reference included), clicking one enables or disables it (its tooltip says so) and one always stays enabled. **Export Selected Scoring Report** shows in each section the operators enabled on the page. When the results have several locations or Vendors, a selector chooses the one shown (for example **City: London**), the first by default; sections listed per campaign offer the campaigns chronologically, the latest chosen by default. These choices are kept when the page is reloaded (opening the page again starts from the defaults). Throughout the tabs, in the NetCheck theme, a GAP or a loss behind the reference is red and a lead green, Data points are teal and Voice points amber; the other themes give them their own colours (see [Choose a theme](#choose-a-theme)).

### Summary

| Section | What it shows |
| --- | --- |
| **How the measurements ran** | The **Reference & Other Campaigns** (the latest campaign, with the others scored), the first and last day of tests and the days with tests, the cities and Connecting Roads routes, the environments with their points and, per operator, the Data tests, calls and Speech samples scored in each environment of the latest campaign |
| **Where to act** | For the operator chosen in **Operator** (the first compared operator by default; it also chooses Where to act, by performance owner, the places ranked and the route that loses most): a headline and the themes that hold its points lost, the most first (Voice calls, Failed data tests, Below-par data tests), each with what to do (the points of the failed tests and the KPIs that lose most, each with the points of the scoring it loses against its maximum, not the GAP to the reference of GAP Analysis; every figure of points stands out in bold in the loss colour of the theme, as on the slides) and the view of the results to open (the **Deep-dive** column: Points lost per KPI of Voice or Data, Sites to review or Route stretches, each a link that opens its section of **Points Lost**), then the **Sites to review** (the first one to review) and the **Route stretches** (the route that loses most and its first stretch) |
| **Where to act, by performance owner** | A card per performance owner (the Regions of the CDRs, such as Vendor A, Vendor B, VMO2 North and VMO2 South) in a colour of the theme, the same on every view and slide (VMO2 North, VMO2 South, Vendor B and Vendor A take its first four colours, other owners the next ones by name): its points lost, its main issue (the setting that holds most of them and the points of each environment), its two biggest areas, its High priority sites and where its points are (Cities, Towns, Roads and railways; a Saved Filter calculated before these were kept asks to be recalculated with **Recalculate**) |
| **Where each operator stands** | For the latest campaign: every operator ranked by its score, each a bar of its Data and Voice points with its total and its change since the previous campaign. Below, per chosen operator, its score and position, its GAP to the reference split into Data and Voice, how far it is behind the operator above it and ahead of the one below it, its GAP to the reference in every part of the scoring (as in [GAP by part](#gap-by-part)) and a sentence that sums it up |
| **Position in every environment and service** | Per chosen operator, a matrix of every environment and All Environments by Voice, Data and Overall: each tile is its position among the operators measured (green for the first, light green for the second, light red in between and red for the last) and its share of the points available, and the bar under it the points it missed of those available. All Environments scales the environments measured to the full maximum, as the scoring per location does |
| **Biggest levers** | Per chosen operator, the KPIs where matching the reference wins most points (up to 8), with both values and the points to win |
| **Cities ranked**, **Towns ranked**, **Roads ranked**, **Railways ranked** | The places of the latest campaign (big cities, medium and small cities, connecting roads and train routes, from `G_Level_3` and `G_Level_2`) ranked by their share of the points (85% or more in the High colour, 75–85% Medium, under 75% Low), with their performance owners and their share of the tests, *(drive + walk)* when both were measured, the change since the previous campaign, their Voice and Data shares and their points lost on one bar scale for every ranking; it needs City in Split by |
| **<Route>: where the points are** | The route that loses most (or the one chosen in **Route**): the map of its stretches, drawn as the maps of Connecting Roads (each circle sized and coloured from yellow to red by its points lost, the five with the most numbered with their nearest city beside them, the measured cities around it named) with each circle ringed in the colour of its owner; the points of each owner with its share of the tests (and those whose start cell has no Region); the five stretches with the most points and their main owner, and what to review first |

The points lost of these views are the points of the scoring lost against the maximum of each KPI (not the GAP to the reference of GAP Analysis); a calculation split by City, Cluster or Region scores each place on the whole maximum, so the points of each place count by its share of the tests (national estimates) and the views add them up. They need the Saved Filter calculated with this version to tell Cities from Towns, name the owners and the cities around a route (older results rank the places as Cities and routes as Roads).

The days of the tests and the test counts are kept by calculations made with this version; older results leave out the days and count the KPI samples instead until they are calculated again.

### Scoring Tables

| View | What it shows |
| --- | --- |
| **Summary** | Category totals and the weighted score total |
| **Breakdown** | Each category as a section with its subtotal, then its KPIs |
| **Show KPI values** | Measured KPI values in Breakdown, before the Score columns |
| **Show GAP values** | GAP columns at the end or next to each compared operator's score |

The Scoring and GAP tables read as a scorecard: the header starts with the operators (in their colour); each group below them (a route, city or campaign, when the results are split by more than one level) is ruled under its name and set apart from the next one by a gap (a line in PowerPoint and Word), so each one shows where it ends; each category opens a section with its subtotal (or its number of KPIs in the GAP tables), and each KPI shows the badge of its type (**R** for Reliable, **D** for Diff) with its weight and maximum points, in place of Category, Type of KPI, Score weight and Max score columns. When the KPIs are ordered by GAP, their categories are no longer together and each KPI carries its category instead. The weighted total closes the table. The PowerPoint and Word tables have the same design.

Summary highlights the highest and lowest valid scores **across the whole displayed row**, each inside the box of its cell. Tied extremes can highlight several cells. Equal scores, or fewer than two valid scores, remain neutral.

Breakdown scores take the colour of their **Low**, **Medium**, **High** and **UltraHigh** bands and show their share of the maximum points as the theme draws it (see [Choose a theme](#choose-a-theme)). The legend of the bands shows each band as its cells look in the theme, on the page and in PowerPoint and Word: Ericsson and Vodafone fill their cells with the colours of the legend, NetCheck and Umlaut draw it as their data bars, Heatmap as its tints, Paper as its underlined text and Midnight as its glowing bars. Category totals remain neutral. Raw measurements are not summed across different KPIs because their units differ. The bar of each GAP is as long as the GAP against the largest GAP of its table, so small GAPs stay quiet and only the large ones stand out.

GAP visibility starts unchecked. It affects Scoring Tables and its PowerPoint tables; dedicated GAP Analysis views remain available.

**Campaign Comparison** appears below the tables when Campaign is a Split by level with at least two campaigns. Choose the **Operator** (with each combination of the other levels), the **Baseline campaign** and the **Compared campaign** (by default the previous and the latest campaigns): the table, across the whole card, lists every KPI with its value and points in both campaigns and **Δ Points** (compared minus baseline), from the largest loss to the largest gain in a red–green scale, with the total **Scoring Points Gap**. The PowerPoint and Word exports compare the two latest campaigns.

### GAP Analysis

**GAP = compared operator weighted points − reference operator weighted points.**

| Value | Meaning |
| --- | --- |
| Positive / green | The compared operator leads the reference |
| Negative / red | The compared operator trails the reference |
| Zero | Equal weighted points |
| **N/A*** | No valid comparison is available |

**GAP comparison** offers **All vs reference** and each individual operator. Individual comparisons order KPI rows from lowest to highest GAP in the latest campaign (with several campaigns; the other campaigns break ties), with the KPIs unavailable in it last, on the page and in the PowerPoint and Word exports. All Operators retains KPI definition order. Saved GAP priorities do not control this display order.

Every GAP table ends with **Total KPI GAP**, the sum of the valid KPI GAPs in **each column separately**, in web and PowerPoint.

Individual PowerPoint slides also show:

| Side note | Calculation |
| --- | --- |
| **Average KPI GAP** | Mean of all valid KPI GAP cells displayed on the slide |
| **Average total KPI GAP** | Calculate each column's KPI sum, then average those column totals |

Columns represent combinations of the selected levels, such as City and Campaign. Columns without any valid GAPs are excluded from the mean of totals.

> [!IMPORTANT]
> **Do not apply KPI weights again to GAP points.** Each KPI GAP already subtracts weighted scoring points. Totals sum those points; averages use them directly.

**Example — two campaign columns:** Q1 totals −51.64 points and Q2 totals −87.08 points. The **Average total KPI GAP** is `(−51.64 − 87.08) / 2 = −69.36 points`. This differs from the mean per KPI.

#### GAP by part

Below the GAP tables, **GAP by part of the scoring over the campaigns** gives, per chosen operator, its GAP to the reference in every part of the scoring in the latest campaigns (up to six), with the total and, with several campaigns, a bar of the latest one; each cell is shaded red behind the reference and green ahead. With the NetCheck methodologies, whose KPIs are typed Reliable or not, the parts are the **reliability** of Voice and Data (calls and tests that complete, POLQA below 1.6, the lowest throughputs) and their **quality** (speeds, times, speech quality and the higher thresholds); with other methodologies, each category.

#### KPI GAP Profile

Below them, **KPI GAP Profile** first chooses the location (for example **City: London**, when the results have several; campaigns are listed chronologically, the latest chosen by default) and then one or more **Operators** (all of them by default; choosing an operator in **GAP comparison** above shows that one, and GAP comparison follows a single chosen operator). Each chosen operator other than the reference gets a table of its **GAP to <reference>** per KPI (operator points − reference points, per environment and in total), two operators side by side. The KPIs are grouped by category, the categories furthest behind first, each with its subtotal. The points each operator loses against the maximum are in [Points lost per KPI](#points-lost-per-kpi). The location and operators are shared with **Points lost per KPI** and the **Points Lost Map**, and they are kept when the page is reloaded (opening the page again starts from the defaults).

The columns are the environments of the selected environment (each environment of All Environments) and **Total**. Every column has its own data bars, red below zero and green above, which fade from the colour to white like Excel data bars, with the value written over them. Each KPI starts with the **R** (Reliable) or **D** (Diff) badge of its type, as in the Score and GAP tables; the Reliable KPIs are the ones of the Most Reliable scoring. The note below names the total GAP of each operator to the reference.

### Points Lost

| Section | What it shows |
| --- | --- |
| **Where the points go** | For the latest campaign, the points each operator loses split by how it loses them: **Failed tests** (the Reliable KPIs: calls and tests that did not complete, POLQA below 1.6, the lowest throughputs), **Below the threshold** (tests that passed but under the threshold of a KPI, such as a setup over 10 s or under 5, 20 or 100 Mbit/s) and **Quality shortfall** (what the averages, medians and 90th percentiles miss of their best score), as bars and as a table; hover a bar for the KPIs that lose most |
| [**Points lost per KPI**](#points-lost-per-kpi) | The points each chosen operator, the reference included, loses against the maximum of every KPI |
| [**Points Lost Map**](#points-lost-map) | Where each operator loses its points, per City, Region or Cluster |
| [**Per Vendor, per kind of site, sites and stretches**](#points-lost-per-vendor-kind-of-site-site-and-stretch) | The points lost shared among the cells that served the tests |

#### Points lost per KPI

Per chosen operator, the reference included, a table of the points it loses per KPI (KPI maximum points − points scored, per environment and in total), grouped by category, the categories that lose most first, two operators side by side, with red data bars in every column and the **R** or **D** badge of each KPI. It shares the location and **Operators** of the KPI GAP Profile and the Points Lost Map, and its note names the total points each operator loses.

#### Points Lost Map

Below the points lost per KPI of All Environments and of each environment, **Points Lost Map** shows where each operator loses its scoring points. It uses the location and **Operators** of the KPI GAP Profile and the points lost per KPI (choosing them in one section chooses them in all; clicking an operator enables or disables it, as its tooltip says, and one always stays enabled; several operators show their maps side by side, the reference operator among them), and adds **Maps per** **City**, **Region** or **Cluster** (an option without data in the results, such as Cluster without Clusters, is shown disabled). Each map is headed by its operator, large and in its colour. Drag a rectangle over a map to zoom into it, or use the zoom buttons (zoom in, zoom out, whole map) shown while the pointer is over the map.

With **Maps per** City, **Colour areas by** (one choice above every map) chooses how the map areas are coloured:

- **Points of the city or route that loses most in each area** (the default): each area takes the whole points of the city or Connecting Roads route that loses most among those measured in it (a city or route belongs to every area holding at least 2% of its tests), so a whole route takes its colour and London colours every London area.
- **Points lost in each area by the city or route that loses most there**: each area takes the points really lost in it by the city or route that loses most there, so a route shows where along its way it loses its points, and a city spread over many small areas, such as London, colours each one with what it loses there.

In All Environments, the **Type** column of the ranking under each City map names, in short (for example City or Roads; hover it for the full name), the environments where each city or route loses points; per Region or Cluster it does not, since they hold tests of every environment. Each area keeps its colour while rows or areas are chosen (the others are only dimmed), and changing **Colour areas by** keeps them chosen, so both colourings can be compared.

Click a row of the ranking to show its areas alone on the map, which centres and zooms on them; Ctrl/⌘-click adds or removes single rows and Shift+click chooses every row from the last one clicked. Click an area of the map, or hold Shift and drag a rectangle to choose several, to leave lit the rows measured there and dim the others. Clicking the same choice again, clicking outside every area or pressing Esc shows everything again. In All Environments the ranking names, beside each area, the environments where it loses points (most first).

| View | Map | Ranking |
| --- | --- | --- |
| **per City** | The **map areas** of the countries of the tests, coloured from yellow to red as chosen in **Colour areas by**: the [Map Areas](workspace-config.md#map-areas) of the workspace or the ones shipped with the application for its main markets (for example the UK **ITL3 areas**, the NUTS3 level, the provinces of Spain or the counties of the USA), and the whole country for any other; hover an area for its points and its cities and routes | The cities (`City`, or `G_Level_4`) and Connecting Roads routes (for example *Sheffield to Leeds*) that lose most, with their points and share |
| **per Cluster / Region** | The polygons of the workspace's **Clusters** or **Regions** dataset applied to the CDRs, coloured the same way | The clusters or regions that lose most |

How the points are placed: each KPI loses its maximum points minus the points scored, and the loss is shared among the tests that cause it. For ratio KPIs every test that misses the KPI (a failed call, a POLQA below 1.6, a transfer below its threshold…) weighs one; for averages, medians and P90 each test weighs what it misses the KPI's High threshold by; for packet loss, the packets lost. Each test belongs to the City of its CDR row (a Connecting Roads route is a City value such as *Manchester to Sheffield*, with every test of the drive between both cities) and to the map area of its country that contains its coordinates (kept in the rows of its CDR, see [Map Areas](workspace-config.md#map-areas)), and the result keeps the points each city or route loses in each area. A country without Map Areas is coloured as one area, the whole country, and a note above the maps names it. The map uses the same points as the selected scoring (Best Network or Most Reliable); calculate the Saved Filters again after adding Map Areas; results calculated before this version only offer the first way of colouring.

The sources and licences of the areas shipped with the application, such as the ITL3 boundaries of the Office for National Statistics, are listed in `assets/map-areas/README.md`. To map your own clusters, import a Clusters GeoJSON in Workspace Management and apply it to the CDRs before calculating: the job keeps a simplified copy of its polygons.

#### Points lost per Vendor, kind of site, site and stretch

The points lost of each test are also shared among the cells that served its start, from the serving cells the CDRs get from the [Vendor Mapping](workspace-management.md#vendor-mapping) with Network Inventories (`Vendor`, `Serving_Network`, `Serving_Host_Network`, `Serving_eMOCN_Scenario` and `Serving_Site_ID`), with the scope and **Operators** of each section:

| Section | What it shows |
| --- | --- |
| **Points lost per Vendor of the serving cell** | Per operator, the points lost on the cells of each RAN Vendor with their share of the points lost and of the tests of the operator, the environments where they are lost and the cities and routes that lose most; **Not identified** gathers the tests without a serving cell in the inventories |
| **Points lost per kind of serving site** | The same per kind of site: the network that owns it and, when another network hosts its RAN, *on* that network (Beacon, MORAN), with the NNS sites apart |
| **Sites to review** | Per operator, the sites that lose most (up to 25) with their network, Vendor, city or route, points lost, failed tests (the calls and tests that missed the Reliable KPIs) and points lost in the earlier campaigns. **High** priority: 1 point or more lost and losses on the same site in an earlier campaign; **Medium**: one of the two; **Low**: neither |
| **Connecting Roads: where along each route the points are** | Per operator and route (the six that lose most), a map of the route on the map areas (ITL3 in the UK) with the measured cities around it named and a circle per stretch of about 20 km whose area and colour (from yellow to red, on the scale of the theme) tell its points lost; the stretches that lose most (up to eight) are numbered on the map with the nearest city of the measurements beside them (for example *14 km north-east of Leeds*) and listed with their main Vendor. The Route stretches slides draw the same map |

On both route maps (Connecting Roads and *<Route>: where the points are*), choosing a stretch in the table beside the map zooms the map in on it and rings its circle; choosing it again, or **Whole route** on the map, shows the whole route again. Double-clicking a route map opens it larger, as the other maps, charts and tables of the results. Every **Operator** selector and list of operators of the results follows the order of the Operator Maps.

A share of the points lost well above the share of the tests is red. These sections need results calculated with this version from CDRs with serving cells: older results show a note asking to calculate the Saved Filter again.

### Scoring Charts

| Chart | Use it to… |
| --- | --- |
| **Best Network / Most Reliable Network Scoring per Service** | Compare total points and Data/Voice contributions; Data stacks below Voice |
| **Best Network / Most Reliable Network Scoring per Category** | Compare category contributions within each operator/context stack |
| **Best Network / Most Reliable Network Scoring per Category (Breakdown)** | Compare operators directly within each category |
| **Maximum score allocation donuts** | Inspect configured environment, service and category maxima and shares |

Voice and Speech KPIs contribute to **Voice**; Data KPIs contribute to **Data**, regardless of category names. Allocation donuts show **maximum available allocation**, not earned scores. Chart titles and donuts follow the selected scoring.

Hover bars, segments, totals or donut sectors for values and context. Double-click a chart, a map or a table of Scoring Tables and GAP Analysis to open it larger, taking the whole screen but 5% on each side; a chart shows there whole, however wide it is on the page. Charts and maps zoom into a rectangle dragged with the mouse, or with the zoom buttons (zoom in, zoom out, whole view) shown while the pointer is over them (on touch screens, a tap shows them for a few seconds, until a tap elsewhere), also in the larger view. A chart with more bars than fit its card is fitted to the card when its bars and labels keep at least three quarters of their size, and otherwise keeps its size and scrolls horizontally: zoom out narrows it by steps down to the width of the card (the whole chart, more compressed), zoom in widens it back to its size and then zooms into it, and whole view fits it to the card. Operator Mapping supplies labels, order and colors.

A single Split by level uses normal axis labels; multiple levels use separate header rows. Campaign labels display year-quarter, such as **2026-Q1**, while stored campaign names and CSV identifiers remain unchanged.

### Geographical Areas

| Section | What it shows |
| --- | --- |
| **Scoring per City / Cluster / Region** | When City, Cluster or Region is a Split by level with 2 to 12 values: one card per value with its operators from the highest score, each a bar of its Data points (teal) and Voice points (amber) with its rank, its total and, behind the first, its distance to it, labelled with the operator names of the mapping table (hover a bar for its points) |
| **Cities and routes ranked** (or Clusters, Regions) | Per chosen operator, every location of the latest campaign from its highest share of the points available (**Points %**), with its change since the previous campaign, its Voice % and Data %, its points lost and, when the tests have serving cells, the Vendors of the cells that served them. **Geographical Areas** chooses City, Cluster or Region and **Group** the combination of the other levels |
| **Each operator against the reference per location** | Per chosen operator other than the reference, its GAP to it in each location, overall and in Voice and Data, in points of percentage of the points available, as bars to the left (behind) or to the right (ahead), from the location furthest behind |

The cards and rankings follow City first, then Cluster, then Region, and group the other levels: with several campaigns, one set of cards per campaign shows the latest one. In All Environments each card adds the environments measured in that location and scales them to the full maximum (1,000 points in NetCheck 2026), so a city measured only in Drive - City is comparable with the others, as the NetCheck per-city rankings do; the note above the cards says so and gives the maximum and its Voice and Data parts. A single environment shows its own points.

Whatever the Split by, the tab shows the areas of the **Geographical Areas** of the calculation panel: each area of the **Breakdown** and each of the **Separate cities** (when its CDRs have tests there), scored on the whole country with the filters other than Region, Cluster and City, so it shows the cards and ranking of the breakdown and the card of each of those cities. A Saved Filter calculated before is calculated again when it is opened; results calculated before this show a note to calculate them again. From the Scoring History these calculations add about a second; from the CDR rows they take about as long as the scoring itself, unless the calculation (without area filters and split by the same levels) or its National & Geographical Areas Trends (with the campaigns of the calculation) already scored them, whose calculations they then reuse.

### Scoring Trends

The charts of this tab use the campaigns and time split of the **Scoring Trends** of the Geographical Areas & Scoring Trends panel (the campaigns of the Campaign filter when it has none), whatever the campaigns of the other tabs, and the areas of its **Geographical Areas**.

| Section | What it shows |
| --- | --- |
| **Best Network / Most Reliable Network Scoring Trend** | With two campaigns or more: each operator's total points per campaign, one line per operator ending in its name and latest score (the reference thicker), with the latest campaign shaded. With campaigns of its own it comes from the National scoring of those campaigns (or of the periods of the time split of the National & Geographical Areas Trends); otherwise it offers one series per combination of the other Split by levels in its selector, with the same points as the scoring per location |
| **Best Network / Most Reliable Network Trends — National & Geographical Areas** | The National scoring, then each area of the breakdown (Regions or Clusters), then the cities, each group with its names in its own colour (as the titles of its charts) and a thick rule between groups, with each operator's score in the latest campaign or period, its change from the previous one and its GAP to the reference, and a trend chart per area on the same scale, as tall as the table beside them (labels tilted when they do not fit), titled in one colour for National, another for the breakdown and another for the cities; a double click on a chart or on the table enlarges it alone (a single separate city next to National, several after the breakdown). An area not measured in the latest campaign or period is listed without a score, and its chart shows the earlier ones |

Without two campaigns or periods, the tab says how to get them.

### Incomplete coverage and achievable scoring

The pale yellow **Calculation notes** card lists affected combinations, missing KPI names and the **exact maximum achievable score** after excluding their unavailable contributions.

> [!WARNING]
> **Missing points are not redistributed.** An incomplete result keeps the original weights and configured benchmark maximum. Available contributions are not scaled up to a complete score.

**Environments without results in any series are scaled.** When the filters leave an environment without results for every operator and series of the calculation (for example, City = London only covers Drive - City), the Combined scores use the environments with results and scale them to the full maximum scoring: an environment without results gets 0 points and the others share its points in proportion, the same for every operator, so GAPs stay comparable. An orange **Scaled results** card explains which environments were scaled and the factor applied; scaled values are not marked as incomplete. The *Maximum score per environment* donuts show the configured points of every environment struck through beside the points finally allocated, and the PowerPoint and Word exports show the same notice in orange on their first page. When an environment has results in any series it is never scaled, and the series without it keep their partial score and their notes. Saved results are scaled when they are opened, without calculating them again.

Example: **VF_UK / Samsung / Q1: maximum 583.2645 of 650 points**, with the unavailable KPI names listed below. Another campaign can have a different achievable maximum because different KPIs are missing.

- Incomplete numeric values appear **in bold red with `*`**.
- Unavailable values appear **as N/A*** in the same style.
- Total KPI GAP sums available contributions and carries `*` when a contribution is missing or partial.
- All Environments GAP uses valid environment contributions common to both sides. A subset is partial; no common contribution is unavailable.
- Tooltips explain partial GAP coverage; PowerPoint slide notes include the coverage details.

All Environments raw KPI values are calculated from pooled source rows, not averaged from environment KPI values. Older results without these saved measurements show N/A until recalculated. Weighted scoring points still sum the separately calculated environment contributions.

## Methodology

A methodology contains the complete environment, KPI, weighting, threshold and priority setup. Open **Workspace Config → Scoring & GAP Analysis Setup** to edit it; the **Scoring Methodologies** shortcut of the Calculation and Results panels opens it directly. The aggregation hierarchy is not part of a methodology (see [Set filters, aggregation and reference](#3-set-filters-aggregation-and-reference)).

### Named methodologies and portable JSON

Open **Workspace Config → Scoring & GAP Analysis Setup**. Select a methodology or use **Create Methodology** / **Duplicate Methodology** to prepare another one.

The selector's name identifies the methodology. **Methodology title** is an optional editable description preserved in transfers.

#### Methodologies by campaign

**Applies to campaigns** gives the campaigns a methodology was made for: choose its first campaign in **From** and its last one in **To** among the quarters of the workspace's campaigns, or **No start (every earlier campaign)** and **No end (every later campaign)** to leave either end open; **Save Methodology** saves them with the rest of the methodology. The campaigns of two methodologies cannot overlap, so each campaign has one methodology. With no start and no end the methodology is not tied to any campaign. For example, **NetCheck 2026** with No start to 2026-Q2 and **NetCheck 2026-Q3** from 2026-Q3 to No end.

A calculation **By campaign** scores each campaign with the methodology whose campaigns include it (by year and quarter) and the other campaigns with the default methodology. Each campaign then totals the full score of its own methodology, and a KPI that only some methodologies have (such as TikTok from 2026-Q3) appears only in their campaigns. The campaigns of each methodology are exported, transferred and backed up with it.

#### One complete save

The toolbar and the sibling panels offer the same **Save Methodology** action:

| Panel | Settings included in the save |
| --- | --- |
| **Methodology Environments** | All environments, allocations, KPI specifications and thresholds |
| **Methodology KPIs Priorities for GAP analysis** | Saved priority order |

> [!NOTE]
> **Save Methodology commits all pending settings together.** The buttons are convenient entry points to one complete save, not separate panel-specific saves. The shared status above the panels indicates saved or pending changes.

Selecting a methodology does not change the workspace default. **Set Default** chooses the methodology initially offered for future calculations. You can choose another saved methodology for each calculation.

The default methodology cannot be deleted until another is set as default. Saved results keep their captured rules; opened again after the methodology is edited, they are calculated with its new rules, and after it is deleted they are shown as they were.

#### Save versus export

| Action | Scope | Result |
| --- | --- | --- |
| **Save Methodology** | Open methodology and all pending edits | Writes to the workspace database |
| **Export Methodology (JSON)** | Selected saved methodology | Downloads a one-methodology document |
| **Import Methodology (JSON)** | One methodology or a collection | Adds IDs and replaces matching IDs after confirmation, preserving other methodologies and the existing default |
| **Admin Scoring & GAP Analysis Methodologies export/import** | Complete collection and default | Transfers the workspace's methodology setup |
| **Configuration backup / restore** | Included scoring configuration component | Preserves/restores the collection and default |
| **Workspace database backup / restore** | Whole workspace database | Also preserves the Saved Filters with their results and the local calculation selections |

> [!TIP]
> Save pending edits before exporting. Duplicate a methodology before revising a benchmark, and export or back up the collection before replacing it through Admin.

The editor import merges by methodology ID. Duplicate names with different IDs are rejected. Collection replacement through Admin replaces the destination collection; review its contents first.

### Configure environments

An environment defines **which CDR rows to include** and **how many points its KPIs can contribute**. It belongs to the selected methodology.

#### Source-row matching

Select the environment and use **CDR filters**:

| Field | Meaning | Example |
| --- | --- | --- |
| **G_Level_1** | Required first-level source value | Drive |
| **G_Level_2** | Optional second-level source value | City |

With Drive and City selected, only rows matching **both** values are included. Leaving G_Level_2 empty includes every second-level value for the selected G_Level_1.

These source values are different from geographic Region/City filters. Changing an environment's display name does not change its matching rule.

> [!WARNING]
> **Environment source rules cannot overlap.** Two environments cannot select the same first/second-level combination. An unrestricted second level also conflicts with a narrower environment using the same first level.

Available choices come from ready workspace CDR catalogues. Saved source values remain selectable even when absent from current CDRs. Configuration exports carry the selected values; available choices at the destination come from its own CDRs.

#### Create, rename or delete

1. Use **Create Environment** and enter its name, reference environment, points and source filters.
2. The new environment copies KPI thresholds and relative shares from the reference.
3. Review the copied rules, then **Save Methodology**.

**Rename Environment** preserves KPI contexts, weights, thresholds and source filters. Historical numeric results stay unchanged; supported result views can display the current environment name.

**Delete Environment** removes its contexts from the draft. Keep at least one environment and a positive overall allocation. Names must be unique, ignoring case; **Combined** is reserved.

> [!WARNING]
> **Copied thresholds need review for their new context.** The initial Walk environment has zero points and City-derived rules. Validate it before assigning benchmark points.

#### Environment allocation

| Edit mode | Effect |
| --- | --- |
| **Points** | Set the environment's absolute allocation |
| **Weight (%)** | Change its share while preserving the grand total and redistributing other environments proportionally |
| **Distribute points keeping percentages** | Allocate a chosen total using a reference environment's relative KPI shares |

Distribution changes points, not formulas or thresholds. Relative shares can be edited and retained even when an environment has zero points.

### Editing, replacing, adding and removing KPIs

#### Edit a definition

1. Select the environment.
2. Expand the pastel red **KPI Definitions, Scoring & Thresholds** subpanel.
3. Edit the definition and its environment-specific scoring settings.
4. Save the complete methodology, then calculate or recalculate the scoring.

| Setting | What it controls |
| --- | --- |
| **Code** | Stable identity and priority references |
| **KPI / Category** | Display labels and grouping |
| **Source** | Data, Voice or Speech CDR rows |
| **Formula / filters** | Measurement and eligible source rows |
| **Direction** | Whether higher or lower measurements are better |
| **Mapping** | Linear, Quadratic or Smooth curve interpolation |
| **KPI Type** | Reliable / Diff classification; Reliable KPIs form the Most Reliable scoring |
| **Max points / weight** | The KPI's contribution to the environment in the Best Network scoring |
| **Most Reliable points** | The maximum points of a Reliable KPI in the Most Reliable scoring; editable only on Reliable KPIs |
| **Thresholds / score anchors** | Measurement boundaries and normalized score awarded at each boundary |

KPI Type does not change the formula, mapping or GAP arithmetic; it only decides which KPIs take part in the Most Reliable scoring. Calculation basis is read-only information derived from the formula; it does not set the denominator.

#### Points and weights

- **Points:** edit a KPI's absolute maximum.
- **Weight (%):** edit its environment share; the environment total stays fixed and other KPI shares adjust proportionally.
- **Global weight:** read-only KPI points divided by the total points across all environments.

Category totals refresh from their KPI allocations. Setting a KPI to zero points keeps its definition without adding a scoring contribution.

#### Add, move, replace or remove

Category controls move whole categories or insert a category below the current one. KPI row controls insert a definition below that row, move it within its category or delete it.

To replace a KPI, revise its label, formula, filters, source, thresholds and points. If you add a replacement as a new row, remove the old contribution deliberately to avoid counting both.

**Example:** replace `PCT90(Mean_Data_Rate)` with `AVG(Mean_Data_Rate)`, rename the KPI to mean throughput and review its thresholds. Keep or change its FDTT/DL/Completed filters intentionally.

Codes remain stable when rows move. New KPIs receive the next unused K number; deleted codes are not recycled. Renaming a code in the editor remaps its saved priority reference. When editing JSON manually, update `gap_priority` references too.

#### Priorities

The priority editor supports moving a KPI up/down, to the first/last position or to a specified position. Category membership remains visible.

> [!NOTE]
> **GAP priorities are saved settings.** Current individual GAP tables sort by signed GAP, while All Operators uses KPI definition order. Editing priority does not change these display orders.

#### Supported expression language and limits

| Operation | Example |
| --- | --- |
| Average | `AVG(Call_Setup_Time)` |
| Median | `MEDIAN(field)` |
| 90th percentile | `PCT90(Mean_Data_Rate)` |
| Sum / count | `SUM(field)` / `COUNT(field)` |
| Supported conditional ratio | `100 * SUM(Call_Status == "Completed") / COUNT(Call_Status)` |

Conditions support the implemented comparisons, `AND`, `CONTAINS(...)` and `IS NOT NULL`. Filters use JSON objects; values inside a field select its permitted source values:

```json
{
  "Session_Type": ["CALL", "MultiRAB CALL"],
  "Call_Status": ["Completed", "Dropped"]
}
```

The Interactivity packet-error formula has explicit IFNULL behavior for lost, discarded, corrupted and unsent packets. Missing optional loss components count as zero in that formula. `Packets_Sent` remains required and its sum must be positive; missing or zero sent packets produce N/A.

> [!CAUTION]
> **Formulas use a supported expression allowlist.** Arbitrary Python, SQL or Tableau expressions are not executed. Other absent source fields do not become optional because the packet-loss formula supports IFNULL.

Limits: **256 KPIs**, **32 environments** per methodology and **64 methodologies** per workspace. New fields or unsupported operations require engine support, not just a JSON edit.

### Most Reliable Network scoring

NetCheck publishes two rankings. **Best Network** rates every KPI. **Most Reliable** rates only the reliability KPIs (the KPIs marked with `*` in the NetCheck reports, whose KPI Type is **Reliable**), with its own maximum points, and uses the same formulas, thresholds, score anchors and mapping as Best Network: each KPI keeps its normalized score and only its maximum points change.

| | Best Network | Most Reliable |
| --- | --- | --- |
| KPIs | Every KPI with Max points | Only KPIs whose **KPI Type** is **Reliable** |
| Points of a KPI | Normalized score × Max points | Normalized score × Most Reliable points |
| Thresholds, anchors, mapping | The methodology's | The same |
| GAP | Compared − reference Best Network points | Compared − reference Most Reliable points |

#### Configure it

1. Open **Workspace Config → Scoring & GAP Analysis Setup** and the methodology.
2. In **KPI Definitions, Scoring & Thresholds**, set **Type** to **Reliable** for the KPIs of the Most Reliable scoring (the NetCheck 2026 methodology already does) and enter their **Most Reliable points** in each environment (see [Most Reliable reference points](#most-reliable-reference-points)). The column can only be edited on Reliable KPIs. The line above the table counts the Reliable KPIs and their points in the selected environment and in all environments, and warns about Reliable KPIs without points.
3. **Save Methodology**, then calculate or recalculate the scoring.

Most Reliable points are part of the methodology: changing them gives the methodology a different identity, so the saved results of the Saved Filters that use it are calculated again when they are opened. The Most Reliable results are derived from the saved KPI scores of the result, so they never read the CDRs again. A new environment or a new KPI starts without Most Reliable points. A KPI whose Type is not Reliable never takes part, even if it had Most Reliable points (they are dropped when the methodology is saved).

Most Reliable points copied with two decimals can miss an environment's total by a few hundredths (650.02 for 650): when the Most Reliable total of an environment is within 0.1 points of its Best Network total, its Most Reliable points are scaled to match it exactly.

> [!NOTE]
> **Environments without Most Reliable points contribute nothing to it.** The Most Reliable maximum of an environment is the sum of its KPIs' Most Reliable points; All Environments adds them, and [environments without results are scaled](#incomplete-coverage-and-achievable-scoring) the same way as in Best Network.

### Portable JSON reference

#### Envelope and required content

Exchange format **version 3** uses the same envelope for one methodology or a complete collection. Files exported before the rename to DriveTest Analyzer, with the format `dashboard-analytic-scoring-configuration`, are still accepted. A one-methodology export has one item in `profiles`; Admin exports can contain all items.

The internal JSON names `profiles` and `active_profile_id` remain format identifiers. In the interface, these entities are called **methodologies**, and the active ID identifies the default.

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

Environment totals and positive-point relative weights are derived from KPI maximum points, so exports do not duplicate them. Relative shares for zero-point environments are retained.

`most_reliable_points` is optional; omitted or 0 leaves the KPI out of the Most Reliable scoring of that environment. Files without it are still imported and keep their identity.

Reference filenames, workbook cells, denominator descriptions and Tableau grouping keys are not needed for an operational methodology and are omitted. Optional mapping/anchor settings use supported defaults when omitted; retain explicit settings when customized.

Version-2 exchange envelopes must be replaced with a new export. Existing supported workspace records are normalized on read; this is different from accepting an obsolete exchange envelope.

> [!IMPORTANT]
> JSON import/export, ZIP configuration packages, transfers and configuration backup/restore use the same methodology format. The Favourites Filters travel on their own, as the **Scoring & GAP Favourites Filters** element of Admin's Import / Export / Transfer, with Full Workspace transfers and with backups, without their results (each one finds its CDRs by file in the receiving workspace, or, with a Campaign choice such as Latest campaign, takes the CDRs it stands for there, and keeps its name and order); the results travel only with the workspace database. The saved configurations of the report editor travel the same way, as the **Scoring & GAP Report Templates** element (one JSON file; importing it adds new configurations and replaces those with the same name), on top of the editor's **Export JSON** / **Import JSON** buttons. Scoring & GAP Analysis Methodologies packages and backups made before, which carried the Saved Filters and the report configurations, still restore them.

### Reference Prep flow and implemented calculation

#### From raw rows to points

1. Apply environment source selectors and the selected filters.
2. Group raw rows by the selected Operator/Vendor/Region/City/Campaign levels.
3. Calculate each KPI from its formula and source filters.
4. Map the measurement to a normalized score between 0 and 1.
5. Multiply by the KPI's configured maximum points.
6. Sum weighted points for categories, environments and total scoring.

Operator aliases use the mapping snapshot saved with the result. When Campaign is not selected as a Split by level, campaign rows are pooled before KPI calculation.

Unlike the source Prep flow's inner joins, the application preserves groups with missing measurements as N/A and reports their incomplete coverage.

#### Mapping methods and anchors

For normalized position `t` between adjacent measurement thresholds:

| Method | Interpolation fraction |
| --- | --- |
| **Linear** | `t` |
| **Quadratic** | `t²` |
| **Smooth curve** | `3t² − 2t³` |

All methods preserve the configured threshold anchors, direction and score limits. Mapping and Direction are separate settings. The original NetCheck definitions use Linear.

Default NetCheck anchors without Ultra are **Low = 0%**, **Medium = 80%**, **High = 100%**. With Ultra, K20/K25 use **High = 90%** and other supported mappings use **95%**; **Ultra = 100%**. Per-context anchors are editable.

Dynamic best-value Ultra thresholds use all operators in the selected comparison context. Selecting a different operator scope can therefore change a dynamic threshold.

#### Combined environments and coverage

All Environments sums configured maxima and separately calculated environment points. Missing measurements do not reduce the configured benchmark or redistribute their allocations.

Global raw KPI values are recalculated from pooled source rows across configured environments. They are not averages of environment KPI measurements. Zero-point environments can contribute raw measurements without adding weighted points.

> [!WARNING]
> **A zero-point environment does not cause incomplete weighted scoring.** A missing positive-point contribution does. Older results without saved global raw measurements require recalculation to display those values.

#### GAP calculations and aggregates

GAP subtracts **reference weighted points** from **compared operator weighted points** within the same context. Vendor matching can use the reference operator's All group; other context levels still match.

| Result | Calculation |
| --- | --- |
| KPI GAP | Operator KPI points − reference KPI points |
| Scoring category/final GAP | Mean of valid original KPI comparisons |
| GAP table footer | Sum of valid KPI GAPs in each column |
| Individual PPT Average KPI GAP | Mean of valid displayed KPI GAP cells |
| Individual PPT Average total KPI GAP | Mean of the displayed columns' KPI sums |

The overall KPI mean uses original KPI rows, not an unweighted mean of category means. No aggregate applies KPI weights a second time.

For All Environments, only valid environment contributions common to both sides are compared. A subset is marked partial; disjoint coverage or a missing reference gives N/A. Column totals with missing/partial contributions carry an asterisk.




## Scoring History

The **Scoring History** keeps, in the workspace database, the components of every scoring KPI of every ready Data, Voice and Speech CDR, so a calculation does not read the CDR rows again:

- **What it keeps**: the tests of each CDR grouped by day (of their start time), campaign, operator, vendor, environment, Region, Cluster and City (every city, not only the Main Cities), and for each group and KPI of the workspace methodologies what the KPI needs to be calculated again over any set of groups: the sums and counts of its ratios and averages, and a mergeable sketch of the values of its medians and 90th percentiles (approximate, within a quarter of a percent). Scores and points are never stored: they are calculated with the thresholds of the methodology chosen, so any methodology, period (days, weeks, months, quarters, campaigns or years) and area can be scored from the same history.
- **When it is filled**: as a background task, shown in the floating background tasks card (**Scoring History indexing**), after the other background work: as soon as a CDR finishes processing, when the workspace is opened (for the CDRs it does not hold yet) and once nobody has used the application for two minutes (the pages refreshing themselves do not count). A calculation it cannot do yet reads the rows of the CDRs and says why in its progress, for example *(from the CDR rows: the Scoring History is still indexing 3 of its 18 CDRs)*. The Points Lost Map reads only what the map needs from those rows, without calculating the scores again. Each CDR is read once; it is read again only when it is processed again (or its Vendor, Region or Cluster mapping changes) or a methodology adds a KPI it has not indexed.
- **How a CDR is identified**: by the SHA-256 of its whole source file (about half a second per GB, kept until the file changes) and the signature of its processing, never by its name or ID, so renaming a CDR, reordering the IDs or transferring the workspace keeps its history. The history of a deleted CDR is kept as a record; a CDR processed again replaces the history of its former processing. Each source records its stage (Daily, Weekly or Final), campaigns and days, so a Final CDR can supersede the Daily and Weekly CDRs it contains.
- **Calculations from the history**: a calculation whose CDRs are all indexed at their current processing, whose **Split by** uses Operator, Vendor, Region, Cluster, City, Campaign or Dataset Type and whose filters are Region, Cluster, City, Operator, Vendor, Operator_Vendor or Campaign is calculated from the history in seconds, with its National & Geographical Areas Trends (from the CDRs of their own campaigns when they have some). Its scores, tables and charts show at once; the **Points Lost Map**, which needs the rows of each test, is prepared next from the CDRs in a job of its own, **Points Lost Map #N** among the background tasks, after the calculations waiting so they do not wait for it, and while it is drawn it gives way to the work of the workspace queued before it (such as the calculation of another Saved Filter) after the CDR or group of tests it is on, then goes on (the results show *Preparing the Points Lost Map…* and update themselves). Its card shows a progress bar and the step it is on (the CDR being read, such as *CDR 3 of 18*, then the CDR type and group of tests being mapped, and with a methodology per campaign which methodology), and once it has advanced enough, about how long it has left. The Saved Filter being looked at goes first: its calculation and its map move ahead of the others queued in the workspace. Any other job reads the CDR rows as before.
- **Shared calculations**: the National & Geographical Areas Trends and the Points Lost Map of each methodology are kept in the workspace folder (`.scoring-cache`, the most recently used up to 1 GB) and reused by any Saved Filter (or the same one calculated again) with the same CDRs at the same processing, methodology, options, Operator Maps and Map Areas: Saved Filters that share their Scoring Trends (such as *All available campaigns*) calculate them once, and with a methodology per campaign each campaign keeps its map, so *Latest 2 campaigns* takes those of *Latest campaign* and *Previous campaign*. A map drawn before is added as soon as the scores are saved, without a job of its own. While nobody uses the application for three minutes, the Favourites Filters of the open workspace whose result no longer matches their CDRs, methodology or Operator Maps (such as *Latest campaign* once a new campaign is processed), or that have none yet, are calculated one after another with their Points Lost Maps (logged in App Events as calculations of `system`), so they open at once. A change of CDR, methodology, Operator Maps, Map Areas or version of the application calculates them again. With a methodology per campaign, each methodology reads only the CDRs of its own campaigns.
- **Where it is**: the **Scoring History**, **Scoring History Sources** and **Scoring History Files** tables of Database Management. It is part of the workspace database, so it travels with workspace exports, transfers and backups of the Workspace Database; it has no export of its own because the application rebuilds it from the CDRs.

## Persistence and exports

### Results exports

| Action | Contents |
| --- | --- |
| **Export to CSV** above the Scoring table | The scoring table shown: expanded results, category subtotals and totals of the selected scoring and environment |
| **Export to CSV** above the GAP table | The GAP table shown: expanded GAP results and their existing numeric fields of the selected scoring and environment |
| **Generate Scoring Report (PPT/Word)** (Calculation panel) | A report whose content is chosen in the report editor, with the CDRs, filters, Split by, Geographical Areas & Scoring Trends, GAP reference, methodology and theme of the page |
| **Export Selected Scoring Report (PPT/Word)** (Results panel) | The selected Saved Filter as it was calculated (its CDRs, Split by levels and filters), with editable tables and charts, covers and environment transitions. Its dialog asks for the scorings (**Best Network**, **Most Reliable**, when the Saved Filter has it) and the environments (**All Environments**, all of them combined, and each environment) with checkboxes, Best Network and All Environments ticked, and for PowerPoint or Word |
| **Word** | The same slides as the PowerPoint, composed as the Scoring section of a [Bundle Report Template](reporting.md#bundle-report-templates) (so are the PowerPoint exports, which end with the closing slide): exactly as in PowerPoint (rendered with LibreOffice, included in the Docker image), the report cover on a page of its own with its background, a **Contents** page in the theme of the export, then portrait pages with as many charts and tables of a section as fit, in their order (a view that does not fit whole in what is left of a page, such as the Points Lost per City of every operator, starts the next one), under the title of each scoring and environment. Without LibreOffice, one page per slide with the slide tables and charts rebuilt |
| **Slides of the operators** | Position per environment, Biggest levers, GAP by part and Points Lost per Vendor and per kind of site show the operators together: up to three side by side, four in two rows of two and five or six in two rows of three (more share slides of four, so a slide never has one alone). The slides of a single campaign (KPI GAP Profile, Points Lost, Points lost per KPI, per City, per Vendor and per kind of site, Sites to review and Route stretches) show the latest campaign only. The rule of each operator under the table headers spans all its campaigns, the names at the end of the Scoring Trend lines stand apart (a line that ends before the latest campaign is named where it is clearest) and Campaign Comparison names each operator in its colour over a rule of its colour |

**Generate Scoring Report (PPT/Word)** opens the **report editor** (see [Report scenarios](#report-scenarios)) for one report whose content only is chosen there (its scorings, environments and sections, remembered for the next time), without saved configurations, theme or JSON files: it takes the CDRs used, NR Mode, filters, Split by, Geographical Areas & Scoring Trends, GAP reference, methodology and theme of the page (the scenarios of the Scoring artifacts and Bundle Report Templates keep their own filters). **Export Selected Scoring Report (PPT/Word)** exports the selected Saved Filter without the editor. A progress dialog stays open while either document is generated.

### Report scenarios

A report has one or more **scenarios**, in order: for example *National*, then *London*, then the *Main Cities*, then by Vendor. Every scenario uses the CDRs, NR Mode, methodology and GAP reference selected in the Calculation panel with its own **filters** (Operator, Operator_Vendor, Vendor_Operator, Vendor, Region, Cluster, City with **Main Cities**, Campaign) and **Split by** levels. Each filter list has a search box that narrows the values as you type, **Select All / None** for the listed values, and closes when you click outside it or open another one. Its **All** option keeps no restriction, so the scenario always includes every value of the CDRs when the report is generated, also values that appear in later CDRs (for example a new Operator); **Main Cities** checks the workspace main cities and uses that list when the report is generated. The values stay editable with All or Main Cities checked: changing one keeps exactly the values checked. A closed list shows one chosen value by name and several by their number (for example `2/4 selected` or `Main Cities (5/12)`; hover it to see the values); campaigns are shown with the workspace [Campaign Maps](workspace-config.md#campaign-maps). When the document is generated, each scenario reuses its Saved Filter (the same selection used before, with its result up to date) or calculates it, so it can take longer the first time. A Split by level with a single value (for example **Campaign** when the CDRs hold one campaign, or **City** filtered to one city) splits nothing, so it is left out of the scenario, as it is of every chart, table and document of Scoring & GAP Analysis.

For each scenario and each scoring (**Best Network** and **Most Reliable Network**, which can be left out), choose:

| Group | Options (default) |
| --- | --- |
| Environments | **All Environments only** (default) or All Environments and each environment |
| Summary | How the measurements ran, Where to act, Where to act by performance owner, Standings, Position per environment and service, Biggest levers against the reference, Cities, Towns, Roads and Railways ranked and The route that loses most (all on) |
| Scoring Charts | Scoring per Service, per Category and per Category (Breakdown) (all on) |
| Scoring Tables | Category table and Breakdown table (on), Show KPI values and Show GAP values (off), Campaign comparison (on) |
| Geographical Areas | The per City / Cluster / Region cards (of the Breakdown and Separate cities of the Geographical Areas & Scoring Trends, on the whole country), the locations ranked and each operator against the reference per location (all on) |
| Scoring Trends | The Scoring Trend (two campaigns or more) and the National & Geographical Areas Trends (both on) |
| GAP Analysis | (The table of all operators shows every operator; the individual tables are those of the **Focus operators** of the Operator Maps, every operator when no label has the Focus role) the table of all the operators, the individual tables against the reference, the GAP by part over the campaigns and the KPI GAP Profile (all on) |
| Points Lost | Where the points go, Points lost per KPI, the Points lost per City map, Points lost per Vendor, per kind of site, Sites to review and Route stretches (all on) |

Configurations saved before the Summary, Geographical Areas (called Locations before), Scoring Trends and Points Lost groups keep their choices: the cards and the Scoring Trend follow the former Scoring Charts options, the map the former GAP Analysis option and the points lost per KPI the former KPI GAP Profile option.

Below the Split by levels, each scenario has a **Geographical Areas & Scoring Trends** panel, always included and always scored on the whole country, also in a scenario with Region, Cluster, City or Main Cities filters (scenarios saved without it include it now). Its **Geographical Areas** subpanel chooses the areas of the Geographical Areas and the National & Geographical Areas Trends slides: **Breakdown** (**Region**, the default, Cluster, City or None, which needs Separate cities) and **Separate cities**, the cities shown on their own (**London** by default, any other city and the workspace **Main Cities**). Its **Scoring Trends** subpanel has the **Campaigns** of the trends, **All available campaigns** (the default), **Latest campaign**, **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns**, **Previous campaign** (resolved at each report), **Same as the scenario** or **Chosen campaigns** (scenarios saved before keep All available campaigns), with which its Scoring Trend and National & Geographical Areas Trends are calculated whatever the campaigns of the scenario, and the **Time split** of the trends only: **All selected CDRs** aggregates every selected CDR into one value (for example 24 weekly CDRs into the score of those 24 weeks), **Campaign** (the default) splits by campaign, and **Daily**, **Weekly** (ISO weeks, such as `2026-W07`), **Monthly**, **Quarterly** and **Yearly** split by the period of the start time of each test, whatever the CDRs are (daily, weekly or per campaign), so 28 daily CDRs give four weekly points. The scenario's calculation then also scores the National scoring with that time split, the chosen cities and each value of the breakdown, every one with its own measurements: KPI values (rates, medians, P90…) are not additive and their points come from non-linear thresholds, so an area score is not a share of the National points.

With several scenarios, every setting whose value is not the same in all of them (a filter, a Split by level, the Scoring Trends, a scoring, its environments or one of its options) is highlighted in amber in each scenario, so what changes from one scenario to another stands out; the highlights follow every change.

The document starts with a cover listing the scenarios; with several scenarios each one opens with its transition (01 National, 02 London…, with its NR Mode and the filters that choose part of the country or of the operators), then each scoring (1.1 Best Network Scoring, 1.2 Most Reliable Network Scoring) and each environment block (1.1.1, 1.1.2…) has its own transition, and its slide subtitles name the scenario and the scoring; with one scenario the scorings are 01, 02 and their environments 1.1, 1.2… With All Environments only, the subtitles omit *All Environments*; each environment block names its environment. Show KPI values adds a **Value** column before each Score of the Breakdown tables.

The **Theme** selector of the editor's toolbar chooses the colours of the document (see [Choose a theme](#choose-a-theme)): a saved configuration keeps its theme, Default takes the theme of the page, and Reporting Jobs keep the theme of their report.

The editor opens with the scenarios of the last report, remembered as soon as **Generate PowerPoint** or **Generate Word** is pressed. Its selector always tells the saved configuration (or **Default**) whose scenarios are the ones shown, and **<Not saved configuration>** when no saved configuration has them; it follows every change of the scenarios. The editor's toolbar saves (**Save as…**) and deletes **named configurations** of the workspace, and exports or imports them as JSON; they also travel as the **Scoring & GAP Report Templates** element of Admin's Import / Export / Transfer, with Full Workspace transfers and with backups. Choosing a configuration in its selector loads it at once, **Default** included (one scenario with the filters and aggregation of the selected Saved Filter plus **Campaign**, which is left out when there is a single campaign; *Default* is always listed, cannot be deleted and is not available as a saved name). When the scenarios have unsaved changes, choosing another configuration asks first: **Cancel** keeps them, **Discard changes** loads the chosen configuration and **Save as…** saves them before loading it. The last configuration used to generate a document opens again in any later session. Saved configurations and the last one used travel with the **Scoring & GAP Analysis Methodologies** in Import / Export, transfers and backups.

Exports use the saved results; they do not recalculate KPIs. Both **Export to CSV** buttons export the selected Saved Filter.

CSV preserves stored names, numeric values and its schema, with a `cluster` column after `region` for results split by Cluster; the Most Reliable CSV has the same columns with the Most Reliable points (`scoring=most_reliable` in the export address). Its existing category/final GAP aggregates remain valid-KPI means. The new **Total KPI GAP** footer is a web/PowerPoint display total; it does not redefine CSV GAP fields. `gap_partial` and `gap_environments` identify partial coverage.

### What is in the PowerPoint?

When the result has a Most Reliable scoring, each scenario contains both scorings: a **Best Network Scoring** section and then a **Most Reliable Network Scoring** section. Slide subtitles name the scoring (and the environment of an environment block, for example *Most Reliable Network — Drive - City*), then the area, operators and vendors of the slide (see [Area, operators and vendors of each chart and table](#area-operators-and-vendors-of-each-chart-and-table)), and slide notes carry the notes of that scoring. Reporting Jobs generate the same document for their Scoring artifact. Without Most Reliable points the document has only the Best Network sections. Cover and transition titles that are wider than the slide are reduced to fit on one line.

Each block follows the order of the results tabs, as chosen in the scenario. The **Focus operators** (the Operator labels with the **Focus** role in [Operator Maps](workspace-config.md#operator-maps), with every name of the CDRs they stand for; every operator without them, or when none of the operators of the results is one of them) choose the operators of Where to act and Where to act, by performance owner with their places ranked and route, the locations ranked and *Per location*, the individual GAP comparisons, *GAP by part*, the KPI GAP Profile, the points lost per KPI, the points-lost maps (per City, Region…), per Vendor and per kind of site, *Sites to review* and *Route stretches*; the other slides show every operator, and a choice made in a section of the page before exporting it is kept:

1. **Summary**, after the cover of the scoring: *How the measurements ran*, then for the operator chosen in Where to act (else for every Focus operator; every operator but the reference without them) *Where to act* and *Where to act, by performance owner*, then *Standings* (every operator from the highest score with its Data and Voice points, then a panel per operator with its position, its GAP to the reference by part and a sentence that sums it up), *Position — per environment* (two operators per slide), *Biggest levers — vs <reference>* (two operators per slide) and, for the operator chosen in Where to act, *Cities ranked*, *Towns ranked*, *Roads ranked* and *Railways ranked* (18 places per slide, *(1 of 2)*…) and *<Route>: where the points are* (its map, owners, five stretches and what to review on one slide).
2. Best Network (or Most Reliable Network) Scoring per Service and per Category, with the maximum score allocation donuts.
3. Scoring per Category (Breakdown).
4. Scoring Tables — Summary and Breakdown, then Campaign Comparison.
5. **Geographical Areas**: the scoring per City / Cluster / Region (of the Breakdown and Separate cities of the Geographical Areas & Scoring Trends, on the whole country), *<Cities and routes> ranked* and *Per location — <operator> vs <reference>* for each Focus operator (up to four).
6. **Scoring Trends**: the Scoring Trend and the National & Geographical Areas Trends, with the campaigns of the Scoring Trends of the scenario.
7. All Operators GAP comparison (every operator), then the individual comparison of each Focus operator, *GAP by part — vs <reference>* and the KPI GAP Profile.
8. **Points Lost**: *Points Lost — where the points go*, the points lost per KPI, the points-lost maps, *Points Lost — per Vendor* and *per kind of site* (two operators per slide), *Sites to review* (High priority first) and *Route stretches* (the two routes that lose most of each Focus operator).

The All Environments block also contains, when they apply and are chosen:

- **Best Network (or Most Reliable Network) Trends — National & Geographical Areas** in Scoring Trends: a table with the National scoring, each area of the breakdown and the cities (six per slide; each group's names in its colour and a thick rule between groups), with the score of the reference and of the operators to compare in the latest campaign or period of its time split, from the highest score, their change from the previous one (Δ vs, with two or more) and their GAP to the reference (Δ vs EE), and with several campaigns or periods a trend chart per area on the same scale. With **All Environments and each environment**, each environment block has its own.
- **Scoring per City / Cluster / Region**: a note with the maximum points and up to 12 cards with each operator's Data (teal) and Voice (amber) points as a bar, from the highest score, with the totals, labelled with the operator names of the mapping table, for the latest campaign.
- **Scoring Trend** first in Scoring Trends: a line chart of the campaigns of the Scoring Trends (with campaigns of their own, of their National scoring; otherwise per combination of the other levels, up to six), each line ending in the name and latest score of its operator.
- **KPI GAP Profile** after the GAP tables: the GAP to the reference per KPI of two Focus operators per slide, grouped by category with their subtotals, with gradient data bars in every column, for each combination of the other levels, such as each selected City, Cluster or Region (up to twelve; the latest campaign's when there are more). The note names the operators in their colour and the totals in bold.
- **Points lost per KPI** in Points Lost: the same tables with the points each operator loses against the maximum, the reference operator included when it is one of the **Focus operators**.
- **Points Lost per City** after them: one slide per Focus operator (the reference operator included when it is one of them), headed by the operator in large type, with the map areas coloured as the web does by default (the points of the city or route that loses most among those measured in each area, the cities and routes that lose most labelled once, over the grey outline of their countries) and its yellow–red scale, and the cities and routes that lose most as bars (up to 30, each with the environments where it loses points), with the share of the points lost they account for. A single exported environment gets its own maps. Workspaces with Clusters or Region Mapping polygons add a **Points Lost per Cluster** or **per Region** slide. Without map areas (a country without Map Areas) the cities are bubbles over the test locations.
- **Campaign Comparison** at the end: the comparison tables of up to eight operator and level combinations, two per slide.

Slide titles take the colours of the theme (blue in NetCheck), with the part that tells consecutive slides apart in bold and in the accent of the theme: the focus (for example *Best Network Scoring **per City***) or what follows the dash (for example *GAP Analysis — **3 vs EE*** or *Scoring Tables — **Summary***). Subtitles name the scoring, the environment, the area, the operators and the vendors in bold, smaller when they would not fit on one line.

Covers and transitions use the Vodafone-Three red of the template (`Template_VodafoneThree.pptx`) with the Ericsson mark drawn in outline behind them and the Vodafone-Three and Ericsson logos at the top right. Every cover has the same title and subtitle sizes (54 and 24 pt) and every transition smaller ones (40 and 20 pt), whatever the module; the subtitle starts right below the room of two title lines, so a long title wraps into it. Each transition shows its counter above its title: 01, 02… for the first level and 2.1, 2.1.1… below it. A scoring cover or transition has the NR Mode as its subtitle and, under the line of the layout, the **Campaigns**, the Split by and each filter, with white labels and **bold yellow values**. Long lists can be shortened visually without changing the calculation.

The export follows Scoring Tables GAP visibility and column placement. Dedicated GAP slides remain included. Individual slides include the Priority arrow, mean KPI GAP and column-averaged total; every GAP table includes its column totals and, on one line under it, its color scale, and takes the height of the slide down to it with the largest text its rows fit (the KPIs wider when the GAP columns are few).

### Dense-chart options

| Chart | Export asks whether to split when… |
| --- | --- |
| Best Network | More than 20 bars |
| Scoring per Category | More than 40 bars |

Keep all bars for one slide, or split for more readable charts. Splitting preserves complete category groups where applicable and a common Best Network scale. **Scoring per Category (Breakdown)** keeps every category on one slide up to 50 bars and, above that, spreads the categories over as few slides as possible with a similar number of bars each (*Page 1 of 2*), in PowerPoint and Word. Scoring bar labels use smaller integers above 40 bars and are hidden above 70. Small stacked segments may omit labels; their values remain in the editable chart.

> [!TIP]
> Narrow filters or split charts when many combinations make labels too small. Dense tables keep their combinations together, so reducing the scope also improves table readability.

### Save, export and backup are different

| Action | Purpose |
| --- | --- |
| **Save Methodology** | Commit edits to the workspace database |
| **Export Methodology (JSON)** | Download the selected saved methodology |
| **Admin → Import / Export → Scoring & GAP Analysis Methodologies** | Transfer the complete methodology collection and its default |
| **Workspace database backup / restore** | Preserve methodologies, Saved Filters with their results and shared selections |

Favourites Filters packages carry the Saved Filters without their results, nor the workspace-local CDR selection: in the receiving workspace each Saved Filter finds its CDRs by the SHA-256 of their files and waits until they are processed there. Workspace duplication, database exports, transfers and ZIP database backups preserve the Saved Filters with their results in the workspace database.

After a restart, interrupted calculations are kept as failed and can be recalculated. Processing CDRs calculates nothing on its own (only the Favourites Filters are calculated again while the application is idle; see [Scoring History](#scoring-history)): the [Scoring History](#scoring-history) indexes them in the background as soon as they are processed, so their first calculation is quick.

## Troubleshooting

| Symptom | Check or action |
| --- | --- |
| No CDRs used | Verify workspace, NR Mode, the Campaign (each campaign needs Data, Voice and Speech CDRs), ready processing status and the In Combined? choice in Workspace |
| Calculate is disabled | Read the yellow notice; complete each campaign's three source types, or wait for the running calculation of the same selection |
| Expected vendor/city choices are missing | Check mappings, the Campaign and the other filters (each filter lists the values they leave); reprocess older incomplete catalogues |
| GAP is N/A* | Verify the reference and matching context, including common valid environment coverage |
| Maximum achievable points differ between columns | Read the excluded KPI list for each combination; unavailable contributions can differ |
| Results differ from another report | Compare methodology revision, filters, Split by levels, thresholds and coverage |
| CDR changed during calculation | Wait for processing/mapping to finish and recalculate |
| Older All Environments KPI values are N/A | Recalculate to save pooled global measurements |
| A calculation failed after an interruption | Recalculate the Saved Filter; delete it only if no longer needed |

> [!NOTE]
> **NR Mode selects the dataset universe.** It does not supply a different SA methodology automatically. Validate copied or customized environment rules before using them for a new benchmark.

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

The workbook contains 32 KPI definitions in each of DriveCity and DriveConnectionroad, rows 4–35. Its maximum allocations were checked against the extracted rules; City totals **650** and Road **350** points.

The current Road selector uses **G_Level_1 = Drive**, **G_Level_2 = Connecting Roads**. The workbook sheet name is provenance, not the current source selector. Known legacy Road definitions are corrected without changing their points; explicit customized names/selectors are preserved.

Walk is a zero-point extension with City-derived starting thresholds. It needs validation before assigning points.

#### Documented differences

> [!NOTE]
> **Reference documents are not interchangeable numerical baselines.** Match raw inputs, revision, filters, operator scope, aggregation and coverage before comparing results.

- Dynamic City best-value Ultra ranges in the workbook exclude some operators; the application uses all selected operators, following the best-achieved definition.
- Two City P90 operator formulas use High = 95% while the common formulas and Road use 90%. The application consistently uses 90% for K20/K25.
- The PDF's Drive/Walk allocation totals 675 points; this mapping uses the workbook's 1,000-point City/Road allocation.
- The earlier example PPT uses different Q4 weights; it supplies layout guidance, not a numeric golden for the current mapping.
- POLQA low-quality calculation uses **LQ <= 1.6**, despite the source label. Call setup threshold uses **> 10 seconds**, rather than the older example PPT's > 15 seconds.

The source Prep flow has 18 aggregation steps and 17 inner joins. The application calculates the supported formulas directly from processed rows and retains missing comparisons visibly.

Regression fixtures cover representative formulas and mapping examples. Full numerical parity with an external Prep/Excel output still requires matching source data and an independently verified result.

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

The NetCheck 2026 Most Reliable scoring rates 10 KPIs with **650** points in Drive - City and **350** in Drive - Connecting Roads (Voice 350, Data 650, **1,000** in total); the KPIs underlined in the NetCheck Q2 2026 report are the same. Each KPI has global points (for example 141.75 for the classic call success ratio) split 65% City and 35% Road, as in Best Network. `Netcheck_Score_Mapping_2026Q2_Mostreliable_Drive_City_Road.xlsx` writes these points by hand rounded to two decimals, which adds up to 1,000.04; neither the workbooks nor the reports give a formula to derive them, so they are part of the methodology. Thresholds and score anchors are the Best Network ones. Enter these values in the Most Reliable points column:

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

The campaigns up to Q1 2026 follow the NET CHECK 2025/26 Benchmarking Methodology. The **NetCheck 2025** methodology, shipped with the application beside NetCheck 2026, has the KPIs, thresholds and Data points of NetCheck 2026 with two differences, from its drive test ranking (Drive - City 65 %, Drive - Connecting Roads 35 %): K3 is **CALL SETUP TIME > 15 s [%]** (calls whose setup takes more than 15 s, with the same thresholds 3 % / 0.6 % / 0 %) instead of > 10 s, and the voice points give the classic calls 252 points and WhatsApp calls 84 (NetCheck 2026: 203 and 133). Its Most Reliable points are those of NetCheck 2026.

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

The shipped methodologies say the campaigns they apply to, so **By campaign** scores each campaign with its own: NetCheck 2025 up to 2026-Q1, NetCheck 2026 for 2026-Q2 and NetCheck 2026-Q3 from 2026-Q3. A new workspace starts with NetCheck 2026 as its active methodology; an existing workspace receives NetCheck 2025 once, with its campaigns unless they overlap those of one of its methodologies (then without them: set them in **Applies to campaigns**).

### NetCheck 2026-Q3

From Q3 2026 NetCheck adds TikTok to Video Streaming. The **NetCheck 2026-Q3** methodology, shipped with the application beside NetCheck 2026, keeps the 20 % of Video Streaming but divides it between YouTube (13 %) and TikTok (7 %), following the NetCheck Q3 ranking templates (Best Network and Most Reliable, National and City). K28, K29 and K30 become the YouTube KPIs (`Test_Name` = `YouTube`, as every Video Streaming test of the earlier campaigns) and K33, K34 and K35 the same KPIs for TikTok (`Test_Name` = `TikTok`), with the same thresholds; every other KPI and the 650 City and 350 Road points of both scorings are those of NetCheck 2026. Choose it in the Calculation panel for the Q3 campaigns.

| Code | KPI | City points | Road points | Most Reliable City / Road |
|---|---|---:|---:|---:|
| K28 | YOUTUBE VIDEO STREAMING SUCCESS RATIO [%] | 35.1520 | 18.9280 | 54.9250 / 29.5750 |
| K29 | YOUTUBE VIDEO STREAMING TTFP >= 10 s [%] | 2.1970 | 1.1830 | |
| K30 | YOUTUBE VIDEO STREAMING IRRITATING EXPERIENCE [%] | 17.5760 | 9.4640 | |
| K33 | TIK TOK VIDEO STREAMING SUCCESS RATIO [%] | 18.9280 | 10.1920 | 29.5750 / 15.9250 |
| K34 | TIK TOK VIDEO STREAMING TTFP >= 10 s [%] | 1.1830 | 0.6370 | |
| K35 | TIK TOK VIDEO STREAMING IRRITATING EXPERIENCE [%] | 9.4640 | 5.0960 | |
