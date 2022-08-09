# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import sys
from inspect import getfullargspec
from typing import Any, Dict, List, Optional

from terragraph_planner.common.configuration.constants import (
    DEFAULT_CARRIER_FREQUENCY,
    DEFAULT_LOS_CONFIDENCE_THRESHOLD,
)
from terragraph_planner.common.configuration.enums import (
    DeviceType,
    EnumParser,
    LoggerLevel,
    RedundancyLevel,
    TopologyRouting,
)
from terragraph_planner.common.constants import DEFAULT_MCS_SNR_MBPS_MAP
from terragraph_planner.common.data_io.csv_library import (
    read_antenna_pattern_data,
    read_mcs_snr_mbps_map_data,
    read_scan_pattern_data,
)
from terragraph_planner.common.exceptions import (
    ConfigException,
    assert_file_extension,
    planner_assert,
)
from terragraph_planner.common.structs import (
    AntennaPatternData,
    MCSMap,
    ScanPatternData,
)

CLASS_NAME_MAPPING = {
    "sector_params": "SectorParams",
    "device_list": "DeviceData",
    "site_detection": "SiteDetectionParams",
}
CLASS_NAME_TO_ENUM_MAPPING = {
    "device_type": "DeviceType",
    "redundancy_level": "RedundancyLevel",
    "topology_routing": "TopologyRouting",
    "logger_level": "LoggerLevel",
}


class ConfigParser:
    def to_dict(self) -> Dict[str, Any]:
        """
        Get args used in __init__ and re-organize them as serializable dict
        @return: dict of args used in __init__
        """
        func_arg_val = {}
        for key in self.__dict__:
            value = getattr(self, key)
            if isinstance(value, (str, int, float)) or value is None:
                func_arg_val[key] = value
            elif isinstance(value, (list, tuple)):
                obj_list = []
                for obj in value:
                    if isinstance(obj, ConfigParser):
                        obj_list.append(obj.to_dict())
                    elif isinstance(value, EnumParser):
                        obj_list.append(obj.to_string())
                    elif isinstance(obj, (str, int, float)):
                        obj_list.append(obj)
                func_arg_val[key] = obj_list
            else:
                if isinstance(value, ConfigParser):
                    func_arg_val[key] = value.to_dict()
                elif isinstance(value, EnumParser):
                    func_arg_val[key] = value.to_string()
                else:
                    raise Exception(
                        "No internal definition with {type(value).}"
                    )
        return func_arg_val

    @classmethod
    def from_dict(cls, propdict: Dict[str, Any]) -> "ConfigParser":
        """
        Instantiate given class with given dict
        @param cls: class to instantiate
        @param propdict: dict of args used in __init__
        @return: instance of cls
        """
        args = getfullargspec(cls.__init__).args
        prop_dict_lower = {k.casefold(): v for k, v in propdict.items()}
        func_arg_val = {}
        for key, value in prop_dict_lower.items():
            # Enable case in-sensitive
            if key in set(args):

                # If the key word is a string for Enum class, map the string to enum integer.
                if key in CLASS_NAME_TO_ENUM_MAPPING:
                    if value is not None:
                        func_arg_val[key] = getattr(
                            sys.modules[__name__],
                            CLASS_NAME_TO_ENUM_MAPPING[key],
                        ).from_string(value)

                # If the value is a dictionary for custom class, e.g. SectorParams and etc.
                # create a instance of the class.
                elif isinstance(value, dict):
                    if key in CLASS_NAME_MAPPING:
                        d = {**value, **propdict}
                        func_arg_val[key] = getattr(
                            sys.modules[__name__], CLASS_NAME_MAPPING[key]
                        ).from_dict(d)

                # If the value is a list of DeviceData, create a list of instances of DeviceData.
                elif isinstance(value, list):
                    obj_list = []
                    for obj in value:
                        if isinstance(obj, dict):
                            d = {**obj, **propdict}
                            obj_list.append(
                                getattr(
                                    sys.modules[__name__],
                                    CLASS_NAME_MAPPING[key],
                                ).from_dict(d)
                            )
                        else:
                            obj_list.append(obj)
                    func_arg_val[key] = obj_list
                else:
                    if value is not None:
                        try:
                            func_arg_val[key] = value
                        except AttributeError as err:
                            raise Exception(f"Unexpected input objects: {err}")
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if sub_key.casefold() in set(args):
                        func_arg_val[sub_key.casefold()] = sub_value
        # If the input key has None value, use the default value in the class constructor
        return cls(
            **{key: val for key, val in func_arg_val.items() if val is not None}
        )

    def __eq__(self, other: object) -> bool:
        """
        Overrides __eq__. Return True if two object have the same values of attriubtes.
        """
        if isinstance(other, self.__class__):
            for key, value in self.__dict__.items():
                other_value = other.__dict__[key]
                if isinstance(value, (int, float, tuple, str)):
                    if value != other_value:
                        return False
                elif isinstance(value, list):
                    value.sort()
                    other_value.sort()
                    for i in range(len(value)):
                        if not value[i].__eq__(other_value[i]):
                            return False
                else:
                    return value.__eq__(other_value)
            return True
        else:
            return NotImplemented


