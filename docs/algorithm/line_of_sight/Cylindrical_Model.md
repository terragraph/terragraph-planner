# Cylindrical Model

The cylindrical model is a simplified model from the ellipsoidal model.
Given the fact that the maximum radius of Fresnel zone of a 60 GHz radio
is small, which is usually less than 1 meter, the cylindrical model is
able to give a credible result when using most geographical data whose
resolution is about 1 meter too. In the cylindrical model, the radius
is uniform everywhere, called “Fresnel radius”, and is inputed by users.


## Problem Modeling

The main problem of this model is to compute the distance in a 3D space.
We compute the distance from DSM grid (or pixel) to the LOS center line
(the line from one end site to the other end site, without width) to determine
is this grid blocks the Fresnel zone. We use the center of the DSM grid as
representative to compute the distance. Thus, this problem becomes computing
distance from a 3-D line segment to another 3-D line segment.


## Math Equations

Since computing the distance between two 3-D lines is difficult, let’s simplify
the computation.

Say the two end sites have coordinates $(x_1​,y_1​,z_1​)$ and
$(x_2​,y_2​,z_2​)$, and one DSM grid $(x_0​,y_0​)$ has the base at $i_0​$ and
the top at h (then the building height is $∣h−i_0​∣$).

Then the formula of the LOS center line is:

$$
\begin{cases} x = x_1 + t \times p \\
y = y_1 + t \times q \\
z = z_1 + t \times r \\
\end{cases}
\text{, where } \frac{x_2-x_1}{p} = \frac{y_2-y_1}{q} = \frac{z_2-z_1}{r}
$$

The line segment for the shortest distance between both lines (i.e., the
line segment between $(x_1​,y_1​,z_1​)$ and $(x_2,y_2​,z_2​)$ and the line
segment between $(x_0​,y_0​,i_0​)$ and $(x_0​,y_0​,h)$ must be orthogonal.
Suppose the intersection on the DSM grid and the line segment is
$(x_0​,y_0​,z_0​)$, and the intersection on the LOS center line and the line
segment is $(x_1​+t_0​ \times p,y_1​+t_0​ \times q,z_1​+t_0​ \times r)$.

Then the shortest distance
$d^2=(x_0​−x_1​−t_0 \times p)^2+(y_0​−y_1​−t_0​\times q)^2+(z_0​−z_1​−t_0​ \times r)^2$.

where $(x_0​−x_1​−t_0​\times p) \times p+(y_0​−y_1​−t_0​\times q) \times q+(z_0​−z_1​−t_0​\times r)\times r=0$,
because of the orthogonality.

Then to simplify them, we get
$d^2=(x_0​−x_1​−t_0\times p)^2+(y_0​−y_1​−t_0​\times q)^2$, where
$(x_0​−x_1​−t_0​\times p)\times p+(y_0​−y_1​−t_0​ \times q)\times q=0$.
It becomes a problem of computing the distance from a 2-D point $(x_0, y_0)$
to a 2-D line from $(x_1​,y_1​)$ to $(x_2​,y_2​)$. The shapely lib can compute
it quickly.

But what if $z_0​>h$, which means the intersection point is actually higher
than the DSM grid top? In this case, we need to compute the distance from
the 3-D point $(x_0​,y_0​,h)$ to the 3-D line between $(x_1​,y_1​,z_1​)$ and
$(x_2​,y_2​,z_2​)$. Then how to determine it? We can compute the formula of
plane that goes through points $(x_1​,y_1​,z_1​)$, $(x_2​,y_2​,z_2​)$ and
$(x_0​,y_0​,z_0​)$, and use the formula to get $z_0$​, and then compare it
with $h$. We already know that line between $(x_0​,y_0​,z_0​)$ and
$(x_1​+t_0​\times p,y_1​+t_0​\times q,z_1​+t_0​\times r)$ is orthogonal with
the line between $(x_1​,y_1​,z_1​)$ and $(x_2​,y_2​,z_2​)$, then we find
another line that is parallel to the line between $(x_0​,y_0​,z_0​)$
and $(x_1​+t_0​\times p,y_1​+t_0​\times q,z_1​+t_0​\times r)$ but intersects
with $(x_1​,y_1​,z_1​)$ and $(x_2​,y_2​,z_2​)$ to determine the plane that
also contains $(x_0​,y_0​,z_0​)$. In that way, we can avoid computing
the plane formula every time for each DSM pixel.

Finally, we get the process to compute the distance, which is implemented
at [`los/cylindrical_los_validator.py`](https://github.com/terragraph/terragraph-planner/blob/main/terragraph_planner/los/cylindrical_los_validator.py).


## Steps to Decide LOS

For each pair of site $(x_1​,y_1​,z_1​)$ and $(x_2​,y_2​,z_2​)$:

1. (Step 1) In 2-D space, we find every DSM pixel $(x,y)$ whose distance
    to the line between $(x_1​,y_1​)$ and $(x_2​,y_2​)$ is smaller than the Fresnel
    radius. The distance from each of those DSM pixels to the 3-D LOS center
    should be smaller than the Fresnel radius if we do not consider the height.
    We call it `possible_obstructions` in the codebase.
2. (Step 2) Use $(x_1​,y_1​,z_1​)$, $(x_2​,y_2​,z_2​)$ and the third point
    $(x_3​,y_3​,z_3​)$, where the line between $(x_1​,y_1​,z_1​)$ and $(x_3​,y_3​,z_3​)$
    should be parallel to the line between $(x_0​,y_0​,z_0​)$ and
    $(x_1​+t_0​ \times p,y_1​+t_0​ \times q,z_1​+t_0​ \times r)$ to compute the
    formula of the plane that contains the intersection point between DSM pixel
    and the orthogonal line. We call that plane as `max_top_view_plane` in codebase.
3. (Step 3) Use the plane formula to check if $z_0​ \leq h$.
    1. If $z0​ \leq h$, use `shapely` lib to compute the distance from point
    $(x_0​,y_0​)$ to the line between $(x_1​,y_1​)$ and $(x_2​,y_2​)$, which
    is equal to the distance from DSM grid to the LOS center line.
    2. If $z0​>h$, compute the distance from $(x_0​,y_0​,h)$ to the line
    between $(x_1​,y_1​,z_1​)$ and $(x_2​,y_2​,z_2​)$ as the final distance.
    Be aware of whether the intersection point is line within the LOS
    center line here, since LOS center line is not an infinite line.
4. Finally, we use the shortest distance to compute the confidence level.
    If the confidence level is greater than the threshold, we propose that
    LOS link, otherwise reject it.

<p align="center">
    <img src="../../figures/los-cylindrical-step-overview.png" width="45%" />
    <img src="../../figures/los-cylindrical-step-1.png" width="45%" />
    <img src="../../figures/los-cylindrical-step-2.png" width="45%" />
    <img src="../../figures/los-cylindrical-step-3-1.png" width="45%" />
    <img src="../../figures/los-cylindrical-step-3-2.png" width="45%" />
    <img src="../../figures/los-cylindrical-step-4.png" width="45%" />
</p>
