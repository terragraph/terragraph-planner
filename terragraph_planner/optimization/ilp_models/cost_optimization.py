# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import time
from typing import Optional

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import DebugFile, StatusType
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.ilp_models.site_optimization import (
    SiteOptimization,
)
from terragraph_planner.optimization.structs import OptimizationSolution
from terragraph_planner.optimization.topology_operations import (
    compute_max_pop_capacity_of_topology,
)

logger: logging.Logger = logging.getLogger(__name__)


class MinCostNetwork(SiteOptimization):
    """
    Find the network design that has enough bandwidth to cover all the
    given demand requirements with smallest construction cost.
    The construction cost is computed as the total site and sector costs.
    In this model, we assume that all sectors on a site is active
    if and only if the site is active as well.
    """

    def __init__(self, topology: Topology, params: OptimizerParams) -> None:
        super(MinCostNetwork, self).__init__(topology, params, set())
        self.model_built = False

    def build_model(self) -> None:
        logger.info("Constructing the cost optimization model.")
        start_time = time.time()

        self.set_up_problem_skeleton(
            rel_stop=self.params.min_cost_rel_stop,
            max_time=self.params.min_cost_max_time,
        )

        self.add_coverage_constraint_cost_objective()
        self.model_built = True
        end_time = time.time()
        logger.info(
            "Time to construct the cost optimization model: "
            f"{end_time - start_time:0.2f} seconds."
        )

    def solve(
        self,
        coverage_percentage: float,
    ) -> Optional[OptimizationSolution]:
        """
        Solve for the minimum cost network subject to a specified coverage
        percentage.

        If the coverage percentage is not supplied, the value in params is
        used. However, if it is specified, the value in params is overwritten.
        This is useful, for example, in cases where the coverage percentage is
        dynamically determined by gradually decreasing the coverage percentage
        until a solution is found and allows for the problem to be solved
        without rebuilding the entire model which can be time-consuming.
        """
        self.params.coverage_percentage = coverage_percentage

        max_capacity = compute_max_pop_capacity_of_topology(
            topology=self.topology,
            pop_capacity=self.params.pop_capacity,
            status_filter=StatusType.reachable_status(),
        )
        if max_capacity < self.max_throughput * self.params.coverage_percentage:
            # The maximum capacity that the POPs can support is less than the
            # total demand in the area. Flow balance constraints can not be
            # satisfied.
            logger.info(
                "Exiting cost optimization early. Total POP capacity"
                + " cannot support the total demand."
            )
            return None

        if not self.model_built:
            self.build_model()
        else:
            try:
                # If model has already been built, do not rebuild all of it,
                # just delete the coverage constraint and re-add it with
                # updated coverage_percentage
                if self.coverage_constraint is not None:
                    self.problem.delConstraint(self.coverage_constraint)
                    self.create_coverage_constraint()
            except Exception:
                self.problem.reset()
                self.build_model()

        self.dump_problem_file_for_debug_mode(DebugFile.COST_OPTIMIZATION)

        logger.info("Solving cost optimization")
        start_time = time.time()
        self.problem.solve()
        end_time = time.time()
        logger.info(
            "Time to solve the cost optimization: "
            f"{end_time - start_time:0.2f} seconds."
        )

        logger.info("Extracting cost solution")
        start_time = time.time()
        solution = self.extract_solution()
        end_time = time.time()
        logger.info(
            "Time for extracting cost solution: "
            f"{end_time - start_time:0.2f} seconds."
        )
        return solution
