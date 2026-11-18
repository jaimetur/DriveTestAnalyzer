# CDR Analysis

CDR Analysis provides on-demand KPI analysis for one processed CDR in the active workspace.

> [!NOTE]
> **One dataset at a time.** Use this module for a focused investigation of one processed Data, Voice or Speech CDR. Use PPT Designer for a complete template across multiple datasets.

> [!TIP]
> **Inspect before exporting.** Update Analysis after changing the controls, then inspect sample counts and the filtered records.

## Presentation

```presentations
cdr-analysis
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Know why a CDR is not listed | [Eligible datasets](#eligible-datasets) |
| Pick a CDR and analyse it | [Analysis workflow](#analysis-workflow) |
| Choose the filters and options of the analysis | [Analysis Controls](#analysis-controls) |
| Read the summary of a CDR | [Dataset Summary](#dataset-summary) |
| Read the charts and scorecards | [Charts and Scorecards](#charts-and-scorecards) |
| See the metrics calculated for the CDR | [Processed Metrics](#processed-metrics) |
| Look at the rows behind a result and export them | [Preview and export](#preview-and-export) |
| <span class="guide-sub">↳ Inspect the persisted rows</span> | <span class="guide-sub">↳ [Inspect persisted rows](#inspect-persisted-rows)</span> |
| <span class="guide-sub">↳ Export the analysis</span> | <span class="guide-sub">↳ [Export the analysis](#export-the-analysis)</span> |
| Follow an example investigation | [Example investigation](#example-investigation) |
| Make large analyses faster | [Performance](#performance) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Eligible datasets

Only processed CDR-Data, CDR-Voice and CDR-Speech datasets are listed; mappings, logs and generic datasets are excluded from the selector.

## Analysis workflow

1. Select a processed dataset: **Input Type** (All CDR Types, CDR-Data, CDR-Voice or CDR-Speech) narrows the **Dataset** list.
2. Choose the metrics, apply the filters and choose an aggregation where offered.
3. Click **Update Analysis** and confirm the filtered sample count.
4. Review charts, scorecards and processed metrics, and export only after validating the analytical context.

## Analysis Controls

Controls adapt to the selected dataset.

- **Metrics:** only measurements, every available one selected by default.
  - First the service KPIs (POLQA LQ, LQ, Mean Data Rate, call setup time, delays, RTT, throughput, jitter and packet loss), then the radio and service measurements (RSRP, RSRQ, SINR, CQI, MCS, BLER, transmit power and throughput averages).
  - Not offered: identifiers, coordinates, phone numbers, IMEI/IMSI/MSISDN, software versions, timestamps, durations, transferred bytes, bands, PCI/ARFCN, quarters, speeds and minimum or maximum columns.
- **Filters:** in the order Source Sheet, Operator, **Operator_Vendor** (`<Operator>_<Vendor>`), **Vendor_Operator** (`<Vendor>_<Operator>`), **Vendor** (the vendor alone), Market, Region, **Cluster**, City, Test Name and the remaining dimensions. Each lists the values found in the rows of the open CDR; dimensions without values are disabled.
  - **Operator_Vendor**, **Vendor_Operator** and **Vendor** stay in sync: selecting identities in one selects them in the other and their Vendors in Vendor; selecting Vendors selects every identity of those Vendors.
  - A filter applied with every value selected (**All values**) stays open: values that appear later in the CDR, for example after a mapping change, are selected too.
- **Date From** and **Date To:** limit the analysis to a date range; disabled while **Ignore event time filtering** is on in [Application Config](app-config.md).
- **Saved per CDR:** **Open Dataset** shows the analysis at once. The last metrics and filters applied with **Update Analysis** are kept for each CDR, shared by every user of the workspace and restored in every session (opening another CDR and coming back keeps them). **Reset** clears them and shows the default analysis.
- **Source data untouched:** filters apply only to the analysis; they never overwrite the stored dataset rows.

## Dataset Summary

- Dataset identity and current context, global summary cards, per-KPI headline values, percentile scorecards and filtered sample counts.
- **Out of scope:** the operators out of scope in the NR Mode of the CDR (the **NR Modes** of their labels in the [Operator Maps](workspace-config.md#operator-maps), such as Three, which has no SA) are named beside **Global Metrics** (*Out of scope: SA · Three*); their rows are left out of the analysis.

## Charts and Scorecards

- **CDF Curve** shows the empirical KPI distribution. **Global CDF Comparison** and **Compare CDF by** draw one curve per value of the chosen dimension (Operator by default, listed first), up to eight curves.
- **Group Benchmark** compares the selected aggregation; bar labels that do not fit are rotated.
- **Zoom:** floating controls at the top right of every chart (−, level, + and reset); dragging a rectangle zooms into it, as in PPT Designer: a CDF narrows its X and Y range, a bar chart widens to fit the selected bars and scrolls to them.
- **Values:** hovering a bar shows its value; hovering a CDF shows the probability of every curve at that value.
- **Visible X Range:** two handles set the start and end of the CDF axis. By default it starts where the first curve reaches 5% of its samples and ends where every curve reaches 95%, leaving out nearly empty tails; a rectangle zoom moves both handles and reset returns to these defaults.
- **Grouped Percentiles** and **Processed Metrics** show two decimals; Processed Metrics lists Cluster after Region.
- **Order:** grouped by Operator, Vendor or Operator_Vendor, tables, percentiles, bars and CDF curves follow the Operator Maps and Vendor Maps order of Workspace Config; values not in the maps follow alphabetically (mixed groups before operators without a vendor).
- Metric cards provide compact numerical summaries.

## Processed Metrics

The table shows the calculated records for the active request. Use it to verify that the chart and KPI cards share the same scope.

## Preview and export

### Inspect persisted rows

**Preview Dataset** opens the stored rows of the CDR in the dataset preview described in [Dataset Preview](workspace-management.md#dataset-preview): 100-row pages, a searchable Dataset selector, column and label selectors, Excel-style column filters, field labels and their rule tooltips. Field naming and fallback rules are in [Fixed CDR Fields](workspace-management.md#fixed-cdr-fields).

### Export the analysis

**Export PowerPoint** and **Export Word** open one dialog:

- **Use the current filters, metrics and chart settings** (checked when an analysis is open): the document is the open CDR exactly as on screen, with its metrics and filters, each chart's **Compare by** and **Compare CDF by**, and each CDF's **Visible X Range**.
- **Unchecked:** exports the CDRs selected in the dialog (the open CDR by default; CDR Data, Voice and Speech panels with **Select All** each) with every KPI and no filters.
- **PowerPoint:** uses the workspace PowerPoint template (`assets/powerpoint-templates/Template_VodafoneThree.pptx`): a title slide names the CDR and lists its type, metrics and every filter, the content slides use the template's title layout, and the deck ends with its closing slide.
- **Word:** the same report, one landscape page per slide (rendered with LibreOffice when it is installed, as in the Docker image).
- **Kept:** exported documents are also kept in the `output/reports/cdr-analysis/` folder of the workspace, where an identical export of the open CDR is reused instead of generated again.
- CDR Analysis is also a section of the reports of [Reporting](reporting.md#the-report-editor), with the CDR types, parts of the analysis and metrics chosen there. For a complete template-driven report, use PPT Designer.

**Theme**, at the start of the floating section bar of the page, applies the themes of [Scoring & GAP Analysis](scoring-gap-analysis.md#choose-a-theme) (**Ericsson** by default; one theme per user and workspace, shared with the other themed modules, recorded in App Events):

- **On the page:** charts, chart and metric cards, statistic tiles, table headers and alternate rows, labels and accents.
- **In the exports:** the CDF curves and the bars without an Operator or Vendor colour, chart and metric cards, table headers and alternate rows, and the titles and subtitles of the content slides (the title and closing slides keep the template look). **Midnight** gives the content slides a night-blue background with white logos and every table, card and chart dark.

## Example investigation

To compare throughput by operator:

```text
Dataset: CDR-Data 2026-Q2
KPI: Mean_Data_Rate
Filter: Test_Result = Completed
Aggregation: Operator
```

First compare group sample counts. Then inspect the CDF and group benchmark. If a result differs from another tool, reproduce the same row set in Preview and verify null/result-state handling.

## Performance

- Opening the page reads cached metadata; which metrics have values in each CDR is checked once and kept until the CDR changes.
- Full analysis starts only after **Update Analysis**.
- The first four metrics show at once; the other metrics and the Processed Metrics table appear a few at a time as they are calculated, while you already work with the first ones.
- Repeated dataset/filter/metric combinations reuse process-local in-memory cache entries, cleared by an application restart.

## Tips & shortcuts

The charts react to the mouse as below. The gestures of **Preview Dataset** are in [Workspace Management](workspace-management.md#tips-shortcuts); the shortcuts that work everywhere are in [Web Interfaces](web-interface.md#tips-shortcuts).

| To… | Do this |
| --- | --- |
| Zoom a CDF into a range | Drag a rectangle over it: it narrows the X and Y range and moves both handles of **Visible X Range** |
| Zoom into some bars | Drag a rectangle over them: the chart widens to fit them and scrolls to them |
| Go back to the whole chart | The reset button of the zoom controls at its top right corner |
| Read a value | Hover a bar, or hover a CDF to read the probability of every curve at that value |
