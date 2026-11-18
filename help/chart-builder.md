# Chart Builder

Chart Builder is the ad-hoc chart editor: draw any chart on the processed CDRs, explore it, and keep it only if you want to.

- **Same chart as PPT Designer:** it uses the PPT Designer individual Canvas chart viewer, embedded directly in the page, and the shelves of the chart builder of the [Designer](ppt-designer.md#designer).
- **Temporary:** its definition creates no PowerPoint report.
- **Kept only on request:** it changes a PPT Design or a PPT Template only when **Add to PPT Design or Template…** puts the chart, with its format, on one of their slides.

> [!NOTE]
> **Temporary exploration.** Changes here create an ad-hoc chart. They do not modify a Report Template or generate a PowerPoint report.

> [!TIP]
> **Investigate empty charts.** Check the selected CDRs, filters and sample counts before changing the chart presentation.

## Presentation

```presentations
builders
```

## Choose your task

| I want to… | Go to |
| --- | --- |
| Watch the presentation | [Presentation](#presentation) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |
| Build a chart step by step | [Workflow](#workflow) |
| Understand the shelves, Chart Type and Format | [Interactive Preview](#interactive-preview) |
| Keep the chart in a PPT Design or Template | [Add to PPT Design or Template](#add-to-ppt-design-or-template) |
| See a complete example | [Example](#example) |
| Filter the rows of the chart | [Filters](#filters) |
| Make it faster or fix an empty chart | [Performance and troubleshooting](#performance-and-troubleshooting) |

## Tips & shortcuts

Gestures that save time while building a chart.

### Shelves and fields

| To… | Do this |
| --- | --- |
| Put a field on a shelf | Drag it there, or click it and choose the shelf |
| Put a field before or after a pill | Drop it near the left or right edge of the pill, or between pills (a bar shows where it goes) |
| Replace a pill | Drop the field on the middle of the pill (the pill it replaces is outlined) |
| Move a pill | Drag it along its shelf or to another shelf; or click its label → **Move before** / **Move after** |
| Change the aggregation of a measure | Click its pill |
| Group a time by hour, day, week or month | Click its pill on Rows or Columns |
| Set the limits of the classes of `Rate Bucket` or `Buckets` | Click its pill; <kbd>Enter</kbd> keeps the limits |
| Change or remove a filter | Click its pill to change it; **×** removes it |
| Choose the chart type | Click the **Chart Type** tab on the right edge of the chart; <kbd>Esc</kbd> or a click outside closes it |

### On the chart

| To… | Do this |
| --- | --- |
| Read the value of a point | Point at it: a tooltip names its label, series and value |
| Change the colour, width, line or opacity of a series | Click its entry in the legend (here it never hides the series) |
| Change the range of a numeric axis | Click its labels and drag the two ends of the slider |
| Choose the values of a text axis | Click its labels: untick values, **Only** one, or **Show all** |
| Change the order of the values of Rows or Columns | Drag an axis label, header or row label before or after another (**Default order** gives it back) |
| Zoom into one area | With the mouse, drag a rectangle over the plot (at 100%; not from the title or the legend) |
| Zoom in or out | **−** and **+** (100% to 400%, in steps of 25%), the reset arrow to go back |
| Move around a zoomed chart | Drag it, or use the arrows that appear once zoomed |
| Copy or download the chart as an image | Point at its card for the buttons at its top right corner. On touch: tap; they show for 5 seconds. |

> [!NOTE]
> **Only in PPT Designer:** zooming with <kbd>Ctrl</kbd>/<kbd>Cmd</kbd> + wheel, the larger view (double-click) and hiding series from the legend are features of the [PPT Designer](ppt-designer.md#tips-shortcuts) viewer.

## Workflow

1. Open **Chart Builder** with a workspace active.
2. Choose **CDR Type**: Data, Voice or Speech.
3. Select one or more processed datasets of that type.
4. Drag a field (or click it) to **Measure**; **Chart Type** marks the types it can draw and chooses one.
5. Drag fields to **Rows**, **Columns** and **Legend**, in the order they split the chart (`Operator` then `Campaign` gives `Operator × Campaign`).
   - A field dropped on the middle of a pill takes its place; dropped near its left or right edge, or between pills, it goes there.
   - While dragging, a bar between the pills shows where it will go (or the pill it replaces is outlined), and a pill moved along its shelf is shown dimmed.
6. Drop a field on **Filters** to choose its values (with their samples) or a numeric condition, and on **One chart per** for a chart of each of its values.
7. Enter a Chart Title, give the chart its look in **Format** and review the regenerated preview.

- **Source Dataset** is filtered by CDR Type and shows only processed datasets of that type.
- **Out of scope operators:** when the chosen datasets are of an NR Mode that leaves operators out of scope (the **NR Modes** of their labels in the [Operator Maps](workspace-config.md#operator-maps), such as Three, which has no SA), the chart header names them (*Out of scope: SA · Three*) and their rows are left out of the chart.

## Interactive Preview

The controls of the chart definition and of the embedded viewer.

| Control | Behaviour |
| --- | --- |
| Chart title | Text displayed above the generated chart. |
| Data, Format | The two tabs of the chart definition: **Data** has the shelves and the settings of the chart type, **Format** the look of the chart (not available for a KPI Card). A dot on **Format** says the chart has a format of its own. |
| Fields | The fields of the chosen CDRs, grouped by the sections of the [CDR Field Dictionary](workspace-config.md) and searchable: dimensions (values, blue `Abc`) and measures (numbers, green `#`), with **NR Mode** (the NR Mode of the CDR of each row, NSA or SA) beside Campaign. Drag one to a shelf, or click it and choose the shelf. |
| Measure | The KPI. Its menu chooses the aggregation (Average, Median, Sum, Count, Count distinct, Minimum, Maximum, or the one of the chart type) and its order; Multi KPI CDF Lines, Scatter and the tables take several. |
| Rows, Columns | Ordered splits of the chart: drag a pill along its shelf, or to another shelf, to change them. |
| Legend | The fields the legend explains. |
| Filters | A field dropped here opens its filter: its values in the chosen CDRs with their samples (Include, Exclude) or a text to contain; a numeric field takes a condition such as `< 1.6`. Each filter is a pill: click it to change it, **×** to remove it. |
| Chart Type | The **Chart Type** tab, in colour on the right edge of the chart beside the panel, opens the chart types over the chart (see below). |
| One chart per | A field whose values each get a chart of their own (up to 12), side by side, as a PPT Design lays them out in the place of one chart. |
| Format | Beside **Data**, as in the [Designer](ppt-designer.md#designer): the colours, lines and opacity of the series, the legend, the labels and the axes, with **Copy format** and **Default colours**. |

**Chart Type**, as in the [Designer](ppt-designer.md#designer):

- **Opening and closing:** the types are each drawn and grouped by what they show, over the chart. Choosing one changes the chart and closes them, as the tab, **×**, <kbd>Esc</kbd> or a click outside them do.
- **Any type for a new chart:** a chart without a measure yet takes any chart type, and the **Chart** subpanel says what the one chosen needs.
- **Greyed types:** the ones the shelves cannot draw are greyed, cannot be chosen and say what they need: one numeric measure, two for Scatter or Dual Lines, a dimension as measure for 100% Stacked Vertical Bars, a latitude and a longitude on Measure for a Map or a Symbol Map, a Columns split for Lines and Areas, two to five fields on Rows and Columns for a Sankey, a time for a Gantt. The chart types and how they read the shelves are in [Supported chart types](ppt-designer.md#supported-chart-types).
- **Settings of the type:** Threshold, Buckets, Bin Size, Whiskers, Target, Direction, Sort and Date Bin are set beside the type that uses them. The classes of a [Distribution chart](ppt-designer.md#distribution-stacked-vertical-bars) are in the **Distribution classes** group of **Fields**: `Rate Bucket` and `Buckets`.
- **Times:** a time dropped on Rows or Columns is grouped by day (its pill chooses the hour, day, week, month or the exact time).
- **KPI Card** shows one figure of the latest campaign, set under Chart Type:
  - **Figure:** Average, Median, Percentile, Count of samples, or a share of a value, below or above a threshold.
  - **Compared with:** the previous campaign, the best competitor or nothing.
  - **One card per:** Operator, Vendor, Region or City.
  - **Trend over the campaigns.**
  - Added to a PPT Design, it is a KPI card of the Design.

**Format on the chart itself:**

- An entry of its legend opens the format of that series.
- A numeric axis opens its range, and a category axis its values.
- A value of the Rows or Columns dragged before or after another one changes their order (**Default order**, in the card of its values, gives it back).

**The embedded viewer** provides the same Canvas rendering, semantic hover details, zoom, panning and refresh behaviour as an individual PPT Designer chart:

- **Refresh chart** (top right of the viewer) draws it again.
- **Zoom:** the zoom buttons (− and +, from 100% to 400% in steps of 25%, and the reset arrow), or a rectangle dragged over the plot with the mouse; the arrows that appear once zoomed, or a drag, move the view.
- **Images:** its chart downloads as a PNG image or copies to the clipboard as a screenshot from the floating buttons at the top right corner of its card (see [Images of charts and tables](web-interface.md#images-of-charts-and-tables)). App Events records each one as `export_chart_builder_image`, with the CDR type and CDRs used.

## Add to PPT Design or Template

Keep the chart on a slide of a PPT Design or a PPT Template.

1. Click **Add to PPT Design or Template…** (disabled until a Measure and a Source Dataset are chosen).
2. Choose the **PPT Design** or **PPT Template** tab. A tab is disabled when you can edit none of that kind; with none of either, the dialog says to create one in PPT Designer first.
3. Choose the Design or Template to use.
4. Choose a **Slide**: the list shows the free places of each slide (a slide without one cannot be chosen).
5. Click **Add** (or **Cancel**).

- **Who:** only the PPT Designs and the PPT Templates whose slides you can edit are listed (see [Who changes a Design](ppt-designer.md#who-changes-a-design)).
- **Where it goes:** the chart goes, with its format and its One chart per (a KPI Card as a KPI card), to a free place of the slide chosen, or to a new slide at the end.
- **PPT Design:** it becomes part of that Design only (one of its differences from its template, see [Designer](ppt-designer.md#designer)).
- **PPT Template:** every PPT Design that follows the template shows it.
- **Its CDRs:** either way it reads the CDRs each Design chooses, not those chosen here.
- App Events record it as `design_chart_added` or `template_chart_added`.

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

- **Values or a text:** a field dropped on **Filters** (or clicked and sent to Filters) opens its filter: its values in the chosen CDRs, most samples first and searchable, to **Include** or **Exclude**, or a text the values **Contain**.
- **Numbers:** a numeric field takes a condition (`<`, `<=`, `>`, `>=`, `=`, `!=`) and a value.
- **Pills joined with AND:** every filter is a pill on the shelf; filters are joined with AND, and each one is written as the template writes it (`Call_Status IN (Completed, Dropped)`).
- Empty, null and NaN values are excluded from result-state calculations.

## Performance and troubleshooting

- **Only the columns it needs:** Chart Builder reads only the columns each chart reads (its measures, Rows, Columns, Legend, Filters and One chart per) from the columnar copies of the chosen CDRs, and keeps the columns it read in memory (up to about 1.5 GB, the CDRs used least recently given up first): a field dropped on a shelf reads only its own column.
- **Read ahead:** the common fields (Operator, Campaign, City, Test Name, Test Result…) are read in the background once the CDRs are chosen, and the values of a filter read only the column of its field.
- **Reuse:** a chart drawn before (undo, another chart type and back) is shown again at once; title, legend-position, format and aggregation changes reuse the rows already read and filtered.
- **While updating:** the chart shown stays, dimmed under **Updating**, while the next chart is worked out; quick changes of the shelves are grouped, and superseded preview requests are cancelled.
- **Read again:** dataset changes, and changes of the Operator Maps, read the CDRs again.
- **No source appears:** process a dataset and select its matching CDR Type.
- **Empty chart:** inspect filtered data and verify KPI, technology and filter values.

Use [PPT Designer](ppt-designer.md) to keep charts in a Design and generate its PowerPoint, and PPT Templates Editor for reusable definitions.
