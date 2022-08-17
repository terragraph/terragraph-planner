# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple
from unittest import TestCase
from unittest.mock import MagicMock, patch

from shapely.geometry import Polygon

from terragraph_planner.common.configuration.configs import (
    DeviceData,
    GISDataParams,
    LOSParams,
    SectorParams,
)
from terragraph_planner.common.configuration.enums import (
    DeviceType,
    LocationType,
    SiteType,
)
from terragraph_planner.common.data_io.input_sites import InputSites
from terragraph_planner.common.exceptions import ConfigException
from terragraph_planner.common.structs import (
    LinkBudgetMeasurements,
    MCSMap,
    ScanPatternData,
)
from terragraph_planner.common.topology_models.site import Site
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.los.helper import (
    construct_topology_from_los_result,
    get_all_sites_links_and_exclusion_zones,
    get_exclusion_zones,
    get_max_los_dist_for_device_pairs,
    get_site_connectable_status,
    infer_input_site_location,
    pick_best_sites_per_building,
    search_max_los_dist_based_on_capacity,
    select_additional_dns,
)
from terragraph_planner.los.test.helper import (
    MockElevation,
    build_detected_site_for_los_test,
    build_site_for_los_test,
)

MOCK_PATH_PREFIX = "terragraph_planner.los.helper"


# Mock fspl_based_estimation and set 0 crossing at 250.0
ZERO_CROSSING = 250.5


def mock_fspl_based_estimation(
    distance: float,
    max_tx_power: float,
    tx_sector_params: SectorParams,
    rx_sector_params: SectorParams,
    mcs_snr_mbps_map: List[MCSMap],
    tx_deviation: float,
    rx_deviation: float,
    el_deviation: float,
    tx_scan_pattern_data: Optional[ScanPatternData],
    rx_scan_pattern_data: Optional[ScanPatternData],
) -> LinkBudgetMeasurements:
    return LinkBudgetMeasurements(0, 0.0, 0.0, ZERO_CROSSING - distance, 0.0)


def build_rx_tx_neighbors(
    sites: List[Site],
    links: List[Tuple[int, int]],
) -> Tuple[List[List[int]], List[List[int]]]:
    rx_neighbors = [[] for _ in range(len(sites))]
    tx_neighbors = [[] for _ in range(len(sites))]
    for site1, site2 in links:
        if sites[site1].site_type != SiteType.CN:
            rx_neighbors[site1].append(site2)
            tx_neighbors[site2].append(site1)
        if sites[site2].site_type != SiteType.CN:
            rx_neighbors[site2].append(site1)
            tx_neighbors[site1].append(site2)
    return rx_neighbors, tx_neighbors


