# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase
from unittest.mock import MagicMock, patch

from terragraph_planner.common.configuration.enums import SiteType, StatusType
from terragraph_planner.common.exceptions import TopologyException
from terragraph_planner.common.geos import GeoLocation, law_of_cosines_spherical
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.test.helper import (
    SampleSite,
    square_topology,
)


class TestLink(TestCase):
    def setUp(self) -> None:
        self.site1 = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(latitude=0.1, longitude=1.2, altitude=0.0),
        )
        self.site2 = SampleSite(
            site_type=SiteType.CN,
            location=GeoLocation(latitude=0.15, longitude=1.25, altitude=4.0),
        )

    def test_key_attributes(self) -> None:
        link = Link(tx_site=self.site1, rx_site=self.site2)
        with self.assertRaisesRegex(AttributeError, "can't set attribute"):
            link.tx_site = self.site2  # pyre-ignore
        with self.assertRaisesRegex(AttributeError, "can't set attribute"):
            link.rx_site = self.site1  # pyre-ignore

    @patch(
        "terragraph_planner.common.topology_models.link.haversine_distance",
        MagicMock(return_value=3.0),
    )
    def test_distance(self) -> None:
        link = Link(tx_site=self.site1, rx_site=self.site2)
        self.assertEqual(link.distance, 5.0)

    def test_sectors(self) -> None:
        sector1 = Sector(
            site=self.site1, node_id=0, position_in_node=0, ant_azimuth=0
        )
        sector2 = Sector(
            site=self.site2, node_id=0, position_in_node=0, ant_azimuth=0
        )
        sector3 = Sector(
            site=self.site1, node_id=1, position_in_node=0, ant_azimuth=0
        )
        sector4 = Sector(
            site=self.site2, node_id=1, position_in_node=0, ant_azimuth=0
        )
        link = Link(tx_sector=sector1, rx_sector=sector2)
        link.tx_sector = sector3  # Same site
        link.rx_sector = sector4  # Same site
        with self.assertRaises(TopologyException):
            link.tx_sector = sector2
        with self.assertRaises(TopologyException):
            link.rx_sector = sector1
        with self.assertRaises(AttributeError):
            link.tx_sector = None  # pyre-ignore
        with self.assertRaises(AttributeError):
            link.rx_sector = None  # pyre-ignore
        link.clear_sectors()
        self.assertIsNone(link.tx_sector)
        self.assertIsNone(link.rx_sector)
        with self.assertRaisesRegex(
            TopologyException, "The link's sectors must both be set or None"
        ):
            link = Link(tx_sector=sector1, rx_site=self.site2)
        with self.assertRaisesRegex(
            TopologyException, "The link's sectors must both be set or None"
        ):
            link = Link(tx_site=self.site1, rx_sector=sector2)

    def test_status(self) -> None:
        link = Link(tx_site=self.site1, rx_site=self.site2)
        with self.assertRaisesRegex(
            TopologyException,
            "The status of the link with a candidate tx or rx site cannot be proposed.",
        ):
            link.status_type = StatusType.PROPOSED
        self.site1.status_type = StatusType.UNREACHABLE
        with self.assertRaisesRegex(
            TopologyException,
            "The status of the link with an unreachable tx or rx site must be unreachable.",
        ):
            link.status_type = StatusType.CANDIDATE
        with self.assertRaisesRegex(
            TopologyException,
            "The tx site and rx site of an existing link must be existing.",
        ):
            link = Link(
                tx_site=self.site1,
                rx_site=self.site2,
                status_type=StatusType.EXISTING,
            )
        site3 = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(latitude=0.1, longitude=1.2, altitude=0.0),
            status_type=StatusType.UNAVAILABLE,
        )
        with self.assertRaisesRegex(
            TopologyException,
            "A link from/to an unavailable sites must be unavailable.",
        ):
            link = Link(
                tx_site=site3,
                rx_site=self.site2,
                status_type=StatusType.PROPOSED,
            )


