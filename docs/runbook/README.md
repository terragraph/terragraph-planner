# Terragraph Planner Runbook

This doc demonstrates how to run a plan using Terragraph Planner software,
and provides an introduction to Terragraph Planner's features.

In order to create a plan, users will gather information about the future
(or existing) installation and the neighborhood it is in, enter this
information as input files and plan parameters, and then run the plan to
generate a network topology, and metrics for network information rate,
connectivity, and total cost of ownership.

# Table of Contents
1. [Quick Start](Quick_Start.md)
   1. [Download](Quick_Start.md#download)
   2. [Install](Quick_Start.md#install)
   3. [Set up FICO Xpress](Quick_Start.md#set-up-fico-xpress)
   4. [Run Tests](Quick_Start.md#run-tests)
   5. [Run a Plan](Quick_Start.md#run-a-plan)
2. [Input Files](Input_Files.md)
   1. [Boundary Polygon File](Input_Files.md#boundary-polygon-file)
   2. [GeoTIFF Files](Input_Files.md#geotiff-files)
   3. [User Input Site File](Input_Files.md#user-input-site-file)
   4. [Building Outline File](Input_Files.md#building-outline-file)
   5. [Candidate Topology File](Input_Files.md#candidate-topology-file)
   6. [Base Topology File](Input_Files.md#base-topology-file)
3. [Output Files](Output_Files.md)
   1. [Topology KML File](Output_Files.md#topology-kml-file)
   2. [Reporting CSV Files](Output_Files.md#reporting-csv-files)
   3. [ILP Problem Files](Output_Files.md#ilp-problem-files)
4. [Features](Features.md)
   1. [POP Placement](Features.md#pop-placement)
   2. [Multi-SKU](Features.md#multi-sku)
   3. [Automatic Site Detection](Features.md#automatic-site-detection)
   4. [Maximum Common Bandwidth](Features.md#maximum-common-bandwidth-mcb)
   5. [Tiered Service](Features.md#tiered-service)
   6. [Extend existing Candidate Graph (EECG)](Features.md#extend-existing-candidate-graph-eecg)
5. [Glossary](Glossary.md)
