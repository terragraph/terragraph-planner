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
Ubuntu. Use another package tool instead if you are using different OS.
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
5. Install the extra recommended Python packages if you are a developer.
   ```sh
   pip3 install -r requirements_dev.txt
   ```

## Set up FICO Xpress

1. Go through steps in [Install](#install) to install xpress
2. Set the environment variable `XPAUTH_PATH` to the full path of your commericial
   license if you have one. Otherwise, the community license is used by default
   (which will only work for very small plans).
3. If you are using a commercial license for xpress, please specify the
   version of xpress and install it separately after step 4 in the last section.
   ```
   pip3 install xpress==x.y.z
   ```
   where x.y.z is the version compatible with your license.

Get more details at [FICO Xpress Optimization Help](https://www.fico.com/fico-xpress-optimization/docs/latest/solver/optimizer/python/HTML/chIntro.html?scroll=secInstall).

## Run Tests

Run the tests to check if the package is correctly installed.
```sh
python3 -m unittest discover terragraph_planner -b
```

## Run a Plan

### Configuration File

One way to customize and run a plan is using an input configuration yaml file. Refer to
[template.yaml](https://github.com/terragraph/terragraph-planner/blob/main/terragraph_planner/data/template.yaml)
for available parameters. In general, any parameter not provided in the input
configuration file will use the default value instead. With the exception of
the file paths and list of devices, default values can be found in that
yaml file.


### Line-of-Sight Analysis Plan

A Line-of-Sight Analysis Plan only runs LOS checks and produces a candidate
network without optimization.

To run an LOS Analysis Plan with a configuration file:

```python
from terragraph_plannner import generate_candidate_topology_with_config_file

generate_candidate_topology_with_config_file(config_file_path)
```


### Optimization Plan and End-to-End Plan

An Optimization Plan optimizes the input candidate network. An End-to-End Plan
runs both the LOS analysis and the network optimization.

To run an Optimization Plan or End-to-End Plan with a configuration file:
```python
from terragraph_plannner import optimize_and_report_topology_with_config_file

optimize_and_report_topology_with_config_file(config_file_path)
```

The configuration file will control which plan type is run. If the candidate
topology file is provided, only the Optimization Plan will be run. If the
candidate topology file is not provided, the End-to-End Plan will run.
