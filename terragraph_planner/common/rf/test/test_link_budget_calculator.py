# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import unittest

from terragraph_planner.common.configuration.configs import SectorParams
from terragraph_planner.common.constants import DEFAULT_MCS_SNR_MBPS_MAP
from terragraph_planner.common.data_io.csv_library import (
    read_antenna_pattern_data,
    read_scan_pattern_data,
)
from terragraph_planner.common.rf.link_budget_calculator import (
    adjust_tx_power_with_backoff,
    compute_oxygen_loss,
    compute_rain_loss,
    extract_gain_from_radio_pattern,
    fspl,
    fspl_based_estimation,
    get_fspl_based_net_gain,
    get_fspl_based_rsl,
    get_link_capacity_from_mcs,
    get_max_boresight_gain_from_pattern_file,
    get_mcs_from_snr,
    get_net_gain,
    get_noise_power,
    get_rsl,
    get_snr,
    get_snr_based_rsl,
    get_snr_from_mcs,
    get_tx_power_from_rsl,
    meter_to_kilometer,
    mhz_to_ghz,
)
from terragraph_planner.common.structs import LinkBudgetMeasurements, MCSMap

DATA_PATH = "terragraph_planner/common/data_io/test/test_data/"


class TestBaseRSLComputation(unittest.TestCase):
    def setUp(self) -> None:
        self.dist = 10  # km
        self.freq = 60  # GHz
        self.fspl = fspl(self.dist, self.freq)
        self.tx_gain = 30
        self.tx_loss = 20
        self.pwr = 20

    def test_rsl_at_zero(self) -> None:
        self.assertAlmostEqual(
            get_net_gain(0, 0, 0, self.freq, None, None, 0), 0.0
        )
        self.assertAlmostEqual(
            get_rsl(0, 0, 0, 0, self.freq, None, None, 0), 0.0
        )

    def test_rsl_without_antenna(self) -> None:
        # rsl = 0 + 0 - 0 - fspl
        self.assertAlmostEqual(
            get_net_gain(0, 0, self.dist, self.freq, None, None, 0), -self.fspl
        )
        self.assertAlmostEqual(
            get_rsl(0, 0, 0, self.dist, self.freq, None, None, 0), -self.fspl
        )

    def test_rsl_without_power(self) -> None:
        # rsl = 0 + 2 * 30 - 2 * 20 - fspl
        self.assertAlmostEqual(
            get_net_gain(
                self.tx_gain, self.tx_loss, self.dist, self.freq, None, None, 0
            ),
            20 - self.fspl,
        )
        self.assertAlmostEqual(
            get_rsl(
                0,
                self.tx_gain,
                self.tx_loss,
                self.dist,
                self.freq,
                None,
                None,
                0,
            ),
            20 - self.fspl,
        )

    def test_rsl_with_power(self) -> None:
        # rsl = 20 + 2 * 30 - 2 * 20 - fspl
        self.assertAlmostEqual(
            get_rsl(
                self.pwr,
                self.tx_gain,
                self.tx_loss,
                self.dist,
                self.freq,
                None,
                None,
                0,
            ),
            40 - self.fspl,
        )

    def test_symmetric_rsl(self) -> None:
        # rsl = 20 + 2 * 30 - 2 * 20 - fspl
        self.assertAlmostEqual(
            get_net_gain(
                self.tx_gain,
                self.tx_loss,
                self.dist,
                self.freq,
                self.tx_gain,
                self.tx_loss,
                0,
            ),
            get_net_gain(
                self.tx_gain, self.tx_loss, self.dist, self.freq, None, None, 0
            ),
        )
        self.assertAlmostEqual(
            get_rsl(
                self.pwr,
                self.tx_gain,
                self.tx_loss,
                self.dist,
                self.freq,
                self.tx_gain,
                self.tx_loss,
                0,
            ),
            get_rsl(
                self.pwr,
                self.tx_gain,
                self.tx_loss,
                self.dist,
                self.freq,
                None,
                None,
                0,
            ),
        )

    def test_true_unsymmetric_rsl(self) -> None:
        # rsl = 20 + 30 - 20 + 10 - 20 - fspl
        rx_gain = 10
        rx_loss = 20
        self.assertAlmostEqual(
            get_net_gain(
                self.tx_gain,
                self.tx_loss,
                self.dist,
                self.freq,
                rx_gain,
                rx_loss,
                0,
            ),
            -self.fspl,
        )
        self.assertAlmostEqual(
            get_rsl(
                self.pwr,
                self.tx_gain,
                self.tx_loss,
                self.dist,
                self.freq,
                rx_gain,
                rx_loss,
                0,
            ),
            20 - self.fspl,
        )


