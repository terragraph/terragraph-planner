# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import List, Optional

from pyre_extensions import none_throws
from shapely.geometry import Polygon

from terragraph_planner.common.topology_models.site import LOSSite
from terragraph_planner.los.base_los_validator import BaseLOSValidator
from terragraph_planner.los.elevation import Elevation
from terragraph_planner.los.fresnel_zone import FresnelZone


class EllipsoidalLOSValidator(BaseLOSValidator):
    """
    Validate if a LOS is valid based on 2.5d surface elevation data (Elevation)
    with the ellipsoidal Fresnel Zone.
    Supports confidence level with `los_confidence_threshold` parameter
    """

    def __init__(
        self,
        surface_elevation: Optional[Elevation],
        max_los_distance: float,
        min_los_distance: float,
        frequency_mhz: float,
        exclusion_zones: List[Polygon],
        los_confidence_threshold: float,
    ) -> None:
        super().__init__(
            surface_elevation,
            max_los_distance,
            min_los_distance,
            exclusion_zones,
            los_confidence_threshold,
        )
        self._frequency_mhz = frequency_mhz

    def compute_confidence(self, site1: LOSSite, site2: LOSSite) -> float:
        if not self._passes_simple_checks(site1, site2):
            return 0.0

        # If there's no surface elevation data, every link that passes the simple checks
        # have a LOS
        if self._surface_elevation is None:
            return 1.0

        fresnel_zone = FresnelZone(
            site1,
            site2,
            self._frequency_mhz,
            self._los_confidence_threshold,
        )

        # The rectangle encapsulates the 2D projection of the ellipsoid
        a, b, c, d = self._get_four_corners_of_rectangle(
            site1.utm_x,
            site1.utm_y,
            site2.utm_x,
            site2.utm_y,
            fresnel_zone.fresnel_radius,
        )

        min_x, max_x = min(a[0], b[0], c[0], d[0]), max(a[0], b[0], c[0], d[0])
        min_y, max_y = min(a[1], b[1], c[1], d[1]), max(a[1], b[1], c[1], d[1])
        filter_func = fresnel_zone.check_point_within_outer_ellipse
        obstructions = none_throws(
            self._surface_elevation
        ).get_all_obstructions(min_x, max_y, max_x, min_y, filter_func)

        min_fresnel_radius = fresnel_zone.fresnel_radius
        for obstruction in obstructions:
            if fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                obstruction
            ):
                return 0.0

            fresnel_radius = fresnel_zone.get_max_fresnel_radius(obstruction)
            min_fresnel_radius = min(fresnel_radius, min_fresnel_radius)

        return min_fresnel_radius / fresnel_zone.fresnel_radius
