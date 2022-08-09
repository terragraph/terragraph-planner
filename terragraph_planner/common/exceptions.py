# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import Set, Type


class PlannerException(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class GeoSystemException(PlannerException):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class TopologyException(PlannerException):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class ConfigException(PlannerException):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class DataException(PlannerException):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class LOSException(PlannerException):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class OptimizerException(PlannerException):
    def __init__(self, message: str) -> None:
        super().__init__(message)


def planner_assert(
    condition: bool,
    message: str = "",
    exception_type: Type[PlannerException] = PlannerException,
) -> None:
    if not condition:
        raise exception_type(message)


def assert_file_extension(
    file_name: str, expected_ext: Set[str], file_role: str
) -> None:
    ext = file_name.split(".")[-1].casefold()
    planner_assert(
        ext in expected_ext,
        f"{file_role} must have {expected_ext} extension.",
        DataException,
    )
