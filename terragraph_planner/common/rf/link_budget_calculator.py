# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import math
from typing import List, Optional, Tuple, Union, cast

import numpy as np
from pyre_extensions import none_throws

from terragraph_planner.common.configuration.configs import SectorParams
from terragraph_planner.common.constants import (
    FREQUENCY_DEPENDENT_OXYGEN_LOSS_MAP,
    FSPL_MARGIN,
    FULL_ROTATION_ANGLE,
)
from terragraph_planner.common.exceptions import DataException, planner_assert
from terragraph_planner.common.structs import (
    AntennaPatternData,
    LinkBudgetMeasurements,
    MCSMap,
    ScanPatternData,
)


def mhz_to_ghz(mhz_value: float) -> float:
    return mhz_value / 1000


def meter_to_kilometer(dist_m: float) -> float:
    return dist_m / 1000


def mbps_to_gbps(mbps: float) -> float:
    return mbps / 1000


def fspl(d_km: float, f_ghz: float) -> float:
    """
    FSPL (dB) when link distance d (kms) and frequency (GHz) is given.
    """
    tol = 10 ** (-FSPL_MARGIN / 20.0 - math.log(f_ghz, 10))
    if d_km <= tol:
        return 0
    return 20.0 * (math.log(d_km, 10) + math.log(f_ghz, 10)) + FSPL_MARGIN


def log_to_linear(dbm_val: float) -> float:
    """Convert the dBm value to mW"""
    return 10 ** (dbm_val / 10)


def linear_to_log(mw_val: float) -> float:
    """Convert from power-ratio to dB (or mW to dBm)"""
    return 10 * math.log10(mw_val)


def get_net_gain(
    ag_tx: float,
    al_tx: float,
    d_km: float,
    f_ghz: float,
    ag_rx: Optional[float],
    al_rx: Optional[float],
    el: float,
) -> float:
    """
    Received gain minus losses (dBi).
    Net_Gain = ag_tx - al_tx + ag_rx - al_rx - fspl(d_km, f_ghz) - el
    If the backhaul link is symmetric (same radio + antenna at Tx and Rx), we get
    Net_Gain = 2 * ag_tx - 2 * al_tx - fspl(d, f) - el

    @param ag_tx: Tx Antenna Gain (dB)
    @param al_tx: Tx Antenna Loss (inclusive of cable loss) (dB)
    @param d_km: distance (km)
    @param f_ghz: frequency of transmission (GHz)
    @param ag_rx: Rx Antenna Gain (dB)
    @param al_rx: Rx Antenna Loss (inclusive of cable loss) (dB)
    @param el: External losses such as oxygen and rain loss (dB)
    """
    # If the rx gains and losses are not specified, then assume it is symmetric
    al_rx = al_tx if al_rx is None else al_rx
    ag_rx = ag_tx if ag_rx is None else ag_rx
    return ag_tx - al_tx + ag_rx - al_rx - fspl(d_km, f_ghz) - el


def get_rsl(
    p_tx: float,
    ag_tx: float,
    al_tx: float,
    d_km: float,
    f_ghz: float,
    ag_rx: Optional[float],
    al_rx: Optional[float],
    el: float,
) -> float:
    """
    Received signal level (dBm).
    RSL = p_tx + net_gain

    @param p_tx: Max Transmit Power (dBm)
    @param ag_tx: Tx Antenna Gain (dB)
    @param al_tx: Tx Antenna Loss (inclusive of cable loss) (dB)
    @param d_km: distance (km)
    @param f_ghz: frequency of transmission (GHz)
    @param ag_rx: Rx Antenna Gain (dB)
    @param al_rx: Rx Antenna Loss (inclusive of cable loss) (dB)
    @param el: External losses such as oxygen and rain loss (dB)
    """
    return p_tx + get_net_gain(ag_tx, al_tx, d_km, f_ghz, ag_rx, al_rx, el)


