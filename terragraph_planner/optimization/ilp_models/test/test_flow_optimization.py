# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import StatusType
from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.topology_models.demand_site import DemandSite
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    flow_tree_topology,
    set_topology_proposed,
    square_topology,
    square_topology_with_cns,
)
from terragraph_planner.optimization.ilp_models.flow_optimization import (
    MaxFlowNetwork,
)


class TestFlowOptimization(TestCase):
    def test_optimization_on_square(self) -> None:
        """
        Test various attributes of flow optimization on the square topology
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = square_topology(params)
        set_topology_proposed(topology)

        solution = MaxFlowNetwork(topology, params).solve()
        self.assertIsNotNone(solution)

        # Ensure that the flow balance constraints hold.
        self.assertGreater(solution.buffer_decision, 0)
        demand_flow = {demand_id: 0.0 for demand_id in topology.demand_sites}
        for (_, site_id2), flow in solution.flow_decisions.items():
            if site_id2 in topology.demand_sites:
                demand_flow[site_id2] += flow
        for flow in demand_flow.values():
            self.assertEqual(flow, solution.buffer_decision)

    def test_optimization_on_square_with_cns(self) -> None:
        """
        Test various attributes of flow optimization on the square topology
        with CNs
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = square_topology_with_cns(params)
        set_topology_proposed(topology)

        solution = MaxFlowNetwork(topology, params).solve()
        self.assertIsNotNone(solution)

        self.assertGreater(solution.buffer_decision, 0)
        self.assertEqual(
            solution.flow_decisions[("DN4", "CN7")], solution.buffer_decision
        )
        self.assertEqual(
            solution.flow_decisions[("DN4", "CN8")], solution.buffer_decision
        )

        # This assumes that flow path is from POP5->DN4->CN7/8
        self.assertAlmostEqual(
            solution.flow_decisions[("POP5", "DN4")],
            topology.links["POP5-DN4"].capacity,
            places=6,
        )

    def test_optimization_on_tree(self) -> None:
        """
        Test flow optimization tree topology. Namely, make the DN1<->DN4,
        DN1<->DN5, DN4<->DN5, DN2<->DN3 and DN3<->DN4 candidates and everything
        else proposed. Also make DN4 and POP5 candidates. Now we have a tree
        rooted at POP6, i.e., POP6->DN3, POP6<->DN2, and DN2<->DN1.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = square_topology(params)
        # Leave only one demand site on each site
        for demand_id in list(topology.demand_sites.keys()):
            if len(topology.demand_sites[demand_id].connected_sites) > 1:
                topology.remove_demand_site(demand_id)
        set_topology_proposed(topology)

        # Deactivate some links and add a couple demand sites
        candidate_links = {
            "DN1-DN4",
            "DN4-DN1",
            "DN1-POP5",
            "POP5-DN1",
            "DN4-POP5",
            "POP5-DN4",
            "DN2-DN3",
            "DN3-DN2",
            "DN3-DN4",
            "DN4-DN3",
        }
        for link_id in candidate_links:
            topology.links[link_id].status_type = StatusType.CANDIDATE

        candidate_sites = {"DN4", "POP5"}
        for site_id in candidate_sites:
            topology.sites[site_id].status_type = StatusType.CANDIDATE

        solution = MaxFlowNetwork(topology, params).solve()
        self.assertIsNotNone(solution)

        self.assertGreater(solution.buffer_decision, 0)
        for (site1, site2), flow in solution.flow_decisions.items():
            if site2 in topology.demand_sites:
                if site1 in {"POP6", "DN3", "DN2", "DN1"}:
                    self.assertEqual(flow, solution.buffer_decision)
                else:
                    self.assertEqual(flow, 0)

        for link_id, link in topology.links.items():
            if link_id in candidate_links:
                self.assertEqual(
                    solution.flow_decisions[
                        (link.tx_site.site_id, link.rx_site.site_id)
                    ],
                    0,
                )
                self.assertEqual(
                    solution.tdm_decisions[
                        (link.tx_site.site_id, link.rx_site.site_id)
                    ],
                    0,
                )
            else:
                if link_id in {"POP6-DN3", "POP6-DN2", "DN2-DN1"}:
                    self.assertGreater(
                        solution.flow_decisions[
                            (link.tx_site.site_id, link.rx_site.site_id)
                        ],
                        0,
                    )
                else:
                    self.assertEqual(
                        solution.flow_decisions[
                            (link.tx_site.site_id, link.rx_site.site_id)
                        ],
                        0,
                    )
                self.assertEqual(
                    solution.tdm_decisions[
                        (link.tx_site.site_id, link.rx_site.site_id)
                    ],
                    1.0,
                )

        # Only demand sites on DN3, DN2 and DN1 are connected
        self.assertEqual(len(solution.connected_demand_sites), 3)

        # Recreate the topology with large demand; it should not impact the
        # solution
        params.demand = 10.0
        for demand in topology.demand_sites.values():
            demand.demand = params.demand

        solution_large_demand = MaxFlowNetwork(topology, params).solve()
        self.assertIsNotNone(solution_large_demand)

        self.assertEqual(
            solution.flow_decisions, solution_large_demand.flow_decisions
        )
        self.assertEqual(
            solution.buffer_decision, solution_large_demand.buffer_decision
        )

    def test_optimization_with_tiered_demand(self) -> None:
        """
        Test flow optimizatoin with tiered demand
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = square_topology_with_cns(params)

        # Add extra demand site to CN7
        for demand in topology.demand_sites.values():
            connected_site_ids = {
                site.site_id for site in demand.connected_sites
            }
            if "CN7" in connected_site_ids:
                demand.num_sites = 2

        set_topology_proposed(topology)

        solution = MaxFlowNetwork(topology, params).solve()
        self.assertIsNotNone(solution)

        # Verify there is positive flow
        self.assertGreater(solution.buffer_decision, 0)
        # Verify that flow to "CN7" is twice that of flow to "CN8"
        self.assertEqual(
            2 * solution.buffer_decision,
            solution.flow_decisions["DN4", "CN7"],
        )
        self.assertEqual(
            solution.buffer_decision,
            solution.flow_decisions["DN4", "CN8"],
        )

    def test_optimization_with_routing(self) -> None:
        """
        Test flow optimization with routed path (i.e., links marked redundant)
        """
        # For regular topology, flow comes through links ("1", "4") and ("5", "4")
        # to meet the demand of the two CNs connected to site 4
        # For routing topology, ("1", "4") is not on the shortest path to the CNs
        # so flow is only through ("5", "4")
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = square_topology_with_cns(params)
        set_topology_proposed(topology)

        # Adjust capacities so that general flow should come from POP5->DN1->DN4
        # and POP6->DN3->DN4. Note: POP5->DN4 will not have flow because of tdm
        # constraint between DN1->DN4 and POP5->DN4 will select the higher-
        # capacity link
        topology.links["POP5-DN1"].capacity = 0.6
        topology.links["DN1-POP5"].capacity = 0.6
        topology.links["DN1-DN4"].capacity = 0.6
        topology.links["DN4-DN1"].capacity = 0.6
        topology.links["POP5-DN4"].capacity = 0.4
        topology.links["DN4-POP5"].capacity = 0.4
        topology.links["POP6-DN2"].capacity = 0
        topology.links["DN2-POP6"].capacity = 0
        topology.links["POP6-DN3"].capacity = 0.5
        topology.links["DN3-POP6"].capacity = 0.5
        topology.links["DN3-DN2"].capacity = 0
        topology.links["DN2-DN3"].capacity = 0

        solution = MaxFlowNetwork(topology, params).solve()
        self.assertIsNotNone(solution)

        self.assertEqual(solution.flow_decisions[("POP5", "DN1")], 0.6)
        self.assertEqual(solution.flow_decisions[("DN1", "DN4")], 0.6)
        self.assertEqual(solution.flow_decisions[("POP6", "DN3")], 0.5)
        self.assertEqual(solution.flow_decisions[("DN3", "DN4")], 0.5)
        self.assertEqual(solution.flow_decisions[("POP5", "DN4")], 0)

        # Mark some links as redundant; namely those not on the shortest path
        redundant_links = {
            "POP5-DN1",
            "DN1-POP5",
            "DN1-DN4",
            "DN4-DN1",
            "POP6-DN3",
            "DN3-POP6",
            "DN3-DN4",
            "DN4-DN3",
        }
        for link_id in redundant_links:
            topology.links[link_id].is_redundant = True

        solution = MaxFlowNetwork(topology, params).solve()
        self.assertIsNotNone(solution)

        self.assertEqual(solution.flow_decisions[("POP5", "DN1")], 0)
        self.assertEqual(solution.flow_decisions[("DN1", "DN4")], 0)
        self.assertEqual(solution.flow_decisions[("POP6", "DN3")], 0)
        self.assertEqual(solution.flow_decisions[("DN3", "DN4")], 0)
        self.assertEqual(solution.flow_decisions[("POP5", "DN4")], 0.4)

    def test_common_buffer_optimization_on_tree(self) -> None:
        """
        Test flow optimization common buffer behavior on a tree topology
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = flow_tree_topology(params)

        # Update the capacities
        topology.links["POP0-DN1"].capacity = 3.0
        topology.links["DN1-POP0"].capacity = 3.0
        topology.links["POP0-DN2"].capacity = 5.0
        topology.links["DN2-POP0"].capacity = 5.0
        topology.links["DN1-DN3"].capacity = 2.0
        topology.links["DN3-DN1"].capacity = 2.0
        topology.links["DN2-DN4"].capacity = 4.0
        topology.links["DN4-DN2"].capacity = 4.0
        topology.links["DN3-CN5"].capacity = 3
        topology.links["DN4-CN6"].capacity = 5
        topology.links["DN1-CN7"].capacity = 3

        set_topology_proposed(topology)

        solution = MaxFlowNetwork(topology, params).solve()
        self.assertIsNotNone(solution)

        # Due to POP->DN1 capacity at 3, each downstream demand takes half of
        # that, so common buffer is 1.5
        self.assertEqual(solution.buffer_decision, 1.5)
        self.assertEqual(len(solution.connected_demand_sites), 3)
        self.assertEqual(solution.flow_decisions[("DN1", "DN3")], 1.5)
        self.assertEqual(solution.flow_decisions[("DN2", "DN4")], 1.5)

        # Now modify the capacity of link DN1->CN7 to be 0
        topology.links["DN1-CN7"].capacity = 0

        solution = MaxFlowNetwork(topology, params).solve()
        self.assertIsNotNone(solution)

        # Now demand at CN7 is disconnected so common buffer is not 2.0
        self.assertEqual(solution.buffer_decision, 2.0)
        self.assertEqual(len(solution.connected_demand_sites), 2)

    def test_optimization_with_disconnected_demand(self) -> None:
        """
        Test flow optimization with disconnected demand site.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = square_topology(params)
        set_topology_proposed(topology)

        solution_connected = MaxFlowNetwork(topology, params).solve()
        self.assertIsNotNone(solution_connected)

        buffer_connected = solution_connected.buffer_decision
        self.assertGreater(buffer_connected, 0)

        topology.add_demand_site(
            DemandSite(
                location=GeoLocation(utm_x=-10, utm_y=-10, utm_epsg=32631),
                demand=params.demand,
            )
        )

        solution_disconnected = MaxFlowNetwork(topology, params).solve()
        self.assertIsNotNone(solution_disconnected)

        buffer_disconnected = solution_disconnected.buffer_decision
        self.assertEqual(buffer_connected, buffer_disconnected)
