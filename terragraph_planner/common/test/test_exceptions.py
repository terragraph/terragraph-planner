# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from terragraph_planner.common.exceptions import (
    ConfigException,
    LOSException,
    PlannerException,
    planner_assert,
)


class TestExceptions(TestCase):
    def test_raise_exceptions(self) -> None:
        with self.assertRaises(ConfigException):
            planner_assert(
                False, "Test catching the exact exception.", ConfigException
            )

        with self.assertRaises(PlannerException):
            planner_assert(
                False, "Test catching the base exception.", ConfigException
            )

        try:
            planner_assert(
                False, "Test missing the exception.", ConfigException
            )
        except LOSException:
            self.assertTrue(False)
        except Exception:
            self.assertTrue(True)
