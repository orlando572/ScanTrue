# ScanTrue frontend

Base de la extensión Chrome/Chromium Manifest V3 (Chrome 116 o posterior). La interfaz se abre en el **panel lateral** de Chrome y usa React y Tailwind CSS; el content script y el service worker están escritos en JavaScript nativo. Las pantallas se completarán una por una según sus planes dentro de esta carpeta.

## Preparar y compilar

Se necesita Node.js 20.19 o superior compatible con `package.json`.

```powershell
cd D:\ScanTrue\frontend
npm install
npm run build
```

La compilación genera `dist/` con `manifest.json`, `sidepanel.html`, `popup.html` (misma App, para volver al popup), recursos locales y `extension/service-worker.js` y `extension/content-script.js`. `dist/` se vuelve a crear al compilar y no se edita directamente.

## Cargar en Chrome

1. Abrir `chrome://extensions` y activar el modo de desarrollador.
2. Elegir **Cargar descomprimida** y seleccionar `D:\ScanTrue\frontend\dist`.
3. Pulsar el icono ScanTrue: se abre el panel lateral. P01 muestra el estado real de `/salud` e inicia el **modo selección** en la pestaña activa.

Después de volver a compilar, pulsar **Recargar** en la tarjeta de ScanTrue dentro de `chrome://extensions` y volver a abrir el panel.

## Selección de fragmentos

- **Modo selección:** «Escoger texto» deja la página en modo selección. Cada texto que se selecciona se añade como fragmento y queda resaltado (CSS Custom Highlight API, sin modificar el HTML). Se puede desplazar la página y seguir marcando. Una barra propia (Shadow DOM) muestra fragmentos y palabras; un clic sobre un resaltado ofrece quitarlo. El modo termina solo con **Terminar selección** (barra o panel).
- **Panel:** P02 lista los fragmentos en vivo y permite quitarlos. Un medidor cuenta **palabras** con el mismo patrón `\b\w+\b` que el backend. **100** es el mínimo de la API (sus «100 tokens» son tokens del BiLSTM, es decir, palabras). La barra se llena hasta **~200**: el BiLSTM lee 192 palabras y BETO 256 subpalabras; medido con el tokenizador de BETO sobre los fragmentos de `datasets/comun_v1` que recorta, 254 subpalabras útiles ≈ 197 palabras (p10–p90: 181–209). Lo que pase de ahí no lo lee ningún modelo.
- **Permiso:** la primera vez que se pulsa «Escoger texto», Chrome pide permiso para leer páginas web (`optional_host_permissions` para http/https). Sin él, el panel —que sigue abierto al navegar— pierde el acceso temporal (`activeTab`) al cambiar de página y no puede marcar texto. Se puede retirar en `chrome://extensions` → ScanTrue → Acceso a sitios.
- Si la pestaña se recarga, navega o se cierra, el modo selección termina solo.
- **Después de analizar** la selección se conserva: **Volver** desde el resultado regresa al texto para editarlo y analizarlo otra vez. **Vaciar** (en P02) o **Escoger otro texto** (en el resultado) empiezan de cero y quitan los resaltados de la página.

## Volver al popup

El panel y el popup cargan la misma App. Para usar el popup, en `public/manifest.json` añadir `"default_popup": "popup.html"` dentro de `action` y recompilar: el service worker lo detecta, desactiva la apertura del panel. El modo selección funciona igual; tras pulsar «Escoger texto» el popup se cierra y la barra de la página sigue activa.

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
