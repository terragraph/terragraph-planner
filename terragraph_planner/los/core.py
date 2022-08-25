# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import math
from functools import partial
from itertools import chain
from multiprocessing import Pool, cpu_count
from time import time
from typing import Dict, List, Optional, Tuple

from pyre_extensions import assert_is_instance, none_throws
from shapely import ops
from shapely.geometry import Polygon

from terragraph_planner.common.configuration.configs import (
    GISDataParams,
    LOSParams,
)
from terragraph_planner.common.configuration.constants import (
    DATA,
    LINE_OF_SIGHT,
)
from terragraph_planner.common.configuration.enums import OutputFile
from terragraph_planner.common.configuration.utils import (
    struct_objects_from_file,
)
from terragraph_planner.common.constants import LAT_LON_EPSG
from terragraph_planner.common.data_io.building_group_loader import (
    BuildingGroupLoader,
)
from terragraph_planner.common.data_io.elevation_loader import ElevationLoader
from terragraph_planner.common.data_io.kml_library import (
    extract_boundary_polygon,
)
from terragraph_planner.common.data_io.topology_serializer import (
    dump_topology_to_kml,
)
from terragraph_planner.common.exceptions import DataException, planner_assert
from terragraph_planner.common.geos import TransformerLib
from terragraph_planner.common.structs import (
    CandidateLOS,
    UTMBoundingBox,
    ValidLOS,
)
from terragraph_planner.common.topology_models.site import LOSSite, Site
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.common.utils import set_system_control_with_config_file
from terragraph_planner.los.building_group import BuildingGroup
from terragraph_planner.los.constants import BATCH_SIZE
from terragraph_planner.los.elevation import Elevation
from terragraph_planner.los.helper import (
    compute_los_batch,
    construct_topology_from_los_result,
    get_los_topology,
    get_max_los_dist_for_device_pairs,
    pick_best_sites_per_building,
    pre_los_check,
    select_additional_dns,
    upsample_to_same_resolution,
)

logger: logging.Logger = logging.getLogger(__name__)


def generate_candidate_topology_with_config_file(
    config_file_path: str,
) -> Topology:
    """
    Given the config file, run the plan to generate candidate graph.

    @param config_file_path
    The file path of the config yaml or json file. If a yaml file is used,
    please refer to the template.yaml under terragraph/data directory.
    """
    set_system_control_with_config_file(config_file_path)
    gis_data_params = assert_is_instance(
        struct_objects_from_file(DATA, config_file_path), GISDataParams
    )
    los_params = assert_is_instance(
        struct_objects_from_file(LINE_OF_SIGHT, config_file_path), LOSParams
    )
    topology = generate_candidate_topology(los_params, gis_data_params)
    return topology


def generate_candidate_topology(
    los_params: LOSParams, gis_data_params: GISDataParams
) -> Topology:
    """
    Genrate a candidate graph based on the configuration and the input GIS data.

    @param los_params
    The config parameters, including LOS distance range, flags in site detection, etc.

    @param gis_data_params
    GIS data, including DEM and building outlines.

    @return
    A candidate network in Topology type.
    """
    pre_los_check(los_params, gis_data_params)
    (
        ll_boundary,
        surface_elevation,
        terrain_elevation,
        building_group,
    ) = load_gis_data(gis_data_params)

    if building_group is not None:
        detected_sites = building_group.detect_site_candidates(
            surface_elevation,
            los_params.mounting_height_above_rooftop,
            los_params.site_detection.max_corner_angle,
            los_params.site_detection.detect_corners,
            los_params.site_detection.detect_centers,
            los_params.site_detection.detect_highest,
        )
    else:
        detected_sites = []

    sites, candidate_links, exclusion_zones, base_topology = get_los_topology(
        gis_data_params,
        los_params,
        ll_boundary,
        detected_sites,
        surface_elevation,
        terrain_elevation,
    )
    device_pair_to_max_los_dist = get_max_los_dist_for_device_pairs(
        los_params.device_list,
        los_params.maximum_eirp,
        los_params.minimum_mcs_of_backhaul_links,
        los_params.minimum_mcs_of_access_links,
        los_params.maximum_los_distance,
    )
    max_los_distance = max(device_pair_to_max_los_dist.values())

    valid_links = compute_los(
        sites,
        candidate_links,
        surface_elevation,
        exclusion_zones,
        max_los_distance,
        los_params.minimum_los_distance,
        los_params.maximum_elevation_scan_angle,
        los_params.los_confidence_threshold,
        los_params.use_ellipsoidal_los_model,
        los_params.fresnel_radius,
        los_params.carrier_frequency,
        los_params.num_processors,
    )

    topology = build_candidate_topology(
        los_params,
        base_topology,
        sites,
        valid_links,
        device_pair_to_max_los_dist,
        gis_data_params.building_outline_file_path is not None,
    )
    dump_topology_to_kml(topology, OutputFile.CANDIDATE_TOPOLOGY)
    return topology


