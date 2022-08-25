# Features

## Multi-SKU

The planner requires users to specify devices to be used in the network plan.
If multiple DN or CN types are included in the list of devices, the planner
can decide which type should be used to minimize cost and maximize coverage.

**How to add a device**

To add a new device, create a new entry in the `DEVICE_LIST` section and
populate the following fields.

| Field name               | Type                                            | Meaning                                                                           |
| ------------------------ | ----------------------------------------------- | --------------------------------------------------------------------------------- |
| DEVICE_SKU               | str                                             | The device SKU or Name that used to identify the hardware                         |
| DEVICE_TYPE              | str                                             | The type of the device, which should be either DN or CN                           |
| NODE_CAPEX               | float                                           | Hardware cost of DN or CN                                                         |
| NUMBER_OF_NODES_PER_SITE | int                                             | Maximum number of radio nodes allowed on each site; for CNs, this input must be 1 |
| SECTOR_PARAMS            | a struct with the fields in the following table | The set of radio specification parameters                                         |

The set of radio specification parameters are:

| Sector Params Fields      |       |                                                                                                           |
| ------------------------- | ----- | --------------------------------------------------------------------------------------------------------- |
| HORIZONTAL_SCAN_RANGE     | float | Per-sector horizontal beamforming scan range of the antenna in degrees                                    |
| NUMBER_SECTORS_PER_NODE   | float | Number of sectors in each node                                                                            |
| ANTENNA_BORESIGHT_GAIN    | float | Antenna gain at boresight (dBi)                                                                           |
| MAXIMUM_TX_POWER          | float | Maximum transmit power in dBm                                                                             |
| MINIMUM_TX_POWER          | float | Minimum transmit power in dBm                                                                             |
| TX_DIVERSITY_GAIN         | float | Transmitter diversity gain in dB (e.g., polarization diversity)                                           |
| RX_DIVERSITY_GAIN         | float | Receiver diversity gain in dB (e.g., polarization diversity)                                              |
| TX_MISCELLANEOUS_LOSS     | float | Miscellaneous losses on the transmitter in dB (e.g., cable losses)                                        |
| RX_MISCELLANEOUS_LOSS     | float | Miscellaneous losses on the receiver in dB (e.g., cable losses)                                           |
| MINIMUM_MCS_LEVEL         | int   | The minimum MCS level allowed                                                                             |
| ANTENNA_PATTERN_FILE_PATH | str   | Antenna pattern file defining the signal loss of the antenna in different angles in Planet's format (txt) |
| SCAN_PATTERN_FILE_PATH    | str   | Scan pattern file defining the signal gain of the antenna boresight in different scan angles (csv)        |
| MCS_MAP_FILE_PATH         | str   | Scan pattern file contains the mapping between MCS, SNR, Mbps and Tx backoff (csv)                        |

**Multi-SKU Site Files**

