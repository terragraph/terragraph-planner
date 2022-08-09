# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
import unittest
from inspect import getfullargspec
from unittest.mock import MagicMock, patch

from terragraph_planner.common.configuration.configs import (
    DeviceData,
    GISDataParams,
    LOSParams,
    OptimizerParams,
    SectorParams,
    SiteDetectionParams,
    SystemParams,
)
from terragraph_planner.common.configuration.constants import (
    SYSTEM,
    TEMPLATE_YAML_FILE_PATH,
)
from terragraph_planner.common.configuration.enums import (
    DeviceType,
    LoggerLevel,
    RedundancyLevel,
    TopologyRouting,
)
from terragraph_planner.common.configuration.utils import (
    DATA,
    LINE_OF_SIGHT,
    OPTIMIZATION,
    _detect_typo,
    _load_dict_from_file,
    struct_objects_from_file,
)

PATH_TO_CONFIGS_PREFIX = (
    "terragraph_planner/common/configuration/test/test_data/"
)
MOCK_PATH_PREFIX = "terragraph_planner.common.configuration.configs"


@patch(
    f"{MOCK_PATH_PREFIX}.read_antenna_pattern_data",
    MagicMock(return_value=None),
)
@patch(
    f"{MOCK_PATH_PREFIX}.read_mcs_snr_mbps_map_data",
    MagicMock(return_value=None),
)
@patch(
    f"{MOCK_PATH_PREFIX}.read_scan_pattern_data",
    MagicMock(return_value=None),
)
class TestUtils(unittest.TestCase):
    def test_detect_typo(self) -> None:
        origin = {
            "A": None,
            "B": None,
            "C": None,
            "D": {
                "D_1": None,
                "D_2": None,
                "D_3": [
                    {
                        "D_3_a": None,
                        "D_3_c": None,
                        "D_3_b": None,
                        "D_3_d": None,
                    }
                ],
            },
        }
        good_data = {
            "A": 123,
            "B": "I AM B",
            "D": {
                "D_1": "I AM D_1",
                "D_2": "I AM D_2",
                "D_3": [
                    {
                        "D_3_a": "Fake",
                        "D_3_c": "Nothing",
                        "D_3_d": 321,
                    },
                    {
                        "D_3_a": "Real",
                        "D_3_b": "Something",
                        "D_3_d": 456,
                    },
                ],
            },
        }
        # No exception raised
        _detect_typo(good_data, origin)

        data_with_space_and_lower_case = {
            "A ": 432,
            " B": "I am B",
            "C": None,
            "d": {
                "D_1": "",
                "D_2": "",
                "D_3": [
                    {
                        "d_3_a": "Fake",
                        "D_3_c": "Nothing",
                        "D_3_d": 321,
                    },
                    {
                        "D_3_a": "Not Real",
                        "D_3_d": 789,
                    },
                ],
            },
        }
        # test case-insensitive, no exception raised
        _detect_typo(data_with_space_and_lower_case, origin)

        bad_data_in_direct_key_words = {
            "aa": 123,
            "B": "I AM B",
            "D": {
                "D_1": "I AM D_1",
                "D_2": "I AM D_2",
                "D_3": [
                    {
                        "D_3_a": "Fake",
                        "D_3_c": "Nothing",
                        "D_3_d": 321,
                    },
                    {
                        "D_3_a": "Real",
                        "D_3_b": "Something",
                        "D_3_d": 456,
                    },
                ],
            },
        }
        # 'aa' is not a legal key word
        with self.assertRaises(Exception):
            _detect_typo(bad_data_in_direct_key_words, origin)

        bad_data_in_list_key_words = {
            "A": 123,
            "B": "I AM B",
            "D": {
                "D_1": "I AM D_1",
                "D_2": "I AM D_2",
                "D_3": [
                    {
                        "D_2_a": "Fake",
                        "D_3_c": "Nothing",
                        "D_3_d": 321,
                    },
                    {
                        "D_3_a": "Real",
                        "D_3_b": "Something",
                        "D_3_d": 456,
                    },
                ],
            },
        }
        # D_2_a is not a legal key word under D_3
        with self.assertRaises(Exception):
            _detect_typo(bad_data_in_list_key_words, origin)

        bad_data_in_wrong_place = {
            "A": 123,
            "B": "I AM B",
            "D_1": "I AM D_1",
            "D": {
                "D_2": "I AM D_2",
                "D_3": [
                    {
                        "D_3_a": "Fake",
                        "D_3_c": "Nothing",
                        "D_3_d": 321,
                    },
                    {
                        "D_3_a": "Real",
                        "D_3_b": "Something",
                        "D_3_d": 456,
                    },
                ],
            },
        }
        # D_1 should be a key workd under D
        with self.assertRaises(Exception):
            _detect_typo(bad_data_in_wrong_place, origin)

    def test_load_dict_from_file(self) -> None:
        data = _load_dict_from_file(TEMPLATE_YAML_FILE_PATH)
        self.assertGreater(len(data), 0)

    def test_struct_objects_from_file(self) -> None:
        los = struct_objects_from_file(LINE_OF_SIGHT, TEMPLATE_YAML_FILE_PATH)
        optimizer = struct_objects_from_file(
            OPTIMIZATION, TEMPLATE_YAML_FILE_PATH
        )
        data = struct_objects_from_file(DATA, TEMPLATE_YAML_FILE_PATH)
        self.assertIsInstance(los, LOSParams)
        self.assertIsNotNone(los)
        self.assertIsInstance(optimizer, OptimizerParams)
        self.assertIsNotNone(optimizer)
        self.assertIsInstance(data, GISDataParams)
        self.assertIsNotNone(data)

    def test_struct_object_from_non_default_file(self) -> None:
        """
        Test to parse all the config parameters from a yaml from with non-default
        values to make sure all the parameters are correctly parsed.
        """
        test_yaml = os.path.join(
            PATH_TO_CONFIGS_PREFIX, "exhausted_configs_with_non_default.yaml"
        )
        parsed_data_params = struct_objects_from_file(DATA, test_yaml)
        parsed_los_params = struct_objects_from_file(LINE_OF_SIGHT, test_yaml)
        parsed_opt_params = struct_objects_from_file(OPTIMIZATION, test_yaml)
        parsed_sys_params = struct_objects_from_file(SYSTEM, test_yaml)

        expected_data_params = GISDataParams(
            boundary_polygon_file_path="boundary.kml",
            dsm_file_paths=["dsm1.tif", "dsm2.tif"],
            dtm_file_path="dtm.tif",
            dhm_file_path="dhm.tif",
            building_outline_file_path="buildings.zip",
            site_file_path="sites.kml",
            base_topology_file_path="base_topology.kmz",
        )
        self.assertEqual(
            parsed_data_params.to_dict(), expected_data_params.to_dict()
        )
        expected_dn_device = DeviceData(
            device_sku="Sample1",
            device_type=DeviceType.DN,
            node_capex=888.8,
            number_of_nodes_per_site=3,
            sector_params=SectorParams(
                horizontal_scan_range=33.3,
                number_sectors_per_node=2,
                antenna_boresight_gain=32.1,
                maximum_tx_power=12.3,
                minimum_tx_power=1.23,
                tx_diversity_gain=1.2,
                rx_diversity_gain=2.3,
                tx_miscellaneous_loss=3.4,
                rx_miscellaneous_loss=4.5,
                minimum_mcs_level=5,
                antenna_pattern_file_path="antenna_pattern1.txt",
                scan_pattern_file_path="scan_pattern1.csv",
                mcs_map_file_path="mcs_map1.csv",
            ),
        )
        expected_cn_device = DeviceData(
            device_sku="Sample2",
            device_type=DeviceType.CN,
            node_capex=555.5,
            number_of_nodes_per_site=1,
            sector_params=SectorParams(
                horizontal_scan_range=23.4,
                number_sectors_per_node=3,
                antenna_boresight_gain=21.0,
                maximum_tx_power=23.4,
                minimum_tx_power=2.34,
                tx_diversity_gain=2.3,
                rx_diversity_gain=3.4,
                tx_miscellaneous_loss=4.5,
                rx_miscellaneous_loss=5.6,
                minimum_mcs_level=6,
                antenna_pattern_file_path="antenna_pattern2.txt",
                scan_pattern_file_path="scan_pattern2.csv",
                mcs_map_file_path="mcs_map2.csv",
            ),
        )
        expected_los_params = LOSParams(
            device_list=[expected_dn_device, expected_cn_device],
            minimum_mcs_of_backhaul_links=2,
            minimum_mcs_of_access_links=3,
            maximum_eirp=40.0,
            rain_rate=35.0,
            link_availability_percentage=78.9,
            maximum_los_distance=500,
            minimum_los_distance=5,
            carrier_frequency=50000.0,
            thermal_noise_power=-78.0,
            noise_figure=6.6,
            mounting_height_above_rooftop=1.2,
            default_dn_height_on_pole=7,
            default_cn_height_on_pole=8,
            default_pop_height_on_pole=6,
            use_ellipsoidal_los_model=True,
            fresnel_radius=1.5,
            los_confidence_threshold=0.5,
            site_detection=SiteDetectionParams(
                dn_deployment=False,
                detect_highest=False,
                detect_centers=True,
                detect_corners=False,
                max_corner_angle=90.0,
            ),
            num_processors=2,
        )
        self.assertEqual(
            parsed_los_params.to_dict(), expected_los_params.to_dict()
        )
        expected_opt_params = OptimizerParams(
            device_list=[expected_dn_device, expected_cn_device],
            pop_site_capex=1900.0,
            cn_site_capex=90.0,
            dn_site_capex=190.0,
            rain_rate=35.0,
            budget=200000.0,
            pop_capacity=9.7,
            oversubscription=1.5,
            carrier_frequency=50000.0,
            thermal_noise_power=-78.0,
            noise_figure=6.6,
            link_availability_percentage=78.9,
            maximum_eirp=40.0,
            number_of_extra_pops=3,
            enable_cn_demand=False,
            enable_uniform_demand=True,
            enable_manual_demand=True,
            demand_spacing=50.0,
            demand_connection_radius=100.0,
            demand=0.012,
            dn_dn_sector_limit=4,
            dn_total_sector_limit=8,
            maximum_number_hops=7,
            diff_sector_angle_limit=20.0,
            near_far_length_ratio=2.5,
            near_far_angle_limit=45.4,
            number_of_channels=2,
            maximize_common_bandwidth=True,
            always_active_pops=False,
            enable_legacy_redundancy_method=False,
            redundancy_level=RedundancyLevel.HIGH,
            backhaul_link_redundancy_ratio=0.32,
            num_threads=3,
            min_cost_rel_stop=0.02,
            min_cost_max_time=2,
            redundancy_rel_stop=0.03,
            redundancy_max_time=3,
            max_coverage_rel_stop=0.04,
            max_coverage_max_time=4,
            interference_rel_stop=0.06,
            interference_max_time=5,
            pop_proposal_rel_stop=0.01,
            pop_proposal_max_time=1,
            demand_site_max_time=6,
            candidate_topology_file_path="topology.kml",
            topology_routing=TopologyRouting.SHORTEST_PATH,
            availability_sim_time=10.0,
            availability_seed=5,
            availability_max_time=20,
        )
        self.assertEqual(
            parsed_opt_params.to_dict(), expected_opt_params.to_dict()
        )

        expected_sys_params = SystemParams(
            output_dir="output",
            debug_mode=True,
            logger_level=LoggerLevel.CRITICAL,
            log_file="tg.log",
            log_to_stderr=False,
        )
        self.assertEqual(
            parsed_sys_params.to_dict(), expected_sys_params.to_dict()
        )

    def test_struct_object_from_exhausted_parameter_list(self) -> None:
        """
        Test whether all the parameters are in the exhausted_configs_with_non_default.yaml.
        Since we compare every config yaml with template.yaml when structing
        them, it also tests whether the template yaml is complete.
        """
        test_yaml = os.path.join(
            PATH_TO_CONFIGS_PREFIX, "exhausted_configs_with_non_default.yaml"
        )
        data_params_args = getfullargspec(GISDataParams.__init__)
        los_params_args = getfullargspec(LOSParams.__init__)
        opt_params_args = getfullargspec(OptimizerParams.__init__)
        sector_params_args = getfullargspec(SectorParams.__init__)
        device_data_args = getfullargspec(DeviceData.__init__)
        site_detection_args = getfullargspec(SiteDetectionParams.__init__)
        args_dict = {
            "GISDataParams": data_params_args,
            "LOSParams": los_params_args,
            "OptimizerParams": opt_params_args,
            "SectorParams": sector_params_args,
            "DeviceData": device_data_args,
            "SiteDetectionParams": site_detection_args,
        }
        with patch(f"{MOCK_PATH_PREFIX}.getfullargspec") as mock_getfullargspec:
            mock_getfullargspec.side_effect = lambda func: args_dict[
                func.config_class
            ]
            with patch(
                f"{MOCK_PATH_PREFIX}.GISDataParams.__init__"
            ) as data_constructor:
                data_constructor.return_value = None
                data_constructor.config_class = "GISDataParams"
                struct_objects_from_file(DATA, test_yaml)
                called_data_args = data_constructor.call_args.kwargs.keys()
            self.assertEqual(
                set(data_params_args.args) - {"self"}, set(called_data_args)
            )

            with patch(
                f"{MOCK_PATH_PREFIX}.LOSParams.__init__"
            ) as los_constructor:
                los_constructor.return_value = None
                los_constructor.config_class = "LOSParams"
                with patch(
                    f"{MOCK_PATH_PREFIX}.SiteDetectionParams.__init__"
                ) as site_detection_constructor:
                    site_detection_constructor.return_value = None
                    site_detection_constructor.config_class = (
                        "SiteDetectionParams"
                    )
                    with patch(
                        f"{MOCK_PATH_PREFIX}.DeviceData.__init__"
                    ) as device_data_constructor:
                        device_data_constructor.return_value = None
                        device_data_constructor.config_class = "DeviceData"
                        with patch(
                            f"{MOCK_PATH_PREFIX}.SectorParams.__init__"
                        ) as sector_constructor:
                            sector_constructor.return_value = None
                            sector_constructor.config_class = "SectorParams"
                            struct_objects_from_file(LINE_OF_SIGHT, test_yaml)
                            called_los_args = (
                                los_constructor.call_args.kwargs.keys()
                            )
                            called_site_detection_args = (
                                site_detection_constructor.call_args.kwargs.keys()
                            )
                            called_device_data_args = (
                                device_data_constructor.call_args.kwargs.keys()
                            )
                            called_sector_args = (
                                sector_constructor.call_args.kwargs.keys()
                            )

            self.assertEqual(
                set(los_params_args.args) - {"self"}, set(called_los_args)
            )
            self.assertEqual(
                set(site_detection_args.args) - {"self"},
                set(called_site_detection_args),
            )
            self.assertEqual(
                set(device_data_args.args) - {"self"},
                set(called_device_data_args),
            )
            self.assertEqual(
                set(sector_params_args.args) - {"self"}, set(called_sector_args)
            )

            with patch(
                f"{MOCK_PATH_PREFIX}.OptimizerParams.__init__"
            ) as opt_constructor:
                opt_constructor.return_value = None
                opt_constructor.config_class = "OptimizerParams"
                with patch(
                    f"{MOCK_PATH_PREFIX}.DeviceData.__init__"
                ) as device_data_constructor:
                    device_data_constructor.return_value = None
                    device_data_constructor.config_class = "DeviceData"
                    with patch(
                        f"{MOCK_PATH_PREFIX}.SectorParams.__init__"
                    ) as sector_constructor:
                        sector_constructor.return_value = None
                        sector_constructor.config_class = "SectorParams"
                        struct_objects_from_file(OPTIMIZATION, test_yaml)
                        called_opt_args = (
                            opt_constructor.call_args.kwargs.keys()
                        )
                        called_device_data_args = (
                            device_data_constructor.call_args.kwargs.keys()
                        )
                        called_sector_args = (
                            sector_constructor.call_args.kwargs.keys()
                        )
            self.assertEqual(
                set(opt_params_args.args) - {"self"}, set(called_opt_args)
            )
            self.assertEqual(
                set(device_data_args.args) - {"self"},
                set(called_device_data_args),
            )
            self.assertEqual(
                set(sector_params_args.args) - {"self"}, set(called_sector_args)
            )

    def test_bad_input_configs(self) -> None:
        with self.assertRaisesRegex(
            Exception,
            "DEFAULT_POP_HEIGHT_ON_POL is an illegal field with no definition, check if it's a typo.",
        ):
            struct_objects_from_file(
                LINE_OF_SIGHT,
                os.path.join(PATH_TO_CONFIGS_PREFIX, "configs_with_typo.yaml"),
            )

        with self.assertRaises(Exception):
            struct_objects_from_file(
                OPTIMIZATION,
                os.path.join(
                    PATH_TO_CONFIGS_PREFIX, "configs_missing_fields.yaml"
                ),
            )