class SectorParams(ConfigParser):
    def __init__(
        self,
        antenna_boresight_gain: float = 30.0,
        maximum_tx_power: float = 16.0,
        number_sectors_per_node: int = 1,
        horizontal_scan_range: float = 70.0,
        carrier_frequency: float = DEFAULT_CARRIER_FREQUENCY,
        thermal_noise_power: float = -81.0,
        noise_figure: float = 7.0,
        rain_rate: float = 30.0,
        link_availability_percentage: float = 99.9,
        tx_diversity_gain: float = 0.0,
        rx_diversity_gain: float = 0.0,
        tx_miscellaneous_loss: float = 0.0,
        rx_miscellaneous_loss: float = 0.0,
        minimum_mcs_level: Optional[int] = None,
        minimum_tx_power: Optional[float] = None,
        antenna_pattern_file_path: Optional[str] = None,
        scan_pattern_file_path: Optional[str] = None,
        mcs_map_file_path: Optional[str] = None,
    ) -> None:
        planner_assert(
            antenna_boresight_gain >= 0,
            "Antenna boresight gain cannot be negative",
            ConfigException,
        )
        planner_assert(
            maximum_tx_power >= 0,
            "Maximum Tx power cannot be negative",
            ConfigException,
        )
        planner_assert(
            number_sectors_per_node >= 1,
            "Number sectors per node must be at least 1",
            ConfigException,
        )
        planner_assert(
            0 <= horizontal_scan_range <= 360,
            "Horizontal scan range of each device must be in [0, 360]",
            ConfigException,
        )
        planner_assert(
            carrier_frequency > 0,
            "Carrier frequency must be positive",
            ConfigException,
        )
        planner_assert(
            noise_figure >= 0,
            "Noise figure must cannot be negative",
            ConfigException,
        )
        planner_assert(
            rain_rate >= 0,
            "Rain rate cannot be negative",
            ConfigException,
        )
        planner_assert(
            0 <= link_availability_percentage <= 100,
            "Link availability percentage must be in [0, 100]",
            ConfigException,
        )
        planner_assert(
            tx_diversity_gain >= 0 and rx_diversity_gain >= 0,
            "Tx/Rx diversity gain of each device cannot be nagative",
            ConfigException,
        )
        planner_assert(
            tx_miscellaneous_loss >= 0 and rx_miscellaneous_loss >= 0,
            "Tx/Rx miscellaneous loss of each device cannot be negative",
            ConfigException,
        )
        planner_assert(
            minimum_mcs_level is None or minimum_mcs_level >= 0,
            "Minimum MCS level cannot be negative",
            ConfigException,
        )
        planner_assert(
            minimum_tx_power is None or minimum_tx_power <= maximum_tx_power,
            "Minimum Tx power must be less than maximum Tx power",
            ConfigException,
        )

        self.antenna_boresight_gain = antenna_boresight_gain
        self.maximum_tx_power = maximum_tx_power
        self.number_sectors_per_node = number_sectors_per_node
        self.horizontal_scan_range = horizontal_scan_range
        self.carrier_frequency = carrier_frequency
        self.thermal_noise_power = thermal_noise_power
        self.noise_figure = noise_figure
        self.rain_rate = rain_rate
        self.link_availability_percentage = link_availability_percentage
        self.tx_diversity_gain = tx_diversity_gain
        self.rx_diversity_gain = rx_diversity_gain
        self.tx_miscellaneous_loss = tx_miscellaneous_loss
        self.rx_miscellaneous_loss = rx_miscellaneous_loss
        self.minimum_mcs_level = minimum_mcs_level
        self.minimum_tx_power = minimum_tx_power
        self.antenna_pattern_file_path = antenna_pattern_file_path
        self.antenna_pattern_data: Optional[AntennaPatternData] = (
            read_antenna_pattern_data(antenna_pattern_file_path)
            if antenna_pattern_file_path is not None
            else None
        )
        self.scan_pattern_file_path = scan_pattern_file_path
        self.scan_pattern_data: Optional[ScanPatternData] = (
            read_scan_pattern_data(scan_pattern_file_path)
            if scan_pattern_file_path is not None
            else None
        )
        self.mcs_map_file_path = mcs_map_file_path
        self.mcs_map: List[MCSMap] = (
            read_mcs_snr_mbps_map_data(mcs_map_file_path, self)
            if mcs_map_file_path is not None
            else DEFAULT_MCS_SNR_MBPS_MAP
        )


