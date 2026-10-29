# Workspace Config

Workspace Config is a dedicated page for settings owned by the active workspace: Main Cities, Mappings & Reference Data (Operator, Vendor and Campaign Maps, Map Areas, Spectrum Holdings, Serving Networks and the CDR Field Dictionary) and Scoring & GAP Analysis Setup. These settings remain workspace-scoped and are included in the applicable import, export, transfer, backup and restore workflows.

> [!IMPORTANT]
> **Workspace settings.** Every edit on this page belongs to the active workspace. Application Config controls shared runtime settings.

> [!TIP]
> **Save versus export.** Save persists edits in the workspace. Export downloads a portable copy; it does not replace the Save action.

Open **Config → Workspace Config** from the main navigation at `/workspace-config`. Mapping and Main Cities actions use routes below `/workspace-config/`. The PPT Templates are not part of Workspace Config: they are managed in [PPT Designer](ppt-designer.md#ppt-templates). The page uses the same teal/navy palette as Application Config, and the **Modules & Sections** tab at the left edge links to its panels.

## Presentation

The presentation **Workspace Config** goes through everything to set up in a new workspace before its first analysis: how operators, vendors and campaigns are named, coloured and ordered, the map areas of its countries, its networks and its methodology. Select it to open it in the slide viewer, play it full screen or download its PowerPoint; every presentation is also in [Product Presentations](presentations.md).

```presentations
workspace-config
```

## In this guide

| Task or topic | Go to |
| --- | --- |
| Presentation | [Open section](#presentation) |
| Access and active workspace | [Open section](#access-and-active-workspace) |
| Mappings & Reference Data | [Open section](#mappings-reference-data) |
| Campaign Maps | [Open section](#campaign-maps) |
| Unassigned values warning | [Open section](#unassigned-values-warning) |
| Map Areas | [Open section](#map-areas) |
| Spectrum Holdings | [Open section](#spectrum-holdings) |
| Serving Networks | [Open section](#serving-networks) |
| CDR Field Dictionary | [Open section](#cdr-field-dictionary) |
| CDR type | [Open section](#cdr-type) |
| Main Cities | [Open section](#main-cities) |
| Portable operations | [Open section](#portable-operations) |
| Scoring & GAP Analysis Setup | [Open section](#scoring-gap-analysis-setup) |
| Scoring Export Panels | [Open section](#scoring-export-panels) |

## Access and active workspace

The Workspace Config section is available to `user-editor`, `admin` and `super-admin` accounts. `user-viewer` accounts do not have access. Open a workspace before using its configuration panels; their contents and changes belong only to that workspace.

## Mappings & Reference Data

The Mappings & Reference Data panel contains Operator Maps, Vendor Maps, Campaign Maps, Map Areas, Spectrum Holdings, Serving Networks and the CDR Field Dictionary as independently collapsible subpanels. Their light blue headers distinguish them from the dark parent header. Existing mapping controls and saved expansion states remain available inside each subpanel.

### Operator Maps

Operator Maps set how the Operators are named, ordered and coloured in every filter, table, chart, legend and report. They have two numbered subpanels, each of which can be collapsed (the browser remembers it):

**1 · Operator names found in the CDRs** lists every Operator name of the ready CDRs of the workspace, with the number of CDRs that contain it (hover it to see their names), its **Label**, its **Status**, read only, the **Role** of its label (Include, Focus or Exclude, set in subpanel 2; it follows a label chosen in the list at once) and its **Comments**, a free note about what the name holds in the CDRs as a reminder (for example that `Vodafone SA` is the SA terminal of the NSA drive of 2026-Q2). The **Label** and **Comments**, the fields edited in this table, are pastel yellow. **Save assignments** saves the comments too; they travel with the Operator Maps in the Mappings & Reference Data export, transfers and backups, and every change is recorded in App Events. The **Status** is:

- **Unassigned** (red, and the number of the subpanel turns red): the name has no label yet, so it is shown as it is and never added up with other names. **Use own names** gives every unassigned name a new label with its own name.
- **Merges N**: the label stands for N names of the CDRs that coincide in the same campaign and NR Mode (in a CDR of that campaign with that NR Mode, or in CDRs of the same campaign and NR Mode), where they are added up as one Operator. Hover it to see the others and the campaigns where they coincide, for example `26-Q2 (NSA)`.
- **Assigned**: the label stands for this name only, or also for names that are never in the same campaign and NR Mode as this one (hover it to see them), which are therefore never added up: for example `Vodafone UK` in the NSA campaigns and `Vodafone SM` in an SA campaign can share `VF`.

Choose the label of each name in its list: one of the Operator labels of subpanel 2, or **+ New label…**, which lets you type a new label (Enter to accept, Esc to cancel) that every list then offers too. Press **Save assignments**; a new label is added at the end of subpanel 2. Each name therefore keeps its own label unless you give several names the same one: for example `Vodafone UK` → `VF`, `Vodafone SA` → `VF-SA` and `Vodafone VoNR` → `VF-VoNR` keep the three apart, while two spellings of the same network (`Vodafone` and `Vodafone UK`) can share `VF`. A name that is itself one of the labels (for example `EE`, shown as `EE`) cannot be changed here: rename that label in subpanel 2. Saving asks for confirmation when a label would add up names of the CDRs that it did not add up before (names that coincide in a campaign and NR Mode, which the dialog names), when a name leaves a label that saved filters or Reporting Jobs use (they no longer include it, and the dialog says how many use it), and when a new label contains `_`, which also separates Operator and Vendor in `Operator_Vendor` values such as `VF_Ericsson`.

**2 · Operator labels** lists one row per label with its **Order**, **Colour**, **Label**, **Role**, **NR Modes**, **Possible names in the CDRs** and **Actions**. The possible names are how the label can be written in the CDRs of the different campaigns, shown as chips: highlighted with the number of CDRs when the current CDRs have them, grey when they are names of other campaigns, and ordered from the name in most CDRs (alphabetically when they tie). Hovering a chip, a CDRs count or a **Merges N** badge shows its CDRs or names at once; clicking it keeps them in a floating panel until it is closed (×, Esc or a click outside). **×** removes a name and **Add a name** with **+** adds one; a name of another label moves to this one at once. Under the label, **Merges N** tells that it adds up N names of the current CDRs that coincide in the same campaign and NR Mode. The label also stands for the name written like itself, so it need not be added. Saving a label asks for the same confirmation as subpanel 1.

Use **Add label** to create a label with its colour, role, NR Modes and possible names (one per line; comma and semicolon separators are accepted too). Change a label's name, role, NR Modes, possible names or colour and press **Save Labels**, below the table, to save every changed label at once (Enter in a label saves that one). **Move up** and **Move down** set its position in Operator charts and in Subscriber dimensions; the first and last rows cannot move beyond the table. **Delete** removes the label after confirmation, and its names are shown as they are until they get another label.

The **Role** beside each label is **Include** (yellow, the default: the operator is analysed as usual), **Focus** (green) or **Exclude** (red), recorded in App Events when it changes; a note above the labels explains each one:

- **Focus**: the label, with every name of the CDRs it stands for, is one of the **Focus operators** of [Scoring & GAP Analysis](scoring-gap-analysis.md#persistence-and-exports): Where to act, the locations ranked, the individual GAP comparisons, GAP by part, the KPI GAP Profile and the Points Lost views of its PowerPoint and Word (from the page, the Scoring artifacts of the Reporting Jobs and the Bundle Report Templates) are those of the Focus operators, and the operator choices of those sections of the page list them first (every operator when no label is a Focus operator). The comments that **Generate comments** writes for the slides of [PPT Designer](ppt-designer.md#generated-comments) follow the Focus operators too.
- **Exclude**: the operator is left out of every analysis, filter, chart and report of the workspace (Scoring & GAP Analysis, CDR Analysis, PPT Designer, the Chart Builder, Network Insights, Non-Qualified Calls, the Bundle Report Templates and the Reporting Jobs), as if every Operator filter left it out (as `NOT Lebara` does, see [Operator patterns](web-interface.md#operator-patterns)), so the Operator filters can stay at All; no Operator list or GAP reference offers it, and its names stay in subpanel 1. Saved Filters are calculated again when the excluded operators change. At least one label must stay included: a Role that would exclude every label goes back to the one it had, and saving, deleting or importing labels that would leave every label excluded is refused without changing them.

The **NR Modes** beside each label are those the operator has a network in: **NSA and SA** (the default), **NSA only** (blue) or **SA only** (magenta), recorded in App Events when they change. An operator without a network in an NR Mode, such as Three, which has no SA, has its tests of the CDRs of that NR Mode out of scope: in the SA CDRs its tests run on LTE and EN-DC, which its NSA CDRs already measure. Those tests are left out of every analysis, filter, chart and report of the workspace (Scoring & GAP Analysis with its Scoring Trends and Geographical Areas, CDR Analysis, PPT Designer, the Chart Builder, Network Insights, the Reporting Jobs and the Bundle Report Templates), and the Operator filters do not offer the operator for the CDRs of that NR Mode alone; its tests of the other NR Mode stay. In [Non-Qualified Calls](non-qualified-calls.md#nq-prioritization) those calls are out of scope (*Out of scope · SA · Three*). Saved Filters with CDRs of that NR Mode are calculated again when the NR Modes change, and the headings of their panels name the pairs out of scope (*Out of scope: SA · Three*). A **Suggested: NSA only** note appears under the NR Modes of a label whose Non-Qualified Calls of the SA campaigns barely ran on NR SA (under 10 %); it is never applied on its own. A label with the Role **Exclude** is left out in both NR Modes whatever its NR Modes. Under **NSA only** or **SA only**, a red note names the NR Mode out of scope (*SA out of scope in every module*), and in subpanel 1 the names of the CDRs of the label show its NR Modes (blue *NSA only*, magenta *SA only*) beside its Role, also while they are changed and not saved yet.

**Out of scope in this workspace**, above the subpanels, sums up what is left out: in **Every module**, the labels with the Role Exclude and the NR Mode · operator pairs of the NR Modes; in **Non-Qualified Calls only**, the regions of the Out of Scope settings of the NQ Prioritization and the operators that are not Focus operators, which the other modules keep.

The roles and NR Modes travel with the Operator Maps in the Mappings & Reference Data exports, transfers and backups; a package exported before the NR Modes gives every label both NR Modes. Workspaces whose Non-Qualified Calls left an NR Mode · operator pair out of scope before the NR Modes (SA · Three, saved in the NQ Prioritization or the default one) took it as the NR Modes of that label once.

Renaming a label updates exact matching references in Report Templates (their slide and chart titles, legends, dynamic values and the values of their Operator, Operator_Vendor, Vendor_Operator and Vendor filter conditions; with a label that is a number, such as `3`, only the filters, legends and dynamic values, never layouts, thresholds or other conditions) and saved Designs, and the values of the Operator, Operator_Vendor, Vendor_Operator and Vendor filters saved in Reporting Jobs (including the GAP reference operator and the Scoring report scenarios), saved Scoring report configurations, the last Scoring calculation (its GAP reference too), the Saved Filters of Scoring & GAP Analysis (their GAP reference and filters; they are found again with the new label and calculated again when opened), the favourite Bundle Report Templates and Network Insights Analysis Selections, the CDR Analysis filters of each CDR and the Non-Qualified Calls filters (`VF_UK` → `VF` also turns `VF_UK_Ericsson` into `VF_Ericsson` and `Ericsson_VF_UK` into `Ericsson_VF`). Campaign filters keep the full campaign value, so changing the Campaign Maps never requires renaming them.

A new workspace starts with the labels of the operators of the country chosen for it in [Workspace Management](workspace-management.md#workspace-lifecycle), in their corporate colours and with the usual ways they are written in the CDRs, also with the country (for example `Telekom`, `Vodafone`, `O2` and `1&1` in Germany, where `o2 - de` is O2; or VF, VF SA, VF VoNR, VF SM, Three, EE, O2 and Lebara in the United Kingdom, where `Vodafone UK`, `VFUK` or `Vodafone` are VF and `3` is Three, which has NSA only), none of them with a Role. A workspace created without a country starts without Operator Maps. The operators of the 50 listed countries come from `assets/labels-operators/operators-by-country.json`, so a deployment can change them for every new workspace. The colour picker sets the label's chart theme colour; charts can derive related shades to distinguish campaigns or series. Every filter, table, chart, legend and report of the tool shows the label, and choosing it selects all its names; only Preview Dataset shows the names as they are in the CDRs.

The maps do not rewrite source workbooks, stored CDR rows or combined CDR tables. Saving, moving or deleting a label clears chart caches so later views use the new settings.

### Vendor Maps

Vendor Maps have the same two subpanels: **1 · Vendor names found in the CDRs** lists every Vendor name of the ready CDRs (the Operators without a Vendor, `<Operator> - All`, are not Vendors) and gives each one a label exactly as in the [Operator Maps](#operator-maps), and **2 · Vendor labels** has the same **Order**, **Colour**, **Label**, **Possible names in the CDRs** and **Actions** controls, with **Add label**, **Save Labels**, **Move up**, **Move down** and confirmed **Delete**. Names are matched without regard to case.

A new workspace starts with the Vendor labels, in this order, Ericsson (`#0255AD`), Ericsson (Mixed) (`#002F61`), Huawei (`#FBBD00`), Samsung (`#008521`), NSN (`#8C00FF`, also `Nokia` and `NNS`), SCW (`#6F42C1`), Mixed (non-Ericsson) (`#5E4F2E`, also `Mixed`), Other Vendor (`#5E4F26`), (blank) (`#7A8791`) and Unknown (`#7A8791`). These labels come from `assets/labels-vendors/default-vendor-maps.json`, so a deployment can change them for every new workspace.

Renaming a Vendor label updates exact matching Report Template and saved Design references, and the same saved filters as an Operator rename.

Vendor order determines the chart sequence for Vendor dimensions and the Vendor portion of combined `Operator_Vendor` values. The selected colour gives a Vendor a consistent chart identity, with related shades where multiple series need distinction. Every filter, table, chart and report shows the Vendor label (and the Operator and Vendor labels of an `Operator_Vendor`), and choosing it selects all its names; the maps do not alter materialized CDR values, which only Preview Dataset shows. Label changes refresh chart caches without rematerializing source data.

### Campaign Maps

Campaign Maps set how every chart, table, legend, filter and PowerPoint or Word report of the workspace names and orders campaigns. They follow a pattern rather than a list, so campaigns uploaded later, such as `2026-Q3` or `2027-Q1`, follow it without editing the map.

- **Label format** writes the label from the parts read in the campaign name: `{year}` (2026), `{yy}` (26), `{quarter}` (2), `{mode}` (SA or NSA) and `{market}` (the country code, such as UK). Characters inside the braces of a marker are written only when the campaign has that part: the default `{yy}-Q{quarter}{-mode}` shows `UK_Q2_2026` as `26-Q2` and `UK_Q2_SA_2026` as `26-Q2-SA` (`{year}` writes them as `2026-Q2` and `2026-Q2-SA`).
- **Order inside a quarter** orders campaigns by year and quarter, and the campaigns of one quarter by mode: by default first the campaign without mode, then NSA, then SA. Use the arrows to change it. **Show in label**, next to NSA and SA, chooses the modes that `{mode}` writes: unchecking NSA shows the NSA campaigns as `26-Q3` while the SA ones stay `26-Q3-SA`, without an exception per campaign. An NSA campaign then reads like the campaign without a mode of its quarter, and both are one campaign (the Preview shows **Merges** when the CDRs have both).
- **Exceptions** give their own label to campaigns that do not follow the pattern, one or more source campaigns per label. They are ordered by the year and quarter of their label, after the campaigns of that quarter, or first, in the table order, when the label has none. The label can write them as a campaign (`2026-Q2 Flex`) or as the label format does: with `{yy}-Q{quarter}{-mode}`, `26-Q2-Flex` is ordered in 2026 Q2. Campaigns without a year and quarter and without an exception keep their name. A campaign whose label or source campaign has the word Flex (`26-Q2-Flex`, `UK_Flex_2026`) is a Flex campaign: the automatic Campaign choices of the modules (Latest campaign, Latest 2, 3 and 4 campaigns, Previous campaign and All available campaigns) leave it out, so it is used only where it is checked by hand.

The **Preview** lists the campaigns of the ready CDRs of the workspace with the labels and order of the map being edited, and the **Status** of each one: **Unassigned** for a campaign without a year and quarter and without an exception (its **+** adds an exception for it, labelled with its own name to start with), **Merges N** when N campaigns share its label, which every filter, table, chart and report adds up as one campaign, and **Assigned** otherwise. Saving an exception that merges two or more campaigns of the CDRs asks for confirmation first. **Default map** fills the default map of the application (`assets/labels-campaigns/default-campaign-map.json`, which a deployment can change; the workspaces without their own map use it); **Save Campaign Maps** applies it and refreshes chart caches. Labels are only visual: filters, stored CDR values and saved selections keep the original campaigns.

### Unassigned values warning

While the ready CDRs of the workspace have Operators, Vendors or Campaigns that no map assigns, every page shows a red card at its bottom centre with the number of unassigned values and, for each kind, the first values (hover them to see all). It appears as soon as a processed CDR brings a new value and stays until every value is assigned; **−** minimizes it for the rest of the browser session. The user-editor, admin and super-admin roles have an **Assign Operators**, **Assign Vendors** or **Assign Campaigns** button that opens the names found in the CDRs of the matching map (or the Campaign Maps) in Workspace Config; the user-viewer role sees the card without the buttons and is asked to inform an administrator.

### Map Areas

Map Areas are the administrative areas the **Points Lost Map** of [Scoring & GAP Analysis](scoring-gap-analysis.md#points-lost-map) colours in each country of the tests, such as municipalities in Spain, counties in the USA or census divisions in Canada. The application ships the areas of its main markets, used by every workspace without downloading anything (also on a server without Internet access): the ITL3 areas of the United Kingdom, and, at the level closest in size to them, Germany (districts), France (arrondissements), Italy (provinces), Spain (provinces), Poland (counties), Romania (counties), the Netherlands (provinces), Portugal (districts), Switzerland (cantons), the United States (counties), Canada (census subdivisions), Mexico (municipios), Japan (prefectures), South Korea (districts) and India (districts); `assets/map-areas/README.md` lists their sources and licences. A workspace can replace the areas shipped for any country with its own. Any other country is coloured as one area, the whole country, until the workspace adds its areas.

- **Countries of the tests** lists the countries found in a sample of the coordinates of the ready CDRs, with their share of the tests and their Map Areas (their own, the ones shipped with the application, or none). **Choose areas…** lists the administrative levels that [geoBoundaries](https://www.geoboundaries.org) offers for the country, each with its number of areas and its licence; the suggested level is the finest one with up to 12,000 areas that allows commercial use, and levels whose licence does not allow it ask before downloading. **Download** saves the areas, simplified, in the workspace (a large country can take a minute). The server must be able to reach geoboundaries.org and github.com; otherwise import the areas from a file.
- **Saved Map Areas** lists one layer per country with its areas, source, licence and last update, and **Delete** removes it.
- **Import areas from a file** reads a GeoJSON, or a ZIP holding one Shapefile, with one polygon per area: give the country (ISO 3166 alpha-3 code, such as `ESP`), the name of the areas (such as *municipality*) and, when it is not detected, the attribute that holds their names. It replaces the saved areas of that country.

Polygons with the same name in the same region are the parts of one area, and a name found in several regions takes the name of its region (for example *Washington (Ohio)*); names published with broken accents are repaired. Each CDR keeps the map area of each of its tests, and its country, in its `Map_Area` and `Map_Area_Country` columns (empty for a test outside every area), placed in the background while the application is idle (a minute without use and no background work queued) and, when the Map Areas are downloaded, imported or deleted, placed again with the new ones (the **Map Areas of the tests** background task, one CDR at a time; the **Map Area Fills** table keeps which Map Areas each CDR was placed with); until then the Points Lost Maps place the tests themselves. Calculate the scoring again after adding or changing the areas of a country: each job keeps the polygons of the areas its tests are in and the outline of their countries. The Map Areas are stored in the **Map Area Layers** table, and travel with the Mappings & Reference Data in Import / Export, transfers and backups. Country borders: Natural Earth (public domain).

### Spectrum Holdings

Spectrum Holdings list the licensed spectrum of each Operator for the **Spectrum** panel of [Network Insights](network-insights.md#spectrum). Enter one band per row with the header `Operator,Band,Duplex,Band Class,Bandwidth MHz,Notes`:

```text
Operator,Band,Duplex,Band Class,Bandwidth MHz,Notes
Vodafone,B20,FDD,Low,20,2x10 MHz
Vodafone,n78,TDD,High (TDD),90,
```

- **Operator** should match a label of the Operator Maps.
- **Band** uses LTE (`B20`) or NR (`n78`) names.
- **Duplex** is `FDD`, `TDD` or `SDL`; **Band Class** is `Low`, `Mid` or `High (TDD)`. Both are inferred for known bands when left empty.
- **Bandwidth MHz** is the total bandwidth held, for example `20` for 2×10 MHz FDD.

Comma, semicolon and tab separators are accepted, so rows can be pasted from a spreadsheet. **Save Spectrum Holdings** validates every row and replaces all holdings of the workspace; an empty text area removes them. The table above the editor shows the MHz per Operator and band class.

### Serving Networks

Serving Networks tell the [Vendor mapping](workspace-management.md#vendor-mapping) which networks' cells can serve the samples of each Operator, in order of preference. The [Non-Qualified Calls](non-qualified-calls.md#repeated-issues) find the site of the cell where each call ended with them too, for its repeated issues and the eNB / gNB of the Root Cause Analysis. An Operator's samples are often served by cells it does not own: Vodafone and Three share their RAN through eMOCN, and an MVNO such as Lebara uses its host network.

Nothing has to be typed or filled in: the table lists every Operator of the Operator Maps with the networks that serve it, and every Operator starts with the defaults — Vodafone and 3 serve each other, Lebara is served by Vodafone and 3, and every other Operator by its own network. The inventories say which network owns each cell and which one hosts its site, but not which Operators' subscribers the cell serves (eMOCN and MVNO agreements), so these relations are not read from them. Change them only when they differ:

- **Served by the cells of** shows the chosen networks in order of preference (numbered, joined by arrows). Click **+ network** to add a network after the others, or a chosen network to remove it; an Operator keeps at least one. The networks offered are Vodafone, 3, O2, EE and those of the Network Inventories of the workspace.
- **Source** is *Default* while an Operator follows the defaults and *Configured* when it differs; **Use default** returns it to them. Changed rows are highlighted until they are saved.
- **Maximum serving distance (km)**, 30 by default: a cell farther than this from a sample's position is not taken as its serving cell, because global cell identities only repeat across Operators.

**Save Serving Networks** stores the Operators that differ from the defaults (the others keep following them) and records the change in App Events. The mapped CDRs are then marked **Vendor mapping outdated** in the Map dialog until they are mapped again. The Serving Networks travel with Mappings & Reference Data in import, export, transfer, backup and restore.

### CDR Field Dictionary

The CDR Field Dictionary shows, for every field the modules read, the columns of the workspace's CDR files that can hold it, in order of preference: a CDR gives each field the first of its columns it has. The columns come from the field profile of the workspace's [CDR type](#cdr-type), so NetCheck CDRs and Umlaut CDRs keep their own column names. The fields are grouped by what reads them:

- **Normalised fields**: the fields every CDR row gains when it is processed, with the same name in every CDR type, such as its result, start and end times, setup time, throughput and latency.
- **CDR-Main fields**: the main fields added to every CDR (Campaign, Operator, Test Name, Technology, Session Type, Call Status...).
- **Non-Qualified Calls**: the fields of every call, the qualification that makes a call Non-Qualified, the identifier of a call or test (which keeps its follow-up) and the Speech sample inside its call.
- **DT Analyzer RCA**: the values of every call that the [DT Analyzer RCA](non-qualified-calls.md#dt-analyzer-rca) rules read.
- **Network Insights**: the radio, position and test fields of each CDR type (Data, Voice and Speech) and the dimensions the analyses are split by.
- **Vendor Mapping**: the serving cells of every sample and when it was measured.

**In the CDRs** names the column the processed CDRs of the workspace have for each field (*Not in the CDRs* when they have none of its columns). Change the columns of a field when the CDRs carry it in another column, separated by semicolons: for example, an Umlaut workspace that measures the call setup up to Option D instead of the alerting puts `Call Setup Duration (OptionD) [s]` first in **Setup time (s)**. **Find a field or column** filters the fields, **Changed fields only** shows the changed ones, which are highlighted, and **Use default** returns a field to its default columns; a field left empty returns to its default too.

**Save CDR Field Dictionary** stores only the changed fields and records them in App Events. Non-Qualified Calls (whose calls are indexed again, each keeping its follow-up also when its identifier changes), the DT Analyzer RCA, Network Insights and the Vendor Mapping read the changed columns at once; the Processing and CDR-Main fields are filled when the CDRs are processed, so [reprocess the CDRs](workspace-management.md) to apply those. The dictionary travels with Mappings & Reference Data in import, export, transfer, backup and restore; a dictionary made for another CDR type is left out on import.

## CDR type

The **Workspace Configuration** panel at the top chooses the **CDR type** of the workspace: the provider of the CDR files it processes. Every workspace handles the CDRs of one provider, with its own field names, values and methodologies, so the CDRs of two providers are never mixed. **NetCheck CDR** is the default and the only type supported today; **Umlaut CDR** and **P3 CDR** files keep their own field names and appear as *coming soon* until they are supported. The type is also chosen when a workspace is created and can be changed from the workspaces table of [Workspace Management](workspace-management.md) while the workspace has no Data, Voice or Speech CDRs; once it has CDRs it keeps their type. It is stored in the workspace database, so it travels with the workspace in transfers, Full Workspace packages and backups. [Benchmarking Providers](benchmarking-providers.md) describes the status of the adaptation to Umlaut and P3 CDRs.

## Main Cities

The Main Cities panel appears before Mappings & Reference Data and lists cities found in ready CDR datasets for the active workspace. Use the center buttons to move selected or all cities between the available list and the selected list, then choose **Save Main Cities**. The setting belongs to this workspace.

Every City selector — PPT filters, the PowerPoint export, Scoring, Network Insights, Non-Qualified Calls and Reporting Jobs — offers **Main Cities** as its first option. Applying it selects the configured cities that are available in the current selection.

## Portable operations

Administrators use Admin's **Import / Export / Transfer** and Super Admin's **Backup Protection** controls to move or restore workspace settings. Main Cities is a portable component alongside Report Templates and Mappings & Reference Data; full-workspace packages and database backups also retain the setting. The Mappings & Reference Data package (`mappings-reference-data/mappings-reference-data.json`) contains the Operator and Vendor Maps, Spectrum Holdings, Serving Networks, the CDR Field Dictionary, Campaign Maps and Map Areas, and importing it replaces all of them in the destination workspace.

For global runtime settings, see [Application Config](app-config.md). Super Admin's [Database Viewer](super-admin.md#database-viewer) documents the underlying Operator and Vendor mapping tables.

## Scoring & GAP Analysis Setup

A methodology defines the complete scoring setup: its title, environments, KPI definitions and weights and KPI priorities. Select or create a methodology before editing its settings. The aggregation hierarchy is an application setting ordered from the Aggregation levels of [Scoring & GAP Analysis](scoring-gap-analysis.md#3-set-filters-aggregation-and-reference), not part of a methodology.

### Methodology controls

| Action | Result |
| --- | --- |
| Create / Duplicate Methodology | Start a new definition or use an existing methodology as the basis for a revision. |
| Rename / edit title | Change the methodology identity or descriptive title. |
| Set Default | Choose the saved methodology initially offered for future scoring calculations. |
| Applies to campaigns | Choose the first and last campaign (or No start / No end) that **By campaign** calculations score with this methodology, saved by Save Methodology; the campaigns of two methodologies cannot overlap. |
| Save Methodology | Validate and persist the complete methodology, including every subpanel. |
| Export Methodology (JSON) | Download the selected methodology only. |
| Import Methodology (JSON) | Import a portable methodology document. |
| Admin Export / Backup | Package every saved methodology and the default selection together. |

> [!IMPORTANT]
> **One save operation.** Save Methodology appears above the subpanels and inside each one for convenience. Every instance saves the same complete setup; there are no independent priority saves.

The database is the source of record. Invalid edits do not replace the saved configuration. Historical jobs keep their methodology snapshot; changing the saved methodology changes the identity of subsequent calculations.

### Methodology Environments

Choose the environment to edit, or create, rename or delete one. Keep at least one environment with a positive overall allocation.

| Setting | What it controls |
| --- | --- |
| CDR filters: G_Level_1 and optional G_Level_2 | Which source rows belong to the environment. Leave the optional second value empty to include all its values. Overlapping environment selections are rejected. |
| Environment total | The maximum points allocated to that environment. |
| Edit weights by Points | Edit absolute KPI allocations. |
| Edit weights by Weight (%) | Edit relative shares while preserving the environment total and redistributing the other shares proportionally. |
| Distribute points keeping percentages | Allocate a new total using a reference environment's relative KPI shares. Thresholds and formulas are not copied. |

Creating an environment copies KPI rules and proportions from the selected reference; its own CDR filters determine the rows included. NetCheck 2026 includes Walk with zero initial points and editable relative weights.

### KPI Definitions, Scoring & Thresholds

Expand this subpanel to edit KPI specifications, thresholds and weights for the selected environment. Its pastel-red presentation separates the detailed KPI editor from the green setup panels.

- Edit the category, label, source CDR type, direction and mapping curve: Linear, Quadratic or Smooth curve.
- Use the KPI Definition pencil to edit the formula and filter JSON in a larger dialog. Closing the dialog retains the draft until Save Methodology.
- Configure thresholds, KPI type and score interpolation anchors. Ultra can be absent, numeric or derived from the best valid KPI measurement in its comparison context.
- Add or delete KPIs; at least one must remain. New KPIs receive stable K-number identifiers. Moving or deleting rows does not renumber other KPIs.
- Move KPIs within their category, change their category or reorder whole categories. Category totals show points, environment-relative weights and global weights.
- Renaming a KPI code updates its saved GAP priority reference without changing its priority.
- KPIs whose **Type** is **Reliable** form the Most Reliable Network scoring, with the same thresholds: set their **Most Reliable points** in the selected environment (the column can only be edited on Reliable KPIs). The line above the table counts the Reliable KPIs and their points. See [Most Reliable Network scoring](scoring-gap-analysis.md#most-reliable-network-scoring).

Max Points displays two decimal places while retaining full precision for calculation and unchanged allocations when saved. The formula determines the calculation basis; formulas and filters must use supported engine fields and operations.

### Methodology KPIs Priorities for GAP analysis

Maintain the transferable KPI priority list with up/down, first/last or specific-position controls. The position must be a whole number from 1 to the number of KPIs; Enter applies it and Escape cancels.

> [!NOTE]
> **Priority and result ordering.** The saved priority list does not currently determine GAP result order. Individual comparisons sort signed GAP from lowest to highest in the latest campaign, with unavailable values last; All Operators retains KPI definition order.

Web and PowerPoint GAP tables include a final sum for each comparison column. Individual PPT comparisons show Average KPI GAP and the average of the column GAP totals. These are distinct statistics; see the [complete Scoring & GAP Analysis guide](scoring-gap-analysis.md) for examples, coverage rules and JSON formats.


### Scoring Export Panels

The **Scoring Export Panels** panel, after the Scoring & GAP Analysis Setup, lists every panel of the Scoring & GAP Analysis results that the PowerPoint and Word documents can include, in a card per results tab (Summary, Scoring Charts, Scoring Tables, Geographical Areas, Scoring Trends, GAP Analysis and Points Lost) with the colour and icon of the tab, in the order of the page. For each panel:

- The **Exportable** switch includes it in the documents (a panel switched off is struck through). A panel that is not exportable is left out of **Export Selected Scoring Report**, **Generate Scoring Report**, the Scoring artifacts of Reporting Jobs and the Scoring section of the Bundle Report Templates, and their editors do not list it.
- **What to Export** chooses its operators with two buttons: **All Operators** (the reference included) or **Focus Operators**, those with the **Focus** role in the [Operator Maps](#operator-maps) (every operator when no label has it; the reference only when it is one of them). The default of each panel is marked with a dot: Focus Operators in Where to act, Where to act by performance owner, Biggest levers, Cities, Towns, Roads and Railways ranked, the route that loses most, Campaign comparison, Geographical Areas ranked, Each operator against the reference, the individual GAP tables, GAP by part, KPI GAP Profile and every Points Lost panel but Where the points go; All Operators in the others.

**Save Export Panels** saves the table for the workspace and **Restore Defaults** brings back the defaults; both are registered in App Events with the panels that changed. **Export All Operators in Focus panels**, in every export dialog and report editor, shows every operator in the Focus Operators panels of one document. The operators chosen on the page with the operator buttons of a panel still apply to **Export Selected Scoring Report** (see [Scoring & GAP Analysis](scoring-gap-analysis.md#what-is-in-the-powerpoint)). The panels travel as the **Scoring Export Panels** element of Admin's Import / Export / Transfer (importing them replaces those of each destination workspace), with Full Workspace transfers and with backups.


### Vendor-only filter labels

Across the application, values follow the Operator Maps and Vendor Maps order: `Vendor` lists pure vendors first, then the mixed group of a vendor (`Ericsson (Mixed)`), other and all-vendor groups, then the operators without a vendor, and the mixed groups of no vendor (`Mixed (non-Ericsson)`) last of all; `Operator_Vendor` is ordered by Operator and, within one Operator, by Vendor, with `Mixed (non-Ericsson)` last within its Operator; `Vendor_Operator` (`<Vendor>_<Operator>`) by Vendor and, within one Vendor, by Operator, with the mixed group of a vendor beside that vendor for each Operator (`Ericsson_3`, `Ericsson (Mixed)_3`, `Ericsson_VF_UK`, `Ericsson (Mixed)_VF_UK`) and the other mixed groups (`Mixed (non-Ericsson)`) last of all, after the operators without a vendor. In both, operators without a vendor (`<Operator> - All`) come last, in Operator Maps order, and values missing from the maps follow the mapped ones alphabetically. Operator-only identities follow with the display suffix ** - All**, based on canonical Operator identities, their configured aliases and cached CDR operators. Configured vendor identities take precedence, so actual vendors remain in the first group. Vendor mapping stores `Operator - All` in `Operator_Vendor` and `Vendor` for operator-only identities. Dataset exports, combined CDRs, transfers and backups preserve that value; legacy operator-only values without the suffix remain supported. This applies to PPT filters, Network Insights, data-preview column filters, Query Builder column filters and Report Template filter assistance.

CDR catalogue caches retain the `Operator_Vendor`, `Vendor`, `Region`, `Cluster`, `City`, `Campaign` and `Operator` universes. CDR processing refreshes them from their source columns, and catalogues of CDRs processed before Cluster existed are backfilled once. The caches remain part of workspace database backups and restores.

Operator mapping colours also apply to operators without a vendor in multivendor charts, including Vendor labels displayed as **Operator - All**. Vendor mapping colours apply to actual vendors.
