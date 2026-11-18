# Chart Builder

Chart Builder is the ad-hoc chart editor: draw any chart on the processed CDRs, explore it, and keep it only if you want to.

- **Same chart as PPT Designer:** it embeds the individual Canvas chart viewer of PPT Designer and uses the shelves of the [Designer](ppt-designer.md#designer).
- **Temporary:** its definition creates no PowerPoint report and changes no Report Template.
- **Kept only on request:** it changes a PPT Design or a PPT Template only when **Add to PPT Design or Template…** puts the chart, with its format, on one of their slides.

## Presentation

```presentations
builders
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Build a chart step by step | [Workflow](#workflow) |
| Change the shelves, chart type and format | [Interactive Preview](#interactive-preview) |
| Keep the chart in a PPT Design or Template | [Add to PPT Design or Template](#add-to-ppt-design-or-template) |
| Follow an example | [Example](#example) |
| Filter the rows of the chart | [Filters](#filters) |
| Make it faster or fix an empty chart | [Performance and troubleshooting](#performance-and-troubleshooting) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Workflow

1. Open **Chart Builder** with a workspace active.
2. Choose **CDR Type**: Data, Voice or Speech.
3. Select one or more processed datasets of that type (**Source Dataset** lists only those).
4. Drag a field (or click it) to **Measure**; **Chart Type** marks the types it can draw and chooses one.
5. Drag fields to **Rows**, **Columns** and **Legend**, in the order they split the chart (`Operator` then `Campaign` gives `Operator × Campaign`). Where a dropped field goes is as in the [Designer](ppt-designer.md#data-source-nr-mode-and-shelves); a pill moved along its shelf is shown dimmed.
6. Drop a field on **Filters** to choose its values or a numeric condition, and on **One chart per** for a chart of each of its values.
7. Enter a Chart Title, give the chart its look in **Format** and review the regenerated preview.

**Out of scope operators:** when the chosen datasets are of an NR Mode that leaves operators out of scope (the **NR Modes** of their labels in the [Operator Maps](workspace-config.md#operator-maps), such as Three, which has no SA), the chart header names them (*Out of scope: SA · Three*) and their rows are left out.

## Interactive Preview

The chart definition and the embedded viewer. Shelves, Chart Type, Format and KPI cards work as in the [Designer](ppt-designer.md#charts-on-the-slide); what differs or adds:

- **Data and Format** are the two tabs of the definition: **Data** has the shelves and the settings of the chart type; **Format** the look (series colours, lines and opacity, legend, labels, axes, **Copy format**, **Default colours**), not available for a KPI Card. A dot on **Format** says the chart has a format of its own.
- **Fields** are those of the chosen CDRs, grouped by the sections of the [CDR Field Dictionary](workspace-config.md) and searchable, with **NR Mode** beside Campaign. Drag one to a shelf, or click it and choose the shelf.
- **Measure:** its menu chooses the aggregation (Average, Median, Sum, Count, Count distinct, Minimum, Maximum, or the one of the chart type) and its order; Multi KPI CDF Lines, Scatter and the tables take several measures.
- **Rows, Columns:** drag a pill along its shelf, or to another shelf, to change the splits.
- **One chart per:** up to 12 charts, side by side, as a PPT Design lays them out in the place of one chart.
- **Chart Type:** the tab on the right edge of the chart, beside the panel, opens the types over the chart; greyed types and what they need are as in the [Designer](ppt-designer.md#chart-type), and how each type reads the shelves is in [Supported chart types](ppt-designer.md#supported-chart-types). The classes of a [Distribution chart](ppt-designer.md#distribution-stacked-vertical-bars) are `Rate Bucket` and `Buckets` in the **Distribution classes** group of **Fields**.
- **KPI Card** is set under Chart Type with the options of a [KPI card](ppt-designer.md#kpi-cards-text-boxes-and-pictures); added to a PPT Design, it is a KPI card of the Design.
- **On the chart:** a legend entry opens the format of that series (it never hides it here), a numeric axis its range, a category axis its values, and dragging a value of Rows or Columns reorders them.

**The embedded viewer** has the Canvas rendering, hover details, zoom, panning and refresh of an individual PPT Designer chart:

- **Refresh chart** (top right of the viewer) draws it again.
- **Zoom:** **−** and **+** (100% to 400% in steps of 25%) and the reset arrow, or a rectangle dragged over the plot with the mouse; once zoomed, its arrows or a drag move the view.
- **Images:** the chart downloads as a PNG or copies to the clipboard from the floating buttons at the top right of its card (see [Images of charts and tables](web-interface.md#images-of-charts-and-tables)). App Events records each as `export_chart_builder_image`, with the CDR type and CDRs used.

## Add to PPT Design or Template

Keep the chart on a slide of a PPT Design or a PPT Template.

1. Click **Add to PPT Design or Template…** (disabled until a Measure and a Source Dataset are chosen).
2. Choose the **PPT Design** or **PPT Template** tab. A tab is disabled when you can edit none of that kind; with none of either, the dialog says to create one in PPT Designer first.
3. Choose the Design or Template: only those whose slides you can edit are listed (see [Who changes a Design](ppt-designer.md#who-changes-a-design)).
4. Choose a **Slide**: the list shows the free places of each slide (a slide without one cannot be chosen).
5. Click **Add** (or **Cancel**).

- **Where it goes:** with its format and its One chart per (a KPI Card as a KPI card), to a free place of the slide chosen, or to a new slide at the end.
- **PPT Design:** it becomes part of that Design only (one of its differences from its template, see [Designer](ppt-designer.md#designer)). **PPT Template:** every PPT Design that follows the template shows it.
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

- **Values or a text:** a field dropped on **Filters** (or clicked and sent to Filters) opens its values in the chosen CDRs, most samples first and searchable, to **Include** or **Exclude**, or a text the values **Contain**.
- **Numbers:** a numeric field takes a condition (`<`, `<=`, `>`, `>=`, `=`, `!=`) and a value, such as `< 1.6`.
- **Pills joined with AND:** each filter is a pill (click it to change it, **×** to remove it), written as the template writes it (`Call_Status IN (Completed, Dropped)`).
- Empty, null and NaN values are excluded from result-state calculations.

## Performance and troubleshooting

- **Only the columns it needs:** Chart Builder reads only the columns each chart uses (measures, Rows, Columns, Legend, Filters and One chart per) from the columnar copies of the chosen CDRs, and keeps them in memory (up to about 1.5 GB, the CDRs used least recently given up first): a field dropped on a shelf reads only its own column.
- **Read ahead:** the common fields (Operator, Campaign, City, Test Name, Test Result…) are read in the background once the CDRs are chosen; the values of a filter read only the column of its field.
- **Reuse:** a chart drawn before (undo, another chart type and back) shows again at once; title, legend-position, format and aggregation changes reuse the rows already read and filtered.
- **While updating:** the chart shown stays, dimmed under **Updating**; quick shelf changes are grouped and superseded preview requests cancelled.
- **Read again:** dataset changes and changes of the Operator Maps read the CDRs again.
- **No source appears:** process a dataset and select its matching CDR Type.
- **Empty chart:** check the selected CDRs, filters and sample counts, then the KPI, technology and filter values, before changing the chart presentation.

Use [PPT Designer](ppt-designer.md) to keep charts in a Design and generate its PowerPoint, and its [PPT Templates](ppt-designer.md#ppt-templates) for reusable definitions.

## Tips & shortcuts

Gestures that save time while building a chart.

### Shelves and fields

| To… | Do this |
| --- | --- |
| Put a field on a shelf | Drag it there, or click it and choose the shelf |
| Put a field before or after a pill, or replace it | Drop it near the left or right edge of the pill or between pills (a bar shows where), or on its middle to replace it (the pill is outlined) |
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
| Zoom | **−** and **+** (100% to 400%, in steps of 25%), the reset arrow to go back, or with the mouse drag a rectangle over the plot (at 100%; not from the title or the legend) |
| Move around a zoomed chart | Drag it, or use the arrows that appear once zoomed |
| Copy or download the chart as an image | Point at its card for the buttons at its top right corner. On touch: tap; they show for 5 seconds. |

> [!NOTE]
> **Only in PPT Designer:** zooming with <kbd>Ctrl</kbd>/<kbd>Cmd</kbd> + wheel, the larger view (double-click) and hiding series from the legend are features of the [PPT Designer](ppt-designer.md#tips-shortcuts) viewer.