class TestFSPLBasedRSLValue(unittest.TestCase):
    test_distance_m = 100  # meters
    tx_sector_params: SectorParams = SectorParams(
        antenna_boresight_gain=30,
        rx_diversity_gain=30,
        tx_miscellaneous_loss=15,
        rx_miscellaneous_loss=1,
    )
    rx_sector_params: SectorParams = SectorParams(
        antenna_boresight_gain=20,
        rx_diversity_gain=7,
        tx_miscellaneous_loss=15,
        rx_miscellaneous_loss=5,
    )

    def test_symmetric_rsl_at_boresight(self) -> None:
        # At 100 meters, we expect RSL to be equal to
        # tx_gain_at_boresight (30)  + rx_gain_at_boresight (30)
        # + tx_diversity_gain (0) + rx_diversity_gain (30)
        # - tx_miscellaneous_loss (15) - rx_miscellaneous_loss (1)- FSPL(frequency, distance)
        gains_and_losses = (
            self.tx_sector_params.antenna_boresight_gain
            + self.tx_sector_params.antenna_boresight_gain
            + self.tx_sector_params.tx_diversity_gain
            + self.tx_sector_params.rx_diversity_gain
            - self.tx_sector_params.tx_miscellaneous_loss
            - self.tx_sector_params.rx_miscellaneous_loss
        )
        gains_and_losses_manual = 30.0 + 30.0 + 0.0 + 30.0 - 15.0 - 1.0
        self.assertEqual(gains_and_losses, gains_and_losses_manual)

        fspl_val = fspl(
            meter_to_kilometer(self.test_distance_m),
            mhz_to_ghz(self.tx_sector_params.carrier_frequency),
        )
        dist_km = meter_to_kilometer(self.test_distance_m)
        rain_loss = compute_rain_loss(
            dist_km=dist_km,
            rain_rate=self.tx_sector_params.rain_rate,
            link_availability_percentage=self.tx_sector_params.link_availability_percentage,
            carrier_frequency=self.tx_sector_params.carrier_frequency,
        )
        oxygen_loss = compute_oxygen_loss(
            dist_km=dist_km,
            carrier_frequency=self.tx_sector_params.carrier_frequency,
        )
        expected_net_gain = (
            gains_and_losses - fspl_val - oxygen_loss - rain_loss
        )
        computed_net_gain = get_fspl_based_net_gain(
            self.test_distance_m,
            self.tx_sector_params,
            None,
            None,
            None,
            0,
            0,
            0,
            0,
        )
        self.assertAlmostEqual(expected_net_gain, computed_net_gain)

        expected_rsl_value = (
            gains_and_losses
            + self.tx_sector_params.maximum_tx_power
            - fspl_val
            - oxygen_loss
            - rain_loss
        )
        computed_RSL_value = get_fspl_based_rsl(
            self.tx_sector_params.maximum_tx_power, computed_net_gain
        )
        self.assertAlmostEqual(expected_rsl_value, computed_RSL_value)

        expected_np_value = (
            self.tx_sector_params.noise_figure
            + self.tx_sector_params.thermal_noise_power
        )
        computed_np_value = get_noise_power(self.tx_sector_params)
        self.assertAlmostEqual(expected_np_value, computed_np_value)

        expected_SNR_value = (
            expected_rsl_value
            - self.tx_sector_params.noise_figure
            - self.tx_sector_params.thermal_noise_power
        )
        computed_SNR_value = get_snr(computed_RSL_value, computed_np_value)
        self.assertAlmostEqual(expected_SNR_value, computed_SNR_value)

    def test_asymmetric_rsl_at_boresight(self) -> None:
        # At 100 meters, we expect RSL to be equal to
        # tx_gain_at_boresight (30)  + rx_gain_at_boresight (30)
        # + tx_diversity_gain (0) + rx_diversity_gain (30)
        # - tx_miscellaneous_loss (15) - rx_miscellaneous_loss (1)- FSPL(frequency, distance)

        gains_and_losses = (
            self.tx_sector_params.antenna_boresight_gain
            + self.rx_sector_params.antenna_boresight_gain
            + self.tx_sector_params.tx_diversity_gain
            + self.rx_sector_params.rx_diversity_gain
            - self.tx_sector_params.tx_miscellaneous_loss
            - self.rx_sector_params.rx_miscellaneous_loss
        )
        gains_and_losses_manual = 30.0 + 20.0 + 0.0 + 7.0 - 15.0 - 5.0
        self.assertEqual(gains_and_losses, gains_and_losses_manual)

        fspl_val = fspl(
            meter_to_kilometer(self.test_distance_m),
            mhz_to_ghz(self.tx_sector_params.carrier_frequency),
        )
        dist_km = meter_to_kilometer(self.test_distance_m)
        rain_loss = compute_rain_loss(
            dist_km=dist_km,
            rain_rate=self.tx_sector_params.rain_rate,
            link_availability_percentage=self.tx_sector_params.link_availability_percentage,
            carrier_frequency=self.tx_sector_params.carrier_frequency,
        )
        oxygen_loss = compute_oxygen_loss(
            dist_km=dist_km,
            carrier_frequency=self.tx_sector_params.carrier_frequency,
        )
        expected_net_gain = (
            gains_and_losses - fspl_val - oxygen_loss - rain_loss
        )
        computed_net_gain = get_fspl_based_net_gain(
            self.test_distance_m,
            self.tx_sector_params,
            None,
            self.rx_sector_params,
            None,
            0,
            0,
            0,
            0,
        )
        self.assertAlmostEqual(expected_net_gain, computed_net_gain)

        expected_rsl_value = (
            gains_and_losses
            + self.tx_sector_params.maximum_tx_power
            - fspl_val
            - oxygen_loss
            - rain_loss
        )
        computed_RSL_value = get_fspl_based_rsl(
            self.tx_sector_params.maximum_tx_power, computed_net_gain
        )
        self.assertAlmostEqual(expected_rsl_value, computed_RSL_value)

        expected_np_value = (
            self.tx_sector_params.noise_figure
            + self.tx_sector_params.thermal_noise_power
        )
        computed_np_value = get_noise_power(self.tx_sector_params)
        self.assertAlmostEqual(expected_np_value, computed_np_value)

        expected_SNR_value = (
            expected_rsl_value
            - self.tx_sector_params.noise_figure
            - self.tx_sector_params.thermal_noise_power
        )
        computed_SNR_value = get_snr(computed_RSL_value, computed_np_value)
        self.assertAlmostEqual(expected_SNR_value, computed_SNR_value)

    def test_rain_loss_computation(self) -> None:
        rain_loss = compute_rain_loss(
            dist_km=1,
            rain_rate=30,
            link_availability_percentage=self.tx_sector_params.link_availability_percentage,
            carrier_frequency=self.tx_sector_params.carrier_frequency,
        )
        self.assertAlmostEqual(rain_loss, 5.8, places=1)


