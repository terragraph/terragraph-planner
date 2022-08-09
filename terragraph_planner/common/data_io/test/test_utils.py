# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
import unittest

from terragraph_planner.common.data_io.patterns import DataWorkSpace
from terragraph_planner.common.data_io.topology_serializer import (
    write_to_kml_file,
)
from terragraph_planner.common.data_io.utils import (
    extract_topology_from_csv_files,
    extract_topology_from_kml_file,
)
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    raw_square_topology,
)

DATA_PATH = "terragraph_planner/common/data_io/test/test_data/"


class TestReadWriteTopology(unittest.TestCase):
    def setUp(self) -> None:
        self.device_list = [DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]

    def test_read_kml_write_kml(self) -> None:
        ori_topology = raw_square_topology()
        ds = DataWorkSpace()
        kml_file_path = os.path.join(
            ds.get_a_temp_dir(), "output_raw_square_topology.kml"
        )
        write_to_kml_file(ori_topology, kml_file_path)

        new_topology = extract_topology_from_kml_file(
            kml_file_path, self.device_list
        )
        self.assertEqual(len(ori_topology.sites), len(new_topology.sites))
        self.assertEqual(len(ori_topology.links), len(new_topology.links))
        self.assertEqual(
            len(ori_topology.demand_sites), len(new_topology.demand_sites)
        )

    def test_extract_topology_from_csv_files(self) -> None:
        ori_topology = raw_square_topology()
        sites_csv_file_path = DATA_PATH + "test_raw_square_topology_sites.csv"
        links_csv_file_path = DATA_PATH + "test_raw_square_topology_links.csv"
        new_topology = extract_topology_from_csv_files(
            sites_csv_file_path, links_csv_file_path, self.device_list
        )
        self.assertEqual(len(ori_topology.sites), len(new_topology.sites))
        self.assertEqual(len(ori_topology.links), len(new_topology.links))
