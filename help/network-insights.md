# Network Insights

Analyse the network behind the measured performance: radio quality (RSRP and SINR), weak-coverage and high-interference areas on a map, the cells that served the samples (their distance, overshooting and hosting network), 5G availability on the sites with NR, the inventory snapshot of every network (owner and host networks, data quality), site density, licensed, deployed and observed spectrum (the sites with NR TDD and NR FDD, the bandwidth of every band and the primary bandwidth of the tests), and network deployment (NNS, eMOCN scenarios, host networks and RAN vendors). Results are split by the dimensions checked in **Split by**; Operator and Campaign are checked by default.

Every panel opens with the question it answers, and its notes explain how to read it.

- **Pills after each title:** as in Scoring & GAP Analysis, the title of every chart and table ends with pills naming its area (the City, Cluster or Region filters, the most specific first, else **National**), its operators (**All Operators** without an Operator filter), its vendors (**All Vendors** without a Vendor filter) and, when chosen, its Environments. A list of over three names shows two and how many more; hovering a pill lists them all. A chart or table without a title of its own has them in a line above it, and its larger view beside its title.
- **Which filters they name:** the measurement panels, those of the analysis shown; the NR sites by duplex mode and the site tables of Network Deployment, those of their own selection (without Environments, which describe measurements); the panels of the whole inventory (Network Snapshot, the grouped Network Deployment views, the inventory density and the licensed and deployed spectrum), National, All Operators and All Vendors.
- **Order and colours:** operators and networks appear everywhere in the order and colours of the workspace **Operator Maps**; rows of ignored CDR sheets are excluded.
- **Long tables** scroll inside their frame under a fixed header.
- **Larger view:** double-click any chart, map or table to open it filling the screen but a narrow margin: charts and maps are drawn again with their zoom controls, and tables show every row.
- **Images:** every panel, chart, map, ladder and table downloads as a PNG or copies to the clipboard from the floating buttons at its top right corner, also in the larger view (see [Images of charts and tables](web-interface.md#images-of-charts-and-tables)); App Events records each one as `export_network_insights_image`.

After **Launch Analysis**, the panels are grouped in three collapsible categories: **Summary** (Overview and Key Findings), **Radio Performance** (Coverage & Interference Maps, RF Quality, Latency & Interactivity, Serving Cells and 5G Availability) and **Network & Spectrum** (Network Snapshot, Network Deployment, Cluster Sites Density and Spectrum). In the floating section bar and the sections menu of the tab, each category goes to its panel and its arrow lists its panels.

Each panel names its **data sources** as coloured labels under its title (hover one for where it comes from). In a panel with several sources each table or chart names its own (*Weakest coverage areas*: CDRs; *Cell status near the weak areas*: Network Inventory), and some labels follow a choice: the Cluster Sites Density table and Network Deployment (Observed Sites/Cells → CDRs; split by Region or Cluster → polygons too), and the ladders and locations of Spectrum (Bandwidth: CA Appendix).

| Source | Panels |
| --- | --- |
| **CDRs** (Data, Voice, Speech) | Overview, Coverage & Interference Maps, RF Quality, Serving Cells, 5G Availability, Cluster Sites Density |
| **CDR Data** | Key Findings, Latency & Interactivity, Spectrum |
| **Network Inventory** | Coverage & Interference Maps, Serving Cells, 5G Availability, Network Snapshot, Network Deployment, Cluster Sites Density, Spectrum |
| **CA Appendix** | Spectrum |
| **Region & Cluster polygons** | Network Deployment, Cluster Sites Density |
| **Spectrum Holdings**, **Serving Networks** (Workspace Config) | Spectrum, Serving Cells |

> [!NOTE]
> **Radio views need no extra input.** RSRP, SINR, maps, observed eNodeBs and observed bands come from the processed CDRs. The Network Inventories (Cell Configuration KMZ packages included) and the licensed spectrum are optional inputs that complete the other panels (see [Pending inputs](#pending-inputs)).

## Presentation

```presentations
network-insights
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Run an analysis | [Launch Analysis](#launch-analysis) |
| <span class="guide-sub">↳ Group the results by area or campaign</span> | <span class="guide-sub">↳ [Grouping](#grouping)</span> |
| <span class="guide-sub">↳ Choose the theme of the analysis</span> | <span class="guide-sub">↳ [Theme](#theme)</span> |
| <span class="guide-sub">↳ Combine LTE and NR</span> | <span class="guide-sub">↳ [LTE+NR](#lte-nr)</span> |
| Compare the coverage and RF quality of the operators | [Overview and RF Quality](#overview-and-rf-quality) |
| Read the main findings at a glance | [Key Findings](#key-findings) |
| Export the analysis to PowerPoint or Word | [Export](#export) |
| Find weak-coverage or high-interference areas | [Coverage and Interference Maps](#coverage-and-interference-maps) |
| Compare the latency of gaming and video chat | [Latency & Interactivity](#latency-interactivity) |
| Find overshooting and far serving cells | [Serving Cells](#serving-cells) |
| Find 5G sites that give no NR | [5G Availability](#5g-availability) |
| See a snapshot of each network | [Network Snapshot](#network-snapshot) |
| Compare the sites and technologies deployed | [Network Deployment](#network-deployment) |
| Compare the density of sites per cluster | [Cluster Sites Density](#cluster-sites-density) |
| Compare the spectrum and bandwidth of the operators | [Spectrum](#spectrum) |
| Use the RF Quality template in PPT Designer | [RF Quality template and Design](#rf-quality-template-and-design) |
| Know which data each panel reads | [Data sources](#data-sources) |
| Provide the inputs that are still missing | [Pending inputs](#pending-inputs) |
| Keep and transfer the analyses | [Persistence and transfers](#persistence-and-transfers) |
| Fix an empty or slow analysis | [Troubleshooting](#troubleshooting) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Launch Analysis

**Favourite**, at the top of the panel, keeps Analysis Selections (every control and filter of the panel) to analyse them again:

- **★ Save as favourite** saves the current selection under the **Name** entered; with a favourite chosen and its name kept, it is updated, and another name saves a new one.
- **Choosing one** makes it the selection of the page and analyses it (at once when its analysis is stored); the selector keeps showing it when the page is reloaded with its selection.
- **Rename** gives the chosen one another name, keeping the selection it saved (not the changes of the panel); **Delete** removes it.
- Favourites belong to the workspace (saving, renaming and deleting needs `user-editor`, `admin` or `super-admin`), are recorded in App Events and travel with the **Network Insights Favourites** element of Admin → Import / Export / Transfer, with Full Workspace transfers and with backups.

1. Open the workspace and the **Network Insights** tab, which follows **Scoring & GAP Analysis**.
2. Choose **NR Mode** and, first among the **Filters**, the **Campaign**. An analysis has one campaign, which chooses its CDRs: the Data, Voice and Speech CDRs of that NR Mode that the combined CDR tables include for it (see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)).
   - **Choices:** **Latest campaign** (the default) and **Previous campaign** (the one before it), the newest campaigns of the NR Mode each time the analysis runs (also when campaigns arrive later), then each campaign. Neither counts [Flex campaigns](workspace-management.md#flex-campaigns) nor [campaigns in progress](workspace-management.md#campaigns-in-progress): those are analysed only when chosen.
   - **Operators out of scope** in the NR Mode (the **NR Modes** of their labels in the [Operator Maps](workspace-config.md#operator-maps), such as Three, which has no SA) are named in a pill of the CDRs used, *Out of scope: SA · Three*, and their tests are left out.
   - **Saved with several campaigns:** selections, favourites and the Network Insights sections of [Reporting](reporting.md) reports saved with several campaigns keep the newest one; those saved with Latest 2, 3 or 4 campaigns, All available campaigns or every campaign take Latest campaign.
   - **CDRs used**, below the Filters, lists them by type, newest campaign first, with their stage and campaigns, following every filter change at once.
3. Restrict **Operators**, **Vendors**, **Regions**, **Clusters**, **Cities** or **Environments** in **Filters** if needed.
   - **Environments** group where the tests ran, from `G_Level_3` (else `G_Level_2`): big cities, driven and walked, are **Cities**; medium and small cities **Towns**; connecting roads, highways and train routes **Roads and railways**.
   - Every filter lists the values of every CDR of the NR Mode, with the labels of the Operator, Vendor and Campaign Maps, narrowed by the other filters (choosing Three as Operator leaves only Three's Vendors) but not by its own choice; an open list stays open while values are checked. **Main Cities** comes first in Cities when configured. Every value selected, or none, applies no restriction.
   - The lists come from the combinations of values each CDR keeps (the **CDR Filter Facets** table), never from the rows of the CDRs.
4. Set the controls above the Filters, in three groups:
   - **Scope:** **Technology** (LTE, NR or LTE+NR) and **Split by** (Operator, Vendor, Region, Cluster, City, Environment, CDR type and Campaign).
   - **Thresholds** of the selected technology (LTE and NR have their own because LTE RSRP/SINR and NR SS-RSRP/SS-SINR use different reference signals; LTE+NR shows both pairs):

     | Threshold | LTE default | NR default |
     | --- | --- | --- |
     | Coverage below (low coverage) | -110 dBm | -115 dBm |
     | Interference below (high interference) | 0 dB | -3 dB |

   - **Maps & inventory:** the **Map grid** size (default 250 m); the **Inventory snapshot**, **Newest of each network** (the default) or one snapshot, used for the networks it covers (the newest for the others; see [Network Snapshot](#network-snapshot)); and **Overshooting beyond (km)**, 5 km by default, the distance from which a sample counts as overshooting in [Serving Cells](#serving-cells).
5. Press **Analyse Network**. A dialog shows the analysis in progress with the elapsed time and closes when the results are ready; **Hide** closes it while the analysis continues.

### Grouping

**Split by** accepts several dimensions, forming a hierarchy in the selector order with Campaign last. Each Overview card, table row, CDF curve and map group is one combination, for example `EE · 2026-Q2`.

- **Operator** is always checked and disabled unless **Vendor** is checked; then uncheck it to pool the selected operators by vendor, or keep it to split each operator by vendor. eNodeBs and cells are counted per source operator, also when pooled.
- **Environment** splits into Cities, Towns, and Roads and railways, in that order.
- **Operator_Vendor**, **Vendor_Operator** and **Vendor** are the identities of the [Vendor Mapping](workspace-management.md#vendor-mapping) (the Vendor list: actual vendors, then Mixed, Other and All Vendor(s), then operators without a vendor as **Operator - All**); Operator_Vendor and Vendor_Operator stay in sync. **Cluster** follows Regions.
- **Curves:** those of one Operator (or Vendor) share its colour; campaigns differ by line width (the latest thickest, older ones progressively thinner, as in PPT Designer), and other secondary groups, such as Region or City, by line style.
- The change between the two latest campaigns appears only in an analysis of CDRs chosen by hand that hold several campaigns, when Campaign is not grouped.

### Theme

**Theme**, at the start of the floating section bar of the page, applies the themes of [Scoring & GAP Analysis](scoring-gap-analysis.md#choose-a-theme) (**Ericsson** by default; one theme per user and workspace, shared with the other themed modules and kept for the next visits and the exports; changes are recorded in App Events) to every chart and table of the page and of the PowerPoint and Word exports:

- the font and the colours of the text, axes and grid lines of the CDFs and maps, the headers and alternate rows of the tables, the quality classes and their scale (the best class in its best colour), the bands, the accents of the Key Findings and the primary bandwidth ladders;
- the style of the titles and subtitles of every content slide and of the Key Findings on the page;
- **Midnight**, the dark theme, gives dark result panels on the page and night-blue slides with dark tables, cards and charts in the exports.

Operators and networks keep the colours of the Operator Maps. A report of [Reporting](reporting.md#the-report-editor) gives its Network Insights section the theme of the report.

### LTE+NR

**LTE+NR** analyses each technology separately with its own thresholds, never pooled: Overview, RF Quality (two CDFs and a table per technology) and the Coverage and Interference Maps show an **LTE** section followed by an **NR** section. Each includes the samples with measurements of its technology; a sample with both counts once in each. Select LTE or NR to analyse one technology.

> [!TIP]
> **Speed.** The first analysis of a CDR reads its samples from its [columnar copy](workspace-management.md#columnar-copy-of-the-cdrs) in about a second; a CDR whose copy is not ready yet has its radio fields copied into the combined reporting tables first, which can take a minute. Later analyses of the same CDRs reuse the parsed samples, so changing filters, thresholds or the map Operator is fast. Repeating an analysis with the same CDRs and options returns the stored result at once, also after a restart (the newest 500 analyses are kept, from the page, the exports and the reports of **Reporting** alike); it is recalculated when the CDRs, inventories and their snapshot dates, Serving Networks, Operator Maps or Spectrum Holdings change. Stored results live in `.cache/network-insights` beside the workspace database and can be deleted at any time.

## Overview and RF Quality

The **Overview** shows one card per group with the median RSRP, the share of samples below the coverage threshold, the median SINR, the share below the interference threshold, the observed eNodeBs and the number of samples. With two or more campaigns (CDRs chosen by hand, see [Grouping](#grouping)) and Campaign not grouped, each indicator shows its change between the two latest campaigns: green when it improves, red when it worsens.

**RF Quality** contains:

- the RSRP and SINR cumulative distributions, one curve per group; as in CDR Analysis, the axis ends where the curves flatten, so a few extreme samples do not squeeze them;
- under each CDF, the P10, P50 and P90 of every group (the values below which 10%, 50% and 90% of its samples fall) as a band from P10 to P90 in its colour with the median marked, all groups on one scale;
- a table per group with median and 10th-percentile RSRP (dBm) and SINR (dB), the low-coverage and high-interference shares (with a bar each, the largest of the table full) and the quality-class distribution;
- **NR quality per carrier:** the NR samples of each group per NR band, with their share of the group, median SS-RSRP and SS-SINR and share in each quality class, so a carrier of lower quality stands out.

| Class | RSRP (dBm) | SINR (dB) |
| --- | --- | --- |
| Excellent | ≥ -80 | ≥ 20 |
| Good | -90 to -80 | 13 to 20 |
| Fair | -100 to -90 | 5 to 13 |
| Poor | -110 to -100 | 0 to 5 |
| Very poor / Bad | < -110 | < 0 |

Values outside physical ranges (RSRP outside -160 to -20 dBm, SINR outside -30 to 50 dB) are treated as missing.

## Key Findings

**Key Findings**, after the Overview, gives six benchmark views of the CDR Data tests, one value per test, each drawn as a slide: a bold title, a headline written from its figures in the accent of the theme, a pill naming the tests it covers (*Data · drive and walk*), its charts, the basis of its figures, a **What it means** box and a footnote with the tests, scope and Campaign. They compare the groups of the analysis without the environment (the Operators by default); with Campaign in Split by, the groups of the latest campaign. A group needs 10 tests for the headlines to name it.

| View | What it shows |
| --- | --- |
| **LTE signal at the test: RSRP and SINR** | Per environment (Cities, Towns, Roads and railways) and group, the share of the Data tests in each class of their LTE PCell RSRP (< −110, −110 to −100, −100 to −90, −90 to −80, ≥ −80 dBm) and SINR (≤ 0, 0 to 5, 5 to 10, 10 to 15, > 15 dB): the group with the weakest signal and the lowest SINR, and whether it is so in every environment. |
| **5G signal at the test: RSRP and quality (SINR)** | The same for the NR PCell of the tests with 5G, the group with the cleanest and the weakest 5G and the share of the tests of each group with 5G. |
| **Primary bandwidth: spread and narrow tests** | Per group, the P10, median and P90 of the primary bandwidth (4G and 5G together, see [Spectrum](#spectrum)) of the download tests, and their share under 40 MHz ranked from the fewest (the best colour of the scale) to the most. |
| **Technology in use** | Per test mode (Drive and Walk, from `G_Level_1`) and group, the share of the Data tests that used 5G at some point (NR time over zero, or an NR value or band logged) and of those on 4G only, with **Reading it**: how often the leading group used 5G and how much of each test's time was on 5G. |
| **Bands in use** | Per test mode and group, the main 4G band of the download tests (2600, 2600 TDD, 2100, 1800, 2300, 700–900 MHz or other, from the LTE PCell), and **5G on 3.5 GHz**: the share of the downloads with 5G whose main 5G carrier is n78 or n77, and the use of 2600 MHz TDD. |
| **Primary bandwidth** | One ladder per group of the classes of the primary bandwidth of its download tests (200+ to under 25 MHz, each block as wide as its class), the share at 100 MHz or more under it. |

Without download tests, the bandwidth and band views use every Data test. The exports draw each view as a slide of editable shapes (a view with more groups than fit continues on another slide).

## Export

**Export PowerPoint** and **Export Word**, beside Analyse Network, create a Summary Network Insights of the current selection in the colours of the chosen [Theme](#theme); the same summary is the Network Insights section of the reports of [Reporting](reporting.md). A progress dialog stays open while the document is prepared.

- **Contents**, each section on its own slide or page, in the order and layout of the page: the CDRs used, technology, grouping, thresholds and filters; the **Overview** cards of every group (with the campaign changes when two campaigns are compared); the [Key Findings](#key-findings) slides; the **Coverage & Interference Maps** of every group (not only the one shown, with their sector overlays), with the weakest coverage areas under the Coverage map, the highest interference areas under the Interference map and the cell status around them; **RF Quality**, with the RSRP CDF beside the SINR CDF and the table under them, and the NR quality per carrier; **Latency & Interactivity**; **Serving Cells** (the distance CDF with each group's summary under it, the breakdowns by band, vendor and host network, the overshooting cells, the NR cell of the NSA samples and MIMO); **5G Availability**; **Network Snapshot** (each network's snapshot, the owner × host network matrix and the inventory quality); **Network Deployment**, networks side by side, with every grouped view of the inventory snapshot (Host Network, RAN Vendor, Technology, Band, eMOCN Scenario, Site Type, Region, Subregion, Cluster and Status; in-service cells) whatever the dropdown shows, each table naming its snapshot date; **Cluster Sites Density** with both data sources whatever the dropdown shows; and **Spectrum** (observed, licensed and deployed spectrum, the NR sites by duplex mode of the selection's filters, the bandwidth per band, and the primary bandwidth chart on a slide titled *Primary bandwidth of each test: LTE + NR* with its explaining line under the title, its ladders per kind of serving site and per RAN Vendor and by location, followed by its figures; its ladders wrap onto more rows when there are many groups, so they show larger).
- **Not exported:** Observed Sites/Cells (from CDRs) and Full Sites/Cells Inventory; use their individual or combined CSV exports.
- **LTE+NR:** the overview, CDFs, maps and weakest areas appear once for LTE and once for NR.
- **Class bars:** the RF Quality and NR quality per carrier tables draw the RSRP and SINR classes of each row as coloured bars in the scale of the theme, with a legend under the table giving the colour and range of each class, also when the table continues on more slides.
- **Pills:** every slide, and every section of the Word document, names under its title the area, operators, vendors and Environments it shows.
- **Time:** charts and maps are rendered at full size, so the export takes longer than the on-screen analysis; its analysis is stored like the others, so exporting the same selection again does not analyse it again.
- **Look:** PowerPoint uses the Template_VodafoneThree.pptx master, cover and layouts of PPT Designer. Table widths follow their headers and values, with wider identity columns and single-line cells.
- **Composition:** both formats are composed as a report section of [Reporting](reporting.md#how-a-report-is-composed): a table spread over several slides becomes one (a long one continues in tables side by side, and on more slides when its values would be too small; a long RF Quality table keeps its first rows under the CDFs and continues on the next slides), small charts and tables share a slide, and Word holds them on portrait pages after the cover and a **Contents** page in its theme, exactly as in PowerPoint, a view that does not fit in what is left of a page starting the next one (rendered with LibreOffice; without it, one page per slide).
- **Kept:** exported documents are also kept in the `output/reports/network-insights/` folder of the workspace.

## Coverage and Interference Maps

The maps show one group at a time (selected in **Group**) over OpenStreetMap; with LTE+NR, the LTE and NR maps of that group are separate sections, each with its own thresholds. Samples are grouped into square grid cells of the selected size (drawn as one square each), coloured by their mean RSRP or SINR class; a cell needs at least three located samples. Very dense selections use a coarser grid automatically, and the note above the maps shows the grid used.

Every map, on the page and enlarged, navigates like a web map: drag, wheel, <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+drag to zoom into a rectangle, <kbd>Alt</kbd>/<kbd>Option</kbd>+drag to measure a distance and bearing, **−**, **+**, the zoom level and **Fit** at its top right, down to street level (OpenStreetMap level 19); see [Tips & shortcuts](#tips-shortcuts).

**Inventory sites.** With an inventory snapshot, the maps draw the sites of the networks that serve the group within 3 km of its weakest coverage and highest interference areas; from zoom level 12 a map loads the sites of the whole view of those networks (its own and those of the Serving Networks).

- **Sites and sectors:** on the whole area each site is a triangle in its vendor's colour (*Vendor sites* in the legend); zoomed in (from level 13), each cell is a translucent wedge under the grid squares pointing to its azimuth with its beamwidth (about 140 m long), and a cell without azimuth a circle.
- **Colours:** those of the **Vendor Maps** (by vendor name or alias); vendors without one use a palette outside the quality scale.
- **Rings:** solid for a site with cells Locked, Halted or Disabled, dashed for a site not on air yet or with cells Planned or In progress (see the cell status below).
- **Controls:** hover a site for its identifier, network, vendors and bands; the **Inventory sites** check of the map toolbar hides or shows them all, and a legend entry hides or shows that vendor's sites and sectors, that state's rings or that quality class.

**Weakest coverage areas** and **Highest interference areas**, below each map, rank the grid cells where at least half of the samples are below the threshold, by the number of affected samples. Select an area (its City) to zoom the map to it, and **Show Whole Area** to return.

**Cell status near the weak areas**, below the maps, lists the sites of the networks that serve the group, within 3 km of those areas, whose cells the inventory snapshot flags: **Locked**, **Halted** or **Disabled** (cells in service whose administrative, OSS or operational state says so) and **In progress** or **Planned** (not on air yet), with their bands, whether the site is on air, its nearest weak area and the distance; select a site to zoom the map to it. On the maps these sites carry their ring (*Locked, halted or disabled* and *Planned or in progress* in the legend), and their tooltip lists the flagged cells per state.

- The states are those of the snapshot (its date is in the note), not of the day of the measurements.
- Only some inventories give the administrative and operational state: about a third of the cells of the Cell Configuration packages, mostly Ericsson cells (the note shows the share). The other cells are only flagged by their OSS status (Locked, Halted) or a status In progress or Planned.

## Latency & Interactivity

**Latency & Interactivity** shows how the interactivity tests (CDR Data tests of type Interactivity, such as gaming and video chat) of every group went in each environment and in all of them: the share of **failed tests** (result not completed), the **round trip** as the median and the slowest tenth (P90) of the median round trip of each passed test (`Interactivity_RTT_Median`), the share of passed tests with **packet loss** and the median **jitter**. Each value is shaded by its rank among the groups of its environment, from the best (green) to the worst (red), and its rank is shown beside it in PowerPoint and Word.

## Serving Cells

After an analysis, each sample's first serving cell (from `LAC_CID_xARFCN` or `Cell_ID`; the NR cell of SA samples) is looked up in the [inventory snapshot](#network-snapshot) among the networks that serve its Operator, its own first, as set in [Serving Networks](workspace-config.md#serving-networks), within their maximum serving distance (30 km by default). Per analysis group, the panel shows:

- **Cards:** the share of samples whose serving cell was found, the median and P90 distance from the sample's start position to the serving site, the share of overshooting samples (served from farther than **Overshooting beyond (km)**) and the share served by cells another network hosts (shared Beacon sites, MORAN or eMOCN). A group whose serving networks have no cells in the snapshot (an operator without Network Inventory) shows **No inventory** and a note to upload its inventory in Workspace.
- **Distance CDFs:** per group and, beside it, per RAN vendor of the serving cell (all groups together, in the Vendor Maps colours), each with P10, P50 and P90 under it.
- **Breakdowns:** samples, median distance and overshooting share by serving band, RAN vendor, serving network (whose cell served the sample: the group's own or one that serves it, such as Three for Vodafone) and host network (that hosts the site).
- **Overshooting cells:** the cells that served most samples beyond the overshooting distance, with their site, band, vendor, owner → host network, samples beyond, samples served and median and maximum distance.
- **NR cell of the NSA samples:** NSA CDRs only identify the LTE anchor cell, so for the CDR Data samples anchored on LTE with an NR PCI (`NR_DL_PCell_PCI_Info_List`, the first one), the NR cell is the cell with that PCI whose band (`NR_DL_PCell_Band`) matches and whose carrier (inventory channel ± half its bandwidth) contains the sample's SSB frequency (`NR_DL_PCell_ARFCN`, the SSB rather than the carrier centre the inventories hold): on the anchor's site first, else the nearest of the networks that serve the Operator (the anchor's network first) within the maximum serving distance. Per group: the samples with an NR PCI, the share whose NR cell was found **On the anchor site**, as the **Only candidate nearby** or as the **Nearest of several** (ambiguous: other cells of that network with the same PCI and frequency are within the distance), the median and P90 distance to the NR site and the NR vendors, then **By NR vendor**.
- **MIMO: inventory TX antennas and reported rank:** per group, technology and TX antennas of the serving cell (the T of its TXRX mode, 4T4R, 64T64R…, mostly Huawei cells, or its number of used TX antennas, mostly Ericsson cells; **Not set** when the inventory gives neither): the samples, their mean rank and time per rank (`LTE_DL_Rank_Index`, `NR_DL_Rank_Index`), the share of time at rank 2 or more, the mean NR maximum MIMO layers (`NR_DL_Max_MIMO_Layers`) and **Rank use**, the mean rank divided by the TX antennas, at most 4 (the layers of the measuring device). LTE samples take their LTE cell; NR samples the NR cell of SA samples or the one found for NSA samples. Only CDR Data reports rank and layers.

## 5G Availability

Samples anchored on an LTE cell whose site also has NR cells in the snapshot should normally reach NR (EN-DC). The first table counts, per group, the samples on LTE cells, those on sites with NR, how many of them measured no NR (the **NR gap on 5G sites**) and the share without NR on the other sites; for the samples with an NR PCI (CDR Data) it adds the share whose NR cell was found (see [Serving Cells](#serving-cells)), the share served from the anchor's own site and the median distance to the NR site. The second table lists the 5G sites with most samples without NR; the third, the **NR sites serving the most NSA samples**, with their vendor, the share of their samples anchored on the same site, the median distance and the position. NR is measured from the NR RSRP of each sample, so only CDRs with NR measurements are meaningful (NSA Data, Voice and Speech).

## Network Snapshot

Every Network Inventory, the VFUK and 3UK files of earlier versions among them, is a snapshot of the network on its **Snapshot** date, with its cells normalised once into the **Inventory Cells** table (see [Network Inventories](workspace-management.md#network-inventories)). The panel loads without an analysis and shows:

- the **Snapshot in use:** the choice of Launch Analysis and the file and date each network takes (also as **Current snapshot** beside **Compare with**);
- one card per network in its Operator Maps colour, with the snapshot used (date and file), its sites, its LTE and NR cells (LTE in red and NR in green, as in every Technology column) and the networks it covers;
- the **Owner network × host network** matrix: the in-service cells and sites of each network carried by the equipment of each host network, the own network highlighted;
- the **Inventory quality** of each network: cells not in service, locked or disabled, without position, azimuth, band, vendor or site, and duplicate identities and their statuses;
- **Changes from another snapshot:** choose one in **Compare with** (the snapshots not in use) to count, for every network both describe, its cells now and then, in both, added and removed, and the cells and sites whose vendor changed, with the vendor swaps (Huawei → Ericsson) and the regions with most changes; cells match by technology and identity;
- every snapshot of the workspace with the networks it covers.

The **Inventory snapshot** of Launch Analysis changes Network Snapshot, Network Deployment, the density and the deployed spectrum at once; the serving-cell panels apply it at the next **Analyse Network**. Switching is immediate: when Network Insights opens, the newest snapshots and every single snapshot are prepared in the background and kept, with the prepared panels, in `.cache/network-insights` beside the workspace database, also after a restart, until the inventory changes. Only the very first preparation of a large inventory (a Cell Configuration package of half a million cells) takes a few seconds.

## Network Deployment

**View / Split by** chooses a grouped view, or the site tables.

**Grouped views** count the distinct sites and cells, LTE and NR, of each owner network of the inventory snapshot (one table per network: Vodafone, 3 and O2 from one Cell Configuration package, by the Network column of its cells) grouped by **Owner Network**, **Host Network** (whose equipment carries the cells), **RAN Vendor**, **Technology**, **Band**, **eMOCN Scenario** (S0, S1, NNS, S2…), **Site Type**, **Region**, **Subregion**, **Cluster**, **City**, **Urban/Rural**, **Performance Polygon**, **Status** or **MIMO (TX/RX)**.

- **Technology** (LTE + NR, LTE or NR) and **In service only** (checked by default: status In Service or empty) restrict the cells counted.
- **Region** and **Cluster** are the names of the imported polygons containing each cell (newest uploads first where they overlap, boundary points included), else the inventory's own Region and Cluster (Engineering Polygon) fields; values a cell lacks are **Not set**.
- They keep their inventory-wide scope; each table has **Export CSV**, and **Export All to CSV** combines every table with its Operator.

**Full Sites/Cells Inventory** shows the complete rows of the inventory of every network: the newest Network Inventory, whatever its format, or the **Inventory snapshot** of Launch Analysis for the networks it covers.

- **Tables:** one per network (the `Network` column of its rows, else the Operator of the file: Vodafone for VFUK and 3 for 3UK unless another is chosen in Workspace), side by side for the selected operators (stacked on narrow screens), each with its own pages of 50 rows (**Previous** / **Next**; horizontal scrolling reveals more columns). On the same date the 3UK file comes before the H3G rows of the VFUK one, and overlapping uploads of VFUK or of 3UK are read together.
- **Rows:** all uploaded inventory rows, whether or not their cells appear in the CDRs, so the tables work without CDRs; repeated rows stay intact, and operators without an uploaded inventory contribute none. Launch Analysis filters Operator, Vendor, Region, City and Technology against the inventory attributes (Region against imported polygon names when Region polygons exist); the CDRs used, NR Mode and Campaigns do not restrict them, as they describe measurements.
- **Highlighted columns:** the first seven, green: **Operator** (the workspace operator identity), **Operator_Vendor** and **Vendor** (from the mapping; inventories with the former Vendor_Only column keep working), **Region**, **Cluster**, **City** (from the mapping) and **Technology** (LTE/NR, from Technology/RAT, Vodafone's 4G/5G source sheets or Three's LTE ECI format).
  - Region and Cluster prefer imported polygon names from the site coordinates, falling back to the inventory fields only when that dimension has no polygons; unmatched locations stay empty. Their source aliases include Vodafone Region, Beacon2Town and Engineering Polygon, and Three UK "Regional", Town and Regional Optimisation Polygon; blank generic columns do not hide populated source attributes.
  - All original columns follow; source headers that collide with them take a `Source_` prefix. Fields missing in another operator's inventory are empty, and Source_Dataset_ID and Source_Dataset_Name identify each file, including several uploaded versions.

**Observed Sites/Cells (from CDRs)**, above Full Sites/Cells Inventory, lists the same per-operator tables from the CDR measurements: one row per observed site and LTE cell (Cell Identity; sites without a reported cell have an empty Cell_ID) with Operator, Vendor, Region, City, Cluster, Technology, Band, CDR types, Campaigns, Samples, mean coordinates and mean RSRP/SINR. They follow every choice of Launch Analysis, including the CDRs used, NR Mode, Campaigns and filters; building them for a new selection takes a few seconds, then the result is stored and reused.

**Filters and CSV of the site tables:**

- Every column header has a **▾** Excel-style filter: search its values (with their row counts under the other active filters), check those to keep (**(Blanks)** keeps empty cells) and **Apply**. Filtered columns are highlighted; **Clear N filters** removes them.
- Each table's **Export CSV** downloads all its matching rows and columns (the filtered rows only, not just the visible page), prepared completely before the download begins; **Export All to CSV** combines the tables in one file. Both use the selection that generated the tables.
- File names end with their operators: `_VF` for Vodafone, `_3` for Three, `_VF_3` for both, and other operators by their name (`site-cell-inventory_VF.csv`, `cdr-observed-sites-cells_3.csv`, `network-deployment-scenario_VF_3.csv`).

Deployment tables and the inventory index are stored in the workspace cache, so switching **View / Split by** is fast until an inventory changes. The per-dataset inventory downloads remain available for complete source exports. No additional persistent data is created; the dataset export, transfer and backup/restore workflows carry the inventories.

## Cluster Sites Density

The **Site density of the inventory snapshot** table counts, per owner network and Cluster (or Region without cluster polygons), its in-service sites and sites with NR, the polygon area (km², equal-area projection), the **sites per km²**, and the median and P90 **distance to the nearest site** of the same network (the inter-site distance). Without imported polygons the sites are grouped by the inventory's Cluster or Region field, without areas; a card then explains that density per km² needs **Clusters — Geospatial** or **Regions — Geospatial** polygons imported in Workspace. **Network Deployment** comes immediately before this panel.

The **Data source** dropdown chooses:

- **Observed Sites/Cells:** follows the CDRs used and the filters of Launch Analysis, counting per group the **observed eNodeBs** (distinct LTE eNodeB identities, Cell Identity ÷ 256, that served the devices) and **observed cells**, with the samples per eNodeB. An explanatory note says that observed eNodeBs depend on the route and do not equal the deployed sites. A yellow **Pending input** card lists the operators of the filtered analysis that no inventory snapshot serves (hidden when all are served or before an analysis).
- **Inventory Sites/Cells:** the inventories of Full Sites/Cells Inventory (the newest of every network, or the **Inventory snapshot** for the networks it covers): distinct sites and cells per operator, deduplicated across overlapping uploads, with inventory total cards, independent of the CDRs and filters.

## Spectrum

**Licensed spectrum** adds up the MHz of [Workspace Config → Spectrum Holdings](workspace-config.md#spectrum-holdings) per Operator into Low (below 1 GHz), Mid (1–3 GHz FDD/SDL) and High (TDD) bands; without holdings it shows a pending-input notice.

**Spectrum deployed in the inventory snapshot** lists, per owner network, technology and band, its in-service sites and cells, its **carriers** (distinct EARFCN/ARFCN channels, up to six shown; channel 0, a placeholder, is left out), the typical bandwidth and the **deployed MHz**: the width of the union of its carriers' frequency ranges (centre ± half the bandwidth), so the several NR-ARFCNs of one carrier and overlapping carriers count once.

**NR sites by duplex mode** counts, per owner network of the inventory snapshot, its in-service sites with NR cells: with **NR TDD** (n77, n78, n38, n40, n41 or n258; NR3400, NR3600 and NR3700 in UK inventories), with **NR FDD** (n1, n3, n7, n8, n20 or n28; NR2100, NR900 and NR700), with both and with only one.

- **Logical and physical sites:** logical sites are the site IDs of each network; sites of any network within 50 m of each other are one physical site, so a mast shared by several networks (MBNL, Beacon) counts once in the **All networks** row closing every table, which has TDD or FDD when any of its networks does. A line separates the logical and physical columns, each group headed by a bar (red for the physical sites).
- **Filters:** **Operators**, **Operator_Vendor**, **Vendors**, **Regions**, **Clusters** and **Cities** of Launch Analysis, matched against the inventory (owner network, vendor, the imported Region or Cluster polygon of the site, else its inventory field, and its inventory city); Campaigns, NR Mode and Environments describe measurements and do not restrict it.
- **Split by** shows the counts per Region, Cluster, City, RAN Vendor or Host Network, each area with its All networks row. It follows the Inventory snapshot and needs no analysis; operators without an inventory (EE in the UK) are named in its status line.

**Spectrum observed in the measurements** shows, per group, a bar for LTE and one for NR with the share of samples on each band (LTE from the serving EARFCN or the band of the cell trace), each band in a theme colour; the line under the bars opens the table of every band with its frequency, duplex mode, class, samples and most frequent downlink bandwidth (in the exports, a slide of bars before that table). Bandwidths are reported only by CDR Data. Observed bands follow the grouping: keep Operator checked to see each operator's bands.

**Tests**, below it, chooses the CDR Data tests of the bandwidth views: **Download tests** (DL in their name, such as FDTT HTTP DL MT; the default) or **All Data tests**. **Bandwidth**, beside it, chooses what the ladders and locations read: **Primary bandwidth (CDR)** (the default) or **Total bandwidth, every carrier (CA Appendix)**: every LTE and NR carrier of each test (`CA_Main_Total_Bandwidth_DL`), NR secondary carriers included, offered when some tests have a [CA Appendix](workspace-management.md#ca-appendix); the other tests then count as without a bandwidth.

- **Bandwidth per band:** per group, technology and serving band (with its duplex mode), the samples at each downlink bandwidth of the primary carrier (LTE PCell or NR PCell), their share of the band shaded, the samples without a bandwidth and the most frequent one. A bandwidth gets a column only where it holds at least 3% of the known samples of a band, or is its only bandwidth; the others are counted in **Other** (hover it for their bandwidths), also in the exports.
- **Primary bandwidth of each test: LTE + NR** adds each test's LTE bandwidth (its mean over the aggregated LTE carriers, `LTE_DL_Test_Bandwidth_Avg`, else its LTE PCell bandwidth, rounded up to 5 MHz as the Reporting field *LTE DL Aggregated BW (MHz)*) and its NR PCell bandwidth, in classes **200+**, **140–199**, **100–139**, **60–99**, **40–59**, **25–39** and **under 25 MHz**.
  - **The ladders:** one per group (the Split by fields other than Environment, as columns) and environment (Cities, Towns, and Roads and railways, as rows); each class is a block as wide as its midpoint and as tall as its share of the tests with a known bandwidth, widest at the bottom. The figure beside it, in the dark red of its block, is the share under 25 MHz; the label under it the share at 100 MHz or more (*93% at 100 MHz+*), bold for the largest of the environment. Hovering a block shows its share and tests.
  - **Title line:** in red under the title, a line explains the ladders and their number and names, per environment, the group with the largest share under 25 MHz (*Most under 25 MHz: Cities, 3 · 2026-Q3 (7%); Roads and railways, O2 · 2026-Q3 (37%)*).
  - **Left out:** tests reporting neither bandwidth, and those without an environment when others have one, counted under the chart; without environments every test is one row.
  - **Primary, not total:** the CDRs do not report the bandwidth of NR secondary carriers, so NR carrier aggregation (n78 with n28 in SA) is not added: the chart, its legend and the Key Findings call it the **primary bandwidth**.
- **Ladders per**, above the chart, chooses its columns: each **Group** (the default), each group and **kind of serving site** (the network owning the cell that served the start of the test and, when another network hosts it, *on* that network, NNS sites apart), or each group and **RAN Vendor of the serving cell**. Both use the serving cells of the [Vendor Mapping](workspace-management.md#vendor-mapping) and keep the combinations with 20 tests or more of a known bandwidth (up to 12).
- **Download tests by location:** per City (up to the 25 with most tests, each with 15 tests or more in some group) and group, the share of tests under 25 MHz and the share that failed or reached 5 Mbit/s or less, as shaded cells; a cell with few tests is hatched.
- **Carrier aggregation of the tests (CA Appendix):** for the tests of **Tests** that have a CA Appendix, per group. It shows what the tests used and complements the inventory snapshots, which it does not read:
  - **Carriers and bandwidth:** the share with 1, 2, 3, 4 and 5+ DL carriers, the mean carriers, the share with LTE CA and with NR CA, and the median total, LTE and NR bandwidth.
  - **Band combinations:** the eight used longest (`B7 + B8 + B1 + B3`, `n78 + B20`) with their tests and share.
  - **eNodeBs and gNodeBs observed:** per technology, the nodes, cells (channel and PCI), carriers per node, nodes with 2+ carriers and, per band, the share of nodes and the usual bandwidth (its channels on hover). Only tests that stayed on one node count.

## RF Quality template and Design

The **RF Quality (RSRP & SINR)** template and its NSA and SA Designs are [starter content](workspace-management.md#workspace-lifecycle) of every workspace; edit, rename or delete them like any other template or Design (a deleted copy is not recreated). The template contains:

- **All CDR types first:** each family (CDF/histograms, averages, classes, thresholds and maps) starts with an **All CDR types** slide that pools the valid Data, Voice and Speech observations per Operator and Campaign (it does not average the three type averages); the type-specific slides follow. LTE and NR stay separate, and missing technologies add no samples.
- **CDFs:** RSRP and SINR CDFs (LTE and NR) for Data, Voice and Speech with contour histograms underneath in a two-by-two layout: 5 dB RSRP and 1 dB SINR bins, percentages normalized per Operator and Campaign, CDF colours and campaign line widths (newer campaigns thicker; multivendor operator comparisons keep their line patterns).
- **Histogram slides** follow each CDF/contour slide for All CDR types, Data, Voice and Speech: the `Title + 2 rows + dynamic columns + comments down` layout with `Dynamic Columns Field = Operator` gives one column per selected Operator, LTE above NR, comments beneath. Every bin has one bar per Campaign, oldest to newest: the newest in the Operator colour, older ones in progressively lighter shades, with the denominator and bins of the contour histograms.
- average LTE and NR RSRP and SINR bars per CDR type;
- LTE and NR RSRP distributions in -110/-100/-90/-80 dBm buckets and SINR in 0/5/13/20 dB buckets, with red-to-green class colours matching the histogram background bands;
- LTE and NR shares of samples below -110 dBm and below 0 dB, from the valid measurements of each technology;
- LTE and NR coverage (RSRP) and quality (SINR) maps for Data, Voice and Speech, red to green with the same ranges, combining the measured samples of the selected Operator, Campaign and geographical filters rather than estimating unmeasured coverage;
- the black-logo closing slide of the NetCheck template.

> [!IMPORTANT]
> NSA uses an LTE anchor and can also provide NR radio measurements. Each chart reads its technology-specific CDR field. NR percentages describe the available valid NR measurements; missing NR values do not count as good coverage or establish NR availability along the entire route. SINR reflects signal quality against both interference and noise.

## Data sources

| Field | CDR Data | CDR Voice (A side) | CDR Speech |
| --- | --- | --- | --- |
| LTE RSRP / SINR | `LTE_PCell_RSRP_Avg`, `LTE_PCell_SINR_Avg` | `4G_RSRP_Avg_A`, `4G_SINR_Avg_A` | `Playing_RSRP_Avg`, `Playing_SINR_Avg` |
| NR RSRP / SINR | `NR_PCell_RSRP_Avg`, `NR_PCell_SINR_Avg` | `NR_RSRP_Avg_A`, `NR_SINR_Avg_A` | `Playing_RSRP_NR_Avg`, `Playing_SINR_NR_Avg` |
| Location | `Test_Start_Latitude/Longitude` | `Call_Start_Latitude/Longitude_A` | `Playing_Latitude/Longitude` |
| Serving cells | `LAC_CID_xARFCN`, `Cell_ID` | `LAC_CID_xARFCN_A`, `Cell_ID_A` | `Cell_IDs_A`, `Playing_eNodeBId` |
| Bands | `LTE_PCC_EARFCN`, `NR_DL_PCell_Band` | `E/U/ARFCN_A`, `NR_BAND_A` | `ARFCN_A` |
| NR cell of NSA samples | `NR_DL_PCell_PCI_Info_List`, `NR_DL_PCell_ARFCN`, `NR_DL_PCell_Band` | — | — |
| Rank and MIMO layers | `LTE_DL_Rank_Index`, `NR_DL_Rank_Index`, `NR_DL_Max_MIMO_Layers` | — | — |
| Bandwidths | `LTE_DL_PCell_Bandwidth`, `LTE_DL_Test_Bandwidth_Avg`, `NR_DL_PCell_Bandwidth` | — | — |
| Download tests | `Test_Name` | — | — |
| Test result and speed (download tests by location) | `Test_Result`, `Mean_Data_Rate` | — | — |
| Latency & Interactivity | `Type_of_Test`, `Test_Result`, `Interactivity_RTT_Median`, `Packets_Lost`, `Packets_Sent`, `Packet_Delay_Variation_Median` | — | — |
| Serving cell (Ladders per kind of site or RAN Vendor) | `Vendor`, `Serving_Network`, `Serving_Host_Network`, `Serving_eMOCN_Scenario` | — | — |
| Environment | `G_Level_3`, else `G_Level_2` | `G_Level_3`, else `G_Level_2` | `G_Level_3`, else `G_Level_2` |
| Test mode (Key Findings: Drive or Walk) | `G_Level_1` | — | — |
| Time on 5G (Key Findings: Technology in use) | `NR_Total_Time`, `Test_Duration` | — | — |

Speech falls back to the `Recording_*` fields when the `Playing_*` fields are absent. Region and City use `Region`/`City`, or `G_Level_2`/`G_Level_4`.

## Pending inputs

| Input | Used by | How to provide it |
| --- | --- | --- |
| Inventory of every network | Serving Cells, 5G Availability, Network Snapshot, Network Deployment, Cluster Sites Density, Spectrum | Upload Network Inventories (CSV, Excel or Cell Configuration KMZ/KML/ZIP) in Workspace and date their snapshots. A [Multivendor Mapping](workspace-management.md#multivendor-mappings) only gives the Vendor of the CDRs: these panels do not read it |
| Cluster or region polygons | Cluster Sites Density (sites per km²), Network Deployment (Region and Cluster) | Upload GeoJSON, JSON or a zipped shapefile as Clusters — Geospatial or Regions — Geospatial in Workspace |
| Serving Networks | Serving Cells, 5G Availability and the Vendor mapping | [Workspace Config → Serving Networks](workspace-config.md#serving-networks); the defaults cover Vodafone, 3 and Lebara |
| Licensed spectrum per Operator | Spectrum | [Workspace Config → Spectrum Holdings](workspace-config.md#spectrum-holdings) |
| Carrier aggregation and total bandwidth of each test | Spectrum (Bandwidth: CA Appendix, Carrier aggregation of the tests) | Upload the quarterly [CA Appendix](workspace-management.md#ca-appendix) of NetCheck in Workspace |
| NNS site list, if it differs from the inventory eMOCN Scenario | Network Deployment | Include it in the uploaded inventory |

## Persistence and transfers

Analyses are calculated on demand. Spectrum Holdings and Serving Networks belong to the workspace and travel with the **Mappings & Reference Data** export, transfers and backups; the inventory snapshots travel with their datasets, and their Inventory Cells are rebuilt from them when needed. Workspace templates and Designs travel with Report Templates and Designs.

Network Insights remembers in this browser, per workspace and user, the selected CDRs, NR Mode, Technology, grouping, filters, thresholds, map grid, inventory snapshot, overshooting distance, deployment grouping and technology, the Split by of the NR sites by duplex mode and the Tests of the bandwidth views; unavailable CDRs or values are omitted when restored. These preferences are not in workspace exports or backups (the [Theme](#theme) is kept by the workspace for each user instead).

Opening or reloading the page, also after a restart, restores the selection of the last analysis and shows that analysis again at once from the stored results; when its result is no longer valid (its CDRs or inputs changed, or an application update changed the results), it runs again by itself. Reloading keeps the scroll position. Once the selection changes, press **Analyse Network**.

## Troubleshooting

- **No ready CDRs** in a CDR list: check the NR Mode and that the CDRs finished processing.
- **No samples match**: clear the Operator, Vendor, Region, City or Campaign restriction.
- **A map is empty**: the selected CDRs carry no coordinates or no values for the selected Technology; the status line says which.
- **NR curves are empty**: NSA CDRs report NR values only while the device is attached to NR; check the NR RSRP samples column in the RF Quality table.
- **The Licensed spectrum panel shows Pending input**: add Spectrum Holdings in Workspace Config.

## Tips & shortcuts

The maps and charts of the page react to the mouse and the keyboard as below. The shortcuts that work everywhere are in [Web Interfaces](web-interface.md#tips-shortcuts).

**Maps** (on the page and in the larger view)

| To… | Do this |
| --- | --- |
| Move the map | Drag it, also with the middle mouse button |
| Zoom in or out | Mouse wheel, towards the pointer; or **−** / **+** at its top right (**Fit** shows the whole area) |
| Zoom into an area | Hold <kbd>Ctrl</kbd>/<kbd>⌘</kbd> (the pointer turns into a crosshair) and drag a rectangle |
| Measure a distance and its bearing from north | Hold <kbd>Alt</kbd>/<kbd>Option</kbd> (the pointer turns into a ruler) and drag between two places; the line stays on the map, moving with it |
| Clear the measured line | <kbd>Esc</kbd>, or click the map |
| Open the map larger | Double-click it |
| Zoom in ×2 in the larger map | Double-click it |
| Hide or show the sites of a vendor, a ring or a quality class | Click its entry in the legend |
| Go to a weak area or a flagged site | Select its row in the table below the map; **Show Whole Area** goes back |

**Charts and tables**

| To… | Do this |
| --- | --- |
| Open a chart or table larger | Double-click it |
| Hide or show a series | Click its entry in the legend; click it again to show it |
| Zoom into part of a chart | Hover it to show its zoom controls (−, +, the zoom level and **1:1** to reset), as in PPT Designer, and drag a rectangle over its plot area; once zoomed, drag or use the arrows to pan |
| Read a value | Hover a point, bar or curve |
| Save or copy a picture | Hover the chart, map or table and use the buttons at its top right corner |
