# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import time
from typing import Optional, Set, Tuple

import xpress as xp

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import (
    DebugFile,
    SiteType,
    StatusType,
)
from terragraph_planner.common.exceptions import (
    OptimizerException,
    planner_assert,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.constants import (
    DEMAND,
    IMAGINARY_SECTOR_TYPES,
    IMAGINARY_SITE_TYPES,
    SUPERSOURCE,
)
from terragraph_planner.optimization.ilp_models.network_optimization import (
    NetworkOptimization,
)
from terragraph_planner.optimization.structs import FlowSolution

logger: logging.Logger = logging.getLogger(__name__)

# See the status correspondance to the integer values at:
# https://www.fico.com/fico-xpress-optimization/docs/latest/solver/
# optimizer/HTML/LPSTATUS.html
xpress_no_solution_statuses = {
    0: "unstarted",
    2: "infeasible",
    5: "unbounded",
    7: "numerical_issues",
    8: "nonlinear_problem",
}


class MaxFlowNetwork(NetworkOptimization):
    """
    Unlike our other optimization models, this model does not have any integer
    decision variables (i.e., it is a linear program). It is intended to be
    called after a candidate deployment topology is proposed.

    Inputs:
    Set of active sites, sectors, links and link capacities (throughputs).
    Note that this model does not decide on which sites/sectors to activate.
    For details on the rest of the inputs check out main_optimization.py.

    Constraints:
    For each demand site, guarantee an incoming flow of
    (default_demand + demand_buffer),
    where demand_buffer is a decision variable that can take negative values
    with a lower bound of -demand_value at that location.

    Objective:
    Not-relaxed version:
    Maximize the additional bandwidth that can be supported at all demand
    locations. When the maximum flow objective is used, the buffer value stays
    at zero because of the way flow balance constraints are formed.
    """

    def __init__(self, topology: Topology, params: OptimizerParams) -> None:
        super(MaxFlowNetwork, self).__init__(topology, params)
        self.number_of_channels = 1

        # Only use the sites/links that have an active status type.
        # By adding sites/links that are of candidate status type, we ensure
        # that the flow on into/from any site and on any link that is not
        # active to be zero.
        self.inactive_sites.update(
            self.topology.get_site_ids(status_filter={StatusType.CANDIDATE})
        )
        self.inactive_links.update(
            self.topology.get_link_site_id_pairs(
                status_filter={StatusType.CANDIDATE}
            )
        )

        # Max throughput represents a large bound on the flow value on all links
        self.max_throughput: float = (
            len(self.type_sets[SiteType.POP]) * self.params.pop_capacity
        )

        # Flow optimization does not make decisions on sites or links, so
        # reachable demand sites are those that can be reached on the
        # underlying active/proposed graph.
        self.connected_demand_sites: Set[
            str
        ] = self._get_reachable_demand_sites_without_constraints(
            status_filter=StatusType.active_status()
        )

        # Variables created when building the optimization model
        self.buffer_var = None  # pyre-fixme

        for link in self.topology.links.values():
            tx_site_id = link.tx_site.site_id
            rx_site_id = link.rx_site.site_id
            # Set redundant links to 0 capacity
            self.link_capacities[(tx_site_id, rx_site_id)] = (
                0 if link.is_redundant else link.capacity
            )

    def _get_ignore_links(self) -> Set[Tuple[str, str]]:
        ignore_links = super(MaxFlowNetwork, self)._get_ignore_links()
        for link in self.topology.links.values():
            tx_site_id = link.tx_site.site_id
            rx_site_id = link.rx_site.site_id
            if link.is_redundant:
                ignore_links.add((tx_site_id, rx_site_id))
        return ignore_links

    def set_up_problem_skeleton(self) -> None:
        # Use Xpress default rel stop and set max time to 60 min which should
        # be overkill for LP problems
        self.create_model(rel_stop=-1, max_time=60)
        self.create_site_decisions()
        self.create_sector_decisions()
        self.create_flow_decisions()
        self.create_tdm_decisions()
        self.create_tdm_sector_relationship()
        self.create_tdm_flow_relationship()
        self.create_flow_site_relationship()
        self.create_inactive_link_flow_constraints()
        self.create_pop_load_constraints()

        self.create_buffer_var()
        self.create_flow_balance_with_buffer()
        self.create_maximum_buffer_objective()

    def solve(self) -> Optional[FlowSolution]:
        logger.info("Finding common buffer post-design flow-route.")
        start_time = time.time()
        self.set_up_problem_skeleton()
        end_time = time.time()
        logger.info(
            "Time to construct the common buffer optimization model: "
            f"{end_time - start_time:0.2f} seconds."
        )

        self.dump_problem_file_for_debug_mode(
            DebugFile.COMMON_BUFFER_OPTIMIZATION
        )

        logger.info("Solving common buffer optimization")
        start_time = time.time()
        self.problem.solve()
        end_time = time.time()
        logger.info(
            "Time to solve the common buffer optimization: "
            f"{end_time - start_time:0.2f} seconds."
        )

        logger.info("Extracting common buffer solution")
        start_time = time.time()
        solution = self.extract_flow_solution()
        end_time = time.time()
        logger.info(
            "Time for extracting common buffer solution: "
            f"{end_time - start_time:0.2f} seconds."
        )
        return solution

    def create_site_decisions(self) -> None:
        # Note: demand and supersource sites can be assumed to be active
        active_sites = self.proposed_sites | self.existing_sites
        self.site_vars = {
            loc: 1 if loc in active_sites else 0
            for loc in self.locations
            if self.location_to_type[loc] not in IMAGINARY_SITE_TYPES
        }

    def create_sector_decisions(self) -> None:
        self.sector_vars = {
            (loc, sec, 0): 1
            if sec in self.proposed_sectors.get(loc, set())
            else 0
            for loc in self.locations
            for sec in self.location_sectors[loc]
            if self.sector_to_type[sec] not in IMAGINARY_SECTOR_TYPES
        }

    def create_maximum_buffer_objective(self) -> None:
        self.problem.setObjective(
            self.buffer_var, sense=xp.maximize  # pyre-ignore
        )

    def create_buffer_var(self) -> None:
        """
        Create buffer variable indicating the identical amount of data
        throughput at all demand sites.
        """
        self.buffer_var = xp.var(  # pyre-ignore
            name="buffer", vartype=xp.continuous, lb=0  # pyre-ignore
        )

        self.problem.addVariable(self.buffer_var)

    def create_flow_balance_with_buffer(self) -> None:
        """
        Flow balance constraints with a buffer variable
        If the site is a DN or a POP site:
        net_flow == 0
        If the site is the SUPERSOURCE:
        net_flow <= -sum_of_all_connected_demand which implies
        outgoing_flow >= sum_of_all_connected_demand
        If the site is a demand site:
        net_flow_i >= demand_i + common_demand_buffer
        """
        for loc in self.locations:
            # Net flow on location loc1
            net_flow = self._get_net_flow(loc)
            # If net_flow is None, then flow balance is irrelevant
            if net_flow is not None:
                if self.location_to_type[loc] == DEMAND:
                    rhs = (
                        self.buffer_var
                        if loc in self.connected_demand_sites
                        else 0
                    )
                    self.problem.addConstraint(net_flow == rhs)
                elif self.location_to_type[loc] == SUPERSOURCE:
                    self.problem.addConstraint(net_flow <= 0)
                else:
                    self.problem.addConstraint(net_flow == 0)

    def extract_flow_solution(self) -> Optional[FlowSolution]:
        # If the problem is neither infeasible nor unbounded, then
        # extract the solution

        if self.problem.attributes.lpstatus in xpress_no_solution_statuses:
            logger.info("No solution was found.")
            logger.info(f"Status is {self.problem.attributes.lpstatus}")
            return None

        solution = self.problem.getSolution()
        buffer_decision = solution[self.problem.getIndex(self.buffer_var)]
        logger.info(f"Common bandwidth = {buffer_decision}")

        flow_decisions = self._extract_flat_dictionary(
            solution, self.flow, binary=False
        )

        flow_decisions = self.prune_loops(flow_decisions)
        tdm_channel_decisions = self._extract_flat_dictionary(
            solution, self.tdm, binary=False
        )
        tdm_decisions = {}
        for (i, j, c), decision in tdm_channel_decisions.items():
            planner_assert(
                c == 0,
                "Flow optimization should not have channel decisions",
                OptimizerException,
            )
            tdm_decisions[(i, j)] = decision

        return FlowSolution(
            flow_decisions=flow_decisions,
            tdm_decisions=tdm_decisions,
            buffer_decision=buffer_decision,
            connected_demand_sites=self.connected_demand_sites,
        )