class DeviceData(ConfigParser):
    def __init__(
        self,
        device_sku: str,
        sector_params: SectorParams,
        node_capex: float = 250.0,
        number_of_nodes_per_site: Optional[int] = None,
        device_type: DeviceType = DeviceType.DN,
    ) -> None:
        planner_assert(
            len(device_sku) > 0,
            "Device SKU cannot be empty.",
            ConfigException,
        )
        planner_assert(
            node_capex >= 0,
            "Node capex of each device cannot be negative",
            ConfigException,
        )
        planner_assert(
            number_of_nodes_per_site is None or number_of_nodes_per_site >= 1,
            "Number of nodes per site must be in at least 1",
            ConfigException,
        )
        self.device_sku = device_sku
        self.sector_params = sector_params
        self.node_capex = node_capex
        if number_of_nodes_per_site is None:
            self.number_of_nodes_per_site: int = (
                1 if device_type == DeviceType.CN else 4
            )
        elif number_of_nodes_per_site != 1 and device_type == DeviceType.CN:
            raise ConfigException(
                "Number of nodes per site of a CN device must be 1."
            )
        else:
            self.number_of_nodes_per_site: int = number_of_nodes_per_site
        planner_assert(
            sector_params.horizontal_scan_range
            * sector_params.number_sectors_per_node
            * self.number_of_nodes_per_site
            <= 360,
            f"Device {device_sku} has radio coverage over 360 degrees.",
            ConfigException,
        )
        self.device_type = device_type

    def __lt__(self, other: "DeviceData") -> bool:
        return self.device_sku < other.device_sku


class SiteDetectionParams(ConfigParser):
    def __init__(
        self,
        dn_deployment: bool = True,
        detect_highest: bool = True,
        detect_centers: bool = False,
        detect_corners: bool = True,
        max_corner_angle: Optional[float] = None,
    ) -> None:
        planner_assert(
            max_corner_angle is None or 0 < max_corner_angle < 180,
            "Max corner angle must be in the range of (0, 180)",
            ConfigException,
        )
        self.dn_deployment = dn_deployment
        self.detect_highest = detect_highest
        self.detect_centers = detect_centers
        self.detect_corners = detect_corners
        self.max_corner_angle = max_corner_angle


