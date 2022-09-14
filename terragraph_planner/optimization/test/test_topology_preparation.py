# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import itertools
import math
import random
from copy import deepcopy
from unittest import TestCase
from unittest.mock import MagicMock, patch

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import (
    DeviceData,
    OptimizerParams,
    SectorParams,
)
from terragraph_planner.common.configuration.enums import (
    DeviceType,
    SectorType,
    SiteType,
)
from terragraph_planner.common.constants import FULL_ROTATION_ANGLE
from terragraph_planner.common.exceptions import OptimizerException
from terragraph_planner.common.geos import GeoLocation, angle_delta
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    SampleSite,
    multi_sector_topology,
    raw_square_topology,
    raw_square_topology_with_cns,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.constants import BACKHAUL_LINK_TYPE_WEIGHT
from terragraph_planner.optimization.topology_preparation import (
    add_sectors_to_links,
    create_cn_sectors,
    create_dn_sectors,
    find_best_equidistant_sectors,
    find_best_sectors,
    get_sector_azimuths_from_node_center,
    prepare_topology_for_optimization,
    validate_link_sectors,
    validate_site_sectors,
)

TEST_PREFIX = "terragraph_planner.optimization.topology_preparation"


class TestTopologyPreparation(TestCase):
    @patch(
        "terragraph_planner.optimization.topology_preparation.add_demand_to_topology",
        MagicMock(side_effect=lambda t, p: None),  # return input topology
    )
    def test_add_link_capacities(self) -> None:
        """
        Test to ensure link capacities are added during topology preparation.
        """
        topology = raw_square_topology()
        prepare_topology_for_optimization(
            topology,
            OptimizerParams(
                device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
                rain_rate=10.0,
            ),
        )
        for link in topology.links.values():
            self.assertEqual(link.capacity, 1.8)

    @patch(
        "terragraph_planner.optimization.topology_preparation.add_demand_to_topology",
        MagicMock(side_effect=lambda t, p: None),  # return input topology
    )
    def test_add_sectors(self) -> None:
        """
        Test to ensure sectors are added during topology preparation
        """
        topology = raw_square_topology()

        # Remove sectors
        for sector_id in list(topology.sectors.keys()):
            topology.remove_sector(sector_id)

        self.assertEqual(len(topology.sectors), 0)

        prepare_topology_for_optimization(
            topology,
            OptimizerParams(
                device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            ),
        )

        # At least one sector on all sites
        self.assertGreaterEqual(len(topology.sectors), len(topology.sites))
        # All links should have a sector due to sufficiently large scan range
        for link in topology.links.values():
            self.assertIsNotNone(link.tx_sector)
            self.assertIsNotNone(link.rx_sector)

    def test_add_given_sectors_to_links(self) -> None:
        """
        Given user-supplied sectors, ensure add_sectors_to_links does not
        change link sector assignments (input should satisfy sector parameters)
        """
        topology = raw_square_topology_with_cns()
        # Point CN sectors away from the links creating large rx_dev; this
        # should not matter since all links should be considered in sector for
        # CNs during pre-optimization
        topology.sectors["CN7-0-0-CN"].ant_azimuth = 180
        topology.sectors["CN8-0-0-CN"].ant_azimuth = 180
        links_to_sectors = {}
        for link in topology.links.values():
            links_to_sectors[link.link_id] = (link.tx_sector, link.rx_sector)
        prepare_topology_for_optimization(
            topology,
            OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]),
        )
        for link in topology.links.values():
            self.assertIsNotNone(link.tx_sector)
            self.assertIs(link.tx_sector, links_to_sectors[link.link_id][0])
            self.assertIsNotNone(link.rx_sector)
            self.assertIs(link.rx_sector, links_to_sectors[link.link_id][1])

    def test_add_demand_sites(self) -> None:
        topology = raw_square_topology_with_cns()
        cn_demand = 0.1
        prepare_topology_for_optimization(
            topology,
            OptimizerParams(
                device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
                demand=cn_demand,
            ),
        )
        self.assertEqual(len(topology.demand_sites), 2)
        for demand in topology.demand_sites.values():
            self.assertEqual(demand.demand, cn_demand)