class TestLinkMCS(unittest.TestCase):
    sector_params = SectorParams(antenna_boresight_gain=15.0)

    def test_distance_mcs_mapping(self) -> None:
        test_data = [(40, 12), (50, 11), (60, 10), (70, 9), (80, 8)]
        antenna_pattern_data = read_antenna_pattern_data(
            DATA_PATH + "test_antenna_pattern.txt"
        )
        for dist_m, expected_mcs in test_data:
            net_gain_dbi = get_fspl_based_net_gain(
                dist_m,
                self.sector_params,
                antenna_pattern_data,
                None,
                None,
                0,
                0,
                0,
                0,
            )
            rsl_dbm = get_fspl_based_rsl(
                self.sector_params.maximum_tx_power, net_gain_dbi
            )
            np_dbm = get_noise_power(self.sector_params)
            snr_dbm = get_snr(rsl_dbm, np_dbm)
            mcs_level = get_mcs_from_snr(snr_dbm, DEFAULT_MCS_SNR_MBPS_MAP)
            self.assertEqual(mcs_level, expected_mcs)

    def test_snr_mcs_mapping(self) -> None:
        """
        Test various SNR values against their expected MCS mappings
        """
        test_data = [
            (3, 3),
            (4.5, 4),
            (5, 5),
            (5.5, 6),
            (18, 12),
            (2, 0),
            (20, 12),
            (5.3, 5),
        ]
        for snr_dbm, expected_mcs in test_data:
            self.assertEqual(
                get_mcs_from_snr(snr_dbm, DEFAULT_MCS_SNR_MBPS_MAP),
                expected_mcs,
            )


