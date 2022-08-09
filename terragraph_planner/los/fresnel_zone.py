# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
from functools import partial

from pyre_extensions import none_throws

from terragraph_planner.common.exceptions import LOSException, planner_assert
from terragraph_planner.common.structs import Point3D
from terragraph_planner.common.topology_models.site import LOSSite


class FresnelZone:
    """
    This class handles everything related to the geometry of a Fresnel zone between two sites.
    This class currectly only supports the first Fresnel Zone.
    This class uses a 2D ellipse on the xy place and a 3D ellipsoid to check if a point is within
    or abovt the Fresnel Zone.

    2D ellipse on the xy plane equation (1):
        ((x - h)cos(A) + (y-k)sin(A))^2 / a^2 + ((x - h)sin(A) - (y-k)cos(A))^2 / b^2 - 1 = 0

        Where angle A is the angle between the x axis and the line which goes through both sites
        (h,k) are the (x,y) offsets from the origin
        `a` is the 2D euclidean distance from a site to the midpoint
        `b` is the Fresnel Radius

    3D ellipsoid equation (2):
        ((x - h)*cos(B)*cos(A) + (y - k)*sin(A)*cos(B) + (z - l)*sin(B))^2 / a^2
        + ((h - x)*sin(A) + (y - k)*cos(A))^2 / b^2
        + ((h - x)*sin(B)*cos(A) + (k - y)*sin(B)*sin(A) + (z - l)*cos(B))^2 / c^2
        - 1 = 0

        Where angle A is the first rotation around the z axis and angle B is the second rotation around the y axis
        (h,k,l) are the (x,y,z) offsets from the origin
        `a` is the 3D euclidean distance from a site to the midpoint
        `b` and `c` are the Fresnel Radius

    Max top view plane equation (3):
        a*x + b*y + c*z + d = 0
        => a/d * x + b/d * x + c/d * z + 1 = 0

        We call the plane whose intersection with the ellipsoid Fresnel Zone has
        the max top view as "max top view plane".
        If a point (x, y, z) is lower than that plane, we check the intersection
        between point (x, y, z) and the 3-D eelipsoid.
        If a point (x, y, z) is higher than that plane, we check the intersection
        between point (x, y) with the 2-D ellipse instead.
    """

    # FIRST_ZONE_MULTIPLIER is used in the equation for maximum radius
    # of the 1st Fresnel Zone: r = 1/2*sqrt(c*D/f)
    # where c = 299,792,458 m/s
    # sqrt(c) / 2 = 8.65725790883
    # Therefore, r = 8.65725790883 * sqrt(D/f)
    # D in meter and f in MHz
    FIRST_ZONE_MULTIPLIER = 8.65725790883

    def __init__(
        self,
        site1: LOSSite,
        site2: LOSSite,
        frequency_mhz: float,
        los_confidence_threshold: float,
    ) -> None:
        """
        @param site1, site2
        The two end sites to compute the Fresnel Zone for

        @param los_confidence_threshold
        The minimum percentage that the inner Fresnel Zone has to be clear of obstructions

        @param frequency_mhz
        The radio frequency in MHz

        @param
        fresnel_radius
        The maximum Fresnel zone radius for the 1st layer in metres
        """
        planner_assert(
            0.0 <= los_confidence_threshold <= 1.0,
            "The minimal clear percentage must be a float in [0, 1]",
            LOSException,
        )
        planner_assert(
            site1.utm_x != site2.utm_x or site1.utm_y != site2.utm_y,
            "The two end site of a Fresnel zone cannot have the same x and y",
            LOSException,
        )
        self._site1 = site1
        self._site2 = site2
        self._los_confidence_threshold = los_confidence_threshold
        self._frequency_mhz = frequency_mhz

        self._get_equation_constants()
        # Checks if a point (x,y) is inside the outer/inner ellipse
        self.check_point_within_outer_ellipse: partial[bool] = partial(
            self._filter_points_outside_of_ellipse,
            self._outer_fresnel_radius_sq,
        )
        self.check_point_within_inner_ellipse: partial[bool] = partial(
            self._filter_points_outside_of_ellipse,
            self._inner_fresnel_radius_sq,
        )

    @property
    def site1(self) -> LOSSite:
        return self._site1

    @property
    def site2(self) -> LOSSite:
        return self._site2

    @property
    def los_confidence_threshold(self) -> float:
        return self._los_confidence_threshold

    @property
    def frequency_mhz(self) -> float:
        return self._frequency_mhz

    @property
    def fresnel_radius(self) -> float:
        return self._outer_fresnel_radius

    def check_point_obstruct_inner_fresnel_zone(self, point: Point3D) -> bool:
        """
        A point (x, y, z) obstructs the Fresnel Zone if the x, y coordinates are inside the ellipse
        and the height z is within or greater than the height of the ellipsoid.
        """
        x, y, z = point
        if (x == self._site1.utm_x and y == self._site1.utm_y) or (
            x == self._site2.utm_x and y == self._site2.utm_y
        ):
            return False

        if self._los_confidence_threshold == 0:
            return False

        if not self.check_point_within_inner_ellipse(x, y):
            return False

        height = self._solve_for_lower_ellipsoid_height(
            x,
            y,
            self._inner_fresnel_radius_sq,
        )
        return z >= height

    def get_max_fresnel_radius(self, point: Point3D) -> float:
        """
        Points that are called to this method should be between the inner and outer ellipses
        Return the maximum Fresnel zone that can be created with the point on the border
        2 cases:
            1: If the point is below max top view plane, we use the 3D ellipsoid to solve for the Fresnel radius
            2: If the point is equal to or above the max top view plane, we use the 2D ellipse because
               the closest distance to the obstruction is where the height(z) is equal
        """
        x, y, z = point
        height = self._solve_for_lower_ellipsoid_height(
            x, y, self._outer_fresnel_radius_sq
        )
        if z < height:
            return self._outer_fresnel_radius

        z_on_max_top_view_plane = -(
            self._a_over_c * x + self._b_over_c * y + self._d_over_c
        )
        if z >= z_on_max_top_view_plane:
            return self._solve_for_max_fresnel_radius_2d(x, y)
        return self._solve_for_max_fresnel_radius_3d(x, y, z)

    def _get_equation_constants(self) -> None:
        """
        Compute all the constant parameters in the 3 equations for the Fresnel Zone.

        _outer_fresnel_radius
        The maximum Fresnel zone radius for the 1st layer in meters

        _inner_fresnel_radius: float
        The minimum Fresnel zone radius that has to be clear of obstructions

        _sin_a, _cos_a, _sin_b, _cos_b
        sin(A), cos(A), sin(B), cos(B) in the equation (1) and (2).

        _x_m, _y_m, _z_m: float
        The (x,y,z) midpoints between site1 and site2, used as (h,k,l) in the equations (1) and (2)

        _half_distance_sq
        Square of the half distance between two sites, used as "a^2" in the 3D ellipsoid equation (1)

        _half_xy_distance_sq
        Square of the half distance in xy plane between two sites, used as "a^2" in the ellipse
        equation (2)

        _outer_fresnel_radius_sq, _inner_fresnel_radius_sq:
        Reused values stored as class attributes to save computation time

        _a_over_c, _b_over_c, _d_over_c: float
        Used to obtain z_on_max_top_view_plane (3) to decide whether to use the 3D or 2D equation to
        solve for fresnel radius
        """
        site1 = self._site1
        site2 = self._site2
        altitude1 = none_throws(site1.altitude)
        altitude2 = none_throws(site2.altitude)

        x_distance = site2.utm_x - site1.utm_x
        y_distance = site2.utm_y - site1.utm_y
        z_distance = altitude2 - altitude1
        xy_distance_sq = x_distance * x_distance + y_distance * y_distance
        xy_distance = math.sqrt(xy_distance_sq)
        distance_sq = xy_distance_sq + z_distance * z_distance
        distance = math.sqrt(distance_sq)

        self._cos_a = x_distance / xy_distance
        self._sin_a = y_distance / xy_distance
        self._cos_b = xy_distance / distance
        self._sin_b = z_distance / distance

        self._outer_fresnel_radius = (
            FresnelZone.FIRST_ZONE_MULTIPLIER
            * math.sqrt(distance / self._frequency_mhz)
        )
        self._outer_fresnel_radius_sq = (
            self._outer_fresnel_radius * self._outer_fresnel_radius
        )
        self._inner_fresnel_radius = (
            self._outer_fresnel_radius * self._los_confidence_threshold
        )
        self._inner_fresnel_radius_sq = (
            self._inner_fresnel_radius * self._inner_fresnel_radius
        )

        self._x_m = (site1.utm_x + site2.utm_x) / 2
        self._y_m = (site1.utm_y + site2.utm_y) / 2
        self._z_m = (altitude1 + altitude2) / 2
        self._half_distance_sq = distance_sq / 4
        self._half_xy_distance_sq = xy_distance_sq / 4

        third_point_z = altitude1
        if x_distance != 0:
            yx_slope = y_distance / x_distance
            third_point_x = site1.utm_x - yx_slope
            third_point_y = site1.utm_y + 1
        elif y_distance != 0:
            xy_slope = x_distance / y_distance
            third_point_x = site1.utm_x + 1
            third_point_y = site1.utm_y - xy_slope
        else:
            raise LOSException("The two sites to check LOS overlap")

        a = (site2.utm_y - site1.utm_y) * (third_point_z - altitude1) - (
            altitude2 - altitude1
        ) * (third_point_y - site1.utm_y)
        b = (altitude2 - altitude1) * (third_point_x - site1.utm_x) - (
            site2.utm_x - site1.utm_x
        ) * (third_point_z - altitude1)
        c = (site2.utm_x - site1.utm_x) * (third_point_y - site1.utm_y) - (
            site2.utm_y - site1.utm_y
        ) * (third_point_x - site1.utm_x)
        d = -(a * site1.utm_x + b * site1.utm_y + c * altitude1)
        self._a_over_c = a / c
        self._b_over_c = b / c
        self._d_over_c = d / c

    def _filter_points_outside_of_ellipse(
        self, fresnel_radius_sq: float, utm_x: float, utm_y: float
    ) -> bool:
        """
        Return True if the point is inside of the ellipse.
        """
        first_term_numerator = (utm_x - self._x_m) * self._cos_a + (
            utm_y - self._y_m
        ) * self._sin_a
        second_term_numerator = (utm_x - self._x_m) * self._sin_a - (
            utm_y - self._y_m
        ) * self._cos_a
        return (
            first_term_numerator
            * first_term_numerator
            / self._half_xy_distance_sq
            + second_term_numerator * second_term_numerator / fresnel_radius_sq
            <= 1
        )

    def _solve_for_lower_ellipsoid_height(
        self, x: float, y: float, fresnel_radius_sq: float
    ) -> float:
        """
        Find the lower height on the ellipsod for a point (x, y).
        Rearrange the 3D ellipsoid equation into standard form of a quadratic equation for variable 'z'
        """
        x_m = self._x_m
        y_m = self._y_m
        cos_a = self._cos_a
        cos_b = self._cos_b
        sin_a = self._sin_a
        sin_b = self._sin_b
        a_sq = self._half_distance_sq
        c_sq = b_sq = fresnel_radius_sq

        tmp1 = ((x - x_m) * cos_a * cos_b) + ((y - y_m) * sin_a * cos_b)
        tmp2 = ((x_m - x) * cos_a * sin_b) + ((y_m - y) * sin_a * sin_b)
        quad_a = ((sin_b * sin_b) / a_sq) + ((cos_b * cos_b) / c_sq)
        quad_b = 2 * (((tmp1 * sin_b) / a_sq) + ((tmp2 * cos_b) / c_sq))
        quad_c = (
            ((tmp1 * tmp1) / a_sq)
            + ((tmp2 * tmp2) / c_sq)
            + (
                (((x_m - x) * sin_a) + ((y - y_m) * cos_a))
                * (((x_m - x) * sin_a) + ((y - y_m) * cos_a))
                / b_sq
            )
            - 1
        )

        quad_d = quad_b * quad_b - 4 * quad_a * quad_c
        planner_assert(
            quad_a > 0,
            "Something goes wrong when solving the quadratic equation in LOS computation. "
            "Please do not change the parameters computed internally.",
            LOSException,
        )
        if quad_d <= 0:
            return math.inf
        if quad_b >= 0:
            return (-quad_b - math.sqrt(quad_d)) / (2 * quad_a) + self._z_m
        return (2 * quad_c) / (-quad_b + math.sqrt(quad_d)) + self._z_m

    def _solve_for_max_fresnel_radius_2d(self, x: float, y: float) -> float:
        """
        Compute the max Fresnel radius for the 2D ellipse, with which the ellipse
        does not intersect with (x, y)
        """
        first_term_numerator = (x - self._x_m) * self._cos_a + (
            y - self._y_m
        ) * self._sin_a
        a = (
            first_term_numerator
            * first_term_numerator
            / self._half_xy_distance_sq
        )
        second_term_numerator = (x - self._x_m) * self._sin_a - (
            y - self._y_m
        ) * self._cos_a
        b = second_term_numerator * second_term_numerator
        if a >= 1:
            return self._outer_fresnel_radius
        return math.sqrt(b / (1 - a))

    def _solve_for_max_fresnel_radius_3d(
        self, x: float, y: float, z: float
    ) -> float:
        """
        Compute the max Fresnel radius for the 3D ellipsoid, with which the ellipsoid
        does not intersect with (x, y, z)
        """
        cos_a = self._cos_a
        cos_b = self._cos_b
        sin_a = self._sin_a
        sin_b = self._sin_b
        a_sq = self._half_distance_sq
        first_term_numerator = (
            ((x - self._x_m) * cos_a * cos_b)
            + ((y - self._y_m) * sin_a * cos_b)
            + ((z - self._z_m) * sin_b)
        )
        a = first_term_numerator * first_term_numerator / a_sq
        second_term_numerator = ((self._x_m - x) * sin_a) + (
            (y - self._y_m) * cos_a
        )
        b = second_term_numerator * second_term_numerator
        third_term_numerator = (
            ((self._x_m - x) * cos_a * sin_b)
            + ((self._y_m - y) * sin_a * sin_b)
            + ((z - self._z_m) * cos_b)
        )
        c = third_term_numerator * third_term_numerator
        if a >= 1:
            return self._outer_fresnel_radius
        return math.sqrt((b + c) / (1 - a))
