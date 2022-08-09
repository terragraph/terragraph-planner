# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


from copy import deepcopy
from unittest import TestCase

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import SiteType
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    hybrid_sites_topology,
    multi_sector_topology,
    square_topology,
    square_topology_with_cns,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.constants import DEMAND
from terragraph_planner.optimization.ilp_models.optimization_setup import (
    OptimizationSetup,
)


class TestSetupOptimizeTopology(TestCase):
    def setUp(self) -> None:
        self.device_list = [DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]
        self.opt_params = OptimizerParams(self.device_list)

    def test_setup_links_square_topology(self) -> None:
        topology = square_topology()
        setup = OptimizationSetup(
            topology,
            self.opt_params,
        )
        num_converted_links = _get_num_converted_links(topology)
        self.assertEqual(len(setup.links), num_converted_links)

    def test_setup_links_square_topology_with_cns(self) -> None:
        topology = square_topology_with_cns()
        setup = OptimizationSetup(topology, self.opt_params)
        num_converted_links = _get_num_converted_links(topology)
        self.assertEqual(len(setup.links), num_converted_links)

    def test_setup_locations_square_topology(self) -> None:
        topology = square_topology()
        setup = OptimizationSetup(topology, self.opt_params)
        self.assertEqual(
            len(setup.locations),
            len(topology.sites) + len(topology.demand_sites) + 1,
        )

    def test_setup_locations_square_topology_with_cns(self) -> None:
        topology = square_topology_with_cns()
        setup = OptimizationSetup(topology, self.opt_params)
        self.assertEqual(
            len(setup.locations),
            len(topology.sites) + len(topology.demand_sites) + 1,
        )

    def test_setup_demand_sites_square_topology(self) -> None:
        topology = square_topology()
        setup = OptimizationSetup(topology, self.opt_params)
        self.assertEqual(
            len(setup.type_sets[DEMAND]), len(topology.demand_sites)
        )

    def test_setup_links_without_sectors(self) -> None:
        topology = square_topology()
        topology.links["DN4-DN3"].clear_sectors()
        topology.links["DN3-DN4"].clear_sectors()
        setup = OptimizationSetup(topology, self.opt_params)
        self.assertTrue(
            all(
                sector_id is None
                for sector_id in setup.link_to_sectors[("DN3", "DN4")]
            )
        )
        self.assertTrue(
            all(
                sector_id is None
                for sector_id in setup.link_to_sectors[("DN4", "DN3")]
            )
        )
        self.assertTrue(
            ("DN3", "DN4") in setup.inactive_links
            and ("DN4", "DN3") in setup.inactive_links
        )

    def test_setup_tiered_demand_square_topology(self) -> None:
        topology = square_topology()
        d_ids = list(topology.demand_sites.keys())
        topology.demand_sites[d_ids[0]].num_sites = 2
        topology.demand_sites[d_ids[1]].num_sites = 3
        setup = OptimizationSetup(topology, self.opt_params)
        # Extra demand site on "7" and two extra on "8"
        self.assertEqual(
            len(setup.type_sets[DEMAND]), len(topology.demand_sites) + 3
        )
        # Ensure extra demand site ids are properly tagged to ensure they are unique
        demand_ids = [
            d_ids[0],
            d_ids[0] + "_1",
            d_ids[1],
            d_ids[1] + "_1",
            d_ids[1] + "_2",
        ]
        for demand_id in demand_ids:
            self.assertTrue(demand_id in setup.type_sets[DEMAND])

    def test_setup_demand_sites_square_topology_with_cns(self) -> None:
        topology = square_topology_with_cns()
        setup = OptimizationSetup(topology, self.opt_params)
        self.assertEqual(
            len(setup.type_sets[DEMAND]), len(topology.demand_sites)
        )

    def test_setup_site_type_cn_square_topology(self) -> None:
        topology = square_topology()
        setup = OptimizationSetup(topology, self.opt_params)
        self.assertEqual(
            len(setup.type_sets[SiteType.CN]),
            len(
                [
                    s
                    for s in topology.sites.values()
                    if s.site_type == SiteType.CN
                ]
            ),
        )

    def test_setup_site_type_cn_square_topology_with_cns(self) -> None:
        topology = square_topology_with_cns()
        setup = OptimizationSetup(topology, self.opt_params)
        self.assertEqual(
            len(setup.type_sets[SiteType.CN]),
            len(
                [
                    s
                    for s in topology.sites.values()
                    if s.site_type == SiteType.CN
                ]
            ),
        )

    def test_setup_site_type_dn_square_topology(self) -> None:
        topology = square_topology()
        setup = OptimizationSetup(topology, self.opt_params)
        self.assertEqual(
            len(setup.type_sets[SiteType.DN]),
            len(
                [
                    s
                    for s in topology.sites.values()
                    if s.site_type == SiteType.DN
                ]
            ),
        )

    def test_setup_site_type_dn_square_topology_with_cns(self) -> None:
        topology = square_topology_with_cns()
        setup = OptimizationSetup(topology, self.opt_params)
        self.assertEqual(
            len(setup.type_sets[SiteType.DN]),
            len(
                [
                    s
                    for s in topology.sites.values()
                    if s.site_type == SiteType.DN
                ]
            ),
        )

    def test_setup_site_type_pop_square_topology(self) -> None:
        topology = square_topology()
        setup = OptimizationSetup(topology, self.opt_params)
        self.assertEqual(
            len(setup.type_sets[SiteType.POP]),
            len(
                [
                    s
                    for s in topology.sites.values()
                    if s.site_type == SiteType.POP
                ]
            ),
        )

    def test_setup_site_type_pop_square_topology_with_cns(self) -> None:
        topology = square_topology_with_cns()
        setup = OptimizationSetup(topology, self.opt_params)
        self.assertEqual(
            len(setup.type_sets[SiteType.POP]),
            len(
                [
                    s
                    for s in topology.sites.values()
                    if s.site_type == SiteType.POP
                ]
            ),
        )

    def test_setup_oversubscription(self) -> None:
        topology = square_topology_with_cns()
        base_setup = OptimizationSetup(topology, self.opt_params)

        oversubscription = 2.0
        oversubscribed_setup = OptimizationSetup(
            topology,
            OptimizerParams(
                device_list=self.device_list, oversubscription=oversubscription
            ),
        )

        # demand_at_location is scaled down
        self.assertNotEqual(
            base_setup.demand_at_location,
            oversubscribed_setup.demand_at_location,
        )
        for base_demand_key in base_setup.demand_at_location.keys():
            self.assertEqual(
                base_setup.demand_at_location[base_demand_key]
                / oversubscription,
                oversubscribed_setup.demand_at_location[base_demand_key],
            )

        # everything but demand_at_location exactly the same
        self.assertEqual(
            base_setup.location_to_type,
            oversubscribed_setup.location_to_type,
        )
        self.assertEqual(base_setup.type_sets, oversubscribed_setup.type_sets)
        self.assertEqual(base_setup.locations, oversubscribed_setup.locations)
        self.assertEqual(
            base_setup.location_sectors,
            oversubscribed_setup.location_sectors,
        )
        self.assertEqual(
            base_setup.cost_site,
            oversubscribed_setup.cost_site,
        )
        self.assertEqual(
            base_setup.cost_sector,
            oversubscribed_setup.cost_sector,
        )
        self.assertEqual(
            base_setup.link_to_sectors,
            oversubscribed_setup.link_to_sectors,
        )
        self.assertEqual(
            base_setup.link_capacities,
            oversubscribed_setup.link_capacities,
        )
        self.assertEqual(
            base_setup.link_weights,
            oversubscribed_setup.link_weights,
        )

    def test_hybrid_sites_setup(self) -> None:
        topology = hybrid_sites_topology()
        self.assertEqual(len(topology.links), 13)
        for demand in topology.demand_sites.values():
            self.assertEqual(len(demand.connected_sites), 2)

        setup = OptimizationSetup(topology, self.opt_params)
        self.assertEqual(
            len(topology.demand_sites), len(setup.type_sets[SiteType.CN])
        )
        self.assertEqual(
            len(setup.wired_links),
            len(setup.type_sets[SiteType.POP])
            + 2 * len(setup.type_sets[DEMAND]),
        )
        self.assertEqual(
            len(
                [
                    link
                    for link in setup.links
                    if link[1] in topology.demand_sites
                ]
            ),
            8,
        )

    def test_multi_sector_setup(self) -> None:
        topology = multi_sector_topology(self.opt_params)
        self.assertEqual(len(topology.links), 4)
        # Two sectors in one node
        self.assertEqual(
            {
                s.node_id
                for s in topology.sectors.values()
                if s.site.site_id == "POP1"
            },
            {0, 1},
        )
        setup = OptimizationSetup(topology, self.opt_params)
        # One of the nodes should have been zeroed out, since they share a node
        self.assertEqual(list(setup.cost_sector["POP1"].values()), [250, 250])

        # Now do it without multiple sectors per node
        opt_params = deepcopy(self.opt_params)
        opt_params.device_list[0].sector_params.number_sectors_per_node = 2
        topology = multi_sector_topology(opt_params)
        self.assertEqual(len(topology.links), 4)
        # Two sectors in one node
        self.assertEqual(
            {
                s.node_id
                for s in topology.sectors.values()
                if s.site.site_id == "POP1"
            },
            {0, 1},
        )
        setup = OptimizationSetup(topology, opt_params)
        # None of the sectors should have been zeroed out, since they don't share a node
        self.assertEqual(
            list(setup.cost_sector["POP1"].values()), [250, 0, 250, 0]
        )


def _get_num_converted_links(topology: Topology) -> int:
    num_pops = len(
        [s for s in topology.sites.values() if s.site_type == SiteType.POP]
    )
    demand_sites = topology.demand_sites.values()
    num_demand_site_links = 0
    for demand_site in demand_sites:
        num_demand_site_links += len(demand_site.connected_sites)
    return len(topology.links) + num_pops + num_demand_site_links
