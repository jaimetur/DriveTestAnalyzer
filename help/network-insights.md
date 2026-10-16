# Network Insights

Analyse the network behind the measured performance: radio quality (RSRP and SINR), weak-coverage and high-interference areas on a map, the cells that served the samples (their distance, overshooting and hosting network), 5G availability on the sites with NR, the inventory snapshot of every network (owner and host networks, data quality), site density, licensed, deployed and observed spectrum (the sites with NR TDD and NR FDD, the bandwidth of every band and the total bandwidth of the tests), and network deployment (NNS, eMOCN scenarios, host networks and RAN vendors). Results are split by the dimensions checked in **Split by**; Operator and Campaign are checked by default.

Every panel opens with the question it answers, and its notes explain how to read it. As in Scoring & GAP Analysis, the title of every chart and table ends with pills naming what it shows: its area (the City, Cluster or Region filters, the most specific first, else **National**), its operators (**All Operators** without an Operator filter), its vendors (**All Vendors** without a Vendor filter) and, when they are chosen, its Environments; a list of over three names shows two and how many more, and hovering a pill lists them all. The measurement panels name the filters of the analysis shown, the NR sites by duplex mode and the site tables of Network Deployment the filters of their own selection (without Environments, which describe the measurements), and the panels of the whole inventory (Network Snapshot, the grouped Network Deployment views, the inventory density and the licensed and deployed spectrum) National, All Operators and All Vendors. A chart or table without a title of its own has them in a line above it, and its larger view shows them beside its title. Operators and networks appear everywhere in the order and colours of the workspace **Operator Maps**. Tables with many rows scroll inside their frame under a fixed header. Double-click any chart, map or table to open it larger, filling the screen but a narrow margin: charts and maps are drawn again with their zoom controls, and tables show every row.

> [!NOTE]
> **Radio views need no extra input.** RSRP, SINR, maps, observed eNodeBs and observed bands come from the processed CDRs. The inventories (Multivendor Mappings and Network Inventories, Cell Configuration KMZ packages included) and the licensed spectrum are optional inputs that complete the Serving Cells, 5G Availability, Network Snapshot, Network Deployment, Cluster Sites Density and Spectrum panels.

## Choose your task

