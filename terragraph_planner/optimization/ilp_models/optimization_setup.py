# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
from copy import deepcopy
from typing import Dict, List, Optional, Set, Tuple, Union

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import (
    LinkType,
    PolarityType,
    SectorType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.exceptions import (
    OptimizerException,
    planner_assert,
)
from terragraph_planner.common.structs import GeoPoint
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.constants import (
    DEMAND,
    DEMAND_SECTOR,
    SUPERSOURCE,
    SUPERSOURCE_SECTOR,
)
from terragraph_planner.optimization.topology_preparation import (
    validate_topology_status,
)

logger: logging.Logger = logging.getLogger(__name__)


class OptimizationSetup(object):
    """
    The constructor of this class takes in two inputs:
    @param topology an Urban Topology structure that has all link, sector, site
    and demand site information.
    @param params the optimizer params

    The outputs are the dictionaries that will be used to set up the
    optimization models.

    1) location_to_type -- is a dictionary where the keys are locations and values
    are the type of that location.

    2) type_sets -- is a dictionary where type_sets[TYPE] would return the LIST of
    locations that are of this type where type can be one of SiteType.POP,
    SiteType.CN, SiteType.DN, DEMAND or SUPERSOURCE.

    3) links -- list of site pairs that have an edge between them.
    4) link_capacities -- dictionary mapping site pairs to the link throughput
    5) link_to_sectors -- dictionary mapping site pairs to the sector ids that
    create the links.
    6) link_to_azimuth -- dictionary mapping site pairs to the tx/rx beam azimuths

    7) locations -- list of locations. Location names can be integers or strings.

    8) demand_at_location -- dictionary that stores the demand information for
    each location.

    9) location_sectors -- a dictionary with keys as locations.
    location_sectors[loc] is list of sectors that can be placed on location loc.

    10) sector_to_type -- is a dictionary where the keys are sectors and values
    are the type of that sector

    11, 12) cost_site and cost_sector are dictionaries with cost information.
    cost_site[loc] is the cost of location loc. Similarly,
    cost_sector[loc][sec] is the cost of the sector sec on location loc.

    13) colocated_locations -- a dictionary where the keys are the lat, lon and
    altitude and values are the list of sites with that geographical location.

    14) location_to_geoloc -- is a dictionary where the keys are the locations
    and values are the lat, lon, and altitude of that location.

    15) sku_location - dictionary mapping sites to their device sku.

    16) fixed_inputs:
        existing_sites, proposed_sites, inactive_sites, proposed_sectors,
        site_polarities, existing_links, proposed_links, inactive_links
        -- These are dictionaries that are allowed to be empty.
        The keys of existing_sites, proposed_sites, inactive_sites,
        must be a subset of locations and their values will be the geohashes.
        site_polarities is a dict of sets of odd, even and hybrid sites.
        proposed_sectors is a dict(dict) with values 1. If a (loc, sec)
        pair exists in proposed_sectors, that sector's corresponding decision
        variable must be equal to 1.
        proposed_links, existing_links and inactive_links are dictionaries
            where keys are site pairs such as (i, j) and the values are link hashes.
        Proposed and existing links must have both end-sectors active (equal to 1).
        Inactive links must have at least one end-sectors disabled (equal to 0)
            and no flow will be allowed on them.
        Variables for sites in proposed and existing lists will
        be forced to be equal to 1 and the variables for sites in the
        inactive list will be forced to be equal to 0.
    """

    def __init__(self, topology: Topology, params: OptimizerParams) -> None:
        logger.info("Setting up optimization.")
        self.topology: Topology = topology
        validate_topology_status(topology)
        self.params: OptimizerParams = deepcopy(params)
        self.cost_site: Dict[Union[SiteType, str], float] = {
            SiteType.POP: params.pop_site_capex,
            SiteType.DN: params.dn_site_capex,
            SiteType.CN: params.cn_site_capex,
        }
        self.extract_fixed_inputs()
        self.set_up_topology_input()
        self.create_links()
        logger.info("Optimization setup complete.")

    def extract_fixed_inputs(self) -> None:
        """
        Extract site/link/sector data with fixed statuses (i.e.,
        existing/proposed or unavailable/unreachable) and identify sites by
        their polarities.
        """
        # Extract fixed sites
        self.existing_sites: Set[str] = self.topology.get_site_ids(
            status_filter={StatusType.EXISTING}
        )
        self.proposed_sites: Set[str] = self.topology.get_site_ids(
            status_filter={StatusType.PROPOSED}
        )
        self.inactive_sites: Set[str] = self.topology.get_site_ids(
            status_filter=StatusType.inactive_status()
        )

        # Extract fixed links
        self.proposed_links: Set[
            Tuple[str, str]
        ] = self.topology.get_link_site_id_pairs({StatusType.PROPOSED})
        self.existing_links: Set[
            Tuple[str, str]
        ] = self.topology.get_link_site_id_pairs({StatusType.EXISTING})
        self.inactive_links: Set[Tuple[str, str]] = (
            self.topology.get_link_site_id_pairs(StatusType.inactive_status())
            | self.topology.get_sectorless_links()
        )

        # Extract fixed sectors
        self.proposed_sectors: Dict[
            str, Set[str]
        ] = self.topology.get_sector_ids(status_filter={StatusType.PROPOSED})

        # Extract fixed polarities
        self.site_polarities: Dict[
            PolarityType, Set[str]
        ] = self.topology.get_site_polarities()

    def set_up_topology_input(self) -> None:
        """
        Prepare data in convenient dictionaries for easy reference when setting
        up constraints for the ILP problems.
        """
        self.location_to_type: Dict[str, Union[SiteType, str]] = {}
        self.location_to_geoloc: Dict[str, GeoPoint] = {}
        self.type_sets: Dict[Union[SiteType, str], Set[str]] = {
            t: set() for t in set(SiteType) | {DEMAND, SUPERSOURCE}
        }
        self.locations: List[str] = []
        self.location_sectors: Dict[str, List[str]] = {}
        self.sector_to_type: Dict[str, Union[SectorType, str]] = {}
        self.demand_at_location: Dict[str, float] = {}
        self.cost_sector: Dict[str, Dict[str, float]] = {}
        self.link_to_sectors: Dict[
            Tuple[str, str], Tuple[Optional[str], Optional[str]]
        ] = {}
        self.link_to_azimuth: Dict[
            Tuple[str, str], Tuple[Optional[float], Optional[float]]
        ] = {}
        self.link_capacities: Dict[Tuple[str, str], float] = {}
        self.sku_location: Dict[str, str] = {}
        # An importance value attached to links -- the larger the weight is,
        # the higher priority it should have for selection.
        self.link_weights: Dict[Tuple[str, str], float] = {}

        maximum_distance: float = 1.0
        if len(self.topology.links) > 0:
            maximum_distance = max(
                none_throws(link.distance)
                for link in self.topology.links.values()
            )

        def get_link_weight(dist: float) -> float:
            if maximum_distance == 0:
                return 1
            return 1 + (maximum_distance - dist) / maximum_distance

        # Create the dummy source node that we call SUPERSOURCE
        self.locations.append(SUPERSOURCE)
        self.location_to_type[SUPERSOURCE] = SUPERSOURCE
        self.sku_location[SUPERSOURCE] = ""
        self.type_sets[SUPERSOURCE].add(SUPERSOURCE)

        # First we create all the site vertices
        for site_id, site_data in self.topology.sites.items():
            self.location_to_type[site_id] = site_data.site_type
            self.location_to_geoloc[site_id] = GeoPoint(
                site_data.longitude, site_data.latitude, site_data.altitude
            )
            self.type_sets[site_data.site_type].add(site_id)
            self.demand_at_location[site_id] = 0
            self.locations.append(site_id)
            self.sku_location[site_id] = site_data.device.device_sku

            if site_data.site_type == SiteType.POP:
                # Connect supersource to the POPs; the supersource is an
                # imaginary site that we use for modeling purposes. We create
                # an imaginary sector on the POP to which the supersource is
                # connected.
                imaginary_sector_id = site_id + "_super"
                self.link_to_sectors[(SUPERSOURCE, site_id)] = (
                    None,
                    imaginary_sector_id,
                )
                self.link_to_azimuth[(SUPERSOURCE, site_id)] = (None, None)
                self.link_capacities[
                    (SUPERSOURCE, site_id)
                ] = self.params.pop_capacity
                self.link_weights[(SUPERSOURCE, site_id)] = get_link_weight(
                    maximum_distance
                )
                self.location_sectors.setdefault(site_id, []).append(
                    imaginary_sector_id
                )
                self.sector_to_type[imaginary_sector_id] = SUPERSOURCE_SECTOR

        # Collect all the co-located sites
        self.colocated_locations: Dict[
            GeoPoint, List[str]
        ] = self.topology.get_colocated_sites()

        seen_node_ids = set()
        for sector_id, sector_data in self.topology.sectors.items():
            site_id = sector_data.site.site_id
            self.location_sectors.setdefault(site_id, []).append(sector_id)
            self.sector_to_type[sector_id] = sector_data.sector_type
            sector_capex = sector_data.node_capex
            node_id = sector_data.node_id
            # Only count cost for the first sector we come across per node
            # since all sectors are linked, this ensures total cost of using any
            # sector is the cost of the whole node
            if (site_id, node_id) in seen_node_ids:
                sector_capex = 0
            seen_node_ids.add((site_id, node_id))
            self.cost_sector.setdefault(site_id, {})[sector_id] = sector_capex

        # Add in the demand sites as vertices
        max_link_cap = (
            max(link.capacity for link in self.topology.links.values())
            if len(self.topology.links) > 0
            else self.params.pop_capacity
        )
        for demand_id, demand_data in self.topology.demand_sites.items():
            # If the demand site is connected to only one location and
            # it is a CN site, then set the demand value on it to be
            # default_CN_demand
            planner_assert(
                demand_data.demand is not None and demand_data.demand >= 0,
                f"Demand site {demand_id} does not have a non-negative assigned demand value.",
                OptimizerException,
            )

            planner_assert(demand_data.num_sites >= 1)
            orig_demand_id = demand_id
            for num_dem in range(demand_data.num_sites):
                if num_dem > 0:
                    demand_id = orig_demand_id + "_" + str(num_dem)

                self.demand_at_location[demand_id] = (
                    none_throws(demand_data.demand)
                    / self.params.oversubscription
                )
                self.locations.append(demand_id)
                self.location_to_type[demand_id] = DEMAND
                self.sku_location[demand_id] = ""
                self.type_sets[DEMAND].add(demand_id)

                for site in demand_data.connected_sites:
                    site_id = site.site_id
                    self.link_capacities[(site_id, demand_id)] = max_link_cap
                    self.link_weights[(site_id, demand_id)] = get_link_weight(
                        maximum_distance
                    )
                    # Connect the site to the demand site
                    imaginary_sector_id = site_id + "_demand"
                    self.link_to_sectors[(site_id, demand_id)] = (
                        imaginary_sector_id,
                        None,
                    )
                    self.link_to_azimuth[(site_id, demand_id)] = (None, None)
                    self.location_sectors.setdefault(site_id, []).append(
                        imaginary_sector_id
                    )
                    self.sector_to_type[imaginary_sector_id] = DEMAND_SECTOR

        # Now we create all the link between the antenna
        for link_data in self.topology.links.values():
            tx_site_id = link_data.tx_site.site_id
            rx_site_id = link_data.rx_site.site_id
            planner_assert(tx_site_id != rx_site_id)
            planner_assert(
                (link_data.tx_sector is None) == (link_data.rx_sector is None)
            )
            tx_sector = link_data.tx_sector
            rx_sector = link_data.rx_sector
            self.link_capacities[(tx_site_id, rx_site_id)] = link_data.capacity
            self.link_weights[(tx_site_id, rx_site_id)] = 1

            if tx_sector is not None:
                self.link_weights[(tx_site_id, rx_site_id)] = get_link_weight(
                    none_throws(link_data.distance)
                )

            self.link_to_sectors[(tx_site_id, rx_site_id)] = (
                tx_sector.sector_id if tx_sector is not None else None,
                rx_sector.sector_id if rx_sector is not None else None,
            )
            self.link_to_azimuth[(tx_site_id, rx_site_id)] = (
                link_data.tx_beam_azimuth,
                link_data.rx_beam_azimuth,
            )
        for loc in self.locations:
            if loc not in self.location_sectors.keys():
                self.location_sectors[loc] = []

    def _get_wired_links(self) -> List[Tuple[str, str]]:
        """
        Get list of wired links; this also includes the imaginary links
        connecting the supersource to the POPs and demand to sites.
        """
        wired_links = []
        for link in self.topology.links.values():
            if link.link_type == LinkType.ETHERNET:
                wired_links.append((link.tx_site.site_id, link.rx_site.site_id))

        for link in self.outgoing_links[SUPERSOURCE]:
            wired_links.append(link)

        for loc in self.locations:
            if loc in self.type_sets[DEMAND]:
                for link in self.incoming_links[loc]:
                    wired_links.append(link)

        return wired_links

    def create_links(self) -> None:
        """
        Collect all links and separately store incoming, outgoing, and wired ones.
        """
        self.links: List[Tuple[str, str]] = list(self.link_capacities.keys())
        self.incoming_links: Dict[str, List[Tuple[str, str]]] = {}
        self.outgoing_links: Dict[str, List[Tuple[str, str]]] = {}

        for loc in self.locations:
            self.incoming_links[loc] = []
            self.outgoing_links[loc] = []

        for link in self.links:
            self.incoming_links[link[1]].append(link)
            self.outgoing_links[link[0]].append(link)

        self.wired_links: List[Tuple[str, str]] = self._get_wired_links()
