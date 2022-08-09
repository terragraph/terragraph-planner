# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import time
from typing import Optional, Set, Tuple

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import DebugFile
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.ilp_models.site_optimization import (
    SiteOptimization,
)
from terragraph_planner.optimization.structs import OptimizationSolution

logger: logging.Logger = logging.getLogger(__name__)


class MaxCoverageNetwork(SiteOptimization):
    """
    Maximum Coverage problem. Maximizes the demand coverage with respect
    to a budget constraint.
    """

    def __init__(
        self,
        topology: Topology,
        params: OptimizerParams,
        adversarial_links: Set[Tuple[str, str]],
    ) -> None:
        super(MaxCoverageNetwork, self).__init__(
            topology, params, adversarial_links
        )

    def build_model(self) -> None:
        logger.info("Constructing the coverage optimization model.")
        start_time = time.time()

        self.set_up_problem_skeleton(
            rel_stop=self.params.max_coverage_rel_stop,
            max_time=self.params.max_coverage_max_time,
        )

        self.add_cost_constraint_coverage_objective()
        end_time = time.time()
        logger.info(
            "Time to construct the coverage optimization model: "
            f"{end_time - start_time:0.2f} seconds."
        )

    def solve(self) -> Optional[OptimizationSolution]:
        if self.params.budget <= 0:
            logger.warning(
                "The budget must be positive - skipping coverage optimization."
            )
            return None

        self.build_model()

        self.dump_problem_file_for_debug_mode(DebugFile.COVERAGE_OPTIMIZATION)

        logger.info("Solving coverage optimization")
        start_time = time.time()
        self.problem.solve()
        end_time = time.time()
        logger.info(
            "Time to solve the coverage optimization: "
            f"{end_time - start_time:0.2f} seconds."
        )

        logger.info("Extracting coverage solution")
        start_time = time.time()
        solution = self.extract_solution()
        end_time = time.time()
        logger.info(
            "Time for extracting coverage solution: "
            f"{end_time - start_time:0.2f} seconds."
        )
        return solution
