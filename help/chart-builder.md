# Chart Builder

Chart Builder is the ad-hoc chart editor. It uses the PPT Designer individual Canvas chart viewer embedded directly in the page and the shelves of the chart builder of the [Designer](ppt-designer.md#designer), while its definition remains temporary: it creates no PowerPoint report, and changes a PPT Design or a PPT Template only when **Add to PPT Design or Template…** puts the chart, with its format, on one of their slides.

> [!NOTE]
> **Temporary exploration.** Changes here create an ad-hoc chart. They do not modify a Report Template or generate a PowerPoint report.

> [!TIP]
> **Investigate empty charts.** Check the selected CDRs, filters and sample counts before changing the chart presentation.

## Presentation

The presentation **Builders** sums the module up. Ad-hoc exploration of the processed CDRs: Chart Builder draws any chart in the PPT viewer and Query Builder runs read-only SQL. Select it to open it in the slide viewer, play it full screen or download its PowerPoint; every presentation is also in [Product Presentations](presentations.md).

```presentations
builders
```

## In this guide

| Task or topic | Go to |
| --- | --- |
| Presentation | [Open section](#presentation) |
| Workflow | [Open section](#workflow) |
| Interactive Preview | [Open section](#interactive-preview) |
| Add to PPT Design | [Open section](#add-to-ppt-design) |
| Example | [Open section](#example) |
| Filters | [Open section](#filters) |
| Performance and troubleshooting | [Open section](#performance-and-troubleshooting) |

## Workflow

1. Open **Chart Builder** with a workspace active.
2. Choose **CDR Type**: Data, Voice or Speech.
3. Select one or more processed datasets of that type.
4. Drag a field (or click it) to **Measure**; **Chart Type** marks the types it can draw and chooses one.
5. Drag fields to **Rows**, **Columns** and **Legend**, in the order they split the chart (`Operator` then `Campaign` gives `Operator × Campaign`). A field dropped on the middle of a pill takes its place; dropped near its left or right edge, or between pills, it goes there.
6. Drop a field on **Filters** to choose its values (with their samples) or a numeric condition, and on **One chart per** for a chart of each of its values.
7. Enter a Chart Title, give the chart its look in **Format** and review the regenerated preview.

The Source Dataset selector is filtered by CDR Type and shows only processed datasets of that type. When the chosen datasets are of an NR Mode that leaves operators out of scope (the **NR Modes** of their labels in the [Operator Maps](workspace-config.md#operator-maps), such as Three, which has no SA), the chart header names them (*Out of scope: SA · Three*) and their rows are left out of the chart.

## Interactive Preview

| Control | Behaviour |
| --- | --- |
| Chart Title | Text displayed above the generated chart. |
| Fields | The fields of the chosen CDRs, grouped by the sections of the [CDR Field Dictionary](workspace-config.md) and searchable: dimensions (values, blue `Abc`) and measures (numbers, green `#`). Drag one to a shelf, or click it and choose the shelf. |
| Measure | The KPI. Its menu chooses the aggregation (Average, Median, Sum, Count, Count distinct, Minimum, Maximum, or the one of the chart type) and its order; Multi KPI CDF Lines, Scatter and the tables take several. |
| Rows, Columns | Ordered splits of the chart: drag a pill along its shelf, or to another shelf, to change them. |
| Legend | The fields the legend explains. |
| Filters | A field dropped here opens its filter: its values in the chosen CDRs with their samples (Include, Exclude) or a text to contain; a numeric field takes a condition such as `< 1.6`. Each filter is a pill: click it to change it, **×** to remove it. |
| Chart Type | As in the [Designer](ppt-designer.md#designer) (a chart without a measure yet takes any chart type, and the **Chart** subpanel says what the one chosen needs), the **Chart Type** tab, in colour on the right edge of the chart beside the panel, opens the chart types, each drawn and grouped by what they show, over the chart; choosing one changes the chart and closes them, as the tab, ×, Esc or a click outside them do. The ones the shelves cannot draw are greyed, cannot be chosen and say what they need (one numeric measure, two for Scatter or Dual Lines, a dimension as measure for 100% Stacked Vertical Bars, a latitude and a longitude on Measure for a Map or a Symbol Map, a Columns split for Lines and Areas, two to five fields on Rows and Columns for a Sankey, a time for a Gantt): the chart types and how they read the shelves are in [Supported chart types](ppt-designer.md#supported-chart-types). Threshold, Buckets, Bin Size, Whiskers, Target, Direction, Sort and Date Bin are set beside the type that uses them, and a time dropped on Rows or Columns is grouped by day (its pill chooses the hour, day, week, month or the exact time). **KPI Card** shows one figure of the latest campaign: its **Figure** (Average, Median, Percentile, Count of samples, or a share of a value, below or above a threshold), what it is **Compared with** (the previous campaign, the best competitor or nothing), **One card per** (Operator, Vendor, Region or City) and its **Trend over the campaigns**, set under Chart Type; added to a PPT Design, it is a KPI card of the Design. |
| One chart per | A field whose values each get a chart of their own (up to 12), side by side, as a PPT Design lays them out in the place of one chart. |
| Format | Beside **Data**, as in the [Designer](ppt-designer.md#designer): the colours, lines and opacity of the series, the legend, the labels and the axes, with **Copy format** and **Default colours**. On the chart itself, an entry of its legend opens the format of that series, a numeric axis its range and a category axis its values. |

The embedded viewer provides the same Canvas rendering, semantic hover details, zoom, panning and refresh behaviour as an individual PPT Designer chart. Its chart downloads as a PNG image or copies to the clipboard as a screenshot from the floating buttons at the top right corner of its card (see [Images of charts and tables](web-interface.md#images-of-charts-and-tables)); App Events records each one as `export_chart_builder_image`, with the CDR type and CDRs used.

## Add to PPT Design or Template

**Add to PPT Design or Template…** lists the PPT Designs and the PPT Templates whose slides you can edit (admins and super-admins any, a user-editor those they created) and their slides with their free places: the chart goes, with its format and its One chart per (a KPI Card as a KPI card), to a free place of the slide chosen, or to a new slide at the end. In a **PPT Design** it becomes part of that Design only (one of its differences from its template, see [Designer](ppt-designer.md#designer)); in a **PPT Template** every PPT Design that follows the template shows it. Either way it reads the CDRs each Design chooses, not those chosen here. App Events record it as `design_chart_added` or `template_chart_added`.

## Example

```text
CDR Type: Data
Datasets: NetCheck_CDR_Data_2026_Q1.xlsx, NetCheck_CDR_Data_2026_Q2.xlsx
Chart Type: CDF Line
KPI: Mean_Data_Rate
Filters: Test_Result IN (Completed, Dropped, Failed);
Rows: Operator
Columns: Campaign
Legend: Campaign
Format · Legend: Bottom
```

## Filters

- A field dropped on **Filters** (or clicked and sent to Filters) opens its filter: its values in the chosen CDRs, most samples first and searchable, to **Include** or **Exclude**, or a text the values **Contain**; a numeric field takes a condition (`<`, `<=`, `>`, `>=`, `=`, `!=`) and a value.
- Every filter is a pill on the shelf; filters are joined with AND, and each one is written as the template writes it (`Call_Status IN (Completed, Dropped)`).
- Empty, null and NaN values are excluded from result-state calculations.

## Performance and troubleshooting

- Title, legend-position and aggregation changes reuse unchanged data where possible.
- Dataset or filter changes invalidate the relevant cache stage.
- Superseded browser preview requests are cancelled.
- If no source appears, process a dataset and select its matching CDR Type.
- If a chart is empty, inspect filtered data and verify KPI, technology and filter values.

Use PPT Reporting (old) for persistent Chart Sets and PPT Templates Editor for reusable definitions.
