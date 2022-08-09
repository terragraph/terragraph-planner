# Flow Optimization

Once a network design is complete, we compute the optimal flow in the network
for analysis and reporting. One of the key differences between this stage and
the planning stage is that the link capacities are now updated based on the
interference from selected links.

This presents a challenge: we do not know ahead of time which links will
actually carry flow and what their time division multiplexing will be. Thus, we
need to solve for the optimal flow in order to get these values, but we need
these values to solve for the optimal flow. Instead, for analysis purposes, we
simply assume uniform time division multiplexing when computing interference.
This, of course, can greatly overstate the amount of interference if, for
example, highly interfering links are included in the network primarily for
redundancy purposes. Therefore, the analysis needs to be understood in this
context.

Furthermore, the traffic in the network is routed based on, e.g., shortest
path, deterministic prefix allocation, etc. The planning phase does not
incorporate the routing but, if we are provided a routing during analysis, we
at least know which links are not used. If the routing is provided, those links
are removed from the interference calculations (the assumption is that links
used for the purpose of redundancy do not cause interference).

Finally, the analysis is a static view of the network. It assumes every
connectable subscriber purchases service and is maxing out their service. This
is obviously highly unrealistic. Therefore, the analysis should not be viewed
as a perfect reflection of reality, but rather a useful tool in comparing
network plans.

The network flow optimization does not make any decisions on sites, sectors,
links or polarity because the network has already been designed. As a result,
there are no binary/integer decision variables, so the problem is an LP rather
than ILP.

Note: the exact implementation of the objective function and/or constraints in
the code might slightly differ from what is written here, but they should be
equivalent.

## Objective Function

The minimum flow to each connected demand site is maximized.

$$
\max\beta
$$

where $\beta > 0$ is a decision variable representing the amount of flow each
connected demand site receives. A demand site is connected if there exists at
least one non-zero capacity path of active links from an active POP to that
demand site. If such a restriction to connected demand sites was not made, then
the optimal value for $\beta=0$.

> Unlike in [Connected Demand Site Optimization](Connected_Demand.md), finding
the connected demand sites in this case can be done using a classic graph
algorithm like BFS. The Flow Optimization constraints do not necessitate
solving another optimization problem.

Unlike the second version of the objective function in
[Coverage Maximization](Coverage_Maximization.md#objective-function), Flow
Optimization does not have a concept of shortage. Thus, it is possible that
each connected demand site gets service in excess of its requested demand.

## Constraints

The [Flow Capacity](Cost_Minimization.md#flow-capacity) constraints are
identical to those before. However, in addition, only active, non-redundant
links can carry flow. Otherwise, $f_{i,j}=0$. The
[Flow Site](Cost_Minimization.md#flow-site) and [Time Division Multiplexing](Cost_Minimization#time-division-multiplexing) constraints are unchanged.

### Flow Balance

Incoming flow equals to outgoing flow (equivalently, the net flow is 0) for all
POPs, DNs, and CNs.

$$
\sum_{j\in\mathcal{S}:(j,i) \in \mathcal{L}} f_{j,i} - \sum_{j\in\mathcal{S}:(i,j) \in \mathcal{L}} f_{i,j} = 0\; \; \; \; \; \forall i \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}\cup\mathcal{S}_{CN}
$$

For connected demand sites, the net flow is equal to $\beta$

$$
\sum_{j\in\mathcal{S}:(j,i) \in \mathcal{L}} f_{j,i} - \sum_{j\in\mathcal{S}:(i,j) \in \mathcal{L}} f_{i,j} = \beta\; \; \; \; \; \forall i \in \widehat{\mathcal{S}}_{DEM}
$$

and

$$
\sum_{j\in\mathcal{S}:(j,i) \in \mathcal{L}} f_{j,i} - \sum_{j\in\mathcal{S}:(i,j) \in \mathcal{L}} f_{i,j} = 0\; \; \; \; \; \forall i \in \mathcal{S}_{DEM} \setminus \widehat{\mathcal{S}}_{DEM}
$$

where $\widehat{\mathcal{S}}_{DEM}$ is the set of connected demand sites.
