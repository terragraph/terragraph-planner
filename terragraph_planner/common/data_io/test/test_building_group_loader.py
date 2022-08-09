# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
import shutil
import unittest
from unittest.mock import MagicMock, patch

from osgeo import osr
from shapely.geometry import Polygon

from terragraph_planner.common.constants import LAT_LON_EPSG
from terragraph_planner.common.data_io.building_group_loader import (
    BuildingGroupLoader,
)
from terragraph_planner.los.building import Building
from terragraph_planner.los.building_group import BuildingGroup
from terragraph_planner.los.test.helper import MockBuildingGroup

DATA_PATH = "terragraph_planner/common/data_io/test/test_data/"
MOCK_PATH_PREFIX = "terragraph_planner.common.data_io.building_group_loader"


class TestBuildingGroupLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = BuildingGroupLoader()

    def test_read_from_shapefile(self) -> None:
        building1 = Building(Polygon(((0, 0), (0, 1), (1, 1), (1, 0))))
        building2 = Building(Polygon(((2, 2), (4, 4), (5, 3))))
        sr = osr.SpatialReference()
        sr.ImportFromEPSG(LAT_LON_EPSG)
        multi_buildings1 = BuildingGroup([building1, building2], sr)
        multi_buildings2 = self.loader._read_from_shapefile(
            DATA_PATH + "test_buildings_loader.zip"
        )
        self.assertEqual(
            len(multi_buildings1.building_list),
            len(multi_buildings2.building_list),
        )
        for i in range(len(multi_buildings1.building_list)):
            self.assertEqual(
                multi_buildings1.building_list[i].polygon.wkt,
                multi_buildings2.building_list[i].polygon.wkt,
            )

    @patch(f"{MOCK_PATH_PREFIX}.extract_polygons")
    def test_read_from_kml(self, mock_extract_polygons: MagicMock) -> None:
        mock_extract_polygons.return_value = [
            Polygon([[1, 10], [2, 11], [10, 0], [11, 2]]),
            Polygon([[3, 4], [7, 8], [4, 3], [8, 7]]),
            Polygon([[5, 7], [7, 9], [7, 5], [9, 7]]),
        ]
        # This kml file is an original kml file got from ISPtoolbox
        # The location has been moved to Pacific Ocean for privacy
        multi_buildings = self.loader._read_from_kml(
            DATA_PATH + "test_single_layer_buildings.kml"
        )
        self.assertEqual(multi_buildings.building_count, 3)

    def test_write(self) -> None:
        building1 = Building(Polygon(((0, 0), (0, 1), (1, 1), (1, 0))))
        building2 = Building(Polygon(((2, 2), (4, 4), (5, 3))))
        sr = osr.SpatialReference()
        sr.ImportFromEPSG(LAT_LON_EPSG)
        buildings1 = BuildingGroup([building1, building2], sr)
        tempdir = self.loader.get_a_temp_dir()
        output_zip = os.path.join(tempdir, "buildings1.zip")
        self.loader.write(output_zip, buildings1)
        buildings2 = self.loader._read_from_shapefile(output_zip)
        self.assertEqual(
            len(buildings1.building_list), len(buildings2.building_list)
        )
        for i in range(len(buildings1.building_list)):
            self.assertEqual(
                buildings1.building_list[i].polygon.wkt,
                buildings2.building_list[i].polygon.wkt,
            )
        shutil.rmtree(tempdir)

    def test_validate(self) -> None:
        test_role = "TEST"
        self.loader.validate(MockBuildingGroup(), test_role)
        self.loader.validate_shp_file([])
        self.assertEqual(len(self.loader.errors), 2)

        # set crs
        self.loader.errors = []
        self.loader.validate(
            MockBuildingGroup(crs_epsg_code=LAT_LON_EPSG), test_role
        )
        self.loader.validate_shp_file([])
        self.assertEqual(len(self.loader.errors), 1)

        # test good file paths
        self.loader.errors = []
        self.loader.validate(
            MockBuildingGroup(
                crs_epsg_code=LAT_LON_EPSG,
            ),
            test_role,
        )
        self.loader.validate_shp_file(["my.shp", "my.shx"])
        self.assertEqual(len(self.loader.errors), 0)

        # test bad file paths
        self.loader.errors = []
        self.loader.validate(
            MockBuildingGroup(crs_epsg_code=LAT_LON_EPSG), test_role
        )
        self.loader.validate_shp_file(["my.shx"])
        self.assertEqual(len(self.loader.errors), 1)