| I want to… | Go to |
| --- | --- |
| Run an analysis | [Analysis Selection](#analysis-selection) |
| Compare coverage and interference per Operator | [Overview and RF Quality](#overview-and-rf-quality) |
| Locate weak-coverage or high-interference areas | [Coverage and Interference Maps](#coverage-and-interference-maps) |
| Count sites and eNodeBs | [Cluster Sites Density](#cluster-sites-density) |
| Compare Low, Mid and High (TDD) spectrum | [Spectrum](#spectrum) |
| Count the sites with NR TDD and NR FDD, logical and physical | [Spectrum](#spectrum) |
| Compare the bandwidth of each band and the total bandwidth (LTE + 5G) of the tests in Cities, Towns, and Roads and railways | [Spectrum](#spectrum) |
| Measure the distance to the serving sites and find overshooting cells | [Serving Cells](#serving-cells) |
| Find 5G sites whose samples get no NR | [5G Availability](#5g-availability) |
| Find the NR cell of NSA samples or compare the MIMO of the cells with the reported rank | [Serving Cells](#serving-cells) |
| Check locked, halted, disabled or planned cells near the weak areas | [Coverage and Interference Maps](#coverage-and-interference-maps) |
| Compare inventory snapshots, host networks and inventory quality | [Network Snapshot](#network-snapshot) |
| Count NNS, eMOCN or shared sites | [Network Deployment](#network-deployment) |
| Present RSRP and SINR slides in a Dashboard | [RF Quality template and Dashboard](#rf-quality-template-and-dashboard) |
| Check which CDR fields are used | [Data sources](#data-sources) |
| Know which inputs are still missing | [Pending inputs](#pending-inputs) |
| Export the analysis to PowerPoint or Word | [Export](#export) |
| View and export complete site/cell inventories or deployment counts as CSV | [Network Deployment](#network-deployment) |

## Analysis Selection

1. Open the workspace and the **Network Insights** tab, which follows **Scoring & GAP Analysis**.
2. Choose **NR Mode** and, first among the **Filters**, the **Campaigns**: they choose the CDRs of the analysis, the Data, Voice and Speech CDRs of that NR Mode that the combined CDR tables include for those campaigns (every campaign when none is restricted): the Final CDR of a campaign before its Weekly and Daily CDRs, or the **In Combined?** choice of Workspace (see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)). Campaigns offers first **Latest campaign**, **Previous campaign** (the one before it), **Latest 2 campaigns** and **All available campaigns**: the newest campaigns, the one before the newest, or every campaign, of the NR Mode each time the analysis runs (also those that arrive later); each one stands alone (checking it clears the other one and the campaigns, checking a campaign clears it), and **Select All / None** checks or clears the campaigns only. **CDRs used**, below the Filters, lists them by type with their stage and campaigns and follows every change of the filters at once.
3. Restrict **Operators**, **Vendors**, **Regions**, **Clusters**, **Cities** or **Environments** in **Filters** if needed. **Environments** groups where the tests ran, from the `G_Level_3` field of the CDRs (else `G_Level_2`): big cities, driven and walked, are **Cities**; medium and small cities are **Towns**; connecting roads, highways and train routes are **Roads and railways**. Every filter lists the values of every CDR of the NR Mode, with the labels of the Operator, Vendor and Campaign Maps, and only those the other filters leave (choosing Three as Operator leaves in Vendors only the Vendors of Three); its own choice does not narrow its list, and an open list stays open while values are checked. **Main Cities** appears first in Cities when configured. Leaving every value selected, or none, applies no restriction. The lists come from the combinations of values each CDR keeps (the **CDR Filter Facets** table), so they never read the rows of the CDRs.
4. The controls above the Filters come in three groups: **Scope**, **Thresholds** and **Maps & inventory**. In Scope, choose **Technology** (LTE, NR or LTE+NR) and **Split by** (Operator, Vendor, Region, Cluster, City, Environment, CDR type and Campaign).
5. In Thresholds, adjust the thresholds of the selected technology; in Maps & inventory, the **Map grid** size (default 250 m). LTE and NR have their own thresholds because LTE RSRP/SINR and NR SS-RSRP/SS-SINR use different reference signals; LTE+NR shows both pairs.

| Threshold | LTE default | NR default |
| --- | --- | --- |
| Coverage below (low coverage) | -110 dBm | -115 dBm |
| Interference below (high interference) | 0 dB | -3 dB |

   Choose the **Inventory snapshot** in Maps & inventory: **Newest of each network** (the default) or one snapshot, used for the networks it covers (the newest one for the others); see [Network Snapshot](#network-snapshot). **Overshooting beyond (km)**, 5 km by default, sets the distance from which a sample counts as overshooting in [Serving Cells](#serving-cells).
6. Press **Analyse Network**. A dialog shows that the analysis is in progress, with the elapsed time, and closes when the results are ready; **Hide** closes it while the analysis continues.

### Grouping

**Split by** accepts several dimensions; they form a hierarchy in the selector order, with Campaign last. Each Overview card, table row, CDF curve and map group is one combination, for example `EE · 2026-Q2`.

- **Operator** is always checked and disabled unless **Vendor** is checked. With Vendor checked, Operator becomes selectable: uncheck it to pool the selected operators by vendor, or keep it to split each operator by vendor.
- **Environment** splits the groups into Cities, Towns, and Roads and railways, in that order (see the Environments filter).
- **Operator_Vendor** uses the `<Operator>_<Vendor>` identity, **Vendor_Operator** the same identity as `<Vendor>_<Operator>` and **Vendor** the vendor alone: actual vendors, then Mixed, Other and All Vendor(s), then operators without a mapped vendor as **Operator - All**. **Operator_Vendor** and **Vendor_Operator** stay in sync: selecting values in one selects the same identities in the other. **Cluster** follows Regions and is also available in **Split by**.
- Curves of the same Operator (or Vendor) share its colour. Campaigns differ by line width: the latest campaign is the thickest and older campaigns are progressively thinner, as in PPT Dashboards. Other secondary groups, such as Region or City, use a different line style.
- The change between the two latest campaigns appears only when Campaign is not a grouping dimension.
- eNodeBs and cells are counted per source operator, also when operators are pooled.

### LTE+NR

**LTE+NR** analyses each technology separately with its own thresholds, so LTE and NR are never pooled: Overview, RF Quality (two CDFs and a table per technology) and the Coverage and Interference Maps show an **LTE** section followed by an **NR** section. Each section includes the samples with measurements of its technology; a sample with both contributes once to each. Select LTE or NR to analyse one technology.

> [!TIP]
> The first analysis of a CDR copies its radio fields into the combined reporting tables and can take a minute. Later analyses of the same CDRs reuse them and the parsed samples, so changing filters, thresholds or the map Operator is fast. Repeating an analysis with the same CDRs and options returns the stored result immediately, also after a restart; it is recalculated when the CDRs, inventories and their snapshot dates, Serving Networks, Operator Maps or Spectrum Holdings change. Stored results live in `.network-insights-cache` beside the workspace database and can be deleted at any time.

Operator names follow the workspace **Operator Maps**, including their colours; rows from ignored CDR sheets are excluded.

## Overview and RF Quality

The **Overview** shows one card per group with the median RSRP, the share of samples below the coverage threshold, the median SINR, the share of samples below the interference threshold, the observed eNodeBs and the number of samples. When the selection contains two or more campaigns and Campaign is not grouped, each indicator shows its change between the two latest campaigns: green when the indicator improves and red when it worsens.

**RF Quality** contains:

- the RSRP and SINR cumulative distributions, one curve per group, coloured by Operator with a line style per secondary group; as in CDR Analysis, the axis ends where the curves flatten, so a few extreme samples do not squeeze them;
- under each CDF, the P10, P50 and P90 of every group (the values below which 10%, 50% and 90% of its samples fall);
- a table per group with median and 10th-percentile RSRP (dBm) and SINR (dB), the low-coverage and high-interference shares and the quality-class distribution.

| Class | RSRP (dBm) | SINR (dB) |
| --- | --- | --- |
| Excellent | ≥ -80 | ≥ 20 |
| Good | -90 to -80 | 13 to 20 |
| Fair | -100 to -90 | 5 to 13 |
| Poor | -110 to -100 | 0 to 5 |
| Very poor / Bad | < -110 | < 0 |

Values outside physical ranges (RSRP outside -160 to -20 dBm, SINR outside -30 to 50 dB) are treated as missing.

## Export

**Export PowerPoint** and **Export Word**, beside Analyse Network, create a Summary Network Insights of the current selection: the CDRs used, technology, grouping, thresholds and filters, the overview cards with campaign deltas, RSRP and SINR CDFs, coverage and interference maps with their weakest areas and the cell status around them, the Serving Cells and 5G Availability tables (with the NR cell of the NSA samples and MIMO), observed and licensed spectrum, the NR sites by duplex mode, the bandwidth per band and the total bandwidth (LTE + 5G) of the download tests with its stepped chart, both Cluster Sites Density data sources and network deployment. Every slide, and every section of the Word document, names under its title the area, operators, vendors and Environments it shows, as the pills of the page. Charts and maps are rendered at full size, so the export takes longer than the on-screen analysis. PowerPoint uses the same Template_01.pptx master, cover and layouts as PPT Dashboards. Table widths follow their headers and values, with wider identity columns and single-line cells; Word uses horizontal pages, increasing their width for wide tables, fixed column widths and repeating single-line headers. Exported documents are also kept in the `output/reports/network-insights/` folder of the workspace.

Both formats include the grouped Network Deployment views of the inventory snapshot by Host Network, RAN Vendor, Technology, Band, eMOCN Scenario, Site Type, Region, Subregion, Cluster and Status (in-service cells), irrespective of the currently displayed dropdown option. Observed Sites/Cells (from CDRs) and Full Sites/Cells Inventory are excluded from PowerPoint and Word; use their individual or combined CSV exports. Both formats follow the order and layout of the page, each section on its own slide or page: the **Overview** cards of every group (with the campaign changes when two campaigns are compared), the **Coverage & Interference Maps** of every group (not only the one shown on the page, with their sector overlays) with the weakest coverage areas under the Coverage map and the highest interference areas under the Interference map, **RF Quality** with the RSRP CDF beside the SINR CDF and the table with the RSRP and SINR class bars under them, **Serving Cells** (the distance CDF with the summary of each group under it, the breakdowns by band, vendor and host network, and the overshooting cells), **5G Availability**, **Network Snapshot** (the snapshot of each network, the owner × host network matrix and the inventory quality), **Network Deployment** with the networks side by side, **Cluster Sites Density** (with the density of the inventory snapshot) and **Spectrum** (with the deployed spectrum, the NR sites by duplex mode of the selection's filters, the bandwidth per band and the total bandwidth chart on a slide titled *Total bandwidth: LTE and 5G together*, with the line that explains the ladders under the title, followed by its figures). A progress dialog stays open while the document is prepared. With LTE+NR, the overview, CDFs, maps and weakest areas appear once for LTE and once for NR. The same summary is available as a [Reporting](reporting.md) artifact.

## Coverage and Interference Maps

The maps show one group at a time (selected in **Group**) over OpenStreetMap; with LTE+NR, the LTE and NR maps of that group appear in separate sections, each classified with its own thresholds. Samples are grouped into square grid cells of the selected size, and each cell is coloured by its mean RSRP or SINR class. Cells need at least three located samples. Very dense selections use a coarser grid automatically to keep the map readable; the note above the maps shows the grid actually used.

With an inventory snapshot, the maps also draw the sites of the networks that serve the group within 3 km of its weakest coverage and highest interference areas: on the whole area each site is a triangle in the colour of its vendor (listed in the legend as *Vendor sites*), and zooming to an area draws one translucent wedge per cell under the grid squares, pointing to its azimuth with its beamwidth (about 140 m long), and cells without an azimuth as a circle. The sites take the vendor colours of the **Vendor Maps** in Workspace Config (by vendor name or alias); vendors without one use a palette outside the quality scale. A solid ring marks a site with cells Locked, Halted or Disabled, and a dashed ring a site not on air yet or with cells Planned or In progress (see Cell states near the weak areas). Hover over a site to see its identifier, network, vendors and bands; the **Inventory sites** check of the map toolbar hides or shows them all, and clicking an entry of the legend hides or shows that vendor's sites and sectors, that state's rings or that quality class.

The samples are drawn as squares, one per grid square. Every map, on the page and enlarged, navigates like a web map: dragging moves it, the mouse wheel zooms towards the pointer down to street level (OpenStreetMap level 19), Ctrl/Cmd+drag draws a rectangle to zoom into (the pointer turns into a crosshair while Ctrl/Cmd is held), Alt/Opt+drag measures the distance between two places, with its bearing from north (the pointer turns into a ruler; the line stays on the map, moving with it, until a click or Escape), and **−**, **+**, the zoom level and **Fit** sit at its top right. A double-click opens a map larger, where a double-click zooms in. From zoom level 12 a map loads the inventory sites of the whole view, not only those around the weakest areas, of the networks that serve the group (its own and those of the Serving Networks); from level 13 they are drawn as sectors.

Below each map, the **Weakest coverage areas** and **Highest interference areas** tables rank the cells where at least half of the samples are below the threshold, by the number of affected samples. Select an area (its City) to zoom the map to it, and **Show Whole Area** to return. Hover over a CDF or map to show its zoom controls (−, +, the zoom level and 1:1 to reset), as in PPT Dashboards; drag a rectangle to magnify an area, then drag or use the arrows to pan.

Below the maps, **Cell status near the weak areas** lists the sites of the networks that serve the group, within 3 km of those areas, whose cells the inventory snapshot flags: **Locked**, **Halted** or **Disabled** (cells in service whose administrative, OSS or operational state says so) and **In progress** or **Planned** (cells not on air yet), with their bands, whether the site is already on air, its nearest weak area and the distance; select a site to zoom the map to it. On the maps these sites carry a ring, dashed when they are not on air yet or have planned or in-progress cells (in the legend as *Locked, halted or disabled* and *Planned or in progress*), and their tooltip lists the flagged cells per state. The states are those of the snapshot (its date is in the note), not of the day of the measurements, and only some inventories give the administrative and operational state: about a third of the cells of the Cell Configuration packages, mostly Ericsson cells (the note shows the share). The other cells are only flagged by their OSS status (Locked, Halted) or when their status is In progress or Planned.

## Serving Cells

After an analysis, each sample's first serving cell (from `LAC_CID_xARFCN` or `Cell_ID`; the NR cell of SA samples) is looked up in the [inventory snapshot](#network-snapshot) among the networks that serve its Operator ([Workspace Config → Serving Networks](workspace-config.md#serving-networks): its own network first, by default Vodafone and Three for each other and both for Lebara). A cell farther than the maximum serving distance (30 km by default) is not taken as the sample's serving cell. The panel shows, per analysis group:

- cards with the share of samples whose serving cell was found, the median and P90 distance from the sample's start position to the serving site, the share of overshooting samples (served from farther than **Overshooting beyond (km)**) and the share served by cells hosted by another network (shared Beacon sites, MORAN or eMOCN). A group whose serving networks have no cells in the snapshot (for example an operator without Network Inventory) shows **No inventory** on its card and a note to upload its inventory in Workspace;
- the cumulative distribution of the distance to the serving site per group and, beside it, per RAN vendor of the serving cell (every group together, in the Vendor Maps colours), each with the P10, P50 and P90 under it;
- the samples, median distance and overshooting share by serving band, RAN vendor, serving network (the network whose cell served the sample: the group's own or one that serves it, for example Three for Vodafone) and host network (the network that hosts the site);
- the **Overshooting cells**: the cells that served the most samples beyond the overshooting distance, with their site, band, vendor, owner → host network, samples beyond, samples served and median and maximum distance;
- the **NR cell of the NSA samples**: NSA CDRs only identify the LTE anchor cell, so for the CDR Data samples anchored on LTE with an NR PCI (`NR_DL_PCell_PCI_Info_List`, the first one) the NR cell is the cell with that PCI whose band (`NR_DL_PCell_Band`) matches and whose carrier (inventory channel ± half its bandwidth) contains the sample's SSB frequency (`NR_DL_PCell_ARFCN`, the SSB rather than the carrier centre the inventories hold): on the anchor's site first, otherwise the nearest one of the networks that serve the Operator, the anchor's network first, within the maximum serving distance. Per group, the table shows the samples with an NR PCI, the share whose NR cell was found **On the anchor site**, as the **Only candidate nearby** or as the **Nearest of several** (ambiguous: other cells of that network with the same PCI and frequency are within the distance), the median and P90 distance to the NR site and the NR vendors, followed by the breakdown **By NR vendor**;
- **MIMO: inventory TX antennas and reported rank**: per group, technology and TX antennas of the cell that served the samples — the T of its TXRX mode (4T4R, 64T64R…, mostly Huawei cells) or its number of used TX antennas (mostly Ericsson cells), **Not set** when the inventory gives neither — the samples, their mean rank and time per rank (`LTE_DL_Rank_Index`, `NR_DL_Rank_Index`), the share of time at rank 2 or more, the mean NR maximum MIMO layers (`NR_DL_Max_MIMO_Layers`) and the **Rank use**: the mean rank divided by the TX antennas, at most 4 (the layers of the measuring device). LTE samples take their LTE cell; NR samples the NR cell of SA samples or the one found for NSA samples. Only CDR Data reports rank and layers.

## 5G Availability

Samples anchored on an LTE cell whose site also has NR cells in the snapshot should normally reach NR (EN-DC). The table counts, per analysis group, the samples on LTE cells, those on sites with NR, how many of them measured no NR and that **NR gap on 5G sites**, beside the share without NR on the other sites. The second table lists the 5G sites with the most samples without NR. NR is measured from the NR RSRP of each sample, so only CDRs with NR measurements are meaningful (NSA Data, Voice and Speech).

For the samples that measured NR with an NR PCI (CDR Data), the first table also shows the share whose NR cell was found (see [Serving Cells](#serving-cells)), the share served from the anchor's own site and the median distance to the NR site; the third table lists the **NR sites serving the most NSA samples**, with their vendor, the share of their samples anchored on the same site, the median distance and the position.

## Network Snapshot

Every Multivendor Mapping and Network Inventory is a snapshot of the network on its **Snapshot** date (see [Network Inventories](workspace-management.md#network-inventories)), with its cells normalised once into the **Inventory Cells** table. The panel loads without an analysis and shows:

- the **Snapshot in use**: the choice of the Analysis Selection and the file and date each network takes (also shown as **Current snapshot** beside **Compare with**);
- one card per network in its Operator Maps colour, with the snapshot used (its date and file), its sites, its LTE and NR cells (LTE in red and NR in green, as in every Technology column) and the networks it covers;
- the **Owner network × host network** matrix: the in-service cells and sites of each network carried by the equipment of each host network, with the own network highlighted;
- the **Inventory quality** of each network: cells not in service, locked or disabled, without position, azimuth, band, vendor or site, duplicate identities and their statuses;
- **Changes from another snapshot**: choose a snapshot in **Compare with** (which lists the snapshots not in use) to count, for every network both describe, its cells now and then, the cells in both, added and removed, and the cells and sites whose vendor changed, with the vendor swaps (for example Huawei → Ericsson) and the regions with the most changes; cells are matched by technology and identity;
- every snapshot of the workspace with the networks it covers.

The **Inventory snapshot** of the Analysis Selection changes the snapshot of Network Snapshot, Network Deployment, the density and the deployed spectrum at once; the serving-cell panels apply it at the next **Analyse Network**. Switching snapshots is immediate: when Network Insights opens, the newest snapshots and every single snapshot are prepared in the background, and the cells of every snapshot and the prepared panels are kept in `.network-insights-cache` beside the workspace database, also after a restart, until the inventory changes. Only the very first preparation of a large inventory (a Cell Configuration package of half a million cells, for example) takes a few seconds.

## Network Deployment

The grouped views count the distinct sites and cells of each owner network in the inventory snapshot (one table per network: for example Vodafone, 3 and O2 from one Cell Configuration package, whose cells belong to the network of their Network column) grouped by **Owner Network**, **Host Network** (whose equipment carries the cells), **RAN Vendor**, **Technology**, **Band**, **eMOCN Scenario** (for example S0, S1, NNS or S2), **Site Type**, **Region**, **Subregion**, **Cluster**, **City**, **Urban/Rural**, **Performance Polygon**, **Status** or **MIMO (TX/RX)**, with their LTE and NR cells. **Technology** (LTE + NR, LTE or NR) and **In service only** (checked by default: the cells whose status is In Service or empty) restrict the counted cells. **Region** and **Cluster** use the names of the imported polygons containing each cell (newest uploads first where they overlap, boundary points included), and the inventory's own Region and Cluster (Engineering Polygon) fields without polygons; values a cell lacks are **Not set**. Each table has an **Export CSV** button with its rows, and **Export All to CSV** combines every table with its Operator.

Choose **Full Sites/Cells Inventory** in **View / Split by** to see separate Vodafone and Three tables side by side for the selected operators, each with its own pages of 50 rows (stacked on narrow screens). The first seven columns — **Operator**, **Operator_Vendor**, **Vendor**, **Region**, **Cluster**, **City** and **Technology** — have green backgrounds. Operator uses the workspace operator identity; Operator_Vendor is the `<Operator>_<Vendor>` identity and Vendor the vendor alone from the mapping; inventories with the former Vendor_Only column keep working. City comes from the mapping. Region and Cluster prefer imported polygon names resolved from the inventory site coordinates, falling back to the inventory fields only when no polygons exist for that dimension; unmatched polygon locations remain empty. Their source-header aliases include Vodafone Region, Beacon2Town and Engineering Polygon, and Three UK "Regional", Town and Regional Optimisation Polygon; blank generic columns do not hide populated source attributes. Technology uses LTE/NR, resolved from Technology/RAT, Vodafone's 4G/5G source sheets or Three's LTE ECI format.

The inventory tables include **all uploaded mapping rows**, whether or not their cells appear in the CDRs. **Analysis Selection** filters Operator, Vendor, Region, City and Technology directly against the mapping attributes; Region filters match imported polygon names when Region polygons are present. The CDRs used, NR Mode and Campaigns do not restrict inventory rows because they describe measurements rather than the deployed inventory. The tables also work without CDRs. Operators without a matching uploaded inventory contribute no records.

**Previous** and **Next** navigate the filtered table; horizontal scrolling reveals additional columns. Each table’s **Export CSV** downloads all matching rows and columns for its operator, not only the visible page. The complete CSV is prepared before the download begins to prevent partially exported inventories. **Export All to CSV** combines both operators in one file. Both exports use the selection that generated the displayed tables. Repeated inventory rows remain intact. Missing fields in another operator's inventory appear empty. Source_Dataset_ID and Source_Dataset_Name identify each mapping file, including multiple uploaded versions. All original columns are retained after the highlighted fields; source headers that collide with those fields use a `Source_` prefix so their original values remain available.

Choose **Observed Sites/Cells (from CDRs)**, above Full Sites/Cells Inventory, to list the same per-operator tables from the CDR measurements instead: one row per observed site and LTE cell (Cell Identity; sites without a reported cell appear with an empty Cell_ID) with Operator, Vendor, Region, City, Cluster, Technology, Band, CDR types, Campaigns, Samples, mean coordinates and mean RSRP/SINR. These tables follow the full Analysis Selection, including the CDRs used, NR Mode, Campaigns and filters. Building them for a new selection takes a few seconds; the result is stored and reused.

Every column header of both tables has a **▾** button with an Excel-style filter: search the column values (with their row counts, under the other active filters), check the ones to keep — **(Blanks)** keeps empty cells — and **Apply**. Filtered columns are highlighted, **Clear N filters** removes them, and the table's **Export CSV** exports only the filtered rows.

CSV file names identify their operators: `_VF` for Vodafone tables, `_3` for Three tables and `_VF_3` for files combining both, for example `site-cell-inventory_VF.csv`, `cdr-observed-sites-cells_3.csv` or `network-deployment-scenario_VF_3.csv`.

Grouped deployment counts and their CSVs retain their inventory-wide scope. Deployment tables and the inventory index are stored in the workspace cache, so switching **View / Split by** is fast until an inventory changes. Existing per-dataset inventory download endpoints remain available for complete source exports. No additional persistent data is created; existing dataset export, transfer and backup/restore workflows continue to carry the mappings.


## Cluster Sites Density

The **Site density of the inventory snapshot** table counts, per owner network and Cluster (or Region when there are no cluster polygons), its in-service sites and the sites with NR, the area of the polygon (km², equal-area projection) and the **sites per km²**, and the median and P90 **distance to the nearest site** of the same network (the inter-site distance). Without imported polygons the sites are grouped by the inventory's Cluster or Region field, without areas.

Choose the **Data source** dropdown:

- **Observed Sites/Cells** follows the CDRs used and Analysis Selection filters. The table counts, per group, the **observed eNodeBs** (distinct LTE eNodeB identities, Cell Identity ÷ 256, that served the measuring devices) and **observed cells**, with the samples per eNodeB. Observed eNodeBs depend on the route and do not equal the deployed sites.

- **Inventory Sites/Cells** reads every ready Vodafone and Three Vendor mapping dataset uploaded in Workspace. It shows distinct sites and cells per operator, deduplicating identifiers across overlapping uploads, plus inventory total cards. These are complete inventory counts, independent of CDR selection and filters. Other operator inventory formats are not currently supported.

A card explains that site density per km² needs cluster or region polygons imported in Workspace as **Clusters — Geospatial** or **Regions — Geospatial** (GeoJSON, JSON or zipped shapefile); it is hidden once they are imported. **Network Deployment** appears immediately before this panel.

The explanatory note appears only in Observed Sites/Cells mode. A separate yellow **Pending input** card above the cluster-polygon card lists only operators present in the filtered analysis that no inventory snapshot serves. It is hidden when all analysed operators are served, before an analysis exists, and in Inventory Sites/Cells mode. PowerPoint and Word include both data sources irrespective of the selected dropdown option.

## Spectrum

**Licensed spectrum** aggregates the MHz configured in [Workspace Config → Spectrum Holdings](workspace-config.md#spectrum-holdings) per Operator into Low (below 1 GHz), Mid (1–3 GHz FDD/SDL) and High (TDD) bands. Without holdings, the panel shows a pending-input notice.

**Spectrum deployed in the inventory snapshot** lists, per owner network, technology and band, its in-service sites and cells, its **carriers** (distinct EARFCN/ARFCN channels, up to six shown; channel 0 is a placeholder and is left out), the typical bandwidth and the **deployed MHz**: the width of the union of the frequency ranges of its carriers (centre frequency ± half the bandwidth), so the several NR-ARFCNs of one carrier and overlapping carriers count once.

**NR sites by duplex mode** counts, per owner network of the inventory snapshot, its in-service sites with NR cells: those with **NR TDD** (n77, n78, n38, n40, n41 or n258; NR3400, NR3600 and NR3700 in UK inventories), with **NR FDD** (n1, n3, n7, n8, n20 or n28; NR2100, NR900 and NR700), with both and with only one of them. They are counted as **logical sites** (the site IDs of each network) and as **physical sites**: sites of any network within 50 m of each other stand on one physical site, so a mast shared by several networks (MBNL, Beacon) counts once in the **All networks** row that closes every table, which has TDD or FDD when any of its networks does. The table follows the **Operators**, **Operator_Vendor**, **Vendors**, **Regions**, **Clusters** and **Cities** filters of the Analysis Selection, matched against the inventory (the owner network of each cell, its vendor, the imported Region or Cluster polygon of its site, else its inventory field, and its inventory city); Campaigns, NR Mode and Environments describe the measurements and do not restrict it. **Split by** shows the counts per Region, Cluster, City, RAN Vendor or Host Network, each area with its own All networks row. It follows the Inventory snapshot of the Analysis Selection and does not need an analysis. Operators without an inventory (EE in the UK) are named in its status line.

**Spectrum observed in the measurements** shows the share of samples served on each LTE band (from the serving EARFCN or the band of the cell trace) and NR band, with the frequency, duplex mode, class and the most frequent downlink bandwidth. Bandwidths are reported only by CDR Data. Observed bands follow the grouping: keep Operator checked to see each operator's own bands.

**Tests**, below it, chooses the CDR Data tests of the two bandwidth views: **Download tests** (the tests with DL in their name, such as FDTT HTTP DL MT and FDFS HTTP(S) DL ST; the default) or **All Data tests**.

- **Bandwidth per band** counts, per group, technology and serving band (with its duplex mode), the samples at each downlink bandwidth of its primary carrier (the LTE PCell or the NR PCell), with their share of the band shaded, the samples without a bandwidth and the most frequent bandwidth.
- **Total bandwidth: LTE and 5G together** adds, for each test, its LTE bandwidth (its mean over the aggregated LTE carriers, `LTE_DL_Test_Bandwidth_Avg`, else its LTE PCell bandwidth, rounded up to 5 MHz as the Reporting field *LTE DL Aggregated BW (MHz)*) and its NR PCell bandwidth, and classes it as **200+**, **140–199**, **100–139**, **60–99**, **40–59**, **25–39** or **under 25 MHz**. A stepped chart shows one ladder per group (the Split by fields other than Environment, as columns) and environment (Cities, Towns, and Roads and railways, as rows): each class is a block as wide as its midpoint and as tall as its share of the tests with a known bandwidth, widest at the bottom; the figure beside it, in the dark red of its block, is the share under 25 MHz, and the label under it the share at 100 MHz or more (*93% at 100 MHz+*), in bold for the largest of the environment. The chart carries this title and, under it in red, a line that explains the ladders and their number and names, for each environment, the group with the largest share under 25 MHz (for example *Most under 25 MHz: Cities, 3 · 2026-Q3 (7%); Roads and railways, O2 · 2026-Q3 (37%)*). Hovering a block shows its share and tests. The tests that report neither bandwidth, and those without an environment when others have one, are left out and counted under the chart; without environments, every test is one row. The CDRs do not report the bandwidth of the NR secondary carriers, so NR carrier aggregation (for example n78 with n28 in SA) is not added.


## RF Quality template and Dashboard

The existing **NSA - RF Quality (RSRP & SINR)** template and **RF Quality (RSRP & SINR)** Dashboard are workspace content. The application does not install them automatically. Import them from another workspace or create them in the editors. A Dashboard without a saved CDR universe uses the two newest NSA CDRs of each type. The template contains:

Each family (CDF/histograms, averages, classes, thresholds and maps) starts with an **All CDR types** slide. It pools valid Data, Voice and Speech observations per Operator and Campaign; it does not average the three type averages. LTE and NR stay separate, and missing technologies do not contribute samples. The existing type-specific slides follow the aggregate.

- Grouped-bar histogram slides follow each CDF/contour slide for All CDR types, Data, Voice and Speech. Their `Title + 2 rows + dynamic columns + comments down` layout and `Dynamic Columns Field = Operator` create one column per selected Operator on the same slide, with LTE above NR and comments beneath. Every bin has one bar per Campaign, ordered oldest to newest: the newest uses the Operator colour and older Campaigns use progressively lighter shades. Percentages use the same valid-sample denominator and bin widths as the contour histograms.
- RSRP and SINR CDFs (LTE and NR) for Data, Voice and Speech, with contour histograms underneath in a two-by-two layout. RSRP uses 5 dB bins and SINR uses 1 dB bins; percentages are normalized per Operator and Campaign. Histograms reuse CDF colours and campaign line widths: newer campaigns are thicker, while multivendor operator comparisons retain their distinct line patterns;
- average LTE and NR RSRP and SINR bars per CDR type;
- separate LTE and NR RSRP distributions in -110/-100/-90/-80 dBm buckets and SINR distributions in 0/5/13/20 dB buckets, with red-to-green class colours matching the histogram background bands;
- separate LTE and NR shares of samples below -110 dBm and below 0 dB, calculated from valid measurements of each technology;
- LTE and NR coverage (RSRP) and quality (SINR) maps for Data, Voice and Speech, coloured from red to green using the same quality ranges; maps combine the measured samples in the selected Operator, Campaign and geographical filters, rather than estimating unmeasured coverage;
- the same black-logo closing slide as the NSA NetCheck template.

Edit, rename or delete them like any other template or Dashboard. A deleted copy is not recreated.

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
| Environment | `G_Level_3`, else `G_Level_2` | `G_Level_3`, else `G_Level_2` | `G_Level_3`, else `G_Level_2` |

Speech falls back to the `Recording_*` fields when the `Playing_*` fields are absent. Region and City use `Region`/`City`, or `G_Level_2`/`G_Level_4`.

## Pending inputs

| Input | Used by | How to provide it |
| --- | --- | --- |
| Inventory of every network | Serving Cells, 5G Availability, Network Snapshot, Network Deployment, Cluster Sites Density, Spectrum | Upload Multivendor Mappings or Network Inventories (CSV, Excel or Cell Configuration KMZ/KML/ZIP) in Workspace and date their snapshots |
| Cluster or region polygons | Cluster Sites Density (sites per km²), Network Deployment (Region and Cluster) | Upload GeoJSON, JSON or a zipped shapefile as Clusters — Geospatial or Regions — Geospatial in Workspace |
| Serving Networks | Serving Cells, 5G Availability and the Vendor mapping | [Workspace Config → Serving Networks](workspace-config.md#serving-networks); the defaults cover Vodafone, 3 and Lebara |
| Licensed spectrum per Operator | Spectrum | [Workspace Config → Spectrum Holdings](workspace-config.md#spectrum-holdings) |
| NNS site list, if it differs from the inventory eMOCN Scenario | Network Deployment | Include it in the uploaded inventory |

## Persistence and transfers

Analyses are calculated on demand. Spectrum Holdings and Serving Networks belong to the workspace and travel with the **Mappings & Reference Data** export, transfers and backups; the inventory snapshots travel with their datasets, and their Inventory Cells are rebuilt from them when needed. Workspace templates and Dashboards travel with Report Templates and Dashboards.

Network Insights remembers the selected CDRs, NR Mode, Technology, grouping, filters, thresholds, map grid, inventory snapshot, overshooting distance, deployment grouping and technology, the Split by of the NR sites by duplex mode and the Tests of the bandwidth views in this browser, separately for each workspace and user. Unavailable CDRs or values are omitted when restored. Opening or reloading Network Insights, also after the application restarts, restores the selection of the last analysis and shows that analysis again at once, from the results the workspace keeps; when its stored result is no longer valid (its CDRs or inputs changed, or an application update changed the results), the analysis runs again by itself. Reloading keeps the scroll position. Once the selection changes, press **Analyse Network** to calculate it. These browser preferences are not included in workspace exports or backups.

## Troubleshooting

- **No ready CDRs** in a CDR list: check the NR Mode and that the CDRs finished processing.
- **No samples match**: clear the Operator, Vendor, Region, City or Campaign restriction.
- **A map is empty**: the selected CDRs carry no coordinates or no values for the selected Technology; the status line says which.
- **NR curves are empty**: NSA CDRs report NR values only while the device is attached to NR; check the NR RSRP samples column in the RF Quality table.
- **The Licensed spectrum panel shows Pending input**: add Spectrum Holdings in Workspace Config.