def load_gis_data(
    gis_data_params: GISDataParams,
) -> Tuple[
    Polygon, Optional[Elevation], Optional[Elevation], Optional[BuildingGroup]
]:
    """
    Load, validate and process the GIS data used to compute LOS

    Return a boundary polygon in lat/lon, surface elevation, terrain elevation and building outline data.
    """
    logger.info("Start loading and preprocessing GIS data......")
    ll_boundary_polygon, utm_epsg_code = extract_boundary_polygon(
        gis_data_params.boundary_polygon_file_path
    )
    planner_assert(
        ll_boundary_polygon.is_valid,
        "The boundary polygon is invalid",
        DataException,
    )
    logger.info(f"UTM epsp code of the AOI: {utm_epsg_code}")
    transformer = TransformerLib.get_tranformer(LAT_LON_EPSG, utm_epsg_code)
    utm_boundary_polygon = ops.transform(
        transformer.transform, ll_boundary_polygon
    )
    bounds = utm_boundary_polygon.bounds
    utm_bounding_box = UTMBoundingBox(
        min_utm_x=math.floor(bounds[0]),
        min_utm_y=math.floor(bounds[1]),
        max_utm_x=math.ceil(bounds[2]),
        max_utm_y=math.ceil(bounds[3]),
    )

    building_group_loader = BuildingGroupLoader()
    logger.info(f"UTM bounding box of the AOI: {utm_bounding_box}")

    if gis_data_params.building_outline_file_path is not None:
        building_group = building_group_loader.read(
            none_throws(gis_data_params.building_outline_file_path)
        )
        building_group.preprocess(ll_boundary_polygon, utm_epsg_code, [])
    else:
        building_group = None
    elevation_loader = ElevationLoader()
    dsm = (
        elevation_loader.read(
            gis_data_params.dsm_file_paths, utm_epsg_code, utm_bounding_box
        )
        if len(gis_data_params.dsm_file_paths) > 0
        else None
    )
    dtm = (
        elevation_loader.read(
            [gis_data_params.dtm_file_path], utm_epsg_code, utm_bounding_box
        )
        if gis_data_params.dtm_file_path is not None
        else None
    )
    dhm = (
        elevation_loader.read(
            [gis_data_params.dhm_file_path], utm_epsg_code, utm_bounding_box
        )
        if gis_data_params.dhm_file_path is not None
        else None
    )
    if dsm is None and dtm is not None and dhm is not None:
        upsample_to_same_resolution(dtm, dhm)
        dsm = dtm + dhm
    elif dsm is not None and dtm is None and dhm is not None:
        dtm = dsm - dhm

    errors = building_group_loader.errors + elevation_loader.errors
    if len(errors) > 0:
        error_msg = ""
        for error in errors:
            error_msg += error.message + "\n"
        raise DataException(error_msg)

    logger.info("Completed loading and preprocessing GIS data")
    return ll_boundary_polygon, dsm, dtm, building_group


