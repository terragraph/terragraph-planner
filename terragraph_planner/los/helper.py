# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
from collections import defaultdict, deque
from copy import deepcopy
from functools import partial
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import numpy.typing as npt
from osgeo import osr
from pyre_extensions import none_throws
from shapely import wkt
from shapely.geometry import Polygon
from shapely.prepared import prep

from terragraph_planner.common.configuration.configs import (
    DeviceData,
    GISDataParams,
    LOSParams,
    SectorParams,
)
from terragraph_planner.common.configuration.enums import (
    DeviceType,
    LocationType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.constants import (
    LOWER_BOUND_FOR_LOS_DISTANCE,
    UPPER_BOUND_FOR_LOS_DISTANCE,
)
from terragraph_planner.common.data_io.input_sites_loader import (
    InputSitesLoader,
)
from terragraph_planner.common.data_io.kml_library import extract_polygons
from terragraph_planner.common.data_io.utils import extract_topology_from_file
from terragraph_planner.common.exceptions import (
    ConfigException,
    LOSException,
    planner_assert,
)
from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.rf.link_budget_calculator import (
    fspl_based_estimation,
    get_max_tx_power,
)
from terragraph_planner.common.structs import (
    CandidateLOS,
    MCSMap,
    UTMBoundingBox,
    ValidLOS,
)
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.site import (
    DetectedSite,
    LOSSite,
    Site,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.los.constants import (
    BI_DIRECTIONAL_LINKS,
    BUILDING_HEIGHT_THRESHOLD,
    DIRECTED_LINKS,
    DISTANCE_TOLERANCE_PERCENT,
    ELE_SCAN_ANGLE_TOLERANCE,
)
from terragraph_planner.los.cylindrical_los_validator import (
    CylindricalLOSValidator,
)
from terragraph_planner.los.elevation import Elevation
from terragraph_planner.los.ellipsoidal_los_validator import (
    EllipsoidalLOSValidator,
)

logger: logging.Logger = logging.getLogger(__name__)


def pre_los_check(
    los_params: LOSParams, gis_data_params: GISDataParams
) -> None:
    """
    Before doing the actual LOS computation, check if there will be errors.
    """
    if gis_data_params.building_outline_file_path is None:
        return
    site_detection = los_params.site_detection
    # If CN will be detected
    if (
        site_detection.detect_centers
        or site_detection.detect_corners
        or site_detection.detect_highest
    ):
        for device in los_params.device_list:
            if device.device_type == DeviceType.CN:
                break
        else:
            raise LOSException(
                "CN sites will be detected, but no CN device is provided."
            )
        # If DN will be detected
        if site_detection.dn_deployment:
            for device in los_params.device_list:
                if device.device_type == DeviceType.DN:
                    break
            else:
                raise LOSException(
                    "DN sites will be detected, but no DN device is provided."
                )


def infer_input_site_location(
    latitude: float,
    longitude: float,
    altitude: Optional[float],
    height: Optional[float],
    location_type: LocationType,
    site_type: SiteType,
    surface_elevation: Optional[Elevation],
    terrain_elevation: Optional[Elevation],
    mounting_height_above_rooftop: float,
    default_pop_height_on_pole: float,
    default_dn_height_on_pole: float,
    default_cn_height_on_pole: float,
) -> Tuple[GeoLocation, LocationType]:
    """
    Infer the location and location site of an input site, return in GeoLocation and LocationType.
    @param latitude, longitude
    The 2-D location of the input site.
    @param altitude, height
    The altitude/height inputed by user. Both can be None.
    @param location_type
    The input location_type. Only infer it when it's unknown.
    @param site_type
    Site type of the input site, used to detemine which default is applied.
    @param surface_elevation, terrain_elevation
    The elevation data used to infer the location.
    @param mounting_height_above_rooftop
    Only apply when the input altitude and height is None, and the location type is ROOFTOP.
    @param default_pop_height_on_pole, default_dn_height_on_pole, default_cn_height_on_pole
    Only apply when the input altitude and height is None, and the location type is not ROOFTOP.
    """
    location = GeoLocation(
        latitude=latitude, longitude=longitude, altitude=altitude
    )
    # Is no surface elevation data is provided, the planner is not able
    # to infer either altitude or location type
    if surface_elevation is None:
        return location, location_type

    surface_elevation = none_throws(surface_elevation)
    cur_surface_elevation = float(
        surface_elevation.get_value(location.utm_x, location.utm_y)
    )

    # Only infer the location type when it's unknown and there's terrain elevation data
    if location_type == LocationType.UNKNOWN and terrain_elevation is not None:
        if (
            cur_surface_elevation
            - terrain_elevation.get_value(location.utm_x, location.utm_y)
            >= BUILDING_HEIGHT_THRESHOLD
        ):
            location_type = LocationType.ROOFTOP
        else:
            location_type = LocationType.STREET_LEVEL

    # No need to infer the altitude when it's given
    if altitude is not None:
        return location, location_type
    # No need to use the default height if the height is given
    if height is not None:
        location = location.copy(altitude=cur_surface_elevation + height)
        return location, location_type

    if location_type == LocationType.ROOFTOP:
        location = location.copy(
            altitude=cur_surface_elevation + mounting_height_above_rooftop
        )
        return location, location_type

    if site_type == SiteType.POP:
        location = location.copy(
            altitude=cur_surface_elevation + default_pop_height_on_pole
        )
    elif site_type == SiteType.DN:
        location = location.copy(
            altitude=cur_surface_elevation + default_dn_height_on_pole
        )
    else:
        location = location.copy(
            altitude=cur_surface_elevation + default_cn_height_on_pole
        )
    return location, location_type


def get_exclusion_zones(
    user_input_file_path: Optional[str], ll_boundary: Polygon
) -> List[Polygon]:
    """
    Get a list of Polygon, representing the exclusion zones. boundary polygon
    is used to filter out zones not fully contained in the boundary.
    """
    if user_input_file_path is not None and len(user_input_file_path) > 0:
        ext = user_input_file_path.split(".")[-1].casefold()
        # CSV file does not support exclusion zones
        if ext == "kmz" or ext == "kml":
            exclusion_polygons = extract_polygons(user_input_file_path)
            prepared_boundary = prep(ll_boundary)
            return list(filter(prepared_boundary.contains, exclusion_polygons))
    return []


def get_all_sites_links_and_exclusion_zones(
    gis_data_params: GISDataParams,
    los_params: LOSParams,
    ll_boundary: Polygon,
    detected_sites: List[Site],
    surface_elevation: Optional[Elevation],
    terrain_elevation: Optional[Elevation],
) -> Tuple[List[Site], List[CandidateLOS], List[ValidLOS], List[Polygon]]:
    """
    - Extract delta sites and exclusion zones from user input csv/kml, and filter them with
    boundary polygon.
    - Conveted detected sites into the same format of input delta sites
    - Extract sites of the base topology. Merge input delta sites, detected sites as
    well as base sites, and then get all the sites.
    - Build candidate links to be validated by the LOSValidator. One end site of the candidate
    link comes from the input delta sites or detected sites, and the other could be any site from
    all sites. Note that the "candidate" here does not mean the final status of the link, but
    it's candidate link to be validated by the LOSValidator.
    - Extract existing links of the base topology. Note that the "existing" here does not mean
    the final status of the link, but it exists in the base topology.
    @param gis_data_params
    The params containing file paths of all the needed data.
    @param los_params
    Input config for building candidate graph. Has all the params needed to extract
    the input sites and exclusion zones
    @param ll_boundary
    A boundary polygon in lat and lon.
    @param detected_site_list
    Detected sites from detect_site_candidates step. May contain DNs and CNs, but it's
    not grouped.
    @param surface_elevation
    2-D surface elevation data. Used to calculate altitude of the input sites and
    determine whether a input site is on the strret level or the building rooftops when
    terrain data is also available.
    @param terrain_elevation
    2-D terrain elevation data. Used to determine whether a input site is on the street level
    or the building rooftops when available.
    """
    input_delta_sites = InputSitesLoader(
        los_params.device_list
    ).read_user_input(
        gis_data_params.site_file_path,
        ll_boundary,
        partial(
            infer_input_site_location,
            surface_elevation=surface_elevation,
            terrain_elevation=terrain_elevation,
            mounting_height_above_rooftop=los_params.mounting_height_above_rooftop,
            default_pop_height_on_pole=los_params.default_pop_height_on_pole,
            default_dn_height_on_pole=los_params.default_dn_height_on_pole,
            default_cn_height_on_pole=los_params.default_cn_height_on_pole,
        ),
    )

    if (
        gis_data_params.base_topology_file_path is not None
        and len(gis_data_params.base_topology_file_path) > 0
    ):
        base_topology = extract_topology_from_file(
            gis_data_params.base_topology_file_path, los_params.device_list
        )
    else:
        base_topology = Topology()

    base_sites = list(base_topology.sites.values())

    all_sites = input_delta_sites.site_list + detected_sites + base_sites

    logger.info(f"{len(all_sites)} sites are detected or inputed in total.")

    candidate_links: List[CandidateLOS] = []
    for i in range(len(input_delta_sites) + len(detected_sites)):
        for j in range(i + 1, len(all_sites)):
            site1 = all_sites[i]
            site2 = all_sites[j]
            if (site1.site_type, site2.site_type) in BI_DIRECTIONAL_LINKS:
                candidate_links.append(CandidateLOS(i, j, True))
            elif (site1.site_type, site2.site_type) in DIRECTED_LINKS:
                candidate_links.append(CandidateLOS(i, j, False))
            elif (site2.site_type, site1.site_type) in DIRECTED_LINKS:
                candidate_links.append(CandidateLOS(j, i, False))

    existing_links: List[ValidLOS] = []
    site_id_to_idx: Dict[str, int] = {}
    base_idx = len(input_delta_sites) + len(detected_sites)
    for oft, site in enumerate(base_sites):
        site_id_to_idx[site.site_id] = base_idx + oft
    for link in base_topology.links.values():
        existing_links.append(
            ValidLOS(
                site_id_to_idx[link.tx_site.site_id],
                site_id_to_idx[link.rx_site.site_id],
                1.0,
            )
        )

    exclusion_zones = get_exclusion_zones(
        gis_data_params.site_file_path, ll_boundary
    )

    logger.info(
        f"{len(candidate_links)} links are prepared for computing line-of-sight."
    )

    return all_sites, candidate_links, existing_links, exclusion_zones


def get_max_los_dist_for_device_pairs(
    device_list: List[DeviceData],
    max_eirp_dbm: Optional[float],
    min_dn_dn_mcs: Optional[int],
    min_dn_cn_mcs: Optional[int],
    los_upper_bound: Optional[int],
) -> Dict[Tuple[str, str], int]:
    """
    Given a list of devices, return the max LOS distance of each pair of devices, by
    computing the max distance to get a non-zero capacity between two devices.
    @param device_list
    A list of device data.
    @param max_eirp_dbm
    max tx power.
    @param min_dn_dn_mcs/min_dn_cn_mcs
    Minimum MCS class for DN-DN and DN-CN links, respectively. This value is independent
    of the Min MCS in the sector parameters within the device list although it will only
    impact results if it is larger than that Min MCS value. Its purpose is to further
    constrain the length of the links within the candidate graph.
    @return
    A dict mapping a pair of device SKUs to the max los distance.
    """
    device_to_max_tx_power: Dict[str, float] = {
        device.device_sku: get_max_tx_power(
            device.sector_params, None, max_eirp_dbm
        )
        for device in device_list
    }
    device_pair_to_max_los_dist: Dict[Tuple[str, str], int] = {}

    for tx_device in device_list:
        if tx_device.device_type == DeviceType.CN:
            continue
        for rx_device in device_list:
            mcs_snr_mbps_map = rx_device.sector_params.mcs_map

            if (
                rx_device.device_type == DeviceType.DN
                and min_dn_dn_mcs is not None
            ):
                mcs_snr_mbps_map = [
                    mcs_map
                    for mcs_map in mcs_snr_mbps_map
                    if mcs_map.mcs >= min_dn_dn_mcs
                ]
                if len(mcs_snr_mbps_map) == 0:
                    raise ConfigException(
                        "Min DN-DN MCS level is larger than the max MCS level in the mapping table."
                    )
            elif (
                rx_device.device_type == DeviceType.CN
                and min_dn_cn_mcs is not None
            ):
                mcs_snr_mbps_map = [
                    mcs_map
                    for mcs_map in mcs_snr_mbps_map
                    if mcs_map.mcs >= min_dn_cn_mcs
                ]
                if len(mcs_snr_mbps_map) == 0:
                    raise ConfigException(
                        "Min DN-CN MCS level is larger than the max MCS level in the mapping table."
                    )

            max_los_distance = search_max_los_dist_based_on_capacity(
                LOWER_BOUND_FOR_LOS_DISTANCE,
                UPPER_BOUND_FOR_LOS_DISTANCE,
                device_to_max_tx_power[tx_device.device_sku],
                tx_device.sector_params,
                rx_device.sector_params,
                mcs_snr_mbps_map,
            )
            planner_assert(
                max_los_distance is not None,
                f"The max LOS distance should not exceed {UPPER_BOUND_FOR_LOS_DISTANCE}.",
                LOSException,
            )
            logger.info(
                f"Max LOS distance for {tx_device.device_sku}->{rx_device.device_sku} is {max_los_distance}"
            )

            # If the device pairs are DN <-> DN and the max LOS distance of its reverse direction
            # has been computed, use the larger one of max LOS distance of two directions and
            # update the max LOS distance of its reverse direction
            if (
                rx_device.device_sku,
                tx_device.device_sku,
            ) in device_pair_to_max_los_dist:
                max_los_distance = max(
                    device_pair_to_max_los_dist[
                        (rx_device.device_sku, tx_device.device_sku)
                    ],
                    none_throws(max_los_distance),
                )
                device_pair_to_max_los_dist[
                    (rx_device.device_sku, tx_device.device_sku)
                ] = max_los_distance
            device_pair_to_max_los_dist[
                (tx_device.device_sku, rx_device.device_sku)
            ] = none_throws(max_los_distance)

        if los_upper_bound is not None:
            for device_pair, dist in device_pair_to_max_los_dist.items():
                if dist > los_upper_bound:
                    device_pair_to_max_los_dist[device_pair] = los_upper_bound
                    logger.warning(
                        f"The max los distance between {device_pair} evaluates to {dist} based on the "
                        f"device data, but the input global max los distance is {los_upper_bound}."
                    )

    return device_pair_to_max_los_dist


def search_max_los_dist_based_on_capacity(
    lower_bound: int,
    upper_bound: int,
    max_tx_power: float,
    tx_sector_params: SectorParams,
    rx_sector_params: SectorParams,
    mcs_snr_mbps_map: List[MCSMap],
) -> Optional[int]:
    """
    Get a max los distance for a device pair, by binary searching the minimal distance to have
    zero capacity.
    @param lower_bound
    A int indicating the lower bound of the searching space.
    @param upper_bound
    A int indicating the upper bound of the searching space
    @param max_tx_power
    The maximum power of the transmitter device.
    @param tx_sector_params
    The list of parameters that has tx radio related specifications.
    @param rx_sector_params
    The list of parameters that has rx radio related specifications.
    @param mcs_snr_mbps_map
    Mapping between mcs, snr and down-link throughput (mbps)
    @return
    A int indicating the minimal distance to have zero capacity. Return None if
    even the upper bound has a non-zero capacity; return lower_bound if lower_bound
    has a zero capacity.
    """
    mid, capacity = 0, 0
    while lower_bound < upper_bound:
        mid = (lower_bound + upper_bound) // 2
        link_budget_measurements = fspl_based_estimation(
            distance=mid,
            max_tx_power=max_tx_power,
            tx_sector_params=tx_sector_params,
            rx_sector_params=rx_sector_params,
            mcs_snr_mbps_map=mcs_snr_mbps_map,
            tx_deviation=0.0,
            rx_deviation=0.0,
            el_deviation=0.0,
            tx_scan_pattern_data=None,
            rx_scan_pattern_data=None,
        )
        capacity = link_budget_measurements.capacity
        if capacity > 0:
            lower_bound = mid + 1
        else:
            upper_bound = mid
    # Computes the capacity of the lower bound again.
    # If capacity > 0, it means the input upper_bound still has capacity > 0
    link_budget_measurements = fspl_based_estimation(
        distance=lower_bound,
        max_tx_power=max_tx_power,
        tx_sector_params=tx_sector_params,
        rx_sector_params=rx_sector_params,
        mcs_snr_mbps_map=mcs_snr_mbps_map,
        tx_deviation=0.0,
        rx_deviation=0.0,
        el_deviation=0.0,
        tx_scan_pattern_data=None,
        rx_scan_pattern_data=None,
    )
    capacity = link_budget_measurements.capacity
    if capacity > 0:
        return None
    else:
        return lower_bound


def compute_los_batch(
    candidate_links: List[CandidateLOS],
    los_sites: List[LOSSite],
    exclusion_zones_wkts: List[str],
    elevation_data_matrix: Optional[npt.NDArray[np.float32]],
    utm_bounding_box: Optional[UTMBoundingBox],
    x_resolution: Optional[float],
    y_resolution: Optional[float],
    crs_epsg_code: Optional[int],
    left_top_x: Optional[float],
    left_top_y: Optional[float],
    max_los_distance: int,
    min_los_distance: int,
    max_el_scan_angle: float,
    los_confidence_threshold: float,
    use_ellipsoidal_los_model: bool,
    fresnel_radius: float,
    carrier_frequency: float,
) -> List[ValidLOS]:
    if (
        elevation_data_matrix is None
        or utm_bounding_box is None
        or x_resolution is None
        or y_resolution is None
        or crs_epsg_code is None
        or left_top_x is None
        or left_top_y is None
    ):
        surface_elevation = None
    else:
        sr = osr.SpatialReference()
        sr.ImportFromEPSG(crs_epsg_code)
        surface_elevation = Elevation(
            data_matrix=elevation_data_matrix,
            utm_bounding_box=utm_bounding_box,
            x_resolution=x_resolution,
            y_resolution=y_resolution,
            left_top_x=left_top_x,
            left_top_y=left_top_y,
            spatial_reference=sr,
            collection_time=None,
        )
    exclusion_zones = [wkt.loads(wkt_str) for wkt_str in exclusion_zones_wkts]
    if use_ellipsoidal_los_model:
        los_validator = EllipsoidalLOSValidator(
            surface_elevation,
            max_los_distance * (1 + DISTANCE_TOLERANCE_PERCENT),
            min_los_distance * (1 - DISTANCE_TOLERANCE_PERCENT),
            min(max_el_scan_angle + ELE_SCAN_ANGLE_TOLERANCE, 90),
            carrier_frequency,
            exclusion_zones,
            los_confidence_threshold,
        )
    else:
        los_validator = CylindricalLOSValidator(
            surface_elevation,
            max_los_distance * (1 + DISTANCE_TOLERANCE_PERCENT),
            min_los_distance * (1 - DISTANCE_TOLERANCE_PERCENT),
            min(max_el_scan_angle + ELE_SCAN_ANGLE_TOLERANCE, 90),
            fresnel_radius,
            exclusion_zones,
            los_confidence_threshold,
        )
    memoized_calculations = {}
    valid_los_links = []
    for site1_idx, site2_idx, is_bidirectional in candidate_links:
        site1 = los_sites[site1_idx]
        site2 = los_sites[site2_idx]
        key1 = (site1.utm_x, site1.utm_y, site1.altitude)
        key2 = (site2.utm_x, site2.utm_y, site2.altitude)
        if (key1, key2) in memoized_calculations:
            confidence = memoized_calculations[(key1, key2)]
        elif (key2, key1) in memoized_calculations:
            confidence = memoized_calculations[(key2, key1)]
        else:
            confidence = los_validator.compute_confidence(site1, site2)
            memoized_calculations[(key1, key2)] = confidence

        if confidence > 0:
            valid_los_links.append(ValidLOS(site1_idx, site2_idx, confidence))
            if is_bidirectional:
                valid_los_links.append(
                    ValidLOS(
                        site2_idx,
                        site1_idx,
                        confidence,
                    )
                )
    return valid_los_links


def pick_best_sites_per_building(
    sites: List[Site],
    rx_neighbors: List[List[int]],
    tx_neighbors: List[List[int]],
    dn_deployment: bool,
    confidence_dict: Dict[Tuple[int, int], float],
) -> List[int]:
    """
    Given sites and links, pick sites with most Line-of-Sight on each building.
    TO BE NOTED:
    This function may UPDATE the sites, rx_neighbors and tx_neighbors IN-PLACE.
    @param sites
    A list of Site to pick from. It contains all the detected sites and human
    input sites, but we only care about the detected ones here. All the detected sites
    are initially DNs because we want to get all the neighbors from/to the sites.
    @param rx_neighbors
    A adjacent list. If rx_site is in rx_neighbors[tx_site], it means there's a LOS from
    tx_site to rx_site.
    @param tx_neighbors
    A adjacent list. If tx_site is in tx_neighbors[rx_site], it means there's a LOS from
    tx_site to rx_site.
    @param dn_deployment
    If true, a DN will be deployed at each building, else not.
    @param confidence_dict
    A dict representing the confidence level of each link. This function may update confidence_dict
    when updating rx_neighbors.
    @return
    A list of int indicating the indices of picked sites.
    """
    picked_sites = []
    # Build a dict which map building to the sites on that building
    building_to_sites = defaultdict(list)
    for site_idx, site in enumerate(sites):
        if site.building_id is not None and site.building_id > -1:
            building_to_sites[site.building_id].append(site_idx)
        else:
            # User input sites must be picked
            picked_sites.append(site_idx)

    for sites_on_building in building_to_sites.values():
        sites_on_building.sort(
            reverse=True, key=lambda site: len(rx_neighbors[site])
        )
        if dn_deployment:
            picked_sites.append(sites_on_building[0])

        dn_site_idx = sites_on_building[0]
        dn_site = sites[dn_site_idx]
        cn_site_idx = len(sites)
        # Build a new Site that is the same as the input site except the site type and then
        # append it to sites, because we want a new Site with site_type == SiteType.CN
        cn_site = DetectedSite(
            site_type=SiteType.CN,
            location=GeoLocation(
                latitude=dn_site.latitude,
                longitude=dn_site.longitude,
                altitude=dn_site.altitude,
            ),
            building_id=none_throws(dn_site.building_id),
        )
        sites.append(cn_site)
        # CN has no rx neighbors
        rx_neighbors.append([])
        # Copy the tx neighbors
        tx_neighbors.append(deepcopy(tx_neighbors[dn_site_idx]))
        for tx_neighbor in tx_neighbors[cn_site_idx]:
            rx_neighbors[tx_neighbor].append(cn_site_idx)
            confidence_dict[(tx_neighbor, cn_site_idx)] = confidence_dict[
                (dn_site_idx, tx_neighbor)
            ]
        picked_sites.append(cn_site_idx)

    return picked_sites


def get_site_connectable_status(
    sites: List[Site],
    rx_neighbors: List[List[int]],
    picked_sites: List[int],
) -> Tuple[Set[int], Set[int], Set[int], Set[int]]:
    """
    Get the connectable status of each input site. The connectable status includes
    "connected", "unconnected", "potential_connectable", "potential_others":
      - "connected" means the site is picked as a candidate site and connected from
        either pop.
      - "unconnected" means the site is picked as a candidate site and unconnected
        from either pop.
      - "potential_connectable" means the site is not picked as candidate site and it
        can be directly (one-hop away) connected by a "connected" site.
      - "potential_other" means the site is not picked as candidate site and cannot
        be directly connected by a "connected" site.
    @param sites
    A list of Site object for each input sites.
    @param rx_neighbors
    A adjacent list. If rx_site is in rx_neighbors[tx_site], it means there's a LOS from
    tx_site to rx_site.
    @param picked_sites
    A list of int indicating the indices of all the picked sites from upstreaming steps.
    @return
    4 sets and each set contains indices of the sites with the corresponding status.
    """
    unconnected_sites = set(picked_sites)
    potential_other_sites = set(range(len(sites))) - unconnected_sites
    connected_sites: Set[int] = set()
    potential_connectable_sites: Set[int] = set()

    sites_to_explore = deque()
    for site_idx, site in enumerate(sites):
        # Add all the picked POP sites into connected_sites and add them to
        # sites_to_explore to start the BFS
        if site.site_type == SiteType.POP and site_idx in unconnected_sites:
            sites_to_explore.append(site_idx)
            unconnected_sites.remove(site_idx)
            connected_sites.add(site_idx)

    # Use BFS to traveese the topology
    while len(sites_to_explore) > 0:
        tx_site = sites_to_explore.popleft()
        for rx_site in rx_neighbors[tx_site]:
            if rx_site in unconnected_sites:
                sites_to_explore.append(rx_site)
                unconnected_sites.remove(rx_site)
                connected_sites.add(rx_site)
            elif rx_site in potential_other_sites:
                potential_other_sites.remove(rx_site)
                potential_connectable_sites.add(rx_site)

    return (
        connected_sites,
        unconnected_sites,
        potential_connectable_sites,
        potential_other_sites,
    )


def select_additional_dns(
    sites: List[Site],
    rx_neighbors: List[List[int]],
    tx_neighbors: List[List[int]],
    picked_sites: List[int],
) -> List[int]:
    """
    Given all the sites and links, select additional DNs to cover unconnected CNs.
    @param sites
    A list of Site for each input sites.
    @param rx_neighbors
    A adjacent list. If rx_site is in rx_neighbors[tx_site], it means there's a LOS from
    tx_site to rx_site.
    @param tx_neighbors
    A adjacent list. If tx_site is in tx_neighbors[rx_site], it means there's a LOS from
    tx_site to rx_site.
    @param picked_sites
    A list of int indicating the indices of all the picked sites from upstreaming steps.
    @return additional_dns
    A list of int indicating the indices of selected additional DNs.
    """
    cnt = 0
    (
        connected_sites,
        unconnected_sites,
        potential_connectable_sites,
        potential_other_sites,
    ) = get_site_connectable_status(sites, rx_neighbors, picked_sites)
    # Get unconnected CNs to cover
    unconnected_cns_set = set(
        filter(
            lambda site_idx: sites[site_idx].site_type == SiteType.CN,
            unconnected_sites,
        )
    )
    # A deque of (unconnected_cn, try_ times)
    unconnected_cns_dq = deque(
        map(
            lambda cn_idx: (cn_idx, 1),
            unconnected_cns_set,
        )
    )
    additional_dns = []
    while len(unconnected_cns_dq) > 0:
        current_unconnected_cn, try_times = unconnected_cns_dq.popleft()
        # If current_unconnected_cn was alread covered as an additional covered
        # CN by a DN neighbor of another CN, it would be removed from this set.
        if current_unconnected_cn not in unconnected_cns_set:
            continue
        # All neighbor DNs to current CN that are potential connectable
        potential_connectable_neighbor_dns = filter(
            lambda neighbor: neighbor in potential_connectable_sites,
            tx_neighbors[current_unconnected_cn],
        )

        # Select a best potential DN that can cover most number of unconnected CNs
        best_potential_dn = None
        most_unconnected_cn_neighbors = []
        for dn in potential_connectable_neighbor_dns:
            unconnected_cn_neighbors = list(
                filter(
                    lambda rx_neighbor: rx_neighbor in unconnected_cns_set,
                    rx_neighbors[dn],
                )
            )
            if len(unconnected_cn_neighbors) > len(
                most_unconnected_cn_neighbors
            ):
                best_potential_dn = dn
                most_unconnected_cn_neighbors = unconnected_cn_neighbors

        if best_potential_dn is not None:
            cnt += 1
            additional_dns.append(best_potential_dn)
            # Remove all the unconnected CNs that are covered by this DN
            unconnected_cns_set -= set(most_unconnected_cn_neighbors)
            # Set the status of this selected DN to connected
            connected_sites.add(best_potential_dn)
            potential_connectable_sites.remove(best_potential_dn)
            # Update the status of all the rx neighbors of the selected DN
            for rx_neighbor in rx_neighbors[best_potential_dn]:
                if rx_neighbor in potential_other_sites:
                    potential_other_sites.remove(rx_neighbor)
                    potential_connectable_sites.add(rx_neighbor)
                elif rx_neighbor in unconnected_sites:
                    unconnected_sites.remove(rx_neighbor)
                    connected_sites.add(rx_neighbor)
        elif try_times < 3:  # Try every site for three times at most
            unconnected_cns_dq.append((current_unconnected_cn, try_times + 1))

    logger.info(
        f"{cnt} additional DNs are added to get higher CN connectivity."
    )
    return additional_dns


def construct_topology_from_los_result(
    sites: List[Site],
    rx_neighbors: List[List[int]],
    picked_sites: List[int],
    confidence_dict: Dict[Tuple[int, int], float],
    device_list: List[DeviceData],
    device_pair_to_max_los_dist: Dict[Tuple[str, str], int],
    min_los_dist: int,
    max_el_scan_angle: float,
) -> Topology:
    """
    Construct a Topology instance for candidate graph from LOS result.
    @param sites
    A list of Site for each input sites.
    @param rx_neighbors
    A adjacent list. If rx_site is in rx_neighbors[tx_site], it means there's a LOS from
    tx_site to rx_site.
    @param picked_sites
    A list of int indicating the indices of all the picked sites.
    @param confidence_dict
    A dict representing the confidence level of each link.
    @param device_list
    A list of device data.
    @param device_pair_to_max_los_dist
    A dict mapping a pair of device SKUs to the max los distance.
    @param min_los_dist
    An int for the min los distance.
    @param max_el_scan_angle
    An float for the max elevation scan angle.
    @return
    A Topology representing the candidate graph.
    """
    picked_sites_set = set(picked_sites)

    topology, site_map = add_sites_to_topology(
        sites,
        picked_sites_set,
        device_list,
    )

    return add_links_to_topology(
        topology,
        rx_neighbors,
        picked_sites_set,
        site_map,
        confidence_dict,
        device_pair_to_max_los_dist,
        min_los_dist,
        max_el_scan_angle,
    )


def add_sites_to_topology(
    sites: List[Site],
    picked_sites_set: Set[int],
    device_list: List[DeviceData],
) -> Tuple[Topology, Dict[int, List[Site]]]:
    """
    Called by construct_topology_from_los_result, this function is to add sites to
    the candidate topology. Return a Topology, a dict site_idx_to_device mapping
    site index to device options, and a dict site_id_map mapping (site_idx, device_sku)
    to a site id.
    """
    topology = Topology()

    # Get the SKUs of candidate devices to be mounted on the detected sites for each device type
    devices_on_detected_sites: Dict[DeviceType, List[DeviceData]] = defaultdict(
        list
    )
    for device in device_list:
        devices_on_detected_sites[device.device_type].append(device)

    # Mapping from the index of site in "sites" to a list site objects in topology.
    # This is mainly for link detected sites.
    site_map: Dict[int, List[Site]] = defaultdict(list)

    for site_idx, site in enumerate(sites):
        if site_idx not in picked_sites_set:
            continue
        # If the site is inputed by users
        if not isinstance(site, DetectedSite):
            topology.add_site(site)
            site_map[site_idx] = [site]
        else:
            detected_site = site
            # If the site is detected at the building rooftop by the planner
            device_type = (
                DeviceType.CN
                if site.site_type == SiteType.CN
                else DeviceType.DN
            )

            for device in devices_on_detected_sites[device_type]:
                site_with_device = detected_site.to_site(device)
                if site_with_device.site_id not in topology.sites:
                    topology.add_site(site_with_device)
                    site_map[site_idx].append(site_with_device)

    return topology, site_map


def add_links_to_topology(
    topology: Topology,
    rx_neighbors: List[List[int]],
    picked_sites_set: Set[int],
    site_map: Dict[int, List[Site]],
    confidence_dict: Dict[Tuple[int, int], float],
    device_pair_to_max_los_dist: Dict[Tuple[str, str], int],
    min_los_dist: int,
    max_el_scan_angle: float,
) -> Topology:
    """
    Called by construct_topology_from_los_result, this function is to add links to
    the candidate topology.
    """
    for tx_site_idx, rx_site_indices in enumerate(rx_neighbors):
        if tx_site_idx not in picked_sites_set:
            continue
        for rx_site_idx in rx_site_indices:
            if rx_site_idx not in picked_sites_set:
                continue
            for tx_site in site_map[tx_site_idx]:
                for rx_site in site_map[rx_site_idx]:
                    link = Link(
                        tx_site=tx_site,
                        rx_site=rx_site,
                        tx_sector=None,
                        rx_sector=None,
                        status_type=StatusType.CANDIDATE,
                        is_wireless=True,
                        confidence_level=confidence_dict[
                            (tx_site_idx, rx_site_idx)
                        ],
                    )
                    if (
                        min_los_dist
                        <= link.distance
                        <= device_pair_to_max_los_dist[
                            (
                                tx_site.device.device_sku,
                                rx_site.device.device_sku,
                            )
                        ]
                        and link.el_dev <= max_el_scan_angle
                    ):
                        topology.add_link(link)
    return topology


def upsample_to_same_resolution(
    elevation1: Elevation, elevation2: Elevation
) -> None:
    """
    Upsample the two elevations to the same resolution.
    The minimum x/y resolution of the two input elevations is set to match.
    """
    x_res = min(elevation1.x_resolution, elevation2.x_resolution)
    y_res = min(elevation1.y_resolution, elevation2.y_resolution)
    elevation1.set_resolution(x_res, y_res)
    elevation2.set_resolution(x_res, y_res)
