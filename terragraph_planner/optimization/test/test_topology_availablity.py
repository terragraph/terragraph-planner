# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.enums import LinkType, StatusType
from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.topology_models.demand_site import DemandSite
from terragraph_planner.common.topology_models.test.helper import (
    set_topology_proposed,
    square_topology,
    square_topology_with_cns,
)
from terragraph_planner.optimization.topology_availability import (
    compute_availability,
)
from terragraph_planner.optimization.topology_networkx import build_digraph


class TestAvailability(TestCase):
    def test_square_topology(self) -> None:
        topology = square_topology()
        set_topology_proposed(topology)

        graph = build_digraph(topology, StatusType.active_status())
        availability, sim_link_availability = compute_availability(
            graph,
            link_availability=99.99,
            sim_length=20,
            seed=0,
        )

        # Availability should be 100%
        self.assertAlmostEqual(min(availability.values()), 1.0, places=6)
        self.assertAlmostEqual(max(availability.values()), 1.0, places=6)

        # Generally, simulated link availability should be in [99.98, 0.99.998]
        # but that could depend on the random numbers generated - these values
        # can be relaxed if necessary, but if they fall well outside this range
        # that likely indicates something is wrong
        self.assertGreater(min(sim_link_availability.values()), 0.99980)
        self.assertLess(max(sim_link_availability.values()), 0.99998)

    def test_square_topology_with_cns(self) -> None:
        topology = square_topology_with_cns()
        set_topology_proposed(topology)

        graph = build_digraph(topology, StatusType.active_status())
        availability, sim_link_availability = compute_availability(
            graph,
            link_availability=99.99,
            sim_length=20,
            seed=0,
        )

        # Availability should be 100%
        self.assertAlmostEqual(min(availability.values()), 1.0, places=6)
        self.assertAlmostEqual(max(availability.values()), 1.0, places=6)

        # Only backhaul link failures should be simulated
        self.assertEqual(
            len(sim_link_availability),
            len(
                topology.get_link_site_id_pairs(
                    StatusType.active_status(), {LinkType.WIRELESS_BACKHAUL}
                )
            )
            / 2,
        )

        # Now test with a single link failure
        topology = square_topology_with_cns()
        proposed_links = {"POP5-DN4", "DN4-POP5", "DN4-CN7", "DN4-CN8"}
        for link_id, link in topology.links.items():
            if link_id in proposed_links:
                link.tx_site.status_type = StatusType.PROPOSED
                none_throws(link.tx_sector).status_type = StatusType.PROPOSED
                link.rx_site.status_type = StatusType.PROPOSED
                none_throws(link.rx_sector).status_type = StatusType.PROPOSED
                link.status_type = StatusType.PROPOSED

        graph = build_digraph(topology, StatusType.active_status())
        availability, sim_link_availability = compute_availability(
            graph,
            link_availability=99.99,
            sim_length=20,
            seed=0,
        )

        # Only one possible link failure so availability should equal it
        self.assertEqual(len(sim_link_availability), 1)
        sim_link_av = list(sim_link_availability.values())[0]
        self.assertTrue(0.99990 < sim_link_av < 0.99995)
        for a in availability.values():
            self.assertEqual(a, sim_link_av)

        # Now test with path with two links each of which can fail
        topology = square_topology_with_cns()
        proposed_links = {
            "POP6-DN3",
            "DN3-POP6",
            "DN3-DN4",
            "DN4-DN3",
            "DN4-CN7",
            "DN4-CN8",
        }
        for link_id, link in topology.links.items():
            if link_id in proposed_links:
                link.tx_site.status_type = StatusType.PROPOSED
                none_throws(link.tx_sector).status_type = StatusType.PROPOSED
                link.rx_site.status_type = StatusType.PROPOSED
                none_throws(link.rx_sector).status_type = StatusType.PROPOSED
                link.status_type = StatusType.PROPOSED

        graph = build_digraph(topology, StatusType.active_status())
        availability, sim_link_availability = compute_availability(
            graph,
            link_availability=99.99,
            sim_length=20,
            seed=0,
        )

        # Probability of failure is less than link availability because both
        # links have to be available simultaneously
        for a in availability.values():
            for la in sim_link_availability.values():
                self.assertLess(a, la)

        # Now test with two disjoint paths
        topology = square_topology_with_cns()
        proposed_links = {
            "POP5-DN4",
            "DN4-POP5",
            "POP6-DN3",
            "DN3-POP6",
            "DN3-DN4",
            "DN4-DN3",
            "DN4-CN7",
            "DN4-CN8",
        }
        for link_id, link in topology.links.items():
            if link_id in proposed_links:
                link.tx_site.status_type = StatusType.PROPOSED
                none_throws(link.tx_sector).status_type = StatusType.PROPOSED
                link.rx_site.status_type = StatusType.PROPOSED
                none_throws(link.rx_sector).status_type = StatusType.PROPOSED
                link.status_type = StatusType.PROPOSED

        graph = build_digraph(topology, StatusType.active_status())
        availability, sim_link_availability = compute_availability(
            graph,
            link_availability=99.9,
            sim_length=1000,  # Simulate for long enough to find simultaneous failures
            seed=0,
        )

        # Due to disjoint paths, availability is greater than any link
        # availability
        for a in availability.values():
            for la in sim_link_availability.values():
                self.assertGreater(a, la)

    def test_disconnected_demand_site(self) -> None:
        topology = square_topology()
        topology.add_demand_site(
            DemandSite(
                GeoLocation(latitude=0, longitude=0),
                connected_sites=[],
            )
        )
        set_topology_proposed(topology)

        graph = build_digraph(topology, StatusType.active_status())
        availability, _ = compute_availability(
            graph,
            link_availability=99.99,
            sim_length=20,
            seed=0,
        )

        self.assertEqual(len(availability), len(topology.demand_sites) - 1)

        # Availability should be 100%
        self.assertAlmostEqual(min(availability.values()), 1.0, places=6)
        self.assertAlmostEqual(max(availability.values()), 1.0, places=6)
