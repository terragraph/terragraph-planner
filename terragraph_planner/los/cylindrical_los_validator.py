# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
from typing import Callable, List, Optional, Tuple

from pyre_extensions import none_throws
from shapely.geometry import Polygon

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
        # Get the four corners of the 2D projection of the cylinder
        p, q, r, s = self._get_four_corners_of_rectangle(
            site1.utm_x,
            site1.utm_y,
            site2.utm_x,
            site2.utm_y,
            self._fresnel_radius,
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

        minimal_radius = self._fresnel_radius * self._los_confidence_threshold
        minimal_distance = self._fresnel_radius

        # Higher grids are more likely to block the LOS. Sort possible_obstructions in
        # descending order to find blocks as soon as possible so that we can quit the following
        # loop earlier if there's a block.
        obstructions.sort(key=lambda loc: loc.z, reverse=True)

        # Pre-compute some variables used in the distance computation
        ax, ay, az = site1.utm_x, site1.utm_y, none_throws(site1.altitude)
        bx = site2.utm_x - ax
        by = site2.utm_y - ay
        bz = none_throws(site2.altitude) - az
        b_len_2d_sq = bx * bx + by * by
        b_len_2d = math.sqrt(b_len_2d_sq)
        b_len_3d_sq = b_len_2d_sq + bz * bz

        highest_site_altitude = max(az, none_throws(site2.altitude))
        for grid in obstructions:
            if (
                self._los_confidence_threshold == 1.0
                and grid.z > highest_site_altitude
            ):
                return 0.0

            distance = self._distance_between_grid_and_center_line(
                grid, ax, ay, az, bx, by, bz, b_len_2d_sq, b_len_2d, b_len_3d_sq
            )
            if distance < minimal_radius:
                return 0.0
            minimal_distance = min(minimal_distance, distance)
        return minimal_distance / self._fresnel_radius

    def _distance_between_grid_and_center_line(
        self,
        grid: Point3D,
        ax: float,
        ay: float,
        az: float,
        bx: float,
        by: float,
        bz: float,
        b_len_2d_sq: float,
        b_len_2d: float,
        b_len_3d_sq: float,
    ) -> float:
        """
        Use grid center as representative point. Compute the distance from the vertical
        line that goes through grid center to the 3d los center line to check if LOS
        is blocked.

        The LOS center line is represented as r = a + p * b, and the vertical
        line is represented as r = c + q * d, where a, b, c, d are 3-D vectors,
        and p, q are numbers between (0, 1). Since d is vertical, we use d = (0, 0, -1)
        here, then b * d = (-by, bx, 0)

        The shortest distance is computed by d = (c - a) b * d / (b * d),
        where * is cross production between vectors.

        However, we also need to check if the intersection point is on the line segement
        by computing p and q in the simultaneous equation ((a + p * b) - (c + q * d))b = 0,
        ((a + p * b) - (c + q * d))d = 0.

        Based on q value, we have two different cases:
        1. q >= 0, which means the intersection point is not higher than the top of grid.
           a. If p <= 0 pr p >= 1, which means the block is behind the LOS, this function
              will return fresnel radius
           b. otherwise return the distance between two lines.

        2. p < 0, which means the intersection point is higher on the grid. In this
           case, the function returns the distance from grid top to the LOS center line
           by first determining where the cloest point is and then computing the distance
           between two points. If the closest point, which is the intersection of the
           LOS line and its orthogonal line going through grid top, is not between two
           sites, return fresnel radius.
        """
        cx, cy, cz = grid
        p = ((cx - ax) * bx + (cy - ay) * by) / b_len_2d_sq
        q = cz - az - p * bz
        if q >= 0:
            # Compute distance beween line b and line d
            if 0 <= p <= 1:
                return ((ax - cx) * by + (cy - ay) * bx) / b_len_2d
            else:
                # The obstruction is behind the site
                return self._fresnel_radius
        else:
            # Compute distance between point c to line b
            delta_ca_x = cx - ax
            delta_ca_y = cy - ay
            delta_ca_z = cz - az
            t = (
                delta_ca_x * bx + delta_ca_y * by + delta_ca_z * bz
            ) / b_len_3d_sq
            # The closest point is not between two sites
            if t < 0 or t > 1:
                return self._fresnel_radius
            # The following is the vector represents the distance between
            # grid top and the closest point
            dist_x = ax + t * bx - cx
            dist_y = ay + t * by - cy
            dist_z = az + t * bz - cz

            return math.sqrt(
                dist_x * dist_x + dist_y * dist_y + dist_z * dist_z
            )

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
