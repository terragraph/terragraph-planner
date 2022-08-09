# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import math
import time
from typing import Dict, Optional, Set, Tuple

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import SiteType
from terragraph_planner.common.exceptions import (
    OptimizerException,
    planner_assert,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.constants import (
    DEMAND,
    EPSILON,
    IMAGINARY_SECTOR_TYPES,
    IMAGINARY_SITE_TYPES,
    UNASSIGNED_CHANNEL,
)
from terragraph_planner.optimization.ilp_models.network_optimization import (
    NetworkOptimization,
)
from terragraph_planner.optimization.structs import OptimizationSolution

logger: logging.Logger = logging.getLogger(__name__)


class SiteOptimization(NetworkOptimization):
    def __init__(
        self,
        topology: Topology,
        params: OptimizerParams,
        adversarial_links: Set[Tuple[str, str]],
    ) -> None:
        super(SiteOptimization, self).__init__(topology, params)
        self.number_of_channels = 1  # Disable multi-channel
        self.adversarial_links = adversarial_links
        if self.params.maximize_common_bandwidth:
            self.connected_demand_sites: Set[
                str
            ] = self._compute_connectable_demand_sites()

    def _compute_connectable_demand_sites(self) -> Set[str]:
        if self.params.ignore_polarities:
            connected_demand_sites = (
                self._get_reachable_demand_sites_without_constraints()
            )
        else:
            connected_demand_sites = (
                self._get_reachable_demand_sites_with_constraints()
            )
            if connected_demand_sites is None:
                logger.info(
                    "Polarity constrained connected demand sites were not found"
                )
                # Get the connected demand sites without polarity constraints instead
                connected_demand_sites = (
                    self._get_reachable_demand_sites_without_constraints()
                )

        logger.info(
            f"Number of connected demand sites = {len(connected_demand_sites)}"
        )
        return connected_demand_sites

    def _get_ignore_links(self) -> Set[Tuple[str, str]]:
        """
        Add adversarial links to the ignored links.
        """
        ignore_links = super(SiteOptimization, self)._get_ignore_links()
        # Reachable demand sites cannot be connected through adversarial links
        for link in self.links:
            if link in self.adversarial_links:
                ignore_links.add(link)
        return ignore_links

    def _get_ignore_sites(self) -> Set[str]:
        """
        If any of the co-located sites are active, then the colocated site
        constraint will prevent any of the others from being selected. Add
        those other sites to the ignored sites.
        """
        ignore_sites = super(SiteOptimization, self)._get_ignore_sites()

        input_active_sites = self.proposed_sites | self.existing_sites
        for locs in self.colocated_locations.values():
            active_colocated_sites = input_active_sites.intersection(set(locs))
            if len(active_colocated_sites) == 0:
                continue
            (
                max_site_type,
                valid_site_types,
            ) = self._get_max_and_valid_site_types_from_colocated_sites(
                active_colocated_sites
            )
            for loc in locs:
                if self.location_to_type[loc] not in valid_site_types or (
                    self.location_to_type[loc] == max_site_type
                    and loc not in input_active_sites
                ):
                    ignore_sites.add(loc)

        return ignore_sites

    def set_up_problem_skeleton(
        self,
        rel_stop: float,
        max_time: float,
    ) -> None:
        """
        Create and add all the common variables and constraints that are used
        in all versions of the coverage problem (i.e. cost minimization wrt a
        coverage threshold, coverage maximization wrt a budget or coverage
        maximization wrt a POP limit.
        """
        # Set up the model parameters such us time limit and relative stop
        # tolerance and create problem.
        self.create_model(rel_stop=rel_stop, max_time=max_time)

        # Create decision variables
        self.create_site_decisions()
        self.create_sector_decisions()
        self.create_flow_decisions()
        self.create_tdm_decisions()
        self.create_shortage_decisions()
        self.create_polarity_decisions()

        # Create constraints
        self.create_colocated_site_relationship()
        self.create_tdm_flow_relationship()
        self.create_tdm_sector_relationship()
        self.create_pop_load_constraints()
        self.create_flow_balance_with_shortage()
        self.create_flow_site_relationship()
        self.create_adversarial_restrictions()
        self.create_tdm_polarity_relationship()
        self.create_fixed_input_constraints_without_sectors()

    def create_sector_decisions(self) -> None:
        """
        Create sector decision variables. In site optimization, the sector
        decision is the same as the corresponding site decision.
        """
        self.sector_vars = {
            (i, a, 0): self.site_vars[i]
            for i in self.location_sectors
            for a in self.location_sectors[i]
            if self.sector_to_type[a] not in IMAGINARY_SECTOR_TYPES
        }

    def add_cost_constraint_coverage_objective(self) -> None:
        """
        Find the maximum coverage network that has a construction cost below
        a given budget value.
        """
        # Ensure that the total cost of deployment is below a budget
        self.create_cost_constraint()
        # Create maximum coverage objective function
        self.create_coverage_objective()

    def add_coverage_constraint_cost_objective(self) -> None:
        """
        Find the minimum-cost network that covers at least a given ratio
        of the total demand.
        """
        # Ensure that a minimum percentage of demand is covered
        self.create_coverage_constraint()
        # Create minimum cost objective function
        self.create_cost_objective()

    def create_adversarial_restrictions(self) -> None:
        # Restrict the flow on "important edges" to be zero
        for link in self.links:
            if link in self.adversarial_links:
                self.problem.addConstraint(self.flow[link] == 0)

    def _compatible_polarity(
        self, loc1: str, loc2: str, odd_site_decisions: Dict[str, int]
    ) -> bool:
        """
        Returns False if loc1 and loc2 cannot communicate due to
        polarity reasons.

        If sites loc1 and loc2 are both DN/POP site locations, then
        at most one of them can be even (or odd) for them to be able to
        communicate.

        If they are not DN/POP sites, polarity is irrelevant is assumed to
        have no affect on the communication.
        """
        if ((loc1, loc2) in self.existing_links | self.proposed_links) or (
            (loc1, loc2) in self.wired_links
        ):
            # If the link (loc1, loc2) was set to be active by the user
            # initially OR
            # if it is a wired link
            # then it will dominate the polarities being compatible
            return True

        elif (
            self.location_to_type[loc1] in SiteType.dist_site_types()
            and self.location_to_type[loc2] in SiteType.dist_site_types()
        ):
            return odd_site_decisions.get(loc1, 0) != odd_site_decisions.get(
                loc2, 0
            )
        else:
            # If loc1 and loc2 are not both DN/POP sites,
            # then polarity does not matter.
            return True

    def get_sector_decisions_from_sites(
        self, site_decisions: Dict[str, int]
    ) -> Dict[Tuple[str, str], int]:
        """
        Extract the decisions on sectors with binary values from the
        solution vector.
        """
        sector_decisions = {}
        for loc in self.locations:
            if self.location_to_type[loc] in IMAGINARY_SITE_TYPES:
                continue
            for sec in self.location_sectors[loc]:
                if self.sector_to_type[sec] in IMAGINARY_SECTOR_TYPES:
                    continue
                sector_decisions[(loc, sec)] = site_decisions[loc]
        return sector_decisions

    def get_link_decisions_from_sectors_and_polarity(
        self,
        site_decisions: Dict[str, int],
        odd_site_decisions: Optional[Dict[str, int]],
        sector_decisions: Dict[Tuple[str, str], int],
    ) -> Dict[Tuple[str, str], int]:
        """
        In the optimization models except the deployment optimization,
        we do not explicitly make link decisions. Rather, we use sectors
        to infer whether a link is active or not.

        This function extracts the link statuses in the topology using
        the statuses of the sectors that create it.

        For example, suppose a link between sites i and j is achieved via
        sectors a and b. If sectors a and b both have active statuses, then
        link (i, j) is also active. Otherwise; it is not.
        """
        link_decisions = {(i, j): 0 for (i, j) in self.links}
        for (loc1, loc2) in self.links:
            if (
                self.location_to_type[loc1] in IMAGINARY_SITE_TYPES
                or self.location_to_type[loc2] in IMAGINARY_SITE_TYPES
            ):
                continue
            if (loc1, loc2) in self.inactive_links or self.link_capacities[
                (loc1, loc2)
            ] <= 0:
                continue  # may cause trouble during sector lookup
            compatible_polarities = (
                odd_site_decisions is None
                or self._compatible_polarity(loc1, loc2, odd_site_decisions)
            )
            if compatible_polarities and all(
                site_decisions[i] == 1 for i in {loc1, loc2}
            ):
                if (loc1, loc2) in self.wired_links:
                    link_decisions[(loc1, loc2)] = 1
                    continue

                (sector1, sector2) = self.link_to_sectors.get(
                    (loc1, loc2), (None, None)
                )
                planner_assert(
                    sector1 is not None and sector2 is not None,
                    f"No sector found for link {loc1}-{loc2}",
                    OptimizerException,
                )
                sector1_decision = sector_decisions.get(
                    (loc1, none_throws(sector1)), 0
                )
                sector2_decision = sector_decisions.get(
                    (loc2, none_throws(sector2)), 0
                )
                link_decisions[(loc1, loc2)] = (
                    1 if sector1_decision + sector2_decision == 2 else 0
                )

        return link_decisions

    def extract_solution(self) -> Optional[OptimizationSolution]:
        """
        This function extracts the decisions from xpress variables and
        returns an OptimizationSolution consisting of site, sector, link,
        flow, polarity decisions and the objective function value.
        """
        ignore_polarities = self.params.ignore_polarities

        # If at least one MIP solution is found, then extract it.
        if self.problem.attributes.mipsols > 0:
            solution_vector = self.problem.getSolution()
            site_decisions = self._extract_flat_dictionary(
                solution_vector, self.site_vars
            )
            odd_site_decisions = (
                self._extract_flat_dictionary(solution_vector, self.odd)
                if not ignore_polarities
                else {}
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
            flow_decisions = self.prune_loops(flow_decisions)
            if math.isclose(sum(flow_decisions.values()), 0, abs_tol=EPSILON):
                planner_assert(
                    self.common_bandwidth is None
                    or solution_vector[
                        self.problem.getIndex(self.common_bandwidth)
                    ]
                    == 0,
                    "No flow in solution, but common bandwidth is positive",
                    OptimizerException,
                )
                logger.info("No flow in solution -- assuming to be degenerate.")
                return None

            # If a site has no incoming or outgoing flow and is not a proposed
            # or existing site, but is selected by the optimizer, then the
            # decision did not impact feasibility or the optimal value.
            # Therefore, such sites should be deselected. Note: even if
            # always_active_pops is enabled, POPs without flow will be
            # deselected because all of their neighbors will be deselected and
            # that POP will be isolated from the network
            forced_active_sites = self.proposed_sites | self.existing_sites
            for (i, j) in self.proposed_links | self.existing_links:
                forced_active_sites.add(i)
                forced_active_sites.add(j)

            for loc in self.locations:
                if self.location_to_type[loc] in IMAGINARY_SITE_TYPES:
                    continue
                if site_decisions[loc] == 0 or loc in forced_active_sites:
                    continue
                incoming_flow = sum(
                    flow_decisions[link] for link in self.incoming_links[loc]
                )
                outgoing_flow = sum(
                    flow_decisions[link] for link in self.outgoing_links[loc]
                )
                if math.isclose(
                    incoming_flow, 0, abs_tol=EPSILON
                ) and math.isclose(outgoing_flow, 0, abs_tol=EPSILON):
                    site_decisions[loc] = 0
                    if not ignore_polarities:
                        even_site_decisions[loc] = 0
                        odd_site_decisions[loc] = 0

            # We call this function from cost and coverage optimization
            # problems, where the sector decisions are assumed to
            # be the same as the site decisions.
            sector_decisions = self.get_sector_decisions_from_sites(
                site_decisions
            )
            channel_decisions = {
                sector_key: 0 if decision == 1 else UNASSIGNED_CHANNEL
                for sector_key, decision in sector_decisions.items()
            }
            link_decisions = self.get_link_decisions_from_sectors_and_polarity(
                site_decisions,
                odd_site_decisions if not ignore_polarities else None,
                sector_decisions,
            )

            sectors_with_active_links = self.get_sectors_with_active_links(
                link_decisions
            )
            sites_with_active_links = self.get_sites_with_active_links(
                link_decisions
            )
            # POPs directly connected to demand are still active
            for (loc1, loc2) in self.links:
                if (
                    self.location_to_type[loc2] == DEMAND
                    and site_decisions[loc1] == 1
                ):
                    sites_with_active_links.add(loc1)

            # If the location was forced to be active, but it is not used for
            # any connections/sectors, then assume that the location is inactive
            for loc in self.locations:
                if self.location_to_type[loc] in IMAGINARY_SITE_TYPES:
                    continue
                if loc not in sites_with_active_links:
                    site_decisions[loc] = 0
                    if not ignore_polarities:
                        odd_site_decisions[loc] = 0
                        even_site_decisions[loc] = 0
                for sec in self.location_sectors[loc]:
                    if self.sector_to_type[sec] in IMAGINARY_SECTOR_TYPES:
                        continue
                    if sec not in sectors_with_active_links.get(loc, set()):
                        sector_decisions[(loc, sec)] = 0

            tdm_channel_decisions = self._extract_flat_dictionary(
                solution_vector, self.tdm, binary=False
            )
            tdm_decisions = {}
            for (i, j, c), decision in tdm_channel_decisions.items():
                planner_assert(
                    c == 0,
                    "Site optimization does not make channel decisions",
                    OptimizerException,
                )
                tdm_decisions[(i, j)] = decision

            shortage_decisions = self._extract_flat_dictionary(
                solution_vector, self.shortage, binary=False
            )

            # None check here is necessary because this code is common to both
            # min cost and max coverage. Thus, checking the parameter that
            # controls the coverage cost function is not sufficient.
            if self.common_bandwidth is not None:
                common_bandwidth = solution_vector[
                    self.problem.getIndex(self.common_bandwidth)
                ]
                logger.info(f"Common bandwidth = {common_bandwidth}")
                if common_bandwidth == 0:
                    logger.warning(
                        "No common bandwidth found; consider maximizing total network bandwidth"
                    )

            cost = self._extract_cost(site_decisions, sector_decisions)

            return OptimizationSolution(
                site_decisions=site_decisions,
                sector_decisions=sector_decisions,
                link_decisions=link_decisions,
                odd_site_decisions=odd_site_decisions,
                even_site_decisions=even_site_decisions,
                channel_decisions=channel_decisions,
                tdm_decisions=tdm_decisions,
                flow_decisions=flow_decisions,
                shortage_decisions=shortage_decisions,
                objective_value=self.problem.getObjVal(),
                cost=cost,
            )
        logger.info("No solution was found.")
        return None

    # Demand Site Optimization Functions
    def build_connected_demand_model(self) -> None:
        """
        Build demand site optimization model
        """
        logger.info("Constructing the demand site optimization model.")
        start_time = time.time()
        self.create_connected_demand_model(
            max_time=self.params.demand_site_max_time
        )

        self.create_unit_flow_decisions()
        self.create_polarity_decisions()
        self.create_demand_site_decisions()

        self.create_ignore_link_flow_constraints()
        self.create_tdm_polarity_relationship()
        self.create_active_link_polarity_constraints()
        self.create_unit_flow_balance_constraints()

        self.create_demand_site_objective()
        end_time = time.time()
        logger.info(
            "Time to construct the demand site optimization model: "
            f"{end_time - start_time:0.2f} seconds."
        )

    def create_unit_flow_decisions(self) -> None:
        """
        Create "unit" flow decision variables. Assign tdm to be the same as
        flow for easier code re-use (e.g., create_tdm_polarity_relationship)
        """
        super(SiteOptimization, self).create_unit_flow_decisions()
        self.tdm = {(i, j, 0): self.flow[(i, j)] for (i, j) in self.flow}

    def reset_connected_demand_model(self) -> None:
        self.problem.reset()
        self.site_vars = None
        self.flow = None
        self.tdm = None
        self.odd = None
        self.demand_vars = None
