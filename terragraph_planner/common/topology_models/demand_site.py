# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import Iterable, List, Optional

from terragraph_planner.common.geos import GeoLocation
from terragraph_planner.common.topology_models.site import Site
from terragraph_planner.common.utils import deterministic_hash


class DemandSite:
    """
    Demand sites are imaginary graph nodes we use for modeling purposes.
    Conceptually, they represent the sinks in the flow network.
    """

    def __init__(
        self,
        location: GeoLocation,
        num_sites: int = 1,
        demand: Optional[float] = None,
        connected_sites: Iterable[Site] = (),
    ) -> None:
        """
        The location is the key attribute, which impact the site_id and are read-only.
        Whenever you want to update the key attribute, please initialize a new DemandSite instance.

        @param location
        The geographical location of the site, using latitude and longitude or
        utm coordinates.

        @param num_sites
        The number of sites that are connected to the demand site.

        @param demand
        The connectivity demand for this point.

        @param connected_sites
        The list of sites that are connected to the demand site
        """
        self._location = location
        self._demand_id: str = deterministic_hash(
            self.latitude, self.longitude, self.altitude
        )

        self.num_sites = num_sites
        self.demand = demand

        self.connected_sites: List[Site] = []
        for site in connected_sites:
            self.connected_sites.append(site)

    @property
    def latitude(self) -> float:
        return self._location.latitude

    @property
    def longitude(self) -> float:
        return self._location.longitude

    @property
    def utm_x(self) -> float:
        return self._location.utm_x

    @property
    def utm_y(self) -> float:
        return self._location.utm_y

    @property
    def utm_epsg(self) -> int:
        return self._location.utm_epsg

    @property
    def altitude(self) -> Optional[float]:
        return self._location.altitude

    @property
    def demand_id(self) -> str:
        return self._demand_id
