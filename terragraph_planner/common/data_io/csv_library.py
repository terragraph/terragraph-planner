# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import csv
import re
from itertools import combinations
from typing import TYPE_CHECKING, List, Optional, Tuple

import pandas as pd
from pyre_extensions import none_throws

from terragraph_planner.common.configuration.enums import (
    LocationType,
    SiteType,
    StatusType,
)
from terragraph_planner.common.data_io.data_key import (
    NUMERIC_KEYS,
    DataKey,
    LinkKey,
    SiteKey,
)
from terragraph_planner.common.exceptions import DataException, planner_assert
from terragraph_planner.common.structs import (
    AntennaPatternData,
    MCSMap,
    RawSite,
    ScanPatternData,
)

if TYPE_CHECKING:
    from terragraph_planner.common.configuration.configs import SectorParams


def dms_to_decimal(dms: str) -> float:
    """
    Convert string in dms (or decimal with just direction) to decimal.
    E.g., 100°20'2.04"E or 122.4194° W
    """
    try:
        dms_split = re.split("[\\s°'\"]+", dms.strip())
        slen = len(dms_split)
        direction = dms_split[slen - 1]
        planner_assert(
            (slen == 2 or slen == 4) and direction in ["N", "E", "S", "W"],
            f"Provided input contains a malformed lat/long value: {dms}.",
            DataException,
        )
        dec = float(dms_split[0])
        if slen == 4:  # in dms format
            dec += float(dms_split[1]) / 60 + float(dms_split[2]) / 3600
        scale = 1 if direction in ["N", "E"] else -1
        return dec * scale
    except ValueError:
        planner_assert(
            False,
            f"Provided input contains a malformed lat/long value: {dms}.",
            DataException,
        )
        return 0


def load_csv_and_validate(
    csv_file_path: str,
    input_key_list: List[DataKey],
    required_key_lists: List[List[DataKey]],
) -> pd.DataFrame:
    """
    Load data from csv file and validate it with expected_cols and required_key_sets.

    @param csv_file_path
    A str representing the ABSOLUTE file path of the csv file.
    @param input_key_list
    A list of DataKey. These keys may exist in the csv file, but are not required.
    @param required_key_lists
    A list of DataKey lists, of which each list represents a set of required keys. The CSV file should
    satisfy at least one of the required key sets.

    @return pd.DataFrame
    A dataframe loaded from the input csv file after validation.
    """
    df = pd.DataFrame()
    # Read file
    try:
        df = pd.read_csv(
            csv_file_path, header=0, keep_default_na=False, encoding="utf-8-sig"
        )
    except Exception:
        planner_assert(
            False,
            f"Could not read from {csv_file_path}.",
            DataException,
        )

    # Standardize column to make it easy to process in the following validation
    for col_name in df.columns:
        df.rename(columns={col_name: col_name.strip().casefold()}, inplace=True)
    duplicated_cols = []
    nb_matched_cols = {}
    for input_key in input_key_list:
        matched_cols = input_key.value.possible_input_names.intersection(
            set(df.columns)
        )
        # Rename the column name as the input key
        for col in matched_cols:
            if input_key not in NUMERIC_KEYS:
                df[col] = df[col].apply(str)
            df.rename(columns={col: input_key}, inplace=True)
        nb_matched_cols[input_key] = len(matched_cols)
        if nb_matched_cols[input_key] > 1:
            duplicated_cols.append(input_key.value.output_name)
    for col in df.columns:
        if not isinstance(col, (SiteKey, LinkKey)):
            df.drop(col, axis=1, inplace=True)
    planner_assert(
        len(duplicated_cols) == 0,
        f"There are multiple columns representing {','.join(duplicated_cols)}.",
        DataException,
    )

    # Check if it satisfies either list in the required_key_lists
    for key_list in required_key_lists:
        for key in key_list:
            if key not in nb_matched_cols or nb_matched_cols[key] == 0:
                break
        else:
            break
    else:
        planner_assert(
            False,
            "Some columns are missing.",
            DataException,
        )

    # Validation and preprocessing on some columns
    for idx, row in df.iterrows():
        if SiteKey.LATITUDE in row and isinstance(row[SiteKey.LATITUDE], str):
            df.loc[idx, SiteKey.LATITUDE] = dms_to_decimal(
                row[SiteKey.LATITUDE]
            )
        if SiteKey.LONGITUDE in row and isinstance(row[SiteKey.LONGITUDE], str):
            df.loc[idx, SiteKey.LONGITUDE] = dms_to_decimal(
                row[SiteKey.LONGITUDE]
            )
        if SiteKey.NUMBER_OF_SUBSCRIBERS in row:
            if df.loc[idx, SiteKey.NUMBER_OF_SUBSCRIBERS] == "":
                df.loc[idx, SiteKey.NUMBER_OF_SUBSCRIBERS] = None
            elif isinstance(row[SiteKey.NUMBER_OF_SUBSCRIBERS], str):
                df.loc[idx, SiteKey.NUMBER_OF_SUBSCRIBERS] = int(
                    row[SiteKey.NUMBER_OF_SUBSCRIBERS]
                )
        for input_key in input_key_list:
            if input_key in row and input_key not in NUMERIC_KEYS:
                df.loc[idx, input_key] = row[input_key].strip()
    return df


