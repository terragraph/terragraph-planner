# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
from typing import Optional, Tuple

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.enums import (
    LinkType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.constants import (
    FULL_ROTATION_ANGLE,
    STRAIGHT_ANGLE,
)
from terragraph_planner.common.exceptions import (
    TopologyException,
    planner_assert,
)
from terragraph_planner.common.geos import (
    bearing_in_degrees,
    haversine_distance,
)
from terragraph_planner.common.structs import LinkBudgetMeasurements
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.site import Site
from terragraph_planner.optimization.constants import UNASSIGNED_CHANNEL


class Link:
    def __init__(
        self,
        tx_site: Optional[Site] = None,
        rx_site: Optional[Site] = None,
        tx_sector: Optional[Sector] = None,
        rx_sector: Optional[Sector] = None,
        status_type: StatusType = StatusType.CANDIDATE,
        is_wireless: bool = True,
        confidence_level: Optional[float] = None,
    ) -> None:
        """
        The tx_site and rx_site are the key attributes, which impact the link_id and are read-only.
        Whenever you want to update the key attributes, please initialize a new Link instance.
        If tx/rx_sector is provided, then the tx/rx_site can be grabbed from them; otherwise, they
        will be verified for consistency.

        @param tx_site
        The transmitter site of the link.

        @param rx_site
        The receiver site of the link.

        @param tx_sector
        The transmitter sector of the link.

        @param
        The receiver sector of the link.

        @param status_type
        The status of the Link, which can be UNAVAILABLE, CANDIDATE, PROPOSED, EXISTING or UNREACHABLE.

        @param is_wireless
        A boolean indicating whether the link is wireless or not.

        @param confidence_level
        A float between [0, 1] to indicate how confident about whether there is a line-of-sight for
        wireless links.
        """
        if tx_site is None:
            planner_assert(
                tx_sector is not None,
                "A link's input sites and sectors cannot both be None",
                TopologyException,
            )
            self._tx_site: Site = none_throws(tx_sector).site
        else:
            self._tx_site = tx_site

        if rx_site is None:
            planner_assert(
                rx_sector is not None,
                "A link's input sites and sectors cannot both be None",
                TopologyException,
            )
            self._rx_site: Site = none_throws(rx_sector).site
        else:
            self._rx_site = rx_site

        planner_assert(
            self.tx_site.site_type != SiteType.CN,
            "A CN site cannot be the tx site of a link.",
            TopologyException,
        )

        self._link_id: str = Link.get_link_id_by_site_ids(
            self.tx_site.site_id, self.rx_site.site_id
        )

        if tx_sector is None and rx_sector is None:
            self.clear_sectors()
        elif tx_sector is None or rx_sector is None:
            raise TopologyException(
                "The link's sectors must both be set or None"
            )
        else:
            self.tx_sector = tx_sector
            self.rx_sector = rx_sector

        self.is_wireless = is_wireless

        self._status_type = status_type
        self._check_compatible_status(status_type)

        self.confidence_level = confidence_level
        self.link_budget = LinkBudgetMeasurements(
            mcs_level=0,
            rsl_dbm=-math.inf,
            snr_dbm=-math.inf,
            capacity=0.0,
            tx_power=-math.inf,
        )

        self._distance: Optional[float] = None
        self._tx_beam_azimuth: Optional[float] = None
        self._rx_beam_azimuth: Optional[float] = None

        self.is_redundant = False
        self.proposed_flow: float = 0
        self.utilization: float = 0
        self.breakdowns: int = 0

    @property
    def tx_site(self) -> Site:
        return self._tx_site

    @property
    def rx_site(self) -> Site:
        return self._rx_site

    @property
    def link_id(self) -> str:
        return self._link_id

    @property
    def status_type(self) -> StatusType:
        return self._status_type

    @property
    def tx_sector(self) -> Optional[Sector]:
        return self._tx_sector

    @property
    def rx_sector(self) -> Optional[Sector]:
        return self._rx_sector

    @tx_sector.setter
    def tx_sector(self, tx_sector: Sector) -> None:
        if tx_sector.site is not self.tx_site:
            raise TopologyException(
                "The link's tx sector's site does not match the link's tx site"
            )
        self._tx_sector = tx_sector

    @rx_sector.setter
    def rx_sector(self, rx_sector: Sector) -> None:
        if rx_sector.site is not self.rx_site:
            raise TopologyException(
                "The link's rx sector's site does not match the link's rx site"
            )
        self._rx_sector = rx_sector

    def clear_sectors(self) -> None:
        self._tx_sector = None
        self._rx_sector = None

    @status_type.setter
    def status_type(self, status_type: StatusType) -> None:
        planner_assert(
            len(
                {self._status_type, status_type} & StatusType.immutable_status()
            )
            == 0,
            f"Cannot change the link status to/from {StatusType.immutable_status()}.",
            TopologyException,
        )
        self._check_compatible_status(status_type)
        self._status_type = status_type

    @property
    def link_type(self) -> LinkType:
        """
        Infer link type if the input link type is not ethernet
        """
        if not self.is_wireless:
            return LinkType.ETHERNET
        if self._rx_site.site_type == SiteType.CN:
            return LinkType.WIRELESS_ACCESS
        return LinkType.WIRELESS_BACKHAUL

    @property
    def distance(self) -> float:
        if self._distance is None:
            # Convert to Python primitive float
            self._distance = float(
                haversine_distance(
                    self.tx_site.longitude,
                    self.tx_site.latitude,
                    self.rx_site.longitude,
                    self.rx_site.latitude,
                )
            )
            if (
                self.tx_site.altitude is not None
                and self.rx_site.altitude is not None
            ):
                self._distance = math.sqrt(
                    self._distance * self._distance
                    + (
                        none_throws(self.tx_site.altitude)
                        - none_throws(self.rx_site.altitude)
                    )
                    ** 2
                )
        return self._distance

    @property
    def tx_beam_azimuth(self) -> float:
        if self._tx_beam_azimuth is None:
            self._update_azimuth()
        return none_throws(self._tx_beam_azimuth)

    @property
    def rx_beam_azimuth(self) -> float:
        if self._rx_beam_azimuth is None:
            self._update_azimuth()
        return none_throws(self._rx_beam_azimuth)

    @property
    def tx_dev(self) -> Optional[float]:
        if self.link_type == LinkType.ETHERNET or self.tx_sector is None:
            return None
        tx_sector_az = none_throws(self.tx_sector).ant_azimuth
        tx_dev = abs(self.tx_beam_azimuth - tx_sector_az)
        return min(tx_dev, FULL_ROTATION_ANGLE - tx_dev)

    @property
    def rx_dev(self) -> Optional[float]:
        if self.link_type == LinkType.ETHERNET or self.rx_sector is None:
            return None
        rx_sector_az = none_throws(self.rx_sector).ant_azimuth
        rx_dev = abs(self.rx_beam_azimuth - rx_sector_az)
        return min(rx_dev, FULL_ROTATION_ANGLE - rx_dev)

    @property
    def el_dev(self) -> float:
        return (
            math.degrees(
                math.asin(
                    (self.rx_site.altitude - self.tx_site.altitude)
                    / self.distance
                )
            )
            if self.distance > 0
            and self.tx_site.altitude is not None
            and self.rx_site.altitude is not None
            else 0
        )

    @property
    def link_hash(self) -> str:
        site_hashes = [
            self.tx_site.site_hash + "_" + self.tx_site.site_type.to_string(),
            self.rx_site.site_hash + "_" + self.rx_site.site_type.to_string(),
        ]
        site_hashes.sort()
        return "-".join(site_hashes)

    @property
    def link_channel(self) -> int:
        if self.status_type in StatusType.active_status():
            if self.tx_sector and self.rx_sector:
                planner_assert(
                    self.tx_sector.channel == self.rx_sector.channel,
                    "Channels of the two sectors of a link should be the same.",
                    TopologyException,
                )
                return none_throws(self.tx_sector).channel
        return UNASSIGNED_CHANNEL

    @property
    def mcs_level(self) -> int:
        return self.link_budget.mcs_level

    @mcs_level.setter
    def mcs_level(self, mcs_level: int) -> None:
        self.link_budget.mcs_level = mcs_level

    @property
    def rsl_dbm(self) -> float:
        return self.link_budget.rsl_dbm

    @rsl_dbm.setter
    def rsl_dbm(self, rsl_dbm: float) -> None:
        self.link_budget.rsl_dbm = rsl_dbm

    @property
    def snr_dbm(self) -> float:
        return self.link_budget.snr_dbm

    @snr_dbm.setter
    def snr_dbm(self, snr_dbm: float) -> None:
        self.link_budget.snr_dbm = snr_dbm

    @property
    def capacity(self) -> float:
        return self.link_budget.capacity

    @capacity.setter
    def capacity(self, capacity: float) -> None:
        self.link_budget.capacity = capacity

    @property
    def tx_power(self) -> float:
        return self.link_budget.tx_power

    @tx_power.setter
    def tx_power(self, tx_power: float) -> None:
        self.link_budget.tx_power = tx_power

    @property
    def sinr_dbm(self) -> float:
        return self.link_budget.sinr_dbm

    @sinr_dbm.setter
    def sinr_dbm(self, sinr_dbm: float) -> None:
        self.link_budget.sinr_dbm = sinr_dbm

    @property
    def sorted_site_ids(self) -> Tuple[str, str]:
        if self.tx_site.site_id < self.rx_site.site_id:
            return self.tx_site.site_id, self.rx_site.site_id
        return self.rx_site.site_id, self.tx_site.site_id

    @classmethod
    def get_link_id_by_site_ids(self, tx_site_id: str, rx_site_id: str) -> str:
        return f"{tx_site_id}-{rx_site_id}"

    def _update_azimuth(self) -> None:
        self._tx_beam_azimuth = bearing_in_degrees(
            self.tx_site.longitude,
            self.tx_site.latitude,
            self.rx_site.longitude,
            self.rx_site.latitude,
        )
        self._rx_beam_azimuth = (
            none_throws(self._tx_beam_azimuth) + STRAIGHT_ANGLE
        ) % FULL_ROTATION_ANGLE

    def _check_compatible_status(self, status_type: StatusType) -> None:
        if status_type == StatusType.EXISTING:
            if (
                self._tx_site.status_type != StatusType.EXISTING
                or self._rx_site.status_type != StatusType.EXISTING
            ):
                raise TopologyException(
                    "The tx site and rx site of an existing link must be existing.",
                )
        if (
            self._tx_site.status_type == StatusType.UNAVAILABLE
            or self._rx_site.status_type == StatusType.UNAVAILABLE
        ):
            if status_type != StatusType.UNAVAILABLE:
                raise TopologyException(
                    "A link from/to an unavailable sites must be unavailable."
                )
        if (
            self._tx_site.status_type == StatusType.UNREACHABLE
            or self._rx_site.status_type == StatusType.UNREACHABLE
        ) and status_type != StatusType.UNREACHABLE:
            raise TopologyException(
                "The status of the link with an unreachable tx or rx site must be unreachable."
            )
        if (
            self._tx_site.status_type == StatusType.CANDIDATE
            or self._rx_site.status_type == StatusType.CANDIDATE
        ) and status_type in StatusType.active_status():
            raise TopologyException(
                "The status of the link with a candidate tx or rx site cannot be proposed or existing."
            )

    def is_out_of_sector(self) -> bool:
        return self.tx_sector is None or self.rx_sector is None
