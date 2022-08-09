# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


from typing import Dict, List, Optional, Union

from osgeo.osr import SpatialReference
from pyre_extensions import assert_is_instance


class MockSpatialReference(SpatialReference):
    def __init__(
        self,
        attr_dict: Optional[Dict[str, List[str]]] = None,
        linear_units: float = 1.0,
        linear_units_name: str = "",
    ) -> None:
        self.attr_dict: Dict[str, List[str]] = (
            attr_dict if attr_dict is not None else {}
        )
        self.linear_units = linear_units
        self.linear_units_name = linear_units_name

    def GetAttrValue(self, *args: Union[str, int]) -> Optional[str]:
        value = None
        if len(args) > 0:
            key = assert_is_instance(args[0], str)
            if key in self.attr_dict:
                values = self.attr_dict[key]
                if len(args) > 1:
                    idx = assert_is_instance(args[1], int)
                else:
                    idx = 0
                if idx < len(values):
                    value = values[idx]
        if isinstance(value, str):
            value = value.casefold()
        return value

    def GetLinearUnits(self) -> float:  # pyre-ignore
        return self.linear_units

    def GetLinearUnitsName(self) -> str:  # pyre-ignore
        return self.linear_units_name.lower()
