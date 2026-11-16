# Web y panel de la verificación (incremento 2, Fase 6)

Documento de la Fase 6 de [PLAN_INCREMENTO_2.md](PLAN_INCREMENTO_2.md) (secciones 4.7 y 6). Se comprobó el 15 nov 2026 con la API real, el Supabase de desarrollo, `llama-server` con Q8_0 y el navegador. **La verificación sigue apagada por omisión** (`VERIFICATION_ENABLED`): hasta que la Fase 7 ajuste la regla de conclusión, no debe encenderse donde el público vea resultados.

## 1. Qué hay

### API

| Ruta | Acceso | Qué hace |
| --- | --- | --- |
| `GET /admin/verificacion` | Admin | Casos pendientes, en proceso, fallidos y completados; duración media; si el LLM responde; si hay trabajador y si está en pausa. |
| `POST /admin/casos/{id}/verificacion/reintentar` | Admin | Devuelve a la cola una verificación **fallida** (con los intentos a cero) o **en espera** (la adelanta para que se intente ya). Responde el caso actualizado. |
| `POST /admin/verificacion/pausar` y `/reanudar` | Admin | Detiene o reanuda el trabajador de esta API; la cola se conserva. |
| `GET /admin/casos?verificacion=…` | Admin | Filtro nuevo en el panel: las cuatro conclusiones, `sin_verificar` y los estados `pendiente`, `en_proceso` y `fallida`. |
| `GET /salud` | Público | Añade `llm: {configurado, disponible}`. El `estado` (`ok`/`degradado`) y `modelos` no cambian: un LLM caído no degrada el análisis rápido. |

- `GET /publico/analisis` y `…/{id}` **no cambian de contrato**: `verificacion_web` ya traía estado, conclusión, resumen, afirmaciones y fuentes. Se comprobó que no filtran `intentos`, `ultimo_error` ni los tiempos (solo los ve el panel, en `seguimiento_verificacion`).
- `POST …/reintentar` responde 404 si el caso no tiene fila de verificación y 409 si está `en_proceso` o `completada`. El cambio se hace con un filtro por estado, así que si el trabajador reservó el caso un instante antes, no se pisa.
- `POST /admin/verificacion/pausar` y `/reanudar` responden 409 `verificacion_apagada` si el trabajador no está encendido en ese servidor.
- **La pausa vive en memoria**: si se reinicia la API, el trabajador vuelve a correr mientras `VERIFICATION_ENABLED` siga encendido. No hay interruptor persistente.
- El estado del LLM es una consulta ligera a `GET /models` (con la clave), con 1,5 s de espera máxima y un resultado que se recuerda 15 s: `/salud` la usa la extensión con frecuencia y un LLM caído no puede frenarla (`backend/services/llm_status.py`).
- **Sin migración nueva:** los conteos y el reintento usan PostgREST directamente. La duración media es la de los últimos 200 casos completados con búsqueda propia (sin las copias de otro análisis).
- Los cinco conteos del estado de la cola se piden a la vez: en las pruebas bajaron de 1,5–3 s a 0,3–1,1 s por consulta.

### Web

- **Tablero del panel:** bloque «Verificación web» con el trabajador (activo, en pausa o apagado), el LLM (responde, no responde o sin configurar), los casos por estado, la duración media, el botón **Pausar / Reanudar** y enlaces a las fallidas y a las que esperan. Se actualiza cada 10 s. Si el trabajador está apagado lo dice y no muestra el botón.
- **Casos del panel:** filtro «Verificación web», etiqueta del estado en cada fila de la lista y, en el detalle, el seguimiento (intentos, causa de la falla en lenguaje claro, próximo intento, duración, instrucciones usadas) con el botón **Reintentar la verificación** (o **Intentar ahora** si espera su turno).
- **Detalle público y del panel:** el panel «Verificación web» ahora muestra, por cada afirmación, su veredicto (respaldada, contradicha, fuera de contexto, sin evidencia suficiente) y si se reutilizó una verificación anterior, y por cada fuente su dominio, la fecha de consulta y **la cita literal**. Los casos en cola, en proceso o fallidos explican qué pasa. El panel ocupa todo el ancho de la fila cuando tiene contenido (en una tercera columna quedaba estrecho). Debajo del resumen dice que lo redactó un modelo de lenguaje y puede equivocarse: **lo comprobable son las afirmaciones y sus fuentes** (por lo medido en la Fase 5).
- **Portada pública:** un contador «Verificados con fuentes» que solo aparece cuando hay verificaciones completadas.

## 2. Qué se comprobó con datos reales

El Supabase de desarrollo ya tenía casos completados, fallidos y uno en proceso de las fases 2 a 5 (casi todos de prueba). Para ver **cada estado y cada conclusión** se dejaron cinco casos más, **marcados con `modelo_llm = prueba-fase-6`**:

