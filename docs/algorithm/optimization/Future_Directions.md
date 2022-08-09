# Future Directions

## P2MP Constraints in Site Selection

During the site selection phase, we do not incorporate P2MP constraints. That
is not done until
[Interference Minimization](Interference_Minimization.md#point-to-multipoint)
when decisions are made on links/sectors. In our experience, this is one of the
primary causes of disconnected sites in the final plan that is not addressed by
making changes to the input configuration (i.e., it is not a user error).

What happens is that the base minimum cost network from
[Cost Minimization](Cost_Minimization.md) does not propose enough DNs to
actually serve all of the CNs. Because P2MP is not incorporated, a DN might
connect to far more sites than it is allowed. By the time that P2MP gets
incorporated, site selection is finalized and there are not enough DNs to
connect the network.

Sometimes this gets taken care of by the redundancy phase, which can add
additional sites. This is most common with
[Coverage Maximization](Coverage_Maximization.md). In fact,
[Cost Minimization with Redundancy](Redundancy_Optimization.md) might tend to
have worse performance because it is not arbitrarily adding additional sites
like Coverage Maximization can when the budget allows. Regardless, the
redundancy phase adding additional sites that addresses P2MP limitations is a
side-effect and not a sufficiently robust or reliable approach.

Unfortunately, to incorporate P2MP constraints in the site selection phase
would require adding link decisions which significantly increases the size of
the problem. It would essentially add all of the links in the candidate network
to the optimization problem. By delaying the link decisions until site
selection is finalized, we are working on a much smaller subgraph of the
candidate network. It makes the problem tractable.

Previously, we attempted to incorporate P2MP into the site selection phase. It
solved the stated issues, but the optimization problem did not reliably find a
solution in a reasonable amount of time.

At this point, some research needs to be done to see if another approach can
work. Some ideas include:

- Repeatedly solve the cost minimization problem until the P2MP constraints are
satisfied. Between each solve, identify sectors with P2MP violations and
through some reasonable process remove some of the violating links from
consideration (e.g., links that carry the least amount of flow).

- Reduce the number of links in the optimization problem by using some
heuristic to remove links that are unlikely to be useful. The idea here is to
fully incorporate link decisions and related constraints (including P2MP) into
the cost minimization step but remove the vast majority of links from
consideration. This is similar in principle to the heuristic acceleration used
in [Cost Minimization with Redundancy](Redundancy_Optimization.md#heuristic-acceleration).

One of the interesting advantages of the second option is that it can
theoretically obviate the need for Interference Minimization. In addition to
P2MP constraints, ideally it would include the interference constraints, but
even if it did not, it might reduce Interference Minimization to simply channel
assignment. If that's the case, it might even motivate the usage of an
interference-aware heuristic for channel assignment. And for single-channel
networks, using interference-aware constraints (e.g., combinations of links
that should not be selected together based on the amount of interference they
would cause) might be sufficient.

## Multi-Channel Link Capacity and Interference

At this point we do not model link capacity and interference differences
between the channels in multi-channel network planning. Instead, we leverage a
single driving frequency. For now, that means users would have to do some
post-processing of the channel assignments to decide which channel decision
from the network plan corresponds to which channel frequency band in
deployments.

Fortunately, incorporating the link capacities should not require significant
changes to
[Interference Minimization](Interference_Minimization.md#multi-channel-constraints).
In particular, the main constraints that need to be modified are Flow Balance,
which would become

$$
f_{i,j} \leq \sum^{C}_{c=1} \tau_{i,j,c} t_{i,j,c}\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$

and SINR, which would become

$$
S^{-1}_{i,j,c}=\frac{N_p + \sum_{(k,l)}{\chi_{i,k,l}I^{i,j,c}_{k,l}}}{RSL_{i,j,c}}
$$

Essentially, the changes are simply to make link capacity, RSL and interference
channel-dependent.

## Sector Orientation

Ideally, the orientation of the sector would be part of the optimization
problems. However, incorporating it would make the optimization problem much
larger and more complex. Instead, we use a heuristic approach.

Prior to the optimization, the DN sectors are oriented in such a way as to
minimize the deviation of all the candidate links from the boresight of its
connecting sector. But if the number of DN nodes, sectors per node, and
horizontal scan range do not cover the full 360 degrees, inevitably there will
be some links that do not have any sectors. Unfortunately, that means those
links cannot be selected during the optimization phase in order to ensure the
final link selection can always have a valid sector assignment. This is a
downside of not including sector orientation in the optimization problem; in
that case, it would instead prevent certain combinations of links from being
selected but not eliminate any particular link explicitly.

After the optimization is complete, the sectors are re-oriented to minimize the
deviation of all the active links from the boresight of its connecting sector
while obeying P2MP, deployment and other constraints enforced during the
optimization. More weight is given to long-distance and backhaul links to
ensure they are more likely to be in the boresight so they do not suffer from
too much scan loss. However, there can be issues as this can hardly guarantee
that all critical links are close to the boresight. In many cases, they can
fall much closer to the sector boundary.

The general approach is likely worth revisiting to avoid eliminating
potentially useful links prior to optimization and having critical links end up
close to the sector boundary.

## POP Placement

In some cases, users need to add POPs to the network but want the planner to
propose the POP locations from the candidate DNs. The current approach converts
all the DNs into POPs, removes all backhaul links (leaving just POP-CN and
POP-Demand Site connections) and maximizes the coverage. This helps distribute
the additional POPs in such a way to avoid having overlapping coverage but
views the network with a single hop. Bringing a multi-hop view should provide
even better POP placement.

Some ideas to achieve this include:

- Solve the base minimum cost network problem but let every DN be convertible
into a POP. Critically, backhaul links are not removed. This is easiest to
achieve by adding a link decision between the supersource and each DN. If that
link is selected, then the DN is converted into a POP.

- Use a heuristic approach, for example one based on clustering in graph space
(e.g., Lloyd's algorithm).

## Variable POP Capacity

The current assumption is that each POP connects to the internet backbone and
has the same connection capacity, usually 10 Gbps. But it is possible that in
mixed-radio (e.g., Microwave and 60GHz) environments, some POPs might have
different connection capacities. This should be a fairly straightforward update
that lets the users specify a POP capacity in the input sites file.

## Uplink Modeling

Currently only the downlink performance is optimized, but uplink performance
can be quite different. For starters, the interference a link experiences when
transmitting downlink versus uplink is not necessarily the same. And with
asymmetric time division duplexing, the network plan can potentially improve
downlink performance at the cost of uplink performance, but without modeling
uplink, the trade-off is not clear.

It is worthwhile to explore modeling uplink performance in both optimization
and analysis. An open question is if the network plan would change
significantly enough to merit its inclusion in the optimization stage. If not,
the feature could be restricted to just analysis so as to avoid making the
optimization problems even larger.

## Channel Bonding

Channel bonding is the practice of combining two adjacent channels within a
frequency band to improve link throughput. In CB1, there are 4 channels, 1
through 4. In CB2, channels 1 and 2 are combined to form channel 9, channels 2
and 3 are combined to form channel 10, and channels 3 and 4 are combined to
form channel 11.

Modeling CB2 presents several challenges. Channel 10 overlaps with channels 9
and 11, but
[Interference Minimization](Interference_Minimization.md#multi-channel-constraints)
assumes that the channels are orthogonal. The modeling of interference for such
cases would have to be updated in order to incorporate this. Of course, if the
network is restricted to just channels 9 and 11, this is not an issue. In this
case, simply updating the MCS table and some of the other parameters like
thermal noise power should be sufficient. However, for hybrid CB1/CB2 networks,
the issue of overlapping channels reappears.

## A Note on Run-to-Run Reproducibility

It is critical for both software development and user-confidence that running
the same plan twice produces the same results. This can be particularly
challenging when solving ILPs because small changes can result in very
different network plans. A great deal of care has been taken to ensure
run-to-run reproducibility in the software.

For the ILP solver to produce the exact same results every time, it is
necessary that the constraints are added to the optimization problem in the
same order every time. For this reason, the sites, sectors and links in the
topology are sorted prior to optimization.

The sorting is based on an internal id that is assigned to each topology
component. Importantly, that id must be the same every run so it is derived
from the relevant fixed properties of the topology component. The site id is
based on its location, type, and device sku. The sector id is based on its site
id, node id, position and device type. The link id is based on the site ids of
its connecting sites.

As long as the site id is unique and reproducible, the sector and link ids
will be as well. To generate the site id, it needs to use its longitude and
latitude. Instead of using them directly, we hash them along with the altitude,
site type and device sku. Most default hashing functions change from run to
run, so MD5 is used to ensure the output is always the same with the same
inputs. It is considered cryptographically weak, but that is irrelevant for our
purpose.

One thing we carefully avoid in the code is performing loops over sets where
the order of the loop matters, such as when adding variables and constraints to
the optimization problem. The order of data within sets, unlike dictionaries in
Python, can change in every run.

It also is important that the ILP solver is configured for producing
deterministic results. For FICO Xpress, it can be made deterministic by
explicitly setting the number of threads. There are other ways (so that the
number of threads can match the host machine), but you might have to reach out
to FICO for details.

If you are seeing run-to-run variations, there are several steps to help debug
the issue:

1. Enable debug mode
2. Check the kml file of the sorted topology to make sure they are identical;
if the site ids or anything else is different, there are no guarantees of
reproducibility
3. Check the kml files at each step of the optimization to identify at which
stage the difference appears
4. Check the optimization problem files at each step of the optimization and
identify at which stage the difference appears

For a given stage, if the problem files are the same but the kml output is
different, then that indicates the issue lies in the ILP solver (e.g., the
number of threads was not set). On the other hand, if the problem files are
different, then the issue is likely with some variable or constraint appearing
in different order from one run to the next. Try to identify which variable or
constraint it is (it is often fairly clear just by reading through the problem
file) and then try to identify where in the code the variable or constraint is
added and the underlying cause of the problem.
