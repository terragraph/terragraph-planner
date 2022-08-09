# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


from unittest import TestCase

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import SiteType
from terragraph_planner.common.exceptions import OptimizerException
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    square_topology_with_cns,
)
from terragraph_planner.optimization.ilp_models.network_optimization import (
    NetworkOptimization,
)


class TestNetworkOptimizeTopology(TestCase):
    def setUp(self) -> None:
        self.device_list = [DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        self.opt_params = OptimizerParams(self.device_list)

    def test_pop_infeasibility(self) -> None:
        topology = square_topology_with_cns()
        for link in topology.links.values():
            tx_site = link.tx_site
            if tx_site and tx_site.site_type == SiteType.POP:
                link.capacity = 0.0
        with self.assertRaisesRegex(
            OptimizerException, "No POP has a positive capacity outgoing link."
        ):
            NetworkOptimization(topology, self.opt_params)

    def test_demand_feasibility(self) -> None:
        topology = square_topology_with_cns()
        for link in topology.links.values():
            if link.rx_site.site_type == SiteType.CN:
                link.capacity = 0.0
        with self.assertRaisesRegex(
            OptimizerException,
            "No CN or demand-connected DN has a positive capacity incoming link.",
        ):
            NetworkOptimization(topology, self.opt_params)
