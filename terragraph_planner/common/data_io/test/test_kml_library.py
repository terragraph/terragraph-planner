# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import unittest

from terragraph_planner.common.configuration.enums import (
    LinkType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.data_io.kml_library import (
    extract_boundary_polygon,
    extract_raw_data_from_kml_file,
)

DATA_PATH = "terragraph_planner/common/data_io/test/test_data/"


class TestKmlLibrary(unittest.TestCase):
    def test_extract_raw_data_from_kml(self) -> None:
        kml_file_path = DATA_PATH + "test_raw_square_topology.kml"
        sites, links, demands = extract_raw_data_from_kml_file(kml_file_path)
        self.assertEqual(len(sites), 6)
        self.assertEqual(len(links), 16)
        self.assertEqual(len(demands), 6)

        pop_sites = [site for site in sites if site.site_type == SiteType.POP]
        dn_sites = [site for site in sites if site.site_type == SiteType.DN]
        candidate_sites = [
            site for site in sites if site.status_type == StatusType.CANDIDATE
        ]
        backhaul_links = [
            link
            for link in links
            if link.link_type == LinkType.WIRELESS_BACKHAUL
        ]
        self.assertEqual(len(pop_sites), 2)
        self.assertEqual(len(dn_sites), 4)
        self.assertEqual(len(candidate_sites), 6)
        self.assertEqual(len(backhaul_links), 16)

    def test_get_kml_from_kmz(self) -> None:
        kmz_file_path = DATA_PATH + "test_raw_square_topology.kmz"
        sites, links, demands = extract_raw_data_from_kml_file(kmz_file_path)
        self.assertEqual(len(sites), 6)
        self.assertEqual(len(links), 16)
        self.assertEqual(len(demands), 6)

        pop_sites = [site for site in sites if site.site_type == SiteType.POP]
        dn_sites = [site for site in sites if site.site_type == SiteType.DN]
        candidate_sites = [
            site for site in sites if site.status_type == StatusType.CANDIDATE
        ]
        backhaul_links = [
            link
            for link in links
            if link.link_type == LinkType.WIRELESS_BACKHAUL
        ]
        self.assertEqual(len(pop_sites), 2)
        self.assertEqual(len(dn_sites), 4)
        self.assertEqual(len(candidate_sites), 6)
        self.assertEqual(len(backhaul_links), 16)

    def test_extract_boundary_polygon_from_kml(self) -> None:
        kml_file_path = DATA_PATH + "test_boundary_polygon.kml"
        polygon, utm_epsg_code = extract_boundary_polygon(kml_file_path)
        self.assertEqual(len(list(polygon.exterior.coords)), 7)
        self.assertEqual(utm_epsg_code, 32757)

    def test_extract_boundary_polygon_from_kmz(self) -> None:
        kml_file_path = DATA_PATH + "test_boundary_polygon.kmz"
        polygon, utm_epsg_code = extract_boundary_polygon(kml_file_path)
        self.assertEqual(len(list(polygon.exterior.coords)), 7)
        self.assertEqual(utm_epsg_code, 32757)

    def test_extract_boundary_polygon_from_multipolygon(self) -> None:
        kml_file_path = (
            DATA_PATH + "test_extract_boundary_polygon_from_multipolygon.kml"
        )
        polygon, _ = extract_boundary_polygon(kml_file_path)
        self.assertEqual(len(list(polygon.exterior.coords)), 5)
