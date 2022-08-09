# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


from copy import deepcopy
from unittest import TestCase
from unittest.mock import MagicMock, patch

from terragraph_planner.common.configuration.configs import (
    DeviceData,
    OptimizerParams,
    SectorParams,
)
from terragraph_planner.common.configuration.enums import (
    DeviceType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.topology_models.demand_site import DemandSite
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    SampleSite,
    square_topology,
    square_topology_with_cns,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.topology_operations import (
    compute_max_pop_capacity_of_topology,
    get_adversarial_links,
    mark_unreachable_components,
    readjust_sectors_post_opt,
    update_link_caps_with_sinr,
)
from terragraph_planner.optimization.topology_optimization import (
    optimize_topology,
)
from terragraph_planner.optimization.topology_preparation import (
    prepare_topology_for_optimization,
)

TEST_PREFIX = "terragraph_planner.optimization.topology_operations"


class TestMarkUnreachable(TestCase):
    def test_mark_unreachable_with_single_pop(self) -> None:
        """
        Test mark unreachable for a topology with one POP
        """
        sites = [
            SampleSite(
                site_id="POP1",
                site_type=SiteType.POP,
                location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="DN1",
                site_type=SiteType.DN,
                location=GeoLocation(utm_x=100, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="DN2",
                site_type=SiteType.DN,
                location=GeoLocation(utm_x=200, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="CN1",
                site_type=SiteType.CN,
                location=GeoLocation(utm_x=300, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="CN2",
                site_type=SiteType.CN,
                location=GeoLocation(utm_x=300, utm_y=-100, utm_epsg=32631),
            ),
            SampleSite(
                site_id="CN3",
                site_type=SiteType.CN,
                location=GeoLocation(utm_x=300, utm_y=-200, utm_epsg=32631),
            ),
        ]

        sectors = [
            Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(site=sites[4], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(site=sites[5], node_id=0, position_in_node=0, ant_azimuth=0),
        ]

        links = [
            Link(tx_sector=sectors[0], rx_sector=sectors[1]),  # POP1->DN1
            Link(tx_sector=sectors[1], rx_sector=sectors[3]),  # DN1->CN1
            Link(tx_sector=sectors[1], rx_sector=sectors[4]),  # DN1->CN2
            Link(tx_sector=sectors[2], rx_sector=sectors[5]),  # DN2->CN3
        ]

        topology = Topology(sites=sites, links=links, sectors=sectors)

        mark_unreachable_components(topology, None)

        connected_sites = {"POP1", "DN1", "CN1", "CN2"}
        self.assertEqual(
            topology.get_site_ids(
                status_filter=StatusType.reachable_status(),
            ),
            connected_sites,
        )
        connected_sectors = {
            "POP1-0-0-DN",
            "DN1-0-0-DN",
            "CN1-0-0-CN",
            "CN2-0-0-CN",
        }
        self.assertEqual(
            {
                sector_id
                for sector_id, sector in topology.sectors.items()
                if sector.status_type in StatusType.reachable_status()
            },
            connected_sectors,
        )
        connected_links = {"POP1-DN1", "DN1-CN1", "DN1-CN2"}
        self.assertEqual(
            {
                link_id
                for link_id, link in topology.links.items()
                if link.status_type in StatusType.reachable_status()
            },
            connected_links,
        )

        # Now test with max hops
        for site in topology.sites.values():
            site.status_type = StatusType.CANDIDATE
        for link in topology.links.values():
            link.status_type = StatusType.CANDIDATE
        for sector in topology.sectors.values():
            sector.status_type = StatusType.CANDIDATE

        mark_unreachable_components(topology, maximum_hops=1)

        connected_sites = {"POP1", "DN1"}
        self.assertEqual(
            topology.get_site_ids(
                status_filter=StatusType.reachable_status(),
            ),
            connected_sites,
        )
        connected_sectors = {"POP1-0-0-DN", "DN1-0-0-DN"}
        self.assertEqual(
            {
                sector_id
                for sector_id, sector in topology.sectors.items()
                if sector.status_type in StatusType.reachable_status()
            },
            connected_sectors,
        )
        connected_links = {"POP1-DN1"}
        self.assertEqual(
            {
                link_id
                for link_id, link in topology.links.items()
                if link.status_type in StatusType.reachable_status()
            },
            connected_links,
        )

    def test_mark_unreachable_with_multiple_pops(self) -> None:
        """
        Test mark unreachable for a topology with two POPs
        """
        sites = [
            SampleSite(
                site_id="POP1",
                site_type=SiteType.POP,
                location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="POP2",
                site_type=SiteType.POP,
                location=GeoLocation(utm_x=400, utm_y=-200, utm_epsg=32631),
            ),
            SampleSite(
                site_id="DN1",
                site_type=SiteType.DN,
                location=GeoLocation(utm_x=100, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="DN2",
                site_type=SiteType.DN,
                location=GeoLocation(utm_x=200, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="CN1",
                site_type=SiteType.CN,
                location=GeoLocation(utm_x=300, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="CN2",
                site_type=SiteType.CN,
                location=GeoLocation(utm_x=300, utm_y=-100, utm_epsg=32631),
            ),
            SampleSite(
                site_id="CN3",
                site_type=SiteType.CN,
                location=GeoLocation(utm_x=300, utm_y=-200, utm_epsg=32631),
            ),
        ]

        sectors = [
            Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(site=sites[2], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(site=sites[3], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(site=sites[4], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(site=sites[5], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(site=sites[6], node_id=0, position_in_node=0, ant_azimuth=0),
        ]

        links = [
            Link(tx_sector=sectors[0], rx_sector=sectors[2]),  # POP1->DN1
            Link(tx_sector=sectors[2], rx_sector=sectors[4]),  # DN1->CN1
            Link(tx_sector=sectors[2], rx_sector=sectors[5]),  # DN1->CN2
            Link(tx_sector=sectors[3], rx_sector=sectors[6]),  # DN2->CN3
            Link(tx_sector=sectors[1], rx_sector=sectors[6]),  # POP2->CN3
        ]

        topology = Topology(sites=sites, links=links, sectors=sectors)

        mark_unreachable_components(topology, None)

        connected_sites = {"POP1", "POP2", "DN1", "CN1", "CN2", "CN3"}
        self.assertEqual(
            topology.get_site_ids(
                status_filter=StatusType.reachable_status(),
            ),
            connected_sites,
        )
        connected_sectors = {
            "POP1-0-0-DN",
            "POP2-0-0-DN",
            "DN1-0-0-DN",
            "CN1-0-0-CN",
            "CN2-0-0-CN",
            "CN3-0-0-CN",
        }
        self.assertEqual(
            {
                sector_id
                for sector_id, sector in topology.sectors.items()
                if sector.status_type in StatusType.reachable_status()
            },
            connected_sectors,
        )
        connected_links = {"POP1-DN1", "DN1-CN1", "DN1-CN2", "POP2-CN3"}
        self.assertEqual(
            {
                link_id
                for link_id, link in topology.links.items()
                if link.status_type in StatusType.reachable_status()
            },
            connected_links,
        )

        # Now test with max hops
        for site in topology.sites.values():
            site.status_type = StatusType.CANDIDATE
        for link in topology.links.values():
            link.status_type = StatusType.CANDIDATE
        for sector in topology.sectors.values():
            sector.status_type = StatusType.CANDIDATE

        mark_unreachable_components(topology, maximum_hops=1)

        connected_sites = {"POP1", "DN1", "POP2", "CN3"}
        self.assertEqual(
            topology.get_site_ids(
                status_filter=StatusType.reachable_status(),
            ),
            connected_sites,
        )
        connected_sectors = {
            "POP1-0-0-DN",
            "DN1-0-0-DN",
            "POP2-0-0-DN",
            "CN3-0-0-CN",
        }
        self.assertEqual(
            {
                sector_id
                for sector_id, sector in topology.sectors.items()
                if sector.status_type in StatusType.reachable_status()
            },
            connected_sectors,
        )
        connected_links = {"POP1-DN1", "POP2-CN3"}
        self.assertEqual(
            {
                link_id
                for link_id, link in topology.links.items()
                if link.status_type in StatusType.reachable_status()
            },
            connected_links,
        )


class TestMaxPOPCapacity(TestCase):
    def test_max_pop_capacity(self) -> None:
        """
        Test max pop capacity of a topology
        """
        sites = [
            SampleSite(
                site_id="POP1",
                site_type=SiteType.POP,
                location=GeoLocation(latitude=0, longitude=0),
            ),
            SampleSite(
                site_id="POP2",
                site_type=SiteType.POP,
                location=GeoLocation(latitude=0, longitude=1),
            ),
            SampleSite(
                site_id="DN1",
                site_type=SiteType.DN,
                location=GeoLocation(latitude=1, longitude=0),
            ),
            SampleSite(
                site_id="DN2",
                site_type=SiteType.DN,
                location=GeoLocation(latitude=1, longitude=1),
            ),
            SampleSite(
                site_id="DN3",
                site_type=SiteType.DN,
                location=GeoLocation(latitude=1, longitude=2),
            ),
        ]

        sectors = [
            Sector(site=sites[0], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(
                site=sites[0], node_id=1, position_in_node=0, ant_azimuth=90
            ),
            Sector(site=sites[1], node_id=0, position_in_node=0, ant_azimuth=0),
            Sector(
                site=sites[1], node_id=1, position_in_node=0, ant_azimuth=90
            ),
            Sector(
                site=sites[2], node_id=0, position_in_node=0, ant_azimuth=180
            ),
            Sector(
                site=sites[3], node_id=0, position_in_node=0, ant_azimuth=180
            ),
            Sector(
                site=sites[4], node_id=0, position_in_node=0, ant_azimuth=180
            ),
        ]

        links = [
            Link(tx_sector=sectors[0], rx_sector=sectors[4]),  # POP1->DN1
            Link(tx_sector=sectors[4], rx_sector=sectors[0]),  # DN1->POP1
            Link(tx_sector=sectors[1], rx_sector=sectors[5]),  # POP1->DN2
            Link(tx_sector=sectors[5], rx_sector=sectors[1]),  # DN2->POP1
            Link(tx_sector=sectors[2], rx_sector=sectors[4]),  # POP2->DN1
            Link(tx_sector=sectors[4], rx_sector=sectors[2]),  # DN1->POP2
            Link(tx_sector=sectors[3], rx_sector=sectors[5]),  # POP2->DN2
            Link(tx_sector=sectors[5], rx_sector=sectors[3]),  # DN2->POP2
            Link(tx_sector=sectors[4], rx_sector=sectors[5]),  # DN1->DN2
            Link(tx_sector=sectors[5], rx_sector=sectors[4]),  # DN2->DN1
            Link(
                tx_site=sites[0], rx_site=sites[4], is_wireless=False
            ),  # POP1->DN3
        ]

        for link in links:
            link.capacity = 1.0

        topology = Topology(sites=sites, links=links, sectors=sectors)

        # Max capacity is bound by pop capacity
        pop_capacity = 1.0
        max_capacity = compute_max_pop_capacity_of_topology(
            topology, pop_capacity, StatusType.reachable_status()
        )
        self.assertEqual(max_capacity, 2.0)

        pop_capacity = 10.0

        # Max capacity is sum of all POP sector capacities
        max_capacity = compute_max_pop_capacity_of_topology(
            topology, pop_capacity, StatusType.reachable_status()
        )
        self.assertEqual(max_capacity, 5.0)

        # Move a link from one sector to another
        topology.links["POP2-DN2"].tx_sector = sectors[2]
        max_capacity = compute_max_pop_capacity_of_topology(
            topology, pop_capacity, StatusType.reachable_status()
        )
        self.assertEqual(max_capacity, 4.0)

        # Mark another link unavailable
        topology.links["POP1-DN1"]._status_type = StatusType.UNAVAILABLE
        max_capacity = compute_max_pop_capacity_of_topology(
            topology, pop_capacity, StatusType.reachable_status()
        )
        self.assertEqual(max_capacity, 3.0)


class TestAdversarial(TestCase):
    def test_square_topology_with_adversarial_links(self) -> None:
        topology = square_topology()

        for site in topology.sites.values():
            site.status_type = StatusType.PROPOSED
        for sector in topology.sectors.values():
            sector.status_type = StatusType.PROPOSED
        for link in topology.links.values():
            link.status_type = StatusType.PROPOSED

        adversarial_links = get_adversarial_links(
            topology=topology,
            adversarial_links_ratio=1.0,
        )
        # No adversarial links because the topology has perfect redundancy
        self.assertSetEqual(adversarial_links, set())

        # Deactivate some links and add a couple demand sites
        candidate_links = {
            "DN1-DN2",
            "DN2-DN1",
            "DN2-DN3",
            "DN3-DN2",
            "DN3-DN4",
            "DN4-DN3",
            "DN4-DN1",
            "DN1-DN4",
        }
        for link_id in candidate_links:
            topology.links[link_id].status_type = StatusType.CANDIDATE

        topology.add_demand_site(
            DemandSite(
                location=deepcopy(topology.sites["POP5"].location),
                connected_sites=[topology.sites["POP5"]],
            )
        )
        topology.add_demand_site(
            DemandSite(
                location=deepcopy(topology.sites["POP6"].location),
                connected_sites=[topology.sites["POP6"]],
            )
        )

        adversarial_links = get_adversarial_links(
            topology=topology,
            adversarial_links_ratio=0.1,
        )

        # Ceil of 0.1 of 8 links is just 1 link but backhaul links are marked together
        expected_links = {("POP5", "DN1"), ("DN1", "POP5")}
        self.assertSetEqual(adversarial_links, expected_links)

        adversarial_links = get_adversarial_links(
            topology=topology,
            adversarial_links_ratio=0.4,
        )

        # Ceil of 0.4 of 8 links is 4 links
        expected_links = {
            ("POP5", "DN1"),
            ("DN1", "POP5"),
            ("POP5", "DN4"),
            ("DN4", "POP5"),
        }
        self.assertSetEqual(adversarial_links, expected_links)

        adversarial_links = get_adversarial_links(
            topology=topology,
            adversarial_links_ratio=1.0,
        )

        expected_links = {
            ("POP5", "DN1"),
            ("DN1", "POP5"),
            ("POP5", "DN4"),
            ("DN4", "POP5"),
            ("POP6", "DN3"),
            ("DN3", "POP6"),
        }
        self.assertSetEqual(adversarial_links, expected_links)


class TestReadjustSectorsPostOpt(TestCase):
    def setUp(self) -> None:
        dn_device = DeviceData(
            device_sku="DN_DEVICE",
            sector_params=SectorParams(horizontal_scan_range=220),
            number_of_nodes_per_site=1,
            device_type=DeviceType.DN,
        )
        cn_device = DeviceData(
            device_sku="CN_DEVICE",
            sector_params=SectorParams(horizontal_scan_range=30),
            number_of_nodes_per_site=1,
            device_type=DeviceType.CN,
        )
        # For some of the sites below, although connecting links are candidate,
        # for test purposes, assume that there are other topology components
        # (sites/links) that do connect to these sites but are not explicitly
        # added to the test topology
        sites = [
            SampleSite(
                site_id="POP1",
                site_type=SiteType.POP,
                device=dn_device,
                status_type=StatusType.PROPOSED,
                location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="CN2",
                site_type=SiteType.CN,
                device=cn_device,
                status_type=StatusType.PROPOSED,
                location=GeoLocation(utm_x=10, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="CN3",
                site_type=SiteType.CN,
                device=cn_device,
                status_type=StatusType.PROPOSED,
                location=GeoLocation(utm_x=-10, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="CN4",
                site_type=SiteType.CN,
                device=cn_device,
                status_type=StatusType.PROPOSED,
                location=GeoLocation(utm_x=0, utm_y=10, utm_epsg=32631),
            ),
            SampleSite(
                site_id="CN5",
                site_type=SiteType.CN,
                device=cn_device,
                status_type=StatusType.PROPOSED,
                location=GeoLocation(utm_x=0, utm_y=-10, utm_epsg=32631),
            ),
        ]
        sectors = [
            Sector(
                site=sites[0],
                node_id=0,
                position_in_node=0,
                ant_azimuth=0,
                status_type=StatusType.PROPOSED,
                channel=0,
            ),
            Sector(
                site=sites[1],
                node_id=0,
                position_in_node=0,
                ant_azimuth=180,
                status_type=StatusType.PROPOSED,
                channel=0,
            ),
            Sector(
                site=sites[2],
                node_id=0,
                position_in_node=0,
                ant_azimuth=90,
                status_type=StatusType.PROPOSED,
                channel=0,
            ),
            Sector(
                site=sites[3],
                node_id=0,
                position_in_node=0,
                ant_azimuth=0,
                status_type=StatusType.PROPOSED,
                channel=0,
            ),
            Sector(
                site=sites[4],
                node_id=0,
                position_in_node=0,
                ant_azimuth=0,
                status_type=StatusType.PROPOSED,
                channel=0,
            ),
        ]
        links = [
            Link(
                tx_sector=sectors[0],
                rx_sector=sectors[1],
                status_type=StatusType.PROPOSED,
            ),  # POP1->CN2
            Link(
                tx_sector=sectors[0],
                rx_sector=sectors[2],
                status_type=StatusType.CANDIDATE,
            ),  # POP1->CN3
            Link(
                tx_sector=sectors[0],
                rx_sector=sectors[3],
                status_type=StatusType.CANDIDATE,
            ),  # POP1->CN4
            Link(
                tx_sector=sectors[0],
                rx_sector=sectors[4],
                status_type=StatusType.CANDIDATE,
            ),  # POP1->CN5
        ]
        self.topology = Topology(sites=sites, sectors=sectors, links=links)
        self.params = OptimizerParams(device_list=[dn_device, cn_device])

    # Note: although the find_best_sectors results do not make sense for CNs
    # with no active links in the topology, assume that there are other active
    # links and connecting sites, but they are just not explicitly included in
    # the test topology and instead these results are mocked
    @patch(
        f"{TEST_PREFIX}.find_best_sectors",
        MagicMock(side_effect=[[[90]], [[270]], [[80]], [[170]], [[20]]]),
    )
    @patch(
        f"{TEST_PREFIX}.add_link_capacities_with_deviation",
        MagicMock(side_effect=lambda t, p: None),  # return input topology
    )
    def test_readjust_sectors(self) -> None:
        """
        Test case where find_best_sectors return a valid
        solution and then readjust_sectors_post_opt re-assign the
        ant_azimuth for each node
        """
        readjust_sectors_post_opt(self.topology, self.params)
        azimuths = [90, 270, 80, 170, 20]
        sectors = list(self.topology.sectors.values())
        for sector, sector_azimuth in zip(sectors, azimuths):
            self.assertEqual(sector.ant_azimuth, sector_azimuth)

        # Verify link is in sector
        pop_cn2_link = self.topology.links["POP1-CN2"]
        self.assertIsNotNone(pop_cn2_link.tx_sector)
        self.assertIsNotNone(pop_cn2_link.rx_sector)

        # Verify link is out of DN sector
        pop_cn3_link = self.topology.links["POP1-CN3"]
        self.assertIsNone(pop_cn3_link.tx_sector)
        self.assertIsNone(pop_cn3_link.rx_sector)

        # Verify link is in sector
        pop_cn4_link = self.topology.links["POP1-CN4"]
        self.assertIsNotNone(pop_cn4_link.tx_sector)
        self.assertIsNotNone(pop_cn4_link.rx_sector)

        # Verify link is out of CN sector
        pop_cn5_link = self.topology.links["POP1-CN5"]
        self.assertIsNone(pop_cn5_link.tx_sector)
        self.assertIsNone(pop_cn5_link.rx_sector)


class TestLinkInterferenceUpdate(TestCase):
    def test_interference_converge(self) -> None:
        topology = square_topology_with_cns()
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        prepare_topology_for_optimization(topology, params)
        for link in topology.links.values():
            link.sinr_dbm /= 2
        optimize_topology(topology, params)
        active_links = [
            link
            for link in topology.links.values()
            if link.status_type in StatusType.active_status()
        ]
        if len(active_links) > 0:
            interference_pre = sum(
                link.snr_dbm - link.sinr_dbm for link in active_links
            ) / len(active_links)
            update_link_caps_with_sinr(topology, params.maximum_eirp)
            interference_post = sum(
                link.snr_dbm - link.sinr_dbm
                for link in topology.links.values()
                if link.status_type in StatusType.active_status()
            ) / len(active_links)
            self.assertLessEqual(interference_post, interference_pre)
