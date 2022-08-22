# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import (
    PolarityType,
    StatusType,
)
from terragraph_planner.common.data_io.data_key import (
    LinkKey,
    SectorKey,
    SiteKey,
)
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    square_topology,
    square_topology_with_cns,
)
from terragraph_planner.optimization.structs import Capex, TopologyCounts
from terragraph_planner.optimization.topology_report import analyze


class TestTopologyReport(TestCase):
    def test_square_topology(self) -> None:
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = square_topology()

        # Manually generate an optimized topology
        even_sites = {"DN1", "DN4", "POP5"}
        for site_id, site in topology.sites.items():
            site.status_type = StatusType.PROPOSED
            if site_id in even_sites:
                site.polarity = PolarityType.EVEN
            else:
                site.polarity = PolarityType.ODD
        for sector in topology.sectors.values():
            sector.status_type = StatusType.PROPOSED
            sector.channel = 0
        proposed_links = {
            "DN1-DN2",
            "DN2-DN1",
            "DN1-POP5",
            "POP5-DN1",
            "DN2-POP6",
            "POP6-DN2",
            "DN3-DN4",
            "DN3-POP6",
            "POP6-DN3",
            "DN4-DN3",
            "DN4-POP5",
            "POP5-DN4",
        }
        for link_id in proposed_links:
            topology.links[link_id].status_type = StatusType.PROPOSED

        result = analyze(topology, params)

        result_outgoing_flows = result.site_df[
            SiteKey.OUTGOING_FLOW.value.output_name
        ].to_list()
        expected_outgoing_flows = [0.0, 0.0, 0.9, 0.0, 1.8, 3.6]
        for i in range(len(result_outgoing_flows)):
            self.assertAlmostEqual(
                result_outgoing_flows[i], expected_outgoing_flows[i], 6
            )
        result_incoming_flows = result.site_df[
            SiteKey.INCOMING_FLOW.value.output_name
        ].to_list()
        expected_incoming_flows = [0.9, 1.8, 1.8, 1.8, 0.0, 0.0]
        for i in range(len(result_incoming_flows)):
            self.assertAlmostEqual(
                result_incoming_flows[i], expected_incoming_flows[i], 6
            )
        self.assertEqual(
            result.site_df[SiteKey.BREAKDOWNS.value.output_name].to_list(),
            [1, 1, 1, 1, 0, 0],
        )

        result_proposed_flows = result.link_df[
            LinkKey.PROPOSED_FLOW.value.output_name
        ].to_list()
        expected_proposed_flows = [
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.9,
            0.0,
            0.9,
            0.0,
            0.9,
            0.0,
            1.8,
            0.0,
            1.8,
            0.0,
        ]
        for i in range(len(result_proposed_flows)):
            self.assertAlmostEqual(
                result_proposed_flows[i], expected_proposed_flows[i], 6
            )
        self.assertEqual(
            result.sector_df[SectorKey.CHANNEL.value.output_name].to_list(),
            ["0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
        )
        self.assertEqual(
            result.metrics.capex,
            Capex(total_capex=11750.0, proposed_capex=11750.0),
        )
        self.assertEqual(
            result.metrics.counts,
            TopologyCounts(
                active_sites=6,
                total_sites=6,
                active_pop_sites=2,
                total_pop_sites=2,
                active_dn_sites=4,
                total_dn_sites=4,
                active_cn_sites=0,
                connectable_dn_sites=4,
                connectable_cn_sites=0,
                total_cn_sites=0,
                active_cns_with_backup_dns=0,
                active_demand_connected_cn_sites=0,
                active_demand_connected_dn_sites=4,
                active_demand_connected_pop_sites=0,
                active_nodes=11,
                total_nodes=11,
                active_dn_nodes=11,
                total_dn_nodes=11,
                active_cn_nodes=0,
                total_cn_nodes=0,
                active_sectors=11,
                total_sectors=11,
                active_dn_sectors_on_dns=8,
                active_dn_sectors_on_pops=3,
                active_cn_sectors=0,
                active_backhaul_links=6,
                total_backhaul_links=8,
                active_access_links=0,
                total_access_links=0,
                active_wired_links=0,
                total_wired_links=0,
            ),
        )
        self.assertIsNotNone(result.metrics.flow_metrics)
        flow_metrics = none_throws(result.metrics.flow_metrics)
        self.assertAlmostEqual(flow_metrics.total_bandwidth, 5.4, 6)
        self.assertAlmostEqual(
            flow_metrics.minimum_bandwdith_for_connected_demand, 0.9, 6
        )
        self.assertAlmostEqual(
            flow_metrics.link_capacity_utilization.avg, 58.333333, 6
        )
        self.assertAlmostEqual(
            flow_metrics.link_capacity_utilization.max, 100.0, 6
        )
        self.assertAlmostEqual(
            flow_metrics.link_capacity_utilization.min, 0.0, 6
        )

    def test_square_topology_with_cns(self) -> None:
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = square_topology_with_cns()

        # Manually generate an optimized topology
        proposed_sites = {
            "DN3": PolarityType.EVEN,
            "DN4": PolarityType.ODD,
            "POP5": PolarityType.EVEN,
            "POP6": PolarityType.ODD,
            "CN7": PolarityType.UNASSIGNED,
            "CN8": PolarityType.UNASSIGNED,
        }
        for site_id, polarity in proposed_sites.items():
            topology.sites[site_id].status_type = StatusType.PROPOSED
            topology.sites[site_id].polarity = polarity
        for sector in topology.sectors.values():
            if sector.site.site_id in proposed_sites:
                sector.status_type = StatusType.PROPOSED
                sector.channel = 0
        proposed_links = {
            "DN3-DN4",
            "DN4-DN3",
            "DN3-POP6",
            "POP6-DN3",
            "DN4-POP5",
            "POP5-DN4",
            "DN4-CN7",
            "DN4-CN8",
        }
        for link_id in proposed_links:
            topology.links[link_id].status_type = StatusType.PROPOSED

        result = analyze(topology, params)

        result_outgoing_flows = result.site_df[
            SiteKey.OUTGOING_FLOW.value.output_name
        ].to_list()
        expected_outgoing_flows = [0.0, 0.0, 0.0, 1.8, 1.8, 0.0, 0.0, 0.0]
        for i in range(len(result_outgoing_flows)):
            self.assertAlmostEqual(
                result_outgoing_flows[i], expected_outgoing_flows[i], 6
            )
        result_incoming_flows = result.site_df[
            SiteKey.INCOMING_FLOW.value.output_name
        ].to_list()
        expected_incoming_flows = [0.0, 0.0, 0.0, 1.8, 0.0, 0.0, 0.9, 0.9]
        for i in range(len(result_incoming_flows)):
            self.assertAlmostEqual(
                result_incoming_flows[i], expected_incoming_flows[i], 6
            )
        self.assertEqual(
            result.site_df[SiteKey.BREAKDOWNS.value.output_name].to_list(),
            [0, 0, 0, 2, 0, 0, 0, 0],
        )

        result_proposed_flows = result.link_df[
            LinkKey.PROPOSED_FLOW.value.output_name
        ].to_list()
        expected_proposed_flows = [
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.8,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.9,
            0.9,
        ]
        for i in range(len(result_proposed_flows)):
            self.assertAlmostEqual(
                result_proposed_flows[i], expected_proposed_flows[i], 6
            )
        self.assertEqual(
            result.sector_df[SectorKey.CHANNEL.value.output_name].to_list(),
            ["0", "0", "0", "0", "0", "0", "0", "0", "0"],
        )
        self.assertEqual(
            result.metrics.capex,
            Capex(total_capex=11050.0, proposed_capex=11050.0),
        )
        self.assertEqual(
            result.metrics.counts,
            TopologyCounts(
                active_sites=6,
                total_sites=8,
                active_pop_sites=2,
                total_pop_sites=2,
                active_dn_sites=2,
                total_dn_sites=4,
                active_cn_sites=2,
                connectable_dn_sites=4,
                connectable_cn_sites=2,
                total_cn_sites=2,
                active_cns_with_backup_dns=0,
                active_demand_connected_cn_sites=2,
                active_demand_connected_dn_sites=0,
                active_demand_connected_pop_sites=0,
                active_nodes=9,
                total_nodes=13,
                active_dn_nodes=7,
                total_dn_nodes=11,
                active_cn_nodes=2,
                total_cn_nodes=2,
                active_sectors=9,
                total_sectors=13,
                active_dn_sectors_on_dns=4,
                active_dn_sectors_on_pops=3,
                active_cn_sectors=2,
                active_backhaul_links=3,
                total_backhaul_links=8,
                active_access_links=2,
                total_access_links=2,
                active_wired_links=0,
                total_wired_links=0,
            ),
        )
        self.assertIsNotNone(result.metrics.flow_metrics)
        flow_metrics = none_throws(result.metrics.flow_metrics)
        self.assertAlmostEqual(flow_metrics.total_bandwidth, 1.8, 6)
        self.assertAlmostEqual(
            flow_metrics.minimum_bandwdith_for_connected_demand, 0.9, 6
        )
        self.assertAlmostEqual(
            flow_metrics.link_capacity_utilization.avg, 40.0, 6
        )
        self.assertAlmostEqual(
            flow_metrics.link_capacity_utilization.max, 100.0, 6
        )
        self.assertAlmostEqual(
            flow_metrics.link_capacity_utilization.min, 0.0, 6
        )
