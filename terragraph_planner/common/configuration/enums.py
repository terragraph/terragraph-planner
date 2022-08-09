# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
from enum import Enum
from typing import List, Set, Union


class EnumParser(Enum):
    def to_string(self) -> str:
        return self.name

    # To make the name case-insensitive
    @classmethod
    def from_string(cls, label: Union[str, int]) -> "EnumParser":
        if isinstance(label, str):
            return cls[label.upper()]
        elif isinstance(label, int):
            return cls(label)
        raise Exception(f"Invalid input: {label}")

    @classmethod
    def names(cls) -> List[str]:
        return [e.name for e in cls]


class DebugFile(EnumParser):
    PREPARED_TOPOLOGY = 1
    MIN_COST_TOPOLOGY = 2
    MAX_COVERAGE_TOPOLOGY = 3
    REDUNDANT_TOPOLOGY = 4
    MIN_INTERFERENCE_TOPOLOGY = 5
    OPTIMIZED_TOPOLOGY = 6
    POP_PROPOSAL_OPTIMIZATION = 7
    COST_OPTIMIZATION = 8
    COVERAGE_OPTIMIZATION = 9
    REDUNDANT_MIN_SHORTAGE_OPTIMIZATION = 10
    REDUNDANT_MIN_COST_OPTIMIZATION = 11
    INTERFERENCE_OPTIMIZATION = 12
    COMMON_BUFFER_OPTIMIZATION = 13


class DeviceType(EnumParser):
    CN = 1
    DN = 2


class LinkType(EnumParser):
    WIRELESS_BACKHAUL = 1
    WIRELESS_ACCESS = 2
    ETHERNET = 3

    def is_wireless(self) -> bool:
        return self != LinkType.ETHERNET


class LocationType(EnumParser):
    STREET_LEVEL = 1
    ROOFTOP = 2
    UNKNOWN = 3


class LoggerLevel(EnumParser):
    NOTSET = logging.NOTSET
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class OutputFile(EnumParser):
    CANDIDATE_TOPOLOGY = 1
    REPORTING_TOPOLOGY = 2
    LINK = 3
    SITE = 4
    SECTOR = 5
    METRICS = 6


class PolarityType(EnumParser):
    ODD = 1
    EVEN = 2
    UNASSIGNED = 3


class RedundancyLevel(EnumParser):
    NONE = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4


class SectorType(EnumParser):
    CN = 1  # Terragraph Client Node
    DN = 2  # Terragraph Distribution Node


class SiteType(EnumParser):
    CN = 1
    DN = 2
    POP = 3

    @classmethod
    def dist_site_types(cls) -> Set["SiteType"]:
        return {SiteType.POP, SiteType.DN}


class StatusType(EnumParser):
    PROPOSED = 1  # Components suggested to be activated by optimizer
    EXISTING = 2  # Components that already exist, user-input only
    CANDIDATE = 3  # Components that can potentially be used (in input topology) or non-selected components (in optimized output topology)
    UNAVAILABLE = 4  # Components that cannot be used, user-input only
    UNREACHABLE = 5  # Components that cannot be reached from any POP

    @classmethod
    def immutable_status(cls) -> Set["StatusType"]:
        """
        EXISTING and UNAVAILABLE are only from user input, so they cannot
        be changed from/to.
        """
        return {cls.EXISTING, cls.UNAVAILABLE}

    @classmethod
    def active_status(cls) -> Set["StatusType"]:
        return {cls.PROPOSED, cls.EXISTING}

    @classmethod
    def inactive_status(cls) -> Set["StatusType"]:
        return {cls.UNAVAILABLE, cls.UNREACHABLE}

    @classmethod
    def reachable_status(cls) -> Set["StatusType"]:
        return {cls.PROPOSED, cls.EXISTING, cls.CANDIDATE}


class TopologyRouting(EnumParser):
    SHORTEST_PATH = 1
    MCS_COST_PATH = 2
    DPA_PATH = 3
