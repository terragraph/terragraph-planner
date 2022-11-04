# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import logging
import math
import time
from itertools import product
from typing import Any, List, Optional, Set, Tuple

import networkx as nx
import numpy as np
import xpress as xp
from scipy.spatial import Delaunay

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import (
    DebugFile,
    PolarityType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.exceptions import (
    OptimizerException,
    planner_assert,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.constants import (
    EPSILON,
    IMAGINARY_SECTOR_TYPES,
    IMAGINARY_SITE_TYPES,
    SUPERSOURCE,
    UNASSIGNED_CHANNEL,
)
from terragraph_planner.optimization.ilp_models.site_optimization import (
    SiteOptimization,
)
from terragraph_planner.optimization.structs import (
    RedundancyParams,
    RedundancySolution,
)

logger: logging.Logger = logging.getLogger(__name__)


class RedundantNetwork(SiteOptimization):
    """
    Given a base backhaul network (POPs and DNs), find additional DNs with the
    smallest construction cost that satisfy the desired redundancy for the base
    backhaul network. This redundancy is a combination of several parameters
    which indicate the number of simultaneous link, DN and/or POP failures that
    the network is resilient to.

    The input topology can include the CNs and demand sites but those will be
    ignored for the purpose of building redundancy in the backhaul.
    """

    def __init__(
        self,
        topology: Topology,
        params: OptimizerParams,
        redundancy_params: RedundancyParams,
        restricted_links: Optional[Set[Tuple[str, str]]] = None,
    ) -> None:
        # Maximize common bandwidth is not relevant for redundancy
        # Set to false for site optimization initialization
        maximize_common_bandwidth = params.maximize_common_bandwidth
        params.maximize_common_bandwidth = False

        super(RedundantNetwork, self).__init__(topology, params, set())

        # Restore parameter value
        params.maximize_common_bandwidth = maximize_common_bandwidth

        # Collect all the DNs for which redundancy is being built
        self.dns: List[str] = [
            loc
            for loc in self.locations
            if (loc in self.proposed_sites or loc in self.existing_sites)
            and self.location_to_type[loc] == SiteType.DN
        ]

        # Limit topology to just the backhaul; apply further restriction if
        # requested (e.g., from some heuristic used to make ILP smaller)
        super_dist_site_types = SiteType.dist_site_types() | {SUPERSOURCE}
        self.restricted_links: Set[Tuple[str, str]] = {
            (i, j)
            for (i, j) in self.links
            if self.link_capacities[(i, j)] > 0
            and self.location_to_type[i] in super_dist_site_types
            and self.location_to_type[j] in super_dist_site_types
            and (
                restricted_links is None
                or i == SUPERSOURCE
                or j == SUPERSOURCE
                or (i, j) in restricted_links
            )
        }
        self.restricted_sites: Set[str] = {
            loc for link in self.restricted_links for loc in link
        }
        planner_assert(
            set(self.dns).issubset(self.restricted_sites),
            "Restricted sites must include all active DNs",
            OptimizerException,
        )

        # Variables created when building the optimization model
        self.problem = None  # pyre-fixme
        self.site_vars = None  # pyre-fixme
        self.odd = None  # pyre-fixme
        self.flow = None  # pyre-fixme
        self.shortage = None  # pyre-fixme

        # Parameters controlling redundancy
        self.pop_node_capacity: int = redundancy_params.pop_node_capacity
        self.dn_node_capacity: int = redundancy_params.dn_node_capacity
        self.sink_node_capacity: int = redundancy_params.sink_node_capacity

    def setup_problem_skeleton(self, shortage_decisions: bool) -> None:
        """
        Create and add all the common variables and constraints that are used
        in all versions of the problem.
        """
        # Set up the model parameters such us time limit and relative stop
        # tolerance and create problem.
        self.create_model(
            rel_stop=self.params.redundancy_rel_stop,
            max_time=self.params.redundancy_max_time,
        )

        # Create decision variables
        self.create_site_decisions()
        self.create_polarity_decisions()
        self.create_flow_decisions()
        if shortage_decisions:
            self.create_shortage_decisions()

        # Create constraints
        self.create_decided_site_constraints()
        self.create_inactive_link_flow_constraints()
        self.create_colocated_site_relationship()
        self.create_flow_site_relationship()
        self.create_flow_balance_with_shortage()
        self.create_flow_polarity_constraints()

    def create_site_decisions(self) -> None:
        """
        Decision variables for backhaul site selection.
        """
        self.site_vars = {
            loc: xp.var(name=f"site_{loc}", vartype=xp.binary)
            for loc in self.locations
            if loc in self.restricted_sites
            and self.location_to_type[loc] not in IMAGINARY_SITE_TYPES
        }
        self.problem.addVariable(self.site_vars)

    def create_polarity_decisions(self) -> None:
        """
        Decision variables for polarity
        """
        if self.params.ignore_polarities:
            return

        # A proposed site is either odd or even
        self.odd = {
            loc: xp.var(name=f"odd_{loc}", vartype=xp.binary)
            for loc in self.locations
            if loc in self.restricted_sites
            and self.location_to_type[loc] in SiteType.dist_site_types()
        }

        self.problem.addVariable(self.odd)

    def create_flow_decisions(self) -> None:
        """
        Decision variables for flow. For each base network DN (self.dns), there
        are flow decision variables for all the positive capacity links. That
        means for each base network DN, the network flow is determined. In
        other words, a series of network flow problems are being solved
        simultaneously.
        """
        self.flow = {
            (i, j, f): xp.var(
                name=f"flow_{i}_{j}_{f}",
                vartype=xp.continuous,
                lb=0,
                ub=self.pop_node_capacity
                if i == SUPERSOURCE or j == SUPERSOURCE
                else 1,
            )
            for f, (i, j) in product(self.dns, self.links)
            if (i, j) in self.restricted_links
        }
        self.problem.addVariable(self.flow)

    def create_shortage_decisions(self) -> None:
        """
        Decision variables for shortage. Each base network DN (self.dns) should
        have self.sink_node_capacity incoming flow, but if that cannot be
        achieved, self.shortage represents how much less than that flow is
        actually delivered.
        """
        self.shortage = {
            dn: xp.var(
                name=f"dn_{dn}",
                vartype=xp.continuous,
                lb=0,
                ub=self.sink_node_capacity,
            )
            for dn in self.dns
        }
        self.problem.addVariable(self.shortage)

    def create_decided_site_constraints(self) -> None:
        """
        Active input sites should remain active and inactive sites cannot be
        proposed. Extra POPs cannot be proposed.
        """
        for loc in self.locations:
            if loc not in self.restricted_sites:
                continue
            if loc in self.proposed_sites or loc in self.existing_sites:
                # Note: this includes all self.dns
                self.problem.addConstraint(self.site_vars[loc] == 1)
            elif loc in self.inactive_sites:
                self.problem.addConstraint(self.site_vars[loc] == 0)
            elif loc in self.type_sets[SiteType.POP]:
                # If POP is not proposed/existing, don't let it become so.
                # Note: earlier proposed/existing site case took care of those POPs
                self.problem.addConstraint(self.site_vars[loc] == 0)

    def create_inactive_link_flow_constraints(self) -> None:
        """
        No flow is allowed on inactive links.
        """
        for (i, j) in self.links:
            if (i, j) not in self.restricted_links:
                continue

            if (i, j) in self.inactive_links:
                for dn in self.dns:
                    self.problem.addConstraint(self.flow[(i, j, dn)] == 0)

    def create_colocated_site_relationship(self) -> None:
        """
        For co-located DNs, only one of the DN types can be selected. If a POP
        is already active on the site, then no DN can be selected.
        """
        for locs in self.colocated_locations.values():
            # If the DN is co-located with an active POP, then only POP can be
            # selected due to create_decided_site_constraints. If POP is not
            # active, only one of the DNs can be selected
            dn_locs = [
                loc
                for loc in locs
                if self.location_to_type[loc] in SiteType.dist_site_types()
                and loc in self.site_vars
            ]
            if len(dn_locs) > 0:
                self.problem.addConstraint(
                    xp.Sum(self.site_vars[loc] for loc in dn_locs) <= 1
                )

    # pyre-fixme
    def _get_incoming_flow(self, loc: str, dn: str) -> Optional[Any]:
        """
        Returns the sum of flow variables of incoming links if they exist;
        otherwise, returns None.
        """
        incoming_dist_links = {
            link
            for link in self.incoming_links[loc]
            if link in self.restricted_links
        }

        incoming_flow = [
            self.flow[(i, j, dn)] for (i, j) in incoming_dist_links
        ]

        return xp.Sum(incoming_flow) if len(incoming_flow) > 0 else None

    # pyre-fixme
    def _get_outgoing_flow(self, loc: str, dn: str) -> Optional[Any]:
        """
        Returns the sum of flow variables of outgoing links if they exist;
        otherwise, returns None.
        """
        outgoing_dist_links = {
            link
            for link in self.outgoing_links[loc]
            if link in self.restricted_links
        }

        outgoing_flow = [
            self.flow[(i, j, dn)] for (i, j) in outgoing_dist_links
        ]

        return xp.Sum(outgoing_flow) if len(outgoing_flow) > 0 else None

    def create_flow_site_relationship(self) -> None:
        """
        No flow is allowed on a site that is not active. Total incoming flow to
        an active site is pop_node_capacity for POPs, dn_node_capacity for DNs
        and sink_node_capacity for DN sinks.
        """
        for loc in self.locations:
            if loc not in self.restricted_sites:
                continue

            for dn in self.dns:
                cap = (
                    self.pop_node_capacity
                    if self.location_to_type[loc] == SiteType.POP
                    else self.sink_node_capacity
                    if loc == dn
                    else self.dn_node_capacity
                )

                incoming_flow = self._get_incoming_flow(loc, dn)
                if incoming_flow is not None:
                    self.problem.addConstraint(
                        incoming_flow <= cap * self.site_vars[loc]
                    )

    def create_flow_balance_with_shortage(self) -> None:
        """
        Flow balance constraints: incoming flow and outgoing flow must be the
        same. The exceptions are to the supersource with sink_node_capacity
        minus shortage outgoing flow and to the DN sink with sink_node_capacity
        minus shortage incoming flow.
        """
        for loc in self.locations:
            if loc not in self.restricted_sites:
                continue
            for dn in self.dns:
                incoming_flow = self._get_incoming_flow(loc, dn)
                outgoing_flow = self._get_outgoing_flow(loc, dn)
                if incoming_flow is None and outgoing_flow is None:
                    continue
                incoming_flow = incoming_flow if incoming_flow else 0
                outgoing_flow = outgoing_flow if outgoing_flow else 0
                net_flow = incoming_flow - outgoing_flow
                if loc == SUPERSOURCE:
                    self.problem.addConstraint(
                        net_flow >= self.shortage[dn] - self.sink_node_capacity
                    )
                elif loc == dn:
                    self.problem.addConstraint(
                        net_flow >= self.sink_node_capacity - self.shortage[dn]
                    )
                else:
                    self.problem.addConstraint(net_flow == 0)

    def create_flow_polarity_constraints(self) -> None:
        """
        If the flow from one site to another is strictly larger than zero, then
        the polarity of the connected sites has to be opposite.
        """
        if self.params.ignore_polarities:
            return

        for (i, j) in self.links:
            if (i, j) not in self.restricted_links:
                continue

            if (i, j) in self.wired_links:
                continue

            # If a link should be active, then the end sites must be of
            # opposite polarities (partly because in case flow is 0 for such a
            # link, we still want the constraint to apply)
            if (i, j) in self.proposed_links or (i, j) in self.existing_links:
                self.problem.addConstraint(self.odd[i] == 1 - self.odd[j])
                continue

            for dn in self.dns:
                # If both are even, then flow <= odd_i + odd_j = 0
                # If both are odd, then flow <= 2 - odd_i - odd_j = 0
                # The second constraint is equivalent to
                # flow <= even_i + even_j
                self.problem.addConstraint(
                    self.flow[(i, j, dn)] <= self.odd[i] + self.odd[j]
                )
                self.problem.addConstraint(
                    self.flow[(i, j, dn)] <= 2 - self.odd[i] - self.odd[j]
                )

    def create_cost_objective(self) -> None:
        """
        Cost of the network given the site decisions (assumes all sectors are
        active on active sites). Existing sites are not included.
        """
        total_cost = 0
        for loc in self.locations:
            if (
                loc not in self.restricted_sites
                or self.location_to_type[loc] in IMAGINARY_SITE_TYPES
            ):
                continue

            if loc not in self.existing_sites:
                total_cost += (
                    self.cost_site[self.location_to_type[loc]]
                    * self.site_vars[loc]
                )
                for sec in self.location_sectors[loc]:
                    if self.sector_to_type[sec] in IMAGINARY_SECTOR_TYPES:
                        continue
                    total_cost += (
                        self.cost_sector[loc][sec] * self.site_vars[loc]
                    )

        self.problem.setObjective(total_cost, sense=xp.minimize)

    def create_shortage_objective(self) -> None:
        """
        Total shortage in the network.
        """
        self.problem.setObjective(xp.Sum(self.shortage), sense=xp.minimize)

    def shortage_solve(self) -> None:
        """
        Solve optimization problem to minimize shortage in the network.
        """
        logger.info("Constructing redundant min shortage optimization model.")
        start_time = time.time()
        self.setup_problem_skeleton(shortage_decisions=True)
        self.create_shortage_objective()
        end_time = time.time()
        logger.info(
            "Time to construct the redundant min shortage optimization model: "
            f"{end_time - start_time:0.2f} seconds."
        )

        self.dump_problem_file_for_debug_mode(
            DebugFile.REDUNDANT_MIN_SHORTAGE_OPTIMIZATION
        )

        logger.info("Solving redundant min shortage optimization")
        start_time = time.time()
        self.problem.solve()
        end_time = time.time()
        logger.info(
            "Time to solve the redundant min shortage optimization: "
            f"{end_time - start_time:0.2f} seconds."
        )

        logger.info("Extracting redundant min shortage solution")
        start_time = time.time()
        if self.problem.attributes.mipsols > 0:
            solution_vector = self.problem.getSolution()
            shortage_decisions = self._extract_flat_dictionary(
                solution_vector, self.shortage, binary=False
            )
            # Set shortage to decisions output for second solve
            self.shortage = shortage_decisions
        else:
            self.shortage = None
        end_time = time.time()
        logger.info(
            "Time for extracting redundant min shortage solution: "
            f"{end_time - start_time:0.2f} seconds."
        )

    def solve(self) -> Optional[RedundancySolution]:
        """
        Solve optimization problem to minimize network cost subject to
        desired redundancy constraints. In order to ensure those constraints
        can be satisfied (i.e., not infeasible), shortage is allowed where
        necessary to relax them (the total shortage is first minimized).
        """
        # Minimize total shortage
        self.shortage_solve()
        if self.shortage is None:
            logger.info("No redundancy shortage solution found.")
            return None

        # Minimize network cost
        logger.info("Constructing redundant min cost optimization model.")
        start_time = time.time()

        self.problem.reset()
        self.setup_problem_skeleton(shortage_decisions=False)

        self.create_cost_objective()
        end_time = time.time()
        logger.info(
            "Time to construct the redundant min cost optimization model: "
            f"{end_time - start_time:0.2f} seconds."
        )

        self.dump_problem_file_for_debug_mode(
            DebugFile.REDUNDANT_MIN_COST_OPTIMIZATION
        )

        logger.info("Solving redundant min cost optimization")
        start_time = time.time()
        self.problem.solve()
        end_time = time.time()
        logger.info(
            "Time to solve the redundant min cost optimization: "
            f"{end_time - start_time:0.2f} seconds."
        )

        logger.info("Extracting redundant min cost solution")
        start_time = time.time()
        solution = self.extract_redundancy_solution()
        end_time = time.time()
        logger.info(
            "Time for extracting redundant min cost solution: "
            f"{end_time - start_time:0.2f} seconds."
        )
        return solution

    def extract_redundancy_solution(self) -> Optional[RedundancySolution]:
        """
        Extract and process decisions from solved optimization problem.
        """
        if self.problem.attributes.mipsols == 0:
            logger.info("No solution was found.")
            return None

        # If at least one MIP solution is found, then extract it
        ignore_polarities = self.params.ignore_polarities

        solution_vector = self.problem.getSolution()
        site_decisions = self._extract_flat_dictionary(
            solution_vector, self.site_vars
        )

        forced_active_sites = self.proposed_sites | self.existing_sites
        for (i, j) in self.proposed_links | self.existing_links:
            forced_active_sites.add(i)
            forced_active_sites.add(j)

        for loc in self.locations:
            if self.location_to_type[loc] in IMAGINARY_SITE_TYPES:
                continue
            elif self.location_to_type[loc] == SiteType.CN:
                # Carry site decisions for CNs from input
                if loc in forced_active_sites:
                    # If CN was upgraded to a DN for redundancy, do not
                    # activate the CN
                    geoloc = self.location_to_geoloc[loc]
                    if len(self.colocated_locations.get(geoloc, [])) <= 1:
                        site_decisions[loc] = 1
                    else:
                        any_dn_active = False
                        for coloc in self.colocated_locations[geoloc]:
                            if (
                                self.location_to_type[coloc]
                                in SiteType.dist_site_types()
                                and coloc in site_decisions
                                and site_decisions[coloc] == 1
                            ):
                                any_dn_active = True
                                break
                        site_decisions[loc] = 0 if any_dn_active else 1
                else:
                    site_decisions[loc] = 0
            elif (
                self.location_to_type[loc] in SiteType.dist_site_types()
                and loc not in site_decisions
            ):
                # In this case, DN should not be in forced_active_sites because
                # if it was, it would be in self.dns; however, a POP that just
                # connects to demand sites might not be in the restricted sites
                site_decisions[loc] = 1 if loc in forced_active_sites else 0

        odd_site_decisions = (
            self._extract_flat_dictionary(solution_vector, self.odd)
            if not ignore_polarities
            else {}
        )
        if not ignore_polarities:
            for loc in self.locations:
                if (
                    self.location_to_type[loc] in SiteType.dist_site_types()
                    and loc not in odd_site_decisions
                ):
                    odd_site_decisions[loc] = (
                        1
                        if site_decisions[loc] == 1
                        and loc in self.site_polarities[PolarityType.ODD]
                        else 0
                    )

        even_site_decisions = {}
        for loc, decision in odd_site_decisions.items():
            if site_decisions[loc] == 0:
                odd_site_decisions[loc] = 0
                even_site_decisions[loc] = 0
            else:
                even_site_decisions[loc] = 1 - decision

        flow_decisions = self._extract_flat_dictionary(
            solution_vector, self.flow, binary=False
        )
        sector_decisions = self.get_sector_decisions_from_sites(site_decisions)
        channel_decisions = {
            sector_key: 0 if decision == 1 else UNASSIGNED_CHANNEL
            for sector_key, decision in sector_decisions.items()
        }
        link_decisions = self.get_link_decisions_from_sectors_and_polarity(
            site_decisions,
            odd_site_decisions if not ignore_polarities else None,
            sector_decisions,
        )

        cost = self._extract_cost(site_decisions, sector_decisions)

        return RedundancySolution(
            site_decisions=site_decisions,
            sector_decisions=sector_decisions,
            link_decisions=link_decisions,
            odd_site_decisions=odd_site_decisions,
            even_site_decisions=even_site_decisions,
            channel_decisions=channel_decisions,
            flow_decisions=flow_decisions,
            shortage_decisions=self.shortage,
            objective_value=self.problem.getObjVal(),
            cost=cost,
        )


def compute_candidate_edges_for_redundancy(
    topology: Topology,
    pop_source_capacity: float,
    dn_source_capacity: float,
) -> Set[Tuple[str, str]]:
    """
    Use a heuristic approach to find a sub-topology of a base topology to be
    used for Redundancy Optimization. The approach is to use maximum flow
    calculations between various sources and sinks to identify edges that are
    most likely to be useful for building redundancy. More specifically, by
    splitting each node into a node with the incoming edges and a node with
    outgoing edges with a single edge of unit capacity between them, maximum
    flow provides the node-disjoint paths between the source and the sink. The
    number of such paths is the capacity of the source.

    Given a base backhaul network (POPs and DNs), in this heuristic, there are
    two rounds of maximum flow calculations. The first is between each POP in
    the base network and each DN in the base network. The second is between
    each of the DNs in the base network. Any edge that appears in the maximum
    flow output is added to the edges of the sub-topology.

    The second round can sometimes be expensive because there are O(n^2)
    maximum flow calculations. To accelerate this, a Delaunay triangulation
    is done among the DNs (using their geographic locations). In this case,
    the maximum flow calculations are performed only between DNs that are
    within one or two hops in the triangulation. The general idea is that as
    long as DNs nearby have multiple disjoint paths, far away DNs will as well.
    Two hops are included to help account for polarity constraints.

    @param topology: base topology on which redundancy will be built
    @param pop_source_capacity: number of node disjoint paths to be found
        between each POP in the base network and each DN in the base network
    @param dn_source_capacity: number of node disjoint paths to be found
        between each of the DNs in the base network
    @returns: set of edges of the sub-topology
    """

    def _get_node_in(node_id: str) -> Tuple[str, str]:
        return ("_in", node_id)

    def _get_node_out(node_id: str) -> Tuple[str, str]:
        return ("_out", node_id)

    G = nx.DiGraph()
    for site_id, site in topology.sites.items():
        if site.status_type in StatusType.inactive_status():
            continue

        if site.site_type not in SiteType.dist_site_types():
            continue

        # For node-disjoint paths, each node is split into an incoming edges
        # node and a outgoing edges node with a single edge of unit capacity
        # between them (except for POPs with pop_source_capacity)
        G.add_edge(
            _get_node_in(site_id),
            _get_node_out(site_id),
            capacity=pop_source_capacity
            if site.site_type == SiteType.POP
            else 1.0,
        )
        if site.site_type == SiteType.POP:
            G.add_edge(
                SUPERSOURCE, _get_node_in(site_id), capacity=pop_source_capacity
            )

    for link in topology.links.values():
        if link.status_type in StatusType.inactive_status():
            continue
        if link.capacity <= 0:
            continue

        tx_site = link.tx_site
        rx_site = link.rx_site
        if (
            tx_site.status_type in StatusType.inactive_status()
            or rx_site.status_type in StatusType.inactive_status()
        ):
            continue
        if (
            tx_site.site_type not in SiteType.dist_site_types()
            or rx_site.site_type not in SiteType.dist_site_types()
        ):
            continue

        # Add edge from outgoing tx node to incoming rx node
        G.add_edge(
            _get_node_out(tx_site.site_id),
            _get_node_in(rx_site.site_id),
            capacity=1.0,
        )

    # Do not use topology.get_site_ids() since order of the site ids may matter
    # Dictionaries maintain order while sets do not
    pops = [
        site_id
        for site_id, site in topology.sites.items()
        if site.site_type == SiteType.POP
        and site.status_type in StatusType.active_status()
    ]
    dns = [
        site_id
        for site_id, site in topology.sites.items()
        if site.site_type == SiteType.DN
        and site.status_type in StatusType.active_status()
    ]

    edges = set()

    # Compute max flow from each POP to each DN
    # Edges used in max flow are added to the candidate edges
    if pop_source_capacity > 0:
        logger.info("Computing disjoint paths from POP")
        for (i, dn) in enumerate(dns):
            for pop in pops:
                for other in pops:
                    G[SUPERSOURCE][_get_node_in(other)]["capacity"] = (
                        pop_source_capacity if pop == other else 0.0
                    )
                f, D = nx.maximum_flow(G, SUPERSOURCE, _get_node_in(dn))
                planner_assert(
                    f <= pop_source_capacity,
                    f"Max flow {f} should not be greater than than {pop_source_capacity}",
                    OptimizerException,
                )
                for u in D:
                    for v, f in D[u].items():
                        if (
                            f > EPSILON
                            and u[1] != v[1]
                            and SUPERSOURCE not in {u, v}
                        ):
                            planner_assert(
                                topology.get_link_by_site_ids(u[1], v[1])
                                is not None,
                                f"Link ({u[1]}, {v[1]}) is not in the topology",
                                OptimizerException,
                            )
                            edges.add((u[1], v[1]))
            if i + 1 in {
                math.ceil(p * len(dns)) for p in [0.25, 0.5, 0.75, 1.0]
            }:
                logger.info(f"{i+1}/{len(dns)} DNs processed")

        # Restore pop capacity
        for pop in pops:
            G[SUPERSOURCE][_get_node_in(pop)]["capacity"] = pop_source_capacity

    # Compute max flow from each DN to each other DN it is connected to in the
    # Delaunay triangulation
    # Edges used in max flow are added to the candidate edges
    if dn_source_capacity > 0:
        logger.info("Computing disjoint paths between DNs")

        B = G.copy()
        B.remove_node(SUPERSOURCE)

        is_symmetric = all(
            B.has_edge(_get_node_out(v[1]), _get_node_in(u[1]))
            for u, v in B.edges()
            if u[1] != v[1]
        )
        logger.info(f"Graph is symmetric: {is_symmetric}")

        delaunay_edges = set()
        if len(dns) > 2:
            # Compute Delaunay triangulation (in 2D space)
            # Note: two proposed DNs with the same lat/lon should not occur
            tri = Delaunay(
                np.array(
                    [
                        [
                            topology.sites[dn].latitude,
                            topology.sites[dn].longitude,
                        ]
                        for dn in dns
                    ]
                )
            )

            # Build graph from Delaunay triangulation
            delaunay_graph = nx.Graph()
            for T in tri.simplices:
                nx.add_cycle(delaunay_graph, T)

            # Pair vertices together that are one hop or two hops away in
            # Delaunay triangulation; if graph is symmetric, only add one of
            # the pairs
            for u in delaunay_graph.nodes():
                for v in nx.ego_graph(
                    delaunay_graph, u, center=False, radius=2
                ):
                    if not is_symmetric or u < v:
                        delaunay_edges.add((dns[u], dns[v]))

        elif len(dns) == 2:
            delaunay_edges = {(dns[0], dns[1])}
            if not is_symmetric:
                delaunay_edges.add((dns[1], dns[0]))

        for (i, (dn, other)) in enumerate(delaunay_edges):
            # Keep track of changes to undo at end of each iteration
            restore_capacities = {}

            # Form directed graph where source DN has no incoming edges of
            # positive capacity but is connected to the supersource with
            # dn_source_capacity; the supersource is detached from the POPs
            # but is connected to the DN directly
            for u, v, data in B.in_edges(_get_node_in(dn), data=True):
                restore_capacities[(u, v)] = data["capacity"]
                data["capacity"] = 0
            restore_capacities[_get_node_in(dn), _get_node_out(dn)] = B.edges[
                _get_node_in(dn), _get_node_out(dn)
            ]["capacity"]
            B.edges[_get_node_in(dn), _get_node_out(dn)][
                "capacity"
            ] = dn_source_capacity
            B.add_edge(
                SUPERSOURCE, _get_node_in(dn), capacity=dn_source_capacity
            )

            f, D = nx.maximum_flow(B, SUPERSOURCE, _get_node_in(other))
            planner_assert(
                f <= dn_source_capacity,
                f"Max flow {f} should not be greater than than {dn_source_capacity}",
                OptimizerException,
            )
            for u in D:
                for v, f in D[u].items():
                    if (
                        f > EPSILON
                        and u[1] != v[1]
                        and SUPERSOURCE not in {u, v}
                    ):
                        planner_assert(
                            topology.get_link_by_site_ids(u[1], v[1])
                            is not None,
                            f"Link ({u[1]}, {v[1]}) is not in the topology",
                            OptimizerException,
                        )
                        edges.add((u[1], v[1]))
                        if is_symmetric:
                            planner_assert(
                                topology.get_link_by_site_ids(v[1], u[1])
                                is not None,
                                f"Link ({v[1]}, {u[1]}) is not in the topology",
                                OptimizerException,
                            )
                            edges.add((v[1], u[1]))

            # Restore graph
            B.remove_node(SUPERSOURCE)
            for (u, v), capacity in restore_capacities.items():
                B.edges[u, v]["capacity"] = capacity

            if i + 1 in {
                math.ceil(p * len(delaunay_edges))
                for p in [0.25, 0.5, 0.75, 1.0]
            }:
                logger.info(
                    f"{i+1}/{len(delaunay_edges)} Delaunay DN pairs processed"
                )

    return edges
