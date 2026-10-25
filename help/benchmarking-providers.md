# Benchmarking providers

DriveTest Analyzer was built for the CDRs of NetCheck. It is being adapted to the CDRs of other benchmarking providers, Umlaut first and then P3, without losing any feature and without translating their CDRs into NetCheck names. This chapter describes the status of that adaptation and the model it follows; the compatibility report of each provider, below it in Help Navigation, compares its CDRs with NetCheck CDRs.

> [!NOTE]
> **Available versus planned.** Today every workspace processes NetCheck CDRs. **Umlaut CDR** and **P3 CDR** appear as *coming soon* in the [CDR type](workspace-config.md#cdr-type) of a workspace until they are supported. The compatibility reports describe planned work, not features of the current release.

## In this guide

| Task or topic | Go to |
| --- | --- |
| Presentation | [Open section](#presentation) |
| Adaptation status | [Open section](#adaptation-status) |
| The multi-provider model | [Open section](#the-multi-provider-model) |
| Compatibility reports | [Open section](#compatibility-reports) |

## Presentation

The adaptation is also a presentation, **Benchmarking Providers Roadmap**, in [Product Presentations](presentations.md): the multi-provider model, the status of each phase, how the tool is built inside and how it is deployed as a Docker container in the cloud, on AWS or in the Ericsson cloud. Select it to open it in the slide viewer or download its PowerPoint.

```presentations
benchmarking-providers
```

## Adaptation status

The adaptation is planned in seven phases. The durations are indicative: they depend on multi-operator samples, the Umlaut Scoring methodology and the P3 format.

| Phase | Scope | Status |
| --- | --- | --- |
| 1. Multi-provider base | The CDR types of the providers and a field profile per CDR type; the modules read the CDR columns through the profile of the workspace. | **Done** in version 0.9.0 |
| 2. Umlaut reader, profile and upload | The Umlaut reader (files per service, the Statistics sheet, Side1/Side2 headers, samples joined to their call), the Umlaut profile with its native names, campaign and operator detection confirmed on upload, derived columns (call key, ECI, mean radio of the call) and a CDR Field Dictionary panel. | **Done** in version 0.9.0; Umlaut CDR stays *coming soon* until a multi-operator export validates it |
| 3. Scoring ready for Umlaut | Formulas with native names and a field picker, percentiles other than P90 and environments by the Umlaut scoring category; the Umlaut methodology is loaded when it is available. | Planned · 1 week |
| 4. Umlaut PPT templates | PPT Dashboards templates per service and Auto-calculated Fields with Umlaut values. | Planned · 1 week |
| 5. Non-Qualified Calls and RCA | NQ = Qualifier NOT QUALIFIED, an Umlaut call key, the Umlaut values of the DT Analyzer RCA (available in every workspace) and the Ericsson RCA by the provider's call key. | Planned · 1.5–2 weeks |
| 6. Umlaut Network Insights | The radio of the calls from their samples, NR cells by PCI + ARFCN + distance, MIMO rank and bandwidths. | Planned · 1–1.5 weeks |
| 7. P3 | The P3 reader, profile and content, with the same model. | Once a P3 sample is available |

Phase 1 is available now and changes nothing for NetCheck workspaces:

- **CDR types.** NetCheck CDR is the supported type; Umlaut CDR and P3 CDR are listed as coming soon. A workspace that has Data, Voice or Speech CDRs keeps its CDR type (see [CDR type](workspace-config.md#cdr-type)).
- **Field profiles.** Every CDR type has a field profile that holds the CDR columns the tool reads: the sheets and fields of ingestion, the sources of Non-Qualified Calls (its index, the import of previous analyses and the Failure Map), the radio and dimension columns of Network Insights, the serving cells of the Vendor Mapping and the coordinates of Map Areas. The NetCheck profile holds exactly the columns read before.
- **Validated.** The same real NetCheck CDRs processed before and after the change gave the same results (89 of 89 outputs).

Phase 2 is available too, while Umlaut CDR stays *coming soon* until a multi-operator Umlaut export validates it:

- **Umlaut reader.** Each service workbook (Voice_M2M_Calls, Voice_M2M_SQ_Samples, HTTP_File_DL, Ping...) is a CDR: its Statistics sheet is ignored and every other sheet holds the rows of one operator (`client<N>_<Operator>`, with its Operator column). A header repeated for the second side of a call takes the side of its block (`Side2 Sequence`, `Side2 Route Name`). The All_Data and All_Voice workbooks summarise the others and are not CDRs.
- **Umlaut profile.** Every field keeps its Umlaut name. The results are read in the tool's words (SUCCESS is Completed, FAILED Failed, DROPPED Dropped), the throughputs in Mbit/s (Umlaut gives kbit/s) and the call setup up to the alerting (the [CDR Field Dictionary](workspace-config.md#cdr-field-dictionary) changes it to Option D).
- **Derived columns.** `Campaign` (the benchmark of the file name, such as `WindTre_Vendor_Benchmark_2025_Round1`, when the CDR has none), `Test_Key` (the Filename, Task Name and start of each test: the Sequence of a call is shared by the data tests run at the same time) and `ECI` (eNodeB × 256 + Cell ID of the LTE cells where each row started and ended).
- **Upload.** In an Umlaut workspace the file types read *Umlaut CDR — Data / Voice / Speech* and each file is proposed its type from its service (the SQ_Samples workbooks are Speech, the Calls workbooks Voice, the data services Data) and the Final stage (the export stamp that ends the name is not a measurement date); the summary workbooks ask for a type and offer **Leave out**.
- **Non-Qualified Calls.** A call or test is NQ when its qualifier (Qualifier, Browsing, Datastream, File Transfer or YouTube Qualifier) is NOT QUALIFIED; Ping and DNS have none. A data test is identified by its `Test_Key`, a call and its speech samples by its Sequence; its failure comment is the Failure Indication, and a Voice call takes the mean radio of its speech samples (the radio of its setup without them).
- **CDR Field Dictionary.** A new subpanel of Mappings & Reference Data in [Workspace Config](workspace-config.md#cdr-field-dictionary) shows the columns of every field and lets each workspace change them.
- **Validated.** The same real NetCheck CDRs processed before and after phase 2 gave the same results (90 of 90 outputs); a real Umlaut export (WindTre, Round 1) was processed with the Umlaut profile in a test workspace.

The common engine of phase 5, the [DT Analyzer RCA](non-qualified-calls.md#dt-analyzer-rca), is available too: it finds the root cause of every Non-Qualified Call from the data of its CDR, read through the field profile of the workspace, with rules each workspace can change.

## The multi-provider model

### Decisions

- **One provider per workspace.** A workspace is created for NetCheck, Umlaut or P3 CDRs (its CDR type) and keeps it once it has CDRs. The CDRs of several providers are never mixed.
- **Native names.** Every CDR keeps its original columns, and users see the field names, values and files of their provider. Whatever the tool needs and the provider does not bring is added as a derived column, marked as such.
- **Each provider's Scoring.** The NetCheck methodology is not adapted: the Umlaut methodology is implemented when it is available, written with the Umlaut fields.
- **NQ by provider.** In NetCheck CDRs a call or test is NQ when its result is not Completed; in Umlaut CDRs, when its own Qualifier column says NOT QUALIFIED.
- **A DT Analyzer RCA.** When the provider brings an RCA it is one more source. A DT Analyzer RCA is the common engine for every provider, and the Ericsson RCA is imported by the call key of each provider.

### Three layers per provider

| Layer | What it is | What it holds |
| --- | --- | --- |
| Reader | Code per provider | The structure of the export: which files and sheets are CDRs, the type of each (Data, Voice, Speech), the sheets to ignore (KPI Definition in NetCheck, Statistics in Umlaut), the headers repeated per side and the joins (each speech sample with its call). |
| Field profile | Declarative configuration | Where each concept the modules use lives (result, start, coordinates, cell, RSRP, setup, MOS, call key, whether the call is NQ), with its native column, its conversion and the meaning of its values. |
| Content | Workspace configuration | Scoring methodologies, PPT templates, Auto-calculated Fields, queries, the RCA catalogue and Campaign Maps, written with the provider's names and values. |

The modules keep a single logic: they read the data through the profile of the workspace and use the content of its provider.

### How it looks in each module

| Module | In an Umlaut workspace |
| --- | --- |
| [Workspace Management](workspace-management.md) | The provider is chosen when the workspace is created and shows next to its name. The whole export is uploaded (ZIP or folder) and what was detected is confirmed: services, campaigns, operators, dates, NR Mode and stage. |
| Workspace Config | A "CDR Field Dictionary" panel: every concept with its provider column, conversion and values, editable and included in export, backup and restore. |
| CDR Analysis, **Builders** and the preview | The columns exactly as they come in the files, plus a group of columns derived by DriveTest Analyzer (call key, ECI, mean radio of the call). |
| Scoring & GAP Analysis | Only the provider’s methodologies. Formulas with native names (a field picker and quoted names, because Umlaut uses names such as "Call Setup Duration (OptionD) [s]") and percentiles other than P90. The Umlaut visual theme already exists. |
| PPT Dashboards | The provider’s templates; for Umlaut, per service (M2M voice, OTT, Browsing, FDTT, File, YouTube, Interactivity), filtering by Umlaut values (SUCCESS, VOICE M2M MOC). |
| Non-Qualified Calls | Columns with the provider’s names (Sequence, Qualifier, Failure Indication). In Umlaut, NQ = Qualifier NOT QUALIFIED. RCA sources: the provider’s when it exists, the DriveTest Analyzer one and the Ericsson one. |
| Network Insights | The same panels, with the radio read through the profile; whatever the provider does not bring is marked as not available. |
| [Reporting](reporting.md) and Help | Names and texts according to the workspace’s provider. |

### RCA

- The **NetCheck RCA** source of Non-Qualified Calls suggests a domain and a cause with keywords on Failure_Classification, Failure_Category, Failure_SubCategory and Failure_Comment. Its rule engine is generic; what is specific to NetCheck are its fields and its catalogue.
- The [DT Analyzer RCA](non-qualified-calls.md#dt-analyzer-rca), available in every workspace, reads the failure fields, the radio and the KPIs of each call through the profile of its provider, and editable rules give its root category and cause (for example RSRP below −110 dBm → coverage, SINR below 0 dB → interference, a DNS or service access failure → protocol or core).
- For Umlaut it reads Failure Indication, Sequence Detailed Status Overall, the status of each phase (network access, DNS, connection, service access, TTFB, transfer) and the radio at the start and the end.
- In NetCheck workspaces the NetCheck RCA stays as one more source, like the Ericsson RCA and the DT Analyzer RCA; the Ericsson RCA will be imported by the provider's call key instead of the NetCheck JOIN_ID.

## Compatibility reports

Each provider has a compatibility report of its own, listed below Benchmarking Providers in Help Navigation and shown in its own design:

- [Umlaut CDR Compatibility](/documents/reports/umlaut-cdr-compatibility): the analysis of a sample Umlaut export. It compares the Umlaut files, fields and values with NetCheck CDRs: the equivalent of each of the 109 groups of NetCheck fields the tool uses (84 of them have the same data, the same data with another unit or values, or an exact calculation), what each module will have with Umlaut CDRs and what it will not, the Scoring KPIs with equivalent data, the limits of full compatibility and the open questions.
- [P3 CDR Compatibility](/documents/reports/p3-cdr-compatibility): pending a sample of P3 CDRs; it tells what is known, what the analysis will cover and what is needed.

See the [Roadmap](roadmap.md) for the other planned work.
