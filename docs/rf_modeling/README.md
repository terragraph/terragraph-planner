# RF Modeling for Terragraph Network Planning

This document provides an in-depth description of the RF modeling and
implementation details used in Terragraph Planner's development process.

The tool takes certain key parameters as input that describe the functional
range of any manufacturer’s equipment. These parameters cover the
subcomponents antenna and radio units. The input parameter list also
extends to cover additional details such as propagation modeling assumptions
and higher-layer capabilities.

# Table of Contents
1. [System Architecture & Topology](System_Architecture_And_Topology.md)
2. [Antenna Front End](Antenna_Front_End.md)
   1. [Single-beam Pattern](Antenna_Front_End.md#single-beam-pattern)
   2. [Multi-beam Effects](Antenna_Front_End.md#multi-beam-effects)
   3. [Multi-sector Capability](Antenna_Front_End.md#multi-sector-capability)
3. [Radio Models](Radio_Models.md)
   1. [RF Front End](Radio_Models.md#rf-front-end)
   2. [Baseband](Radio_Models.md#baseband)
4. [Propagation Models](Propagation_Models.md)
   1. [FSPL](Propagation_Models.md#fspl)
   2. [GAL](Propagation_Models.md#gal)
   3. [Rain Loss](Propagation_Models.md#rain-loss)
5. [Link Budget Calculations](Link_Budget_Calculations.md)
   1. [RSL Calculation](Link_Budget_Calculations.md#rsl-calculation)
   2. [SINR Calculation](Link_Budget_Calculations.md#sinr-calculation)
