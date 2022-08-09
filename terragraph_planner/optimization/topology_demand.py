# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
from itertools import product
from typing import Dict, Set

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.constants import (
    UNKNOWN_BUILDING_ID,
)
from terragraph_planner.common.configuration.enums import LocationType, SiteType
from terragraph_planner.common.exceptions import (
    OptimizerException,
    planner_assert,
)
from terragraph_planner.common.geos import (
    GeoLocation,
    grid_deltas,
    haversine_distance,
)
from terragraph_planner.common.structs import GeoPoint
from terragraph_planner.common.topology_models.demand_site import DemandSite
from terragraph_planner.common.topology_models.topology import Topology

logger: logging.Logger = logging.getLogger(__name__)


def add_demand_to_topology(topology: Topology, params: OptimizerParams) -> None:

    # Remove demand sites that might have been loaded into the topology if the
    # manual demand model is not enabled
    if params.enable_manual_demand:
        for demand_site in topology.demand_sites.values():
            demand_site.demand = params.demand
            demand_site.connected_sites = []
    else:
        topology.demand_sites = {}

    manual_demand_sites = set(topology.demand_sites.keys())

    if params.enable_uniform_demand:
        _add_uniform_demand_sites(
            topology, params.demand_spacing, params.demand
        )

    # Connect sites to demand - prune uniform demand sites that are not
    # connected to any other site
    for demand_id in list(topology.demand_sites.keys()):
        demand_site = topology.demand_sites[demand_id]
        connected_sites = [
            site
            for site in topology.sites.values()
            if haversine_distance(
                site.longitude,
                site.latitude,
                demand_site.longitude,
                demand_site.latitude,
            )
            <= params.demand_connection_radius
        ]
        if len(connected_sites) == 0 and demand_id not in manual_demand_sites:
            topology.remove_demand_site(demand_id)
        else:
            demand_site.connected_sites = connected_sites

    if params.enable_cn_demand:
        _add_cn_demand_sites(topology, params.demand)

    _add_dn_sites_to_cn_connected_demand(topology)

    planner_assert(
        len(topology.demand_sites) > 0,
        "No demand sites were added to the topology.",
        OptimizerException,
    )

    logger.info(
        f"{len(topology.demand_sites)} demand sites are added to the topology."
    )


def _add_cn_demand_sites(topology: Topology, demand: float) -> None:
    """
    Place a demand site on each CN in the topology
    """
    cn_sites = [
        site
        for site in topology.sites.values()
        if site.site_type == SiteType.CN
    ]

    demand_locations = {}

    for cn in cn_sites:
        cn_lat_lon = GeoPoint(latitude=cn.latitude, longitude=cn.longitude)
        if cn_lat_lon not in demand_locations:
            demand_site = DemandSite(
                location=cn.location.copy(altitude=None),
                num_sites=cn.number_of_subscribers,
                demand=demand,
                connected_sites=[cn],
            )
            topology.add_demand_site(demand_site)
            demand_locations[cn_lat_lon] = demand_site.demand_id
        else:
            demand_site = topology.demand_sites[demand_locations[cn_lat_lon]]
            demand_site.connected_sites.append(cn)


def _add_uniform_demand_sites(
    topology: Topology, grid_spacing: float, demand: float
) -> None:
    """
    Generate a uniform grid of demand sites.
    """
    # Get bounding box of the topology taking care of the antimeridian
    # If sites cross the antimeridian, assume they are all within 5 degrees
    # longitude of it
    delta = 5
    antimeridian = any(
        site.longitude >= 180 - delta for site in topology.sites.values()
    ) and any(
        site.longitude <= -180 + delta for site in topology.sites.values()
    )
    left = min(
        site.longitude
        for site in topology.sites.values()
        if not antimeridian or site.longitude >= 180 - delta
    )
    right = max(
        site.longitude
        for site in topology.sites.values()
        if not antimeridian or site.longitude <= -180 + delta
    )
    bottom = min(site.latitude for site in topology.sites.values())
    top = max(site.latitude for site in topology.sites.values())

    # Add some buffer
    dx, dy = grid_deltas(left, bottom, grid_spacing)
    left -= dx
    right += dx
    bottom -= dy
    top += dy

    longitude = left
    while longitude <= right or (antimeridian and longitude >= left):
        latitude = bottom
        while latitude <= top:
            topology.add_demand_site(
                DemandSite(
                    location=GeoLocation(
                        latitude=latitude, longitude=longitude
                    ),
                    demand=demand,
                )
            )
            latitude += dy
        longitude += dx
        if longitude > 180:
            longitude -= 360