def load_input_sites_from_csv_file(
    csv_file_path: str, is_user_input: bool
) -> List[RawSite]:
    """
    Load site data from CSV file.

    @param csv_source
    Optional. Return a InputSites object with empty site list.

    @param is_user_input
    bool indicating if it's for user input for topology site list. It will only affect the
    required keys. e.g. site name is not required for user input, but required for topology sites.
    """
    site_df = load_csv_and_validate(
        csv_file_path,
        SiteKey.input_keys(),
        SiteKey.required_keys_for_user_input()
        if is_user_input
        else SiteKey.required_keys_for_topology(),
    )
    raw_sites: List[RawSite] = []
    for _, site_row in site_df.iterrows():
        # Use POP as the default site type. The default only works for user input file
        # because type column is required in topology site file
        site_type_str = site_row.get(
            SiteKey.SITE_TYPE, SiteType.POP.to_string()
        )
        try:
            site_type = SiteType[site_type_str.upper().split(" ")[0]]
        except KeyError:
            raise DataException(
                f"Invalid site type {site_type_str} in site csv file."
            )
        latitude = site_row[SiteKey.LATITUDE]
        longitude = site_row[SiteKey.LONGITUDE]
        if latitude is None or longitude is None:
            continue
        site = RawSite(
            site_type=site_type,
            status_type=StatusType.CANDIDATE,
            device_sku=site_row.get(SiteKey.DEVICE_SKU, None),
            name=site_row.get(SiteKey.NAME, None),
            latitude=latitude,
            longitude=longitude,
            altitude=site_row.get(SiteKey.ALTITUDE, None),
            height=site_row.get(SiteKey.HEIGHT, None),
            location_type=LocationType.UNKNOWN,
            building_id=site_row.get(SiteKey.BUILDING_ID, None),
            number_of_subscribers=site_row.get(
                SiteKey.NUMBER_OF_SUBSCRIBERS, None
            ),
        )
        raw_sites.append(site)
    return raw_sites


def load_topology_link_csv(csv_file_path: str) -> List[Tuple[str, str]]:
    """
    Load topology (Candidate graph) link csv file, return as a list of site name pair.
    """

    def _add_link(tx_site_name: str, rx_site_name: str) -> None:
        tx_site_name = tx_site_name.strip()
        rx_site_name = rx_site_name.strip()
        link = (tx_site_name, rx_site_name)
        if link not in link_set:
            link_set.add(link)
            link_list.append(link)
        else:
            planner_assert(
                False,
                "Duplicated links in csv file.",
                DataException,
            )

    link_df = load_csv_and_validate(
        csv_file_path,
        LinkKey.input_keys(),
        LinkKey.required_keys(),
    )
    link_list = []
    link_set = set()
    if LinkKey.SITE_PAIR in link_df.columns:
        for _, link in link_df.iterrows():
            site_names = link[LinkKey.SITE_PAIR].split("-->")
            planner_assert(
                len(site_names) == 2,
                "Please use the format of '<tx_site> --> <rx_site>' in sites/site_pair column",
                DataException,
            )
            _add_link(site_names[0], site_names[1])
    elif (
        LinkKey.SITE1_NAME in link_df.columns
        and LinkKey.SITE2_NAME in link_df.columns
    ):
        for _, link in link_df.iterrows():
            _add_link(link[LinkKey.SITE1_NAME], link[LinkKey.SITE2_NAME])
            _add_link(link[LinkKey.SITE2_NAME], link[LinkKey.SITE1_NAME])
    else:
        for _, link in link_df.iterrows():
            _add_link(link[LinkKey.TX_SITE_NAME], link[LinkKey.RX_SITE_NAME])
    return link_list


