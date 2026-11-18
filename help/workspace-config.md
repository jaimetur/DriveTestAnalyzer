# Workspace Config

Workspace Config is a dedicated page for settings owned by the active workspace: Main Cities, Mappings & Reference Data (Operator, Vendor and Campaign Maps, Map Areas, Spectrum Holdings, Serving Networks and the CDR Field Dictionary), Auto-calculated Fields, Scoring & GAP Analysis Setup, Scoring Export Panels and the AI Assistant Glossary. These settings remain workspace-scoped and are included in the applicable import, export, transfer, backup and restore workflows (see [Portable operations](#portable-operations)).

> [!IMPORTANT]
> **Workspace settings.** Every edit on this page belongs to the active workspace. Application Config controls shared runtime settings.

> [!TIP]
> **Save versus export.** Save persists edits in the workspace. Export downloads a portable copy; it does not replace the Save action.

Open **Config → Workspace Config** from the main navigation at `/workspace-config`. Mapping and Main Cities actions use routes below `/workspace-config/`. The PPT Templates are not part of Workspace Config: they are managed in [PPT Designer](ppt-designer.md#ppt-templates). The page uses the same teal/navy palette as Application Config, and the **Modules & Sections** tab at the left edge links to its panels.

## Presentation & Guide

```presentations
workspace-config
guide:workspace-config.md
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Know which workspace is configured | [Access and active workspace](#access-and-active-workspace) |
| Name the operators, vendors and campaigns of the CDRs | [Mappings & Reference Data](#mappings-reference-data) |
| <span class="guide-sub">↳ Name the operators and their roles</span> | <span class="guide-sub">↳ [Operator Maps](#operator-maps)</span> |
| <span class="guide-sub">↳ Name the campaigns</span> | <span class="guide-sub">↳ [Campaign Maps](#campaign-maps)</span> |
| <span class="guide-sub">↳ Fix values that are still unassigned</span> | <span class="guide-sub">↳ [Unassigned values warning](#unassigned-values-warning)</span> |
| <span class="guide-sub">↳ Add map areas and postal codes</span> | <span class="guide-sub">↳ [Map Areas](#map-areas)</span> |
| <span class="guide-sub">↳ Add the spectrum holdings</span> | <span class="guide-sub">↳ [Spectrum Holdings](#spectrum-holdings)</span> |
| Add fields calculated from the CDR columns | [Auto-calculated Fields](#auto-calculated-fields) |
| <span class="guide-sub">↳ Write a field in the editor</span> | <span class="guide-sub">↳ [The editor](#the-editor)</span> |
| Know the CDR type of the workspace | [CDR type](#cdr-type) |
| Choose the main cities | [Main Cities](#main-cities) |
| Copy the configuration to another workspace | [Portable operations](#portable-operations) |
| Set up the scoring methodology of the workspace | [Scoring & GAP Analysis Setup](#scoring-gap-analysis-setup) |
| <span class="guide-sub">↳ Set up the environments</span> | <span class="guide-sub">↳ [Methodology Environments](#methodology-environments)</span> |
| <span class="guide-sub">↳ Define the KPIs, scoring and thresholds</span> | <span class="guide-sub">↳ [KPI Definitions, Scoring & Thresholds](#kpi-definitions-scoring-thresholds)</span> |
| <span class="guide-sub">↳ Choose the panels of the scoring exports</span> | <span class="guide-sub">↳ [Scoring Export Panels](#scoring-export-panels)</span> |
| <span class="guide-sub">↳ Teach the AI Assistant the workspace words</span> | <span class="guide-sub">↳ [AI Assistant Glossary](#ai-assistant-glossary)</span> |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Access and active workspace

The Workspace Config section is available to `user-editor`, `admin` and `super-admin` accounts; `user-viewer` accounts do not have access. Open a workspace before using its configuration panels; their contents and changes belong only to that workspace.

## Mappings & Reference Data

The Mappings & Reference Data panel holds Operator Maps, Vendor Maps, Campaign Maps, Map Areas, Spectrum Holdings, Serving Networks and the CDR Field Dictionary as independently collapsible subpanels, with light blue headers under the dark parent header; their expansion states are saved.

The maps only change how values are shown: every filter, table, chart, legend and report shows the labels, and choosing a label selects all its names. They never rewrite source workbooks, stored CDR rows or combined CDR tables (only Preview Dataset shows the names as they are in the CDRs), and saving, moving or deleting a label clears chart caches so later views use the new settings.

### Operator Maps

Operator Maps set how the Operators are named, ordered and coloured. They have two numbered subpanels, each collapsible (the browser remembers it).

**1 · Operator names found in the CDRs** lists every Operator name of the ready CDRs with:

- the number of CDRs that contain it (hover it to see their names);
- its **Label** and **Comments** (the editable fields, pastel yellow). Comments are a free reminder of what the name holds, for example that `Vodafone SA` is the SA terminal of the NSA drive of 2026-Q2; **Save assignments** saves them too, they travel with the Operator Maps and every change is recorded in App Events;
- its read-only **Status**:
  - **Unassigned** (red, and the number of the subpanel turns red): the name has no label, so it is shown as it is and never added up with other names. **Use own names** gives every unassigned name a label with its own name.
  - **Merges N:** the label stands for N names that coincide in the same campaign and NR Mode (in one CDR or in CDRs of that campaign and NR Mode), where they are added up as one Operator. Hover it for the others and the campaigns where they coincide (`26-Q2 (NSA)`).
  - **Assigned:** the label stands for this name only, or also for names never in the same campaign and NR Mode (hover to see them), so never added up: `Vodafone UK` in the NSA campaigns and `Vodafone SM` in an SA campaign can share `VF`.
- the **Role** and **NR Modes** of its label (set in subpanel 2; they follow a label chosen in the list at once, also before saving).

Choose the label of each name in its list, then press **Save assignments**:

- **The list:** the labels of subpanel 2, or **+ New label…** to type a new one (<kbd>Enter</kbd> accepts, <kbd>Esc</kbd> cancels) that every list then offers; it is added at the end of subpanel 2 when you save.
- **Keeping names apart:** each name keeps its own label unless several share one: `Vodafone UK` → `VF`, `Vodafone SA` → `VF-SA` and `Vodafone VoNR` → `VF-VoNR` stay apart, while two spellings of one network (`Vodafone` and `Vodafone UK`) can share `VF`.
- **Names that are labels:** a name that is itself a label (`EE`) cannot be changed here: rename the label in subpanel 2.
- **Confirmation:** saving asks first when a label would add up names it did not add up before (names that coincide in a campaign and NR Mode, which the dialog names), when a name leaves a label that saved filters use (they no longer include it; the dialog says how many), and when a new label contains `_`, which also separates Operator and Vendor in `Operator_Vendor` values such as `VF_Ericsson`.

**2 · Operator labels** lists one row per label with its **Order**, **Colour**, **Label**, **Role**, **NR Modes**, **Possible names in the CDRs** and **Actions**:

- **Possible names in the CDRs:** chips of how the label is written in the CDRs of the different campaigns, highlighted with their number of CDRs when the current CDRs have them, grey for names of other campaigns, from the name in most CDRs (alphabetically on ties). **×** removes a name and **Add a name** with **+** adds one; a name of another label moves here at once. The label also stands for the name written like itself.
- **Hover and click:** hovering a chip, a CDRs count or a **Merges N** badge (under the label: it adds up N names that coincide in a campaign and NR Mode) shows its CDRs or names; clicking keeps them in a floating panel until it is closed (×, <kbd>Esc</kbd> or a click outside).
- **New Operator label** (or **New Vendor label**) creates a label in a dialog with its colour, role, NR Modes and possible names; **Add label** takes one per line (commas and semicolons too).
- **Save Labels**, below the table, saves every changed label at once, with the confirmation of subpanel 1 (<kbd>Enter</kbd> in a label saves that one).
- **Move up** / **Move down** set its position in Operator charts and Subscriber dimensions (the first and last rows cannot move beyond the table). **Delete** removes it after confirmation; its names are shown as they are until they get another label.
- **Colour:** the label's chart colour; charts derive related shades to distinguish campaigns or series.

**Role** is **Include** (yellow, the default: analysed as usual), **Focus** (green) or **Exclude** (red), explained in a note above the labels and recorded in App Events when it changes:

- **Focus:** the label, with every name it stands for, is one of the **Focus operators** of [Scoring & GAP Analysis](scoring-gap-analysis.md#persistence-and-exports): Where to act, the locations ranked, the individual GAP comparisons, GAP by part, the KPI GAP Profile and the Points Lost views of its PowerPoint and Word (from the page and the reports of [Reporting](reporting.md)) are those of the Focus operators, and the operator choices of those sections list them first (every operator when no label is Focus). **Generate comments** in [PPT Designer](ppt-designer.md#generated-comments) follows them too.
- **Exclude:** the operator is left out of every analysis, filter, chart and report of the workspace, in every module, as if every Operator filter left it out (as `NOT Lebara` does, see [Operator patterns](web-interface.md#operator-patterns)), so the Operator filters can stay at All; no Operator list or GAP reference offers it, and its names stay in subpanel 1. Saved Scorings are calculated again when the excluded operators change. At least one label must stay included: a Role that would exclude every label reverts, and saving, deleting or importing labels that would exclude every label is refused.

**NR Modes** are those the operator has a network in: **NSA and SA** (the default), **NSA only** (blue) or **SA only** (magenta), recorded in App Events when they change.

- **Tests out of scope:** an operator without a network in an NR Mode, such as Three, which has no SA, has its tests of the CDRs of that NR Mode out of scope (in the SA CDRs its tests run on LTE and EN-DC, which its NSA CDRs already measure). They are left out of every analysis, filter, chart and report of every module (Scoring Trends and Country Areas included), and the Operator filters do not offer the operator for the CDRs of that NR Mode alone; its tests of the other NR Mode stay. In [Non-Qualified Calls](non-qualified-calls.md#nq-prioritization) those calls are out of scope (*Out of scope · SA · Three*).
- **Saved Scorings** with CDRs of that NR Mode are calculated again when the NR Modes change, and their panel headings name the pairs out of scope (*Out of scope: SA · Three*).
- **Suggestion:** **Suggested: NSA only** appears under a label whose Non-Qualified Calls of the SA campaigns barely ran on NR SA (under 10 %); it is never applied on its own.
- **Exclude wins:** a label with the Role **Exclude** is left out in both NR Modes.
- **Notes:** under **NSA only** or **SA only**, a red note names the NR Mode out of scope (*SA out of scope in every module*), and subpanel 1 shows the label's NR Modes (blue *NSA only*, magenta *SA only*) beside its Role.
- **Earlier versions:** a package exported before the NR Modes gives every label both NR Modes. Workspaces whose Non-Qualified Calls left an NR Mode · operator pair out of scope before (SA · Three, saved in the NQ Prioritization or the default one) took it as the NR Modes of that label once.

**Out of scope in this workspace**, above the subpanels, sums up what is left out: in **Every module**, the labels with the Role Exclude and the NR Mode · operator pairs; in **Non-Qualified Calls only**, the regions of the Out of Scope settings of the NQ Prioritization and the operators that are not Focus operators, which the other modules keep.

**Renaming a label** updates its exact references in:

- Report Templates (slide and chart titles, legends, dynamic values and the values of their Operator, Operator_Vendor, Vendor_Operator and Vendor filter conditions; for a number label such as `3`, only filters, legends and dynamic values, never layouts, thresholds or other conditions) and saved Designs;
- the Operator, Operator_Vendor, Vendor_Operator and Vendor filter values of Scoring report configurations, the last Scoring calculation (GAP reference too), the Saved Scorings (GAP reference and filters; found again with the new label and calculated again when opened), the reports of [Reporting](reporting.md), the Network Insights Analysis Selections, the CDR Analysis filters of each CDR and the Non-Qualified Calls filters (`VF_UK` → `VF` also turns `VF_UK_Ericsson` into `VF_Ericsson` and `Ericsson_VF_UK` into `Ericsson_VF`).

Campaign filters keep the full campaign value, so changing the Campaign Maps never requires renaming them.

**Starting labels.** A new workspace starts with the operators of the country chosen for it in [Workspace Management](workspace-management.md#workspace-lifecycle), in their corporate colours and with the usual ways they are written in the CDRs, none with a Role: for example `Telekom`, `Vodafone`, `O2` and `1&1` in Germany, where `o2 - de` is O2; or VF, VF SA, VF VoNR, VF SM, Three, EE, O2 and Lebara in the United Kingdom, where `Vodafone UK`, `VFUK` or `Vodafone` are VF and `3` is Three, which has NSA only. Without a country it starts without Operator Maps. The operators of the 50 listed countries come from `assets/labels-operators/operators-by-country.json`, which a deployment can change.

### Vendor Maps

Vendor Maps work exactly as the [Operator Maps](#operator-maps), without Role and NR Modes: **1 · Vendor names found in the CDRs** labels every Vendor name of the ready CDRs (`<Operator> - All` is not a Vendor), and **2 · Vendor labels** has the same **Order**, **Colour**, **Label**, **Possible names in the CDRs** and **Actions**. Names match without regard to case. Renaming a Vendor label updates the same references as an Operator rename.

Vendor order sets the chart sequence of Vendor dimensions and the Vendor part of `Operator_Vendor` values; filters, tables, charts and reports show the Operator and Vendor labels of an `Operator_Vendor`.

A new workspace starts with these labels, in this order, from `assets/labels-vendors/default-vendor-maps.json` (which a deployment can change): Ericsson (`#0255AD`), Ericsson (Mixed) (`#002F61`), Huawei (`#FBBD00`), Samsung (`#008521`), NSN (`#8C00FF`, also `Nokia` and `NNS`), SCW (`#6F42C1`), Mixed (non-Ericsson) (`#5E4F2E`, also `Mixed`), Other Vendor (`#5E4F26`), (blank) (`#7A8791`) and Unknown (`#7A8791`).

### Campaign Maps

Campaign Maps set how every chart, table, legend, filter and PowerPoint or Word report names and orders campaigns. They follow a pattern rather than a list, so later campaigns such as `2026-Q3` or `2027-Q1` follow it without editing.

- **Label format** writes the label from the parts of the campaign name: `{year}` (2026), `{yy}` (26), `{quarter}` (2), `{mode}` (SA or NSA) and `{market}` (the country code, such as UK). Characters inside the braces of a marker are written only when the campaign has that part: the default `{yy}-Q{quarter}{-mode}` shows `UK_Q2_2026` as `26-Q2` and `UK_Q2_SA_2026` as `26-Q2-SA` (`{year}` writes `2026-Q2` and `2026-Q2-SA`).
- **Order inside a quarter:** campaigns are ordered by year and quarter, and within a quarter by mode: by default the one without mode, then NSA, then SA; the arrows change it. **Show in label**, next to NSA and SA, chooses the modes `{mode}` writes: unchecking NSA shows the NSA campaigns as `26-Q3` while SA stays `26-Q3-SA`; an NSA campaign then reads like the campaign without a mode of its quarter, and both are one campaign (the Preview shows **Merges** when the CDRs have both).
- **Exceptions** give their own label to one or more source campaigns that do not follow the pattern. They are ordered by the year and quarter of their label, after the campaigns of that quarter, or first, in table order, when the label has none. The label can be written as a campaign (`2026-Q2 Flex`) or as the format does (`26-Q2-Flex`, ordered in 2026 Q2). Campaigns without a year and quarter and without an exception keep their name.
- **Flex:** a campaign whose label or source campaign has the word Flex (`26-Q2-Flex`, `UK_Flex_2026`) is a [Flex campaign](workspace-management.md#flex-campaigns), a local one used only where it is checked by hand.

The **Preview** lists the campaigns of the ready CDRs with the labels and order of the map being edited, and their **Status**: **Unassigned** for a campaign without a year and quarter and without an exception (its **+** adds an exception labelled with its own name), **Merges N** when N campaigns share its label (added up as one campaign everywhere), and **Assigned** otherwise. Saving an exception that merges campaigns of the CDRs asks for confirmation first. **Default map** fills the default map of the application (`assets/labels-campaigns/default-campaign-map.json`, which a deployment can change; workspaces without their own map use it); **Save Campaign Maps** applies it and refreshes chart caches. Labels are only visual: filters, stored CDR values and saved selections keep the original campaigns.

### Unassigned values warning

While the ready CDRs have Operators, Vendors or Campaigns that no map assigns, every page shows a red card at its bottom centre with the number of unassigned values and, per kind, the first ones (hover for all). It appears as soon as a processed CDR brings a new value and stays until every value is assigned; **−** minimizes it for the browser session. User-editors, admins and super-admins get **Assign Operators**, **Assign Vendors** or **Assign Campaigns**, which open the names found in the CDRs of that map; user-viewers see the card without buttons and are asked to inform an administrator.

### Map Areas

Map Areas are the administrative areas the **Points Lost Map** of [Scoring & GAP Analysis](scoring-gap-analysis.md#points-lost-map) colours in each country of the tests, such as municipalities in Spain or counties in the USA.

- **Shipped areas**, used without downloading anything (also on a server without Internet access): the ITL3 areas of the United Kingdom and, at the level closest in size to them, Germany (districts), France (arrondissements), Italy (provinces), Spain (provinces), Poland (counties), Romania (counties), the Netherlands (provinces), Portugal (districts), Switzerland (cantons), the United States (counties), Canada (census subdivisions), Mexico (municipios), Japan (prefectures), South Korea (districts) and India (districts); `assets/map-areas/README.md` lists their sources and licences. A workspace can replace them with its own; any other country is coloured as one area until the workspace adds its areas.
- **Countries of the tests** lists the countries found in a sample of the coordinates of the CDRs of the latest campaign of each NR Mode (of every ready CDR while none says its campaign), with their share of the tests and their Map Areas (own, shipped or none).
  - **Choose areas…** lists the administrative levels [geoBoundaries](https://www.geoboundaries.org) offers for the country, with their number of areas and licence; the suggested level is the finest with up to 12,000 areas that allows commercial use, and levels whose licence does not allow it ask before downloading.
  - **Download** saves the areas, simplified, in the workspace (a large country can take a minute). The server must reach geoboundaries.org and github.com; otherwise import a file.
- **Saved Map Areas** lists one layer per country with its areas, source, licence and last update; **Delete** removes it.
- **Import areas from a file** reads a GeoJSON, or a ZIP with one Shapefile, with one polygon per area: give the country (ISO 3166 alpha-3, such as `ESP`), the name of the areas (*municipality*) and, when not detected, the attribute with their names. It replaces the saved areas of that country. With **Areas** set to **Postal Codes** it saves the file as the [Postal Codes](#postal-codes) of the country instead; use only maps whose licence allows it.
- **Names:** polygons with the same name in the same region are parts of one area; a name found in several regions takes the name of its region (*Washington (Ohio)*); names published with broken accents are repaired.
- **Areas of the tests:** each CDR keeps the area of each test, and its country, in its `Map_Area` and `Map_Area_Country` columns (empty outside every area). They are placed in the background while the application is idle (a minute without use and no background work queued) and again when Map Areas are downloaded, imported or deleted (the **Map Areas of the tests** task, one CDR at a time; the **Map Area Fills** table keeps which areas each CDR was placed with); until then the Points Lost Maps place the tests themselves. Calculate the scoring again after changing the areas of a country: each job keeps the polygons of its tests' areas and the outline of their countries.
- **Storage:** the **Map Area Layers** table. Country borders: Natural Earth (public domain).

#### Postal Codes

The **Postal Codes** of a country are the areas of **Maps per Postal Code** in the [Points Lost Map](scoring-gap-analysis.md#points-lost-map), used only by the Saved Scorings that ask for them, so other calculations and the CDR rows do not change. No free set of postal polygons covers the world, so they are worked out from the postal code points [GeoNames](https://www.geonames.org) publishes for about 120 countries (Creative Commons Attribution 4.0): each code takes the land closest to its points, cut to its country. They are approximate, not official borders.

A workspace keeps up to three maps per country, and each Saved Scoring chooses one in the **Country Areas** of its calculation. In the **Postal Codes** column of **Countries of the tests**, the list shows which ones the country has and chooses which one to get; **Download**, **Download again** or **Import file** saves it, and the others stay.

- **Full postcodes** (the Saved Scoring default where GeoNames publishes them, so far the United Kingdom, with Northern Ireland): postcode districts (`RG14`) worked out from about 1.8 million full postcode points, so they follow the districts closely, also in city centres. Downloaded from download.geonames.org (about 14 MB) and worked out in the workspace in about a minute; until then a copy included in the application is used, also on a server that cannot reach that address (a calculation tries again after an hour).
- **One point per place:** from the GeoNames file of the country, lighter and less precise; the default of every other country. Each download is registered in App Events, also when it fails. A server without access imports a file, or receives the Postal Codes of another server with the Mappings & Reference Data.
- **Own file:** a map of your own, such as one your project team has a licence for. **Import file** opens **Import areas from a file** with **Postal Codes** and the country filled in; another import replaces the Own file of that country, and its other maps stay.

About the areas worked out from GeoNames:

- **Level:** the codes GeoNames publishes; a country with more than 12,000 codes groups them by their first characters (the first 4 digits in the United States).
- **Codes without a point of their own**, such as those of a city centre with **One point per place**, form one area named after them (`28070, 28071 +6 · Madrid`).
- **Quality** varies: GeoNames estimates many coordinates; Chile, China, Ireland, Malta, Argentina and Brazil only have part of their codes; Germany lists codes of large companies, which then name their areas.

**Saved Postal Codes** lists the saved maps with their source and licence; **Delete** removes one. A calculation that needs a map the workspace lacks downloads it (it then appears in this list); an Own file cannot be downloaded, so the Saved Scoring takes the full postcodes and its maps say so. A Saved Scoring keeps the map it was calculated with until it is calculated again. They are stored in the **Map Area Postal Layers** table.

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

Serving Networks tell the [Vendor mapping](workspace-management.md#vendor-mapping) which networks' cells can serve the samples of each Operator, in order of preference; [Non-Qualified Calls](non-qualified-calls.md#repeated-issues) use them to find the site of the cell where each call ended (its repeated issues and the eNB / gNB of the Root Cause Analysis), and Network Insights to find serving cells. An Operator's samples are often served by cells it does not own: Vodafone and Three share their RAN through eMOCN, and an MVNO such as Lebara uses its host network.

Nothing has to be filled in: the table lists every Operator of the Operator Maps with its networks, starting from the defaults (Vodafone and 3 serve each other, Lebara is served by Vodafone and 3, every other Operator by its own network). Inventories say which network owns each cell and which hosts its site, but not whose subscribers it serves (eMOCN and MVNO agreements), so these relations are not read from them. Change them only when they differ:

- **Served by the cells of** shows the chosen networks in order (numbered, joined by arrows). Click a chip such as **+ Vodafone** to add that network last, or a chosen network to remove it; an Operator keeps at least one. Offered: Vodafone, 3, O2, EE and the networks of the workspace's Network Inventories.
- **Source** is *Default* or *Configured*; **Use default** returns an Operator to the defaults. Changed rows are highlighted until saved.
- **Maximum serving distance (km)**, 30 by default: a cell farther than this from a sample is not taken as its serving cell, because global cell identities repeat across Operators.

**Save Serving Networks** stores the Operators that differ from the defaults (the others keep following them) and records the change in App Events. The mapped CDRs are then marked **Vendor mapping outdated** in the Map dialog until mapped again.

### CDR Field Dictionary

The CDR Field Dictionary shows, for every field the modules read, the columns of the workspace's CDR files that can hold it, in order of preference: a CDR gives each field the first of those columns it has. The columns come from the field profile of the workspace's [CDR type](#cdr-type), so NetCheck and Umlaut CDRs keep their own column names. Fields are grouped by what reads them:

- **Normalised fields:** those every CDR row gains when processed, with the same name in every CDR type (result, start and end times, setup time, throughput, latency…).
- **CDR-Main fields:** the main fields added to every CDR (Campaign, Operator, Test Name, Technology, Session Type, Call Status...).
- **Non-Qualified Calls:** the fields of every call, the qualification that makes a call Non-Qualified, the identifier of a call or test (which keeps its follow-up), its IDs in the provider's tools (NetCheck CloudNM: Session_ID_A and Session_ID_B of a call, Test_ID and Session_id of a test; shown beside its JOIN_ID and found by the call searches) and the Speech sample inside its call.
- **DT Analyzer RCA:** the values of every call that the [DT Analyzer RCA](non-qualified-calls.md#dt-analyzer-rca) rules read.
- **Network Insights:** the radio, position and test fields of each CDR type and the dimensions the analyses are split by.
- **Vendor Mapping:** the serving cells of every sample and when it was measured.

**In the CDRs** names the column the processed CDRs have for each field (*Not in the CDRs* when none). Change the columns of a field, separated by semicolons, when the CDRs carry it elsewhere: an Umlaut workspace that measures the call setup up to Option D instead of the alerting puts `Call Setup Duration (OptionD) [s]` first in **Setup time (s)**. **Find a field or column** filters the fields, **Changed fields only** shows the changed (highlighted) ones, and **Use default**, or leaving a field empty, returns it to its default columns.

**Save CDR Field Dictionary** stores only the changed fields and records them in App Events. Non-Qualified Calls (whose calls are indexed again, each keeping its follow-up even when its identifier changes), the DT Analyzer RCA, Network Insights and the Vendor Mapping read the changed columns at once; the Processing and CDR-Main fields are filled when the CDRs are processed, so [reprocess the CDRs](workspace-management.md) to apply those.

## Auto-calculated Fields

An Auto-calculated Field gives each CDR row a value worked out from its other fields, such as the NSA, SA or Others of each sample from its RAT. It becomes a column of every individual and combined CDR table of the types it applies to, so filters, splits, legends, KPIs and Query Builder use it like any other field.

The **Auto-calculated Fields** panel follows Mappings & Reference Data, with a card per field in the order they are worked out:

- its name and number of **rules**, or **Formula**;
- **Applies to:** each CDR type it is a column of (CDR-DATA in green, CDR-VOICE in blue, CDR-SPEECH in purple) with the state of its tables: up to date, **updating** (with progress) or waiting for an update;
- the values it gives, as a bar with the share of rows of each value: the most frequent one by one, the rest as *Other values* and rows no rule takes as *No value* (read as the editor tries a field, on up to 150,000 rows per CDR type; until then, or without CDRs of its types, the values its rules give);
- **From** (the fields it reads) and **When no rule applies** (what the other rows get);
- **Used in:** the PPT Templates whose charts show, split or filter by it, the PPT Designs that filter by it or use those templates, the Query Builder queries and the fields that read it (hover a count for their names).

Above the cards, a pill sums up the CDR tables (*All CDR tables up to date*, *Updating CDR tables* with its percentage, or the fields waiting), **Find a field, value or CDR field** filters the cards and **Data**, **Voice** and **Speech** show only the fields of those types. **New Field** opens the editor on a new field and a card opens its field; the **⋯** menu holds **Import JSON…**, **Export All Fields** and **Re-materialize All Fields**. The same editor opens from the PPT Templates editor and from PPT Designer (**Auto-Calculated Fields**). Every account that opens Workspace Config can change the fields.

### The editor

The fields are listed on the left in the order they are worked out: a field can read the fields above it. Its arrows move it; an order where a field would read one below it is refused. The chosen field is edited on the right:

- **Name** and **Applies to** (CDR-Data, CDR-Voice, CDR-Speech).
- **What value each row gets**, from **Rules** or a **Formula**:
  - **Rules** are tried top to bottom; the first whose condition holds gives the value. A rule has one or more conditions, all (AND) or any (OR) of which must hold, and its result. A condition is a field, an operator and its values. The field is one of the CDRs of the chosen types or an Auto-calculated Field above; **+ or** adds another spelling, and the first one the CDR has is read (`[RAT] OR [RAT_A]`). While typing a value, the field's values in the CDRs are offered with their row counts; operators with several values keep them as chips. A rule mixing AND and OR is edited as text.
  - A **Formula** is Tableau-style: `IF condition THEN value`, any `ELSEIF condition THEN value`, an optional `ELSE value` and `END`; a THEN or ELSE can hold another `IF … END`. Typing `[` offers the fields, and buttons insert IF, ELSEIF, ELSE, AND, OR, a field or an operator. Switching to Formula writes the rules as a formula; switching back turns a formula without nested IF blocks into rules.
  - **Operators and syntax** lists every operator with an example (table below).
- **When no rule gives a value:** the rows stay empty, take a fixed value, or keep the value of another field (and, where it is empty, a fixed value or nothing).
- **Checks while editing:** an error keeps **Save** disabled and says what to change: an unreadable condition or formula, a field reading itself or one below it, a name the CDRs already have, or a name the application keeps in the CDR tables (`NR_Mode`, the NR Mode of the CDR of each row, `Operator`, `Campaign`…). A warning names the CDR types that lack a field a condition reads: there those conditions are skipped.
- **Result on the CDRs** tries the unsaved field on up to 150,000 rows of each CDR type (every n-th row of each CDR): the rows of each value with their share, the rows each rule takes, and the rows no rule takes, with what they get and their values in each field the rules read (why no rule takes them, such as calls whose result is `Dropped`).

| Operator | Meaning | Example |
|---|---|---|
| `=`, `!=` | is, is not | `[Test_Result] = Completed` |
| `IN`, `NOT IN` | is one of, is none of | `[RAT] IN (LTE, 'NR SA')` |
| `CONTAINS`, `NOT CONTAINS` | contains (any of the values), does not contain | `[Test_Name] CONTAINS (YouTube, FDFS)` |
| `STARTS WITH`, `NOT STARTS WITH` | starts with (any of the values), does not | `[RAT] STARTS WITH 'NR SA'` |
| `ENDS WITH`, `NOT ENDS WITH` | ends with (any of the values), does not | `[RAT] ENDS WITH '/LTE'` |
| `MATCHES`, `NOT MATCHES` | matches the regular expression, does not | `[Test_Name] MATCHES 'FDTT .* DL'` |
| `>`, `>=`, `<`, `<=` | compares numbers | `[Mean_Data_Rate] > 100` |
| `IS EMPTY`, `IS NOT EMPTY` | has no value, has one | `[Failure_Category] IS EMPTY` |

Text comparisons ignore case. A value with spaces or symbols is quoted (`'NR SA'`, `\'` for a quote). In `MATCHES '(^|/)NR(/|$)'`, `(^|/)` is the start of the text or a `/`, and `(/|$)` a `/` or the end: it finds `NR` as one item of a list such as `NR/LTE` or `LTE/NR/GSM`, but not inside `LTE-5GNR`.

### Saving and updates

- **Save** (<kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>S</kbd>) saves the field alone and updates, in the background, only its column and those of the fields that read it, in every individual and combined CDR table of its types, as its card and the [CDR Tables Updates](workspace-management.md#cdr-tables-updates) card of [Workspace Management](workspace-management.md) show. There is nothing else to save; closing the editor (its close button, a click outside it or <kbd>Esc</kbd>, which first hides an open suggestion list) asks only while the field has unsaved changes.
- **Delete** removes a field and its column (refused while another field reads it); **Duplicate** opens a copy below it, saved when it is saved.
- **What is updated:** the fields are compared with what the CDR tables hold after the last complete update, so a save that changes no CDR (a new order) updates nothing, and an update stopped half-way, or a change imported meanwhile, is caught up by the next one.
- **Pending updates** (fields imported or restored, saved while another update ran, or cut by a restart) start on their own within half a minute, without opening Workspace Management; after a failure the next try waits ten minutes, and one stopped by hand waits for **Re-materialize All Fields**.
- **Re-materialize All Fields** works every field out again in every CDR table: only needed to repair them (after an interrupted update, for example); disabled while any CDR table update runs. The tool stays usable during updates; the CDR Tables Updates card shows one bar per active task with its table, phase and row operations.
- **Types:** fields apply only to their CDR types and leave the types they no longer apply to. The combined tables keep the fields the conditions read, the preview-filter fields and the resulting Auto-calculated Fields.
- **Renaming** keeps it the same field: the new name reaches the fields that read it, the PPT Templates (KPI, filters, splits and legends), the saved Designs and the SQL of the saved Query Builder queries where it is a column of the CDR tables (quoted or not; text values and comments are left as they are), and its column is renamed. An import, transfer or restore that renames a field does the same (see [Matching and creators](administrator-config.md#matching-and-creators)).
- **Import JSON…** adds the fields of a file and replaces those with the same name, after confirming them; **Export All Fields** downloads them all. Both keep the format of earlier versions, which import as they are (`[Field A] OR [Field B]`, the former `Field A|Field B` and unbracketed fields included).

### Starting fields

New workspaces start with:

- `Call_Family` (Voice and Speech): `MultiRAB`, `WhatsApp` or `VoLTE` from the Session Type, `CALL` otherwise.
- `Test_Family` (Data): `YouTube`, `FDFS` or `FDTT` from the Test Name, otherwise the Type of Test.
- `Test_Result_Group`: `Success` (Completed, Visible Completed) or `Failure` (Cutoff, Failed, Dropped) from the result of the test or call.
- `RAT_Group`: the RAT of each sample with each technology on its own (`EN-DC`, `NR SA` with NE-DC, `LTE`, `VoNR`, `EPSFB`, `VoLTE`, `CSFB`, `2G/3G`, `No Service`) and its combinations grouped (`ENDC Mixed`, `NR SA Mixed`, `VoNR Mixed`, `VoLTE Mixed`, `LTE Mixed`), the RAT itself otherwise (`Unknown`).
- `NR_Mode_from_RAT`: `SA` when the RAT of the sample used 5G SA (`NR SA`, `NE-DC`, `5G NR`, `VoNR`, `EPSFB`, or `NR` as an item of the list, as Voice and Speech CDRs write it), `NSA` when it used 5G NSA and no SA (`EN-DC`, `LTE-5GNR`), and `Others` otherwise (LTE, VoLTE, 2G and 3G, no service, unknown). It is the 5G mode of each sample, not **NR Mode**, the NR Mode of the CDR it comes from.

## CDR type

The **Workspace Configuration** panel at the top chooses the **CDR type** of the workspace, saved with **Save CDR Type**: the provider of the CDR files it processes. Each workspace handles the CDRs of one provider, with its own field names, values and methodologies, so CDRs of two providers are never mixed. **NetCheck CDR** is the default and the only type supported today; **Umlaut CDR**, **P3 CDR** and **RootMetrics CDR** keep their own field names and appear as *coming soon*. The type is also chosen when a workspace is created and can be changed from the workspaces table of [Workspace Management](workspace-management.md#workspace-lifecycle) while the workspace has no Data, Voice or Speech CDRs. It is stored in the workspace database, so it travels with the workspace in transfers, Full Workspace packages and backups. [Benchmarking Providers](benchmarking-providers.md) describes the adaptation to Umlaut and P3 CDRs.

## Main Cities

The Main Cities panel, before Mappings & Reference Data, lists the cities found in the ready CDRs of the workspace. Move selected or all cities between the available and selected lists with the center buttons, then choose **Save Main Cities**.

Every City selector (PPT filters, the PowerPoint export, Scoring, Network Insights, Non-Qualified Calls and the reports of [Reporting](reporting.md)) offers **Main Cities** first; applying it selects the configured cities available in the current selection.

## Portable operations

Administrators move or restore workspace settings with Admin's **Import / Export / Transfer** and Super Admin's **Backup Protection**; full-workspace packages and database backups keep every setting of this page.

- **Mappings & Reference Data** (`mappings-reference-data/mappings-reference-data.json`): the Operator Maps (with comments, roles and NR Modes), Vendor Maps, Campaign Maps, Map Areas, Postal Codes, Spectrum Holdings, Serving Networks and the CDR Field Dictionary (a dictionary made for another CDR type is left out on import). Importing it replaces all of them in the destination workspace.
- **Main Cities**, **Report Templates**, **Scoring Export Panels** and **AI Assistant Glossary** are elements of their own (see their sections).

For global runtime settings, see [Application Config](app-config.md). Super Admin's [Database Viewer](super-admin.md#database-viewer) documents the underlying Operator and Vendor mapping tables.

## Scoring & GAP Analysis Setup

A methodology defines the complete scoring setup: its title, environments, KPI definitions and weights and KPI priorities. Select or create a methodology before editing it. The aggregation hierarchy is an application setting ordered from **Split by** of [Scoring & GAP Analysis](scoring-gap-analysis.md#set-filters-break-down-by-and-reference), not part of a methodology.

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

The database is the source of record: invalid edits do not replace the saved configuration. Historical jobs keep their methodology snapshot; changing the saved methodology changes the identity of later calculations.

### Methodology Environments

Choose the environment to edit, or create, rename or delete one. Keep at least one environment with a positive overall allocation.

- **CDR filters (G_Level_1 and optional G_Level_2):** which source rows belong to the environment; leave the second empty to include all its values. Overlapping environments are rejected.
- **Environment total:** the maximum points of the environment.
- **Edit weights by Points** edits absolute KPI allocations; **by Weight (%)** edits relative shares, keeping the environment total and redistributing the other shares proportionally.
- **Distribute points keeping percentages:** allocates a new total with a reference environment's relative KPI shares (thresholds and formulas are not copied).
- **New environment:** copies the KPI rules and proportions of the selected reference; its own CDR filters decide its rows. NetCheck 2026 includes Walk with zero initial points and editable relative weights.

### KPI Definitions, Scoring & Thresholds

Expand this subpanel (pastel red, apart from the green setup panels) to edit the KPIs, thresholds and weights of the selected environment.

- Edit the category, label, source CDR type, direction and mapping curve: Linear, Quadratic or Smooth curve.
- The KPI Definition pencil edits the formula and filter JSON in a larger dialog; closing it keeps the draft until Save Methodology. Formulas and filters must use supported engine fields and operations.
- Configure thresholds, KPI type and score interpolation anchors. Ultra can be absent, numeric or derived from the best valid KPI measurement in its comparison context.
- Add or delete KPIs (at least one remains). New KPIs get stable K-number identifiers; moving or deleting rows does not renumber others.
- Move KPIs within their category, change their category or reorder whole categories. Category totals show points, environment-relative weights and global weights.
- Renaming a KPI code updates its saved GAP priority reference without changing its priority.
- KPIs whose **Type** is **Reliable** form the Most Reliable Network scoring, with the same thresholds: set their **Most Reliable points** in the selected environment (editable only on Reliable KPIs); the line above the table counts the Reliable KPIs and their points. See [Most Reliable Network scoring](scoring-gap-analysis.md#most-reliable-network-scoring).
- Max Points shows two decimals but keeps full precision for calculation and unchanged allocations when saved.

### Methodology KPIs Priorities for GAP analysis

Maintain the transferable KPI priority list with up/down, first/last or specific-position controls. The position must be a whole number from 1 to the number of KPIs; <kbd>Enter</kbd> applies it and <kbd>Esc</kbd> cancels.

> [!NOTE]
> **Priority and result ordering.** The saved priority list does not currently determine GAP result order. Individual comparisons sort signed GAP from lowest to highest in the latest campaign, with unavailable values last; All Operators retains KPI definition order.

Web and PowerPoint GAP tables include a final sum for each comparison column. Individual PPT comparisons show Average KPI GAP and the average of the column GAP totals; these are distinct statistics (see the [complete Scoring & GAP Analysis guide](scoring-gap-analysis.md) for examples, coverage rules and JSON formats).

### Scoring Export Panels

The **Scoring Export Panels** panel, after the Scoring & GAP Analysis Setup, lists every panel of the Scoring & GAP Analysis results that the PowerPoint and Word documents can include, in a card per results tab (Summary, Scoring Charts, Scoring Tables, Country Areas, Scoring Trends, GAP Analysis, Points Lost and [Methodology Impact](scoring-gap-analysis.md#methodology-impact), whose panels are those of the documents of its own tab), with the colour and icon of the tab, in page order. For each panel:

- The **Exportable** switch includes it in the documents (a panel switched off is struck through). A panel that is not exportable is left out of **Export Selected Scoring Report**, **Generate Scoring Report** and the Scoring section of the reports of [Reporting](reporting.md), and their editors do not list it.
- **What to Export** chooses its operators: **All Operators** (the reference included) or **Focus Operators**, those with the **Focus** role in the [Operator Maps](#operator-maps) (every operator when no label has it; the reference only when it is one of them). The default of each panel is marked with a dot: Focus Operators in Where to act, Where to act by performance owner, Biggest levers, Cities, Towns, Roads and Railways ranked, the route that loses most, Campaign comparison, Country Areas ranked, Each operator against the reference, the individual GAP tables, GAP by part, KPI GAP Profile and every Points Lost panel but Where the points go; All Operators in the others.

**Save Export Panels** saves the table for the workspace and **Restore Defaults** brings back the defaults; both are registered in App Events with the panels that changed. **Export All Operators in Focus panels**, in every export dialog and report editor, shows every operator in the Focus Operators panels of one document. The operators chosen on the page with the operator buttons of a panel still apply to **Export Selected Scoring Report** (see [Scoring & GAP Analysis](scoring-gap-analysis.md#what-is-in-the-powerpoint)). The panels travel as the **Scoring Export Panels** element of Admin's Import / Export / Transfer (importing them replaces those of each destination workspace), with Full Workspace transfers and with backups.

### AI Assistant Glossary

The **AI Assistant Glossary** panel, the last of the page, holds what the [AI Assistant](assistant.md) needs to know about the workspace that its data does not tell: what a Region, a label or a word of the team means (for example *Vendor A: the Region of the tests whose network Ericsson operates*). Every question of the workspace takes its terms, the names they hold sent as codes like every other name; the Operator Maps, Campaign Maps and methodologies are read from the workspace and need no entry.

- **Suggestions from the chat** lists the terms users suggest below the assistant's answers, with who suggested them and when: **Accept** adds one as it is or corrected, **Dismiss** removes it.
- **Terms** lists the glossary, each with its meaning and who changed it last and when: **Save** keeps a change and **×** deletes the term once you confirm.
- **New term** opens a dialog where **Add Term** adds a term with its meaning.

Every change is registered in App Events. The terms travel as the **AI Assistant Glossary** element of Admin's Import / Export / Transfer (an imported term replaces the one with the same identity, or else the same term, and nothing is deleted), with Full Workspace transfers and with backups; suggestions not accepted stay in their workspace.

### Vendor-only filter labels

Across the application (PPT filters, Network Insights, data-preview and Query Builder column filters, Report Template filter assistance), values follow the Operator Maps and Vendor Maps order:

- **`Vendor`:** pure vendors first, then the mixed group of a vendor (`Ericsson (Mixed)`), other and all-vendor groups, then the operators without a vendor, and the mixed groups of no vendor (`Mixed (non-Ericsson)`) last.
- **`Operator_Vendor`:** by Operator and, within one Operator, by Vendor, with `Mixed (non-Ericsson)` last within its Operator.
- **`Vendor_Operator`** (`<Vendor>_<Operator>`): by Vendor and, within one Vendor, by Operator, with the mixed group of a vendor beside that vendor for each Operator (`Ericsson_3`, `Ericsson (Mixed)_3`, `Ericsson_VF_UK`, `Ericsson (Mixed)_VF_UK`) and the other mixed groups (`Mixed (non-Ericsson)`) last, after the operators without a vendor.
- **Operators without a vendor** (`<Operator> - All`) come last in both, in Operator Maps order; values missing from the maps follow the mapped ones alphabetically.

Operator-only identities show the suffix ** - All**, based on canonical Operator identities, their configured aliases and cached CDR operators; configured vendor identities take precedence, so actual vendors stay in the first group. Vendor mapping stores `Operator - All` in `Operator_Vendor` and `Vendor` for them, preserved by dataset exports, combined CDRs, transfers and backups; legacy operator-only values without the suffix remain supported. Operator Maps colours also apply to these operators in multivendor charts (Vendor labels shown as **Operator - All**); Vendor Maps colours apply to actual vendors.

CDR catalogue caches keep the `Operator_Vendor`, `Vendor`, `Region`, `Cluster`, `City`, `Campaign` and `Operator` universes; CDR processing refreshes them from their source columns (catalogues of CDRs processed before Cluster existed were backfilled once), and they are part of workspace database backups and restores.

## Tips & shortcuts

These keys and gestures speed up the mappings and the Auto-calculated Fields. The shortcuts that work everywhere are in [Web Interfaces](web-interface.md#tips-shortcuts).

**Operator and Vendor Maps**

| To… | Do this |
| --- | --- |
| See the CDRs or the names behind a CDR count, a name chip or a **Merges N** badge | Hover it |
| Keep that list open | Click it; **×**, <kbd>Esc</kbd> or a click outside closes it |
| Type a new label in the list of a name | Choose **+ New label…**, type it and press <kbd>Enter</kbd> (<kbd>Esc</kbd> cancels) |
| Save one label | Press <kbd>Enter</kbd> in it (**Save Labels** saves every changed label) |

**Auto-calculated Fields**

| To… | Do this |
| --- | --- |
| Open a field from its card | Click the card, or focus it and press <kbd>Enter</kbd> or <kbd>Space</kbd> |
| Move through the **⋯** menu | <kbd>↑</kbd> / <kbd>↓</kbd>; <kbd>Esc</kbd> closes it |
| Save the field | <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>S</kbd> |
| Insert a field in a formula | Type `[` and choose it |
| Indent a line of a formula | <kbd>Tab</kbd> adds two spaces (while no suggestion list is open) |
| Add a value to a condition with several values | Type it and press <kbd>Enter</kbd> or <kbd>,</kbd> |
| Remove the last value of that condition | <kbd>Backspace</kbd> in its empty box |
| Close the suggestions, then the editor | <kbd>Esc</kbd> (the editor asks first while the field has changes not saved) |
