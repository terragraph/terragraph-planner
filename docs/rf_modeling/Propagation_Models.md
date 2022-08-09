# Propagation Models

## FSPL

The fundamental propagation loss occurring between the Tx and Rx antenna is
modeled using the standard Free-space Pathloss (FSPL) and Gaseous Absorption
Loss (GAL). In a line-of-sight radio system, losses are mainly due to free-space
path loss (FSPL). FSPL is proportional to the square of the distance between
the transmitter and receiver (spreading loss) as well as the square of the
frequency of the radio signal (absorption loss).

$$
FSPL_{dB} = 20\log{d} + 20\log{f} + 92.45
$$

where $d$ is distance in km and $f$ is frequency in GHz.

## GAL

The Gaseous Absorption Loss models the oxygen absorption loss given by the
following equation:

$$
GAL(f_{c}) = \alpha(f_{c})d/1000
$$

where,
- $\alpha(f_{c})$ is frequency dependent oxygen loss [dB/km] characterized
in Table 7.6.1-1 in [ETSI TR 138 901 V14.0.0](https://www.etsi.org/deliver/etsi_tr/138900_138999/138901/14.00.00_60/tr_138901v140000p.pdf),
which is shown below.
- d is the distance in meters.

<p align="center">
    <img src="../figures/rf-freq-dependent-oxygen-loss-table.png" />
</p>
<p align="center">
    <em>Figure 6: Frequency dependent oxygen loss</em>
</p>

## Rain Loss

Rain loss is an important factor in the link level network planning as it
affects the overall network availability. It is modeled and included i4n
the Terragraph Planner in the following method:

- Get the value of rain-rate (as $R_{0.01}$) from user. This typically ranges
  from 0 - 120 mm/hr
- Calculate rain attenuation in dB/km using the following constant values:

$$
k = 0.8515, \alpha = 0.7486, \gamma_{R} = kR_{0.01}\alpha
$$

where,
- $\gamma_{R}$ (in dB/km) is multiplied by distance d to get the attenuation
  $A_{0.01}$ [dB] using:
  $$
  A_{0.01} = \gamma_{R}d
  $$
- $A_{0.01}$ is used in the link budget calculations in
  [Link Budget Calculations](Link_Budget_Calculations.md)

  If a certain link availability is provided by the user (say $p_{i}$, in range
99.9 - 99.999), then $A_{0.01}$ is adjusted to $A_{p}$ using the following set
of equations:
$$
r = \frac{1}{0.477d^{0.633}R^{0.073\alpha}_{0.01}f^{0.123}-10.579(1-\exp{(0.024d)})} \\
$$
$$
A_{0.01} = \gamma_{R}dr \\
$$
$$
\frac{A_{p}}{A_{0.01}} = C_{1}p^{-(C_{2}+C_{3}\log_{10}{p})}
$$
$$
p = 100 - p_{i}
$$
$$
C_{0} = 0.12 + 0.4[\log_{10}{(f/10)^{0.8}}]
$$
$$
C_{1} = (0.07^{C_{0}})(0.12^{1-C_{0}})
$$
$$
C_{2} = 0.855C_{0} + 0.546(1-C_{0})
$$
$$
C_{3} = 0.139C_{0} + 0.043(1-C_{0})
$$
