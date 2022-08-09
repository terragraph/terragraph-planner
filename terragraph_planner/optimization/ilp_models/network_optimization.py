# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import itertools
import logging
import os
from time import time
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
from terragraph_planner.common.exceptions import OptimizerException
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.common.utils import current_system_params
from terragraph_planner.optimization.constants import (
    DEMAND,
    EPSILON,
    IMAGINARY_SECTOR_TYPES,
    IMAGINARY_SITE_TYPES,
    SUPERSOURCE,
)
from terragraph_planner.optimization.ilp_models.optimization_setup import (
    OptimizationSetup,
)
from terragraph_planner.optimization.topology_operations import (
    get_reachable_demand_sites,
)

logger: logging.Logger = logging.getLogger(__name__)


class NetworkOptimization(OptimizationSetup):
    """
    The class structure that has all the necessary information of the topology
    @param topology Topology
    @param OptimizerParams struct params
    """

    def __init__(self, topology: Topology, params: OptimizerParams) -> None:
        super(NetworkOptimization, self).__init__(topology, params)
        self.check_pop_feasibility(topology)
        self.check_demand_feasibility(topology)

        # Due to numerical precisions issues, summing directly over the set of
        # demand sites, which is not in the same order from run to run, can
        # result in very slight differences in output
        self.max_throughput: float = sum(
            self.demand_at_location[k]
            for k in self.locations
            if k in self.type_sets[DEMAND]
        )

        # Set the number of channels from parameters. This might be overwritten
        # by derived classes
        self.number_of_channels: int = self.params.number_of_channels

        # Variables created when building the optimization model
        self.problem = None  # pyre-fixme
        self.site_vars = None  # pyre-fixme
        self.sector_vars = None  # pyre-fixme
        self.flow = None  # pyre-fixme
        self.tdm = None  # pyre-fixme
        self.odd = None  # pyre-fixme
        self.shortage = None  # pyre-fixme
        self.common_bandwidth = None  # pyre-fixme
        self.connected_demand_sites = None  # pyre-fixme
        self.coverage_constraint = None  # pyre-fixme
        self.coverage_obj = None  # pyre-fixme

        # Variables created for demand site optimization model
        self.demand_vars = None  # pyre-fixme
        self.ignore_links: Set[Tuple[str, str]] = set()
        self.ignore_sites: Set[str] = set()

    def check_pop_feasibility(self, topology: Topology) -> None:
        """
        The topology is infeasible if there are no POPs or the POPs do not have
        any outgoing links of positive capacity.
        """
        for pop_site in self.type_sets[SiteType.POP]:
            if (
                len(self.outgoing_links[pop_site]) > 0
                and sum(
                    self.link_capacities[link_pair]
                    for link_pair in self.outgoing_links[pop_site]
                )
                > 0
            ):
                return
        raise OptimizerException(
            "No POP has a positive capacity outgoing link."
        )

    def check_demand_feasibility(self, topology: Topology) -> None:
        """
        The topology is infeasible if the sites connected to the demand sites
        do not have any incoming links of positive capacity.
        """
        for demand in topology.demand_sites.values():
            for site in demand.connected_sites:
                if (
                    len(self.incoming_links[site.site_id]) > 0
                    and sum(
                        self.link_capacities[link]
                        for link in self.incoming_links[site.site_id]
                    )
                    > 0
                ):
                    return
        raise OptimizerException(
            "No CN or demand-connected DN has a positive capacity incoming link."
        )

    def _get_ignore_links(self) -> Set[Tuple[str, str]]:
        ignore_links = set()
        for link in self.topology.links.values():
            if link.capacity <= 0:
                ignore_links.add((link.tx_site.site_id, link.rx_site.site_id))

        return ignore_links

    def _get_ignore_sites(self) -> Set[str]:
        return set()

    def _get_reachable_demand_sites_with_constraints(
        self,
    ) -> Optional[Set[str]]:
        """
        Identify connectable demand sites via optimization rather than using
        graph-based search techniques. This is useful when there are
        constraints that need to be applied such as polarity constraints or
        edge-based constraints like P2MP.
        """
        self.ignore_links = self._get_ignore_links()
        self.ignore_sites = self._get_ignore_sites()
        return self.solve_connected_demand()

    def _get_reachable_demand_sites_without_constraints(
        self, status_filter: Optional[Set[StatusType]] = None
    ) -> Set[str]:
        """
        Identify connectable demand sites via standard graph-based searching.
        As long as no additional constraints such as polarity or P2MP are
        required, this is the preferred approach
        """
        if status_filter is None:
            status_filter = StatusType.reachable_status()
        ignore_links = self._get_ignore_links()
        ignore_sites = self._get_ignore_sites()
        sites_status: Dict[str, StatusType] = {}
        links_status: Dict[Tuple[str, str], StatusType] = {}
        for (tx_site_id, rx_site_id) in ignore_links:
            link = self.topology.get_link_by_site_ids(tx_site_id, rx_site_id)
            if link is not None:
                links_status[(tx_site_id, rx_site_id)] = link.status_type
                link.status_type = StatusType.UNREACHABLE
        for site_id in ignore_sites:
            site = self.topology.sites.get(site_id, None)
            if site is not None:
                sites_status[site_id] = site.status_type
                site.status_type = StatusType.UNREACHABLE
        reachable_demand_sites = get_reachable_demand_sites(
            self.topology, status_filter
        )
        for (tx_site_id, rx_site_id) in ignore_links:
            link = none_throws(
                self.topology.get_link_by_site_ids(tx_site_id, rx_site_id)
            )
            link.status_type = links_status[(tx_site_id, rx_site_id)]
        for site_id in ignore_sites:
            site = none_throws(self.topology.sites.get(site_id, None))
            site.status_type = sites_status[site_id]
        return {
            demand_id if num_dem == 0 else demand_id + "_" + str(num_dem)
            for demand_id, demand_data in self.topology.demand_sites.items()
            if demand_id in reachable_demand_sites
            for num_dem in range(demand_data.num_sites)
        }

    def create_model(
        self,
        rel_stop: float,
        max_time: float,
    ) -> None:
        self.problem = xp.problem()  # pyre-ignore
        self.problem.setprobname(self.__class__.__name__)

        if rel_stop > 0:
            self.problem.setControl("miprelstop", rel_stop)
            logger.info(
                "Setting relative stopping criteria to "
                f"{rel_stop * 100}% of optimal"
            )

        # Set the optimizer time limit. It is made negative to force solver to
        # exit rather than for it to continue searching for integer solution if
        # not yet found (Xpress convention)
        max_time = abs(max_time)
        self.problem.setControl("maxtime", -max_time * 60)
        logger.info(f"Setting maximum optimizer runtime to {max_time} minutes")

        self.problem.setControl("treememorylimit", 15000)

        if self.params.num_threads is not None:
            self.problem.setControl("threads", self.params.num_threads)
            logger.info(
                f"Setting number of threads to {self.params.num_threads}"
            )

    def did_problem_timeout(self) -> bool:
        """
        After a planning problem is solved, query the solution status and check
        if the problem timed out. In particular, if the status is 1,2,3 or 4,
        then the global search was incomplete indicating likely time out.
        More details on the statuses according to Xpress documentation:
        1 - The initial continuous relaxation has not been solved and no integer
            solution has been found
        2 - The initial continuous relaxation has been solved and no integer
            solution has been found
        3 - No integer solution found
        4 - An integer solution has been found
        Status 4 indicates a solution was found, but is not necessarily optimal.
        """
        timed_out_statuses = {1, 2, 3, 4}
        return (
            self.problem is not None
            and self.problem.getAttrib("mipstatus") in timed_out_statuses
        )

    def create_site_decisions(self) -> None:
        # Binary variable -- 1 if site i is selected, 0 otherwise
        # Called UseLocation in Mosel
        self.site_vars = {
            loc: xp.var(name=f"site_{loc}", vartype=xp.binary)  # pyre-ignore
            for loc in self.locations
            if self.location_to_type[loc] not in IMAGINARY_SITE_TYPES
        }
        self.problem.addVariable(self.site_vars)

    def create_flow_decisions(self) -> None:
        # Flow on link (i,j)
        self.flow = {
            (i, j): xp.var(  # pyre-ignore
                name=f"flow_{i}_{j}", vartype=xp.continuous  # pyre-ignore
            )
            for (i, j) in self.links
        }
        self.problem.addVariable(self.flow)

    def create_tdm_decisions(self) -> None:
        # Time division multiplexing on link (i,j). A continuous variable
        # that is between 0 and 1. This represents the percent of time a sector
        # communicates with its connecting sector over the link.
        # Like sectors, tdm is equipped with a channel, so effectively the same
        # connection is repeated for each channel; however sector channel
        # constraints combined with sector tdm constraints ensure only one tdm
        # channel is chosen (corresponding to the sector channel). This is
        # equivalent to splitting each sector into multiple sectors (based on
        # the number of channels) and connecting them each with links with
        # their own tdm. This is particularly useful for modeling things like
        # interference where identifying if two sectors/links are on the same
        # channel is critical.
        self.tdm = {
            (i, j, c): xp.var(  # pyre-ignore
                name=f"tdm_{i}_{j}_{c}",
                vartype=xp.continuous,  # pyre-ignore
                lb=0,
                ub=1,
            )
            for (i, j) in self.links
            for c in range(self.number_of_channels)
            if self.location_to_type[i] not in IMAGINARY_SITE_TYPES
            and self.location_to_type[j] not in IMAGINARY_SITE_TYPES
            and (i, j) not in self.wired_links
        }
        self.problem.addVariable(self.tdm)

    def create_polarity_decisions(self) -> None:
        if self.params.ignore_polarities:
            return

        # A proposed site is either odd or even
        self.odd = {
            loc: xp.var(name=f"odd_{loc}", vartype=xp.binary)  # pyre-ignore
            for loc in self.locations
            if self.location_to_type[loc] in SiteType.dist_site_types()
        }

        self.problem.addVariable(self.odd)

    def create_shortage_decisions(self) -> None:
        # Nonnegative variable that represents shortage of demand at a
        # demand site
        self.shortage = {
            loc: xp.var(  # pyre-ignore
                name=f"shortage_{loc}",
                vartype=xp.continuous,  # pyre-ignore
                lb=0,
                ub=self.demand_at_location[loc],
            )
            for loc in self.locations
            if loc in self.type_sets[DEMAND]
        }

        self.problem.addVariable(self.shortage)

    def create_sector_decisions(self) -> None:
        # Binary variable -- 1 if sector a on site i is used, 0 otherwise
        # Called UseSector in Mosel
        #
        # Each sector is equipped with a channel as well, so the same sector is
        # repeated for each channel; however sector channel constraints will
        # limit only one channel from being chosen. Similarly, links (where
        # applicable) from those sectors are equipped with a channel as well.
        # This is equivalent to splitting each sector into multiple sectors
        # (based on the number of channels) and connecting them each with
        # links. This is particularly useful for modeling things like
        # interference where identifying if two sectors/links are on the same
        # channel is critical.
        self.sector_vars = {
            (i, a, c): xp.var(  # pyre-ignore
                name=f"s_{i}_{a}_{c}", vartype=xp.binary  # pyre-ignore
            )
            for i in self.location_sectors
            for a in self.location_sectors[i]
            if self.sector_to_type[a] not in IMAGINARY_SECTOR_TYPES
            for c in range(
                self.number_of_channels
                # Only real DN sectors need channels
                # CNs take channel of serving DN
                if self.sector_to_type[a] == SectorType.DN
                else 1
            )
        }
        self.problem.addVariable(self.sector_vars)

    def create_sector_constraints(self) -> None:
        self.create_tdm_sector_relationship()
        self.create_sector_site_relationship()
        self.create_same_node_sector_relationship()
        self.create_always_active_sector_constraints()
        self.create_sector_channel_constraints()

    def create_sector_channel_constraints(self) -> None:
        if self.number_of_channels == 1:
            return

        # Only one channel can be selected
        for loc in self.location_sectors:
            for sec in self.location_sectors[loc]:
                if self.sector_to_type[sec] != SectorType.DN:
                    continue
                sectors = [
                    self.sector_vars[loc, sec, channel]
                    for channel in range(self.number_of_channels)
                ]
                if len(sectors) > 1:
                    self.problem.addConstraint(
                        xp.Sum(sectors) <= 1  # pyre-ignore
                    )

    def create_always_active_sector_constraints(self) -> None:
        for loc in self.locations:
            # If there are already fixed (chosen to be active) sectors,
            # push this decision to be followed.
            if loc in self.proposed_sectors:
                for sec in self.proposed_sectors[loc]:
                    # Implicit assumption: Only sectors with already-set values
                    # exist in active_sectors dictionary
                    self.problem.addConstraint(
                        xp.Sum(  # pyre-ignore
                            self.sector_vars[(loc, sec, channel)]
                            for channel in range(self.number_of_channels)
                            if (loc, sec, channel) in self.sector_vars
                        )
                        == 1
                    )

    def create_sector_site_relationship(self) -> None:
        # If a site is inactive then no sectors on it can be active
        for loc in self.locations:
            if self.location_to_type[loc] in IMAGINARY_SITE_TYPES:
                continue
            for sec in self.location_sectors[loc]:
                if self.sector_to_type[sec] in IMAGINARY_SECTOR_TYPES:
                    continue
                self.problem.addConstraint(
                    xp.Sum(  # pyre-ignore
                        self.sector_vars[(loc, sec, channel)]
                        for channel in range(self.number_of_channels)
                        if (loc, sec, channel) in self.sector_vars
                    )
                    <= self.site_vars[loc]
                )

    def create_same_node_sector_relationship(self) -> None:
        # If a sector in a node is active, all sectors in that node are active.
        nodes = {}
        for loc in self.locations:
            for sec in self.location_sectors[loc]:
                if self.sector_to_type[sec] in IMAGINARY_SECTOR_TYPES:
                    continue  # skip imaginary sectors - they're their own thing
                node_id = self.topology.sectors[sec].node_id
                if (loc, sec) in self.sector_vars:
                    nodes.setdefault((loc, node_id), []).append((loc, sec))
        for linked_sectors in nodes.values():
            for s1, s2 in itertools.combinations(linked_sectors, 2):
                loc1, sec1 = s1
                loc2, sec2 = s2
                self.problem.addConstraint(
                    xp.Sum(  # pyre-ignore
                        self.sector_vars[loc1, sec1, channel]
                        for channel in range(self.number_of_channels)
                        if (loc1, sec1, channel) in self.sector_vars
                    )
                    == xp.Sum(  # pyre-ignore
                        self.sector_vars[loc2, sec2, channel]
                        for channel in range(self.number_of_channels)
                        if (loc1, sec1, channel) in self.sector_vars
                    )
                )

    def create_tdm_sector_relationship(self) -> None:
        # For each sector, the sum of tdm values for incoming and outgoing
        # signals can not be greater than one.
        for i in self.locations:
            if self.location_to_type[i] in IMAGINARY_SITE_TYPES:
                continue
            for sec in self.location_sectors[i]:
                for channel in range(self.number_of_channels):
                    if (i, sec, channel) not in self.sector_vars:
                        continue
                    sum_tdm_outgoing = 0
                    for _, j in self.outgoing_links[i]:
                        tx_sector = self.link_to_sectors[(i, j)][0]
                        if tx_sector is None or tx_sector != sec:
                            continue
                        if (i, j, channel) in self.tdm:
                            sum_tdm_outgoing += self.tdm[(i, j, channel)]

                    sum_tdm_incoming = 0
                    for j, _ in self.incoming_links[i]:
                        rx_sector = self.link_to_sectors[(j, i)][1]
                        if rx_sector is None or rx_sector != sec:
                            continue
                        if (j, i, channel) in self.tdm:
                            sum_tdm_incoming += self.tdm[(j, i, channel)]

                    if not isinstance(sum_tdm_outgoing, (int, float)):
                        self.problem.addConstraint(
                            sum_tdm_outgoing
                            <= self.sector_vars[(i, sec, channel)]
                        )
                    if not isinstance(sum_tdm_incoming, (int, float)):
                        self.problem.addConstraint(
                            sum_tdm_incoming
                            <= self.sector_vars[(i, sec, channel)]
                        )

    def create_pop_load_constraints(self) -> None:
        pop_capacity = self.params.pop_capacity
        for loc in self.locations:
            if loc in self.type_sets[SiteType.POP]:
                outgoing_flow = (
                    xp.Sum(  # pyre-ignore
                        self.flow[link] for link in self.outgoing_links[loc]
                    )
                    if len(self.outgoing_links[loc]) > 0
                    else None
                )

                if outgoing_flow is not None:
                    self.problem.addConstraint(outgoing_flow <= pop_capacity)

    def create_tdm_flow_relationship(self) -> None:
        for (i, j) in self.links:
            link_capacity = self.link_capacities[(i, j)]
            if (i, j, 0) in self.tdm:
                # Flow on edge can not be more than the effective edge capacity
                # which is tdm x edge_capacity
                self.problem.addConstraint(
                    self.flow[(i, j)]
                    <= link_capacity
                    * xp.Sum(  # pyre-ignore
                        self.tdm[(i, j, channel)]
                        for channel in range(self.number_of_channels)
                    )
                )
            else:
                # The flow on any edge should not exceed max throughput
                self.problem.addConstraint(
                    self.flow[(i, j)] <= min(link_capacity, self.max_throughput)
                )

    def create_tdm_polarity_relationship(self) -> None:
        if self.params.ignore_polarities:
            return

        input_active_links = self.proposed_links | self.existing_links
        for (i, j) in self.links:
            # If link (i, j) is set to be active by the user, opposite polarity
            # enforcement will be handled separately (partly because in case
            # tdm is 0 for such a link, we still want the constraint to apply)
            if (i, j) in input_active_links:
                continue
            if (i, j) in self.wired_links:
                continue
            # If tdm (i, j) is strictly larger than zero, then the polarity of
            # i and j has to be opposite
            if (
                self.location_to_type[i] in SiteType.dist_site_types()
                and self.location_to_type[j] in SiteType.dist_site_types()
            ):
                # If both are even, then tdm <= odd_i + odd_j = 0
                # If both are odd, then tdm <= 2 - odd_i - odd_j = 0
                # The second constraint is equivalent to tdm <= even_i + even_j
                self.problem.addConstraint(
                    xp.Sum(  # pyre-ignore
                        self.tdm[(i, j, channel)]
                        for channel in range(self.number_of_channels)
                    )
                    <= self.odd[i] + self.odd[j]
                )
                self.problem.addConstraint(
                    xp.Sum(  # pyre-ignore
                        self.tdm[(i, j, channel)]
                        for channel in range(self.number_of_channels)
                    )
                    <= 2 - self.odd[i] - self.odd[j]
                )

    # pyre-fixme
    def _get_incoming_flow(self, loc: str) -> Optional[Any]:
        """
        Returns the sum of flow variables of incoming links if there are
        incoming links. Otherwise, returns None.
        """
        incoming_flow = (
            xp.Sum(  # pyre-ignore
                self.flow[link] for link in self.incoming_links[loc]
            )
            if len(self.incoming_links[loc]) > 0
            else None
        )
        return incoming_flow

    # pyre-fixme
    def _get_outgoing_flow(self, loc: str) -> Optional[Any]:
        """
        Returns the sum of flow variables of incoming links if there are
        incoming links. Otherwise, returns None.
        """
        outgoing_flow = (
            xp.Sum(  # pyre-ignore
                self.flow[link] for link in self.outgoing_links[loc]
            )
            if len(self.outgoing_links[loc]) > 0
            else None
        )
        return outgoing_flow

    # pyre-fixme
    def _get_net_flow(self, loc: str) -> Optional[Any]:
        """
        Returns the difference of incoming flow and outgoing flow variables
        if there are incoming OR outgoing links to loc.
        Otherwise, returns None.
        """
        incoming_flow = self._get_incoming_flow(loc)
        outgoing_flow = self._get_outgoing_flow(loc)
        if incoming_flow is None and outgoing_flow is None:
            return None
        incoming_flow = incoming_flow if incoming_flow else 0
        outgoing_flow = outgoing_flow if outgoing_flow else 0
        return incoming_flow - outgoing_flow

    # pyre-fixme
    def _get_rhs_for_flow_balance(self, loc: str) -> Any:
        if self.location_to_type[loc] == DEMAND:
            return self.demand_at_location[loc] - self.shortage[loc]
        elif self.location_to_type[loc] == SUPERSOURCE:
            total_shortage = (
                xp.Sum(  # pyre-ignore
                    self.shortage[loc]
                    for loc in self.locations
                    if loc in self.type_sets[DEMAND]
                )
                if len(self.type_sets[DEMAND]) > 0
                else 0
            )
            return -self.max_throughput + total_shortage
        else:
            return 0

    def create_flow_site_relationship(self) -> None:
        for loc in self.locations:
            incoming_flow = self._get_incoming_flow(loc)
            outgoing_flow = self._get_outgoing_flow(loc)
            site_var = (
                self.site_vars[loc]
                if self.location_to_type[loc] not in IMAGINARY_SITE_TYPES
                else 1
            )
            if incoming_flow is not None:
                self.problem.addConstraint(
                    incoming_flow <= self.max_throughput * site_var
                )
            if outgoing_flow is not None:
                self.problem.addConstraint(
                    outgoing_flow <= self.max_throughput * site_var
                )

    def create_flow_balance_with_shortage(self) -> None:
        # Flow balance constraints
        for loc in self.locations:
            # Net flow on location loc
            net_flow = self._get_net_flow(loc)
            right_hand_side = self._get_rhs_for_flow_balance(loc)
            # If net_flow is None, then flow balance is irrelevant
            if net_flow is not None:
                self.problem.addConstraint(net_flow == right_hand_side)

    def _get_max_and_valid_site_types_from_colocated_sites(
        self, sites: Set[str]
    ) -> Tuple[SiteType, Set[SiteType]]:
        # Site type order is CN < DN < POP. Valid site types are those that
        # match the max site type or are greater.
        max_site_type = SiteType.CN
        for loc in sites:
            site_type = self.location_to_type[loc]
            if site_type == SiteType.DN and max_site_type != SiteType.POP:
                max_site_type = SiteType.DN
            elif site_type == SiteType.POP:
                max_site_type = SiteType.POP

        # CN sites can be upgraded to a DN or POP
        # DN/POP sites cannot have their type changed
        valid_site_types = set()
        if max_site_type == SiteType.CN:
            valid_site_types.add(SiteType.CN)
            valid_site_types.add(SiteType.DN)
            valid_site_types.add(SiteType.POP)
        elif max_site_type == SiteType.DN:
            valid_site_types.add(SiteType.DN)
        elif max_site_type == SiteType.POP:
            valid_site_types.add(SiteType.POP)

        return max_site_type, valid_site_types

    def create_colocated_site_relationship(self) -> None:
        # The logic for co-located sites must match that of _get_ignore_sites()
        # in SiteOptimization and the logic for finding adversarial links.

        input_active_sites = self.proposed_sites | self.existing_sites
        for (i, j) in self.proposed_links | self.existing_links:
            input_active_sites.add(i)
            input_active_sites.add(j)
        if self.params.always_active_pops:
            for i in self.locations:
                if (
                    i in self.type_sets[SiteType.POP]
                    and i not in self.inactive_sites
                ):
                    input_active_sites.add(i)
        for locs in self.colocated_locations.values():
            if len(locs) <= 1:
                continue

            active_colocated_sites = input_active_sites.intersection(set(locs))

            if len(active_colocated_sites) == 0:
                # If none of the co-located sites are active, then only one can
                # be picked
                self.problem.addConstraint(
                    xp.Sum(self.site_vars[loc] for loc in locs)  # pyre-ignore
                    <= 1
                )
            else:
                # If there are active co-located sites, then a CN can be
                # upgraded to a DN/POP or a DN can be upgraded to a POP
                (
                    max_site_type,
                    valid_site_types,
                ) = self._get_max_and_valid_site_types_from_colocated_sites(
                    active_colocated_sites
                )

                # At least one of the active co-located sites or upgraded sites
                # must be picked
                self.problem.addConstraint(
                    xp.Sum(self.site_vars[loc] for loc in locs)  # pyre-ignore
                    == 1
                )
                # CN site can be upgraded to a DN but one CN cannot be exchanged
                # for another (i.e., if devices are different).
                # DN/POP sites cannot be upgraded or downgraded or exchanged
                # for another equivalent site type.
                invalid_sites = [
                    self.site_vars[loc]
                    for loc in locs
                    if self.location_to_type[loc] not in valid_site_types
                    or (
                        self.location_to_type[loc] == max_site_type
                        and loc not in input_active_sites
                    )
                ]
                if len(invalid_sites) > 0:
                    self.problem.addConstraint(
                        xp.Sum(invalid_sites) == 0  # pyre-ignore
                    )

    def create_cost_constraint(self) -> None:
        sector_vars = {}
        for loc in self.location_sectors:
            for sec in self.location_sectors[loc]:
                sector_vars[(loc, sec)] = xp.Sum(  # pyre-ignore
                    self.sector_vars[(loc, sec, channel)]
                    for channel in range(self.number_of_channels)
                    if (loc, sec, channel) in self.sector_vars
                )
        total_cost = self._extract_cost(self.site_vars, sector_vars)
        budget = self.params.budget if self.params.budget else 0
        # If the total cost is a function of decision variables, then
        # add the budget constraint
        if not isinstance(total_cost, (int, float)):
            self.problem.addConstraint(total_cost <= budget)

    def create_cost_objective(self) -> None:
        sector_vars = {}
        for loc in self.location_sectors:
            for sec in self.location_sectors[loc]:
                sector_vars[(loc, sec)] = xp.Sum(  # pyre-ignore
                    self.sector_vars[(loc, sec, channel)]
                    for channel in range(self.number_of_channels)
                    if (loc, sec, channel) in self.sector_vars
                )
        total_cost = self._extract_cost(self.site_vars, sector_vars)
        self.problem.setObjective(total_cost)

    # pyre-fixme
    def _extract_cost(
        self,
        site_decisions: Dict[str, Any],
        sector_decisions: Dict[Tuple[str, str], Any],  # pyre-fixme
    ) -> Any:
        # This function is used to compute the cost of a network given the site
        # and sector decisions. To ensure consistency with the budget used in
        # setting the cost constraint, this function is also called by
        # create_cost_constraint. In that case, site_decisions and
        # sector_decisions are binary decision variables and thus this function
        # is written in such a way to work for both contexts.
        total_cost = 0
        for i in self.locations:
            if self.location_to_type[i] in IMAGINARY_SITE_TYPES:
                continue
            if i not in self.existing_sites:
                total_cost += (
                    self.cost_site[self.location_to_type[i]] * site_decisions[i]
                )
                for a in self.location_sectors[i]:
                    if self.sector_to_type[a] in IMAGINARY_SECTOR_TYPES:
                        continue
                    total_cost += (
                        self.cost_sector[i][a] * sector_decisions[(i, a)]
                    )
        return total_cost

    def create_coverage_constraint(self) -> None:
        if len(self.type_sets[DEMAND]) == 0:
            return
        if self.params.maximize_common_bandwidth:
            # Common bandwidth cannot exceeed the minimum of the demand at all
            # connectable demand sites. Thus, x% coverage would mean that the
            # bandwidth at every demand site is at least x% of the minimum
            # demand.
            min_demand = min(
                [
                    self.demand_at_location[loc]
                    for loc in self.locations
                    if loc in self.connected_demand_sites
                ]
            )
            self.coverage_constraint = [
                self.demand_at_location[loc] - self.shortage[loc]
                >= self.params.coverage_percentage * min_demand
                for loc in self.locations
                if loc in self.connected_demand_sites
            ]
        else:
            total_demand = sum(
                self.demand_at_location[dem]
                for dem in self.locations
                if dem in self.type_sets[DEMAND]
            )
            self.coverage_constraint = (
                xp.Sum(  # pyre-ignore
                    self.shortage[loc]
                    for loc in self.locations
                    if loc in self.type_sets[DEMAND]
                )
                <= (1 - self.params.coverage_percentage) * total_demand
            )
        self.problem.addConstraint(self.coverage_constraint)

    def create_common_bandwidth_variable_and_constraint(self) -> None:
        self.common_bandwidth = xp.var(  # pyre-ignore
            name="common_bandwidth",
            vartype=xp.continuous,  # pyre-ignore
            lb=0,
            ub=min(
                [
                    self.demand_at_location[loc]
                    for loc in self.connected_demand_sites
                ]
            ),
        )
        self.problem.addVariable(self.common_bandwidth)

        for loc in self.locations:
            if loc not in self.connected_demand_sites:
                continue
            self.problem.addConstraint(
                self.common_bandwidth
                <= self.demand_at_location[loc] - self.shortage[loc]
            )

    # pyre-fixme
    def _create_coverage_objective_expr(self) -> Any:
        obj = 0
        if self.params.maximize_common_bandwidth:
            if len(self.connected_demand_sites) > 0:
                self.create_common_bandwidth_variable_and_constraint()
                obj = -self.common_bandwidth
        else:
            if len(self.type_sets[DEMAND]) > 0:
                obj = xp.Sum(self.shortage)  # pyre-ignore

        return obj

    def create_coverage_objective(self) -> None:
        self.coverage_obj = self._create_coverage_objective_expr()
        self.problem.setObjective(
            self.coverage_obj, sense=xp.minimize  # pyre-ignore
        )

    def create_fixed_input_constraints_without_sectors(self) -> None:
        self.create_decided_site_constraints()
        self.create_active_link_polarity_constraints()
        self.create_inactive_link_flow_constraints()

    def create_decided_site_constraints(self) -> None:
        # Force active sites to be active; no special logic needed for active
        # links because topology validation ensures their connected sites are
        # already active
        for loc in self.locations:
            if (
                self.params.always_active_pops
                and loc in self.type_sets[SiteType.POP]
            ):
                if (
                    loc not in self.inactive_sites
                    # Colocated sites handled in create_colocated_site_relationship
                    and len(
                        self.colocated_locations.get(
                            self.location_to_geoloc[loc], []
                        )
                    )
                    <= 1
                ):
                    self.problem.addConstraint(self.site_vars[loc] == 1)
            elif loc in self.proposed_sites or loc in self.existing_sites:
                # Colocated sites handled in create_colocated_site_relationship
                if (
                    len(
                        self.colocated_locations.get(
                            self.location_to_geoloc[loc], []
                        )
                    )
                    <= 1
                ):
                    self.problem.addConstraint(self.site_vars[loc] == 1)
            elif loc in self.inactive_sites:
                self.problem.addConstraint(self.site_vars[loc] == 0)

    def create_active_link_polarity_constraints(self) -> None:
        if self.params.ignore_polarities:
            return
        # If a link should be active, then the end sites must be of opposite polarities
        for (i, j) in self.links:
            if (i, j) in self.proposed_links or (i, j) in self.existing_links:
                if i in self.odd and j in self.odd:
                    # Because only co-located CN sites can be upgraded and CN
                    # sites are not in self.odd, this constraint is safe for
                    # co-located DNs/POPs
                    self.problem.addConstraint(self.odd[i] == 1 - self.odd[j])

    def create_inactive_link_flow_constraints(self) -> None:
        # Ensure that inactive links have no flow on them
        for (i, j) in self.links:
            if (i, j) in self.inactive_links:
                self.problem.addConstraint(self.flow[(i, j)] == 0)

    def prune_loops(
        self, flows: Dict[Tuple[str, str], float]
    ) -> Dict[Tuple[str, str], float]:
        proposed_flow = {(i, j): 0.0 for (i, j) in self.links}
        # Prune loops to make the flow network a DAG
        is_loop_free: Dict[str, bool] = {loc: False for loc in self.locations}

        # Because _prune_loop loops over all j given an i, create map from each
        # i to all j so loop over entire flows input dictionary is not needed
        i_to_j_map = {}
        for (i, j) in flows.keys():
            i_to_j_map.setdefault(i, []).append(j)

        # pyre-fixme
        def _prune_loop(i, min_flows):
            for j in i_to_j_map.get(i, []):
                if flows[(i, j)] > EPSILON and (not is_loop_free[j]):

                    # min_flows[loc] is the minimum flow of all links from loc
                    # to i, min_flow[loc]=min_flow(loc -> ... -> i)

                    # Now build an updated structure to include edge i -> j
                    latest_min = {
                        loc: min(min_flows[loc], flows[(i, j)])
                        for loc in min_flows
                    }
                    latest_min[i] = flows[(i, j)]

                    if j in min_flows:
                        # j is an upstream location, so i -> j is the last edge
                        # of a loop, where j is the beginning of the loop.
                        # Now the whole loop need to be reduced by the minimum
                        # flow amount starting from j (j-> ... i->j), which
                        # is latest_min[j]
                        flows[(i, j)] -= latest_min[j]

                        # Mission completed for this layer of the stack,
                        # trace back with the answer (loop head and min_flow)
                        return (j, latest_min[j])

                    # j is not in upstream, no loop found directly
                    # try searching further after j
                    k, reduce_flow = _prune_loop(j, latest_min)
                    while k is not None:
                        # A loop found containing i->j from the downstream,
                        # starting with k: k -> ... i -> j -> ... k
                        # Minimum flow in the loop is reduce_flow

                        # first, as part of the loop, the flow of i->j
                        # needs to be reduced anyways
                        flows[(i, j)] -= reduce_flow

                        if k != i:
                            # if k is some upstream node of i, i.e.:
                            # k -> ... i -> j -> .. k
                            # then reducing flows[i][j] is the only thing needed
                            # in this layer of the stack.
                            # We can safely exist, trace back and pass the answer
                            # to upper-stream
                            return (k, reduce_flow)

                        # if i is the beginning of the loop:
                        # i -> j -> ... -> k = i
                        # Then after reducing flows[i][j], we still need to check
                        # other possible loops containing i->j
                        if abs(flows[(i, j)]) < EPSILON or is_loop_free[j]:
                            # if i->j no longer exists or j is loop free, then
                            # i->j is safe, continue to check the next edge of i
                            break
                        else:
                            # if i->j is not clear, keep searching for loops
                            # containing i -> j with the updated flow

                            # since flow[i][j] is updated (smaller)
                            # latest_min should be updated to pass the correct info
                            for loc in latest_min:
                                latest_min[loc] = min(
                                    latest_min[loc], flows[(i, j)]
                                )

                            k, reduce_flow = _prune_loop(j, latest_min)

            # No loops containing i (all i->j finished without returning)
            is_loop_free[i] = True
            return (None, float("inf"))

        # With memoiozation, the overall complexity is about O(n_edge * n_loop)
        for loc in is_loop_free:
            while not is_loop_free[loc]:
                _prune_loop(loc, {})

        for (i, j) in flows:
            proposed_flow[(i, j)] = flows[(i, j)]
        return proposed_flow

    def _get_binary_value(self, decision: float) -> int:
        return 1 if decision > 1 - EPSILON else 0

    # pyre-fixme
    def _extract_flat_dictionary(
        self,
        solution_vector: List[float],
        variable_dict,  # pyre-fixme
        binary: bool = True,
    ):
        decision_vector = {}
        for key in variable_dict:
            decision = solution_vector[
                self.problem.getIndex(variable_dict[key])
            ]
            decision_vector[key] = (
                self._get_binary_value(decision) if binary else decision
            )
        return decision_vector

    def get_sites_with_active_links(
        self, link_decisions: Dict[Tuple[str, str], int]
    ) -> Set[str]:
        """
        Find all sites that have at least one active link associated with it.
        """
        sites_with_active_links = set()
        for (loc1, loc2) in self.links:
            if link_decisions.get((loc1, loc2), 0) == 1:
                sites_with_active_links.add(loc1)
                sites_with_active_links.add(loc2)
        return sites_with_active_links

    def get_sectors_with_active_links(
        self, link_decisions: Dict[Tuple[str, str], int]
    ) -> Dict[str, Set[str]]:
        """
        Find all sectors with at least one associated active link.
        """
        sectors_with_active_links = {}
        for (loc1, loc2) in self.links:
            if link_decisions.get((loc1, loc2), 0) == 1:
                (sec1, sec2) = self.link_to_sectors[(loc1, loc2)]
                for (loc, sec) in [(loc1, sec1), (loc2, sec2)]:
                    if sec is None:
                        continue
                    if self.sector_to_type[sec] in IMAGINARY_SECTOR_TYPES:
                        continue
                    node_id = self.topology.sectors[sec].node_id
                    # All sectors on an active node should be active
                    for other_sec in self.location_sectors[loc]:
                        if (
                            self.sector_to_type[other_sec]
                            in IMAGINARY_SECTOR_TYPES
                        ):
                            continue
                        if node_id == self.topology.sectors[other_sec].node_id:
                            sectors_with_active_links.setdefault(
                                loc, set()
                            ).add(other_sec)
        return sectors_with_active_links

    # Demand Site Optimization Functions
    def create_connected_demand_model(self, max_time: float) -> None:
        self.problem = xp.problem()  # pyre-ignore
        self.problem.setprobname(self.__class__.__name__)

        # Set the optimizer time limit. It is made negative to force solver to
        # exit rather than for it to continue searching for integer solution if
        # not yet found (Xpress convention)
        max_time = abs(max_time)
        self.problem.setControl("maxtime", -max_time * 60)
        logger.info(f"Setting maximum optimizer runtime to {max_time} minutes")

        self.problem.setControl("treememorylimit", 15000)

        if self.params.num_threads is not None:
            self.problem.setControl("threads", self.params.num_threads)
            logger.info(
                f"Setting number of threads to {self.params.num_threads}"
            )

    def create_unit_flow_decisions(self) -> None:
        """
        Create "unit" flow decision variables.
        """
        self.flow = {
            (i, j): xp.var(  # pyre-ignore
                name=f"flow_{i}_{j}",
                vartype=xp.continuous,  # pyre-ignore
                lb=0,
                ub=1,
            )
            for (i, j) in self.links
        }
        self.problem.addVariable(self.flow)

    def create_demand_site_decisions(self) -> None:
        """
        Create demand site decision variables.
        """
        self.demand_vars = {
            loc: xp.var(name=f"site_{loc}", vartype=xp.binary)  # pyre-ignore
            for loc in self.locations
            if loc in self.type_sets[DEMAND]
        }
        self.problem.addVariable(self.demand_vars)

        self.site_vars = {
            loc: 0
            if loc in self.inactive_sites or loc in self.ignore_sites
            else 1
            for loc in self.locations
            if self.location_to_type[loc] not in IMAGINARY_SITE_TYPES
        }

    def create_ignore_link_flow_constraints(self) -> None:
        """
        Ensure that ignored links have no flow on them.
        """
        self.create_inactive_link_flow_constraints()
        for link in self.links:
            if link in self.ignore_links:
                self.problem.addConstraint(self.flow[link] == 0)

    def create_unit_flow_balance_constraints(self) -> None:
        """
        Flow balance constraints

        POP/DN/CN must have equal incoming and outgoing flow. The supersource
        must have non-negative flow and demand sites with positive flow are
        selected.
        """
        for loc in self.locations:
            incoming_flow = self._get_incoming_flow(loc)
            outgoing_flow = self._get_outgoing_flow(loc)

            # Real sites must have flow balance
            if self.location_to_type[loc] not in IMAGINARY_SITE_TYPES:
                if incoming_flow is None and outgoing_flow is None:
                    continue

                # Inactive sites have 0 incoming or outgoing flows
                if self.site_vars[loc] == 0:
                    if incoming_flow is not None:
                        self.problem.addConstraint(incoming_flow == 0)
                    if outgoing_flow is not None:
                        self.problem.addConstraint(outgoing_flow == 0)
                    continue

                incoming_flow = incoming_flow if incoming_flow else 0
                outgoing_flow = outgoing_flow if outgoing_flow else 0
                self.problem.addConstraint(outgoing_flow == incoming_flow)
            elif self.location_to_type[loc] == SUPERSOURCE:
                if outgoing_flow is not None:
                    self.problem.addConstraint(outgoing_flow >= 0)
            # Demand sites can only be active if there is non-zero incoming
            # flow, i.e., demand_var <= large_value * incoming_flow.
            # The objective function maximizing the number of connected demand
            # sites ensures that all demand sites that can have incoming flow
            # will have incoming flow. Similarly, although this constraint
            # means that the demand_var can be 0 even if the incoming flow is
            # positive, the objective function ensures that the demand_var will
            # be 1 (i.e., the former is a feasible solution while the latter is
            # a feasible solution that is more optimal).
            # If large value == number of demand sites, then even if there is
            # only one POP serving demand and all demand sites are connectable,
            # then the flow can be equally divided among them. If there is more
            # than one POP or not all demand sites are connectable, then each
            # connectable demand site can have more flow, so this large value
            # is sufficient. We scale it up a bit just to be safe
            elif self.location_to_type[loc] == DEMAND:
                incoming_flow = incoming_flow if incoming_flow else 0
                self.problem.addConstraint(
                    self.demand_vars[loc]
                    <= 10 * len(self.type_sets[DEMAND]) * incoming_flow
                )

    def create_demand_site_objective(self) -> None:
        """
        Maximize the number of connected demand sites
        """
        obj = xp.Sum(self.demand_vars)  # pyre-ignore
        self.problem.setObjective(obj, sense=xp.maximize)  # pyre-ignore

    def build_connected_demand_model(self) -> None:
        # This function will be overridden in derived classes
        pass

    def reset_connected_demand_model(self) -> None:
        # This function will be overridden in derived classes
        pass

    def solve_connected_demand(self) -> Optional[Set[str]]:
        """
        Solve demand site optimization model. If successful, output is a set of
        reachable demand sites.
        """
        self.problem = None
        self.build_connected_demand_model()
        if self.problem is None:
            return None

        logger.info("Solving demand site optimization")
        start_time = time()
        self.problem.solve()
        end_time = time()
        logger.info(
            "Time to solve the demand site optimization: "
            f"{end_time - start_time:0.2f} seconds."
        )

        if self.problem.attributes.mipsols == 0:
            return None

        # If at least one MIP solution is found, then extract it.
        logger.info("Extracting demand site solution")
        start_time = time()
        reachable_demand_sites = set()
        solution_vector = self.problem.getSolution()
        for key, val in self.demand_vars.items():
            decision = solution_vector[self.problem.getIndex(val)]
            if decision > 1 - EPSILON:
                reachable_demand_sites.add(key)
        end_time = time()
        logger.info(
            "Time for extracting demand site solution: "
            f"{end_time - start_time:0.2f} seconds."
        )

        # Because the regular optimization and connected demand site
        # optimization models re-use many of the same variables, for safety,
        # reset those variables to reduce risk of cross contamination between
        # the models.
        self.reset_connected_demand_model()

        return reachable_demand_sites

    def dump_problem_file_for_debug_mode(self, file_type: DebugFile) -> None:
        if not current_system_params.debug_mode or self.problem is None:
            return
        dump_dir = os.path.join(current_system_params.output_dir, "debug")
        if not os.path.exists(dump_dir):
            os.mkdir(dump_dir)
        time_suffix = "".join(str(time()).split("."))
        full_file_path = os.path.join(
            dump_dir, f"{file_type.name.lower()}_{time_suffix}"
        )
        self.problem.write(full_file_path, "lp")
        logger.info(
            f"{file_type.name.lower()} has been dumped to {full_file_path}.lp"
        )