def is_scan_pattern_data(
    pattern_data: Union[AntennaPatternData, ScanPatternData]
) -> bool:
    """
    Check if the pattern data is type of ScanPatternData
    """
    return all(isinstance(k, float) for k in pattern_data.keys())


def extract_gain_from_radio_pattern(
    boresight_gain: float,
    diversity_gain: float,
    radio_pattern_data: Optional[Union[AntennaPatternData, ScanPatternData]],
    az_deviation: float,
    el_deviation: float,
) -> float:
    """
    This function extracts the total radio gain from antenna/scan pattern
    based on the horizontal and vertical deviations from boresight.

    @param boresight_gain: the gain at boresight
    @param diversity_gain: additional gains
    @param radio_pattern_data: antenna/scan pattern data of the radio
    @param az_deviation: the angle between a link and the radio's
        boresight (in degrees) on horizontal axis
    @param el_deviation: the angle between a link and the radio's
        boresight (in degrees) on vertical axis
    """
    if radio_pattern_data is None:
        return boresight_gain + diversity_gain

    if is_scan_pattern_data(radio_pattern_data):
        # cast to remove pyre errors
        radio_pattern_data = cast(ScanPatternData, radio_pattern_data)
        max_boresight_gain = get_max_boresight_gain_from_pattern_file(
            radio_pattern_data
        )
        # round az_deviation and el_deviation to the closest available value
        r = (
            radio_pattern_data.get(az_deviation)
            or radio_pattern_data[
                min(
                    radio_pattern_data.keys(),
                    key=lambda key: abs(key - az_deviation),
                )
            ]
        )
        scan_loss = (
            r.get(el_deviation)
            or r[min(r.keys(), key=lambda key: abs(key - el_deviation))]
        ) - max_boresight_gain
        return boresight_gain + scan_loss + diversity_gain

    # In planet's antenna pattern format, they first list the horizontal (az)
    # axis gains and then the vertical (el) gains. When we read these files in,
    # this ordering translates into 0 for horizontal and 1 for vertical axes.
    AZ_INDEX = 0
    EL_INDEX = 1
    # Some antenna patterns may contain gains for multiple antenna types
    # Currently, we always take the first antenna as the main hardware
    radio_pattern_data = cast(AntennaPatternData, radio_pattern_data)
    antenna_names_in_pattern = list(radio_pattern_data.keys())
    antenna_type = (
        antenna_names_in_pattern[0]
        if len(antenna_names_in_pattern) > 0
        else None
    )
    planner_assert(
        antenna_type is not None,
        "No antennas were found in the antenna pattern file.",
        DataException,
    )

    # Convert deviation from (-180, 180] to [0, 360)
    # Round value first so small negative number goes to 0 not 360
    el_dev_360 = round(el_deviation)
    el_dev_360 = (
        el_dev_360 if el_dev_360 >= 0 else el_dev_360 + int(FULL_ROTATION_ANGLE)
    )
    az_dev_360 = round(az_deviation)
    az_dev_360 = (
        az_dev_360 if az_dev_360 >= 0 else az_dev_360 + int(FULL_ROTATION_ANGLE)
    )
    el_gain = radio_pattern_data[none_throws(antenna_type)][EL_INDEX][
        el_dev_360
    ]
    az_gain = radio_pattern_data[none_throws(antenna_type)][AZ_INDEX][
        az_dev_360
    ]
    return boresight_gain + diversity_gain + el_gain + az_gain


