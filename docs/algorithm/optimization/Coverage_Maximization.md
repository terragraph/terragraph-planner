# Coverage Maximization

There are two methods for adding redundancy to the base minimum cost network.
This approach identifies links that would cause the most disruption in the
network if they fail, enforces zero flow on these links, and then augments the
network by maximizing coverage on it subject to a budget constraint (which is a
user-specified configuration).

The maximum coverage network optimization is part of the site selection phase.
During this phase, all the sectors on a chosen site are assumed to be selected
as well. Likewise, the links are assumed to be selected provided that the
polarity constraints are satisfied. Considerations such as P2MP and link
interference are ignored.

Note: the exact implementation of the objective function and/or constraints in
the code might slightly differ from what is written here, but they should be
equivalent.

## Objective Function

The amount of shortage is minimized. There are two versions of the objective
function (the choice depends on a user-specified configuration).

$$
\min\sum_{i \in \mathcal{S}_{DEM}} \phi_i
$$

if `MAXIMIZE_COMMON_BANDWIDTH` is `False`, or

$$
\max\min_{i \in \mathcal{S}_{DEM}} \left (d_i - \phi_i \right)
$$

if `MAXIMIZE_COMMON_BANDWIDTH` is `True`.

The first version ensures that the total shortage is minimized. The second
version ensures that the minimum flow to each of the demand sites is maximized.

> Technically, the second version does not apply to all sites
$i \in \mathcal{S}_{DEM}$ because it might not be possible to send any flow to
some of those demand sites (consider a case where the demand site is
disconnected from all of the POPs). Such demand sites are removed from the
constraint otherwise the optimal value will be $0$. The set of demand sites for
which the constraint applies is referred to as the connected demand sites.

While the second version is not a linear objective function as written, this
can be addressed by introducing a new decision variable, $\beta$, where
$\beta \leq d_i - \phi_i$ $\forall i \in \mathcal{S}_{DEM}$ and using

$$
\max\beta
$$

as the objective function. While, in theory,
$\beta \leq \min_{i \in \mathcal{S}_{DEM}} \left (d_i - \phi_i \right)$,
at the optimum,
$\beta = \min_{i \in \mathcal{S}_{DEM}} \left (d_i - \phi_i \right)$.

## Constraints

The constraints are identical to those of
[Cost Minimization](Cost_Minimization.md#constraints), except for
[Minimum Coverage](Cost_Minimization.md#minimum-coverage), which does not
apply. However, it adds a few constraints of its own.

### Budget

The cost of constructing the network is limited by a provided budget, $B$ (which is
a user-specified configuration).

$$
\sum_{i \in \mathcal{S}} {c_i s_i} + \sum_{i \in \mathcal{S}}\sum_{k \in \mathcal{K_i}}{\tilde{c}_{i,k} \sigma_{i,k}} \leq B
$$

In this case, because all sectors on a site are selected if the site is
selected (i.e., $\sigma_{i,k}=s_i$), this simplifies to

$$
\sum_{i \in \mathcal{S}}\left (c_i + \sum_{k \in \mathcal{K_i}}{\tilde{c}_{i,k}} \right) s_i \leq B
$$

> A user-specified budget is not necessarily a very user-friendly or
straightforward input. It is also encumbered by a number of other subtle
challenges. Namely, the optimizer has no cost pressure during this phase other
than the upper bound. It can arbitrarily add sites, even those that might not
be necessary to the plan. For example, if there are multiple extra routes to
reach the demand site, the ILP can select just one of them, some of them, or
all of them provided the budget allows. In fact, it is entirely possible that
if budget remains sufficiently high, counterintuitively, lowering the budget
can theoretically result in more sites being selected (we are subject to the
whim of the optimizer, unfortunately). Thus, building sufficient redundancy
without overdoing it becomes a tricky game of setting the budget carefully.
Hence, we recently developed a [new approach](Redundancy_Optimization.md).

### Adversarial Links

A separate process identifies the most critical links in the base minimum cost
network, here referred to as adversarial links. The set of such links is
$\mathcal{L}_{ADV} \subseteq \mathcal{L}$. For such links we do not permit any
flow. Thus, the optimizer must find alternate routes for the flow to serve the
desired demand.

$$
f_{i,j} = 0\; \; \; \; \; \forall (i,j) \in \mathcal{L}_{ADV}
$$
