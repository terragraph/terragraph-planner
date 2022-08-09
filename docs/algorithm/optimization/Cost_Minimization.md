# Cost Minimization

The planner first designs a base mininmum cost network that ensures that the
throughput requirements at the demand sites are met.

The minimum cost network optimization is part of the site selection phase.
During this phase, all the sectors on a chosen site are assumed to be selected
as well. Likewise, the links are assumed to be selected provided that the
polarity constraints are satisfied. Considerations such as P2MP and link
interference are ignored.

Note: the exact implementation of the objective function and/or constraints in
the code might slightly differ from what is written here, but they should be
equivalent.

## Objective Function

The objective is to minimize the cost of constructing the network.
Sites/sectors that have already been built are excluded.

$$
\min\left (\sum_{i \in \mathcal{S}} {c_i s_i} + \sum_{i \in \mathcal{S}}\sum_{k \in \mathcal{K_i}}{\tilde{c}_{i,k} \sigma_{i,k}} \right)
$$

## Constraints

### Minimum Coverage

The allowed amount of shortage is limited. There are two versions of this
constraint (the choice depends on a user-specified configuration). Given a
coverage ratio $\gamma$, the constraint is either

$$
\sum_{i \in \mathcal{S}_{DEM}} \phi_i \leq (1-\gamma)\sum_{i \in \mathcal{S}_{DEM}} d_i
$$

or

$$
d_i - \phi_i \geq \gamma \min_{j \in \mathcal{S}_{DEM}} d_j\; \; \; \; \; \forall i \in \mathcal{S}_{DEM}
$$

The first version ensures that the total shortage is less than some fraction of
the total demand in the network. The second version ensures that the flow into
each site is at least some fraction of the minimum demand at all of the demand
sites (generally, the demand at all the demand sites is the same). The result
ensures that each demand site receives at least some amount of minimum flow.

> Technically, the second version does not apply to all sites
$i \in \mathcal{S}_{DEM}$ because it might not be possible to send any flow to
some of those demand sites (consider a case where the demand site is
disconnected from all of the POPs). Such demand sites are removed from the
constraint otherwise the constraint could only be satisfied if $\gamma = 0$.
The set of demand sites for which the constraint applies is referred to as the
connected demand sites.

Ideally you would want to solve this for the maximum $\gamma$ possible. Because
that is not easy to determine, during the minimum cost phase, it will start at
$1.0$ and be incrementally decreased until a feasible solution is found.

### Flow Balance

Incoming flow equals to outgoing flow (equivalently, the net flow is 0) for all
POPs, DNs, and CNs.

$$
\sum_{j\in\mathcal{S}:(j,i) \in \mathcal{L}} f_{j,i} - \sum_{j\in\mathcal{S}:(i,j) \in \mathcal{L}} f_{i,j} = 0\; \; \; \; \; \forall i \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}\cup\mathcal{S}_{CN}
$$

For demand sites, the net flow is equal to the demand minus the shortage.

$$
\sum_{j\in\mathcal{S}:(j,i) \in \mathcal{L}} f_{j,i} - \sum_{j\in\mathcal{S}:(i,j) \in \mathcal{L}} f_{i,j} = d_i - \phi_i\; \; \; \; \; \forall i \in \mathcal{S}_{DEM}
$$

### Flow Capacity

The flow on a link is bounded by the capacity of the link multiplied by the
time-division multiplexing on the link.

$$
f_{i,j} \leq \tau_{i,j} t_{i,j}\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$

When $i$ or $j$ is an imaginary site such as the supersource or a demand site,
then $\tau_{i,j}$ is dropped (or equivalently, $\tau_{i,j}=1$). The capacity
for links to the demand sites are some sufficiently large value. The capacity
for links to each of the POPs is the data rate being served to the POP from the
internet backbone.

### Flow Site

The incoming flow to a site is 0 if it is not selected. Due to flow balance
constraints, this ensures the outgoing flow from a site is also 0 in this case.

$$
\sum_{j\in\mathcal{S}:(j,i) \in \mathcal{L}} f_{j,i} \leq M s_i\; \; \; \; \; \forall i \in \mathcal{S}
$$

where $M$ is some large value that exceeds the total possible incoming flow to
a site.

### Time Division Multiplexing

For a given sector, the sum of the fraction of time spent on each incoming or
outgoing link cannot exceed 1. It is also 0 if the sector is not selected.

$$
\sum_{j \in \mathcal{S}:(i,j) \in \mathcal{\Lambda}_{i, k}} \tau_{i,j} \leq \sigma_{i,k}\; \; \; \; \; \forall k \in \mathcal{K_i},i \in \mathcal{S}
$$

$$
\sum_{j \in \mathcal{S}:(j,i) \in \mathcal{\Lambda}_{j, k}} \tau_{j,i} \leq \sigma_{i,k}\; \; \; \; \; \forall k \in \mathcal{K_i},i \in \mathcal{S}
$$


### Polarity

The polarity of connected sites must be opposite. Because there are no link
decisions during this phase, we have to use other variables as a proxy to force
this requirement. In this case, the flow between sites can only be positive if
the polarities are opposite. However, because flow is not bounded by 1, it is
not a good choice. Instead, we can use the time division multiplexing variable
which we only allow to be positive if the polarities are opposite.

$$
\tau_{i,j} \leq p_i + p_j\; \; \; \; \; \forall (i,j) \in \mathcal{L}:i,j \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}
$$
$$
\tau_{i,j} \leq 2 - p_i - p_j\; \; \; \; \; \forall (i,j) \in \mathcal{L}:i,j \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}
$$

This ensures that if $\tau_{i,j} > 0$, then $p_i \neq p_j$.

### Co-Located Sites

For CNs, DNs and/or POPs in the same location, only one may be chosen. There
might be multiple sites of the same type in the same location because their
hardware might be different. This is how the planner makes a decision on the
choice of hardware at a particular location.

We define $G:\mathcal{S} \rightarrow \mathcal{G}$ to be the mapping of a site
$i$ to its location $g$, then

$$
\sum_{i:G(i)=g} {s_i} \leq 1\; \; \; \; \;  \forall g \in \mathcal{G}
$$
