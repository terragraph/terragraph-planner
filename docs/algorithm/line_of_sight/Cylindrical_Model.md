# Cylindrical Model

The cylindrical model is a simplified model of radio wave propagation that is
fast to compute and reasonably accurate. It assumes that Fresnel zones are
cylindrical in shape with axes along the direct path connecting the transmitter
and receivier. In other words, the distance from that direct path to the
boundary of the first Fresnel zone is uniform along the entire path. That
distance is the radius of the first Fresnel zone, which we often refer to as
the Fresnel radius. The radius of the cylindrical model is specified by the
user.

Keep in mind that the accuracy of determining LOS is heavily dependent on the
accuracy and resolution of the underlying surface elevation data. Given that
the radius of the first Fresnel zone is usually less than 1 meter for 60 GHz
radio communication and that the geographical data typically has a resolution
of around 1 meter as well, in many cases, the cylindrical model is sufficient.

## Problem Modeling

Determining LOS for the cylindrical model ultimately comes down to finding the
shortest distance between a line segment (the line representing the direct path
between the two sites) and a semi-infinite line (the vertical line from the
height of the surface down as specified by the DSM located at the center of the
DSM pixel). If the shortest distance is less than the Fresnel radius and
between the two sites, then the LOS is blocked.

> In this implementation of the cylindrical model, we use a tilted or oblique
cylinder where the end caps are orthogonal to the xy-plane. The difference
between an oblique cylinder and a rotated cylinder is relatively minor and only
near the ends. Given that this is an approximate model, such differences are
acceptable.

## Mathematical Formulation

Assume the two end sites have coordinates $(x_1​,y_1​,z_1​)$ and
$(x_2​,y_2​,z_2​)$, and the DSM height at pixel $(x_0​,y_0​)$ is $z_0$.

The formula of the line representing the direct path between the sites is

$$
\begin{cases}
x = x_1 + p (x_2 - x_1) \\
y = y_1 + p (y_2 - y_1) \\
z = z_1 + p (z_2 - z_1) \\
\end{cases}
p \in [0,1]
$$

Similarly, the formula for the vertical line at the DSM pixel is

$$
\begin{cases}
x = x_0 \\
y = y_0 \\
z = z_0 - q \\
\end{cases}
q \geq 0
$$

In vector notation, we will write these two equations as

$$
L(p) = {\bf a} + p {\bf b}
$$

$$
M(q) = {\bf c} + q {\bf d}
$$

where ${\bf a} = (x_1, y_1, z_1)$, ${\bf b} = (x_2 - x_1, y_2 - y_1, z_2 - z_1)$, ${\bf c} = (x_0, y_0, z_0)$, and ${\bf d} = (0, 0, -1)$.

The line segment for the shortest distance between the two lines must be
perpendicular to both lines. The unit vector that is perpendicular to both
lines is

$$
\frac{{\bf b}  \times {\bf d}}{\left | {\bf b}  \times {\bf d} \right |}
$$

Then the shortest distance, $d$, between the lines is the projection of the
vector connecting the two lines on the unit vector perpendicular to both lines.
That is, the shortest distance is

$$
d = ({\bf c} - {\bf a}) \cdot \frac{{\bf b}  \times {\bf d}}{\left | {\bf b}  \times {\bf d} \right |}
$$

Expanding this equation in terms of our original variables, we get

$$
d = \frac{(x_1-x_0)(y_2-y_1) - (y_1-y_0)(x_2-x_1)}{\sqrt{(x_2-x_1)^2 + (y_2-y_1)^2}}
$$

> We know the lines will not be parallel because of
[Easy Negative Case #1](Easy_Negative_Cases.md). In other words, we should
never have the situation where $x_2 = x_1$ and $y_2 = y_1$.

Any vector connecting the two lines can be expressed as

$$
{\bf a} + p {\bf b} - {\bf c} - q {\bf d}
$$

For some value of $p$ and $q$, this vector will be perpendicular to both lines.

$$
({\bf a} + p {\bf b} - {\bf c} - q {\bf d}) \cdot {\bf b} = 0
$$

$$
({\bf a} + p {\bf b} - {\bf c} - q {\bf d}) \cdot {\bf d} = 0
$$

We have two equations with two unknowns, which we solve to get

$$
p = \frac{(x_0-x_1)(x_2-x_1)+(y_0-y_1)(y_2-y_1)}{(x_2-x_1)^2 + (y_2-y_1)^2}
$$

$$
q = z_0 - z_1 -p(z_2-z_1)
$$

If both $p \in [0,1]$ and $q \geq 0$, then LOS is blocked if $d$ is less than
the Fresnel radius. If $p \notin [0, 1]$, then LOS is not blocked (this is due
to using an oblique cylinder). If $q < 0$ then the shortest distance is from
the point $M(0) = {\bf c}$ to the line $L(p)$. This can happen if, for example,
the top of a building is below the direct path between the two sites; in this
situation, the closest point is likely above the top of the building, but the
top of the building might still be within the Fresnel radius.

In this case, the problem becomes finding the distance between a point and a
line. We know the shortest distance from ${\bf c}$ to $L(p)$ is perpendicular to $L(p)$.

$$
({\bf a} + p {\bf b} - {\bf c}) \cdot {\bf b} = 0
$$

Therefore

$$
p = -\frac{({\bf a} - {\bf c}) \cdot {\bf b}}{\left | {\bf b} \right |^2}
$$

and the distance is

$$
d = \left | {\bf a} - {\bf c} - \frac{({\bf a} - {\bf c}) \cdot {\bf b}}{\left | {\bf b} \right |^2} {\bf b} \right |
$$

It turns out that this is equivalent to

$$
d = \frac{\left | {\bf b} \times ({\bf a} - {\bf c}) \right |}{\left | {\bf b} \right |}
$$

Once again, if $p \notin [0, 1]$, then LOS is not blocked.

## Algorithm

1. Find the rectangular projection of the oblique cylinder on the xy-plane.
   Only consider DSM grid points that are inside this rectangular projection.
   Call these candidate obstruction points.
2. For each candidate obstruction point, compute the shortest distance to the
   LOS direct path between the sites using the formulae above. If the distance
   is less than the Fresnel radius, LOS is blocked. For all such obstructions,
   we keep track of the minimum shortest distance in order to compute the
   [confidence level](Confidence_Level.md). If the distance is equal to or
   exceeds the Fresnel radius (or Fresnel radius scaled by the user-supplied
   confidence level threshold) for all candidate obstruction points, it is
   valid LOS.
