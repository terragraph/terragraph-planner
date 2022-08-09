# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
from typing import Callable, List, Optional, Tuple

from pyre_extensions import none_throws
from shapely.geometry import LineString, Point, Polygon

from terragraph_planner.common.structs import Point3D
from terragraph_planner.common.topology_models.site import LOSSite
from terragraph_planner.los.base_los_validator import BaseLOSValidator
from terragraph_planner.los.elevation import Elevation


class CylindricalLOSValidator(BaseLOSValidator):
    """
    Validate if a LOS is valid based on 2.5d surface elevation data (Elevation) using a
    cylindrical model.

    The cylinderical model is a simplified version of ellipsodal Fresnel Zone for the high
    frequency radio. It's suggested to use only when the resolution of elevation data is not
    much smaller than the Fresnel radius.

    For a 60,000 MHz radio between two sites that are 250 meters far away from each other, the
    Fresnel radius is about 1 meter. See more details about the Fresnel radius and Fresnel Zone.
    See class `FresnelZone` and our docs for more details.

    Supports confidence level with `los_confidence_threshold` parameter
    """

    def __init__(
        self,
        surface_elevation: Optional[Elevation],
        max_los_distance: float,
        min_los_distance: float,
        fresnel_radius: float,
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
        self._fresnel_radius = fresnel_radius
        self._fresnel_radius_sq: float = fresnel_radius * fresnel_radius

    def compute_confidence(self, site1: LOSSite, site2: LOSSite) -> float:
        """
        Given two sites, compute the confidence level if the minimal distance from any blocks
        to the LOS center >= fresnel_radius * MINIMAL_FRESNEL_RADIUS_THRESHOLD, else return 0.0
        """
        if not self._passes_simple_checks(site1, site2):
            return 0.0

        if self._surface_elevation is None:
            return 1.0

        return self._compute_confidence_by_radius(site1, site2)

    def _compute_confidence_by_radius(
        self, site1: LOSSite, site2: LOSSite
    ) -> float:
        utm_x1, utm_y1 = site1.utm_x, site1.utm_y
        utm_x2, utm_y2 = site2.utm_x, site2.utm_y
        altitude1, altitude2 = none_throws(site1.altitude), none_throws(
            site2.altitude
        )

        # Get the four corners of the 2D projection of the cylinder
        p, q, r, s = self._get_four_corners_of_rectangle(
            utm_x1, utm_y1, utm_x2, utm_y2, self._fresnel_radius
        )

        # Vectors pq, pr used to check if a point is within the 2D projection
        pq = (q[0] - p[0], q[1] - p[1])
        pr = (r[0] - p[0], r[1] - p[1])
        pq_squared = (pq[0] * pq[0]) + (pq[1] * pq[1])
        pr_squared = (pr[0] * pr[0]) + (pr[1] * pr[1])

        # Get all the obstructions within the 2D projection of the cylinder
        min_x, max_x = min(p[0], q[0], r[0], s[0]), max(p[0], q[0], r[0], s[0])
        min_y, max_y = min(p[1], q[1], r[1], s[1]), max(p[1], q[1], r[1], s[1])
        filter_func = self._filter_points_outside_of_rectangle(
            p, pq, pr, pq_squared, pr_squared
        )
        obstructions = none_throws(
            self._surface_elevation
        ).get_all_obstructions(min_x, max_y, max_x, min_y, filter_func)

        # Computes slopes
        # Slopes are used to:
        # 1. Compute the equation of the plane whose intersection with the los zone (a rectangle)
        #    has the same top view as the top view of the los zone. Let's call it max_top_view_plane
        #    here.
        # 2. Compute the distance from a point to the line
        yx_slope = None
        zx_slope = None
        xy_slope = None
        zy_slope = None
        sum_slope_sq = 0
        # Use two sets of slopes, one of which is based on x and the other is based on y
        # to avoid infinite slope value
        if utm_x2 != utm_x1:
            yx_slope = (utm_y2 - utm_y1) / (utm_x2 - utm_x1)
            zx_slope = (altitude2 - altitude1) / (utm_x2 - utm_x1)
            sum_slope_sq = 1 + yx_slope * yx_slope + zx_slope * zx_slope
        elif utm_y2 != utm_y1:
            xy_slope = (utm_x2 - utm_x1) / (utm_y2 - utm_y1)
            zy_slope = (altitude2 - altitude1) / (utm_y2 - utm_y1)
            sum_slope_sq = xy_slope * xy_slope + 1 + zy_slope * zy_slope

        # Compute the equation of the max_top_view_plane: ax + by + cz + d = 0
        # At first we need a third point on this plane. The line between this point
        # and site1 should be orthogonal with the los center line and be horizontal
        third_point_z = altitude1
        if yx_slope is not None:
            third_point_x = utm_x1 - yx_slope
            third_point_y = utm_y1 + 1
        else:
            third_point_x = utm_x1 + 1
            third_point_y = utm_y1 - none_throws(xy_slope)
        a = (utm_y2 - utm_y1) * (third_point_z - altitude1) - (
            altitude2 - altitude1
        ) * (third_point_y - utm_y1)
        b = (altitude2 - altitude1) * (third_point_x - utm_x1) - (
            utm_x2 - utm_x1
        ) * (third_point_z - altitude1)
        c = (utm_x2 - utm_x1) * (third_point_y - utm_y1) - (utm_y2 - utm_y1) * (
            third_point_x - utm_x1
        )
        d = -(a * utm_x1 + b * utm_y1 + c * altitude1)
        a_over_c = a / c
        b_over_c = b / c
        d_over_c = d / c

        los_2d_line = LineString([(utm_x1, utm_y1), (utm_x2, utm_y2)])

        minimal_radius = self._fresnel_radius * self._los_confidence_threshold
        minimal_distance = self._fresnel_radius

        # Higher grids are more likely to block the LOS. Sort possible_obstructions in
        # descending order to find blocks as soon as possible so that we can quit the following
        # loop earlier if there's a block.
        obstructions.sort(key=lambda loc: loc.z, reverse=True)

        highest_site_altitude = max(altitude1, altitude2)
        for grid in obstructions:
            x, y, z = grid
            if (
                self._los_confidence_threshold == 1.0
                and z > highest_site_altitude
            ):
                return 0.0
            z_on_max_top_view_plane = -(a_over_c * x + b_over_c * y + d_over_c)
            if z > z_on_max_top_view_plane:
                distance = los_2d_line.distance(Point(x, y))
            else:
                distance = self._distance_between_grid_top_and_center_line(
                    grid,
                    site1,
                    site2,
                    yx_slope,
                    zx_slope,
                    xy_slope,
                    zy_slope,
                    sum_slope_sq,
                )
            if distance < minimal_radius:
                return 0.0
            minimal_distance = min(minimal_distance, distance)
        return minimal_distance / self._fresnel_radius

    def _distance_between_grid_top_and_center_line(
        self,
        grid: Point3D,
        site1: LOSSite,
        site2: LOSSite,
        yx_slope: Optional[float],
        zx_slope: Optional[float],
        xy_slope: Optional[float],
        zy_slope: Optional[float],
        sum_slope_sq: float,
    ) -> float:
        """
        Use grid center as representative point. Compute the distance from the grid
        center to the 3d los center line to check if it's in the LOS zone.
        """
        x, y, z = grid
        altitude1 = none_throws(site1.altitude)
        # Gets x, y, z of the nearest point
        if yx_slope is not None:
            t = (
                (x - site1.utm_x)
                + yx_slope * (y - site1.utm_y)
                + none_throws(zx_slope) * (z - altitude1)
            ) / sum_slope_sq
            # If the orthogonal point is not on the line, use the nearest end
            if site2.utm_x > site1.utm_x:
                t = min(max(t, 0), site2.utm_x - site1.utm_x)
            else:
                t = min(max(t, site2.utm_x - site1.utm_x), 0)
            x_n = site1.utm_x + t
            y_n = site1.utm_y + t * yx_slope
            z_n = altitude1 + t * none_throws(zx_slope)
        else:
            t = (
                none_throws(xy_slope) * (x - site1.utm_x)
                + (y - site1.utm_y)
                + none_throws(zy_slope) * (z - altitude1)
            ) / sum_slope_sq
            # If the orthogonal point is not on the line, use the nearest end
            if site2.utm_y > site1.utm_y:
                t = min(max(t, 0), site2.utm_y - site1.utm_y)
            else:
                t = min(max(t, site2.utm_y - site1.utm_y), 0)
            x_n = site1.utm_x + t * none_throws(xy_slope)
            y_n = site1.utm_y + t
            z_n = altitude1 + t * none_throws(zy_slope)

        dist_sq = (
            (x - x_n) * (x - x_n)
            + (y - y_n) * (y - y_n)
            + (z - z_n) * (z - z_n)
        )

        return math.sqrt(dist_sq)

    def _filter_points_outside_of_rectangle(
        self,
        p: Tuple[float, float],
        pq: Tuple[float, float],
        pr: Tuple[float, float],
        pq_squared: float,
        pr_squared: float,
    ) -> Callable[[float, float], bool]:
        def check_point(utm_x: float, utm_y: float) -> bool:
            """
            Vectors pq and pr are perpendicular to each other.
            A point(m) is within the a rectangle if
            (0 <= pm⋅pq <= pq⋅pq) ∧ (0 <= pm⋅pr <= pr⋅pr)
            """
            pm = (utm_x - p[0], utm_y - p[1])
            return (0 <= (pm[0] * pq[0]) + (pm[1] * pq[1]) <= pq_squared) and (
                0 <= (pm[0] * pr[0]) + (pm[1] * pr[1]) <= pr_squared
            )

        return check_point
