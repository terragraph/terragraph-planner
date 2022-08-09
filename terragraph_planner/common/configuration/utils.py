# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import json
import logging
import os
from typing import Any, Dict

import yaml

from terragraph_planner.common.configuration.configs import (
    ConfigParser,
    GISDataParams,
    LOSParams,
    OptimizerParams,
    SystemParams,
)
from terragraph_planner.common.configuration.constants import (
    DATA,
    LINE_OF_SIGHT,
    NETWORK_DESIGN,
    OPTIMIZATION,
    RADIO,
    SYSTEM,
    TEMPLATE_YAML_FILE_PATH,
)
from terragraph_planner.common.exceptions import ConfigException, planner_assert

logger: logging.Logger = logging.getLogger(__name__)


def _detect_typo(data: Dict[str, Any], origin: Dict[str, Any]) -> None:
    """
    Detect if there is a typo of user input. The user inputs are case-insensitive

    @params data: a dict generated from user input.
    @params origin: a dict generated from empty template.
    """
    origin_lower_cases = {k.casefold(): k for k in origin.keys()}
    for k, value in data.items():
        if k.strip().casefold() not in origin_lower_cases:
            raise ConfigException(
                f"{k} is an illegal field with no definition, check if it's a typo."
            )
        key = origin_lower_cases[k.strip().casefold()]
        origin_value = origin[key]
        if isinstance(value, dict):
            _detect_typo(value, origin_value)

        if isinstance(value, list):
            if isinstance(origin_value[0], dict):
                for i in range(len(value)):
                    _detect_typo(value[i], origin_value[0])


def _load_dict_from_file(
    file_path: str,
) -> Dict[str, Any]:
    """
    Construct classes from given json/yaml file.

    @param file_path: json/yaml file path to configs.
    @return: a tuple of all the classes.
    """
    planner_assert(
        os.path.exists(file_path),
        f"file {file_path} is invalid.",
        ConfigException,
    )
    planner_assert(
        (
            file_path.endswith(".json")
            or file_path.endswith(".yml")
            or file_path.endswith(".yaml")
        ),
        "Only JSON or YAML file is supported.",
        ConfigException,
    )
    if file_path.endswith(".json"):
        with open(file_path) as f:
            data = json.load(f)
    else:
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)
    with open(TEMPLATE_YAML_FILE_PATH, "r") as fi:
        origin = yaml.safe_load(fi)
        _detect_typo(data, origin)

    return data


def struct_objects_from_file(obj_name: str, file_path: str) -> ConfigParser:
    data_dict = _load_dict_from_file(file_path)
    try:
        if obj_name == SYSTEM:
            # If system parameters are missing in the config file, the default
            # is used and there's no raised exception.
            system_params = SystemParams.from_dict(data_dict.get(SYSTEM, {}))
            logging.info(
                "Config parameters for system control has been parsed."
            )
            return system_params
        elif obj_name == LINE_OF_SIGHT:
            if RADIO not in data_dict and NETWORK_DESIGN not in data_dict:
                los_params = LOSParams.from_dict(data_dict[LINE_OF_SIGHT])
            else:
                los_params = LOSParams.from_dict(
                    {**data_dict[LINE_OF_SIGHT], **data_dict[RADIO]}
                )
            logger.info("Config parameters for LOS analysis has been parsed.")
            return los_params
        elif obj_name == OPTIMIZATION:
            logger.info("Config parameters for optimization has been parsed.")
            return OptimizerParams.from_dict(
                {**data_dict[RADIO], **data_dict[NETWORK_DESIGN]}
            )
        elif obj_name == DATA:
            logger.info("Config parameters for input data has been parsed")
            return GISDataParams.from_dict(data_dict[DATA])
        else:
            raise ConfigException("Illegal object name")
    except KeyError as err:
        raise ConfigException(
            f"Bad input file. Missing necessary key(s): {err}"
        )