def compute_rain_loss(
    dist_km: float,
    rain_rate: float,
    link_availability_percentage: float,
    carrier_frequency: float,
) -> float:
    """
    Mathematical model from ITU to compute rain loss

    @param dist_km: length of the link in kilometers
    @param rain_rate: rain rate for the planning region in mm/hr
    @param link_availability_percentage: percentage of time in one year that
        each line-of-sight (LOS) link will be live
    @param carrier_frequency: carrier frequency in MHz
    """
    if dist_km <= 0:
        return 0

    frequency_ghz = mhz_to_ghz(carrier_frequency)

    p = 100 - link_availability_percentage
    k = 0.8515
    alpha = 0.7486
    gamma_r = k * math.pow(rain_rate, alpha)
    a = gamma_r * dist_km

    r = 1 / (
        0.477
        * math.pow(dist_km, 0.633)
        * math.pow(rain_rate, 0.073 * alpha)
        * math.pow(frequency_ghz, 0.123)
        - 10.579 * (1 - math.exp(-0.024 * dist_km))
    )
    r = min(r, 2.5)  # r should not exceed 2.5
    a_001 = a * r

    c0 = 0.12 + 0.4 * math.log10(math.pow(frequency_ghz / 10, 0.8))
    c1 = math.pow(0.07, c0) * math.pow(0.12, 1 - c0)
    c2 = 0.855 * c0 + 0.546 * (1 - c0)
    c3 = 0.139 * c0 + 0.043 * (1 - c0)
    a_p = a_001 * c1 * math.pow(p, -(c2 + c3 * math.log10(p)))
    return max(a_p, 0)


def compute_oxygen_loss(dist_km: float, carrier_frequency: float) -> float:
    """
    Compute oxygen absorption loss

    @param dist_km: length of the link in kilometers
    @param carrier_frequency: carrier frequency in MHz
    """
    oxygen_loss_map = FREQUENCY_DEPENDENT_OXYGEN_LOSS_MAP
    frequency_ghz = mhz_to_ghz(carrier_frequency)

    oxygen_loss = np.interp(
        frequency_ghz,
        np.fromiter(oxygen_loss_map.keys(), dtype=float),
        np.fromiter(oxygen_loss_map.values(), dtype=float),
        left=0.0,
        right=0.0,
    )

    return float(oxygen_loss) * dist_km


def get_fspl_based_net_gain(
    dist_m: float,
    tx_sector_params: SectorParams,
    tx_radio_pattern_data: Optional[Union[AntennaPatternData, ScanPatternData]],
    rx_sector_params: Optional[SectorParams],
    rx_radio_pattern_data: Optional[Union[AntennaPatternData, ScanPatternData]],
    tx_deviation: float,
    rx_deviation: float,
    tx_el_deviation: float,
    rx_el_deviation: float,
) -> float:
    """
    Compute received net gain (dBi) at the receiver assuming that:
    1) If the antenna pattern file has multiple antennas, we use the
    first specs entered by default.
    2) the transmitter and the receiver have the same specifications.
    3) both tx and rx antennas are at the same height (no EL consideration).

    @param dist_m: length of the link in meters.
    @param tx_sector_params: The list of parameters that has tx radio related specifications
    @param tx_radio_pattern_data: The antenna/scan pattern data for the tx radio.
    @param rx_sector_params: The list of parameters that has rx radio related specifications
    @param rx_radio_pattern_data: The antenna/scan pattern data for the rx radio.
    @param tx_deviation: Horizontal deviation from boresight in tx direction (degrees)
    @param rx_deviation: Horizontal deviation from boresight in rx direction (degrees)
    @param tx_el_deviation: Vertical deviation from horizontal plane in tx direction (degrees)
    @param rx_el_deviation: Vertical deviation from horizontal plane rx rx direction (degrees)
    """

    # FSPL (dB) when link distance d (kms) and frequency (GHz) is given.
    frequency_ghz = mhz_to_ghz(tx_sector_params.carrier_frequency)
    dist_km = meter_to_kilometer(dist_m)

    # If rx_sector_params or pattern is not specified, we assume that tx and
    # rx sectors have the exact same configurations.
    if rx_sector_params is None:
        rx_sector_params = tx_sector_params
        rx_radio_pattern_data = tx_radio_pattern_data

    # We assume that there is a single type of DN antenna and
    # a single CN antenna. If no CN antenna parameters are specified, we assume
    # that there is only a single type of hardware used.
    tx_gain = extract_gain_from_radio_pattern(
        tx_sector_params.antenna_boresight_gain,
        tx_sector_params.tx_diversity_gain,
        tx_radio_pattern_data,
        tx_deviation,
        tx_el_deviation,
    )
    rx_gain = extract_gain_from_radio_pattern(
        rx_sector_params.antenna_boresight_gain,
        rx_sector_params.rx_diversity_gain,
        rx_radio_pattern_data,
        rx_deviation,
        rx_el_deviation,
    )
    rain_loss = compute_rain_loss(
        dist_km=dist_km,
        rain_rate=tx_sector_params.rain_rate,
        link_availability_percentage=tx_sector_params.link_availability_percentage,
        carrier_frequency=tx_sector_params.carrier_frequency,
    )
    oxygen_loss = compute_oxygen_loss(
        dist_km=dist_km, carrier_frequency=tx_sector_params.carrier_frequency
    )

    return get_net_gain(
        tx_gain,
        tx_sector_params.tx_miscellaneous_loss,
        dist_km,
        frequency_ghz,
        rx_gain,
        rx_sector_params.rx_miscellaneous_loss,
        rain_loss + oxygen_loss,
    )


