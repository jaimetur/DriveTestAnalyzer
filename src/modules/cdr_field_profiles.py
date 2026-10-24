"""The CDR columns each module reads, per CDR type (the provider of the CDRs).

Each workspace handles the CDRs of one provider (see cdr_types). Ingestion, Non-Qualified Calls, Network Insights,
the serving-cell Vendor Mapping and the points lost of Scoring (Map Areas) read the columns they need through the
field profile of that provider, so the CDRs of every provider keep their own column names and values.

A profile lists, for each logical field, its candidate source columns in order of preference; column names are
matched regardless of case and separators (see column_names.resolve_column_name). The NetCheck profile holds the
columns the modules have always read. Providers without a profile yet read as NetCheck, as every workspace did before
the profiles existed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.modules.cdr_types import DEFAULT_CDR_TYPE, workspace_cdr_type

Sources = tuple[str, ...]
CoordinatePairs = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CdrFieldProfile:
    """Where one provider's CDRs keep each field the modules read."""

    cdr_type: str
    # -- ingestion ----------------------------------------------------------------------------------------------
    # Worksheets that never hold CDR rows, and the sheet the operator sheets follow (empty: every visible sheet).
    ignored_sheets: frozenset[str]
    operator_sheets_after: str
    # The word in a file name that tells its CDR type, in order, then the columns that tell it otherwise.
    kind_name_words: tuple[tuple[str, str], ...]
    kind_markers: dict[str, frozenset[str]]
    # Internal fields of every CDR row (operator, status, setup_time_seconds…): the first column with a value.
    normalised_sources: dict[str, Sources]
    # Internal fields averaged over every column present (packet loss and jitter of both sides).
    averaged_sources: dict[str, Sources]
    # Yes/No columns that also mark a row as dropped, and as an unsustainable call.
    dropped_flag: str
    unsustainable_flag: str
    # CDR-Main fields added to every CDR (see ingestion.ensure_fixed_cdr_fields), and the fields filled from the
    # first of a group of columns: (fields, columns).
    fixed_sources: dict[str, Sources]
    fixed_groups: tuple[tuple[Sources, Sources], ...]
    # -- Non-Qualified Calls -------------------------------------------------------------------------------------
    nq_field_sources: dict[str, Sources]
    nq_join_sources: Sources
    nq_identifier_sources: dict[str, Sources]
    nq_sample_sources: Sources
    nq_subscriber_sources: Sources
    # The column that tells whether a call is qualified, and its value for a qualified call (any other is NQ).
    nq_qualification_sources: Sources
    nq_qualified_value: str
    # The LTE PCIs of the cells of a call, for its Map.
    pci_columns: dict[str, Sources]
    # -- Network Insights ----------------------------------------------------------------------------------------
    rf_field_aliases: dict[str, dict[str, Sources]]
    dimension_aliases: dict[str, Sources]
    # -- serving cells (Vendor Mapping) and the Map of NQ calls ------------------------------------------------------
    cell_columns: Sources
    start_coordinates: dict[str, CoordinatePairs]
    end_coordinates: dict[str, CoordinatePairs]
    time_columns: Sources
    # -- points lost of Scoring and Map Areas ----------------------------------------------------------------------
    area_fields: dict[str, Sources]
    coordinate_sources: dict[str, CoordinatePairs]
    environment_columns: Sources


_NETCHECK_STATUS = ('status', 'Call_Status', 'Test_Result', 'Test_Status')

