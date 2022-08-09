# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import math
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional, Set, Tuple

import xpress as xp
from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import (
    DebugFile,
    SectorType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.constants import (
    FULL_ROTATION_ANGLE,
    SECTOR_LINK_ANGLE_TOLERANCE,
)
from terragraph_planner.common.exceptions import (
    OptimizerException,
    planner_assert,
)
from terragraph_planner.common.geos import angle_delta
from terragraph_planner.common.rf.link_budget_calculator import (
    log_to_linear,
    mbps_to_gbps,
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
from terragraph_planner.optimization.structs import (
    LinkPair,
    OptimizationSolution,
)

logger: logging.Logger = logging.getLogger(__name__)


class MinInterferenceNetwork(NetworkOptimization):
    """
    Select links and sectors so that coverage is maximized by minimizing
    interference in the network.
    """

    def __init__(
        self,
        topology: Topology,
        params: OptimizerParams,
        angle_limit_violating_links: List[LinkPair],
        interfering_rsl: Dict[Tuple[str, str], float],
    ) -> None:
        super(MinInterferenceNetwork, self).__init__(topology, params)

        # We do not want the proposed links and sectors that were extracted from
        # the previous optimization's solution to be enforced here.
        # So, proposed links and sectors are overridden.
        self.proposed_sectors.clear()
        self.proposed_links.clear()

        self.angle_limit_violating_links = angle_limit_violating_links

        # Cache value to avoid repeated evaluation
        self.horizontal_scan_range: Dict[str, float] = {}
        for site_id, site in topology.sites.items():
            sector_params = site.device.sector_params
            self.horizontal_scan_range[
                site_id
            ] = sector_params.horizontal_scan_range

        self.rsl_linear: Dict[Tuple[str, str], float] = {
            (link.tx_site.site_id, link.rx_site.site_id): log_to_linear(
                link.rsl_dbm
            )
            for link in topology.links.values()
        }
        self.interfering_rsl_linear: Dict[Tuple[str, str], float] = {
            (link.tx_site.site_id, link.rx_site.site_id): log_to_linear(
                interfering_rsl[(link.tx_site.site_id, link.rx_site.site_id)]
            )
            if (link.tx_site.site_id, link.rx_site.site_id) in interfering_rsl
            else 0
            for link in topology.links.values()
        }

        self.noise_linear: Dict[str, float] = {}
        self.snr_linear_inverse: Dict[str, List[float]] = {}
        self.cap_gbps: Dict[str, List[float]] = {}
        for device in self.params.device_list:
            self.noise_linear[device.device_sku] = log_to_linear(
                device.sector_params.thermal_noise_power
                + device.sector_params.noise_figure
            )
            self.snr_linear_inverse[device.device_sku] = []
            self.cap_gbps[device.device_sku] = []
            for row in device.sector_params.mcs_map:
                self.snr_linear_inverse[device.device_sku].append(
                    1 / log_to_linear(row.snr)
                )
                self.cap_gbps[device.device_sku].append(mbps_to_gbps(row.mbps))

        if self.params.maximize_common_bandwidth:
            self.connected_demand_sites: Set[
                str
            ] = self._compute_connectable_demand_sites()

        # Variables created when building the optimization model
        self.active_link = None  # pyre-fixme
        self.deployment_link = None  # pyre-fixme
        self.link_capacity_vars = None  # pyre-fixme
        self.zero_cap_prod_vars = None  # pyre-fixme
        self.tdm_compatible_polarity = None  # pyre-fixme

    def _compute_connectable_demand_sites(self) -> Set[str]:
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

    def _get_ignore_sites(self) -> Set[str]:
        """
        Deployment optimization makes decision on links, but site decisions
        are fixed, so reachable demand sites must be connected through active
        sites. Thus, all candidate are added to the ignored sites.
        """
        ignore_sites = super(MinInterferenceNetwork, self)._get_ignore_sites()
        active_sites = self._get_active_sites()
        for site_id, site in self.topology.sites.items():
            if site.status_type == StatusType.CANDIDATE:
                ignore_sites.add(site_id)
            elif (
                site.status_type in StatusType.active_status()
                and site_id not in active_sites
            ):
                ignore_sites.add(site_id)
        return ignore_sites

    def setup_problem_skeleton(self) -> None:
        self.create_model(
            self.params.interference_rel_stop, self.params.interference_max_time
        )
        self.create_site_decisions()
        self.create_polarity_decisions()
        self.create_flow_decisions()
        self.create_shortage_decisions()
        self.create_active_link_decisions()
        self.create_deployment_link_decisions()
        self.create_sector_decisions()
        self.create_tdm_decisions()

        # Constraints
        self.create_tdm_flow_relationship()
        self.create_tdm_link_relationship()
        self.create_flow_balance_with_shortage()
        self.create_pop_load_constraints()
        self.create_flow_link_relationship()
        self.create_symmetric_link_constraints()
        self.create_sector_constraints()
        self.create_sector_link_constraints()
        self.create_cn_link_constraints()
        self.create_polarity_link_relationship()
        self.create_fixed_input_constraints_with_sectors()
        self.create_multi_point_contstraints()
        self.create_deployment_link_constraints()
        self.create_angle_limit_guideline_constraints()
        self.create_exact_capacity_constraints()

    def solve(self) -> Optional[OptimizationSolution]:
        if len(self.proposed_sites) + len(self.existing_sites) == 0:
            return None

        logger.info("Constructing the interference optimization model.")
        start_time = time.time()
        if self.problem is not None:
            self.problem.reset()
        self.setup_problem_skeleton()
        self.create_coverage_and_weighted_link_objective()
        end_time = time.time()
        logger.info(
            "Time to construct the interference optimization model: "
            f"{end_time - start_time:0.2f} seconds."
        )

        self.dump_problem_file_for_debug_mode(
            DebugFile.INTERFERENCE_OPTIMIZATION
        )

        logger.info("Solving interference optimization")
        start_time = time.time()
        self.problem.solve()
        end_time = time.time()
        logger.info(
            "Time to solve the interference optimization: "
            f"{end_time - start_time:0.2f} seconds."
        )

        # If maximize common bandwidth is enabled but no common bandwidth is
        # found, re-solve the problem by maximizing total network bandwidth
        if self.problem.attributes.mipsols > 0:
            if self.common_bandwidth is not None:
                sol = self.problem.getSolution()
                common_bandwidth = sol[
                    self.problem.getIndex(self.common_bandwidth)
                ]
                if common_bandwidth == 0:
                    logger.warning(
                        "No common bandwidth was found, re-solving with maximizing total network bandwidth"
                    )
                    self.params.maximize_common_bandwidth = False
                    try:
                        self.problem.delVariable(self.common_bandwidth)
                    except Exception:
                        self.problem.reset()
                        self.setup_problem_skeleton()
                    self.common_bandwidth = None
                    self.create_coverage_and_weighted_link_objective()
                    start_time = time.time()
                    self.problem.solve()
                    end_time = time.time()
                    logger.info(
                        "Time to re-solve the interference optimization: "
                        f"{end_time - start_time:0.2f} seconds."
                    )

        logger.info("Extracting interference solution")
        start_time = time.time()
        solution = self.extract_solution()
        end_time = time.time()
        logger.info(
            "Time for extracting interference solution: "
            f"{end_time - start_time:0.2f} seconds."
        )
        return solution

    def _get_active_sites(self) -> Set[str]:
        active_sites = set()

        input_active_sites = self.proposed_sites | self.existing_sites
        for i in self.locations:
            if i in input_active_sites:
                # Colocated sites handled below
                if (
                    len(
                        self.colocated_locations.get(
                            self.location_to_geoloc[i], []
                        )
                    )
                    <= 1
                ):
                    active_sites.add(i)

        # The proposed/existing co-located site with the max site type is the
        # one that is active in the network. For example, given an existing CN
        # and proposed DN, the DN is the active site in the network.
        for locs in self.colocated_locations.values():
            if len(locs) <= 1:
                continue
            active_colocated_sites = input_active_sites.intersection(set(locs))
            if len(active_colocated_sites) == 0:
                continue
            (
                max_site_type,
                _,
            ) = self._get_max_and_valid_site_types_from_colocated_sites(
                active_colocated_sites
            )
            for loc in locs:
                if (
                    self.location_to_type[loc] == max_site_type
                    and loc in input_active_sites
                ):
                    active_sites.add(loc)

        return active_sites

    def create_site_decisions(self) -> None:
        # Note: demand and supersource sites can be assumed to be active
        active_sites = self._get_active_sites()
        self.site_vars = {
            loc: 1 if loc in active_sites else 0
            for loc in self.locations
            if self.location_to_type[loc] not in IMAGINARY_SITE_TYPES
        }

    def create_active_link_decisions(self) -> None:
        # Wireless link decisions
        self.active_link = {
            (i, j): xp.var(  # pyre-ignore
                name=f"active_link_{i}_{j}", vartype=xp.binary  # pyre-ignore
            )
            for (i, j) in self.links
            if self.link_capacities[(i, j)] > 0
            and all(self.link_to_sectors.get((i, j), (None, None)))
            and self.location_to_type[i] not in IMAGINARY_SITE_TYPES
            and self.location_to_type[j] not in IMAGINARY_SITE_TYPES
            and (i, j) not in self.wired_links
        }

        self.problem.addVariable(self.active_link)

    def create_deployment_link_decisions(self) -> None:
        # Link channel decisions for angle limit violating links
        # If only one channel, active_link can be used instead
        if self.number_of_channels == 1:
            return

        deployment_links = []
        for (i, j, k) in self.angle_limit_violating_links:
            if (i, j) in self.active_link and (i, k) in self.active_link:
                deployment_links.append((i, j))
                deployment_links.append((i, k))

        self.deployment_link = {
            (i, j, c): xp.var(  # pyre-ignore
                name=f"deployment_link_{i}_{j}_{c}",
                vartype=xp.binary,  # pyre-ignore
            )
            for (i, j) in deployment_links
            for c in range(self.number_of_channels)
        }

        self.problem.addVariable(self.deployment_link)

    def create_fixed_input_constraints_with_sectors(self) -> None:
        self.create_decided_link_constraints()
        self.create_active_link_polarity_constraints()
        self.create_inactive_link_flow_constraints()

    def create_decided_link_constraints(self) -> None:
        # Ensure that proposed and existing links are active
        for (i, j) in self.links:
            if (i, j) not in self.proposed_links and (
                i,
                j,
            ) not in self.existing_links:
                continue
            # Avoid infeasibility if an active link connects two sites that are
            # inactive. This can happen, for example, if an existing link connects
            # to a co-located site with a site type that is getting upgraded.
            if self.site_vars[i] == 0 or self.site_vars[j] == 0:
                continue

            if (i, j) in self.active_link:
                self.problem.addConstraint(self.active_link[(i, j)] == 1)

            # Ensure one of the sectors are active if the link is active
            (sector1, sector2) = self.link_to_sectors.get((i, j), (None, None))
            planner_assert(
                sector1 is not None or sector2 is not None,
                f"No sector found for link {i}-{j}",
                OptimizerException,
            )
            if sector1:
                self.problem.addConstraint(
                    xp.Sum(  # pyre-ignore
                        self.sector_vars[(i, sector1, channel)]
                        for channel in range(self.number_of_channels)
                        if (i, sector1, channel) in self.sector_vars
                    )
                    == 1
                )
            if sector2:
                self.problem.addConstraint(
                    xp.Sum(  # pyre-ignore
                        self.sector_vars[(j, sector2, channel)]
                        for channel in range(self.number_of_channels)
                        if (j, sector2, channel) in self.sector_vars
                    )
                    == 1
                )

        # Ensure that inactive links are inactive
        for (i, j) in self.links:
            if (i, j) not in self.inactive_links:
                continue
            if (i, j) in self.active_link:
                self.problem.addConstraint(self.active_link[(i, j)] == 0)

    def create_multi_point_contstraints(self) -> None:
        """
        A DN sector can connect to a limited number of other DN and
        DN + CN sectors. For example, a DN might only be allowed to connect to
        2 other DN sectors and up to 13 CN sectors, or 1 DN sector and up to 14
        CN sectors or 0 DN sectors and up to 15 CN sectors.
        """
        for i in self.locations:
            if self.location_to_type[i] not in SiteType.dist_site_types():
                continue
            for sec in self.location_sectors[i]:
                var_dn_dn_sector_links = 0
                var_dn_cn_sector_links = 0
                num_dn_dn_sector_links = 0
                num_dn_cn_sector_links = 0
                for _, j in self.outgoing_links[i]:
                    tx_sector = self.link_to_sectors[(i, j)][0]
                    if tx_sector is None or tx_sector != sec:
                        continue
                    if (i, j) not in self.active_link:
                        continue
                    if self.location_to_type[j] in SiteType.dist_site_types():
                        var_dn_dn_sector_links = (
                            var_dn_dn_sector_links + self.active_link[(i, j)]
                        )
                        num_dn_dn_sector_links += 1
                        var_dn_cn_sector_links = (
                            var_dn_cn_sector_links + self.active_link[(i, j)]
                        )
                        num_dn_cn_sector_links += 1
                    elif self.location_to_type[j] == SiteType.CN:
                        var_dn_cn_sector_links = (
                            var_dn_cn_sector_links + self.active_link[(i, j)]
                        )
                        num_dn_cn_sector_links += 1

                # Apply P2MP constraints - only needed if number of possible
                # links exceeds the allowed limit
                if num_dn_dn_sector_links >= self.params.dn_dn_sector_limit:
                    # There must be at most params.dn_dn_sector_limit active
                    # DN sector connections
                    self.problem.addConstraint(
                        var_dn_dn_sector_links
                        <= self.params.dn_dn_sector_limit
                        * xp.Sum(  # pyre-ignore
                            self.sector_vars[(i, sec, channel)]
                            for channel in range(self.number_of_channels)
                        )
                    )

                if num_dn_cn_sector_links >= self.params.dn_total_sector_limit:
                    # There must be at most params.dn_total_sector_limit active
                    # DN-DN and DN-CN sector connections
                    self.problem.addConstraint(
                        var_dn_cn_sector_links
                        <= self.params.dn_total_sector_limit
                        * xp.Sum(  # pyre-ignore
                            self.sector_vars[(i, sec, channel)]
                            for channel in range(self.number_of_channels)
                        )
                    )

    def create_flow_link_relationship(self) -> None:
        """
        Each link has a maximum throughput value and the flow sent on it
        cannot be more than this maximum throughput value.

        We also force each active site to have at least one active link
        associated with it.
        """
        for (i, j) in self.flow:
            if (i, j) in self.active_link:
                link_cap = self.link_capacities[(i, j)]
                self.problem.addConstraint(
                    self.flow[(i, j)] <= link_cap * self.active_link[(i, j)]
                )

    def create_cn_link_constraints(self) -> None:
        for cn in self.locations:
            if cn not in self.type_sets[SiteType.CN]:
                continue
            incoming_cn_links = [
                link
                for link in self.incoming_links[cn]
                if link in self.active_link
            ]
            if len(incoming_cn_links) > 0:
                self.problem.addConstraint(
                    xp.Sum(  # pyre-ignore
                        self.active_link[link] for link in incoming_cn_links
                    )
                    <= 1
                )

    def create_sector_link_constraints(self) -> None:
        """
        This set of constraints set up the relationship between sector_vars and active_link.
        active_link can be equal to 1 only if the sector variables that form this link also
        are equal to one.
        """

        # For each link that has a binary decision attached to it
        for (i, j) in self.active_link:
            # Find the IDs of the tx and rx sectors that form this link.
            (sec1, sec2) = self.link_to_sectors.get((i, j), (None, None))

            # Sector must be active for the link to be active
            if (i, sec1, 0) in self.sector_vars:
                self.problem.addConstraint(
                    self.active_link[(i, j)]
                    <= xp.Sum(  # pyre-ignore
                        self.sector_vars[(i, sec1, channel)]
                        for channel in range(self.number_of_channels)
                        if (i, sec1, channel) in self.sector_vars
                    )
                )
            if (j, sec2, 0) in self.sector_vars:
                self.problem.addConstraint(
                    self.active_link[(i, j)]
                    <= xp.Sum(  # pyre-ignore
                        self.sector_vars[(j, sec2, channel)]
                        for channel in range(self.number_of_channels)
                        if (j, sec2, channel) in self.sector_vars
                    )
                )

            if (
                self.number_of_channels == 1
                or self.location_to_type[j] == SiteType.CN
            ):
                continue

            # Link can only be active if the connecting sectors have the same
            # channel; these are unnecessary if there is only one channel or if
            # the receiving site is a CN
            for channel in range(self.number_of_channels):
                self.problem.addConstraint(
                    self.active_link[(i, j)]
                    <= self.sector_vars[(i, sec1, channel)]
                    - self.sector_vars[(j, sec2, channel)]
                    + 1
                )
                self.problem.addConstraint(
                    self.active_link[(i, j)]
                    <= self.sector_vars[(j, sec2, channel)]
                    - self.sector_vars[(i, sec1, channel)]
                    + 1
                )

    def create_tdm_link_relationship(self) -> None:
        # Time-division multiplexing
        for (i, j) in self.links:
            if (i, j, 0) in self.tdm:
                if (i, j) in self.active_link:
                    self.problem.addConstraint(
                        xp.Sum(  # pyre-ignore
                            self.tdm[(i, j, c)]
                            for c in range(self.number_of_channels)
                        )
                        <= self.active_link[(i, j)]
                    )

    def create_polarity_link_relationship(self) -> None:
        """
        Polarity constraints are almost identical to that of main_optimization.
        Here, we are making use of the binary variables active_link[(i,j)]
        rather than tdm[(i,j)].
        """
        if self.params.ignore_polarities:
            return

        input_active_links = self.proposed_links | self.existing_links
        for (i, j) in self.links:
            # If link (i, j) is set to be active by the user, opposite polarity
            # enforcement will be handled separately.
            if (i, j) in input_active_links:
                continue
            # If link (i, j) is active, then the polarity of i and j has
            # to be opposite
            if (
                (i, j) in self.active_link
                and self.location_to_type[i] in SiteType.dist_site_types()
                and self.location_to_type[j] in SiteType.dist_site_types()
            ):
                # If both are even, then active link <= odd_i + odd_j = 0
                # If both are odd, then active link <= 2 - odd_i - odd_j = 0
                # The second constraint is equivalent to
                # active link <= even_i + even_j
                self.problem.addConstraint(
                    self.active_link[(i, j)] <= self.odd[i] + self.odd[j]
                )
                self.problem.addConstraint(
                    self.active_link[(i, j)] <= 2 - self.odd[i] - self.odd[j]
                )

    def create_symmetric_link_constraints(self) -> None:
        # If link (i, j) is active, then link (j, i) should also be active
        for (i, j) in self.active_link:
            if (j, i) in self.active_link:
                self.problem.addConstraint(
                    self.active_link[(i, j)] == self.active_link[(j, i)]
                )

    def create_deployment_link_constraints(self) -> None:
        # If only one channel, active_link is used instead of deployment_link
        if self.number_of_channels == 1:
            return

        for (i, j, c) in self.deployment_link:
            self.problem.addConstraint(
                self.deployment_link[(i, j, c)] <= self.active_link[(i, j)]
            )

            # Find the IDs of the tx and rx sectors that form this link.
            (sec1, sec2) = self.link_to_sectors[(i, j)]

            self.problem.addConstraint(
                self.deployment_link[(i, j, c)]
                <= self.sector_vars[(i, sec1, c)]
            )

            # If receiving sector is a CN, there is only a single sector variable
            rx_sector_var = (
                self.sector_vars[(j, sec2, c)]
                if (j, sec2, c) in self.sector_vars
                else self.sector_vars[(j, sec2, 0)]
            )

            self.problem.addConstraint(
                self.deployment_link[(i, j, c)] <= rx_sector_var
            )

            # Force deployment link to be 1 if link is active and both sectors
            # on the particular channel are active
            self.problem.addConstraint(
                self.deployment_link[(i, j, c)]
                >= self.active_link[(i, j)]
                + self.sector_vars[(i, sec1, c)]
                + rx_sector_var
                - 2
            )

    def create_angle_limit_guideline_constraints(self) -> None:
        """
        If links (i,j) and (i,k) are identified to violate the angle-related
        deployment guidelines, then do not allow both links to be active at the
        same time.
        """
        input_active_links = self.proposed_links | self.existing_links
        for (i, j, k) in self.angle_limit_violating_links:
            if (i, j) in self.active_link and (i, k) in self.active_link:
                # If links (i, j) and (i, k) are being forced to be active
                # because of a user input, then ignore the angle limit
                # constraint for that pair
                if (i, j) in input_active_links and (
                    i,
                    k,
                ) in input_active_links:
                    continue

                if self.number_of_channels == 1:
                    self.problem.addConstraint(
                        self.active_link[(i, j)] + self.active_link[(i, k)] <= 1
                    )
                else:
                    for c in range(self.number_of_channels):
                        self.problem.addConstraint(
                            self.deployment_link[(i, j, c)]
                            + self.deployment_link[(i, k, c)]
                            <= 1
                        )

    def get_interferering_links(
        self,
        tx_site: str,
        rx_site: str,
        rx_sector: str,
    ) -> List[Tuple[str, str]]:
        """
        For the link from site tx_site to rx_site, find all sites and their
        sectors that can transmit to the rx_sector on rx_site.

        If the interfering sector transmits via other links, then that causes
        interference. This function returns all such other links.
        """
        is_rx_cn = self.location_to_type[rx_site] == SiteType.CN

        interfering_links = []
        for in_link in self.incoming_links[rx_site]:
            los_site, _ = in_link

            # Ignore, e.g., wired links as interfering paths
            if (los_site, rx_site) not in self.active_link:
                continue
            # Only consider links with the same receiving sector
            if not is_rx_cn and rx_sector != self.link_to_sectors[in_link][1]:
                continue
            # Only consider links if the interfering path tx sites is active
            # Skip current link as well
            if self.site_vars[los_site] == 0 or los_site == tx_site:
                continue

            if (
                is_rx_cn
                and self.horizontal_scan_range[rx_site] < FULL_ROTATION_ANGLE
            ):
                link_azimuth = none_throws(
                    self.link_to_azimuth[(tx_site, rx_site)][1]
                )
                in_link_azimuth = none_throws(self.link_to_azimuth[in_link][1])
                angle_between = angle_delta(in_link_azimuth, link_azimuth)
                if (
                    angle_between
                    >= self.horizontal_scan_range[rx_site] / 2
                    + SECTOR_LINK_ANGLE_TOLERANCE
                ):
                    continue

            los_sector = self.link_to_sectors[in_link][0]

            for out_link in self.outgoing_links[los_site]:
                # Ignore, e.g., wired links as interferers
                if (los_site, out_link[1]) not in self.active_link:
                    continue
                # Only consider links outgoing from los_sector
                if self.link_to_sectors[out_link][0] != los_sector:
                    continue
                # Only consider links if the interfering rx site is active
                # Skip interfering path as well
                if self.site_vars[out_link[1]] == 0 or out_link[1] == rx_site:
                    continue

                interfering_links.append(out_link)

        return interfering_links

    def create_tdm_compatible_polarity_decisions(self) -> None:
        """
        For a link to cause interference on another link, the two sites
        connected by the interfering path must have opposite polarities.
        Given a link (i, j) and an interfering path (k, j), the interference
        constraint contains terms like (see get_interfering_rsl_expr):
        (tdm(k, l1) + tdm(k, l2) + ...) * p(k, j)
        where links (k, l1), (k, l2), ... cause interference on (i, j)
        and p(k, j) = 1 if sites k and j are opposite polarities and 0
        otherwise. This is equvialent to q(k, i) = 1 if sites k and i are the
        same polarity and 0 otherwise. Because CNs do not have explicit
        polarity assignment, we use q(k, i) instead.
        The term tdm(k, l1) * q(k, i) has to be linearized, i.e. it is replaced
        with a decision varitable tdm_compatible_polarity(i, k, l1) where

        tdm_compatible_polarity(i, k, l1) <= 1 + odd(i) - odd(k)
        tdm_compatible_polarity(i, k, l1) <= 1 - odd(i) + odd(k)
        tdm_compatible_polarity(i, k, l1) <= tdm(k, l1)
        tdm_compatible_polarity(i, k, l1) >= tdm(k, l1) + odd(i) + odd(k) - 2
        tdm_compatible_polarity(i, k, l1) >= tdm(k, l1) - odd(i) - odd(k)
        """
        if self.params.ignore_polarities:
            return

        self.tdm_compatible_polarity = {}
        # For each link and each class, create a binary variable
        for link in self.active_link:
            tx_site, rx_site = link

            if self.site_vars[tx_site] == 0 or self.site_vars[rx_site] == 0:
                continue

            _, rx_sector = self.link_to_sectors[link]

            interfering_links = self.get_interferering_links(
                tx_site, rx_site, none_throws(rx_sector)
            )

            for (tx_interferer, rx_interferer) in interfering_links:
                for channel in range(self.number_of_channels):
                    if (
                        tx_site,
                        tx_interferer,
                        rx_interferer,
                        channel,
                    ) in self.tdm_compatible_polarity:
                        continue

                    tdm_compatible_polarity = xp.var(  # pyre-ignore
                        name=f"tdm_compatible_polarity_{tx_site}_{tx_interferer}_{rx_interferer}_{channel}",
                        vartype=xp.continuous,  # pyre-ignore
                        lb=0,
                        ub=1,
                    )
                    self.problem.addVariable(tdm_compatible_polarity)

                    self.tdm_compatible_polarity[
                        (tx_site, tx_interferer, rx_interferer, channel)
                    ] = tdm_compatible_polarity

                    tdm = self.tdm[(tx_interferer, rx_interferer, channel)]

                    # If polarity of the two sites are opposite, then
                    # tdm_compatible_polarity <= 0 (and <= 2)
                    self.problem.addConstraint(
                        tdm_compatible_polarity
                        <= 1 + self.odd[tx_interferer] - self.odd[tx_site]
                    )
                    self.problem.addConstraint(
                        tdm_compatible_polarity
                        <= 1 - self.odd[tx_interferer] + self.odd[tx_site]
                    )
                    self.problem.addConstraint(tdm_compatible_polarity <= tdm)
                    # If polarity of the two sites are the same, then
                    # tdm_compatible_polarity >= tdm (and >= tdm - 2)
                    # When combined with tdm_compatible_polarity <= tdm, we get
                    # tdm_compatible_polarity = tdm
                    # If polarity of the two sites are opposite, then
                    # tdm_compatible_polarity >= 0 >= tdm - 1.
                    # When combined with tdm_compatible_polarity <= 0, we get
                    # tdm_compatible_polarity = 0
                    self.problem.addConstraint(
                        tdm_compatible_polarity
                        >= tdm + self.odd[tx_interferer] + self.odd[tx_site] - 2
                    )
                    self.problem.addConstraint(
                        tdm_compatible_polarity
                        >= tdm - self.odd[tx_site] - self.odd[tx_interferer]
                    )

    # pyre-fixme
    def get_interfering_rsl_expr(
        self,
        tx_site: str,
        rx_site: str,
        rx_sector: str,
        channel: int,
    ) -> Tuple[Any, float]:
        """
        For the link from site tx_site to rx_site, find all other links that
        cause interference on it via an interfering path that transmits from
        an interfering sector to the rx_sector on the rx_site.

        The amount of interference depends on the proportion of time the
        interfering sector transmits on the other links and hence is scaled by
        tdm.

        This function also computes the maximum possible interfering rsl by
        assuming that tdm = 1 on the interfering links.

        Note: it is worth re-iterating here that for a given sector and given
        link (tdm), the decision variables are repeated for each channel. So if
        there are two channels, each sector and tdm has two corresponding
        decision variables. Thus, we find the interference expression and apply
        the constraint for each channel separately.
        """

        interfering_links = self.get_interferering_links(
            tx_site, rx_site, rx_sector
        )
        neighboring_rsl_expression = []
        max_neighboring_rsl = 0.0
        for (tx_interferer, rx_interferer) in interfering_links:
            in_link = (tx_interferer, rx_site)
            rsl_linear = self.interfering_rsl_linear[in_link]
            if self.params.ignore_polarities:
                tdm_compatible_polarity = self.tdm[
                    (tx_interferer, rx_interferer, channel)
                ]
            else:
                tdm_compatible_polarity = self.tdm_compatible_polarity[
                    (tx_site, tx_interferer, rx_interferer, channel)
                ]
            neighboring_rsl_expression.append(
                rsl_linear * tdm_compatible_polarity
            )
            max_neighboring_rsl += rsl_linear

        return (
            xp.Sum(neighboring_rsl_expression),  # pyre-ignore
            max_neighboring_rsl,
        )

    def create_exact_capacity_constraints(self) -> None:
        """
        This function creates constraints that
        1. Calculates the SINR in terms of tdm decision variables.
        2. Maps this SINR expression to the right interval of SNR thresholds.
        3. Assigns the right throughput value to the link based on the interval
           the SINR falls under.
        """
        # Find MCS class with 0 mbps; add row with 0 throughput if necessary
        cap_gbps = deepcopy(self.cap_gbps)
        snr_linear_inverse = deepcopy(self.snr_linear_inverse)
        zero_row = {}
        for sku, gbps in cap_gbps.items():
            if 0 not in gbps:
                cap_gbps[sku].append(0)
                snr_linear_inverse[sku].append(0)  # value doesn't matter
            zero_row[sku] = cap_gbps[sku].index(0)

        # Decision variable that maps a link to an SNR-level class.
        self.link_capacity_vars = {}
        # For each link and each class, create a binary variable
        for link in self.active_link:
            tx_site, rx_site = link

            # See comment in loop below; the logic here should match that
            if self.site_vars[tx_site] == 0 or self.site_vars[rx_site] == 0:
                continue

            rx_sku = self.sku_location[rx_site]
            len_classes = len(snr_linear_inverse[rx_sku])

            for channel in range(self.number_of_channels):
                self.link_capacity_vars[(tx_site, rx_site, channel)] = {
                    i: xp.var(  # pyre-ignore
                        name=f"link_cap_var_{link}_{channel}_{i}",
                        vartype=xp.binary,  # pyre-ignore
                    )
                    for i in range(len_classes)
                }
        # Add these variables to the ILP problem.
        self.problem.addVariable(self.link_capacity_vars)

        # Create decision variables equal to tdm if the tx interfering site has
        # the opposite polarity of the interfered rx site (or 0 otherwise)
        # This will be used in self.get_interfering_rsl_expr
        self.create_tdm_compatible_polarity_decisions()

        for current_link in self.active_link:
            tx_site, rx_site = current_link

            # If site is not proposed/existing, then the link cannot be proposed
            # and the capacity constraints are not relevant
            # The logic in creating link_capacity_vars should match this
            if self.site_vars[tx_site] == 0 or self.site_vars[rx_site] == 0:
                continue

            tx_sector, rx_sector = self.link_to_sectors[current_link]

            rx_sku = self.sku_location[rx_site]
            len_classes = len(snr_linear_inverse[rx_sku])

            for channel in range(self.number_of_channels):
                current_link_rsl_linear = self.rsl_linear[current_link]
                # Get the RSL expression which is a linear function
                (
                    interfering_rsl_expr,
                    max_neighboring_rsl,
                ) = self.get_interfering_rsl_expr(
                    tx_site,
                    rx_site,
                    none_throws(rx_sector),
                    channel,
                )

                # We need to take the inverse of the SINR value because the
                # term with the decision variables is in the denominator.
                # By taking the inverse, we ensure that this term is a
                # linear function.
                # Current links's RSL value is just a constant, so it is okay
                # for it to be in the denominator.
                current_link_sinr_inverse = (
                    (interfering_rsl_expr + self.noise_linear[rx_sku])
                    / current_link_rsl_linear
                    if current_link_rsl_linear != 0
                    else 0
                )

                # This constraint along with the next one, assigns which SINR
                # threshold the current link falls under (i.e., the appropriate MCS
                # class). Note that snr_linear_inverse is a constant directly
                # derived from the MCS-SNR-Mbps mapping user input. This constraint
                # applies for every link whether or not it is later proposed. In
                # this form, this provides an upper-bound on the SINR inverse on
                # every link; however, links that are not proposed (or, more
                # precisely, links with 0 mbps throughput) can have arbitrarily
                # large SINR inverses (or, equivalently, arbitrarily small SINR).
                # So, if the MCS class chosen corresponds to the 0 mbps throughput,
                # this constraint can be unnecessarily restrictive. Therefore, the
                # snr_linear_inverse corresponding to 0 mbps throughput can be set
                # to a much larger number, in particular, the largest SINR inverse
                # that is possible for that link.
                snr_linear_inverse[rx_sku][zero_row[rx_sku]] = (
                    (max_neighboring_rsl + self.noise_linear[rx_sku])
                    / current_link_rsl_linear
                    if current_link_rsl_linear != 0
                    else 0
                )

                self.problem.addConstraint(
                    current_link_sinr_inverse
                    <= xp.Sum(  # pyre-ignore
                        snr_linear_inverse[rx_sku][i]
                        * self.link_capacity_vars[(tx_site, rx_site, channel)][
                            i
                        ]
                        for i in range(len_classes)
                    )
                )

                # A link can belong to at most one class.
                # If all class variables are zero, then its flow would
                # be pushed to zero as well.
                self.problem.addConstraint(
                    xp.Sum(  # pyre-ignore
                        self.link_capacity_vars[(tx_site, rx_site, channel)][i]
                        for i in range(len_classes)
                    )
                    <= 1
                )

                # Ensure that the tdm decision corresponds to the channel that
                # has positive capacity. Without this, say channel 0 has
                # positive capacity and channel 1 has zero capacity: the flow
                # is bounded by the capacity of the positive capacity channel
                # (see flow constraint below) independent of the tdm (and channel)
                # decision itself. Thus, the optimizer could choose sector/link
                # channel 1 but still have positive flow across the link. This
                # is an alternative approach to taking the product of the MCS
                # class decision and the link decision in the flow constraint
                # (so they are not independent) but this would increase the
                # complexity of the problem in order to linearize it. If there
                # is only one channel, this constraint is trivially satisfied.
                if self.number_of_channels > 1:
                    self.problem.addConstraint(
                        self.tdm[(tx_site, rx_site, channel)]
                        <= 1
                        - self.link_capacity_vars[(tx_site, rx_site, channel)][
                            zero_row[rx_sku]
                        ]
                    )

            # For each channel, the link capacity can only be non-zero for at
            # most one of them. This ensures that the flow is bounded by the
            # sum of the link capacities over all channels. If there is only
            # one channel this constraint is trivially satisfied.
            if self.number_of_channels > 1:
                self.problem.addConstraint(
                    xp.Sum(  # pyre-ignore
                        self.link_capacity_vars[(tx_site, rx_site, channel)][
                            zero_row[rx_sku]
                        ]
                        for channel in range(self.number_of_channels)
                    )
                    >= self.number_of_channels - 1
                )

            # For each link, limit the flow to be the the throughput value
            # assigned by its class. Note that cap_gbps is a constant read
            # from the MCS-SNR-Mbps mapping user input. For multi-channel
            # cases, only one channel can have positive link capacity, so
            # the flow can be bounded by the sum over all channels.
            # Note: this should be scaled by tdm but doing so would create a
            # product of decision variables which can be linearized at the
            # expense of a much larger ILP. This is ignored for now.
            self.problem.addConstraint(
                self.flow[current_link]
                <= xp.Sum(  # pyre-ignore
                    cap_gbps[rx_sku][i]
                    * self.link_capacity_vars[(tx_site, rx_site, channel)][i]
                    for i in range(len_classes)
                    for channel in range(self.number_of_channels)
                )
            )

    def create_coverage_and_weighted_link_objective(self) -> None:
        self.coverage_obj = self._create_coverage_objective_expr()

        if self.params.maximize_common_bandwidth:
            # Scale by length of shortage so it is on roughly
            # equal footing with sum of shortage
            self.coverage_obj *= len(self.shortage)

        # Shorter links have larger weight making them more desirable.
        # This should incentivize CNs to connect to the closer-by POPs.
        weighted_number_of_links = xp.Sum(  # pyre-ignore
            self.link_weights[link] * self.active_link[link]
            for link in self.active_link
        )

        self.problem.setObjective(
            self.max_throughput * self.coverage_obj - weighted_number_of_links,
            sense=xp.minimize,  # pyre-ignore
        )

    def get_link_decisions(
        self, sol: List[float], flow_decisions: Dict[Tuple[str, str], float]
    ) -> Dict[Tuple[str, str], int]:
        link_decisions = self._extract_flat_dictionary(sol, self.active_link)
        for link in self.flow.keys() - self.active_link.keys():
            if (
                self.location_to_type[link[0]] in IMAGINARY_SITE_TYPES
                or self.location_to_type[link[1]] in IMAGINARY_SITE_TYPES
            ):
                continue
            link_decisions[link] = (
                0
                if math.isclose(flow_decisions[link], 0, abs_tol=EPSILON)
                else 1
            )

        # Ensure that wired links are active if both end sites are active
        for (i, j) in self.wired_links:
            if (
                self.location_to_type[i] in IMAGINARY_SITE_TYPES
                or self.location_to_type[j] in IMAGINARY_SITE_TYPES
            ):
                continue
            tx_active = self.site_vars[i]
            rx_active = self.site_vars[j]
            if tx_active == 1 and rx_active == 1:
                link_decisions[(i, j)] = 1
        return link_decisions

    def get_sector_and_channel_decisions(
        self, sol: List[float], link_decisions: Dict[Tuple[str, str], int]
    ) -> Tuple[Dict[Tuple[str, str], int], Dict[Tuple[str, str], int]]:
        sector_channel_decisions = self._extract_flat_dictionary(
            sol, self.sector_vars
        )
        sector_decisions = {}
        channel_decisions = {}
        for i in self.location_sectors:
            for a in self.location_sectors[i]:
                if self.sector_to_type[a] in IMAGINARY_SECTOR_TYPES:
                    continue
                decisions = [
                    sector_channel_decisions[(i, a, c)]
                    for c in range(self.number_of_channels)
                    if (i, a, c) in sector_channel_decisions
                ]
                planner_assert(
                    len(decisions) > 0,
                    "Sector must have at least one channel decisions",
                    OptimizerException,
                )
                decision = sum(decisions)
                planner_assert(
                    decision <= 1,
                    "Sector cannot have multiple channels",
                    OptimizerException,
                )
                sector_decisions[(i, a)] = decision
                if self.sector_to_type[a] != SectorType.DN:
                    continue
                channel_decisions[(i, a)] = (
                    decisions.index(1) if decision == 1 else UNASSIGNED_CHANNEL
                )

        for i in self.location_sectors:
            for a in self.location_sectors[i]:
                if self.sector_to_type[a] != SectorType.CN:
                    continue
                decision = sector_decisions[(i, a)]
                if decision == 0:
                    channel_decisions[(i, a)] = UNASSIGNED_CHANNEL
                    continue
                # Determine CN channel from active incoming link
                incoming_links = [
                    link
                    for link in self.incoming_links[i]
                    if link in self.active_link
                ]
                active_link_cnt = 0
                for link in incoming_links:
                    if link_decisions[link] == 0:
                        continue
                    tx_site = link[0]
                    tx_sector, rx_sector = self.link_to_sectors[link]
                    if a == rx_sector:
                        channel_decisions[(i, a)] = channel_decisions[
                            (tx_site, tx_sector)
                        ]
                        active_link_cnt += 1
                # CNs should only have 1 incoming active link
                planner_assert(
                    active_link_cnt <= 1,
                    "CN sector can only have one incoming link",
                    OptimizerException,
                )
                if active_link_cnt == 0:
                    sector_decisions[(i, a)] = 0
                    channel_decisions[(i, a)] = UNASSIGNED_CHANNEL
        return sector_decisions, channel_decisions

    def extract_solution(self) -> Optional[OptimizationSolution]:
        # If at least one MIP solution is found, then extract it
        if self.problem.attributes.mipsols > 0:
            sol = self.problem.getSolution()
            site_decisions = self.site_vars
            shortage_decisions = self._extract_flat_dictionary(
                sol, self.shortage, binary=False
            )
            tdm_channel_decisions = self._extract_flat_dictionary(
                sol, self.tdm, binary=False
            )
            tdm_decisions = {}
            for (i, j) in self.links:
                if (i, j, 0) not in tdm_channel_decisions:
                    continue
                decisions = [
                    tdm_channel_decisions[(i, j, c)]
                    for c in range(self.number_of_channels)
                ]
                # Verify only 1 channel should have non-zero decision
                bin_decisions = [
                    0 if math.isclose(d, 0, abs_tol=EPSILON) else 1
                    for d in decisions
                ]
                planner_assert(
                    sum(bin_decisions) <= 1,
                    "Sector cannot have multiple channels",
                    OptimizerException,
                )
                tdm_decisions[(i, j)] = sum(decisions)

            odd_site_decisions = (
                self._extract_flat_dictionary(sol, self.odd)
                if not self.params.ignore_polarities
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
                sol, self.flow, binary=False
            )
            flow_decisions = self.prune_loops(flow_decisions)
            if math.isclose(sum(flow_decisions.values()), 0, abs_tol=EPSILON):
                planner_assert(
                    self.common_bandwidth is None
                    or sol[self.problem.getIndex(self.common_bandwidth)] == 0,
                    "No flow in solution, but common bandwidth is positive",
                    OptimizerException,
                )
                logger.info("No flow in solution -- assuming to be degenerate.")
                return None

            link_decisions = self.get_link_decisions(sol, flow_decisions)
            (
                sector_decisions,
                channel_decisions,
            ) = self.get_sector_and_channel_decisions(sol, link_decisions)

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
                    if not self.params.ignore_polarities:
                        odd_site_decisions[loc] = 0
                        even_site_decisions[loc] = 0
                    for sec in self.location_sectors[loc]:
                        sector_decisions[(loc, sec)] = 0
                        channel_decisions[(loc, sec)] = UNASSIGNED_CHANNEL

                for sec in self.location_sectors[loc]:
                    if self.sector_to_type[sec] in IMAGINARY_SECTOR_TYPES:
                        continue
                    if sec not in sectors_with_active_links.get(loc, set()):
                        sector_decisions[(loc, sec)] = 0
                        channel_decisions[(loc, sec)] = UNASSIGNED_CHANNEL

            if self.common_bandwidth is not None:
                common_bandwidth = sol[
                    self.problem.getIndex(self.common_bandwidth)
                ]
                logger.info(f"Common bandwidth = {common_bandwidth}")
                if common_bandwidth == 0:
                    logger.warning(
                        "No common bandwidth found; consider maximizing total network bandwidth"
                    )

            cost = self._extract_cost(site_decisions, sector_decisions)

            return OptimizationSolution(
                link_decisions=link_decisions,
                flow_decisions=flow_decisions,
                site_decisions=site_decisions,
                odd_site_decisions=odd_site_decisions,
                even_site_decisions=even_site_decisions,
                sector_decisions=sector_decisions,
                channel_decisions=channel_decisions,
                tdm_decisions=tdm_decisions,
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
        self.create_active_link_decisions()
        self.create_deployment_link_decisions()
        self.create_sector_decisions()
        self.create_polarity_decisions()
        self.create_demand_site_decisions()

        self.create_ignore_link_flow_constraints()
        self.create_polarity_link_relationship()
        self.create_active_link_polarity_constraints()
        self.create_unit_flow_balance_constraints()
        self.create_decided_link_constraints()
        self.create_sector_site_relationship()
        self.create_same_node_sector_relationship()
        self.create_always_active_sector_constraints()
        self.create_sector_channel_constraints()
        self.create_sector_link_constraints()
        self.create_symmetric_link_constraints()
        self.create_multi_point_contstraints()
        self.create_cn_link_constraints()
        self.create_deployment_link_constraints()
        self.create_angle_limit_guideline_constraints()
        self.create_unit_flow_link_relationship()

        self.create_demand_site_objective()
        end_time = time.time()
        logger.info(
            "Time to construct the demand site optimization model: "
            f"{end_time - start_time:0.2f} seconds."
        )

    def reset_connected_demand_model(self) -> None:
        self.problem.reset()
        self.site_vars = None
        self.flow = None
        self.tdm = None
        self.odd = None
        self.active_link = None
        self.deployment_link = None
        self.sector_vars = None
        self.link_capacity_vars = None
        self.tdm_compatible_polarity = None
        self.demand_vars = None

    def create_unit_flow_link_relationship(self) -> None:
        """
        A link can only have flow if it is selected.
        """
        for (i, j) in self.flow:
            if (i, j) in self.active_link:
                self.problem.addConstraint(
                    self.flow[(i, j)] <= self.active_link[(i, j)]
                )
