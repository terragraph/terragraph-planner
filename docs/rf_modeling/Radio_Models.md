# Radio Models

In this section a joint model of Baseband and RF up/down-conversion is
described. The model is primarily driven by the following input parameters:

## RF Front End

This module interfaces with the antenna subsystem and the Baseband. The key
functionality of this module is to up/down-convert the signals to/from higher
frequencies (mixing).

- **Maximum Tx Power**: Maximum Transmission Power in dBm. Different
  manufacturers have different limits on the maximum allowed transmit power.
  The transmit power control (TPC) algorithm programmed in the tool will use
  this as the upper limit while trying to identify the best transmit power for
  each unit.
- **Minimum Tx Power**: Minimum Transmission Power in dBm. Similar to the Max
  Tx power, there is a minimum Tx power for each manufacturer’s equipment and
  is also used as a lower limit in the TPC algorithm
- **Maximum EIRP**: Maximum Equivalent/Effective Isotropically Radiated Power
  in dBm. This is typically set by the regulatory bodies in the deployment area.
  The TPC takes this into account and caps the max power such that the sum of
  Tx power and antenna boresight gain does not exceed the Maximum EIRP limit.
- **Tx Miscellaneous Loss**: Miscellaneous losses on the transmitter in dB.
  These can include, but not limted to cable/connector losses, RF hardware
  mismatch losses.
- **Rx Miscellaneous Loss**: Miscellaneous losses on the receiver in dB.
  These can include, but not limited to cable/connector losses, RF hardware
  mismatch losses.
- **Frequency**: Frequency (in MHz) at which these sectors operate.
- **Noise Figure**: A critical link budget factor that degrades the received
  SNR. The Noise Figure (NF) is defined in dB and formulated in log scale as
  the degradation of SNR. i.e. NF = SNR input - SNR output. In
  [Link Budget Calculations](Link_Budget_Calculations.md) we
  show the formulation on NF in link budget calculation

## Baseband


The Baseband module, as a receiver, receives down-converted signals from the RF
front end and extracts data (as bits) from these signals. As a transmitter,
provides input signals to the RF front-end for up-conversion to higher
frequencies. The following terms are tied to the SNR gains achieved

- **Tx Diversity Gain**: Transmitter diversity gain in dB. This could be
  achieved due to polarization diversity or any other spatial diversity scheme.
- **Rx Diversity Gain**: Receiver diversity gain in dB. This could be achieved
  due to polarization diversity or any other spatial diversity scheme.
- **Minimum MCS Level**: The minimum MCS level allowed. This could be forcefully
  set to a higher value to always guarantee a certain MCS in all links.
- **Thermal Noise Power**: Thermal noise power (dBm) is used in the link budget
  calculations to capture the noise floor level. This is dependent on system
  temperature and bandwidth used. A detailed formulation is given in
  [Link Budget Calculations](Link_Budget_Calculations.md).
- **MCS Map File**: A CSV file that contains the mapping between MCS, SNR and
  Mbps where Mbps represents effective download rate. There must be exactly
  one column with headers ”mcs”, ”snr” and ”mbps”.
