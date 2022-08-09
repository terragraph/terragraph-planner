# Copyright (c) Meta Platforms, Inc. and affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import Any, Dict


def check_if_subdict(sub: Dict[str, Any], base: Dict[str, Any]) -> bool:
    for k, v in sub.items():
        if k not in base.keys():
            print(f"{k} is not in base.")
            return False
        if isinstance(v, dict):
            return check_if_subdict(sub[k], base[k])
        elif isinstance(v, list):
            for i in range(len(v)):
                if isinstance(v[i], dict):
                    if not check_if_subdict(v[i], base[k][i]):
                        return False
                elif isinstance(v[i], (int, float, str)):
                    if v[i] != base[k][i]:
                        return False
        else:
            if base[k] != sub[k]:
                print(f"{k}: {base[k]} != {sub[k]}")
                return False
    return True
