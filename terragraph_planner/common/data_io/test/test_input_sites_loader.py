# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
from shapely.geometry import Polygon

from terragraph_planner.common.configuration.enums import (
    LocationType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.data_io.data_key import SiteKey
from terragraph_planner.common.data_io.input_sites_loader import (
    InputSitesLoader,
)
from terragraph_planner.common.exceptions import DataException
from terragraph_planner.common.structs import RawSite
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
)

CSV_LIBRARY_PREFIX: str = "terragraph_planner.common.data_io.csv_library"
KML_LIBRARY_PREFIX: str = "terragraph_planner.common.data_io.input_sites_loader"
CSV_FAKE_FILE_PATH: str = "I'm a fake file path.csv"
KML_FAKE_FILE_PATH: str = "I'm a fake file path.kml"


class TestInputSitesLoader(unittest.TestCase):
    def setUp(self) -> None:
        device_list = [DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        self.loader = InputSitesLoader(device_list)

    @patch(
        f"{CSV_LIBRARY_PREFIX}.load_csv_and_validate",
        MagicMock(
            return_value=pd.DataFrame(
                {
                    SiteKey.LATITUDE: [0.1, 0.2, 1.1],
                    SiteKey.LONGITUDE: [0.1, 0.2, 1.3],
                    SiteKey.NAME: ["a", "b", "c"],
                }
            )
        ),
    )
    def test_read_from_csv(self) -> None:
        sites = self.loader.read_user_input(CSV_FAKE_FILE_PATH, None, None)
        self.assertEqual(len(sites), 3)
        sites = self.loader.read_user_input(
            CSV_FAKE_FILE_PATH,
            Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]),
            None,
        )
        # site (1.1, 1.3) is filter out by boundary
        self.assertEqual(len(sites), 2)
        for site in sites:
            self.assertEqual(site.site_type, SiteType.POP)

    @patch(
        f"{CSV_LIBRARY_PREFIX}.load_csv_and_validate",
        MagicMock(
            side_effect=[
                pd.DataFrame(
                    {
                        SiteKey.LATITUDE: [0.1, 0.2, 1.1],
                        SiteKey.LONGITUDE: [0.1, 0.2, 1.3],
                        SiteKey.SITE_TYPE: ["dn", "Cn", "POP"],
                        SiteKey.NAME: ["1", "2", "3"],
                    }
                ),
                pd.DataFrame(
                    {
                        SiteKey.LATITUDE: [0.1],
                        SiteKey.LONGITUDE: [0.1],
                        SiteKey.SITE_TYPE: ["dnsite"],
                        SiteKey.NAME: ["4"],
                    }
                ),
            ]
        ),
    )
    def test_load_from_topology_site_csv(self) -> None:
        sites = self.loader.read_user_input(CSV_FAKE_FILE_PATH, None, None)
        expected_site_types = [SiteType.DN, SiteType.CN, SiteType.POP]
        for expect_site_type, site in zip(expected_site_types, sites):
            self.assertEqual(expect_site_type, site.site_type)
        error_obj = DataException("Invalid site type dnsite in site csv file.")
        with self.assertRaisesRegex(DataException, str(error_obj)):
            sites = self.loader.read_user_input(CSV_FAKE_FILE_PATH, None, None)

    @patch(
        f"{KML_LIBRARY_PREFIX}.extract_raw_data_from_kml_file",
        MagicMock(
            return_value=(
                [
                    RawSite(
                        site_type=SiteType.POP,
                        status_type=StatusType.CANDIDATE,
                        device_sku=None,
                        name="site1",
                        latitude=0.1,
                        longitude=0.1,
                        altitude=None,
                        height=None,
                        location_type=LocationType.UNKNOWN,
                        building_id=None,
                        number_of_subscribers=None,
                    ),
                    RawSite(
                        site_type=SiteType.DN,
                        status_type=StatusType.CANDIDATE,
                        device_sku=None,
                        name="site2",
                        latitude=0.2,
                        longitude=0.2,
                        altitude=None,
                        height=None,
                        location_type=LocationType.UNKNOWN,
                        building_id=None,
                        number_of_subscribers=None,
                    ),
                    RawSite(
                        site_type=SiteType.CN,
                        status_type=StatusType.CANDIDATE,
                        device_sku=None,
                        name="site3",
                        latitude=0.3,
                        longitude=0.3,
                        altitude=None,
                        height=None,
                        location_type=LocationType.UNKNOWN,
                        building_id=None,
                        number_of_subscribers=None,
                    ),
                ],
                [],
                [],
            )
        ),
    )
    def test_read_from_kml(self) -> None:
        sites = self.loader.read_user_input(KML_FAKE_FILE_PATH, None, None)
        self.assertEqual(len(sites), 3)

    @patch(
        f"{KML_LIBRARY_PREFIX}.extract_raw_data_from_kml_file",
        MagicMock(
            return_value=(
                [
                    RawSite(
                        site_type=SiteType.POP,
                        status_type=StatusType.CANDIDATE,
                        device_sku="SAMPLE_DN_DEVICE",
                        name="site1",
                        latitude=0.1,
                        longitude=0.1,
                        altitude=None,
                        height=None,
                        location_type=LocationType.UNKNOWN,
                        building_id=None,
                        number_of_subscribers=None,
                    ),
                    RawSite(
                        site_type=SiteType.DN,
                        status_type=StatusType.CANDIDATE,
                        device_sku="fake",
                        name="site2",
                        latitude=0.2,
                        longitude=0.2,
                        altitude=None,
                        height=None,
                        location_type=LocationType.UNKNOWN,
                        building_id=None,
                        number_of_subscribers=None,
                    ),
                    RawSite(
                        site_type=SiteType.CN,
                        status_type=StatusType.CANDIDATE,
                        device_sku="SAMPLE_CN_DEVICE",
                        name="site3",
                        latitude=0.3,
                        longitude=0.3,
                        altitude=None,
                        height=None,
                        location_type=LocationType.UNKNOWN,
                        building_id=None,
                        number_of_subscribers=None,
                    ),
                ],
                [],
                [],
            )
        ),
    )
    @patch(
        f"{CSV_LIBRARY_PREFIX}.load_csv_and_validate",
        MagicMock(
            return_value=pd.DataFrame(
                {
                    SiteKey.LATITUDE: [0.1, 0.2, 1.1],
                    SiteKey.LONGITUDE: [0.1, 0.2, 1.3],
                    SiteKey.NAME: ["a", "b", "c"],
                    SiteKey.DEVICE_SKU: [
                        "SAMPLE_CN_DEVICE",
                        "fake",
                        "SAMPLE_DN_DEVICE",
                    ],
                    SiteKey.SITE_TYPE: ["cn", "dn", "pop"],
                }
            )
        ),
    )
    def test_invalid_device_sku(self) -> None:
        error_msg = "Device fake does not exist in device list"
        with self.assertRaisesRegex(DataException, error_msg):
            self.loader.read_user_input(KML_FAKE_FILE_PATH, None, None)
        with self.assertRaisesRegex(DataException, error_msg):
            self.loader.read_user_input(CSV_FAKE_FILE_PATH, None, None)
