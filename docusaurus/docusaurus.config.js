/**
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 *
 * @format
 */
// @ts-check
// Note: type annotations allow type checking and IDEs autocompletion

const lightCodeTheme = require('prism-react-renderer/themes/github');
const darkCodeTheme = require('prism-react-renderer/themes/dracula');

// Rehype Plugin to rewrite URLs -- in conjunction with `staticDirectories`,
// this allows us to write markdown with relatives paths such that docs render
// images properly in GitHub or in IDE and still work with Docusaurus.
const visit = require('unist-util-visit');
const rehypeRewriteUrlPlugin = (options) => {
  const transformer = async (ast) => {
    visit(ast, 'jsx', (node) => {
      node.value = node.value.replaceAll("../media/", "/");
    });
  };
  return transformer;
};

// Enable math equation support witih KaTeX
const math = require('remark-math');
const katex = require('rehype-katex');

const BASEURL = '/terragraph-planner';

const DISCORD_URL = 'https://discord.gg/HQaxCevzus';
const TERRAGRAPH_REPO_URL = 'https://github.com/terragraph/meta-terragraph'
const TERRAGRAPH_URL = "https://terragraph.com";
const TGNMS_REPO_URL = 'https://github.com/terragraph/tgnms';
const TGPLANNER_REPO_URL = 'https://github.com/terragraph/terragraph-planner';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'Terragraph Planner',
  tagline: 'Developed for operators to plan, optimize, deploy, and manage a Terragraph network.',
  url: 'https://terragraph.github.io/',
  baseUrl: BASEURL + '/',
  trailingSlash: false,
  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',
  favicon: 'logo/terragraph-logo-favicon-32x32-full-RGB.png',

  // GitHub pages deployment config.
  // If you aren't using GitHub pages, you don't need these.
  organizationName: 'terragraph', // Usually your GitHub org/user name.
  projectName: 'terragraph-planner', // Usually your repo name.
  staticDirectories: ['static', '../docs/media'],
  // Even if you don't use internalization, you can use this field to set useful
  // metadata like html lang. For example, if your site is Chinese, you may want
  // to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          path: '../docs',
          exclude: ['build/**'],
          editUrl: ({ versionDocsDirPath, docPath }) =>
            `${TGPLANNER_REPO_URL}/edit/main/docs/${versionDocsDirPath}/${docPath}`,
          routeBasePath: '/',
          sidebarPath: require.resolve('./sidebars.js'),
          remarkPlugins: [math],
          rehypePlugins: [katex, rehypeRewriteUrlPlugin]
        },
        blog: false,
        theme: {
          customCss: require.resolve('./src/css/custom.css'),
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      prism: {
        theme: lightCodeTheme,
        darkTheme: darkCodeTheme,
      },
      algolia: {
        appId: 'SZDKMHI44K',
        apiKey: 'f1942a94b52f299c140bc5fcb0a91eee',
        indexName: 'terragraph-planner',
      },
      docs: {
        sidebar: {
          hideable: true,
        }
      },
      image: 'logo/terragraph-logo-full-RGB.png',
      navbar: {
        logo: {
          alt: 'Terragraph Logo',
          src: 'logo/terragraph-logo-favicon-32x32-full-RGB.svg',
          srcDark: 'logo/terragraph-logo-favicon-32x32-white-RGB.svg',
        },
        items: [
          {
            to: TGPLANNER_REPO_URL, // NOTE: avoiding 'href' to hide IconExternalLink
            position: 'right',
            className: 'githubButton navbarIconButton',
            title: 'GitHub',
          },
          {
            to: DISCORD_URL, // NOTE: avoiding 'href' to hide IconExternalLink
            position: 'right',
            className: 'discordButton navbarIconButton',
            title: 'Discord',
          },
          {
            type: 'dropdown',
            label: 'Docs',
            position: 'right',
            items: [
              {
                type: 'doc',
                docId: 'runbook/README',
                label: "Runbook",
                activeClassName: '', // HACK: broken in docusaurus 2.0.0-beta.21
              },
              {
                type: 'doc',
                docId: 'algorithm/README',
                label: 'Algorithm',
                activeClassName: '', // HACK: broken in docusaurus 2.0.0-beta.21
              },
              {
                type: 'doc',
                docId: 'rf_modeling/README',
                label: 'RF Modeling',
                activeClassName: '', // HACK: broken in docusaurus 2.0.0-beta.21
              },
            ],
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Terragraph',
            items: [
              {
                label: 'Terragraph',
                href: TERRAGRAPH_URL,
              },
              {
                label: 'Meta Connectivity',
                href: 'https://www.facebook.com/connectivity/solutions/terragraph',
              },
            ],
          },
          {
            title: 'Community',
            items: [
              {
                label: 'Terragraph',
                href: TERRAGRAPH_REPO_URL,
              },
              {
                label: 'Terragraph Planner',
                href: TGPLANNER_REPO_URL,
              },
              {
                label: 'Terragraph NMS',
                href: TGNMS_REPO_URL,
              },
              {
                label: 'Discord',
                href: DISCORD_URL,
              },
            ],
          },
          {
            title: 'Legal',
            // Please do not remove the privacy and terms, it's a legal requirement.
            items: [
              {
                label: 'Privacy',
                href: 'https://opensource.facebook.com/legal/privacy/',
              },
              {
                label: 'Terms',
                href: 'https://opensource.facebook.com/legal/terms/',
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} Meta Platforms, Inc. Built with Docusaurus.`,
      },
    }),

  stylesheets: [
    {
      href: BASEURL + '/katex/katex.min.css',
      type: 'text/css',
    },
  ],
};

module.exports = config;
