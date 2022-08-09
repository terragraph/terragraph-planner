# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
from typing import List, Set

from terragraph_planner.common.data_io.shared_rules import (
    has_crs_rule,
    vertical_crs_is_valid_if_present_rule,
)
from terragraph_planner.common.exceptions import DataException
from terragraph_planner.los.building_group import BuildingGroup

# Mac OS has a mechanism called "resource fork", which will create a
# "__MACOSX" folder automatically when zip file is create in Mac OS,
# so we should consider zip file with "__MACOSX" folder at the top level as valid
MAC_RESOURCE_FORK_DIR = "__MACOSX"


class BuildingGroupRules:
    def __init__(self, building_group: BuildingGroup, role: str) -> None:
        self.building_group = building_group
        self.role = role

    def has_crs_rule(self) -> List[DataException]:
        return has_crs_rule(self.building_group.spatial_reference, self.role)

    def only_contains_certain_geometries_rule(
        self, expected_geometries: Set[str]
    ) -> List[DataException]:
        for building in self.building_group.building_list:
            if building.polygon.geom_type not in expected_geometries:
                return [
                    DataException(
                        f"{self.role} must only include geometries with "
                        f"following type(s): {expected_geometries}"
                    )
                ]
        return []

    def vertical_crs_is_valid_if_present_rule(
        self, valid_unit_names: Set[str]
    ) -> List[DataException]:
        return vertical_crs_is_valid_if_present_rule(
            self.building_group.spatial_reference, valid_unit_names, self.role
        )


class ZippedShpFileRules:
    def __init__(self, namelist: List[str]) -> None:
        self.namelist = namelist
        self.role = "Building SHP"

    def all_files_at_top_level_in_zip_rule(self) -> List[DataException]:
        for file_name in self.namelist:
            # Use "/" to check if the file locates at the top level
            # If the original file name contain "/", it would be replaced with ":" in the
            # namelist, and files are not allowed to have ":" in file.
            if (
                "/" in file_name
                and os.path.dirname(file_name) != MAC_RESOURCE_FORK_DIR
            ):
                return [
                    DataException(
                        f"{self.role}: All files in zip file should lie at the top level.",
                    )
                ]
        return []

    def zip_file_contains_exactly_one_shp_file(self) -> List[DataException]:
        shp_files = [
            os.path.basename(name)
            for name in self.namelist
            if not os.path.basename(name).startswith(".")  # ignore system files
            and os.path.splitext(name)[1]
            == ".shp"  # only include root shapefiles
        ]
        shp_file_number = len(shp_files)
        if shp_file_number != 1:
            return [
                DataException(
                    f"{self.role}: One .zip file can only have exactly one .shp file, "
                    f"but it has {shp_file_number}"
                )
            ]
        return []
