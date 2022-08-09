# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import math
import time
from copy import deepcopy
from typing import Dict, List, Set, Tuple

import networkx as nx

from terragraph_planner.common.configuration.enums import (
    LinkType,
    SiteType,
    StatusType,
    TopologyRouting,
)
from terragraph_planner.common.exceptions import (
    OptimizerException,
    planner_assert,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.constants import DEMAND, SUPERSOURCE
from terragraph_planner.optimization.structs import DisjointPath

logger: logging.Logger = logging.getLogger(__name__)


def build_digraph(
    topology: Topology, status_filter: Set[StatusType]
) -> nx.DiGraph:
    """
    Returns a directed networkx graph where the graph vertices are the active
    sites and the graph edges are the active links
    """

    def _mcs_to_cost(mcs: int) -> float:
        """
        Convert mcs_level to cost.
        """
        mcs_cost = {
            2: 15,
            3: 15,
            4: 3,
            5: 3,
            6: 3,
            7: 3,
            8: 3,
            9: 1,
            10: 1,
            11: 1,
            12: 1,
        }
        return 1 if mcs > 12 else mcs_cost.get(mcs, math.inf)

    G = nx.DiGraph()
    default_link_cost = 1
    for site_id, site in topology.sites.items():
        if site.site_type == SiteType.POP and site.status_type in status_filter:
            G.add_edge(
                SUPERSOURCE,
                site_id,
                link_type=SUPERSOURCE,
                link_cost=default_link_cost,
            )

    nx.set_node_attributes(G, {SUPERSOURCE: SUPERSOURCE}, name="site_type")

    for link in topology.links.values():
        if (
            link.status_type in status_filter
            and link.tx_site.status_type in status_filter
            and link.rx_site.status_type in status_filter
        ):
            G.add_edge(
                link.tx_site.site_id,
                link.rx_site.site_id,
                link_type=link.link_type,
                link_cost=_mcs_to_cost(link.mcs_level),
            )

    nx.set_node_attributes(
        G,
        {site.site_id: site.site_type for site in topology.sites.values()},
        name="site_type",
    )

    for demand_id, demand in topology.demand_sites.items():
        for site in demand.connected_sites:
            if site.status_type in status_filter:
                G.add_edge(
                    site.site_id,
                    demand_id,
                    link_type=DEMAND,
                    link_cost=default_link_cost,
                )

    nx.set_node_attributes(
        G,
        {demand.demand_id: DEMAND for demand in topology.demand_sites.values()},
        name="site_type",
    )

    if len(G.nodes()) == 0 or len(G.edges()) == 0:
        logger.warning("NetworkX graph does not have any nodes or edges.")

    return G


def find_connected_demands(graph: nx.Graph) -> Set[str]:
    """
    Find the set of demand sites that are connected to the graph originating at
    the supersource
    """
    descendants = nx.descendants(graph, source=SUPERSOURCE)
    connected_demand_ids = set()
    for node, site_type in graph.nodes(data="site_type"):
        if site_type == DEMAND and node in descendants:
            connected_demand_ids.add(node)
    return connected_demand_ids


def single_edge_failures(graph: nx.Graph) -> Dict[Tuple[str, str], Set[str]]:
    """
    Determine the disconnected demand sites when each wireless backhaul link is
    disabled.
    """
    graph_copy = deepcopy(graph)
    connected_demand_ids = find_connected_demands(graph)

    # Do not distinguish between an edge and its reverse
    def _sorted_edge(node1: str, node2: str) -> Tuple[str, str]:
        if node1 < node2:
            return (node1, node2)
        return (node2, node1)

    # Find list of demand sites that get service disruption when an edge is
    # disrupted
    edge_disruptions = {}
    for u, v, link_type in graph.edges(data="link_type"):
        if (
            link_type == SUPERSOURCE
            or link_type == DEMAND
            or link_type == LinkType.WIRELESS_ACCESS
            or link_type == LinkType.ETHERNET
        ):
            continue

        key = _sorted_edge(u, v)
        if key in edge_disruptions:
            continue

        has_rev = graph.has_edge(v, u)

        # Detect the number of disruptions caused by each edge.
        graph_copy.remove_edge(u, v)
        if has_rev:
            graph_copy.remove_edge(v, u)
        descendents = nx.descendants(graph_copy, source=SUPERSOURCE)
        graph_copy.add_edge(u, v)
        if has_rev:
            graph_copy.add_edge(v, u)

        # If any of the connected demand sites lose their connection
        # due to the closure of edge e, then count this demand site
        # towards the failures caused
        edge_disruptions[key] = connected_demand_ids - descendents

    return edge_disruptions


def single_site_failures(
    graph: nx.Graph,
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """
    This function closes all CN/DN/POP-CN/DN/POP locations one by one
    and checks which demand locations get disconnected from the supersource
    Note: This computation ignores throughput values and
    time division multiplexing
    """
    connected_demand_ids = find_connected_demands(graph)

    # The list of demand sites that get service disruption when
    # a site is closed
    pop_disruptions: Dict[str, Set[str]] = {}
    dn_disruptions: Dict[str, Set[str]] = {}

    graph_copy = deepcopy(graph)

    # Out of the connected demand sites, count how many of them
    # would lose service if the site was down.
    for site_id, site_type in graph.nodes(data="site_type"):
        if (
            site_type == SiteType.CN
            or site_type == DEMAND
            or site_id == SUPERSOURCE
        ):
            continue
        edges_to_remove = [
            (site_id, rx_site_id, graph_copy[site_id][rx_site_id])
            for rx_site_id in graph_copy[site_id]
        ]
        graph_copy.remove_edges_from(edges_to_remove)
        descendents = nx.descendants(graph_copy, source=SUPERSOURCE)
        graph_copy.add_edges_from(edges_to_remove)
        # If any of the connected demand sites lose their connection
        # due to the closure of the site, then count this demand site
        # towards the failures caused
        site_disruptions = connected_demand_ids - descendents

        if len(site_disruptions) == 0:
            continue
        if site_type == SiteType.POP:
            pop_disruptions[site_id] = site_disruptions
        elif site_type == SiteType.DN:
            dn_disruptions[site_id] = site_disruptions

    return pop_disruptions, dn_disruptions


def find_most_disruptive_links(
    proposed_graph: nx.DiGraph, candidate_graph: nx.DiGraph, count: int
) -> Set[Tuple[str, str]]:
    """
    Identify edges that cause the most disruption in the event of a failure.
    First, find the edge with the most disruptions and check whether it causes
    a disruption in the canidate graph. If not it is added to the disruptive
    edges list and removed from the candidate graph. Then the second most
    disruptive edge is checked for whether it causes a disruption
    in the modified candidate graph. If not it is added to the disruptive edges
    list and removed from the candidate graph. This process continues until
    count number of edges are found.
    """
    if count <= 0:
        return set()

    start = time.time()
    edge_disruptions = single_edge_failures(proposed_graph)
    sorted_edges = sorted(
        edge_disruptions, key=lambda i: len(edge_disruptions[i]), reverse=True
    )

    candidate_connected_demands = find_connected_demands(candidate_graph)

    candidate_graph_copy = deepcopy(candidate_graph)

    disruptive_edges = set()
    for u, v in sorted_edges:
        if len(disruptive_edges) >= count:
            break
        elif len(edge_disruptions[(u, v)]) == 0:
            break
        elif proposed_graph[u][v]["link_type"] == LinkType.WIRELESS_ACCESS:
            continue
        elif (u, v) in disruptive_edges:
            continue

        has_rev = candidate_graph.has_edge(v, u)

        # If removing this edge from the candidate graph in addition
        # to the previous edges in disruptive_edges cuts off one or more
        # demands in the candidate graph, do not add this to disruptive_edges
        candidate_graph_copy.remove_edge(u, v)
        if has_rev:
            candidate_graph_copy.remove_edge(v, u)
        descendents = nx.descendants(candidate_graph_copy, source=SUPERSOURCE)

        candidate_disruptions = candidate_connected_demands - descendents

        if len(candidate_disruptions) == 0:
            disruptive_edges.add((u, v))
            if has_rev:
                disruptive_edges.add((v, u))
        else:
            candidate_graph_copy.add_edge(u, v)
            if has_rev:
                candidate_graph_copy.add_edge(v, u)
    end = time.time()
    logger.info(
        f"Found {len(disruptive_edges)} adversarial edges in {end-start:0.2f} seconds."
    )
    return disruptive_edges


def _get_dpa_routing_paths(
    graph: nx.Graph, paths: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    """
    Get DPA (Deterministic Prefix Allocation) paths.
    The graph is first divided into zones based on unweighted shortest path,
    each zone with 1 POP and all nodes connect to the POP; then MCS-weighted
    shortest paths are recalculated in each zone, and all merged and return
    as the DPA shortest paths.
    """
    dpa_paths: Dict[str, List[str]] = {}
    subgraph_nodes: Dict[str, Set[str]] = {}
    for p in paths.values():
        if len(p) <= 1:
            continue
        pop = p[1]
        if pop not in subgraph_nodes.keys():
            subgraph_nodes[pop] = set()
        subgraph_nodes[pop].update(p)
    for sg_nodes in subgraph_nodes.values():
        subgraph = graph.subgraph(list(sg_nodes))
        subgraph_paths = nx.shortest_path(
            subgraph, source=SUPERSOURCE, weight="link_cost"
        )
        dpa_paths.update(subgraph_paths)
    return dpa_paths


def get_topology_routing_results(
    topology: Topology,
    graph: nx.Graph,
    type: TopologyRouting,
) -> Set[str]:
    """
    This function looks at a computes shortest routing paths from SUPERSOURCE to each
    demand site. Then, (1) Returns minimum hop length for each demand site
    (dict where keys are demand_site ids)
    (2) Number of times a link was used at a shortest path
    (dict where keys are antenna links at the networkx graph)
    (3) Number of times a sector was used at a shortest path
    (dict where keys are all sector ids)
    This computation ignores throughput values and
    time division multiplexing

    @param topology: The Topology object.
    @param graph: The networkx graph based on the topology.
    @param type: The user input routing method type.
    """
    if type == TopologyRouting.MCS_COST_PATH:
        shortest_paths = nx.shortest_path(
            graph, source=SUPERSOURCE, weight="link_cost"
        )
    else:
        shortest_paths = nx.single_source_shortest_path(
            graph, source=SUPERSOURCE
        )
        if type == TopologyRouting.DPA_PATH:
            shortest_paths = _get_dpa_routing_paths(graph, shortest_paths)

    # Hop length is number of sites the shortest path passes through
    # NOT including the demand site and supersource
    links_used = set()

    for d in topology.demand_sites.keys():
        if d not in shortest_paths:
            continue
        shortest_path = shortest_paths[d]
        # Below calculation does not count number of times
        # (SOURCE,POP) and (DN/CN/POP, DEMAND) links are used
        for n in range(2, len(shortest_path) - 1):
            edge = (shortest_path[n - 1], shortest_path[n])
            link_id = "-".join(edge)
            planner_assert(
                link_id in topology.links,
                "A path has an intermediate demand site.",
                OptimizerException,
            )
            links_used.add(link_id)

    return links_used


def disjoint_paths(topology: Topology, graph: nx.Graph) -> DisjointPath:
    """
    This function checks if there are two disjoint paths from
    active POPs to each demand location. Returns a dictionary
    with boolean values.
    Note: This computation ignores throughput values and
    time-division-multiplexing
    """
    all_shortest_paths = nx.single_source_shortest_path(
        graph, source=SUPERSOURCE
    )

    demand_with_disjoint_paths = set()
    disconnected_demand_locations = set()
    demand_connected_to_pop = set()
    for demand_id in topology.demand_sites:
        shortest_path = []
        if demand_id in all_shortest_paths:
            # Filter the shortest path that end with demand_id
            shortest_path = all_shortest_paths[demand_id]
        else:
            disconnected_demand_locations.add(demand_id)
            continue

        # Consider the case where a demand is directly connected to a POP,
        # then, there will be no links to remove. In that case, count the
        # number of all simple paths.
        if len(shortest_path) <= 3:
            # The case where shortest path length is < 3 and > 0
            # should not exist; because length = 2 would imply that there is
            # an edge between SUPERSOURCE and demand site. If length == 1,
            # then it should mean that the path is only SUPERSOURCE, which
            # means that the demand site is disconnected.
            planner_assert(
                len(shortest_path) == 3,
                "The shortest path length should be at least 3.",
                OptimizerException,
            )
            # Make sure that the shortest path is passing through a POP
            planner_assert(
                topology.sites[shortest_path[1]].site_type == SiteType.POP,
                "The shortest path must pass through a POP.",
                OptimizerException,
            )
            demand_connected_to_pop.add(demand_id)
            continue

        # Delete edges from POPs to that demand location
        # Not including:
        # 1 - (SUPERSOURCE, POP) connection
        # 2 - (DN/POP, CN) connection
        # 3 - (CN/DN/POP, DEMAND) connection
        # Example1: For a path: [SOURCE, POP, DN1, DN2, DN3, DEMAND]
        # We remove edges (POP, DN1), (DN1, DN2), (DN2, DN3)
        # Example2: For a path: [SOURCE, POP, DN1, DN2, DN3, CN1, DEMAND]
        # We remove edges (POP, DN1), (DN1, DN2), (DN2, DN3)
        link_ids = []
        end = 0
        for n in range(1, len(shortest_path) - 2):
            tail_site_id = shortest_path[n + 1]
            if topology.sites[tail_site_id].site_type == SiteType.CN:
                break
            edge = (shortest_path[n], shortest_path[n + 1])
            link_id = "-".join(edge)
            link_ids.append(link_id)
            graph.remove_edge(shortest_path[n], shortest_path[n + 1])
            end = n + 1

        if nx.has_path(graph, source=SUPERSOURCE, target=demand_id):
            demand_with_disjoint_paths.add(demand_id)

        # Recover the graph back to initial version
        for n in range(1, end):
            graph.add_edge(
                shortest_path[n], shortest_path[n + 1], link_id=link_ids[n - 1]
            )
    return DisjointPath(
        demand_with_disjoint_paths=demand_with_disjoint_paths,
        disconnected_demand_locations=disconnected_demand_locations,
        demand_connected_to_pop=demand_connected_to_pop,
    )