class TestAddSectorsToLinks(TestCase):
    def test_add_sectors_to_links(self) -> None:
        """
        Test adding sectors to links with different scan ranges.
        """
        device_dn90 = DeviceData(
            device_sku="Device_DN90",
            sector_params=SectorParams(horizontal_scan_range=90),
            number_of_nodes_per_site=4,
            device_type=DeviceType.DN,
        )
        device_dn70 = DeviceData(
            device_sku="Device_DN70",
            sector_params=SectorParams(horizontal_scan_range=70),
            number_of_nodes_per_site=4,
            device_type=DeviceType.DN,
        )
        device_dn360 = DeviceData(
            device_sku="Device_DN360",
            sector_params=SectorParams(horizontal_scan_range=360),
            number_of_nodes_per_site=1,
            device_type=DeviceType.DN,
        )
        device_cn360 = DeviceData(
            device_sku="Device_CN360",
            sector_params=SectorParams(horizontal_scan_range=360),
            number_of_nodes_per_site=1,
            device_type=DeviceType.CN,
        )

        topology = multi_sector_topology()

        # Remove sectors
        for sector_id in list(topology.sectors.keys()):
            topology.remove_sector(sector_id)

        # Links from site POP1 are at bearings 90 and 180
        topology.add_sector(
            Sector(
                site=topology.sites["POP1"],
                node_id=0,
                position_in_node=0,
                ant_azimuth=135,
            )
        )
        topology.add_sector(
            Sector(
                site=topology.sites["DN2"],
                node_id=0,
                position_in_node=0,
                ant_azimuth=270,
            )
        )
        topology.add_sector(
            Sector(
                site=topology.sites["DN3"],
                node_id=0,
                position_in_node=0,
                ant_azimuth=0,
            )
        )

        for site in topology.sites.values():
            site._device = device_dn90
        add_sectors_to_links(topology, False, None)
        self.assertEqual(
            none_throws(topology.links["POP1-DN2"].tx_sector).sector_id,
            "POP1-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-DN2"].rx_sector).sector_id,
            "DN2-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-DN3"].tx_sector).sector_id,
            "POP1-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-DN3"].rx_sector).sector_id,
            "DN3-0-0-DN",
        )

        # Now we can't reach
        for link in topology.links.values():
            link.clear_sectors()
        for site in topology.sites.values():
            site._device = device_dn70
        add_sectors_to_links(topology, False, None)
        self.assertIsNone(topology.links["POP1-DN2"].tx_sector)
        self.assertIsNone(topology.links["POP1-DN2"].rx_sector)
        self.assertIsNone(topology.links["POP1-DN3"].tx_sector)
        self.assertIsNone(topology.links["POP1-DN3"].rx_sector)

        for link in topology.links.values():
            link.clear_sectors()
        for site in topology.sites.values():
            site._device = device_dn360
        add_sectors_to_links(topology, False, None)
        self.assertIsNotNone(topology.links["POP1-DN2"].tx_sector)
        self.assertIsNotNone(topology.links["POP1-DN2"].rx_sector)
        self.assertIsNotNone(topology.links["POP1-DN3"].tx_sector)
        self.assertIsNotNone(topology.links["POP1-DN3"].rx_sector)

        # Try again after adjusting the node on site 1 so it can reach one of the DNs
        for link in topology.links.values():
            link.clear_sectors()
        topology.remove_sector("POP1-0-0-DN")
        topology.add_sector(
            Sector(
                site=topology.sites["POP1"],
                node_id=0,
                position_in_node=0,
                ant_azimuth=190,
            )
        )
        for site in topology.sites.values():
            site._device = device_dn70
        add_sectors_to_links(topology, False, None)
        self.assertIsNone(topology.links["POP1-DN2"].tx_sector)
        self.assertIsNone(topology.links["POP1-DN2"].rx_sector)
        self.assertEqual(
            none_throws(topology.links["POP1-DN3"].tx_sector).sector_id,
            "POP1-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-DN3"].rx_sector).sector_id,
            "DN3-0-0-DN",
        )

        # Now make site 3 a CN - that should relax its angle constraint so all links should be
        # given the expected nodes, even if we point the CN sector in the opposite direction
        for link in topology.links.values():
            link.clear_sectors()
        # Move node back to center
        topology.remove_sector("POP1-0-0-DN")
        topology.add_sector(
            Sector(
                site=topology.sites["POP1"],
                node_id=0,
                position_in_node=0,
                ant_azimuth=135,
            )
        )
        topology.remove_sector("DN3-0-0-DN")

        # Point CN away from the DN site it links to - it shouldn't matter
        cn = SampleSite(
            site_id="CN3",
            site_type=SiteType.CN,
            location=deepcopy(topology.sites["DN3"].location),
        )
        topology.remove_site("DN3")
        topology.add_site(cn)
        topology.add_link(Link(tx_site=topology.sites["POP1"], rx_site=cn))
        topology.add_sector(
            Sector(
                site=topology.sites["CN3"],
                node_id=0,
                position_in_node=0,
                ant_azimuth=180,
            )
        )
        for site in topology.sites.values():
            if site.site_type in SiteType.dist_site_types():
                site._device = device_dn90
            elif site.site_type == SiteType.CN:
                site._device = device_cn360

        add_sectors_to_links(topology, False, None)
        self.assertEqual(
            none_throws(topology.links["POP1-DN2"].tx_sector).sector_id,
            "POP1-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-DN2"].rx_sector).sector_id,
            "DN2-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-CN3"].tx_sector).sector_id,
            "POP1-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-CN3"].rx_sector).sector_id,
            "CN3-0-0-CN",
        )

    def test_add_sectors_to_links_multi_device(self) -> None:
        """
        Test add_sectors_to_links with a case where the scan range is just
        large enough to include both links and then just small enough to only
        include one.
        """
        topology = multi_sector_topology()
        topology.add_link_from_site_ids("DN2", "DN3")

        # Remove sectors
        for sector_id in list(topology.sectors.keys()):
            topology.remove_sector(sector_id)

        # Links from site POP1 are at bearings 90 and 180
        topology.add_sector(
            Sector(
                site=topology.sites["POP1"],
                node_id=0,
                position_in_node=0,
                ant_azimuth=135,
            )
        )
        topology.add_sector(
            Sector(
                site=topology.sites["DN2"],
                node_id=0,
                position_in_node=0,
                ant_azimuth=270,
            )
        )
        topology.add_sector(
            Sector(
                site=topology.sites["DN3"],
                node_id=0,
                position_in_node=0,
                ant_azimuth=0,
            )
        )

        # Angle between sector on DN2 and DN2->DN3 is just slightly more than
        # 45 degrees so set the scan range to just a bit more than 90 degrees
        device_dn91 = DeviceData(
            device_sku="Device_DN91",
            sector_params=SectorParams(horizontal_scan_range=91),
            number_of_nodes_per_site=3,
            device_type=DeviceType.DN,
        )
        device_dn88 = DeviceData(
            device_sku="Device_DN88",
            sector_params=SectorParams(horizontal_scan_range=88),
            number_of_nodes_per_site=4,
            device_type=DeviceType.DN,
        )

        for site in topology.sites.values():
            site._device = device_dn91
        add_sectors_to_links(topology, False, None)
        self.assertEqual(
            none_throws(topology.links["POP1-DN2"].tx_sector).sector_id,
            "POP1-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-DN2"].rx_sector).sector_id,
            "DN2-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-DN3"].tx_sector).sector_id,
            "POP1-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-DN3"].rx_sector).sector_id,
            "DN3-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["DN2-DN3"].tx_sector).sector_id,
            "DN2-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["DN2-DN3"].rx_sector).sector_id,
            "DN3-0-0-DN",
        )

        # Site 2 can't reach site 3
        for link in topology.links.values():
            link.clear_sectors()
        topology.sites["DN2"]._device = device_dn88
        add_sectors_to_links(topology, False, None)
        self.assertEqual(
            none_throws(topology.links["POP1-DN2"].tx_sector).sector_id,
            "POP1-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-DN2"].rx_sector).sector_id,
            "DN2-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-DN3"].tx_sector).sector_id,
            "POP1-0-0-DN",
        )
        self.assertEqual(
            none_throws(topology.links["POP1-DN3"].rx_sector).sector_id,
            "DN3-0-0-DN",
        )
        self.assertIsNone(topology.links["DN2-DN3"].tx_sector)
        self.assertIsNone(topology.links["DN2-DN3"].rx_sector)