def _add_dn_sites_to_cn_connected_demand(topology: Topology) -> None:
    """
    First, identify DN/POP sites that should be connected directly to the same
    demand site as a corresponding CN site. Such sites include those that have
    the same location or sit on the same building rooftop.

    Then, update the demand site connected sites to include the appropriate
    DNs/POPs.
    """
    # Maps CN sites to DN sites that should also be connected to the same Demand
    cn_sites_to_dn_sites = {}

    # Find DNs that are approximately on the same location as another CN
    _handle_hybrid_locations(topology, cn_sites_to_dn_sites)

    # Find DNs on the same building as another CN
    _handle_rooftop_connections(topology, cn_sites_to_dn_sites)

    # Connect these DNs to the same Demand as the CN
    connect_demand_to_colocated_sites(topology, cn_sites_to_dn_sites)


def _handle_hybrid_locations(
    topology: Topology, cn_sites_to_dn_sites: Dict[str, Set[str]]
) -> None:
    """
    Users can duplicate CNs and DNs. In that case, we'll have DN and CN locations
    on the exact same lat, lon and altitude. This can be useful, for example, to
    have the optimizer decide which site type should be used (CNs are generally
    cheaper, but DNs can distribute bandwidth to downstream clients).

    In this function we identify DN/POPs and CNs that have the same location. If
    that's the case, we will use that information to connect the DN/POP to the
    same demand sites as the corresponding CN is connected to.
    """
    # CN and DN sites that share locations
    colocated_sites = topology.get_colocated_sites()
    for site_ids in colocated_sites.values():
        if len(site_ids) <= 1:
            continue
        cn_site_ids = [
            site_id
            for site_id in site_ids
            if topology.sites[site_id].site_type == SiteType.CN
        ]
        dn_site_ids = [
            site_id
            for site_id in site_ids
            if topology.sites[site_id].site_type in SiteType.dist_site_types()
        ]
        for cn_site_id, dn_site_id in product(cn_site_ids, dn_site_ids):
            cn_sites_to_dn_sites.setdefault(cn_site_id, set()).add(dn_site_id)


def _handle_rooftop_connections(
    topology: Topology, cn_sites_to_dn_sites: Dict[str, Set[str]]
) -> None:
    """
    CNs and DNs can be placed on the same rooftop. The optimizer will decide
    which sites to use, however, if a DN is selected, it can be wired directly to
    the demand site rather than have the bandwidth flow through the CN on the
    building.

    In this function we identify DN/POPs and CNs that were placed on the same
    building. If that's the case, we will use that information to connect the
    DN/POP to the same demand sites as the corresponding CN is connected to.
    """
    # CN and DN sites that share buildings
    building_cn_sites = {}
    building_dn_sites = {}
    for site_id, site in topology.sites.items():
        if (
            site.location_type == LocationType.ROOFTOP
            # Negative id indicates unknown building so such buildings cannot
            # be matched
            and none_throws(site.building_id) > UNKNOWN_BUILDING_ID
        ):
            if site.site_type == SiteType.CN:
                building_cn_sites.setdefault(site.building_id, set()).add(
                    site_id
                )
            elif site.site_type in {SiteType.DN, SiteType.POP}:
                building_dn_sites.setdefault(site.building_id, set()).add(
                    site_id
                )

    for common_bldg in building_cn_sites.keys() & building_dn_sites.keys():
        cn_site_ids = building_cn_sites[common_bldg]
        dn_site_ids = building_dn_sites[common_bldg]
        for cn_site_id, dn_site_id in product(cn_site_ids, dn_site_ids):
            if cn_site_id not in cn_sites_to_dn_sites:
                cn_sites_to_dn_sites[cn_site_id] = set()
            cn_sites_to_dn_sites[cn_site_id].add(dn_site_id)


def connect_demand_to_colocated_sites(
    topology: Topology, site_to_colocated_sites: Dict[str, Set[str]]
) -> None:
    """
    Given the POP/DN sites that should be connected to the same demand sites as a
    corresponding CN site, update the demand site connected sites as needed.
    """
    for demand in topology.demand_sites.values():
        connected_site_ids = {site.site_id for site in demand.connected_sites}
        for site in demand.connected_sites:
            dn_site_ids = site_to_colocated_sites.get(site.site_id, set())
            for dn_site_id in dn_site_ids:
                # Only append to the demand site if it is not already
                # connected to the POP/DN
                if dn_site_id not in connected_site_ids:
                    demand.connected_sites.append(topology.sites[dn_site_id])
                    connected_site_ids.add(dn_site_id)
