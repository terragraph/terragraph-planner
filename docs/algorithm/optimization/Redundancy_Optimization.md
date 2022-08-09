# Cost Minimization with Redundancy

Due to some [shortcomings](Coverage_Maximization.md#budget) in the formulation
for redundancy using coverage maximization, we developed a new approach
relatively recently. This approach enforces particular constraints in the
optimization to ensure a desired level of redundancy while minimizing the
network cost. The result is a network that is redundant to various link and/or
site failures and is no more expensive than it needs to be.

The minimum cost with redundancy optimization is part of the site selection
phase. During this phase, all the sectors on a chosen site are assumed to be
selected as well. Likewise, the links are assumed to be selected provided that
the polarity constraints are satisfied. Considerations such as P2MP and link
interference are ignored.

Note: the exact implementation of the objective function and/or constraints in
the code might slightly differ from what is written here, but they should be
equivalent.

## Objective Function

The objective is to minimize the cost of constructing the network just as in
[Cost Minimization](Cost_Minimization.md#objective-function).

$$
\min \sum_{i \in \mathcal{S}}\left (c_i + \sum_{k \in \mathcal{K_i}}{\tilde{c}_{i,k}} \right) s_i
$$

## Decision Variables

Before introducing the redundancy constraints, some of the decision variables
in the problem differ slightly from those
[provided previously](Notation.md#decision-variables). The site and polarity
decision variables are unchanged. However, the flow decisions are quite
different.

The idea of the redundancy constraints is to ensure a certain number of site-
or link-disjoint paths between the POPs and the proposed DNs in the base
minimum cost network. It's easiest to understand this through some concrete
examples.

Consider a single DN in a base minimum cost network with multiple POPs. This
will serve as the sink node and will be referred to as such. Let's say each POP
in the network provides 2 units of flow and the sink node requires 2 units of
incoming flow. Assume each link in the network supports at most 1 unit of flow.
If you optimize the network under these constraints (as well as standard
constraints such as flow balance), the resulting network will have two
link-disjoint paths from the POPs to the DN (the two paths may or may not share
the same POP). To verify this, if the two paths did share a link, that link
would restrict the flow to just 1 unit and thus the sink node would only
receive 1 unit of flow. This would fail to satisfy the constraint.

Because there are two link-disjoint paths from the POPs to the sink node, the
resulting network is resilient to any single link failure. If instead of
applying this to not just a single DN sink node, we expand it to all of the DNs
in the base minimum cost network simultaneously but independently, the
resulting network will have two link-disjoint paths from the POPs to each DN.

The constraints themselves can be modified to enforce even more redundancy in
the network. If each POP in the network provides 1 unit of flow, the sink nodes
require 2 units of flow, but the sum of the incoming flow to any non-sink node
DN is restricted to just 1 unit of flow, the result is a network that is
resilient to any single site (POP or DN) failure. If each POP in the network
provides 2 units of flow, the sink nodes require 4 units of flow, but the sum
of the incoming flow to any non-sink node DN is restricted to just 1 unit of
flow, the result is a network that is resilient to a simultaneous POP and DN
failure or 3 simultaneous DN failures. So, by just modifying these parameters,
various levels of redundancy can be achieved. In fact, the three levels
described here and in the previous paragraphs are what we currently call low,
medium and high levels of redundancy.

Thus, there are three parameters that control the redundancy constraints: POP
capacity, $\mathcal{C}_{POP}$, DN capacity, $\mathcal{C}_{DN}$ and sink
capacity, $\mathcal{C}_{SINK}$.

Because these problems are being solved simultaneously but independently, we
need flow decisions for each DN in the base minimum cost network. The new
decision variables are

$f_{i,j,\delta} \in [0, 1]$ : flow through link $(i, j) \in \mathcal{L}_{B}$
for a given $\delta \in \Delta$

where $\mathcal{L}_{B}$ is the set of backhaul links (in the entire candidate
network) and $\Delta$ is the set of DNs in the base minimum cost network.
Actually, the upper-bound of the flow for the links from the supersource is
$\mathcal{C}_{POP}$, but it is $1$ for all other links.

> The actual link capacity is not incorporated in this model. Extra sites and
links are added without consideration for the potential throughput when traffic
has to be re-routed due to site or link failures. Generally, it is best to
simply omit low-capacity/low-MCS links, particularly in backhaul, from the
candidate graph.

## Redundancy Constraints

### Flow Site

The incoming flow to a site is 0 if it is not selected. The maximum total
incoming flow $\mathcal{C}_i$ to a site is $\mathcal{C}_{POP}$ for POPs,
$\mathcal{C}_{DN}$ for DNs, and $\mathcal{C}_{SINK}$ for DN sinks.

$$
\sum_{j\in\mathcal{S}_{B}:(j,i) \in \mathcal{L}_{B}} f_{j,i,\delta} \leq \mathcal{C}_i s_i\; \; \; \; \; \forall i \in \mathcal{S}_{B},\forall \delta \in \Delta
$$

where $\mathcal{S}_{B}$ is the set of backhaul sites (in the entire candidate
network).

### Flow Balance

Incoming flow equals to outgoing flow (equivalently, the net flow is 0) for all
POPs and non-sink node DNs

$$
\sum_{j\in\mathcal{S}_{B}:(j,i) \in \mathcal{L}_{B}} f_{j,i,\delta} - \sum_{j\in\mathcal{S}_{B}:(i,j) \in \mathcal{L}_{B}} f_{i,j,\delta} = 0\; \; \; \; \; \forall i \in \mathcal{S}_{B} \setminus \delta,\forall \delta \in \Delta
$$

For sink node DNs, the net flow is equal to $\mathcal{C}_{SINK}$.

$$
\sum_{j\in\mathcal{S}_{B}:(j,\delta) \in \mathcal{L}_{B}} f_{j,\delta,\delta} - \sum_{j\in\mathcal{S}_{B}:(\delta,j) \in \mathcal{L}_{B}} f_{\delta,j,\delta} = \mathcal{C}_{SINK}\; \; \; \; \; \forall \delta \in \Delta
$$

### Polarity

The polarity of connected sites must be opposite. Because there are no link
decisions during this phase, we have to use other variables as a proxy to force
this requirement. In this case, the flow, which is bounded by 1, between sites
can only be positive if the polarities are opposite.

$$
f_{i,j,\delta} \leq p_i + p_j\; \; \; \; \; \forall (i,j) \in \mathcal{L}_{B}:i,j \in \mathcal{S}_{B},\forall \delta \in \Delta
$$

$$
f_{i,j,\delta} \leq 2 - p_i - p_j\; \; \; \; \; \forall (i,j) \in \mathcal{L}_{B}:i,j \in \mathcal{S}_{B},\forall \delta \in \Delta
$$

## Two Phase Solution

Depending on the candidate network, it might not be possible to satisfy the
flow balance constraints perfectly. Hence, we actually solve this problem in
two phases. In the first phase, we try to relax the flow balance constraints as
little as possible and then, using that result, modify the constraints and
minimize the network cost.

### Flow Balance with Shortage

Define a decision variable $\varphi_\delta \in [0, \mathcal{C}_{SINK}]$ to be
the unsatisfied flow for sink node DN $\delta \in \Delta$. Then, the net flow
is equal to $\mathcal{C}_{SINK} - \varphi_\delta$.

$$
\sum_{j\in\mathcal{S}_{B}:(j,\delta) \in \mathcal{L}_{B}} f_{j,\delta,\delta} - \sum_{j\in\mathcal{S}_{B}:(\delta,j) \in \mathcal{L}_{B}} f_{\delta,j,\delta} = \mathcal{C}_{SINK} - \varphi_\delta\; \; \; \; \; \forall \delta \in \Delta
$$

### Relaxed Redundancy Objective Function

During the first phase, the amount of shortage is minimized.

$$
\min\sum_{\delta \in \Delta} \varphi_\delta
$$

Once the shortage is minimized, the optimal shortage decisions become fixed
values in the flow balance with shortage constraint for the second phase. In
the second phase, the network cost is minimized.

## Heuristic Acceleration

Because we are solving a network flow problem for each of the DNs in the base
minimum cost network simultaneously, the resultant ILP is quite large. Even for
modest size problems, the ILP is large enough that a solution is rarely found
within a reasonable time even when running multi-threaded. What is clear is
that the scaling for this redundancy formulation is a serious issue.

To address this, we added a heuristic that would greatly reduce the size of the
underlying candidate graph. The ILP size is most seriously impacted by the
number of links in the candidate graph. If we could reasonably prune links that
are highly unlikely to be part of the final solution, then the ILP size will be
greatly reduced.

The approach is to use a bunch of maximum flow calculations between various
sources and sinks to identify the most useful links. More specifically, by
splitting each site into a site with the incoming links and a site with the
outgoing links and a single link of unit capacity between them, maximum flow
provides site-disjoint paths between the source and the sink. The number
of such paths is the capacity of the source. And most importantly, maximum flow
problems can be solved in polynomial time.

In the heuristic, we added two rounds of maximum flow calculations. The first
is between each POP and each DN in the base minimum cost network. The second is
between each of the DNs in the base minimum cost network. Any link that appears
in the maximum flow output is added to the set of candidate links for the ILP.
Any link that does not is pruned away. In the planner, we request 4
site-disjoint paths between each POP and each DN and we request 2 site-disjoint
paths between each of the DNs. From our experimentation, this appears to be
sufficient even if the user requests a high level of redundancy. In our test
cases, no additional shortage was added and the number of additional DNs was
nearly the same, i.e., optimality was not compromised either.

The heuristic was a major improvement. After applying it, all the ILPs could be
solved by a single thread within an hour and usually within a few minutes or
better. The ILP sizes themselves were reduced by an order of magnitude in each
of the number of variables and number of constraints. For example, one problem
was reduced from 660k x 320k to 65k x 30k. Another was reduced from 6.2M x 2.9M
to 830k x 380k.

### Delaunay Acceleration

Even with this acceleration, moderately large problems could still be too
expensive. While the modest size problems would compute the heuristic in a few
minutes or less, the larger ones could take 30 minutes or more. The bottleneck
was all the maximum flow calculations between each of the DNs. Not only does
this scale quadratically in the number of proposed DNs in the base minimum cost
network, for large networks each maximum flow calculation itself becomes much
more expensive.

One more additional heuristic is applied. A Delaunay triangulation is done
among the DNs using their geographic locations. Then, the maximum flow
calculations are performed only between DNs that are within one or two hops in
the triangulation. The general idea is that if nearby DNs have multiple
disjoint paths, far away DNs will as well. Two hops are included to help
account for polarity constraints which are not accounted for in the maximum
flow calculations.

This additional acceleration significantly improved the heuristic computation
time. The case that previously took 30 minutes now took just 8 (and the ILP
size drops too). Once again, in our test cases, no additional shortage was
added, and optimality was not compromised.
