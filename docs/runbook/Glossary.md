# Glossary

For the config parameter demonstration, please refer to [template.yaml](https://github.com/terragraph/terragraph-planner/blob/main/terragraph_planner/data/template.yaml)

**2.5D**

Commonly used to describe raster GeoTIFF files. A given x,y raster tile correlates
to a single elevation. This is considered 2.5D because there's only a single data
point in the third dimension (z-axis) and not multiple data points, which is
expected of true 3D.

**3D**

Three dimensional.

**Access**

A network that connects subscribers to a particular service provider and, through
the carrier network, to other networks such as the Internet.

**AOI**

Area of Interest.

**Azimuth**

The orientation at which a radio antenna is pointed. This is based on a
compass angle between 0-360 degrees.

**Backhaul**

A backhaul is the connection from the wireless cell tower to the internet.

**Beamwidth**

Beam width is the aperture angle from where most of the power is radiated.

**Boresight**

Boresight is the axis of maximum gain (maximum radiated power) of a directional
antenna.

**Boundary**

The area of interest as a polygon.

**Candidate Graph**

A graph with all possible deployment sites and all possible line-of-sight
links between them.

**CAPEX**

One-time cost of the asset, including things like equipment, install,
down payment, etc.

**CIR**

Committed Information Rate.

**CN**

Client Node. A node serving as the termination point where service delivery
takes place. These are not a part of the mesh network for distribution, but
provide connectivity to a fixed client such as an eNodeB, Wi-Fi Access point
(AP), or a fixed connection to a home or office.

**dB**

A unit of measurement of Radio Frequency Power or Radio Signal Strength.

**dBi**

The expression dBi is used to define the gain of an antenna system relative
to an isotropic radiator at radio frequencies.

**dBm**

The power ratio in decibels (dB) of the measured power referenced to one
milliwatt (mW).

**Deg**

Degree.

**Device**

The hardware that is mounted on the physical site.

**Device SKU**

The stock keeping unit of the device to differentiate different types of devices.

**DHM**

Digital Height Model providing a 2.5D model of the relative height of buildings,
foliage, construction, etc. to the surface.

**DN**

Distribution Node. A node that distributes the bandwidth from a fiber PoP to
neighboring nodes in the Terragraph mesh network. These are the active elements
that make up the network itself.

**DSM**

Digital Surface Model providing a 2.5D model of the absolute elevation of the
surface.

**DTM**

Digital Terrain Model providing a 2.5D model of the absolute elevation of the
terrain without buildings, foliage, construction, etc.

**Frequency**

Frequency (measured in Hz) describes the number of waves that pass a fixed
place in a given amount of time.

**Gain**

It is a key performance number which combines the antenna\'s directivity
and electrical efficiency. In a transmitting antenna, the gain describes
how well the antenna converts input power into radio waves headed in a
specified direction.

**Gbps**

Gigabits per second.

**GeoTIFF**

GeoTIFF is a public domain metadata standard which allows georeferencing
information to be embedded within a TIFF file.

**Hops**

A portion of a signal\'s journey from source to receiver or a communications
channel between two stations.

**Human Input**

Any combination of POPs, CNs, DNs, and/or Exclusion Zones to be manually
included.

**Hybrid**

A network that uses more than one type of connecting technology or topology.

**KML**

KML is a file format used to display geographic data in an Earth browser.

**KPI**

Key Performance Indicators.

**Latency**

Delay before a transfer of data begins following an instruction for its transfer.

**LOS**

Line of Sight.

**Max**

Maximum.

**Mbps**

Megabits per second.

**MCS**

Based on a link's SNR and PER, link adaptation on the Terragraph radio will
pick a corresponding MCS to ensure that the link remains stable in changing
RF conditions. MCS refers to the notion of packaging less data in fewer number
of bits and mathematically protecting it to increase the probability of
successful decoding on the receiver end. Low MCS is directly proportional
to lower throughput.

**Mean**

The value obtained by dividing the sum of several quantities by their number;
an average.

**Mesh Network**

Terragraph employs a directed mesh network of DNs to deliver broadband services.
A directed mesh network is designed to use multiple connections in several
directions from each node thereby providing both high reliability and path
redundancy.

**MHz**

Megahertz.

**Min**

Minimum.

**Ms**

Milliseconds.

**Nb times on MCS route**

Number of times this link would be used if an MCS based routing protocol is
followed.

**Noise Figure**

It is a measure of degradation of the signal-to-noise ratio, caused by
components in a signal chain. It is a number by which the performance of
an amplifier or a radio receiver can be specified, with lower values
indicating better performance.

**OPEX**

Operating Expenditure. OPEX or Opex is classified as day-to-day or recurring
expenditures such as ncluding things like maintenance, lease, grid power etc.

**Optimized Graph**

A subset of the candidate graph that guarantees to have enough capacity to
support the user load.

**OSM**

Open Street Map.

**Outages Caused**

Number of demand sites that would lose their connection to any of the active
POPs if this link were to go down.

**POP**

Point of presence. A DN that serves as the demarcation between the Terragraph
network and the provider's backbone network. The PoP node is part of the
Terragraph network

**Rx**

Receiver.

**Sector**

The geographical area covered by cellular radio antennas often refer to sector,
as the coverage area of the antenna beam.

**Site**

A collection of one or more nodes installed at the same physical location

**SKU**

All the **SKU**s mentioned in the documentation refer to the Device SKU.

**SNR**

Signal-to-Noise Ratio. The ratio of intended receive signal to the total
noise and interference. The limit of connectivity is determined by the
SNR that is achieved at the receiver, which drives connectivity and the
speed of the connection.

**Terragraph**

Terragraph, (abbreviated as TG) is a 60 GHz multi-hop multi-point wireless
network, designed to meet the growing demand for reliable, high-speed
internet that delivers gigabit speeds in dense urban or suburban areas.

**Tx**

Transmitter.
