# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import Set

BACKHAUL_LINK_TYPE_WEIGHT = 8  # Access link weight is 1
COVERAGE_STEP_SIZE = 0.1  # coverage increment during min cost optimization
COVERAGE_THRESHOLD = 0.5  # lower bound of coverage for min cost optimization
EPSILON = 1e-5
MAX_LINK_BUDGET_ITERATIONS = 10  # Max iterations for tx power iteration
UNASSIGNED_CHANNEL = -1

DEMAND = "DEMAND"
DEMAND_SECTOR = "DEMAND_SECTOR"  # imaginary POP/DN/CN sector linked to demand
SUPERSOURCE = "SUPERSOURCE"
SUPERSOURCE_SECTOR = (
    "SUPERSOURCE_SECTOR"  # imaginary POP sector linked to supersource
)

IMAGINARY_SECTOR_TYPES: Set[str] = {DEMAND_SECTOR, SUPERSOURCE_SECTOR}
IMAGINARY_SITE_TYPES: Set[str] = {DEMAND, SUPERSOURCE}
