const { defineConfig } = require('vite');
const react = require('@vitejs/plugin-react');
const esbuild = require('esbuild');

const jsxInJs = () => ({
  name: 'jsx-in-js',
  enforce: 'pre',
  async transform(code, id) {
    if (!id || !id.endsWith('.js')) return null;
    if (id.includes('node_modules')) return null;
    // Normalize for Windows + POSIX paths.
    if (!(id.includes('/src/') || id.includes('\\src\\'))) return null;

    const result = await esbuild.transform(code, {
      loader: 'jsx',
      jsx: 'automatic',
      sourcemap: true,
      sourcefile: id,
    });

    return {
      code: result.code,
      map: result.map,
    };
  },
});

module.exports = defineConfig({
  base: '/training/',
  plugins: [jsxInJs(), react()],
  build: {
    outDir: 'build',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  },
});
