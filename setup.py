# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import List

from setuptools import find_packages, setup

with open("requirements.txt") as f:
    install_requires: List[str] = f.read().splitlines()

setup(
    name="terragraph_planner",
    version="1.2.0",
    description="""
The Terragraph Planner is developed for operators to plan and optimize
 a mesh network using Terragraph's 60 GHz mmWave technology
""",
    long_description=open("README.md").read(),
    author="Meta Connectivity",
    url="terragraph.com",
    license=open("LICENSE").read(),
    install_requires=install_requires,
    include_package_data=True,
    packages=find_packages(),
    python_require=">=3.8",
)
