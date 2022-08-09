# Quick Start

The Terragraph Planner is an open-source Python library developed for operators
to plan and optimize a mesh network using Terragraph's 60 GHz mmWave technology.

## Download

```sh
git clone git@github.com:terragraph/terragraph-planner.git
```
or
```sh
git clone https://github.com/terragraph/terragraph-planner.git
```

## Install

1. Update the source, install pip3 and gdal lib. Use apt if you are using
Ubuntu. Use other package tool instead if you're using other OS.
   ```sh
   apt update && \
   apt install -y software-properties-common && \
   apt install -y python3-pip && \
   apt install -y gdal-bin && \
   apt install -y libgdal-dev && \
   ```
2. Set up environment varibles for gdal lib.
   ```sh
   export CPLUS_INCLUDE_PATH=/usr/include/gdal && \
   export C_INCLUDE_PATH=/usr/include/gdal
   ```
3. Change the directory to your local repository.
4. Install the terragraph_planner package.
   ```sh
   pip3 install .
   ```
5. Install the extra recommended Python packages if you're a developer.
   ```sh
   pip3 install -r requirements_dev.txt
   ```

## Set up FICO Xpress

1. Go through steps in [Install](#install) to install xpress
2. Set the environment variable `XPAUTH_PATH` to the full path of your commericial
   license if you have one. Otherwise, the community license is used by default.

Get more details at [FICO Xpress Optimization Help](https://www.fico.com/fico-xpress-optimization/docs/latest/solver/optimizer/python/HTML/chIntro.html?scroll=secInstall).

## Run Tests

Run the tests to check if the package is correctly installed.
```sh
python3 -m unittest discover terragraph_planner -b
```

## Run a Plan

### Line-of-Sight Analysis Plan

A Line-of-Sight Analysis Plan only runs LOS checks and produces a candidate
network without optimization.

To run a LOS Analysis Plan with the config file:

```Python
from terragraph_plannner import generate_candidate_topology_with_config_file

generate_candidate_topology_with_config_file(config_file_path)
```


### Optimization Plan and End-to-End Plan

An Optimization Plan runs optimization algorithms on the an input candidate network,
while an End-to-End Plan has both the LOS part and the optimization part.

To run a Optimization Plan or End-to-End Plan with the config file:
```Python
from terragraph_plannner import optimize_and_report_topology_with_config_file

optimize_and_report_topology_with_config_file(config_file_path)
```

The function will run an Optimization Plan or an End-to-End plan based on the config.
If the candidate topology file is provided, only the optimization step will be run.
If the candidate topology file is missing and LOS config is provided, the End-to-End plan
will run with the LOS step that generates the candidate topology.

To customized your plan, please refer to [template.yaml](https://github.com/terragraph/terragraph-planner/blob/main/terragraph_planner/data/template.yaml)
to set up your own parameters.
