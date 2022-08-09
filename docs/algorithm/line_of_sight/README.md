# Line-of-Sight

This doc describes how TG Planner determine whether a Line-of-Sight(LOS) link
is valid or not. TG planner has 2 models, the ellipsoidal model and the
cylindrical model to check if a LOS is blocked, and they share some common
rules to check easy negative cases. What’s more, the doc also talks about
the confidence level used for LOS links.

# Table of Contents
1. [Easy Negative Cases](Easy_Negative_Cases.md)
2. [Confidence Level](Confidence_Level.md)
3. [Cylindrical Model](Cylindrical_Model.md)
   1. [Problem Modeling](Cylindrical_Model.md#problem-modeling)
   2. [Math Equations](Cylindrical_Model.md#math-equations)
   3. [Steps to Decide LOS](Cylindrical_Model.md#steps-to-decide-los)
4. [Ellipsoidal MoDEL](Ellipsoidal_Model.md)
   1. [Problem Modeling](Ellipsoidal_Model.md#problem-modeling)
   2. [Math Equations](Ellipsoidal_Model.md#math-equations)
   3. [Steps to Decide LOS](Ellipsoidal_Model.md#steps-to-decide-los)
