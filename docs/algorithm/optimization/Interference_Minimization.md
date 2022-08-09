# Interference Minimization

After site selection is complete and finalized, the next step selects the links
and sectors in order to minimize interference in the network. At this stage,
P2MP, deployment, and interference constraints are incorporated into
optimization.

Note: the exact implementation of the objective function and/or constraints in
the code might slightly differ from what is written here, but they should be
equivalent.

## Objective Function

The objective is to minimize the shortage in the network just as in
[Coverage Maximization](Coverage_Maximization#objective-function).

$$
\min\sum_{i \in \mathcal{S}_{DEM}} \phi_i
$$

or

$$
\max\min_{i \in \mathcal{S}_{DEM}} \left (d_i - \phi_i \right)
$$

However, we also want as many additional links to be included as possible in
order to ensure as much redundancy in the network as possible. Otherwise, the
optimizer has no incentive to include links that do not serve to minimize the
shortage. Thus, we also include the term

$$
\sum_{(i,j) \in \mathcal{L}} w_{i,j} \ell_{i, j}
$$

where the weight $w_{i,j}$ is a decreasing function of the link's length. Thus,
the total objective function becomes

$$
\min \left(M \sum_{i \in \mathcal{S}_{DEM}} \phi_i - \sum_{(i,j) \in \mathcal{L}} w_{i,j} \ell_{i, j} \right)
$$

or

$$
\max \left(M \min_{i \in \mathcal{S}_{DEM}} \left (d_i - \phi_i \right) + \sum_{(i,j) \in \mathcal{L}} w_{i,j} \ell_{i, j} \right)
$$

where $M$ is some large value (i.e., some relative weighting between the two
components of the objective function).

## Constraints

Most of the constraints are similar to those before
([Flow Balance](Cost_Minimization.md#flow-balance) and
[Flow Capacity](Cost_Minimization.md#flow-capacity) are unchanged) but with
some slight modifications due to the addition of the link selection decision
variable $\ell_{i,j}$.

### Time Division Multiplexing

In addition to the [Time Division Multiplexing](Cost_Minimization.md#time-division-multiplexing) constraint from before, time division multiplexing on a link is forced to 0 if the link is not selected.

$$
\tau_{i,j} \leq \ell_{i,j}\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$

Due to [Flow Capacity](Cost_Minimization.md#flow-capacity), this automatically
ensures that

$$
f_{i,j} \leq \ell_{i,j} t_{i,j}\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$

### Polarity

The polarity of connected sites must be opposite.

$$
\ell_{i,j} \leq p_i + p_j\; \; \; \; \; \forall (i,j) \in \mathcal{L}:i,j \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}
$$
$$
\ell_{i,j} \leq 2 - p_i - p_j\; \; \; \; \; \forall (i,j) \in \mathcal{L}:i,j \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}
$$

This ensures that if $\ell_{i,j} > 0$, then $p_i \neq p_j$.

### Sector

A sector can only be selected if the site is also selected.

$$
\sigma_{i,k} \leq s_i\; \; \; \; \; \forall k \in \mathcal{K_i},i \in \mathcal{S}
$$

> In this case, $s_i$ is no longer a decision variable but simply a value based
on the site selection decisions of the previous optimization steps.

When a node contains multiple sectors, if one sector in the node is selected,
all sectors in that node are selected. We define $n_k$ to be the node that
contains sector k, then

$$
\sigma_{i, k} = \sigma_{i, l}\; \; \; \; \; \forall k,l \in \mathcal{K_i}:n_k=n_l,i \in \mathcal{S}
$$

A link can only be selected if the sectors it is connected to are also
selected.

$$
\ell_{i, j} \leq \sigma_{i, k}\; \; \; \; \; \forall (i, j) \in \mathcal{L}: (i, j) \in \Lambda_{i, k}
$$

$$
\ell_{i, j} \leq \sigma_{j, \kappa}\; \; \; \; \; \forall (i, j) \in \mathcal{L}: (i, j) \in \Lambda_{j, \kappa}
$$

### Symmetric Link

Backhaul links are bi-directional but are modeled with two separate directed
links. If a link is selected, its reverse must also be selected.

$$
\ell_{i, j} = \ell_{j, i}\; \; \; \; \; \forall (i, j) \in \mathcal{L}: (j, i) \in \mathcal{L}
$$

### Point-to-Multipoint

A DN sector can connect to a limited number of other sectors. The number of
DN-DN connections, $\mathcal{P}_{D}$, and the number of total connections,
$\mathcal{P}_{T}$, are each limited (both are user-specified configurations).

$$
\sum_{j \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}:(i, j) \in \Lambda_{i, k}} \ell_{i, j} \leq \mathcal{P}_{D}\; \; \; \; \; \forall k \in \mathcal{K}_{i},\forall i \in \mathcal{S}
$$

$$
\sum_{j \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}\cup\mathcal{S}_{CN}:(i, j) \in \Lambda_{i, k}} \ell_{i, j} \leq \mathcal{P}_{T}\; \; \; \; \; \forall k \in \mathcal{K}_{i},\forall i \in \mathcal{S}
$$

Generally, $\mathcal{P}_{D} = 2$ and $\mathcal{P}_{T} = 15$.

### CN Link

CNs can only have a single incoming link

$$
\sum_{i \in \mathcal{S}:(i,j) \in \mathcal{L}} \ell_{i, j} \leq 1\; \; \; \; \; \forall j \in \mathcal{S}_{CN}
$$

### Deployment Guidelines

We enforce two deployment guidelines/constraints: for any two links leaving
different sectors on the same site,

- The angle between them must be at least $\alpha$
- The angle between them must be at least $\theta$ if the ratio of their link
distances (larger distance over smaller) is greater than $\rho$.

Typical values are $\alpha = 25$, $\theta = 45$ and $\rho = 3$ (all are
user-specified configurations).

We identify all link pairs $(i, j) \in \mathcal{L}$ and
${(i, k) \in \mathcal{L}}$ that violate these conditions. Define $\mathcal{Q}$
to be the set of all such $\{(i, j),(i,k)\}$ link pairs.

$$
\ell_{i, j} + \ell_{i, k} \leq 1\; \; \; \; \; \forall \{(i, j),(i, k)\} \in \mathcal{Q}
$$

### Interference

In order to incorporate interference into the model, we use the SINR of a link
to determine its MCS class which is then used to modify its capacity. The SINR
is determined based on how much time interference-causing links are
transmitting and how much interference they cause while the interfered-on link
is simultaneously transmitting. All of this is expressed using a linear
function of various decisions variables.

The SINR (in dBm) on link $(i,j)$ is calculated as

$$
SINR_{i,j} = 10\log_{10}\frac{RSL_{i,j}}{N_p + \sum_{(k,l)}{\tau_{k,l}I^{i,j}_{k,l}}}
$$

where $RSL_{i,j}$ is the received signal level for the link $(i, j)$ in mW,
$I^{i,j}_{k,l}$ is the interference caused by the link $(k,l)$ on the link
$(i, j)$ in mW, and $N_p$ is the noise power in mW. In order for the link
$(k, l)$ to cause interference on link $(i, j)$:

- There must be LOS from site $k$ to site $j$
- The receiving sector for link $(i, j)$ must be the same as the receiving
sector for the LOS $(k, j)$
- The transmitting sector for link $(k, l)$ must be the same as the
transmitting sector for the LOS $(k, j)$
- Sites $j$ and $k$ must have opposite polarity.

Time division multiplexing is incorporated into this equation in order to scale
the amount of interference based on how much time the interference-causing link
is actually transmitting. While not precise, for planning purposes, this
hopefully provides a reasonable approximation. For example, it is useful for
removing redundant links from interference considerations.

> $I^{i,j}_{k,l}$ is pre-computed prior to the optimization. An issue with this
is that through transmit power modulation, the links do not necessarily
transmit at full power. However, incorporating this as a decision variable
would greatly complicate this model. Thus, for planning purposes, the
worst-case-scenario of maximum transmit power is assumed.

Unfortunately, as written, the expression for SINR is not linear in the
decision variables. However, define $S_{i,j}=10^\frac{SINR_{i,j}}{10}$
(converting SINR from dBm to mW), then

$$
S^{-1}_{i,j}=\frac{N_p + \sum_{(k,l)}{\tau_{k,l}I^{i,j}_{k,l}}}{RSL_{i,j}}
$$

which is a linear function of the decision variables $\tau_{k,l}$.

Hidden in this is that the polarity decisions are also part of this equation.
Namely, we require that $p_k \neq p_j$. Because polarity decisions are not made
for CNs, it is easier to require that $p_k = p_i$, which is equivalent (if
$p_i = p_j$ then the link $(i, j)$ cannot be selected). We add a decision
variable $\varrho_{k,i} \in \{0,1\}$ which is 1 if sites $k$ and $i$ have the
same polarity and 0 otherwise. Then this expression is really

$$
S^{-1}_{i,j}=\frac{N_p + \sum_{(k,l)}{\tau_{k,l}\varrho_{k,i}I^{i,j}_{k,l}}}{RSL_{i,j}}
$$

This is no longer a linear function of decision variables, but it can be
linearized by introducing a different decision variable
$\chi_{i,k,l} \in [0,1]$ which is $\tau_{k,l}$ if sites $k$ and $i$ have the
same polarity and 0 otherwise. Then this expression becomes

$$
S^{-1}_{i,j}=\frac{N_p + \sum_{(k,l)}{\chi_{i,k,l}I^{i,j}_{k,l}}}{RSL_{i,j}}
$$

In order to ensure that $\chi_{i,k,l}$ has the desired properties, we have the
following constraints

$$
\chi_{i,k,l} \leq 1 + p_i - p_k
$$

$$
\chi_{i,k,l} \leq 1 - p_i + p_k
$$

$$
\chi_{i,k,l} \leq \tau_{k,l}
$$

$$
\chi_{i,k,l} \geq \tau_{k,l} + p_i + p_k - 2
$$

$$
\chi_{i,k,l} \geq \tau_{k,l} - p_i - p_k
$$

Thus, if $p_i=p_k$, then these constraints become $\chi_{i,k,l} \leq 1$,
$\chi_{i,k,l} \leq \tau_{k,l}$, $\chi_{i,k,l} \geq \tau_{k,l}$, and
$\chi_{i,k,l} \geq \tau_{k,l} - 2$. This is only satisfied if
$\chi_{i,k,l} = \tau_{k,l}$. If $p_i \neq p_k$, then these constraints become
$\chi_{i,k,l} \leq 2$, $\chi_{i,k,l} \leq 0$,$\chi_{i,k,l} \leq \tau_{k,l}$,
$\chi_{i,k,l} \geq \tau_{k,l} - 1$. This is only satisfied if $\chi_{i,k,l}=0$.

Now that $S^{-1}_{i,j}$ is a linear function of decision variables, it has to
be mapped to the modified link capacity based on the MCS class. Using a sample
MCS table, we add an extra column which is $S^{-1}$.

| **MCS** | **SINR (dBm)** | **Throughput (Mbps)** | **SINR Inverse (1/mW)** |
| :-----: | :------------: | :-------------------: | :---------------------: |
| 3       | 3              | 0                     | 0.501                   |
| 4       | 4.5            | 67.5                  | 0.355                   |
| 5       | 5              | 115                   | 0.316                   |
| 6       | 5.5            | 260                   | 0.282                   |
| 7       | 7.5            | 452.5                 | 0.178                   |
| 8       | 9              | 645                   | 0.126                   |
| 9       | 12             | 741.25                | 0.063                   |
| 10      | 14             | 1030                  | 0.040                   |
| 11      | 16             | 1415                  | 0.025                   |
| 12      | 18             | 1800                  | 0.016                   |

Create a decision variable for each MCS class for each link,
$\mu_{i,j,m} \in \{0,1\}$ which 1 if link $(i,j)$ is in MCS class $m$. Assume
there are $\mathcal{M}$ such MCS classes (here, the classes are
$m \in \{1,\ldots,\mathcal{M}\}$ even if the MCS class itself has a different
number, e.g., $m=1$ refers to MCS class 3). A link can only belong to one MCS
class.

$$
\sum^{\mathcal{M}}_{m=1} \mu_{i,j,m} \leq 1\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$

Denote $\vartheta_m$ and $\upsilon_m$ to be the throughput and SINR Inverse
corresponding to MCS class $m$. If $S^{-1}_{i,j} \leq \upsilon_\mathcal{M}$,
then $\mu_{i,j,\mathcal{M}}=1$. If
$\upsilon_\mathcal{M} < S^{-1}_{i,j} \leq \upsilon_\mathcal{M-1}$, then
$\mu_{i,j,\mathcal{M-1}}=1$. Continuing to the end, if
$\upsilon_3 < S^{-1}_{i,j} \leq \upsilon_2$, then $\mu_{i,j,2}=1$ and finally,
$\upsilon_2 < S^{-1}_{i,j} \leq M$ where M is some appropriately large value,
$\mu_{i,j,1}=1$. For this final constraint, we use $M$ instead of $\upsilon_1$
because links with $S^{-1}_{i,j} > \upsilon_1$ still belong to class 1. In the
example above, this is equivalent to saying that links with SINR less than 3
dBm are in MCS class 3. As a single constraint, this is

$$
S^{-1}_{i,j} \leq M \mu_{i,j,1} + \sum^{\mathcal{M}}_{m=2} \mu_{i,j,m} \upsilon_m\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$

Although $S^{-1}_{i,j}$ is not bounded on both sides, we know that the
optimization will try to maximize the throughput so at optimum it will not
choose an MCS class lower than necessary provided it does not violate the SINR
Inverse constraint. In the example above, this is equivalent to saying that a
link with, e.g., SINR of 15 dBm can be of MCS class up to 10. If 1030 Mbps of
throughput is needed for that link, the optimizer will select MCS 10. If only
400 Mbps of throughput is needed, the optimizer will select MCS 7-10, but
between those options, the actual decision is irrelevant.

Finally, the flow is bounded by the appropriate throughput

$$
f_{i,j} \leq \sum^{\mathcal{M}}_{m=1} \mu_{i,j,m} \vartheta_m\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$

> Technically the bound on the flow should also be scaled by $\tau_{i,j}$, but
this would make the constraint quadratic and linearizing it would make the size
of the optimization problem significantly larger, so it is omitted here. The
scaling is still done in the
[Flow Capacity](Cost_Minimization.md#flow-capacity) constraints but omitting it
means the flow on the link can be larger than it technically should be. While
this is not ideal, by minimizing interference, the optimizer can limit the
severity of this omission. The judgement being made here is that the scaling
would hopefully not impact the overall network plan significantly enough to
warrant its inclusion.

## Multi-Channel Constraints

For networks that can support it, enabling multi-channel can reduce the amount
of interference and improve overall network performance. The assumption is that
links on different channels do not interfere with each other. Thus if link
$(k, l)$ is causing a lot of interference on link $(i, j)$, the optimizer can
put those links on different channels to remove the interference.

Critically, we do not currently model link capacity differences between the
channels. We use a single driving frequency and derive the link capacities and
interference from that. A future improvement would be to address this
shortcoming. However, because of this, the channel selected by the optimizer
has an arbitrary association with the actual channel number. Some
post-processing might involve assigning the most commonly selected channel to
the one with the best real-world performance.

There are two constraints that are impacted by multi-channel planning. The
first is [Deployment Guidelines](#deployment-guidelines) and the second is
[Interference](#interference). That is, links on different channels do not
violate deployment guidelines and do not cause interference on each other.

Formally, the channel decision is associated with each sector. However, instead
of having several channel decisions for each sector, the sector decisions
themselves are slightly modified. Whereas before we had $\sigma_{i,k}$ decision
variables, we now have $\sigma_{i,k,c}$ for $c \in \{1,\ldots,C\}$. That is,
there are now $C$ sector decisions for each physical sector, with each one
corresponding to a sector on a particular channel. This is not the case for CN
sectors which automatically take on the channel of the serving DN and therefore
do not need additional decision variables.

### Multi-Channel Sector

Sectors can only have one channel.

$$
\sum^{C}_{c=1} \sigma_{i,k,c} \leq 1 \; \; \; \; \; \forall k \in \mathcal{K}_{i}, i \in \mathcal{S}
$$

Some of the other sector constraints are also modified. A sector can only be
selected if the site is also selected

$$
\sum^{C}_{c=1} \sigma_{i,k,c} \leq s_i\; \; \; \; \; \forall k \in \mathcal{K_i},i \in \mathcal{S}
$$

When a node contains multiple sectors, if one sector in the node is selected,
all sectors in that node are selected.

$$
\sum^{C}_{c=1} \sigma_{i,k,c} = \sum^{C}_{c=1} \sigma_{i,l,c}\; \; \; \; \; \forall k,l \in \mathcal{K_i}:n_k=n_l,i \in \mathcal{S}
$$

A link can only be selected if the sectors it is connected to are also
selected.

$$
\ell_{i, j} \leq \sum^{C}_{c=1} \sigma_{i,k,c}\; \; \; \; \; \forall (i, j) \in \mathcal{L}: (i, j) \in \Lambda_{i, k}
$$

$$
\ell_{i, j} \leq \sum^{C}_{c=1} \sigma_{j,\kappa,c}\; \; \; \; \; \forall (i, j) \in \mathcal{L}: (i, j) \in \Lambda_{j, \kappa}
$$

For multi-channel, an additional constraint requires that the two sectors
connecting the link must have the same channel. This additional constraint is
not required if the receiving site is a CN.

$$
\ell_{i,j} \leq \sigma_{i,k,c} - \sigma_{j,\kappa,c} + 1\; \; \; \; \; \forall (i, j) \in \mathcal{L}: (i, j) \in \Lambda_{i, k}\cap \Lambda_{j, \kappa}, \forall c \in \{1,\ldots,C\}
$$

$$
\ell_{i,j} \leq \sigma_{j,\kappa,c} - \sigma_{i,k,c} + 1\; \; \; \; \; \forall (i, j) \in \mathcal{L}: (i, j) \in \Lambda_{i, k}\cap \Lambda_{j, \kappa}, \forall c \in \{1,\ldots,C\}
$$

Thus, if $\sigma_{i,k}$ and $\sigma_{j,\kappa}$ are on the same channel, then
these constraints become $\ell_{i,j} \leq 1$. If they are on different
channels, then for some channel, the one of the constraints becomes
$\ell_{i,j} \leq 0$.

### Multi-Channel Deployment Guidelines

The deployment guidelines/constraints only apply if the two sectors that the
links are leaving from are on the same channel. If they are on different
channels, then the constraint does not apply. To model this, we introduce
binary decision variables, we will call them deployment links,
$\zeta_{i,j,c} \in \{0,1\}$ for all the links in $\mathcal{\overline{Q}}$ which
is 1 if link $\ell_{i,j}$ is on channel $c$. $\mathcal{\overline{Q}}$ is the
"flattened" version of $\mathcal{Q}$ containing each link of all link pairs
separately and it should be much smaller than $\mathcal{L}$, so we do not need
to do this for all links.

A deployment link can only be selected if its corresponding link is selected.

$$
\zeta_{i,j,c} \leq \ell_{i,j}\; \; \; \; \; \forall (i, j) \in \mathcal{\overline{Q}}, \forall c \in \{1,\ldots,C\}
$$

Furthermore, the deployment link is connected to a sector of the same channel.

$$
\zeta_{i,j,c} \leq \sigma_{i,k,c}\; \; \; \; \; \forall (i, j) \in \mathcal{\overline{Q}}: (i, j) \in \Lambda_{i, k}, \forall c \in \{1,\ldots,C\}
$$

$$
\zeta_{i,j,c} \leq \sigma_{j,\kappa,c}\; \; \; \; \; \forall (i, j) \in \mathcal{\overline{Q}}: (i, j) \in \Lambda_{j, \kappa},  \forall c \in \{1,\ldots,C\}
$$

If the receiving site is a CN, the last constraint is slightly modified because
there are no channel decisions on CNs.

$$
\zeta_{i,j,c} \leq \sigma_{j,\kappa}\; \; \; \; \; \forall (i, j) \in \mathcal{\overline{Q}}: (i, j) \in \Lambda_{j, \kappa},  \forall c \in \{1,\ldots,C\}
$$

However, the deployment link must be selected if the link is selected and both
sectors on a particular channel are selected.

$$
\zeta_{i,j,c} \geq \ell_{i,j} + \sigma_{i,k,c} + \sigma_{j,\kappa,c} - 2\; \; \; \; \; \forall (i, j) \in \mathcal{\overline{Q}}: (i, j) \in \Lambda_{i, k}\cap \Lambda_{j, \kappa}, \forall c \in \{1,\ldots,C\}
$$

Finally, the deployment guidelines constraint becomes

$$
\zeta_{i,j,c} + \zeta_{i,k,c} \leq 1\; \; \; \; \; \forall \{(i, j),(i, k)\} \in \mathcal{Q}, \forall c \in \{1,\ldots,C\}
$$

### Multi-Channel Time Division Multiplexing

In order to model multi-channel interference, we need to modify the time
division multiplexing decision variable to incorporate channels. Whereas before
we had $\tau_{i,j}$ decision variables, we now have $\tau_{i,j,c}$ for
$c \in \{1,\ldots,C\}$.

Before dissecting the interference constraints, we first see how it modifies
some of the other time division multiplexing constraints.

The sum of the time division multiplexing decision on each sector does not
change much.

$$
\sum_{j \in \mathcal{S}:(i,j) \in \mathcal{\Lambda}_{i, k}} \tau_{i,j,c} \leq \sigma_{i,k,c}\; \; \; \; \; \forall k \in \mathcal{K_i},i \in \mathcal{S}, \forall c \in \{1,\ldots,C\}
$$

$$
\sum_{j \in \mathcal{S}:(j,i) \in \mathcal{\Lambda}_{j, k}} \tau_{j,i,c} \leq \sigma_{i,k,c}\; \; \; \; \; \forall k \in \mathcal{K_i},i \in \mathcal{S}, \forall c \in \{1,\ldots,C\}
$$

This also ensures that the time division multiplexing decision is 0 on channels
that are not selected.

Flow capacity has to be updated

$$
f_{i,j} \leq \sum^{C}_{c=1} \tau_{i,j,c} t_{i,j}\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$

as does the constraint that time division multiplexing is 0 if the link is not
selected

$$
\sum^{C}_{c=1} \tau_{i,j,c} \leq \ell_{i,j}\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$

### Multi-Channel Interference

Due to the change in the time division multiplexing decision variable,
$\chi_{i,k,l}$ becomes $\chi_{i,k,l,c}$ for $c \in \{1,\ldots,C\}$. Then, we
have

$$
S^{-1}_{i,j,c}=\frac{N_p + \sum_{(k,l)}{\chi_{i,k,l,c}I^{i,j}_{k,l}}}{RSL_{i,j}}
$$

Critically, this is done for each channel separately. Thus, if all links
$(k, l)$ are communicating on a different channel than $(i, j)$,
$\sum_{(k,l)}{\chi_{i,k,l,c}I^{i,j}_{k,l}} = 0$ because the time division
multiplexing decision variable will be 0.

The remaining MCS class decision variable, $\mu_{i,j,m}$ becomes
$\mu_{i,j,c,m}$ for $c \in \{1,\ldots,C\}$. Then we have

$$
\sum^{\mathcal{M}}_{m=1} \mu_{i,j,c,m} \leq 1\; \; \; \; \; \forall (i,j) \in \mathcal{L}, \forall c \in \{1,\ldots,C\}
$$

and

$$
S^{-1}_{i,j,c} \leq M \mu_{i,j,c,1} + \sum^{\mathcal{M}}_{m=2} \mu_{i,j,c,m} \upsilon_m\; \; \; \; \; \forall (i,j) \in \mathcal{L}, \forall c \in \{1,\ldots,C\}
$$

Additionally, we have to enforce that the chosen MCS class has positive
capacity for only one of the channels.

$$
\sum^{C}_{c=1} \mu_{i,j,c,1} \geq C - 1\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$

With this, the flow is bounded by the appropriate throughput

$$
f_{i,j} \leq \sum^{C}_{c=1} \sum^{\mathcal{M}}_{m=1} \mu_{i,j,c,m} \vartheta_m\; \; \; \; \; \forall (i,j) \in \mathcal{L}
$$

> Like before, technically the bound on the flow should also be scaled by
$\tau_{i,j,c}$, but for the same reason, it is omitted here.

Here, we must also ensure that the time division multiplexing decision
corresponds to the channel that has positive capacity. Without this, say
channel 0 has positive capacity and channel 1 has zero capacity: the flow is
bounded by the capacity of the positive capacity channel independent of the
time division multiplexing (and channel) decision itself. Thus, the optimizer
could choose sector/link channel 1 but still have positive flow across the
link.

$$
\tau_{i,j,c} \leq 1 - \mu_{i,j,c,1}\; \; \; \; \; \forall (i,j) \in \mathcal{L}, \forall c \in \{1,\ldots,C\}
$$
