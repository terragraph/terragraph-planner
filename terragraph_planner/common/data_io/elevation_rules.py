# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from datetime import datetime, timedelta
from typing import List, Set

from pyre_extensions import none_throws

from terragraph_planner.common.data_io.shared_rules import (
    has_crs_rule,
    vertical_crs_is_valid_if_present_rule,
)
from terragraph_planner.common.exceptions import DataException
from terragraph_planner.los.elevation import Elevation

YEARS_AGO = 20
DAYS_AGO = 0
EXPECTED_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"


class ElevationRules:
    def __init__(self, elevation: Elevation) -> None:
        self.elevation = elevation
        self.role = "GeoTIFF"

    def geogcs_has_enough_info_rule(self) -> List[DataException]:
        errors = []
        sr = self.elevation.spatial_reference

        # If there's no GEOGCS, this rule does not apply
        if sr.GetAttrValue("GEOGCS") is None:
            return []
        if sr.GetAttrValue("GEOGCS|DATUM") is None:
            errors.append(
                DataException(
                    f"{self.role}: GEOGCS must have datum.",
                )
            )
        if sr.GetAttrValue("GEOGCS|PRIMEM") is None:
            errors.append(
                DataException(
                    f"{self.role}: GEOGCS must have primem (Prime Meridian).",
                )
            )
        if (
            sr.GetAttrValue("GEOGCS|UNIT") is None
            or sr.GetAttrValue("GEOGCS|UNIT", 1) is None
        ):
            errors.append(DataException(f"{self.role}: GEOGCS must have unit."))
        return errors

    def has_crs_rule(self) -> List[DataException]:
        return has_crs_rule(self.elevation.spatial_reference, self.role)

    def has_recent_collection_time_rule(self) -> List[DataException]:
        if self.elevation.collection_time is not None:
            current_time = datetime.now()

            tifftag_datetime = none_throws(self.elevation.collection_time)
            try:
                collection_time = datetime.strptime(
                    tifftag_datetime, EXPECTED_DATETIME_FORMAT
                )
            except ValueError:
                return [
                    DataException(
                        f"{self.role}: The collection time does not fit the format"
                    )
                ]
            if current_time - collection_time > timedelta(
                days=365 * YEARS_AGO + DAYS_AGO
            ):
                return [
                    DataException(
                        f"{self.role}: The collection time cannot exceed 20 years in the past"
                    )
                ]
            if current_time < collection_time:
                return [
                    DataException(
                        f"{self.role}: The collection time shouldn't be in future"
                    )
                ]
        return []

    def has_valid_linear_unit_rule(
        self, linear_units: float, linear_units_names: Set[str]
    ) -> List[DataException]:
        sr = self.elevation.spatial_reference
        # If there's no PROJCS, this rule does not apply
        if sr.GetAttrValue("PROJCS") is None:
            return []
        errors = []
        linear_unit = sr.GetLinearUnits()
        if linear_unit != linear_units:
            errors.append(
                DataException(
                    f"{self.role}: Linear units must be{linear_units}."
                )
            )
        linear_unit_name = sr.GetLinearUnitsName()
        if linear_unit_name not in linear_units_names:
            errors.append(
                DataException(
                    f"{self.role}: Linear units name must be {linear_units_names}."
                )
            )
        return errors

    def has_valid_pixel_size_rule(
        self, min_pixel_size: float, max_pixel_size: float
    ) -> List[DataException]:
        sr = self.elevation.spatial_reference
        # There's no PROJCS, this rule does not apply
        if sr.GetAttrValue("PROJCS") is None:
            return []
        pixel_width = self.elevation.x_resolution
        pixel_height = self.elevation.y_resolution
        if not (
            min_pixel_size <= pixel_width <= max_pixel_size
            and min_pixel_size <= pixel_height <= max_pixel_size
        ):
            return [
                DataException(
                    f"{self.role}: Pixel size must lie within range "
                    f"[{min_pixel_size}, {max_pixel_size}]."
                )
            ]
        return []

    def vertical_crs_is_valid_if_present_rule(
        self, valid_unit_names: Set[str]
    ) -> List[DataException]:
        return vertical_crs_is_valid_if_present_rule(
            self.elevation.spatial_reference, valid_unit_names, self.role
        )
