# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
from pathlib import Path

# Default radio frequency, in MHz
DEFAULT_CARRIER_FREQUENCY = 6e4
# Default LOS confidence threshold used to detemine LOS
DEFAULT_LOS_CONFIDENCE_THRESHOLD = 0.8

# The path of the installed package
PACKAGE_PATH: str = str(Path(__file__).parent.parent.parent)

# The path to store the template yaml file
TEMPLATE_YAML_FILE_PATH: str = os.path.join(
    PACKAGE_PATH, "data", "template.yaml"
)

# The following constants are the field names in the config file
DATA: str = "DATA"
LINE_OF_SIGHT: str = "LINE_OF_SIGHT"
NETWORK_DESIGN: str = "NETWORK_DESIGN"
OPTIMIZATION: str = "OPTIMIZATION"
RADIO: str = "RADIO"
SYSTEM: str = "SYSTEM"

# A building id used for the rooftop sites from user input
UNKNOWN_BUILDING_ID = -1
