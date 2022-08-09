# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import List, Set

from osgeo.osr import SpatialReference

from terragraph_planner.common.exceptions import DataException

GDF_GEOMETRY_COLUMN = "geometry"
GDF_HEIGHT_COLUMN = "HEIGHT"


def has_crs_rule(
    spatial_reference: SpatialReference, role_str: str
) -> List[DataException]:
    # If there's no crs, AUTHORITY should be None
    if spatial_reference.GetAttrValue("AUTHORITY") is None:
        return [DataException(f"{role_str}: Has no projection information.")]
    return []


def vertical_crs_is_valid_if_present_rule(
    spatial_reference: SpatialReference,
    valid_unit_names: Set[str],
    role_str: str,
) -> List[DataException]:
    errors = []
    # Only support crs in wkt format to check vertical crs
    if spatial_reference.GetAttrValue("VERT_CS") is not None:
        vert_datum = spatial_reference.GetAttrValue("VERT_CS|VERT_DATUM")
        vert_unit = spatial_reference.GetAttrValue("VERT_CS|UNIT")
        vert_axis0 = spatial_reference.GetAttrValue("VERT_CS|AXIS")
        vert_axis1 = spatial_reference.GetAttrValue("VERT_CS|AXIS", 1)
        # Currently we only check if vert_datum is present,
        # more research is probably needed around this to know
        # which datums are valid
        if vert_datum is None:
            errors.append(
                DataException(
                    f"{role_str}: If vertical CRS is present, "
                    "vertical datum must be provided."
                )
            )
        if vert_unit is None or vert_unit not in valid_unit_names:
            errors.append(
                DataException(
                    f"{role_str}: If vertical CRS is present, "
                    f"vertical unit must be one of {valid_unit_names}"
                )
            )
        if (vert_axis0 is None or vert_axis0 != "up") and (
            vert_axis1 is None or vert_axis1 != "up"
        ):
            errors.append(
                DataException(
                    f"{role_str}: If vertical CRS is present, "
                    'vertical axis must be "up".'
                )
            )
    return errors
