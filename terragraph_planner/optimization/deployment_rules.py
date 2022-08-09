# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from itertools import combinations
from typing import Dict, List, Set

from terragraph_planner.common.configuration.enums import SectorType, StatusType
from terragraph_planner.common.geos import law_of_cosines_spherical
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.site import Site
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.structs import (
    AngleViolatingLinkPairs,
    LinkPair,
)


def find_angle_violating_link_pairs(
    topology: Topology,
    diff_sector_angle_limit: float,
    near_far_angle_limit: float,
    near_far_length_ratio: float,
    active_components: bool,
) -> AngleViolatingLinkPairs:
    """
    This function is used mainly for the formulation of the deployment
    optimization where we would like to prevent two links that violate the
    angle rules from being active.
    For each three points i, j, k in space where edges (i,j) and (i,k) exist,
    this function computes the angle between these edges and records them if
    the angle is less than a threshold value. We use the terragraph deployment
    guidelines for the rules and threshold values.

    @return
    The struct AngleViolatingLinkPairs, containing the following 2 different lists:
    diff_sector_list: List of (i, j, k) site-triplets where links
        (i, j) and (i, k) that are leaving from different sectors and
        have an angle less than the deployment threshold
    near_far_list: List of (i, j, k) site-triplets where links
        (i, j) and (i, k) that are leaving from different sectors and
        have a length ratio greater than the near-far ratio and angle less
        than the near-far link angle threshold have an angle less than
        the deployment threshold
    """

    # Create a dictionary that records the set of sites that each site
    # has a link to.
    adjacency_dictionary = _get_adjacency_dictionary(
        topology, active_components
    )

    diff_sector_list = []
    near_far_list = []

    for common_site, adjacency_list in adjacency_dictionary.items():
        for link1, link2 in combinations(adjacency_list, 2):
            site1, sector1 = link1.rx_site, link1.tx_sector
            site2, sector2 = link2.rx_site, link2.tx_sector
            link_pair = (
                common_site.site_id,
                min(site1.site_id, site2.site_id),
                max(site1.site_id, site2.site_id),
            )
            angle, length_ratio = law_of_cosines_spherical(
                common_site.latitude,
                common_site.longitude,
                site1.latitude,
                site1.longitude,
                site2.latitude,
                site2.longitude,
            )
            if sector1 is not sector2 and (
                not active_components or sector1.channel == sector2.channel
            ):
                if angle <= diff_sector_angle_limit:
                    diff_sector_list.append(link_pair)
                elif (
                    angle <= near_far_angle_limit
                    and length_ratio >= near_far_length_ratio
                ):
                    near_far_list.append(link_pair)

    return AngleViolatingLinkPairs(diff_sector_list, near_far_list)


def _get_adjacency_dictionary(
    topology: Topology, active_components: bool
) -> Dict[Site, List[Link]]:
    adjacency_dictionary: Dict[Site, List[Link]] = {
        site: [] for site in topology.sites.values()
    }
    for link in topology.links.values():
        if not link.is_wireless:
            continue
        if (
            active_components and link.status_type in StatusType.active_status()
        ) or not active_components:
            adjacency_dictionary[link.tx_site].append(link)
    return adjacency_dictionary


def get_violating_link_ids(
    topology: Topology,
    site_triplets: List[LinkPair],
) -> Set[str]:
    """
    Get link_ids violating deployment rules.
    """
    violating_links = set()
    for (i, j, k) in site_triplets:
        indices = [(i, j), (i, k), (j, i), (k, i)]
        links = [
            topology.get_link_by_site_ids(pair[0], pair[1]) for pair in indices
        ]
        for link in links:
            if link is not None:
                violating_links.add(link.link_id)
    return violating_links


def find_sector_limit_violations(
    topology: Topology, dn_dn_sector_limit: int, dn_total_sector_limit: int
) -> Dict[str, List[str]]:
    """
    Find the set of sectors and the associated links that violate these limits.
    Each DN sector should connect to at most dn_total_sector_limit many DN/CN,
    and dn_dn_sector_limit many DNs.

    Outputs:
    violating_sectors (dictionary):
        Keys are sector ids that are violating link limits and the corresponding
        values are the list of rx sector ids
    """
    active_dn_sectors = [
        sector_id
        for sector_id, sector in topology.sectors.items()
        if sector.sector_type == SectorType.DN
        and sector.status_type in StatusType.active_status()
    ]
    violating_sectors = {}
    for tx_sector_id in active_dn_sectors:
        connections_to_dn = 0
        connections_to_cn = 0
        # An active sector may have no associated links in a multi-sector node
        all_rx_sectors = topology.sector_connectivity.get(tx_sector_id, {})
        for rx_sector_id, link_id in all_rx_sectors.items():
            if (
                topology.links[link_id].status_type
                in StatusType.active_status()
            ):
                if topology.sectors[rx_sector_id].sector_type == SectorType.DN:
                    connections_to_dn += 1
                if topology.sectors[rx_sector_id].sector_type == SectorType.CN:
                    connections_to_cn += 1
        if (connections_to_dn > dn_dn_sector_limit) or (
            connections_to_dn + connections_to_cn > dn_total_sector_limit
        ):
            violating_sectors[tx_sector_id] = [
                n
                for n in all_rx_sectors
                if topology.sectors[n].status_type in StatusType.active_status()
            ]
    return violating_sectors