class TestValidateSectors(TestCase):
    def test_validate_site_sectors(self) -> None:
        site = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
            device=DeviceData(
                device_sku="SAMPLE_DN_DEVICE",
                sector_params=SectorParams(
                    number_sectors_per_node=1, horizontal_scan_range=70
                ),
                number_of_nodes_per_site=4,
            ),
        )
        sector1 = Sector(
            site=site, node_id=0, position_in_node=0, ant_azimuth=0
        )

        sector2 = Sector(
            site=SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=1, utm_y=0, utm_epsg=32631, altitude=0
                ),
            ),
            node_id=0,
            position_in_node=0,
            ant_azimuth=70,
        )
        with self.assertRaisesRegex(
            OptimizerException, "Cannot validate sectors on different sites"
        ):
            validate_site_sectors([sector1, sector2])

        sector3 = Sector(
            site=site, node_id=0, position_in_node=0, ant_azimuth=0
        )
        sector4 = Sector(
            site=site, node_id=0, position_in_node=0, ant_azimuth=70
        )
        with self.assertRaisesRegex(
            OptimizerException,
            "Each sector in the same node must have different positions",
        ):
            validate_site_sectors([sector3, sector4])

        site.device.number_of_nodes_per_site = 2
        sector5 = Sector(
            site=site, node_id=0, position_in_node=0, ant_azimuth=0
        )
        sector6 = Sector(
            site=site, node_id=1, position_in_node=0, ant_azimuth=120
        )
        sector7 = Sector(
            site=site, node_id=2, position_in_node=0, ant_azimuth=240
        )
        with self.assertRaisesRegex(
            OptimizerException, "Number of nodes on a site cannot exceed 2"
        ):
            validate_site_sectors([sector5, sector6, sector7])

        site.device.sector_params.number_sectors_per_node = 2
        with self.assertRaisesRegex(
            OptimizerException, "Number of sectors in each node must be 2"
        ):
            validate_site_sectors([sector1])

        sector8 = Sector(
            site=site, node_id=0, position_in_node=0, ant_azimuth=0
        )
        sector9 = Sector(
            site=site, node_id=0, position_in_node=1, ant_azimuth=120
        )
        sector10 = Sector(
            site=site, node_id=0, position_in_node=2, ant_azimuth=240
        )
        with self.assertRaisesRegex(
            OptimizerException, "Number of sectors in each node must be 2"
        ):
            validate_site_sectors([sector8, sector9, sector10])

        sector11 = Sector(
            site=site, node_id=0, position_in_node=0, ant_azimuth=0
        )
        sector12 = Sector(
            site=site, node_id=0, position_in_node=1, ant_azimuth=295
        )
        with self.assertRaisesRegex(
            OptimizerException,
            "Sectors within the same node are separated by 65.0, but must be separated by the horizontal scan range 70",
        ):
            validate_site_sectors([sector11, sector12])

        sector13 = Sector(
            site=site, node_id=0, position_in_node=0, ant_azimuth=0
        )
        sector14 = Sector(
            site=site, node_id=0, position_in_node=1, ant_azimuth=290
        )
        sector15 = Sector(
            site=site, node_id=1, position_in_node=0, ant_azimuth=225
        )
        sector16 = Sector(
            site=site, node_id=1, position_in_node=1, ant_azimuth=155
        )
        with self.assertRaisesRegex(
            OptimizerException,
            "Sector nodes are separated by 65.0, but must be separated by at least the horizontal scan range 70",
        ):
            validate_site_sectors([sector13, sector14, sector15, sector16])

        site.device.sector_params.number_sectors_per_node = 3
        site.device.sector_params.horizontal_scan_range = 50
        sector17 = Sector(
            site=site, node_id=0, position_in_node=0, ant_azimuth=0
        )
        sector18 = Sector(
            site=site, node_id=0, position_in_node=1, ant_azimuth=50
        )
        sector19 = Sector(
            site=site, node_id=0, position_in_node=2, ant_azimuth=310
        )
        sector20 = Sector(
            site=site, node_id=1, position_in_node=0, ant_azimuth=70
        )
        sector21 = Sector(
            site=site, node_id=1, position_in_node=1, ant_azimuth=120
        )
        sector22 = Sector(
            site=site, node_id=1, position_in_node=2, ant_azimuth=170
        )
        with self.assertRaisesRegex(
            OptimizerException,
            "Sector nodes are separated by 20.0, but must be separated by at least the horizontal scan range 50",
        ):
            validate_site_sectors(
                [sector17, sector18, sector19, sector20, sector21, sector22]
            )

        site.device.sector_params.number_sectors_per_node = 4
        site.device.sector_params.horizontal_scan_range = 40
        sector23 = Sector(
            site=site, node_id=0, position_in_node=0, ant_azimuth=0
        )
        sector24 = Sector(
            site=site, node_id=0, position_in_node=1, ant_azimuth=40
        )
        sector25 = Sector(
            site=site, node_id=0, position_in_node=2, ant_azimuth=320
        )
        sector26 = Sector(
            site=site, node_id=0, position_in_node=3, ant_azimuth=280
        )
        sector27 = Sector(
            site=site, node_id=1, position_in_node=0, ant_azimuth=330
        )
        sector28 = Sector(
            site=site, node_id=1, position_in_node=1, ant_azimuth=290
        )
        sector29 = Sector(
            site=site, node_id=1, position_in_node=2, ant_azimuth=250
        )
        sector30 = Sector(
            site=site, node_id=1, position_in_node=3, ant_azimuth=210
        )
        with self.assertRaisesRegex(
            OptimizerException, "Sector nodes cannot overlap"
        ):
            validate_site_sectors(
                [
                    sector23,
                    sector24,
                    sector25,
                    sector26,
                    sector27,
                    sector28,
                    sector29,
                    sector30,
                ]
            )

        # No error should be thrown in this case
        sector27.ant_azimuth = 240
        sector28.ant_azimuth = 200
        sector29.ant_azimuth = 160
        sector30.ant_azimuth = 120
        validate_site_sectors(
            [
                sector23,
                sector24,
                sector25,
                sector26,
                sector27,
                sector28,
                sector29,
                sector30,
            ]
        )

    def test_validate_link_sectors(self) -> None:
        site1 = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
        )
        site2 = SampleSite(
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=0, utm_y=1, utm_epsg=32631, altitude=0),
        )
        sector1 = Sector(
            site=site1, node_id=0, position_in_node=0, ant_azimuth=0
        )
        sector2 = Sector(
            site=site2, node_id=0, position_in_node=0, ant_azimuth=180
        )
        link = Link(tx_sector=sector1, rx_sector=sector2)

        # No error should be thrown in this case
        validate_link_sectors(link, force_full_cn_scan_range=False)

        sector1.ant_azimuth = 36
        with self.assertRaisesRegex(
            OptimizerException,
            "Link is not within the horizontal scan range of the connected tx sector",
        ):
            validate_link_sectors(link, force_full_cn_scan_range=False)

        sector1.ant_azimuth = 0
        sector2.ant_azimuth = 216
        with self.assertRaisesRegex(
            OptimizerException,
            "Link is not within the horizontal scan range of the connected rx sector",
        ):
            validate_link_sectors(link, force_full_cn_scan_range=False)

        # No error should be throw in this case
        validate_link_sectors(link, force_full_cn_scan_range=True)


