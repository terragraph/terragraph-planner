# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from copy import deepcopy
from unittest import TestCase

from terragraph_planner.common.configuration.enums import (
    LinkType,
    StatusType,
    TopologyRouting,
)
from terragraph_planner.common.topology_models.demand_site import DemandSite
from terragraph_planner.common.topology_models.test.helper import (
    dpa_topology,
    set_topology_proposed,
    square_topology,
    square_topology_with_cns,
)
from terragraph_planner.optimization.topology_networkx import (
    build_digraph,
    disjoint_paths,
    get_topology_routing_results,
    single_edge_failures,
    single_site_failures,
)


class TestDisruptionFunctions(TestCase):
    def test_disruptions_on_square_topology(self) -> None:
        """
        Find link disruptions on the square topology
        """
        topology = square_topology()
        set_topology_proposed(topology)

        graph = build_digraph(topology, StatusType.active_status())

        edge_failure_disruptions = single_edge_failures(graph)

        # Number of links in the disruptions dictionary should match the number
        # of backhaul links in the topology / 2 (each backhaul link counted
        # just once)
        self.assertEqual(len(edge_failure_disruptions), len(topology.links) / 2)

        # Because of the way square topology was constructed, if all links are
        # active, there should not be any disruptions caused by the single edge
        # failures
        self.assertTrue(
            all(len(val) == 0 for val in edge_failure_disruptions.values())
        )
        pop_disruptions, dn_disruptions = single_site_failures(graph)
        self.assertEqual(len(dn_disruptions), 4)
        self.assertEqual(pop_disruptions, {})

    def test_disruptions_on_modified_square_topology(self) -> None:
        """
        Find link disruptions on a modified square topology. Namely, make the
        DN1<->DN2, DN2<->DN3, DN3<->DN4 candidates and everything
        else proposed. Then, sites DN2 and DN3 will be dependent on POP6. If a
        POP6<->DN2 or POP6<->DN3 fails, then demand sites connected to sites
        DN2 and DN3 only will fail.
        """
        topology = square_topology()
        set_topology_proposed(topology)

        # Deactivate some links and add a couple demand sites
        candidate_links = {
            "DN1-DN2",
            "DN2-DN1",
            "DN2-DN3",
            "DN3-DN2",
            "DN3-DN4",
            "DN4-DN3",
        }
        for link_id in candidate_links:
            topology.links[link_id].status_type = StatusType.CANDIDATE

        topology.add_demand_site(
            DemandSite(
                location=deepcopy(topology.sites["POP5"].location),
                connected_sites=[topology.sites["POP5"]],
            )
        )
        topology.add_demand_site(
            DemandSite(
                location=deepcopy(topology.sites["POP6"].location),
                connected_sites=[topology.sites["POP6"]],
            )
        )

        graph = build_digraph(topology, StatusType.active_status())

        edge_failure_disruptions = single_edge_failures(graph)

        self.assertEqual(len(edge_failure_disruptions), 5)

        for link, val in edge_failure_disruptions.items():
            if (link[0], link[1]) in {
                ("POP6", "DN2"),
                ("POP6", "DN3"),
                ("DN2", "POP6"),
                ("DN3", "POP6"),
            }:
                self.assertEqual(len(val), 1)
            else:
                self.assertEqual(len(val), 0)
        pop_disruptions, dn_disruptions = single_site_failures(graph)
        self.assertEqual(len(dn_disruptions), 4)
        self.assertEqual(len(pop_disruptions), 2)
        self.assertEqual(len(pop_disruptions["POP5"]), 3)
        self.assertEqual(len(pop_disruptions["POP6"]), 3)

    def test_disruptions_on_tree_topology(self) -> None:
        """
        Find link disruptions on a tree topology. Namely, make the DN1<->DN4,
        DN1<->DN5, DN4<->DN5, DN2<->DN3 and DN3<->DN4 candidates and everything
        else proposed. Also make DN4 and POP5 candidates. Now we have a tree
        rooted at POP6, i.e., POP6->DN3, POP6<->DN2, and DN2<->DN1.
        """
        topology = square_topology()
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

        graph = build_digraph(topology, StatusType.active_status())

        edge_failure_disruptions = single_edge_failures(graph)

        self.assertEqual(len(edge_failure_disruptions), 3)
        for link, val in edge_failure_disruptions.items():
            if (link[0], link[1]) in {("POP6", "DN3"), ("DN3", "POP6")}:
                for demand_id in val:
                    for site in topology.demand_sites[
                        demand_id
                    ].connected_sites:
                        site.site_id in {"DN3"}
            elif (link[0], link[1]) in {("POP6", "DN2"), ("DN2", "POP6")}:
                for demand_id in val:
                    for site in topology.demand_sites[
                        demand_id
                    ].connected_sites:
                        site.site_id in {"DN2", "DN1"}
            elif (link[0], link[1]) in {("DN2", "DN1"), ("DN1", "DN2")}:
                for demand_id in val:
                    for site in topology.demand_sites[
                        demand_id
                    ].connected_sites:
                        site.site_id in {"DN1"}

        pop_disruptions, dn_disruptions = single_site_failures(graph)
        self.assertEqual(len(dn_disruptions), 3)
        self.assertEqual(len(dn_disruptions["DN1"]), 1)
        self.assertEqual(len(dn_disruptions["DN2"]), 2)
        self.assertEqual(len(dn_disruptions["DN3"]), 2)
        self.assertEqual(len(pop_disruptions), 1)
        self.assertEqual(len(pop_disruptions["POP6"]), 5)

    def test_disruptions_on_square_topology_with_cns(self) -> None:
        topology = square_topology_with_cns()
        set_topology_proposed(topology)

        graph = build_digraph(topology, StatusType.active_status())

        edge_failure_disruptions = single_edge_failures(graph)

        # Number of links in the disruptions dictionary should match the number
        # of backhaul links in the topology / 2 (each backhaul link counted
        # just once)
        self.assertEqual(
            len(edge_failure_disruptions),
            len(
                [
                    link_id
                    for link_id, link in topology.links.items()
                    if link.link_type == LinkType.WIRELESS_BACKHAUL
                ]
            )
            / 2,
        )

        # Because of the way square topology was constructed, if all links are
        # active, only DN-CN links should cause a disruption on that CN's demand
        # point. So, we expect a single demand disruption for the two DN->CN
        # links and no disruptions for the rest of the links.
        cn_site_ids = {"CN7", "CN8"}
        for link, val in edge_failure_disruptions.items():
            if link[1] in cn_site_ids:
                self.assertEqual(len(val), 1)
            else:
                self.assertEqual(len(val), 0)

        pop_disruptions, dn_disruptions = single_site_failures(graph)
        self.assertEqual(len(dn_disruptions), 1)
        self.assertEqual(pop_disruptions, {})


