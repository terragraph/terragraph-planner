# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
import shutil
import tempfile
from collections import defaultdict
from itertools import product
from typing import Dict, List, Optional, Tuple
from zipfile import ZipFile

from pyproj import Transformer
from pyre_extensions import none_throws
from scipy.spatial import KDTree

from terragraph_planner.common.configuration.configs import DeviceData
from terragraph_planner.common.configuration.enums import (
    LinkType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.constants import LAT_LON_EPSG
from terragraph_planner.common.data_io.constants import SITE_LINK_DIST_THRESHOLD
from terragraph_planner.common.data_io.csv_library import (
    load_input_sites_from_csv_file,
    load_topology_link_csv,
)
from terragraph_planner.common.data_io.input_sites import InputSites
from terragraph_planner.common.data_io.input_sites_loader import (
    InputSitesLoader,
)
from terragraph_planner.common.data_io.kml_library import (
    extract_raw_data_from_kml_file,
)
from terragraph_planner.common.exceptions import DataException, planner_assert
from terragraph_planner.common.geos import TransformerLib
from terragraph_planner.common.structs import RawLink
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.site import Site
from terragraph_planner.common.topology_models.topology import Topology


def _build_kd_tree(sites: InputSites) -> KDTree:
    """
    Build KDTree.
    """
    if len(sites) == 0:
        raise DataException("No sites in the kml input.")
    transformer = TransformerLib.get_tranformer(
        LAT_LON_EPSG, none_throws(sites.utm_epsg)
    )
    site_utm_locs: List[Tuple[float, float]] = [
        transformer.transform(site.longitude, site.latitude) for site in sites
    ]
    return KDTree(site_utm_locs)


def _find_nearest_sites_to_loc(
    latitude: float,
    longitude: float,
    kdtree: KDTree,
    sites: InputSites,
    transformer: Transformer,
    geohash_to_site_ids: Dict[str, List[str]],
    site_id_to_utms: Dict[str, Tuple[float, float]],
) -> List[Site]:
    """
    Find a list of nearest sites to a lat/lon location.
    """
    distance_threshold = SITE_LINK_DIST_THRESHOLD
    loc_utm_x, loc_utm_y = transformer.transform(longitude, latitude)
    _, nearest_site_idx = kdtree.query(
        [loc_utm_x, loc_utm_y], distance_upper_bound=distance_threshold
    )
    if nearest_site_idx == len(sites):
        raise DataException(
            "The closest site to link end-point with (lon, lat) = "
            f"({longitude}, {latitude}) is too far away. Please either "
            "remove this link or add a new placemark closer to its end-point."
        )
    nearest_site = sites[nearest_site_idx]

    nearest_sites = []
    distance_threshold_sq = distance_threshold * distance_threshold
    for site_id in geohash_to_site_ids[nearest_site.site_hash]:
        site_utm_x, site_utm_y = site_id_to_utms[site_id]
        if (site_utm_x - loc_utm_x) * (site_utm_x - loc_utm_x) + (
            site_utm_y - loc_utm_y
        ) * (site_utm_y - loc_utm_y) <= distance_threshold_sq:
            found_site = sites.get_site_by_id(site_id)
            nearest_sites.append(found_site)
    return nearest_sites


def _add_link_between_sites(
    topology: Topology,
    tx_site: Site,
    rx_site: Site,
    raw_link: Optional[RawLink],
) -> None:
    """
    Helper to add a Link between two Sites. If the inputs are csv files,
    raw_link would be None since corresponding data are not available.
    """
    existing_link = topology.get_link_by_site_ids(
        tx_site.site_id, rx_site.site_id
    )
    if existing_link is None:
        if tx_site.site_type != SiteType.CN:
            if raw_link is None:
                status_type = StatusType.CANDIDATE
                is_wireless = True
                confidence_level = None
            else:
                status_type = raw_link.status_type
                is_wireless = raw_link.link_type.is_wireless()
                confidence_level = raw_link.confidence_level
            topology.add_link(
                Link(
                    tx_site=tx_site,
                    rx_site=rx_site,
                    status_type=status_type,
                    is_wireless=is_wireless,
                    confidence_level=confidence_level,
                )
            )
    elif (
        raw_link is not None
        and existing_link.status_type != raw_link.status_type
    ):
        raise DataException(
            f"Links between coordinates ({tx_site.longitude}, {tx_site.latitude}) -"
            + f"({rx_site.longitude}, {rx_site.latitude}) have inconsistent statuses."
        )


def map_input_sites_links_from_kml(
    topology: Topology,
    input_sites: InputSites,
    raw_links: List[RawLink],
) -> None:
    """
    Map and construct topology links based on raw link data read from kml file and
    constructed topology sites. Tx/Rx site names are first used for the mapping,
    if not available, a KDTree will be used to locate nearest sites.
    """
    if len(raw_links) == 0:
        return
    geohash_to_site_ids: Dict[str, List[str]] = defaultdict(list)
    site_id_to_utms: Dict[str, Tuple[float, float]] = {}
    transformer = TransformerLib.get_tranformer(
        LAT_LON_EPSG, none_throws(input_sites.utm_epsg)
    )
    kdtree: KDTree = _build_kd_tree(input_sites)
    for site in input_sites:
        geohash_to_site_ids[site.site_hash].append(site.site_id)
        site_id_to_utms[site.site_id] = transformer.transform(
            site.longitude, site.latitude
        )

    for raw_link in raw_links:
        if raw_link.link_type == LinkType.ETHERNET:
            continue
        if (
            raw_link.tx_site_name is not None
            and raw_link.rx_site_name is not None
        ):
            tx_site = input_sites.get_site_by_name(raw_link.tx_site_name)
            rx_site = input_sites.get_site_by_name(raw_link.rx_site_name)
            if tx_site is None or rx_site is None:
                missing_names = []
                if tx_site is None:
                    missing_names.append(raw_link.tx_site_name)
                if rx_site is None:
                    missing_names.append(raw_link.rx_site_name)
                raise DataException(
                    f"Tx/rx site name {', '.join(missing_names)} of link in KML file"
                    + " does not match name of any site."
                )
            else:
                _add_link_between_sites(topology, tx_site, rx_site, raw_link)
                _add_link_between_sites(topology, rx_site, tx_site, raw_link)
        else:
            sites_near_loc1 = _find_nearest_sites_to_loc(
                raw_link.tx_latitude,
                raw_link.tx_longitude,
                kdtree,
                input_sites,
                transformer,
                geohash_to_site_ids,
                site_id_to_utms,
            )
            sites_near_loc2 = _find_nearest_sites_to_loc(
                raw_link.rx_latitude,
                raw_link.rx_longitude,
                kdtree,
                input_sites,
                transformer,
                geohash_to_site_ids,
                site_id_to_utms,
            )
            for site1, site2 in product(sites_near_loc1, sites_near_loc2):
                _add_link_between_sites(topology, site1, site2, raw_link)
                _add_link_between_sites(topology, site2, site1, raw_link)


def extract_topology_from_kml_file(
    kml_file_path: str, device_list: List[DeviceData]
) -> Topology:
    raw_sites, raw_links, demand_sites = extract_raw_data_from_kml_file(
        kml_file_path
    )
    input_sites = InputSitesLoader(device_list).get_input_sites(
        raw_sites, None, None
    )
    topology = Topology(sites=input_sites, demand_sites=demand_sites)
    map_input_sites_links_from_kml(topology, input_sites, raw_links)
    return topology


def extract_topology_from_csv_files(
    sites_csv_file_path: str,
    links_csv_file_path: str,
    device_list: List[DeviceData],
) -> Topology:
    """
    Extract a urban topology from csv files (sites + links)
    """
    raw_sites = load_input_sites_from_csv_file(sites_csv_file_path, False)
    input_sites = InputSitesLoader(device_list).get_input_sites(
        raw_sites, None, None
    )
    topology = Topology(sites=input_sites)
    site_name_pairs = load_topology_link_csv(links_csv_file_path)
    for tx_site_name, rx_site_name in site_name_pairs:
        tx_site = input_sites.get_site_by_name(tx_site_name)
        rx_site = input_sites.get_site_by_name(rx_site_name)
        if tx_site is None or rx_site is None:
            missing_names = []
            if tx_site is None:
                missing_names.append(tx_site_name)
            if rx_site is None:
                missing_names.append(rx_site_name)
            raise DataException(
                f"Site name {', '.join(missing_names)} from link csv file"
                + " does not show up in site csv file."
            )
        else:
            _add_link_between_sites(topology, tx_site, rx_site, None)
            _add_link_between_sites(topology, rx_site, tx_site, None)
    return topology


def extract_topology_from_file(
    topology_file_path: str, device_list: List[DeviceData]
) -> Topology:
    if topology_file_path.endswith(".kml") or topology_file_path.endswith(
        ".kmz"
    ):
        return extract_topology_from_kml_file(topology_file_path, device_list)
    else:
        zip_ref = ZipFile(topology_file_path, "r")
        planner_assert(
            "sites.csv" in zip_ref.namelist()
            and "links.csv" in zip_ref.namelist(),
            'A "sites.csv" file and a "links.csv" file must be contained at'
            "the top level of the zipped candidate file.",
            DataException,
        )
        tmp_dir = tempfile.mkdtemp()
        zip_ref.extractall(tmp_dir)
        try:
            topology = extract_topology_from_csv_files(
                os.path.join(tmp_dir, "sites.csv"),
                os.path.join(tmp_dir, "links.csv"),
                device_list,
            )
        except Exception as e:
            shutil.rmtree(tmp_dir)
            zip_ref.close()
            raise e
        shutil.rmtree(tmp_dir)
        zip_ref.close()
        return topology
