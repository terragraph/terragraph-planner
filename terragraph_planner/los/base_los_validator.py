# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from shapely.geometry import LineString, Polygon
from shapely.prepared import PreparedGeometry, prep

from terragraph_planner.common.configuration.enums import LocationType
from terragraph_planner.common.exceptions import LOSException, planner_assert
from terragraph_planner.common.topology_models.site import LOSSite
from terragraph_planner.los.elevation import Elevation


class BaseLOSValidator(ABC):
    """
    Base LOS Validator class used to support CylindricalLOSValidator and EllipsoidalLOSValidator.

    If surface_elevation is None, every link passes simple checks should have confidence level 1.0 .
    """

    def __init__(
        self,
        surface_elevation: Optional[Elevation],
        max_los_distance: float,
        min_los_distance: float,
        exclusion_zones: List[Polygon],
        los_confidence_threshold: float,
    ) -> None:
        planner_assert(
            0 <= los_confidence_threshold <= 1.0,
            "Invalid LOS confidence threshold",
            LOSException,
        )

        self._surface_elevation = surface_elevation
        self._max_los_distance_sq: float = max_los_distance * max_los_distance
        self._min_los_distance_sq: float = min_los_distance * min_los_distance
        self._exclusion_zones: List[PreparedGeometry] = [
            prep(exclusion_polygon) for exclusion_polygon in exclusion_zones
        ]
        self._los_confidence_threshold = los_confidence_threshold

    @abstractmethod
    def compute_confidence(self, site1: LOSSite, site2: LOSSite) -> float:
        raise NotImplementedError

    def _passes_simple_checks(self, site1: LOSSite, site2: LOSSite) -> bool:
        """
        Performs these simple checks
        Check 1: on the same xy coordinate
        Check 2: on the same building
        Check 3: out of distance range
        Check 4: intersects with the exclusion zones
        """
        if site1.utm_x == site2.utm_x and site1.utm_y == site2.utm_y:
            return False

        if self._on_the_same_building(site1, site2):
            return False

        if self._los_out_of_distance_range(site1, site2):
            return False

        if self._los_intersects_with_exclusion_zones(site1, site2):
            return False

        return True

    def _on_the_same_building(self, site1: LOSSite, site2: LOSSite) -> bool:
        return (
            site1.location_type
            == site2.location_type
            == LocationType.ROOFTOP.value
            and site1.building_id == site2.building_id
        )

    def _los_out_of_distance_range(
        self, site1: LOSSite, site2: LOSSite
    ) -> bool:
        x_diff = site1.utm_x - site2.utm_x
        y_diff = site1.utm_y - site2.utm_y
        if site1.altitude is not None and site2.altitude is not None:
            z_diff = site1.altitude - site2.altitude
        else:
            z_diff = 0
        dist_sq = x_diff * x_diff + y_diff * y_diff + z_diff * z_diff
        return (
            not self._min_los_distance_sq
            <= dist_sq
            <= self._max_los_distance_sq
        )

    def _los_intersects_with_exclusion_zones(
        self, site1: LOSSite, site2: LOSSite
    ) -> bool:
        """
        Check if the LOS(a line without width) intersects with the exclusion zones in 2-D space.
        """
        los_center_line_2d = LineString(
            ((site1.utm_x, site1.utm_y), (site2.utm_x, site2.utm_y))
        )
        for zone in self._exclusion_zones:
            if zone.intersects(los_center_line_2d):
                return True
        return False

    def _get_four_corners_of_rectangle(
        self,
        utm_x1: float,
        utm_y1: float,
        utm_x2: float,
        utm_y2: float,
        radius: float,
    ) -> Tuple[
        Tuple[float, float],
        Tuple[float, float],
        Tuple[float, float],
        Tuple[float, float],
    ]:
        """
        Returns the four corners a,b,c,d of a rectangle with width = 2*radius
        ac and ab are parallel to each other
        ab and dc are parallel to each other
        """
        # Avoid divide by 0 precision errors by using larger value in denominator
        if abs(utm_x2 - utm_x1) >= abs(utm_y2 - utm_y1):
            slope = (utm_y2 - utm_y1) / (utm_x2 - utm_x1)
            offset_y = radius / math.sqrt(1 + slope * slope)
            offset_x = offset_y * slope
        else:
            slope_inv = (utm_x2 - utm_x1) / (utm_y2 - utm_y1)
            offset_x = radius / math.sqrt(1 + slope_inv * slope_inv)
            offset_y = offset_x * slope_inv

        a = utm_x1 + offset_x, utm_y1 - offset_y
        b = utm_x1 - offset_x, utm_y1 + offset_y
        c = utm_x2 + offset_x, utm_y2 - offset_y
        d = utm_x2 - offset_x, utm_y2 + offset_y

        return a, b, c, d