def get_max_boresight_gain_from_pattern_file(
    scan_pattern_data: ScanPatternData,
) -> float:
    """
    Get the maximum value from the scan pattern data
    """
    return max(
        max(val for val in row.values()) for row in scan_pattern_data.values()
    )


def get_max_tx_power(
    tx_sector_params: SectorParams,
    max_eirp_dbm: Optional[float],
) -> float:
    """
    Maximum Tx power = min(Max EIRP - Tx Antenna Gain, user input Max Tx power)
    """
    max_tx_power = tx_sector_params.maximum_tx_power
    if max_eirp_dbm is not None:
        max_tx_gain = extract_gain_from_radio_pattern(
            boresight_gain=tx_sector_params.antenna_boresight_gain,
            diversity_gain=tx_sector_params.tx_diversity_gain,
            radio_pattern_data=None,
            az_deviation=0,
            el_deviation=0,
        )
        max_tx_power = float(
            min(
                max_tx_power,
                max_eirp_dbm - max_tx_gain,
            ),
        )
    if tx_sector_params.minimum_tx_power is not None:
        max_tx_power = float(
            max(tx_sector_params.minimum_tx_power, max_tx_power)
        )
    return max_tx_power


def get_backoff_from_mcs(
    mcs_level: int, mcs_snr_mbps_map: List[MCSMap]
) -> float:
    """
    Return Tx power backoff given the MCS level
    """
    tx_backoff = [
        row.tx_backoff for row in mcs_snr_mbps_map if row.mcs == mcs_level
    ]
    return tx_backoff[0] if len(tx_backoff) > 0 else 0.0


def adjust_tx_power_with_backoff(
    mcs_level: int,
    mcs_snr_mbps_map: List[MCSMap],
    min_tx_power: Optional[float],
    max_tx_power: float,
    net_gain_dbi: float,
    np_dbm: float,
) -> Tuple[int, float]:
    """
    Get the adjusted Tx power considering Tx power backoff. For a given MCS
    level, if the Tx power exceeds the adjusted max Tx power (max Tx power minus
    backoff), the MCS level (and hence the corresponding Tx power) is reduced
    until that is no longer the case. This function returns the adjusted MCS
    level and Tx power.
    """
    while mcs_level > 0:
        snr_dbm = get_snr_from_mcs(mcs_level, mcs_snr_mbps_map)
        rsl_dbm = get_snr_based_rsl(snr_dbm, np_dbm)
        tx_power = get_tx_power_from_rsl(rsl_dbm, net_gain_dbi)
        if min_tx_power is not None:
            tx_power = max(min_tx_power, tx_power)
        tx_backoff = get_backoff_from_mcs(mcs_level, mcs_snr_mbps_map)
        if tx_power <= max_tx_power - tx_backoff:
            return mcs_level, tx_power
        mcs_level -= 1
    return 0, -math.inf


