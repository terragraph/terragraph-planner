# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import unittest
from datetime import datetime, timedelta

from terragraph_planner.common.constants import LAT_LON_EPSG
from terragraph_planner.common.data_io.elevation_rules import (
    EXPECTED_DATETIME_FORMAT,
    ElevationRules,
)
from terragraph_planner.common.data_io.test.helper import MockSpatialReference
from terragraph_planner.los.test.helper import MockElevation


class TestElevationRules(unittest.TestCase):
    def test_geogcs_has_enough_info_rule(self) -> None:
        # test has enough info
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "GEOGCS": ["geogcs"],
                        "GEOGCS|DATUM": ["North_American_Datum_1983"],
                        "GEOGCS|PRIMEM": ["Greenwich"],
                        "GEOGCS|UNIT": ["degree", "0.0174532925199433"],
                    },
                    linear_units=1,
                    linear_units_name="",
                )
            )
        )
        errors = rules.geogcs_has_enough_info_rule()
        self.assertEqual(len(errors), 0)

        # test missing datum
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "GEOGCS": ["geogcs"],
                        "GEOGCS|PRIMEM": ["Greenwich"],
                        "GEOGCS|UNIT": ["degree", "0.0174532925199433"],
                    },
                    linear_units=1,
                    linear_units_name="",
                )
            )
        )
        errors = rules.geogcs_has_enough_info_rule()
        self.assertEqual(len(errors), 1)

        # test missing primem
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "GEOGCS": ["geogcs"],
                        "GEOGCS|DATUM": ["North_American_Datum_1983"],
                        "GEOGCS|UNIT": ["degree", "0.0174532925199433"],
                    },
                    linear_units=1,
                    linear_units_name="",
                )
            )
        )
        errors = rules.geogcs_has_enough_info_rule()
        self.assertEqual(len(errors), 1)

        # test missing units
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "GEOGCS": ["geogcs"],
                        "GEOGCS|DATUM": ["North_American_Datum_1983"],
                        "GEOGCS|PRIMEM": ["Greenwich"],
                    },
                    linear_units=1,
                    linear_units_name="",
                )
            )
        )
        errors = rules.geogcs_has_enough_info_rule()
        self.assertEqual(len(errors), 1)

        # test missing multiple info
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "GEOGCS": ["geogcs"],
                        "GEOGCS|DATUM": ["North_American_Datum_1983"],
                    },
                    linear_units=1,
                    linear_units_name="",
                )
            )
        )
        errors = rules.geogcs_has_enough_info_rule()
        self.assertEqual(len(errors), 2)

        # test has no info
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"GEOGCS": ["geogcs"]},
                    linear_units=1,
                    linear_units_name="",
                )
            )
        )
        errors = rules.geogcs_has_enough_info_rule()
        self.assertEqual(len(errors), 3)

    def test_has_projection_rule(self) -> None:
        # test has valid projection
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"AUTHORITY": [f"{LAT_LON_EPSG}"]},
                    linear_units=1,
                    linear_units_name="",
                )
            )
        )
        errors = rules.has_crs_rule()
        self.assertEqual(len(errors), 0)

        # test has no projection
        rules = ElevationRules(MockElevation())
        errors = rules.has_crs_rule()
        self.assertEqual(len(errors), 1)

    def test_has_recent_collection_time_rule(self) -> None:
        def get_valid_datetime_str(days_delta: int) -> str:
            return datetime.strftime(
                datetime.now() + timedelta(days=days_delta),
                EXPECTED_DATETIME_FORMAT,
            )

        # test no date time
        rules = ElevationRules(MockElevation())
        errors = rules.has_recent_collection_time_rule()
        self.assertEqual(len(errors), 0)

        # test wrong date time format
        rules = ElevationRules(
            MockElevation(collection_time="2000-01-01 00:00:00")
        )
        errors = rules.has_recent_collection_time_rule()
        self.assertEqual(len(errors), 1)

        # test date time not recent enough
        rules = ElevationRules(
            MockElevation(collection_time=get_valid_datetime_str(-20 * 365 - 1))
        )
        errors = rules.has_recent_collection_time_rule()
        self.assertEqual(len(errors), 1)

        # test date time is recent
        rules = ElevationRules(
            MockElevation(collection_time=get_valid_datetime_str(-20 * 365 + 1))
        )
        errors = rules.has_recent_collection_time_rule()
        self.assertEqual(len(errors), 0)

        # test future date time
        rules = ElevationRules(
            MockElevation(collection_time=get_valid_datetime_str(1))
        )
        errors = rules.has_recent_collection_time_rule()
        self.assertEqual(len(errors), 1)

    def test_has_valid_linear_unit_rule(self) -> None:
        # test valid liner unit and name
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"PROJCS": ["projcs"]},
                    linear_units=1.0,
                    linear_units_name="metre",
                )
            )
        )
        errors = rules.has_valid_linear_unit_rule(1.0, {"metre", "meter"})
        self.assertEqual(len(errors), 0)

        # test invalid liner unit name "foot"
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"PROJCS": ["projcs"]},
                    linear_units=1.0,
                    linear_units_name="foot",
                )
            )
        )
        errors = rules.has_valid_linear_unit_rule(1.0, {"metre", "meter"})
        self.assertEqual(len(errors), 1)

        # test invalid liner units
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"PROJCS": ["projcs"]},
                    linear_units=2.0,
                    linear_units_name="foot",
                )
            )
        )
        errors = rules.has_valid_linear_unit_rule(1.0, {"metre", "meter"})
        self.assertEqual(len(errors), 2)

        # test case insensitive
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"PROJCS": ["projcs"]},
                    linear_units=1.0,
                    linear_units_name="Metre",
                )
            )
        )
        errors = rules.has_valid_linear_unit_rule(1.0, {"metre", "meter"})
        self.assertEqual(len(errors), 0)

    def test_has_valid_pixel_size_rule(self) -> None:
        # test valid pixel size
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"PROJCS": ["projcs"]},
                    linear_units=1,
                    linear_units_name="",
                ),
            )
        )
        errors = rules.has_valid_pixel_size_rule(0.5, 5.0)
        self.assertEqual(len(errors), 0)

        # test minimum pixel size
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"PROJCS": ["projcs"]},
                    linear_units=1,
                    linear_units_name="",
                ),
                x_resolution=0.5,
                y_resolution=0.5,
            )
        )
        errors = rules.has_valid_pixel_size_rule(0.5, 5.0)
        self.assertEqual(len(errors), 0)

        # test maximum pixel size
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"PROJCS": ["projcs"]},
                    linear_units=1,
                    linear_units_name="",
                ),
                x_resolution=5,
                y_resolution=5,
            )
        )
        errors = rules.has_valid_pixel_size_rule(0.5, 5.0)
        self.assertEqual(len(errors), 0)

        # test too small pixel size
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"PROJCS": ["projcs"]},
                    linear_units=1,
                    linear_units_name="",
                ),
                x_resolution=0.3,
                y_resolution=0.3,
            )
        )
        errors = rules.has_valid_pixel_size_rule(0.5, 5.0)
        self.assertEqual(len(errors), 1)

        # test too large pixel size
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"PROJCS": ["projcs"]},
                    linear_units=1,
                    linear_units_name="",
                ),
                x_resolution=6,
                y_resolution=6,
            )
        )
        errors = rules.has_valid_pixel_size_rule(0.5, 5.0)
        self.assertEqual(len(errors), 1)

        # test non square pixel size
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"PROJCS": ["projcs"]},
                    linear_units=1,
                    linear_units_name="",
                ),
                x_resolution=0.5,
                y_resolution=0.3,
            )
        )
        errors = rules.has_valid_pixel_size_rule(0.5, 5.0)
        self.assertEqual(len(errors), 1)

        # test non square pixel size
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={"PROJCS": ["projcs"]},
                    linear_units=1,
                    linear_units_name="",
                ),
                x_resolution=0.5,
                y_resolution=1,
            )
        )
        errors = rules.has_valid_pixel_size_rule(0.5, 5.0)
        self.assertEqual(len(errors), 0)

    def test_vertical_crs_is_valid_if_present_rule(self) -> None:
        rules = ElevationRules(MockElevation())
        errors = rules.vertical_crs_is_valid_if_present_rule(
            {"metre", "meter", "m"}
        )
        self.assertEqual(len(errors), 0)

        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "VERT_CS": ["EGM96 geoid height"],
                        "VERT_CS|VERT_DATUM": ["EGM96 geoid"],
                        "VERT_CS|UNIT": ["metre"],
                        "VERT_CS|AXIS": ["Up"],
                    }
                )
            )
        )
        errors = rules.vertical_crs_is_valid_if_present_rule(
            {"metre", "meter", "m"}
        )
        self.assertEqual(len(errors), 0)

        # test mssing vert datum
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "VERT_CS": ["EGM96 geoid height"],
                        "VERT_CS|UNIT": ["metre"],
                        "VERT_CS|AXIS": ["Up"],
                    }
                )
            )
        )
        errors = rules.vertical_crs_is_valid_if_present_rule(
            {"metre", "meter", "m"}
        )
        self.assertEqual(len(errors), 1)

        # test mssing vert unit
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "VERT_CS": ["EGM96 geoid height"],
                        "VERT_CS|VERT_DATUM": ["EGM96 geoid"],
                        "VERT_CS|AXIS": ["Up"],
                    }
                )
            )
        )
        errors = rules.vertical_crs_is_valid_if_present_rule(
            {"metre", "meter", "m"}
        )
        self.assertEqual(len(errors), 1)

        # test invalid vert unit
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "VERT_CS": ["EGM96 geoid height"],
                        "VERT_CS|UNIT": ["foot"],
                        "VERT_CS|VERT_DATUM": ["EGM96 geoid"],
                        "VERT_CS|AXIS": ["Up"],
                    }
                )
            )
        )
        errors = rules.vertical_crs_is_valid_if_present_rule(
            {"metre", "meter", "m"}
        )
        self.assertEqual(len(errors), 1)

        # test missing vert axis
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "VERT_CS": ["EGM96 geoid height"],
                        "VERT_CS|UNIT": ["m"],
                        "VERT_CS|VERT_DATUM": ["EGM96 geoid"],
                    }
                )
            )
        )
        errors = rules.vertical_crs_is_valid_if_present_rule(
            {"metre", "meter", "m"}
        )
        self.assertEqual(len(errors), 1)

        # test invalid vert axis
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "VERT_CS": ["EGM96 geoid height"],
                        "VERT_CS|UNIT": ["m"],
                        "VERT_CS|VERT_DATUM": ["EGM96 geoid"],
                        "VERT_CS|AXIS": ["down"],
                    }
                )
            )
        )
        errors = rules.vertical_crs_is_valid_if_present_rule(
            {"metre", "meter", "m"}
        )
        self.assertEqual(len(errors), 1)

        # test multiple errors
        rules = ElevationRules(
            MockElevation(
                spatial_reference=MockSpatialReference(
                    attr_dict={
                        "VERT_CS": ["EGM96 geoid height"],
                        "VERT_CS|UNIT": ["m"],
                    }
                )
            )
        )
        errors = rules.vertical_crs_is_valid_if_present_rule(
            {"metre", "meter", "m"}
        )
        self.assertEqual(len(errors), 2)
