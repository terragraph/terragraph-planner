# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

import numpy as np
from osgeo import osr
from shapely.geometry import Polygon

from terragraph_planner.common.configuration.constants import (
    DEFAULT_CARRIER_FREQUENCY,
    DEFAULT_LOS_CONFIDENCE_THRESHOLD,
)
from terragraph_planner.common.configuration.enums import LocationType
from terragraph_planner.common.structs import UTMBoundingBox
from terragraph_planner.los.elevation import Elevation
from terragraph_planner.los.ellipsoidal_los_validator import (
    EllipsoidalLOSValidator,
)
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

    def test_same_x_y_coordinate(self) -> None:
        los_validator = EllipsoidalLOSValidator(
            self.elevation,
            5,
            1,
            90,
            DEFAULT_CARRIER_FREQUENCY,
            [],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )
        self.assertEqual(
            los_validator.compute_confidence(
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
            0.0,
        )

    def test_on_the_same_building(self) -> None:
        los_validator = EllipsoidalLOSValidator(
            self.elevation,
            5,
            1,
            25,
            DEFAULT_CARRIER_FREQUENCY,
            [],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
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
        los_validator = EllipsoidalLOSValidator(
            self.elevation,
            2,
            1,
            25,
            DEFAULT_CARRIER_FREQUENCY,
            [],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 10),
                build_los_site_for_los_test(2.5, 2.5, 9),
            ),
            0.0,
        )

    def test_large_el_dev(self) -> None:
        los_validator = EllipsoidalLOSValidator(
            self.elevation,
            50,
            1,
            25,
            DEFAULT_CARRIER_FREQUENCY,
            [],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(2.5, 2.5, 20),
                build_los_site_for_los_test(6.5, 2.5, 10),
            ),
            0.0,
        )

    def test_intersects_with_exclusion_zone(self) -> None:
        los_validator = EllipsoidalLOSValidator(
            self.elevation,
            5,
            1,
            25,
            DEFAULT_CARRIER_FREQUENCY,
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

    def test_grid_within_fresnel_zone_and_higher_than_sites(self) -> None:
        los_validator = EllipsoidalLOSValidator(
            self.elevation,
            5,
            1,
            25,
            DEFAULT_CARRIER_FREQUENCY,
            [],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 1),
                build_los_site_for_los_test(2.5, 2.5, 2),
            ),
            0.0,
        )

    def test_clear_fresnel_zone(self) -> None:
        los_validator = EllipsoidalLOSValidator(
            self.elevation,
            5,
            1,
            25,
            DEFAULT_CARRIER_FREQUENCY,
            [],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.7, 0.5, 5.4),
                build_los_site_for_los_test(1.2, 1.8, 5.5),
            ),
            1.0,
        )
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.6, 0.5, 5.4),
                build_los_site_for_los_test(2.7, 1.5, 5.3),
            ),
            1.0,
        )

    def test_obstruction_below_ellipsoid_region(self) -> None:
        los_validator = EllipsoidalLOSValidator(
            self.elevation,
            5,
            1,
            25,
            DEFAULT_CARRIER_FREQUENCY,
            [],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 5.4),
                build_los_site_for_los_test(2.5, 2.5, 5.5),
            ),
            1.0,
        )
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 1.5, 5.4),
                build_los_site_for_los_test(2.5, 1.5, 5.1),
            ),
            1.0,
        )

    def test_obstruction_inside_ellipsoid_region(self) -> None:
        elevation = Elevation(
            np.array([[4, 2, 3], [2, 5.45, 1], [3, 2, 1]]),
            UTMBoundingBox(3, 3, 0, 0),
            1,
            1,
            0.5,
            2.5,
            self.spatial_reference,
            None,
        )
        los_validator = EllipsoidalLOSValidator(
            elevation,
            5,
            1,
            25,
            DEFAULT_CARRIER_FREQUENCY,
            [],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        # point at (1.5, 1.5, 5.45) is inside the ellipsoid
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 5.4),
                build_los_site_for_los_test(2.5, 2.5, 5.5),
            ),
            0.0,
        )

    def test_obstruction_inside_ellipsoid_region2(self) -> None:
        elevation = Elevation(
            np.array([[4, 1, 2, 6, 3], [2, 5.45, 2, 3, 1], [3, 5, 6, 2, 1]]),
            UTMBoundingBox(3, 3, 0, 0),
            0.5,
            1,
            0.5,
            2.5,
            self.spatial_reference,
            None,
        )
        los_validator = EllipsoidalLOSValidator(
            elevation,
            5,
            1,
            25,
            DEFAULT_CARRIER_FREQUENCY,
            [],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        # point at (1, 1, 5.45) is inside the ellipsoid
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 5.4),
                build_los_site_for_los_test(1.5, 2.5, 5.5),
            ),
            0.0,
        )

    def test_obstruction_above_ellipsoid_region(self) -> None:
        elevation = Elevation(
            np.array(
                [
                    [4, 2, 5, 6, 3],
                    [2, 3, 4, 7, 1],
                    [3, 4, 5, 2, 1],
                    [3, 3, 5, 2, 1],
                    [3, 4, 5, 2, 1],
                ]
            ),
            UTMBoundingBox(3, 3, 0, 0),
            0.5,
            0.5,
            0.5,
            2.5,
            self.spatial_reference,
            None,
        )
        los_validator = EllipsoidalLOSValidator(
            elevation,
            5,
            1,
            45,
            DEFAULT_CARRIER_FREQUENCY,
            [],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        # point at (2, 2, 7) is greater than the height of the ellipsoid
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 5.4),
                build_los_site_for_los_test(2.5, 2.5, 7.5),
            ),
            0.0,
        )

    def test_obstruction_above_ellipsoid_region2(self) -> None:
        elevation = Elevation(
            np.array(
                [
                    [4, 2, 5, 6, 3],
                    [2, 3, 4, 7, 1],
                    [3, 6.8, 5, 2, 1],
                    [3, 3, 5, 2, 1],
                    [3, 4, 5, 2, 1],
                ]
            ),
            UTMBoundingBox(3, 3, 0, 0),
            0.5,
            0.5,
            0.5,
            2.5,
            self.spatial_reference,
            None,
        )
        los_validator = EllipsoidalLOSValidator(
            elevation,
            5,
            1,
            45,
            DEFAULT_CARRIER_FREQUENCY,
            [],
            DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        )

        # point at (1.5, 1, 6.8) is greater than the height of the ellipsoid
        self.assertEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0.5, 0.5, 5.4),
                build_los_site_for_los_test(1.5, 2.5, 7.5),
            ),
            0.0,
        )

    def test_confidence_level_height_equal_to_midpoint(self) -> None:
        elevation = Elevation(
            np.array(
                [
                    [6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
                    [6, 6, 6, 6, 6, 6, 6, 5, 1, 6, 6],
                    [6, 6, 6, 5, 1, 5, 6, 6, 6, 6, 6],
                    [6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
                ]
            ),
            UTMBoundingBox(1, 1, 0, 0),
            0.1,
            0.1,
            0,
            0.3,
            self.spatial_reference,
            None,
        )
        los_validator = EllipsoidalLOSValidator(
            elevation, 5, 1, 25, DEFAULT_CARRIER_FREQUENCY, [], 0.6
        )

        # point at (0.5, 0.1, 5) is the closest obstruction that creates the smallest fresnel zone
        self.assertAlmostEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0, 0, 5),
                build_los_site_for_los_test(1, 0.25, 5),
            ),
            0.6759563171263228,
        )

    def test_confidence_level_height_above_midpoint(self) -> None:
        elevation = Elevation(
            np.array(
                [
                    [6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
                    [6, 9, 1, 1, 9, 6, 6, 6, 6, 6, 6],
                    [6, 6, 6, 6, 9, 1, 1, 1, 6, 6, 6],
                    [6, 6, 6, 6, 6, 6, 6, 6, 6, 1, 1],
                ]
            ),
            UTMBoundingBox(1, 1, 0, 0),
            0.1,
            0.1,
            0,
            0.3,
            self.spatial_reference,
            None,
        )
        los_validator = EllipsoidalLOSValidator(
            elevation, 5, 1, 75, DEFAULT_CARRIER_FREQUENCY, [], 0.6
        )

        # point at (0.1, 0.2, 9) is the closest obstruction that creates the smallest fresnel zone
        self.assertAlmostEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0, 0.25, 5),
                build_los_site_for_los_test(1, 0, 3),
            ),
            0.743430593011,
        )

    def test_confidence_level_height_below_midpoint(self) -> None:
        elevation = Elevation(
            np.array(
                [
                    [6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
                    [6, 6, 6, 6, 6, 6, 3.1, 1, 1, 2.30, 6],
                    [6, 6, 4.3, 1, 1, 1, 3.13, 6, 6, 6, 6],
                    [1, 1, 1, 6, 6, 6, 6, 6, 6, 6, 6],
                ]
            ),
            UTMBoundingBox(1, 1, 0, 0),
            0.1,
            0.1,
            0,
            0.3,
            self.spatial_reference,
            None,
        )
        los_validator = EllipsoidalLOSValidator(
            elevation, 5, 1, 75, DEFAULT_CARRIER_FREQUENCY, [], 0.6
        )

        # point at (0.9, 0.2, 2.3) is the closest obstruction that creates the smallest fresnel zone
        self.assertAlmostEqual(
            los_validator.compute_confidence(
                build_los_site_for_los_test(0, 0, 5),
                build_los_site_for_los_test(1, 0.25, 2),
            ),
            0.6580516,
        )
