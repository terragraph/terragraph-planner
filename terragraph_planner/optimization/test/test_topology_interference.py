# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


from copy import deepcopy
from typing import Dict, List, Tuple
from unittest import TestCase
from unittest.mock import Mock, patch

import xpress as xp
from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import StatusType
from terragraph_planner.common.geos import angle_delta
from terragraph_planner.common.rf.link_budget_calculator import (
    get_fspl_based_rsl,
    get_max_tx_power,
    log_to_linear,
)
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    interfering_links_topology,
    intersecting_links_topology,
    set_topology_proposed,
    square_topology,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.constants import UNASSIGNED_CHANNEL
from terragraph_planner.optimization.ilp_models.interference_optimization import (
    MinInterferenceNetwork,
)
from terragraph_planner.optimization.topology_interference import (
    _compute_link_interference_net_gain,
    analyze_interference,
    compute_link_interference,
    compute_link_rsl_map,
)


class TestInterferenceComputation(TestCase):
    def test_interference_on_square_topology(self) -> None:
        """
        Test interference computation on square topology. Note: polarities are
        not assigned in this test case.
        """
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
        )
        topology = square_topology(params)
        set_topology_proposed(topology)

        # Only links POP6-DN2 and POP6-DN3 have interference
        analyze_interference(topology)
        links_with_interference = {"POP6-DN2", "POP6-DN3"}
        for link in topology.links.values():
            if link.link_id in links_with_interference:
                self.assertLess(link.sinr_dbm, link.snr_dbm)
            else:
                self.assertEqual(link.sinr_dbm, link.snr_dbm)

        # Disabling link DN2<->DN3 should not impact interference on POP6-DN2, POP6-DN3
        topology.links["DN3-DN2"].status_type = StatusType.CANDIDATE
        topology.links["DN2-DN3"].status_type = StatusType.CANDIDATE
        analyze_interference(topology)
        for link_id in links_with_interference:
            self.assertLess(
                topology.links[link_id].sinr_dbm,
                topology.links[link_id].snr_dbm,
            )

        # Disabling link DN2-POP6 and DN3-POP6 should remove interference on POP6-DN2, POP6-DN3
        topology.links["DN2-POP6"].status_type = StatusType.CANDIDATE
        topology.links["DN3-POP6"].status_type = StatusType.CANDIDATE
        analyze_interference(topology)
        for link_id in links_with_interference:
            self.assertEqual(
                topology.links[link_id].sinr_dbm,
                topology.links[link_id].snr_dbm,
            )

    @patch(
        "terragraph_planner.optimization.ilp_models.optimization_setup.validate_topology_status",
        Mock(side_effect=lambda t: None),  # do nothing to avoid throwing error
    )
    def test_analyze_interference(self) -> None:
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            always_active_pops=False,
        )
        topology = interfering_links_topology(params)
        # Simplify topology for testing purposes by only keeping links in one direction
        links_to_delete = {
            "DN1-POP0",
            "DN2-DN1",
            "DN3-POP0",
            "DN4-DN3",
            "DN5-DN4",
            "DN2-DN5",
            "DN3-DN2",
            "DN5-POP0",
        }
        for link_id in links_to_delete:
            topology.remove_link(link_id)
        set_topology_proposed(topology)

        # Create a single sector on each site - while not necessarily
        # compatible with the sector horizontal scan range, we do this
        # for testing purposes
        for sector_id in list(topology.sectors.keys()):
            topology.remove_sector(sector_id)

        site_to_sector = {}
        for site in topology.sites.values():
            sector = Sector(
                site=site,
                node_id=0,
                position_in_node=0,
                ant_azimuth=0,
                status_type=StatusType.PROPOSED,
            )
            site_to_sector[site.site_id] = sector
            topology.add_sector(sector)

        for link in topology.links.values():
            link.tx_sector = site_to_sector[link.tx_site.site_id]
            link.rx_sector = site_to_sector[link.rx_site.site_id]

        # Interfering paths can be active or inactive and still cause
        # interference due to positive tdm on interference causing links
        topology.links["POP0-DN5"]._status_type = StatusType.UNAVAILABLE

        # Update tx power for interference analysis
        for link in topology.links.values():
            tx_sector_params = link.tx_site.device.sector_params
            link.tx_power = get_max_tx_power(
                tx_sector_params=tx_sector_params,
                max_eirp_dbm=params.maximum_eirp,
            )

        copied_topology = deepcopy(topology)  # copy for later use

        analyze_interference(topology)

        link_rsl_map = compute_link_rsl_map(topology)
        self.assertEqual(len(link_rsl_map), 3)

        interfering_tuple_list = []

        # DN3 receives interference from DN2 when DN2 transmits to CN6. The
        # interference path is DN2-DN3, while the link whose tx power causes
        # interference to DN3 is DN2-CN6. The link that suffers from this
        # interference is POP0-DN3.
        self.assertLess(
            topology.links["POP0-DN3"].sinr_dbm,
            topology.links["POP0-DN3"].snr_dbm,
        )
        interfering_tuple_list.append(("DN2-DN3", "POP0-DN3", ["DN2-CN6"]))

        # DN3 receives interference from POP0 when POP0 transmits to DN1. The
        # interference path is POP0-DN3, while the link whose tx power causes
        # interference is POP0-DN1. The link that suffers from this
        # interference is DN2-DN3
        self.assertLess(
            topology.links["DN2-DN3"].sinr_dbm,
            topology.links["DN2-DN3"].snr_dbm,
        )
        interfering_tuple_list.append(("POP0-DN3", "DN2-DN3", ["POP0-DN1"]))

        # DN5 receives interference from POP0 when POP0 transmits to DN1 or
        # DN3. The interference path is POP0-DN5, while the links whose tx
        # power causes interference to DN5 are POP0-DN1 and POP0-DN3. The two
        # interfering links POP0-DN1 and POP0-DN3 time-share, so we average the
        # interference they cause to DN5 in analyze_interference(). The link
        # that suffers from this interference is DN4-DN5.
        self.assertLess(
            topology.links["DN4-DN5"].sinr_dbm,
            topology.links["DN4-DN5"].snr_dbm,
        )
        interfering_tuple_list.append(
            ("POP0-DN5", "DN4-DN5", ["POP0-DN1", "POP0-DN3"])
        )

        def _compute_test_rsl_map(
            topology: Topology,
            interfering_tuple_list: List[Tuple[str, str, List[str]]],
        ) -> Dict[str, float]:
            test_rsl_map = {}
            for (
                interfering_path_link_id,
                rx_interfered_link_id,
                tx_interfering_link_ids,
            ) in interfering_tuple_list:
                interfering_path = topology.links[interfering_path_link_id]
                rx_interfered_link = topology.links[rx_interfered_link_id]

                interference_sum = 0
                for tx_interfering_link_id in tx_interfering_link_ids:
                    tx_interfering_link = topology.links[tx_interfering_link_id]

                    tx_dev = angle_delta(
                        none_throws(interfering_path.tx_dev),
                        none_throws(tx_interfering_link.tx_dev),
                    )
                    rx_dev = angle_delta(
                        none_throws(interfering_path.rx_dev),
                        none_throws(rx_interfered_link.rx_dev),
                    )
                    tx_el_dev = angle_delta(
                        interfering_path.el_dev, tx_interfering_link.el_dev
                    )
                    rx_el_dev = -angle_delta(
                        interfering_path.el_dev, rx_interfered_link.el_dev
                    )

                    net_gain = _compute_link_interference_net_gain(
                        interfering_path, tx_dev, rx_dev, tx_el_dev, rx_el_dev
                    )
                    interference = log_to_linear(
                        get_fspl_based_rsl(
                            topology.links[tx_interfering_link_id].tx_power,
                            net_gain,
                        )
                    )
                    self.assertGreater(interference, 0)
                    interference_sum += interference
                test_rsl_map[rx_interfered_link_id] = interference_sum / len(
                    tx_interfering_link_ids
                )
            return test_rsl_map

        test_rsl_map = _compute_test_rsl_map(topology, interfering_tuple_list)
        self.assertEqual(link_rsl_map, test_rsl_map)

        # None of the other links have interference
        for link_id, link in topology.links.items():
            if link_id not in {"POP0-DN3", "DN4-DN5", "DN2-DN3"}:
                self.assertEqual(link.sinr_dbm, link.snr_dbm)

        # Comparing with interference optimization RSL expression
        risl_P1_D3 = link_rsl_map["POP0-DN3"]
        risl_D4_D5 = link_rsl_map["DN4-DN5"]
        risl_D2_D3 = link_rsl_map["DN2-DN3"]
        interfering_rsl = compute_link_interference(
            topology, params.maximum_eirp
        )
        min_int_network = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        )

        solution = min_int_network.solve()
        self.assertIsNotNone(solution)

        for link_id, link in topology.links.items():
            # Set tdm to match logic in compute_link_interference
            min_int_network.tdm_compatible_polarity[
                ("POP0", "DN2", "CN6", 0)
            ] = 0.5
            min_int_network.tdm_compatible_polarity[
                ("DN2", "POP0", "DN1", 0)
            ] = 0.5
            min_int_network.tdm_compatible_polarity[
                ("DN4", "POP0", "DN1", 0)
            ] = 0.5
            min_int_network.tdm_compatible_polarity[
                ("DN4", "POP0", "DN3", 0)
            ] = 0.5
            if link_id == "POP0-DN3":
                # While POP0->DN3, DN2->CN6; POP0->DN3 is not simultaneous with DN2->DN3
                min_int_network.tdm_compatible_polarity[
                    ("POP0", "DN2", "CN6", 0)
                ] = 1
            elif link_id == "DN2-DN3":
                # While DN2->DN3, POP0->DN1; DN2->DN3 is not simultaneous with POP0->DN3
                min_int_network.tdm_compatible_polarity[
                    ("DN2", "POP0", "DN1", 0)
                ] = 1
                min_int_network.tdm_compatible_polarity[
                    ("DN4", "POP0", "DN1", 0)
                ] = 1
                min_int_network.tdm_compatible_polarity[
                    ("DN4", "POP0", "DN3", 0)
                ] = 0

            risl = xp.evaluate(  # pyre-ignore
                min_int_network.get_interfering_rsl_expr(
                    tx_site=link.tx_site.site_id,
                    rx_site=link.rx_site.site_id,
                    rx_sector=none_throws(link.rx_sector).sector_id,
                    channel=0,
                ),
                problem=min_int_network.problem,
            )
            if link_id not in {"POP0-DN3", "DN4-DN5", "DN2-DN3"}:
                self.assertEqual(risl[0], 0)
            else:
                if link_id == "POP0-DN3":
                    self.assertEqual(risl[0], risl_P1_D3, 10)
                    self.assertGreater(risl_P1_D3, 0)
                elif link_id == "DN4-DN5":
                    self.assertEqual(risl[0], risl_D4_D5)
                    self.assertGreater(risl_D4_D5, 0)
                elif link_id == "DN2-DN3":
                    self.assertEqual(risl[0], risl_D2_D3)
                    self.assertGreater(risl_D2_D3, 0)

        # To test handling of redundant links, manually set is_redundant for
        # POP0-DN1 to true. Redundant links are not expected to cause interference
        # on other links. DN4-DN5 and DN2-DN3 should no longer suffer interference
        # caused by POP0-DN1. However, for DN4-DN5, there is still interference
        # caused by POP0-DN3.
        copied_topology.links["POP0-DN1"].is_redundant = True
        analyze_interference(copied_topology)
        self.assertGreater(
            copied_topology.links["DN2-DN3"].sinr_dbm,
            topology.links["DN2-DN3"].sinr_dbm,
        )
        self.assertEqual(
            copied_topology.links["DN2-DN3"].sinr_dbm,
            copied_topology.links["DN2-DN3"].sinr_dbm,
        )
        self.assertLess(
            copied_topology.links["DN4-DN5"].sinr_dbm,
            copied_topology.links["DN4-DN5"].snr_dbm,
        )

        # Because P1-D1 is redundant, D2-D3 no longer in the rsl_map.
        new_link_rsl_map = compute_link_rsl_map(copied_topology)
        self.assertEqual(len(new_link_rsl_map), len(link_rsl_map) - 1)
        self.assertTrue("DN2-DN3" not in new_link_rsl_map)
        for link, link_rsl in new_link_rsl_map.items():
            self.assertGreaterEqual(link_rsl_map[link], link_rsl)

        new_interfering_tuple_list = []
        new_interfering_tuple_list.append(("DN2-DN3", "POP0-DN3", ["DN2-CN6"]))
        new_interfering_tuple_list.append(("POP0-DN5", "DN4-DN5", ["POP0-DN3"]))

        new_test_rsl_map = _compute_test_rsl_map(
            copied_topology, new_interfering_tuple_list
        )
        self.assertEqual(new_link_rsl_map, new_test_rsl_map)

    def test_multi_channel_interference(self) -> None:
        params = OptimizerParams(
            device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            demand=1.8,  # Max demand that can be satisfied with 0 interference
        )
        topology = intersecting_links_topology(params)

        set_topology_proposed(topology)
        topology.links["DN1-DN4"]._status_type = StatusType.UNAVAILABLE
        topology.links["DN4-DN1"]._status_type = StatusType.UNAVAILABLE
        topology.links["DN2-DN3"]._status_type = StatusType.UNAVAILABLE
        topology.links["DN3-DN2"]._status_type = StatusType.UNAVAILABLE

        # Update tx power for interference analysis
        for link in topology.links.values():
            tx_sector_params = link.tx_site.device.sector_params
            link.tx_power = get_max_tx_power(
                tx_sector_params=tx_sector_params,
                max_eirp_dbm=params.maximum_eirp,
            )

        # Without multi-channel, i.e. all channels are default 0,
        # links "DN1-DN2" and "DN3-DN4" suffer interference
        analyze_interference(topology)
        inter_links = {"DN1-DN2", "DN2-DN1", "DN3-DN4", "DN4-DN3"}
        for link in topology.links.values():
            if link.link_id in inter_links:
                self.assertLess(link.sinr_dbm, link.snr_dbm)
            else:
                self.assertEqual(link.sinr_dbm, link.snr_dbm)

        # Comparing with interference optimization RSL expression
        # D2 receives interference from D3 when D3 transmits to D4
        # D4 receives interference from D1 when D1 transmits to D2
        link_rsl_map = compute_link_rsl_map(topology)
        self.assertEqual(len(link_rsl_map), 4)

        risl_D2 = link_rsl_map["DN1-DN2"]
        risl_D4 = link_rsl_map["DN3-DN4"]

        # Enable only one channel
        params.number_of_channels = 1
        interfering_rsl = compute_link_interference(
            topology, params.maximum_eirp
        )
        min_int_network = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        )
        solution = min_int_network.solve()
        self.assertIsNotNone(solution)

        # Update topology with sector channel assignments
        for sector_id, sector in topology.sectors.items():
            sector.channel = solution.channel_decisions.get(
                (sector.site.site_id, sector_id), UNASSIGNED_CHANNEL
            )

        # Set tdm to be 1/# links to match logic in compute_link_interference
        min_int_network.tdm_compatible_polarity[("DN1", "DN3", "DN4", 0)] = 1.0
        min_int_network.tdm_compatible_polarity[("DN3", "DN1", "DN2", 0)] = 1.0
        for link_id, link in topology.links.items():
            risl = xp.evaluate(  # pyre-ignore
                min_int_network.get_interfering_rsl_expr(
                    tx_site=link.tx_site.site_id,
                    rx_site=link.rx_site.site_id,
                    rx_sector=none_throws(link.rx_sector).sector_id,
                    channel=none_throws(link.tx_sector).channel,
                ),
                problem=min_int_network.problem,
            )
            if link_id not in {"DN1-DN2", "DN3-DN4"}:
                self.assertEqual(risl[0], 0)
            else:
                if link_id == "DN1-DN2":
                    self.assertEqual(risl[0], risl_D2)
                    self.assertGreater(risl_D2, 0)
                if link_id == "DN3-DN4":
                    self.assertEqual(risl[0], risl_D4)
                    self.assertGreater(risl_D4, 0)

        # Enable multiple channels - use interference model to do
        # channel assignment
        params.number_of_channels = 2
        min_int_network = MinInterferenceNetwork(
            topology, params, [], interfering_rsl
        )
        solution = min_int_network.solve()
        self.assertIsNotNone(solution)

        # Update topology with sector channel assignments
        for sector_id, sector in topology.sectors.items():
            sector.channel = solution.channel_decisions.get(
                (sector.site.site_id, sector_id), UNASSIGNED_CHANNEL
            )

        channel1 = solution.channel_decisions[("DN1", "DN1-0-0-DN")]
        channel2 = solution.channel_decisions[("DN3", "DN3-0-0-DN")]
        self.assertNotEqual(channel1, channel2)
        self.assertEqual(
            solution.channel_decisions[("DN2", "DN2-1-0-DN")],
            channel1,
        )
        self.assertEqual(
            solution.channel_decisions[("DN4", "DN4-1-0-DN")],
            channel2,
        )

        analyze_interference(topology)
        for link in topology.links.values():
            self.assertEqual(link.sinr_dbm, link.snr_dbm)

        # Comparing with interference optimization RSL expression
        # DN2 does not receive interference from DN3 when DN3 transmits to DN4
        # DN4 does not receive interference from DN1 when DN1 transmits to DN2
        link_rsl_map = compute_link_rsl_map(topology)
        self.assertEqual(len(link_rsl_map), 0)

        for link in topology.links.values():
            risl = xp.evaluate(  # pyre-ignore
                min_int_network.get_interfering_rsl_expr(
                    tx_site=link.tx_site.site_id,
                    rx_site=link.rx_site.site_id,
                    rx_sector=none_throws(link.rx_sector).sector_id,
                    channel=none_throws(link.tx_sector).channel,
                ),
                problem=min_int_network.problem,
            )
            self.assertEqual(risl[0], 0)
