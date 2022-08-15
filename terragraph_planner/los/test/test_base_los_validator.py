# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

import numpy as np
from osgeo import osr
from shapely.geometry import Polygon

from terragraph_planner.common.configuration.enums import LocationType
from terragraph_planner.common.structs import UTMBoundingBox
from terragraph_planner.common.topology_models.site import LOSSite
from terragraph_planner.los.base_los_validator import BaseLOSValidator
from terragraph_planner.los.elevation import Elevation
from terragraph_planner.los.test.helper import build_los_site_for_los_test


class MockBaseLOSValidator(BaseLOSValidator):
    """
    Overwrite the abstract method so that we can initialize it in the tests.
    """

    def compute_confidence(self, site1: LOSSite, site2: LOSSite) -> float:
        return 1.0


class TestBaseLOSValidator(TestCase):
    def setUp(self) -> None:
        spatial_reference = osr.SpatialReference()
        spatial_reference.ImportFromEPSG(32647)
        self.elevation = Elevation(
            np.array([[4, 2, 3], [2, 5, 1], [3, 2, 1]]),
            UTMBoundingBox(3, 3, 0, 0),
            1,
            1,
            0.5,
            2.5,
            spatial_reference,
            None,
        )

    def test_same_x_y_coordinate(self) -> None:
        base_los_validator = MockBaseLOSValidator(self.elevation, 5, 1, [], 1)
        self.assertEqual(
            base_los_validator._passes_simple_checks(
                build_los_site_for_los_test(
                    2.5,
                    2.5,
                    10,
                    location_type=LocationType.ROOFTOP,
                    building_id=3,
                ),
                build_los_site_for_los_test(
                    2.5,
                    2.5,
                    9,
                    location_type=LocationType.ROOFTOP,
                    building_id=1,
                ),
            ),
            False,
        )

    def test_on_the_same_building(self) -> None:
        base_los_validator = MockBaseLOSValidator(self.elevation, 5, 1, [], 1)
        self.assertEqual(
            base_los_validator._on_the_same_building(
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
            True,
        )

    def test_out_of_distance_range(self) -> None:
        base_los_validator = MockBaseLOSValidator(self.elevation, 2, 1, [], 1)
        self.assertEqual(
            base_los_validator._los_out_of_distance_range(
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
                    building_id=2,
                ),
            ),
            True,
        )

    def test_intersects_with_exclusion_zone(self) -> None:
        base_los_validator = MockBaseLOSValidator(
            self.elevation, 5, 1, [Polygon([(1, 1), (2, 1), (2, 2), (1, 2)])], 1
        )
        self.assertEqual(
            base_los_validator._los_intersects_with_exclusion_zones(
                build_los_site_for_los_test(0.5, 0.5, 10),
                build_los_site_for_los_test(2.5, 2.5, 9),
            ),
            True,
        )

    def test_passes_simple_checks(self) -> None:
        base_los_validator = MockBaseLOSValidator(
            self.elevation, 5, 1, [Polygon([(4, 1), (5, 1), (5, 2), (4, 2)])], 1
        )
        self.assertEqual(
            base_los_validator._passes_simple_checks(
                build_los_site_for_los_test(0.5, 0.5, 10),
                build_los_site_for_los_test(2.5, 2.5, 9),
            ),
            True,
        )

    def test_get_four_corners_of_rectangle(self) -> None:
        base_los_validator = MockBaseLOSValidator(self.elevation, 5, 1, [], 1)
        a, b, c, d = base_los_validator._get_four_corners_of_rectangle(
            0.5, 7, 3, 3, 1
        )

        self.assertAlmostEqual(a[0], 1.34799830401)
        self.assertAlmostEqual(a[1], 7.52999894)
        self.assertAlmostEqual(b[0], -0.347998304005)
        self.assertAlmostEqual(b[1], 6.47000106)
        self.assertAlmostEqual(c[0], 3.84799830401)
        self.assertAlmostEqual(c[1], 3.52999894)
        self.assertAlmostEqual(d[0], 2.15200169599)
        self.assertAlmostEqual(d[1], 2.47000106)

    def test_get_four_corners_of_rectangle_x_alinged(self) -> None:
        base_los_validator = MockBaseLOSValidator(self.elevation, 5, 1, [], 1)
        a, b, c, d = base_los_validator._get_four_corners_of_rectangle(
            3, 7, 3, 3, 1
        )

        self.assertEqual(a[0], 4)
        self.assertEqual(a[1], 7)
        self.assertEqual(b[0], 2)
        self.assertEqual(b[1], 7)
        self.assertEqual(c[0], 4)
        self.assertEqual(c[1], 3)
        self.assertEqual(d[0], 2)
        self.assertEqual(d[1], 3)

    def test_get_four_corners_of_rectangle_y_alinged(self) -> None:
        base_los_validator = MockBaseLOSValidator(self.elevation, 5, 1, [], 1)
        a, b, c, d = base_los_validator._get_four_corners_of_rectangle(
            0.5, 3, 3, 3, 1
        )

        self.assertEqual(a[0], 0.5)
        self.assertEqual(a[1], 2)
        self.assertEqual(b[0], 0.5)
        self.assertEqual(b[1], 4)
        self.assertEqual(c[0], 3)
        self.assertEqual(c[1], 2)
        self.assertEqual(d[0], 3)
        self.assertEqual(d[1], 4)