class TestFindBestEquidistantSectors(TestCase):
    def test_find_equidistant_straight_line_sectors(self) -> None:
        """
        Test find_best_equidistance_sectors for several sites in a straight line
        """
        from_site = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
        )
        to_sites = [
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=0, utm_y=1, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=0.1, utm_y=2, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=0.2, utm_y=3, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=0.3, utm_y=4, utm_epsg=32631, altitude=0
                ),
            ),
        ]
        scan_range = 70

        # Test with 4 nodes each with 1 sector
        nodes = find_best_equidistant_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=4,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
        )
        scan_range = 70

        self.assertEqual(len(nodes), 4)
        for node in nodes:
            self.assertEqual(len(node), 1)
        self.assertEqual(abs(angle_delta(nodes[0][0], nodes[1][0])), 90)
        self.assertEqual(abs(angle_delta(nodes[1][0], nodes[2][0])), 90)
        self.assertEqual(abs(angle_delta(nodes[2][0], nodes[3][0])), 90)
        self.assertEqual(abs(angle_delta(nodes[3][0], nodes[0][0])), 90)

    def test_find_equidistant_cardinal_sectors(self) -> None:
        """
        Test find_best_sectors for a site with neighbors on all four sides
        roughly spaced 90 degrees apart
        """
        from_site = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
        )
        to_sites = [
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=1.1, utm_y=0.9, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=0.95, utm_y=-1.05, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=-1.05, utm_y=-0.90, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=-1, utm_y=1, utm_epsg=32631, altitude=0
                ),
            ),
        ]
        scan_range = 70

        # Test with 4 nodes each with 1 sector
        nodes = find_best_equidistant_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=4,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
        )

        self.assertEqual(len(nodes), 4)
        for node in nodes:
            self.assertEqual(len(node), 1)
        self.assertEqual(abs(angle_delta(nodes[0][0], nodes[1][0])), 90)
        self.assertEqual(abs(angle_delta(nodes[1][0], nodes[2][0])), 90)
        self.assertEqual(abs(angle_delta(nodes[2][0], nodes[3][0])), 90)
        self.assertEqual(abs(angle_delta(nodes[3][0], nodes[0][0])), 90)

        # Each sector should be approximately aligned with each link
        for i in range(4):
            self.assertTrue(
                abs(
                    nodes[i][0]
                    - math.degrees(
                        math.atan2(to_sites[i].utm_x, to_sites[i].utm_y)
                    )
                    % 360
                )
                < 5
            )

    def test_find_equidistant_many_sectors(self) -> None:
        """
        Test find_best_equidistant_sectors for a site with many randomly
        distributed neighbors
        """
        from_site = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
        )
        rng = random.Random(0)
        num_neighbors = 20
        to_sites = []
        for _ in range(num_neighbors):
            to_sites.append(
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(
                        utm_x=(2 * rng.random() - 1),
                        utm_y=(2 * rng.random() - 1),
                        utm_epsg=32631,
                        altitude=0,
                    ),
                )
            )
        scan_range = 70

        # Test with 4 nodes each with 1 sector
        nodes = find_best_equidistant_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=4,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
        )

        self.assertEqual(len(nodes), 4)
        for node in nodes:
            self.assertEqual(len(node), 1)
        self.assertEqual(abs(angle_delta(nodes[0][0], nodes[1][0])), 90)
        self.assertEqual(abs(angle_delta(nodes[1][0], nodes[2][0])), 90)
        self.assertEqual(abs(angle_delta(nodes[2][0], nodes[3][0])), 90)
        self.assertEqual(abs(angle_delta(nodes[3][0], nodes[0][0])), 90)

        # Test with 2 nodes each with 2 sectors
        nodes = find_best_equidistant_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=2,
            number_of_sectors_per_node=2,
            horizontal_scan_range=scan_range,
        )

        self.assertEqual(len(nodes), 2)
        for node in nodes:
            self.assertEqual(len(node), 2)
        self.assertEqual(abs(angle_delta(nodes[0][0], nodes[0][1])), scan_range)
        self.assertEqual(
            abs(angle_delta(nodes[0][1], nodes[1][0])),
            (360 - 2 * scan_range) / 2,
        )
        self.assertEqual(abs(angle_delta(nodes[1][0], nodes[1][1])), scan_range)
        self.assertEqual(
            abs(angle_delta(nodes[1][1], nodes[0][0])),
            (360 - 2 * scan_range) / 2,
        )

        # Test with 1 node with 1 sector
        nodes = find_best_equidistant_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=1,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
        )

        self.assertEqual(len(nodes), 1)
        for node in nodes:
            self.assertEqual(len(node), 1)

        # Test with a larger scan range
        scan_range = 120
        nodes = find_best_equidistant_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=4,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
        )

        self.assertEqual(len(nodes), 3)
        for node in nodes:
            self.assertEqual(len(node), 1)
        self.assertEqual(abs(angle_delta(nodes[0][0], nodes[1][0])), scan_range)
        self.assertEqual(abs(angle_delta(nodes[1][0], nodes[2][0])), scan_range)
        self.assertEqual(abs(angle_delta(nodes[2][0], nodes[0][0])), scan_range)

        scan_range = 360
        nodes = find_best_equidistant_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=4,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
        )
        self.assertEqual(len(nodes), 1)
        for node in nodes:
            self.assertEqual(len(node), 1)


