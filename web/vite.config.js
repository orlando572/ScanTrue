import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// La web reutiliza la lógica de presentación de la extensión (../frontend/src):
// niveles del resultado, desglose por modelo, fechas y estado de los servicios.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { fs: { allow: ['..'] } },
  build: { outDir: 'dist', emptyOutDir: true },
});