class TestDeviationAngles(TestCase):
    def setUp(self) -> None:
        self.topology = square_topology()

    def test_boresight_links(self) -> None:
        """
        Test the values for horizontal and vertical angle deviations from
        boresight when the link is in the boresight
        """
        # The sectors for DN1-DN2 links are pointed at each otehr
        # The antenna azimuth should be almost the same as the tx/rx beam azimuths
        self.assertAlmostEqual(
            self.topology.sectors["DN1-0-0-DN"].ant_azimuth,
            self.topology.links["DN1-DN2"].tx_beam_azimuth,
            delta=0.1,
        )
        self.assertAlmostEqual(
            self.topology.sectors["DN2-1-0-DN"].ant_azimuth,
            self.topology.links["DN1-DN2"].rx_beam_azimuth,
            delta=0.1,
        )
        self.assertAlmostEqual(
            self.topology.sectors["DN2-1-0-DN"].ant_azimuth,
            self.topology.links["DN2-DN1"].tx_beam_azimuth,
            delta=0.1,
        )
        self.assertAlmostEqual(
            self.topology.sectors["DN1-0-0-DN"].ant_azimuth,
            self.topology.links["DN2-DN1"].rx_beam_azimuth,
            delta=0.1,
        )

        # As a result, the link deviations should be close to 0
        self.assertAlmostEqual(
            self.topology.links["DN1-DN2"].tx_dev, 0, delta=0.1
        )
        self.assertAlmostEqual(
            self.topology.links["DN1-DN2"].rx_dev, 0, delta=0.1
        )
        self.assertEqual(self.topology.links["DN1-DN2"].el_dev, 0)
        self.assertAlmostEqual(
            self.topology.links["DN2-DN1"].tx_dev, 0, delta=0.1
        )
        self.assertAlmostEqual(
            self.topology.links["DN2-DN1"].rx_dev, 0, delta=0.1
        )
        self.assertEqual(self.topology.links["DN2-DN1"].el_dev, 0)

        # The tx/rx beam azimuths of opposing links should be the same
        self.assertAlmostEqual(
            self.topology.links["DN2-DN1"].tx_beam_azimuth,
            self.topology.links["DN1-DN2"].rx_beam_azimuth,
            delta=1e-3,
        )
        self.assertAlmostEqual(
            self.topology.links["DN1-DN2"].tx_beam_azimuth,
            self.topology.links["DN2-DN1"].rx_beam_azimuth,
            delta=1e-3,
        )

        # The sectors for the DN3-DN4 links are pointed at each other
        # The antenna azimuth should be almost the same as the tx/rx beam azimuths
        self.assertAlmostEqual(
            self.topology.sectors["DN3-1-0-DN"].ant_azimuth,
            self.topology.links["DN3-DN4"].tx_beam_azimuth,
            delta=0.1,
        )
        self.assertAlmostEqual(
            self.topology.sectors["DN4-1-0-DN"].ant_azimuth,
            self.topology.links["DN3-DN4"].rx_beam_azimuth,
            delta=0.1,
        )
        self.assertAlmostEqual(
            self.topology.sectors["DN4-1-0-DN"].ant_azimuth,
            self.topology.links["DN4-DN3"].tx_beam_azimuth,
            delta=0.1,
        )
        self.assertAlmostEqual(
            self.topology.sectors["DN3-1-0-DN"].ant_azimuth,
            self.topology.links["DN4-DN3"].rx_beam_azimuth,
            delta=0.1,
        )

        # As a result, the link deviations should be close to 0
        self.assertAlmostEqual(
            self.topology.links["DN3-DN4"].tx_dev, 0, delta=0.1
        )
        self.assertAlmostEqual(
            self.topology.links["DN3-DN4"].rx_dev, 0, delta=0.1
        )
        self.assertEqual(self.topology.links["DN3-DN4"].el_dev, 0)
        self.assertAlmostEqual(
            self.topology.links["DN4-DN3"].tx_dev, 0, delta=0.1
        )
        self.assertAlmostEqual(
            self.topology.links["DN4-DN3"].rx_dev, 0, delta=0.1
        )
        self.assertEqual(self.topology.links["DN4-DN3"].el_dev, 0)

        # The tx/rx beam azimuths of opposing links should be the same
        self.assertAlmostEqual(
            self.topology.links["DN3-DN4"].tx_beam_azimuth,
            self.topology.links["DN4-DN3"].rx_beam_azimuth,
            delta=1e-3,
        )
        self.assertAlmostEqual(
            self.topology.links["DN4-DN3"].tx_beam_azimuth,
            self.topology.links["DN3-DN4"].rx_beam_azimuth,
            delta=1e-3,
        )

    def test_deviation_from_boresight(self) -> None:
        """
        Test the deviation from boresight for a sector positioned roughly
        equally between two links
        """

        # The associated links with sector "DN1-1-0-DN" are DN1<->DN4, DN1<->POP5
        self.assertAlmostEqual(
            self.topology.sectors["DN1-1-0-DN"].ant_azimuth,
            (
                self.topology.links["DN1-DN4"].tx_beam_azimuth
                + self.topology.links["DN1-POP5"].tx_beam_azimuth
            )
            / 2,
            delta=0.1,
        )

        self.assertAlmostEqual(
            self.topology.links["DN1-DN4"].tx_dev,
            abs(
                self.topology.links["DN1-DN4"].tx_beam_azimuth
                - self.topology.links["DN1-POP5"].tx_beam_azimuth
            )
            / 2,
            delta=0.1,
        )

    def test_deviation_angle_against_law_of_cosine(self) -> None:
        """
        Test the deviation against the angle between the sites computed using
        the law of cosines
        """
        # Compute the angle between links DN1->DN4 and DN1->POP5
        lat0 = self.topology.sites["DN1"].latitude
        lon0 = self.topology.sites["DN1"].longitude

        lat1 = self.topology.sites["DN4"].latitude
        lon1 = self.topology.sites["DN4"].longitude

        lat2 = self.topology.sites["POP5"].latitude
        lon2 = self.topology.sites["POP5"].longitude

        angle, _ = law_of_cosines_spherical(lat0, lon0, lat1, lon1, lat2, lon2)

        self.assertAlmostEqual(
            self.topology.links["DN1-DN4"].tx_dev, angle / 2, delta=0.1
        )
        self.assertAlmostEqual(
            self.topology.links["DN4-DN1"].rx_dev, angle / 2, delta=0.1
        )
        self.assertAlmostEqual(
            self.topology.links["DN1-POP5"].tx_dev, angle / 2, delta=0.1
        )
        self.assertAlmostEqual(
            self.topology.links["POP5-DN1"].rx_dev, angle / 2, delta=0.1
        )

    def test_deviation_around_true_north(self) -> None:
        """
        Test the deviation around true north where the angles are either close
        to 0 or close to 360
        """
        sites = [
            SampleSite(
                site_id="DN1",
                site_type=SiteType.DN,
                location=GeoLocation(utm_x=0, utm_y=0, utm_epsg=32631),
            ),
            SampleSite(
                site_id="DN2",
                site_type=SiteType.DN,
                location=GeoLocation(utm_x=-5, utm_y=100, utm_epsg=32631),
            ),
        ]

        sectors = [
            Sector(
                site=sites[0],
                node_id=0,
                position_in_node=0,
                ant_azimuth=5,
            ),
            Sector(
                site=sites[1],
                node_id=0,
                position_in_node=0,
                ant_azimuth=200,
            ),
        ]

        links = [
            Link(tx_sector=sectors[0], rx_sector=sectors[1]),
            Link(tx_sector=sectors[1], rx_sector=sectors[0]),
        ]

        # The tx beam azimuth of "DN1-DN2" and rx beam azimuth of "DN2-DN1"
        # should be in (355, 360), but sector azimuth is 5 so deviation should
        # be between (0, 10) and not (350, 355).
        self.assertGreater(links[0].tx_beam_azimuth, 355)
        self.assertLess(links[0].tx_beam_azimuth, 360)
        self.assertGreater(links[0].tx_dev, 0)
        self.assertLess(links[0].tx_dev, 10)

        self.assertGreater(links[1].rx_beam_azimuth, 355)
        self.assertLess(links[1].rx_beam_azimuth, 360)
        self.assertGreater(links[1].rx_dev, 0)
        self.assertLess(links[1].rx_dev, 10)