def get_fspl_based_rsl(maximum_tx_power: float, net_gain_dbi: float) -> float:
    """
    Compute received signal level (dBm) at the receiver.
    RSL (dBm) = Tx Power (dBm) + Net Gain (dBi)
    """

    return maximum_tx_power + net_gain_dbi


def get_noise_power(sectorParams: SectorParams) -> float:
    """
    Noise power (dBm) = Noise Figure (dB) + Thermal Noise Power (dBm)
    """
    return sectorParams.noise_figure + sectorParams.thermal_noise_power


def get_snr(rsl_dbm: float, noise_power_dbm: float) -> float:
    """
    SNR (dB) = RSL (dBm) - Noise power (dBm)
    """
    return rsl_dbm - noise_power_dbm


def get_mcs_from_snr(snr_dbm: float, mcs_snr_mbps_map: List[MCSMap]) -> int:
    """
    Assuming that a mapping between SNR thresholds and MCS values are given,
    look-up the MCS value that snr_dbm corresponds to.
    For example, if the table MCS -> SNR looks like the following:
    MCS_TO_SNR = {8: 9, 9: 12, 10: 14, 11: 16, 12: 18},
    then an SNR value less than 9 will be assumed to have MCS-zero (no throughput),
    if 12 > SNR >= 9, then the link corresponds to MCS8,
    if 14 > SNR >= 12, then the link corresponds to MCS9 and so on.
    MCS = max{mcs: snr_dbm >= SNR[mcs]}
    """
    mcs_snr_mapping = {row.mcs: row.snr for row in mcs_snr_mbps_map}
    if math.isnan(snr_dbm) or snr_dbm < min(mcs_snr_mapping.values()):
        return 0

    mcs_level = max(m for m, t in mcs_snr_mapping.items() if snr_dbm >= t)
    return mcs_level


def get_snr_from_mcs(mcs: int, mcs_snr_mbps_map: List[MCSMap]) -> float:
    """
    Assuming that a mapping between SNR thresholds and MCS values are given,
    look-up the SNR value that MCS corresponds to.
    For example, if the table MCS -> SNR looks like the following:
    MCS_TO_SNR = {8: 9, 9: 12, 11: 16, 12: 18}, where NO MCS 10,
    then an MCS value less than 8 will be assumed to have SNR-zero (no throughput),
    if MCS = 10, then the link corresponds to snr_dbm = 12 (same as MCS 9),
    if MCS >= 12, then the link corresponds to snr_dbm = 18 and so on.
    snr_dbm = max{snr: MCS >= MCS[snr]}
    """
    snr_mcs_mapping = {row.snr: row.mcs for row in mcs_snr_mbps_map}
    if mcs < min(snr_mcs_mapping.values()):
        return 0

    snr_dbm = max(t for t, m in snr_mcs_mapping.items() if mcs >= m)
    return snr_dbm


def get_snr_based_rsl(snr_dbm: float, noise_power_dbm: float) -> float:
    """
    RSL (dBm) = SNR (dB) + Noise power (dBm)
    """
    return snr_dbm + noise_power_dbm


def get_tx_power_from_rsl(rsl_dbm: float, net_gain_dbi: float) -> float:
    """
    Tx Power (dBm) = RSL (dBm)  - Net Gain (dBi)
    """
    return rsl_dbm - net_gain_dbi


def get_link_capacity_from_mcs(
    mcs_level: int, mcs_snr_mbps_map: List[MCSMap]
) -> float:
    """
    Returns Mbps values given the MCS level
    """
    mbps_value = [row.mbps for row in mcs_snr_mbps_map if row.mcs == mcs_level]
    if len(mbps_value) == 0:
        return 0.0
    return mbps_to_gbps(mbps_value[0])


