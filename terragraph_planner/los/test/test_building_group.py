# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
import unittest
from unittest.mock import MagicMock

import numpy as np
from osgeo import osr
from shapely import ops
from shapely.geometry import Polygon

from terragraph_planner.common.geos import TransformerLib, lat_lon_to_utm_epsg
from terragraph_planner.common.structs import UTMBoundingBox
from terragraph_planner.los.building import Building
from terragraph_planner.los.building_group import BuildingGroup
from terragraph_planner.los.elevation import Elevation
from terragraph_planner.los.test.helper import MockElevation


class TestBuildingGroup(unittest.TestCase):
    def setUp(self) -> None:
        self.spatial_reference1 = osr.SpatialReference()
        self.spatial_reference1.ImportFromEPSG(4326)

        self.spatial_reference2 = osr.SpatialReference()
        self.spatial_reference2.ImportFromEPSG(32631)

    def test_preprocess(self) -> None:
        # Building3.geom should be cut into geometry with coords2 as exterior by boundary
        # Building2 should be filetered out by selection
        coords1 = [(0.0, 0.0), (0.0, 0.0001), (0.0001, 0.0001), (0.0001, 0.0)]
        building1 = Building(Polygon(coords1))
        building2 = Building(
            Polygon(((0.0002, 0.0002), (0.0004, 0.0004), (0.0005, 0.0003)))
        )
        building3 = Building(
            Polygon(
                (
                    (0.0009, 0.0009),
                    (0.0011, 0.0009),
                    (0.0011, 0.0011),
                    (0.0009, 0.0011),
                )
            )
        )
        coords2 = [
            (0.001, 0.0009),
            (0.0009, 0.0009),
            (0.0009, 0.001),
            (0.001, 0.001),
        ]
        buildings = BuildingGroup(
            [building1, building2, building3],
            spatial_reference=self.spatial_reference1,
        )
        ll_boundary_polygon = Polygon(
            [[0.0, 0.0], [0.001, 0.0], [0.001, 0.001], [0.0, 0.001]]
        )
        utm_epsg_code = lat_lon_to_utm_epsg(
            ll_boundary_polygon.centroid.y, ll_boundary_polygon.centroid.x
        )
        select_polygons = [
            Polygon(
                [[0.0, 0.0], [0.0002, 0.0], [0.0002, 0.0002], [0.0, 0.0002]]
            ),
            Polygon(
                [
                    [0.0009, 0.0009],
                    [0.001, 0.0009],
                    [0.001, 0.001],
                    [0.0009, 0.001],
                ]
            ),
        ]
        buildings.preprocess(
            ll_boundary_polygon, utm_epsg_code, select_polygons
        )
        self.assertEqual(len(buildings.building_list), 2)
        transformer = TransformerLib.get_tranformer(
            lat_lon_to_utm_epsg(0.001, 0.001), 4326
        )
        coords3 = list(
            ops.transform(
                transformer.transform, buildings.building_list[0].polygon
            ).exterior.coords
        )
        coords4 = list(
            ops.transform(
                transformer.transform, buildings.building_list[1].polygon
            ).exterior.coords
        )
        for i in range(4):
            self.assertAlmostEqual(coords1[i][0], coords3[i][0], places=4)
            self.assertAlmostEqual(coords1[i][1], coords3[i][1], places=4)
            self.assertAlmostEqual(coords2[i][0], coords4[i][0], places=4)
            self.assertAlmostEqual(coords2[i][1], coords4[i][1], places=4)

    def test_detect_site_candidates(self) -> None:
        building1 = Building(Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]))
        building2 = Building(Polygon([(20, 20), (40, 20), (30, 35)]))
        building3 = Building(Polygon([(20, 10), (25, 10), (25, 5), (20, 5)]))
        sr = MagicMock()
        sr.GetAuthorityCode.return_value = 32610
        buildings = BuildingGroup([building1, building2, building3], sr)
        surface_elevation = MockElevation(uniform_value=1)
        candidate_sites1 = buildings.detect_site_candidates(
            surface_elevation=surface_elevation,
            site_height_above_rooftop=2,
            max_corner_angle=None,
            detect_center=True,
            detect_corners=True,
            detect_highest=False,
        )
        # 1 center and 3 corners are detected per building
        self.assertEqual(len(candidate_sites1), 12)

    def test_filter_small_polygons_in_preprocess(self) -> None:
        # area of building1 = 25 < 50, so building1 will be filter out
        coords1 = [(0, 0), (5, 0), (5, 5), (0, 5)]
        building1 = Building(Polygon(coords1))
        # area of building2 = 100 > 50
        coords2 = [(10, 10), (10, 20), (20, 20), (20, 10)]
        building2 = Building(Polygon(coords2))
        # area of building3 = 400 > 50
        coords3 = [(20, 20), (40, 20), (40, 40), (20, 40)]
        building3 = Building(Polygon(coords3))
        buildings = BuildingGroup(
            [building1, building2, building3],
            spatial_reference=self.spatial_reference2,
        )
        boundary_polygon = Polygon([[-2, 0], [-2, 1], [1, -1], [0, -1]])
        buildings.preprocess(boundary_polygon, 32631, None)
        self.assertEqual(buildings.building_count, 2)
        output_coords1 = list(
            buildings.building_list[0].polygon.exterior.coords
        )
        output_coords2 = list(
            buildings.building_list[1].polygon.exterior.coords
        )
        for i in range(4):
            self.assertAlmostEqual(
                coords2[i][0], output_coords1[i][0], places=4
            )
            self.assertAlmostEqual(
                coords2[i][1], output_coords1[i][1], places=4
            )
            self.assertAlmostEqual(
                coords3[i][0], output_coords2[i][0], places=4
            )
            self.assertAlmostEqual(
                coords3[i][1], output_coords2[i][1], places=4
            )

    def test_to_dhm(self) -> None:
        coords1 = [(0.5, 0.5), (2.5, 0.5), (2.5, 2.5), (0.5, 2.5)]
        building1 = Building(Polygon(coords1))
        coords2 = [(1.5, 3.5), (3.5, 3.5), (3.5, 1.5), (1.5, 1.5)]
        building2 = Building(Polygon(coords2))
        buildings = BuildingGroup(
            [building1, building2], spatial_reference=self.spatial_reference2
        )
        dtm = Elevation(
            np.zeros((5, 5)),
            UTMBoundingBox(5, 5, 0, 0),
            x_resolution=1,
            y_resolution=1,
            left_top_x=0.5,
            left_top_y=4.5,
            spatial_reference=self.spatial_reference2,
            collection_time=None,
        )
        dhm = buildings.to_dhm(dtm, 3.8)
        expected_height_matrix = np.array(
            [
                [0, 0, 0, 0, 0],
                [0, 3.8, 3.8, 3.8, 0],
                [3.8, 3.8, 3.8, 3.8, 0],
                [3.8, 3.8, 3.8, 3.8, 0],
                [3.8, 3.8, 3.8, 0, 0],
            ],
            dtype=np.float32,
        )
        self.assertEqual(np.sum(expected_height_matrix == dhm.data_matrix), 25)
