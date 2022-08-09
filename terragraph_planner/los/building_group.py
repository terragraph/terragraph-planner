# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
from typing import List, Optional

import numpy as np
from osgeo import osr
from PIL import Image, ImageDraw
from pyre_extensions import none_throws
from shapely import ops, prepared
from shapely.geometry import MultiPolygon, Polygon

from terragraph_planner.common.configuration.enums import SiteType
from terragraph_planner.common.constants import LAT_LON_EPSG
from terragraph_planner.common.data_io.patterns import GISData
from terragraph_planner.common.geos import GeoLocation, TransformerLib
from terragraph_planner.common.structs import Point3D
from terragraph_planner.common.topology_models.site import DetectedSite
from terragraph_planner.los.building import Building
from terragraph_planner.los.constants import MINIMUM_BUILDING_AREA
from terragraph_planner.los.elevation import Elevation

logger: logging.Logger = logging.getLogger(__name__)


class BuildingGroup(GISData):
    """
    Used to store and handle building data.
    """

    def __init__(
        self,
        building_list: List[Building],
        spatial_reference: osr.SpatialReference,
    ) -> None:
        self.building_list = building_list
        super().__init__(spatial_reference)

    @property
    def building_count(self) -> int:
        return len(self.building_list)

    @property
    def building_polygons(self) -> List[Polygon]:
        return [building.polygon for building in self.building_list]

    def add_building(
        self,
        building: Optional[Building] = None,
        polygon: Optional[Polygon] = None,
    ) -> None:
        """
        Append the building list if the building polygon is valid and not empty
        - If building is given, append the building lists with the input building
        - Else use polygon to construct a Building instance and then append
        """
        if building is not None:
            if building.polygon.is_valid and not building.polygon.is_empty:
                self.building_list.append(building)
        elif polygon is not None and polygon.is_valid and not polygon.is_empty:
            self.building_list.append(Building(polygon))

    def preprocess(
        self,
        ll_boundary_polygon: Polygon,
        utm_epsg_code: int,
        selection_polygons: Optional[List[Polygon]],
    ) -> None:
        """
        - Convert crs to Lat/Lon if it wasn't
        - Use boundary polygon to filter out, cut, or transform building polygons
        - Use selection polygons to filter out building polygons
        - Filter out invalid or empty polygons
        - Convert Lat/Lon to UTM
        """
        # Convert crs to Lat/Lon if it wasn't
        if self.crs_epsg_code != LAT_LON_EPSG:
            transformer = TransformerLib.get_tranformer(
                self.crs_epsg_code, LAT_LON_EPSG
            )
            for building in self.building_list:
                building.polygon = ops.transform(
                    transformer.transform, building.polygon
                )
        # Use boundary polygon to filter out, cut, or transform building polygons
        prep_boundary = prepared.prep(ll_boundary_polygon)
        building_list = self.building_list
        self.building_list = []
        for building in building_list:
            geom = building.polygon
            if geom is not None and geom.is_valid:
                if prep_boundary.contains(geom):
                    self.add_building(building=building)
                elif prep_boundary.intersects(geom):
                    cut_geom = geom.intersection(ll_boundary_polygon)
                    if isinstance(cut_geom, Polygon):
                        self.add_building(polygon=cut_geom)
                    elif isinstance(cut_geom, MultiPolygon):
                        for subgeom in cut_geom:
                            self.add_building(polygon=subgeom)
        # Use selection polygons to filter out building polygons
        if selection_polygons is not None and len(selection_polygons) > 0:
            building_list = self.building_list
            self.building_list = []
            unioned_geom = ops.unary_union(selection_polygons)
            unioned_geom = prepared.prep(unioned_geom)
            for building in building_list:
                if unioned_geom.contains(building.polygon):
                    self.add_building(building)
        # Convert Lat/Lon to UTM
        transformer = TransformerLib.get_tranformer(LAT_LON_EPSG, utm_epsg_code)
        building_list = self.building_list
        self.building_list = []
        for building in building_list:
            polygon = ops.transform(transformer.transform, building.polygon)
            if polygon.area > MINIMUM_BUILDING_AREA:
                self.add_building(polygon=polygon)
        self.spatial_reference = osr.SpatialReference()
        self.spatial_reference.ImportFromEPSG(utm_epsg_code)
        logger.info(
            f"{self.building_count} buildings remained after preprocessing."
        )

    def detect_site_candidates(
        self,
        surface_elevation: Optional[Elevation],
        site_height_above_rooftop: float,
        max_corner_angle: Optional[float],
        detect_corners: bool,
        detect_center: bool,
        detect_highest: bool,
    ) -> List[DetectedSite]:
        """
        Detect site candidates on buildings.

        @param surface_elevation
        Surface elevation data used to get the altitude of the detected sites. If None is passed in,
        the altitude of all the sites will equal to 0.

        @param site_height_above_rooftop
        The site height (in metres) for all detected sites on the rooftop (center/corners/highest).

        @param max_corner_angle
        If given, only vertices whose angle is smaller than that will be detected as corners,
        else all vertices will be detected.

        @param detect_corners, detect_center, detect_highest
        Flags indicting which type of locations will be detected.

        @return
        A list of Site representing the information of the detected sites.
        """

        def _convert_point_3d_to_site(
            location: Point3D, building_id: int
        ) -> DetectedSite:
            lon, lat = transformer.transform(location.x, location.y)
            return DetectedSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    latitude=lat,
                    longitude=lon,
                    altitude=location.z + site_height_above_rooftop
                    if surface_elevation is not None
                    else None,
                ),
                building_id=building_id,
            )

        site_candidates = []
        transformer = TransformerLib.get_tranformer(
            self.crs_epsg_code, LAT_LON_EPSG
        )

        for building_id, building in enumerate(self.building_list):
            if detect_center:
                site_candidates.append(
                    _convert_point_3d_to_site(
                        none_throws(building.detect_center(surface_elevation)),
                        building_id,
                    )
                )
            if detect_highest and surface_elevation is not None:
                site_candidates.append(
                    _convert_point_3d_to_site(
                        none_throws(building.detect_highest(surface_elevation)),
                        building_id,
                    )
                )
            if detect_corners:
                corners = building.detect_corners(
                    surface_elevation, max_corner_angle
                )
                if len(corners) <= 3:
                    for corner in corners:
                        site_candidates.append(
                            _convert_point_3d_to_site(corner, building_id)
                        )
                else:
                    spacing = len(corners) // 3
                    for i in range(3):
                        site_candidates.append(
                            _convert_point_3d_to_site(
                                corners[i * spacing], building_id
                            )
                        )

        return site_candidates

    def to_dhm(
        self, dtm: Elevation, default_building_height: float
    ) -> Elevation:
        """
        Convert buildings to a dhm and output it as Elevation.
        Currently only support uniform building height. We'll try to support various
        height and also include other height data like foliage in future.

        @param dtm
        The Elevation contains terrain elevation data.

        @param default_building_height
        The height of each building in meters.

        @return Elevation
        The Elevations contains height data.
        """
        dhm_image = Image.new("F", (dtm.x_size, dtm.y_size), 0)
        imgd = ImageDraw.Draw(dhm_image)
        for building in self.building_list:
            coords_utm = building.polygon.exterior.coords
            coords_pixel = [
                (
                    (utm_x - dtm.left_top_x) / dtm.x_resolution,
                    (dtm.left_top_y - utm_y) / dtm.y_resolution,
                )
                for utm_x, utm_y in coords_utm
            ]
            imgd.polygon(
                xy=coords_pixel,
                fill=int(default_building_height * 1000),
                outline=int(default_building_height * 1000),
            )

        dhm_matrix = np.asarray(dhm_image) / 1000
        return Elevation(
            data_matrix=dhm_matrix,
            utm_bounding_box=dtm.utm_bounding_box,
            x_resolution=dtm.x_resolution,
            y_resolution=dtm.y_resolution,
            left_top_x=dtm.left_top_x,
            left_top_y=dtm.left_top_y,
            spatial_reference=dtm.spatial_reference,
            collection_time=None,
        )