class GISDataParams(ConfigParser):
    def __init__(
        self,
        boundary_polygon_file_path: str,
        building_outline_file_path: Optional[str] = None,
        dsm_file_paths: Optional[List[Optional[str]]] = None,
        dtm_file_path: Optional[str] = None,
        dhm_file_path: Optional[str] = None,
        site_file_path: Optional[str] = None,
        base_topology_file_path: Optional[str] = None,
    ) -> None:
        assert_file_extension(
            boundary_polygon_file_path,
            {"kml", "kmz"},
            "BOUNDARY_POLYGON_FILE_PATH",
        )
        if building_outline_file_path is not None:
            assert_file_extension(
                building_outline_file_path,
                {"kml", "kmz", "zip"},
                "BUILDING_OUTLINE_FILE_PATH",
            )
        if dsm_file_paths is not None:
            for dsm_file_path in dsm_file_paths:
                if dsm_file_path is not None:
                    assert_file_extension(
                        dsm_file_path, {"tif"}, "DSM_FILE_PATH"
                    )
        if dtm_file_path is not None:
            assert_file_extension(dtm_file_path, {"tif"}, "DTM_FILE_PATH")
        if dhm_file_path is not None:
            assert_file_extension(dhm_file_path, {"tif"}, "DHM_FILE_PATH")
        if site_file_path is not None:
            assert_file_extension(
                site_file_path,
                {"kml", "kmz", "csv"},
                "SITE_FILE_PATH",
            )
        if base_topology_file_path is not None:
            assert_file_extension(
                base_topology_file_path,
                {"kml", "kmz"},
                "BASE_TOPOLOGY_FILE_PATH",
            )

        self.boundary_polygon_file_path = boundary_polygon_file_path
        self.building_outline_file_path = building_outline_file_path
        self.dsm_file_paths: List[str] = []
        if dsm_file_paths is not None:
            for path in dsm_file_paths:
                if path is not None:
                    self.dsm_file_paths.append(path)
        self.dtm_file_path = dtm_file_path
        self.dhm_file_path = dhm_file_path
        self.site_file_path = site_file_path
        self.base_topology_file_path = base_topology_file_path