If you choose to use an optional [Sites File](Input_Files.md#user-input-site-file)
in your plan, you may populate the Device SKU column in the CSV or field in the
KML file. If you wish to identify the device type for a particular site, the
SKU must correspond to one of the `DEVICE_SKU` entries you provide in the
`DEVICE_LIST` section. If it does not, an error will be returned.

**Note:** All SKUs are case-insensitive.

**Specifying Multiple SKUs for a Single Site**

Leave the field blank. This will allow the system to choose a SKU for you
during the plan's run. The Planner will take all the devices that match the
appropriate site type, place all SKUs at each site, and select among them. This
is equivalent to specifying multiple sites at the same location and explicitly
setting each one to each of the devices.

**How does Multi-SKU work?**

The planner places each available device at a site and selects the best device
to minimize cost and maximize coverage.

In general, you should not need to touch your sites file to switch between a
single-SKU run and a multi-SKU run. Instead, you can leave the Device SKU
column/field in the sites file blank and modify the device list. Of course, if
you have reason to predetermine a particular device type at a particular
site, specify the Device SKU explicitly.

## Automatic Site Detection

In addition to candidate site locations provided by the user, the planner can
automatically determine candidate site locations on building rooftops. This
can help accelerate the planning time by helping skip the process of manual
placement of sites. It can help ensure that, for example, the highest point
on the rooftop is selected, which can be difficult to do manually.

**How to use it**

1.  Provide the building outline data in the .shp or .kml format. See more
    details in [Building Outline File](Input_Files.md#building-outline-file).
2.  Populate the field under AUTOMATIC_SITE_DETECTION
    1.  Set `DETECT_HIGHEST`, `DETECT_CENTERS`, `DETECT_CORNERS` based on which
        type of location you want.
        -   `DETECT_HIGHEST` will detect a site location on the highest point on
            each building rooftop, based on the surface elevation data. If the
            surface elevation data (DSM or DTM + DHM) is not provided, the
            planner will use DETECT_CENTERS instead automatically.
        -   `DETECT_CENTERS` will detect a site location on the geometric center
            of each building rooftop.
        -   `DETECT_CORNERS` will detect one or more locations on the corners of
            each building rooftop. Set MAX_CORNER_ANGLE, which is used to filter
            corners when DETECT_CORNERS is enabled. If not set, every vertex
            on the rooftop is considered to be a corner.
        -   Among all the candidate locations, the planner will pick the ones
            with the most LOS links.
    2.  Set `DN_DEPLOYMENT` as False if you don't want to detect DN site location.
        If enabled, the location with the most LOS links would be selected as
        the DN location. A candidate CN is still placed at that same location
        in case the planner decides that the DN is not needed.

## Demand Models

Demand sites are imaginary sites in the network that are added to represent
the final destination of downstream flow from the POPs. In graph theory
terminology, they are the sinks nodes of the directed graph that represents the
network. They are distinct from CNs because, in part,

- Not all networks will have a CN
- Multiple CNs can connect to the same demand site allowing the network to
  decide which CN is needed
- A DN and a CN can connect to the same demand site allowing the network to
  decide which one is needed (e.g., a DN can both serve the customer like a
  CN while simultaneously pushing data to other customers downstream).
- Each DN and CN can connect to a different number of demand sites resulting
  in different overall demand requirements for each one

Each demand site is associated with an amount of desired demand, i.e.,
throughput. The flexibility afforded by using demand sites enables several
different approaches to demand modeling.

There are three demand models that can be enabled:

1. CN Demand
2. Uniform Demand
3. Manual Demand

**CN Demand**

In this case, a demand site is added to every CN in the network. This is a
very common deployment scenario. Consider a rooftop deployment - the demand
sites in this case are effectively equivalent to subscribers.

**Uniform Demand**

A grid of demand sites is added within the area of interest. The spacing of the
grid is configurable and for each demand site, the DNs and CNs within a
specified distance of it are connected to it.

This can be useful when wanting to ensure coverage throughout a geographic
area to blanket it with service (e.g., for municipal Wi-Fi).

**Manual Demand**

The demand sites are added explicitly by the user. Like the Uniform Demand
model, for each demand site, the DNs and CNs within a specified distance of it
are connected to it.

**How to use it**

Parameters to control the demand site model are found under the `DIMENSIONING`
subsection of `NETWORK_DESIGN`.

1. To enable the CN Demand model, set
   `ENABLE_CN_DEMAND` to True. To enable the Uniform Demand model, set
   `ENABLE_UNIFORM_DEMAND` to True. To enable the Manual Demand model, set
   `ENABLE_MANUAL_DEMAND` to True. At least one must be set to True but
   multiple can be enabled simultaneously, in which case demand sites will be
   added according to each enabled model.
2. If `ENABLE_UNIFORM_DEMAND` is True, specify the grid spacing under
   `DEMAND_SPACING`.
3. If `ENABLE_MANUAL_DEMAND` is True, specify the demand sites in the
   [Candidate Topology File](Input_Files.md#candidate-topology-file).
4. If `ENABLE_UNIFORM_DEMAND` or `ENABLE_MANUAL_DEMAND` is True, specify the
   connection distance between the DNs/CNs and the demand sites under
   `DEMAND_CONNECTION_RADIUS`.
5. Specify the amount of demand under `DEMAND`.

## Tiered Service

Tiered Service allows you to provide different levels of bandwidth to chosen
CNs when the CN Demand model is enabled. Example use-cases are:

1.  A region with single-family homes and multi-dwelling buildings with a
    different number of units in each one. For example, assume you want each
    customer to receive 100 Mbps of service and there is a building with 5
    units and another with 3. This feature allows you to serve 500 Mbps of
    service to the first building and 300 Mbps of service to the second which
    is then further subdivided among the various customers so each one receives
    exactly the desired amount of service.
2.  Networks shared by businesses and residential homes where businesses require
    more bandwidth.

The feature works by creating multiple demand sites at specified CN locations.
For the example in #1 above, this means placing 5 demand sites on the CN on the
building with 5 units and 3 demand sites on the building with 3 units.

**How to use it**

1. Set `ENABLE_CN_DEMAND` to True.
2. Modify the [User Input Site File](Input_Files.md#user-input-site-file).
   1. For KML/KMZ input, for each relevant site, add a `number of subscribers`
      data field and set to the desired value.
   2. For CSV input, add a `number of subscribers` column and set it to the
      desired value for each relevant site.

The `number of subscribers` field is only applied to CNs and ignored for DNs
and POPs. If left blank for a CN, it is assumed to be 1.

## POP Placement

POP Placement allows you to specify additional POPs you would like to add to a
candidate topology. The POPs are selected from the candidate DNs.

This can be useful to meet demand requirements when the number of provided POPs
is insufficient. It can also help connect disconnected portions of the network.
It is particularlly useful in early-stage planning where not all possible POP
locations are already known.

**How to use it**

Specify the number of additional POPs you would like in `NUMBER_OF_EXTRA_POPS`
under the `NETWORK_DESIGN` section.

## Maximize Common Bandwidth

Maximize Common Bandwidth (MCB) equally distributes bandwidth across all
connected demand sites during the network optimization steps. When MCB is
disabled, the total shortage (unsatisfied demand) in the network is minimized
but there are no guarantees of how that shortage is distributed among clients.

If the input demand is too high for the underlyling network, some clients can
be disconnected in order to improve the bandwidth to other clients. Consider
the following example. Suppose you have a single POP connected to 10 CNs.
For simplicity, assume that this POP has one sector and each of the links from
the POP to the CNs has a capacity of 1.8 Gbps. If you request that each CN
receives 200 Mbps of service, it will not be possible to satisfy that amount of
demand, so there will be (200 * 10 - 1800) = 200 Mbps shortage in the network.
With MCB disabled, that shortage can be split among all the CNs in different
ways (unfortunately, how it is distributed is unpredictable). It is possible
that the planner could provide 200 Mbps of service to 9 of the 10 CNs and leave
1 of the CNs disconnected. This is a common cause of disconnected sites when
planning networks.

One way to address this is to simply reduce the demand to 180 Mbps instead of
200 Mbps. However, it can often be difficult to determine what this value
should be in more complex networks. With MCB enabled, each of the 10 CNs will
get 180 Mbps of service because the shortage will be distributed among the CNs
evenly.

Unfortunately, this feature requires solving a few extra optimization problems
which might make the overall runtime worse. In many cases, simply adding more
POPs to the network or reducing the requested demand is a better alternative.

**How to use it**

To use the Maximize Common Bandwidth feature, set `MAXIMIZE_COMMON_BANDWIDTH` under
the `NETWORK_DESIGN` section to True.

## Extend Base Topology

This feature enables the addition of new sites to a base topology with known
sites and links. The sites and links can be assigned with any status.

LOS will be computed between the sites in the base topology and the new sites
and between each of the new sites. The new candidate topology includes the base
topology as a subgraph. The candidate topology is then optimized to generate
a network plan.

**How to use it**

1. Get or generate the topology for the existing network. Store it as a
   KML/KMZ or CSV using the same rules as
   [Candidate Topology File](Input_Files.md#candidate-topology-file).
2. Specify the file path in `BASE_TOPOLOGY_FILE_PATH` under the `DATA` section.
3. Generate a [User Input Site File](Input_Files.md#user-input-site-file) to
   specify the new sites.

**NOTE**: This feature cannot be enabled together with [Automatic Site Detection](#automatic-site-detection)
feature.
