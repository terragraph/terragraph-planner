# Easy Negative Cases

There are 4 easy negative cases for both 2 models, which is coded in
[`BaseLOSValidator`](https://github.com/terragraph/terragraph-planner/blob/main/terragraph_planner/los/base_los_validator.py).
If any of these cases happen, the planner regards
the link as invalid, and would not move forward to check if it’s blocked.

1. With the same latitude and longitude
2. On the same building
3. Out of distance range
4. Intersecting with the exclusion zones
