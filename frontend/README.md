# ScanTrue frontend

Base de la extensión Chrome/Chromium Manifest V3. El popup usa React y Tailwind CSS; el content script y el service worker están escritos en JavaScript nativo. Las pantallas se completarán una por una según sus planes dentro de esta carpeta.

## Preparar y compilar

Se necesita Node.js 20.19 o superior compatible con `package.json`.

```powershell
cd D:\ScanTrue\frontend
npm install
npm run build
```

La compilación genera `dist/` con `manifest.json`, `popup.html`, recursos locales y `extension/service-worker.js` y `extension/content-script.js`. `dist/` se vuelve a crear al compilar y no se edita directamente.

## Cargar en Chrome

1. Abrir `chrome://extensions` y activar el modo de desarrollador.
2. Elegir **Cargar descomprimida** y seleccionar `D:\ScanTrue\frontend\dist`.
3. Abrir el icono ScanTrue. P01 muestra el estado real de `/salud`, permite navegar dentro del popup e inicia la selección de texto en la pestaña activa.

Después de volver a compilar, pulsar **Recargar** en la tarjeta de ScanTrue dentro de `chrome://extensions` y cerrar cualquier popup anterior antes de abrirlo de nuevo.

## Estructura de carpetas

Se omiten las carpetas generadas `dist/` y `node_modules/`.

```text
frontend/
├── README.md
├── SISTEMA_DISENO.md
├── package.json
├── package-lock.json
├── popup.html
├── vite.config.js
├── public/
│   ├── manifest.json
│   └── popup-fallback.css
├── scripts/
│   └── build-extension.mjs
├── src/
│   ├── extension/
│   │   ├── account.js
│   │   ├── analysis.js
│   │   ├── content-script.js
│   │   ├── history.js
│   │   ├── metrics.js
│   │   └── service-worker.js
│   ├── popup/
│   │   ├── assets/
│   │   │   └── scantrue-mark.svg
│   │   ├── components/
│   │   │   ├── PasswordVisibilityButton.jsx
│   │   │   └── ResultGaugePanel.jsx
│   │   ├── screens/
│   │   │   ├── AccountScreen.jsx
│   │   │   ├── BreakdownScreen.jsx
│   │   │   ├── HistoryDetailScreen.jsx
│   │   │   ├── HistoryScreen.jsx
│   │   │   ├── LoginScreen.jsx
│   │   │   ├── MetricsScreen.jsx
│   │   │   ├── RegisterScreen.jsx
│   │   │   └── ResultScreen.jsx
│   │   ├── App.jsx
│   │   ├── extension-message.js
│   │   ├── history-presentation.js
│   │   ├── main.jsx
│   │   ├── metrics-presentation.js
│   │   ├── result-presentation.js
│   │   └── styles.css
│   └── shared/
│       └── api.js
├── referencias/
│   └── imágenes de referencia de las pantallas
└── tests/
    ├── account.test.js
    ├── analysis.test.js
    ├── breakdown-presentation.test.js
    ├── extension-message.test.js
    ├── history-api.test.js
    ├── history-presentation.test.js
    ├── metrics.test.js
    ├── result-presentation.test.js
    └── selection.test.js
```