def compute_los(
    sites: List[Site],
    candidate_links: List[CandidateLOS],
    surface_elevation: Optional[Elevation],
    exclusion_zones: List[Polygon],
    max_los_distance: int,
    min_los_distance: int,
    max_el_scan_angle: float,
    los_confidence_threshold: float,
    use_ellipsoidal_los_model: bool,
    fresnel_radius: float,
    carrier_frequency: float,
    num_processors: Optional[int],
) -> List[ValidLOS]:
    """
    This function computes LOS between two candidate sites with cylinderical or ellipsoidal model,

    @params sites
    All the candidate sites information, including detected sites and existing/input sites.

    @params candidate_links
    A list of tuples in the format of (site1_idx, site2_idx, is_bidirectional).

    @params surface_elevation
    The surface elevation in the area of interest.

    @params exlcusion_zones
    A list of Polygons where a LOS is prohibited.

    @params max_los_distance, min_los_distance, max_el_scan_angle, los_confidence_threshold,
    fresnel_radius, carrier_frequency
    A set of params to construct the LOS validator to validate the LOS

    @params use_ellipsoidal_los_model
    Use EllipsoidalLOSValidator instead of CylindricalLOSValidator.

    @return
    A list of tuples in format of (tx_site_idx, rx_site_idx, confidence).
    """
    start_time = time()
    logger.info("Start computing line-of-sight......")
    if num_processors is None:
        num_processors = cpu_count()
    elif num_processors > cpu_count():
        logger.warning(
            f"Num processors is set as {num_processors} in config,"
            f" but there are only {cpu_count()} cpus. Using {cpu_count()}"
            "for multiprocessing"
        )
        num_processors = cpu_count()

    los_sites = [
        LOSSite(
            utm_x=s.utm_x,
            utm_y=s.utm_y,
            altitude=s.altitude,
            location_type=s.location_type.value,
            building_id=s.building_id,
        )
        for s in sites
    ]
    exclusion_zones_wkts = [zone.wkt for zone in exclusion_zones]

    with Pool(num_processors) as p:
        result = p.map(
            partial(
                compute_los_batch,
                los_sites=los_sites,
                exclusion_zones_wkts=exclusion_zones_wkts,
                elevation_data_matrix=surface_elevation.data_matrix
                if surface_elevation is not None
                else None,
                utm_bounding_box=surface_elevation.utm_bounding_box
                if surface_elevation is not None
                else None,
                x_resolution=surface_elevation.x_resolution
                if surface_elevation is not None
                else None,
                y_resolution=surface_elevation.y_resolution
                if surface_elevation is not None
                else None,
                crs_epsg_code=surface_elevation.crs_epsg_code
                if surface_elevation is not None
                else None,
                left_top_x=surface_elevation.left_top_x
                if surface_elevation is not None
                else None,
                left_top_y=surface_elevation.left_top_y
                if surface_elevation is not None
                else None,
                max_los_distance=max_los_distance,
                min_los_distance=min_los_distance,
                max_el_scan_angle=max_el_scan_angle,
                los_confidence_threshold=los_confidence_threshold,
                use_ellipsoidal_los_model=use_ellipsoidal_los_model,
                fresnel_radius=fresnel_radius,
                carrier_frequency=carrier_frequency,
            ),
            [
                candidate_links[
                    i
                    * BATCH_SIZE : min(
                        (i + 1) * BATCH_SIZE, len(candidate_links)
                    )
                ]
                for i in range(math.ceil(len(candidate_links) / BATCH_SIZE))
            ],
        )

    valid_los_links = list(chain(*result))
    logger.info("Completed computing line-of-sight.")
    end_time = time()
    logger.info(
        f"Time to compute line-of-sight {end_time - start_time:0.2f} seconds."
    )
    return valid_los_links


def build_candidate_topology(
    los_params: LOSParams,
    topology: Topology,
    sites: List[Site],
    links: List[ValidLOS],
    device_pair_to_max_los_dist: Dict[Tuple[str, str], int],
    site_detection_enabled: bool,
) -> Topology:
    """
    Build a Topology instance based on all the sites (detected + existing) and
    LOS links (computed + existing).

    @param los_params
    Input config for building candidate graph.

    @param topology
    The base topology to add sites and links to.

    @param sites
    All the candidate sites information, including detected sites and existing/input sites.

    @param link
    A list of tuples in the format of (tx_site_idx, rx_site_idx, confidence).

    @param site_detection_enabled
    Whether or not the site detection feature is enabled.

    @return
    A candidate network in Topology type.
    """
    logger.info("Start constructing a topology representing the mesh network.")
    # If rx_site is in rx_neighbors[tx_site], it means there's a LOS from
    # tx_site to rx_site. tx_neighbors vice verse.
    rx_neighbors = [[] for _ in range(len(sites))]
    tx_neighbors = [[] for _ in range(len(sites))]
    confidence_dict = {}
    for tx_site, rx_site, confidence in links:
        rx_neighbors[tx_site].append(rx_site)
        tx_neighbors[rx_site].append(tx_site)
        confidence_dict[(tx_site, rx_site)] = confidence

    if site_detection_enabled:
        picked_sites = pick_best_sites_per_building(
            sites,
            rx_neighbors,
            tx_neighbors,
            los_params.site_detection.dn_deployment,
            confidence_dict,
        )
        additional_dns = select_additional_dns(
            sites, rx_neighbors, tx_neighbors, picked_sites
        )
    else:
        # If site detection is disabled, all sites are picked, and there
        # are no additional DNs.
        picked_sites = list(range(len(sites)))
        additional_dns = []

    construct_topology_from_los_result(
        topology,
        sites,
        rx_neighbors,
        picked_sites + additional_dns,
        confidence_dict,
        los_params.device_list,
        device_pair_to_max_los_dist,
        los_params.minimum_los_distance,
        los_params.maximum_elevation_scan_angle,
    )
    logger.info("Completed constructing the topology.")
    return topology
