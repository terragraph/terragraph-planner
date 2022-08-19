# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from terragraph_planner.common.configuration.enums import StatusType
from terragraph_planner.common.data_io.utils import (
    extract_topology_from_kml_file,
)
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    set_topology_proposed,
    square_topology,
    square_topology_with_cns,
    square_topology_with_cns_with_multi_dns,
)
from terragraph_planner.optimization.topology_component_counter import (
    count_topology_components,
)

DATA_PATH = "terragraph_planner/common/data_io/test/test_data/"


class TestComponentCounter(TestCase):
    def test_square_topology(self) -> None:
        topology = square_topology()
        set_topology_proposed(topology)

        component_counts, _, _ = count_topology_components(topology)

        self.assertEqual(component_counts.active_sectors, 11)
        self.assertEqual(component_counts.active_dn_sectors_on_pops, 3)
        self.assertEqual(component_counts.active_dn_sectors_on_dns, 8)
        self.assertEqual(component_counts.active_cn_sectors, 0)

        self.assertEqual(component_counts.active_backhaul_links, 8)
        self.assertEqual(component_counts.active_access_links, 0)
        self.assertEqual(component_counts.active_pop_sites, 2)
        self.assertEqual(component_counts.active_dn_sites, 4)
        self.assertEqual(component_counts.active_cn_sites, 0)
        self.assertEqual(component_counts.active_demand_connected_pop_sites, 0)
        self.assertEqual(component_counts.active_demand_connected_dn_sites, 4)
        self.assertEqual(component_counts.active_demand_connected_cn_sites, 0)

        self.assertEqual(component_counts.total_backhaul_links, 8)
        self.assertEqual(component_counts.total_access_links, 0)
        self.assertEqual(component_counts.total_pop_sites, 2)
        self.assertEqual(component_counts.total_dn_sites, 4)
        self.assertEqual(component_counts.total_cn_sites, 0)

    def test_square_topology_with_cns(self) -> None:
        topology = square_topology_with_cns()
        set_topology_proposed(topology)

        component_counts, _, _ = count_topology_components(topology)

        self.assertEqual(component_counts.active_sectors, 13)
        self.assertEqual(component_counts.active_dn_sectors_on_pops, 3)
        self.assertEqual(component_counts.active_dn_sectors_on_dns, 8)
        self.assertEqual(component_counts.active_cn_sectors, 2)

        self.assertEqual(component_counts.active_backhaul_links, 8)
        self.assertEqual(component_counts.active_access_links, 2)
        self.assertEqual(component_counts.active_pop_sites, 2)
        self.assertEqual(component_counts.active_dn_sites, 4)
        self.assertEqual(component_counts.active_cn_sites, 2)
        self.assertEqual(component_counts.active_demand_connected_pop_sites, 0)
        self.assertEqual(component_counts.active_demand_connected_dn_sites, 0)
        self.assertEqual(component_counts.active_demand_connected_cn_sites, 2)
        self.assertEqual(component_counts.active_cns_with_backup_dns, 0)

        self.assertEqual(component_counts.total_backhaul_links, 8)
        self.assertEqual(component_counts.total_access_links, 2)
        self.assertEqual(component_counts.total_pop_sites, 2)
        self.assertEqual(component_counts.total_dn_sites, 4)
        self.assertEqual(component_counts.total_cn_sites, 2)

    def test_square_topology_with_cns_multi_dns(self) -> None:
        topology = square_topology_with_cns_with_multi_dns()
        set_topology_proposed(topology)
        topology.links["DN3-CN8"].status_type = StatusType.UNREACHABLE

        component_counts, _, _ = count_topology_components(topology)

        self.assertEqual(component_counts.active_sectors, 13)
        self.assertEqual(component_counts.active_dn_sectors_on_pops, 3)
        self.assertEqual(component_counts.active_dn_sectors_on_dns, 8)
        self.assertEqual(component_counts.active_cn_sectors, 2)

        self.assertEqual(component_counts.active_backhaul_links, 8)
        self.assertEqual(component_counts.active_access_links, 2)
        self.assertEqual(component_counts.active_pop_sites, 2)
        self.assertEqual(component_counts.active_dn_sites, 4)
        self.assertEqual(component_counts.active_cn_sites, 2)
        self.assertEqual(component_counts.active_demand_connected_pop_sites, 0)
        self.assertEqual(component_counts.active_demand_connected_dn_sites, 0)
        self.assertEqual(component_counts.active_demand_connected_cn_sites, 2)
        self.assertEqual(component_counts.active_cns_with_backup_dns, 1)

        self.assertEqual(component_counts.total_backhaul_links, 8)
        self.assertEqual(component_counts.total_access_links, 3)
        self.assertEqual(component_counts.total_pop_sites, 2)
        self.assertEqual(component_counts.total_dn_sites, 4)
        self.assertEqual(component_counts.total_cn_sites, 2)

    def test_square_topology_with_unreachable_site(self) -> None:
        topology = square_topology()
        set_topology_proposed(topology)
        topology.sites["DN1"].status_type = StatusType.UNREACHABLE

        component_counts, _, _ = count_topology_components(topology)

        self.assertEqual(component_counts.active_sectors, 11)
        self.assertEqual(component_counts.active_dn_sectors_on_pops, 3)
        self.assertEqual(component_counts.active_dn_sectors_on_dns, 8)
        self.assertEqual(component_counts.active_cn_sectors, 0)

        self.assertEqual(component_counts.active_backhaul_links, 8)
        self.assertEqual(component_counts.active_access_links, 0)
        self.assertEqual(component_counts.active_pop_sites, 2)
        self.assertEqual(component_counts.active_dn_sites, 3)
        self.assertEqual(component_counts.active_cn_sites, 0)
        self.assertEqual(component_counts.active_demand_connected_pop_sites, 0)
        self.assertEqual(component_counts.active_demand_connected_dn_sites, 3)
        self.assertEqual(component_counts.active_demand_connected_cn_sites, 0)

        self.assertEqual(component_counts.total_backhaul_links, 8)
        self.assertEqual(component_counts.total_access_links, 0)
        self.assertEqual(component_counts.total_pop_sites, 2)
        self.assertEqual(component_counts.total_dn_sites, 4)
        self.assertEqual(component_counts.total_cn_sites, 0)

    def test_sku_metrics(self) -> None:
        kml_file_path = DATA_PATH + "test_raw_square_topology.kml"
        topology = extract_topology_from_kml_file(
            kml_file_path, [DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE], None
        )

        # All sites are candidate, active_site_sku_counter should be empty
        _, active_site_sku_counter, _ = count_topology_components(topology)
        self.assertEqual(len(active_site_sku_counter), 0)

        # Now test when all sites are proposed
        set_topology_proposed(topology)

        _, active_site_sku_counter, _ = count_topology_components(topology)
        self.assertEqual(
            active_site_sku_counter[DEFAULT_DN_DEVICE.device_sku],
            6,
        )

    def test_topology_with_disconnected_sites(self) -> None:
        topology = square_topology_with_cns()

        # Remove links around DN2 and CN7
        links_to_remove = {
            "POP6-DN2",
            "DN2-POP6",
            "DN1-DN2",
            "DN2-DN1",
            "DN2-DN3",
            "DN3-DN2",
            "DN4-CN7",
        }
        for link in links_to_remove:
            topology.remove_link(link)

        set_topology_proposed(topology)

        component_counts, _, _ = count_topology_components(topology)

        self.assertEqual(component_counts.active_sectors, 13)
        self.assertEqual(component_counts.active_dn_sectors_on_pops, 3)
        self.assertEqual(component_counts.active_dn_sectors_on_dns, 8)
        self.assertEqual(component_counts.active_cn_sectors, 2)

        self.assertEqual(component_counts.active_backhaul_links, 5)
        self.assertEqual(component_counts.active_access_links, 1)
        self.assertEqual(component_counts.active_pop_sites, 2)
        self.assertEqual(component_counts.active_dn_sites, 4)
        self.assertEqual(component_counts.active_cn_sites, 2)
        self.assertEqual(component_counts.active_demand_connected_pop_sites, 0)
        self.assertEqual(component_counts.active_demand_connected_dn_sites, 0)
        self.assertEqual(component_counts.active_demand_connected_cn_sites, 2)
        self.assertEqual(component_counts.active_cns_with_backup_dns, 0)

        self.assertEqual(component_counts.total_backhaul_links, 5)
        self.assertEqual(component_counts.total_access_links, 1)
        self.assertEqual(component_counts.total_pop_sites, 2)
        self.assertEqual(component_counts.total_dn_sites, 4)
        self.assertEqual(component_counts.total_cn_sites, 2)

        self.assertEqual(component_counts.connectable_dn_sites, 3)
        self.assertEqual(component_counts.connectable_cn_sites, 1)
