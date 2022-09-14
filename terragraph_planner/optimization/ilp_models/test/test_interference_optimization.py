# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from copy import deepcopy
from unittest import TestCase

import xpress as xp
from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import SiteType, StatusType
from terragraph_planner.common.geos import angle_delta
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    different_sector_angle_topology,
    dn_cn_limit_topology,
    dn_dn_limit_topology,
    intersecting_links_topology,
    square_topology,
    square_topology_with_cns,
    square_topology_with_cns_with_multi_dns,
)
from terragraph_planner.optimization.ilp_models.interference_optimization import (
    MinInterferenceNetwork,
)
from terragraph_planner.optimization.topology_interference import (
    compute_link_interference,
)


class TestInterferenceOptimization(TestCase):
    def test_max_common_bandwidth(self) -> None:
        """
        Test interference minimization with maximize common bandwidth enabled
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            maximize_common_bandwidth=True,
        )
        topology = square_topology_with_cns(params)

        proposed_sites = {"POP5", "DN4", "CN7", "CN8"}
        for site_id in proposed_sites:
            topology.sites[site_id].status_type = StatusType.PROPOSED
        topology.links["DN4-CN8"].capacity = 0.02

        interfering_rsl = compute_link_interference(
            topology, params.maximum_eirp
        )

        # Validate behavior of max common bandwidth
        min_int_network = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        )
        self.assertEqual(
            len(min_int_network.connected_demand_sites),
            2,
        )

        solution = min_int_network.solve()
        self.assertIsNotNone(solution)

        common_buffer = min_int_network.problem.getSolution(
            min_int_network.common_bandwidth
        )
        delta = 1e-8  # some annoying numerical issues
        self.assertGreaterEqual(
            solution.flow_decisions[("DN4", "CN7")], common_buffer - delta
        )
        self.assertGreaterEqual(
            solution.flow_decisions[("DN4", "CN8")], common_buffer - delta
        )
        for demand_id, demand in topology.demand_sites.items():
            actual_buffer = (
                none_throws(demand.demand)
                - solution.shortage_decisions[demand_id]
            )
            self.assertGreaterEqual(actual_buffer, common_buffer - delta)

        # Validate that candidate sites are are excluded in determining connected
        # demand sites
        topology.sites["CN8"].status_type = StatusType.CANDIDATE
        self.assertEqual(
            len(
                MinInterferenceNetwork(
                    topology,
                    params,
                    [],
                    interfering_rsl,
                ).connected_demand_sites
            ),
            1,
        )
        topology.sites["CN8"].status_type = StatusType.PROPOSED

        # Validate the behavior with one of the demand sites cut-off
        topology.links["DN4-CN8"].capacity = 0
        min_int_network_filtered = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        )
        self.assertEqual(
            len(min_int_network_filtered.connected_demand_sites),
            1,
        )

        solution_filtered = min_int_network_filtered.solve()
        self.assertIsNotNone(solution_filtered)

        common_buffer_filtered = min_int_network_filtered.problem.getSolution(
            min_int_network_filtered.common_bandwidth
        )
        self.assertEqual(common_buffer_filtered, 0.025)
        self.assertGreaterEqual(
            solution_filtered.flow_decisions[("DN4", "CN7")],
            common_buffer_filtered - delta,
        )
        self.assertGreaterEqual(common_buffer_filtered, common_buffer)

        # Validate behavior of determining connected demand sites if polarities
        # are ignored
        topology.links["DN4-CN8"].capacity = 0.02
        params.ignore_polarities = True

        # Validate that candidate sites are are excluded in determining connected
        # demand sites
        topology.sites["CN8"].status_type = StatusType.CANDIDATE
        self.assertEqual(
            len(
                MinInterferenceNetwork(
                    topology,
                    params,
                    [],
                    interfering_rsl,
                ).connected_demand_sites
            ),
            1,
        )
        topology.sites["CN8"].status_type = StatusType.PROPOSED

        # Validate the behavior with one of the demand sites cut-off
        topology.links["DN4-CN8"].capacity = 0
        self.assertEqual(
            len(
                MinInterferenceNetwork(
                    topology,
                    params,
                    [],
                    interfering_rsl,
                ).connected_demand_sites
            ),
            1,
        )

    def test_multi_channel_interference(self) -> None:
        """
        Test multi-channel decisions in interference minimization
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            demand=1.8,  # Max demand that can be satisfied with 0 interference
        )
        topology = intersecting_links_topology(params)

        for site in topology.sites.values():
            site.status_type = StatusType.PROPOSED
        topology.links["DN1-DN4"]._status_type = StatusType.UNAVAILABLE
        topology.links["DN4-DN1"]._status_type = StatusType.UNAVAILABLE
        topology.links["DN2-DN3"]._status_type = StatusType.UNAVAILABLE
        topology.links["DN3-DN2"]._status_type = StatusType.UNAVAILABLE

        interfering_rsl = compute_link_interference(
            topology, params.maximum_eirp
        )

        # First solve with single channel
        params.number_of_channels = 1
        one_channel_solution = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        ).solve()
        self.assertIsNotNone(one_channel_solution)

        # Check that not all demand can be satisfied with a single channel
        self.assertGreater(
            sum(one_channel_solution.shortage_decisions.values()), 0
        )

        # Flow into demand equals actual demand - shortage
        demand_flow = {demand_id: 0.0 for demand_id in topology.demand_sites}
        for (_, site_id2), flow in one_channel_solution.flow_decisions.items():
            if site_id2 in topology.demand_sites:
                demand_flow[site_id2] += flow
        for demand_site_id, flow in demand_flow.items():
            self.assertEqual(
                flow,
                params.demand
                - one_channel_solution.shortage_decisions[demand_site_id],
            )

        # Without multi-channel, i.e. all channels are default 0,
        # links "DN1-DN2" and "DN3-DN4" suffer interference
        params.number_of_channels = 2
        two_channel_solution = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        ).solve()
        self.assertIsNotNone(two_channel_solution)

        # Check that more of the demand can be satisfied with two channels
        # compared to one channel
        self.assertGreater(
            sum(one_channel_solution.shortage_decisions.values()),
            sum(two_channel_solution.shortage_decisions.values()),
        )

        # Based on the link budgets in this topology and the request demand,
        # in this case the shortage should be 0 with two channels
        self.assertEqual(
            sum(two_channel_solution.shortage_decisions.values()), 0
        )

        # Flow into demand equals actual demand
        demand_flow = {demand_id: 0.0 for demand_id in topology.demand_sites}
        for (_, site_id2), flow in two_channel_solution.flow_decisions.items():
            if site_id2 in topology.demand_sites:
                demand_flow[site_id2] += flow
        for flow in demand_flow.values():
            self.assertEqual(flow, params.demand)

        # Verify consistent channel assignments
        channel1 = two_channel_solution.channel_decisions[("DN1", "DN1-0-0-DN")]
        channel2 = two_channel_solution.channel_decisions[("DN3", "DN3-0-0-DN")]
        self.assertNotEqual(channel1, channel2)
        self.assertEqual(
            two_channel_solution.channel_decisions[("DN2", "DN2-1-0-DN")],
            channel1,
        )
        self.assertEqual(
            two_channel_solution.channel_decisions[("DN4", "DN4-1-0-DN")],
            channel2,
        )

    def test_interference_on_cns(self) -> None:
        """
        Test determination of interfering links for CNs. Namely verify that
        interfering paths that are not within the horizontal scan range of
        the active link cannot cause any additional interference.
        """
        # Use a deeop copy of DEFAULT_CN_DEVICE so updates made to it cannot
        # impact other tests
        ANOTHER_CN_DEVICE = deepcopy(DEFAULT_CN_DEVICE)
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, ANOTHER_CN_DEVICE],
        )
        params.ignore_polarities = True  # So there can be interference
        topology = square_topology_with_cns_with_multi_dns(params)
        # Update CNs to use the correct device
        for site in topology.sites.values():
            if site.site_type == SiteType.CN:
                site._device = ANOTHER_CN_DEVICE

        for site_id in ["DN3", "DN4", "POP5", "POP6", "CN7", "CN8"]:
            topology.sites[site_id].status_type = StatusType.PROPOSED

        angle_between = abs(
            angle_delta(
                topology.links["DN4-CN8"].rx_beam_azimuth,
                topology.links["DN3-CN8"].rx_beam_azimuth,
            )
        )

        # Set CN scan range to just large enough to include both links
        topology.sites["CN8"].device.sector_params.horizontal_scan_range = (
            2 * angle_between + 1.0
        )

        interfering_rsl = compute_link_interference(
            topology, params.maximum_eirp
        )
        min_int_network = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        )

        solution = min_int_network.solve()
        self.assertIsNotNone(solution)

        # Ensure there is flow on link DN4-CN7 which will cause interference
        # on link DN3-CN8 via interfering path link DN4-CN8
        self.assertGreater(solution.flow_decisions[("DN4", "CN7")], 0)
        self.assertGreater(solution.tdm_decisions[("DN4", "CN7")], 0)

        risl = {}
        for link_id in ["DN4-CN7", "DN4-CN8", "DN3-CN8"]:
            link = topology.links[link_id]
            risl[link_id] = xp.evaluate(  # pyre-ignore
                min_int_network.get_interfering_rsl_expr(
                    link.tx_site.site_id,
                    link.rx_site.site_id,
                    none_throws(link.rx_sector).sector_id,
                    0,
                ),
                problem=min_int_network.problem,
            )[0]
        # DN4-CN7 does not have any interferers; at least one of DN4-CN8 or
        # DN3-CN8 will be interfered on
        self.assertEqual(risl["DN4-CN7"], 0)
        self.assertGreater(risl["DN4-CN8"] + risl["DN3-CN8"], 0)

        # Set CN scan range to just large enough to not include both links
        topology.sites["CN8"].device.sector_params.horizontal_scan_range = (
            2 * angle_between - 1.0
        )

        interfering_rsl = compute_link_interference(
            topology, params.maximum_eirp
        )
        min_int_network = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        )

        solution = min_int_network.solve()
        self.assertIsNotNone(solution)

        # Ensure there is flow on link DN4-CN7 which would've caused interference
        # on link DN3-CN8 via interfering path link DN4-CN8 if it was within the
        # scan range
        self.assertGreater(solution.flow_decisions[("DN4", "CN7")], 0)
        self.assertGreater(solution.tdm_decisions[("DN4", "CN7")], 0)

        for link_id in ["DN4-CN7", "DN4-CN8", "DN3-CN8"]:
            link = topology.links[link_id]
            risl = xp.evaluate(  # pyre-ignore
                min_int_network.get_interfering_rsl_expr(
                    link.tx_site.site_id,
                    link.rx_site.site_id,
                    none_throws(link.rx_sector).sector_id,
                    0,
                ),
                problem=min_int_network.problem,
            )[0]
            # There should be no interferers due to links not being within each
            # other's scan range
            self.assertEqual(risl, 0)

    def test_optimization_with_built_link_triangle(self) -> None:
        """
        Set the triangle of links POP5<->DN1<->DN4<->POP5 in the square
        topology to be existing. Due to polarity restrictions, this should
        cause infeasibility.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = square_topology(params)
        sites = ["POP5", "DN1", "DN4"]
        links = [
            "POP5-DN1",
            "DN1-POP5",
            "POP5-DN4",
            "DN4-POP5",
            "DN1-DN4",
            "DN4-DN1",
        ]
        for site_id in sites:
            topology.sites[site_id]._status_type = StatusType.EXISTING
        for sector in topology.sectors.values():
            if sector.site.site_id in sites:
                sector._status_type = StatusType.EXISTING
        for link_id in links:
            topology.links[link_id]._status_type = StatusType.EXISTING

        # Due to polarity restrictions, ILP is infeasible
        interfering_rsl = compute_link_interference(
            topology, params.maximum_eirp
        )
        solution = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        ).solve()
        self.assertIsNone(solution)

        # After relaxing polarity constraints, ILP should be feasible
        params.ignore_polarities = True
        solution = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        ).solve()
        self.assertIsNotNone(solution)
        self.assertEqual(solution.even_site_decisions, {})
        self.assertEqual(solution.odd_site_decisions, {})

    def test_dn_dn_limit(self) -> None:
        """
        Verify that the DN-DN limit constraint is enforced in interference
        minimization.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            dn_dn_sector_limit=2,
        )
        topology = dn_dn_limit_topology(params)
        for site in topology.sites.values():
            site.status_type = StatusType.PROPOSED

        # Verify that only 2 of the 3 links are selected
        interfering_rsl = compute_link_interference(
            topology, params.maximum_eirp
        )
        solution = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        ).solve()
        self.assertIsNotNone(solution)

        num_pop_links = sum(
            [
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ]
                for link in topology.links.values()
                if link.tx_site.site_type == SiteType.POP
            ]
        )
        self.assertEqual(num_pop_links, 2)

        # If we relax the DN-DN sector limit, then all three links are selected
        params.dn_dn_sector_limit = 3
        solution = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        ).solve()
        self.assertIsNotNone(solution)

        num_pop_links = sum(
            [
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ]
                for link in topology.links.values()
                if link.tx_site.site_type == SiteType.POP
            ]
        )
        self.assertEqual(num_pop_links, 3)

    def test_dn_cn_limit(self) -> None:
        """
        Verify that the DN-CN limit constraint is enforced in interference
        minimization.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            dn_total_sector_limit=7,
        )
        topology = dn_cn_limit_topology(params)
        for site in topology.sites.values():
            site.status_type = StatusType.PROPOSED

        # Verify that only 7 of the 8 links are selected
        interfering_rsl = compute_link_interference(
            topology, params.maximum_eirp
        )
        solution = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        ).solve()
        self.assertIsNotNone(solution)

        num_pop_links = sum(
            [
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ]
                for link in topology.links.values()
                if link.tx_site.site_type == SiteType.POP
            ]
        )
        self.assertEqual(num_pop_links, 7)

        # If we relax the DN-CN sector limit, then all eight links are selected
        params.dn_total_sector_limit = 8
        solution = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        ).solve()
        self.assertIsNotNone(solution)

        num_pop_links = sum(
            [
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ]
                for link in topology.links.values()
                if link.tx_site.site_type == SiteType.POP
            ]
        )
        self.assertEqual(num_pop_links, 8)

    def test_angle_violation_limits(self) -> None:
        """
        Verify that the angle limit constraint is enforced in interference
        minimization.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            dn_total_sector_limit=7,
        )
        topology = different_sector_angle_topology(params)
        for site in topology.sites.values():
            site.status_type = StatusType.PROPOSED

        interfering_rsl = compute_link_interference(
            topology, params.maximum_eirp
        )
        angle_violations = [("POP0", "DN1", "DN2")]
        solution = MinInterferenceNetwork(
            topology, params, angle_violations, interfering_rsl
        ).solve()
        self.assertIsNotNone(solution)

        self.assertEqual(
            solution.link_decisions[("POP0", "DN1")]
            + solution.link_decisions[("POP0", "DN2")],
            1,
        )

        solution = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        ).solve()
        self.assertIsNotNone(solution)

        self.assertEqual(
            solution.link_decisions[("POP0", "DN1")]
            + solution.link_decisions[("POP0", "DN2")],
            2,
        )