def cleaned_str_input(name: Optional[str]) -> str:
    if name is None:
        return ""
    return name.casefold().strip()  # nice and clean


def read_antenna_pattern_data(
    pattern_file_path: str,
) -> AntennaPatternData:
    """
    Read an antenna pattern (or multiple) in .pln format.

    This supports a .pln file containing multiple antenna patterns. The patterns
    will be identified by their "NAME" row.

    Returns is a dict of the antenna patterns, storing lists of azimuth and
    elevation gains in 1 degree increments.
    """
    pattern_data = {}
    try:
        data = pd.read_csv(
            pattern_file_path,
            header=None,
            sep=None,
            skipinitialspace=True,
            engine="python",
        )
        # strip leading/trailing space, convert to upper case
        data = data.applymap(
            lambda x: x.strip().upper() if isinstance(x, str) else x
        )
        # change empty strings to NA
        data = data.replace("", pd.NA)
        # drop columns and rows filled with NA values
        data = data.dropna(axis=1, how="all").dropna(axis=0, how="all")
    except Exception:
        planner_assert(
            False,
            "Imported antenna pattern file is not in the typical .pln format!",
            DataException,
        )
    idx = data[data[0] == "NAME"].index
    if len(idx) == 0:
        planner_assert(
            False,
            "Imported antenna pattern file is not in the typical .pln format!",
            DataException,
        )

    az_startlist = data[data[0] == "HORIZONTAL"].index
    el_startlist = data[data[0] == "VERTICAL"].index
    for i in range(len(idx)):
        az_start = az_startlist[i]
        el_start = el_startlist[i]
        try:
            az_pattern = data.iloc[az_start + 1 : az_start + 361].astype(
                "float"
            )
            el_pattern = data.iloc[el_start + 1 : el_start + 361].astype(
                "float"
            )
        except ValueError:
            planner_assert(
                False,
                "Imported antenna pattern file has an unexpected number of loss entries!",
                DataException,
            )
        antenna_pattern = [
            (-1 * az_pattern[1]).values.tolist(),
            (-1 * el_pattern[1]).values.tolist(),
        ]
        pattern_id = cleaned_str_input(str(data.iloc[idx[i]][1]))
        pattern_data[pattern_id] = antenna_pattern
    return pattern_data


def read_scan_pattern_data(
    pattern_file_path: str,
) -> ScanPatternData:
    """
    Read a scan pattern file in csv format.
    """
    pattern_data = {}
    try:
        df = pd.read_csv(pattern_file_path, index_col=0)
    except Exception:
        planner_assert(
            False,
            "Imported scan pattern file is not in the expected .csv format!",
            DataException,
        )
    df_dict = df.to_dict("index")
    pattern_data = {
        float(hor): {float(ver): float(v) for ver, v in row.items()}
        for hor, row in df_dict.items()
    }
    return pattern_data