| Caso | De dónde sale |
| --- | --- |
| `respaldada` | Las 3 afirmaciones «apoyada» del caso real de García Márquez de la Fase 5, con sus fuentes y citas reales. Resumen: plantilla del backend. |
| `fuera_de_contexto` | Dos afirmaciones «fuera de contexto» reales del caso del puente (Fase 5) y una «apoyada»; resumen de plantilla. |
| `pendiente` | Un caso de prueba tras una falla del LLM, con su próximo intento en 30 min. |
| `en_proceso` | Un caso de prueba con la reserva vigente. |
| `fallida` | Un caso de prueba con la causa «se agotó el cupo de la búsqueda». |

`contradicha` y `evidencia_insuficiente` son resultados reales de la Fase 5 (qwen3-4b-instruct-2507). La conclusión `respaldada` y `fuera_de_contexto` casi no salen del LLM con la regla actual, por eso se arman así: **no son una muestra de lo que producirá el sistema**.

**Filtros contra la base** (comparando los casos que devuelve la API con los de la tabla): `respaldada` 25 de 25, `contradicha` 7 de 7, `fuera_de_contexto` 1 de 1, `evidencia_insuficiente` 34 de 34, `sin_verificar` 2 de 2, y en el panel `pendiente` 1 de 1, `en_proceso` 1 de 1, `fallida` 6 de 6.

**En el navegador** (escritorio y móvil de 375 px): el detalle público de un caso `respaldada` y de otro `fuera_de_contexto` (afirmaciones con veredicto y fuentes con cita), el de un caso `fallida`, el tablero con el LLM caído y con el LLM respondiendo, el filtro por «Fallida» con 6 casos, **pausar y reanudar** (el trabajador pasa a «en pausa» y vuelve), el tablero con el trabajador apagado, y **reintentar** un caso fallido: volvió a `pendiente`, el trabajador real lo tomó solo y lo dejó `completada` con `evidencia_insuficiente` (el texto de prueba no tenía afirmaciones).

Pruebas nuevas: 27 en el backend (26 en `test_verification_admin.py`: filtros, columnas del panel, conteos, reintento, pausa, rutas, sonda del LLM y `/salud`; 1 en `test_case.py`, el plural de la plantilla; 316 en total) y 7 en la web (presentación de afirmaciones, fuentes, los cuatro estados y las cuatro conclusiones, seguimiento, cola y filtros; 16 en total). La extensión (81) y `datos_comunes` siguen pasando.

## 3. Cambios fuera de lo que pedía el plan

- **`seguimiento_verificacion`** en los casos del panel y **el filtro por estado** en `/admin/casos`: el plan no los nombra, pero sin ellos el panel no puede mostrar la causa de una falla ni listar las fallidas.
- **Reintentar también adelanta un caso `pendiente`** (la espera puede ser de 15 min y se quiere probar tras reiniciar el LLM). No reintenta lo `completado`: eso destruiría un resultado publicado, y con coincidencia exacta en la base volvería a dar lo mismo.
- **Arreglo de la Fase 5 que salió aquí:** el resumen de plantilla decía «3 respaldada por fuentes»; ahora concuerda («3 respaldadas por fuentes»).

## 4. Lo que no se resolvió o no se midió

- **Textos de la portada.** Siguen diciendo que la verificación web es «Próximamente»; se cambian cuando se decida encenderla (después de la Fase 7). Lo mismo con `web/README.md`, que aún dice que la verificación no existe (Fase 8).
- **Autenticación real del panel.** Se probó con la API local con la comprobación de administrador sustituida por una cuenta de prueba **solo en ese proceso de prueba** (no en el repositorio); no se entró con una cuenta ni contraseña reales. El código que valida el rol no cambió.
- **La pausa no persiste** y no hay botón para reintentar varios casos a la vez.
- **Casos reales con `fuera_de_contexto`:** la web los muestra bien, pero la calidad del veredicto es la que midió la Fase 4 (poco fiable) y la regla de conclusión es la de la Fase 5 (una sola contradicción decide el caso): lo de la Fase 7.
- **Rendimiento con muchos casos:** el conteo por estado hace una consulta por estado; con la base de desarrollo (77 análisis) tarda menos de 1,2 s, no se midió con miles.
- **La web no se probó con lector de pantalla**; las etiquetas nuevas llevan texto y `aria` como el resto, y la lista de afirmaciones y fuentes son listas ordenadas.

## 5. Cómo repetirlo

Guiones en la carpeta temporal de la sesión (no están en el repositorio): `f6_sembrar.py` (deja los cinco casos de prueba), `f6_api.py` (levanta la API con `.env.desarrollo`, el trabajador encendido y el administrador de prueba; `F6_VERIF=false` para verla apagada). Con la API en `127.0.0.1:8000` y `npm run dev` en `web/`, para entrar al panel basta guardar en `sessionStorage` una sesión de prueba (`scantrue.admin`). Necesita `llama-server` levantado como en [MEDICIONES_LLM.md](MEDICIONES_LLM.md).
