# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import unittest

from terragraph_planner.common.configuration.enums import (
    DeviceType,
    RedundancyLevel,
)


class TestEnums(unittest.TestCase):
    def test_enum_parser_to_dict(self) -> None:
        self.assertEqual(DeviceType.DN.to_string(), "DN")
        self.assertEqual(RedundancyLevel.LOW.to_string(), "LOW")

    def test_enum_parser_from_string(self) -> None:
        self.assertEqual(DeviceType.from_string("DN"), DeviceType.DN)
        # Test case-insensitive
        self.assertEqual(
            RedundancyLevel.from_string("low"), RedundancyLevel.LOW
        )

        self.assertEqual(DeviceType.from_string(1), DeviceType.CN)
        self.assertEqual(RedundancyLevel.from_string(1), RedundancyLevel.NONE)

    def test_enum_names_list(self) -> None:
        self.assertEqual(
            RedundancyLevel.names(),
            ["NONE", "LOW", "MEDIUM", "HIGH"],
        )
        self.assertEqual(DeviceType.names(), ["CN", "DN"])
