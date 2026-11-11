## ScanTrue: 4 incrementos

### 1. Plataforma web de resultados y administración
- **Qué hace:** muestra al usuario la página analizada, el fragmento, la predicción rápida y la verificación posterior. El administrador filtra casos, revisa evidencias, compara versiones de modelos, activa una y vuelve a la anterior.
- **Cómo:** guarda por separado el fragmento original y el texto recortado que recibió cada modelo.
- **Equipo:** RTX 3050 (backend y base de datos).
- **ML:** ninguno. Gestión de versiones de modelos.

### 2. Verificación diferida con LLM y búsqueda web
- **Qué hace:** contrasta el resultado rápido con fuentes externas.
- **Cómo:**
  1. BiLSTM y mBERT dan el resultado rápido.
  2. Una cola toma el caso y Qwen 4B extrae las afirmaciones.
  3. Se consulta primero la base de verificaciones anteriores y luego internet (búsqueda hecha por el backend).
  4. Qwen compara y concluye: respaldada, contradicha, fuera de contexto o evidencia insuficiente, con fuentes.
- **Equipo:** LLM en la RTX 5060 como servidor de API; búsqueda y cola en el backend.
- **ML:** LLM cuantizado a 4 bits, uso de herramientas (*tool use*), razonamiento sobre evidencia.

### 3. Revisión de resultados y creación de datasets
- **Qué hace:** convierte los análisis en datos de calidad.
- **Cómo:** el administrador aprueba, corrige o descarta cada conclusión. Los casos aprobados pasan a una versión del dataset con etiqueta, procedencia y evidencia. Se priorizan los casos donde BiLSTM y mBERT discrepan, y se separan duplicados y noticias del mismo evento entre entrenamiento y prueba.
- **Equipo:** interfaz web y backend.
- **ML:** aprendizaje activo, humano en el bucle, control de calidad de etiquetas.

### 4. Entrenamiento, evaluación y mejora
- **Qué hace:** mejora los modelos y comprueba si el nuevo supera al actual.
- **Cómo:** el administrador elige dataset y parámetros; un proceso separado entrena y muestra progreso y métricas; se compara el candidato con el activo y se decide si activarlo.
  - **4A (núcleo):** BiLSTM y mBERT, con calibración, salida "resultado incierto" y, si aporta, un tercer clasificador compacto. Corre en la RTX 3050.
  - **4B (opcional, final):** fine-tuning de Qwen 4B con QLoRA, cuando haya suficientes casos aprobados. Corre en la RTX 5060 con las verificaciones en pausa.
- **ML:** aprendizaje supervisado, transfer learning, calibración, métricas F1, LoRA/QLoRA.

### Ciclo que los une
```
Clasificar → Verificar (2) → Revisar (3) → Reentrenar (4) → Activar en la web (1) → Clasificar mejor
```
