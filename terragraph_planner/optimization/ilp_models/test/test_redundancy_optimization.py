# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import SiteType, StatusType
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    diamond_topology,
    figure_eight_topology,
)
from terragraph_planner.optimization.ilp_models.redundancy_optimization import (
    RedundantNetwork,
    compute_candidate_edges_for_redundancy,
)
from terragraph_planner.optimization.structs import RedundancyParams


class TestRedundancyOptimization(TestCase):
    def test_figure_eight_redundancy(self) -> None:
        """
        Test redundancy optimization on a figure eight topology.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = figure_eight_topology(params)

        # Propose some of the sites/links to build redundancy
        proposed_sites = {"POP0", "DN1", "DN3", "DN4", "DN6", "CN7"}
        for site_id in proposed_sites:
            topology.sites[site_id].status_type = StatusType.PROPOSED
        for sector in topology.sectors.values():
            if sector.site.site_id in proposed_sites:
                sector.status_type = StatusType.PROPOSED
        proposed_links = {
            "POP0-DN1",
            "DN1-POP0",
            "DN1-DN3",
            "DN3-DN1",
            "DN3-DN4",
            "DN4-DN3",
            "DN4-DN6",
            "DN6-DN4",
            "DN6-CN7",
        }
        for link_id in proposed_links:
            topology.links[link_id].status_type = StatusType.PROPOSED

        # Redundancy params = (1, 1, 1) is automatically satisfied by
        # base network if all DNs have a path to a POP
        redundancy_params = RedundancyParams(
            pop_node_capacity=1, dn_node_capacity=1, sink_node_capacity=1
        )
        solution = RedundantNetwork(topology, params, redundancy_params).solve()
        self.assertIsNotNone(solution)

        for site_id in proposed_sites:
            self.assertEqual(solution.site_decisions[site_id], 1)
            if topology.sites[site_id].site_type == SiteType.DN:
                self.assertEqual(solution.shortage_decisions[site_id], 0)
        for site_id in ["DN2", "DN5"]:
            self.assertEqual(solution.site_decisions[site_id], 0)

        # Redundancy params = (2, 2, 2) needs sites DN2 and POP5 to satisfy
        # redundancy constraints
        redundancy_params = RedundancyParams(
            pop_node_capacity=2, dn_node_capacity=2, sink_node_capacity=2
        )
        solution = RedundantNetwork(topology, params, redundancy_params).solve()
        self.assertIsNotNone(solution)

        for site_id in proposed_sites:
            self.assertEqual(solution.site_decisions[site_id], 1)
            if topology.sites[site_id].site_type == SiteType.DN:
                self.assertEqual(solution.shortage_decisions[site_id], 0)
        for site_id in ["DN2", "DN5"]:
            self.assertEqual(solution.site_decisions[site_id], 1)

        # Redundancy params = (2, 1, 2) cannot be satisfied at all sites
        # There is shortage at sites DN4 and CN6 and site DN5 is not proposed
        redundancy_params = RedundancyParams(
            pop_node_capacity=2, dn_node_capacity=1, sink_node_capacity=2
        )
        solution = RedundantNetwork(topology, params, redundancy_params).solve()
        self.assertIsNotNone(solution)

        for site_id in proposed_sites | {"DN2"}:
            self.assertEqual(solution.site_decisions[site_id], 1)
        self.assertEqual(solution.site_decisions["DN5"], 0)
        for site_id in ["DN1", "DN3"]:
            self.assertEqual(solution.shortage_decisions[site_id], 0)
        for site_id in ["DN4", "DN6"]:
            self.assertEqual(solution.shortage_decisions[site_id], 1.0)

    def test_diamond_redundancy(self) -> None:
        """
        Test redundancy optimization on a diamond topology (which has two POPs)
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = diamond_topology(params)

        # Propose some of the sites/links to build redundancy
        proposed_sites = {"POP0", "DN1", "DN4", "POP5", "CN6", "CN7"}
        for site_id in proposed_sites:
            topology.sites[site_id].status_type = StatusType.PROPOSED
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
            topology.links[link_id].status_type = StatusType.PROPOSED

        # Redundancy params = (1, 1, 2) should connect the two disconnected
        # subnetworks via the DN1-DN4 link
        redundancy_params = RedundancyParams(
            pop_node_capacity=1, dn_node_capacity=1, sink_node_capacity=2
        )
        solution = RedundantNetwork(topology, params, redundancy_params).solve()
        self.assertIsNotNone(solution)

        for site_id in proposed_sites:
            self.assertEqual(solution.site_decisions[site_id], 1)
            if topology.sites[site_id].site_type == SiteType.DN:
                self.assertEqual(solution.shortage_decisions[site_id], 0)
        for site_id in ["DN2", "DN3"]:
            self.assertEqual(solution.site_decisions[site_id], 0)
        for link_id in proposed_links | {"DN1-DN4", "DN4-DN1"}:
            link = topology.links[link_id]
            self.assertEqual(
                solution.link_decisions[
                    (link.tx_site.site_id, link.rx_site.site_id)
                ],
                1,
            )

        # Making link DN1-DN4 unavailable means an extra site (DN2 or DN3) must be
        # proposed to satisfy redundancy constraints
        unavailable_links = ["DN1-DN4", "DN4-DN1"]
        for link_id in unavailable_links:
            topology.links[link_id]._status_type = StatusType.UNAVAILABLE

        solution = RedundantNetwork(topology, params, redundancy_params).solve()
        self.assertIsNotNone(solution)

        for site_id in proposed_sites:
            self.assertEqual(solution.site_decisions[site_id], 1)
            if topology.sites[site_id].site_type == SiteType.DN:
                self.assertEqual(solution.shortage_decisions[site_id], 0)
        self.assertEqual(
            solution.site_decisions["DN2"] + solution.site_decisions["DN3"], 1
        )

        # Redundancy params = (2, 1, 4) requires both extra sites to satisfy
        # redundancy constraints; in fact only (2, 1, 3) can actually be satisfied
        for link_id in unavailable_links:
            topology.links[
                link_id
            ]._status_type = StatusType.CANDIDATE  # Reset status

        redundancy_params = RedundancyParams(
            pop_node_capacity=2, dn_node_capacity=1, sink_node_capacity=4
        )
        solution = RedundantNetwork(topology, params, redundancy_params).solve()
        self.assertIsNotNone(solution)

        for site_id in proposed_sites | {"DN2", "DN3"}:
            self.assertEqual(solution.site_decisions[site_id], 1)
        for site_id in ["DN1", "DN4"]:
            self.assertEqual(solution.shortage_decisions[site_id], 1.0)

    def test_diamond_redundancy_heuristic(self) -> None:
        """
        Test the redundancy heuristic on the diamond topology
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
        )
        topology = diamond_topology(params)

        # Propose some of the sites/links to build redundancy
        proposed_sites = {"POP0", "DN1", "DN4", "POP5", "CN6", "CN7"}
        for site_id in proposed_sites:
            topology.sites[site_id].status_type = StatusType.PROPOSED
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
            topology.links[link_id].status_type = StatusType.PROPOSED

        # In these tests, solutions are not unique but the number of node
        # disjoint paths should be satisfied based on the input. For simplicity,
        # each path is explicitly tested, but due to non-uniqueness, this test
        # can be updated as needed

        # There should be at least one path from each POP to each DN
        edges = compute_candidate_edges_for_redundancy(
            topology=topology, pop_source_capacity=1.0, dn_source_capacity=0
        )

        # DN1: POP0 ->DN1; POP5->DN3->DN1
        # DN4: POP5->DN4; POP0->DN1->DN4
        ans = {
            ("POP0", "DN1"),
            ("POP5", "DN3"),
            ("DN3", "DN1"),
            ("POP5", "DN4"),
            ("DN1", "DN4"),
        }
        self.assertSetEqual(edges, ans)

        # There should be at least two paths from each POP to each DN
        edges = compute_candidate_edges_for_redundancy(
            topology=topology, pop_source_capacity=2.0, dn_source_capacity=0
        )

        # DN1: POP0->DN1; POP0->DN2->DN1; POP5->DN3->DN1; POP5->DN4->DN1
        # DN4: POP5->DN4; POP5->DN3->DN4; POP0->DN1->DN4; POP0->DN2->DN4
        ans = {
            ("POP0", "DN1"),
            ("POP0", "DN2"),
            ("DN2", "DN1"),
            ("POP5", "DN3"),
            ("DN3", "DN1"),
            ("POP5", "DN4"),
            ("DN4", "DN1"),
            ("DN3", "DN4"),
            ("DN1", "DN4"),
            ("DN2", "DN4"),
        }
        self.assertSetEqual(edges, ans)

        # There should be at least one path between each DN
        edges = compute_candidate_edges_for_redundancy(
            topology=topology, pop_source_capacity=0, dn_source_capacity=1.0
        )

        # DN1: DN4->DN1; DN4: DN1->DN4
        ans = {("DN4", "DN1"), ("DN1", "DN4")}
        self.assertSetEqual(edges, ans)

        # There should be at least two paths between each DN
        edges = compute_candidate_edges_for_redundancy(
            topology=topology, pop_source_capacity=0, dn_source_capacity=2.0
        )

        # DN1: DN4->DN1; DN4->DN2->DN1; DN4: DN1->DN4; DN1->DN2->DN4
        ans = {
            ("DN4", "DN1"),
            ("DN4", "DN2"),
            ("DN2", "DN1"),
            ("DN1", "DN4"),
            ("DN1", "DN2"),
            ("DN2", "DN4"),
        }
        self.assertSetEqual(edges, ans)

        # Test Delaunay version by adding an extra DN
        add_sites = {"DN2"}
        for site_id in add_sites:
            topology.sites[site_id].status_type = StatusType.PROPOSED
        for sector in topology.sectors.values():
            if sector.site.site_id in add_sites:
                sector.status_type = StatusType.PROPOSED
        add_links = {"POP0-DN2", "DN2-POP0", "DN2-DN4", "DN4-DN2"}
        for link_id in add_links:
            topology.links[link_id].status_type = StatusType.PROPOSED

        edges = compute_candidate_edges_for_redundancy(
            topology=topology, pop_source_capacity=0, dn_source_capacity=2.0
        )

        ans = {
            ("DN4", "DN1"),
            ("DN1", "DN2"),
            ("DN3", "DN2"),
            ("DN4", "DN2"),
            ("DN3", "DN1"),
            ("DN2", "DN1"),
            ("DN1", "DN4"),
            ("DN2", "DN4"),
            ("DN1", "DN3"),
            ("DN2", "DN3"),
        }
        self.assertSetEqual(edges, ans)