class LOSParams(ConfigParser):
    def __init__(
        self,
        device_list: List[DeviceData],
        minimum_mcs_of_backhaul_links: Optional[int] = None,
        minimum_mcs_of_access_links: Optional[int] = None,
        maximum_eirp: Optional[float] = None,
        rain_rate: float = 30.0,
        link_availability_percentage: float = 99.9,
        maximum_los_distance: Optional[int] = 200,
        minimum_los_distance: int = 50,
        carrier_frequency: float = DEFAULT_CARRIER_FREQUENCY,
        thermal_noise_power: float = -81.0,
        noise_figure: float = 7.0,
        mounting_height_above_rooftop: float = 1.5,
        default_dn_height_on_pole: float = 5.0,
        default_cn_height_on_pole: float = 5.0,
        default_pop_height_on_pole: float = 5.0,
        use_ellipsoidal_los_model: bool = False,
        fresnel_radius: float = 1.0,
        los_confidence_threshold: float = DEFAULT_LOS_CONFIDENCE_THRESHOLD,
        site_detection: SiteDetectionParams = SiteDetectionParams(),
        num_processors: Optional[int] = None,
    ) -> None:
        planner_assert(
            len(device_list) > 0,
            "At least 1 device needed for LOS analysis",
            ConfigException,
        )
        planner_assert(
            (
                minimum_mcs_of_backhaul_links is None
                or minimum_mcs_of_backhaul_links >= 0
            )
            and (
                minimum_mcs_of_access_links is None
                or minimum_mcs_of_access_links >= 0
            ),
            "Minimum MCS of backhaul links and access links cannot be negative",
            ConfigException,
        )
        planner_assert(
            maximum_los_distance is None
            or (0 <= maximum_los_distance <= maximum_los_distance),
            "Maximum/maximum LOS distance cannot be negative "
            "and maximum LOS distance must be larger than minimum LOS distance",
            ConfigException,
        )
        planner_assert(
            mounting_height_above_rooftop >= 0,
            "Mounting height above rooftop cannot be negative",
            ConfigException,
        )
        planner_assert(
            default_dn_height_on_pole >= 0
            and default_cn_height_on_pole >= 0
            and default_pop_height_on_pole >= 0,
            "Default DN/CN/POP height cannot be negative",
            ConfigException,
        )
        planner_assert(
            fresnel_radius > 0,
            "Fresnel radius must be positive",
            ConfigException,
        )
        planner_assert(
            0 <= los_confidence_threshold <= 1,
            "LOS confidence threshold must be in [0, 1]",
            ConfigException,
        )
        _check_duplicated_devices(device_list)
        self.device_list = device_list
        self.minimum_mcs_of_backhaul_links = minimum_mcs_of_backhaul_links
        self.minimum_mcs_of_access_links = minimum_mcs_of_access_links
        self.maximum_eirp = maximum_eirp
        self.rain_rate = rain_rate
        self.maximum_los_distance = maximum_los_distance
        self.minimum_los_distance = minimum_los_distance
        self.carrier_frequency = carrier_frequency
        self.thermal_noise_power = thermal_noise_power
        self.noise_figure = noise_figure
        self.mounting_height_above_rooftop = mounting_height_above_rooftop
        self.default_dn_height_on_pole = default_dn_height_on_pole
        self.default_cn_height_on_pole = default_cn_height_on_pole
        self.default_pop_height_on_pole = default_pop_height_on_pole
        self.use_ellipsoidal_los_model = use_ellipsoidal_los_model
        self.fresnel_radius = fresnel_radius
        self.los_confidence_threshold = los_confidence_threshold
        self.site_detection = site_detection
        self.num_processors = num_processors

        self.link_availability_percentage = link_availability_percentage
        _populate_project_level_parameter(
            self.device_list,
            carrier_frequency,
            thermal_noise_power,
            noise_figure,
            rain_rate,
            link_availability_percentage,
        )


