# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import unittest

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
from terragraph_planner.common.data_io.input_sites import InputSites
from terragraph_planner.common.exceptions import DataException
from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.topology_models.site import Site


class TestInputSites(unittest.TestCase):
    def test_add_duplicated_site(self) -> None:
        device_list = [
            DeviceData(device_sku="dn_device0", sector_params=SectorParams()),
            DeviceData(device_sku="dn_device1", sector_params=SectorParams()),
        ]
        site_list = InputSites()
        site_list.add_site(
            Site(
                site_type=SiteType.DN,
                location=GeoLocation(longitude=0, latitude=0),
                device=device_list[0],
                status_type=StatusType.CANDIDATE,
                location_type=LocationType.UNKNOWN,
                building_id=None,
                name="",
                number_of_subscribers=None,
            )
        )
        site_list.add_site(
            Site(
                site_type=SiteType.DN,
                location=GeoLocation(longitude=0, latitude=0),
                device=device_list[1],
                status_type=StatusType.CANDIDATE,
                location_type=LocationType.UNKNOWN,
                building_id=None,
                name="",
                number_of_subscribers=None,
            )
        )
        # The above two sites are not duplicated, so there are 2 sites
        self.assertEqual(len(site_list), 2)
        site_list.add_site(
            Site(
                site_type=SiteType.DN,
                location=GeoLocation(longitude=0, latitude=0),
                device=device_list[0],
                status_type=StatusType.CANDIDATE,
                location_type=LocationType.UNKNOWN,
                building_id=None,
                name="",
                number_of_subscribers=None,
            )
        )
        # The new site is duplicated, so the site count is still 2
        self.assertEqual(len(site_list), 2)

    def test_add_site_with_non_empty_name(self) -> None:
        device_list = [
            DeviceData(
                device_sku="dn_device0",
                sector_params=SectorParams(),
                device_type=DeviceType.DN,
            ),
            DeviceData(
                device_sku="dn_device1",
                sector_params=SectorParams(),
                device_type=DeviceType.DN,
            ),
            DeviceData(
                device_sku="dn_device2",
                sector_params=SectorParams(),
                device_type=DeviceType.DN,
            ),
        ]
        site_list = InputSites()
        site0 = Site(
            site_type=SiteType.DN,
            location=GeoLocation(longitude=0, latitude=0),
            device=device_list[0],
            status_type=StatusType.CANDIDATE,
            location_type=LocationType.UNKNOWN,
            building_id=None,
            name="dn0",
            number_of_subscribers=None,
        )
        site_list.add_site(site0)
        self.assertEqual(site0.name, "dn0")
        site1 = Site(
            site_type=SiteType.DN,
            location=GeoLocation(longitude=0, latitude=0),
            device=device_list[1],
            status_type=StatusType.CANDIDATE,
            location_type=LocationType.UNKNOWN,
            building_id=None,
            name="dn0",
            number_of_subscribers=None,
        )
        site_list.add_site(site1)
        self.assertEqual(site1.name, "dn0_dn_device1")
        self.assertEqual(site0.name, "dn0_dn_device0")
        site2 = Site(
            site_type=SiteType.DN,
            location=GeoLocation(longitude=0, latitude=0),
            device=device_list[2],
            status_type=StatusType.CANDIDATE,
            location_type=LocationType.UNKNOWN,
            building_id=None,
            name="dn0",
            number_of_subscribers=None,
        )
        site_list.add_site(site2)
        self.assertEqual(site2.name, "dn0_dn_device2")
        self.assertEqual(site1.name, "dn0_dn_device1")
        self.assertEqual(site0.name, "dn0_dn_device0")
        site3 = Site(
            site_type=SiteType.DN,
            location=GeoLocation(longitude=1, latitude=0),
            device=device_list[2],
            status_type=StatusType.CANDIDATE,
            location_type=LocationType.UNKNOWN,
            building_id=None,
            name="dn0",
            number_of_subscribers=None,
        )
        error_msg = f"Duplicate site name {site3.name} with the same device sku {site3.device.device_sku}"
        with self.assertRaisesRegex(DataException, error_msg):
            site_list.add_site(site3)
