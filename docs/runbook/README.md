# Terragraph Planner Runbook

This document demonstrates how to run a plan using the Terragraph Planner
software and provides an introduction to its features.

In order to create a plan, users must gather information about the future
(or existing) installation, the neighborhood it is in, and enter this
information as input files and plan parameters. The planner will then generate
a network topology from which various metrics are computed such as network
connectivity, throughput and cost of construction.

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
   3. [Debugging Files](Output_Files.md#debugging-files)
4. [Features](Features.md)
   1. [Multi-SKU](Features.md#multi-sku)
   2. [Automatic Site Detection](Features.md#automatic-site-detection)
   3. [Demand Models](Features.md#demand-models)
   4. [Tiered Service](Features.md#tiered-service)
   5. [POP Placement](Features.md#pop-placement)
   6. [Maximum Common Bandwidth](Features.md#maximize-common-bandwidth)
   7. [Extend Existing Candidate Graph](Features.md#extend-existing-candidate-graph)
