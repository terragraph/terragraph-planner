# Confidence Level

It is possible to allow links that have obstructions to still be declared valid
LOS, particularly if those obstructions are near the boundary of the Fresnel
zone.

In addition to the Fresnel radius used by the model ($F_1$), we also compute
the first obstruction radius ($F_o$). The confidence level, $C$, refers to the
ratio of the latter to the former:

$$
C = \frac{F_o}{F_1}
$$

Therefore, links without any obstructions have a confidence level of 1. Links
with obstructions on the direct LOS signal path have confidence level of 0.

The first obstruction radius depends on the model that is being used. It is the
radius of the largest cylinder or ellipsoid that can be constructed without
any obstructions. For the cylindrical model, it is simply the shortest distance
from the nearest obstruction to the direct LOS signal path.

Users can set a threshold for the confidence level, which is the minimal
confidence level required for a valid LOS. Decreasing the level provides more
valid LOS links but with greater risk that those links do not have actual LOS
during field surveys.
