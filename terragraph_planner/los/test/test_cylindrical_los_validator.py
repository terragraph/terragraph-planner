# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

import numpy as np
from osgeo import osr
from shapely.geometry import Polygon

from terragraph_planner.common.configuration.constants import (
    DEFAULT_LOS_CONFIDENCE_THRESHOLD,
)
from terragraph_planner.common.configuration.enums import LocationType
from terragraph_planner.common.structs import UTMBoundingBox
from terragraph_planner.los.cylindrical_los_validator import (
    CylindricalLOSValidator,
)
from terragraph_planner.los.elevation import Elevation
from terragraph_planner.los.test.helper import build_los_site_for_los_test


class TestEllipsoidalLOSValidator(TestCase):
    def setUp(self) -> None:
        self.spatial_reference = osr.SpatialReference()
        self.spatial_reference.ImportFromEPSG(32647)
        self.elevation = Elevation(
            np.array([[4, 2, 3], [2, 5, 1], [3, 2, 1]]),
            UTMBoundingBox(3, 3, 0, 0),
            1,
            1,
            0.5,
            2.5,
            self.spatial_reference,
            None,
        )

    def test_on_the_same_building(self) -> None:
        los_validator = CylindricalLOSValidator(
            self.elevation, 5, 1, 0.4, [], DEFAULT_LOS_CONFIDENCE_THRESHOLD
        )
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(
                    0.5,
                    0.5,
                    10,
                    location_type=LocationType.ROOFTOP,
                    building_id=1,
                ),
                build_los_site_for_los_test(
                    2.5,
                    2.5,
                    9,
                    location_type=LocationType.ROOFTOP,
                    building_id=1,
                ),
            ),
            0.0,
        )

    def test_out_of_distance_range(self) -> None:
        los_validator = CylindricalLOSValidator(
            self.elevation, 2, 1, 0.4, [], DEFAULT_LOS_CONFIDENCE_THRESHOLD
        )
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 10),
                build_los_site_for_los_test(2.5, 2.5, 9),
            ),
            0.0,
        )

    def test_intersects_with_exclusion_zone(self) -> None:
        los_validator = CylindricalLOSValidator(
            self.elevation,
            5,
            1,
            0.4,
            [Polygon([(1, 1), (2, 1), (2, 2), (1, 2)])],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 10),
                build_los_site_for_los_test(2.5, 2.5, 9),
            ),
            0.0,
        )

    def test_grid_higher_than_sites(self) -> None:
        los_validator = CylindricalLOSValidator(
            self.elevation, 5, 1, 0.4, [], DEFAULT_LOS_CONFIDENCE_THRESHOLD
        )
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 1),
                build_los_site_for_los_test(2.5, 2.5, 2),
            ),
            0.0,
        )

    def test_a_clear_los(self) -> None:
        los_validator = CylindricalLOSValidator(
            self.elevation, 5, 1, 0.4, [], DEFAULT_LOS_CONFIDENCE_THRESHOLD
        )
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 10),
                build_los_site_for_los_test(2.5, 2.5, 9),
            ),
            1.0,
        )

    def test_grid_higher_than_max_top_view_plane(self) -> None:
        los_validator = CylindricalLOSValidator(
            self.elevation, 5, 1, 0.4, [], DEFAULT_LOS_CONFIDENCE_THRESHOLD
        )
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 5.2),
                build_los_site_for_los_test(2.5, 2.5, 4.75),
            ),
            0.0,
        )

    def test_grid_center_within_utm_zone(self) -> None:
        los_validator = CylindricalLOSValidator(
            self.elevation, 5, 1, 0.4, [], DEFAULT_LOS_CONFIDENCE_THRESHOLD
        )
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 5.4),
                build_los_site_for_los_test(2.5, 2.5, 5.5),
            ),
            1.0,
        )
        self.assertLess(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 5.4),
                build_los_site_for_los_test(2.5, 2.5, 5.3),
            ),
            1.0,
        )

    def test_compute_confidence(self) -> None:
        grid_matrix = np.ones([5, 5]) * 5
        grid_matrix[2] = 0
        elevation = Elevation(
            grid_matrix,
            UTMBoundingBox(5, 5, 0, 0),
            1,
            1,
            0.5,
            4.5,
            self.spatial_reference,
            None,
        )
        los_validator = CylindricalLOSValidator(
            elevation, 5, 1, 1, [], DEFAULT_LOS_CONFIDENCE_THRESHOLD
        )
        # The LOS line is below the max_top_view_plane, so the minimal distance
        # is from point (x.5, 3.5, z) to the LOS center, where x = 1,2,3,4, and z < 5
        self.assertAlmostEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 2.6, 4.5),
                build_los_site_for_los_test(4.5, 2.6, 4.8),
            ),
            0.9,
            places=5,
        )
        # Although the (x, y) are the same as those above, these 2 sites are too short
        # the minimal distance is from point (0.5, 2.5, 0)
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 2.6, 0.5),
                build_los_site_for_los_test(4.5, 2.6, 0.8),
            ),
            0.0,
        )
        # The LOS line is above the max_top_view_plane, so the minimal distance is
        # from point (x.5, 3.5, 5) to the LOS center.
        self.assertAlmostEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 2.26, 5.57),
                build_los_site_for_los_test(4.5, 2.26, 5.57),
            ),
            0.95,
            places=5,
        )

    def test_point_within_rectangle(self) -> None:
        los_validator = CylindricalLOSValidator(
            self.elevation, 5, 1, 1, [], DEFAULT_LOS_CONFIDENCE_THRESHOLD
        )
        utm_x1, utm_y1 = (1, 1)
        utm_x2, utm_y2 = (3, 0.5)
        a, b, c, d = los_validator._get_four_corners_of_rectangle(
            utm_x1, utm_y1, utm_x2, utm_y2, 2
        )
        ab = (b[0] - a[0], b[1] - a[1])
        ac = (c[0] - a[0], c[1] - a[1])
        ab_squared = (ab[0] * ab[0]) + (ab[1] * ab[1])
        ac_squared = (ac[0] * ac[0]) + (ac[1] * ac[1])

        check_point = los_validator._filter_points_outside_of_rectangle(
            a, ab, ac, ab_squared, ac_squared
        )
        self.assertEqual(check_point(3, -1), False)
        self.assertEqual(check_point(3, 2.8), False)
        self.assertEqual(check_point(1, 2), False)
        self.assertEqual(check_point(1, -1.2), False)
        self.assertEqual(check_point(2, -1), True)
        self.assertEqual(check_point(1.05, 1), True)
        self.assertEqual(check_point(3, 2), True)

    def test_compute_confidence_filter_obstructions(self) -> None:
        elevation = Elevation(
            data_matrix=np.array(
                [
                    [3, 3, 3, 3, 3],
                    [3, 3, 0, 3, 3],
                    [3, 0, 0, 0, 3],
                    [0, 0, 0, 3, 3],
                    [3, 0, 3, 3, 3],
                ]
            ),
            utm_bounding_box=UTMBoundingBox(4, 5, 0, 0),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=0,
            left_top_y=5,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        los_validator = CylindricalLOSValidator(elevation, 5, 1, 2, [], 1.0)

        # Obstructions with height 3 will cause confidence level to be 0 but they
        # are not within the 2D projection and are filtered out
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(2, 2, 2),
                build_los_site_for_los_test(1, 3, 2),
            ),
            1.0,
        )

    def test_compute_confidence_filter_obstructions2(self) -> None:
        elevation = Elevation(
            data_matrix=np.array(
                [
                    [3, 3, 3, 3, 3],
                    [3, 0, 0, 3, 3],
                    [3, 0, 0, 0, 3],
                    [3, 0, 0, 0, 3],
                    [3, 3, 0, 0, 3],
                ]
            ),
            utm_bounding_box=UTMBoundingBox(4, 5, 0, 0),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=0,
            left_top_y=5,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        los_validator = CylindricalLOSValidator(elevation, 5, 1, 2, [], 1.0)

        # Obstructions with height 3 will cause confidence level to be 0 but they
        # are not within the 2D spatial_reference and are filtered out
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(1, 2, 2),
                build_los_site_for_los_test(3, 3, 2),
            ),
            1.0,
        )

    def test_compute_confidence_x_aligned(self) -> None:
        elevation = Elevation(
            data_matrix=np.array(
                [
                    [3, 3, 3, 3],
                    [3, 3, 3, 3],
                    [0, 0, 0, 3],
                    [0, 0, 0, 3],
                    [3, 3, 3, 3],
                    [3, 3, 3, 3],
                ]
            ),
            utm_bounding_box=UTMBoundingBox(3, 5, 0, 0),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=0,
            left_top_y=5,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        los_validator = CylindricalLOSValidator(elevation, 5, 1, 1, [], 1.0)

        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(1, 2, 2),
                build_los_site_for_los_test(1, 3, 2),
            ),
            1.0,
        )

    def test_compute_confidence_y_aligned(self) -> None:
        elevation = Elevation(
            data_matrix=np.array(
                [
                    [3, 3, 3, 3, 3],
                    [3, 0, 0, 0, 3],
                    [3, 0, 0, 0, 3],
                    [3, 0, 0, 0, 3],
                    [3, 0, 0, 0, 3],
                    [3, 0, 0, 0, 3],
                    [3, 3, 3, 3, 3],
                ]
            ),
            utm_bounding_box=UTMBoundingBox(4, 5, 0, 0),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=0,
            left_top_y=5,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        los_validator = CylindricalLOSValidator(elevation, 5, 1, 2, [], 1.0)

        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(1, 2, 2),
                build_los_site_for_los_test(3, 2, 2),
            ),
            1.0,
        )
