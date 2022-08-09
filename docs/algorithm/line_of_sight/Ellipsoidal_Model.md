# Ellipsoidal Model

The ellipsoidal model is more practical and theoretically more accurate
than the cylindrical model when the data resolution is better, but usually
costs more time to compute. The core concept of the ellipsoidal model is
the Fresnel zone. With the ellipsoidal model, the radius is non-uniform
and become largest at the center, which is called Fresnel radius. The
Fresnel radius here is computed based on the frequency, rather than
inputed by user.

TLDR of a Fresnel zone from the [Wiki](https://en.wikipedia.org/wiki/Fresnel_zone):

*Although intuitively, clear line-of-sight between transmitter and receiver
may seem to be all that is required for a strong antenna system, but because
of the complex nature of radio waves, obstructions within the first Fresnel
zone can cause significant weakness, even if those obstructions are not
blocking the apparent line-of-sight signal path. For this reason, it is
valuable to do a calculation of the size of the 1st, or primary, Fresnel
zone for a given antenna system. Doing this will enable the antenna installer
to decide if an obstacle, such as a tree, is going to make a significant
impact on signal strength.*

Example Fresnel Zone between two sites:
<img src="../../figures/los-ellipsoidal-fresnel-zone.png" />

## Problem Modeling

We will use a 2D ellipse on the $xy$ plane and a 3D ellipsoid. The 2D ellipse
is used to filter out all obstructions that are not within the 2D projection
of the Fresnel Zone. The 3D ellipsoid is used to check if the obstruction’s
height interferes with the Fresnel Zone.

Code is in [los/frensel_zone.py](https://github.com/terragraph/terragraph-planner/blob/main/terragraph_planner/los/fresnel_zone.py)
and [`los/ellipsoidal_los_validators.py`](https://github.com/terragraph/terragraph-planner/blob/main/terragraph_planner/los/ellipsoidal_los_validator.py)

Useful tools for visualization

* https://www.geogebra.org/calculator - 3D ellipsoid
* https://www.desmos.com/calculator - 2D ellipse

Ellipse and Ellipsoidal

1. We create a 2D ellipse on the $xy$ plane with the two sites as the end points.
2. (Red is x-axis, Green is y-axis, Blue is z-axis). In reality, the Fresnel
    radius is much smaller, but it’s enlarged here for visualization
   <img src="../../figures/los-ellipsoidal-2d.png" />
3. We also create a 3D ellipsoid with the two sites as the endpoints
   <img src="../../figures/los-ellipsoidal-3d.png" />

## Math Equations

Given two sites Site 1:$(x_1​,y_1​,z_1​)$, Site 2:$(x_2​,y_2​,z_2​)$

To calculate the maximum radius of the first Fresnel zone, we use this
equation from the [wiki](https://en.wikipedia.org/wiki/Fresnel_zone)

$$
F_1[m] = 8.656\sqrt{\frac{D[km]}{f[GHz]}} \\
where \; D = \sqrt{(x_2-x_1)^2+(y_2-y_1)^2+(z_2-z_1)^2}
$$
* D=(x2​−x1​)2+(y2​−y1​)2+(z2​−z1​)2​.  UTM is in meters

Equation for 2D ellipse on the $xy$ plane:

$$
\frac{((x-h)\cos(A)+(y-k)\sin(A))^2}{a^2} + \frac{((x-h)\sin(A)-(y-k)\cos(A))^2}{b^2} - 1 = 0
$$
where
* $h,k$ are the offsets from origin $(0,0)$ to the midpoint of the ellipse
* Angle $A$ is the is the angle between the $x$-axis and the line which goes
    through both sites
* $a$ is the 2D euclidean distance from a site to the midpoint
* $b$ is the Fresnel Radius

To check if a point $(x,y)$ is inside the ellipse, we just need to evaluate
the ellipse equation. if the result $\leq 0$, it is inside the ellipse otherwise
it is outside.

Equation for 3D ellipsoid:
The standard equation of an ellipsoid that is not rotated and at the origin is

$$
\frac{x^2}{a^2} + \frac{y^2}{b^2} + \frac{z^2}{c^2} = 1
$$
where
* $a$ is the 3D euclidean distance from a site to the midpoint
* $b$ and $c$ are both equal to the Fresnel Radius

We need to find a rotated ellipsoid that is not at the origin.

* We use 3D rotational matrices. We perform intrinsic rotations first on
    $z$-axis with angle $A$, then $y$-axis with angle $B$ then $x$-axis with
    angle $C$
    * **intrinsic** means the rotation is always based on the rotating coordinate system
* The three rotational matrices are
    $$
    R_z(\theta)=\begin{bmatrix}
    1 & 0 & 0 \\
    0 & \cos\theta & -\sin\theta \\
    0 & \sin\theta & \cos\theta \end{bmatrix} \\
    \ \\
    R_y(\theta)=\begin{bmatrix}
    \cos\theta & 0 & \sin\theta \\
    0 & 1 & 0 \\
    -\sin\theta & 0 & \cos\theta \end{bmatrix} \\
    \ \\
    R_z({\theta}) = \begin{bmatrix}
    \cos\theta & -\sin\theta & 0 \\
    \sin\theta & \cos\theta & 0 \\
    0 & 0 & 1 \\
    \end{bmatrix}
    $$
* Using a [right handed coordinate system](https://en.wikipedia.org/wiki/Right-hand_rule).
    We want a positive angle $A$ to rotate from postive $x$-axis to positive
    $y$-axis, a positive angle $B$ to rotate from postive $x$-axis to positive
    $z$-axis, and a positive angle $C$ to rotate from postive $y$-axis to
    positive $z$-axis
    * We get $\begin{bmatrix}x' \\ y' \\ z' \end{bmatrix} = R_x(-C)R_y(B)R_z(-A)
      \begin{bmatrix}x-h \\ y-k \\ z-l \end{bmatrix}$, then we plug $x'$, $y'$ and
      $z'$ into the standard ellipsoid equation $\frac{x'^2}{a^2}​+\frac{y'^2}{b^2}​
      +\frac{z'^2}{c^2} ​=1$
* Since $b$ and $c$ are both equal to the Fresnel Radius, Angle $C$ (around the
    $x$-axis) will not have an impact since it is a sphere on the $yz$ plane.
    We can simplify the equation with $C = 0$
* Final 3D ellipsoid equation is
$$
\frac{((x-h)\times\cos(B)\times\cos(A)+(y-k)\times\sin(A)\times\cos(B)+(z-l)\times\sin(B))^2 }{a^2} \\
+ \frac{((h-x)\times\sin(A)+(y-k)\times\cos(A))^2}{b^2} \\
+ \frac{((h-x)\times\sin(B)\times\cos(A)+(k-y)\times\sin(B)\times\sin(A)+(z-l)\times\cos(B))^2 }{c^2} \\
- 1 = 0
$$

* Where angle $A$ is the first rotation around the $z$-axis, calculated using
    $\arctan\frac{y_1-y_2}{x_1-x_2}​​$

* Angle $B$ is the second rotation around the $y$-axis applied after the first
    rotation, calculated by
    $$
        \begin{rcases}
            B = \arctan\frac{z_1-z_2}{x'_1-x'_2} \\
            x'_1 = x_1\cos(-A)-y_1\sin(-A) \\
            x'_2 = x_2\cos(-A)-y_2\sin(-A)
        \end{rcases} \\
        \implies B = \arctan\frac{z_1-z_2}{(x_1-x_2)\times\cos(A)+(y_1-y_2)\times\sin(A)}
    $$

 * To find the two heights on the ellipsoid for a point($x$,$y$), we rearrange
    the ellipsoid equation for variable $z$ into standard quadratic form
    $ax^2 + bx + c = 0$, then get
    $$
     (z-l)^2(\frac{\sin^2(B)}{a^2}+\frac{\cos^2(B)}{c^2})
     + (z-l)(\frac{p\times\sin(B)}{a^2}+\frac{q\times\cos(B)}{c^2}) \\
     + (\frac{p^2}{a^2}+\frac{q^2}{c^2}+\frac{((h-x)\times\sin(A)+(y-k)\times\cos(A))^2}{b^2}) = 0
    $$
  * where, $\ p = ((x-h)\times\cos(B)\times\cos(A)+(y-k)\times\sin(A)\times\cos(B))$
  * $q = ((h−x)\times\sin(B)\times\cos(A)+(k−y)\times\sin(B)\times\sin(A))$
  * We get the two heights by using [this numericaly stable method to solve for roots](https://people.csail.mit.edu/bkph/articles/Quadratics.pdf)
    and adding offset $l$. If there’s no roots, then it’s obviously that the LOS
    is clear. To compute the confidence level, we only care about the higher
    intersection. If it’s higher than `max_top_view_plane` , which is described
    in the section of [Cylindrical Model](Cylindrical_Model#steps-to-decide-los),
    we compute the confidence level with the 3D ellipsoid equation; otherwise,
    the 2D ellipse is used because the closest obstruction is on the
    `max_top_view_plane`.

## Steps to Decide LOS

1. We create a rectangular bounding box around the ellipse. Points $I, J, K, L$
    define the bounding rectangle surrounding the ellipse region
    <img src="../../figures/los-ellipsoidal-step-1.png" />
2. We scan through a rectangular area on the DSM that cover the ellipse and
    obtain all the `potential_obstructions`
3. For each potential obstruction, we first check if it is inside the $xy$ ellipse.

    For example Here point $F$ and $G$ will get filtered out because they are not
    within the 2D projection, but points $C$,$D$,$E$ may still be an obstruction
    <img src="../../figures/los-ellipsoidal-step-3.png" />
4. For all the obstructions inside the ellipse, we then use the 3D ellipsoid
    to check if the obstruction’s height interferes with the Fresnel Zone.
    With DSM data, we only have $(x,y,z)$ coordinate with $z$ being the highest
    point on the object therefore. Then an obstruction interferes with the
    Fresnel Zone if the height is within or greater than the ellipsoid

    For example, here point $E$ and $C$ is an obstruction because it is
    within/above the Fresnel Zone but point $D$ is not an obstruction since
    it is below the Fresnel Zone.
    <img src="../../figures/los-ellipsoidal-step-4.png" />
