# Workspace Config

Workspace Config is a dedicated page for settings owned by the active workspace: PPT Templates Management, Main Cities, Mappings & Reference Data (Operator, Vendor and Campaign Maps, Map Areas, Spectrum Holdings and Serving Networks) and Scoring & GAP Analysis Setup. These settings remain workspace-scoped and are included in the applicable import, export, transfer, backup and restore workflows.

> [!IMPORTANT]
> **Workspace settings.** Every edit on this page belongs to the active workspace. Application Config controls shared runtime settings.

> [!TIP]
> **Save versus export.** Save persists edits in the workspace. Export downloads a portable copy; it does not replace the Save action.

Open **Config → Workspace Config** from the main navigation at `/workspace-config`. Template, mapping and Main Cities actions use routes below `/workspace-config/`. The page uses the same teal/navy palette as Application Config, and the **Modules & Sections** tab at the left edge links to its panels.

## In this guide

| Task or topic | Go to |
| --- | --- |
| Access and active workspace | [Open section](#access-and-active-workspace) |
| PPT Templates Management | [Open section](#ppt-templates-management) |
| PPT Templates Editor | [Open section](#ppt-templates-editor) |
| Report Template reference | [Open section](#report-template-reference) |
| Mappings & Reference Data | [Open section](#mappings-reference-data) |
| Campaign Maps | [Open section](#campaign-maps) |
| Unassigned values warning | [Open section](#unassigned-values-warning) |
| Map Areas | [Open section](#map-areas) |
| Spectrum Holdings | [Open section](#spectrum-holdings) |
| Serving Networks | [Open section](#serving-networks) |
| CDR type | [Open section](#cdr-type) |
| Main Cities | [Open section](#main-cities) |
| Portable operations | [Open section](#portable-operations) |
| Scoring & GAP Analysis Setup | [Open section](#scoring-gap-analysis-setup) |
| Scoring Export Panels | [Open section](#scoring-export-panels) |

## Access and active workspace

The Workspace Config section is available to `user-editor`, `admin` and `super-admin` accounts. `user-viewer` accounts do not have access. Open a workspace before using its configuration panels; their contents and changes belong only to that workspace.

## PPT Templates Management

Templates belong to the active workspace and are stored in that workspace database's `report_templates` table. Import, export, backup and transfer packages serialize them as portable CSV files, but those files are package artifacts rather than the live source of record. Obsolete `slides-templates` directories are removed by the current migration and portability flows.

PPT Templates Management supports NSA and SA templates, one default for each technology, and the editor described below. Template names are unique per NR Mode, so an NSA and an SA template may share a name.

The library is sorted by NR Mode (NSA first) and then name; its columns show the NR Mode, creation and last update times, and **Last Updated by**, the user who last imported, edited, renamed, duplicated, promoted or moved the template.

Available actions:

- New
- Import CSV
- Edit
- Rename
- Duplicate
- Change NR Mode (NSA/SA)
- Set Default
- Export
- Delete

**New Template** creates a blank NSA definition and opens it for editing. Import accepts a CSV name or derives it from the filename, can convert a legacy catalogue when prompted and requires explicit overwrite confirmation for a case-insensitive name collision.

Renaming saves when you leave the name field or press Enter; the field keeps its previous name and shows an error if the save fails. Each template has an identity that never changes, and each Dashboard refers to its template by it, so a renamed template stays the template of its Dashboards (whose names, when they repeat the template name, follow it too); a duplicate gets its own identity. Duplicate creates `- Copy`; a non-default template can move between NSA and SA when no same-name target exists.

One template can be default for each technology within a workspace. Reporting initially selects that default but does not change it when a user chooses another template for one job. A default template cannot change type or be deleted until another template becomes default. Only admins, super-admins and the user who created a template (with New Template, Import CSV or Duplicate; one brought by Admin Import / Transfer belongs to its creator on the source server when that user is active here, otherwise to whoever imports it) delete it; for the other users **Delete** is disabled and its tooltip says why. New workspaces start without templates.

The row Export action downloads that individual CSV; portable ZIP export is available under Import / Export / Transfer.

## PPT Templates Editor

**Edit** opens the selected template in a large dialog. The surrounding page controls are omitted from the embedded editor.

### Grid behaviour

- The table scrolls vertically and horizontally inside its viewport.
- The bottom action bar remains visible.
- Shared slide cells are visually merged across charts on the same slide.
- Row controls add, remove, reorder and preview chart definitions.
- **Re-Enumerate Slides** rewrites slide numbers into their current visual order.
- Edited cells use a light pastel-yellow background.
- Newly inserted text is highlighted more strongly.
- A successful save resets all change highlighting.
- **Find & Replace** (or Ctrl/Cmd+F inside the editor) searches every editable cell of the template. Matching cells are outlined and the current one is highlighted; Enter and Shift+Enter (or Next and Previous) move between them. **Replace** changes every occurrence in the current cell and **Replace All** changes every occurrence in the template after a confirmation. Replacements are ordinary unsaved edits until **Save Template**; **Match case** restricts matching to the exact capitalization.

### Validation

- Manual cell edits are validated after a short pause and when leaving the cell. Save revalidates the complete grid and stops if a row or filter is malformed.
- Every row error names the row as the editor shows it: `Slide: n - Chart: n` (the chart is the place of the row among the rows of its slide), or `Slide: n` for a Title, Transition or End Slide, followed by what to correct.
- Fixing the invalid cell clears the error message.
- Filter conditions render on separate lines with visual bullets; bullets are not stored in the cell.
- CSV filter cells retain one condition per line.

### Assistance and previews

- Searchable single-select assistance for layouts, chart types, fields and positions.
- Ordered multi-select assistance for Rows, Columns and Legend.
- Cell Assistance writes a value to the cell as soon as it is chosen (and the KPI operation as soon as it is picked); the values of Rows, Columns and Legend follow what is ticked. **Close**, at its bottom, closes it.
- Shared Filter Builder with parsed-expression display. Its conditions reach the Filters cell when **Apply filter** is pressed, once the filter is complete.
- Chart Data Preview opens the full filtered dataset directly.
- Chart Preview reuses the shared Interactive Preview.
- **Update Template** applies preview values to the in-memory row; it does not save to disk.
- **Auto-calculated Fields** opens the shared active-workspace field manager.

**Save Template** validates and persists the complete grid atomically. Dashboard comment reconciliation runs separately when slide identity changes; any required combined CDR update also runs after the save response. The Dashboard viewer refreshes the saved template when the editor closes. A combined CDR update is queued only when a template adds a source field missing from that CDR table.

Removing the last template reference leaves the existing column available for future reuse. Close, Escape and backdrop actions preserve the editor when unsaved changes still require a decision.

## Report Template reference

This is the canonical authoring reference for templates used by both [PPT Dashboards](ppt-dashboards.md) and [PPT Reporting (old)](ppt-reporting-old.md). The common `assets/powerpoint-templates/Template_VodafoneThree.pptx` supplies the masters, named layouts and placeholders. Each distinct `Slide` value creates one slide; chart rows sharing that value fill its chart placeholders in row order.

### Template columns

| Column | Purpose |
| --- | --- |
| `Slide` | Positive slide number. Rows are sorted by this value; rows with the same number form one slide. |
| `Slide Tittle` | Shared slide title. The historical `Tittle` spelling is part of the CSV schema. |
| `Slide Subtittle` | Optional shared slide subtitle. |
| `Layout` | Select `Title Page`, `Title Only`, or a grid named `Title + N rows + M columns`, optionally followed by `+ comments down` or `+ comments right`. Dynamic grids also appear in the selector. |
| `Chart Tittle` | Optional title drawn inside the chart. |
| `Source Dataset` | `CDR-Data`, `CDR-Voice`, `CDR-Speech` or `CDR-All`; leave blank for structural slides. `CDR-All` pools selected RF observations using `LTE_RSRP`, `NR_RSRP`, `LTE_SINR`, `NR_SINR`, `Latitude` and `Longitude`, retaining Operator/Campaign context. |
| `KPI` | Processed CDR field or metric expression to render. |
| `Chart type` | Automated chart type or structural slide type. |
| `Filters` | Conditions applied before aggregation, one per line and terminated with `;`. |
| `Rows Split` | Category/table-row hierarchy. Separate dimensions with `×`. |
| `Columns Split` | Comparison-series/table-column hierarchy. Separate dimensions with `×`. |
| `Legend` | Optional field whose plotted or filtered values should be explained. Blank means no legend. |
| `Legend Position` | `Top`, `Bottom`, `Left` or `Right`; blank defaults to `Top`. |
| `Legend Format` | Optional list defining legend colour, font, styles and relative size. Blank retains automatic formatting. |
| `Label Position` | Optional value placement: `None`, `Top`, `Up`, `Middle` or `Down`. Blank retains automatic placement. |
| `Label Format` | Optional list defining label colour, font, styles and relative size. Blank retains automatic formatting. |
| `Axis X Range` | Optional CDF limits in KPI units: `[min,max]`, `[min,]` or `[,max]`. Blank keeps the automatic domain. |
| `Axis Y Range` | Optional CDF cumulative-percentage limits from 0 to 100, using the same syntax. Blank keeps 0–100%. |
| `Exclude Null/Empty` | `Yes` removes rows whose plotted value is null or empty before chart calculations. Blank keeps them. |
| `Exclude Zero` | `Yes` removes rows whose plotted numeric value is exactly zero before chart calculations. Blank keeps them. |

For multi-chart slides, the editor visually groups `Slide`, `Slide Tittle`, `Slide Subtittle` and `Layout`; the CSV still stores them on every row.

### Structural slides

Use one row without `Source Dataset` or KPI fields. A structural row cannot share its slide number with chart rows.

- `Title Slide` normally uses `Title Page` and fills title/subtitle placeholders.
- `Transition Slide` normally uses `Title Only` and creates a section divider.
- `End Slide` uses `Black logo end slide` and adds the closing slide of the template as it is, without title, subtitle or counter; its `Slide Tittle` is optional and only names the slide in the PPT Dashboards viewer.
- A row without `Source Dataset` or `Chart type` takes the structural type of its layout: `Title Page` is a Title Slide, `Transition` and `Title Only` a Transition Slide and `Black logo end slide` an End Slide. A row on `Black logo end slide` is an End Slide also when it still says `Title Slide` or `Transition Slide` (for example a transition moved to the closing layout). Saving the template writes that `Chart type` in the row.
- Title and Transition subtitles use the template's yellow accent (theme accent 4) in exported presentations, whatever layout hosts them.
- Every Title or Transition slide after the cover is a transition with its counter (01, 02…) above its title, with the sizes and places of every transition of the reports.
- In PPT Dashboards, a Title Slide that opens the Dashboard also lists the Scope, Regions and Cities below its subtitle and decorative line, in the viewer and in the exported PPT.

```text
Slide: 1
Slide Tittle: NetCheck 5G Executive Dashboard
Slide Subtittle: 2026-Q2 · Operator Comparison
Layout: Title Page
Chart type: Title Slide
```

```text
Slide: 6
Slide Tittle: Voice service analysis
Layout: Title Only
Chart type: Transition Slide
```

```text
Slide: 18
Layout: Black logo end slide
Chart type: End Slide
```

### Supported chart types

Automated rows support:

- `100% Stacked Vertical Bars`
- `Count Stacked Horizontal Bars`
- `CDF Line`
- `Histogram Line`
- `Histogram Bars`
- `Multi KPI CDF Lines`
- `Scatter`
- `Map`
- `Table`
- `Average Vertical Bars`
- `Median Vertical Bars`
- `Distribution Stacked Vertical Bars`
- `Threshold Stacked Vertical Bars`

Choose a KPI and at least one Rows or Columns Split dimension. `CDF Line` creates one curve per complete aggregation combination. Count charts retain empty combinations where required so comparisons remain aligned.

The RF Quality template includes combined Data/Voice/Speech slides before each chart family. Its `CDR-All` source is virtual: it uses the selected physical datasets and creates no duplicate CDR dataset or database table. Templates containing this source are retained by JSON/CSV import/export, workspace transfers and backup/restore.

`Histogram Bars` uses the same bins as `Histogram Line`, with side-by-side Campaign bars and lighter shades for older Campaigns. Paired LTE/NR rows can use a dynamic layout with `Dynamic Columns Field = Operator` to show all selected Operators on one slide.

`Histogram Line` draws an unfilled step contour for each aggregation combination. Set `Bin Size = 5` in Filters for 5-unit bins, or `Bin Size = 1` for 1-unit bins. The vertical axis shows the percentage of valid samples in each bin, normalized independently per series; series models retain sample counts. Histograms reuse CDF colours, progressive campaign widths and multivendor operator line patterns. Add four `Buckets = ...` thresholds for five red-to-green quality background bands. Add `Class Colours = Quality` to matching distribution charts to use those same five class colours. The existing template/JSON export, import and backup workflows preserve these chart settings.

Axis ranges are visual settings, not data filters, and are available to every chart family with a numeric axis. For example, `Axis X Range: [0.01,]` starts the horizontal axis at `0.01` while retaining its automatically calculated maximum; `[,30]` retains the automatic minimum and fixes the maximum at `30`. Empty range cells preserve the existing automatic behaviour.

Percentage axes continue to use values from 0 to 100, while count, KPI, coordinate and scatter axes use their native units. Category axes and tables have no numeric domain to constrain.

`Label` is available to every chart family. For bars, `None` hides values, `Top` places them outside the bar, and `Up`, `Middle` and `Down` place them inside near the leading edge, centre or origin edge; horizontal bars map those directions to outside-right, inside-right, centre and inside-left.

For CDF, scatter and map charts the same setting places point or endpoint labels around the plotted mark. An empty cell preserves each renderer's existing automatic behaviour.

`Exclude Null/Empty` and `Exclude Zero` are independent and apply to every chart family. For scatter charts the exclusions are checked on both plotted axes; for CDF and Multi KPI CDF charts they are checked on each plotted metric before the cumulative distribution is calculated.

This allows a CDF to begin at its first non-zero observation instead of merely hiding the zero-valued section with an axis range.

### Chart recipes

The examples show chart-specific cells. Add the shared `Slide`, titles and `Layout` appropriate to the target layout.

#### 100% Stacked Vertical Bars

Use for proportions, success ratios and categorical quality splits. KPI categories become stack segments.

```text
Source Dataset: CDR-Voice
KPI: Call_Status
Chart type: 100% Stacked Vertical Bars
Filters: Call Family IN (VoLTE, MultiRAB); Operator IN (Vodafone, 3, EE)
Rows Split: Call Family
Columns Split: Operator × Campaign
Legend Position: Right
```

#### Count Stacked Horizontal Bars

Use for event or failure counts. Rows form horizontal categories and the KPI normally supplies statuses or causes.
Column hierarchy headers keep complete aggregation values in both the Dashboard canvas and exported PowerPoint chart. Each successive level uses a smaller font, which can shrink further to fit narrow columns; the final header row has its own space above the data.

```text
Source Dataset: CDR-Data
KPI: Test_Result
Chart type: Count Stacked Horizontal Bars
Filters: Test Family IN (FDFS, FDTT); Test_Result IN (Failed, Dropped)
Rows Split: Test Family × City
Columns Split: Operator × Campaign
Legend Position: Bottom
```

#### CDF Line

Use for continuous metrics such as throughput, duration, latency or MOS.

```text
Source Dataset: CDR-Data
KPI: Mean_Data_Rate
Chart type: CDF Line
Filters: Test_Result = Completed; Test_Name CONTAINS FDFS; Direction = DL
Rows Split: Operator
Columns Split: Campaign
Legend Position: Bottom
```

With two operators and two campaigns this produces four curves. With multiple campaigns, the latest campaign is emphasised within each comparison family.

#### Multi KPI CDF Lines

Separate continuous KPI names with `|`. The renderer keeps the shared filters, Rows Split, Columns Split and legend and places one CDF panel per measure.

```text
Source Dataset: CDR-Data
KPI: NR_PCell_SINR_Avg | LTE_PCell_SINR_Avg
Chart type: Multi KPI CDF Lines
Filters: Test_Result = Completed; Test_Name = FDTT http DL MT
Rows Split: Operator
Columns Split: Campaign
Legend Position: Right
```

#### Average Vertical Bars and Median Vertical Bars

Use Average for mean values or Median when outliers should have less influence.

```text
Source Dataset: CDR-Speech
KPI: LQ
Chart type: Average Vertical Bars
Filters: Call_Status = Completed; Call Family = WhatsApp
Rows Split: Operator
Columns Split: Campaign
Legend Position: Top
```

Change only `Chart type` to `Median Vertical Bars` for the median.

#### Distribution Stacked Vertical Bars

Use explicit numeric ranges with `Buckets = ...`, or ordered upper bounds with `Buckets < ...` / `Buckets <= ...`. Upper-bound mode generates `belowN` categories plus `Above`; use `Rate Bucket` as the final column aggregation.

```text
Source Dataset: CDR-Data
KPI: Mean_Data_Rate
Chart type: Distribution Stacked Vertical Bars
Filters: Test_Result = Completed; Test_Name = FDTT http DL MT; Buckets < 2,5,20,100
Rows Split: Operator
Columns Split: Campaign × Rate Bucket
Legend Position: Right
```

With upper-bound mode, `Buckets < 2,5,20,100` evaluates each value against the limits in order and produces `below2`, `below5`, `below20`, `below100` or `Above`. Use `Buckets < 1,3,10,20` for the corresponding FDTT UDP UL distribution. `<=` is also accepted when boundary values must remain inside their named bucket.

Explicit ranges such as `Buckets = 1,5,20` produce `<1`, `1-5`, `5-20` and `20+`. Negative limits use `to`, so `Buckets = -110,-100,-90,-80` produces `< -110`, `-110 to -100`, `-100 to -90`, `-90 to -80` and `-80+` for RSRP. Stacked segments and legend entries always follow ascending numeric order, regardless of the order in which values appear in the CDR rows.

#### Threshold Stacked Vertical Bars

Use for a below/above distribution around one threshold.

```text
Source Dataset: CDR-Speech
KPI: LQ
Chart type: Threshold Stacked Vertical Bars
Filters: Call_Status = Completed; Call Family = VoLTE; Threshold = 1.6
Rows Split: Operator
Columns Split: Campaign
Legend Position: Right
```

The legend shows the configured threshold, for example `< 1.6` and `≥ 1.6`; `Threshold = -110` produces `< -110` and `≥ -110`.

#### Scatter

Use `Metric vs Dimension` to compare a KPI with a radio or quality dimension.

```text
Source Dataset: CDR-Speech
KPI: LQ vs Playing_RSRP_NR_Avg
Chart type: Scatter
Filters: Call_Status = Completed; Call Family = WhatsApp
Rows Split: Operator
Columns Split: Campaign
Legend Position: Bottom
```

#### Map

Use latitude and longitude in `Latitude vs Longitude` order. Rows Split, Columns Split and Legend determine point grouping and colour.

To colour a radio-quality map by a measured value, use `Latitude vs Longitude vs Measure`, set **Rows Split** and **Legend** to `Value Bucket`, and define four ascending thresholds with `Buckets = ...`. For example, RSRP uses `Buckets = -110,-100,-90,-80`, and SINR uses `Buckets = 0,5,13,20`. These five ranges use red, orange, yellow, light green and green. Missing measurements are excluded when **Exclude Null/Empty** is enabled. Two-field maps retain their existing grouping colours.

```text
Source Dataset: CDR-Data
KPI: Test_Start_Latitude vs Test_Start_Longitude
Chart type: Map
Filters: G_Level_4 = London
Rows Split: Operator
Columns Split: Campaign
Legend: Test_Result
Legend Position: Right
```

#### Table

Use when exact values are more useful than a chart. Rows and columns form the axes; KPI supplies the aggregated cell value.

```text
Source Dataset: CDR-Voice
KPI: Call_Setup_Time
Chart type: Table
Filters: Call_Status = Completed
Rows Split: City
Columns Split: Operator × Campaign
Legend Position: Top
```

### Template filter language

Conditions are joined with logical AND and separated by `;`. Column matching is case-insensitive.

```text
Call Family IN (VoLTE, MultiRAB); Direction = DL; Vendor NOT CONTAINS (Mixed, Other)
```

| Operator | Example |
| --- | --- |
| Equals / not equal | `Call_Status = Completed`, `Operator != EE` |
| List inclusion / exclusion | `Operator IN (VF, O2, 3, EE)`, `Campaign NOT IN (2025-Q4)` |
| Contains / not contains | `Test_Name CONTAINS FDFS`, `Vendor NOT CONTAINS (Mixed, Other)` |
| Numeric comparison | `LQ < 1.6`, `Mean_Data_Rate >= 20` |

`Vendor` filters the vendor alone and `Operator_Vendor` the `<Operator>_<Vendor>` identity. Import accepts the former `Vendor_Only` and `Vendor V3` (as `Vendor`) and `OP_Vendor` (as `Operator_Vendor`) filter names, and templates written for earlier versions are converted once: their `Vendor` groupings and legends become `Operator_Vendor` and their `Vendor_Only` filters become `Vendor`, so their charts stay identical. Operator-prefixed filter values are resolved using workspace operator aliases when the report runs. This alias handling applies to filter fields, while aggregation fields keep their selected comparison semantics.

`IN`, `NOT IN`, `CONTAINS` and `NOT CONTAINS` accept comma-separated values. Parentheses are optional in Filter Builder input. A comma separates values within one condition; use `;` between independent conditions. `Threshold = 1.6` configures threshold charts and `Buckets = 1,5,20,100` configures distribution ranges.

### Rows Split, Columns Split and legends

Selection order defines the hierarchy:

```text
Rows Split: Call Family × G Level 4
Columns Split: Operator × Campaign
```

- Rows supplies chart categories or table rows.
- Column supplies comparison series or table columns.
- Blank Columns Split creates one `(all)` comparison.
- `Campaign` is ordered chronologically from oldest to newest.
- In Multivendor scope, `Operator` aggregation resolves to the mapped comparison field; an Operator filter still applies to the physical CDR Operator field.

Legend behaviour:

- Blank draws no legend.
- A KPI or aggregation dimension shows plotted values.
- A field used only by Filters shows its applied values as contextual text.
- CDF handles reproduce series colour and relative line width.
- Threshold legends show below/above colours and the configured value.
- Bucket legends show readable ranges derived from `Buckets`.

Top/Bottom produces a compact horizontal legend; Left/Right produces a vertical legend and reserves plot space.

### Multi-chart slides, operators and colours

Rows sharing a `Slide` number create separate charts on one slide. They must share `Slide Tittle`, `Slide Subtittle` and `Layout`, may use different sources, KPIs, filters and chart types, and require at least as many placeholders as chart rows.

Operator and Vendor aliases resolve to the canonical values configured in Workspace Config without changing the source workbook. Their table order controls Operator, Subscriber, Vendor and combined Operator_Vendor chart dimensions. Each canonical row defines its chart theme colour; multiple campaigns or operators using one identity receive contrasting shades derived from that colour.

## Mappings & Reference Data

The Mappings & Reference Data panel contains Operator Maps, Vendor Maps, Campaign Maps, Map Areas, Spectrum Holdings and Serving Networks as independently collapsible subpanels. Their light blue headers distinguish them from the dark parent header. Existing mapping controls and saved expansion states remain available inside each subpanel.

### Operator Maps

Operator Maps set how the Operators are named, ordered and coloured in every filter, table, chart, legend and report. They have two numbered subpanels, each of which can be collapsed (the browser remembers it):

**1 · Operator names found in the CDRs** lists every Operator name of the ready CDRs of the workspace, with the number of CDRs that contain it (hover it to see their names), its **Label**, its **Status**, read only, the **Role** of its label (Include, Focus or Exclude, set in subpanel 2; it follows a label chosen in the list at once) and its **Comments**, a free note about what the name holds in the CDRs as a reminder (for example that `Vodafone SA` is the SA terminal of the NSA drive of 2026-Q2). The **Label** and **Comments**, the fields edited in this table, are pastel yellow. **Save assignments** saves the comments too; they travel with the Operator Maps in the Mappings & Reference Data export, transfers and backups, and every change is recorded in App Events. The **Status** is:

- **Unassigned** (red, and the number of the subpanel turns red): the name has no label yet, so it is shown as it is and never added up with other names. **Use own names** gives every unassigned name a new label with its own name.
- **Merges N**: the label stands for N names of the CDRs that coincide in the same campaign and NR Mode (in a CDR of that campaign with that NR Mode, or in CDRs of the same campaign and NR Mode), where they are added up as one Operator. Hover it to see the others and the campaigns where they coincide, for example `26-Q2 (NSA)`.
- **Assigned**: the label stands for this name only, or also for names that are never in the same campaign and NR Mode as this one (hover it to see them), which are therefore never added up: for example `Vodafone UK` in the NSA campaigns and `Vodafone SM` in an SA campaign can share `VF`.

Choose the label of each name in its list: one of the Operator labels of subpanel 2, or **+ New label…**, which lets you type a new label (Enter to accept, Esc to cancel) that every list then offers too. Press **Save assignments**; a new label is added at the end of subpanel 2. Each name therefore keeps its own label unless you give several names the same one: for example `Vodafone UK` → `VF`, `Vodafone SA` → `VF-SA` and `Vodafone VoNR` → `VF-VoNR` keep the three apart, while two spellings of the same network (`Vodafone` and `Vodafone UK`) can share `VF`. A name that is itself one of the labels (for example `EE`, shown as `EE`) cannot be changed here: rename that label in subpanel 2. Saving asks for confirmation when a label would add up names of the CDRs that it did not add up before (names that coincide in a campaign and NR Mode, which the dialog names), when a name leaves a label that saved filters or Reporting Jobs use (they no longer include it, and the dialog says how many use it), and when a new label contains `_`, which also separates Operator and Vendor in `Operator_Vendor` values such as `VF_Ericsson`.

**2 · Operator labels** lists one row per label with its **Order**, **Colour**, **Label**, **Role**, **Possible names in the CDRs** and **Actions**. The possible names are how the label can be written in the CDRs of the different campaigns, shown as chips: highlighted with the number of CDRs when the current CDRs have them, grey when they are names of other campaigns, and ordered from the name in most CDRs (alphabetically when they tie). Hovering a chip, a CDRs count or a **Merges N** badge shows its CDRs or names at once; clicking it keeps them in a floating panel until it is closed (×, Esc or a click outside). **×** removes a name and **Add a name** with **+** adds one; a name of another label moves to this one at once. Under the label, **Merges N** tells that it adds up N names of the current CDRs that coincide in the same campaign and NR Mode. The label also stands for the name written like itself, so it need not be added. Saving a label asks for the same confirmation as subpanel 1.

Use **Add label** to create a label with its colour, role and possible names (one per line; comma and semicolon separators are accepted too). Change a label's name, role, possible names or colour and press **Save Labels**, below the table, to save every changed label at once (Enter in a label saves that one). **Move up** and **Move down** set its position in Operator charts and in Subscriber dimensions; the first and last rows cannot move beyond the table. **Delete** removes the label after confirmation, and its names are shown as they are until they get another label.

The **Role** beside each label is **Include** (yellow, the default: the operator is analysed as usual), **Focus** (green) or **Exclude** (red), recorded in App Events when it changes; a note above the labels explains each one:

- **Focus**: the label, with every name of the CDRs it stands for, is one of the **Focus operators** of [Scoring & GAP Analysis](scoring-gap-analysis.md#persistence-and-exports): Where to act, the locations ranked, the individual GAP comparisons, GAP by part, the KPI GAP Profile and the Points Lost views of its PowerPoint and Word (from the page, the Scoring artifacts of the Reporting Jobs and the Bundle Report Templates) are those of the Focus operators, and the operator choices of those sections of the page list them first (every operator when no label is a Focus operator).
- **Exclude**: the operator is left out of every analysis, filter, chart and report of the workspace (Scoring & GAP Analysis, CDR Analysis, PPT Dashboards, the Chart Builder, Network Insights, Non-Qualified Calls, the Bundle Report Templates and the Reporting Jobs), as if every Operator filter left it out (as `NOT Lebara` does, see [Operator patterns](web-interface.md#operator-patterns)), so the Operator filters can stay at All; no Operator list or GAP reference offers it, and its names stay in subpanel 1. Saved Filters are calculated again when the excluded operators change. At least one label must stay included: a Role that would exclude every label goes back to the one it had, and saving, deleting or importing labels that would leave every label excluded is refused without changing them.

The roles travel with the Operator Maps in the Mappings & Reference Data exports, transfers and backups.

Renaming a label updates exact matching references in Report Templates (their slide and chart titles, legends, dynamic values and the values of their Operator, Operator_Vendor, Vendor_Operator and Vendor filter conditions; with a label that is a number, such as `3`, only the filters, legends and dynamic values, never layouts, thresholds or other conditions) and saved Dashboards, and the values of the Operator, Operator_Vendor, Vendor_Operator and Vendor filters saved in Reporting Jobs (including the GAP reference operator and the Scoring report scenarios), saved Scoring report configurations, the last Scoring calculation (its GAP reference too), the Saved Filters of Scoring & GAP Analysis (their GAP reference and filters; they are found again with the new label and calculated again when opened), the favourite Bundle Report Templates and Network Insights Analysis Selections, the CDR Analysis filters of each CDR and the Non-Qualified Calls filters (`VF_UK` → `VF` also turns `VF_UK_Ericsson` into `VF_Ericsson` and `Ericsson_VF_UK` into `Ericsson_VF`). Campaign filters keep the full campaign value, so changing the Campaign Maps never requires renaming them.

A new workspace starts with the labels of the operators of the country chosen for it in [Workspace Management](workspace-management.md#workspace-lifecycle), in their corporate colours and with the usual ways they are written in the CDRs, also with the country (for example `Telekom`, `Vodafone`, `O2` and `1&1` in Germany, where `o2 - de` is O2; or EE, 3, VF, VF SA, VF VoNR, O2 and Lebara in the United Kingdom, where `Vodafone UK`, `VFUK` or `Vodafone` are VF), none of them with a Role. A workspace created without a country starts without Operator Maps. The operators of the 50 listed countries come from `assets/labels-operators/operators-by-country.json`, so a deployment can change them for every new workspace. The colour picker sets the label's chart theme colour; charts can derive related shades to distinguish campaigns or series. Every filter, table, chart, legend and report of the tool shows the label, and choosing it selects all its names; only Preview Dataset shows the names as they are in the CDRs.

The maps do not rewrite source workbooks, stored CDR rows or combined CDR tables. Saving, moving or deleting a label clears chart caches so later views use the new settings.

### Vendor Maps

Vendor Maps have the same two subpanels: **1 · Vendor names found in the CDRs** lists every Vendor name of the ready CDRs (the Operators without a Vendor, `<Operator> - All`, are not Vendors) and gives each one a label exactly as in the [Operator Maps](#operator-maps), and **2 · Vendor labels** has the same **Order**, **Colour**, **Label**, **Possible names in the CDRs** and **Actions** controls, with **Add label**, **Save Labels**, **Move up**, **Move down** and confirmed **Delete**. Names are matched without regard to case.

A new workspace starts with the Vendor labels, in this order, Ericsson (`#0255AD`), Ericsson (Mixed) (`#002F61`), Huawei (`#FBBD00`), Samsung (`#008521`), NSN (`#8C00FF`, also `Nokia` and `NNS`), SCW (`#6F42C1`), Mixed (non-Ericsson) (`#5E4F2E`, also `Mixed`), Other Vendor (`#5E4F26`) and (blank) (`#7A8791`). These labels come from `assets/labels-vendors/default-vendor-maps.json`, so a deployment can change them for every new workspace.

Renaming a Vendor label updates exact matching Report Template and saved Dashboard references, and the same saved filters as an Operator rename.

Vendor order determines the chart sequence for Vendor dimensions and the Vendor portion of combined `Operator_Vendor` values. The selected colour gives a Vendor a consistent chart identity, with related shades where multiple series need distinction. Every filter, table, chart and report shows the Vendor label (and the Operator and Vendor labels of an `Operator_Vendor`), and choosing it selects all its names; the maps do not alter materialized CDR values, which only Preview Dataset shows. Label changes refresh chart caches without rematerializing source data.

### Campaign Maps

Campaign Maps set how every chart, table, legend, filter and PowerPoint or Word report of the workspace names and orders campaigns. They follow a pattern rather than a list, so campaigns uploaded later, such as `2026-Q3` or `2027-Q1`, follow it without editing the map.

- **Label format** writes the label from the parts read in the campaign name: `{year}` (2026), `{yy}` (26), `{quarter}` (2), `{mode}` (SA or NSA) and `{market}` (the country code, such as UK). Characters inside the braces of a marker are written only when the campaign has that part: the default `{year}-Q{quarter}{-mode}` shows `UK_Q2_2026` as `2026-Q2` and `UK_Q2_SA_2026` as `2026-Q2-SA`.
- **Order inside a quarter** orders campaigns by year and quarter, and the campaigns of one quarter by mode: by default first the campaign without mode, then NSA, then SA. Use the arrows to change it. **Show in label**, next to NSA and SA, chooses the modes that `{mode}` writes: unchecking NSA shows the NSA campaigns as `2026-Q3` while the SA ones stay `2026-Q3-SA`, without an exception per campaign. An NSA campaign then reads like the campaign without a mode of its quarter, and both are one campaign (the Preview shows **Merges** when the CDRs have both).
- **Exceptions** give their own label to campaigns that do not follow the pattern, one or more source campaigns per label. They are ordered by the year and quarter of their label, after the campaigns of that quarter, or first, in the table order, when the label has none. Campaigns without a year and quarter and without an exception keep their name.

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

## CDR type

The **Workspace Configuration** panel at the top chooses the **CDR type** of the workspace: the provider of the CDR files it processes. Every workspace handles the CDRs of one provider, with its own field names, values and methodologies, so the CDRs of two providers are never mixed. **NetCheck CDR** is the default and the only type supported today; **Umlaut CDR** and **P3 CDR** files keep their own field names and appear as *coming soon* until they are supported. The type is also chosen when a workspace is created and can be changed from the workspaces table of [Workspace Management](workspace-management.md) while the workspace has no Data, Voice or Speech CDRs; once it has CDRs it keeps their type. It is stored in the workspace database, so it travels with the workspace in transfers, Full Workspace packages and backups. [Benchmarking Providers](benchmarking-providers.md) describes the status of the adaptation to Umlaut and P3 CDRs.

## Main Cities

The Main Cities panel appears before Mappings & Reference Data and lists cities found in ready CDR datasets for the active workspace. Use the center buttons to move selected or all cities between the available list and the selected list, then choose **Save Main Cities**. The setting belongs to this workspace.

Every City selector — Dashboard filters, the PowerPoint export, Scoring, Network Insights, Non-Qualified Calls and Reporting Jobs — offers **Main Cities** as its first option. Applying it selects the configured cities that are available in the current selection.

## Portable operations

Administrators use Admin's **Import / Export / Transfer** and Super Admin's **Backup Protection** controls to move or restore workspace settings. Main Cities is a portable component alongside Report Templates and Mappings & Reference Data; full-workspace packages and database backups also retain the setting. The Mappings & Reference Data package (`mappings-reference-data/mappings-reference-data.json`) contains the Operator and Vendor Maps, Spectrum Holdings and Campaign Maps, and importing it replaces all of them in the destination workspace.

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


### Chart layouts

The editor offers **121 layouts**: every combination of **1–6 rows × 1–6 columns**, each without comments, with comments below, or with comments to the right (108 fixed grids), plus nine dynamic layouts and `Title Page`, `Title Only`, `Transition` and `Black logo end slide`. The physical layouts appear immediately after `Black Title Page` in the same order as the selector, excluding the virtual dynamic options.

Names follow `Title + N rows + M columns`, optionally followed by `+ comments down` or `+ comments right`. The 108 fixed grids and four structural layouts exist physically in the reference PPT. `Source Dataset = CDR-All` exposes the union of Data, Voice and Speech fields, including normalized RF fields and `CDR_Type`, in cell assistance. The nine dynamic options are virtual: the renderer selects a fixed grid from the distinct values of their row and column fields. The widened Layout cell-assistance selector lists Title Page, Title Only, Transition and Black logo end slide first, followed by the nine dynamic grids and then the fixed grids. Long names stay on one line; narrow screens can scroll horizontally. Structural layouts have blue shading, dynamic layouts purple shading and the selected option yellow shading; selection retains its position without a duplicate at the top. Other native layouts remain internal to structural slides. Historic layout names are normalized on import and in stored templates; exports use the canonical names. Grids without comments use the full chart area.

### Dynamic chart grids

CSV imports identify columns by name and accept them in any order; duplicate names or aliases are rejected. The editor and exported CSV place **Dynamic Rows Field** and **Dynamic Columns Field** immediately after **Layout**. Use these fields to choose which source field creates the rows and columns. A dynamic layout requires a non-empty field for each dynamic axis; the parser rejects missing fields. Leave the field for a fixed axis empty. CSV exports include both columns; template import/export, transfers, backup and restore preserve them. Older CSVs with `Dynamic Field` remain importable: its value is assigned to the dynamic axis declared by the layout.

| Layout | Repeated dimension | Commentary |
|---|---|---|
| `Title + 2 rows + dynamic columns` | Columns | None |
| `Title + 2 rows + dynamic columns + comments down` | Columns | Below |
| `Title + 2 rows + dynamic columns + comments right` | Columns | Right |
| `Title + dynamic rows + 2 columns` | Rows | None |
| `Title + dynamic rows + 2 columns + comments down` | Rows | Below |
| `Title + dynamic rows + 2 columns + comments right` | Rows | Right |
| `Title + dynamic rows + dynamic columns` | Rows and columns | None |
| `Title + dynamic rows + dynamic columns + comments down` | Rows and columns | Below |
| `Title + dynamic rows + dynamic columns + comments right` | Rows and columns | Right |

- **Two fixed rows:** use two chart definitions on the slide with the same Layout and Dynamic Columns Field. The first fills the top row and the second the bottom row.
- **Two fixed columns:** use two chart definitions with the same Layout and Dynamic Rows Field. The first fills the left column and the second the right column.
- **Both axes dynamic:** use one chart definition and two different fields, for example `Region` for rows and `Operator` for columns. Each chart includes only samples matching both values.

Distinct values come from the selected, filtered CDR universe; empty values are excluded. Both-axis grids paginate at six rows and six columns. Multivendor grids also paginate at six repeated values, keeping operators of the same vendor together where possible. Larger ordinary single-axis grids can be derived from the native geometry; charts become smaller as the grid grows.

> [!TIP]
> **Readability:** a 6 × 6 grid fits 36 charts, but gives each chart little space. Prefer fewer charts when labels or distributions need close inspection.

For RF histograms, select **Operator**: the first definition is LTE and the second NR, so each Operator occupies one column. Campaigns remain grouped inside each chart. Changing filters changes the number of columns; LTE and NR keep their corresponding positions even when one technology has no valid samples.

> [!NOTE]
> **Vendor comparison:** When **Report type** is **Multivendor Comparison**, the **Vendor comparison** selector appears to its right. **Vendor Only (All Operators Combined)** is the first and default option when opening the export dialog; it pools selected operators using the same `Vendor` value. Choose **Operator - Vendor** to keep each operator separate. Campaigns remain separate. The job retains this choice for retries. Dynamic vendor grids use up to six columns per slide and keep operators of the same vendor together where possible.

### Vendor-only filter labels

Across the application, values follow the Operator Maps and Vendor Maps order: `Vendor` lists pure vendors first, then the mixed group of a vendor (`Ericsson (Mixed)`), other and all-vendor groups, then the operators without a vendor, and the mixed groups of no vendor (`Mixed (non-Ericsson)`) last of all; `Operator_Vendor` is ordered by Operator and, within one Operator, by Vendor, with `Mixed (non-Ericsson)` last within its Operator; `Vendor_Operator` (`<Vendor>_<Operator>`) by Vendor and, within one Vendor, by Operator, with the mixed group of a vendor beside that vendor for each Operator (`Ericsson_3`, `Ericsson (Mixed)_3`, `Ericsson_VF_UK`, `Ericsson (Mixed)_VF_UK`) and the other mixed groups (`Mixed (non-Ericsson)`) last of all, after the operators without a vendor. In both, operators without a vendor (`<Operator> - All`) come last, in Operator Maps order, and values missing from the maps follow the mapped ones alphabetically. Operator-only identities follow with the display suffix ** - All**, based on canonical Operator identities, their configured aliases and cached CDR operators. Configured vendor identities take precedence, so actual vendors remain in the first group. Vendor mapping stores `Operator - All` in `Operator_Vendor` and `Vendor` for operator-only identities. Dataset exports, combined CDRs, transfers and backups preserve that value; legacy operator-only values without the suffix remain supported. This applies to Dashboard filters, Network Insights, data-preview column filters, Query Builder column filters and Report Template filter assistance.

CDR catalogue caches retain the `Operator_Vendor`, `Vendor`, `Region`, `Cluster`, `City`, `Campaign` and `Operator` universes. CDR processing refreshes them from their source columns, and catalogues of CDRs processed before Cluster existed are backfilled once. The caches remain part of workspace database backups and restores.

Operator mapping colours also apply to operators without a vendor in multivendor charts, including Vendor labels displayed as **Operator - All**. Vendor mapping colours apply to actual vendors.
