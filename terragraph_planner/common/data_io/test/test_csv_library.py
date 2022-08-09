# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import os
import unittest

import pandas as pd

from terragraph_planner.common.configuration.configs import SectorParams
from terragraph_planner.common.constants import DEFAULT_MCS_SNR_MBPS_MAP
from terragraph_planner.common.data_io.csv_library import (
    cleaned_str_input,
    load_csv_and_validate,
    load_topology_link_csv,
    read_antenna_pattern_data,
    read_mcs_snr_mbps_map_data,
    read_scan_pattern_data,
)
from terragraph_planner.common.data_io.data_key import SiteKey
from terragraph_planner.common.exceptions import DataException

DATA_PATH = "terragraph_planner/common/data_io/test/test_data/"


class TestCSVLibrary(unittest.TestCase):
    def helper(self, csv_file_path: str, is_user_input: bool) -> pd.DataFrame:
        return load_csv_and_validate(
            csv_file_path,
            SiteKey.input_keys(),
            SiteKey.required_keys_for_user_input()
            if is_user_input
            else SiteKey.required_keys_for_topology(),
        )

    def test_load_user_input_with_height(self) -> None:
        user_input = self.helper(DATA_PATH + "test_sites_with_height.csv", True)
        self.assertEqual(len(user_input), 8)
        self.assertTrue(SiteKey.ALTITUDE not in user_input.columns)
        self.assertTrue(SiteKey.NAME not in user_input.columns)
        for _, site in user_input.iterrows():
            self.assertIsNotNone(site[SiteKey.HEIGHT])
            self.assertIsNotNone(site[SiteKey.LATITUDE])
            self.assertIsNotNone(site[SiteKey.LONGITUDE])
            self.assertTrue(isinstance(site[SiteKey.HEIGHT], float))
            self.assertTrue(isinstance(site[SiteKey.LATITUDE], float))
            self.assertTrue(isinstance(site[SiteKey.LONGITUDE], float))

    def test_load_user_input_with_altitude(self) -> None:
        user_input = self.helper(DATA_PATH + "test_sites_with_alt.csv", True)
        self.assertEqual(len(user_input), 3)
        self.assertTrue(SiteKey.HEIGHT not in user_input.columns)
        for _, site in user_input.iterrows():
            self.assertIsNotNone(site[SiteKey.ALTITUDE])
            self.assertIsNotNone(site[SiteKey.LATITUDE])
            self.assertIsNotNone(site[SiteKey.LONGITUDE])
            self.assertTrue(isinstance(site[SiteKey.LATITUDE], float))

    def test_load_user_input_with_name(self) -> None:
        user_input = self.helper(DATA_PATH + "test_sites_with_name.csv", True)
        self.assertEqual(len(user_input), 3)
        for _, site in user_input.iterrows():
            self.assertIsNotNone(site[SiteKey.ALTITUDE])
            self.assertIsNotNone(site[SiteKey.LATITUDE])
            self.assertIsNotNone(site[SiteKey.LONGITUDE])
            self.assertIsNotNone(site[SiteKey.NAME])
            self.assertTrue(isinstance(site[SiteKey.NAME], str))

    def test_read_directed_links(self) -> None:
        links_data = load_topology_link_csv(
            DATA_PATH + "test_directed_links.csv"
        )
        expected_links = [
            ("POP", "DN1"),
            ("DN1", "DN2"),
            ("DN1", "CN1"),
            ("DN2", "DN1"),
            ("DN2", "CN1"),
            ("DN2", "CN2"),
        ]
        self.assertEqual(len(links_data), len(expected_links))
        for i in range(len(expected_links)):
            self.assertEqual(links_data[i], expected_links[i])

    def test_read_bidirectional_links(self) -> None:
        links_data = load_topology_link_csv(
            DATA_PATH + "test_bidirectional_links.csv"
        )
        expected_links = [
            ("POP", "DN1"),
            ("DN1", "POP"),
            ("DN1", "DN2"),
            ("DN2", "DN1"),
            ("DN1", "CN1"),
            ("CN1", "DN1"),
            ("DN2", "CN1"),
            ("CN1", "DN2"),
            ("DN2", "CN2"),
            ("CN2", "DN2"),
        ]
        self.assertEqual(len(links_data), len(expected_links))
        for i in range(len(expected_links)):
            self.assertEqual(links_data[i], expected_links[i])

    def test_read_duplicated_cols(self) -> None:
        full_path = os.path.join(
            DATA_PATH + "test_links_reader_duplicated_cols.csv"
        )
        with self.assertRaises(DataException):
            load_topology_link_csv(full_path)

    def test_read_missing_cols(self) -> None:
        with self.assertRaises(DataException):
            load_topology_link_csv(
                DATA_PATH + "test_links_reader_missing_cols.csv"
            )

    def test_read_links_with_site_pair_col(self) -> None:
        links_data = load_topology_link_csv(
            DATA_PATH + "test_links_with_site_pair_col.csv"
        )
        expected_links = [
            ("POP", "DN1"),
            ("POP", "DN2"),
            ("DN1", "CN1"),
            ("DN1", "CN2"),
            ("DN2", "CN2"),
            ("DN2", "CN3"),
        ]
        self.assertEqual(len(links_data), len(expected_links))
        for i in range(len(expected_links)):
            self.assertEqual(links_data[i], expected_links[i])

    def test_csv_with_duplicated_links(self) -> None:
        with self.assertRaisesRegex(
            DataException, "Duplicated links in csv file."
        ):
            load_topology_link_csv(
                DATA_PATH + "test_csv_with_duplicated_links.csv"
            )

    def test_extract_user_input_csv_with_latlon_strings(self) -> None:
        user_input = self.helper(
            DATA_PATH + "test_csv_with_latlon_strings.csv", True
        )
        self.assertEqual(len(user_input), 3)
        latitude = [5.4169, 37.7749, -33.8688]
        longitude = [160.3339, -122.4194, 171.2093]
        for i in range(3):
            self.assertEqual(
                (
                    round(user_input.loc[i, SiteKey.LATITUDE], 4),
                    round(user_input.loc[i, SiteKey.LONGITUDE], 4),
                ),
                (latitude[i], longitude[i]),
            )

    def test_load_csv_and_validate(self) -> None:
        # test_load_csv_and_validate.csv has 4 column [lat, lon, name, height] and 1 row
        df1 = load_csv_and_validate(
            DATA_PATH + "test_load_csv_and_validate.csv",
            [SiteKey.LATITUDE, SiteKey.LONGITUDE, SiteKey.NAME],
            [[SiteKey.NAME]],
        )
        self.assertEqual(len(df1), 1)
        # All 3 keys in the input key list are found in the csv
        self.assertEqual(len(df1.columns), 3)

        # test_load_csv_and_validate_unicode.csv has 4 column [lat, lon, name, height] and 1 row
        # name column should be encoded as utf-8
        df_unicode = load_csv_and_validate(
            DATA_PATH + "test_load_csv_and_validate_unicode.csv",
            [SiteKey.LATITUDE, SiteKey.LONGITUDE, SiteKey.NAME],
            [[SiteKey.NAME]],
        )
        self.assertEqual(len(df_unicode), 1)
        # All 3 keys in the input key list are found in the csv
        self.assertEqual(df_unicode.at[0, SiteKey.NAME], "123 Nákupní")
        self.assertEqual(len(df_unicode.columns), 3)

        df2 = load_csv_and_validate(
            DATA_PATH + "test_load_csv_and_validate.csv",
            [SiteKey.LATITUDE, SiteKey.LONGITUDE, SiteKey.ALTITUDE],
            [[SiteKey.LATITUDE]],
        )
        self.assertEqual(len(df2), 1)
        # Only 2 keys in the input key list are found in the csv. Altitude is not in the csv.
        self.assertEqual(len(df2.columns), 2)
        # Raise error because the required key Altitude is not in the csv
        with self.assertRaisesRegex(DataException, "Some columns are missing."):
            load_csv_and_validate(
                DATA_PATH + "test_load_csv_and_validate.csv",
                [
                    SiteKey.LATITUDE,
                    SiteKey.LONGITUDE,
                    SiteKey.ALTITUDE,
                    SiteKey.NAME,
                ],
                [[SiteKey.ALTITUDE]],
            )
        # Don't raise error because the second required key set is found in the csv
        df3 = load_csv_and_validate(
            DATA_PATH + "test_load_csv_and_validate.csv",
            [
                SiteKey.LATITUDE,
                SiteKey.LONGITUDE,
                SiteKey.ALTITUDE,
                SiteKey.NAME,
            ],
            [[SiteKey.ALTITUDE], [SiteKey.NAME, SiteKey.LONGITUDE]],
        )
        self.assertEqual(len(df3), 1)
        self.assertEqual(len(df3.columns), 3)
        # An additional device_sku column should be added if it's a site file with column type
        df4 = load_csv_and_validate(
            DATA_PATH + "test_load_csv_and_validate.csv",
            [
                SiteKey.LATITUDE,
                SiteKey.LONGITUDE,
                SiteKey.NAME,
                SiteKey.SITE_TYPE,
            ],
            [[SiteKey.NAME]],
        )
        self.assertEqual(len(df4), 1)
        # 4 keys in the input key list
        self.assertEqual(len(df4.columns), 4)

        df5 = load_csv_and_validate(
            DATA_PATH + "test_load_csv_and_validate.csv",
            [
                SiteKey.LATITUDE,
                SiteKey.LONGITUDE,
                SiteKey.NAME,
                SiteKey.SITE_TYPE,
                SiteKey.DEVICE_SKU,
            ],
            [[SiteKey.NAME]],
        )
        self.assertEqual(len(df5), 1)
        # All 5 keys in the input key list are found in the csv
        self.assertEqual(len(df5.columns), 5)

    def test_parse_correct_type_from_site(self) -> None:
        site_df = self.helper(
            DATA_PATH + "test_parse_correct_type_from_site.csv", False
        )
        for _, row in site_df.iterrows():
            self.assertTrue(type(row[SiteKey.NAME]) is str)
            self.assertTrue(type(row[SiteKey.LONGITUDE]) is float)
            self.assertTrue(type(row[SiteKey.LATITUDE]) is float)
            self.assertTrue(type(row[SiteKey.ALTITUDE]) is float)
            self.assertTrue(type(row[SiteKey.DEVICE_SKU]) is str)
        link_list = load_topology_link_csv(
            DATA_PATH + "test_parse_correct_type_from_link.csv"
        )
        for tx_site, rx_site in link_list:
            self.assertTrue(type(tx_site) is str)
            self.assertTrue(type(rx_site) is str)

    def test_load_user_site_csv_with_sku(self) -> None:
        user_input = self.helper(
            DATA_PATH + "test_load_user_site_csv_with_sku.csv", True
        )
        self.assertEqual(len(user_input), 4)
        self.assertEqual(user_input.loc[0, SiteKey.DEVICE_SKU], "dn_device")
        self.assertEqual(user_input.loc[1, SiteKey.DEVICE_SKU], "dn_device")
        self.assertEqual(user_input.loc[2, SiteKey.DEVICE_SKU], "")
        self.assertEqual(user_input.loc[3, SiteKey.DEVICE_SKU], "cn_device")

    def test_load_user_input_with_demand(self) -> None:
        user_input = self.helper(DATA_PATH + "test_sites_with_demand.csv", True)
        self.assertEqual(len(user_input), 3)
        self.assertEqual(user_input.loc[0, SiteKey.NUMBER_OF_SUBSCRIBERS], None)
        self.assertEqual(user_input.loc[1, SiteKey.NUMBER_OF_SUBSCRIBERS], None)
        self.assertEqual(user_input.loc[2, SiteKey.NUMBER_OF_SUBSCRIBERS], 2)


