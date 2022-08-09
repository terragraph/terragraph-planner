# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import Counter, Dict, List, NamedTuple, Optional, Set, Tuple

import pandas as pd

from terragraph_planner.common.configuration.enums import (
    LinkType,
    SectorType,
    SiteType,
)
from terragraph_planner.common.topology_models.topology import Topology

# (i, j, k) means a pair of link (i, j) and link (i, k) where i, j, k are site ids
LinkPair = Tuple[str, str, str]


class MetricStatistics(NamedTuple):
    avg: float
    max: float
    min: float


class AvailabilityMetrics(NamedTuple):
    avg: float
    percentiles: Dict[int, float]


class AngleViolatingLinkPairs(NamedTuple):
    diff_sector_list: List[LinkPair]
    near_far_list: List[LinkPair]


class Capex(NamedTuple):
    total_capex: float
    proposed_capex: float


class ComponentCounts(NamedTuple):
    site_counts_by_type: Dict[SiteType, int]
    site_counts_by_sku: Counter[str]
    node_counts_by_type: Dict[SectorType, int]
    sector_counts_by_type: Dict[SectorType, int]
    link_counts_by_type: Dict[LinkType, int]
    link_counts_by_channel: Counter[int]
    demand_connected_sites_by_type: Dict[SiteType, int]
    dn_sectors_on_pops: int


class FailureDisruption(NamedTuple):
    edge_fail_effect: MetricStatistics
    pop_fail_effect: MetricStatistics
    dn_fail_effect: MetricStatistics


class DemandMetrics(NamedTuple):
    number_of_demands: int
    number_of_disconnected_demands: int
    number_of_demands_connected_to_pops: int
    number_of_demands_with_disjoint_path: int
    percentage_of_demand_with_disjoint_path: float
    total_demand: float
    total_demand_oversubscribed: float


class DisjointPath(NamedTuple):
    demand_with_disjoint_paths: Set[str]
    disconnected_demand_locations: Set[str]
    demand_connected_to_pop: Set[str]


class FlowSolution(NamedTuple):
    flow_decisions: Dict[Tuple[str, str], float]
    tdm_decisions: Dict[Tuple[str, str], float]
    buffer_decision: float
    connected_demand_sites: Set[str]


class FlowMetrics(NamedTuple):
    total_bandwidth: float
    minimum_bandwdith_for_connected_demand: float
    link_capacity_utilization: MetricStatistics


class LinkMetrics(NamedTuple):
    active_count: int
    links_per_sector: MetricStatistics
    link_dist: MetricStatistics


class OptimizationSolution(NamedTuple):
    site_decisions: Dict[str, int]
    sector_decisions: Dict[Tuple[str, str], int]
    link_decisions: Dict[Tuple[str, str], int]
    odd_site_decisions: Dict[str, int]
    even_site_decisions: Dict[str, int]
    channel_decisions: Dict[Tuple[str, str], int]
    flow_decisions: Dict[Tuple[str, str], float]
    tdm_decisions: Dict[Tuple[str, str], float]
    shortage_decisions: Dict[str, float]
    objective_value: float
    cost: int


class RedundancyParams(NamedTuple):
    pop_node_capacity: int
    dn_node_capacity: int
    sink_node_capacity: int


class RedundancySolution(NamedTuple):
    site_decisions: Dict[str, int]
    sector_decisions: Dict[Tuple[str, str], int]
    link_decisions: Dict[Tuple[str, str], int]
    odd_site_decisions: Dict[str, int]
    even_site_decisions: Dict[str, int]
    channel_decisions: Dict[Tuple[str, str], int]
    flow_decisions: Dict[Tuple[str, str, str], float]
    shortage_decisions: Dict[str, float]
    objective_value: float
    cost: int


class RoutingSolution(NamedTuple):
    flow_solution: FlowSolution
    active_link_utilization: Dict[Tuple[str, str], float]


class TopologyCounts(NamedTuple):
    active_sites: int
    total_sites: int
    active_pop_sites: int
    total_pop_sites: int
    active_dn_sites: int
    total_dn_sites: int
    active_cn_sites: int
    connectable_dn_sites: int
    connectable_cn_sites: int
    total_cn_sites: int
    active_cns_with_backup_dns: int
    active_demand_connected_pop_sites: int
    active_demand_connected_dn_sites: int
    active_demand_connected_cn_sites: int
    active_nodes: int
    total_nodes: int
    active_dn_nodes: int
    total_dn_nodes: int
    active_cn_nodes: int
    total_cn_nodes: int
    active_sectors: int
    total_sectors: int
    active_dn_sectors_on_pops: int
    active_dn_sectors_on_dns: int
    active_cn_sectors: int
    active_backhaul_links: int
    total_backhaul_links: int
    active_access_links: int
    total_access_links: int
    active_wired_links: int
    total_wired_links: int


class TopologyMetrics(NamedTuple):
    capex: Capex
    counts: TopologyCounts
    active_site_sku_counter: Dict[str, int]
    channel_occupancy_counter: Dict[int, int]
    demand_metrics: DemandMetrics
    flow_metrics: Optional[FlowMetrics]
    backhaul_link: LinkMetrics
    access_link: LinkMetrics
    backhaul_mcs: Counter[int]
    access_mcs: Counter[int]
    availability_metrics: AvailabilityMetrics
    failure_disruption: FailureDisruption
    diff_sector_link_violations: int
    near_far_link_violations: int
    sector_link_limit_violations: int


class AnalysisResult(NamedTuple):
    topology: Topology
    link_df: pd.DataFrame
    site_df: pd.DataFrame
    sector_df: pd.DataFrame
    metrics: TopologyMetrics
