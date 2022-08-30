# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import math
import os
from collections import Counter, defaultdict
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple

import numpy as np
import pandas as pd
import yaml
from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import (
    LinkType,
    OutputFile,
    SectorType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.data_io.data_key import (
    LinkKey,
    SectorKey,
    SiteKey,
)
from terragraph_planner.common.data_io.topology_serializer import (
    dump_topology_to_kml,
)
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.common.utils import current_system_params
from terragraph_planner.optimization.constants import (
    EPSILON,
    MAX_LINK_BUDGET_ITERATIONS,
    SUPERSOURCE,
    UNASSIGNED_CHANNEL,
)
from terragraph_planner.optimization.deployment_rules import (
    find_angle_violating_link_pairs,
    find_sector_limit_violations,
    get_violating_link_ids,
)
from terragraph_planner.optimization.ilp_models.flow_optimization import (
    MaxFlowNetwork,
)
from terragraph_planner.optimization.structs import (
    AnalysisResult,
    AngleViolatingLinkPairs,
    AvailabilityMetrics,
    Capex,
    DemandMetrics,
    DisjointPath,
    FailureDisruption,
    FlowMetrics,
    LinkMetrics,
    MetricStatistics,
    RoutingSolution,
    TopologyCounts,
    TopologyMetrics,
)
from terragraph_planner.optimization.topology_availability import (
    compute_availability,
)
from terragraph_planner.optimization.topology_component_counter import (
    count_topology_components,
)
from terragraph_planner.optimization.topology_networkx import (
    build_digraph,
    disjoint_paths,
    get_topology_routing_results,
    single_edge_failures,
    single_site_failures,
)
from terragraph_planner.optimization.topology_operations import (
    compute_capex,
    hops_from_pops,
    update_link_caps_with_sinr,
)

logger: logging.Logger = logging.getLogger(__name__)


def analyze_with_dump(
    topology: Topology, params: OptimizerParams
) -> AnalysisResult:
    result = analyze(topology, params)
    dump_topology_to_kml(result.topology, OutputFile.REPORTING_TOPOLOGY)
    dump_df_to_csv(result.link_df, OutputFile.LINK)
    dump_df_to_csv(result.site_df, OutputFile.SITE)
    dump_df_to_csv(result.sector_df, OutputFile.SECTOR)
    dump_metrics_to_yaml(result.metrics)
    return result


def analyze(
    topology: Topology,
    params: OptimizerParams,
) -> AnalysisResult:
    """
    This function analyzes a topology for report.
    """
    proposed_graph = build_digraph(topology, StatusType.active_status())

    # Compute optimal flow in the network
    if params.topology_routing is None:
        flow_solution = get_routing_flow_solution(topology, params)
    else:
        routing_links = get_topology_routing_results(
            topology, proposed_graph, params.topology_routing
        )
        get_routing_topology(topology, routing_links)
        flow_solution = get_routing_flow_solution(topology, params)

    # Compute disjoint paths
    disjoint = disjoint_paths(topology, proposed_graph)

    # Compute edge/site failure disruptions
    edge_failure_disruptions = single_edge_failures(proposed_graph)
    pop_failure_disruptions, dn_failure_disruptions = single_site_failures(
        proposed_graph
    )

    # Compute availability statistics
    if params.availability_sim_time > 0:
        seed = (
            params.availability_seed if params.availability_seed >= 0 else None
        )
        max_time = params.availability_max_time * 60
        availability, _ = compute_availability(
            proposed_graph,
            params.link_availability_percentage,
            params.availability_sim_time,
            max_time,
            seed,
        )
    else:
        availability = {}

    # Find link and sector violations
    violating_links = find_angle_violating_link_pairs(
        topology,
        params.diff_sector_angle_limit,
        params.near_far_angle_limit,
        params.near_far_length_ratio,
        active_components=True,
    )

    violating_sectors = find_sector_limit_violations(
        topology, params.dn_dn_sector_limit, params.dn_total_sector_limit
    )

    metrics = get_topology_metrics(
        topology=topology,
        params=params,
        routing_solution=flow_solution,
        disjoint_paths=disjoint,
        edge_failure_disruptions=edge_failure_disruptions,
        pop_failure_disruptions=pop_failure_disruptions,
        dn_failure_disruptions=dn_failure_disruptions,
        availability=availability,
        violating_links=violating_links,
        violating_sectors=violating_sectors,
    )

    add_statistics_to_topology(
        topology=topology,
        routing_solution=flow_solution,
        edge_failure_disruptions=edge_failure_disruptions,
        pop_failure_disruptions=pop_failure_disruptions,
        dn_failure_disruptions=dn_failure_disruptions,
    )

    total_active_links = (
        metrics.counts.active_backhaul_links
        + metrics.counts.active_access_links
        + metrics.counts.active_wired_links
    )
    if total_active_links > 0:
        link_df = build_links_df(
            topology,
            violating_links,
            violating_sectors,
        )
    else:
        link_df = pd.DataFrame()

    site_type_to_cost = {
        SiteType.POP: params.pop_site_capex,
        SiteType.DN: params.dn_site_capex,
        SiteType.CN: params.cn_site_capex,
    }
    if metrics.counts.active_sites > 0:
        site_df = build_sites_df(
            topology,
            site_type_to_cost,
        )
    else:
        site_df = pd.DataFrame()

    if metrics.counts.active_sectors > 0:
        sector_df = build_sectors_df(topology, violating_sectors)
    else:
        sector_df = pd.DataFrame()

    return AnalysisResult(topology, link_df, site_df, sector_df, metrics)


def get_routing_flow_solution(
    topology: Topology, params: OptimizerParams
) -> Optional[RoutingSolution]:
    """
    Calculate maximum flow solution and active link utilization.
    """
    update_link_caps_with_sinr(topology, params, MAX_LINK_BUDGET_ITERATIONS)
    flow_solution = MaxFlowNetwork(topology, params).solve()
    if flow_solution is None:
        return None
    flows = {}
    active_link_utilization = {}

    # Most links in topology are bi-directional (i.e. all DN-DN links).
    # However, in our reports we show one value per physical link.
    for link in topology.links.values():
        link_key = (link.tx_site.site_id, link.rx_site.site_id)
        flow_val = flow_solution.flow_decisions.get(link_key, 0)
        flows[link_key] = flow_val
        rev_link_key = (link.rx_site.site_id, link.tx_site.site_id)

        # For active bi-directional links, one flow should be 0 and the other
        # might not be. Store the non-zero value in active_link_utilization.
        # If they are both 0, store just one (does not matter which)
        if link.status_type in StatusType.active_status():
            util = flow_val / link.capacity if link.capacity > 0 else 0
            percent_capacity = 100 * util
            active_link_utilization[link_key] = percent_capacity
            if rev_link_key in active_link_utilization:
                rev_percent_capacity = active_link_utilization[rev_link_key]
                if math.isclose(
                    percent_capacity, 0, abs_tol=EPSILON
                ) or math.isclose(rev_percent_capacity, 0, abs_tol=EPSILON):
                    if percent_capacity > rev_percent_capacity:
                        active_link_utilization.pop(rev_link_key)
                    else:
                        active_link_utilization.pop(link_key)
                else:
                    logger.warning(
                        "Something is wonky with flow optimization: "
                        "both bidirectional links have non-zero flow."
                    )

    return RoutingSolution(
        flow_solution=flow_solution,
        active_link_utilization=active_link_utilization,
    )


def get_routing_topology(topology: Topology, route_links: Set[str]) -> None:
    """
    This function creates a modified topology of links that are in links_used
    """
    for link_id, link in topology.links.items():
        reverse_link = topology.get_link_by_site_ids(
            link.rx_site.site_id, link.tx_site.site_id
        )
        if link_id not in route_links and (
            reverse_link is None or reverse_link.link_id not in route_links
        ):
            link.is_redundant = True


def add_statistics_to_topology(
    topology: Topology,
    routing_solution: Optional[RoutingSolution],
    edge_failure_disruptions: Dict[Tuple[str, str], Set[str]],
    pop_failure_disruptions: Dict[str, Set[str]],
    dn_failure_disruptions: Dict[str, Set[str]],
) -> None:
    """
    This function stores the componenet statistics to topology.
    @param topology: The Topology object.
    @param graph: The networkx graph based on the topology.
    @param routing_solution: The maximum flow solution based on routing selection.
    """
    for link in topology.links.values():
        if link.status_type in StatusType.active_status():
            link_key = (link.tx_site.site_id, link.rx_site.site_id)
            link.proposed_flow = (
                routing_solution.flow_solution.flow_decisions.get(link_key, 0.0)
                if routing_solution
                else 0.0
            )
            link.utilization = (
                routing_solution.active_link_utilization.get(link_key, 0.0)
                if routing_solution
                else 0.0
            )
            link.breakdowns = len(edge_failure_disruptions.get(link_key, []))

    for site in topology.sites.values():
        site.breakdowns = (
            len(pop_failure_disruptions.get(site.site_id, []))
            if site.site_type == SiteType.POP
            else len(dn_failure_disruptions.get(site.site_id, []))
            if site.site_type == SiteType.DN
            else 0
        )


def get_topology_metrics(
    topology: Topology,
    params: OptimizerParams,
    routing_solution: Optional[RoutingSolution],
    disjoint_paths: DisjointPath,
    edge_failure_disruptions: Dict[Tuple[str, str], Set[str]],
    pop_failure_disruptions: Dict[str, Set[str]],
    dn_failure_disruptions: Dict[str, Set[str]],
    availability: Dict[str, float],
    violating_links: AngleViolatingLinkPairs,
    violating_sectors: Dict[str, List[str]],
) -> TopologyMetrics:
    """
    Calculate topology metrics for report.
    """
    capex = compute_capex(topology, params)
    (
        component_counts,
        active_site_sku_counter,
        channel_occupancy_counter,
    ) = count_topology_components(topology)

    # Add demand metrics
    number_of_demands = len(topology.demand_sites)
    number_of_disconnected_demands = len(
        disjoint_paths.disconnected_demand_locations
    )
    number_of_demands_connected_to_pops = len(
        disjoint_paths.demand_connected_to_pop
    )
    number_of_demands_with_disjoint_path = len(
        disjoint_paths.demand_with_disjoint_paths
    )
    if (
        number_of_demands == 0
        or number_of_demands_connected_to_pops >= number_of_demands
    ):
        percentage_of_demand_with_disjoint_path = 0
    else:
        dems_nonzero_hops_away = (
            number_of_demands - number_of_demands_connected_to_pops
        )
        percentage_of_demand_with_disjoint_path = 100 * (
            number_of_demands_with_disjoint_path / dems_nonzero_hops_away
        )
    total_demand = sum(
        d.demand * d.num_sites
        for d in topology.demand_sites.values()
        if d.demand is not None
    )
    demand_metrics = DemandMetrics(
        number_of_demands=number_of_demands,
        number_of_disconnected_demands=number_of_disconnected_demands,
        number_of_demands_connected_to_pops=number_of_demands_connected_to_pops,
        number_of_demands_with_disjoint_path=number_of_demands_with_disjoint_path,
        percentage_of_demand_with_disjoint_path=percentage_of_demand_with_disjoint_path,
        total_demand=total_demand,
        total_demand_oversubscribed=total_demand / params.oversubscription,
    )
    if routing_solution is not None:
        active_link_utilization = (
            routing_solution.active_link_utilization.values()
        )
        flow_solution = routing_solution.flow_solution
        flow_metrics = FlowMetrics(
            total_bandwidth=flow_solution.buffer_decision
            * len(flow_solution.connected_demand_sites),
            minimum_bandwdith_for_connected_demand=flow_solution.buffer_decision,
            link_capacity_utilization=MetricStatistics(
                avg=sum(active_link_utilization) / len(active_link_utilization),
                max=max(active_link_utilization),
                min=min(active_link_utilization),
            ),
        )
    else:
        flow_metrics = None

    # Add flow metrics
    backhaul_link_dist = [
        link.distance
        for link in topology.links.values()
        if link.link_type == LinkType.WIRELESS_BACKHAUL
        and link.status_type in StatusType.active_status()
    ]
    access_link_dist = [
        link.distance
        for link in topology.links.values()
        if link.link_type == LinkType.WIRELESS_ACCESS
        and link.status_type in StatusType.active_status()
    ]

    active_backhaul_links_by_dn_sector = {
        s.sector_id: set()
        for s in topology.sectors.values()
        if s.sector_type == SectorType.DN
        and s.status_type in StatusType.active_status()
    }
    active_access_links_by_dn_sector = {
        s.sector_id: set()
        for s in topology.sectors.values()
        if s.sector_type == SectorType.DN
        and s.status_type in StatusType.active_status()
    }
    for link in topology.links.values():
        if link.status_type in StatusType.active_status():
            tx_sector = none_throws(link.tx_sector)
            rx_sector = none_throws(link.rx_sector)

            # The pair of bi-direction backhaul links have the same 'link_hash'
            # and they would be counted as 1 per sector
            if link.link_type == LinkType.WIRELESS_BACKHAUL:
                active_backhaul_links_by_dn_sector[tx_sector.sector_id].add(
                    link.link_hash
                )
                active_backhaul_links_by_dn_sector[rx_sector.sector_id].add(
                    link.link_hash
                )
            elif link.link_type == LinkType.WIRELESS_ACCESS:
                active_access_links_by_dn_sector[tx_sector.sector_id].add(
                    link.link_hash
                )
    dn_sector_active_backhaul_links = [
        len(v) for v in active_backhaul_links_by_dn_sector.values()
    ]
    dn_sector_active_access_links = [
        len(v) for v in active_access_links_by_dn_sector.values()
    ]

    active_dn_sectors = (
        component_counts.active_dn_sectors_on_pops
        + component_counts.active_dn_sectors_on_dns
    )

    avg_backhaul_links_per_sector = (
        sum(dn_sector_active_backhaul_links) / active_dn_sectors
        if active_dn_sectors > 0
        else 0.0
    )
    max_backhaul_links_per_sector = (
        max(dn_sector_active_backhaul_links)
        if len(dn_sector_active_backhaul_links) > 0
        else 0
    )
    min_backhaul_links_per_sector = (
        min(dn_sector_active_backhaul_links)
        if len(dn_sector_active_backhaul_links) > 0
        else 0
    )
    avg_access_links_per_sector = (
        sum(dn_sector_active_access_links) / active_dn_sectors
        if active_dn_sectors > 0
        else 0.0
    )
    max_access_links_per_sector = (
        max(dn_sector_active_access_links)
        if len(dn_sector_active_access_links) > 0
        else 0
    )
    min_access_links_per_sector = (
        min(dn_sector_active_access_links)
        if len(dn_sector_active_access_links) > 0
        else 0
    )

    backhaul_link = LinkMetrics(
        active_count=component_counts.active_backhaul_links,
        links_per_sector=MetricStatistics(
            avg=avg_backhaul_links_per_sector,
            max=max_backhaul_links_per_sector,
            min=min_backhaul_links_per_sector,
        ),
        link_dist=MetricStatistics(
            avg=sum(backhaul_link_dist) / len(backhaul_link_dist)
            if len(backhaul_link_dist) > 0
            else 0,
            max=max(backhaul_link_dist) if len(backhaul_link_dist) > 0 else 0,
            min=min(backhaul_link_dist) if len(backhaul_link_dist) > 0 else 0,
        ),
    )
    access_link = LinkMetrics(
        active_count=component_counts.active_access_links,
        links_per_sector=MetricStatistics(
            avg=avg_access_links_per_sector,
            max=max_access_links_per_sector,
            min=min_access_links_per_sector,
        ),
        link_dist=MetricStatistics(
            avg=sum(access_link_dist) / len(access_link_dist)
            if len(access_link_dist) > 0
            else 0,
            max=max(access_link_dist) if len(access_link_dist) > 0 else 0,
            min=min(access_link_dist) if len(access_link_dist) > 0 else 0,
        ),
    )

    backhaul_link_mcs = {}
    access_link_mcs = {}
    for link in topology.links.values():
        if link.status_type not in StatusType.active_status():
            continue
        if link.link_type == LinkType.WIRELESS_BACKHAUL:
            backhaul_link_mcs[link.sorted_site_ids] = link.mcs_level
        elif link.link_type == LinkType.WIRELESS_ACCESS:
            access_link_mcs[link.sorted_site_ids] = link.mcs_level
    backhaul_mcs = Counter(sorted(backhaul_link_mcs.values()))
    access_mcs = Counter(sorted(access_link_mcs.values()))

    # Add failure disruption
    edge_failures = [len(v) for v in edge_failure_disruptions.values()]
    edge_fail_effect = MetricStatistics(
        avg=sum(edge_failures) / len(edge_failures)
        if len(edge_failures) > 0
        else 0,
        max=max(edge_failures) if len(edge_failures) > 0 else 0,
        min=min(edge_failures) if len(edge_failures) > 0 else 0,
    )

    pop_failures = [len(v) for v in pop_failure_disruptions.values()]
    pop_fail_effect = MetricStatistics(
        avg=sum(pop_failures) / component_counts.active_pop_sites,
        max=max(pop_failures) if len(pop_failures) > 0 else 0,
        min=min(pop_failures)
        if len(pop_failures) > 0
        and len(pop_failures) == component_counts.active_pop_sites
        else 0,
    )
    dn_failures = [len(v) for v in dn_failure_disruptions.values()]
    dn_fail_effect = MetricStatistics(
        avg=sum(dn_failures) / component_counts.active_dn_sites
        if component_counts.active_dn_sites > 0
        else 0,
        max=max(dn_failures) if len(dn_failures) > 0 else 0,
        min=min(dn_failures)
        if len(dn_failures) > 0
        and len(dn_failures) == component_counts.active_dn_sites
        else 0,
    )
    failure_disruption = FailureDisruption(
        edge_fail_effect=edge_fail_effect,
        pop_fail_effect=pop_fail_effect,
        dn_fail_effect=dn_fail_effect,
    )

    # Average availability
    availability_vals = np.array(list(availability.values()), dtype=float)
    avg_availability = (
        100.0 * float(np.mean(availability_vals))
        if len(availability_vals) > 0
        else 0
    )
    percentiles = [0, 25, 50, 75, 100]
    availability_numbers = {
        p: 100.0 * float(np.percentile(availability_vals, p))
        if len(availability_vals) > 0
        else 0
        for p in percentiles
    }
    availability_metrics = AvailabilityMetrics(
        avg=avg_availability, percentiles=availability_numbers
    )

    return TopologyMetrics(
        capex=capex,
        counts=component_counts,
        channel_occupancy_counter=channel_occupancy_counter,
        active_site_sku_counter=active_site_sku_counter,
        demand_metrics=demand_metrics,
        flow_metrics=flow_metrics,
        backhaul_link=backhaul_link,
        access_link=access_link,
        backhaul_mcs=backhaul_mcs,
        access_mcs=access_mcs,
        availability_metrics=availability_metrics,
        failure_disruption=failure_disruption,
        diff_sector_link_violations=len(violating_links.diff_sector_list),
        near_far_link_violations=len(violating_links.near_far_list),
        sector_link_limit_violations=len(violating_sectors),
    )


def build_links_df(
    topology: Topology,
    violating_links: AngleViolatingLinkPairs,
    violating_sectors: Dict[str, List[str]],
) -> pd.DataFrame:
    """
    A function for building a pandas dataframe storing reported info about all
    links being reported on.
    """

    def _get_sector_identifier(link: Link) -> str:
        if link.link_type == LinkType.ETHERNET:
            return "WIRED CONNECTION"
        if link.tx_sector is None or link.rx_sector is None:
            return "UNKNOWN"
        return f"{link.tx_sector.sector_id} --> {link.rx_sector.sector_id}"

    diff_sector_violating_links = get_violating_link_ids(
        topology, violating_links.diff_sector_list
    )
    near_far_violating_links = get_violating_link_ids(
        topology, violating_links.near_far_list
    )
    # initialize our columns and dataframe before populating it
    raw_links = {}
    for link_id, link in topology.links.items():
        link_keys = {}
        for link_key in LinkKey.csv_output_keys():
            output_name, output_value = link_key.get_output_name_and_value(
                link, digits_for_float=2, xml_output=False
            )
            if link_key == LinkKey.SECTORS:
                output_value = _get_sector_identifier(link)
            elif link_key == LinkKey.CHANNEL:
                output_value = (
                    str(link.link_channel)
                    if link.link_channel > UNASSIGNED_CHANNEL
                    else "UNASSIGNED"
                )
            elif link_key == LinkKey.VIOLATES_DIFF_SECTOR_ANGLE:
                output_value = link.link_id in diff_sector_violating_links
            elif link_key == LinkKey.VIOLATES_NEAR_FAR:
                output_value = link_id in near_far_violating_links
            elif link_key == LinkKey.VIOLATES_SECTOR_LIMIT:
                output_value = (
                    link.tx_sector is not None
                    and link.tx_sector.sector_id in violating_sectors
                )
            link_keys[output_name] = output_value
        raw_links[link_id] = link_keys

    # links here are problematic, they are doubles between sites.
    list_of_series = [pd.Series(raw_links[i]) for i in raw_links]
    links_df = pd.DataFrame(list_of_series).set_index(
        LinkKey.LINK_GEOHASH.value.output_name
    )

    return links_df


def build_sectors_df(
    topology: Topology, violating_sectors: Dict[str, List[str]]
) -> pd.DataFrame:
    """
    A function for building a pandas dataframe storing reported info about all
    sectors being reported on.
    """
    # initialize our columns and dataframe before populating it
    active_backhaul_links_per_sector = {
        s.sector_id: set() for s in topology.sectors.values()
    }
    active_access_links_per_sector = {
        s.sector_id: set() for s in topology.sectors.values()
    }
    for link in topology.links.values():
        if link.status_type in StatusType.active_status():
            if link.link_type == LinkType.WIRELESS_BACKHAUL:
                active_backhaul_links_per_sector[
                    none_throws(link.tx_sector).sector_id
                ].add(link.link_hash)
                active_backhaul_links_per_sector[
                    none_throws(link.rx_sector).sector_id
                ].add(link.link_hash)
            elif link.link_type == LinkType.WIRELESS_ACCESS:
                active_access_links_per_sector[
                    none_throws(link.tx_sector).sector_id
                ].add(link.link_hash)
                active_access_links_per_sector[
                    none_throws(link.rx_sector).sector_id
                ].add(link.link_hash)
    raw_sectors = {}
    for sector_id, sector in topology.sectors.items():
        if sector.status_type in StatusType.active_status():
            sector_keys = {}
            for sector_key in SectorKey.csv_output_keys():
                (
                    output_name,
                    output_value,
                ) = sector_key.get_output_name_and_value(
                    sector, digits_for_float=1, xml_output=False
                )

                if sector_key == SectorKey.CHANNEL:
                    output_value = (
                        str(sector.channel)
                        if sector.channel > UNASSIGNED_CHANNEL
                        else "UNASSIGNED"
                    )
                elif sector_key == SectorKey.ACTIVE_BACKHAUL_LINKS:
                    output_value = len(
                        active_backhaul_links_per_sector[sector_id]
                    )
                elif sector_key == SectorKey.ACTIVE_ACCESS_LINKS:
                    output_value = len(
                        active_access_links_per_sector[sector_id]
                    )
                elif sector_key == SectorKey.VIOLATES_LINK_LOAD:
                    output_value = sector_id in violating_sectors
                sector_keys[output_name] = output_value
            raw_sectors[sector_id] = sector_keys

    list_of_series = [pd.Series(raw_sectors[i]) for i in raw_sectors]
    sectors_df = pd.DataFrame(list_of_series).set_index(
        SectorKey.SECTOR_ID.value.output_name
    )

    numeric_cols = [
        SectorKey.AZIMUTH_ORIENTATION.value.output_name,
    ]
    sectors_df[numeric_cols] = sectors_df[numeric_cols].astype(np.float32)
    return sectors_df


def site_flow_statistics(
    topology: Topology,
) -> Dict[str, Dict[str, float]]:
    """
    Calculate outgoing/incoming flow for each site
    """
    site_flow = defaultdict(lambda: {"incoming": 0.0, "outgoing": 0.0})
    for link in topology.links.values():
        if link.status_type not in StatusType.active_status():
            continue
        if link.tx_site.site_id is SUPERSOURCE:
            continue
        if link.rx_site.site_id in topology.demand_sites:
            continue
        site_flow[link.tx_site.site_id]["outgoing"] += link.proposed_flow
        site_flow[link.rx_site.site_id]["incoming"] += link.proposed_flow
    return site_flow


def build_sites_df(
    topology: Topology, site_type_to_cost: Dict[SiteType, float]
) -> pd.DataFrame:
    """
    A function for building a pandas dataframe storing reported info about all
    sites being reported on.
    """
    active_nodes_per_site = {s.site_id: set() for s in topology.sites.values()}
    active_sectors_per_site = {
        s.site_id: set() for s in topology.sites.values()
    }
    for sector in topology.sectors.values():
        if sector.status_type in StatusType.active_status():
            active_nodes_per_site[sector.site.site_id].add(sector.node_id)
            active_sectors_per_site[sector.site.site_id].add(sector.sector_id)
    active_links_per_site = {s.site_id: set() for s in topology.sites.values()}
    for link in topology.links.values():
        if (
            link.status_type in StatusType.active_status()
            and link.link_type != LinkType.ETHERNET
        ):
            active_links_per_site[link.tx_site.site_id].add(link.link_hash)
            active_links_per_site[link.rx_site.site_id].add(link.link_hash)

    hop_counts = hops_from_pops(
        topology, status_filter=StatusType.active_status()
    )
    site_flow = site_flow_statistics(topology)
    # initialize our columns and dataframe before populating it
    raw_sites = {}
    for site_id, site in topology.sites.items():
        site_keys = {}
        for site_key in SiteKey.csv_output_keys():
            if site_key in {
                SiteKey.LATITUDE,
                SiteKey.LONGITUDE,
                SiteKey.ALTITUDE,
            }:
                output_name, output_value = site_key.get_output_name_and_value(
                    site,
                    digits_for_float=6,
                    xml_output=False,
                )
            else:
                output_name, output_value = site_key.get_output_name_and_value(
                    site,
                    digits_for_float=1,
                    xml_output=False,
                )
            if site_key == SiteKey.SITE_CAPEX:
                output_value = site_type_to_cost[site.site_type]
            elif site_key == SiteKey.ACTIVE_NODES:
                output_value = len(active_nodes_per_site[site_id])
            elif site_key == SiteKey.ACTIVE_SECTORS:
                output_value = len(active_sectors_per_site[site_id])
            elif site_key == SiteKey.ACTIVE_LINKS:
                output_value = len(active_links_per_site[site_id])
            elif site_key == SiteKey.HOPS_TO_NEAREST_POP:
                output_value = hop_counts.get(site_id, "disconnected")
            elif site_key == SiteKey.OUTGOING_FLOW:
                output_value = site_flow.get(site.site_id, {}).get(
                    "outgoing", 0
                )
            elif site_key == SiteKey.INCOMING_FLOW:
                output_value = site_flow.get(site.site_id, {}).get(
                    "incoming", 0
                )
            site_keys[output_name] = output_value
        raw_sites[site_id] = site_keys

    names_exist = len(
        [site.site_id for site in topology.sites.values() if site.name]
    )
    if names_exist > 0:
        for site in topology.sites.values():
            raw_sites[site.site_id][SiteKey.NAME.value.output_name] = site.name

    series_list = [pd.Series(raw_sites[i]) for i in raw_sites]
    sites_df = pd.DataFrame(series_list)
    sites_df.fillna(0, inplace=True)

    numeric_cols = [
        SiteKey.LATITUDE.value.output_name,
        SiteKey.LONGITUDE.value.output_name,
    ]
    sites_df[numeric_cols] = sites_df[numeric_cols].astype(np.float32)
    return sites_df


def dump_df_to_csv(df: pd.DataFrame, file_type: OutputFile) -> None:
    dump_dir = os.path.join(current_system_params.output_dir, "output")
    if not os.path.exists(dump_dir):
        os.mkdir(dump_dir)
    full_file_path = os.path.join(dump_dir, f"{file_type.name.lower()}.csv")
    df.to_csv(full_file_path)
    logger.info(
        f"{file_type.name.lower()} csv file has been dump to {full_file_path}"
    )


def dump_metrics_to_yaml(metrics: TopologyMetrics) -> None:
    def _convert_to_dict(obj: NamedTuple) -> Dict[str, Any]:
        d = obj._asdict()
        for k, v in d.items():
            if isinstance(
                v,
                (
                    TopologyMetrics,
                    Capex,
                    TopologyCounts,
                    DemandMetrics,
                    FlowMetrics,
                    MetricStatistics,
                    LinkMetrics,
                    AvailabilityMetrics,
                    FailureDisruption,
                ),
            ):
                d[k] = _convert_to_dict(v)
            elif isinstance(v, Counter):
                d[k] = dict(v)
        return d

    dump_dir = os.path.join(current_system_params.output_dir, "output")
    if not os.path.exists(dump_dir):
        os.mkdir(dump_dir)
    full_file_path = os.path.join(
        dump_dir, f"{OutputFile.METRICS.name.lower()}.yaml"
    )
    with open(full_file_path, "w") as f:
        yaml.dump(_convert_to_dict(metrics), f, sort_keys=False)
    logger.info(
        f"{OutputFile.METRICS.name.lower()} has been dumped to {full_file_path}"
    )