class OptimizerParams(ConfigParser):
    def __init__(
        self,
        device_list: List[DeviceData],
        pop_site_capex: float = 1500.0,
        cn_site_capex: float = 1500.0,
        dn_site_capex: float = 1500.0,
        rain_rate: float = 30.0,
        budget: float = 300000.0,
        pop_capacity: float = 10.0,
        oversubscription: float = 1.0,
        carrier_frequency: float = DEFAULT_CARRIER_FREQUENCY,
        thermal_noise_power: float = -81,
        noise_figure: float = 7,
        link_availability_percentage: float = 99.9,
        maximum_eirp: Optional[float] = None,
        number_of_extra_pops: int = 0,
        enable_cn_demand: bool = True,
        enable_uniform_demand: bool = False,
        enable_manual_demand: bool = False,
        demand_spacing: float = 0.0,
        demand_connection_radius: float = 0.0,
        demand: float = 0.025,
        dn_dn_sector_limit: int = 2,
        dn_total_sector_limit: int = 15,
        maximum_number_hops: int = 15,
        diff_sector_angle_limit: float = 25.0,
        near_far_length_ratio: float = 3.0,
        near_far_angle_limit: float = 45.0,
        number_of_channels: int = 1,
        maximize_common_bandwidth: bool = False,
        always_active_pops: bool = True,
        enable_legacy_redundancy_method: bool = True,
        redundancy_level: RedundancyLevel = RedundancyLevel.MEDIUM,
        backhaul_link_redundancy_ratio: float = 0.2,
        num_threads: Optional[int] = None,
        min_cost_rel_stop: float = 0.05,
        min_cost_max_time: int = 60,
        redundancy_rel_stop: float = 0.05,
        redundancy_max_time: int = 60,
        max_coverage_rel_stop: float = -1,
        max_coverage_max_time: int = 60,
        interference_rel_stop: float = -1,
        interference_max_time: int = 60,
        pop_proposal_rel_stop: float = -1,
        pop_proposal_max_time: int = 60,
        demand_site_max_time: int = 15,
        topology_routing: Optional[TopologyRouting] = None,
        availability_sim_time: float = 100.0,
        availability_seed: int = 0,
        availability_max_time: int = 60,
        candidate_topology_file_path: Optional[str] = None,
    ) -> None:
        planner_assert(
            len(device_list) > 0,
            "At least 1 device needed for optimizer",
            ConfigException,
        )
        _check_duplicated_devices(device_list)
        planner_assert(
            pop_site_capex >= 0 and cn_site_capex >= 0 and dn_site_capex >= 0,
            "POP/DN/CN capex cannot be negative",
            ConfigException,
        )
        planner_assert(
            budget >= 0,
            "Budget cannot be negative",
            ConfigException,
        )
        planner_assert(
            pop_capacity > 0,
            "POP capacity must be positive",
            ConfigException,
        )
        planner_assert(
            oversubscription >= 1,
            "Oversubscription must be at least 1",
            ConfigException,
        )
        planner_assert(
            number_of_extra_pops >= 0,
            "Number of extra POPs cannot be negative",
            ConfigException,
        )
        planner_assert(
            enable_cn_demand or enable_uniform_demand or enable_manual_demand,
            "At least one method of adding demand must be enabled",
            ConfigException,
        )
        planner_assert(
            not enable_uniform_demand or demand_spacing > 0,
            "When uniform demand is enabled, the demand spacing must be positive",
            ConfigException,
        )
        planner_assert(
            not (enable_uniform_demand or enable_manual_demand)
            or demand_connection_radius > 0,
            "When uniform or manual demand is enabled, the demand connection radius must be positive",
            ConfigException,
        )
        planner_assert(
            demand > 0,
            "Demand must be positive",
            ConfigException,
        )
        planner_assert(
            dn_total_sector_limit >= dn_dn_sector_limit > 0,
            "The maximum DN-DN radio connections must be positive and cannot "
            "exceed the maximum total DN radio connections",
            ConfigException,
        )
        planner_assert(
            maximum_number_hops > 0,
            "Maximum number of hops must be positive",
            ConfigException,
        )
        planner_assert(
            0 <= diff_sector_angle_limit <= 180,
            "Diff sector angle limit must be in the range [0, 180]",
            ConfigException,
        )
        planner_assert(
            near_far_length_ratio > 0,
            "Near far length ratio must be positive",
            ConfigException,
        )
        planner_assert(
            0 <= near_far_angle_limit <= 180,
            "Near far angle limit must be in [0, 180]",
            ConfigException,
        )
        planner_assert(
            number_of_channels >= 1,
            "Number of channels must be at least 1",
            ConfigException,
        )
        planner_assert(
            backhaul_link_redundancy_ratio >= 0
            and backhaul_link_redundancy_ratio <= 1,
            "Backhaul link redundancy ratio must be in [0, 1]",
            ConfigException,
        )
        planner_assert(
            num_threads is None or num_threads > 0,
            "Number of threads must be positive",
            ConfigException,
        )
        planner_assert(
            min_cost_max_time > 0
            and redundancy_max_time > 0
            and interference_max_time > 0
            and pop_proposal_max_time > 0
            and demand_site_max_time > 0,
            "Maximum solver time must be positive",
            ConfigException,
        )
        planner_assert(
            availability_max_time > 0,
            "Maximum availability solver time must be positive",
        )
        if candidate_topology_file_path is not None:
            assert_file_extension(
                candidate_topology_file_path,
                {"kml", "kmz", "zip"},
                "CANDIDATE_TOPOLOGY_FILE_PATH",
            )
        self.pop_site_capex = pop_site_capex
        self.cn_site_capex = cn_site_capex
        self.dn_site_capex = dn_site_capex
        self.device_list = device_list
        self.rain_rate = rain_rate
        self.budget = budget
        self.pop_capacity = pop_capacity
        self.oversubscription = oversubscription
        self.carrier_frequency = carrier_frequency
        self.thermal_noise_power = thermal_noise_power
        self.noise_figure = noise_figure
        self.maximum_eirp = maximum_eirp
        self.enable_cn_demand = enable_cn_demand
        self.enable_uniform_demand = enable_uniform_demand
        self.enable_manual_demand = enable_manual_demand
        self.demand_spacing = demand_spacing
        self.demand_connection_radius = demand_connection_radius
        self.demand = demand
        self.number_of_extra_pops = number_of_extra_pops
        self.dn_dn_sector_limit = dn_dn_sector_limit
        self.dn_total_sector_limit = dn_total_sector_limit
        self.maximum_number_hops = maximum_number_hops
        self.diff_sector_angle_limit = diff_sector_angle_limit
        self.near_far_length_ratio = near_far_length_ratio
        self.near_far_angle_limit = near_far_angle_limit
        self.number_of_channels = number_of_channels
        self.maximize_common_bandwidth = maximize_common_bandwidth
        self.always_active_pops = always_active_pops
        self.enable_legacy_redundancy_method = enable_legacy_redundancy_method
        self.redundancy_level = redundancy_level
        self.backhaul_link_redundancy_ratio = backhaul_link_redundancy_ratio
        self.num_threads = num_threads
        self.min_cost_rel_stop = min_cost_rel_stop
        self.min_cost_max_time = min_cost_max_time
        self.redundancy_rel_stop = redundancy_rel_stop
        self.redundancy_max_time = redundancy_max_time
        self.max_coverage_rel_stop = max_coverage_rel_stop
        self.max_coverage_max_time = max_coverage_max_time
        self.interference_rel_stop = interference_rel_stop
        self.interference_max_time = interference_max_time
        self.pop_proposal_rel_stop = pop_proposal_rel_stop
        self.pop_proposal_max_time = pop_proposal_max_time
        self.demand_site_max_time = demand_site_max_time
        self.topology_routing = topology_routing
        self.availability_sim_time = availability_sim_time
        self.availability_seed = availability_seed
        self.availability_max_time = availability_max_time
        self.candidate_topology_file_path = candidate_topology_file_path

        self.link_availability_percentage = link_availability_percentage
        _populate_project_level_parameter(
            self.device_list,
            carrier_frequency,
            thermal_noise_power,
            noise_figure,
            rain_rate,
            link_availability_percentage,
        )

        # Internal parameters, not provided by users.
        self.coverage_percentage = 1.0
        self.ignore_polarities = False