class TestPatternFile(unittest.TestCase):
    def test_read_antenna_pattern(self) -> None:
        SAMPLE_ANTENNA_PATTERN_1 = "sample_antenna_pattern_1"
        SAMPLE_ANTENNA_PATTERN_2 = "sample_antenna_pattern_2"
        SAMPLE_ANTENNA_PATTERN_3 = "sample_antenna_pattern_3"
        SAMPLE_ANTENNA_PATTERN_SPACE_DELIM = (
            "sample_antenna_pattern_space_delim"
        )
        pattern_data = read_antenna_pattern_data(
            DATA_PATH + "test_antenna_pattern_multiple.txt"
        )
        self.assertEqual(len(pattern_data), 3)

        for key in pattern_data.keys():
            self.assertEqual(key, cleaned_str_input(key))
            self.assertEqual(len(pattern_data[key][0]), 360)
            self.assertEqual(len(pattern_data[key][1]), 360)

        # Test values of random entries
        self.assertIn(SAMPLE_ANTENNA_PATTERN_1, pattern_data)
        self.assertIn(SAMPLE_ANTENNA_PATTERN_2, pattern_data)
        self.assertIn(SAMPLE_ANTENNA_PATTERN_3, pattern_data)
        self.assertAlmostEqual(
            pattern_data[SAMPLE_ANTENNA_PATTERN_1][0][88], -393.94, 2
        )
        self.assertAlmostEqual(
            pattern_data[SAMPLE_ANTENNA_PATTERN_1][1][342], -253.01, 2
        )
        self.assertAlmostEqual(
            pattern_data[SAMPLE_ANTENNA_PATTERN_2][0][83], -289.25, 2
        )
        self.assertAlmostEqual(
            pattern_data[SAMPLE_ANTENNA_PATTERN_2][1][23], -237.52, 2
        )
        self.assertAlmostEqual(
            pattern_data[SAMPLE_ANTENNA_PATTERN_3][0][78], -249.14, 2
        )
        self.assertAlmostEqual(
            pattern_data[SAMPLE_ANTENNA_PATTERN_3][1][50], -283.39, 2
        )

        # Test assert with unexpected format
        with self.assertRaises(Exception):
            read_antenna_pattern_data(
                DATA_PATH + "test_antenna_pattern_wrong_format.txt"
            )
        with self.assertRaises(DataException):
            read_antenna_pattern_data(
                DATA_PATH + "test_antenna_pattern_missing_angle.txt"
            )

        # Test with a space-delimited file
        pattern_data = read_antenna_pattern_data(
            DATA_PATH + "test_antenna_pattern_space_delim.txt"
        )
        self.assertEqual(len(pattern_data), 1)
        for key in pattern_data.keys():
            self.assertEqual(key, cleaned_str_input(key))
            self.assertEqual(len(pattern_data[key][0]), 360)
            self.assertEqual(len(pattern_data[key][1]), 360)
        self.assertIn(SAMPLE_ANTENNA_PATTERN_SPACE_DELIM, pattern_data)
        self.assertAlmostEqual(
            pattern_data[SAMPLE_ANTENNA_PATTERN_SPACE_DELIM][0][88], -393.94, 2
        )
        self.assertAlmostEqual(
            pattern_data[SAMPLE_ANTENNA_PATTERN_SPACE_DELIM][1][342], -253.01, 2
        )

    def test_read_scan_pattern(self) -> None:
        pattern_data = read_scan_pattern_data(
            DATA_PATH + "test_scan_pattern.csv"
        )
        self.assertEqual(len(pattern_data), 661)
        self.assertEqual(len(pattern_data[0]), 121)
        self.assertAlmostEqual(pattern_data[0][0], 28.04, 2)
        self.assertAlmostEqual(pattern_data[27][-12], 28.14, 2)
        self.assertAlmostEqual(pattern_data[-82][7], 28.05, 2)


