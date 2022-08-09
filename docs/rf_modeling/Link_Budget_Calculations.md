# Link Budget Calculations

Given all the assumptions, models and calculations we have seen in the above
sections, in this section we describe the link budget calculations as
implemented in the tool. This section has two parts:
1. Received Signal Level (RSL) calculation procedure
2. Signal-to-interference-plus-noise (SINR) ration using the interference models

## RSL Calculation

Assuming you are transmitting from Site A to Site B, below is a simple link
budget to calculate the RSL in dBm

$$
RSL = PA-MA+GA-PL+GB-MB
$$
where,
- $PA$ = Transmit Power at A
- $MA$ = Miscellaneous Losses at A
- $GA$ = Antenna Gain measured at the deviation from the boresight at A
- $PL$ = FSPL + GAL
- $GB$ = Antenna Gain measured at the deviation from the boresight at B
- $MB$ = Miscellaneous Losses at B

# SINR Calculation

For every receiver site Rxn there is an intended transmitter site T xn. Any
other transmitter that has LOS to this receiver is considered as source of
interference. Say T xi is once such transmitter where i ̸= n. The interference
power from the ith transmitter on nth receiver is calculated as

$$
I_{i,n} = PA_{i} - MA_{i} + GA_{i} - PL + GB_{n} - MB_{n}
$$

where,
- $PA_{i}$ = Transmit Power from $Tx_{i}$
- $MA_{i}$ = Miscellaneous Losses at $Tx_{i}$
- $GA_{i}$ = Antenna Gain measured at the deviation from the boresight at A
- $PL$ = Pathloss ($FSPL + GA$) from $i$ to $n$
- $GB_{n}$ = Antenna Gain measured at the deviation from the boresight at $Rx_{n}$
- $MB_{n}$ = Miscellaneous Losses at $Rx_{n}$

The $SINR_{n}$ (in dBm) at $Rx_{n}$ is calculated using the following formula:

$$
SINR_{n} = 10\log_{10}{\frac{RSL_{n}}{\sum{I^{o}_{i,n} + N_{p}}}}
$$

where,
- $RSL_{n}$ = the $RSL$ calculated from the intended transmitter $Tx_{n}$ in mW
- $N_{p}$ = the thermal noise power calculated using the following equation in mW
- $I^{o}_{i,n}$ = the interference power in mW

$$
N_{p} = KTB
$$

where,
- $K$ = Boltzmann’s constant
- $T$ = the system temperature in K
- $B$ = the used bandwidth in Hz
