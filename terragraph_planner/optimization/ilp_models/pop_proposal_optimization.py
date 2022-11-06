# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import logging
import time
from collections import defaultdict
from copy import deepcopy
from typing import Dict, List, Optional

import xpress as xp
from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import (
    DebugFile,
    SiteType,
    StatusType,
)
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.sector import Sector
from terragraph_planner.common.topology_models.site import Site
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.ilp_models.site_optimization import (
    SiteOptimization,
)
from terragraph_planner.optimization.structs import OptimizationSolution
from terragraph_planner.optimization.topology_demand import (
    connect_demand_to_colocated_sites,
)
from terragraph_planner.optimization.topology_operations import (
    mark_unreachable_components,
)

logger: logging.Logger = logging.getLogger(__name__)


def add_duplicate_pop_to_dn_site(
    topology: Topology, solution: OptimizationSolution
) -> None:
    """
    Once the access network optimization is ran and a solution is found, duplicate all
    activated DN sites to create new POPs (with duplicated links and sectors) to the same
    location. Set corresponding DNs/POPs to CANDIDATE for optimizer to pick.
    """
    sectors_for_sites: Dict[str, List[Sector]] = defaultdict(list)
    for sector in topology.sectors.values():
        sectors_for_sites[sector.site.site_id].append(sector)

    duplicated_sites: Dict[str, Site] = {}
    duplicated_sectors: Dict[str, Sector] = {}
    for site_id in list(topology.sites.keys()):
        site = topology.sites[site_id]
        if (
            solution.site_decisions.get(site_id, 0) == 1
            and site.site_type == SiteType.DN
        ):
            # Create POP at same location as DN
            new_pop = Site(
                site_type=SiteType.POP,
                location=site.location,
                device=site.device,
                status_type=StatusType.CANDIDATE,
                location_type=site.location_type,
                building_id=site.building_id,
                name=site.name + "_POP",
                number_of_subscribers=None,
            )
            topology.add_site(new_pop)
            duplicated_sites[site_id] = new_pop

            # Add sectors to the POP that are equivalent to the one on the DN
            for sector in sectors_for_sites[site_id]:
                new_sector = Sector(
                    site=new_pop,
                    node_id=sector.node_id,
                    position_in_node=sector.position_in_node,
                    ant_azimuth=sector.ant_azimuth,
                    status_type=StatusType.CANDIDATE,
                    channel=sector.channel,
                )
                topology.add_sector(new_sector)
                duplicated_sectors[sector.sector_id] = new_sector

    for dn_id, pop_site in duplicated_sites.items():
        dn_site = topology.sites[dn_id]
        for neighbor_site in topology.get_successor_sites(dn_site):
            # Do not duplicate link if the other site is POP
            if neighbor_site.site_type == SiteType.POP:
                continue
            # Duplicate DN -> neighbor link
            tx_link = none_throws(
                topology.get_link_by_site_ids(dn_id, neighbor_site.site_id)
            )
            if tx_link.tx_sector is None or tx_link.rx_sector is None:
                continue
            new_tx_link = Link(
                tx_site=pop_site,
                rx_site=neighbor_site,
                tx_sector=duplicated_sectors[tx_link.tx_sector.sector_id],
                rx_sector=tx_link.rx_sector,
                status_type=StatusType.CANDIDATE,
                is_wireless=tx_link.is_wireless,
                confidence_level=tx_link.confidence_level,
            )
            new_tx_link.link_budget = deepcopy(tx_link.link_budget)
            topology.add_link(new_tx_link)

        for neighbor_site in topology.get_predecessor_sites(dn_site):
            # Do not duplicate link if the other site is POP
            if neighbor_site.site_type == SiteType.POP:
                continue
            # Duplicate neighbor -> DN link
            rx_link = none_throws(
                topology.get_link_by_site_ids(neighbor_site.site_id, dn_id)
            )
            if rx_link.tx_sector is None or rx_link.rx_sector is None:
                continue
            new_rx_link = Link(
                tx_site=neighbor_site,
                rx_site=pop_site,
                tx_sector=rx_link.tx_sector,
                rx_sector=duplicated_sectors[rx_link.rx_sector.sector_id],
                status_type=StatusType.CANDIDATE,
                is_wireless=tx_link.is_wireless,
                confidence_level=tx_link.confidence_level,
            )
            new_rx_link.link_budget = deepcopy(rx_link.link_budget)
            topology.add_link(new_rx_link)

    # Add the new POPs to the demand connected to their corresponding DNs
    duplicated_site_id_map = {
        dn_id: {pop_site.site_id}
        for dn_id, pop_site in duplicated_sites.items()
    }
    connect_demand_to_colocated_sites(topology, duplicated_site_id_map)