class SystemParams(ConfigParser):
    def __init__(
        self,
        output_dir: str = "./",
        debug_mode: bool = False,
        logger_level: LoggerLevel = LoggerLevel.INFO,
        log_file: Optional[str] = None,
        log_to_stderr: bool = True,
    ) -> None:
        self.output_dir = output_dir
        self.debug_mode = debug_mode
        self.logger_level = logger_level
        self.log_file = log_file
        self.log_to_stderr = log_to_stderr


def _populate_project_level_parameter(
    device_list: List[DeviceData],
    carrier_frequency: float,
    thermal_noise_power: float,
    noise_figure: float,
    rain_rate: float,
    link_availability_percentage: float,
) -> None:
    """
    Populate project-level parameters to the sector parameters of each device
    """
    for device in device_list:
        device.sector_params.carrier_frequency = carrier_frequency
        device.sector_params.thermal_noise_power = thermal_noise_power
        device.sector_params.noise_figure = noise_figure
        device.sector_params.rain_rate = rain_rate
        device.sector_params.link_availability_percentage = (
            link_availability_percentage
        )


def _check_duplicated_devices(device_list: List[DeviceData]) -> None:
    sku_set = set()
    for device in device_list:
        if device.device_sku.casefold() in sku_set:
            raise ConfigException(
                f"There are duplicated device skus: {device.device_sku}. "
                "Note that the device sku is case insensitive."
            )
        sku_set.add(device.device_sku.casefold())
