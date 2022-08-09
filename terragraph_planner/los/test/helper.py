# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import List, Optional, Tuple

import numpy as np
import numpy.typing as npt
from osgeo.osr import SpatialReference

from terragraph_planner.common.configuration.configs import DeviceData
from terragraph_planner.common.configuration.enums import LocationType, SiteType
from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.topology_models.site import (
    DetectedSite,
    LOSSite,
    Site,
)
from terragraph_planner.common.topology_models.test.helper import SampleSite
from terragraph_planner.los.building import Building
from terragraph_planner.los.building_group import BuildingGroup
from terragraph_planner.los.elevation import Elevation


class MockElevation(Elevation):
    def __init__(
        self,
        crs_epsg_code: int = 32610,
        uniform_value: float = 0.0,
        x_resolution: float = 1.0,
        y_resolution: float = 1.0,
        spatial_reference: Optional[SpatialReference] = None,
        collection_time: Optional[str] = None,
    ) -> None:
        self._crs_epsg_code = crs_epsg_code
        self.elevation_search_radius = 50
        self.uniform_value = uniform_value
        self.x_resolution = x_resolution
        self.y_resolution = y_resolution
        self.spatial_reference: SpatialReference = (
            spatial_reference
            if spatial_reference is not None
            else SpatialReference()
        )
        self.collection_time = collection_time

    def get_data_as_list(self) -> List[Tuple[float, float, float]]:
        return []

    @property
    def crs_epsg_code(self) -> int:
        if self.spatial_reference is None:
            return self._crs_epsg_code
        return super().crs_epsg_code

    def get_value(self, x: float, y: float) -> float:
        return self.uniform_value

    def get_value_matrix_within_bound(
        self,
        min_utm_x: float,
        min_utm_y: float,
        max_utm_x: float,
        max_utm_y: float,
    ) -> npt.NDArray[np.float32]:
        return np.array([[self.uniform_value]])


class MockBuildingGroup(BuildingGroup):
    def __init__(
        self,
        building_list: Optional[List[Building]] = None,
        crs_epsg_code: Optional[int] = None,
        spatial_reference: Optional[SpatialReference] = None,
    ) -> None:
        if spatial_reference is None:
            spatial_reference = SpatialReference()
        if crs_epsg_code is not None:
            spatial_reference.ImportFromEPSG(crs_epsg_code)
        super().__init__(
            building_list if building_list is not None else [],
            spatial_reference,
        )


def build_los_site_for_los_test(
    utm_x: float = 0.0,
    utm_y: float = 0.0,
    altitude: float = 0.0,
    location_type: LocationType = LocationType.UNKNOWN,
    building_id: Optional[int] = None,
) -> LOSSite:
    return LOSSite(utm_x, utm_y, altitude, location_type.value, building_id)


def build_site_for_los_test(
    utm_x: float = 0.0,
    utm_y: float = 0.0,
    altitude: float = 0.0,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    device: Optional[DeviceData] = None,
    location_type: LocationType = LocationType.UNKNOWN,
    building_id: Optional[int] = None,
    site_type: SiteType = SiteType.DN,
    name: str = "",
) -> Site:
    if building_id is not None:
        location_type = LocationType.ROOFTOP
    if latitude is not None and longitude is not None:
        location = GeoLocation(
            latitude=latitude, longitude=longitude, altitude=altitude
        )
    else:
        location = GeoLocation(
            utm_x=utm_x, utm_y=utm_y, utm_epsg=32601, altitude=altitude
        )
    return SampleSite(
        site_type=site_type,
        location=location,
        device=device,
        location_type=location_type,
        building_id=building_id,
        name=name,
    )


def build_detected_site_for_los_test(
    utm_x: float = 0.0,
    utm_y: float = 0.0,
    altitude: float = 0.0,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    building_id: int = 0,
    site_type: SiteType = SiteType.DN,
) -> DetectedSite:
    if latitude is not None and longitude is not None:
        location = GeoLocation(
            latitude=latitude, longitude=longitude, altitude=altitude
        )
    else:
        location = GeoLocation(
            utm_x=utm_x, utm_y=utm_y, utm_epsg=32601, altitude=altitude
        )
    return DetectedSite(
        site_type=site_type,
        location=location,
        building_id=building_id,
    )
