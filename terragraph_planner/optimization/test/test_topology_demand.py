# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from copy import deepcopy
from unittest import TestCase

from terragraph_planner.common.configuration.configs import OptimizerParams
from terragraph_planner.common.configuration.enums import LocationType, SiteType
from terragraph_planner.common.data_io.utils import extract_topology_from_file
from terragraph_planner.common.exceptions import OptimizerException
from terragraph_planner.common.geos import GeoLocation, translate_point
from terragraph_planner.common.topology_models.demand_site import DemandSite
from terragraph_planner.common.topology_models.test.helper import (
    DEFAULT_CN_DEVICE,
    DEFAULT_DN_DEVICE,
    SampleSite,
    raw_square_topology,
    raw_square_topology_with_cns,
)
from terragraph_planner.common.topology_models.topology import Topology
from terragraph_planner.optimization.topology_demand import (
    _add_cn_demand_sites,
    _handle_hybrid_locations,
    _handle_rooftop_connections,
    add_demand_to_topology,
    connect_demand_to_colocated_sites,
)


class TestTopologyDemand(TestCase):
    def test_demand_on_square(self) -> None:
        """
        Test demand site placement on square topology with CNs
        """
        topology = raw_square_topology_with_cns()
        cn_demand = 0.1
        add_demand_to_topology(
            topology,
            OptimizerParams(
                device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
                demand=cn_demand,
            ),
        )
        self.assertEqual(len(topology.demand_sites), 2)
        for demand in topology.demand_sites.values():
            self.assertEqual(demand.demand, cn_demand)

    def test_demand_to_cn_simple(self) -> None:
        """
        Test demand placement on CNs
        """
        sites = [
            SampleSite(
                site_type=SiteType.CN,
                location=GeoLocation(latitude=0.0, longitude=0.0, altitude=0.0),
            ),
            SampleSite(
                site_type=SiteType.CN,
                location=GeoLocation(
                    latitude=0.0, longitude=0.0, altitude=100.0
                ),
            ),
            SampleSite(
                site_type=SiteType.CN,
                location=GeoLocation(
                    latitude=10.0, longitude=0.0, altitude=0.0
                ),
            ),
        ]
        topology = Topology(sites=sites)
        add_demand_to_topology(
            topology,
            OptimizerParams(device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE]),
        )
        # Although the CNs do not have any neighbors, demand sites should still
        # be added. However, only one demand site should be added at
        # lat,lon = 0,0 but with two connected sites
        self.assertEqual(len(topology.demand_sites), 2)
        for demand in topology.demand_sites.values():
            if demand.latitude == 0.0 and demand.longitude == 0.0:
                self.assertEqual(len(demand.connected_sites), 2)
            else:
                self.assertEqual(len(demand.connected_sites), 1)

    def test_uniform_demand_on_square(self) -> None:
        """
        Test uniform placement of demand sites
        """
        topology = raw_square_topology()
        add_demand_to_topology(
            topology,
            OptimizerParams(
                device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
                demand=0.1,
                enable_uniform_demand=True,
                demand_spacing=20,
                demand_connection_radius=50,
            ),
        )

        # Due to filtering of uniform demand sites, each site should connect to
        # up to 25 demand sites
        self.assertLessEqual(
            len(topology.demand_sites), 25 * len(topology.sites)
        )
        site_to_demand_sites = {}
        for demand_site in topology.demand_sites.values():
            for connected_site in demand_site.connected_sites:
                site_to_demand_sites[connected_site.site_id] = (
                    site_to_demand_sites.get(connected_site.site_id, 0) + 1
                )
        for number_demand in site_to_demand_sites.values():
            self.assertGreater(number_demand, 0)
            self.assertLessEqual(number_demand, 25)

    def test_uniform_demand_antimeridian(self) -> None:
        """
        Test uniform placement of demand sites across the antimeridian
        """
        locs = [
            translate_point(
                longitude=180, latitude=15, bearing=270, distance=105
            ),
            translate_point(
                longitude=-180, latitude=15, bearing=90, distance=105
            ),
            translate_point(
                longitude=180, latitude=15, bearing=0, distance=105
            ),
            translate_point(
                longitude=180, latitude=15, bearing=180, distance=105
            ),
        ]
        sites = [
            SampleSite(
                site_type=SiteType.POP,
                location=GeoLocation(latitude=locs[i][1], longitude=locs[i][0]),
            )
            for i in range(len(locs))
        ]

        topology = Topology(sites=sites)
        add_demand_to_topology(
            topology,
            OptimizerParams(
                device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
                demand=0.1,
                enable_uniform_demand=True,
                demand_spacing=50,
                demand_connection_radius=1000,
            ),
        )

        # Demand grid should be 7 x 7 (5 demand sites in 210m plus 1 additional
        # on each site due to buffer)
        self.assertEqual(len(topology.demand_sites), 49)

    def test_manual_demand(self) -> None:
        """
        Test manual placement of demand sites
        """
        topology = raw_square_topology()
        topology.demand_sites = {}

        # Generate demand sites at increasing distances away from each
        # subsequent site
        num_sites = len(topology.sites)
        locs = [
            translate_point(
                longitude=site.longitude,
                latitude=site.latitude,
                bearing=360.0 / num_sites * i,
                distance=50 + 10 * i,
            )
            for i, site in enumerate(topology.sites.values())
        ]
        for i in range(len(locs)):
            topology.add_demand_site(
                DemandSite(
                    location=GeoLocation(
                        latitude=locs[i][1], longitude=locs[i][0]
                    ),
                )
            )

        add_demand_to_topology(
            topology,
            OptimizerParams(
                device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
                demand=0.1,
                enable_manual_demand=True,
                demand_connection_radius=95,
            ),
        )

        # Each demand should connect to 1 site except for 1 which exceeds the
        # demand connection radius
        for demand_site in topology.demand_sites.values():
            self.assertEqual(demand_site.demand, 0.1)
            self.assertEqual(
                len(demand_site.connected_sites),
                0
                if demand_site.longitude == locs[-1][0]
                and demand_site.latitude == locs[-1][1]
                else 1,
            )

        # This time, set connection radius to be to small to connect to any
        # other sites; also ensure demand updates
        add_demand_to_topology(
            topology,
            OptimizerParams(
                device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
                demand=0.2,
                enable_manual_demand=True,
                demand_connection_radius=20,
            ),
        )

        for demand_site in topology.demand_sites.values():
            self.assertEqual(demand_site.demand, 0.2)
            self.assertEqual(len(demand_site.connected_sites), 0)

        # Verify that when not using manual demand, input demand sites are removed
        with self.assertRaisesRegex(
            OptimizerException, "No demand sites were added to the topology."
        ):
            add_demand_to_topology(
                topology,
                OptimizerParams(
                    device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
                    enable_cn_demand=True,
                    enable_manual_demand=False,
                ),
            )

    def test_load_manual_demand(self) -> None:
        kml_file_path = "terragraph_planner/common/data_io/test/test_data/test_raw_square_topology.kml"
        topology = extract_topology_from_file(
            kml_file_path,
            [DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
            None,
        )
        add_demand_to_topology(
            topology,
            OptimizerParams(
                device_list=[DEFAULT_DN_DEVICE, DEFAULT_CN_DEVICE],
                demand=0.1,
                enable_manual_demand=True,
                demand_connection_radius=1000,
            ),
        )

        # Each demand should connect to all sites due to large demand
        # connection radius
        self.assertEqual(len(topology.demand_sites), 6)
        for demand_site in topology.demand_sites.values():
            self.assertEqual(demand_site.demand, 0.1)
            self.assertEqual(len(demand_site.connected_sites), 6)

    def test_multi_sku_demand(self) -> None:
        """
        Test demand site placement in multi-SKU networks
        """
        dn_device1 = DEFAULT_DN_DEVICE
        dn_device2 = deepcopy(dn_device1)
        dn_device2.device_sku = "SAMPLE_DN_DEVICE2"
        cn_device1 = DEFAULT_CN_DEVICE
        cn_device2 = deepcopy(cn_device1)
        cn_device2.device_sku = "SAMPLE_CN_DEVICE2"
        params = OptimizerParams(
            device_list=[dn_device1, dn_device2, cn_device1, cn_device2]
        )

        sites = [
            SampleSite(
                site_id="CN1",
                site_type=SiteType.CN,
                location=GeoLocation(latitude=0, longitude=0),
                device=cn_device1,
            ),
            SampleSite(
                site_id="CN2",
                site_type=SiteType.CN,
                location=GeoLocation(latitude=0, longitude=0),
                device=cn_device2,
            ),
            SampleSite(
                site_id="DN1",
                site_type=SiteType.DN,
                location=GeoLocation(latitude=0, longitude=0),
                device=dn_device1,
            ),
            SampleSite(
                site_id="DN2",
                site_type=SiteType.DN,
                location=GeoLocation(latitude=0, longitude=0),
                device=dn_device2,
            ),
            SampleSite(
                site_id="POP",
                site_type=SiteType.POP,
                location=GeoLocation(latitude=10, longitude=0),
                device=dn_device1,
            ),
        ]

        topology = Topology(sites)
        topology.add_link_from_site_ids("POP", "DN1")
        topology.add_link_from_site_ids("POP", "DN2")
        topology.add_link_from_site_ids("POP", "CN1")
        topology.add_link_from_site_ids("POP", "CN2")

        add_demand_to_topology(topology, params)

        # Only one demand site although there are 2 CNs
        self.assertEqual(len(topology.demand_sites), 1)

        # That demand site has four connected site ids corresponding to each
        # co-located DN/CN
        demand_id = list(topology.demand_sites.keys())[0]
        self.assertEqual(
            len(topology.demand_sites[demand_id].connected_sites), 4
        )

        connected_sites = set()
        for site in topology.demand_sites[demand_id].connected_sites:
            connected_sites.add(site.site_id)
        self.assertEqual(connected_sites, {"CN1", "CN2", "DN1", "DN2"})

    def test_demand_on_hybrid_sites(self) -> None:
        """
        Test demand site placements with DN/CNs in the same location
        """
        topology = raw_square_topology()
        topology.demand_sites = {}  # Remove existing demand sites

        # Add a CN at the same location as each POP/DN
        # For the purpose of adding demand sites in this test, adding the
        # sectors and links are not necessary
        for site_id in list(topology.sites.keys()):
            site = topology.sites[site_id]
            cn_site = SampleSite(
                site_type=SiteType.CN, location=deepcopy(site.location)
            )
            topology.add_site(cn_site)

        # Add demand sites at each CN to the topology
        _add_cn_demand_sites(topology, demand=0.025)

        # There are 6 CNs, so check there are 6 demand sites
        self.assertEqual(len(topology.demand_sites), 6)

        # Connect hybrid DNs to the demand sites
        cn_sites_to_dn_sites = {}
        _handle_hybrid_locations(topology, cn_sites_to_dn_sites)

        self.assertEqual(len(cn_sites_to_dn_sites), 6)

        # Check that every CN site shares a location with a DN
        self.assertEqual(
            len(
                {
                    cn_site_id
                    for cn_site_id, dn_site_ids in cn_sites_to_dn_sites.items()
                    if len(dn_site_ids) > 0
                }
            ),
            6,
        )

        # Before connecting the DNs to the demand, only CNs should be connected
        self.assertEqual(
            len(
                [
                    site
                    for site in topology.demand_sites.values()
                    if len(site.connected_sites) > 1
                ]
            ),
            0,
        )

        connect_demand_to_colocated_sites(topology, cn_sites_to_dn_sites)

        # Check that all DNs have now been connected as well
        self.assertEqual(
            len(
                [
                    site
                    for site in topology.demand_sites.values()
                    if len(site.connected_sites) > 1
                ]
            ),
            len(topology.demand_sites),
        )

    def test_demand_on_building_rooftops(self) -> None:
        """
        Test demand site placement with DN/CNs on the same building
        """
        topology = raw_square_topology()
        topology.demand_sites = {}  # Remove existing demand sites

        # Add building ids to the POPs/DNs
        for site in topology.sites.values():
            site._location_type = LocationType.ROOFTOP
            site._building_id = (
                int(site.site_id[2])
                if site.site_type == SiteType.DN
                else int(site.site_id[3])
            )

        # Add a CN on same building as each POP/DN; the CN locations are arbitrary
        # to avoid placing in same location as the POP/DN (lat/lon = building_id/0
        # is used to make the locatioin arbitrary)
        # For the purpose of adding demand sites in this test, adding the
        # sectors and links are not necessary
        for site_id in list(topology.sites.keys()):
            site = topology.sites[site_id]
            cn_site = SampleSite(
                site_type=SiteType.CN,
                location=GeoLocation(latitude=site.building_id, longitude=0),
                location_type=LocationType.ROOFTOP,
                building_id=site.building_id,
            )
            topology.add_site(cn_site)

        # Add demand sites at each CN to the topology
        _add_cn_demand_sites(topology, demand=0.025)

        # There are 6 CNs, so check there are 6 demand sites
        self.assertEqual(len(topology.demand_sites), 6)

        # Connect DNs on the same rooftop as CNs to the demand sites
        cn_sites_to_dn_sites = {}
        _handle_rooftop_connections(topology, cn_sites_to_dn_sites)

        self.assertEqual(len(cn_sites_to_dn_sites), 6)

        # Check that every CN site shares a rooftop with a DN
        self.assertEqual(
            len(
                {
                    cn_site_id
                    for cn_site_id, dn_site_ids in cn_sites_to_dn_sites.items()
                    if len(dn_site_ids) > 0
                }
            ),
            6,
        )

        # Before connecting the DNs to the demand, only CNs should be connected
        self.assertEqual(
            len(
                [
                    site
                    for site in topology.demand_sites.values()
                    if len(site.connected_sites) > 1
                ]
            ),
            0,
        )

        connect_demand_to_colocated_sites(topology, cn_sites_to_dn_sites)

        # Check that all DNs have now been connected as well
        self.assertEqual(
            len(
                [
                    site
                    for site in topology.demand_sites.values()
                    if len(site.connected_sites) > 1
                ]
            ),
            len(topology.demand_sites),
        )
