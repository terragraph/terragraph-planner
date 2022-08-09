# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import TestCase

from terragraph_planner.common.configuration.enums import StatusType
from terragraph_planner.common.topology_models.test.helper import (
    different_sector_angle_topology,
    dn_cn_limit_topology,
    dn_dn_limit_topology,
    near_far_effect_topology,
    rectangle_topology,
    set_topology_proposed,
    straight_line_topology,
)
from terragraph_planner.optimization.deployment_rules import (
    find_angle_violating_link_pairs,
    find_sector_limit_violations,
    get_violating_link_ids,
)


class TestDeploymentRules(TestCase):
    def test_straight_line_topology(self) -> None:
        topology = straight_line_topology()
        violation_list = find_angle_violating_link_pairs(
            topology,
            25.0,
            45.0,
            3.0,
            False,
        )
        self.assertEqual(len(violation_list.diff_sector_list), 0)
        self.assertEqual(len(violation_list.near_far_list), 0)

    def test_rectangle_topology(self) -> None:
        topology = rectangle_topology()
        # Case 1: No links violate any rules
        violation_lists = find_angle_violating_link_pairs(
            topology,
            45.0,
            75.0,
            3.0,
            False,
        )
        self.assertEqual(len(violation_lists.diff_sector_list), 0)
        self.assertEqual(len(violation_lists.near_far_list), 0)

        # Case 2: 95.0 > 90, all 4 angles violates the diff sector rule
        violation_lists = find_angle_violating_link_pairs(
            topology,
            95.0,
            105.0,
            3.0,
            False,
        )
        self.assertEqual(len(violation_lists.diff_sector_list), 4)
        self.assertEqual(len(violation_lists.near_far_list), 0)

        # Case3: 105.0 > 90 > 45.0, and 100 / 20 = 5 > 3.0. All angles
        # violate the near fast rule
        violation_lists = find_angle_violating_link_pairs(
            topology,
            45.0,
            105.0,
            3.0,
            False,
        )
        self.assertEqual(len(violation_lists.diff_sector_list), 0)
        self.assertEqual(len(violation_lists.near_far_list), 4)

        # Case 4: 105.0 > 90 > 45.0, but 100 / 20 = 5 < 6.0. No angles
        # violate the near fast rule
        violation_lists = find_angle_violating_link_pairs(
            topology,
            45.0,
            105.0,
            6.0,
            False,
        )
        self.assertEqual(len(violation_lists.diff_sector_list), 0)
        self.assertEqual(len(violation_lists.near_far_list), 0)

        # Case 5: the same as Case 2, except active_components = True,
        # so no validations will be found
        violation_lists = find_angle_violating_link_pairs(
            topology,
            95.0,
            105.0,
            3.0,
            True,
        )
        self.assertEqual(len(violation_lists.diff_sector_list), 0)
        self.assertEqual(len(violation_lists.near_far_list), 0)

        # Case 6: the same as Case 3, except active_components = True,
        # so no validations will be found
        violation_lists = find_angle_violating_link_pairs(
            topology,
            45.0,
            105.0,
            3.0,
            True,
        )
        self.assertEqual(len(violation_lists.diff_sector_list), 0)
        self.assertEqual(len(violation_lists.near_far_list), 0)

        # Make every site, link and sector active
        for site in topology.sites.values():
            site.status_type = StatusType.PROPOSED

        for link in topology.links.values():
            link.status_type = StatusType.PROPOSED

        for sector in topology.sectors.values():
            sector.status_type = StatusType.PROPOSED

        # Case 7: the same as Case 5, except that the sites, links and sectors
        # are active now
        violation_lists = find_angle_violating_link_pairs(
            topology,
            95.0,
            105.0,
            3.0,
            True,
        )
        self.assertEqual(len(violation_lists.diff_sector_list), 4)
        self.assertEqual(len(violation_lists.near_far_list), 0)

        # Case 8: the same as Case 6, except that the sites, links and sectors
        # are active now
        violation_lists = find_angle_violating_link_pairs(
            topology,
            45.0,
            105.0,
            3.0,
            True,
        )
        self.assertEqual(len(violation_lists.diff_sector_list), 0)
        self.assertEqual(len(violation_lists.near_far_list), 4)

        # Case 9: the same as Case 8, except that sector 1-0-0-DN is assigned
        # a different channel, so the number of near far violations is reduced.
        topology.sectors["1-0-0-DN"].channel = 1
        violation_lists = find_angle_violating_link_pairs(
            topology,
            45.0,
            105.0,
            3.0,
            True,
        )
        self.assertEqual(len(violation_lists.diff_sector_list), 0)
        self.assertEqual(len(violation_lists.near_far_list), 3)

    def test_dn_dn_limit(self) -> None:
        """
        Verify that the DN-DN limit violations are found.
        """
        topology = dn_dn_limit_topology()

        # Propose some sites/sectors/links but without any violations
        proposed_sites = {"POP0", "DN1", "DN2", "CN4", "CN5"}
        for site_id, site in topology.sites.items():
            if site_id in proposed_sites:
                site.status_type = StatusType.PROPOSED
        for sector in topology.sectors.values():
            if sector.site.site_id in proposed_sites:
                sector.status_type = StatusType.PROPOSED
        for link in topology.links.values():
            if (
                link.tx_site.site_id in proposed_sites
                and link.rx_site.site_id in proposed_sites
            ):
                link.status_type = StatusType.PROPOSED

        violating_sectors = find_sector_limit_violations(topology, 2, 15)
        self.assertEqual(len(violating_sectors), 0)

        # Proposing everything should create a violation
        set_topology_proposed(topology)

        violating_sectors = find_sector_limit_violations(topology, 2, 15)
        self.assertEqual(len(violating_sectors), 1)

    def test_dn_cn_limit(self) -> None:
        """
        Verify that the DN-CN limit violations are found.
        """
        topology = dn_cn_limit_topology()

        # Propose some sites/sectors/links but without any violations
        proposed_sites = {
            "POP0",
            "CN1",
            "CN2",
            "CN3",
            "CN4",
            "CN5",
            "CN6",
            "CN7",
        }
        for site_id, site in topology.sites.items():
            if site_id in proposed_sites:
                site.status_type = StatusType.PROPOSED
        for sector in topology.sectors.values():
            if sector.site.site_id in proposed_sites:
                sector.status_type = StatusType.PROPOSED
        for link in topology.links.values():
            if (
                link.tx_site.site_id in proposed_sites
                and link.rx_site.site_id in proposed_sites
            ):
                link.status_type = StatusType.PROPOSED

        violating_sectors = find_sector_limit_violations(topology, 2, 7)
        self.assertEqual(len(violating_sectors), 0)

        # Proposing everything should create a violation
        set_topology_proposed(topology)

        violating_sectors = find_sector_limit_violations(topology, 2, 7)
        self.assertEqual(len(violating_sectors), 1)

    def test_different_sector_angles(self) -> None:
        """
        Verify different sector angles violations are found.
        """
        topology = different_sector_angle_topology()

        # Propose some sites/sectors/links but without any violations
        proposed_sites = {"POP0", "DN1", "CN3"}
        for site_id, site in topology.sites.items():
            if site_id in proposed_sites:
                site.status_type = StatusType.PROPOSED
        for sector in topology.sectors.values():
            if sector.site.site_id in proposed_sites:
                sector.status_type = StatusType.PROPOSED
        for link in topology.links.values():
            if (
                link.tx_site.site_id in proposed_sites
                and link.rx_site.site_id in proposed_sites
            ):
                link.status_type = StatusType.PROPOSED

        violating_links = find_angle_violating_link_pairs(
            topology,
            diff_sector_angle_limit=15,
            near_far_angle_limit=0,
            near_far_length_ratio=3,
            active_components=True,
        )

        self.assertEqual(len(violating_links.diff_sector_list), 0)
        self.assertEqual(len(violating_links.near_far_list), 0)

        # Proposing everything should create a violation
        set_topology_proposed(topology)

        violating_links = find_angle_violating_link_pairs(
            topology,
            diff_sector_angle_limit=15,
            near_far_angle_limit=0,
            near_far_length_ratio=3,
            active_components=True,
        )

        self.assertEqual(len(violating_links.diff_sector_list), 1)
        self.assertEqual(len(violating_links.near_far_list), 0)

        near_far_violating_links = get_violating_link_ids(
            topology, violating_links.diff_sector_list
        )

        self.assertEqual(len(near_far_violating_links), 4)

    def test_near_far_effect(self) -> None:
        """
        Verify near-far effect violations are found.
        """
        topology = near_far_effect_topology()

        # Propose some sites/sectors/links but without any violations
        proposed_sites = {"POP0", "DN1", "CN3"}
        for site_id, site in topology.sites.items():
            if site_id in proposed_sites:
                site.status_type = StatusType.PROPOSED
        for sector in topology.sectors.values():
            if sector.site.site_id in proposed_sites:
                sector.status_type = StatusType.PROPOSED
        for link in topology.links.values():
            if (
                link.tx_site.site_id in proposed_sites
                and link.rx_site.site_id in proposed_sites
            ):
                link.status_type = StatusType.PROPOSED

        violating_links = find_angle_violating_link_pairs(
            topology,
            diff_sector_angle_limit=0,
            near_far_angle_limit=45,
            near_far_length_ratio=3,
            active_components=True,
        )

        self.assertEqual(len(violating_links.diff_sector_list), 0)
        self.assertEqual(len(violating_links.near_far_list), 0)

        # Proposing everything should create a violation
        set_topology_proposed(topology)

        violating_links = find_angle_violating_link_pairs(
            topology,
            diff_sector_angle_limit=0,
            near_far_angle_limit=45,
            near_far_length_ratio=3,
            active_components=True,
        )

        self.assertEqual(len(violating_links.diff_sector_list), 0)
        self.assertEqual(len(violating_links.near_far_list), 1)

        near_far_violating_links = get_violating_link_ids(
            topology, violating_links.near_far_list
        )

        self.assertEqual(len(near_far_violating_links), 4)