NETCHECK_PROFILE = CdrFieldProfile(
    cdr_type='netcheck',
    ignored_sheets=frozenset({
        'MASTER',
        'KPI Definition',
        'KPI Definition_OLD',
        'RANKING',
        'RANKING OnDemand',
        'RANKING 5G',
        'Lists',
        'SetupEnviroment',
        'TMP_CLIPBOARD',
    }),
    # NetCheck CDR workbooks place their operator extracts immediately after the KPI Definition worksheet.
    operator_sheets_after='KPI Definition',
    kind_name_words=(('speech', 'speech'), ('voice', 'voice'), ('data', 'data')),
    kind_markers={
        'voice': frozenset({
            'POLQA_LQ_Avg', 'Call_Setup_Time', 'Call_Duration', 'Call_Status',
            'Dropped_in_first_70s', 'Disturbed_Call', 'Impaired_Call',
        }),
        'speech': frozenset({
            'LQ', 'RTP_Jitter_Avg_A', 'RTP_Jitter_Avg_B', 'RTP_Packet_Loss_A',
            'RTP_Packet_Loss_B', 'Receive_Delay', 'Listening_Technology',
            'Recording_Technology', 'Playing_Handovers',
        }),
        'data': frozenset({
            'Mean_Data_Rate', 'TCP_Throughput', 'Data_Throughput', 'Test_Result',
            'Transfer_Access_Duration', 'Transfer_Duration',
            'TCP_RTT_Service_Access_Delay', 'DNS_Service_Access_Delay',
            'VideoStream_Time_To_Start_Buffering', 'VideoStream_Video_Stream_Duration',
            'http_Browser_Access_Duration',
        }),
    },
    normalised_sources={
        'campaign': ('Campaign',),
        'market': ('market', 'Market'),
        'period': ('period', 'Period'),
        'operator': ('operator', 'Operator_A', 'Operator', 'Home_Operator_A', 'Home_Operator'),
        'session_type': ('session_type', 'Session_Type_A', 'Session_Type', 'Type_of_Test', 'type_of_test'),
        'test_name': ('test_name', 'Test_Name'),
        'direction': ('direction', 'Direction_A', 'Direction', 'Call_Direction', 'call_direction'),
        'region': ('region', 'Region'),
        'city': ('city', 'City'),
        'status': ('status', 'Call_Status_A', 'Call_Status', 'Test_Result', 'Test_Status'),
        'disturbed': ('Disturbed_Call',),
        'impaired': ('Impaired_Call',),
        'event_start_time': ('Call_Start_Time', 'Call Start Time', 'Test_Start_Time', 'Test Start Time', 'Data_Start_Time', 'Data Start Time'),
        'event_end_time': ('Call_End_Time', 'Call End Time', 'Test_End_Time', 'Test End Time', 'Data_End_Time', 'Data End Time'),
        'setup_time_seconds': ('Call_Setup_Time', 'Transfer_Access_Duration', 'http_Browser_Access_Duration', 'VideoStream_Time_To_Start_Buffering'),
        'duration_seconds': ('Call_Duration', 'Test_Duration', 'Data_Test_Duration', 'Transfer_Duration', 'VideoStream_Video_Stream_Duration'),
        'quality_score': ('POLQA_LQ_Avg', 'LQ', 'Mean_Data_Rate'),
        'throughput_mbps': ('Mean_Data_Rate', 'TCP_Throughput', 'Data_Throughput'),
        'latency_ms': ('Receive_Delay', 'TCP_RTT_Service_Access_Delay', 'DNS_Service_Access_Delay'),
        'handovers': ('Handovers_Info', 'Handovers_Info_A', 'Playing_Handovers'),
        'technology_primary': ('RAT', 'RAT_A', 'L2_call_Mode_A', 'Playing_Technology'),
        'technology_secondary': ('L2_call_Mode_B', 'RAT_B', 'Recording_Technology', 'RAT_Timeline'),
    },
    averaged_sources={
        'packet_loss_pct': ('RTP_Packet_Loss_A', 'RTP_Packet_Loss_B', 'Packet_Loss_Score'),
        'jitter_ms': ('RTP_Jitter_Avg_A', 'RTP_Jitter_Avg_B'),
    },
    dropped_flag='Dropped_in_first_70s',
    unsustainable_flag='Unsustainable_Call',
    fixed_sources={
        'Campaign': ('Campaign',),
        'Benchmark': ('Benchmark',),
        'Campaign_Year': ('Campaign_Year',),
        'Campaign_Quarter': ('Campaign_Quarter',),
        'Period': ('Period',),
        'Market': ('Market',),
        'Region': ('Region',),
        'Zone': ('Zone', 'G_Level_3'),
        'City': ('City', 'G_Level_4'),
        'Operator': ('Operator', 'Operator_A', 'Home_Operator_A', 'Home_Operator'),
        'Subscriber': ('Subscriber', 'Suscriber'),
        'Test_Name': ('Test_Name',),
    },
    fixed_groups=(
        (('Technology', 'RAT', 'RAT_A', 'L2_Call_Mode_A', 'Playing_Technology'),
         ('Technology', 'RAT', 'RAT_A', 'L2_Call_Mode_A', 'Playing_Technology')),
        (('Session_Type', 'Type_Of_Test'), ('Session_Type', 'Type_Of_Test')),
        (('Call_Status', 'Status', 'Result', 'Test_Result'), ('Call_Status', 'Status', 'Result', 'Test_Result')),
    ),
    nq_field_sources={
        'campaign': ('Campaign',),
        'operator': ('Operator', 'Operator_A', 'Home_Operator_A', 'Home_Operator'),
        'operator_vendor': ('Operator_Vendor',),
        'vendor': ('Vendor',),
        'region': ('region', 'Region'),
        'cluster': ('Cluster',),
        'city': ('city', 'City'),
        'technology': ('Technology', 'technology_primary', 'RAT_A', 'RAT'),
        'test_name': ('Test_Name', 'Type_Of_Test', 'Session_Type', 'Test_Type'),
        'session_type': ('Session_Type',),
        'direction': ('Direction', 'Call_Direction'),
        'result': _NETCHECK_STATUS,
        'start_time': ('event_start_time', 'Call_Start_Time', 'Test_Start_Time'),
        'end_time': ('event_end_time', 'Call_End_Time', 'Test_End_Time'),
        'failure_phase': ('Failure_Phase',),
        'failure_technology': ('Failure_Technology',),
        'failure_classification': ('Failure_Classification',),
        'failure_category': ('Failure_Category',),
        'failure_subcategory': ('Failure_Subcategory',),
        'failure_comment': ('Failure_Comment',),
        # The cell that served the call (the serving-cell Vendor Mapping) and where it ran (City or Connecting Roads).
        'host_network': ('Serving_Host_Network',),
        'site_id': ('Serving_Site_ID',),
        'environment': ('G_Level_2',),
        'latitude': ('Call_Start_Latitude_A', 'Test_Start_Latitude', 'Playing_Latitude', 'Recording_Latitude'),
        'longitude': ('Call_Start_Longitude_A', 'Test_Start_Longitude', 'Playing_Longitude', 'Recording_Longitude'),
        'cell_id': ('Cell_ID_A', 'Cell_ID', 'Cell_IDs_A', 'LAC_CID_xARFCN_A', 'LAC_CID_xARFCN'),
    },
    # NetCheck's identifier of each voice call and data test, the same in the Daily and Final CDRs.
    nq_join_sources=('JOIN_ID',),
    # Without a JOIN_ID: the test of a Data CDR, the session (the call) of a Voice or Speech CDR.
    nq_identifier_sources={
        'data': ('Test_ID', 'Session_id'),
        'voice': ('Session_ID_A', 'Session_id', 'Test_ID'),
        'speech': ('Session_ID_A', 'Session_id'),
    },
    # A Speech sample inside its call.
    nq_sample_sources=('Test_ID', 'Sample_ID', 'Sequence_ID_per_File_ID'),
    nq_subscriber_sources=('Subscriber',),
    # A NetCheck call or test is Non-Qualified when its result is anything other than Completed.
    nq_qualification_sources=_NETCHECK_STATUS,
    nq_qualified_value='completed',
    pci_columns={'voice': ('PCI_A',), 'data': ('LTE_DL_PCell_PCI_Info_List', 'PCI'), 'speech': ('PCI_A',)},
    # Each logical radio field lists, per CDR type, the source columns that carry it in priority order. Voice uses
    # the measuring (A) side.
    rf_field_aliases={
        'latitude': {
            'data': ('Test_Start_Latitude',), 'voice': ('Call_Start_Latitude_A',), 'speech': ('Playing_Latitude', 'Recording_Latitude'),
        },
        'longitude': {
            'data': ('Test_Start_Longitude',), 'voice': ('Call_Start_Longitude_A',), 'speech': ('Playing_Longitude', 'Recording_Longitude'),
        },
        'lte_rsrp': {
            'data': ('LTE_PCell_RSRP_Avg',), 'voice': ('4G_RSRP_Avg_A',), 'speech': ('Playing_RSRP_Avg', 'Recording_RSRP_Avg'),
        },
        'nr_rsrp': {
            'data': ('NR_PCell_RSRP_Avg',), 'voice': ('NR_RSRP_Avg_A',), 'speech': ('Playing_RSRP_NR_Avg', 'Recording_RSRP_NR_Avg'),
        },
        'lte_sinr': {
            'data': ('LTE_PCell_SINR_Avg',), 'voice': ('4G_SINR_Avg_A',), 'speech': ('Playing_SINR_Avg', 'Recording_SINR_Avg'),
        },
        'nr_sinr': {
            'data': ('NR_PCell_SINR_Avg',), 'voice': ('NR_SINR_Avg_A',), 'speech': ('Playing_SINR_NR_Avg', 'Recording_SINR_NR_Avg'),
        },
        'cell_trace': {
            'data': ('LAC_CID_xARFCN',), 'voice': ('LAC_CID_xARFCN_A',), 'speech': (),
        },
        'cell_ids': {
            'data': ('Cell_ID',), 'voice': ('Cell_ID_A',), 'speech': ('Cell_IDs_A',),
        },
        'enodeb_id': {
            'data': (), 'voice': (), 'speech': ('Playing_eNodeBId', 'Recording_eNodeBId'),
        },
        'earfcn': {
            'data': ('LTE_PCC_EARFCN',), 'voice': ('E/U/ARFCN_A',), 'speech': ('ARFCN_A',),
        },
        'nr_band': {
            'data': ('NR_DL_PCell_Band',), 'voice': ('NR_BAND_A',), 'speech': (),
        },
        'lte_bandwidth': {
            'data': ('LTE_DL_PCell_Bandwidth',), 'voice': (), 'speech': (),
        },
        'nr_bandwidth': {
            'data': ('NR_DL_PCell_Bandwidth',), 'voice': (), 'speech': (),
        },
        # The mean LTE bandwidth of a test over every aggregated carrier, and the test (download tests carry "DL").
        'lte_aggregated_bandwidth': {
            'data': ('LTE_DL_Test_Bandwidth_Avg',), 'voice': (), 'speech': (),
        },
        'test_name': {
            'data': ('Test_Name',), 'voice': (), 'speech': (),
        },
        # The time of a test on NR and its duration (s), for the share of the tests that used 5G (Key Findings).
        'nr_time': {
            'data': ('NR_Total_Time',), 'voice': (), 'speech': (),
        },
        'test_duration': {
            'data': ('Test_Duration',), 'voice': (), 'speech': (),
        },
        # The NR leg of NSA samples (its PCI and SSB NR-ARFCN) and the MIMO rank and layers the device reported.
        'nr_pci': {
            'data': ('NR_DL_PCell_PCI_Info_List',), 'voice': (), 'speech': (),
        },
        'nr_arfcn': {
            'data': ('NR_DL_PCell_ARFCN',), 'voice': (), 'speech': (),
        },
        'lte_rank': {
            'data': ('LTE_DL_Rank_Index',), 'voice': (), 'speech': (),
        },
        'nr_rank': {
            'data': ('NR_DL_Rank_Index',), 'voice': (), 'speech': (),
        },
        'nr_layers': {
            'data': ('NR_DL_Max_MIMO_Layers',), 'voice': (), 'speech': (),
        },
        # The result, speed and interactivity of the CDR Data tests, for the download tests by location and Latency &
        # Interactivity.
        'test_result': {
            'data': ('Test_Result',), 'voice': (), 'speech': (),
        },
        'type_of_test': {
            'data': ('Type_of_Test',), 'voice': (), 'speech': (),
        },
        'mean_data_rate': {
            'data': ('Mean_Data_Rate',), 'voice': (), 'speech': (),
        },
        'rtt_median': {
            'data': ('Interactivity_RTT_Median',), 'voice': (), 'speech': (),
        },
        'packets_lost': {
            'data': ('Packets_Lost',), 'voice': (), 'speech': (),
        },
        'packets_sent': {
            'data': ('Packets_Sent',), 'voice': (), 'speech': (),
        },
        'jitter': {
            'data': ('Packet_Delay_Variation_Median', 'jitter_ms'), 'voice': (), 'speech': (),
        },
        # The network, host network and eMOCN scenario of the cell that served the start of each sample (the
        # serving-cell Vendor Mapping), for the kind of serving site.
        'serving_network': {
            'data': ('Serving_Network',), 'voice': ('Serving_Network',), 'speech': ('Serving_Network',),
        },
        'serving_host': {
            'data': ('Serving_Host_Network',), 'voice': ('Serving_Host_Network',), 'speech': ('Serving_Host_Network',),
        },
        'serving_scenario': {
            'data': ('Serving_eMOCN_Scenario',), 'voice': ('Serving_eMOCN_Scenario',), 'speech': ('Serving_eMOCN_Scenario',),
        },
    },
    dimension_aliases={
        'operator': ('Operator',),
        'operator_vendor': ('Operator_Vendor',),
        'vendor': ('Vendor',),
        'campaign': ('Campaign', 'Period'),
        'region': ('Region', 'G_Level_2'),
        'cluster': ('Cluster',),
        'city': ('City', 'G_Level_4'),
        # The test environment (see cdr_environments): the most detailed level, else the route level.
        'environment': ('G_Level_3',),
        'environment_route': ('G_Level_2',),
        # Drive or Walk (see network_insights_findings.mode_of_test).
        'mode': ('G_Level_1',),
        'source_sheet': ('source_sheet',),
    },
    cell_columns=(
        'Cell_ID_A', 'Cell_IDs_A', 'Cell_ID', 'Cell ID A', 'Cell IDs A', 'Global_Cell_ID_A', 'Global_Cell_ID',
        'Global CI', 'Global_CI', 'GCID', 'GCI', 'CGI', 'ECI', 'Serving_Cell_ID',
    ),
    start_coordinates={
        'data': (('Test_Start_Longitude', 'Test_Start_Latitude'),),
        'voice': (('Call_Start_Longitude_A', 'Call_Start_Latitude_A'),),
        'speech': (('Playing_Longitude', 'Playing_Latitude'), ('Recording_Longitude', 'Recording_Latitude')),
    },
    end_coordinates={'voice': (('Call_End_Longitude_A', 'Call_End_Latitude_A'),)},
    time_columns=('Test_Start_Time', 'Call_Start_Time_A', 'Call_Start_Time', 'Playing_Start_Time', 'Recording_Start_Time',
                  'event_start_time', 'Start_Time', 'Date'),
    area_fields={'City': ('City', 'G_Level_4'), 'Region': ('Region',), 'Cluster': ('Cluster',)},
    coordinate_sources={
        'data': (('Test_Start_Latitude', 'Test_Start_Longitude'),),
        'voice': (('Call_Start_Latitude_A', 'Call_Start_Longitude_A'),),
        'speech': (('Recording_Latitude', 'Recording_Longitude'), ('Playing_Latitude', 'Playing_Longitude')),
    },
    environment_columns=('G_Level_1', 'G_Level_2', 'G_Level_3'),
)

FIELD_PROFILES: dict[str, CdrFieldProfile] = {'netcheck': NETCHECK_PROFILE}


def field_profile(cdr_type: object = DEFAULT_CDR_TYPE) -> CdrFieldProfile:
    """The field profile of a CDR type; a type without its own profile yet reads as NetCheck."""
    key = str(cdr_type or '').strip().casefold()
    return FIELD_PROFILES.get(key, NETCHECK_PROFILE)


def workspace_field_profile(repository: Any) -> CdrFieldProfile:
    """The field profile of the CDR type of a workspace."""
    return field_profile(workspace_cdr_type(repository))
