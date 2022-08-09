# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.enums import SiteType, StatusType
from terragraph_planner.common.exceptions import TopologyException
from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.test.helper import SampleSite
from terragraph_planner.common.topology_models.topology import Topology


class TestTopology(TestCase):
    def setUp(self) -> None:
        self.site1 = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(latitude=1.0, longitude=1.0),
            site_id="site-1",
        )
        self.sector1 = Sector(
            site=self.site1,
            node_id=0,
            position_in_node=0,
            status_type=StatusType.CANDIDATE,
            ant_azimuth=0,
        )
        self.site2 = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(latitude=2.0, longitude=2.0),
            site_id="site-2",
        )
        self.sector2 = Sector(
            site=self.site2,
            node_id=0,
            position_in_node=0,
            status_type=StatusType.CANDIDATE,
            ant_azimuth=0,
        )
        self.link1 = Link(
            tx_site=self.site1,
            rx_site=self.site2,
            tx_sector=self.sector1,
            rx_sector=self.sector2,
        )
        self.link2 = Link(
            tx_site=self.site2,
            rx_site=self.site1,
            tx_sector=self.sector2,
            rx_sector=self.sector1,
        )
        self.topology = Topology(
            sites=[self.site1, self.site2],
            sectors=[self.sector1, self.sector2],
            links=[self.link1, self.link2],
        )

    def test_construct(self) -> None:
        empty_topology = Topology()
        self.assertEqual(len(empty_topology.sites), 0)
        self.assertEqual(len(empty_topology.sectors), 0)
        self.assertEqual(len(empty_topology.demand_sites), 0)
        self.assertEqual(len(empty_topology.links), 0)

        topology = Topology(
            sites=[self.site1, self.site2],
            sectors=[self.sector1],
            links=[self.link1],
        )

        self.assertEqual(len(topology.sites), 2)
        self.assertIs(self.site1, topology.sites[self.site1.site_id])
        self.assertIs(self.site2, topology.sites[self.site2.site_id])
        self.assertEqual(len(topology.sectors), 1)
        self.assertIs(self.sector1, topology.sectors[self.sector1.sector_id])
        self.assertEqual(len(topology.links), 1)
        self.assertIs(
            self.link1,
            topology.get_link_by_site_ids(
                self.site1.site_id, self.site2.site_id
            ),
        )

    def test_add_remove_site(self) -> None:
        topology = Topology()
        self.assertEqual(len(topology.sites), 0)
        site3 = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(latitude=3.0, longitude=3.0),
        )
        topology.add_site(site3)
        self.assertEqual(len(topology.sites), 1)

        # Add a sector whose site is not in topology
        with self.assertRaisesRegex(
            TopologyException,
            f"Invalid site id {self.sector1.site.site_id} of sector {self.sector1.sector_id}",
        ):
            topology.add_sector(self.sector1)

        # Now add the site in and then add the sector again
        topology.add_site(self.site1)
        self.assertEqual(len(topology.sites), 2)
        topology.add_sector(self.sector1)
        self.assertEqual(len(topology.sectors), 1)

        # Add link
        topology.add_site(self.site2)
        topology.add_sector(self.sector2)
        topology.add_link(self.link1)
        self.assertEqual(len(topology.links), 1)

        # Remove site1, and then the sector1 and link1 should disppear as well
        topology.remove_site(self.site1.site_id)
        self.assertEqual(len(topology.sites), 2)
        self.assertNotIn(self.site1.site_id, topology.sites)
        self.assertEqual(len(topology.sectors), 1)
        self.assertNotIn(self.sector1.sector_id, topology.sectors)
        self.assertEqual(len(topology.links), 0)

    def test_add_remove_sector(self) -> None:
        topology = self.topology
        self.assertEqual(len(topology.sectors), 2)
        topology.remove_sector(self.sector1.sector_id)
        self.assertIsNone(self.link1.tx_sector)
        self.assertIsNone(self.link1.rx_sector)
        self.assertEqual(len(topology.sectors), 1)
        topology.remove_sector(self.sector2.sector_id)
        self.assertEqual(len(topology.sectors), 0)

    def test_add_remove_link(self) -> None:
        topology = self.topology
        topology.remove_link(self.link1.link_id)
        self.assertEqual(len(topology.links), 1)
        topology.add_link_from_site_ids(
            self.site1.site_id,
            self.site2.site_id,
            status_type=StatusType.UNREACHABLE,  # pyre-ignore[6]
            is_wireless=False,  # pyre-ignore[6]
        )
        self.assertEqual(len(topology.links), 2)
        link = none_throws(
            topology.get_link_by_site_ids(
                self.site1.site_id, self.site2.site_id
            )
        )
        self.assertEqual(link.status_type, StatusType.UNREACHABLE)
        self.assertEqual(link.is_wireless, False)

    def test_connectivity_dicts(self) -> None:
        topology = Topology(
            sites=[self.site1, self.site2],
            sectors=[self.sector1, self.sector2],
            links=[self.link1],
        )
        self.assertEqual(len(topology.site_connectivity), 1)
        self.assertEqual(len(topology.site_connectivity[self.site1.site_id]), 1)
        self.assertEqual(
            topology.site_connectivity[self.site1.site_id][self.site2.site_id],
            self.link1.link_id,
        )

        self.assertEqual(len(topology.site_connectivity_reverse), 1)
        self.assertEqual(
            len(topology.site_connectivity_reverse[self.site2.site_id]), 1
        )
        self.assertEqual(
            topology.site_connectivity_reverse[self.site2.site_id][
                self.site1.site_id
            ],
            self.link1.link_id,
        )

        self.assertEqual(len(topology.sector_connectivity), 1)
        self.assertEqual(
            len(topology.sector_connectivity[self.sector1.sector_id]), 1
        )
        self.assertEqual(
            topology.sector_connectivity[self.sector1.sector_id][
                self.sector2.sector_id
            ],
            self.link1.link_id,
        )

    def test_get_link(self) -> None:
        topology = self.topology
        self.assertIs(
            topology.get_link_by_site_ids(
                self.site1.site_id, self.site2.site_id
            ),
            self.link1,
        )
        self.assertIs(
            topology.get_link_by_sector_ids(
                self.sector1.sector_id, self.sector2.sector_id
            ),
            self.link1,
        )
        self.assertIs(topology.get_reverse_link(self.link1), self.link2)

    def test_get_neighbor(self) -> None:
        topology = self.topology
        successor_sites1 = topology.get_successor_sites(self.site1)
        self.assertEqual(len(successor_sites1), 1)
        self.assertIs(successor_sites1[0], self.site2)
        predecessor_sites1 = topology.get_predecessor_sites(self.site1)
        self.assertEqual(len(predecessor_sites1), 1)
        self.assertIs(predecessor_sites1[0], self.site2)
        successor_sites2 = topology.get_successor_sites(self.site2)
        self.assertEqual(len(successor_sites2), 1)
        self.assertIs(successor_sites2[0], self.site1)
        predecessor_sites2 = topology.get_predecessor_sites(self.site2)
        self.assertEqual(len(predecessor_sites2), 1)
        self.assertIs(predecessor_sites2[0], self.site1)

        successor_sites3 = topology.get_wireless_successor_sites(self.site1)
        self.assertEqual(len(successor_sites3), 1)
        self.assertIs(successor_sites3[0], self.site2)
        predecessor_site3 = topology.get_wireless_predecessor_sites(self.site1)
        self.assertEqual(len(predecessor_site3), 1)
        self.assertIs(predecessor_site3[0], self.site2)
        self.link1.is_wireless = False
        self.link2.is_wireless = False
        successor_sites4 = topology.get_wireless_successor_sites(self.site1)
        self.assertEqual(len(successor_sites4), 0)
        predecessor_sites4 = topology.get_wireless_predecessor_sites(self.site1)
        self.assertEqual(len(predecessor_sites4), 0)
