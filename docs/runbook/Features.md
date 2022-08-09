# Features

The following table indicates how different features impact the result.

| **Feature Name**                                                                | **CN Connectivity** | **Bandwidth Impact** | **Network Operations** |
| ------------------------------------------------------------------------------- | ------------------- | -------------------- | ---------------------- |
| [POP Placement](#pop-placement)                                                 |                     | **X**                |                        |
| [Multi-SKU](#multi-sku)                                                         | **X**               |                      |                        |
| [Automatic Site Detection](#automatic-site-detection)                           |                     |                      | **X**                  |
| [Maximum Common Bandwidth (MCB)](#maximum-common-bandwidth-mcb)                 | **X**               | **X**                |                        |
| [Tiered Service](#tiered-service)                                               |                     |                      | **X**                  |
| [Extend existing Candidate Graph (EECG)](#extend-existing-candidate-graph-eecg) |                     |                      | **X**                  |


The following table introduce each feature briefly.

| **Feature Name**                                                                | **Feature Description**                                                                                                                                                                                                                                                                                                                                                                  | **Use Case Notes**                                                                                                            |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| [POP Placement](#pop-placement)                                                 | The POP placement allows you to specify bandwidth and the number of POPs you would like to add to a plan. The planner will place POPs strategically, including additional DNs, to improve coverage and bandwidth.                                                                                                                                                                        | This feature is useful to meet bandwidth in rural areas and dense urban clusters.                                             |
| [Multi-SKU](#multi-sku)                                                         | The Multi-SKU feature adds support for Terragraph Network Plans that can mix and match devices from a set in order to minimize cost and maximize coverage.                                                                                                                                                                                                                               | This feature is useful when planning a network with multiple types of hardware.                                               |
| [Automatic Site Detection](#automatic-site-detection)                           | The planner can automatically determine candidate site locations on building rooftops. This can help accelerate the planning time by helping to skip the process of manual placement of sites.                                                                                                                                                                                           | It can help ensure that the highest point in the rooftop is selected, which can be difficult to do manually.                  |
| [Maximum Common Bandwidth (MCB)](#maximum-common-bandwidth-mcb)                 | Maximum Common Bandwidth equally distributes bandwidth across all CNs, reducing the number of CNs that experience bandwidth starvation.                                                                                                                                                                                                                                                  | MCB was used in plans with different morphology (dense urban, suburban, and rural).                                           |
| [Tiered Service](#tiered-service)                                               | With the Tiered Service Feature, you can now provide different levels of bandwidth to a selected number of CNs that cover multi-dwelling units, businesses and residential homes.                                                                                                                                                                                                        | The tiered feature properly addresses residential homes and multi-dwelling buildings requiring different levels of bandwidth. |
| [Extend existing Candidate Graph (EECG)](#extend-existing-candidate-graph-eecg) | Previously the TG Planner only supported computing line-of-sight from scratch. Now the planner supports extending a base network with extra sites. Now the planner will reserve all the sites and links in the base topology, and then compute the links between new sites and existing sites and generate a candidate graph and a final optimized graph. This reduces the plan runtime. | The EECG feature addresses extending the existing network area adding more sites.                                             |

## POP Placement

POP Placement allows you to specify the number of POPs you would like to add to
a plan. The planner will place POPs strategically, including positioning
additional DNs, to improve coverage and bandwidth.

This feature is useful to meet bandwidth and coverage requirements. POP
Placement is helpful in rural areas which contain site clusters with
significant distance between them and very few POP locations. It is also
helpful in dense urban clusters that do not have enough POPs to meet bandwidth
requirements.

**How to use it?**

To use the POP Placement feature:

1.  Go to the Network Design section of the YAML file.

2.  Populate the Extra POPs parameter with a value greater than zero. **Note:**
    The Always Active POPs parameter is useful when adding POPs to an existing
    plan. If you select Always Active POPs, the system assumes POP sites in the
    human sites file already exist and should be used.

3.  Run your plan.

If you have already run your plan without adding extra POPs, you will probably
find your new plan impacts the following metrics:

-   Number of active/candidate POP sites

-   Number of active CN/DN/POPs connected to demand sites

-   Number of active DN sectors on POP locations

-   Minimum guaranteed bandwidth for the full topology flow results

## Multi-SKU

The Multi-SKU feature adds support for Terragraph Network Plans that can mix
and match devices from a set in order to minimize cost and maximize coverage.

**How to add a device**

To add a new device, create a new section within the `DEVICE_LIST` section and
populate the following fields.

| Field name               | Type                                            | Meaning                                                                                                   |
| ------------------------ | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| DEVICE_SKU               | str                                             | The device SKU or Name that used to identify the hardware                                                 |
| DEVICE_TYPE              | str                                             | The type of the device, which should be either DN or CN                                                   |
| NODE_CAPEX               | float                                           | Hardware cost of DN or CN.                                                                                |
| NUMBER_OF_NODES_PER_SITE | int                                             | Maximum number of radio nodes allowed on each site. For CNs, this input will be ignored as it is always 1 |
| SECTOR_PARAMS            | a struct with the fields in the following table | The set of radio specification parameters                                                                 |

| Sector Params Fields      |       |                                                                                                           |
| ------------------------- | ----- | --------------------------------------------------------------------------------------------------------- |
| HORIZONTAL_SCAN_RANGE     | float | Per-sector horizontal beamforming scan range of the antenna in degrees                                    |
| NUMBER_SECTORS_PER_NODE   | float | Number of sectors in each node                                                                            |
| ANTENNA_BORESIGHT_GAIN    | float | Antenna gain at boresight (dBi)                                                                           |
| MAXIMUM_TX_POWER          | float | Maximum Transmission power in dBm                                                                         |
| MINIMUM_TX_POWER          | float | Minimum Transmission power in dBm                                                                         |
| TX_DIVERSITY_GAIN         | float | Transmitter diversity gain in dB (e.g., polarization diversity)                                           |
| RX_DIVERSITY_GAIN         | float | Receiver diversity gain in dB (e.g., polarization diversity)                                              |
| TX_MISCELLANEOUS_LOSS     | float | Miscellaneous losses on the transmitter in dB (e.g., cable losses)                                        |
| RX_MISCELLANEOUS_LOSS     | float | Miscellaneous losses on the receiver in dB (e.g., cable losses)                                           |
| MINIMUM_MCS_LEVEL         | float | The minimum MCS level allowed                                                                             |
| ANTENNA_PATTERN_FILE_PATH | str   | Antenna pattern file defining the signal loss of the antenna in different angles in Planet's format (txt) |
| SCAN_PATTERN_FILE_PATH    | str   | Scan pattern file defining the signal gain of the antenna boresight in different scan angles (csv)        |
| MCS_MAP_FILE_PATH         | str   | Scan pattern file contains the mapping between MCS, SNR, Mbps and Tx backoff (csv)                        |

**How to delete a device**

You can delete a device from your plan's device list. To do this:

1.  In the `DEVICE_LIST` of the `RADIO` section, select the parameters of the device you
    would like to remove.
2.  Delete them from the YAML file and re-save the YAML file.

The device will no longer be included in your device list for your plan.

**Multi-SKU in Site Files**

If you choose to use an optional Sites File in your plan, you may populate
the Device SKU column in the CSV or field in the KML file. If you wish to
identify the device type for a particular site, the SKU will need to
correspond to the SKU/Name you provide in the devices configuration step.

**What happens if I include a non-existent SKU in my sites file?**

Upon running the plan, the Network Planner will need to match the SKU in
the Sites File with a defined SKU in your plan. If it cannot, it will return
an error. The error will not be identified until run-time.

**Note:** All SKUs are case-insensitive.

**What if I don't provide the SKU in the sites file?**

This will allow the system to choose a SKU for you during the plan's run.
The Planner will take all the devices that match the appropriate site type,
place all SKUs at each site, and select among them.

**How does multi-SKU work?**

The Terragraph Planner places each available device at a site and selects the
most appropriate device to minimize cost and maximize coverage.

You do not need to touch your sites file to switch between a single-SKU run
and a multi-SKU run. Leave the Device SKU column/field in the sites file blank
unless you have reason to predetermine a particular device type at a particular
site. The Terragraph Planner will select the best device type to optimize
coverage and budget.

**What if I don't want a multi-SKU plan?**

You are not required to use the multi-SKU capabilities of the Terragraph Planner.
You are able to run a single-SKU plan by using the new Device field to define or
configure one DN and one CN device.

## Automatic Site Detection

In addition to candidate site locations provided by the user, the planner can
automatically determine candidate site locations on building rooftops. This
can help accelerate the planning time by helping skip the process of manual
placement of sites. It can help ensure that, for example, the highest point
on the rooftop is selected, which can be difficult to do manually.

**How do I use it?**

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

## Maximum Common Bandwidth (MCB)

Maximum Common Bandwidth (MCB) equally distributes bandwidth across all connected
clients. When MCB is disabled, the total shortage in the network is minimized
but there are no guarantees of how that shortage is distributed among clients.
In fact, when MCB is disabled, if the input demand is too high for the
underlying network, some clients can be disconnected in order to improve
the bandwidth to the connected clients. Instead, MCB ensures that all of
the clients that can be connected are connected, although sometimes at
a lower bandwidth. This is roughly equivalent to lowering the demand.

The minimum guaranteed bandwidth can be improved by relieving network congestion
of highly utilized links either by moving POPs or placing extra POPs. See the
[Pop Placement](#pop-placement) feature for information on how to quickly place
extra POPs.

**How to use it?**

1.  Go to the Network Design section.
2.  Set the Maximize minimum guaranteed bandwidth parameter to "True".
3.  Set the Link Capacity Filter value (Gbps) as required; Default = 0

**Note:** Some links might have 0 capacity. In that case, if such a link is
necessary to reach the site, it\'s still unreachable. There is also a
parameter to filter links below some capacity. That could be useful in some
rare cases where low capacity links are connecting some sites causing the max
common bandwidth to be low. In that case, it's better to disconnect those sites
by filtering out the low capacity links (that is, prevent the optimizer from
selecting them). Regardless, if you choose to filter links below 10Mbps for
example, then all such links will be marked unreachable.

**Key Metrics**

- Number of active CN/DN/POPs connected to demand sites
- Number of active/connectable candidate/total candidate CN sites
- Full topology flow results - Percent of demand sites, minimum guaranteed
  bandwidth (Gbps)

## Tiered Service

Previously the TG Planner only provided identical bandwidth to each of the CNs
it serves. With the Tiered Service feature, you can now provide different levels
of bandwidth to a selected number of CNs. The Tiered Service feature properly
addresses two use cases:

1.  Multi-dwelling buildings with units requiring different levels of bandwidth.
2.  Network shared by businesses and residential homes where businesses require
    a higher amount of bandwidth.

These use cases can increase with more businesses going to a work from home format.

**How to use it?**

1.  Create a plan with a new modified Site List CSV, which includes a new
    "demand_sites" column.
2.  Optionally, a new modified KML/KMZ site file can be used instead of modified
    Site List CSV. The KML/KMZ file is supposed to contain a demand_site data
    field

**Key Metrics:**

Full topology flow "Percent of demand sites, minimum guaranteed bandwidth" Gbps
metric should be compared to values in the "Incoming flow" column in the sites
optimized csv file for matching.

## Extend Existing Candidate Graph (EECG)

The EECG feature addresses the use case of extending existing network area by
adding more sites. Previously the TG Planner only supported computing Line-of-Sight
from scratch before. Now the Planner supports to extend a base network with
extra sites. Now the planner will reserve all the sites and links in the base
topology, and then compute the links between new sites and existing sites and
generate a candidate graph and a final optimized graph. This reduces the plan
runtime.

**How to use it?**

1.  Get all the files from an existing plan.
2.  Keep the configs from the existing plan, but update the following fields
    1.  `BASE_TOPOLOGY_FILE_PATH`: a file path of the output file from the existing
        plan
    2.  `SITE_FILE_PATH`: a path of the file with the added sites
3.  Rerun the plan

**Key Metrics**:

Number of active/connectable candidate/total candidate CN sites.
