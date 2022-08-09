# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from collections import Counter, defaultdict
from typing import Container, Dict, Optional, Tuple

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.enums import (
    LinkType,
    SectorType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.structs import (
    ComponentCounts,
    TopologyCounts,
)
from terragraph_planner.optimization.topology_operations import hops_from_pops


def count_topology_components(
    topology: Topology,
) -> Tuple[TopologyCounts, Dict[str, int], Dict[int, int]]:
    """
    Count active and total topology components
    """
    # Compute active counts
    active_counts = _component_counter(topology, active_components=True)

    active_sites = sum(
        active_counts.site_counts_by_type[site_type]
        for site_type in list(SiteType)
    )
    active_pop_sites = active_counts.site_counts_by_type[SiteType.POP]
    active_dn_sites = active_counts.site_counts_by_type[SiteType.DN]
    active_cn_sites = active_counts.site_counts_by_type[SiteType.CN]

    active_site_sku_counter = dict(active_counts.site_counts_by_sku)

    active_nodes = sum(
        active_counts.node_counts_by_type[sector_type]
        for sector_type in list(SectorType)
    )
    active_dn_nodes = active_counts.node_counts_by_type[SectorType.DN]
    active_cn_nodes = active_counts.node_counts_by_type[SectorType.CN]

    active_sectors = sum(
        active_counts.sector_counts_by_type[sector_type]
        for sector_type in list(SectorType)
    )
    active_cn_sectors = active_counts.sector_counts_by_type[SectorType.CN]
    active_dn_sectors = active_counts.sector_counts_by_type[SectorType.DN]

    active_backhaul_links = active_counts.link_counts_by_type[
        LinkType.WIRELESS_BACKHAUL
    ]
    active_access_links = active_counts.link_counts_by_type[
        LinkType.WIRELESS_ACCESS
    ]
    active_wired_links = active_counts.link_counts_by_type[LinkType.ETHERNET]

    channel_occupancy_counter = dict(active_counts.link_counts_by_channel)

    active_demand_connected_pop_sites = (
        active_counts.demand_connected_sites_by_type[SiteType.POP]
    )
    active_demand_connected_dn_sites = (
        active_counts.demand_connected_sites_by_type[SiteType.DN]
    )
    active_demand_connected_cn_sites = (
        active_counts.demand_connected_sites_by_type[SiteType.CN]
    )

    active_dn_sectors_on_pops = active_counts.dn_sectors_on_pops

    # Compute total counts
    total_counts = _component_counter(topology, active_components=False)
    redundant_counts = _redundant_sites_counter(topology, None)

    total_sites = sum(
        total_counts.site_counts_by_type[site_type]
        for site_type in list(SiteType)
    ) - sum(redundant_counts[site_type] for site_type in list(SiteType))
    total_pop_sites = (
        total_counts.site_counts_by_type[SiteType.POP]
        - redundant_counts[SiteType.POP]
    )
    total_dn_sites = (
        total_counts.site_counts_by_type[SiteType.DN]
        - redundant_counts[SiteType.DN]
    )
    total_cn_sites = (
        total_counts.site_counts_by_type[SiteType.CN]
        - redundant_counts[SiteType.CN]
    )

    total_nodes = sum(
        total_counts.node_counts_by_type[sector_type]
        for sector_type in list(SectorType)
    )
    total_dn_nodes = total_counts.node_counts_by_type[SectorType.DN]
    total_cn_nodes = total_counts.node_counts_by_type[SectorType.CN]

    total_sectors = sum(
        total_counts.sector_counts_by_type[sector_type]
        for sector_type in list(SectorType)
    )

    total_backhaul_links = total_counts.link_counts_by_type[
        LinkType.WIRELESS_BACKHAUL
    ]
    total_access_links = total_counts.link_counts_by_type[
        LinkType.WIRELESS_ACCESS
    ]
    total_wired_links = total_counts.link_counts_by_type[LinkType.ETHERNET]

    # Find the number of DNs/CNs that have a path to a POP
    hop_counts = hops_from_pops(
        topology, status_filter=StatusType.reachable_status()
    )
    redundant_connected_counts = _redundant_sites_counter(topology, hop_counts)
    connectable_dn_sites = (
        len(
            [
                site_id
                for site_id, site in topology.sites.items()
                if site.site_type == SiteType.DN and site_id in hop_counts
            ]
        )
        - redundant_connected_counts[SiteType.DN]
    )
    connectable_cn_sites = (
        len(
            [
                site_id
                for site_id, site in topology.sites.items()
                if site.site_type == SiteType.CN and site_id in hop_counts
            ]
        )
        - redundant_connected_counts[SiteType.CN]
    )

    # Count number of CNs that could switch to a new DN if serving DN goes down
    cns_from_active_dns = defaultdict(int)
    for link in topology.links.values():
        if (
            link.rx_site.site_type == SiteType.CN
            and link.rx_site.status_type in StatusType.active_status()
            and link.tx_sector is not None
            and none_throws(link.tx_sector).status_type
            in StatusType.active_status()
        ):
            cns_from_active_dns[link.rx_site.site_id] += 1

    active_cns_with_backup_dns = len(
        [a for a in cns_from_active_dns.values() if a > 1]
    )

    return (
        TopologyCounts(
            active_sites=active_sites,
            total_sites=total_sites,
            active_pop_sites=active_pop_sites,
            total_pop_sites=total_pop_sites,
            active_dn_sites=active_dn_sites,
            total_dn_sites=total_dn_sites,
            active_cn_sites=active_cn_sites,
            connectable_dn_sites=connectable_dn_sites,
            connectable_cn_sites=connectable_cn_sites,
            total_cn_sites=total_cn_sites,
            active_cns_with_backup_dns=active_cns_with_backup_dns,
            active_demand_connected_pop_sites=active_demand_connected_pop_sites,
            active_demand_connected_dn_sites=active_demand_connected_dn_sites,
            active_demand_connected_cn_sites=active_demand_connected_cn_sites,
            active_nodes=active_nodes,
            total_nodes=total_nodes,
            active_dn_nodes=active_dn_nodes,
            total_dn_nodes=total_dn_nodes,
            active_cn_nodes=active_cn_nodes,
            total_cn_nodes=total_cn_nodes,
            active_sectors=active_sectors,
            total_sectors=total_sectors,
            active_dn_sectors_on_pops=active_dn_sectors_on_pops,
            active_dn_sectors_on_dns=active_dn_sectors
            - active_dn_sectors_on_pops,
            active_cn_sectors=active_cn_sectors,
            active_backhaul_links=active_backhaul_links,
            total_backhaul_links=total_backhaul_links,
            active_access_links=active_access_links,
            total_access_links=total_access_links,
            active_wired_links=active_wired_links,
            total_wired_links=total_wired_links,
        ),
        active_site_sku_counter,
        channel_occupancy_counter,
    )


def _component_counter(
    topology: Topology, active_components: bool
) -> ComponentCounts:
    """
    Returns the number of sectors, sites and links as a dictionary
    by the component types.
    """
    status_type_filter = (
        StatusType.active_status() if active_components else set(StatusType)
    )

    site_counts_by_type = Counter(
        site.site_type
        for site in topology.sites.values()
        if site.status_type in status_type_filter
    )
    site_counts_by_sku = Counter(
        site.device.device_sku
        for site in topology.sites.values()
        if site.status_type in status_type_filter
    )

    sector_counts_by_type = Counter(
        sector.sector_type
        for sector in topology.sectors.values()
        if sector.status_type in status_type_filter
    )

    node_counts_by_type = {
        sector_type: len(
            {
                (sector.site.site_id, sector.node_id)
                for sector in topology.sectors.values()
                if sector.sector_type == sector_type
                and sector.status_type in status_type_filter
            }
        )
        for sector_type in list(SectorType)
    }

    link_counts_by_type = {
        link_type: len(
            {
                link.link_hash
                for link in topology.links.values()
                if link.status_type in status_type_filter
                and link.link_type == link_type
            }
        )
        for link_type in list(LinkType)
    }

    link_channels = {}
    for link in topology.links.values():
        if link.status_type in status_type_filter and link.is_wireless:
            link_channels[link.sorted_site_ids] = link.link_channel
    link_counts_by_channel = Counter(link_channels.values())

    demand_connected_sites_by_type = {
        site_type: len(
            {
                site.site_id
                for demand in topology.demand_sites.values()
                for site in demand.connected_sites
                if site.site_type == site_type
                and site.status_type in status_type_filter
            }
        )
        for site_type in list(SiteType)
    }

    dn_sectors_on_pops = sum(
        1
        for sector in topology.sectors.values()
        if sector.status_type in status_type_filter
        and sector.sector_type == SectorType.DN
        and sector.site.site_type == SiteType.POP
    )

    return ComponentCounts(
        site_counts_by_type=site_counts_by_type,
        site_counts_by_sku=site_counts_by_sku,
        node_counts_by_type=node_counts_by_type,
        sector_counts_by_type=sector_counts_by_type,
        link_counts_by_type=link_counts_by_type,
        link_counts_by_channel=link_counts_by_channel,
        demand_connected_sites_by_type=demand_connected_sites_by_type,
        dn_sectors_on_pops=dn_sectors_on_pops,
    )


def _redundant_sites_counter(
    topology: Topology, site_subset: Optional[Container[str]]
) -> Dict[SiteType, int]:
    """
    Calculate the number of redundant colocated sites in a candidate topology.
    For each physical site, there could be only 1 for each site type, and the
    rest are considered redundant and should not be count in connectivity reporting.

    The output is a dict of number of redundant sites for each site type.
    """
    colocated_sites = topology.get_colocated_sites()
    keys = set(SiteType)
    redundant_counts: Dict[SiteType, int] = dict.fromkeys(keys, int(0))
    for site_ids in colocated_sites.values():
        counts: Dict[SiteType, int] = dict.fromkeys(keys, int(0))
        for s_id in site_ids:
            site = topology.sites.get(s_id, None)
            if site is not None and (
                site_subset is None or s_id in site_subset
            ):
                counts[site.site_type] += 1
        for k, v in counts.items():
            if v > 1:
                redundant_counts[k] += v - 1
    return redundant_counts