def _compute_access_candidate_topology(topology: Topology) -> Topology:
    """
    Assume that all DNs can be used as POPs and the only links are from POPs to CNs.
    This function converts DNs into POPs and deletes all backhaul links.
    """
    topology_copy = deepcopy(topology)
    colocated_sites = topology_copy.get_colocated_sites()

    # Find DNs that are co-located with other POPs
    dns_on_pops = set()
    for sites in colocated_sites.values():
        any_pops = any(
            topology_copy.sites[site_id].site_type == SiteType.POP
            for site_id in sites
        )
        if any_pops:
            for site_id in sites:
                if topology_copy.sites[site_id].site_type == SiteType.DN:
                    dns_on_pops.add(site_id)

    for site in topology_copy.sites.values():
        if site.site_type == SiteType.DN:
            # No need to remove the DN if it's co-located with a POP because
            # its incoming links will be removed
            if site.site_id not in dns_on_pops:
                # This is a hacky way to convert the DN into a POP; however, for
                # the purposes here, it is a convenient work-around. Ideally,
                # a copy of the site would be created and added along with copies
                # of all the relevant links/sectors. Because we know that there is
                # no POP at the same location, there won't be a site_id collision
                # and, furthermore, this topology is local to this optimization.
                site._site_type = SiteType.POP

    links_to_delete = []
    for link in topology_copy.links.values():
        rx_site_type = topology_copy.sites[link.rx_site.site_id].site_type
        if rx_site_type != SiteType.CN:
            links_to_delete.append(link.link_id)

    for link_id in links_to_delete:
        topology_copy.remove_link(link_id)

    # All POPs are connected to CNs, so max hops is irrelevant
    mark_unreachable_components(topology_copy, maximum_hops=None)
    return topology_copy


class POPProposalNetwork(SiteOptimization):
    def __init__(self, topology: Topology, params: OptimizerParams) -> None:
        self.input_topology = topology
        access_topology = _compute_access_candidate_topology(topology)

        # No site polarities for access network optimization
        # Do not propose all POPs
        # Connected demand site optimization is not currently set up to handle
        # POP constraints, so do not run common bandwidth
        ignore_polarities = params.ignore_polarities
        always_active_pops = params.always_active_pops
        maximize_common_bandwidth = params.maximize_common_bandwidth
        params.ignore_polarities = True
        params.always_active_pops = False
        params.maximize_common_bandwidth = False

        super(POPProposalNetwork, self).__init__(access_topology, params, set())

        # Restore parameter values
        params.ignore_polarities = ignore_polarities
        params.always_active_pops = always_active_pops
        params.maximize_common_bandwidth = maximize_common_bandwidth

    def create_pop_constraint(self) -> None:
        num_input_pops = len(
            [
                site.site_id
                for site in self.input_topology.sites.values()
                if site.site_type == SiteType.POP
                and site.status_type not in StatusType.inactive_status()
            ]
        )
        num_access_pops = len(
            [
                site.site_id
                for site in self.topology.sites.values()
                if site.site_type == SiteType.POP
                and site.status_type not in StatusType.inactive_status()
            ]
        )

        # Number of POPs to be proposed should equal to the number of extra
        # POPs plus the input POPs. That number should not exceed the number of
        # POPs in the access topology.
        num_pops = min(
            self.params.number_of_extra_pops + num_input_pops, num_access_pops
        )
        if num_pops == 0:
            return None

        self.problem.addConstraint(
            xp.Sum(
                self.site_vars[loc]
                for loc in self.locations
                if loc in self.type_sets[SiteType.POP]
            )
            == num_pops
        )

    def add_pop_constraint_coverage_objective(self) -> None:
        # Ensure total number of POPs is less than prescribed limit
        self.create_pop_constraint()
        # Create maximum coverage objective function
        self.create_coverage_objective()

    def propose_pops(self) -> Optional[OptimizationSolution]:
        """
        This function returns the maximum coverage access network that has
        at most number_of_extra_pops + number_of_provided_pops many active POPs.
        """
        logger.info("Finding a set of POPs to propose.")
        start_time = time.time()

        # Set status of provided POPs to proposed in searching extra POPs
        for site in self.input_topology.sites.values():
            if (
                site.site_type == SiteType.POP
                and site.status_type not in StatusType.inactive_status()
            ):
                self.proposed_sites.add(site.site_id)
                # Modifying the topology site status directly is not necessary
                # but do it just to be consistent
                self.topology.sites[
                    site.site_id
                ].status_type = StatusType.PROPOSED

        self.set_up_problem_skeleton(
            rel_stop=self.params.pop_proposal_rel_stop,
            max_time=self.params.pop_proposal_max_time,
        )
        self.add_pop_constraint_coverage_objective()
        end_time = time.time()
        logger.info(
            "Time to construct the propose POPs optimization model: "
            f"{end_time - start_time:0.2f} seconds."
        )

        self.dump_problem_file_for_debug_mode(
            DebugFile.POP_PROPOSAL_OPTIMIZATION
        )

        logger.info("Solving POP proposal optimization")
        start_time = time.time()
        self.problem.solve()
        end_time = time.time()
        logger.info(
            "Time to solve the POP proposal optimization: "
            f"{end_time - start_time:0.2f} seconds."
        )

        logger.info("Extracting POP proposal solution")
        start_time = time.time()
        solution = self.extract_solution()
        end_time = time.time()
        logger.info(
            "Time for extracting POP proposal solution: "
            f"{end_time - start_time:0.2f} seconds."
        )
        return solution
