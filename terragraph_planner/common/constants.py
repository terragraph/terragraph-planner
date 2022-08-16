# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import Dict

from terragraph_planner.common.structs import MCSMap

DEFAULT_POINTING_PRECISION = (
    3  # precision used in placement of equidistance sectors
)
EARTH_RADIUS: float = 6371000.0  # the radius of the earth, in meters
# The upper bound for elevation deviation for valid los
ELE_SCAN_ANGLE_LIMIT = 25
FSPL_MARGIN = 92.45  # free-space path loss constant
FULL_ROTATION_ANGLE = 360.0
# WGS 84, aka EPSG 4326, latitude/longitude coordinate system based on the Earth's
# center of mass, used by the Global Positioning System among others.
LAT_LON_EPSG: int = 4326
# precision in converting latitude/longitude to geo hash
LAT_LON_TO_GEO_HASH_PRECISION = 10
# The lower bound used in searching for max los distance based on capacity. in meters.
LOWER_BOUND_FOR_LOS_DISTANCE = 0
SECTOR_LINK_ANGLE_TOLERANCE = 1e-2
STRAIGHT_ANGLE = 180.0
# The upper bound used in searching for max los distance based on capacity. in meters.
UPPER_BOUND_FOR_LOS_DISTANCE = 10000

# Frequency dependent oxygen absorption loss (maps frequency in GHz to oxygen
# loss in dB/km). Table 7.6.1-1 on page 44 of
# https://www.etsi.org/deliver/etsi_tr/138900_138999/138901/14.00.00_60/tr_138901v140000p.pdf
FREQUENCY_DEPENDENT_OXYGEN_LOSS_MAP: Dict[float, float] = {
    52.0: 0,
    53.0: 1,
    54.0: 2.2,
    55.0: 4,
    56.0: 6.6,
    57.0: 9.7,
    58.0: 12.6,
    59.0: 14.6,
    60.0: 15,
    61.0: 14.6,
    62.0: 14.3,
    63.0: 10.5,
    64.0: 6.8,
    65.0: 3.9,
    66.0: 1.9,
    67.0: 1,
    68.0: 0,
}

# Default mapping between mcs, snr, down-link throughput (mbps) and
# Tx backoff
DEFAULT_MCS_SNR_MBPS_MAP = [
    MCSMap(mcs=3, snr=3, mbps=0, tx_backoff=0),
    MCSMap(mcs=4, snr=4.5, mbps=67.5, tx_backoff=0),
    MCSMap(mcs=5, snr=5, mbps=115, tx_backoff=0),
    MCSMap(mcs=6, snr=5.5, mbps=260, tx_backoff=0),
    MCSMap(mcs=7, snr=7.5, mbps=452.5, tx_backoff=0),
    MCSMap(mcs=8, snr=9, mbps=645, tx_backoff=0),
    MCSMap(mcs=9, snr=12, mbps=741.25, tx_backoff=0),
    MCSMap(mcs=10, snr=14, mbps=1030, tx_backoff=2),
    MCSMap(mcs=11, snr=16, mbps=1415, tx_backoff=4),
    MCSMap(mcs=12, snr=18, mbps=1800, tx_backoff=6),
]
