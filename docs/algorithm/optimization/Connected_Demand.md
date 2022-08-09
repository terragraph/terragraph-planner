# Connected Demand Site Optimization

In both [Cost Minimization](Cost_Minimization.md#minimum-coverage),
[Coverage Maximization](Coverage_Maximization.md#objective-function), and
[Interference Minimization](Interference_Minimization.md#objective-function),
we have a version of a constraint or objective function designed to ensure
equal flow is delivered to all of the connected demand sites. The connected
demand sites are a subset of demand sites for which it is possible to send
positive flow under the constraints of the governing optimization problem.

The critical challenge here is incorporating the constraints, such as polarity
or point-to-multipoint. Without the constraints, this problem can be solved by
classic graph algorithms, such as BFS, to find all such demand sites. But with
the constraints, we solve an optimization problem to maximize the number of
demand sites that can receive flow.

## Objective Function

The objective is to maximize the number of demand sites that receive flow. We
will later add constraints that ensure a demand site is selected if it receives
flow and does not get selected otherwise.

$$
\max \sum_{i \in \mathcal{S}_{DEM}} s_i
$$

## Decision Variables

Before introducing the constraints, some of the decision variables differ
slightly from those [provided previously](Notation.md#decision-variables). The
polarity decision variables are unchanged. However, the flow decisions are
slightly different.

The idea of the connected demand site optimization is to send flow from the
supersource and identify which demand sites it is able to reach. We normalize
the problem by limiting each link to a unit of throughput capacity. The actual
capacity of the link is irrelevant as long as it is positive. Thus the unit
flow decision variables are

$f_{i,j,} \in [0, 1]$ : flow through link $(i, j) \in \mathcal{L}$

There is no concept of time division multiplexing, so those decision variables
are not included.

Additionally, there are no site decisions other than the demand sites. Instead,
$s_i$ is just a value based on whether or not it can be selected by the
governing optimization problem.

## Cost Minimization and Coverage Maximization Constraints

### Flow Balance

Incoming flow equals to outgoing flow (equivalently, the new flow is 0) for all
POPs, DNs, and CNs.

$$
\sum_{j\in\mathcal{S}:(j,i) \in \mathcal{L}} f_{j,i} - \sum_{j\in\mathcal{S}:(i,j) \in \mathcal{L}} f_{i,j} = 0\; \; \; \; \; \forall i \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}\cup\mathcal{S}_{CN}
$$

### Flow Capacity

While the capacity of the link is largely ignored, it is important that 0
capacity links do not carry any flow.

$$
f_{i,j} = 0\; \; \; \; \; \forall (i,j) \in \mathcal{L}:t_{i,j}=0
$$

### Flow Site

The incoming flow to a site is 0 if it is not selectable. Due to flow balance
constraints, this ensures the outgoing flow from a site is also 0 in this case.

$$
\sum_{j\in\mathcal{S}:(j,i) \in \mathcal{L}} f_{j,i} = 0\; \; \; \; \; \forall i \in \mathcal{S}:s_i=0
$$

### Polarity

The polarity of connected sites must be opposite. Because there are no link
decisions during this phase, we have to use other variables as a proxy to force
this requirement. In this case, the flow between sites can only be positive if
the polarities are opposite.

$$
f_{i,j} \leq p_i + p_j\; \; \; \; \; \forall (i,j) \in \mathcal{L}:i,j \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}
$$
$$
f_{i,j} \leq 2 - p_i - p_j\; \; \; \; \; \forall (i,j) \in \mathcal{L}:i,j \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}
$$

### Adversarial Links

Only relevant for
[Coverage Maximization](Coverage_Maximization.md#adversarial-links), no flow
is permitted for adversarial links.

$$
f_{i,j} = 0\; \; \; \; \; \forall (i,j) \in \mathcal{L}_{ADV}
$$

### Flow Demand

Demand sites can only be selected if there is non-zero incoming flow.

$$
s_i \leq M \sum_{j\in\mathcal{S}:(j,i) \in \mathcal{L}} f_{j,i}\; \; \; \; \; \forall i \in \mathcal{S}_{DEM}
$$

where $M$ is some large value. While in theory $s_i$ for
$i \in \mathcal{S}_{DEM}$ can be 0 even if the incoming flow is positive, at
the optimum, $s_i=1$ in such cases.

The choice of large value for $M$ must be done with some care. There is a set
of flow decisions such that the flow is equally divided among all connected
demand sites. Since the connected demand sites are a subset of all the demand
sites, there is set of flow decisions such that each connected demand sites has
at least $\frac{1}{\left | \mathcal{S}_{DEM} \right |}$ units of flow. Thus, setting
$M \geq \left | \mathcal{S}_{DEM} \right |$ will work.

## Interference Minimization Constraints

The vast majority of the constraints in
[Interference Minimization](Interference_Minimization.md#constraints) are
identical here. However,
[Interference Constraints](Interference_Minimization.md#interference) are not
applied. Theoretically, in Interference Minimization, the time division
multiplexing decision can be made sufficiently small to virtually eliminate the
impact of interference while still supporting flow over the link. Perhaps this
is not entirely true for a link whose SNR is right at the boundary of a 0
throughput MCS class, but this is ignored. In the worst case, Interference
Minimization will fallback to the $\min\sum_{i \in \mathcal{S}_{DEM}} \phi_i$
objective function if it cannot find a solution where
$\min_{i \in \widehat{\mathcal{S}}_{DEM}} (d_i - \phi_i) > 0$
($\widehat{\mathcal{S}}_{DEM}$ is the set of connected demand sites).

### Flow Link

Because
[Time Division Multiplexing](Interference_Minimization.md#time-division-multiplexing)
decision variables and constraints are not included, we still have to ensure
that there is flow only on selected links.

$$
f_{i,j} \leq \ell_{i,j}\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$
