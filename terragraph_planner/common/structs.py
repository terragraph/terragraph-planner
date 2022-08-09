# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from dataclasses import dataclass, field
from typing import Dict, List, NamedTuple, Optional

from terragraph_planner.common.configuration.enums import (
    LinkType,
    LocationType,
    SiteType,
    StatusType,
)

AntennaPatternData = Dict[str, List[List[float]]]
ScanPatternData = Dict[float, Dict[float, float]]


class CandidateLOS(NamedTuple):
    site1_idx: int
    site2_idx: int
    is_bidirectional: bool


class GeoPoint(NamedTuple):
    longitude: float
    latitude: float
    altitude: Optional[float] = None


class MCSMap(NamedTuple):
    mcs: int
    snr: float
    mbps: float
    tx_backoff: float = 0


class Point3D(NamedTuple):
    x: float
    y: float
    z: float


class UTMBoundingBox(NamedTuple):
    max_utm_x: int
    max_utm_y: int
    min_utm_x: int
    min_utm_y: int


class ValidLOS(NamedTuple):
    tx_site_idx: int
    rx_site_idx: int
    confidence: float


class RawSite(NamedTuple):
    """
    RawSite is used to store raw site data read from a KML or CSV file, and will be
    further processed, validated and constructed to topology Site.
    """

    site_type: SiteType
    status_type: StatusType
    device_sku: Optional[str]
    name: Optional[str]
    latitude: float
    longitude: float
    altitude: Optional[float]
    height: Optional[float]
    location_type: LocationType
    building_id: Optional[int]
    number_of_subscribers: Optional[int]


class RawLink(NamedTuple):
    """
    RawLink is used to store raw link data read from a KML or CSV file, and will be
    further processed, validated and constructed to topology Link.
    """

    link_type: LinkType
    status_type: StatusType
    confidence_level: Optional[float]
    tx_site_name: str
    tx_latitude: float
    tx_longitude: float
    rx_site_name: str
    rx_latitude: float
    rx_longitude: float


@dataclass
class LinkBudgetMeasurements:
    mcs_level: int
    rsl_dbm: float
    snr_dbm: float
    capacity: float
    tx_power: float
    # sinr_dbm is not in the __init__ of LinkBudgetMeasurements,
    # and is set to snr in __post_init__. Therefore, when a new
    # LinkBudgetMeasurements is constructed, it's equal to snr_dbm.
    # It may get updated when the interference gets considered.
    sinr_dbm: float = field(init=False)

    def __post_init__(self) -> None:
        self.sinr_dbm = self.snr_dbm
