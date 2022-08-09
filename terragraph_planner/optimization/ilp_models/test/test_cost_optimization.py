# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import SiteType, StatusType
from terragraph_planner.common.topology_models.test.helper import (
    ANOTHER_DN_DEVICE,
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    hybrid_sites_topology,
    multi_path_topology,
    simple_minimize_cost_topology,
    simple_pop_multi_sku_topology,
    square_topology,
    square_topology_with_cns,
    square_topology_with_colocated_sites,
    tdm_cn_constraint_topology,
)
from terragraph_planner.optimization.ilp_models.cost_optimization import (
    MinCostNetwork,
)


class TestCostOptimization(TestCase):
    def test_optimization_on_square(self) -> None:
        """
        Test various attributes of cost optimization on the square topology
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
        )
        topology = square_topology(params)
        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )

        # All DNs but only one POP proposed
        self.assertIsNotNone(solution)
        for site_id in ["DN1", "DN2", "DN3", "DN4"]:
            self.assertEqual(solution.site_decisions[site_id], 1)
        self.assertEqual(
            solution.site_decisions["POP5"] + solution.site_decisions["POP6"], 1
        )

        # Flow into demand equals actual demand
        demand_flow = {demand_id: 0.0 for demand_id in topology.demand_sites}
        for (_, site_id2), flow in solution.flow_decisions.items():
            if site_id2 in topology.demand_sites:
                demand_flow[site_id2] += flow
        for flow in demand_flow.values():
            self.assertEqual(flow, params.demand)
        self.assertEqual(sum(solution.shortage_decisions.values()), 0)

        # POP5 has 1 sector and POP6 has two sectors, so 0.9 gbps is max demand
        # at all demand sites
        params.demand = 0.9
        for demand in topology.demand_sites.values():
            demand.demand = params.demand

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )

        # Now all DNs and POPs should be proposed
        self.assertIsNotNone(solution)
        for site_id in topology.sites:
            self.assertEqual(solution.site_decisions[site_id], 1)

        # Now full coverage will not be sufficient
        params.demand = 1.0
        for demand in topology.demand_sites.values():
            demand.demand = params.demand

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )
        self.assertIsNone(solution)

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=0.9
        )
        self.assertIsNotNone(solution)

        # Total flow into demand equals total flow scaled by coverage percentage
        total_demand_flow = 0
        for (_, site_id2), flow in solution.flow_decisions.items():
            if site_id2 in topology.demand_sites:
                total_demand_flow += flow
        self.assertAlmostEqual(total_demand_flow, 6 * 1.0 * 0.9, places=6)
        self.assertAlmostEqual(
            sum(solution.shortage_decisions.values()), 6 * 1.0 * 0.1, places=6
        )

    def test_optimization_on_square_with_cns(self) -> None:
        """
        Test various attributes of cost optimization on the square topology
        with CNs
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
        )
        topology = square_topology_with_cns(params)
        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )

        # Only one POP and the DN conencted to the CNs are proposed
        self.assertIsNotNone(solution)
        proposed_sites = {"POP5", "DN4", "CN7", "CN8"}
        for site_id in topology.sites:
            self.assertEqual(
                solution.site_decisions[site_id],
                1 if site_id in proposed_sites else 0,
            )

        self.assertEqual(
            solution.odd_site_decisions["POP5"]
            + solution.even_site_decisions["POP5"],
            1,
        )
        self.assertEqual(
            solution.odd_site_decisions["DN4"]
            + solution.even_site_decisions["DN4"],
            1,
        )
        self.assertEqual(
            solution.odd_site_decisions["POP5"]
            + solution.odd_site_decisions["DN4"],
            1,
        )
        self.assertEqual(
            solution.even_site_decisions["POP5"]
            + solution.even_site_decisions["DN4"],
            1,
        )

        # Flow into the CNs equals actual demand
        for (_, site_id2), flow in solution.flow_decisions.items():
            if (
                site_id2 in topology.sites
                and topology.sites[site_id2].site_type == SiteType.CN
            ):
                self.assertEqual(flow, params.demand)

    def test_max_common_bandwidth(self) -> None:
        """
        Test cost optimization with maximize common bandwidth enabled
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            maximize_common_bandwidth=True,
        )
        topology = square_topology_with_cns(params)
        topology.links["DN4-CN8"].capacity = 0.02

        # Validate behavior of max common bandwidth
        min_cost_network = MinCostNetwork(topology, params)
        self.assertEqual(len(min_cost_network.connected_demand_sites), 2)

        # 0.02/0.025 = 0.8, so that's the minimum coverage percentage with a
        # feasible solution. Due to rounding, we decrease the coverage
        # percentage slightly

        solution = min_cost_network.solve(coverage_percentage=0.81)
        self.assertIsNone(solution)
        solution = min_cost_network.solve(coverage_percentage=0.79)
        self.assertIsNotNone(solution)

        common_buffer = min(
            [
                min_cost_network.demand_at_location[loc]
                - solution.shortage_decisions[loc]
                for loc in min_cost_network.connected_demand_sites
            ]
        )
        self.assertGreaterEqual(
            solution.flow_decisions[("DN4", "CN7")], common_buffer
        )
        self.assertGreaterEqual(
            solution.flow_decisions[("DN4", "CN8")], common_buffer
        )
        for demand_id, demand in topology.demand_sites.items():
            actual_buffer = (
                none_throws(demand.demand)
                - solution.shortage_decisions[demand_id]
            )
            self.assertGreaterEqual(actual_buffer, common_buffer)

        # Validate the behavior with one of the demand sites cut-off
        topology.links["DN4-CN8"].capacity = 0
        min_cost_network_filtered = MinCostNetwork(topology, params)
        self.assertEqual(
            len(min_cost_network_filtered.connected_demand_sites),
            1,
        )

        solution_filtered = min_cost_network_filtered.solve(
            coverage_percentage=1.0
        )
        self.assertIsNotNone(solution_filtered)

        common_buffer_filtered = min(
            [
                min_cost_network_filtered.demand_at_location[loc]
                - solution_filtered.shortage_decisions[loc]
                for loc in min_cost_network_filtered.connected_demand_sites
            ]
        )
        self.assertEqual(common_buffer_filtered, 0.025)
        self.assertGreaterEqual(
            solution_filtered.flow_decisions[("DN4", "CN7")],
            common_buffer_filtered,
        )
        self.assertGreaterEqual(common_buffer_filtered, common_buffer)

        # Validate behavior of determining connected demand sites if polarities
        # are ignored
        params.ignore_polarities = True
        self.assertEqual(
            len(MinCostNetwork(topology, params).connected_demand_sites),
            1,
        )

    def test_optimization_ignore_polarities(self) -> None:
        """
        Test cost optimization with ignore_polarities set to True
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
        )
        params.ignore_polarities = True
        topology = square_topology(params)
        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )

        # All polarity decisions should be empty
        self.assertIsNotNone(solution)
        self.assertEqual(solution.odd_site_decisions, {})
        self.assertEqual(solution.even_site_decisions, {})

        # All DNs but only one POP proposed
        for site_id in ["DN1", "DN2", "DN3", "DN4"]:
            self.assertEqual(solution.site_decisions[site_id], 1)
        self.assertEqual(
            solution.site_decisions["POP5"] + solution.site_decisions["POP6"], 1
        )

    def test_square_topology_with_colocated_sites(self) -> None:
        """
        Test cost optimization with co-located sites
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = square_topology_with_colocated_sites(params)

        # Verify demand connected sites
        loc_to_sites = {
            (topology.sites["CN7"].latitude, topology.sites["CN7"].longitude): {
                "CN7"
            },
            (topology.sites["CN8"].latitude, topology.sites["CN8"].longitude): {
                "CN8"
            },
            (
                topology.sites["CN10"].latitude,
                topology.sites["CN10"].longitude,
            ): {"POP5", "DN9", "CN10"},
            (
                topology.sites["CN11"].latitude,
                topology.sites["CN11"].longitude,
            ): {"DN3", "CN11"},
        }
        for demand in topology.demand_sites.values():
            self.assertEqual(
                set(site.site_id for site in demand.connected_sites),
                loc_to_sites[(demand.latitude, demand.longitude)],
            )

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )
        self.assertIsNotNone(solution)

        # Verify only up to 1 of the co-located sites is selected
        colocated_sites1 = ["POP5", "DN9", "CN10"]
        colocated_sites2 = ["DN3", "CN11"]
        self.assertGreaterEqual(
            1,
            sum(
                [
                    solution.site_decisions[site_id]
                    for site_id in colocated_sites1
                ]
            ),
        )
        self.assertGreaterEqual(
            1,
            sum(
                [
                    solution.site_decisions[site_id]
                    for site_id in colocated_sites2
                ]
            ),
        )

    def test_hybrid_sites_case_optimization(self) -> None:
        """
        Another test of cost optimization with co-located sites
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = hybrid_sites_topology()
        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )

        # Verify POP1 is selected and CN0 is not since POP1 can serve the demand
        self.assertIsNotNone(solution)
        self.assertEqual(solution.site_decisions["POP1"], 1)
        self.assertEqual(solution.site_decisions["CN0"], 0)

        # Verify only one of DN1, DN2 is selected to route to demand at DN3/CN3
        self.assertEqual(
            solution.site_decisions["DN1"] + solution.site_decisions["DN2"],
            1,
        )

        # Verify if DN1 is selected, then it serves demand directly, otherwise CN1 does
        self.assertEqual(
            solution.site_decisions["DN1"] + solution.site_decisions["CN1"],
            1,
        )

        # Verify if DN2 is selected, then it serves demand directly, otherwise CN2 does
        self.assertEqual(
            solution.site_decisions["DN2"] + solution.site_decisions["CN2"],
            1,
        )

        # Verify CN3 is selected rather than the more expensive DN3
        self.assertEqual(solution.site_decisions["DN3"], 0)
        self.assertEqual(solution.site_decisions["CN3"], 1)

    def test_optimization_with_built_links(self) -> None:
        """
        Test cost optimization with existing links
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = square_topology_with_cns(params)
        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )

        sites = ["POP5", "DN1"]
        links = ["POP5-DN1", "DN1-POP5"]

        # In base scenario, POP5<->DN1 links is not proposed
        self.assertIsNotNone(solution)
        for link_id in links:
            link = topology.links[link_id]
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                0,
            )

        # Now force, POP5 and DN1 to be built
        for site_id in sites:
            topology.sites[site_id]._status_type = StatusType.EXISTING
        for sector in topology.sectors.values():
            if sector.site.site_id in sites:
                sector._status_type = StatusType.EXISTING
        for link_id in links:
            topology.links[link_id]._status_type = StatusType.EXISTING

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )

        # Once POP5<->DN1 exists, it is now proposed
        self.assertIsNotNone(solution)
        for link_id in links:
            link = topology.links[link_id]
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                1,
            )

    def test_optimization_with_built_link_triangle(self) -> None:
        """
        Set the triangle of links POP5<->DN1<->DN4<->POP5 in the square
        topology to be existing. Due to polarity restrictions, this should
        cause infeasibility.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = square_topology()
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
        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )
        self.assertIsNone(solution)

        # After relaxing polarity constraints, ILP should be feasible
        params.ignore_polarities = True
        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )
        self.assertIsNotNone(solution)
        self.assertEqual(solution.even_site_decisions, {})
        self.assertEqual(solution.odd_site_decisions, {})
        for link_id in links:
            link = topology.links[link_id]
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                1,
            )

    def test_optimization_with_unavailable_links(self) -> None:
        """
        Test cost optimization with unavailable links
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = square_topology()
        links = ["POP5-DN4", "DN4-POP5", "POP5-DN1", "DN1-POP5"]
        for link_id in links:
            topology.links[link_id]._status_type = StatusType.UNAVAILABLE

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )
        self.assertIsNotNone(solution)
        for link_id in links:
            link = topology.links[link_id]
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                0,
            )

        # Links leaving POP siste 5 are all unavailable; now, make POP6 links
        # unavailable as well. The min cost problem must be infeasible now.
        links = ["POP6-DN3", "DN3-POP6", "POP6-DN2", "DN2-POP6"]
        for link_id in links:
            topology.links[link_id]._status_type = StatusType.UNAVAILABLE

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )
        self.assertIsNone(solution)

    def test_simple_pop_multi_sku_topology(self) -> None:
        """
        Tests co-located POPs with always active POPs enabled.
        """
        params = OptimizerParams(
            device_list=[
                DEFAULT_DN_DEVICE,
                DEFAULT_CN_DEVICE,
                ANOTHER_DN_DEVICE,
            ],
            always_active_pops=True,
        )
        topology = simple_pop_multi_sku_topology()

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )

        # No infeasibility due to always active POPs combined with only one of
        # the skus selected
        self.assertIsNotNone(solution)

        # Only one POP is selected
        self.assertEqual(
            solution.site_decisions["POP0"] + solution.site_decisions["POP1"],
            1,
        )

    def test_minimize_cost_for_given_demand(self) -> None:
        """
        Test cost minimization based on demand and link capacity limitations
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = multi_path_topology()

        # Set demand = 1, POP-DN link capacity = 3, DN-CN link capacity = 4
        for demand in topology.demand_sites.values():
            demand.demand = 1.0
        for link in topology.links.values():
            if (
                link.tx_site.site_type == SiteType.POP
                or link.rx_site.site_type == SiteType.POP
            ):
                link.capacity = 3.0
            else:
                link.capacity = 4.0

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )

        # Only one of the DNs are proposed; the POP and CNs are proposed
        self.assertIsNotNone(solution)
        for site_id in ["POP1", "CN1", "CN2"]:
            self.assertEqual(solution.site_decisions[site_id], 1)
        self.assertEqual(
            solution.site_decisions["DN1"] + solution.site_decisions["DN2"], 1
        )

        links = set()
        if solution.site_decisions["DN1"] == 1:
            links = {"POP1-DN1", "DN1-POP1", "DN1-CN1", "DN1-CN2"}
        elif solution.site_decisions["DN2"] == 1:
            links = {"POP1-DN2", "DN2-POP1", "DN2-CN1", "DN2-CN2"}

        for link_id, link in topology.links.items():
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                1 if link_id in links else 0,
            )
            if link_id in links:
                self.assertGreaterEqual(
                    solution.flow_decisions[
                        (link.tx_site.site_id, link.rx_site.site_id)
                    ],
                    2.0
                    if link.tx_site.site_type == SiteType.POP
                    else 0.0
                    if link.rx_site.site_type == SiteType.POP
                    else 1.0,
                )
            else:
                self.assertEqual(
                    solution.flow_decisions[
                        (link.tx_site.site_id, link.rx_site.site_id)
                    ],
                    0,
                )

        # Set demand = 2, POP-DN link capacity = 3, DN-CN link capacity = 4
        for demand in topology.demand_sites.values():
            demand.demand = 2.0
        for link in topology.links.values():
            if (
                link.tx_site.site_type == SiteType.POP
                or link.rx_site.site_type == SiteType.POP
            ):
                link.capacity = 3.0
            else:
                link.capacity = 4.0

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )

        # All sites/links proposed
        self.assertIsNotNone(solution)
        for site_id in topology.sites:
            self.assertEqual(solution.site_decisions[site_id], 1)
        for link_id, link in topology.links.items():
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                1,
            )

    def test_tdm_cn_constraint(self) -> None:
        """
        Test tdm constraint on CNs for cost minimization
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
            demand=1.8,
        )
        topology = tdm_cn_constraint_topology(params)

        # Due to tdm constraint on the CN, solution cannot be found
        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )
        self.assertIsNone(solution)

        # By reducing the demand, a solution can be found
        params.demand = 0.9
        for demand in topology.demand_sites.values():
            demand.demand = params.demand

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )
        self.assertIsNotNone(solution)
        self.assertEqual(sum(solution.tdm_decisions.values()), 1.0)

    def test_simple_minimize_cost(self) -> None:
        """
        Very basic test for cost minimization
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = simple_minimize_cost_topology()

        solution = MinCostNetwork(topology, params).solve(
            coverage_percentage=1.0
        )

        # POP1->CN1 should be chosen over POP1->DN1->CN1
        self.assertIsNotNone(solution)
        for site_id in topology.sites:
            self.assertEqual(
                solution.site_decisions[site_id],
                1 if site_id in {"POP1", "CN1"} else 0,
            )
        for link_id, link in topology.links.items():
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                1 if link_id == "POP1-CN1" else 0,
            )

    def test_timeout(self) -> None:
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            demand=1.0,
        )
        topology = square_topology(params)

        min_cost_network = MinCostNetwork(topology, params)
        solution = min_cost_network.solve(coverage_percentage=1.0)

        # Demand is too large for a solution to be found
        self.assertIsNone(solution)

        # Problem did not time out
        self.assertFalse(min_cost_network.did_problem_timeout())
