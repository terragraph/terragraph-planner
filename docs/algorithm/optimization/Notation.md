# Notation

## Parameters

The following notation will be used throughout the mathematical descriptions
of each of the ILPs.

$\mathcal{S}$: set of sites

$\mathcal{S}_{POP}$: set of POPs

$\mathcal{S}_{DN}$: set of DNs

$\mathcal{S}_{CN}$: set of CNs

$\mathcal{S}_{DEM}$: set of demand sites

$\mathcal{G}$: set of geographic locations for all the sites (some sites might
have the same location)

$\mathcal{K}_{i}$: set of candidate sectors on site $i \in \mathcal{S}$

$\mathcal{L}$: set of links between sites

$\mathcal{\Lambda}_{i, k}$: set of links connected to sector
$k \in \mathcal{K_i}$ on site $i \in \mathcal{S}$

$c_i$: cost of site $i$ (e.g., installation and other costs indepdendent of
hardware)

$\tilde{c}_{i,k}$: cost of sector $k$ on site $i$ (for nodes with multiple
sectors, the node cost will only be counted once)

$d_i$: amount of demand at site $i \in \mathcal{S}_{DEM}$

$t_{i,j}$: throughput capacity of link $(i, j) \in \mathcal{L}$

## Decision Variables

The following notation will be used for for the various decision variables in
the ILPs.

$s_i \in \{0,1\}$: binary selection decision for site ${i} \in \mathcal{S}$

$\sigma_{i,k} \in \{0,1\}$: binary selection decision for sector
${k} \in \mathcal{K_i}$

$\ell_{i,j} \in \{0,1\}$: binary selection decision for link
$(i, j) \in \mathcal{L}$

$p_i \in \{0,1\}$: binary polarity (e.g., odd) decision for site
${i} \in \mathcal{S}_{POP}\cup\mathcal{S}_{DN}$

$f_{i,j} \in [0, t_{i,j}]$ : flow through link $(i, j) \in \mathcal{L}$

$\tau_{i, j} \in [0, 1]$: time division multiplexing for link
$(i, j) \in \mathcal{L}$

$\phi_i \in [0, d_i]$: amount of unsatisfied demand (or shortage) for demand
site ${i} \in \mathcal{S}_{DEM}$
