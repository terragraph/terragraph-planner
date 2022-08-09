# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
from unittest import TestCase

from terragraph_planner.common.configuration.constants import (
    DEFAULT_CARRIER_FREQUENCY,
    DEFAULT_LOS_CONFIDENCE_THRESHOLD,
)
from terragraph_planner.common.exceptions import LOSException
from terragraph_planner.common.structs import Point3D
from terragraph_planner.los.fresnel_zone import FresnelZone
from terragraph_planner.los.test.helper import build_los_site_for_los_test


class TestFresnelZone(TestCase):
    def test_calculate_maximum_first_layer_fresnel_radius(self) -> None:
        site1 = build_los_site_for_los_test(5, 8, 6)
        site2 = build_los_site_for_los_test(225, 13, 10)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertAlmostEqual(fresnel_zone.fresnel_radius, 0.524333983)

    def test_fresnel_zone_rotation_angles(self) -> None:
        site1 = build_los_site_for_los_test(1, 1.5, 1.5)
        site2 = build_los_site_for_los_test(4, 2.8, 2.8)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertAlmostEqual(fresnel_zone._sin_a, 0.397607, places=6)
        self.assertAlmostEqual(fresnel_zone._cos_a, 0.917556, places=6)
        self.assertAlmostEqual(fresnel_zone._sin_b, 0.369473, places=6)
        self.assertAlmostEqual(fresnel_zone._cos_b, 0.929241, places=6)

    def test_fresnel_zone_rotation_angles_negative_slope(self) -> None:
        site1 = build_los_site_for_los_test(1, -1.5, -1.5)
        site2 = build_los_site_for_los_test(4, -2.8, -2.8)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertAlmostEqual(fresnel_zone._sin_a, -0.397607, places=6)
        self.assertAlmostEqual(fresnel_zone._cos_a, 0.917556, places=6)
        self.assertAlmostEqual(fresnel_zone._sin_b, -0.369473, places=6)
        self.assertAlmostEqual(fresnel_zone._cos_b, 0.929241, places=6)

    def test_fresnel_zone_rotation_angles_0_degrees(self) -> None:
        site1 = build_los_site_for_los_test(1, 10.5, 10.5)
        site2 = build_los_site_for_los_test(10, 10.5, 10.5)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertEqual(fresnel_zone._sin_a, 0.0)
        self.assertEqual(fresnel_zone._cos_a, 1.0)
        self.assertEqual(fresnel_zone._sin_b, 0.0)
        self.assertEqual(fresnel_zone._cos_b, 1.0)

    def test_fresnel_zone_rotation_angles_90_degrees(self) -> None:
        site1 = build_los_site_for_los_test(2, 1.5, 1.5)
        site2 = build_los_site_for_los_test(2, 2.8, 2.8)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertEqual(fresnel_zone._sin_a, 1.0)
        self.assertEqual(fresnel_zone._cos_a, 0.0)
        self.assertAlmostEqual(fresnel_zone._sin_b, 0.707107, places=6)
        self.assertAlmostEqual(fresnel_zone._cos_b, 0.707107, places=6)

    def test_fresnel_zone_rotation_angles_45_degrees(self) -> None:
        site1 = build_los_site_for_los_test(1, 1, 1)
        site2 = build_los_site_for_los_test(2, 2, 2)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertAlmostEqual(fresnel_zone._sin_a, 0.707107, places=6)
        self.assertAlmostEqual(fresnel_zone._cos_a, 0.707107, places=6)
        self.assertAlmostEqual(fresnel_zone._sin_b, 0.577350, places=6)
        self.assertAlmostEqual(fresnel_zone._cos_b, 0.816497, places=6)

    def test_fresnel_zone_midpoint(self) -> None:
        site1 = build_los_site_for_los_test(5, 8, 6)
        site2 = build_los_site_for_los_test(25, 13, 10)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertEqual(fresnel_zone._x_m, 15)
        self.assertEqual(fresnel_zone._y_m, 10.5)
        self.assertEqual(fresnel_zone._z_m, 8)

    def test_find_distance_to_midpoint(self) -> None:
        site1 = build_los_site_for_los_test(5, 8, 150)
        site2 = build_los_site_for_los_test(225, 56, 10)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertAlmostEqual(
            fresnel_zone._half_distance_sq,
            17576.0,
            places=6,
        )

        self.assertAlmostEqual(
            fresnel_zone._half_xy_distance_sq,
            12676.0,
            places=6,
        )

    def test_check_point_within_xy_ellipse(self) -> None:
        site1 = build_los_site_for_los_test(160.8, 89.2, 0)
        site2 = build_los_site_for_los_test(30.9, 29.8, 0)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )
        check_point_within_xy_ellipse = (
            fresnel_zone.check_point_within_outer_ellipse
        )

        slope = (site2.utm_y - site1.utm_y) / (site2.utm_x - site1.utm_x)
        y_intercept = site1.utm_y - slope * site1.utm_x
        for x in range(40, 160):
            self.assertEqual(
                check_point_within_xy_ellipse(x, (x * slope) + y_intercept),
                True,
            )
        self.assertEqual(check_point_within_xy_ellipse(60, 42), False)
        self.assertEqual(check_point_within_xy_ellipse(135.6, 78.1), False)
        self.assertEqual(check_point_within_xy_ellipse(95.8, 60), False)
        self.assertEqual(
            check_point_within_xy_ellipse(56.85, 41.296),
            True,
        )
        self.assertEqual(check_point_within_xy_ellipse(135.5, 77.9), True)
        self.assertEqual(check_point_within_xy_ellipse(95.9, 59.89), True)

    def test_check_point_within_xy_ellipse_ellipse_x_aligned(self) -> None:
        site1 = build_los_site_for_los_test(60, 125, 0)
        site2 = build_los_site_for_los_test(60, 5, 0)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )
        check_point_within_xy_ellipse = (
            fresnel_zone.check_point_within_outer_ellipse
        )

        for y in range(5, 125):
            self.assertEqual(check_point_within_xy_ellipse(60, y), True)
        self.assertEqual(check_point_within_xy_ellipse(59.9, 5.1), False)
        self.assertEqual(check_point_within_xy_ellipse(61, 64), False)
        self.assertEqual(
            check_point_within_xy_ellipse(60.4, 104.9),
            False,
        )
        self.assertEqual(check_point_within_xy_ellipse(59.9, 7.4), True)
        self.assertEqual(check_point_within_xy_ellipse(60.3, 64.5), True)
        self.assertEqual(
            check_point_within_xy_ellipse(60.25, 104.9),
            True,
        )

    def test_check_point_within_xy_ellipse_y_aligned(self) -> None:
        site1 = build_los_site_for_los_test(5, 10, 0)
        site2 = build_los_site_for_los_test(225, 10, 0)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )
        check_point_within_xy_ellipse = (
            fresnel_zone.check_point_within_outer_ellipse
        )

        for x in range(5, 225):
            self.assertEqual(check_point_within_xy_ellipse(x, 10), True)
        self.assertEqual(check_point_within_xy_ellipse(116, 10.6), False)
        self.assertEqual(check_point_within_xy_ellipse(221, 10.2), False)
        self.assertEqual(check_point_within_xy_ellipse(65, 9.5), False)
        self.assertEqual(check_point_within_xy_ellipse(116, 10.5), True)
        self.assertEqual(check_point_within_xy_ellipse(221, 10.1), True)
        self.assertEqual(check_point_within_xy_ellipse(65, 9.6), True)

    def test_solve_for_ellipsoid_height(self) -> None:
        site1 = build_los_site_for_los_test(5, 80, 60)
        site2 = build_los_site_for_los_test(225, 13, 10)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        height = fresnel_zone._solve_for_lower_ellipsoid_height(
            49, 66.5, fresnel_zone._outer_fresnel_radius_sq
        )

        self.assertAlmostEqual(
            height,
            49.560260,
            places=6,
        )

    def test_solve_for_ellipsoid_height_x_aligned(self) -> None:
        site1 = build_los_site_for_los_test(51, 13, 6)
        site2 = build_los_site_for_los_test(51, 130, 100)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        height = fresnel_zone._solve_for_lower_ellipsoid_height(
            51.3, 56.6, fresnel_zone._outer_fresnel_radius_sq
        )
        self.assertAlmostEqual(
            height,
            40.655046,
            places=6,
        )

    def test_solve_for_ellipsoid_height_y_aligned(self) -> None:
        site1 = build_los_site_for_los_test(13, 51, 6)
        site2 = build_los_site_for_los_test(130, 51, 100)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        height = fresnel_zone._solve_for_lower_ellipsoid_height(
            80.5, 51.2, fresnel_zone._outer_fresnel_radius_sq
        )
        self.assertAlmostEqual(
            height,
            59.745234,
            places=6,
        )

    def test_solve_for_ellipsoid_height_at_sites(self) -> None:
        site1 = build_los_site_for_los_test(13, 51, 6)
        site2 = build_los_site_for_los_test(130, 51, 100)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        height = fresnel_zone._solve_for_lower_ellipsoid_height(
            13, 51, fresnel_zone._outer_fresnel_radius_sq
        )
        self.assertAlmostEqual(
            height,
            6,
            places=6,
        )

        height = fresnel_zone._solve_for_lower_ellipsoid_height(
            130, 51, fresnel_zone._outer_fresnel_radius_sq
        )
        self.assertAlmostEqual(
            height,
            99.994851,
            places=6,
        )

    def test_solve_for_ellipsoid_height_no_real_solutions(self) -> None:
        site1 = build_los_site_for_los_test(13, 51, 6)
        site2 = build_los_site_for_los_test(130, 51, 100)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        height = fresnel_zone._solve_for_lower_ellipsoid_height(
            200, 300, fresnel_zone._outer_fresnel_radius_sq
        )

        self.assertEqual(height, math.inf)

    def test_check_point_obstruct_inner_fresnel_zone(self) -> None:
        site1 = build_los_site_for_los_test(5, 8, 6)
        site2 = build_los_site_for_los_test(225, 13, 25)
        fresnel_zone = FresnelZone(site1, site2, DEFAULT_CARRIER_FREQUENCY, 1.0)

        # Point not inside xy ellipse
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(30, 6.5, 15.5)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(115, 8, 15.5)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(219, 9.8, 15.5)
            ),
            False,
        )

        # Point inside xy ellipse and height below ellipsoid
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(30, 8.4, 7)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(115, 10.5, 14.3)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(220, 12.9, 22)
            ),
            False,
        )

        # Point inside xy ellipse and height inside ellipsoid
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(30, 8.4, 7.87)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(115, 10.5, 15.3)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(220, 12.9, 24.6)
            ),
            True,
        )

        # Point inside xy ellipse and height greater than ellipsoid
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(30, 8.4, 9)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(115, 10.5, 17)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(220, 12.9, 25)
            ),
            True,
        )

    def test_check_point_obstruct_inner_fresnel_zone_x_aligned(self) -> None:
        site1 = build_los_site_for_los_test(225, 25, 12)
        site2 = build_los_site_for_los_test(225, 130, 90)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        # Point not inside xy ellipse
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(222, 26, 51)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(226, 78, 51)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(224.8, 125, 51)
            ),
            False,
        )

        # Point inside xy ellipse and height below ellipsoid
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(225, 26.9, 13)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(224.96, 78.95, 51)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(225.1, 126.2, 87)
            ),
            False,
        )

        # Point inside xy ellipse and height inside ellipsoid
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(225, 26.9, 13.4)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(224.96, 78.95, 52.3)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(225.1, 126.2, 87.1)
            ),
            True,
        )

        # Point inside xy ellipse and height greater than ellipsoid
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(225, 26.9, 14)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(224.96, 78.95, 52.8)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(225.1, 126.2, 87.5)
            ),
            True,
        )

    def test_check_point_obstruct_inner_fresnel_zone_y_aligned(self) -> None:
        site1 = build_los_site_for_los_test(189, 80, 20)
        site2 = build_los_site_for_los_test(380, 80, 150)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        # Point not inside xy ellipse
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(194, 81, 85)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(284, 78, 85)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(375, 80.5, 85)
            ),
            False,
        )

        # Point inside xy ellipse and height below ellipsoid
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(194, 79.9, 23)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(282, 79.8, 81)
            ),
            False,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(375, 80, 146)
            ),
            False,
        )

        # Point inside xy ellipse and height inside ellipsoid
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(194, 79.9, 23.4)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(282, 79.8, 82.9)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(375, 80, 146.6)
            ),
            True,
        )

        # Point inside xy ellipse and height greater than ellipsoid
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(194, 79.9, 24)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(282, 79.8, 84)
            ),
            True,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(375, 80, 146.81)
            ),
            True,
        )

    def test_check_point_obstruct_inner_fresnel_zone_same_xy_as_site(
        self,
    ) -> None:
        site1 = build_los_site_for_los_test(
            utm_x=358694.4,
            utm_y=3881176.2,
            altitude=1668.8,
        )
        site2 = build_los_site_for_los_test(
            utm_x=358680.1,
            utm_y=3881192.6,
            altitude=1668.8,
        )

        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(
                Point3D(358680.1, 3881192.6, 1669.4)
            ),
            False,
        )

    def test_invalid_fresnel_zone(self) -> None:
        site1 = build_los_site_for_los_test(0, 0, 0)
        site2 = build_los_site_for_los_test(0, 0, 0)

        with self.assertRaisesRegex(
            LOSException,
            "The two end site of a Fresnel zone cannot have the same x and y",
        ):
            FresnelZone(
                site1,
                site2,
                DEFAULT_CARRIER_FREQUENCY,
                DEFAULT_LOS_CONFIDENCE_THRESHOLD,
            )

    def test_get_max_fresnel_radius_point_equal_to_center_line(self) -> None:
        site1 = build_los_site_for_los_test(0, 0, 5)
        site2 = build_los_site_for_los_test(1, 0.25, 5)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertAlmostEqual(
            fresnel_zone.get_max_fresnel_radius(Point3D(0.7, 0.2, 5)),
            0.0266145323711,
        )

    def test_get_max_fresnel_radius_point_greater_than_center_line(
        self,
    ) -> None:
        site1 = build_los_site_for_los_test(80, 170, 5)
        site2 = build_los_site_for_los_test(0, 200, 5)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertAlmostEqual(
            fresnel_zone.get_max_fresnel_radius(Point3D(37, 185.8, 8)),
            0.305106102966,
        )

    def test_get_max_fresnel_radius_point_less_than_center_line(self) -> None:
        site1 = build_los_site_for_los_test(10, 20, 6)
        site2 = build_los_site_for_los_test(60, 75, 6)
        fresnel_zone = FresnelZone(
            site1,
            site2,
            DEFAULT_CARRIER_FREQUENCY,
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertAlmostEqual(
            fresnel_zone.get_max_fresnel_radius(Point3D(46.1, 59.5, 5.9)),
            0.19271464599127164,
        )

    def test_zero_min_percentage_clear(self) -> None:
        site1 = build_los_site_for_los_test(0, 0, 1)
        site2 = build_los_site_for_los_test(6, 6, 6)
        fresnel_zone = FresnelZone(site1, site2, DEFAULT_CARRIER_FREQUENCY, 0)

        obstruction = Point3D(4, 4, 5)
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(obstruction),
            False,
        )
        self.assertAlmostEqual(
            fresnel_zone.get_max_fresnel_radius(obstruction), 0
        )

        obstruction = Point3D(4, 4, 4.3)
        self.assertEqual(
            fresnel_zone.check_point_obstruct_inner_fresnel_zone(obstruction),
            False,
        )
        self.assertAlmostEqual(
            fresnel_zone.get_max_fresnel_radius(obstruction),
            0.030421409151524737,
        )
