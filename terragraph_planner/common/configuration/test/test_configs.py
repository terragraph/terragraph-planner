# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import unittest
from unittest.mock import MagicMock, patch

from terragraph_planner.common.configuration.configs import (
    DeviceData,
    GISDataParams,
    LOSParams,
    OptimizerParams,
    SectorParams,
    SiteDetectionParams,
)
from terragraph_planner.common.configuration.test.helper import check_if_subdict

MOCK_PATH_PREFIX = "terragraph_planner.common.configuration"


class TestConfigs(unittest.TestCase):
    def setUp(self) -> None:
        self.patch1 = patch(
            f"{MOCK_PATH_PREFIX}.configs.read_antenna_pattern_data",
            MagicMock(return_value=None),
        )
        self.patch2 = patch(
            f"{MOCK_PATH_PREFIX}.configs.read_mcs_snr_mbps_map_data",
            MagicMock(return_value=None),
        )
        self.patch3 = patch(
            f"{MOCK_PATH_PREFIX}.configs.read_scan_pattern_data",
            MagicMock(return_value=None),
        )
        self.patch1.start()
        self.patch2.start()
        self.patch3.start()
        self.sector_params = SectorParams(
            antenna_boresight_gain=1000,
            tx_diversity_gain=100,
            rx_diversity_gain=100,
            tx_miscellaneous_loss=200,
            rx_miscellaneous_loss=100,
            minimum_mcs_level=1,
            minimum_tx_power=10,
            rain_rate=11.0,
            antenna_pattern_file_path="xxx.txt",
            scan_pattern_file_path="xxx.csv",
            mcs_map_file_path="abc.csv",
        )
        self.sector_params_dict = {
            "antenna_boresight_gain": 1000,
            "tx_diversity_gain": 100,
            "rx_diversity_gain": 100,
            "tx_miscellaneous_loss": 200,
            "rx_miscellaneous_loss": 100,
            "minimum_mcs_level": 1,
            "minimum_tx_power": 10,
            "rain_rate": 11.0,
            "antenna_pattern_file_path": "xxx.txt",
            "scan_pattern_file_path": "xxx.csv",
            "mcs_map_file_path": "abc.csv",
        }
        self.device_data = DeviceData(
            device_sku="I AM A DEVICE_SKU",
            sector_params=self.sector_params,
        )

        another_device_data = DeviceData(
            device_sku="I AM ANOTHER DEVICE_SKU",
            sector_params=self.sector_params,
        )

        self.device_data_dict = {
            "device_sku": "I AM A DEVICE_SKU",
            "sector_params": self.sector_params_dict,
        }
        another_device_data_dict = {
            "device_sku": "I AM ANOTHER DEVICE_SKU",
            "sector_params": self.sector_params_dict,
        }

        self.site_detection_params = SiteDetectionParams(
            max_corner_angle=120,
            dn_deployment=False,
            detect_highest=False,
            detect_centers=True,
            detect_corners=False,
        )
        self.site_detection_dict = {
            "max_corner_angle": 120,
            "dn_deployment": False,
            "detect_highest": False,
            "detect_centers": True,
            "detect_corners": False,
        }

        self.los_params = LOSParams(
            minimum_mcs_of_backhaul_links=10,
            minimum_mcs_of_access_links=1,
            maximum_eirp=0.09,
            rain_rate=11.0,
            device_list=[self.device_data, another_device_data],
            site_detection=self.site_detection_params,
        )

        self.los_params_dict = {
            "minimum_mcs_of_backhaul_links": 10,
            "minimum_mcs_of_access_links": 1,
            "maximum_eirp": 0.09,
            "rain_rate": 11.0,
            "device_list": [self.device_data_dict, another_device_data_dict],
            "site_detection": self.site_detection_dict,
        }

        self.optimizer_params = OptimizerParams(
            pop_site_capex=12000,
            cn_site_capex=2500,
            dn_site_capex=2400,
            device_list=[self.device_data, another_device_data],
            rain_rate=11.0,
            diff_sector_angle_limit=15.0,
            near_far_length_ratio=2.0,
            near_far_angle_limit=35.0,
            demand=0.025,
        )

        self.optimizer_params_dict = {
            "pop_site_capex": 12000,
            "cn_site_capex": 2500,
            "dn_site_capex": 2400,
            "device_list": [self.device_data_dict, another_device_data_dict],
            "rain_rate": 11.0,
            "diff_sector_angle_limit": 15.0,
            "near_far_length_ratio": 2.0,
            "near_far_angle_limit": 35.0,
            "demand": 0.025,
        }

        self.data_params = GISDataParams(
            boundary_polygon_file_path="boundary.kml",
            building_outline_file_path="building.zip",
            dsm_file_paths=["dsm1.tif", "dsm2.tif"],
            dtm_file_path="dtm.tif",
            dhm_file_path="dhm.tif",
            site_file_path="sites.csv",
            base_topology_file_path=None,
        )
        self.data_params_dict = {
            "boundary_polygon_file_path": "boundary.kml",
            "building_outline_file_path": "building.zip",
            "dsm_file_paths": ["dsm1.tif", "dsm2.tif"],
            "dtm_file_path": "dtm.tif",
            "dhm_file_path": "dhm.tif",
            "site_file_path": "sites.csv",
            "base_topology_file_path": None,
        }

    def tearDown(self) -> None:
        self.patch1.stop()
        self.patch2.stop()
        self.patch3.stop()

    def test_config_parser_from_dict(self) -> None:
        self.assertEqual(
            SectorParams.from_dict(self.sector_params_dict),
            self.sector_params,
        )
        self.assertEqual(
            DeviceData.from_dict(self.device_data_dict),
            self.device_data,
        )

        self.assertEqual(
            SiteDetectionParams.from_dict(self.site_detection_dict),
            self.site_detection_params,
        )

        self.assertEqual(
            LOSParams.from_dict(self.los_params_dict),
            self.los_params,
        )

        self.assertEqual(
            OptimizerParams.from_dict(self.optimizer_params_dict),
            self.optimizer_params,
        )

        self.assertEqual(
            GISDataParams.from_dict(self.data_params_dict),
            self.data_params,
        )

    def test_config_parser_to_dict(self) -> None:
        self.assertTrue(
            check_if_subdict(
                self.sector_params_dict, self.sector_params.to_dict()
            )
        )
        self.assertTrue(
            check_if_subdict(
                self.device_data_dict,
                self.device_data.to_dict(),
            )
        )
        self.assertTrue(
            check_if_subdict(
                self.optimizer_params_dict,
                self.optimizer_params.to_dict(),
            )
        )

        self.assertTrue(
            check_if_subdict(
                self.los_params_dict,
                self.los_params.to_dict(),
            )
        )
        self.assertTrue(
            check_if_subdict(
                self.data_params_dict,
                self.data_params.to_dict(),
            )
        )
        self.assertTrue(
            check_if_subdict(
                self.site_detection_dict,
                self.site_detection_params.to_dict(),
            )
        )
