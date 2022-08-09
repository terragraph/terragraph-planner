# Overview

## Problem Modeling

The network planning problem is modeled using directed graphs, whose vertices
are the sites and edges are the links. Sites are equipped with a type, i.e.,
POP, DN and CN. Generally, each POP is a source in the network, however, to
simplify modeling, we introduce a supersource that connects to each of the POPs
(so that flow emanates from a single location).

The sinks in the network are imaginary sites we call demand sites (each
equipped with some amount of desired demand) and are only used for modeling the
network flow problem. In many cases, demand sites will connect directly to a
CN, however, they can also connect to DNs. If multiple demand sites are
connected to a single CN (or DN), then the desired demand at each site might
not be the same. The reason demand sites are added to the network is because
they are conceptually distinct from CNs. For example, multiple CNs can connect
to the same demand site in some scenarios allowing the network to select which
CN is needed. In other cases, some DNs might be deployed to also serve as a CN
for some customers. Thus, separating demand sites from CNs allows for more
flexible use-cases.

The sectors within each node, which sit on each of the sites, alternate between
transmitting and receiving in complementary time slots. Polarity assignment is
used to split sectors between transmitting and receiving for a given time slot
(e.g., all odd sectors are transmitting while all even sectors are receiving
and vice versa). Neighbors in the network must have opposite polarity. While a
site can technically have sectors of different polarities (called hardware
hybrid), not a lot of hardware supports this, so polarities are assigned to
sites instead. Software hybrid can subdivide the time slot into two causing a
50% drop in throughput, so this is also not modeled in the planner.

## High-Level Formulation

The planner selects sites and links to optimize the network subject to various
constraints, such as
* Flow balance, i.e., incoming flow equals outgoing flow for each POP/DN/CN
* Incoming flow to each demand site is equal to the desired demand minus the
shortage
* The incoming/outgoing flow from each POP cannot exceed the POP throughput
capacity
* Each link has a maximum throughput capacity which, when scaled by the time
divison multiplexing, bounds the flow on the link
* Connected POP and DN sites must have opposite polarity
* P2MP sector limitations, e.g., a DN sector can connect to at most 2 other DN
sectors and a total of 15 other sectors
* Sectors with LOS can cause interference on other links thereby limiting their
capacity

There are generally two cost function options:

* Minimize cost subject to a coverage constraint. This constraint ensures that
a certain amount of demand in the total network or each individual site is
satisfied (the choice depends on a user-specified configuration).
* Maximize coverage subject to a budget constraint. The coverage objective
either minimizes the total shortage in the network or maximizes the minimum
throughput at each connected demand site (the choice depends on a user-specified
configuration).

The optimization problem is framed as a Mixed Integer Linear Program (ILP)
which is a Linear Program (LP) except some of the variables are restricted to
take integer values. A linear program in canonical form is:

Find $\bf{x}$ that minimizes $\bf{c^Tx}$ subject to $\bf{Ax \geq b}$ and
$\bf{x \geq 0}$. For example, minimize $2x_1+4x_2$ subject to
$x_1+x_2 \geq 3$, $3x_1+2x_2-x_3 \geq 14$, and $x_1,x_2,x_3 \geq 0$ (answer is
$(x_1,x_2,x_3)=(4.6666667,0,0))$. Any general linear programming problem can be
reduced to canonical form. What is critical is that the objective function and
all of the constraints must be linear.

While flow optimization is generally an LP problem, the process of selecting
sites and links makes the problem an ILP. ILP is NP-hard. Thus, they can be
expensive to solve and we generally want to make the problems as small as
reasonably possible.

## Optimization Workflow

The planner avoids making decisions on both sites and links/sectors
simultaneously. It first selects sites and then selects links/sectors. During
the site selection phase, all links and sectors are assumed to be active
provided that the polarity constraints are satisfied (constraints like P2MP or
interference are therefore ignored).

The planner first designs a base mininmum cost network that ensures that the
throughput requirements at the demand sites are met. The coverage percentage is
dynamically determined by starting at 100% and gradually decreasing it until a
feasible solution is found.

After this base minimum cost network is computed, redundancy is added to the
network. There are two approaches in the planner to add redundancy (the choice
depends on a user-specified configuration). The first approach identifies links
that would cause the most disruption in the network if they fail, enforce 0
flow on these links, and then augments the network by maximizing coverage on it
subject to a budget constraint (which is a user-specified configuration). The
second approach augments the network by solve another minimum cost problem but
this time subject to various constraints that ensure it is redundant to various
link or node failures (the exact level of redundancy is a user-specified
configuration).

Once the redundancy phase is complete and the site decisions have been
finalized, the next step selects the links and sectors in order to minimize
interference in the network. Other constraints including P2MP are added to the
problem. To model interference, we estimate the SINR for each link and modify
the link capacity accordingly.

## Network Analysis

During the network analysis/reporting phase of the planner, the optimal flow on
the network is computed. The flow optimization maximizes the minimum throughput
to all of the connected demand sites. In this case, there are no binary/integer
decision variables, so it is an LP.
