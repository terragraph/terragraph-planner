# Confidence Level

The confidence level describes how confident the planner is about the valid
LOS links. To compute it, we introduce the “max Fresnel radius”, which means
the maximum radius of a Fresnel zone without obstruction. With the cylindrical
model, it’s simplified as the shortest distance from nearest obstruction to
the center line.

$$
ConfidenceLevel = \frac{MaxFresnelRadius}{ActualFresnelRadius}
$$

Users can set a threshold of the confidence level, which is the minimal
confidence level of a valid LOS.
