# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import logging
import time
from itertools import chain
from typing import Dict, Optional, Tuple, Union

from pyre_extensions import assert_is_instance, none_throws

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.constants import OPTIMIZATION
from terragraph_planner.common.configuration.enums import (
    DebugFile,
    PolarityType,
    RedundancyLevel,
    SiteType,
    StatusType,
)
from terragraph_planner.common.configuration.utils import (
    struct_objects_from_file,
)
from terragraph_planner.common.data_io.topology_serializer import (
    dump_topology_to_kml,
)
from terragraph_planner.common.data_io.utils import extract_topology_from_file
from terragraph_planner.common.exceptions import (
    OptimizerException,
    planner_assert,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.common.utils import set_system_control_with_config_file
from terragraph_planner.los.core import (
    generate_candidate_topology_with_config_file,
)
from terragraph_planner.optimization.constants import (
    COVERAGE_STEP_SIZE,
    COVERAGE_THRESHOLD,
    UNASSIGNED_CHANNEL,
)
from terragraph_planner.optimization.deployment_rules import (
    find_angle_violating_link_pairs,
)
from terragraph_planner.optimization.ilp_models.cost_optimization import (
    MinCostNetwork,
)
from terragraph_planner.optimization.ilp_models.coverage_optimization import (
    MaxCoverageNetwork,
)
from terragraph_planner.optimization.ilp_models.interference_optimization import (
    MinInterferenceNetwork,
)
from terragraph_planner.optimization.ilp_models.pop_proposal_optimization import (
    POPProposalNetwork,
    add_duplicate_pop_to_dn_site,
)
from terragraph_planner.optimization.ilp_models.redundancy_optimization import (
    RedundantNetwork,
    compute_candidate_edges_for_redundancy,
)
from terragraph_planner.optimization.structs import (
    OptimizationSolution,
    RedundancyParams,
    RedundancySolution,
)
from terragraph_planner.optimization.topology_interference import (
    compute_link_interference,
)
from terragraph_planner.optimization.topology_operations import (
    compute_capex,
    compute_max_pop_capacity_of_topology,
    get_adversarial_links,
    hops_from_pops,
    mark_unreachable_components,
    readjust_sectors_post_opt,
)
from terragraph_planner.optimization.topology_preparation import (
    prepare_topology_for_optimization,
)
from terragraph_planner.optimization.topology_report import analyze_with_dump

logger: logging.Logger = logging.getLogger(__name__)


def optimize_and_report_topology_with_config_file(
    config_file_path: str,
) -> Topology:
    """
    Given the config file, run the plan to optimize and report the network topology.

    @param config_file_path
    The file path of the config yaml or json file. If a yaml file is used,
    please refer to the template.yaml under terragraph/data directory.
        - If CANDIDATE_TOPOLOGY_FILE_PATH is set, the topology will be extracted from
          that file.
        - If CANDIDATE_TOPOLOGY_FILE_PATH is not set, this function will run the
          los function `generate_canidate_graph` first. Please give the LOS config
          parameters in this case.
    """
    set_system_control_with_config_file(config_file_path)
    opt_params = assert_is_instance(
        struct_objects_from_file(OPTIMIZATION, config_file_path),
        OptimizerParams,
    )
    if opt_params.candidate_topology_file_path is not None:
        topology = extract_topology_from_file(
            opt_params.candidate_topology_file_path,
            opt_params.device_list,
        )
    else:
        topology = generate_candidate_topology_with_config_file(
            config_file_path,
        )
    optimize_and_report_topology(topology, opt_params)
    return topology


def optimize_and_report_topology(
    topology: Topology, params: OptimizerParams
) -> None:
    pre_opt_check(topology, params)
    prepare_topology_for_optimization(topology, params)
    optimize_topology(topology, params)
    analyze_with_dump(topology, params)


def pre_opt_check(topology: Topology, params: OptimizerParams) -> None:
    # Check if there is a POP
    if params.number_of_extra_pops <= 0:
        for site in topology.sites.values():
            if site.site_type == SiteType.POP:
                break
        else:
            raise OptimizerException(
                "The input topology must contain at least one POP "
                "location or set number of extra POPs greater than zero.",
            )
    # Check if there is demand - only applicable for CN demand case
    if not params.enable_uniform_demand and not params.enable_manual_demand:
        for site in topology.sites.values():
            if site.site_type == SiteType.CN:
                break
        else:
            raise OptimizerException(
                "No demand sites will be added to the topology because the "
                "input topology has no CNs."
            )


def optimize_topology(topology: Topology, params: OptimizerParams) -> None:
    start_time = time.time()

    # Normalize the input for equivalent topologies by sorting it
    topology.sort()

    # Propose some extra POPs if necessary
    _run_propose_extra_pops_step(topology, params)

    # Mark disconnected components and those that exceed max hops from POPs
    # as unreachable
    mark_unreachable_components(
        topology, maximum_hops=params.maximum_number_hops
    )
    dump_topology_to_kml(topology, DebugFile.PREPARED_TOPOLOGY)

    logger.info(
        f"Input problem has {len(topology.sites)} sites, "
        f"{len(topology.links)} links, "
        f"{len(topology.sectors)} sectors, and "
        f"{len(topology.demand_sites)} demand sites."
    )

    # Force polarities to be included
    params.ignore_polarities = False

    # Step 1: Solve minimum cost problem
    _run_min_cost_step(topology, params)
    dump_topology_to_kml(topology, DebugFile.MIN_COST_TOPOLOGY)

    # Step 2: Add redundancy to network
    if params.enable_legacy_redundancy_method:
        _run_max_coverage_step(topology, params)
        dump_topology_to_kml(topology, DebugFile.MAX_COVERAGE_TOPOLOGY)
    else:
        _run_redundancy_step(topology, params)
        dump_topology_to_kml(topology, DebugFile.REDUNDANT_TOPOLOGY)

    # Step 3: Minimize interference in network
    _run_interference_step(topology, params)
    dump_topology_to_kml(topology, DebugFile.MIN_INTERFERENCE_TOPOLOGY)

    # Step 4: Update sector orientations based on chosen links
    readjust_sectors_post_opt(topology, params)
    dump_topology_to_kml(topology, DebugFile.OPTIMIZED_TOPOLOGY)

    end_time = time.time()
    logger.info(
        "Total elapsed time performing network optimization: "
        f"{end_time - start_time:0.2f} seconds."
    )


def _run_min_cost_step(
    topology: Topology, params: OptimizerParams
) -> OptimizationSolution:
    logger.info("Running cost minimization.")
    min_cost_network = MinCostNetwork(topology, params)
    coverage_percentage = 1.0
    solution = None
    timed_out = False
    while solution is None and coverage_percentage >= COVERAGE_THRESHOLD:
        logger.info(
            f"Setting coverage threshold to {coverage_percentage:.2f} and "
            "performing network optimization."
        )
        solution = min_cost_network.solve(
            coverage_percentage=coverage_percentage
        )
        timed_out = min_cost_network.did_problem_timeout()
        coverage_percentage -= COVERAGE_STEP_SIZE

    if solution is not None:
        update_topology_with_solution(solution, topology)
        return solution

    if timed_out:
        raise OptimizerException(
            "The minimum cost network planning problem timed-out. We recommend "
            "either increasing the optimization time or relative stopping "
            "criteria or making the problem smaller by either subdividing the "
            "region of interest, removing sites and/or removing links (e.g., "
            "by increasing Min MCS)."
        )

    max_capacity = compute_max_pop_capacity_of_topology(
        topology=topology,
        pop_capacity=params.pop_capacity,
        status_filter=StatusType.reachable_status(),
    )
    max_throughput = sum(
        none_throws(d.demand) for d in topology.demand_sites.values()
    )
    if max_capacity < max_throughput * COVERAGE_THRESHOLD:
        raise OptimizerException(
            f"Insufficient number of POPs to meet {COVERAGE_THRESHOLD*100}% "
            "of requested demand. We recommend to increase the number of POPs "
            "or reduce demand."
        )

    # Raise generic error message if infeasibility reason cannot be determined
    raise OptimizerException(
        "The minimum cost network planning problem is infeasible for the given "
        "parameters."
    )


def _run_propose_extra_pops_step(
    topology: Topology, params: OptimizerParams
) -> Optional[OptimizationSolution]:
    """
    Propose extra POP sites selected from the DNs in the candiate network.
    """
    if params.number_of_extra_pops == 0:
        num_pops = len(
            [
                site.site_id
                for site in topology.sites.values()
                if site.site_type == SiteType.POP
            ]
        )
        if num_pops == 0:
            raise OptimizerException(
                "Input candidate network has no POPs, so the number of extra "
                "POPs must be greater than 0."
            )
        return

    pop_proposal_network = POPProposalNetwork(topology, params)
    solution = pop_proposal_network.propose_pops()

    if solution is not None:
        add_duplicate_pop_to_dn_site(topology, solution)
        return solution

    if pop_proposal_network.did_problem_timeout():
        logger.warning(
            "The POP proposal network planning problem timed-out. We recommend "
            "either increasing the optimization time or relative  stopping "
            "criteria or making the problem smaller by either subdividing the "
            "region of interest, removing sites and/or removing links (e.g., "
            "by increasing Min MCS). Planning will proceed without extra "
            "proposed POPs."
        )
    else:
        logger.warning(
            "The POP proposal network planning problem is infeasible for the "
            "given parameters. Planning will proceed without extra proposed "
            "POPs."
        )

    return None


def _run_max_coverage_step(
    topology: Topology, params: OptimizerParams
) -> Optional[OptimizationSolution]:
    logger.info(f"Maximizing coverage with {params.budget} budget.")

    costs = compute_capex(topology, params)
    extra_budget = params.budget - costs.proposed_capex
    logger.info(f"Min cost network leaves ${extra_budget} of extra budget.")

    if extra_budget <= 0:
        if extra_budget < 0:
            logger.warning(
                f"Automatically updating input budget to {costs.proposed_capex} "
                "in order to meet minimum network requirements. Final network "
                "cost may be less."
            )
        return None

    adversarial_links = get_adversarial_links(
        topology,
        params.backhaul_link_redundancy_ratio,
    )

    logger.info("Performing network optimization.")
    max_cov_network = MaxCoverageNetwork(topology, params, adversarial_links)
    solution = max_cov_network.solve()

    if solution is not None:
        min_cost_dns = len(
            topology.get_site_ids(
                status_filter=StatusType.active_status(),
                site_type_filter={SiteType.DN},
            )
        )
        update_topology_with_solution(solution, topology)
        max_cov_dns = len(
            topology.get_site_ids(
                status_filter=StatusType.active_status(),
                site_type_filter={SiteType.DN},
            )
        )
        logger.info(
            f"Max coverage topology addeed {max_cov_dns - min_cost_dns} DN(s)"
        )

        return solution

    if max_cov_network.did_problem_timeout():
        logger.warning(
            "The maximum coverage network planning problem timed-out. We "
            "recommend either increasing the optimization time or relative "
            "stopping criteria or making the problem smaller by either "
            "subdividing the region of interest, removing sites and/or "
            "removing links (e.g., by increasing Min MCS). Planning will "
            "proceed with the minimum cost network."
        )
    else:
        logger.warning(
            "The maximum coverage network planning problem is infeasible "
            "for the given parameters. It is possible this can be addressed "
            "by increasing the budget or decreasing the backhaul link "
            "redundancy ratio. Planning will proceed with the minimum cost "
            "network."
        )

    return None


def _run_redundancy_step(
    topology: Topology,
    params: OptimizerParams,
) -> Optional[RedundancySolution]:
    logger.info("Adding redundancy to network.")

    num_pops = len(
        topology.get_site_ids(
            status_filter=StatusType.active_status(),
            site_type_filter={SiteType.POP},
        )
    )

    if params.redundancy_level == RedundancyLevel.LOW:
        # Redundant to any single link failure
        redundancy_params = RedundancyParams(
            pop_node_capacity=2, dn_node_capacity=2, sink_node_capacity=2
        )
    elif params.redundancy_level == RedundancyLevel.MEDIUM:
        if num_pops > 1:
            # Redundant to any single site (POP or DN) failure
            redundancy_params = RedundancyParams(
                pop_node_capacity=1, dn_node_capacity=1, sink_node_capacity=2
            )
        else:
            # Redundant to any single DN failure
            redundancy_params = RedundancyParams(
                pop_node_capacity=2, dn_node_capacity=1, sink_node_capacity=2
            )
    elif params.redundancy_level == RedundancyLevel.HIGH:
        if num_pops > 1:
            # Redundant to a POP and DN failure or 3 DN failures
            redundancy_params = RedundancyParams(
                pop_node_capacity=2, dn_node_capacity=1, sink_node_capacity=4
            )
        else:
            # Redundant to any 2 DN failures
            redundancy_params = RedundancyParams(
                pop_node_capacity=3, dn_node_capacity=1, sink_node_capacity=3
            )
    else:
        return None

    # Apply heuristic to reduce size of the redundancy ILP. Based on some
    # experimentation, finding 4 node disjoint paths between each POP and DN
    # and 2 disjoint paths between each DN achieves nearly same result as
    # version without heuristic for high redundancy level (and hence lower
    # redundancy levels as well).
    logger.info("Running heuristic to reduce size of site/link selection pool.")
    candidate_links = compute_candidate_edges_for_redundancy(
        topology=topology, pop_source_capacity=4.0, dn_source_capacity=2.0
    )

    # Add proposed links between all nodes in the heuristic output. This adds
    # links between proposed DNs of opposite polarity that were not included
    # in the original heuristic.
    candidate_nodes = set(chain(*candidate_links))
    candidate_links |= {
        (link.tx_site.site_id, link.rx_site.site_id)
        for link in topology.links.values()
        if link.tx_site.site_id in candidate_nodes
        and link.rx_site.site_id in candidate_nodes
        and link.status_type in StatusType.active_status()
    }

    logger.info("Performing network optimization.")
    redundancy_network = RedundantNetwork(
        topology, params, redundancy_params, candidate_links
    )
    solution = redundancy_network.solve()

    if solution is not None:
        min_cost_dns = len(
            topology.get_site_ids(
                status_filter=StatusType.active_status(),
                site_type_filter={SiteType.DN},
            )
        )
        update_topology_with_solution(solution, topology)
        red_dns = len(
            topology.get_site_ids(
                status_filter=StatusType.active_status(),
                site_type_filter={SiteType.DN},
            )
        )
        logger.info(f"Redundant topology addeed {red_dns - min_cost_dns} DN(s)")
        return solution

    if redundancy_network.did_problem_timeout():
        logger.warning(
            "The redundant network planning problem timed-out. We recommend "
            "either increasing the optimization time or relative stopping "
            "criteria or making the problem smaller by either subdividing the "
            "region of interest, removing sites and/or  removing links (e.g., "
            "by increasing Min MCS). Planning will  proceed with the minimum "
            "cost network."
        )
    else:
        logger.warning(
            "The redundant network planning problem is infeasible for the given "
            "parameters. Planning will proceed with the minimum cost network."
        )

    return None


def _run_interference_step(
    topology: Topology,
    params: OptimizerParams,
) -> OptimizationSolution:
    logger.info(
        "Maximizing the coverage that follows interference-based capacity constraints."
    )

    logger.info("Finding pairs of links that violate angle limitations.")
    violating_links = find_angle_violating_link_pairs(
        topology,
        params.diff_sector_angle_limit,
        params.near_far_angle_limit,
        params.near_far_length_ratio,
        active_components=False,
    )

    logger.info("Computing interference on all links.")
    interfering_rsl = compute_link_interference(topology, params.maximum_eirp)

    logger.info("Performing network optimization.")
    min_int_network = MinInterferenceNetwork(
        topology,
        params,
        violating_links.diff_sector_list + violating_links.near_far_list,
        interfering_rsl,
    )
    solution = min_int_network.solve()

    if solution is not None:
        update_topology_with_solution(solution, topology)
        return solution

    if min_int_network.did_problem_timeout():
        raise OptimizerException(
            "The minimum interference network planning problem timed-out. We "
            "recommend either increasing the optimization time or relative "
            "stopping criteria or making the problem smaller by either "
            "subdividing the region of interest, removing sites  and/or "
            "removing links (e.g., by increasing Min MCS)."
        )

    # Raise generic error message if infeasibility reason cannot be determined
    raise OptimizerException(
        "The minimum interference network planning problem is infeasible "
        "for the given parameters."
    )


def update_topology_with_solution(
    solution: Union[OptimizationSolution, RedundancySolution],
    topology: Topology,
) -> None:
    """
    Updates the information stored in sites, sectors and links in the topology
    using the solution obtained from the optimizer.
    """
    sector_decisions = solution.sector_decisions
    link_decisions = solution.link_decisions
    site_decisions = solution.site_decisions
    odd_site_decisions = solution.odd_site_decisions
    even_site_decisions = solution.even_site_decisions
    channel_decisions = solution.channel_decisions

    _update_topology_sites(
        topology,
        site_decisions,
        odd_site_decisions,
        even_site_decisions,
    )
    _update_topology_sectors(topology, sector_decisions, channel_decisions)
    _update_topology_links(topology, link_decisions)
    _remove_disconnected_components_from_topology(topology)


def _update_topology_sites(
    topology: Topology,
    site_decisions: Dict[str, int],
    odd_site_decisions: Dict[str, int],
    even_site_decisions: Dict[str, int],
) -> None:
    """
    Update the status and polarity of sites using the optimizer solution.
    """
    for site_id, site in topology.sites.items():
        decision = site_decisions.get(site_id, 0)
        current_status = site.status_type
        if current_status not in StatusType.immutable_status() | {
            StatusType.UNREACHABLE
        }:
            site.status_type = (
                StatusType.PROPOSED if decision == 1 else StatusType.CANDIDATE
            )
        odd_decision = odd_site_decisions.get(site_id, 0)
        even_decision = even_site_decisions.get(site_id, 0)
        planner_assert(
            not (odd_decision == 1 and even_decision == 1),
            "A site cannot be both odd and even",
            OptimizerException,
        )
        site.polarity = (
            PolarityType.ODD
            if odd_decision == 1
            else PolarityType.EVEN
            if even_decision == 1
            else PolarityType.UNASSIGNED
        )


def _update_topology_sectors(
    topology: Topology,
    sector_decisions: Dict[Tuple[str, str], int],
    channel_decisions: Dict[Tuple[str, str], int],
) -> None:
    """
    Updates the status of sectors using the solution optimizer_solution.
    """
    for sector_id, sector in topology.sectors.items():
        site = sector.site
        decision = sector_decisions.get((site.site_id, sector_id), 0)
        current_status = sector.status_type
        if current_status not in StatusType.immutable_status() | {
            StatusType.UNREACHABLE
        }:
            sector.status_type = (
                StatusType.PROPOSED if decision == 1 else StatusType.CANDIDATE
            )
        sector.channel = channel_decisions.get(
            (site.site_id, sector_id), UNASSIGNED_CHANNEL
        )


def _update_topology_links(
    topology: Topology, link_decisions: Dict[Tuple[str, str], int]
) -> None:
    """
    Updates the capacity, proposed flow and status information of links
    in topology using the solution obtained from the optimizer.
    """
    for link in topology.links.values():
        site_pair = (link.tx_site.site_id, link.rx_site.site_id)
        decision = link_decisions.get(site_pair, 0)
        current_status = link.status_type
        if current_status not in StatusType.immutable_status() | {
            StatusType.UNREACHABLE
        }:
            link.status_type = (
                StatusType.PROPOSED if decision == 1 else StatusType.CANDIDATE
            )


def _remove_disconnected_components_from_topology(topology: Topology) -> None:
    """
    This function removes these disconnected components from the topology.
    """
    hop_counts = hops_from_pops(
        topology, status_filter=StatusType.active_status()
    )
    for sector in topology.sectors.values():
        site = sector.site
        if site.site_id not in hop_counts:
            current_site_status = site.status_type
            if current_site_status not in StatusType.immutable_status() | {
                StatusType.UNREACHABLE
            }:
                site.status_type = StatusType.CANDIDATE

            current_sector_status = sector.status_type
            if current_sector_status not in StatusType.immutable_status() | {
                StatusType.UNREACHABLE
            }:
                sector.status_type = StatusType.CANDIDATE

    # Some active links may have ended up with candidate end-sites
    # Ensure that those links are also set to candidate.
    for link in topology.links.values():
        if link.status_type in StatusType.active_status():
            tx_site = link.tx_site
            rx_site = link.rx_site
            if (
                tx_site.status_type == StatusType.CANDIDATE
                or rx_site.status_type == StatusType.CANDIDATE
            ):
                current_link_status = link.status_type
                if current_link_status not in StatusType.immutable_status() | {
                    StatusType.UNREACHABLE
                }:
                    link.status_type = StatusType.CANDIDATE
