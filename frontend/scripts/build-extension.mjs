import { build } from 'esbuild';

await build({
  entryPoints: {
    'service-worker': 'src/extension/service-worker.js',
    'content-script': 'src/extension/content-script.js',
  },
  outdir: 'dist/extension',
  entryNames: '[name]',
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: 'chrome120',
  minify: true,
  logLevel: 'info',
});