class TestSimpleFindBestSectors(TestCase):
    def test_get_sector_azimuths_from_node_center(self) -> None:
        """
        Test helper function that computes sector azimuths from node center --
        should be evenly spaced sectors one scan range apart.
        """
        self.assertEqual(
            list(get_sector_azimuths_from_node_center(0, 0, 90)), []
        )
        self.assertEqual(
            list(get_sector_azimuths_from_node_center(0, 1, 90)), [0]
        )
        self.assertEqual(
            list(get_sector_azimuths_from_node_center(0, 2, 90)), [315, 45]
        )
        self.assertEqual(
            list(get_sector_azimuths_from_node_center(0, 3, 90)), [270, 0, 90]
        )
        self.assertEqual(
            list(get_sector_azimuths_from_node_center(0, 3, 0.8)),
            [359.2, 0, 0.8],
        )

    def test_find_two_cluster_sectors(self) -> None:
        """
        Test find_best_sectors for a site with neighbors clustered on either
        side of it
        """
        from_site = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
        )
        to_sites = [
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=1.0, utm_y=0.1, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=1.1, utm_y=-0.2, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=-1.3, utm_y=-0.1, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=-0.9, utm_y=0.15, utm_epsg=32631, altitude=0
                ),
            ),
        ]
        scan_range = 70

        # Test with 4 nodes each with 1 sector
        nodes = find_best_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=4,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )

        self.assertEqual(len(nodes), 2)
        for node in nodes:
            self.assertEqual(len(node), 1)
        self.assertGreaterEqual(
            abs(angle_delta(nodes[0][0], nodes[1][0])), scan_range
        )

    def test_find_cardinal_sectors(self) -> None:
        """
        Test find_best_sectors for a site with neighbors on all four sides
        roughly spaced 90 degrees apart
        """
        from_site = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
        )
        to_sites = [
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=1.1, utm_y=0.9, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=0.95, utm_y=-1.05, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=-1.05, utm_y=-0.90, utm_epsg=32631, altitude=0
                ),
            ),
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(
                    utm_x=-1, utm_y=1, utm_epsg=32631, altitude=0
                ),
            ),
        ]
        scan_range = 70

        # Test with 4 nodes each with 1 sector
        nodes = find_best_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=4,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )

        self.assertEqual(len(nodes), 4)
        for node in nodes:
            self.assertEqual(len(node), 1)
        self.assertGreaterEqual(
            abs(angle_delta(nodes[0][0], nodes[1][0])), scan_range
        )
        self.assertGreaterEqual(
            abs(angle_delta(nodes[1][0], nodes[2][0])), scan_range
        )
        self.assertGreaterEqual(
            abs(angle_delta(nodes[2][0], nodes[3][0])), scan_range
        )
        self.assertGreaterEqual(
            abs(angle_delta(nodes[3][0], nodes[0][0])), scan_range
        )

        # Each sector should be approximately aligned with each link
        for i in range(4):
            self.assertTrue(
                abs(
                    nodes[i][0]
                    - math.degrees(
                        math.atan2(to_sites[i].utm_x, to_sites[i].utm_y)
                    )
                    % 360
                )
                < 5
            )

    def test_find_many_sectors(self) -> None:
        """
        Test find_best_sectors for a site with many randomly distributed
        neighbors
        """
        from_site = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
        )
        rng = random.Random(0)
        num_neighbors = 20
        to_sites = []
        for _ in range(num_neighbors):
            to_sites.append(
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(
                        utm_x=(2 * rng.random() - 1),
                        utm_y=(2 * rng.random() - 1),
                        utm_epsg=32631,
                        altitude=0,
                    ),
                )
            )
        scan_range = 70

        # Test with 4 nodes each with 1 sector
        nodes = find_best_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=4,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )

        self.assertEqual(len(nodes), 4)
        for node in nodes:
            self.assertEqual(len(node), 1)
        self.assertGreaterEqual(
            abs(angle_delta(nodes[0][0], nodes[1][0])), scan_range
        )
        self.assertGreaterEqual(
            abs(angle_delta(nodes[1][0], nodes[2][0])), scan_range
        )
        self.assertGreaterEqual(
            abs(angle_delta(nodes[2][0], nodes[3][0])), scan_range
        )
        self.assertGreaterEqual(
            abs(angle_delta(nodes[3][0], nodes[0][0])), scan_range
        )

        # Test with 2 nodes each with 2 sectors
        nodes = find_best_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=2,
            number_of_sectors_per_node=2,
            horizontal_scan_range=scan_range,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )

        self.assertEqual(len(nodes), 2)
        for node in nodes:
            self.assertEqual(len(node), 2)
        self.assertEqual(abs(angle_delta(nodes[0][0], nodes[0][1])), scan_range)
        self.assertGreaterEqual(
            abs(angle_delta(nodes[0][1], nodes[1][0])), scan_range
        )
        self.assertEqual(abs(angle_delta(nodes[1][0], nodes[1][1])), scan_range)
        self.assertGreaterEqual(
            abs(angle_delta(nodes[1][1], nodes[0][0])), scan_range
        )

        # Test with 1 node with 1 sector
        nodes = find_best_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=1,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )

        self.assertEqual(len(nodes), 1)
        for node in nodes:
            self.assertEqual(len(node), 1)

        # Test with a larger scan range
        scan_range = 120
        nodes = find_best_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=4,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )

        self.assertEqual(len(nodes), 3)
        for node in nodes:
            self.assertEqual(len(node), 1)
        self.assertEqual(abs(angle_delta(nodes[0][0], nodes[1][0])), scan_range)
        self.assertEqual(abs(angle_delta(nodes[1][0], nodes[2][0])), scan_range)
        self.assertEqual(abs(angle_delta(nodes[2][0], nodes[0][0])), scan_range)

        scan_range = 360
        nodes = find_best_sectors(
            site=from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=4,
            number_of_sectors_per_node=1,
            horizontal_scan_range=scan_range,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertEqual(len(nodes), 1)
        for node in nodes:
            self.assertEqual(len(node), 1)


class TestFindBestSectors(TestCase):
    def setUp(self) -> None:
        self.from_site = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=10, utm_y=10, utm_epsg=32631),
        )
        self.dn_dn_sector_limit = 2
        self.dn_total_sector_limit = 7
        self.number_of_nodes = 4
        self.number_of_sectors_per_node = 1
        self.horizontal_scan_range = 70

    @patch(
        f"{TEST_PREFIX}.bearing_in_degrees",
        MagicMock(return_value=[0, 90, 180, 270]),
    )
    def test_right_angle_sectors(self) -> None:
        """
        Test a simple case where the link_angles for four neighbor_site_list are
        0, 90, 180, 270, and the sector position will be exactly the same as
        link_angles and mets = 0
        """
        sectors = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=4
            * [
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=self.horizontal_scan_range,
            dn_dn_sector_limit=self.dn_dn_sector_limit,
            dn_total_sector_limit=self.dn_total_sector_limit,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertIsNotNone(sectors)
        self.assertEqual(len(sectors), 4)
        self.assertEqual(sectors[0], 0)
        self.assertEqual(sectors[1], 90)
        self.assertEqual(sectors[2], 180)
        self.assertEqual(sectors[3], 270)

        # Multiple sensor per node
        sectors = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=4
            * [
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=2,
            horizontal_scan_range=self.horizontal_scan_range,
            dn_dn_sector_limit=self.dn_dn_sector_limit,
            dn_total_sector_limit=self.dn_total_sector_limit,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertIsNotNone(sectors)
        self.assertEqual(len(sectors), 2)
        self.assertEqual(len(sectors[0]), 2)
        self.assertEqual(len(sectors[1]), 2)
        self.assertEqual(sectors[0][0], 10)
        self.assertEqual(sectors[0][1], 80)
        self.assertEqual(sectors[1][0], 190)
        self.assertEqual(sectors[1][1], 260)

        # Multi-sector but sectors can only handle one link each, should
        # revert to old strategy
        sectors = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=4
            * [
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=2,
            horizontal_scan_range=90,
            dn_dn_sector_limit=1,
            dn_total_sector_limit=self.dn_total_sector_limit,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertIsNotNone(sectors)
        self.assertEqual(len(sectors), 2)
        self.assertEqual(len(sectors[0]), 2)
        self.assertEqual(len(sectors[1]), 2)
        self.assertEqual(sectors[0][0], 0)
        self.assertEqual(sectors[0][1], 90)
        self.assertEqual(sectors[1][0], 180)
        self.assertEqual(sectors[1][1], 270)

    @patch(f"{TEST_PREFIX}.bearing_in_degrees", MagicMock(return_value=[0, 30]))
    def test_dn_dn_sector_limit(self) -> None:
        """
        Test whether dn_dn_sector_limit works
        We test two case that are almost the same except the dn_dn_sector_limit
        The best solution in the case where dn_dn_sector_limit = 2 is excluded in
        the case where dn_dn_sector_limit = 1 because if we have a sector with
        degree in [345, 360) or [0, 45], it will have 2 dns in this sector
        """
        to_sites = [
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
            )
        ] * 2
        horizontal_scan_range = 90
        sectors_with_limit_one = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=horizontal_scan_range,
            dn_dn_sector_limit=1,
            dn_total_sector_limit=self.dn_total_sector_limit,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertIsNotNone(sectors_with_limit_one)
        self.assertEqual(len(sectors_with_limit_one), 2)
        self.assertEqual(sectors_with_limit_one[0][0], 60)
        self.assertEqual(sectors_with_limit_one[1][0], 330)

        sectors_with_limit_two = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=horizontal_scan_range,
            dn_dn_sector_limit=self.dn_dn_sector_limit,
            dn_total_sector_limit=self.dn_total_sector_limit,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertIsNotNone(sectors_with_limit_two)
        self.assertEqual(len(sectors_with_limit_two), 1)
        self.assertEqual(sectors_with_limit_two[0], 15)

    @patch(
        f"{TEST_PREFIX}.bearing_in_degrees",
        MagicMock(return_value=[100, 90, 80, 110]),
    )
    def test_dn_total_sector_limit(self) -> None:
        """
        Similar to test_dn_dn_sector_limit but to test dn_total_sector_limit
        Also test when the link_angles are not in order
        """
        to_sites = 4 * [
            SampleSite(
                site_type=SiteType.CN,
                location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
            )
        ]
        horizontal_scan_range = 90
        sectors_with_limit_four = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=horizontal_scan_range,
            dn_dn_sector_limit=self.dn_dn_sector_limit,
            dn_total_sector_limit=4,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertIsNotNone(sectors_with_limit_four)
        self.assertEqual(len(sectors_with_limit_four), 1)
        self.assertEqual(sectors_with_limit_four[0][0], 96)

        sectors_with_limit_three = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=horizontal_scan_range,
            dn_dn_sector_limit=self.dn_dn_sector_limit,
            dn_total_sector_limit=3,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertIsNotNone(sectors_with_limit_three)
        self.assertEqual(len(sectors_with_limit_three), 2)
        self.assertEqual(sectors_with_limit_three[0][0], 36)
        self.assertEqual(sectors_with_limit_three[1][0], 126)

        # Both dn_dn_sector_limit and dn_total_sector_limit exclude the
        # best solution without limitation
        to_sites = 2 * [
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
            )
        ] + 2 * [
            SampleSite(
                site_type=SiteType.CN,
                location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
            )
        ]
        sectors_with_limit_one_three = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=to_sites,
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=horizontal_scan_range,
            dn_dn_sector_limit=1,
            dn_total_sector_limit=3,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertIsNotNone(sectors_with_limit_one_three)
        self.assertEqual(len(sectors_with_limit_one_three), 2)
        self.assertEqual(sectors_with_limit_one_three[0][0], 51)
        self.assertEqual(sectors_with_limit_one_three[1][0], 141)

    @patch(
        f"{TEST_PREFIX}.bearing_in_degrees",
        MagicMock(return_value=[0, 70, 90, 180, 260, 265, 270]),
    )
    def test_non_equidistant_sectors(self) -> None:
        """
        A simple test case for non-equidistant sectors
        """
        sectors = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=7
            * [
                SampleSite(
                    site_type=SiteType.CN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=self.horizontal_scan_range,
            dn_dn_sector_limit=self.dn_dn_sector_limit,
            dn_total_sector_limit=self.dn_total_sector_limit,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertIsNotNone(sectors)
        self.assertEqual(len(sectors), 4)
        self.assertEqual(sectors[0], 0)
        self.assertEqual(sectors[1], 81)
        self.assertEqual(sectors[2], 180)
        self.assertEqual(sectors[3], 264)

    @patch(
        f"{TEST_PREFIX}.bearing_in_degrees",
        MagicMock(return_value=[0, 90, 180, 270]),
    )
    def test_no_solution(self) -> None:
        """
        Test case where there's no good solution. Sector placement should
        return nothing.
        """
        sectors = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=4
            * [
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=240,
            dn_dn_sector_limit=1,
            dn_total_sector_limit=1,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertEqual(len(sectors), 0)

    @patch(f"{TEST_PREFIX}.bearing_in_degrees")
    @patch(f"{TEST_PREFIX}.haversine_distance")
    def test_long_distance_sectors(
        self,
        haversine_distance_func: MagicMock,
        bearing_in_degrees_func: MagicMock,
    ) -> None:
        """
        Test sector center should be closer to long distance links if possible
        """
        bearing_in_degrees_func.return_value = [0, 70, 80]
        haversine_distance_func.return_value = [50, 50, 50]
        sectors_s = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=3
            * [
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=90,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertEqual(len(sectors_s), 2)

        haversine_distance_func.return_value = [300, 50, 50]
        sectors_l = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=3
            * [
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=90,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertEqual(len(sectors_l), 2)
        # The angle delta to the to-site at 0 degree is smaller in long distance case
        self.assertLess(
            min(min(s[0], abs(FULL_ROTATION_ANGLE - s[0])) for s in sectors_l),
            sectors_s[0][0],
        )

    @patch(
        f"{TEST_PREFIX}.bearing_in_degrees",
        MagicMock(return_value=[160]),
    )
    @patch(
        f"{TEST_PREFIX}.haversine_distance",
        MagicMock(return_value=[100]),
    )
    def test_node_with_multi_sectors(self) -> None:
        nodes = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=[
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=1,
            number_of_sectors_per_node=2,
            horizontal_scan_range=140,
            dn_dn_sector_limit=2,
            dn_total_sector_limit=7,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertIsNotNone(nodes)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0][0], 20)
        self.assertEqual(nodes[0][1], 160)

    @patch(
        f"{TEST_PREFIX}.bearing_in_degrees",
        MagicMock(return_value=[0, 30]),
    )
    def test_link_type_weighted_sectors(self) -> None:
        """
        Test link type weight in calculate sector position
        """
        # Sector boresight in the middle of the 2 DN links
        neighbor_site_list = 2 * [
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
            )
        ]
        sectors = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=neighbor_site_list,
            number_of_nodes=1,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=self.horizontal_scan_range,
            dn_dn_sector_limit=self.dn_dn_sector_limit,
            dn_total_sector_limit=self.dn_total_sector_limit,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertEqual(len(sectors), 1)
        self.assertEqual(sectors[0], 15)

        # Sector boresight close to the DN link
        neighbor_site_list = [
            SampleSite(
                site_type=SiteType.CN,
                location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
            )
        ]
        neighbor_site_list.append(
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
            )
        )
        sectors = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=neighbor_site_list,
            number_of_nodes=1,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=self.horizontal_scan_range,
            dn_dn_sector_limit=self.dn_dn_sector_limit,
            dn_total_sector_limit=self.dn_total_sector_limit,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=BACKHAUL_LINK_TYPE_WEIGHT,
            sector_channel_list=None,
        )
        self.assertEqual(len(sectors), 1)
        self.assertEqual(sectors[0], 27)

    @patch(f"{TEST_PREFIX}.bearing_in_degrees")
    @patch(f"{TEST_PREFIX}.law_of_cosines_spherical")
    def test_angle_deployment_rules(
        self,
        law_of_cosines_spherical_func: MagicMock,
        bearing_in_degrees_func: MagicMock,
    ) -> None:
        """
        Test angle deployment rules
        """
        bearing_in_degrees_func.return_value = [0, 30, 60, 90]
        law_of_cosines_spherical_func.return_value = (30, 5)
        # Base case not check any angle deployment rules
        # 3 sectors at [45, 96, 354]
        nodes_base = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=4
            * [
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=50,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertEqual(len(nodes_base), 3)

        # Different sector angle violation
        # no solution to cover all links, return 1 sector at [78]
        nodes_diff_sector = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=4
            * [
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=50,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=35,
            near_far_angle_limit=None,
            near_far_length_ratio=None,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertEqual(len(nodes_diff_sector), 1)

        # Near-far ratio violation
        # no solution to cover all links, return 1 sector at [78]
        nodes_near_far = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=4
            * [
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=50,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=None,
            near_far_angle_limit=45,
            near_far_length_ratio=3,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertEqual(len(nodes_near_far), 1)

        # No angle deployment rules violation under the configured values
        # return is the same as nodes_base
        nodes_no_violation = find_best_sectors(
            site=self.from_site,
            neighbor_site_list=4
            * [
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
                )
            ],
            number_of_nodes=self.number_of_nodes,
            number_of_sectors_per_node=self.number_of_sectors_per_node,
            horizontal_scan_range=50,
            dn_dn_sector_limit=None,
            dn_total_sector_limit=None,
            diff_sector_angle_limit=20,
            near_far_angle_limit=45,
            near_far_length_ratio=6,
            backhaul_link_type_weight=None,
            sector_channel_list=None,
        )
        self.assertEqual(len(nodes_no_violation), 3)


class TestCreateSectors(TestCase):
    def test_create_dns(self) -> None:
        """
        Test DN sector creation on a random topology
        """
        rng = random.Random(0)
        num_sites = 20
        sites = []
        for _ in range(num_sites):
            sites.append(
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(
                        utm_x=(2 * rng.random() - 1),
                        utm_y=(2 * rng.random() - 1),
                        utm_epsg=32631,
                        altitude=0,
                    ),
                )
            )
        links = [
            Link(tx_site=pair[0], rx_site=pair[1])
            for pair in itertools.permutations(sites, 2)
        ]

        topology = Topology(sites=sites, links=links)
        for link in topology.links.values():
            link.clear_sectors()
        for site in topology.sites.values():
            site._device = DeviceData(
                device_sku="SAMPLE_DN_DEVICE",
                sector_params=SectorParams(
                    number_sectors_per_node=1, horizontal_scan_range=360
                ),
                number_of_nodes_per_site=1,
                device_type=DeviceType.DN,
            )

        create_dn_sectors(topology)
        add_sectors_to_links(topology, False, None)

        # All sites get a sector; all links get sectors
        self.assertEqual(len(topology.sectors), num_sites)
        for link in topology.links.values():
            self.assertIsNotNone(link.tx_sector)
            self.assertIsNotNone(link.rx_sector)

        topology = Topology(sites=sites, links=links)
        for link in topology.links.values():
            link.clear_sectors()
        for site in topology.sites.values():
            site._device = DeviceData(
                device_sku="SAMPLE_DN_DEVICE",
                sector_params=SectorParams(
                    number_sectors_per_node=1, horizontal_scan_range=90
                ),
                node_capex=250,
                number_of_nodes_per_site=4,
                device_type=DeviceType.DN,
            )

        create_dn_sectors(topology)
        add_sectors_to_links(topology, False, None)

        # All sites get at least one sector and at most 4; all links get sectors
        self.assertLessEqual(len(topology.sectors), 4 * num_sites)
        self.assertGreaterEqual(len(topology.sectors), num_sites)
        for link in topology.links.values():
            self.assertIsNotNone(link.tx_sector)
            self.assertIsNotNone(link.rx_sector)

    def test_create_cns(self) -> None:
        """
        Test CN sector creation on a random topology
        """
        rng = random.Random(0)
        num_dns = 3
        num_cns = 10
        dns = []
        for _ in range(num_dns):
            dns.append(
                SampleSite(
                    site_type=SiteType.DN,
                    location=GeoLocation(
                        utm_x=(2 * rng.random() - 1),
                        utm_y=(2 * rng.random() - 1),
                        utm_epsg=32631,
                        altitude=0,
                    ),
                    device=DeviceData(
                        device_sku="SAMPLE_DN_DEVICE",
                        sector_params=SectorParams(
                            number_sectors_per_node=1, horizontal_scan_range=90
                        ),
                        node_capex=250,
                        number_of_nodes_per_site=4,
                        device_type=DeviceType.DN,
                    ),
                )
            )
        links = [
            Link(tx_site=pair[0], rx_site=pair[1])
            for pair in itertools.permutations(dns, 2)
        ]
        cns = []
        for _ in range(num_cns):
            cn = SampleSite(
                site_type=SiteType.CN,
                location=GeoLocation(
                    utm_x=(2 * rng.random() - 1),
                    utm_y=(2 * rng.random() - 1),
                    utm_epsg=32631,
                    altitude=0,
                ),
                device=DeviceData(
                    device_sku="SAMPLE_CN_DEVICE",
                    sector_params=SectorParams(
                        number_sectors_per_node=1, horizontal_scan_range=360
                    ),
                    node_capex=250,
                    number_of_nodes_per_site=1,
                    device_type=DeviceType.CN,
                ),
            )
            cns.append(cn)
            for dn in dns:
                links.append(Link(tx_site=dn, rx_site=cn))

        topology = Topology(sites=dns + cns, links=links)
        create_dn_sectors(topology)
        create_cn_sectors(topology)
        add_sectors_to_links(topology, False, None)

        # All DNs get at least one sector and at most 4; all CNs get one sector;
        # all links get sectors
        self.assertLessEqual(len(topology.sectors), 4 * num_dns + num_cns)
        self.assertGreaterEqual(len(topology.sectors), num_dns + num_cns)
        self.assertEqual(
            len(
                [
                    sector
                    for sector in topology.sectors.values()
                    if sector.sector_type == SectorType.CN
                ]
            ),
            num_cns,
        )
        for link in topology.links.values():
            self.assertIsNotNone(link.tx_sector)
            self.assertIsNotNone(link.rx_sector)

    def test_create_dn_without_neighbors(self) -> None:
        """
        DNs without neighbors get no sectors
        """
        dn_site = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
        )

        topology = Topology(sites=[dn_site])
        create_dn_sectors(topology)
        self.assertEqual(len(topology.sectors), 0)

    def test_create_cn_without_neighbors(self) -> None:
        """
        CNs without neighbors get no sectors
        """
        cn_site = SampleSite(
            site_type=SiteType.CN,
            location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631, altitude=0),
        )

        topology = Topology(sites=[cn_site])
        create_cn_sectors(topology)
        self.assertEqual(len(topology.sectors), 0)
