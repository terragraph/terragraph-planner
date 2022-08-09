# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import heapq
import logging
import time
from copy import deepcopy
from typing import Dict, List, Optional, Tuple

import networkx as nx
import numpy as np

from terragraph_planner.common.configuration.enums import LinkType
from terragraph_planner.common.exceptions import (
    OptimizerException,
    planner_assert,
)
from terragraph_planner.optimization.constants import SUPERSOURCE
from terragraph_planner.optimization.topology_networkx import (
    find_connected_demands,
)

logger: logging.Logger = logging.getLogger(__name__)


def compute_availability(
    graph: nx.Graph,
    link_availability: float,
    sim_length: float,
    time_limit_sec: Optional[float] = None,
    seed=None,  # pyre-fixme
) -> Tuple[Dict[str, float], Dict[Tuple[str, str], float]]:
    """
    Very simple and somewhat fast continuous time simulation of network
    failure. Failure and repair time are exponentially distributed.

    This code is a slight modification of the original version written by Erik
    Zawadzki.

    @param graph nx.Graph: network graph
    @param link_availability: percentage of time that a link is live
    @param sim_length float: simulation time (unitless)
    @param time_limit_sec float: time limit in seconds to stop the
        availability computations
    @returns
        availability: dictionary from demand site ids to simulated availability
        sim_link_availability: dictionary from link site id pairs to simulated
            link availability (should be approximately equal to input
            link_availability)
    """
    planner_assert(
        0 <= link_availability <= 100,
        "Link availability percentage must be in [0, 100]",
        OptimizerException,
    )
    planner_assert(
        sim_length > 0, "Simulation time must be positive", OptimizerException
    )

    rng = np.random.default_rng(seed)

    connected_demand_ids = find_connected_demands(graph)

    def _sorted_edge(node1: str, node2: str) -> Tuple[str, str]:
        if node1 < node2:
            return (node1, node2)
        return (node2, node1)

    availability = {demand_id: 0.0 for demand_id in connected_demand_ids}
    sim_link_availability = {
        _sorted_edge(u, v): 0.0
        for u, v, link_type in graph.edges(data="link_type")
        if link_type == LinkType.WIRELESS_BACKHAUL
    }

    mttf = link_availability / 100
    mttr = 1.0 - mttf

    # Set up heap with single _SIM_END terminal signal
    _FAILED = 0
    _REPAIRED = 1
    _SIM_END = 2
    events: List[Tuple[float, Tuple[str, str], int]] = [
        (sim_length, ("", ""), _SIM_END)
    ]

    # Generate failure and repair events for each backhaul edge; add to heap
    processed_edges = set()
    for u, v, link_type in graph.edges(data="link_type"):
        if link_type != LinkType.WIRELESS_BACKHAUL:
            continue

        key = _sorted_edge(u, v)
        if key in processed_edges:
            continue

        planner_assert(
            graph.has_edge(v, u),
            "Backhaul links must be bidirectional",
            OptimizerException,
        )

        curr = 0
        while curr < sim_length:
            time_to_failure = rng.exponential(mttf)
            curr += time_to_failure
            heapq.heappush(events, (curr, key, _FAILED))

            time_to_repair = rng.exponential(mttr)
            curr += time_to_repair
            heapq.heappush(events, (curr, key, _REPAIRED))

        processed_edges.add(key)

    # Iterate through events, check connectivity whenever edges are removed or
    # added
    graph_copy = deepcopy(graph)  # Do not modify input graph

    sim_events = 0
    last_event_time = 0
    missing_edges = set()
    start_time = time.time()
    while len(events) > 0:
        sim_events += 1
        if 0 == sim_events % 1000:
            logger.info(f"Simulating event {sim_events}...")

        # Get the next event
        event_time, (u, v), event_type = heapq.heappop(events)
        planner_assert(
            event_time <= sim_length,
            "Event time should not exceed the desired simulation length",
            OptimizerException,
        )
        dT = (event_time - last_event_time) / sim_length

        # Compute demand sites that are still connected
        descendents = nx.descendants(graph_copy, source=SUPERSOURCE)
        descendents = connected_demand_ids.intersection(descendents)

        for demand_id in descendents:
            availability[demand_id] += dT

        for edge in sim_link_availability:
            if edge not in missing_edges:
                sim_link_availability[edge] += dT

        # Simulate event.
        last_event_time = event_time
        if event_type == _REPAIRED:
            graph_copy.add_edge(u, v)
            graph_copy.add_edge(v, u)
            planner_assert(
                (u, v) in missing_edges,
                "Available link cannot be repaired",
                OptimizerException,
            )
            missing_edges.remove((u, v))
        elif event_type == _FAILED:
            graph_copy.remove_edge(u, v)
            graph_copy.remove_edge(v, u)
            planner_assert(
                (u, v) not in missing_edges,
                "Unavailable link cannot fail",
                OptimizerException,
            )
            missing_edges.add((u, v))
        else:
            planner_assert(
                _SIM_END == event_type,
                "Something wonky happened during the availability simulation.",
                OptimizerException,
            )
            break

        if (
            time_limit_sec is not None
            and (time.time() - start_time) > time_limit_sec
        ):
            actual_simulation_time = event_time
            # Re-scale the availability values
            for demand_id, val in availability.items():
                availability[demand_id] = (
                    val * sim_length / actual_simulation_time
                )
            logger.warning(
                "Availability computation terminated due to reaching time limit."
            )
            break
    logger.info(f"Simulated {sim_events} events.")

    return availability, sim_link_availability
