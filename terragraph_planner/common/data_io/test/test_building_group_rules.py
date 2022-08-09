# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import unittest

from shapely.geometry.point import Point
from shapely.geometry.polygon import Polygon

from terragraph_planner.common.constants import LAT_LON_EPSG
from terragraph_planner.common.data_io.building_group_rules import (
    BuildingGroupRules,
    ZippedShpFileRules,
)
from terragraph_planner.common.data_io.test.helper import MockSpatialReference
from terragraph_planner.los.building import Building
from terragraph_planner.los.test.helper import MockBuildingGroup


class TestBuildingGroupRules(unittest.TestCase):
    TEST_ROLE = "TEST"

    def test_has_crs_rule(self) -> None:
        rules = BuildingGroupRules(
            MockBuildingGroup(crs_epsg_code=LAT_LON_EPSG), self.TEST_ROLE
        )
        errors = rules.has_crs_rule()
        self.assertEqual(len(errors), 0)

        rules = BuildingGroupRules(MockBuildingGroup(), self.TEST_ROLE)
        errors = rules.has_crs_rule()
        self.assertEqual(len(errors), 1)

    def test_only_contains_certain_geometries_rule(self) -> None:
        # test only contains polygons
        rules = BuildingGroupRules(
            MockBuildingGroup(
                building_list=[
                    Building(Polygon([[0, 0], [0, 1], [1, 1]])),
                    Building(Polygon([[2, 2, 4], [2, 3, 4], [3, 3, 4]])),
                ]
            ),
            self.TEST_ROLE,
        )
        errors = rules.only_contains_certain_geometries_rule({"Polygon"})
        self.assertEqual(len(errors), 0)

        # test also contains points
        rules = BuildingGroupRules(
            MockBuildingGroup(
                building_list=[
                    Building(Polygon([[0, 0], [0, 1], [1, 1]])),
                    Building(Point([0, 0])),  # pyre-ignore
                ],
            ),
            self.TEST_ROLE,
        )
        errors = rules.only_contains_certain_geometries_rule({"Polygon"})
        self.assertEqual(len(errors), 1)

        # test contains empty polygon
        rules = BuildingGroupRules(
            MockBuildingGroup(
                building_list=[
                    Building(Polygon([[0, 0], [0, 1], [1, 1]])),
                    Building(Polygon()),
                ]
            ),
            self.TEST_ROLE,
        )
        errors = rules.only_contains_certain_geometries_rule({"Polygon"})
        self.assertEqual(len(errors), 1)

    def test_vertical_crs_is_valid_if_present_rule(
        self,
    ) -> None:
        VALID_UNIT_NAMES = {"metre", "meter", "m"}
        # test building group without vcs
        rules = BuildingGroupRules(
            MockBuildingGroup(spatial_reference=MockSpatialReference()),
            self.TEST_ROLE,
        )
        errors = rules.vertical_crs_is_valid_if_present_rule(VALID_UNIT_NAMES)
        self.assertEqual(len(errors), 0)

        # test spatial reference not from wkt
        rules = BuildingGroupRules(
            MockBuildingGroup(crs_epsg_code=LAT_LON_EPSG), self.TEST_ROLE
        )
        errors = rules.vertical_crs_is_valid_if_present_rule(VALID_UNIT_NAMES)
        self.assertEqual(len(errors), 0)


class TestZippedShpFileRules(unittest.TestCase):
    def test_all_files_at_top_level_in_zip_rule(self) -> None:
        rules = ZippedShpFileRules(["my.shp", "my.shx"])
        errors = rules.all_files_at_top_level_in_zip_rule()
        self.assertEqual(len(errors), 0)

        rules = ZippedShpFileRules(["my.shp", "my/my.shx"])
        errors = rules.all_files_at_top_level_in_zip_rule()
        self.assertEqual(len(errors), 1)

    def test_zip_file_contains_exactly_one_shp_file(self) -> None:
        # test has no shp files
        rules = ZippedShpFileRules(["my.shx"])
        errors = rules.zip_file_contains_exactly_one_shp_file()
        self.assertEqual(len(errors), 1)

        # test has exactly one shp file
        rules = ZippedShpFileRules(["my.shx", "my.shp"])
        errors = rules.zip_file_contains_exactly_one_shp_file()
        self.assertEqual(len(errors), 0)

        # test has two shp files
        rules = ZippedShpFileRules(["my.shx", "my.shp", "another.shp"])
        errors = rules.zip_file_contains_exactly_one_shp_file()
        self.assertEqual(len(errors), 1)
