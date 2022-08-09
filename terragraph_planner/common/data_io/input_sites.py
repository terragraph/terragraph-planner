# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from collections import abc, defaultdict
from typing import Dict, Iterator, List, Optional, Set, Tuple

from terragraph_planner.common.configuration.enums import LocationType, SiteType
from terragraph_planner.common.exceptions import DataException
from terragraph_planner.common.geos import lat_lon_to_utm_epsg
from terragraph_planner.common.topology_models.site import Site


class InputSites(abc.Sized, abc.Iterable):
    def __init__(self) -> None:
        self._site_list: List[Site] = []
        self._site_name_to_device_skus: Dict[str, Set[str]] = defaultdict(set)
        self._site_name_to_site: Dict[str, Site] = {}
        self._site_id_to_site: Dict[str, Site] = {}
        # primary keys are keys to deduplicate
        self._primary_key_set: Set[
            Tuple[
                float, float, Optional[float], SiteType, LocationType, str, str
            ]
        ] = set()

    def __add__(self, other_site_list: "InputSites") -> "InputSites":
        for site in other_site_list:
            self.add_site(site)
        return self

    def __iter__(self) -> Iterator[Site]:
        yield from self._site_list

    def __len__(self) -> int:
        return len(self._site_list)

    def __getitem__(self, idx: int) -> Site:
        return self._site_list[idx]

    @property
    def utm_epsg(self) -> Optional[int]:
        if len(self) == 0:
            return None
        return lat_lon_to_utm_epsg(
            self._site_list[0].latitude, self._site_list[0].longitude
        )

    @property
    def site_list(self) -> List[Site]:
        return self._site_list

    def get_site_by_name(self, site_name: str) -> Optional[Site]:
        return self._site_name_to_site.get(site_name, None)

    def get_site_by_id(self, site_id: str) -> Optional[Site]:
        return self._site_id_to_site.get(site_id, None)

    def add_site(self, site: Site) -> None:
        if self._is_duplicated_site(site):
            return
        self._validate_site_name(site)
        self._site_list.append(site)
        self._site_id_to_site[site.site_id] = site

    def _is_duplicated_site(self, site: Site) -> bool:
        primary_key = (
            site.latitude,
            site.longitude,
            site.altitude,
            site.site_type,
            site.location_type,
            site.name,
            site.device.device_sku.casefold(),
        )
        ret = primary_key in self._primary_key_set
        self._primary_key_set.add(primary_key)
        return ret

    def _validate_site_name(self, site: Site) -> None:
        # Device sku is case insensitive
        lower_device_sku = site.device.device_sku.casefold()
        # Duplicated sites with the same input name and sku, but different location or site type.
        # The sites with same location, type and device sku have already been de-duplicated
        if lower_device_sku in self._site_name_to_device_skus[site.name]:
            raise DataException(
                f"Duplicate site name {site.name} with the same device sku {site.device.device_sku}"
            )
        # There's already exactly one site with the same name but different sku.
        # To distinguish them, append a device sku to the name of the existing site
        if len(self._site_name_to_device_skus[site.name]) == 1:
            self._append_device_sku_to_site_name(
                self._site_name_to_site[site.name]
            )
        self._site_name_to_device_skus[site.name].add(lower_device_sku)
        # There are over 1 sites with the same name but different sku, including the current one.
        # To distinguish them, append a device sku to the name of the current site
        if len(self._site_name_to_device_skus[site.name]) > 1:
            self._append_device_sku_to_site_name(site)
        else:  # That's the first site with this site name. Then no need to append device_sku
            self._site_name_to_site[site.name] = site

    def _append_device_sku_to_site_name(self, site: Site) -> None:
        if site.name in self._site_name_to_site:
            del self._site_name_to_site[site.name]
        site.name = f"{site.name}_{site.device.device_sku.casefold()}"
        self._site_name_to_site[site.name] = site
