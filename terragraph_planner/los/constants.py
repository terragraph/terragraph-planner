# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import Tuple

from terragraph_planner.common.configuration.enums import SiteType

# The number of candidate links for each batch of LOS computation
BATCH_SIZE: int = 1000

BI_DIRECTIONAL_LINKS: Tuple[
    Tuple[SiteType, SiteType],
    Tuple[SiteType, SiteType],
    Tuple[SiteType, SiteType],
] = (
    (SiteType.POP, SiteType.DN),
    (SiteType.DN, SiteType.DN),
    (SiteType.DN, SiteType.POP),
)

# BUILDING_HEIGHT_THRESHOLD (in metres) is mainly used to:
# 1. Shape files and surface data may not perfectly align, and it cause a corner
#    detected from shape files is on the street level in the surface data. To find
#    a good altitude for the corner, we need to find a neighbor that is over
#    BUILDING_HEIGHT_THRESHOLD higher than its neighbor (it's the neighbor of corner's
#    neighbor) and use its altitude as the corner altitude
# 2. When surface data and terrain data are both provided, we can use that value to
#    check whether the input site is on the building or not.
BUILDING_HEIGHT_THRESHOLD = 2

DIRECTED_LINKS: Tuple[Tuple[SiteType, SiteType], Tuple[SiteType, SiteType]] = (
    (SiteType.POP, SiteType.CN),
    (SiteType.DN, SiteType.CN),
)

# LOS is computed in utm coordinates; distance computation has small error
# compared with haversine distance. Due to this, for LOS computations, increase
# the valid distance range slightly and then filter out invalid links using
# distance computed with haversine later.
DISTANCE_TOLERANCE_PERCENT = 0.02

# Due to the distance tolerance,additional tolerance for the elevation angle
# limit
ELE_SCAN_ANGLE_TOLERANCE = 2

# When getting altitude of corners, we need a square bound with the corner as its center
# to search its neighbors and find a neighbor that is much higher than the neighbor's
# neighbor. HALF_SIDE_LENGTH_FOR_ALTITUDE_SEARCH (in metres) is the half of the side length
# of this bound.
HALF_SIDE_LENGTH_FOR_ALTITUDE_SEARCH = 1

# Buildings that are less than this area will be filtered（in m^2）
MINIMUM_BUILDING_AREA = 50

# The minimal angle that a vertex of the building outline is considered
# as a building corner
MIN_CORNER_ANGLE = 30

POLYGON_MINIMUM_VERTICES = 3
