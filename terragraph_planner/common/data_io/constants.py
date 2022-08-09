# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# The default radius used to search for a valid elevation when the
# elevation data is missing somewhere (meters).
DEFAULT_ELEVATION_SEARCH_RADIUS = 50

# No data value for gdal
NO_DATA_VALUE = -32768
DEFAULT_RESOLUTION = 1

# Minimal resolution used to output the elevation data (meters).
MIN_RES_TO_OUTPUT_AS_LIST = 0.5

# Minimum link length that will be considered as a link (meters).
MIN_LINK_LENGTH = 5

# Maximum distance allowed for a link's end-point to the closest
# placemark (meters).
SITE_LINK_DIST_THRESHOLD = 10
