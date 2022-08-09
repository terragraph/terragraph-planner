# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
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
from terragraph_planner.optimization.topology_optimization import (
    optimize_topology,
)
from terragraph_planner.optimization.topology_report import analyze


class TestTopologyReport(TestCase):
    def test_square_topology(self) -> None:
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = square_topology()
        optimize_topology(topology, params)
        result = analyze(topology, params)

        result_outgoing_flows = result.site_df[
            SiteKey.OUTGOING_FLOW.value.output_name
        ].to_list()
        expected_outgoing_flows = [0, 0.6, 0, 0.6, 3.6, 3.6]
        for i in range(len(result_outgoing_flows)):
            self.assertAlmostEqual(
                result_outgoing_flows[i], expected_outgoing_flows[i], 6
            )
        result_incoming_flows = result.site_df[
            SiteKey.INCOMING_FLOW.value.output_name
        ].to_list()
        expected_incoming_flows = [2.4, 1.8, 2.4, 1.8, 0.0, 0.0]
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
            0.6,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.6,
            0.0,
            1.8,
            1.8,
            1.8,
            1.8,
        ]
        for i in range(len(result_proposed_flows)):
            self.assertAlmostEqual(
                result_proposed_flows[i], expected_proposed_flows[i], 6
            )
        self.assertEqual(
            result.sector_df[SectorKey.CHANNEL.value.output_name].to_list(),
            ["0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
        )
        self.assertEqual(
            result.metrics.capex,
            Capex(total_capex=12000.0, proposed_capex=12000.0),
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
                active_nodes=12,
                total_nodes=12,
                active_dn_nodes=12,
                total_dn_nodes=12,
                active_cn_nodes=0,
                total_cn_nodes=0,
                active_sectors=12,
                total_sectors=12,
                active_dn_sectors_on_dns=8,
                active_dn_sectors_on_pops=4,
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
        self.assertAlmostEqual(flow_metrics.total_bandwidth, 7.2, 6)
        self.assertAlmostEqual(
            flow_metrics.minimum_bandwdith_for_connected_demand, 1.2, 6
        )
        self.assertAlmostEqual(
            flow_metrics.link_capacity_utilization.avg, 77.777778, 6
        )
        self.assertAlmostEqual(
            flow_metrics.link_capacity_utilization.max, 100.0, 6
        )
        self.assertAlmostEqual(
            flow_metrics.link_capacity_utilization.min, 33.333333, 6
        )

    def test_square_topology_with_cns(self) -> None:
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = square_topology_with_cns()
        optimize_topology(topology, params)
        result = analyze(topology, params)

        result_outgoing_flows = result.site_df[
            SiteKey.OUTGOING_FLOW.value.output_name
        ].to_list()
        expected_outgoing_flows = [0.0, 0.0, 0.0, 0.0, 0.0, 1.8, 1.8, 0.0]
        for i in range(len(result_outgoing_flows)):
            self.assertAlmostEqual(
                result_outgoing_flows[i], expected_outgoing_flows[i], 6
            )
        result_incoming_flows = result.site_df[
            SiteKey.INCOMING_FLOW.value.output_name
        ].to_list()
        expected_incoming_flows = [0.9, 0.9, 0.0, 0.0, 0.0, 1.8, 0.0, 0.0]
        for i in range(len(result_incoming_flows)):
            self.assertAlmostEqual(
                result_incoming_flows[i], expected_incoming_flows[i], 6
            )
        self.assertEqual(
            result.site_df[SiteKey.BREAKDOWNS.value.output_name].to_list(),
            [0, 0, 0, 0, 0, 2, 0, 0],
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
            0.9,
            0.9,
            0.0,
            0.0,
            0.0,
            0.0,
            1.8,
            0.0,
            0.0,
        ]
        for i in range(len(result_proposed_flows)):
            self.assertAlmostEqual(
                result_proposed_flows[i], expected_proposed_flows[i], 6
            )
        self.assertEqual(
            result.sector_df[SectorKey.CHANNEL.value.output_name].to_list(),
            ["0", "0", "0", "0", "0", "0", "0", "0"],
        )
        self.assertEqual(
            result.metrics.capex,
            Capex(total_capex=10800.0, proposed_capex=10800.0),
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
                active_nodes=8,
                total_nodes=12,
                active_dn_nodes=6,
                total_dn_nodes=10,
                active_cn_nodes=2,
                total_cn_nodes=2,
                active_sectors=8,
                total_sectors=12,
                active_dn_sectors_on_dns=4,
                active_dn_sectors_on_pops=2,
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
