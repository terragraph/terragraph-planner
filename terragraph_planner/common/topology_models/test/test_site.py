# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from terragraph_planner.common.configuration.configs import (
    DeviceData,
    SectorParams,
)
from terragraph_planner.common.configuration.enums import (
    DeviceType,
    LocationType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.exceptions import TopologyException
from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.topology_models.test.helper import SampleSite


class TestSite(TestCase):
    def test_update_site_id(self) -> None:
        """
        Test whether site id is set and updated correctly when the dependent
        attributes change.
        """
        site1 = SampleSite(
            site_type=SiteType.CN,
            location=GeoLocation(latitude=0.1, longitude=1.2),
        )
        site2 = SampleSite(
            site_type=SiteType.CN,
            location=GeoLocation(latitude=1.2, longitude=0.1),
        )
        self.assertNotEqual(site1.site_id, site2.site_id)
        site3 = SampleSite(
            site_type=SiteType.DN,
            location=GeoLocation(latitude=0.1, longitude=1.2),
        )
        self.assertNotEqual(site1.site_id, site3.site_id)
        site4 = SampleSite(
            site_type=SiteType.CN,
            location=GeoLocation(latitude=0.1, longitude=1.2),
            device=DeviceData(
                device_sku="SAMPLE_DEVICE2",
                sector_params=SectorParams(),
                device_type=DeviceType.CN,
            ),
        )
        self.assertNotEqual(site1.site_id, site4.site_id)

        with self.assertRaisesRegex(AttributeError, "can't set attribute"):
            site1.latitude = 1.2  # pyre-ignore
        with self.assertRaisesRegex(AttributeError, "can't set attribute"):
            site1.site_type = SiteType.DN  # pyre-ignore
        with self.assertRaisesRegex(AttributeError, "can't set attribute"):
            site1.device = DeviceData(  # pyre-ignore
                device_sku="SAMPLE_DEVICE2", sector_params=SectorParams()
            )

    def test_status_type(self) -> None:
        """
        Test whether or not the status type can be set correctly.
        """
        site = SampleSite(
            site_type=SiteType.CN,
            location=GeoLocation(latitude=0.1, longitude=1.2),
        )
        # The default is candidate
        self.assertEqual(site.status_type, StatusType.CANDIDATE)
        site.status_type = StatusType.PROPOSED
        self.assertEqual(site.status_type, StatusType.PROPOSED)
        # Cannot set the status to an immutable status
        with self.assertRaises(TopologyException):
            site.status_type = StatusType.EXISTING
        # Cannot set the status of a site with immutable status
        site = SampleSite(
            site_type=SiteType.CN,
            location=GeoLocation(latitude=0.1, longitude=1.2),
            status_type=StatusType.UNAVAILABLE,
        )
        with self.assertRaises(TopologyException):
            site.status_type = StatusType.PROPOSED

    def test_valid_site(self) -> None:
        with self.assertRaisesRegex(
            TopologyException,
            "Building id must be provided when the location type of a site is ROOFTOP",
        ):
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(latitude=0, longitude=0),
                location_type=LocationType.ROOFTOP,
                building_id=None,
            )

        with self.assertRaisesRegex(
            TopologyException,
            "Building id must not be provided when the location type of a site is not ROOFTOP",
        ):
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(latitude=0, longitude=0),
                location_type=LocationType.UNKNOWN,
                building_id=1,
            )

        with self.assertRaisesRegex(
            TopologyException,
            "Building id must not be provided when the location type of a site is not ROOFTOP",
        ):
            SampleSite(
                site_type=SiteType.DN,
                location=GeoLocation(latitude=0, longitude=0),
                location_type=LocationType.STREET_LEVEL,
                building_id=1,
            )

        with self.assertRaisesRegex(
            TopologyException,
            "Site has a device of inconsistent device type",
        ):
            SampleSite(
                site_type=SiteType.CN,
                device=DeviceData(
                    device_sku="TEST",
                    device_type=DeviceType.DN,
                    sector_params=SectorParams(),
                ),
                location=GeoLocation(latitude=0, longitude=0),
            )