class TestLinkTxPower(unittest.TestCase):
    sector_params = SectorParams(maximum_tx_power=30)

    def test_mcs_snr_mapping(self) -> None:
        """
        Test various MCS values against their expected SNR mappings
        """
        test_data = [
            (3, 3),
            (4, 4.5),
            (5, 5),
            (6, 5.5),
            (12, 18),
            (0, 0),
            (14, 18),
        ]
        for mcs, expected_snr in test_data:
            self.assertEqual(
                get_snr_from_mcs(mcs, DEFAULT_MCS_SNR_MBPS_MAP), expected_snr
            )

    def test_mcs_rsl_mapping(self) -> None:
        """
        Test various MCS values against their expected RSL mappings
        """
        test_data = [
            (3, -71),
            (4, -69.5),
            (5, -69),
            (6, -68.5),
            (12, -56),
            (0, -74),
            (14, -56),
        ]
        for mcs, expected_rsl in test_data:
            snr_dbm = get_snr_from_mcs(mcs, DEFAULT_MCS_SNR_MBPS_MAP)
            np_dbm = get_noise_power(self.sector_params)
            self.assertEqual(get_snr_based_rsl(snr_dbm, np_dbm), expected_rsl)

    def test_mcs_capacity_mapping(self) -> None:
        """
        Test various MCS values against their expected capacity mappings
        """
        test_data = [
            (3, 0),
            (4, 67.5),
            (5, 115),
            (6, 260),
            (12, 1800),
            (0, 0),
            (14, 1800),
        ]
        for mcs, expected_capacity in test_data:
            snr_dbm = get_snr_from_mcs(mcs, DEFAULT_MCS_SNR_MBPS_MAP)
            mcs_level = get_mcs_from_snr(snr_dbm, DEFAULT_MCS_SNR_MBPS_MAP)
            self.assertEqual(
                get_link_capacity_from_mcs(mcs_level, DEFAULT_MCS_SNR_MBPS_MAP),
                mhz_to_ghz(expected_capacity),
            )

    def test_mcs_tx_power_mapping(self) -> None:
        """
        Test various MCS values against their expected Tx power mappings
        """
        test_data = [
            (3, -20.5),
            (4, -19.0),
            (5, -18.5),
            (6, -18.0),
            (12, -5.5),
            (0, -23.5),
        ]
        dist_m = 100
        antenna_pattern_data = read_antenna_pattern_data(
            DATA_PATH + "test_antenna_pattern.txt"
        )
        for mcs, expected_tx_power in test_data:
            snr_dbm = get_snr_from_mcs(mcs, DEFAULT_MCS_SNR_MBPS_MAP)
            np_dbm = get_noise_power(self.sector_params)
            rsl_dbm = get_snr_based_rsl(snr_dbm, np_dbm)
            net_gain_dbi = get_fspl_based_net_gain(
                dist_m,
                self.sector_params,
                antenna_pattern_data,
                None,
                None,
                0,
                0,
                0,
                0,
            )
            max_tx_power_dbm = get_tx_power_from_rsl(rsl_dbm, net_gain_dbi)
            self.assertAlmostEqual(
                max_tx_power_dbm, expected_tx_power, places=1
            )

    def test_tx_power_backoff_adjustment(self) -> None:
        min_tx_power, max_tx_power, net_gain_dbi, np_dbm = (
            -12.0,
            20,
            0.0,
            0.0,
        )
        mcs_level = 11

        # The regulated MCS is the same as expected MCS
        mcs, _ = adjust_tx_power_with_backoff(
            mcs_level=mcs_level,
            mcs_snr_mbps_map=DEFAULT_MCS_SNR_MBPS_MAP,
            min_tx_power=min_tx_power,
            max_tx_power=max_tx_power,
            net_gain_dbi=net_gain_dbi,
            np_dbm=np_dbm,
        )
        self.assertEqual(mcs, mcs_level)

        # The regulated MCS is no less than expected MCS with tx_backoff = 1.0
        mcs_snr_mbps_map = []
        for row in DEFAULT_MCS_SNR_MBPS_MAP:
            if row.mcs < 10:
                mcs_snr_mbps_map.append(row)
            else:
                mod_row = MCSMap(
                    mcs=row.mcs, snr=row.snr, mbps=row.mbps, tx_backoff=1.0
                )
                mcs_snr_mbps_map.append(mod_row)
        mcs, _ = adjust_tx_power_with_backoff(
            mcs_level=mcs_level,
            mcs_snr_mbps_map=mcs_snr_mbps_map,
            min_tx_power=min_tx_power,
            max_tx_power=max_tx_power,
            net_gain_dbi=net_gain_dbi,
            np_dbm=np_dbm,
        )
        self.assertGreaterEqual(mcs, mcs_level)

        # 0 MCS level should kept 0
        mcs_level = 0
        mcs, _ = adjust_tx_power_with_backoff(
            mcs_level=mcs_level,
            mcs_snr_mbps_map=mcs_snr_mbps_map,
            min_tx_power=min_tx_power,
            max_tx_power=max_tx_power,
            net_gain_dbi=net_gain_dbi,
            np_dbm=np_dbm,
        )
        self.assertEqual(mcs, mcs_level)


