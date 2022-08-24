# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import math
from typing import Dict, Optional, Tuple

from pyre_extensions import none_throws

from terragraph_planner.common.configuration.enums import (
    LinkType,
    PolarityType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.geos import angle_delta
from terragraph_planner.common.rf.link_budget_calculator import (
    get_fspl_based_net_gain,
    get_fspl_based_rsl,
    get_max_tx_power,
    get_noise_power,
    linear_to_log,
    log_to_linear,
)
from terragraph_planner.common.topology_models.link import Link
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.constants import UNASSIGNED_CHANNEL

logger: logging.Logger = logging.getLogger(__name__)


def compute_link_interference(
    topology: Topology,
    maximum_eirp: Optional[float],
) -> Dict[Tuple[str, str], float]:
    """
    Compute interference for each link given some deviation from boresight.
    """
    rsl_interference = {}
    for link in topology.links.values():
        if (
            link.link_type == LinkType.ETHERNET
            or link.tx_sector is None
            or link.rx_sector is None
        ):
            rsl_interference[
                (link.tx_site.site_id, link.rx_site.site_id)
            ] = -math.inf
            continue

        # The deviations should be the angle between the interfering path and
        # the interference causing links (tx_el_dev) and the interfered on
        # links (rx_el_dev). However, for a candidate topology prior to
        # optimization, this can be very expensive to compute (all candidate
        # links are considered, not just active ones). Instead, to accelerate
        # computation, we assume that the interference causing and interered on
        # links have the same horizontal/vertical azimuth as their sectors.
        # Based on experimentation, this approximation has only a minor impact
        # on the final plan quality and thus is justified due to improved run
        # time.
        net_gain = _compute_link_interference_net_gain(
            interfering_path=link,
            tx_dev=none_throws(link.tx_dev),
            rx_dev=none_throws(link.rx_dev),
            tx_el_dev=link.el_dev,
            rx_el_dev=-link.el_dev,
        )

        # Use max Tx power without backoff to preserve worst-case interference
        # for optimization purposes
        tx_sector_params = link.tx_site.device.sector_params
        max_tx_power = get_max_tx_power(
            tx_sector_params=tx_sector_params,
            tx_radio_pattern_data=tx_sector_params.antenna_pattern_data,
            max_eirp_dbm=maximum_eirp,
        )
        rsl_interference[
            (link.tx_site.site_id, link.rx_site.site_id)
        ] = get_fspl_based_rsl(max_tx_power, net_gain)
    return rsl_interference


def _compute_link_interference_net_gain(
    interfering_path: Link,
    tx_dev: float,
    rx_dev: float,
    tx_el_dev: float,
    rx_el_dev: float,
) -> float:
    """
    Compute the net gain of a tx interfering link on a rx interfered link
    using the actual deviations between those links and the interfering path.

    The tx_dev/tx_el_dev is the horizontal/vertical deviation in the tx
    direction (degrees) and the rx_dev/rx_el_dev is the horizontal/vertical
    deviation in the rx direction (degrees).
    """
    tx_sector_params = interfering_path.tx_site.device.sector_params
    rx_sector_params = interfering_path.rx_site.device.sector_params
    return get_fspl_based_net_gain(
        dist_m=interfering_path.distance,
        tx_sector_params=tx_sector_params,
        tx_radio_pattern_data=tx_sector_params.antenna_pattern_data,
        rx_sector_params=rx_sector_params,
        rx_radio_pattern_data=rx_sector_params.antenna_pattern_data,
        tx_deviation=tx_dev,
        rx_deviation=rx_dev,
        tx_el_deviation=tx_el_dev,
        rx_el_deviation=rx_el_dev,
    )


def analyze_interference(
    topology: Topology,
    link_net_gain_map: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None,
) -> None:
    """
    Calculate and update SINR on all active wireless links
    """
    link_rsl_map = compute_link_rsl_map(topology, link_net_gain_map)

    for link in topology.links.values():
        if (
            link.link_type == LinkType.ETHERNET
            or link.status_type not in StatusType.active_status()
        ):
            continue

        if link.rsl_dbm == -math.inf:
            link.sinr_dbm = -math.inf
            continue

        np_dbm = get_noise_power(link.rx_site.device.sector_params)
        noise_mw = log_to_linear(np_dbm)

        interfering_rsl = link_rsl_map.get(link.link_id, 0)

        noise_and_interference = linear_to_log(interfering_rsl + noise_mw)
        # Subtract this RSL value from the SNR computed for the active links.
        link.sinr_dbm = link.rsl_dbm - noise_and_interference


def compute_link_rsl_map(
    topology: Topology,
    link_net_gain_map: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None,
) -> Dict[str, float]:
    """
    Loop over all interfering paths to compute the interference on each rx
    interfered link from each of the corresponding tx interfering links

    The link_net_gain_map stores the net gain on each rx interfered link from
    each of the corresponding tx interfering links; will be computed if not
    passed in (pre-computation can save significant amount of time if used
    called repeatedly).

    Returns the dictionary mapping from each rx interfered link to the amount
    of interference on it.
    """

    if link_net_gain_map is None:
        link_net_gain_map = compute_link_net_gain_map(topology)

    link_rsl_map = {}
    for interfering_path_link_id in topology.links:
        rx_interference_map = link_net_gain_map.get(
            interfering_path_link_id, {}
        )

        for (
            rx_interfered_link_id,
            tx_interference_map,
        ) in rx_interference_map.items():

            if len(tx_interference_map) == 0:
                continue
            link_rsl = link_rsl_map.get(rx_interfered_link_id, 0.0)
            interference = 0.0
            for tx_interfering_link_id, net_gain in tx_interference_map.items():
                interference += log_to_linear(
                    get_fspl_based_rsl(
                        topology.links[tx_interfering_link_id].tx_power,
                        net_gain,
                    )
                )
            link_rsl = link_rsl + interference / len(tx_interference_map)
            link_rsl_map[rx_interfered_link_id] = link_rsl

    return link_rsl_map


def compute_link_net_gain_map(
    topology: Topology,
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Loop over all interfering paths to compute the net gain on each rx
    interfered link from each of the corresponding tx interfering links
    (see _calculate_net_gain_on_rx_links).

    Returns the dictionary mapping from each interfering path, rx interfered
    link and tx interfering link to the amount of net gain on it.
    """

    cn_polarities = _get_cn_polarities(topology)

    # Precompute and cache sector connectivity
    sector_connectivity = topology.sector_connectivity
    sector_connectivity_reverse = topology.sector_connectivity_reverse

    # Loop over all links that are interfering paths and compute the interference
    # from its tx sector's links onto its rx sector's links
    link_net_gain_map = {}
    for link in topology.links.values():
        # If link is wired, it is not an interfering path
        if link.link_type == LinkType.ETHERNET:
            continue

        # If link is out-of-sector, it is not an interfering path
        if link.is_out_of_sector():
            continue

        tx_sector = none_throws(link.tx_sector)
        rx_sector = none_throws(link.rx_sector)

        # If link's sectors are inactive or connected sectors do not have
        # compatible polarity or channel, then the link is not an interfering
        # path
        if not (
            tx_sector.status_type in StatusType.active_status()
            and rx_sector.status_type in StatusType.active_status()
            and _compatible_polarity(link, cn_polarities)
            and _compatible_channel(link)
        ):
            continue

        tx_sector_links = sector_connectivity.get(tx_sector.sector_id, {})

        # Redundant links do not cause interference
        tx_sector_to_delete = set()
        for tx_to_sector, tx_interfering_link_id in tx_sector_links.items():
            tx_interfering_link = topology.links[tx_interfering_link_id]
            if tx_interfering_link.is_redundant:
                tx_sector_to_delete.add(tx_to_sector)

        for sector_id in tx_sector_to_delete:
            tx_sector_links.pop(sector_id)

        # If link is the only one from the transmitting sector, then the link
        # is not an interfering path
        if len(tx_sector_links) == 0:
            continue

        rx_sector_links = sector_connectivity_reverse.get(
            rx_sector.sector_id, {}
        )
        # If the link is the only one from the receiving sector, then the link
        # is not an interfering path
        if len(rx_sector_links) <= 1:
            continue

        _calculate_net_gain_on_rx_links(
            link_net_gain_map,
            topology,
            tx_sector_links,
            rx_sector_links,
            link,
        )

    return link_net_gain_map


def _calculate_net_gain_on_rx_links(
    link_net_gain_map: Dict[str, Dict[str, Dict[str, float]]],
    topology: Topology,
    tx_sector_links: Dict[str, str],
    rx_sector_links: Dict[str, str],
    interfering_path: Link,
) -> None:
    """
    Given an interfering path, compute the net gain on each rx interfered
    link from each of the corresponding tx interfering links.

    The link_net_gain_map is the dictionary mapping from the rx interfered
    link to the amount of net gain on it. This dictionary is modified in place.

    The tx_sector_links is the dictionary containing all the links from the
    tx sector of the interfering path.

    The rx_sector_links is the dictionary containing all the links to the
    rx setor of the interfering path.
    """

    for rx_from_sector_id, rx_interfered_link_id in rx_sector_links.items():
        # Skip current interfering path
        if (
            rx_from_sector_id
            == none_throws(interfering_path.tx_sector).sector_id
        ):
            continue

        rx_interfered_link = topology.links[rx_interfered_link_id]
        # There is no interference on wired or inactive links
        if (
            rx_interfered_link.link_type == LinkType.ETHERNET
            or rx_interfered_link.status_type not in StatusType.active_status()
        ):
            continue

        for tx_to_sector_id, tx_interfering_link_id in tx_sector_links.items():
            # Skip current interfering path
            if (
                tx_to_sector_id
                == none_throws(interfering_path.rx_sector).sector_id
            ):
                continue

            # The sector cannot be simultaneously transmitting and receiving
            if tx_to_sector_id == rx_from_sector_id:
                continue

            tx_interfering_link = topology.links[tx_interfering_link_id]
            # There is no interference caused by wired or inactive links
            if (
                tx_interfering_link.link_type == LinkType.ETHERNET
                or tx_interfering_link.status_type
                not in StatusType.active_status()
            ):
                continue

            # Calculate net gain using the angle between the links
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
                interfering_path=interfering_path,
                tx_dev=tx_dev,
                rx_dev=rx_dev,
                tx_el_dev=tx_el_dev,
                rx_el_dev=rx_el_dev,
            )

            link_net_gain_map.setdefault(
                interfering_path.link_id, {}
            ).setdefault(rx_interfered_link_id, {})[
                tx_interfering_link_id
            ] = net_gain


def _get_cn_polarities(topology: Topology) -> Dict[str, PolarityType]:
    """
    Determine the polarity of the CNs from the incoming active link.
    """
    cn_polarities = {}
    for link in topology.links.values():
        if (
            link.status_type not in StatusType.active_status()
            or link.rx_site.site_type != SiteType.CN
        ):
            continue

        tx_site = link.tx_site
        # If DN is unassiged, leave the CN polarity as unassigned,
        # compatible_polarity will return true regardless
        polarity = PolarityType.UNASSIGNED
        if tx_site.polarity == PolarityType.EVEN:
            polarity = PolarityType.ODD
        elif tx_site.polarity == PolarityType.ODD:
            polarity = PolarityType.EVEN

        rx_site_id = link.rx_site.site_id
        if rx_site_id in cn_polarities:
            logger.warning(
                f"CN {link.rx_site.name} has mulitple incoming active links"
            )
            # This should never happen because CNs should only have a single
            # active incoming link, however if it does, handle it gracefully
            if cn_polarities[rx_site_id] != polarity:
                cn_polarities[rx_site_id] = PolarityType.UNASSIGNED
        else:
            cn_polarities[rx_site_id] = polarity
    return cn_polarities


def _compatible_polarity(
    link: Link,
    cn_polarities: Dict[str, PolarityType],
) -> bool:
    """
    Verify if a link is connected to active sites with compatible polarities.

    CN sites do not have assigned polarities but their polarity can be
    determined by the polarity of the active incoming link.

    If both end sites are active DN/POPs, then the polarities are
    compatible if their polarities are not equal or either's polarity
    is unassigned.
    """
    tx_site = link.tx_site
    rx_site = link.rx_site

    # Both end sites must be active for polarities to be relevant.
    if (
        tx_site.status_type not in StatusType.active_status()
        or rx_site.status_type not in StatusType.active_status()
    ):
        return False

    tx_pol = tx_site.polarity
    if rx_site.site_type == SiteType.CN:
        rx_pol = cn_polarities[rx_site.site_id]
    else:
        rx_pol = rx_site.polarity

    # No active site should have unassigned polarity
    # Warn about it but assume compatible if either are
    if tx_pol == PolarityType.UNASSIGNED:
        logger.warning(f"Active site {tx_site.name} has unassigned polarity")
    if rx_pol == PolarityType.UNASSIGNED and rx_site.site_type != SiteType.CN:
        # CN warning handled in get_cn_polarities
        logger.warning(f"Active site {rx_site.name} has unassigned polarity")

    odd_or_even = [PolarityType.EVEN, PolarityType.ODD]
    if (
        tx_pol != rx_pol and tx_pol in odd_or_even and rx_pol in odd_or_even
    ) or PolarityType.UNASSIGNED in {tx_pol, rx_pol}:
        return True

    return False


def _compatible_channel(link: Link) -> bool:
    """
    Verify if a link is connected to active sectors with the same channel.
    """
    if link.is_out_of_sector():
        return False

    tx_sector = none_throws(link.tx_sector)
    rx_sector = none_throws(link.rx_sector)

    # Both sectors must be active for channels to be relevant.
    if (
        tx_sector.status_type not in StatusType.active_status()
        or rx_sector.status_type not in StatusType.active_status()
    ):
        return False

    tx_channel = tx_sector.channel
    rx_channel = rx_sector.channel

    # No active sectors should have unassigned channel
    # Warn about it but assume compatible if either are
    if tx_channel <= UNASSIGNED_CHANNEL:
        logger.warning(
            f"Active sector {tx_sector.sector_id} has unassigned channel"
        )
    if rx_channel <= UNASSIGNED_CHANNEL:
        logger.warning(
            f"Active sector {rx_sector.sector_id} has unassigned channel"
        )

    return tx_channel == rx_channel or UNASSIGNED_CHANNEL in {
        tx_channel,
        rx_channel,
    }
