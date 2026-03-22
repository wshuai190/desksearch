/**
 * electron-builder configuration for DeskSearch.
 *
 * Usage:
 *   npx electron-builder --config electron/build-config.js
 *
 * This config is also embedded in electron/package.json under the "build" key.
 * This file exists as an importable alternative for CI or custom build scripts.
 */

const path = require('path');

module.exports = {
  appId: 'com.desksearch.app',
  productName: 'DeskSearch',

  directories: {
    output: path.resolve(__dirname, '..', 'dist', 'electron'),
  },

  files: [
    'main.js',
    'preload.js',
    'build-config.js',
    'assets/**/*',
  ],

  extraResources: [
    {
      from: path.resolve(__dirname, '..', 'src', 'ui', 'dist'),
      to: 'ui',
      filter: ['**/*'],
    },
  ],

  // --- macOS ---
  mac: {
    category: 'public.app-category.productivity',
    target: ['dmg'],
    icon: 'assets/icon.icns',
    darkModeSupport: true,
    hardenedRuntime: true,
    gatekeeperAssess: false,
    entitlements: null,
    entitlementsInherit: null,
  },

  dmg: {
    title: 'Install DeskSearch',
    iconSize: 80,
    window: { width: 540, height: 380 },
    contents: [
      { x: 170, y: 200 },
      { x: 430, y: 200, type: 'link', path: '/Applications' },
    ],
  },

  // --- Windows ---
  win: {
    target: ['nsis'],
    icon: 'assets/icon.ico',
  },

  nsis: {
    oneClick: false,
    allowToChangeInstallationDirectory: true,
    installerIcon: 'assets/icon.ico',
    uninstallerIcon: 'assets/icon.ico',
    license: null,
  },

  // --- Linux ---
  linux: {
    target: ['AppImage'],
    category: 'Utility',
    icon: 'assets/icon.png',
  },
};