def fspl_based_estimation(
    distance: float,
    max_tx_power: float,
    tx_sector_params: SectorParams,
    rx_sector_params: SectorParams,
    mcs_snr_mbps_map: List[MCSMap],
    tx_deviation: float,
    rx_deviation: float,
    tx_el_deviation: float,
    rx_el_deviation: float,
    tx_scan_pattern_data: Optional[ScanPatternData],
    rx_scan_pattern_data: Optional[ScanPatternData],
) -> LinkBudgetMeasurements:
    """
    Compute link budget measures based on FSPL
    @param distance: The distance between two sites, i.e. the length of the link.
    @param tx_deviation: The horizontal deviation between tx sector and the link.
    @param rx_deviation: The horizontal deviation between rx sector and the link.
    @param tx_el_deviation: The elevation deviation of the link in the tx direction.
    @param rx_el_deviation: The elevation deviation of the link in the rx direction.
    @param max_tx_power: The maximum power of the transmitter site.
    @param tx_sector_params: The list of parameters that has tx radio related specifications
    @param rx_sector_params: The list of parameters that has rx radio related specifications
    @param mcs_snr_mbps_map: mapping between mcs, snr and down-link throughput (mbps)
    @param tx_antenna_pattern: The antenna pattern for the tx radio.
    @param rx_antenna_pattern: The antenna pattern for the rx radio.

    Note: the output tx power is the maximum allowed for the MCS class of the link.
    Due to tx power backoff, this could result in a SNR/RSL that would place the link
    into a higher MCS class. However, this function is primarily used to
    - Compute capacity of a link for determining the max LOS distance (so tx power, SNR,
      RSL do not matter)
    - During pre-optimization setup for usage during interference modeling in the
      optimization phase. There, the RSL values matter and we want these to be as high as
      possible so as to not artifically lower the MCS class of a link when encountering
      interference
    - Prior to TPC where we do not want to artificially lower the MCS class of a link when
      encountering interference. In that case, the TPC iteration will ensure that the final
      tx power output is the minimal necessary to achieve the MCS class (i.e., this is simply
      used to initialize the TPC iteration)
    """
    # First compute link budget using maximum possible tx power
    net_gain_dbi = get_fspl_based_net_gain(
        dist_m=distance,
        tx_sector_params=tx_sector_params,
        tx_radio_pattern_data=tx_scan_pattern_data,
        rx_sector_params=rx_sector_params,
        rx_radio_pattern_data=rx_scan_pattern_data,
        tx_deviation=tx_deviation,
        rx_deviation=rx_deviation,
        tx_el_deviation=tx_el_deviation,
        rx_el_deviation=rx_el_deviation,
    )
    np_dbm = get_noise_power(rx_sector_params)

    rsl_dbm = get_fspl_based_rsl(max_tx_power, net_gain_dbi)
    snr_dbm = get_snr(rsl_dbm, np_dbm)
    mcs_level = get_mcs_from_snr(snr_dbm, mcs_snr_mbps_map)

    # Adjust tx power considering tx power backoff, i.e., tx power for computed
    # MCS level might exceed allowed tx power
    mcs_level, _ = adjust_tx_power_with_backoff(
        mcs_level=mcs_level,
        mcs_snr_mbps_map=mcs_snr_mbps_map,
        min_tx_power=tx_sector_params.minimum_tx_power,
        max_tx_power=max_tx_power,
        net_gain_dbi=net_gain_dbi,
        np_dbm=np_dbm,
    )
    capacity = get_link_capacity_from_mcs(mcs_level, mcs_snr_mbps_map)

    # Set tx power to maximum tx power allowed for that MCS level
    tx_backoff = get_backoff_from_mcs(mcs_level, mcs_snr_mbps_map)
    tx_power = max_tx_power - tx_backoff
    # Due to tx power backoff, SNR could be high enough to merit higher MCS
    # class. But doing so would violate the max allowed tx power, so the MCS
    # class (and hence capacity) is artifically lowered
    rsl_dbm = get_fspl_based_rsl(tx_power, net_gain_dbi)
    snr_dbm = get_snr(rsl_dbm, np_dbm)

    return LinkBudgetMeasurements(
        mcs_level=mcs_level,
        rsl_dbm=rsl_dbm,
        snr_dbm=snr_dbm,
        capacity=capacity,
        tx_power=tx_power,
    )
