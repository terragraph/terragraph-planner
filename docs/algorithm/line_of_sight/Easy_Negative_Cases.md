# Easy Negative Cases

Regardless of the model, there are five situations which immediately return
invalid LOS that has nothing to do with obstructions.

1. Sites have the same latitude and longitude.
2. The elevation angle between the two sites is larger than a user-specified
   maximum elevation scan angle. While this would seemingly make #1 redundant,
   a user can effectively disable this check by setting it to 90 degrees (even
   if that is not advisable).
3. Both sites are on the same building (generally, such sites can be connected
   by wire).
4. The distance between the sites exceeds the maximum distance (i.e., the
   signal is not sufficiently strong to merit valid LOS).
5. The LOS intersects with exclusion zones.
