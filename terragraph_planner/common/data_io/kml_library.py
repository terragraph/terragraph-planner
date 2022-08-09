# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import json
import logging
import os
import zipfile
from typing import List, Optional, Tuple, Union

from osgeo import ogr
from shapely.geometry import Polygon

from terragraph_planner.common.configuration.enums import (
    LinkType,
    LocationType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.data_io.data_key import LinkKey, SiteKey
from terragraph_planner.common.data_io.patterns import DataWorkSpace
from terragraph_planner.common.exceptions import DataException, planner_assert
from terragraph_planner.common.geos import GeoLocation, lat_lon_to_utm_epsg
from terragraph_planner.common.structs import RawLink, RawSite
from terragraph_planner.common.topology_models.demand_site import DemandSite

logger: logging.Logger = logging.getLogger(__name__)


def _get_feature_field(
    feature: ogr.Feature, input: Union[SiteKey, LinkKey]
) -> str:
    """
    Get the value from the corresponding filed of an ogr feature.
    Only the first field in the feature would be returned if multiple matches.
    """
    try:
        feature_key_set = {k.casefold() for k in feature.keys()}
        field = feature.GetField(
            (feature_key_set & input.value.possible_input_names).pop()
        )
        return field if field is not None else ""
    except:
        return ""


def _get_site_altitude_height(
    altitude_mode: str, altitude: Optional[float]
) -> Tuple[Optional[float], Optional[float]]:
    """
    Get site altitude and height based on the altitude_mode from inputs.
    To be noted, the altitude and height will be further processed in
    InputSitesLoader for constructing Site location and location_type.
    """
    mode = altitude_mode or "clampedToGround"
    ret_altitude = None
    if mode == "absolute":
        ret_altitude = altitude
        height = None
    elif mode == "relativeToGround":
        # Google Earth actually treat "relativeToGround" as the height relative to
        # DTM to display the placemark, but our tool treat it relative to DSM, because
        # We want the height of site on the building rooftop is the height relative
        # to the building rooftop instead of the ground
        ret_altitude = None
        height = altitude
    else:
        # If mode is clampedToGround, clampedToSeaFloor or relativeToSeaFloor,
        # we set both altitude and height as None, and get the height from default pole
        # height if it's in build los step, and then get the altitude from DSM + height.
        # If it's not in build los step, altitude and height are not necessary attributes.
        ret_altitude = None
        height = None
    return ret_altitude, height


def extract_sites(
    raw_sites: List[RawSite],
    layer: ogr.Layer,
    site_type: SiteType,
    status_type: StatusType,
) -> None:
    """
    Extract sites data from KML file.
    """
    for feature in layer:
        device_sku = _get_feature_field(feature, SiteKey.DEVICE_SKU)
        name = _get_feature_field(feature, SiteKey.NAME)
        geometry = feature.GetGeometryRef()
        altitude, height = _get_site_altitude_height(
            _get_feature_field(feature, SiteKey.ALTITUDE_MODE), geometry.GetZ()
        )
        location_type_str = _get_feature_field(feature, SiteKey.LOCATION_TYPE)
        location_type = (
            LocationType[location_type_str.upper()]
            if location_type_str.upper() in LocationType.__members__
            else LocationType.STREET_LEVEL
        )
        building_id = _get_feature_field(feature, SiteKey.BUILDING_ID)
        number_of_subscribers = _get_feature_field(
            feature, SiteKey.NUMBER_OF_SUBSCRIBERS
        )
        site = RawSite(
            site_type=site_type,
            status_type=status_type,
            device_sku=device_sku if len(device_sku) > 0 else None,
            name=name if len(name) > 0 else None,
            latitude=geometry.GetY(),
            longitude=geometry.GetX(),
            altitude=altitude,
            height=height,
            location_type=location_type,
            building_id=int(building_id)
            if location_type is LocationType.ROOFTOP and building_id.isdecimal()
            else None,
            number_of_subscribers=int(number_of_subscribers)
            if number_of_subscribers.isdecimal()
            else None,
        )
        raw_sites.append(site)


def extract_links(
    raw_links: List[RawLink],
    layer: ogr.Layer,
    link_type: LinkType,
    status_type: StatusType,
) -> None:
    """
    Extract input links data from KML file.
    """
    for feature in layer:
        geometry = feature.GetGeometryRef()
        link_type_str = _get_feature_field(feature, LinkKey.LINK_TYPE)
        link_type = (
            LinkType[link_type_str.upper()]
            if link_type_str.upper() in LinkType.__members__
            else LinkType.WIRELESS_BACKHAUL
        )
        tx_site_name = _get_feature_field(feature, LinkKey.TX_SITE_NAME)
        rx_site_name = _get_feature_field(feature, LinkKey.RX_SITE_NAME)
        confidence_level = _get_feature_field(feature, LinkKey.CONFIDENCE_LEVEL)
        link = RawLink(
            status_type=status_type,
            link_type=link_type,
            confidence_level=float(confidence_level)
            if confidence_level.isdecimal()
            else None,
            tx_site_name=tx_site_name,
            tx_latitude=geometry.GetPoint(0)[1],
            tx_longitude=geometry.GetPoint(0)[0],
            rx_site_name=rx_site_name,
            rx_latitude=geometry.GetPoint(1)[1],
            rx_longitude=geometry.GetPoint(1)[0],
        )
        raw_links.append(link)


def extract_demand_sites(
    demand_sites: List[DemandSite],
    layer: ogr.Layer,
) -> None:
    """
    Extract demand site data from KML file.
    """
    for feature in layer:
        geometry = feature.GetGeometryRef()
        demand_sites.append(
            DemandSite(
                location=GeoLocation(
                    latitude=geometry.GetY(),
                    longitude=geometry.GetX(),
                    altitude=None,
                )
            )
        )


def _get_kml_file_path_from_kmz(kmz_file_path: str, unzipped_dir: str) -> str:
    """
    Get the KML file path from a KMZ file path.
    """
    with zipfile.ZipFile(kmz_file_path, "r") as zip_ref:
        zip_ref.extractall(unzipped_dir)
        names = [n for n in zip_ref.namelist() if n.casefold().endswith(".kml")]
        if len(names) == 0:
            raise DataException("No KML file in the input KMZ file.")
        return os.path.join(unzipped_dir, names[0])


def extract_raw_data_from_kml_file(
    kml_file_path: str,
) -> Tuple[List[RawSite], List[RawLink], List[DemandSite]]:
    """
    Extract sites, links, and demand_sites from a KML/KMZ file
    """
    try:
        extension = os.path.splitext(kml_file_path)[-1].casefold()
        if extension == ".kmz":
            ds = DataWorkSpace()
            kml_file_path = _get_kml_file_path_from_kmz(
                kml_file_path, ds.get_a_temp_dir()
            )
        elif extension != ".kml":
            raise DataException("Please provide a KML or KMZ file for input.")
        driver = ogr.GetDriverByName("LIBKML")
        kml_ds = driver.Open(kml_file_path)
        status_type = StatusType.CANDIDATE
        raw_sites: List[RawSite] = []
        raw_links: List[RawLink] = []
        demand_sites: List[DemandSite] = []
        for layer in kml_ds:
            layer_name = layer.GetName().casefold()
            if any(x.casefold() in layer_name for x in StatusType.names()):
                status_type = StatusType[
                    next(
                        x
                        for x in StatusType.names()
                        if x.casefold() in layer_name
                    )
                ]
            elif any(x.casefold() in layer_name for x in SiteType.names()):
                site_type = SiteType[
                    next(
                        x
                        for x in SiteType.names()
                        if x.casefold() in layer_name
                    )
                ]
                extract_sites(raw_sites, layer, site_type, status_type)
            elif any(x.casefold() in layer_name for x in LinkType.names()):
                link_type = LinkType[
                    next(
                        x
                        for x in LinkType.names()
                        if x.casefold() in layer_name
                    )
                ]
                extract_links(raw_links, layer, link_type, status_type)
            elif "demand site" in layer_name:
                extract_demand_sites(demand_sites, layer)
        return raw_sites, raw_links, demand_sites
    except Exception:
        raise DataException("Error encountered when reading KML")


def extract_polygons(
    kml_file_path: str,
) -> List[Polygon]:
    """
    Extract polygons for boundary or exclusion zones. Boundary polygon should contain
    exactly one polygon; while exclusion zones may contain both polygans and point lists.
    """
    try:
        extension = os.path.splitext(kml_file_path)[-1].casefold()
        if extension == ".kmz":
            ds = DataWorkSpace()
            kml_file_path = _get_kml_file_path_from_kmz(
                kml_file_path, ds.get_a_temp_dir()
            )
        elif extension != ".kml":
            raise DataException("Please provide a KML or KMZ file for input.")
        driver = ogr.GetDriverByName("LIBKML")
        kml_ds = driver.Open((kml_file_path))
        polygon_list: List[Polygon] = []
        for layer in kml_ds:
            for feature in layer:
                geo = feature.GetGeometryRef()
                for i in range(geo.GetGeometryCount()):
                    coords = json.loads(geo.GetGeometryRef(i).ExportToJson())[
                        "coordinates"
                    ]
                    # The coords of a multipolygon is like [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]
                    # which is in the format of List[List[List[float]]]
                    # We only use the first polygon in the multipolygon
                    if (
                        len(coords) > 0
                        and len(coords[0]) > 0
                        and type(coords[0][0]) is list
                    ):
                        coords = coords[0]
                        logger.warning(
                            "A MultiPolygon is found is the KML. "
                            "Only the first polygon in the MultiPolygon is used."
                        )
                    # A Polygon should contain 3 or more points.
                    # coords have an extra coord to close the loop
                    # e.g. [(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]
                    if len(coords) > 3:
                        polygon_list.append(
                            Polygon([coord[:2] for coord in coords])
                        )
        return polygon_list
    except Exception:
        raise DataException(
            "Error encountered when extract polygans from KML/KMZ file."
        )


def extract_boundary_polygon(kml_file_path: str) -> Tuple[Polygon, int]:
    """
    Extract boundary polygon from kml/kmz input file.
    """
    polygons = extract_polygons(kml_file_path)
    planner_assert(
        len(polygons) == 1,
        "The boundary polygon KML/KMZ file should contain exactly one Polygon",
        DataException,
    )
    return polygons[0], lat_lon_to_utm_epsg(
        polygons[0].centroid.y, polygons[0].centroid.x
    )
