# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import math
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import (
    LinkType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.exceptions import (
    OptimizerException,
    planner_assert,
)
from terragraph_planner.common.rf.link_budget_calculator import (
    adjust_tx_power_with_backoff,
    get_fspl_based_rsl,
    get_link_capacity_from_mcs,
    get_max_tx_power,
    get_mcs_from_snr,
    get_noise_power,
    get_snr,
)
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.site import Site
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.constants import (
    BACKHAUL_LINK_TYPE_WEIGHT,
    EPSILON,
    MAX_LINK_BUDGET_ITERATIONS,
)
from terragraph_planner.optimization.structs import Capex
from terragraph_planner.optimization.topology_interference import (
    analyze_interference,
    compute_link_net_gain_map,
)
from terragraph_planner.optimization.topology_networkx import (
    build_digraph,
    find_most_disruptive_links,
)
from terragraph_planner.optimization.topology_preparation import (
    add_link_capacities,
    add_sectors_to_links,
    find_best_sectors,
)

logger: logging.Logger = logging.getLogger(__name__)


def hops_from_pops(
    topology: Topology,
    status_filter: Optional[Set[StatusType]],
) -> Dict[str, int]:
    if status_filter is None:
        status_filter = set(StatusType)
    hop_counts = {}
    current_site_ids = topology.get_site_ids(
        status_filter=status_filter,
        site_type_filter={SiteType.POP},
    )
    site_count = len(current_site_ids)
    if site_count == 0:
        logger.info("No POP sites in topology using the given status filter")
        return hop_counts

    hop = 0
    for site_id in current_site_ids:
        hop_counts[site_id] = hop

    while True:
        hop += 1
        new_links = [
            [link.tx_site.site_id, link.rx_site.site_id]
            for link in topology.links.values()
            if (
                link.tx_site.site_id in current_site_ids
                and link.status_type in status_filter
            )
        ]
        new_ids = {
            site_id
            for link in new_links
            for site_id in link
            if (
                topology.sites[site_id].status_type in status_filter
                and site_id not in current_site_ids
            )
        }
        if len(new_ids) > 0:
            for site_id in new_ids:
                hop_counts[site_id] = hop
        else:
            break
        current_site_ids |= new_ids
    return hop_counts


def get_reachable_demand_sites(
    topology: Topology, status_filter: Set[StatusType]
) -> Set[str]:
    """
    Get all demand sites that can be reached from any POP.
    """
    hops_counts = hops_from_pops(topology, status_filter=status_filter)
    reachable_demand_sites = set()
    for demand_site in topology.demand_sites.values():
        for site in demand_site.connected_sites:
            if site.site_id in hops_counts:
                reachable_demand_sites.add(demand_site.demand_id)
    return reachable_demand_sites


def mark_unreachable_components(
    topology: Topology,
    maximum_hops: Optional[int],
) -> None:
    """
    Mark components that with no path to any POP as unreachable. If requested,
    mark components that exceed max hops as unreachable.
    """
    # Identify sites connected to POPs and the number of hops away they are
    hop_counts = hops_from_pops(
        topology, status_filter=StatusType.reachable_status()
    )
    for site_id, site in topology.sites.items():
        # Mark disconnected sites and those exceeding max hops as unreachable
        if (
            site_id not in hop_counts
            or (maximum_hops and hop_counts[site_id] > maximum_hops)
        ) and site.status_type is StatusType.CANDIDATE:
            site.status_type = StatusType.UNREACHABLE

            # Mark connected links as unreachable
            successor_sites = topology.get_successor_sites(site)
            for successor in successor_sites:
                link = none_throws(
                    topology.get_link_by_site_ids(site_id, successor.site_id)
                )
                link.status_type = StatusType.UNREACHABLE
            predecessor_sites = topology.get_predecessor_sites(site)
            for predecessor in predecessor_sites:
                link = none_throws(
                    topology.get_link_by_site_ids(predecessor.site_id, site_id)
                )
                link.status_type = StatusType.UNREACHABLE

    # Mark sectors on unreachable sites as unreachable
    for sector in topology.sectors.values():
        if sector.site.status_type == StatusType.UNREACHABLE:
            sector.status_type = StatusType.UNREACHABLE


def compute_max_pop_capacity_of_topology(
    topology: Topology, pop_capacity: float, status_filter: Set[StatusType]
) -> float:
    """
    Compute the max total outgoing capacity from all the POPs in a topology.
    Given a single POP, this is done by first finding the max capacity outgoing
    link from each individual sector, adding them together along with the
    capacity of all the outgoing wired links. The smaller of this and the POP
    capacity is the max outgoing capacity. This is summed across all of the
    POPs in the topology.
    """
    site_sector_capacities = {}
    site_wired_capacities = {}
    for link_data in topology.links.values():
        if link_data.status_type not in status_filter:
            continue

        tx_site = link_data.tx_site
        rx_site = link_data.rx_site

        # Only concerned with POPs
        if tx_site.site_type != SiteType.POP:
            continue

        if (
            tx_site.status_type not in status_filter
            or rx_site.status_type not in status_filter
        ):
            continue

        if link_data.link_type == LinkType.ETHERNET:
            site_wired_capacities.setdefault(tx_site.site_id, []).append(
                link_data.capacity
            )
            continue

        if link_data.is_out_of_sector():
            continue

        site_sector_capacities.setdefault(tx_site.site_id, {}).setdefault(
            none_throws(link_data.tx_sector).sector_id,
            [],  # link_data.is_out_of_sector() confirms non-None tx_sector
        ).append(link_data.capacity)

    max_capacity = 0.0
    for pop_id in topology.get_site_ids(site_type_filter={SiteType.POP}):
        pop_outgoing_capacity = 0
        if pop_id in site_sector_capacities:
            # Sum outgoing capacity of each POP sector
            for capacities in site_sector_capacities[pop_id].values():
                # Find maximum capacity link from each sector - in best case
                # this link is fully utilized
                max_capacity_from_sector = (
                    max(capacities) if len(capacities) > 0 else 0.0
                )
                pop_outgoing_capacity += max_capacity_from_sector
        if pop_id in site_wired_capacities:
            # Sum outgoing capacity from each POP wired link
            pop_outgoing_capacity += sum(site_wired_capacities[pop_id])
        # POP outgoing capacity cannot exceed incoming capacity
        max_capacity += min(pop_outgoing_capacity, pop_capacity)

    return max_capacity


def _find_colocated_sites_to_remove(topology: Topology) -> Set[str]:
    # If any of the co-located sites are active, then the co-located site
    # constraint will prevent any of the others from being selected unless it
    # is a CN. In that case, the CN can be upgraded to a DN or a POP. As a
    # result, the logic to ensure that an adversarial link is not a cut edge in
    # the candidate graph requires that the candidate graph does not include
    # co-located sites that cannot be selected.
    delete_sites = set()

    colocated_sites = topology.get_colocated_sites()
    active_sites = topology.get_site_ids(
        status_filter=StatusType.active_status()
    )
    for site_ids in colocated_sites.values():
        active_colocated_sites = active_sites.intersection(set(site_ids))
        if len(active_colocated_sites) == 0:
            continue
        max_site_type = SiteType.CN
        for site_id in active_colocated_sites:
            site_type = topology.sites[site_id].site_type
            if site_type == SiteType.DN and max_site_type != SiteType.POP:
                max_site_type = SiteType.DN
            elif site_type == SiteType.POP:
                max_site_type = SiteType.POP
        valid_site_types = set()
        if max_site_type == SiteType.CN:
            valid_site_types.add(SiteType.CN)
            valid_site_types.add(SiteType.DN)
            valid_site_types.add(SiteType.POP)
        elif max_site_type == SiteType.DN:
            valid_site_types.add(SiteType.DN)
        elif max_site_type == SiteType.POP:
            valid_site_types.add(SiteType.POP)
        # CN site can be upgraded to a DN but one CN cannot be exchanged
        # for another (i.e., if devices are different).
        # DN/POP sites cannot be upgraded or downgraded or exchanged
        # for another equivalent site type.
        for site_id in site_ids:
            site_type = topology.sites[site_id].site_type
            if site_type not in valid_site_types or (
                site_type == max_site_type and site_id not in active_sites
            ):
                delete_sites.add(site_id)

    return delete_sites


def get_adversarial_links(
    topology: Topology,
    adversarial_links_ratio: float,
) -> Set[Tuple[str, str]]:
    """
    This function generates the adversarial links
    """
    nb_of_active_backhaul_links = len(
        [
            link
            for link in topology.links.values()
            if link.status_type in StatusType.active_status()
            and link.link_type == LinkType.WIRELESS_BACKHAUL
        ]
    )
    if nb_of_active_backhaul_links == 0 or adversarial_links_ratio == 0:
        return set()

    adversarial_links = set()

    proposed_graph = build_digraph(topology, StatusType.active_status())
    candidate_graph = build_digraph(topology, StatusType.reachable_status())

    # Remove zero capacity links from candidate graph
    for link in topology.links.values():
        if link.capacity <= 0:
            candidate_graph.remove_edge(
                link.tx_site.site_id, link.rx_site.site_id
            )

    # Delete extra colocated sites from locations that already have a site selected
    delete_sites = _find_colocated_sites_to_remove(topology)
    for site_id in delete_sites:
        if site_id in candidate_graph:
            candidate_graph.remove_node(site_id)

    # Find most disruptive links
    adversarial_links = find_most_disruptive_links(
        proposed_graph=proposed_graph,
        candidate_graph=candidate_graph,
        count=math.ceil(nb_of_active_backhaul_links * adversarial_links_ratio),
    )

    logger.info(
        f"Number of adversarial links is {len({(u, v) if u < v else (v, u) for u, v in adversarial_links})}"
    )
    return adversarial_links


def readjust_sectors_post_opt(
    topology: Topology,
    params: OptimizerParams,
) -> None:
    """
    Interface for optimizer to re-adjust sectors positions post-optimization
    Taking the optimized topology and OptimizerParams as inputs, this method
    finds sectors for every sites and get active links from optimized topology
    and then call the find_best_sectors to find best sector positions
    for each site. If a best position is return, re-assign the ant_azimuth,
    otherwise keep it as it was.
    """
    logger.info("Updating sector orientation.")

    sectors_for_sites: Dict[str, List[Sector]] = defaultdict(list)
    link_channel_map: Dict[str, int] = {}

    for sector in topology.sectors.values():
        sectors_for_sites[sector.site.site_id].append(sector)

    # Store neighboring sites as a list to avoid reproducibility issue with sets
    # However, take special care to avoid duplications
    neighbor_sites: Dict[str, List[Site]] = {
        site_id: [] for site_id in topology.sites
    }
    neighbor_site_ids: Dict[str, Set[str]] = {
        site_id: set() for site_id in topology.sites
    }
    for link_id, link in topology.links.items():
        if link.status_type in StatusType.active_status() and link.is_wireless:
            if (
                link.rx_site.site_id
                not in neighbor_site_ids[link.tx_site.site_id]
            ):
                neighbor_site_ids[link.tx_site.site_id].add(
                    link.rx_site.site_id
                )
                neighbor_sites[link.tx_site.site_id].append(link.rx_site)
            if (
                link.tx_site.site_id
                not in neighbor_site_ids[link.rx_site.site_id]
            ):
                neighbor_site_ids[link.rx_site.site_id].add(
                    link.tx_site.site_id
                )
                neighbor_sites[link.rx_site.site_id].append(link.tx_site)
            link_channel_map[link_id] = link.link_channel

    # Modify the sectors outside of the loop, otherwise link sectors are
    # updated during the loop
    sectors_ids_to_remove = []
    sectors_to_add = []

    for site_id, site in topology.sites.items():
        sector_params = site.device.sector_params
        neighbor_site_list = neighbor_sites[site_id]

        sector_channel_list: List[Tuple[str, int]] = []
        for neighbor_site in neighbor_site_list:
            link = topology.get_link_by_site_ids(
                site.site_id, neighbor_site.site_id
            )
            if link is not None:
                sector_channel_list.append(
                    (
                        none_throws(link.tx_sector).sector_id,
                        link_channel_map[link.link_id],
                    )
                )

        readjusted_angles = find_best_sectors(
            site=site,
            neighbor_site_list=neighbor_site_list,
            number_of_nodes=site.device.number_of_nodes_per_site,
            number_of_sectors_per_node=sector_params.number_sectors_per_node,
            horizontal_scan_range=sector_params.horizontal_scan_range,
            dn_dn_sector_limit=params.dn_dn_sector_limit,
            dn_total_sector_limit=params.dn_total_sector_limit,
            diff_sector_angle_limit=params.diff_sector_angle_limit,
            near_far_angle_limit=params.near_far_angle_limit,
            near_far_length_ratio=params.near_far_length_ratio,
            backhaul_link_type_weight=BACKHAUL_LINK_TYPE_WEIGHT,
            sector_channel_list=sector_channel_list
            if len({n[1] for n in sector_channel_list}) > 1
            else None,  # channel constraints iff multiple channels assigned
        )
        # If find_best_sectors returns None, leave site as it was
        if len(readjusted_angles) == 0:
            continue
        for sector in sectors_for_sites[site_id]:
            sectors_ids_to_remove.append(sector.sector_id)

        for i, node in enumerate(readjusted_angles):
            for j, sector_azimuth in enumerate(node):
                n = Sector(
                    site=site,
                    node_id=i,
                    position_in_node=j,
                    ant_azimuth=sector_azimuth,
                    status_type=StatusType.CANDIDATE,
                )
                sectors_to_add.append(n)

    for sector_id in sectors_ids_to_remove:
        topology.remove_sector(sector_id)

    for sector in sectors_to_add:
        topology.add_sector(sector)

    # Sectors on inactive CN sites do not have well-defined orientation even
    # post-optimization; clear the sectors for all incoming links to such sites
    # (also needed for validate_link_sectors in add_sectors_to_links)
    for link in topology.links.values():
        if (
            link.rx_site.site_type == SiteType.CN
            and link.rx_site.status_type not in StatusType.active_status()
        ):
            planner_assert(
                link.status_type not in StatusType.active_status(),
                "Active link cannot be connected to inactive site",
                OptimizerException,
            )
            link.clear_sectors()

    add_sectors_to_links(
        topology,
        force_full_cn_scan_range=False,
        link_channel_map=link_channel_map,
    )
    _set_sector_status_in_same_node(topology)


def _set_sector_status_in_same_node(topology: Topology) -> None:
    """
    If a sector is PROPOSED, all other CANDIDATE sectors in the same node
    should be PROPOSED too.
    """
    proposed_nodes = set()
    for sector in topology.sectors.values():
        if sector.status_type == StatusType.PROPOSED:
            proposed_nodes.add((sector.site.site_id, sector.node_id))
    for sector in topology.sectors.values():
        if (sector.site.site_id, sector.node_id) in proposed_nodes:
            sector.status_type = StatusType.PROPOSED


def compute_capex(topology: Topology, params: OptimizerParams) -> Capex:
    """
    Compute total (including existing) and proposed CAPEX
    """
    proposed_capex: float = 0
    existing_capex: float = 0

    seen_nodes = set()
    for sector in topology.sectors.values():
        # Only add node capex for one sector per node
        if (sector.site.site_id, sector.node_id) in seen_nodes:
            continue

        seen_nodes.add((sector.site.site_id, sector.node_id))

        if sector.status_type == StatusType.PROPOSED:
            proposed_capex += sector.site.device.node_capex
        elif sector.status_type == StatusType.EXISTING:
            existing_capex += sector.site.device.node_capex

    site_type_to_cost = {
        SiteType.POP: params.pop_site_capex,
        SiteType.DN: params.dn_site_capex,
        SiteType.CN: params.cn_site_capex,
    }

    for site in topology.sites.values():
        if site.status_type == StatusType.PROPOSED:
            proposed_capex += site_type_to_cost[site.site_type]
        elif site.status_type == StatusType.EXISTING:
            existing_capex += site_type_to_cost[site.site_type]

    return Capex(
        total_capex=proposed_capex + existing_capex,
        proposed_capex=proposed_capex,
    )


def update_link_caps_with_sinr(
    topology: Topology,
    params: OptimizerParams,
    max_iterations: int = MAX_LINK_BUDGET_ITERATIONS,
) -> None:
    """
    Prior to selecting a subset of active links, we compute link capacities
    and MCS values using the computed SNR values (not SINR). This is because
    the SINR values are directly affected by the subset of active links.

    Once the set of active links are selected, we iteratively adjust link
    budgets to convergence. In each iteration, we first compute SINR values
    for each link, update the link capacities and MCS class based on the SINR,
    adjust the tx power based on the new MCS class and then recompute RSL/SNR
    based on the updated tx power.
    """
    planner_assert(
        max_iterations >= 1,
        "Number of TPC iterations must be at least 1",
        OptimizerException,
    )

    add_link_capacities(topology, params, with_deviation=True)
    net_gain = {
        link.link_id: link.rsl_dbm - link.tx_power
        for link in topology.links.values()
    }

    active_links = [
        link
        for link in topology.links.values()
        if link.status_type in StatusType.active_status()
        and link.link_type != LinkType.ETHERNET
    ]

    max_tx_power = {}
    for device in params.device_list:
        max_tx_power[device.device_sku] = get_max_tx_power(
            tx_sector_params=device.sector_params,
            max_eirp_dbm=params.maximum_eirp,
        )

    # Precompute net gain because it does not change during tx power modulation
    # Precomputation can save significant time for large networks
    link_net_gain_map = compute_link_net_gain_map(topology)

    if len(active_links) > 0:
        for _ in range(max_iterations):
            # Compute interference and SINR
            analyze_interference(topology, link_net_gain_map)
            # Adjust tx power and link measurements
            tx_power_stable_count = 0
            for link in active_links:
                tx_data = topology.sites[link.tx_site.site_id].device
                min_tx_power = tx_data.sector_params.minimum_tx_power
                rx_data = topology.sites[link.rx_site.site_id].device
                np_dbm = get_noise_power(rx_data.sector_params)
                mcs_snr_mbps_map = rx_data.sector_params.mcs_map

                # Adjust MCS and capacity based on SINR
                link.mcs_level = get_mcs_from_snr(
                    link.sinr_dbm, mcs_snr_mbps_map
                )
                link.capacity = get_link_capacity_from_mcs(
                    link.mcs_level, mcs_snr_mbps_map
                )
                n_and_i_dbm = link.rsl_dbm - link.sinr_dbm
                # Compute the lowest tx power that maintains the same MCS
                tx_power_prev = link.tx_power
                link.mcs_level, link.tx_power = adjust_tx_power_with_backoff(
                    mcs_level=link.mcs_level,
                    mcs_snr_mbps_map=mcs_snr_mbps_map,
                    min_tx_power=min_tx_power,
                    max_tx_power=max_tx_power[link.tx_site.device.device_sku],
                    net_gain_dbi=net_gain[link.link_id],
                    np_dbm=n_and_i_dbm,
                )
                # Re-compute link measurements from the udpated tx power
                link.rsl_dbm = get_fspl_based_rsl(
                    link.tx_power, net_gain[link.link_id]
                )
                link.snr_dbm = get_snr(link.rsl_dbm, np_dbm)

                # Tx power does not change if the MCS with SINR stayed the same
                tx_power_stable_count += (
                    1
                    if math.isclose(
                        link.tx_power, tx_power_prev, abs_tol=EPSILON
                    )
                    else 0
                )

            # Stop iteration if tx powers are no longer changing
            logger.info(
                f"Ratio of converged link tx powers: {tx_power_stable_count}/{len(active_links)}"
            )
            if tx_power_stable_count == len(active_links):
                break

    # update sinr_dbm, MCS & capacity
    analyze_interference(topology, link_net_gain_map)
    for link in topology.links.values():
        if link.link_type == LinkType.ETHERNET:
            continue
        rx_data = topology.sites[link.rx_site.site_id].device
        mcs_snr_mbps_map = rx_data.sector_params.mcs_map
        link.mcs_level = get_mcs_from_snr(link.sinr_dbm, mcs_snr_mbps_map)
        link.capacity = get_link_capacity_from_mcs(
            link.mcs_level, mcs_snr_mbps_map
        )
