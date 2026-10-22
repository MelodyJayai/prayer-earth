const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*'],
    rules: {
      // Expo 57 currently ships TypeScript 6; eslint-plugin-import's namespace
      // resolver still attempts to load the parser through its legacy path.
      'import/namespace': 'off',
    },
  },
]);