class TestFSPLBasedEstimation(unittest.TestCase):
    sector_params = SectorParams(antenna_boresight_gain=15.0)

    def test_distance_link_budgets(self) -> None:
        test_data = [
            (
                40,
                LinkBudgetMeasurements(
                    mcs_level=10,
                    rsl_dbm=-57.1,
                    snr_dbm=16.9,
                    capacity=1.030,
                    tx_power=14.0,
                ),
            ),
            (
                50,
                LinkBudgetMeasurements(
                    mcs_level=10,
                    rsl_dbm=-59.3,
                    snr_dbm=14.7,
                    capacity=1.030,
                    tx_power=14.0,
                ),
            ),
            (
                60,
                LinkBudgetMeasurements(
                    mcs_level=9,
                    rsl_dbm=-59.1,
                    snr_dbm=14.9,
                    capacity=0.74125,
                    tx_power=16.0,
                ),
            ),
            (
                70,
                LinkBudgetMeasurements(
                    mcs_level=9,
                    rsl_dbm=-60.7,
                    snr_dbm=13.3,
                    capacity=0.74125,
                    tx_power=16.0,
                ),
            ),
            (
                80,
                LinkBudgetMeasurements(
                    mcs_level=8,
                    rsl_dbm=-62.1,
                    snr_dbm=11.9,
                    capacity=0.645,
                    tx_power=16.0,
                ),
            ),
            (
                90,
                LinkBudgetMeasurements(
                    mcs_level=8,
                    rsl_dbm=-63.4,
                    snr_dbm=10.6,
                    capacity=0.645,
                    tx_power=16.0,
                ),
            ),
            (
                100,
                LinkBudgetMeasurements(
                    mcs_level=8,
                    rsl_dbm=-64.5,
                    snr_dbm=9.5,
                    capacity=0.645,
                    tx_power=16.0,
                ),
            ),
            (
                125,
                LinkBudgetMeasurements(
                    mcs_level=6,
                    rsl_dbm=-67.1,
                    snr_dbm=6.9,
                    capacity=0.260,
                    tx_power=16.0,
                ),
            ),
            (
                150,
                LinkBudgetMeasurements(
                    mcs_level=4,
                    rsl_dbm=-69.3,
                    snr_dbm=4.7,
                    capacity=0.0675,
                    tx_power=16.0,
                ),
            ),
            (
                175,
                LinkBudgetMeasurements(
                    mcs_level=0,
                    rsl_dbm=-71.3,
                    snr_dbm=2.7,
                    capacity=0,
                    tx_power=16.0,
                ),
            ),
            (
                200,
                LinkBudgetMeasurements(
                    mcs_level=0,
                    rsl_dbm=-73.1,
                    snr_dbm=0.9,
                    capacity=0,
                    tx_power=16.0,
                ),
            ),
        ]
        for dist_m, expected_link_budget in test_data:
            link_budget = fspl_based_estimation(
                dist_m,
                self.sector_params.maximum_tx_power,
                self.sector_params,
                self.sector_params,
                DEFAULT_MCS_SNR_MBPS_MAP,
                0,
                0,
                0,
                0,
                None,
                None,
            )
            self.assertEqual(
                link_budget.mcs_level, expected_link_budget.mcs_level
            )
            self.assertAlmostEqual(
                link_budget.rsl_dbm, expected_link_budget.rsl_dbm, places=1
            )
            self.assertAlmostEqual(
                link_budget.snr_dbm, expected_link_budget.snr_dbm, places=1
            )
            self.assertEqual(
                link_budget.capacity, expected_link_budget.capacity
            )
            self.assertAlmostEqual(
                link_budget.tx_power, expected_link_budget.tx_power, places=1
            )


