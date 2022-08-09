# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.enums import (
    LinkType,
    PolarityType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.exceptions import (
    TopologyException,
    planner_assert,
)
from terragraph_planner.common.structs import GeoPoint
from terragraph_planner.common.topology_models.demand_site import DemandSite
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.site import DetectedSite, Site


class Topology:
    def __init__(
        self,
        sites: Iterable[Site] = (),
        demand_sites: Iterable[DemandSite] = (),
        sectors: Iterable[Sector] = (),
        links: Iterable[Link] = (),
    ) -> None:
        self.sites: Dict[str, Site] = {}
        self.demand_sites: Dict[str, DemandSite] = {}
        self.sectors: Dict[str, Sector] = {}
        self.links: Dict[str, Link] = {}
        self.site_id_to_sector_ids: Dict[str, Set[str]] = defaultdict(set)

        # site_connecivity[tx_site_id][rx_site_id] == link_id means there's a directed link
        # from tx_site to rx_site
        self.site_connectivity: Dict[str, Dict[str, str]] = {}
        # site_connecivity_reverse[rx_site_id][tx_site_id] == link_id means there's a directed link
        # from tx_site to rx_site
        self.site_connectivity_reverse: Dict[str, Dict[str, str]] = {}
        self.name = ""

        for site in sites:
            self.add_site(site)
        for demand_site in demand_sites:
            self.add_demand_site(demand_site)
        for sector in sectors:
            self.add_sector(sector)
        for link in links:
            self.add_link(link)

    @property
    def sector_connectivity(self) -> Dict[str, Dict[str, str]]:
        """
        sector_connectivity[tx_sector_id][rx_sector_id] == link_id
        means there's a directed link from tx_sector to rx_sector
        """
        sector_connectivity: Dict[str, Dict[str, str]] = {}
        for link in self.links.values():
            if link.is_out_of_sector():
                continue
            tx_sector_id = none_throws(link.tx_sector).sector_id
            rx_sector_id = none_throws(link.rx_sector).sector_id
            sector_connectivity.setdefault(tx_sector_id, {})[
                rx_sector_id
            ] = link.link_id
        return sector_connectivity

    @property
    def sector_connectivity_reverse(self) -> Dict[str, Dict[str, str]]:
        """
        sector_connectivity_reverse[rx_sector_id][tx_sector_id] == link_id
        means there's a directed link from tx_sector to rx_sector
        """
        sector_connectivity_reverse: Dict[str, Dict[str, str]] = {}
        for link in self.links.values():
            if link.is_out_of_sector():
                continue
            tx_sector_id = none_throws(link.tx_sector).sector_id
            rx_sector_id = none_throws(link.rx_sector).sector_id
            sector_connectivity_reverse.setdefault(rx_sector_id, {})[
                tx_sector_id
            ] = link.link_id
        return sector_connectivity_reverse

    def add_site(self, site: Site) -> None:
        planner_assert(
            not isinstance(site, DetectedSite),
            "Don't add DetectedSite object to the Topology",
            TopologyException,
        )
        planner_assert(
            site.site_id not in self.sites,
            f"Site {site.site_id} is already in the Topology",
            TopologyException,
        )
        self.sites[site.site_id] = site

    def remove_site(self, site_id: str) -> None:
        planner_assert(
            site_id in self.sites,
            f"Invalid site id {site_id}",
            TopologyException,
        )

        # Remove sectors on this site
        for sector_id in self.site_id_to_sector_ids[site_id]:
            del self.sectors[sector_id]

        # Remove link from/to the site
        link_to_remove: List[str] = []
        for link_id in self.site_connectivity.get(site_id, {}).values():
            link_to_remove.append(link_id)
        for link_id in self.site_connectivity_reverse.get(site_id, {}).values():
            link_to_remove.append(link_id)
        for link_id in link_to_remove:
            self.remove_link(link_id)

        # Remove the site itself
        del self.sites[site_id]

    def add_demand_site(self, demand_site: DemandSite) -> None:
        """
        Adds a demand site to the topology. Demand sites are represented as nodes
        of their own.
        """
        self.demand_sites[demand_site.demand_id] = demand_site

    def remove_demand_site(self, demand_site_id: str) -> None:
        planner_assert(
            demand_site_id in self.demand_sites,
            f"The demand site {demand_site_id} does not exist in the topology",
            TopologyException,
        )
        del self.demand_sites[demand_site_id]

    def add_sector(self, sector: Sector) -> None:
        """
        Add a sector to the topology. Fails if the sector's designated site is
        not already in the topology. Sectors are represented as node PROPERTIES,
        not as nodes themselves.
        """
        planner_assert(
            sector.sector_id not in self.sectors,
            f"Sector {sector.sector_id} is already in the Topology",
            TopologyException,
        )
        site = sector.site
        planner_assert(
            site.site_id in self.sites,
            f"Invalid site id {site.site_id} of sector {sector.sector_id}",
            TopologyException,
        )
        self.site_id_to_sector_ids[site.site_id].add(sector.sector_id)
        self.sectors[sector.sector_id] = sector

    def remove_sector(self, sector_id: str) -> None:
        # Check validity
        planner_assert(
            sector_id in self.sectors,
            f"Invalid sector id {sector_id}",
            TopologyException,
        )
        sector = self.sectors[sector_id]
        site_id = sector.site.site_id
        planner_assert(
            site_id in self.sites,
            f"Invalid site id {site_id} of sector {sector.sector_id}",
            TopologyException,
        )
        # Delete the reference of the sector in the links
        # If link's tx/rx sector's id is sector_id, then both tx/rx sectors
        # should be nullified (link cannot have one null sector)
        for link_id in self.site_connectivity.get(site_id, {}).values():
            link = self.links[link_id]
            if (
                link.tx_sector is not None
                and link.tx_sector.sector_id == sector_id
            ):
                link.clear_sectors()
        for link_id in self.site_connectivity_reverse.get(site_id, {}).values():
            link = self.links[link_id]
            if (
                link.rx_sector is not None
                and link.rx_sector.sector_id == sector_id
            ):
                link.clear_sectors()
        self.site_id_to_sector_ids[site_id].remove(sector_id)
        del self.sectors[sector_id]

    def add_link(self, link: Link) -> None:
        missing_sites = {
            s
            for s in (link.tx_site.site_id, link.rx_site.site_id)
            if s not in self.sites
        }
        planner_assert(
            len(missing_sites) == 0,
            f"Could not add link {link.tx_site.site_id}-{link.rx_site.site_id} to topology."
            f"The following sites are missing: {missing_sites}.",
        )
        self.links[link.link_id] = link
        tx_site_id = link.tx_site.site_id
        rx_site_id = link.rx_site.site_id
        self.site_connectivity.setdefault(tx_site_id, {})[
            rx_site_id
        ] = link.link_id
        self.site_connectivity_reverse.setdefault(rx_site_id, {})[
            tx_site_id
        ] = link.link_id

    def add_link_from_site_ids(
        self,
        tx_site_id: str,
        rx_site_id: str,
        **kwarg: Dict[str, Any],
    ) -> None:
        planner_assert(
            tx_site_id in self.sites,
            f"The site {tx_site_id} does not exist in the topology",
            TopologyException,
        )
        planner_assert(
            rx_site_id in self.sites,
            f"The site {rx_site_id} does not exist in the topology",
            TopologyException,
        )
        tx_site = self.sites[tx_site_id]
        rx_site = self.sites[rx_site_id]
        link = Link(
            tx_site=tx_site,
            rx_site=rx_site,
            **kwarg,  # pyre-ignore
        )
        self.add_link(link)

    def remove_link(self, link_id: str) -> None:
        planner_assert(
            link_id in self.links,
            f"Link {link_id} does not exist in the topology",
        )
        link = self.links[link_id]
        del self.site_connectivity[link.tx_site.site_id][link.rx_site.site_id]
        del self.site_connectivity_reverse[link.rx_site.site_id][
            link.tx_site.site_id
        ]
        del self.links[link_id]

    def get_successor_sites(self, site: Site) -> List[Site]:
        """
        Given a site, get all successor sites.
        """
        planner_assert(
            site.site_id in self.sites,
            f"The site {site.site_id} is not in the topology",
            TopologyException,
        )
        return (
            list(
                map(
                    lambda site_id: self.sites[site_id],
                    self.site_connectivity[site.site_id].keys(),
                ),
            )
            if site.site_id in self.site_connectivity
            else []
        )

    def get_predecessor_sites(self, site: Site) -> List[Site]:
        """
        Given a site, get all predecessor sites.
        """
        planner_assert(
            site.site_id in self.sites,
            f"The site {site.site_id} is not in the topology",
            TopologyException,
        )
        return (
            list(
                map(
                    lambda site_id: self.sites[site_id],
                    self.site_connectivity_reverse[site.site_id].keys(),
                ),
            )
            if site.site_id in self.site_connectivity_reverse
            else []
        )

    def get_wireless_successor_sites(self, site: Site) -> List[Site]:
        """
        Given a site, get all the wireless successor sites.
        """
        wireless_successor_sites = []
        for successor in self.get_successor_sites(site):
            link = self.get_link_by_site_ids(site.site_id, successor.site_id)
            if link is not None and link.is_wireless:
                wireless_successor_sites.append(successor)
        return wireless_successor_sites

    def get_wireless_predecessor_sites(self, site: Site) -> List[Site]:
        """
        Given a site, get all the wireless predecessor sites.
        """
        wireless_predecessor_sites = []
        for predecessor in self.get_predecessor_sites(site):
            link = self.get_link_by_site_ids(site.site_id, predecessor.site_id)
            if link is not None and link.is_wireless:
                wireless_predecessor_sites.append(predecessor)
        return wireless_predecessor_sites

    def get_link_by_site_ids(
        self, tx_site_id: str, rx_site_id: str
    ) -> Optional[Link]:
        """
        Get a link with tx_site_id and rx_site_id.
        Raise exception when either site id is invalid.
        Return None if site ids are valid but there's no such link.
        """
        planner_assert(
            tx_site_id in self.sites and rx_site_id in self.sites,
            "Invalid tx site id or rx site id",
            TopologyException,
        )
        link_id = Link.get_link_id_by_site_ids(tx_site_id, rx_site_id)
        return self.links.get(link_id, None)

    def get_link_by_sector_ids(
        self, tx_sector_id: str, rx_sector_id: str
    ) -> Optional[Link]:
        """
        Get a link with tx_sector_id and rx_sector_id.
        Raise exception when either sector id is invalid.
        Return None if sector ids are valid but there's no such link.
        """
        planner_assert(
            tx_sector_id in self.sectors,
            f"The sector {tx_sector_id} does not exist in the topology.",
            TopologyException,
        )
        planner_assert(
            rx_sector_id in self.sectors,
            f"The sector {rx_sector_id} does not exist in the topology.",
            TopologyException,
        )
        tx_site = self.sectors[tx_sector_id].site
        rx_site = self.sectors[rx_sector_id].site
        return self.get_link_by_site_ids(tx_site.site_id, rx_site.site_id)

    def get_reverse_link(self, link: Link) -> Optional[Link]:
        return self.get_link_by_site_ids(
            link.rx_site.site_id, link.tx_site.site_id
        )

    def sort(self) -> None:
        """
        Sort the sites, sectors, links, and demand sites. This is primarily used
        when setting up the optimization problem to ensure that the, e.g., constraints
        are applied in the same order from run to run.
        """
        self.sites = dict(sorted(self.sites.items()))
        self.demand_sites = dict(sorted(self.demand_sites.items()))
        self.sectors = dict(sorted(self.sectors.items()))
        self.links = dict(sorted(self.links.items()))
        for demand_site in self.demand_sites.values():
            demand_site.connected_sites.sort(key=lambda s: s.site_id)

    def get_colocated_sites(self) -> Dict[GeoPoint, List[str]]:
        """
        Find co-located sites in the topology. Output is a list of list where each
        sublist is the group of site_ids with the same location.
        """
        colocated_sites = {}
        for site_id, site_data in self.sites.items():
            colocated_sites.setdefault(
                GeoPoint(
                    site_data.longitude, site_data.latitude, site_data.altitude
                ),
                [],
            ).append(site_id)
        return colocated_sites

    def get_site_ids(
        self,
        status_filter: Optional[Set[StatusType]] = None,
        site_type_filter: Optional[Set[SiteType]] = None,
    ) -> Set[str]:
        return {
            site_id
            for site_id, site_data in self.sites.items()
            if (status_filter is None or site_data.status_type in status_filter)
            and (
                site_type_filter is None
                or site_data.site_type in site_type_filter
            )
        }

    def get_link_site_id_pairs(
        self,
        status_filter: Optional[Set[StatusType]] = None,
        link_type_filter: Optional[Set[LinkType]] = None,
    ) -> Set[Tuple[str, str]]:
        return {
            (link_data.tx_site.site_id, link_data.rx_site.site_id)
            for link_data in self.links.values()
            if (status_filter is None or link_data.status_type in status_filter)
            and (
                link_type_filter is None
                or link_data.link_type in link_type_filter
            )
        }

    def get_sectorless_links(self) -> Set[Tuple[str, str]]:
        return {
            (link_data.tx_site.site_id, link_data.rx_site.site_id)
            for link_data in self.links.values()
            if link_data.link_type.is_wireless()
            and link_data.is_out_of_sector()
        }

    def get_sector_ids(
        self, status_filter: Set[StatusType]
    ) -> Dict[str, Set[str]]:
        sector_ids: Dict[str, Set[str]] = {}
        for sector_id, sector_data in self.sectors.items():
            if sector_data.status_type in status_filter:
                sector_ids.setdefault(sector_data.site.site_id, set()).add(
                    sector_id
                )
        return sector_ids

    def get_site_polarities(self) -> Dict[PolarityType, Set[str]]:
        site_polarities = {
            PolarityType.ODD: set(),
            PolarityType.EVEN: set(),
        }
        for site_id in self.get_site_ids(
            status_filter=StatusType.active_status(),
            site_type_filter=SiteType.dist_site_types(),
        ):
            polarity: PolarityType = self.sites[site_id].polarity
            if polarity != PolarityType.UNASSIGNED:
                site_polarities[polarity].add(site_id)
        return site_polarities
