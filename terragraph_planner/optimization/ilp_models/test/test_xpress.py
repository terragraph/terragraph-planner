# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import random
from unittest import TestCase

import xpress as xp


class TestXpress(TestCase):
    def test_xpress_community_license(self) -> None:
        rng = random.Random(0)

        num_vars = 500
        num_constraints = 50

        problem = xp.problem()

        problem.controls.maxtime = -60  # stop after one minute
        problem.controls.miprelstop = 0.05  # stop after converged within 5%

        binvars = [xp.var(vartype=xp.binary) for _i in range(num_vars)]
        problem.addVariable(binvars)

        for _ in range(num_constraints):
            problem.addConstraint(
                xp.Sum((2 * rng.random() - 1) * binvar for binvar in binvars)
                <= 2 * rng.random() - 1
            )

        problem.setObjective(
            xp.Sum(
                xp.Sum((2 * rng.random() - 1) * binvar for binvar in binvars)
            )
        )
        problem.solve()