class TestMCSMap(unittest.TestCase):
    def test_good_input(self) -> None:
        """
        A csv file as expected
        """
        mcs_snr_mbps_map = read_mcs_snr_mbps_map_data(
            DATA_PATH + "test_mcs_good_input.csv", SectorParams()
        )
        self.assertEqual(mcs_snr_mbps_map, DEFAULT_MCS_SNR_MBPS_MAP)

    def test_good_complex_header(self) -> None:
        """
        A csv file as expected -- with more complex column names such as
        "mcs_radio1"
        """
        mcs_snr_mbps_map = read_mcs_snr_mbps_map_data(
            DATA_PATH + "test_mcs_good_complex_header.csv", SectorParams()
        )
        self.assertEqual(mcs_snr_mbps_map, DEFAULT_MCS_SNR_MBPS_MAP)

    def test_shuffled_header(self) -> None:
        """
        A csv file with column order is different
        """
        mcs_snr_mbps_map = read_mcs_snr_mbps_map_data(
            DATA_PATH + "test_mcs_good_shuffled_columns.csv", SectorParams()
        )
        self.assertEqual(mcs_snr_mbps_map, DEFAULT_MCS_SNR_MBPS_MAP)

    def test_bad_entry(self) -> None:
        """
        A csv file with a string entry
        """
        with self.assertRaises(DataException):
            read_mcs_snr_mbps_map_data(
                DATA_PATH + "test_mcs_bad_entry.csv", SectorParams()
            )

    def test_bad_header(self) -> None:
        """
        A csv file with the keyword "mcs" appearing multiple times
        """
        with self.assertRaises(DataException):
            read_mcs_snr_mbps_map_data(
                DATA_PATH + "test_mcs_bad_header.csv", SectorParams()
            )

    def test_bad_header2(self) -> None:
        """
        A csv file with header "mcs_snr_mbps"
        """
        with self.assertRaises(DataException):
            read_mcs_snr_mbps_map_data(
                DATA_PATH + "test_mcs_bad_header2.csv", SectorParams()
            )

    def test_long_row(self) -> None:
        """
        A csv file with a row that has more than three entries
        """
        with self.assertRaises(DataException):
            read_mcs_snr_mbps_map_data(
                DATA_PATH + "test_mcs_bad_long_row.csv", SectorParams()
            )

    def test_no_header(self) -> None:
        """
        A csv file without column names
        """
        with self.assertRaises(DataException):
            read_mcs_snr_mbps_map_data(
                DATA_PATH + "test_mcs_bad_no_header.csv", SectorParams()
            )

    def test_extract_missing_col(self) -> None:
        """
        A csv file missing a column other then tx backoff
        """
        with self.assertRaises(DataException):
            read_mcs_snr_mbps_map_data(
                DATA_PATH + "test_mcs_bad_missing_col.csv", SectorParams()
            )

    def test_min_mcs(self) -> None:
        """
        Test user input Min MCS
        """
        min_mcs = 5
        sector_params = SectorParams(minimum_mcs_level=min_mcs)
        mcs_snr_mbps_map = read_mcs_snr_mbps_map_data(
            DATA_PATH + "test_mcs_good_input.csv", sector_params
        )
        map = [row for row in DEFAULT_MCS_SNR_MBPS_MAP if row.mcs >= min_mcs]
        self.assertEqual(len(mcs_snr_mbps_map), 8)
        self.assertEqual(mcs_snr_mbps_map, map)
