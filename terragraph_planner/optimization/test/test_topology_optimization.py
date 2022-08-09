# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from copy import deepcopy
from unittest import TestCase

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import (
    PolarityType,
    RedundancyLevel,
    SiteType,
    StatusType,
)
from terragraph_planner.common.exceptions import OptimizerException
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    diamond_topology,
    different_sector_angle_topology,
    figure_eight_topology,
    hop_count_topology,
    near_far_effect_topology,
    square_topology,
    square_topology_with_cns,
    square_topology_with_colocated_sites,
    tdm_constraint_topology,
    triangle_topology_with_cns,
)
from terragraph_planner.optimization.constants import UNASSIGNED_CHANNEL
from terragraph_planner.optimization.topology_operations import (
    compute_capex,
    get_adversarial_links,
)
from terragraph_planner.optimization.topology_optimization import (
    _run_interference_step,
    _run_max_coverage_step,
    _run_min_cost_step,
    _run_propose_extra_pops_step,
    _run_redundancy_step,
    optimize_topology,
)


class TestTopologyOptimization(TestCase):
    def test_min_cost_on_square(self) -> None:
        """
        Test min cost topology optimization on the square topology
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
        )
        topology = square_topology(params)

        _run_min_cost_step(topology, params)

        # All DNs but only one POP proposed
        for site_id, site in topology.sites.items():
            if site_id in {"DN1", "DN2", "DN3", "DN4"}:
                self.assertEqual(site.status_type, StatusType.PROPOSED)
                self.assertTrue(
                    site.polarity == PolarityType.EVEN
                    or site.polarity == PolarityType.ODD
                )
        self.assertTrue(
            topology.sites["POP5"].status_type == StatusType.PROPOSED
            or topology.sites["POP6"].status_type == StatusType.PROPOSED
        )
        self.assertTrue(
            topology.sites["POP5"].status_type == StatusType.CANDIDATE
            or topology.sites["POP6"].status_type == StatusType.CANDIDATE
        )
        if topology.sites["POP5"] == StatusType.CANDIDATE:
            self.assertEqual(
                topology.sites["POP5"].polarity, PolarityType.UNASSIGNED
            )
        else:
            self.assertEqual(
                topology.sites["POP6"].polarity, PolarityType.UNASSIGNED
            )

        # Links between proposed sites with compatible polarity are proposed
        for link in topology.links.values():
            tx_site = link.tx_site
            rx_site = link.rx_site
            if (
                tx_site.status_type == StatusType.PROPOSED
                and rx_site.status_type == StatusType.PROPOSED
                and tx_site.polarity != rx_site.polarity
            ):
                self.assertEqual(link.status_type, StatusType.PROPOSED)
            else:
                self.assertEqual(link.status_type, StatusType.CANDIDATE)

        # Proposed sectors must be on proposed sites and at least one sector on
        # the site must be active
        sites_with_active_sectors = set()
        for sector in topology.sectors.values():
            if sector.status_type == StatusType.PROPOSED:
                self.assertEqual(sector.site.status_type, StatusType.PROPOSED)
                sites_with_active_sectors.add(sector.site.site_id)
            self.assertEqual(
                sector.channel,
                0
                if sector.site.status_type == StatusType.PROPOSED
                else UNASSIGNED_CHANNEL,
            )
        self.assertEqual(
            sites_with_active_sectors,
            topology.get_site_ids(
                status_filter={StatusType.PROPOSED},
            ),
        )

    def test_min_cost_on_square_partial_coverage(self) -> None:
        """
        Test automatic adjustment of coverage in min cost topology optimization
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = square_topology(params)
        # Modify demand so that full coverage is not feasible
        for demand in topology.demand_sites.values():
            demand.demand = 1.0

        # Min cost should automatically decrease coverage until feasibility
        solution = _run_min_cost_step(topology, params)
        self.assertGreater(sum(solution.shortage_decisions.values()), 0)

    def test_min_cost_on_square_ignore_polarities(self) -> None:
        """
        Test min cost topology optimization with ignore_polarities set to True
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        params.ignore_polarities = True
        topology = square_topology(params)

        _run_min_cost_step(topology, params)

        # All polarities should be unassigned
        for site in topology.sites.values():
            self.assertEqual(site.polarity, PolarityType.UNASSIGNED)

    def test_adversarial_links(self) -> None:
        """
        Test adversarial link computation in optimization
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            backhaul_link_redundancy_ratio=0.4,
        )
        topology = square_topology(params)

        _run_min_cost_step(topology, params)

        expected_adversarials = {
            ("POP5", "DN4"),
            ("DN4", "POP5"),
            ("POP5", "DN1"),
            ("DN1", "POP5"),
        }
        adversarial_links = get_adversarial_links(
            topology,
            adversarial_links_ratio=params.backhaul_link_redundancy_ratio,
        )
        self.assertSetEqual(adversarial_links, expected_adversarials)

    def test_oversubscription(self) -> None:
        """
        Test optimization with oversubscription
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            oversubscription=1.0,
            pop_capacity=1.8,
            demand=1.35,
        )
        topology = triangle_topology_with_cns(params)

        # Without oversubscription
        min_cost_solution = _run_min_cost_step(topology, params)
        max_cov_solution = _run_max_coverage_step(topology, params)
        self.assertIsNotNone(max_cov_solution)

        self.assertAlmostEqual(
            sum(min_cost_solution.shortage_decisions.values()), 0.9, places=6
        )
        self.assertAlmostEqual(
            min_cost_solution.flow_decisions[("POP0", "CN1")]
            + min_cost_solution.flow_decisions[("POP0", "CN2")],
            1.8,
            places=6,
        )

        self.assertAlmostEqual(max_cov_solution.objective_value, 0.9, places=6)
        self.assertAlmostEqual(
            sum(max_cov_solution.shortage_decisions.values()), 0.9, places=6
        )
        self.assertAlmostEqual(
            max_cov_solution.flow_decisions[("POP0", "CN1")]
            + max_cov_solution.flow_decisions[("POP0", "CN2")],
            1.8,
            places=6,
        )

        # With oversubscription factor of 2x
        params.oversubscription = 2
        min_cost_solution = _run_min_cost_step(topology, params)
        max_cov_solution = _run_max_coverage_step(topology, params)
        self.assertIsNotNone(max_cov_solution)

        self.assertEqual(sum(min_cost_solution.shortage_decisions.values()), 0)
        self.assertAlmostEqual(
            min_cost_solution.flow_decisions[("POP0", "CN1")]
            + min_cost_solution.flow_decisions[("POP0", "CN2")],
            1.35,
            places=6,
        )

        self.assertAlmostEqual(max_cov_solution.objective_value, 0, places=6)
        self.assertAlmostEqual(
            sum(max_cov_solution.shortage_decisions.values()), 0, places=6
        )
        self.assertAlmostEqual(
            max_cov_solution.flow_decisions[("POP0", "CN1")]
            + max_cov_solution.flow_decisions[("POP0", "CN2")],
            1.35,
            places=6,
        )

    def test_max_coverage_on_square_with_cns(self) -> None:
        """
        Test max coverage topology optimization on the square topology with cns
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
        )
        topology = square_topology_with_cns(params)

        proposed_sites = {"POP5", "DN4", "CN7", "CN8"}
        for site_id in proposed_sites:
            topology.sites[site_id].status_type = StatusType.PROPOSED
        topology.sites["POP5"].polarity = PolarityType.ODD
        topology.sites["DN4"].polarity = PolarityType.EVEN
        for sector in topology.sectors.values():
            if sector.site.site_id in proposed_sites:
                sector.status_type = StatusType.PROPOSED
        proposed_links = {"POP5-DN4", "DN4-POP5", "DN4-CN7", "DN4-CN8"}
        for link_id in proposed_links:
            link = topology.links[link_id]
            link.status_type = StatusType.PROPOSED

        # Without any redundancy, solution should be found
        # Provide just a little extra budget so that max coverage is not skipped
        params.budget = compute_capex(topology, params).proposed_capex + 1.0
        params.backhaul_link_redundancy_ratio = 0

        solution = _run_max_coverage_step(topology, params)
        self.assertIsNotNone(solution)

        for site_id, site in topology.sites.items():
            self.assertEqual(
                site.status_type,
                StatusType.PROPOSED
                if site_id in proposed_sites
                else StatusType.CANDIDATE,
            )

        # Adding redundancy leads to infeasibility
        params.backhaul_link_redundancy_ratio = 0.2
        solution = _run_max_coverage_step(topology, params)
        self.assertIsNone(solution)

        # Adding budget makes it feasible again
        params.budget += (
            params.pop_site_capex
            + params.dn_site_capex
            + 4 * DEFAULT_DN_DEVICE.node_capex
        )

        solution = _run_max_coverage_step(topology, params)
        self.assertIsNotNone(solution)

        redundant_proposed_sites = proposed_sites | {"POP6", "DN3"}
        for site_id, site in topology.sites.items():
            self.assertEqual(
                site.status_type,
                StatusType.PROPOSED
                if site_id in redundant_proposed_sites
                else StatusType.CANDIDATE,
            )

    def test_redundancy_on_figure_eight(self) -> None:
        """
        Test redundancy topology optimization on the figure eight topology
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            enable_legacy_redundancy_method=False,
        )
        topology = figure_eight_topology(params)

        proposed_sites = {"POP0", "DN2", "DN3", "DN5", "DN6", "CN7"}
        for site_id in proposed_sites:
            topology.sites[site_id].status_type = StatusType.PROPOSED
        topology.sites["POP0"].polarity = PolarityType.ODD
        topology.sites["DN2"].polarity = PolarityType.EVEN
        topology.sites["DN3"].polarity = PolarityType.ODD
        topology.sites["DN5"].polarity = PolarityType.EVEN
        topology.sites["DN6"].polarity = PolarityType.ODD
        for sector in topology.sectors.values():
            if sector.site.site_id in proposed_sites:
                sector.status_type = StatusType.PROPOSED
        proposed_links = {
            "POP0-DN2",
            "DN2-POP0",
            "DN2-DN3",
            "DN3-DN2",
            "DN3-DN5",
            "DN5-DN3",
            "DN5-DN6",
            "DN6-DN5",
            "DN6-CN7",
        }
        for link_id in proposed_links:
            link = topology.links[link_id]
            link.status_type = StatusType.PROPOSED

        base_topology = deepcopy(topology)

        # Test low redundancy setting
        params.redundancy_level = RedundancyLevel.LOW
        solution = _run_redundancy_step(topology, params)
        self.assertIsNotNone(solution)

        redundant_proposed_sites = proposed_sites | {"DN1", "DN4"}
        for site_id, site in topology.sites.items():
            self.assertEqual(
                site.status_type,
                StatusType.PROPOSED
                if site_id in redundant_proposed_sites
                else StatusType.CANDIDATE,
            )

        # Test med redundancy setting
        # In this case, although a higher redundancy setting is requested,
        # because it cannot be satisfied, the constraint is relaxed and
        # ultimately results in less redundancy than the low case. This can
        # occasionally happen; here, we are simply verifying the behavior
        topology = deepcopy(base_topology)
        params.redundancy_level = RedundancyLevel.MEDIUM
        solution = _run_redundancy_step(topology, params)
        self.assertIsNotNone(solution)

        redundant_proposed_sites = proposed_sites | {"DN1"}
        for site_id, site in topology.sites.items():
            self.assertEqual(
                site.status_type,
                StatusType.PROPOSED
                if site_id in redundant_proposed_sites
                else StatusType.CANDIDATE,
            )

        # Test no redundancy setting
        topology = deepcopy(base_topology)
        params.redundancy_level = RedundancyLevel.NONE
        solution = _run_redundancy_step(topology, params)
        self.assertIsNone(solution)

        # Min cost and redundant topologies should be the same
        # Verify that the candidate and proposed sites are identical
        for site_id in topology.sites:
            self.assertEqual(
                base_topology.sites[site_id].status_type,
                topology.sites[site_id].status_type,
            )

    def test_redundancy_on_diamond(self) -> None:
        """
        Test redundancy topology optimization on the diamond topology
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            enable_legacy_redundancy_method=False,
        )
        topology = diamond_topology(params)

        proposed_sites = {"POP0", "DN1", "POP5", "DN4", "CN6", "CN7"}
        for site_id in proposed_sites:
            topology.sites[site_id].status_type = StatusType.PROPOSED
        topology.sites["POP0"].polarity = PolarityType.ODD
        topology.sites["DN1"].polarity = PolarityType.EVEN
        topology.sites["DN4"].polarity = PolarityType.ODD
        topology.sites["POP5"].polarity = PolarityType.EVEN
        for sector in topology.sectors.values():
            if sector.site.site_id in proposed_sites:
                sector.status_type = StatusType.PROPOSED
        proposed_links = {
            "POP0-DN1",
            "DN1-POP0",
            "POP5-DN4",
            "DN4-POP5",
            "DN1-CN6",
            "DN4-CN7",
        }
        for link_id in proposed_links:
            link = topology.links[link_id]
            link.status_type = StatusType.PROPOSED

        base_topology = deepcopy(topology)

        # Test med redundancy setting
        params.redundancy_level = RedundancyLevel.MEDIUM
        solution = _run_redundancy_step(topology, params)
        self.assertIsNotNone(solution)

        redundant_proposed_sites = proposed_sites
        for site_id, site in topology.sites.items():
            self.assertEqual(
                site.status_type,
                StatusType.PROPOSED
                if site_id in redundant_proposed_sites
                else StatusType.CANDIDATE,
            )

        # Test high redundancy setting
        topology = deepcopy(base_topology)
        params.redundancy_level = RedundancyLevel.HIGH
        solution = _run_redundancy_step(topology, params)
        self.assertIsNotNone(solution)

        redundant_proposed_sites = proposed_sites | {"DN2", "DN3"}
        for site_id, site in topology.sites.items():
            self.assertEqual(
                site.status_type,
                StatusType.PROPOSED
                if site_id in redundant_proposed_sites
                else StatusType.CANDIDATE,
            )

    def test_min_interference_with_different_sector_angles(self) -> None:
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            diff_sector_angle_limit=15,
            near_far_angle_limit=0,  # Ignore near far effect
        )
        topology = different_sector_angle_topology(params)
        for site in topology.sites.values():
            site.status_type = StatusType.PROPOSED

        # Both POP0->DN1 and POP0->DN2 cannot be chosen due to angle violations
        solution = _run_interference_step(topology, params)
        self.assertIsNotNone(solution)

        self.assertTrue(
            topology.links["POP0-DN1"].status_type == StatusType.PROPOSED
            or topology.links["POP0-DN2"].status_type == StatusType.PROPOSED
        )
        self.assertNotEqual(
            topology.links["POP0-DN1"].status_type,
            topology.links["POP0-DN2"].status_type,
        )

        # Reduce the constraint so there is no violation. Then both POP0->DN1
        # and POP0->DN2 are chosen
        params.diff_sector_angle_limit = 10
        topology = different_sector_angle_topology(params)
        for site in topology.sites.values():
            site.status_type = StatusType.PROPOSED

        solution = _run_interference_step(topology, params)
        self.assertIsNotNone(solution)

        self.assertTrue(
            topology.links["POP0-DN1"].status_type == StatusType.PROPOSED
            and topology.links["POP0-DN2"].status_type == StatusType.PROPOSED
        )

    def test_min_interference_with_near_far_effect(self) -> None:
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            diff_sector_angle_limit=0,  # Ignore diff sector angle violations
            near_far_angle_limit=45.0,
            near_far_length_ratio=3.0,
        )
        topology = near_far_effect_topology(params)
        for site in topology.sites.values():
            site.status_type = StatusType.PROPOSED

        # Both POP0->DN1 and POP0->DN2 cannot be chosen due to angle violations
        solution = _run_interference_step(topology, params)
        self.assertIsNotNone(solution)

        self.assertTrue(
            topology.links["POP0-DN1"].status_type == StatusType.PROPOSED
            or topology.links["POP0-DN2"].status_type == StatusType.PROPOSED
        )
        self.assertNotEqual(
            topology.links["POP0-DN1"].status_type,
            topology.links["POP0-DN2"].status_type,
        )

        # Reduce each of the constraints so there is no violation. Then both
        # POP0->DN1 and POP0->DN2 are chosen in both cases
        params.near_far_angle_limit = 10.0
        params.near_far_length_ratio = 3.0
        topology = different_sector_angle_topology(params)
        for site in topology.sites.values():
            site.status_type = StatusType.PROPOSED

        solution = _run_interference_step(topology, params)
        self.assertIsNotNone(solution)

        self.assertTrue(
            topology.links["POP0-DN1"].status_type == StatusType.PROPOSED
            and topology.links["POP0-DN2"].status_type == StatusType.PROPOSED
        )

        params.near_far_angle_limit = 45.0
        params.near_far_length_ratio = 4.0
        topology = different_sector_angle_topology(params)
        for site in topology.sites.values():
            site.status_type = StatusType.PROPOSED

        solution = _run_interference_step(topology, params)
        self.assertIsNotNone(solution)

        self.assertTrue(
            topology.links["POP0-DN1"].status_type == StatusType.PROPOSED
            and topology.links["POP0-DN2"].status_type == StatusType.PROPOSED
        )

    def test_propose_pops(self) -> None:
        """
        Test POP proposal optimization
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            number_of_extra_pops=1,
        )
        topology = square_topology(params)

        solution = _run_propose_extra_pops_step(topology, params)
        self.assertIsNotNone(solution)

        # Topology started with 2 POPs with one extra proposed. Verify that it
        # now has 3 POPs and still has 4 DNs
        self.assertEqual(
            len(
                [
                    site.site_id
                    for site in topology.sites.values()
                    if site.site_type == SiteType.POP
                ]
            ),
            3,
        )
        self.assertEqual(
            len(
                [
                    site.site_id
                    for site in topology.sites.values()
                    if site.site_type == SiteType.DN
                ]
            ),
            4,
        )

    def test_optimization_on_square_with_cns(self) -> None:
        """
        Test topology optimization on the square topology
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = square_topology_with_cns(params)

        optimize_topology(topology, params)

        # Verify both CNs are proposed
        for site_id, site in topology.sites.items():
            if site_id in {"CN7", "CN8"}:
                self.assertEqual(site.status_type, StatusType.PROPOSED)

    def test_optimization_with_redundancy(self) -> None:
        """
        Test topology optimization with new redundancy method
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            enable_legacy_redundancy_method=False,
            redundancy_level=RedundancyLevel.LOW,
            budget=0,  # verify budget does not matter
        )
        topology = figure_eight_topology(params)

        optimize_topology(topology, params)

        # Verify all sites are proposed
        for site in topology.sites.values():
            self.assertEqual(site.status_type, StatusType.PROPOSED)

    def test_optimization_on_square_with_colocated_sites(self) -> None:
        """
        Test topology optimization on the square topology
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = square_topology_with_colocated_sites(params)

        optimize_topology(topology, params)

        # Verify POP5, DN3 and both CNs are proposed (POP5/DN3 are proposed
        # instead of the co-located CNs)
        for site_id, site in topology.sites.items():
            if site_id in {"CN7", "CN8", "POP5", "DN3"}:
                self.assertEqual(site.status_type, StatusType.PROPOSED)

    def test_optimization_with_tiered_demand(self) -> None:
        """
        Test tiered demand
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

        min_cost_solution = _run_min_cost_step(topology, params)
        max_cov_solution = _run_max_coverage_step(topology, params)
        self.assertIsNotNone(max_cov_solution)
        min_int_solution = _run_interference_step(topology, params)

        solutions = [min_cost_solution, max_cov_solution, min_int_solution]

        # Verify there is positive flow
        for solution in solutions:
            self.assertGreater(solution.flow_decisions[("DN4", "CN7")], 0)
            self.assertGreater(solution.flow_decisions[("DN4", "CN8")], 0)
            # Verify that flow to CN7 is twice that of flow to CN8
            # This should be true provided that all demand can be satisfied
            self.assertEqual(
                solution.flow_decisions[("DN4", "CN7")],
                2 * solution.flow_decisions[("DN4", "CN8")],
            )

        # Enable maximize common bandwidth and set demand to large number that
        # network cannot achieve - network should get best possible result
        # regardless with flow to CN7 twice that of flow to CN8
        params.maximize_common_bandwidth = True
        for demand in topology.demand_sites.values():
            demand.demand = 1.0

        min_cost_solution = _run_min_cost_step(topology, params)
        max_cov_solution = _run_max_coverage_step(topology, params)
        self.assertIsNotNone(max_cov_solution)
        min_int_solution = _run_interference_step(topology, params)

        solutions = [min_cost_solution, max_cov_solution, min_int_solution]

        for solution in solutions:
            # Validate unit test itself - demand exceeds capability of network
            # Note: Flow into CN8 equals flow into connected demand site so checking
            # that demand (2.0) is greater than the flow into CN8 is sufficient
            self.assertGreater(2.0, solution.flow_decisions[("DN4", "CN8")])
            # Validate solution
            self.assertGreater(solution.flow_decisions[("DN4", "CN7")], 0)
            self.assertGreater(solution.flow_decisions[("DN4", "CN8")], 0)
            self.assertAlmostEqual(
                solution.flow_decisions[("DN4", "CN7")],
                2 * solution.flow_decisions[("DN4", "CN8")],
                places=6,
            )

    def test_hop_count_constraint(self) -> None:
        """
        Verify that hop count constraint is obeyed during optimization.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )

        # Set max hop count = 1; no CNs within one hop of the POP so there is
        # no feasible solution
        params.maximum_number_hops = 1
        topology = hop_count_topology(params)
        with self.assertRaises(OptimizerException):
            optimize_topology(topology, params)

        # Set max hop count = 2; only POP0->DN1->CN6 is chosen
        params.maximum_number_hops = 2
        topology = hop_count_topology(params)
        optimize_topology(topology, params)

        proposed_sites = {"POP0", "DN1", "CN6"}
        unreachable_sites = {"DN4"}
        proposed_links = {"POP0-DN1", "DN1-POP0", "DN1-CN6"}
        unreachable_links = {"DN3-DN4", "DN4-DN3", "DN4-DN5", "DN5-DN4"}
        for site_id, site in topology.sites.items():
            self.assertEqual(
                site.status_type,
                StatusType.PROPOSED
                if site_id in proposed_sites
                else StatusType.UNREACHABLE
                if site_id in unreachable_sites
                else StatusType.CANDIDATE,
            )
        for link_id, link in topology.links.items():
            self.assertEqual(
                link.status_type,
                StatusType.PROPOSED
                if link_id in proposed_links
                else StatusType.UNREACHABLE
                if link_id in unreachable_links
                else StatusType.CANDIDATE,
            )

        # Set max hop count = 6; all paths are chosen
        params.maximum_number_hops = 6
        topology = hop_count_topology(params)
        optimize_topology(topology, params)

        for site in topology.sites.values():
            self.assertEqual(site.status_type, StatusType.PROPOSED)
        for link in topology.links.values():
            self.assertEqual(link.status_type, StatusType.PROPOSED)

    def test_tdm_constraint(self) -> None:
        """
        Verify tdm constraints are applied during optimization.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            demand=2 / 3,
            maximize_common_bandwidth=True,
        )
        topology = tdm_constraint_topology(params)

        _run_min_cost_step(topology, params)
        _run_max_coverage_step(topology, params)
        solution = _run_interference_step(topology, params)

        # All links and sectors are proposed
        for site in topology.sites.values():
            self.assertEqual(site.status_type, StatusType.PROPOSED)
        for link in topology.links.values():
            self.assertEqual(link.status_type, StatusType.PROPOSED)

        # Each link is active for 1/3 of the time
        for link in topology.links.values():
            self.assertEqual(
                solution.flow_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                link.capacity / 3,
            )
            self.assertEqual(
                solution.tdm_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                1 / 3,
            )


class TestCostVsCapex(TestCase):
    def test_square_topology_with_cns_cost(self) -> None:
        """
        Test that OptimizationSolution cost is equal to proposed_capex.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
        )
        topology = square_topology_with_cns(params)

        min_cost_solution = _run_min_cost_step(topology, params)

        self.assertEqual(
            min_cost_solution.cost,
            compute_capex(topology, params).proposed_capex,
        )
        self.assertEqual(
            min_cost_solution.objective_value, min_cost_solution.cost
        )

        max_cov_solution = _run_max_coverage_step(topology, params)
        self.assertIsNotNone(max_cov_solution)

        self.assertEqual(
            max_cov_solution.cost,
            compute_capex(topology, params).proposed_capex,
        )

        min_int_solution = _run_interference_step(topology, params)
        self.assertIsNotNone(min_int_solution)

        self.assertEqual(
            min_int_solution.cost,
            compute_capex(topology, params).proposed_capex,
        )

    def test_square_topology_with_colocated_sites_cost(self) -> None:
        """
        Tests that OptimizationSolution cost is equal to proposed_capex
        when there are co-located CNs, DNs and POPs.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
        )
        topology = square_topology_with_colocated_sites()

        min_cost_solution = _run_min_cost_step(topology, params)

        min_cost_topology_cost = compute_capex(topology, params).proposed_capex
        self.assertEqual(min_cost_solution.cost, min_cost_topology_cost)
        self.assertEqual(
            min_cost_solution.objective_value, min_cost_solution.cost
        )
        self.assertEqual(min_cost_topology_cost, 8700.0)

        max_cov_solution = _run_max_coverage_step(topology, params)
        self.assertIsNotNone(max_cov_solution)

        max_coverage_topology_cost = compute_capex(
            topology, params
        ).proposed_capex
        self.assertEqual(
            max_cov_solution.cost,
            max_coverage_topology_cost,
        )
        self.assertEqual(max_coverage_topology_cost, 10800.0)

        min_int_solution = _run_interference_step(topology, params)
        self.assertIsNotNone(min_int_solution)

        min_int_topology_cost = compute_capex(topology, params).proposed_capex
        self.assertEqual(min_int_solution.cost, min_int_topology_cost)
        self.assertEqual(min_int_topology_cost, 10800.0)