class TestAntennaPattern(unittest.TestCase):
    def test_gain_with_antenna_pattern(self) -> None:
        pattern_data = read_antenna_pattern_data(
            DATA_PATH + "test_antenna_pattern.txt"
        )

        boresight_gain = 10.0
        diversity_gain = 0.0
        # Gain from the antenna pattern file
        gain = extract_gain_from_radio_pattern(
            boresight_gain, diversity_gain, pattern_data, 0, 0
        )
        self.assertAlmostEqual(gain, 10.0, 6)
        # Negative azimuth is converted to [0, 360)
        gain = extract_gain_from_radio_pattern(
            boresight_gain, diversity_gain, pattern_data, -80, -10
        )
        self.assertAlmostEqual(
            gain, 10.0 - 431.934641341173 - 232.689371582438, 6
        )
        gain = extract_gain_from_radio_pattern(
            boresight_gain, diversity_gain, pattern_data, 75, 5
        )
        self.assertAlmostEqual(
            gain, 10.0 - 255.646229749276 - 31.9743585270337, 6
        )

        # az_deviation and el_deviation round to the closest available value
        gain = extract_gain_from_radio_pattern(
            boresight_gain, diversity_gain, pattern_data, 75.26, 5.45
        )
        self.assertAlmostEqual(
            gain, 10.0 - 255.646229749276 - 31.9743585270337, 6
        )
        # Verify small negative value gets rounded to 0 not 360
        gain = extract_gain_from_radio_pattern(
            boresight_gain, diversity_gain, pattern_data, -0.02, 0
        )
        self.assertAlmostEqual(gain, 10.0, 6)


class TestScanPattern(unittest.TestCase):
    def test_gain_with_scan_pattern(self) -> None:
        pattern_data = read_scan_pattern_data(
            DATA_PATH + "test_scan_pattern.csv"
        )
        # test the maximum value in the pattern file
        max_gain = get_max_boresight_gain_from_pattern_file(pattern_data)
        self.assertEqual(max_gain, 30)

        boresight_gain = 10.0
        diversity_gain = 0.0
        # boresight gain from the scan pattern file
        gain = extract_gain_from_radio_pattern(
            boresight_gain, diversity_gain, pattern_data, 0, 0
        )
        self.assertAlmostEqual(gain, 8.0, 1)
        gain = extract_gain_from_radio_pattern(
            boresight_gain, diversity_gain, pattern_data, -80, -10
        )
        self.assertAlmostEqual(gain, 7.2, 1)
        gain = extract_gain_from_radio_pattern(
            boresight_gain, diversity_gain, pattern_data, 75, 5
        )
        self.assertAlmostEqual(gain, 8.4, 1)

        # az_deviation and el_deviation round to the closest available value
        gain = extract_gain_from_radio_pattern(
            boresight_gain, diversity_gain, pattern_data, 75.26, 5.45
        )
        self.assertAlmostEqual(gain, 8.4, 1)
        # az_deviation is out of range, round to the closest available value
        gain = extract_gain_from_radio_pattern(
            boresight_gain, diversity_gain, pattern_data, 95, 0
        )
        self.assertAlmostEqual(gain, 8.7, 1)
        # el_deviation is out of range, round to the closest available value
        gain = extract_gain_from_radio_pattern(
            boresight_gain, diversity_gain, pattern_data, 0, 30
        )
        self.assertAlmostEqual(gain, 2.7, 1)


class TestOxygenAbsorptionLoss(unittest.TestCase):
    def test_oxygen_absorption_loss(self) -> None:
        test_data = [
            (60000, 1.0, 15.0),
            (60000, 0.5, 7.5),
            (60500, 1.0, 14.8),
            (63200, 1.0, 9.76),
            (51000, 1.0, 0),
            (68000, 1.0, 0),
            (54250, 0.25, 0.6625),
        ]

        for frequency_mhz, dist_km, expected_loss in test_data:
            loss = compute_oxygen_loss(dist_km, frequency_mhz)
            self.assertAlmostEqual(loss, expected_loss, places=6)
