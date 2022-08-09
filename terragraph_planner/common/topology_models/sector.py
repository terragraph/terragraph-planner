# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import TYPE_CHECKING

from terragraph_planner.common.configuration.enums import (
    SectorType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.exceptions import (
    TopologyException,
    planner_assert,
)
from terragraph_planner.optimization.constants import UNASSIGNED_CHANNEL

if TYPE_CHECKING:
    from terragraph_planner.common.topology_models.site import Site


class Sector:
    def __init__(
        self,
        site: "Site",
        node_id: int,
        position_in_node: int,
        ant_azimuth: float,
        status_type: StatusType = StatusType.CANDIDATE,
        channel: int = UNASSIGNED_CHANNEL,
    ) -> None:
        """
        The sector_type, site, node_id and position_in_node are the key attributes, which impact the
        sector_id and are read-only. Whenever you want to update the key attributes, please initialize
        a new Sector instance.

        @param site
        The site this Sector is mounted on.

        @param node_id
        The id (int from 0 to the number of nodes on the site - 1) of the node which contains this sector.

        @param position_in_node
        The position of the sector in the node, from 0 to the number of sectors in the node - 1.

        @param ant_azimuth
        Bearing of the sector's antenna

        @param status_type
        The status of the Sector, which can be UNAVAILABLE, CANDIDATE, PROPOSED, EXISTING or UNREACHABLE.
        """
        self._site = site
        self._sector_type: SectorType = (
            SectorType.CN
            if self._site.site_type == SiteType.CN
            else SectorType.DN
        )

        self._node_id = node_id
        self._position_in_node = position_in_node
        self._sector_id = f"{site.site_id}-{node_id}-{position_in_node}-{self._sector_type.name}"

        self.ant_azimuth = ant_azimuth

        self._status_type = status_type
        self._check_compatible_status_type(status_type)
        self.channel = channel

    @property
    def sector_type(self) -> SectorType:
        return self._sector_type

    @property
    def site(self) -> "Site":
        return self._site

    @property
    def node_id(self) -> int:
        return self._node_id

    @property
    def position_in_node(self) -> int:
        return self._position_in_node

    @property
    def sector_id(self) -> str:
        return self._sector_id

    @property
    def node_capex(self) -> float:
        return self._site.device.node_capex

    @property
    def status_type(self) -> StatusType:
        return self._status_type

    @status_type.setter
    def status_type(self, status_type: StatusType) -> None:
        planner_assert(
            len(
                {self._status_type, status_type} & StatusType.immutable_status()
            )
            == 0,
            f"Cannot change the sector status to/from {StatusType.immutable_status()}",
            TopologyException,
        )
        self._check_compatible_status_type(status_type)
        self._status_type = status_type

    def _check_compatible_status_type(self, status_type: StatusType) -> None:
        if self._site.status_type in StatusType.active_status():
            planner_assert(
                status_type == StatusType.CANDIDATE
                or status_type == StatusType.PROPOSED
                or status_type == StatusType.EXISTING,
                "The sector status must be candidate, proposed or existing if the site status is active.",
                TopologyException,
            )
        else:
            planner_assert(
                status_type == self._site.status_type,
                "The sector status must be the same as site status if the site "
                "status is unreachable or unavailable.",
                TopologyException,
            )
