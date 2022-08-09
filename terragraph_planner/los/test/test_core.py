# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from copy import deepcopy
from itertools import product
from unittest import TestCase
from unittest.mock import MagicMock, patch

import numpy as np
from osgeo import osr
from shapely.geometry import Polygon

from terragraph_planner.common.configuration.configs import GISDataParams
from terragraph_planner.common.configuration.constants import (
    DEFAULT_CARRIER_FREQUENCY,
)
from terragraph_planner.common.structs import CandidateLOS, UTMBoundingBox
from terragraph_planner.los.building_group import BuildingGroup
from terragraph_planner.los.core import compute_los, load_gis_data
from terragraph_planner.los.elevation import Elevation
from terragraph_planner.los.helper import upsample_to_same_resolution
from terragraph_planner.los.test.helper import build_site_for_los_test

MOCK_PATH_PREFIX = "terragraph_planner.los.core"


class TestCore(TestCase):
    @patch(f"{MOCK_PATH_PREFIX}.extract_boundary_polygon")
    @patch(f"{MOCK_PATH_PREFIX}.BuildingGroupLoader.read")
    @patch(f"{MOCK_PATH_PREFIX}.ElevationLoader.read")
    def test_load_gis_data(
        self,
        mock_elevation_read: MagicMock,
        mock_building_read: MagicMock,
        mock_extract_boundary_polygon: MagicMock,
    ) -> None:
        sr = osr.SpatialReference()
        sr.ImportFromEPSG(32601)
        mock_elevation_read.return_value = Elevation(
            data_matrix=np.array([[1, 2], [3, 4]]),
            utm_bounding_box=UTMBoundingBox(2, 2, 0, 0),
            x_resolution=1,
            y_resolution=1,
            left_top_x=0.5,
            left_top_y=1.5,
            spatial_reference=sr,
            collection_time=None,
        )
        mock_building_read.return_value = BuildingGroup([], sr)
        mock_extract_boundary_polygon.return_value = (
            Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]),
            32601,
        )
        gis_data_params = GISDataParams(
            boundary_polygon_file_path="boundary.kml",
            building_outline_file_path="building_outline.zip",
            dsm_file_paths=["dsm1.tif", "dsm2.tif"],
            dtm_file_path="dtm.tif",
            dhm_file_path="dhm.tif",
        )
        for i in range(16):
            cur_params = deepcopy(gis_data_params)
            if i & 1 == 0:
                cur_params.building_outline_file_path = None
            if i & 2 == 0:
                cur_params.dsm_file_paths = []
            if i & 4 == 0:
                cur_params.dtm_file_path = None
            if i & 8 == 0:
                cur_params.dhm_file_path = None
            boundary, dsm, dtm, building_group = load_gis_data(cur_params)
            self.assertTrue(isinstance(boundary, Polygon))
            self.assertEqual(building_group is None, i & 1 == 0)
            self.assertEqual(
                dsm is None, i & 2 == 0 and (i & 4 == 0 or i & 8 == 0)
            )
            self.assertEqual(
                dtm is None, i & 4 == 0 and (i & 2 == 0 or i & 8 == 0)
            )

    def test_compute_los_without_dsm(self) -> None:
        sites = [build_site_for_los_test(utm_x=i * 10) for i in range(10)]
        candidate_links = [
            CandidateLOS(i, j, False) for i, j in product(range(10), range(10))
        ]
        result1 = compute_los(
            sites,
            candidate_links,
            None,
            [],
            100,
            5,
            1,
            False,
            1,
            DEFAULT_CARRIER_FREQUENCY,
            1,
        )
        # Each of 10 sites has a link to all else
        self.assertEqual(len(result1), 90)

        result2 = compute_los(
            sites,
            candidate_links,
            None,
            [],
            25,
            5,
            1,
            False,
            1,
            DEFAULT_CARRIER_FREQUENCY,
            1,
        )
        # Each of 10 sites, except 0, 1, 8, 9, has a link to its 4 neighbors
        self.assertEqual(len(result2), 34)

    @patch(
        "terragraph_planner.los.helper.EllipsoidalLOSValidator.compute_confidence"
    )
    def test_compute_los_memoization(
        self, mock_compute_confidence: MagicMock
    ) -> None:
        mock_compute_confidence.return_value = 1.0
        sites = [build_site_for_los_test(utm_x=i * 10) for i in range(5)]
        sites += reversed(sites)
        candidate_links = [
            CandidateLOS(i, j, False) for i, j in product(range(10), range(10))
        ]
        valid_los_links = compute_los(
            sites,
            candidate_links,
            None,
            [],
            100,
            5,
            1,
            True,
            1,
            DEFAULT_CARRIER_FREQUENCY,
            1,
        )
        self.assertEqual(len(valid_los_links), 100)
        sites = [
            build_site_for_los_test(utm_x=0, altitude=1),
            build_site_for_los_test(utm_x=10, altitude=1),
            build_site_for_los_test(utm_x=0, altitude=2),
            build_site_for_los_test(utm_x=10, altitude=2),
            build_site_for_los_test(utm_x=0, altitude=1),
            build_site_for_los_test(utm_x=10, altitude=1),
        ]
        candidate_links = [
            CandidateLOS(i, j, False) for i, j in product(range(6), range(6))
        ]
        valid_los_links = compute_los(
            sites,
            candidate_links,
            None,
            [],
            100,
            0,
            1,
            True,
            1,
            DEFAULT_CARRIER_FREQUENCY,
            1,
        )
        self.assertEqual(len(valid_los_links), 36)

    def test_upsample_to_same_resolution(self) -> None:
        data_matrix = np.array([[5, 6], [7, 8], [9, 10]])
        utm_bounding_box = UTMBoundingBox(4, 3, 2, 0)
        left_top_x = 2.5
        left_top_y = 2.5
        x_resolution = 1.0
        y_resolution = 1.0
        sr = osr.SpatialReference()
        test_utm_wkt = sr.ExportToWkt()
        elevation1 = Elevation(
            data_matrix,
            utm_bounding_box,
            x_resolution,
            y_resolution,
            left_top_x,
            left_top_y,
            test_utm_wkt,
            None,
        )
        elevation2 = Elevation(
            data_matrix,
            utm_bounding_box,
            0.5,
            0.5,
            left_top_x,
            left_top_y,
            test_utm_wkt,
            None,
        )
        upsample_to_same_resolution(elevation1, elevation2)
        self.assertEqual(elevation1.x_resolution, elevation2.x_resolution)
        self.assertEqual(elevation1.y_resolution, elevation2.y_resolution)
