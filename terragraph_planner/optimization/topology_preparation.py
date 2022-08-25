# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
from itertools import combinations, product
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import numpy.typing as npt
from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import (
    LinkType,
    SectorType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.constants import (
    DEFAULT_POINTING_PRECISION,
    FULL_ROTATION_ANGLE,
    SECTOR_LINK_ANGLE_TOLERANCE,
)
from terragraph_planner.common.exceptions import (
    OptimizerException,
    TopologyException,
    planner_assert,
)
from terragraph_planner.common.geos import (
    angle_delta,
    bearing_in_degrees,
    haversine_distance,
    law_of_cosines_spherical,
)
from terragraph_planner.common.rf.link_budget_calculator import (
    fspl_based_estimation,
    get_max_tx_power,
)
from terragraph_planner.common.structs import LinkBudgetMeasurements
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.site import Site
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.topology_demand import (
    add_demand_to_topology,
)


def prepare_topology_for_optimization(
    topology: Topology, params: OptimizerParams
) -> None:
    """
    Prepare candidate graph for optimization by adding link capacities, creating
    sectors on the sites and adding demand sites.
    """
    add_link_capacities_without_deviation(topology, params)

    setup_node_structure(topology)

    add_demand_to_topology(topology, params)


def add_link_capacities_without_deviation(
    topology: Topology,
    params: OptimizerParams,
) -> None:
    """
    Add link capacities prior to optimization. Because sector orientations can
    change after optimization, the link capacities are computed without
    considering any deviation from boresight. This will be corrected
    post-optimization.
    """
    for link in topology.links.values():
        if link.link_type == LinkType.ETHERNET:
            link.link_budget = LinkBudgetMeasurements(
                mcs_level=0,
                rsl_dbm=-math.inf,
                snr_dbm=-math.inf,
                capacity=params.pop_capacity,
                tx_power=-math.inf,
            )
            continue

        tx_device = topology.sites[link.tx_site.site_id].device
        tx_sector_params = tx_device.sector_params
        rx_device = topology.sites[link.rx_site.site_id].device
        rx_sector_params = rx_device.sector_params
        mcs_snr_mbps_map = rx_device.sector_params.mcs_map

        max_tx_power = get_max_tx_power(
            tx_sector_params=tx_sector_params,
            max_eirp_dbm=params.maximum_eirp,
        )
        link.link_budget = fspl_based_estimation(
            distance=link.distance,
            max_tx_power=max_tx_power,
            tx_sector_params=tx_sector_params,
            rx_sector_params=rx_sector_params,
            mcs_snr_mbps_map=mcs_snr_mbps_map,
            tx_deviation=0.0,
            rx_deviation=0.0,
            tx_el_deviation=0.0,
            rx_el_deviation=0.0,
            tx_scan_pattern_data=None,
            rx_scan_pattern_data=None,
        )


def add_link_capacities_with_deviation(
    topology: Topology,
    params: OptimizerParams,
) -> None:
    """
    Add link capacities after optimizer and deviation is considered.
    """
    for link in topology.links.values():
        if link.link_type == LinkType.ETHERNET:
            link.capacity = params.pop_capacity
            continue
        if link.is_out_of_sector():
            link.link_budget = LinkBudgetMeasurements(
                mcs_level=0,
                rsl_dbm=-math.inf,
                snr_dbm=-math.inf,
                capacity=params.pop_capacity,
                tx_power=-math.inf,
            )
            continue

        tx_device = topology.sites[link.tx_site.site_id].device
        tx_sector_params = tx_device.sector_params
        rx_device = topology.sites[link.rx_site.site_id].device
        rx_sector_params = rx_device.sector_params
        mcs_snr_mbps_map = rx_device.sector_params.mcs_map

        max_tx_power = get_max_tx_power(
            tx_sector_params=tx_sector_params,
            max_eirp_dbm=params.maximum_eirp,
        )
        link.link_budget = fspl_based_estimation(
            distance=link.distance,
            max_tx_power=max_tx_power,
            tx_sector_params=tx_sector_params,
            rx_sector_params=rx_sector_params,
            mcs_snr_mbps_map=mcs_snr_mbps_map,
            tx_deviation=none_throws(link.tx_dev),
            rx_deviation=none_throws(link.rx_dev),
            tx_el_deviation=link.el_dev,
            # CNs have mechanical tilt, so deviation is 0 (not quite right for
            # inactive wireless access links, but this is ignored)
            rx_el_deviation=-link.el_dev
            if link.link_type != LinkType.WIRELESS_ACCESS
            else 0,
            tx_scan_pattern_data=tx_sector_params.scan_pattern_data,
            rx_scan_pattern_data=rx_sector_params.scan_pattern_data,
        )


def setup_node_structure(topology: Topology) -> None:
    create_dn_sectors(topology)
    create_cn_sectors(topology)

    # Pre-optimization, CN horizontal_scan_range should be 360 as the sector
    # should point directly at the incoming DN in post-optimization, i.e.
    # they'll ultimately be leaves with an unambiguous sector choice
    add_sectors_to_links(
        topology, force_full_cn_scan_range=True, link_channel_map=None
    )


def create_dn_sectors(topology: Topology) -> None:

    # sectors_for_sites is used to indicate that we have already added
    # DN antennas
    sectors_for_sites = {}
    for sector_id, sector in topology.sectors.items():
        if sector.sector_type == SectorType.DN:
            sectors_for_sites.setdefault(sector.site.site_id, []).append(
                sector_id
            )

    for site_id, site in topology.sites.items():
        if (
            len(sectors_for_sites.get(site_id, [])) > 0
            or site.site_type not in SiteType.dist_site_types()
        ):
            validate_site_sectors(
                [
                    topology.sectors[sector_id]
                    for sector_id in sectors_for_sites.get(site_id, [])
                ]
            )
            continue
        sector_params = site.device.sector_params
        nodes = find_best_sectors(
            site=site,
            neighbor_site_list=topology.get_wireless_successor_sites(site),
            number_of_nodes=site.device.number_of_nodes_per_site,
            number_of_sectors_per_node=sector_params.number_sectors_per_node,
            horizontal_scan_range=sector_params.horizontal_scan_range,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        for i, node in enumerate(nodes):
            for j, sector_azimuth in enumerate(node):
                n = Sector(
                    site=site,
                    node_id=i,
                    position_in_node=j,
                    ant_azimuth=sector_azimuth,
                    status_type=StatusType.CANDIDATE,
                )
                sectors_for_sites.setdefault(site_id, []).append(n.sector_id)
                topology.add_sector(n)


def create_cn_sectors(topology: Topology) -> None:
    # sectors_for_sites is used to indicate that we have already added
    # CN antennas
    sectors_for_sites = {}
    for sector_id, sector in topology.sectors.items():
        if sector.sector_type == SectorType.CN:
            sectors_for_sites.setdefault(sector.site.site_id, []).append(
                sector_id
            )

    # Get all wireless neighbor sites for CNs here.
    cn_wireless_neighbor_sites = {}
    for link in topology.links.values():
        if link.is_wireless and link.rx_site.site_type == SiteType.CN:
            cn_wireless_neighbor_sites.setdefault(
                link.rx_site.site_id, []
            ).append(topology.sites[link.tx_site.site_id])

    for site_id, site in topology.sites.items():
        if (
            len(sectors_for_sites.get(site_id, [])) > 0
            or site.site_type != SiteType.CN
        ):
            validate_site_sectors(
                [
                    topology.sectors[sector_id]
                    for sector_id in sectors_for_sites.get(site_id, [])
                ]
            )
            continue
        sector_params = site.device.sector_params
        nodes = find_best_equidistant_sectors(
            site=site,
            neighbor_site_list=cn_wireless_neighbor_sites.get(site_id, []),
            number_of_nodes=site.device.number_of_nodes_per_site,  # Forced to 1 in sector parameters
            number_of_sectors_per_node=sector_params.number_sectors_per_node,
            horizontal_scan_range=sector_params.horizontal_scan_range,
        )
        for i, node in enumerate(nodes):
            for j, sector_azimuth in enumerate(node):
                n = Sector(
                    site=site,
                    node_id=i,
                    position_in_node=j,
                    ant_azimuth=sector_azimuth,
                    status_type=StatusType.CANDIDATE,
                )
                sectors_for_sites.setdefault(site_id, []).append(n.sector_id)
                topology.add_sector(n)


def add_sectors_to_links(
    topology: Topology,
    force_full_cn_scan_range: bool,
    link_channel_map: Optional[Dict[str, int]],
) -> None:
    """
    Given a topology, assign the rx_sector_id and tx_sector_id of links where
    possible.

    @param topology: the underlying topology object.
    @param force_full_cn_scan_range: when enabled, treat CN horizontal_scan_range
    as 360 degress. This is enabled when this function is called prior to
    optimizing the topology so that all incoming candidate links are connected
    to the CN sector; during the optimization, only one of those links can be
    selected and the CN sector will point direclty at the incoming DN, so there
    is no risk of selecting a link that will not have a valid sector
    post-optimization.
    @param link_channel_map: channel map of active links.

    In-place modification of input topology.
    """
    sectors_for_sites: Dict[str, List[str]] = {}
    for sector_id, sector in topology.sectors.items():
        sectors_for_sites.setdefault(sector.site.site_id, []).append(sector_id)

    for link in topology.links.values():
        # If the link is wired then sectors are irrelevant
        if link.link_type == LinkType.ETHERNET:
            continue

        # If sectors are already assigned, just check that they are valid
        if link.tx_sector is not None or link.rx_sector is not None:
            validate_link_sectors(link, force_full_cn_scan_range)
            continue

        site_from = topology.sites[link.tx_site.site_id]
        site_to = topology.sites[link.rx_site.site_id]

        bearing_from_to = link.tx_beam_azimuth
        bearing_to_from = link.rx_beam_azimuth

        # Angle bearing issues are dogged by numerical precision issues that
        # are slightly larger than math.isclose() territory but still are noise.
        # Add tolerance to the min delta accordingly.
        horizontal_scan_range_from = (
            site_from.device.sector_params.horizontal_scan_range
        )
        horizontal_scan_range_to = (
            site_to.device.sector_params.horizontal_scan_range
            if site_to.site_type != SiteType.CN or not force_full_cn_scan_range
            else FULL_ROTATION_ANGLE
        )

        min_delta_from = (
            horizontal_scan_range_from / 2 + SECTOR_LINK_ANGLE_TOLERANCE
        )
        min_delta_to = (
            horizontal_scan_range_to / 2 + SECTOR_LINK_ANGLE_TOLERANCE
        )

        best_sector_from = None
        for sector_from_id in sectors_for_sites.get(site_from.site_id, []):
            sector_from = topology.sectors[sector_from_id]
            delta_from = abs(
                angle_delta(sector_from.ant_azimuth, bearing_from_to)
            )
            if delta_from < min_delta_from:
                min_delta_from = delta_from
                best_sector_from = sector_from

        best_sector_to = None
        for sector_to_id in sectors_for_sites.get(site_to.site_id, []):
            sector_to = topology.sectors[sector_to_id]
            delta_to = abs(angle_delta(sector_to.ant_azimuth, bearing_to_from))
            if delta_to < min_delta_to:
                min_delta_to = delta_to
                best_sector_to = sector_to

        if best_sector_from is None or best_sector_to is None:
            # During pre-optimization this likely inidcates a user-supplied active
            # link that has no sector assignment
            planner_assert(
                link.status_type not in StatusType.active_status(),
                "Unexpected issue causing an active link to not have a valid sector",
                OptimizerException,
            )

            # Sector decisions are final - if the link is excluded, we can't use it
            # Reset nodes: this is probably a no-op, but we may have to reset some
            # candidate links' nodes if the sectors changed during re-adjustment
            link.clear_sectors()
            continue

        tx_sector = none_throws(best_sector_from)
        rx_sector = none_throws(best_sector_to)
        link.tx_sector = tx_sector
        link.rx_sector = rx_sector
        reverse_link = topology.get_link_by_site_ids(
            link.rx_site.site_id, link.tx_site.site_id
        )
        if reverse_link is not None:
            reverse_link.tx_sector = rx_sector
            reverse_link.rx_sector = tx_sector

        if (
            link_channel_map is not None
            and link.status_type in StatusType.active_status()
        ):
            tx_sector.channel = rx_sector.channel = link_channel_map[
                link.link_id
            ]
            tx_sector.status_type = rx_sector.status_type = StatusType.PROPOSED


def validate_site_sectors(sectors: List[Sector]) -> None:
    if len(sectors) == 0:
        return

    site = sectors[0].site
    number_of_nodes = site.device.number_of_nodes_per_site
    number_of_sectors_per_node = (
        site.device.sector_params.number_sectors_per_node
    )
    horizontal_scan_range = site.device.sector_params.horizontal_scan_range
    sector_azimuths = {}
    sector_positions = {}
    for sector in sectors:
        planner_assert(
            sector.site is site,
            "Cannot validate sectors on different sites",
            OptimizerException,
        )
        node_id = sector.node_id
        sector_azimuths.setdefault(node_id, []).append(sector.ant_azimuth)
        planner_assert(
            sector.position_in_node not in sector_positions.get(node_id, set()),
            "Each sector in the same node must have different positions",
            OptimizerException,
        )
        sector_positions.setdefault(node_id, set()).add(sector.position_in_node)

    planner_assert(
        len(sector_azimuths) <= number_of_nodes,
        f"Number of nodes on a site cannot exceed {number_of_nodes}",
        OptimizerException,
    )

    for node_id, azimuths in sector_azimuths.items():
        planner_assert(
            len(azimuths) == number_of_sectors_per_node,
            f"Number of sectors in each node must be {number_of_sectors_per_node}",
            OptimizerException,
        )
        # Sort for easier processing, taking special care of the periodicity
        # of the azimuths (sort around circular mean)
        sin_sum = sum([math.sin(math.radians(a)) for a in azimuths])
        cos_sum = sum([math.cos(math.radians(a)) for a in azimuths])
        circ_mean = math.degrees(math.atan2(sin_sum, cos_sum)) % 360
        l1 = [
            a
            for a in azimuths
            if (a <= circ_mean and a > circ_mean - 180) or a > circ_mean + 180
        ]
        l1.sort()
        l2 = [
            a
            for a in azimuths
            if (a > circ_mean and a <= circ_mean + 180) or a <= circ_mean - 180
        ]
        l2.sort()
        sector_azimuths[node_id] = l1 + l2

    # First verify that each sector within the node are exactly horizontal scan
    # range apart. Note: azimuths should already be sorted
    if number_of_sectors_per_node > 1:
        for azimuths in sector_azimuths.values():
            for i in range(len(azimuths) - 1):
                angle_diff = abs(
                    angle_delta(azimuths[i], azimuths[(i + 1) % len(azimuths)])
                )
                planner_assert(
                    abs(angle_diff - horizontal_scan_range)
                    < SECTOR_LINK_ANGLE_TOLERANCE,
                    f"Sectors within the same node are separated by {angle_diff:0.1f}, "
                    f"but must be separated by the horizontal scan range {horizontal_scan_range}",
                    OptimizerException,
                )

    # Verify that the nodes are separate by at least the horizontal scan range
    # and that they do not overlap. Note: azimuths should already be sorted

    # Helper function to determine if a point is inside a periodic interval
    # E.g., 20 is inside [320, 40] (320 is equivalent to -40)
    def _inside_interval(p: float, start: float, end: float) -> bool:
        return (
            (p >= start and p <= end)
            if start <= end
            else (p >= start or p <= end)
        )

    for node_id, azimuths in sector_azimuths.items():
        for other_node_id, other_azimuths in sector_azimuths.items():
            if node_id == other_node_id:
                continue
            angle_diff1 = abs(angle_delta(azimuths[0], other_azimuths[0]))
            angle_diff2 = abs(angle_delta(azimuths[-1], other_azimuths[0]))
            angle_diff3 = abs(angle_delta(azimuths[0], other_azimuths[-1]))
            angle_diff4 = abs(angle_delta(azimuths[-1], other_azimuths[-1]))
            min_angle_diff = min(
                angle_diff1, angle_diff2, angle_diff3, angle_diff4
            )
            planner_assert(
                min_angle_diff >= horizontal_scan_range,
                f"Sector nodes are separated by {min_angle_diff:0.1f}, "
                f"but must be separated by at least the horizontal scan range {horizontal_scan_range}",
                OptimizerException,
            )

            overlap = (
                _inside_interval(other_azimuths[0], azimuths[0], azimuths[-1])
                or _inside_interval(
                    other_azimuths[-1], azimuths[0], azimuths[-1]
                )
                or _inside_interval(
                    azimuths[0], other_azimuths[0], other_azimuths[-1]
                )
                or _inside_interval(
                    azimuths[-1], other_azimuths[0], other_azimuths[-1]
                )
            )
            planner_assert(
                not overlap, "Sector nodes cannot overlap", OptimizerException
            )


def validate_link_sectors(
    link: Link, force_full_cn_scan_range: bool = False
) -> None:
    if link.tx_sector is None and link.rx_sector is None:
        return
    tx_horizontal_scan_range = (
        link.tx_site.device.sector_params.horizontal_scan_range
    )
    planner_assert(
        abs(none_throws(link.tx_dev))
        < tx_horizontal_scan_range / 2 + SECTOR_LINK_ANGLE_TOLERANCE,
        "Link is not within the horizontal scan range of the connected tx sector",
        OptimizerException,
    )
    if (
        force_full_cn_scan_range
        and none_throws(link.rx_sector).site.site_type == SiteType.CN
    ):
        return
    rx_horizontal_scan_range = (
        link.rx_site.device.sector_params.horizontal_scan_range
    )
    planner_assert(
        abs(none_throws(link.rx_dev))
        < rx_horizontal_scan_range / 2 + SECTOR_LINK_ANGLE_TOLERANCE,
        "Link is not within the horizontal scan range of the connected rx sector",
        OptimizerException,
    )


def find_best_equidistant_sectors(
    site: Site,
    neighbor_site_list: Iterable[Site],
    number_of_nodes: int,
    number_of_sectors_per_node: int,
    horizontal_scan_range: float,
) -> List[npt.NDArray[np.float64]]:
    """
    We find the best angles to orient the sectors. Currently we make the angles
    between adjacent sectors equal (inter_sector_angle). We rotate all sectors
    such that the mean squared difference in the bearing to neighboring sites
    (with rf connectivity) and the pointing angle of the sector (azimuth angle
    of the sector antenna) is minimized. The best rotation angle of sectors
    is chosen by computing the mean squared angular difference corresponding to
    equispaced (spaced by DEFAULT_POINTING_PRECISION) rotation angles in the
    range [0,arc_length) and picking the angle (best_rotation_angle) which
    minimizes the mean squared angular difference.
    """
    inter_node_angle = horizontal_scan_range * number_of_sectors_per_node
    num_nodes = min(
        int(FULL_ROTATION_ANGLE / inter_node_angle), number_of_nodes
    )
    arc_length = FULL_ROTATION_ANGLE / num_nodes
    default_node_angles = np.arange(num_nodes) * arc_length

    num_neighbors = sum(1 for _ in neighbor_site_list)
    if num_neighbors == 0:
        return []

    to_site_locs = np.vectorize(lambda site: (site.longitude, site.latitude))(
        neighbor_site_list
    )
    link_angles = bearing_in_degrees(
        site.longitude,
        site.latitude,
        to_site_locs[0],  # NDArray of longitudes of to_sites
        to_site_locs[1],  # NDArray latitude of to_sites
    )

    num_rotation_angles = round(arc_length / DEFAULT_POINTING_PRECISION)
    rotation_angles = (
        np.arange(num_rotation_angles) * arc_length / num_rotation_angles
    ).reshape(-1, 1)
    # We lump all sectors in a node together for the heuristic calculation.
    # N sectors of width W in a node are treated as one sector of width N*W
    node_ids = (
        np.round((link_angles - rotation_angles) / arc_length) % num_nodes
    )
    delta_angles = link_angles - node_ids * arc_length - rotation_angles
    delta_angles[abs(delta_angles) > inter_node_angle / 2] = FULL_ROTATION_ANGLE
    mets = np.sum(delta_angles**2, axis=1)
    best_met_idx = mets.argmin()
    best_rotation_angle = rotation_angles[best_met_idx, 0]
    node_angles = best_rotation_angle + default_node_angles
    return [
        get_sector_azimuths_from_node_center(
            node_angle, number_of_sectors_per_node, horizontal_scan_range
        )
        for node_angle in node_angles
    ]


def get_sector_azimuths_from_node_center(
    center_bearing: float, number_of_sectors: int, horizontal_scan_range: float
) -> npt.NDArray[np.float64]:
    """
    Helper function to get the sector azimuth positions for a node at position
    center_bearing. Returns a numpy array of equally spaced azimuths centered
    at the center_bearing input.

    @param center_bearing: the bearing, in degrees, of the middle of the node
    @param number_of_sectors: the number of sectors in the node
    @param horizontal_scan_range: width, in degrees, of a sector's range
    """
    if number_of_sectors == 0:
        return np.array([])
    if number_of_sectors % 2 == 0:
        # even number: sectors are half a scan range off center
        start_sector_angle = center_bearing - horizontal_scan_range * (
            number_of_sectors / 2 - 0.5
        )
        end_sector_angle = center_bearing + horizontal_scan_range * (
            number_of_sectors / 2 - 0.5
        )
    else:
        # odd number: center sector is exactly at center_bearing
        start_sector_angle = (
            center_bearing
            - horizontal_scan_range * math.floor(number_of_sectors / 2)
        )
        end_sector_angle = center_bearing + horizontal_scan_range * math.floor(
            number_of_sectors / 2
        )

    # overshoot by horizontal_beamwdith / 2 so we always finish at end_sector_angle
    sector_positions = (
        np.arange(
            start_sector_angle,
            end_sector_angle + horizontal_scan_range / 2,
            horizontal_scan_range,
        )
        % FULL_ROTATION_ANGLE
    )
    planner_assert(
        len(sector_positions) == number_of_sectors,
        "Number of sector positions does not match number of sectors",
        OptimizerException,
    )
    return sector_positions


def find_best_sectors(
    site: Site,
    neighbor_site_list: Iterable[Site],
    number_of_nodes: int,
    number_of_sectors_per_node: int,
    horizontal_scan_range: float,
    dn_dn_sector_limit: Optional[int],
    dn_total_sector_limit: Optional[int],
    diff_sector_angle_limit: Optional[float],
    near_far_angle_limit: Optional[float],
    near_far_length_ratio: Optional[float],
    backhaul_link_type_weight: Optional[float],
    sector_channel_list: Optional[List[Tuple[str, int]]],
) -> List[npt.NDArray[np.float64]]:
    """
    We find the best angles to orient the sectors, which are chosen by computing
    the mean squared angular difference between sector azimuths and link angles,
    link type and distance are also used.
    We mainly have three steps to find best sectors:
    Step 1: Compute link angles and distances for each neighbor site
    Step 2: Get all candidate for sector positions in the range [0, 360) (spaced
            by DEFAULT_POINTING_PRECISION), filter out those violating the
            constraints and compute the sum of squared angular for each candidate
            position if it's chosen
    Step 3: Use dynamic programming to find the best position. First choose a
            candidate as the first sector position, and for each first sector
            position, mets[i][j] equal to the minimal sum of squared angular
            difference when we have i sectors assigned and the last sector
            position is at the angle azimuth_candidate[j]
            mets[i][j] = min(mets[i-1][k] + node_mets[j]) for all k if
            azimuth_candidate[k] is not inferenced by zimuth_candidate[j]

    @param site: the subject site to find best sector angles
    @param neighbor_site_list: list of neighbor sites that connected with the subject site
    @param number_of_nodes: maximum number of radio nodes allowed on each site
    @param number_of_sectors_per_node: the number of sectors in the node
    @param horizontal_scan_range: width, in degrees, of a sector's range
    @param dn_dn_sector_limit: maximum DN-DN radio connections
    @param dn_total_sector_limit: maximum total DN radio connections
    @param diff_sector_angle_limit: different radio link angle limit
    @param near_far_angle_limit: the minimum angle between two links that are leaving
            different radios if the ratio of their lengths is large
    @param near_far_length_ratio: the smallest length ratio of two links that are leaving
            different radios on the same site which could cause near-far effect
    @param backhaul_link_type_weight: weight of backhaul link type, access link is 1
    @param sector_channel_list: (tx_sector_id, channel) list of links to neighbor sites,
            None if all channels are unique
    """

    num_neighbors = sum(1 for _ in neighbor_site_list)
    if num_neighbors == 0:
        return []

    num_nodes = min(
        int(
            FULL_ROTATION_ANGLE
            / (horizontal_scan_range * number_of_sectors_per_node)
        ),
        number_of_nodes,
    )

    # Step 1: Compute link_angles and link_dists
    neighbor_site_locs = np.vectorize(
        lambda site: (site.longitude, site.latitude)
    )(neighbor_site_list)
    link_angles = bearing_in_degrees(
        site.longitude,
        site.latitude,
        neighbor_site_locs[0],  # ndarray of to_sites longitude
        neighbor_site_locs[1],  # ndarray of to_sites latitude
    )
    link_dists = haversine_distance(
        site.longitude,
        site.latitude,
        neighbor_site_locs[0],
        neighbor_site_locs[1],
    )

    # link pairs violate different sector angle limit or near-far ratio rules
    angle_violation_pairs = []
    if diff_sector_angle_limit is not None or (
        near_far_angle_limit is not None and near_far_length_ratio is not None
    ):
        for j1, j2 in combinations(range(num_neighbors), 2):
            angle_diff, length_ratio = law_of_cosines_spherical(
                site.latitude,
                site.longitude,
                neighbor_site_locs[1][j1],
                neighbor_site_locs[0][j1],
                neighbor_site_locs[1][j2],
                neighbor_site_locs[0][j2],
            )
            if (
                diff_sector_angle_limit is not None
                and angle_diff <= diff_sector_angle_limit
            ) or (
                near_far_angle_limit is not None
                and angle_diff <= near_far_angle_limit
                and near_far_length_ratio is not None
                and length_ratio >= near_far_length_ratio
            ):
                angle_violation_pairs.append((j1, j2))

    diff_sector_violation_pairs = []
    same_sector_violation_pairs = []
    if sector_channel_list is not None:
        # multi-channels plan with more than 1 channel assigned to the site
        for j1, j2 in combinations(range(num_neighbors), 2):
            # links were from the same sector cannot be assigned to diff sector
            # here already considered angle rules since they were applied in optimizer
            if sector_channel_list[j1][0] == sector_channel_list[j2][0]:
                diff_sector_violation_pairs.append((j1, j2))
            # links were with diff channels cannot be assigned to the same sector
            if sector_channel_list[j1][1] != sector_channel_list[j2][1]:
                same_sector_violation_pairs.append((j1, j2))
    else:
        # angle violation check only needed when there is unique channel
        diff_sector_violation_pairs = angle_violation_pairs

    # Step 2: Pre-compute sum of square difference for each potential
    # sector azimuth, and filter out those invalid candidates
    # UNCOVERED_PENALTY used to make sure that the result sectors cover
    # all the sites
    UNCOVERED_PENALTY = 1e6 * num_neighbors
    num_azimuth_candidates = int(
        FULL_ROTATION_ANGLE / DEFAULT_POINTING_PRECISION
    )

    # we have to track node candidates and sector candidates separately so we
    # can tell when a sector is overloaded
    node_azimuth_candidates = (
        np.arange(num_azimuth_candidates).reshape(-1, 1)
        * DEFAULT_POINTING_PRECISION
    )
    sector_azimuth_candidates = np.array(
        [
            get_sector_azimuths_from_node_center(
                cb, number_of_sectors_per_node, horizontal_scan_range
            ).reshape(-1, 1)
            for cb in node_azimuth_candidates
        ]
    )
    # Angle delta between node and link
    node_delta = abs(node_azimuth_candidates - link_angles)
    # Angle delta between sector and link
    sector_delta = abs(sector_azimuth_candidates - link_angles)

    # Change delta into [0, 180]
    node_delta = FULL_ROTATION_ANGLE / 2 - abs(
        FULL_ROTATION_ANGLE / 2 - node_delta
    )
    sector_delta = FULL_ROTATION_ANGLE / 2 - abs(
        FULL_ROTATION_ANGLE / 2 - sector_delta
    )

    # sector_azimuth_link_mat[k][i][j] == 1 iff the i-th sector of node k can cover link_angles[j]
    sector_azimuth_link_mat = np.zeros(
        (num_azimuth_candidates, number_of_sectors_per_node, num_neighbors)
    )
    sector_azimuth_link_mat[
        np.logical_and(
            sector_delta >= -horizontal_scan_range / 2,
            sector_delta < horizontal_scan_range / 2,
        )
    ] = 1
    # node_azimuth_link_mat[k][j] == 1 iff the node k can cover link_angles[j]
    node_azimuth_link_mat = np.zeros((num_azimuth_candidates, num_neighbors))
    node_azimuth_link_mat[
        np.logical_and(
            node_delta
            >= -horizontal_scan_range * number_of_sectors_per_node / 2,
            node_delta < horizontal_scan_range * number_of_sectors_per_node / 2,
        )
    ] = 1

    sector_list = list(
        product(
            list(range(num_azimuth_candidates)),
            list(range(number_of_sectors_per_node)),
        )
    )
    # Prune away the sector/node if it covers two links which must be on
    # different sectors under the multi-channels plan
    if len(same_sector_violation_pairs) > 0:
        for j1, j2 in same_sector_violation_pairs:
            for (k, i) in sector_list:
                if (
                    sector_azimuth_link_mat[k][i][j1] == 1
                    and sector_azimuth_link_mat[k][i][j2] == 1
                ):
                    sector_azimuth_link_mat[k][i][j1] = 0
                    sector_azimuth_link_mat[k][i][j2] = 0
            for k in range(num_azimuth_candidates):
                if (
                    node_azimuth_link_mat[k][j1] == 1
                    and node_azimuth_link_mat[k][j2] == 1
                ):
                    node_azimuth_link_mat[k][j1] = 0
                    node_azimuth_link_mat[k][j2] = 0
    # Prune away the combination of sectors/nodes pairs if they cover two links
    # separately and must be on the same sector, i.e. either violate different
    # sector angle limit / near-far ratio rules, or under the multi-channels plan
    if len(diff_sector_violation_pairs) > 0:
        for j1, j2 in diff_sector_violation_pairs:
            for (k1, i1), (k2, i2) in combinations(sector_list, 2):
                if (
                    sector_azimuth_link_mat[k1][i1][j1] == 1
                    and sector_azimuth_link_mat[k1][i1][j2] == 0
                    and sector_azimuth_link_mat[k2][i2][j1] == 0
                    and sector_azimuth_link_mat[k2][i2][j2] == 1
                ):
                    sector_azimuth_link_mat[k1][i1][j1] = 0
                    sector_azimuth_link_mat[k2][i2][j2] = 0
                if (
                    sector_azimuth_link_mat[k2][i2][j1] == 1
                    and sector_azimuth_link_mat[k2][i2][j2] == 0
                    and sector_azimuth_link_mat[k1][i1][j1] == 0
                    and sector_azimuth_link_mat[k1][i1][j2] == 1
                ):
                    sector_azimuth_link_mat[k2][i2][j1] = 0
                    sector_azimuth_link_mat[k1][i1][j2] = 0
            for k1, k2 in combinations(list(range(num_azimuth_candidates)), 2):
                if (
                    node_azimuth_link_mat[k1][j1] == 1
                    and node_azimuth_link_mat[k1][j2] == 0
                    and node_azimuth_link_mat[k2][j1] == 0
                    and node_azimuth_link_mat[k2][j2] == 1
                ):
                    node_azimuth_link_mat[k1][j1] = 0
                    node_azimuth_link_mat[k2][j2] = 0
                if (
                    node_azimuth_link_mat[k2][j1] == 1
                    and node_azimuth_link_mat[k2][j2] == 0
                    and node_azimuth_link_mat[k1][j1] == 0
                    and node_azimuth_link_mat[k1][j2] == 1
                ):
                    node_azimuth_link_mat[k2][j1] = 0
                    node_azimuth_link_mat[k1][j2] = 0

    dist_type_sites = np.vectorize(
        lambda site: 1 if site.site_type in SiteType.dist_site_types() else 0
    )(neighbor_site_list)
    link_type_weight = backhaul_link_type_weight or 1
    dist_type_weight = np.vectorize(
        lambda site: link_type_weight
        if site.site_type in SiteType.dist_site_types()
        else 1
    )(neighbor_site_list)

    # get indexes of sectors that have a reasonable number of links assigned
    # note that pre-optimization, this is a no-op. If sector limits aren't
    # specified, max them out - they won't constrain the problem at all.
    if dn_dn_sector_limit is None:
        dn_dn_sector_limit = num_neighbors
    if dn_total_sector_limit is None:
        dn_total_sector_limit = num_neighbors
    valid_candidate_idx = np.logical_and(
        np.all(
            sector_azimuth_link_mat.sum(axis=2) <= dn_total_sector_limit, axis=1
        ),
        np.all(
            (sector_azimuth_link_mat * dist_type_sites).sum(axis=2)
            <= dn_dn_sector_limit,
            axis=1,
        ),
    )
    # this should never happen in pre-optimization
    if not any(valid_candidate_idx):
        return []

    sector_delta = sector_delta[valid_candidate_idx]
    azimuth_candidates = node_azimuth_candidates.reshape(-1)[
        valid_candidate_idx
    ]
    node_azimuth_link_mat = node_azimuth_link_mat[valid_candidate_idx]
    sector_azimuth_link_mat = sector_azimuth_link_mat[valid_candidate_idx]
    sector_weighted = (
        sector_delta**2
        * link_dists
        / max(link_dists)  # pyre-fixme
        * dist_type_weight
    )
    sector_weighted[sector_azimuth_link_mat == 0] = UNCOVERED_PENALTY
    node_mets = sector_weighted.sum(axis=(1, 2))
    num_azimuth_candidates = azimuth_candidates.shape[0]

    # Step 3: Dynamic programming to get best sector positions
    # Upper bound is all angles being missed by all nodes. There should be at
    # least one configuration better than this.
    best_met = (
        num_nodes * number_of_sectors_per_node * num_neighbors + 1
    ) * UNCOVERED_PENALTY**2
    best_position = None
    for first_node_idx in range(num_azimuth_candidates):
        if (
            azimuth_candidates[first_node_idx]
            >= FULL_ROTATION_ANGLE
            - (num_nodes - 1)
            * horizontal_scan_range
            * number_of_sectors_per_node
        ):
            break
        mets = [[math.inf] * num_azimuth_candidates for _ in range(num_nodes)]
        # prev_sector used to record the position for the best solution
        prev_sector = [[-1] * num_azimuth_candidates for _ in range(num_nodes)]
        mets[0][first_node_idx] = node_mets[first_node_idx]
        for num_assigned_nodes in range(0, num_nodes - 1):
            for candidate_idx in range(num_azimuth_candidates):
                if mets[num_assigned_nodes][candidate_idx] < math.inf:
                    for next_candidate_idx in range(
                        candidate_idx + 1, num_azimuth_candidates
                    ):
                        # Interfere with the last sector
                        if (
                            azimuth_candidates[next_candidate_idx]
                            - azimuth_candidates[candidate_idx]
                            < horizontal_scan_range * number_of_sectors_per_node
                        ):
                            continue
                        # Interfere with the first sector
                        if (
                            azimuth_candidates[first_node_idx]
                            + FULL_ROTATION_ANGLE
                            - azimuth_candidates[next_candidate_idx]
                            < horizontal_scan_range * number_of_sectors_per_node
                        ):
                            break
                        if (
                            mets[num_assigned_nodes][candidate_idx]
                            + node_mets[next_candidate_idx]
                            < mets[num_assigned_nodes + 1][next_candidate_idx]
                        ):
                            mets[num_assigned_nodes + 1][next_candidate_idx] = (
                                mets[num_assigned_nodes][candidate_idx]
                                + node_mets[next_candidate_idx]
                            )
                            prev_sector[num_assigned_nodes + 1][
                                next_candidate_idx
                            ] = candidate_idx
        best_met_this_round = min(mets[-1])
        if best_met_this_round < best_met:
            best_met = best_met_this_round
            best_idx = mets[-1].index(best_met)
            best_position = [best_idx]
            for node_idx in range(num_nodes - 1, 0, -1):
                best_idx = prev_sector[node_idx][best_idx]
                best_position.append(best_idx)

    # Something is very wrong if we couldn't improve on the original `mets`
    planner_assert(
        best_position is not None,
        "Could not find best sector position",
        OptimizerException,
    )
    return [
        get_sector_azimuths_from_node_center(
            azimuth_candidates[sector_idx],
            number_of_sectors_per_node,
            horizontal_scan_range,
        )
        for sector_idx in reversed(none_throws(best_position))
        if sum(node_azimuth_link_mat[sector_idx])
        > 0  # drop nodes that cover nothing
    ]


def validate_topology_status(topology: Topology) -> None:
    """
    This function validates the consistency of the status type between
    the links, sites and sectors before optimization as well as before reporting.
    An error will be thrown if inconsistent status type found.
    """
    for link in topology.links.values():
        # Symmetric links, i.e. links (i, j) and (j, i), must have the same status type.
        reverse_link = topology.get_link_by_site_ids(
            link.rx_site.site_id, link.tx_site.site_id
        )
        if link.link_type != LinkType.WIRELESS_ACCESS:
            planner_assert(
                reverse_link is not None,
                f"Backhaul link {link.link_id} must be bidirectional.",
                TopologyException,
            )
        if reverse_link is None:
            continue
        planner_assert(
            link.status_type == reverse_link.status_type,
            f"A link {link.link_id} and its symmetric link have conflicting status types.",
            TopologyException,
        )

        # Existing link must be connected to existing sites/sectors.
        if link.status_type == StatusType.EXISTING:
            planner_assert(
                link.tx_site.status_type == StatusType.EXISTING
                and link.rx_site.status_type == StatusType.EXISTING,
                f"Existing link {link.link_id} must be connected to existing sites.",
                TopologyException,
            )
            planner_assert(
                link.tx_sector is not None
                and none_throws(link.tx_sector).status_type
                == StatusType.EXISTING
                and link.rx_sector is not None
                and none_throws(link.rx_sector).status_type
                == StatusType.EXISTING,
                f"Existing link {link.link_id} must be connected to existing sectors.",
                TopologyException,
            )
        # Proposed link must be connected to active sites/sectors.
        elif link.status_type == StatusType.PROPOSED:
            planner_assert(
                link.tx_site.status_type in StatusType.active_status()
                and link.rx_site.status_type in StatusType.active_status(),
                f"Active link {link.link_id} must be connected to active sites.",
                TopologyException,
            )
            planner_assert(
                link.tx_sector is not None
                and none_throws(link.tx_sector).status_type
                in StatusType.active_status()
                and link.rx_sector is not None
                and none_throws(link.rx_sector).status_type
                in StatusType.active_status(),
                f"Active link {link.link_id} must be connected to active sectors.",
                TopologyException,
            )
        # Candidate link cannot be connected to inactive sites/sectors.
        elif link.status_type == StatusType.CANDIDATE:
            planner_assert(
                link.tx_site.status_type not in StatusType.inactive_status()
                and link.rx_site.status_type
                not in StatusType.inactive_status(),
                f"Candidate link {link.link_id} cannot be connected to inactive sites.",
                TopologyException,
            )
            planner_assert(
                (
                    link.tx_sector is None
                    or none_throws(link.tx_sector).status_type
                    not in StatusType.inactive_status()
                )
                and (
                    link.rx_sector is None
                    or none_throws(link.rx_sector).status_type
                    not in StatusType.inactive_status()
                ),
                f"Candidate link {link.link_id} cannot be connected to inactive sectors.",
                TopologyException,
            )