class TestTopologyRouting(TestCase):
    def test_topology_routing_on_square_topology(self) -> None:
        topology = square_topology()
        set_topology_proposed(topology)

        # Make the POP6 and all of its links candidate.
        topology.sites["POP6"].status_type = StatusType.CANDIDATE
        topology.links["POP6-DN3"].status_type = StatusType.CANDIDATE
        topology.links["DN3-POP6"].status_type = StatusType.CANDIDATE
        topology.links["POP6-DN2"].status_type = StatusType.CANDIDATE
        topology.links["DN2-POP6"].status_type = StatusType.CANDIDATE

        proposed_graph = build_digraph(topology, StatusType.active_status())
        links_used = get_topology_routing_results(
            topology, proposed_graph, TopologyRouting.SHORTEST_PATH
        )

        expected_links_used = {"POP5-DN1", "DN1-DN2", "POP5-DN4", "DN4-DN3"}
        self.assertSetEqual(links_used, expected_links_used)

    def test_topology_routing_on_square_topology_with_cost(self) -> None:
        topology = square_topology()
        set_topology_proposed(topology)

        reachable_graph = build_digraph(topology, StatusType.reachable_status())
        self.assertEqual(
            reachable_graph.get_edge_data("DN4", "DN3")["link_cost"], 1
        )
        self.assertEqual(
            reachable_graph.get_edge_data("DN1", "DN2")["link_cost"], 1
        )
        self.assertEqual(
            reachable_graph.get_edge_data("DN4", "DN1")["link_cost"], 1
        )
        self.assertEqual(
            reachable_graph.get_edge_data("DN3", "DN2")["link_cost"], 1
        )

        # Mock link mcs_level and the costs are updated
        topology.links["DN4-DN3"].mcs_level = 2
        topology.links["DN1-DN2"].mcs_level = 3
        topology.links["DN4-DN1"].mcs_level = 7
        topology.links["DN3-DN2"].mcs_level = 8

        proposed_graph = build_digraph(topology, StatusType.active_status())
        self.assertEqual(
            proposed_graph.get_edge_data("DN4", "DN3")["link_cost"], 15
        )
        self.assertEqual(
            proposed_graph.get_edge_data("DN1", "DN2")["link_cost"], 15
        )
        self.assertEqual(
            proposed_graph.get_edge_data("DN4", "DN1")["link_cost"], 3
        )
        self.assertEqual(
            proposed_graph.get_edge_data("DN3", "DN2")["link_cost"], 3
        )

        links_used = get_topology_routing_results(
            topology, proposed_graph, TopologyRouting.MCS_COST_PATH
        )

        expected_links_used = {"POP5-DN1", "POP5-DN4", "POP6-DN2", "POP6-DN3"}
        self.assertSetEqual(links_used, expected_links_used)

    def test_topology_routing_on_square_topology_with_cns(self) -> None:
        topology = square_topology_with_cns()
        set_topology_proposed(topology)

        proposed_graph = build_digraph(topology, StatusType.active_status())
        links_used = get_topology_routing_results(
            topology, proposed_graph, TopologyRouting.SHORTEST_PATH
        )

        expected_links_used = {"POP5-DN4", "DN4-CN7", "DN4-CN8"}
        self.assertSetEqual(links_used, expected_links_used)

    def test_topology_routing_on_modified_square_topology(self) -> None:
        """
        Find topology routing results on a modified square topology.
        """
        topology = square_topology()
        set_topology_proposed(topology)
        # Deactivate some links and add a couple demand sites
        candidate_links = {
            "DN1-DN2",
            "DN2-DN1",
            "DN2-DN3",
            "DN3-DN2",
            "DN3-DN4",
            "DN4-DN3",
            "POP5-DN1",
            "DN1-POP5",
        }
        for link_id in candidate_links:
            topology.links[link_id].status_type = StatusType.CANDIDATE
        topology.add_demand_site(
            DemandSite(
                location=topology.sites["POP5"]._location,
                connected_sites=[topology.sites["POP5"]],
            )
        )
        topology.add_demand_site(
            DemandSite(
                location=topology.sites["POP6"]._location,
                connected_sites=[topology.sites["POP6"]],
            )
        )

        proposed_graph = build_digraph(topology, StatusType.active_status())
        links_used = get_topology_routing_results(
            topology, proposed_graph, TopologyRouting.SHORTEST_PATH
        )

        expected_links_used = {"POP5-DN4", "DN4-DN1", "POP6-DN3", "POP6-DN2"}
        self.assertSetEqual(links_used, expected_links_used)

    def test_topology_routing_on_tree_topology(self) -> None:
        """
        Find topology routing results on a tree topology. Namely, make the DN1<->DN4,
        DN1<->DN5, DN4<->DN5, DN2<->DN3 and DN3<->DN4 candidates and everything
        else proposed. Also make DN4 and POP5 candidates. Now we have a tree
        rooted at POP6, i.e., POP6->DN3, POP6<->DN2, and DN2<->DN1.
        """
        topology = square_topology()
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

        proposed_graph = build_digraph(topology, StatusType.active_status())
        links_used = get_topology_routing_results(
            topology, proposed_graph, TopologyRouting.SHORTEST_PATH
        )

        expected_links_used = {"POP6-DN3", "POP6-DN2", "DN2-DN1"}
        self.assertSetEqual(links_used, expected_links_used)

    def test_dpa_routing(self) -> None:
        topology = dpa_topology()
        set_topology_proposed(topology)
        # All links are in MCS=12 except the following
        topology.links["POP1-DN3"].mcs_level = 3
        topology.links["POP2-DN6"].mcs_level = 5
        topology.links["POP2-DN8"].mcs_level = 3

        # Shortest paths based on number of hops: POP1->DN3->CN9 & POP2->DN8->CN10
        proposed_graph = build_digraph(topology, StatusType.active_status())
        links_used = get_topology_routing_results(
            topology, proposed_graph, TopologyRouting.SHORTEST_PATH
        )
        expected_links_used = {"POP1-DN3", "DN3-CN9", "POP2-DN8", "DN8-CN10"}
        self.assertSetEqual(links_used, expected_links_used)

        # MCS_based paths: POP1->DN4->DN5->CN9 & POP1->DN4->DN6->DN7->CN10
        links_used = get_topology_routing_results(
            topology, proposed_graph, TopologyRouting.MCS_COST_PATH
        )
        expected_links_used = {
            "POP1-DN4",
            "DN4-DN5",
            "DN5-CN9",
            "DN4-DN6",
            "DN6-DN7",
            "DN7-CN10",
        }
        self.assertSetEqual(links_used, expected_links_used)

        # DPA paths: POP1->DN4->DN5->CN9 & POP2->DN6->DN7->CN10
        links_used = get_topology_routing_results(
            topology, proposed_graph, TopologyRouting.DPA_PATH
        )
        expected_links_used = {
            "POP1-DN4",
            "DN4-DN5",
            "DN5-CN9",
            "POP2-DN6",
            "DN6-DN7",
            "DN7-CN10",
        }
        self.assertSetEqual(links_used, expected_links_used)


