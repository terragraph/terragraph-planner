# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import unittest

import numpy as np
from osgeo import osr

from terragraph_planner.common.exceptions import DataException
from terragraph_planner.common.structs import UTMBoundingBox
from terragraph_planner.los.elevation import Elevation


class TestElevation(unittest.TestCase):
    def setUp(self) -> None:
        self.filter_func = lambda x, y: True
        test_utm_epsg = 32647
        self.spatial_reference = osr.SpatialReference()
        self.spatial_reference.ImportFromEPSG(test_utm_epsg)

    def test_set_resolution(self) -> None:
        data_matrix = np.arange(100).reshape(10, 10)
        geogrids = Elevation(
            data_matrix,
            UTMBoundingBox(10, 10, 0, 0),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=0.5,
            left_top_y=9.5,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        geogrids2 = Elevation(
            data_matrix,
            UTMBoundingBox(10, 10, 0, 0),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=0.5,
            left_top_y=9.5,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        geogrids.set_resolution(2, 2)
        self.assertEqual(geogrids.x_size, 6)
        self.assertEqual(geogrids.y_size, 6)
        for idx_y in range(geogrids.x_size):
            for idx_x in range(geogrids.y_size):
                utm_y = geogrids.left_top_y - idx_y * geogrids.y_resolution
                utm_x = geogrids.left_top_x + idx_x * geogrids.x_resolution
                self.assertEqual(
                    geogrids.get_value(utm_x, utm_y),
                    geogrids2.get_value(utm_x, utm_y),
                )

    def test_get_all_obstructions(self) -> None:
        geogrids = Elevation(
            data_matrix=np.arange(25).reshape(5, 5),
            utm_bounding_box=UTMBoundingBox(10, 20, 6, 16),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=6,
            left_top_y=20,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )

        obstructions = geogrids.get_all_obstructions(
            6, 16, 9, 20, self.filter_func
        )

        number_of_rows = 5
        obstructions_per_row = 4
        self.assertEqual(len(obstructions), 20)
        for i in range(number_of_rows):
            for j in range(obstructions_per_row):
                self.assertEqual(
                    obstructions[(i * obstructions_per_row) + j],
                    (6.0 + j, 20 - i, geogrids.data_matrix[i][j]),
                )

    def test_get_all_obstructions2(self) -> None:
        geogrids = Elevation(
            data_matrix=np.arange(25).reshape(5, 5),
            utm_bounding_box=UTMBoundingBox(10, 20, 6, 16),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=6,
            left_top_y=20,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )

        obstructions = geogrids.get_all_obstructions(
            9.4, 17.2, 8.4, 19.4, self.filter_func
        )

        self.assertEqual(len(obstructions), 6)
        self.assertEqual(obstructions[0], (8.0, 19.0, 7))
        self.assertEqual(obstructions[1], (9.0, 19.0, 8))
        self.assertEqual(obstructions[2], (8.0, 18.0, 12))
        self.assertEqual(obstructions[3], (9.0, 18.0, 13))
        self.assertEqual(obstructions[4], (8.0, 17.0, 17))
        self.assertEqual(obstructions[5], (9.0, 17.0, 18))

    def test_get_all_obstructions_x_aligned(self) -> None:
        geogrids = Elevation(
            data_matrix=np.arange(25).reshape(5, 5),
            utm_bounding_box=UTMBoundingBox(10, 20, 6, 16),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=6,
            left_top_y=20,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )

        obstructions = geogrids.get_all_obstructions(
            6, 18, 9, 18, self.filter_func
        )

        self.assertEqual(len(obstructions), 4)
        self.assertEqual(obstructions[0], (6.0, 18.0, 10))
        self.assertEqual(obstructions[1], (7.0, 18.0, 11))
        self.assertEqual(obstructions[2], (8.0, 18.0, 12))
        self.assertEqual(obstructions[3], (9.0, 18.0, 13))

    def test_get_all_obstructions_y_aligned(self) -> None:
        geogrids = Elevation(
            data_matrix=np.arange(25).reshape(5, 5),
            utm_bounding_box=UTMBoundingBox(10, 20, 6, 16),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=6,
            left_top_y=20,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )

        obstructions = geogrids.get_all_obstructions(
            8, 16, 8, 20, self.filter_func
        )

        self.assertEqual(len(obstructions), 5)
        self.assertEqual(obstructions[0], (8.0, 20.0, 2))
        self.assertEqual(obstructions[1], (8.0, 19.0, 7))
        self.assertEqual(obstructions[2], (8.0, 18.0, 12))
        self.assertEqual(obstructions[3], (8.0, 17.0, 17))
        self.assertEqual(obstructions[4], (8.0, 16.0, 22))

    def test_get_all_obstructions_within_bounds(self) -> None:
        geogrids = Elevation(
            data_matrix=np.arange(25).reshape(5, 5),
            utm_bounding_box=UTMBoundingBox(10, 20, 6, 16),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=6,
            left_top_y=20,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )

        obstructions = geogrids.get_all_obstructions(
            7, 26, 1, 19, self.filter_func
        )

        self.assertEqual(len(obstructions), 4)
        self.assertEqual(obstructions[0], (6.0, 20.0, 0))
        self.assertEqual(obstructions[1], (7.0, 20.0, 1))
        self.assertEqual(obstructions[2], (6.0, 19.0, 5))
        self.assertEqual(obstructions[3], (7.0, 19.0, 6))

    def test_get_value_list_within_bound(self) -> None:
        geogrids = Elevation(
            data_matrix=np.arange(25).reshape(5, 5),
            utm_bounding_box=UTMBoundingBox(5, 15, 0, 10),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=0.5,
            left_top_y=14.5,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        value_list = geogrids.get_value_list_within_bound(1.4, 11.6, 3.6, 14.4)
        self.assertEqual(len(value_list), 6)

    def test_get_value_matrix_within_bound(self) -> None:
        geogrids = Elevation(
            data_matrix=np.arange(25).reshape(5, 5),
            utm_bounding_box=UTMBoundingBox(5, 15, 0, 10),
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=0.5,
            left_top_y=14.5,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        value_matrix = geogrids.get_value_matrix_within_bound(
            1.4, 11.6, 3.6, 14.4
        )
        self.assertEqual(len(value_matrix), 2)
        self.assertEqual(len(value_matrix[0]), 3)

    def test_add_sub(self) -> None:
        utm_bounding_box = UTMBoundingBox(10, 10, 0, 0)
        geogrids1 = Elevation(
            data_matrix=np.arange(4).reshape(2, 2),
            utm_bounding_box=utm_bounding_box,
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=0,
            left_top_y=2,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        geogrids2 = Elevation(
            data_matrix=np.arange(4, 8).reshape(2, 2),
            utm_bounding_box=utm_bounding_box,
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=0,
            left_top_y=2,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        geogrids3 = Elevation(
            data_matrix=np.arange(8, 12).reshape(2, 2),
            utm_bounding_box=utm_bounding_box,
            x_resolution=1.0,
            y_resolution=1.0,
            left_top_x=1,
            left_top_y=3,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        geogrids4 = geogrids1 + geogrids2
        self.assertEqual(geogrids4.get_value(0, 2), 4)
        self.assertEqual(geogrids4.get_value(0, 1), 8)
        self.assertEqual(geogrids4.get_value(1, 2), 6)
        self.assertEqual(geogrids4.get_value(1, 1), 10)
        # metadata is different, raises GeoGridsException
        with self.assertRaises(DataException):
            geogrids1 + geogrids3
        geogrids5 = geogrids2 - geogrids1
        self.assertEqual(geogrids5.get_value(0, 2), 4)
        self.assertEqual(geogrids5.get_value(0, 1), 4)
        self.assertEqual(geogrids5.get_value(1, 2), 4)
        self.assertEqual(geogrids5.get_value(1, 1), 4)
