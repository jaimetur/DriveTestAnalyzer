"""The CDR columns each module reads, per CDR type (the provider of the CDRs).

Each workspace handles the CDRs of one provider (see cdr_types). Ingestion, Non-Qualified Calls, Network Insights,
the serving-cell Vendor Mapping and the points lost of Scoring (Map Areas) read the columns they need through the
field profile of that provider, so the CDRs of every provider keep their own column names and values.

A profile lists, for each logical field, its candidate source columns in order of preference; column names are
matched regardless of case and separators (see column_names.resolve_column_name). The NetCheck profile holds the
columns the modules have always read; the Umlaut profile reads the service workbooks of Umlaut (see umlaut_cdr).
Providers without a profile yet read as NetCheck, as every workspace did before the profiles existed.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.modules import umlaut_cdr
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
    # The values of every call the DT Analyzer RCA reads (see nq_dta_rca.INPUTS), and the factor a number is
    # multiplied by to reach the unit of the RCA (Mbit/s, %, ms...).
    nq_rca_sources: dict[str, Sources]
    nq_rca_scales: dict[str, float]
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
    # -- reading the provider's workbooks (NetCheck needs none of these) --------------------------------------------
    # A repeated header takes the side of the nearest header before it that matches this pattern ("Side2 Sequence");
    # without a pattern, or a side, it is "<header>_Duplicate_<n>".
    side_header_pattern: str = ''
    # The columns the provider's CDRs gain before they are read: (rows, file name) -> rows.
    derive_columns: Callable[[Any, str], Any] | None = None
    # The factor a normalised number is multiplied by to reach the unit of the tool (kbit/s to Mbit/s).
    normalised_scales: dict[str, float] = field(default_factory=dict)
    # The tool's result for each result of the provider (SUCCESS is Completed), regardless of case.
    status_values: dict[str, str] = field(default_factory=dict)
    # The words in a file name of the workbooks that summarise the others and are not CDRs.
    summary_name_words: tuple[str, ...] = ()
    # The DT Analyzer RCA inputs a Voice call takes from the mean of its Speech samples, when its CDR has the radio of
    # a moment of the call only (its setup).
    nq_call_radio_from_samples: Sources = ()
    # Which calls are Non-Qualified, as Non-Qualified Calls says it ("Every call ... whose result is not Completed").
    nq_definition: str = 'whose result is not Completed (Failed, Dropped, Cutoff…)'


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
    # The columns of Data tests (LTE_PCell_, NR_PCell_), of the A side of Voice calls (_A) and of the playing side of
    # Speech samples (Playing_); the B side is the B side of the call and the recording side of the sample.
    nq_rca_sources={
        'failure_side': ('Failure_Side',),
        'failure_events': ('Failure_Events', 'Failure_Events_A', 'Failure_Events_B'),
        'scg_failures': ('SCG_Failures_A', 'SCG_Failures'),
        'lte_rsrp': ('LTE_PCell_RSRP_Avg', '4G_RSRP_Avg_A', 'Playing_RSRP_Avg'),
        'lte_rsrp_min': ('LTE_PCell_RSRP_Min', '4G_RSRP_Min_A', 'Playing_RSRP_Min'),
        'lte_rsrq': ('LTE_PCell_RSRQ_Avg', '4G_RSRQ_Avg_A', 'Playing_RSRQ_Avg'),
        'lte_sinr': ('LTE_PCell_SINR_Avg', '4G_SINR_Avg_A', 'Playing_SINR_Avg'),
        'lte_sinr_min': ('LTE_PCell_SINR_Min', '4G_SINR_Min_A', 'Playing_SINR_Min'),
        'lte_tx_power': ('LTE_PCell_TxPower_Max', '4G_TxPower_Max_A', 'Playing_TxPower_4G_Max'),
        'lte_bler': ('LTE_PCell_BLER', 'Playing_DL_LTE_BLER_Avg'),
        'nr_rsrp': ('NR_PCell_RSRP_Avg', 'NR_RSRP_Avg_A', 'Playing_RSRP_NR_Avg'),
        'nr_rsrp_min': ('NR_PCell_RSRP_Min', 'NR_RSRP_Min_A', 'Playing_RSRP_NR_Min'),
        'nr_rsrq': ('NR_PCell_RSRQ_Avg', 'NR_RSRQ_Avg_A', 'Playing_RSRQ_NR_Avg'),
        'nr_sinr': ('NR_PCell_SINR_Avg', 'NR_SINR_Avg_A', 'Playing_SINR_NR_Avg'),
        'nr_sinr_min': ('NR_PCell_SINR_Min', 'NR_SINR_Min_A', 'Playing_SINR_NR_Min'),
        'nr_tx_power': ('NR_PCell_TxPower_Max', 'NR_TxPower_Max_A', 'Playing_TxPower_NR_Max'),
        'nr_bler': ('NR_DL_BLER', 'Playing_NR_BLER_Avg'),
        'b_lte_rsrp': ('4G_RSRP_Avg_B', 'Recording_RSRP_Avg'),
        'b_lte_sinr': ('4G_SINR_Avg_B', 'Recording_SINR_Avg'),
        'b_nr_rsrp': ('NR_RSRP_Avg_B', 'Recording_RSRP_NR_Avg'),
        'b_nr_sinr': ('NR_SINR_Avg_B', 'Recording_SINR_NR_Avg'),
        'rat': ('RAT', 'RAT_A'),
        'rat_timeline': ('RAT_Timeline', 'RAT_Timeline_A', 'PCell_RAT_Timeline'),
        'handovers': ('handovers',),
        'handovers_info': ('Handovers_Info', 'Handovers_Info_A', 'Playing_Handovers'),
        'throughput': ('throughput_mbps', 'Mean_Data_Rate'),
        'access_time': ('Transfer_Access_Duration', 'http_Browser_Access_Duration'),
        'dns_time': ('DNS_Service_Access_Delay',),
        'dns_success': ('DNS_Resolution_Success_Ratio',),
        'tcp_rtt': ('TCP_RTT_Service_Access_Delay',),
        'packet_loss': ('Packet_Error_Ratio',),
        'rtt': ('Interactivity_RTT_Median', 'ICMP_Ping_RTT_Mean'),
        'setup_time': ('setup_time_seconds', 'Call_Setup_Time'),
        'duration': ('duration_seconds', 'Test_Duration', 'Call_Duration'),
        'mos': ('POLQA_LQ_Avg', 'LQ'),
        'rtp_packet_loss': ('RTP_Packet_Loss_A',),
        'jitter': ('jitter_ms', 'RTP_Jitter_Avg_A'),
    },
    # NetCheck gives the RTP packet loss as a share (0 to 1).
    nq_rca_scales={'rtp_packet_loss': 100.0},
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

# Each Umlaut service names its result, start, position and cells its own way: the candidates list one per service.
_UMLAUT_STATUS = ('Sequence Status Overall', 'Overall Session Status', 'Transfer Status', 'Ping Status', 'DNS Status',
                  'Qualifier', 'YouTube Qualifier')
_UMLAUT_QUALIFIERS = ('Qualifier', 'Browsing Qualifier', 'Datastream Qualifier', 'File Transfer Qualifier', 'YouTube Qualifier')
_UMLAUT_END_TIME = ('Session TA End', 'Ping TA End', 'Playout TA End', 'DNS TA End')
_UMLAUT_FAILURE = ('Failure Indication', 'Overall Failure Indication', 'Sequence Detailed Status Overall')
_UMLAUT_TECHNOLOGY = ('Technology', 'Side1 Call Technology', 'Side1 Sample Technology')
_UMLAUT_LATITUDE = ('Side1 Call Setup LAT', 'Side1 Sample Start LAT', 'Network Access LAT', 'Ping LAT Start', 'DNS LAT Start')
_UMLAUT_LONGITUDE = ('Side1 Call Setup LON', 'Side1 Sample Start LON', 'Network Access LON', 'Ping LON Start', 'DNS LON Start')
_UMLAUT_DATA_POSITIONS = (('Network Access LON', 'Network Access LAT'), ('Ping LON Start', 'Ping LAT Start'),
                          ('DNS LON Start', 'DNS LAT Start'))


def _by_kind(data: Sources = (), voice: Sources = (), speech: Sources = ()) -> dict[str, Sources]:
    return {'data': data, 'voice': voice, 'speech': speech}


UMLAUT_PROFILE = CdrFieldProfile(
    cdr_type='umlaut',
    ignored_sheets=frozenset({'Statistics'}),
    # Every visible sheet but Statistics holds the rows of one operator (client<N>_<Operator>).
    operator_sheets_after='',
    # The service in the file name: the samples of a call, the calls, then the data services.
    kind_name_words=(
        ('sq samples', 'speech'), ('samples', 'speech'), ('calls', 'voice'), ('voice', 'voice'), ('http', 'data'),
        ('interactivity', 'data'), ('youtube', 'data'), ('ping', 'data'), ('dns', 'data'), ('data', 'data'),
    ),
    kind_markers={
        'voice': frozenset({'Sequence Status Overall', 'Call Setup Status', 'Call Completion Status', 'Call Setup Duration (Alerting) [s]'}),
        'speech': frozenset({'POLQA Value Overall', 'POLQA Sample TA Start', 'Sample Technology Both', 'Side1 Sample Technology'}),
        'data': frozenset({'Task Name', 'Network Access Status', 'Transfer Status', 'Ping Status', 'DNS Status', 'Service'}),
    },
    normalised_sources={
        'campaign': ('Campaign',),
        'market': ('Market',),
        'period': ('Period',),
        'operator': ('Operator',),
        'session_type': ('Service', 'Side1 Call Type'),
        'test_name': ('Task Name', 'Side1 Call Type'),
        'direction': ('Direction',),
        'region': ('Region',),
        'city': ('City',),
        'status': _UMLAUT_STATUS,
        'disturbed': (),
        'impaired': (),
        'event_start_time': umlaut_cdr.START_TIME_COLUMNS,
        'event_end_time': _UMLAUT_END_TIME,
        # The call setup up to the alerting; Call Setup Duration (OptionD) [s] is the alternative.
        'setup_time_seconds': ('Call Setup Duration (Alerting) [s]', 'Service Access Duration [s]', 'Video Start Time [s]'),
        'duration_seconds': ('Session Duration [s]', 'Transfer Duration [s]', 'Video Display Duration [s]'),
        'quality_score': ('POLQA Value Overall',),
        'throughput_mbps': ('Transfer Throughput [kbit/s]', 'Transfer Datarate [kbit/s]', 'Transfer User Datarate [kbit/s]'),
        'latency_ms': ('Ping Duration [ms]', 'TWAMP RTT Median', 'DNS Duration [ms]', 'HTTP RTT First [ms]'),
        'handovers': (),
        'technology_primary': _UMLAUT_TECHNOLOGY,
        'technology_secondary': ('Technology List', 'Side2 Call Technology', 'Side2 Sample Technology'),
    },
    averaged_sources={
        'packet_loss_pct': ('TWAMP Packet Loss (%)',),
        'jitter_ms': ('TWAMP Packet Delay Variation Median',),
    },
    dropped_flag='',
    unsustainable_flag='',
    fixed_sources={
        'Campaign': ('Campaign',),
        'Benchmark': ('Benchmark',),
        'Campaign_Year': ('Campaign_Year',),
        'Campaign_Quarter': ('Campaign_Quarter',),
        'Period': ('Period',),
        'Market': ('Market',),
        'Region': ('Region',),
        'Zone': ('Zone',),
        'City': ('City',),
        'Operator': ('Operator',),
        'Subscriber': ('Subscriber',),
        'Test_Name': ('Task Name', 'Side1 Call Type'),
    },
    fixed_groups=(
        (('Technology',), _UMLAUT_TECHNOLOGY),
        (('Session_Type',), ('Service', 'Side1 Call Type')),
        (('Call_Status',), ('status',)),
    ),
    nq_field_sources={
        'campaign': ('Campaign',),
        'operator': ('Operator',),
        'operator_vendor': ('Operator_Vendor',),
        'vendor': ('Vendor',),
        'region': ('Region',),
        'cluster': ('Cluster',),
        'city': ('City',),
        'technology': ('Technology', 'technology_primary'),
        'test_name': ('Task Name', 'Side1 Call Type', 'Test_Name'),
        'session_type': ('Service', 'Session_Type'),
        'direction': ('Direction',),
        'result': ('Call_Status', 'status'),
        'start_time': ('event_start_time',),
        'end_time': ('event_end_time',),
        # Umlaut gives no failure hierarchy: the failure it reports is the comment of the call.
        'failure_phase': (),
        'failure_technology': (),
        'failure_classification': (),
        'failure_category': (),
        'failure_subcategory': (),
        'failure_comment': _UMLAUT_FAILURE,
        'host_network': ('Serving_Host_Network',),
        'site_id': ('Serving_Site_ID',),
        'environment': ('umlaut Scoring Infrastructure Type', 'Infrastructure Type Fine'),
        'latitude': _UMLAUT_LATITUDE,
        'longitude': _UMLAUT_LONGITUDE,
        'cell_id': ('ECI',),
    },
    nq_join_sources=(),
    # A data test is its Test_Key; the calls and their speech samples share the Sequence of the call.
    nq_identifier_sources={'data': ('Test_Key',), 'voice': ('Sequence',), 'speech': ('Sequence',)},
    nq_sample_sources=('POLQA Sample TA Start',),
    nq_subscriber_sources=('Subscriber',),
    # An Umlaut call or test is Non-Qualified when its qualifier is NOT QUALIFIED (Ping and DNS have no qualifier).
    nq_qualification_sources=_UMLAUT_QUALIFIERS,
    nq_qualified_value='qualified',
    pci_columns=_by_kind(('Service Access SC/PCI Start',), ('Side1 Call Setup latest available PCI/SC',), ('Side1 Sample Start PCI/SC',)),
    # The averages of a data test, the radio at the setup of the A side of a call (the B side is Side2; the mean of the
    # speech samples of the call replaces it, see nq_call_radio_from_samples) and at the start of a speech sample.
    nq_rca_sources={
        'failure_side': (),
        'failure_events': (),
        'scg_failures': (),
        'lte_rsrp': ('LTE RSRP Avg', 'Side1 Sample Start RSRP (dBm)', 'Side1 Call Setup latest available RSRP (dBm)'),
        'lte_rsrp_min': ('LTE RSRP Min',),
        'lte_rsrq': ('LTE RSRQ Avg',),
        'lte_sinr': ('LTE SINR Avg', 'Side1 Sample Start SINR (dB)', 'Side1 Call Setup latest available SINR (dB)'),
        'lte_sinr_min': ('LTE SINR Min',),
        'lte_tx_power': ('LTE Tx Power Max',),
        'lte_bler': (),
        'nr_rsrp': ('NR PCell SSB Serving Beam RSRP Avg', 'Side1 Sample Start NR PCell SSB RSRP (dBm)',
                    'Side1 Call Setup latest available NR PCell SSB RSRP (dBm)'),
        'nr_rsrp_min': ('NR PCell SSB Serving Beam RSRP Min',),
        'nr_rsrq': ('NR PCell SSB Serving Beam RSRQ Avg',),
        'nr_sinr': ('NR PCell SSB Serving Beam SINR Avg', 'Side1 Sample Start NR PCell SSB SINR (dB)',
                    'Side1 Call Setup latest available NR PCell SSB SINR (dB)'),
        'nr_sinr_min': ('NR PCell SSB Serving Beam SINR Min',),
        'nr_tx_power': (),
        'nr_bler': (),
        'b_lte_rsrp': ('Side2 Sample Start RSRP (dBm)', 'Side2 Call Setup latest available RSRP (dBm)'),
        'b_lte_sinr': ('Side2 Sample Start SINR (dB)', 'Side2 Call Setup latest available SINR (dB)'),
        'b_nr_rsrp': ('Side2 Sample Start NR PCell SSB RSRP (dBm)', 'Side2 Call Setup latest available NR PCell SSB RSRP (dBm)'),
        'b_nr_sinr': ('Side2 Sample Start NR PCell SSB SINR (dB)', 'Side2 Call Setup latest available NR PCell SSB SINR (dB)'),
        'rat': _UMLAUT_TECHNOLOGY,
        'rat_timeline': ('Technology List', 'Side1 Sequence Technology'),
        'handovers': (),
        'handovers_info': (),
        'throughput': ('throughput_mbps',),
        'access_time': ('Service Access Duration [s]',),
        'dns_time': ('DNS Duration [ms]',),
        'dns_success': (),
        'tcp_rtt': ('HTTP RTT First [ms]',),
        'packet_loss': ('TWAMP Packet Loss (%)',),
        'rtt': ('TWAMP RTT Median', 'Ping Duration [ms]'),
        'setup_time': ('setup_time_seconds',),
        'duration': ('duration_seconds',),
        'mos': ('POLQA Value Overall',),
        'rtp_packet_loss': (),
        'jitter': ('jitter_ms',),
    },
    nq_rca_scales={},
    rf_field_aliases={
        'latitude': _by_kind(('Network Access LAT', 'Ping LAT Start', 'DNS LAT Start'), ('Side1 Call Setup LAT',),
                             ('Side1 Sample Start LAT', 'Side2 Sample Start LAT')),
        'longitude': _by_kind(('Network Access LON', 'Ping LON Start', 'DNS LON Start'), ('Side1 Call Setup LON',),
                              ('Side1 Sample Start LON', 'Side2 Sample Start LON')),
        'lte_rsrp': _by_kind(('LTE RSRP Avg',), ('Side1 Call Setup latest available RSRP (dBm)',),
                             ('Side1 Sample Start RSRP (dBm)', 'Side2 Sample Start RSRP (dBm)')),
        'nr_rsrp': _by_kind(('NR PCell SSB Serving Beam RSRP Avg',), ('Side1 Call Setup latest available NR PCell SSB RSRP (dBm)',),
                            ('Side1 Sample Start NR PCell SSB RSRP (dBm)', 'Side2 Sample Start NR PCell SSB RSRP (dBm)')),
        'lte_sinr': _by_kind(('LTE SINR Avg',), ('Side1 Call Setup latest available SINR (dB)',),
                             ('Side1 Sample Start SINR (dB)', 'Side2 Sample Start SINR (dB)')),
        'nr_sinr': _by_kind(('NR PCell SSB Serving Beam SINR Avg',), ('Side1 Call Setup latest available NR PCell SSB SINR (dB)',),
                            ('Side1 Sample Start NR PCell SSB SINR (dB)', 'Side2 Sample Start NR PCell SSB SINR (dB)')),
        'cell_trace': _by_kind(),
        'cell_ids': _by_kind(('ECI',), ('ECI',), ('ECI',)),
        'enodeb_id': _by_kind(),
        'earfcn': _by_kind((), ('Side1 Call Setup latest available Carrier',), ('Side1 Sample Start Carrier',)),
        'nr_band': _by_kind(('NR PCell Service Band DL Most',)),
        'lte_bandwidth': _by_kind(),
        'nr_bandwidth': _by_kind(('NR PCell Bandwidth DL Most', 'NR PCell Bandwidth Most')),
        'lte_aggregated_bandwidth': _by_kind(),
        'test_name': _by_kind(('Task Name',)),
        'nr_time': _by_kind(),
        'test_duration': _by_kind(('Session Duration [s]', 'Transfer Duration [s]')),
        'nr_pci': _by_kind(('NR PCell Service PCI Most',)),
        'nr_arfcn': _by_kind(('NR PCell Service SSB ARFCN Most',)),
        'lte_rank': _by_kind(),
        'nr_rank': _by_kind(),
        'nr_layers': _by_kind(),
        'test_result': _by_kind(('Call_Status',)),
        'type_of_test': _by_kind(('Service',)),
        'mean_data_rate': _by_kind(('throughput_mbps',)),
        'rtt_median': _by_kind(('TWAMP RTT Median', 'Ping Duration [ms]')),
        'packets_lost': _by_kind(),
        'packets_sent': _by_kind(),
        'jitter': _by_kind(('TWAMP Packet Delay Variation Median', 'jitter_ms')),
        'serving_network': _by_kind(('Serving_Network',), ('Serving_Network',), ('Serving_Network',)),
        'serving_host': _by_kind(('Serving_Host_Network',), ('Serving_Host_Network',), ('Serving_Host_Network',)),
        'serving_scenario': _by_kind(('Serving_eMOCN_Scenario',), ('Serving_eMOCN_Scenario',), ('Serving_eMOCN_Scenario',)),
    },
    dimension_aliases={
        'operator': ('Operator',),
        'operator_vendor': ('Operator_Vendor',),
        'vendor': ('Vendor',),
        'campaign': ('Campaign', 'Period'),
        'region': ('Region',),
        'cluster': ('Cluster',),
        'city': ('City',),
        # The umlaut scoring environment (cities, towns, roads) and the finer one of the route.
        'environment': ('umlaut Scoring Infrastructure Type',),
        'environment_route': ('Infrastructure Type Fine',),
        'mode': ('Mobility',),
        'source_sheet': ('source_sheet',),
    },
    cell_columns=('ECI',),
    start_coordinates={
        'data': _UMLAUT_DATA_POSITIONS,
        'voice': (('Side1 Call Setup LON', 'Side1 Call Setup LAT'),),
        'speech': (('Side1 Sample Start LON', 'Side1 Sample Start LAT'), ('Side2 Sample Start LON', 'Side2 Sample Start LAT')),
    },
    end_coordinates={
        'data': (('Session LON End', 'Session LAT End'), ('Video Session LON End', 'Video Session LAT End')),
        'voice': (('Side1 Call End LON', 'Side1 Call End LAT'),),
    },
    time_columns=(*umlaut_cdr.START_TIME_COLUMNS, 'event_start_time', 'Date'),
    area_fields={'City': ('City',), 'Region': ('Region',), 'Cluster': ('Cluster',)},
    coordinate_sources={
        'data': tuple((latitude, longitude) for longitude, latitude in _UMLAUT_DATA_POSITIONS),
        'voice': (('Side1 Call Setup LAT', 'Side1 Call Setup LON'),),
        'speech': (('Side1 Sample Start LAT', 'Side1 Sample Start LON'), ('Side2 Sample Start LAT', 'Side2 Sample Start LON')),
    },
    environment_columns=('Mobility', 'umlaut Scoring Infrastructure Type', 'Infrastructure Type Fine'),
    side_header_pattern=umlaut_cdr.SIDE_HEADER_PATTERN,
    derive_columns=umlaut_cdr.derive_columns,
    normalised_scales={'throughput_mbps': 0.001},
    status_values={'success': 'Completed', 'failed': 'Failed', 'dropped': 'Dropped',
                   'qualified': 'Completed', 'not qualified': 'Failed'},
    summary_name_words=umlaut_cdr.SUMMARY_NAME_WORDS,
    nq_call_radio_from_samples=('lte_rsrp', 'lte_sinr', 'nr_rsrp', 'nr_sinr', 'b_lte_rsrp', 'b_lte_sinr', 'b_nr_rsrp', 'b_nr_sinr'),
    nq_definition='whose Umlaut qualifier is NOT QUALIFIED (failed, dropped or below the quality thresholds of Umlaut)',
)

FIELD_PROFILES: dict[str, CdrFieldProfile] = {'netcheck': NETCHECK_PROFILE, 'umlaut': UMLAUT_PROFILE}


def field_profile(cdr_type: object = DEFAULT_CDR_TYPE) -> CdrFieldProfile:
    """The field profile of a CDR type; a type without its own profile yet reads as NetCheck."""
    key = str(cdr_type or '').strip().casefold()
    return FIELD_PROFILES.get(key, NETCHECK_PROFILE)


def workspace_field_profile(repository: Any) -> CdrFieldProfile:
    """The field profile of the CDR type of a workspace, with the fields its CDR Field Dictionary changes."""
    from src.modules import cdr_field_dictionary

    return cdr_field_dictionary.apply_overrides(field_profile(workspace_cdr_type(repository)),
                                                cdr_field_dictionary.load_overrides(repository))