class TestGetAllSitesLinksAndExclusionZones(TestCase):
    def setUp(self) -> None:
        self.ll_boundary = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
        self.device_list = [DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        self.input_sites = InputSites()
        self.input_sites.add_site(
            build_site_for_los_test(
                latitude=0.5, longitude=0.5, site_type=SiteType.POP
            )
        )
        self.input_sites.add_site(
            build_site_for_los_test(
                latitude=0.9, longitude=0.9, site_type=SiteType.DN
            )
        )
        self.detected_sites = [
            build_detected_site_for_los_test(
                latitude=0.1,
                longitude=0.1,
                site_type=SiteType.DN,
                building_id=1,
            ),
            build_detected_site_for_los_test(
                latitude=0.1,
                longitude=0.2,
                site_type=SiteType.DN,
                building_id=2,
            ),
            build_detected_site_for_los_test(
                latitude=0.19,
                longitude=0.2,
                site_type=SiteType.CN,
                building_id=2,
            ),
        ]
        self.surface_elevation = MockElevation(
            crs_epsg_code=32631, uniform_value=3
        )
        self.terrain_elevation = MockElevation(
            crs_epsg_code=32631, uniform_value=1
        )

    @patch(
        f"{MOCK_PATH_PREFIX}.get_exclusion_zones",
        MagicMock(return_value=[Polygon([(0.4, 0.4), (0.4, 0.6), (0.5, 0.7)])]),
    )
    @patch(f"{MOCK_PATH_PREFIX}.InputSitesLoader.read_user_input")
    def test_get_without_base_topology(
        self, mock_read_user_input: MagicMock
    ) -> None:
        mock_read_user_input.return_value = self.input_sites
        gis_data_params = GISDataParams(
            boundary_polygon_file_path="BOUNDARY_POLYGON.KML",
        )
        los_params = LOSParams(
            device_list=self.device_list,
        )
        (
            sites,
            candidate_links,
            existing_links,
            exclusion_zones,
        ) = get_all_sites_links_and_exclusion_zones(
            gis_data_params,
            los_params,
            self.ll_boundary,
            self.detected_sites,
            self.surface_elevation,
            self.terrain_elevation,
        )
        self.assertEqual(len(sites), 5)
        self.assertEqual(
            candidate_links,
            [
                (0, 1, True),
                (0, 2, True),
                (0, 3, True),
                (0, 4, False),
                (1, 2, True),
                (1, 3, True),
                (1, 4, False),
                (2, 3, True),
                (2, 4, False),
                (3, 4, False),
            ],
        )
        self.assertEqual(len(existing_links), 0)
        self.assertEqual(len(exclusion_zones), 1)

    @patch(f"{MOCK_PATH_PREFIX}.extract_topology_from_file")
    @patch(f"{MOCK_PATH_PREFIX}.InputSitesLoader.read_user_input")
    def test_get_with_base_topology(
        self,
        mock_read_user_input: MagicMock,
        mock_extract_topology_from_kml_file: MagicMock,
    ) -> None:
        mock_read_user_input.return_value = self.input_sites

        # Mock extract base topology
        base_topology = Topology()
        pop_site = build_site_for_los_test(
            latitude=0.6, longitude=0.7, site_type=SiteType.POP
        )
        dn_site = build_site_for_los_test(
            latitude=0.9, longitude=0.8, site_type=SiteType.DN
        )
        cn_site = build_site_for_los_test(
            latitude=0.7, longitude=0.8, site_type=SiteType.CN
        )
        base_topology.add_site(pop_site)
        base_topology.add_site(dn_site)
        base_topology.add_site(cn_site)
        base_topology.add_link_from_site_ids(pop_site.site_id, dn_site.site_id)
        base_topology.add_link_from_site_ids(dn_site.site_id, pop_site.site_id)
        base_topology.add_link_from_site_ids(dn_site.site_id, cn_site.site_id)
        mock_extract_topology_from_kml_file.return_value = base_topology

        gis_data_params = GISDataParams(
            boundary_polygon_file_path="BOUNDARY_POLYGON.KML",
            base_topology_file_path="BASE_TOPOLOGY.KMZ",
        )
        los_params = LOSParams(device_list=self.device_list)

        (
            sites,
            candidate_links,
            existing_links,
            exclusion_zones,
        ) = get_all_sites_links_and_exclusion_zones(
            gis_data_params,
            los_params,
            self.ll_boundary,
            self.detected_sites,
            self.surface_elevation,
            self.terrain_elevation,
        )
        self.assertEqual(len(sites), 8)
        self.assertEqual(
            candidate_links,
            [
                (0, 1, True),
                (0, 2, True),
                (0, 3, True),
                (0, 4, False),
                (0, 6, True),
                (0, 7, False),
                (1, 2, True),
                (1, 3, True),
                (1, 4, False),
                (1, 5, True),
                (1, 6, True),
                (1, 7, False),
                (2, 3, True),
                (2, 4, False),
                (2, 5, True),
                (2, 6, True),
                (2, 7, False),
                (3, 4, False),
                (3, 5, True),
                (3, 6, True),
                (3, 7, False),
                (5, 4, False),
                (6, 4, False),
            ],
        )
        self.assertEqual(
            existing_links,
            [
                (5, 6, 1.0),
                (6, 5, 1.0),
                (6, 7, 1.0),
            ],
        )
        self.assertEqual(len(exclusion_zones), 0)

    @patch(f"{MOCK_PATH_PREFIX}.extract_polygons")
    def test_get_exclusion_zones(
        self, mock_extract_polygons: MagicMock
    ) -> None:
        mock_extract_polygons.return_value = [
            Polygon([(0.4, 0.4), (0.4, 0.6), (0.5, 0.7)])
        ]
        # The only exclusion zone is contained by the boundary
        self.assertEqual(
            len(get_exclusion_zones("EXCLUSION_ZONES.KMZ", self.ll_boundary)), 1
        )
        # The user input is not in KML/KMZ format
        self.assertEqual(
            len(get_exclusion_zones("EXCLUSION_ZONES.CSV", self.ll_boundary)), 0
        )
        # One of the polygons are filter out
        mock_extract_polygons.return_value = [
            Polygon([(0.4, 0.4), (0.4, 0.6), (0.5, 0.7)]),
            Polygon([(0.4, 1.4), (0.4, 0.6), (0.5, 0.7)]),
        ]
        self.assertEqual(
            len(get_exclusion_zones("EXCLUSION_ZONES.KMZ", self.ll_boundary)), 1
        )

    def test_infer_input_site_location(self) -> None:
        # Just use it when altitude is given
        location, location_type = infer_input_site_location(
            latitude=0,
            longitude=0,
            altitude=123,
            height=None,
            location_type=LocationType.UNKNOWN,
            site_type=SiteType.POP,
            surface_elevation=None,
            terrain_elevation=None,
            mounting_height_above_rooftop=2,
            default_pop_height_on_pole=10,
            default_dn_height_on_pole=8,
            default_cn_height_on_pole=5,
        )
        self.assertEqual(location.altitude, 123)
        self.assertEqual(location_type, LocationType.UNKNOWN)
        # Cannot do anything when surface elevation data is not given
        location, location_type = infer_input_site_location(
            latitude=0,
            longitude=0,
            altitude=None,
            height=5,
            location_type=LocationType.UNKNOWN,
            site_type=SiteType.POP,
            surface_elevation=None,
            terrain_elevation=None,
            mounting_height_above_rooftop=2,
            default_pop_height_on_pole=10,
            default_dn_height_on_pole=8,
            default_cn_height_on_pole=5,
        )
        self.assertIsNone(location.altitude)
        self.assertEqual(location_type, LocationType.UNKNOWN)
        # Infer the altitude when height and surface elevation are given
        location, location_type = infer_input_site_location(
            latitude=0,
            longitude=0,
            altitude=None,
            height=123,
            location_type=LocationType.UNKNOWN,
            site_type=SiteType.POP,
            surface_elevation=self.surface_elevation,
            terrain_elevation=None,
            mounting_height_above_rooftop=2,
            default_pop_height_on_pole=10,
            default_dn_height_on_pole=8,
            default_cn_height_on_pole=5,
        )
        self.assertEqual(location.altitude, 126)
        self.assertEqual(location_type, LocationType.UNKNOWN)
        # Use the default pop height when the location type and height is unknown
        location, location_type = infer_input_site_location(
            latitude=0,
            longitude=0,
            altitude=None,
            height=None,
            location_type=LocationType.UNKNOWN,
            site_type=SiteType.POP,
            surface_elevation=self.surface_elevation,
            terrain_elevation=None,
            mounting_height_above_rooftop=2,
            default_pop_height_on_pole=10,
            default_dn_height_on_pole=8,
            default_cn_height_on_pole=5,
        )
        self.assertEqual(
            location.altitude, 13
        )  # surface + default_pop_height_on_pole
        self.assertEqual(location_type, LocationType.UNKNOWN)
        # Infer the location type when both surface and terrain data are given
        location, location_type = infer_input_site_location(
            latitude=0,
            longitude=0,
            altitude=None,
            height=None,
            location_type=LocationType.UNKNOWN,
            site_type=SiteType.POP,
            surface_elevation=self.surface_elevation,
            terrain_elevation=self.terrain_elevation,
            mounting_height_above_rooftop=2,
            default_pop_height_on_pole=10,
            default_dn_height_on_pole=8,
            default_cn_height_on_pole=5,
        )
        self.assertEqual(
            location.altitude, 5
        )  # surface + mounting_height_above_rooftop
        self.assertEqual(location_type, LocationType.ROOFTOP)
        # The difference between surface and terrain elevation is not large enough
        location, location_type = infer_input_site_location(
            latitude=0,
            longitude=0,
            altitude=None,
            height=None,
            location_type=LocationType.UNKNOWN,
            site_type=SiteType.DN,
            surface_elevation=self.surface_elevation,
            terrain_elevation=MockElevation(
                crs_epsg_code=32631, uniform_value=2
            ),
            mounting_height_above_rooftop=2,
            default_pop_height_on_pole=10,
            default_dn_height_on_pole=8,
            default_cn_height_on_pole=5,
        )
        self.assertEqual(
            location.altitude, 11
        )  # surface + default_dn_height_on_pole
        self.assertEqual(location_type, LocationType.STREET_LEVEL)
        # Use the input location type rooftop even if the difference is not large enough
        location, location_type = infer_input_site_location(
            latitude=0,
            longitude=0,
            altitude=None,
            height=None,
            location_type=LocationType.ROOFTOP,
            site_type=SiteType.DN,
            surface_elevation=self.surface_elevation,
            terrain_elevation=MockElevation(
                crs_epsg_code=32631, uniform_value=2
            ),
            mounting_height_above_rooftop=2,
            default_pop_height_on_pole=10,
            default_dn_height_on_pole=8,
            default_cn_height_on_pole=5,
        )
        self.assertEqual(
            location.altitude, 5
        )  # surface + default_dn_height_on_pole
        self.assertEqual(location_type, LocationType.ROOFTOP)


class TestGetMaxLosDistForDevicePairs(TestCase):
    def setUp(self) -> None:
        self.sector_params = SectorParams()

    def device_builder(
        self, device_sku: str, device_type: DeviceType
    ) -> DeviceData:
        return DeviceData(
            device_sku=device_sku,
            sector_params=self.sector_params,
            node_capex=250,
            device_type=device_type,
        )

    @patch(
        f"{MOCK_PATH_PREFIX}.fspl_based_estimation",
        MagicMock(side_effect=mock_fspl_based_estimation),
    )
    def test_search_max_los_dist_with_good_bound(self) -> None:
        max_los_distance = search_max_los_dist_based_on_capacity(
            lower_bound=0,
            upper_bound=math.ceil(ZERO_CROSSING * 100),
            max_tx_power=12.3,
            tx_sector_params=self.sector_params,
            rx_sector_params=self.sector_params,
            mcs_snr_mbps_map=[],
        )
        self.assertEqual(max_los_distance, math.ceil(ZERO_CROSSING))

    @patch(
        f"{MOCK_PATH_PREFIX}.fspl_based_estimation",
        MagicMock(side_effect=mock_fspl_based_estimation),
    )
    def test_search_max_los_dist_with_small_upper_bound(self) -> None:
        max_los_distance = search_max_los_dist_based_on_capacity(
            lower_bound=0,
            upper_bound=math.floor(ZERO_CROSSING),
            max_tx_power=12.3,
            tx_sector_params=self.sector_params,
            rx_sector_params=self.sector_params,
            mcs_snr_mbps_map=[],
        )
        self.assertIsNone(max_los_distance)

    @patch(
        f"{MOCK_PATH_PREFIX}.fspl_based_estimation",
        MagicMock(side_effect=mock_fspl_based_estimation),
    )
    def test_search_max_los_dist_with_large_lower_bound(self) -> None:
        lower_bound = math.ceil(ZERO_CROSSING * 2)
        max_los_distance = search_max_los_dist_based_on_capacity(
            lower_bound=lower_bound,
            upper_bound=math.ceil(ZERO_CROSSING * 100),
            max_tx_power=12.3,
            tx_sector_params=self.sector_params,
            rx_sector_params=self.sector_params,
            mcs_snr_mbps_map=[],
        )
        self.assertEqual(max_los_distance, lower_bound)

    @patch(
        f"{MOCK_PATH_PREFIX}.search_max_los_dist_based_on_capacity",
        MagicMock(side_effect=[120, 100, 130, 140, 170, 150]),
    )
    def test_get_max_los_dist_for_device_pairs(self) -> None:
        device_skus = ["dn_device0", "dn_device1", "cn_device"]
        device_types = [DeviceType.DN, DeviceType.DN, DeviceType.CN]
        device_list = [
            self.device_builder(device_skus[i], device_types[i])
            for i in range(3)
        ]
        device_pair_to_max_los_dist = get_max_los_dist_for_device_pairs(
            device_list, 41, None, None, None
        )
        # CN device cannot be the transmitter
        expected_valid_device_pairs = [
            (device_skus[0], device_skus[0]),
            (device_skus[0], device_skus[1]),
            (device_skus[0], device_skus[2]),
            (device_skus[1], device_skus[0]),
            (device_skus[1], device_skus[1]),
            (device_skus[1], device_skus[2]),
        ]
        self.assertEqual(
            set(device_pair_to_max_los_dist.keys()),
            set(expected_valid_device_pairs),
        )
        # Max LOS distance of dn_device0 -> dn_device1 should be overwritten with
        # the max LOS distance of dn_device1 -> dn_device0
        expected_max_los_distance = [120, 140, 130, 140, 170, 150]
        for k, v in zip(expected_valid_device_pairs, expected_max_los_distance):
            self.assertEqual(device_pair_to_max_los_dist[k], v)

    def test_get_max_los_dist_for_device_pairs_min_mcs(self) -> None:
        # Make second CN device long distance
        device_list = [
            DeviceData(
                device_sku="CN Device 1",
                device_type=DeviceType.CN,
                sector_params=SectorParams(antenna_boresight_gain=22),
            ),
            DeviceData(
                device_sku="CN Device 2",
                device_type=DeviceType.CN,
                sector_params=SectorParams(antenna_boresight_gain=45),
            ),
            DeviceData(
                device_sku="DN Device",
                device_type=DeviceType.DN,
                sector_params=SectorParams(antenna_boresight_gain=22),
            ),
        ]

        dist_wout_minmcs = get_max_los_dist_for_device_pairs(
            device_list,
            max_eirp_dbm=41,
            min_dn_dn_mcs=None,
            min_dn_cn_mcs=None,
            los_upper_bound=None,
        )
        dist_with_minmcs = get_max_los_dist_for_device_pairs(
            device_list,
            max_eirp_dbm=41,
            min_dn_dn_mcs=9,
            min_dn_cn_mcs=5,
            los_upper_bound=None,
        )

        # Distance without a min MCS should always be greater than
        # the distance with a specified min MCS
        for key, dist in dist_wout_minmcs.items():
            self.assertGreater(dist, dist_with_minmcs[key])
            self.assertGreater(dist_with_minmcs[key], 0)  # sanity check

        # Distance with long range equipment should be larger
        key_short = ("DN Device", "CN Device 1")
        key_long = ("DN Device", "CN Device 2")
        self.assertGreater(
            dist_wout_minmcs[key_long], dist_wout_minmcs[key_short]
        )
        self.assertGreater(
            dist_with_minmcs[key_long], dist_with_minmcs[key_short]
        )

        # DN-CN1 should be longer than DN-DN for min mcs case because
        # min_dn_dn_mcs=9 > min_dn_cn_mcs=5 (and other link budget parameters
        # are the same)
        key_dn = ("DN Device", "DN Device")
        self.assertGreater(
            dist_with_minmcs[key_short], dist_with_minmcs[key_dn]
        )

        # Min MCS 13 exceeds the MCS table and should error
        with self.assertRaises(ConfigException):
            get_max_los_dist_for_device_pairs(
                device_list,
                max_eirp_dbm=41,
                min_dn_dn_mcs=13,
                min_dn_cn_mcs=None,
                los_upper_bound=None,
            )

        with self.assertRaises(ConfigException):
            get_max_los_dist_for_device_pairs(
                device_list,
                max_eirp_dbm=41,
                min_dn_dn_mcs=None,
                min_dn_cn_mcs=13,
                los_upper_bound=None,
            )


class TestPickBestSitesPerBuilding(TestCase):
    def test_with_dn_deployment(self) -> None:
        site_building_ids = [None, None, None, 0, 0, 0, 1, 1, 1]
        sites = [
            build_site_for_los_test()
            if building_id is None
            else build_detected_site_for_los_test(building_id=building_id)
            for building_id in site_building_ids
        ]

        links = [
            (0, 3),
            (0, 7),
            (1, 3),
            (1, 4),
            (1, 7),
            (1, 8),
            (2, 3),
            (2, 4),
            (2, 5),
            (2, 6),
            (2, 7),
            (2, 8),
            (3, 7),
        ]
        rx_neighbors, tx_neighbors = build_rx_tx_neighbors(sites, links)
        picked_sites = pick_best_sites_per_building(
            sites, rx_neighbors, tx_neighbors, True, defaultdict(lambda: 1.0)
        )
        self.assertEqual(picked_sites, [0, 1, 2, 3, 9, 7, 10])
        self.assertEqual(len(sites), 11)

    def test_without_dn_deployment(self) -> None:
        site_building_ids = [None, None, None, 0, 0, 0, 1, 1, 1]
        sites = [
            build_site_for_los_test()
            if building_id is None
            else build_detected_site_for_los_test(building_id=building_id)
            for building_id in site_building_ids
        ]
        links = [
            (0, 3),
            (0, 7),
            (1, 3),
            (1, 4),
            (1, 7),
            (1, 8),
            (2, 3),
            (2, 4),
            (2, 5),
            (2, 6),
            (2, 7),
            (2, 8),
            (3, 7),
        ]
        rx_neighbors, tx_neighbors = build_rx_tx_neighbors(sites, links)
        picked_sites = pick_best_sites_per_building(
            sites,
            rx_neighbors,
            tx_neighbors,
            False,
            defaultdict(lambda: 1.0),
        )
        self.assertEqual(picked_sites, [0, 1, 2, 9, 10])
        self.assertEqual(len(sites), 11)


class TestSelectAdditionalDNs(TestCase):
    def test_get_site_connectable_status(self) -> None:
        all_site_types = (
            [SiteType.POP] * 2 + [SiteType.DN] * 4 + [SiteType.CN] * 5
        )
        all_sites = [
            build_site_for_los_test(site_type=site_type)
            for site_type in all_site_types
        ]
        links = [
            (0, 2),
            (1, 3),
            (1, 4),
            (1, 5),
            (2, 3),
            (3, 8),
            (4, 8),
            (5, 9),
            (5, 10),
        ]
        rx_neighbors, _ = build_rx_tx_neighbors(all_sites, links)
        picked_sites = [0, 1, 2, 4, 5, 6, 8, 9]
        (
            connected_sites,
            unconnected_sites,
            potential_connectable_sites,
            potential_other_sites,
        ) = get_site_connectable_status(all_sites, rx_neighbors, picked_sites)
        self.assertSetEqual(connected_sites, {0, 1, 2, 4, 5, 8, 9})
        self.assertSetEqual(unconnected_sites, {6})
        self.assertSetEqual(potential_connectable_sites, {3, 10})
        self.assertSetEqual(potential_other_sites, {7})

    def test_select_additional_dns(self) -> None:
        all_site_types = (
            [SiteType.POP] * 1 + [SiteType.DN] * 5 + [SiteType.CN] * 7
        )
        all_sites = [
            build_site_for_los_test(site_type=site_type)
            for site_type in all_site_types
        ]
        links = [
            (0, 1),
            (0, 2),
            (0, 3),
            (0, 4),
            (1, 6),
            (2, 5),
            (2, 7),
            (2, 11),
            (4, 9),
            (5, 8),
            (5, 10),
        ]
        rx_neighbors, tx_neighbors = build_rx_tx_neighbors(all_sites, links)
        picked_sites = [0, 1, 4, 7, 8, 9, 11]
        additional_dns = select_additional_dns(
            all_sites, rx_neighbors, tx_neighbors, picked_sites
        )
        self.assertSetEqual(set(additional_dns), {2, 5})


class TestConstructTopologyFromLOSResult(TestCase):
    def setUp(self) -> None:
        self.confidence_dict = defaultdict(lambda: 0.95)
        self.device0 = DeviceData(
            device_sku="device0",
            device_type=DeviceType.DN,
            sector_params=SectorParams(),
        )
        self.device1 = DeviceData(
            device_sku="device1",
            device_type=DeviceType.DN,
            sector_params=SectorParams(),
        )
        self.device_pair_to_max_los_dist: Dict[Tuple[str, str], int] = {
            (self.device0.device_sku, self.device0.device_sku): 1,
            (self.device0.device_sku, self.device1.device_sku): 2,
            (self.device1.device_sku, self.device0.device_sku): 3,
            (self.device1.device_sku, self.device1.device_sku): 4,
        }
        self.min_los_distance = 0

    def validate_topology(
        self,
        topology: Topology,
        num_sites: int,
        num_links: int,
        expected_links: Set[str],
    ) -> None:
        self.assertEqual(len(topology.sites), num_sites)
        self.assertEqual(len(topology.links), num_links)
        result_links = set()
        for link in topology.links.values():
            tx_site = link.tx_site
            rx_site = link.rx_site
            result_links.add(
                f"{tx_site.utm_x}_{tx_site.device.device_sku}-{rx_site.utm_x}_{rx_site.device.device_sku}"
            )
        self.assertEqual(expected_links, result_links)

    def test_construct_with_multiple_devices_on_detected_sites(self) -> None:
        # 6 sites have non-zero distance, and each site has 2 device options.
        # Set max los dist for device pairs. It will filter out some candidate links
        sites = [build_detected_site_for_los_test(utm_x=i) for i in range(6)]
        links = [(0, 1), (0, 2), (0, 4), (2, 4), (2, 5), (4, 5)]
        rx_neighbors, _ = build_rx_tx_neighbors(sites, links)  # pyre-ignore
        picked_sites = [0, 4, 5]
        topology = construct_topology_from_los_result(
            sites=sites,  # pyre-ignore
            rx_neighbors=rx_neighbors,
            picked_sites=picked_sites,
            confidence_dict=self.confidence_dict,
            device_list=[self.device0, self.device1],
            device_pair_to_max_los_dist=self.device_pair_to_max_los_dist,
            min_los_dist=self.min_los_distance,
        )
        expected_links = {
            "0_device1-4_device1",
            "4_device1-0_device1",
            "4_device0-5_device0",
            "4_device0-5_device1",
            "4_device1-5_device0",
            "4_device1-5_device1",
            "5_device0-4_device0",
            "5_device0-4_device1",
            "5_device1-4_device0",
            "5_device1-4_device1",
        }
        self.validate_topology(topology, 6, 10, expected_links)

    def test_construct_with_human_input_sites_with_sku(self) -> None:
        devices = [
            self.device1,
            self.device1,
            self.device0,
            self.device0,
            self.device1,
            self.device0,
        ]
        sites = [
            build_site_for_los_test(utm_x=i, device=devices[i])
            for i in range(6)
        ]
        links = [(0, 1), (0, 2), (0, 4), (2, 4), (2, 5), (4, 5)]
        rx_neighbors, _ = build_rx_tx_neighbors(sites, links)
        picked_sites = [0, 4, 5]
        topology = construct_topology_from_los_result(
            sites=sites,
            rx_neighbors=rx_neighbors,
            picked_sites=picked_sites,
            confidence_dict=self.confidence_dict,
            device_list=[self.device0, self.device1],
            device_pair_to_max_los_dist=self.device_pair_to_max_los_dist,
            min_los_dist=self.min_los_distance,
        )
        expected_links = {
            "0_device1-4_device1",
            "4_device1-0_device1",
            "4_device1-5_device0",
            "5_device0-4_device1",
        }
        self.validate_topology(topology, 3, 4, expected_links)

    def test_construct_with_both_detected_and_input(self) -> None:
        sites = [
            build_site_for_los_test(utm_x=0, device=self.device1),
            build_detected_site_for_los_test(utm_x=1),
            build_site_for_los_test(utm_x=2, device=self.device0),
            build_site_for_los_test(utm_x=3, device=self.device1),
            build_detected_site_for_los_test(utm_x=4),
            build_detected_site_for_los_test(utm_x=5),
        ]
        links = [(0, 1), (0, 2), (0, 4), (2, 4), (2, 5), (4, 5)]
        rx_neighbors, _ = build_rx_tx_neighbors(sites, links)
        picked_sites = [0, 4, 5]
        topology = construct_topology_from_los_result(
            sites=sites,
            rx_neighbors=rx_neighbors,
            picked_sites=picked_sites,
            confidence_dict=self.confidence_dict,
            device_list=[self.device0, self.device1],
            device_pair_to_max_los_dist=self.device_pair_to_max_los_dist,
            min_los_dist=self.min_los_distance,
        )
        expected_links = {
            "0_device1-4_device1",
            "4_device0-5_device0",
            "4_device0-5_device1",
            "4_device1-0_device1",
            "4_device1-5_device0",
            "4_device1-5_device1",
            "5_device0-4_device0",
            "5_device0-4_device1",
            "5_device1-4_device0",
            "5_device1-4_device1",
        }
        # Like test_construct_with_multiple_devices_on_detected_sites, there are 10 links,
        # but unlike that, there are 5 sites instead of 6, because sites[0] is inputed with
        # specific device
        self.validate_topology(topology, 5, 10, expected_links)

    def test_construct_with_filtered_links(self) -> None:
        sites = [
            build_site_for_los_test(utm_x=0, altitude=0, device=self.device0),
            build_site_for_los_test(
                utm_x=0.5, altitude=0.2, device=self.device0
            ),
            build_site_for_los_test(utm_x=1.5, altitude=0, device=self.device0),
            build_site_for_los_test(
                utm_x=-0.5, altitude=0.3, device=self.device0
            ),
        ]
        links = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
        rx_neighbors, _ = build_rx_tx_neighbors(sites, links)
        picked_sites = [0, 1, 2, 3]
        topology = construct_topology_from_los_result(
            sites=sites,
            rx_neighbors=rx_neighbors,
            picked_sites=picked_sites,
            confidence_dict=self.confidence_dict,
            device_list=[self.device0, self.device1],
            device_pair_to_max_los_dist=self.device_pair_to_max_los_dist,
            min_los_dist=self.min_los_distance,
        )
        # The first two sites will be connected. The third site exceeds max
        # distance and the fourth site exceeds elevation deviation
        expected_links = {
            "0_device0-0.5_device0",
            "0.5_device0-0_device0",
        }
        self.validate_topology(topology, 4, 2, expected_links)
