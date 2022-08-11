/**
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 *
 * @format
 */
/**
 * Creating a sidebar enables you to:
 - create an ordered group of docs
 - render a sidebar for each doc of that group
 - provide next/previous navigation

 The sidebars can be generated from the filesystem, or explicitly defined here.

 Create as many sidebars as you want.
 */

// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docs: [
    {
      type: 'doc',
      id: 'README',
    },
    {
      type: 'category',
      label: 'Runbook',
      items: [
        'runbook/Quick_Start',
        'runbook/Input_Files',
        'runbook/Output_Files',
        'runbook/Features',
      ],
      link: {
        type: 'doc',
        id: 'runbook/README',
      }
    },
    {
      type: 'category',
      label: 'Algorithm',
      items: [
        {
          type: 'category',
          label: 'Line-of-Sight',
          items: [
            'algorithm/line_of_sight/Easy_Negative_Cases',
            'algorithm/line_of_sight/Confidence_Level',
            'algorithm/line_of_sight/Cylindrical_Model',
            'algorithm/line_of_sight/Ellipsoidal_Model',
          ],
          link: {
            type: 'doc',
            id: 'algorithm/line_of_sight/README',
          }
        },
        {
          type: 'category',
          label: 'Optimization',
          items: [
            'algorithm/optimization/Overview',
            'algorithm/optimization/Notation',
            'algorithm/optimization/Cost_Minimization',
            'algorithm/optimization/Coverage_Maximization',
            'algorithm/optimization/Redundancy_Optimization',
            'algorithm/optimization/Interference_Minimization',
            'algorithm/optimization/Connected_Demand',
            'algorithm/optimization/Flow_Optimization',
            'algorithm/optimization/Future_Directions',
          ],
          link: {
            type: 'doc',
            id: 'algorithm/optimization/README',
          },
        },
      ],
      link: {
        type: 'doc',
        id: 'algorithm/README',
      },
    },
    {
      type: 'category',
      label: 'RF Modeling',
      items: [
        'rf_modeling/System_Architecture_And_Topology',
        'rf_modeling/Antenna_Front_End',
        'rf_modeling/Radio_Models',
        'rf_modeling/Propagation_Models',
        'rf_modeling/Link_Budget_Calculations',
      ],
      link: {
        type: 'doc',
        id: 'rf_modeling/README',
      }
    },
  ]
};

module.exports = sidebars;
