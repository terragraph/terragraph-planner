# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from terragraph_planner.common.configuration.enums import (
    SectorType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.exceptions import TopologyException
from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.test.helper import SampleSite


class TestSector(TestCase):
    def setUp(self) -> None:
        self.site1 = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(latitude=0.1, longitude=1.2),
        )
        self.site2 = SampleSite(
            site_type=SiteType.CN,
            location=GeoLocation(latitude=0.1, longitude=1.2),
        )

    def test_sector_id(self) -> None:
        sector1 = Sector(
            site=self.site1,
            node_id=0,
            position_in_node=0,
            status_type=StatusType.CANDIDATE,
            ant_azimuth=0,
        )
        sector2 = Sector(
            site=self.site2,
            node_id=0,
            position_in_node=0,
            status_type=StatusType.CANDIDATE,
            ant_azimuth=0,
        )
        self.assertNotEqual(sector1.sector_id, sector2.sector_id)
        sector3 = Sector(
            site=self.site1,
            node_id=2,
            position_in_node=0,
            status_type=StatusType.CANDIDATE,
            ant_azimuth=0,
        )
        self.assertNotEqual(sector1.sector_id, sector3.sector_id)
        sector4 = Sector(
            site=self.site1,
            node_id=0,
            position_in_node=2,
            status_type=StatusType.CANDIDATE,
            ant_azimuth=0,
        )
        self.assertNotEqual(sector1.sector_id, sector4.sector_id)

        with self.assertRaisesRegex(AttributeError, "can't set attribute"):
            sector1.sector_type = SectorType.CN  # pyre-ignore
        with self.assertRaisesRegex(AttributeError, "can't set attribute"):
            sector1.node_id = 2  # pyre-ignore
        with self.assertRaisesRegex(AttributeError, "can't set attribute"):
            sector1.position_in_node = 2  # pyre-ignore

    def test_status_type(self) -> None:
        error_msg1 = (
            "The sector status must be the same as site status if "
            "the site status is unreachable or unavailable."
        )
        error_msg2 = (
            "The sector status must be candidate, proposed or existing "
            "if the site status is active."
        )
        error_msg3 = f"Cannot change the sector status to/from {StatusType.immutable_status()}"
        with self.assertRaisesRegex(TopologyException, error_msg1):
            Sector(
                site=self.site1,
                node_id=0,
                position_in_node=0,
                status_type=StatusType.PROPOSED,
                ant_azimuth=0,
            )

        with self.assertRaisesRegex(TopologyException, error_msg2):
            self.site1.status_type = StatusType.PROPOSED
            Sector(
                site=self.site1,
                node_id=0,
                position_in_node=0,
                status_type=StatusType.UNREACHABLE,
                ant_azimuth=0,
            )

        self.site1.status_type = StatusType.CANDIDATE
        sector = Sector(
            site=self.site1,
            node_id=0,
            position_in_node=0,
            status_type=StatusType.CANDIDATE,
            ant_azimuth=0,
        )

        with self.assertRaisesRegex(TopologyException, error_msg1):
            sector.status_type = StatusType.PROPOSED

        with self.assertRaisesRegex(TopologyException, error_msg2):
            self.site1.status_type = StatusType.PROPOSED
            sector.status_type = StatusType.UNREACHABLE
        self.site1.status_type = StatusType.CANDIDATE

        with self.assertRaisesRegex(TopologyException, error_msg3):
            sector.status_type = StatusType.UNAVAILABLE