class TestDisjointPaths(TestCase):
    def test_disjoint_on_square_topology(self) -> None:
        topology = square_topology()
        set_topology_proposed(topology)
        graph = build_digraph(topology, StatusType.active_status())
        paths = disjoint_paths(topology, graph)
        for demand_id in topology.demand_sites.keys():
            self.assertTrue(demand_id in paths.demand_with_disjoint_paths)

    def test_disjoint_on_modified_square_topology(self) -> None:
        topology = square_topology()
        set_topology_proposed(topology)
        # Deactivate links (1,2), (2, 3) and (3, 4).
        # Then, sites 4, 1 and 5 are a cycle and the demand sites attached to them
        # will have disjoint paths. For sites 2 and 3, that is not the case.
        candidate_links = {
            "DN1-DN2",
            "DN2-DN1",
            "DN2-DN3",
            "DN3-DN2",
            "DN3-DN4",
            "DN4-DN3",
        }
        for link_id in candidate_links:
            topology.links[link_id].status_type = StatusType.CANDIDATE
        graph = build_digraph(topology, StatusType.active_status())
        paths = disjoint_paths(topology, graph)
        disjoint_path_exists = [True, True, True, False, False, True]
        idx = 0
        for demand_id in topology.demand_sites.keys():
            if disjoint_path_exists[idx]:
                self.assertTrue(demand_id in paths.demand_with_disjoint_paths)
            else:
                self.assertTrue(
                    demand_id not in paths.demand_with_disjoint_paths
                )
            idx += 1

    def test_disjoint_on_tree_topology(self) -> None:
        """
        Find link disruptions on a tree topology. Namely, make the DN1<->DN4,
        DN1<->DN5, DN4<->DN5, DN2<->DN3 and DN3<->DN4 candidates and everything
        else proposed. Also make DN4 and POP5 candidates. Now we have a tree
        rooted at POP6, i.e., POP6->DN3, POP6<->DN2, and DN2<->DN1.
        """
        topology = square_topology()
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

        graph = build_digraph(topology, StatusType.active_status())
        paths = disjoint_paths(topology, graph)
        disjoint_path_exists = [False, False, False, False, False, True]
        idx = 0
        for demand_id in topology.demand_sites.keys():
            if disjoint_path_exists[idx]:
                self.assertTrue(demand_id in paths.demand_with_disjoint_paths)
            else:
                self.assertTrue(
                    demand_id not in paths.demand_with_disjoint_paths
                )
            idx += 1
        self.assertEqual(len(paths.disconnected_demand_locations), 1)

    def test_disjoint_on_square_topology_with_cns(self) -> None:
        topology = square_topology_with_cns()
        set_topology_proposed(topology)
        graph = build_digraph(topology, StatusType.active_status())
        paths = disjoint_paths(topology, graph)
        self.assertEqual(
            len(paths.demand_with_disjoint_paths), len(topology.demand_sites)
        )
        # Both CN sites have at least two disjoint paths to a POP
        self.assertTrue(len(paths.demand_with_disjoint_paths), 2)
