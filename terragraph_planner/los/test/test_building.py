# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from osgeo import osr
from shapely.geometry import Polygon

from terragraph_planner.common.structs import UTMBoundingBox
from terragraph_planner.los.building import (
    Building,
    detect_corners_from_polygon_vertices,
)
from terragraph_planner.los.elevation import Elevation
from terragraph_planner.los.test.helper import MockElevation

MOCK_PATH_PREFIX = "terragraph_planner.los.building"


class TestBuilding(unittest.TestCase):
    def setUp(self) -> None:
        self.surface_elevation = MockElevation(uniform_value=1)
        test_utm_epsg = 32610
        self.spatial_reference = osr.SpatialReference()
        self.spatial_reference.ImportFromEPSG(test_utm_epsg)

    def test_detect_corners_without_max_corner_angle(self) -> None:
        coords = [(0, 0), (10, 0), (10, 10), (0, 10)]
        building = Building(Polygon(coords))
        corners = building.detect_corners(self.surface_elevation, None)
        for i in range(len(coords)):
            self.assertEqual(coords[i], corners[i][:2])
            self.assertEqual(corners[i][2], 1)

    @patch(f"{MOCK_PATH_PREFIX}.detect_corners_from_polygon_vertices")
    def test_detect_corners_with_max_corner_angle(
        self, mock_detect_corners_from_polygon_vertices: MagicMock
    ) -> None:
        mock_detect_corners_from_polygon_vertices.return_value = [
            (10.0, 0.0),
            (10.0, 10.0),
            (-5.0, 5.0),
        ]
        coords = [(0, 0), (10, 0), (10, 10), (0, 10), (-5, 5)]
        building = Building(Polygon(coords))
        # Set a max corner angle. The corner (0, 0) and (0, 10) with angle = 135 won't be detected
        corners = building.detect_corners(
            self.surface_elevation, max_corner_angle=120
        )
        self.assertSetEqual(
            {c[:2] for c in corners}, {coords[1], coords[2], coords[4]}
        )

    def test_detect_center_from_centroid(self) -> None:
        # A simple square whose center should be [4.5, 4.5]
        square = Polygon([(4, 4), (4, 5), (5, 5), (5, 4)])
        building = Building(square)
        center = building.detect_center(self.surface_elevation)
        self.assertEqual(center, (4.5, 4.5, 1))

    def test_detect_center_from_representative_point(self) -> None:
        # A polygon shaped like C, whose center [1.25, 2] does not
        # intersects with itself. Representative point [0.5, 2] should
        # be used as the center
        c_shape = Polygon(
            [(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (3, 3), (3, 4), (0, 4)]
        )
        building = Building(c_shape)
        center = building.detect_center(self.surface_elevation)
        self.assertEqual(center, (0.5, 2, 1))

    def test_get_all_site_candidate_locations(self) -> None:
        building = Building(Polygon([(4, 4), (4, 5), (5, 5), (5, 4)]))
        locations = building.detect_all_site_candidate_locations(
            self.surface_elevation, None, True, True, False
        )
        self.assertEqual(len(locations), 5)
        for location in locations:
            self.assertEqual(location[2], 1)

    def test_detect_highest(self) -> None:
        surface_elevation = Elevation(
            data_matrix=np.array(
                [
                    [1, 1, 2, 1, 1],
                    [1, 2, 3, 2, 1],
                    [2, 3, 4, 3, 2],
                    [1, 2, 3, 2, 1],
                    [1, 1, 2, 1, 1],
                ]
            ),
            utm_bounding_box=UTMBoundingBox(
                max_utm_x=5, max_utm_y=5, min_utm_x=0, min_utm_y=0
            ),
            x_resolution=1,
            y_resolution=1,
            left_top_x=0.5,
            left_top_y=4.5,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        # Highest point within the bound is contained by the polygon
        building1 = Building(
            Polygon([(2.5, 0.5), (4.5, 2.5), (2.5, 4.5), (0.5, 2.5)])
        )
        highest1 = building1.detect_highest(surface_elevation)
        self.assertEqual(highest1, (2.5, 2.5, 4))
        # Highest point within the bound is not contained by the polygon
        building2 = Building(
            Polygon([(3.5, 0.5), (4.5, 1.5), (3.5, 2.5), (2.5, 1.5)])
        )
        highest2 = building2.detect_highest(surface_elevation)
        self.assertEqual(highest2, (2.5, 1.5, 3))

    def test_find_the_good_corner_altitude(self) -> None:
        """
        Test find the good corner altitude when a corner of building polygon is actual
        on the ground in the surface elevation data. The following matrix is the surface
        elevation data, and 12 grids are circled into the building polygon but the left-top
        corner is on the ground level in the surface elevation data. Detect_corners method
        should find a good corner altitude for that left-top corner, and the altitudes of
        all corners should be 4.
        The building polygon is
        1  1 1 1 1
           -------
        1 |1 4 4 4|
        1 |4 5 5 4|
        1 |4 4 4 4|
           -------
        1  1 2 1 1
        """
        surface_elevation = Elevation(
            data_matrix=np.array(
                [
                    [1, 1, 1, 1, 1],
                    [1, 1, 4, 4, 4],
                    [1, 4, 5, 5, 4],
                    [1, 4, 4, 4, 4],
                    [1, 1, 2, 1, 1],
                ]
            ),
            utm_bounding_box=UTMBoundingBox(
                max_utm_x=5, max_utm_y=5, min_utm_x=0, min_utm_y=0
            ),
            x_resolution=1,
            y_resolution=1,
            left_top_x=0.5,
            left_top_y=4.5,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        building = Building(
            Polygon([(1.5, 3.5), (4.5, 3.5), (4.5, 1.5), (1.5, 1.5)])
        )
        corners = building.detect_corners(surface_elevation, None)
        self.assertEqual(len(corners), 4)
        for location in corners:
            self.assertEqual(location.z, 4)

    def test_detect_corners_from_polygon_vertices(self) -> None:
        """
                Pretend this is x=0
        y=100   +    |
                |    |
                |    |    +-----------+
                |    v   X            |
                |      X              |
                |    X                |
                |      X              |
                |        X            |
                |         +-----------+
                |
                |
                + +-----------------------------+ +
                x=0                                x=100
        """
        sideways_pentagon = Polygon(
            [(25, 25), (0, 50), (25, 75), (75, 75), (75, 25), (25, 25)]
        )
        sideways_pentagon_exterior_coords = list(
            sideways_pentagon.exterior.coords
        )

        # All corners should be detected
        corners = detect_corners_from_polygon_vertices(
            sideways_pentagon_exterior_coords, 135
        )
        self.assertEqual(len(corners), 5)

        # Top (really, left) of the pentagon should not be counted as a corner
        corners = detect_corners_from_polygon_vertices(
            sideways_pentagon_exterior_coords, 90
        )
        self.assertEqual(len(corners), 3)

        # No corners should be detected
        corners = detect_corners_from_polygon_vertices(
            sideways_pentagon_exterior_coords, 45
        )
        self.assertEqual(len(corners), 0)
