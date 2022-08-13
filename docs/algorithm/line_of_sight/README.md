# Line-of-Sight

This document describes how the TG Planner determines whether there is valid
Line-of-Sight between two sites. We provide two approaches to modeling the
propagation of radio waves to determine whether or not there is an obstruction:
a simple cyclindrical model and a more accurate ellipsoidal model.

# Table of Contents
1. [Easy Negative Cases](Easy_Negative_Cases.md)
2. [Cylindrical Model](Cylindrical_Model.md)
   1. [Problem Modeling](Cylindrical_Model.md#problem-modeling)
   2. [Mathematical Formulation](Cylindrical_Model.md#mathematical-formulation)
   3. [Algorithm](Cylindrical_Model.md#algorithm)
3. [Ellipsoidal Model](Ellipsoidal_Model.md)
   1. [Problem Modeling](Ellipsoidal_Model.md#problem-modeling)
   2. [Mathematical Formulation](Ellipsoidal_Model.md#mathematical-formulation)
   3. [Steps to Decide LOS](Ellipsoidal_Model.md#steps-to-decide-los)
4. [Confidence Level](Confidence_Level.md)
