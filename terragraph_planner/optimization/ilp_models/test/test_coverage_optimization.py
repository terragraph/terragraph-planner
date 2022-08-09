# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import (
    PolarityType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    another_multi_path_topology,
    multi_path_topology,
    square_topology,
    square_topology_with_cns,
    square_topology_with_colocated_sites,
    tdm_cn_constraint_topology,
    triangle_topology,
)
from terragraph_planner.optimization.ilp_models.coverage_optimization import (
    MaxCoverageNetwork,
)


class TestCoverageOptimization(TestCase):
    def test_optimization_on_square(self) -> None:
        """
        Test various attributes of coverage optimization on the square topology
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = square_topology(params)

        # Compute cost of network if all sites are built
        all_built_cost = float(
            sum(
                [
                    params.pop_site_capex
                    if site.site_type == SiteType.POP
                    else params.dn_site_capex
                    if site.site_type == SiteType.DN
                    else params.cn_site_capex
                    for site in topology.sites.values()
                ]
            )
        ) + float(
            sum(
                [
                    # Note: in square topology, all sectors are in separate nodes
                    sector.site.device.node_capex
                    for sector in topology.sectors.values()
                ]
            )
        )
        params.budget = all_built_cost

        solution = MaxCoverageNetwork(topology, params, set()).solve()

        # All DNs but only one POP proposed
        self.assertIsNotNone(solution)
        for site_id in ["DN1", "DN2", "DN3", "DN4"]:
            self.assertEqual(solution.site_decisions[site_id], 1)
        self.assertGreaterEqual(
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

        solution = MaxCoverageNetwork(topology, params, set()).solve()

        # All DNs and POPs should be proposed
        self.assertIsNotNone(solution)
        for site_id in topology.sites:
            self.assertEqual(solution.site_decisions[site_id], 1)

        # Flow into demand equals actual demand
        demand_flow = {demand_id: 0.0 for demand_id in topology.demand_sites}
        for (_, site_id2), flow in solution.flow_decisions.items():
            if site_id2 in topology.demand_sites:
                demand_flow[site_id2] += flow
        for flow in demand_flow.values():
            self.assertEqual(flow, params.demand)
        self.assertEqual(sum(solution.shortage_decisions.values()), 0)

        # Now full coverage will not be sufficient
        params.demand = 1.0
        for demand in topology.demand_sites.values():
            demand.demand = params.demand

        solution = MaxCoverageNetwork(topology, params, set()).solve()

        # Total flow into demand should be max possible flow
        self.assertIsNotNone(solution)
        total_demand_flow = 0
        for (_, site_id2), flow in solution.flow_decisions.items():
            if site_id2 in topology.demand_sites:
                total_demand_flow += flow
        self.assertAlmostEqual(total_demand_flow, 6 * 1.0 * 0.9, places=6)
        self.assertAlmostEqual(
            sum(solution.shortage_decisions.values()), 6 * 1.0 * 0.1, places=6
        )

        # Remove POP site from budget
        params.demand = 0.9
        for demand in topology.demand_sites.values():
            demand.demand = params.demand

        params.budget -= params.pop_site_capex

        solution = MaxCoverageNetwork(topology, params, set()).solve()

        # One site is removed
        self.assertIsNotNone(solution)
        self.assertEqual(
            sum(
                [
                    decision
                    for site_id, decision in solution.site_decisions.items()
                    if site_id in topology.sites
                ]
            ),
            5,
        )
        self.assertGreater(sum(solution.shortage_decisions.values()), 0)

        # Set budget to just one POP, so budget is insufficient
        params.budget = params.pop_site_capex
        solution = MaxCoverageNetwork(topology, params, set()).solve()

        self.assertIsNone(solution)

        # Sanity check: set budget to 0
        params.budget = 0
        solution = MaxCoverageNetwork(topology, params, set()).solve()

        self.assertIsNone(solution)

    def test_optimization_on_square_with_cns(self) -> None:
        """
        Test various attributes of coverage optimization on the square topology
        with CNs
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
        )
        topology = square_topology_with_cns(params)

        # Only these sites are needed to serve network
        proposed_sites = {"POP5", "DN4", "CN7", "CN8"}

        proposed_cost = float(
            sum(
                [
                    params.pop_site_capex
                    if site.site_type == SiteType.POP
                    else params.dn_site_capex
                    if site.site_type == SiteType.DN
                    else params.cn_site_capex
                    for site_id, site in topology.sites.items()
                    if site_id in proposed_sites
                ]
            )
        ) + float(
            sum(
                [
                    # Note: in square topology, all sectors are in separate nodes
                    sector.site.device.node_capex
                    for sector in topology.sectors.values()
                    if sector.site.site_id in proposed_sites
                ]
            )
        )
        params.budget = proposed_cost

        solution = MaxCoverageNetwork(topology, params, set()).solve()

        # Only one POP and the DN conencted to the CNs are proposed
        self.assertIsNotNone(solution)
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

        # Now construct proposed network and add an adversarial link
        for site_id in proposed_sites:
            topology.sites[site_id].status_type = StatusType.PROPOSED
        topology.sites["POP5"].polarity = PolarityType.ODD
        topology.sites["DN4"].polarity = PolarityType.EVEN
        proposed_links = {"POP5-DN4", "DN4-POP5", "DN4-CN7", "DN4-CN8"}
        for link_id in proposed_links:
            link = topology.links[link_id]
            link.status_type = StatusType.PROPOSED
            none_throws(link.tx_sector).status_type = StatusType.PROPOSED
            none_throws(link.rx_sector).status_type = StatusType.PROPOSED

        adversarial_links = {("POP5", "DN4"), ("DN4", "POP5")}

        solution = MaxCoverageNetwork(
            topology, params, adversarial_links
        ).solve()

        # Budget is insufficient
        self.assertIsNone(solution)

        # Add budget for one more DN
        params.budget += params.dn_site_capex + 2 * DEFAULT_DN_DEVICE.node_capex

        solution = MaxCoverageNetwork(
            topology, params, adversarial_links
        ).solve()

        # Budget is still insufficient because of polarity constraints
        self.assertIsNone(solution)

        # Add budget for one more POP but only one of two sectors
        params.budget += params.pop_site_capex + DEFAULT_DN_DEVICE.node_capex

        solution = MaxCoverageNetwork(
            topology, params, adversarial_links
        ).solve()

        # Budget is still insufficient because both sectors are needed
        self.assertIsNone(solution)

        params.budget += DEFAULT_DN_DEVICE.node_capex

        solution = MaxCoverageNetwork(
            topology, params, adversarial_links
        ).solve()

        self.assertIsNotNone(solution)

        redundant_proposed_sites = proposed_sites | {"POP6", "DN3"}
        for site_id in topology.sites:
            self.assertEqual(
                solution.site_decisions[site_id],
                1 if site_id in redundant_proposed_sites else 0,
            )
        for link in adversarial_links:
            self.assertEqual(solution.flow_decisions[link], 0)

    def test_max_common_bandwidth(self) -> None:
        """
        Test coverage optimization with maximize common bandwidth enabled
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            maximize_common_bandwidth=True,
        )
        topology = square_topology_with_cns()
        topology.links["DN4-CN8"].capacity = 0.02

        # Validate behavior of max common bandwidth
        max_cov_network = MaxCoverageNetwork(topology, params, set())
        self.assertEqual(len(max_cov_network.connected_demand_sites), 2)

        solution = max_cov_network.solve()
        self.assertIsNotNone(solution)

        common_buffer = min(
            [
                max_cov_network.demand_at_location[loc]
                - solution.shortage_decisions[loc]
                for loc in max_cov_network.connected_demand_sites
            ]
        )
        self.assertEqual(
            common_buffer,
            max_cov_network.problem.getSolution(
                max_cov_network.common_bandwidth
            ),
        )
        self.assertEqual(common_buffer, -solution.objective_value)
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

        # Verify that adversarial links are excluded in determining connected
        # demand sites
        self.assertEqual(
            len(
                MaxCoverageNetwork(
                    topology, params, {("DN4", "CN7")}
                ).connected_demand_sites
            ),
            1,
        )

        # Validate the behavior with one of the demand sites cut-off
        topology.links["DN4-CN8"].capacity = 0
        max_cov_network_filtered = MaxCoverageNetwork(topology, params, set())
        self.assertEqual(
            len(max_cov_network_filtered.connected_demand_sites),
            1,
        )

        solution_filtered = max_cov_network_filtered.solve()
        self.assertIsNotNone(solution_filtered)

        common_buffer_filtered = max_cov_network_filtered.problem.getSolution(
            max_cov_network_filtered.common_bandwidth
        )
        self.assertEqual(common_buffer_filtered, 0.025)
        self.assertGreaterEqual(
            solution_filtered.flow_decisions[("DN4", "CN7")],
            common_buffer_filtered,
        )
        self.assertGreaterEqual(common_buffer_filtered, common_buffer)

        # Validate behavior of determining connected demand sites if polarities
        # are ignored
        topology.links["DN4-CN8"].capacity = 0.02
        params.ignore_polarities = True

        # Verify that adversarial links are excluded in determining connected
        # demand sites
        self.assertEqual(
            len(
                MaxCoverageNetwork(
                    topology, params, {("DN4", "CN7")}
                ).connected_demand_sites
            ),
            1,
        )

        # Validate the behavior with one of the demand sites cut-off
        topology.links["DN4-CN8"].capacity = 0
        self.assertEqual(
            len(
                MaxCoverageNetwork(
                    topology, params, set()
                ).connected_demand_sites
            ),
            1,
        )

    def test_square_topology_with_colocated_sites(self) -> None:
        """
        Test coverage optimization with co-located sites
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

        solution = MaxCoverageNetwork(topology, params, set()).solve()
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

    def test_square_topology_with_colocated_site_upgrades(self) -> None:
        """
        Test that co-located sites can be upgraded
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
        )
        topology = square_topology_with_colocated_sites(params)

        # Make some sites proposed, including the CN10 which should be
        # converted into the POP5 during optimization
        proposed_sites = {"DN3", "DN4", "POP6", "CN7", "CN8", "CN10"}
        for site_id, site in topology.sites.items():
            if site_id in proposed_sites:
                site.status_type = StatusType.PROPOSED
        for sector in topology.sectors.values():
            if sector.site.site_id in proposed_sites:
                sector.status_type = StatusType.PROPOSED
        proposed_links = {
            "DN3-DN4",
            "DN4-DN3",
            "POP6-DN3",
            "DN3-POP6",
            "DN4-CN7",
            "DN4-CN8",
            "DN4-CN10",
        }
        for link_id, link in topology.links.items():
            if link_id in proposed_links:
                link.status_type = StatusType.PROPOSED

        # Disable two links so that POP5 will be required to satisfy all demand
        topology.links["DN3-DN4"].capacity = 0
        topology.links["DN4-DN3"].capacity = 0

        solution = MaxCoverageNetwork(topology, params, set()).solve()
        self.assertIsNotNone(solution)

        # Verify that CN10 is upgraded to POP5
        self.assertEqual(solution.site_decisions["CN10"], 0)
        self.assertEqual(solution.site_decisions["POP5"], 1)
        self.assertEqual(sum(solution.shortage_decisions.values()), 0)

    def test_connected_demand_site_optimization(self) -> None:
        """
        Test connected demand site optimization properties, particularly
        behavior around polarity constraints and adversarial links
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        )
        topology = triangle_topology()

        # Make the POP-DN links proposed; this way the POPs and DNs have
        # different polarity and the two DNs have the same polarity
        proposed_sites = {"POP0", "DN1", "DN2"}
        for site_id, site in topology.sites.items():
            if site_id in proposed_sites:
                site.status_type = StatusType.PROPOSED
        for sector in topology.sectors.values():
            if sector.site.site_id in proposed_sites:
                sector.status_type = StatusType.PROPOSED
        proposed_links = {"POP0-DN1", "DN1-POP0", "POP0-DN2", "DN2-POP0"}
        for link_id, link in topology.links.items():
            if link_id in proposed_links:
                link.status_type = StatusType.PROPOSED

        ignore_links = {("POP0", "DN1")}
        connected_demand_sites = MaxCoverageNetwork(
            topology, params, adversarial_links=ignore_links
        )._get_reachable_demand_sites_with_constraints()
        self.assertIsNotNone(connected_demand_sites)
        self.assertEqual(len(connected_demand_sites), 1)

        # However, if polarity constraints are ignored, then both demand sites
        # should still be reachable
        params.ignore_polarities = True
        connected_demand_sites = MaxCoverageNetwork(
            topology, params, adversarial_links=ignore_links
        )._get_reachable_demand_sites_with_constraints()
        self.assertIsNotNone(connected_demand_sites)
        self.assertEqual(len(connected_demand_sites), 2)

        connected_demand_sites = MaxCoverageNetwork(
            topology, params, adversarial_links=ignore_links
        )._get_reachable_demand_sites_without_constraints()
        self.assertEqual(len(connected_demand_sites), 2)

    def test_maximize_coverage_with_given_budget(self) -> None:
        """
        Test coverage optimization behavior with different demand.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        params.budget = (
            params.pop_site_capex
            + params.dn_site_capex
            + params.cn_site_capex
            + 4 * DEFAULT_DN_DEVICE.node_capex
            + DEFAULT_CN_DEVICE.node_capex
        )

        topology = multi_path_topology()
        topology.remove_link("DN1-CN2")
        topology.remove_link("DN2-CN1")

        # CN2 demand = CN1 demand
        solution = MaxCoverageNetwork(topology, params, set()).solve()

        # One of POP1->DN1->CN1 or POP1->DN2->CN2 should be chosen
        self.assertIsNotNone(solution)
        self.assertEqual(solution.site_decisions["POP1"], 1)
        self.assertEqual(
            solution.site_decisions["DN1"] + solution.site_decisions["DN2"], 1
        )
        self.assertEqual(
            solution.site_decisions["CN1"], solution.site_decisions["DN1"]
        )
        self.assertEqual(
            solution.site_decisions["CN2"], solution.site_decisions["DN2"]
        )
        self.assertEqual(
            solution.link_decisions[("POP1", "DN1")],
            solution.site_decisions["DN1"],
        )
        self.assertEqual(
            solution.link_decisions[("DN1", "CN1")],
            solution.site_decisions["DN1"],
        )
        self.assertEqual(
            solution.link_decisions[("POP1", "DN2")],
            solution.site_decisions["DN2"],
        )
        self.assertEqual(
            solution.link_decisions[("DN2", "CN2")],
            solution.site_decisions["DN2"],
        )

        # CN2 demand = 2 * CN1 demand
        for demand in topology.demand_sites.values():
            connected_site_ids = {
                site.site_id for site in demand.connected_sites
            }
            if "CN2" in connected_site_ids:
                demand.demand = 2 * params.demand
            else:
                demand.demand = params.demand

        solution = MaxCoverageNetwork(topology, params, set()).solve()

        # POP1->DN2->CN2 should be chosen
        self.assertIsNotNone(solution)
        proposed_sites = {"POP1", "DN2", "CN2"}
        for site_id in topology.sites:
            self.assertEqual(
                solution.site_decisions[site_id],
                1 if site_id in proposed_sites else 0,
            )
        proposed_links = {"POP1-DN2", "DN2-POP1", "DN2-CN2"}
        for link_id, link in topology.links.items():
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                1 if link_id in proposed_links else 0,
            )

        # CN1 demand = 2 * CN2 demand
        for demand in topology.demand_sites.values():
            connected_site_ids = {
                site.site_id for site in demand.connected_sites
            }
            if "CN1" in connected_site_ids:
                demand.demand = 2 * params.demand
            else:
                demand.demand = params.demand

        solution = MaxCoverageNetwork(topology, params, set()).solve()

        # POP1->DN1->CN1 should be chosen
        self.assertIsNotNone(solution)
        proposed_sites = {"POP1", "DN1", "CN1"}
        for site_id in topology.sites:
            self.assertEqual(
                solution.site_decisions[site_id],
                1 if site_id in proposed_sites else 0,
            )
        proposed_links = {"POP1-DN1", "DN1-POP1", "DN1-CN1"}
        for link_id, link in topology.links.items():
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                1 if link_id in proposed_links else 0,
            )

        # Test against another topology where DN2 connects to CN2 and CN3
        topology = another_multi_path_topology()
        params.budget += params.cn_site_capex + DEFAULT_CN_DEVICE.node_capex

        # CN2 + CN3 demand > CN1 demand
        for demand in topology.demand_sites.values():
            connected_site_ids = {
                site.site_id for site in demand.connected_sites
            }
            if "CN1" in connected_site_ids:
                demand.demand = 1.9 * params.demand
            else:
                demand.demand = params.demand

        solution = MaxCoverageNetwork(topology, params, set()).solve()

        # POP1->DN2->CN2+CN3 should be chosen
        self.assertIsNotNone(solution)
        proposed_sites = {"POP1", "DN2", "CN2", "CN3"}
        for site_id in topology.sites:
            self.assertEqual(
                solution.site_decisions[site_id],
                1 if site_id in proposed_sites else 0,
            )
        proposed_links = {"POP1-DN2", "DN2-POP1", "DN2-CN2", "DN2-CN3"}
        for link_id, link in topology.links.items():
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                1 if link_id in proposed_links else 0,
            )

        # CN2 + CN3 demand < CN1 demand
        for demand in topology.demand_sites.values():
            connected_site_ids = {
                site.site_id for site in demand.connected_sites
            }
            if "CN1" in connected_site_ids:
                demand.demand = 2.1 * params.demand
            else:
                demand.demand = params.demand

        solution = MaxCoverageNetwork(topology, params, set()).solve()

        # POP1->DN1->CN1 should be chosen
        self.assertIsNotNone(solution)
        proposed_sites = {"POP1", "DN1", "CN1"}
        for site_id in topology.sites:
            self.assertEqual(
                solution.site_decisions[site_id],
                1 if site_id in proposed_sites else 0,
            )
        proposed_links = {"POP1-DN1", "DN1-POP1", "DN1-CN1"}
        for link_id, link in topology.links.items():
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                1 if link_id in proposed_links else 0,
            )

    def test_maximize_common_bandwidth_with_given_budget(self) -> None:
        """
        Test maximize common bandwidth behavior under budget restrictions.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            maximize_common_bandwidth=True,
        )
        params.budget = (
            params.pop_site_capex
            + params.dn_site_capex
            + params.cn_site_capex
            + 4 * DEFAULT_DN_DEVICE.node_capex
            + DEFAULT_CN_DEVICE.node_capex
        )

        topology = multi_path_topology()
        topology.remove_link("DN1-CN2")
        topology.remove_link("DN2-CN1")

        # Since the budget does not allow both CNs to be selected, the common
        # bandwidth is 0, so the problem is considered infeasible
        solution = MaxCoverageNetwork(topology, params, set()).solve()
        self.assertIsNone(solution)

        # If there is enough budget, the common bandwidth should not be 0
        params.budget += (
            params.dn_site_capex
            + params.cn_site_capex
            + 2 * DEFAULT_DN_DEVICE.node_capex
            + DEFAULT_CN_DEVICE.node_capex
        )

        solution = MaxCoverageNetwork(topology, params, set()).solve()

        self.assertIsNotNone(solution)
        common_buffer = -solution.objective_value
        self.assertGreater(common_buffer, 0)
        min_demand = min(
            [
                none_throws(demand.demand)
                for demand in topology.demand_sites.values()
            ]
        )
        self.assertAlmostEqual(common_buffer, min_demand, places=6)

    def test_tdm_cn_constraint(self) -> None:
        """
        Test tdm constraint on CNs for coverage minimization
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
            demand=1.8,
        )
        topology = tdm_cn_constraint_topology(params)

        # Due to tdm constraint on the CN, only half of the demand can be served
        solution = MaxCoverageNetwork(topology, params, set()).solve()
        self.assertIsNotNone(solution)
        self.assertEqual(sum(solution.tdm_decisions.values()), 1.0)
        self.assertAlmostEqual(
            sum(
                [
                    flow
                    for link, flow in solution.flow_decisions.items()
                    if link[1] == "CN2"
                ]
            ),
            1.8,
            places=6,
        )
        self.assertAlmostEqual(
            sum(solution.shortage_decisions.values()), 1.8, places=6
        )
