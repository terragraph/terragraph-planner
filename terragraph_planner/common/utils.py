# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import hashlib
import json
import logging
from typing import Optional, Union

from pyre_extensions import assert_is_instance

from terragraph_planner.common.configuration.configs import SystemParams
from terragraph_planner.common.configuration.constants import SYSTEM
from terragraph_planner.common.configuration.enums import LoggerLevel
from terragraph_planner.common.configuration.utils import (
    struct_objects_from_file,
)

current_system_params = SystemParams()


def deterministic_hash(*args: Union[float, int, str, bool, None]) -> str:
    """
    Helper to generate a predictable hash from a list of args
    """
    return str(
        hashlib.md5(json.dumps(list(args), sort_keys=True).encode()).hexdigest()
    )


def set_root_logger(
    logger_level: LoggerLevel, log_file: Optional[str], to_stderr: bool
) -> None:
    logger = logging.getLogger()
    logger.setLevel(logger_level.value)
    while logger.hasHandlers():
        logger.removeHandler(logger.handlers[0])
    if log_file is not None:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)
    if to_stderr:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(stream_handler)


def set_system_control_with_config_file(config_file_path: str) -> None:
    system_params = assert_is_instance(
        struct_objects_from_file(SYSTEM, config_file_path), SystemParams
    )
    global current_system_params
    current_system_params.output_dir = system_params.output_dir
    current_system_params.debug_mode = system_params.debug_mode
    current_system_params.logger_level = system_params.logger_level
    current_system_params.log_file = system_params.log_file
    current_system_params.log_to_stderr = system_params.log_to_stderr
    set_root_logger(
        system_params.logger_level,
        system_params.log_file,
        system_params.log_to_stderr,
    )
