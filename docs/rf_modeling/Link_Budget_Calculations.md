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

## SINR Calculation

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
SINR_{n} = 10\log_{10}{\frac{RSL_{n}}{\sum{I^{o}_{i,n} + N_{p}}}} + NF
$$

where,
- $RSL_{n}$ = the $RSL$ calculated from the intended transmitter $Tx_{n}$ in mW
- $N_{p}$ = the thermal noise power calculated using the following equation in mW
- $I^{o}_{i,n}$ = the interference power in mW
- $NF$ = [Noise Figure](Radio_Models#rf-front-end)

$$
N_{p} = KTB
$$

where,
- $K$ = Boltzmann’s constant
- $T$ = the system temperature in K
- $B$ = the used bandwidth in Hz

Note that in the absence of any interference, the SINR simply boils down to SNR.
In that case, the SNR (in dB) can be directly calculated using the equation below:

$$
SNR_{n} = RSL_{n} - N_{p} - NF
$$

## MCS Table Lookup

As a final step, the SINR calculated in the above section is then used to find
the best operating MCS given the link availability conditions and hardware
specific backoff recom- mendations. The following table is used for 3-9s of
link availability. Note that this table is consistent with the 802.11ad chipsets
with typical backoff values.

| MCS | SNR(dB) | Datarate(Mbps) | Backoff(dB) |
| --- | ------- | -------------- | ----------- |
| 3   | 3       | 0              | 0           |
| 4   | 4.5     | 67.5           | 0           |
| 5   | 5       | 115            | 0           |
| 6   | 5.5     | 260            | 0           |
| 7   | 7.5     | 452.5          | 0           |
| 8   | 9       | 645            | 0           |
| 9   | 12      | 741.25         | 0           |
| 10  | 14      | 1030           | 2           |
| 11  | 16      | 1415           | 4           |
| 12  | 18      | 1800           | 6           |