def read_mcs_snr_mbps_map_data(
    map_file_path: str,
    sector_params: "SectorParams",
) -> List[MCSMap]:
    """
    Read the mapping between MCS, minimum SNR value, Mbps and TX backoff
    from a csv file.
    """
    SNR = "snr"
    MBPS = "mbps"
    MCS = "mcs"
    TX_BACKOFF = "tx_backoff"
    expected_keys = [MCS, SNR, MBPS, TX_BACKOFF]

    # Read MCS mapping from a csv file
    raw_data: List[List[str]] = []
    try:
        with open(map_file_path, mode="r") as csv_file:
            file_reader = csv.reader(csv_file)
            for row in file_reader:
                raw_data.append(row)
    except Exception:
        planner_assert(
            False,
            "Imported MCS mapping file is not in the expected .csv format!",
            DataException,
        )
    planner_assert(
        len(raw_data) > 0,
        "The csv file must contain at least two lines including column names.",
        DataException,
    )

    # Add column TX_BACKOFF if not exist with all values set to 0
    default_tx_backoff = "0"
    column_name_row = [name.casefold().strip() for name in raw_data[0]]
    if TX_BACKOFF not in column_name_row:
        column_name_row.append(TX_BACKOFF)
        raw_data[0].append(TX_BACKOFF)
        for i in range(1, len(raw_data)):
            raw_data[i].append(default_tx_backoff)

    # Check size of each row
    for row in raw_data:
        planner_assert(
            len(row) == len(expected_keys),
            f"Each row must have exactly {len(expected_keys)} entries.",
            DataException,
        )

    # Check the validity of the column names
    # Each key must appear in exactly one column name
    # Find the column that corresponds to each key "mcs", "snr", "mbps" and "tx_backoff"
    key_cols = {}
    for key_name in expected_keys:
        key_cols[key_name] = [
            i
            for i in range(len(column_name_row))
            if key_name in column_name_row[i]
        ]

    if any(
        bool(len(key_cols[key_name]) != 1) for key_name in expected_keys
    ) or any(
        (key_cols[key1] == key_cols[key2])
        for key1, key2 in combinations(expected_keys, 2)
    ):
        planner_assert(
            False,
            f"The column names {', '.join(expected_keys)} must appear exactly once.",
            DataException,
        )

    # Check if values are of the right type
    mapping = {k: [] for k in expected_keys}
    for row in raw_data[1:]:
        for i in range(len(row)):
            key_name = expected_keys[i]
            column_id = key_cols[key_name][0]
            try:
                value = float(row[column_id])
                mapping[key_name].append(value)
            except ValueError:
                planner_assert(
                    False,
                    "All entries except the column names must be numbers.",
                    DataException,
                )

    def _get_ordering(lst: List[float]) -> List[int]:
        """
        The ordering of MCS, SNR, MBPS and TX_BACKOFF must match. For increasing MCS, SNR
        threshold, Mbps and Tx power backoff should be also increasing.
        """
        return [i[0] for i in sorted(enumerate(lst), key=lambda x: x[1])]

    mcs_ordering = _get_ordering(mapping[MCS])
    snr_ordering = _get_ordering(mapping[SNR])
    mbps_ordering = _get_ordering(mapping[MBPS])
    tx_backoff_ordering = _get_ordering(mapping[TX_BACKOFF])
    planner_assert(
        mcs_ordering == snr_ordering
        and mcs_ordering == mbps_ordering
        and mcs_ordering == tx_backoff_ordering,
        "The ordering of all columns must be the same.",
        DataException,
    )

    planner_assert(
        sector_params.minimum_mcs_level is None
        or max(mapping[MCS]) >= sector_params.minimum_mcs_level,
        "The Max MCS level in the mapping table must not smaller than input Min MCS.",
        DataException,
    )

    mcs_snr_mbps_map = [
        MCSMap(
            mcs=int(mapping[MCS][i]),
            snr=mapping[SNR][i],
            mbps=mapping[MBPS][i],
            tx_backoff=mapping[TX_BACKOFF][i],
        )
        for i in range(len(raw_data) - 1)
        if (
            sector_params.minimum_tx_power is None
            or sector_params.maximum_tx_power - mapping[TX_BACKOFF][i]
            >= none_throws(sector_params.minimum_tx_power)
        )
        and (
            sector_params.minimum_mcs_level is None
            or mapping[MCS][i] >= sector_params.minimum_mcs_level
        )
    ]
    return mcs_snr_mbps_map
