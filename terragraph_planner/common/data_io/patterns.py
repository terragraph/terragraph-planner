# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from typing import Generic, List, TypeVar

from osgeo.osr import SpatialReference

from terragraph_planner.common.exceptions import DataException


class GISData:
    """
    Base class for raster data and vector data to inherit from.
    """

    def __init__(self, spatial_reference: SpatialReference) -> None:
        self.spatial_reference = spatial_reference

    @property
    def crs_epsg_code(self) -> int:
        self.spatial_reference.AutoIdentifyEPSG()
        return int(self.spatial_reference.GetAuthorityCode(None))


DataType = TypeVar("DataType", bound=GISData)


class DataWorkSpace:
    def __init__(self) -> None:
        self.tmp_dir: str = tempfile.mkdtemp()
        self.file_cnt: int = 0
        self.dir_cnt: int = 0

    def __del__(self) -> None:
        shutil.rmtree(self.tmp_dir)

    def get_a_temp_file_path(self, extension: str) -> str:
        temp_file_path = os.path.join(
            self.tmp_dir, f"temp_file_{self.file_cnt}.{extension}"
        )
        self.file_cnt += 1
        return temp_file_path

    def get_a_temp_dir(self) -> str:
        temp_dir_path = os.path.join(self.tmp_dir, f"temp_dir_{self.dir_cnt}")
        os.mkdir(temp_dir_path)
        self.dir_cnt += 1
        return temp_dir_path


class DataValidator(ABC, Generic[DataType]):
    def __init__(self) -> None:
        self.errors: List[DataException] = []

    @abstractmethod
    def validate(self, gis_data: DataType) -> None:
        raise NotImplementedError
