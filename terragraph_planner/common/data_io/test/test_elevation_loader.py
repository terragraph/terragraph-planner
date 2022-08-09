# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from osgeo import osr

from terragraph_planner.common.constants import LAT_LON_EPSG
from terragraph_planner.common.data_io.elevation_loader import ElevationLoader
from terragraph_planner.common.data_io.test.helper import MockSpatialReference
from terragraph_planner.common.structs import UTMBoundingBox
from terragraph_planner.los.elevation import Elevation
from terragraph_planner.los.test.helper import MockElevation

DATA_PATH = "terragraph_planner/common/data_io/test/test_data/"
MOCK_PATH_PREFIX = "terragraph_planner.common.data_io.elevation_loader."


class TestElevationLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.test_utm_epsg = 32647
        self.spatial_reference = osr.SpatialReference()
        self.spatial_reference.ImportFromEPSG(self.test_utm_epsg)
        self.loader = ElevationLoader()

    def test_read_from_utm_geotiff(self) -> None:
        elevations = self.loader._read_from_geotiff(
            [DATA_PATH + "test_utm.tif"],
            self.test_utm_epsg,
            UTMBoundingBox(647100, 599000, 647060, 598950),
        )
        self.assertEqual(elevations.crs_epsg_code, 32647)
        self.assertEqual(elevations.x_size, 40)
        self.assertEqual(elevations.y_size, 50)
        self.assertEqual(elevations.x_resolution, 1)
        self.assertEqual(elevations.y_resolution, 1)
        self.assertEqual(elevations.left_top_x, 647060.0)
        self.assertEqual(elevations.left_top_y, 599000.0)
        self.assertEqual(elevations.get_value(647099, 599000), 10)

    def test_read_from_lat_lon_geotiff(self) -> None:
        elevation = self.loader._read_from_geotiff(
            [DATA_PATH + "test_lat_lon.tif"],
            self.test_utm_epsg,
            UTMBoundingBox(647100, 599000, 647060, 598950),
        )
        self.assertEqual(elevation.crs_epsg_code, 32647)
        self.assertEqual(elevation.x_size, 40)
        self.assertEqual(elevation.y_size, 50)
        self.assertAlmostEqual(elevation.x_resolution, 1, places=3)
        self.assertAlmostEqual(elevation.y_resolution, 1, places=3)
        self.assertAlmostEqual(elevation.left_top_x, 647060.0, places=0)
        self.assertAlmostEqual(elevation.left_top_y, 599000.0, places=0)
        self.assertEqual(elevation.get_value(647099, 599000), 6)

    @patch(f"{MOCK_PATH_PREFIX}ElevationLoader._read_from_geotiff")
    def test_read(self, mock_read_from_geotiff: MagicMock) -> None:
        data_matrix = np.array([[5, 6], [7, 8], [9, 10]])
        utm_bounding_box = UTMBoundingBox(4, 3, 2, 0)
        elevation1 = Elevation(
            data_matrix,
            utm_bounding_box,
            x_resolution=1,
            y_resolution=1,
            left_top_x=2,
            left_top_y=2,
            spatial_reference=self.spatial_reference,
            collection_time=None,
        )
        mock_read_from_geotiff.return_value = elevation1
        elevation2 = self.loader.read(
            file_paths=["xxx.tif"],
            utm_epsg_code=111,
            utm_bounding_box=utm_bounding_box,
        )
        self.assertEqual(
            elevation1.data_matrix.all(), elevation2.data_matrix.all()
        )
        self.assertEqual(elevation1.x_resolution, elevation2.x_resolution)
        self.assertEqual(elevation1.crs_epsg_code, elevation2.crs_epsg_code)

    def test_write(self) -> None:
        data_matrix = np.array([[5, 6], [7, 8], [9, 10]])
        utm_bounding_box = UTMBoundingBox(4, 3, 2, 0)
        left_top_x = 2.5
        left_top_y = 2.5
        x_resolution = 1.0
        y_resolution = 1.0
        elevation1 = Elevation(
            data_matrix,
            utm_bounding_box,
            x_resolution,
            y_resolution,
            left_top_x,
            left_top_y,
            self.spatial_reference,
            None,
        )
        self.loader.write("test.tif", elevation1)
        elevation2 = self.loader._read_from_geotiff(
            ["test.tif"], self.test_utm_epsg, utm_bounding_box
        )
        os.remove("test.tif")
        self.assertEqual(
            elevation2.utm_bounding_box.max_utm_x, utm_bounding_box.max_utm_x
        )
        self.assertEqual(
            elevation2.utm_bounding_box.max_utm_y, utm_bounding_box.max_utm_y
        )
        self.assertEqual(
            elevation2.utm_bounding_box.min_utm_x, utm_bounding_box.min_utm_x
        )
        self.assertEqual(
            elevation2.utm_bounding_box.min_utm_y, utm_bounding_box.min_utm_y
        )
        self.assertEqual(elevation2.x_resolution, x_resolution)
        self.assertEqual(elevation2.y_resolution, y_resolution)
        self.assertEqual(elevation2.left_top_x, 1.5)
        self.assertEqual(elevation2.left_top_y, 3.5)
        self.assertEqual(
            elevation2.crs_epsg_code,
            int(self.spatial_reference.GetAuthorityCode(None)),
        )

    def test_read_from_geotiff(self) -> None:
        # "test_read_from_geotiff1.tif" is the left half of "test_utm.tif"
        # and "test_read_from_geotiff2.tif" is the right half of "test_utm.tif"
        geogrids1 = self.loader._read_from_geotiff(
            [
                DATA_PATH + "test_read_from_geotiff1.tif",
                DATA_PATH + "test_read_from_geotiff2.tif",
            ],
            self.test_utm_epsg,
            UTMBoundingBox(647100, 599000, 647060, 598950),
        )
        geogrids2 = self.loader._read_from_geotiff(
            [DATA_PATH + "test_utm.tif"],
            self.test_utm_epsg,
            UTMBoundingBox(647100, 599000, 647060, 598950),
        )
        self.assertEqual(geogrids1.left_top_x, geogrids2.left_top_x)
        self.assertEqual(geogrids1.left_top_y, geogrids2.left_top_y)
        self.assertEqual(geogrids1.x_resolution, geogrids2.x_resolution)
        self.assertEqual(geogrids1.y_resolution, geogrids2.y_resolution)
        self.assertEqual(geogrids1.x_size, geogrids2.x_size)
        self.assertEqual(geogrids1.y_size, geogrids2.y_size)
        list1 = geogrids1.get_data_as_list()
        list2 = geogrids2.get_data_as_list()
        for i in range(len(list1)):
            self.assertEqual(list1[i], list2[i])

    def test_validate(self) -> None:
        # test no validation errors
        self.loader.validate(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "GEOGCS": ["geogcs"],
                        "GEOGCS|DATUM": ["North_American_Datum_1983"],
                        "GEOGCS|PRIMEM": ["Greenwich"],
                        "GEOGCS|UNIT": ["degree", "0.0174532925199433"],
                        "AUTHORITY": [f"{LAT_LON_EPSG}"],
                        "PROJCS": ["projcs"],
                    },
                    linear_units=1,
                    linear_units_name="metre",
                ),
                x_resolution=1,
                y_resolution=1,
            )
        )
        self.assertEqual(len(self.loader.errors), 0)

        # test geogcs missing datum
        self.loader.errors = []
        self.loader.validate(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "GEOGCS": ["geogcs"],
                        "GEOGCS|PRIMEM": ["Greenwich"],
                        "GEOGCS|UNIT": ["degree", "0.0174532925199433"],
                        "AUTHORITY": [f"{LAT_LON_EPSG}"],
                        "PROJCS": ["projcs"],
                    },
                    linear_units=1,
                    linear_units_name="metre",
                ),
                x_resolution=1,
                y_resolution=1,
            )
        )
        self.assertEqual(len(self.loader.errors), 1)

        # test no projection
        self.loader.errors = []
        self.loader.validate(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "GEOGCS": ["geogcs"],
                        "GEOGCS|PRIMEM": ["Greenwich"],
                        "GEOGCS|UNIT": ["degree", "0.0174532925199433"],
                    },
                    linear_units=1,
                    linear_units_name="metre",
                ),
                x_resolution=1,
                y_resolution=1,
            )
        )
        self.assertEqual(len(self.loader.errors), 2)

        # test bad collection time
        self.loader.errors = []
        self.loader.validate(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "GEOGCS": ["geogcs"],
                        "GEOGCS|PRIMEM": ["Greenwich"],
                        "GEOGCS|UNIT": ["degree", "0.0174532925199433"],
                    },
                    linear_units=1,
                    linear_units_name="metre",
                ),
                x_resolution=1,
                y_resolution=1,
                collection_time="2000-01-01 00:00:00",
            )
        )
        self.assertEqual(len(self.loader.errors), 3)

        # test invalid liner unit name
        self.loader.errors = []
        self.loader.validate(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "PROJCS": ["projcs"],
                        "GEOGCS": ["geogcs"],
                        "GEOGCS|PRIMEM": ["Greenwich"],
                        "GEOGCS|UNIT": ["degree", "0.0174532925199433"],
                    },
                    linear_units=1,
                    linear_units_name="foot",
                ),
                x_resolution=1,
                y_resolution=1,
                collection_time="2000-01-01 00:00:00",
            )
        )
        self.assertEqual(len(self.loader.errors), 4)

        # test invalid pixel size
        self.loader.errors = []
        self.loader.validate(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "PROJCS": ["projcs"],
                        "GEOGCS": ["geogcs"],
                        "GEOGCS|PRIMEM": ["Greenwich"],
                        "GEOGCS|UNIT": ["degree", "0.0174532925199433"],
                    },
                    linear_units=1,
                    linear_units_name="foot",
                ),
                x_resolution=101,
                y_resolution=6,
                collection_time="2000-01-01 00:00:00",
            )
        )
        self.assertEqual(len(self.loader.errors), 5)
