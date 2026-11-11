# Teoría básica del entrenamiento de un BiLSTM

> **Nota (10 nov 2026):** este documento explica la teoría del entrenamiento del BiLSTM de producción. Los scripts que menciona (`preentrenados/entrenar.py`, `entrenar_baseline.py`…) se retiraron y están en el historial de Git (commit `d4ece74`); la arquitectura y el tokenizador siguen en `bilstm/modelo.py`, y el modelo está en `datasets/bilstm_produccion/`. El entrenamiento actual es `bilstm/entrenar.py`.

## ¿Qué significa entrenar?

Entrenar un modelo consiste en mostrarle ejemplos de texto con sus etiquetas correctas —en este proyecto, falsa o real— para que ajuste sus parámetros y aprenda patrones asociados con cada clase. El objetivo es que pueda clasificar textos nuevos, no solo memorizar los ejemplos vistos.

## Datos: entrenamiento, validación y prueba

Antes de entrenar, los datos se separan en conjuntos con funciones distintas:

- **Entrenamiento:** los ejemplos que el modelo usa para aprender y actualizar sus parámetros.
- **Validación:** ejemplos que no actualizan los parámetros. Sirven para comparar versiones del modelo, elegir cuándo detener el entrenamiento y ajustar decisiones de configuración.
- **Prueba:** ejemplos reservados para medir el rendimiento final. Conviene usarlos al final; si se consultan repetidamente para elegir configuraciones, dejan de ser una evaluación independiente.

Una separación adecuada evita que el modelo sea evaluado con textos que ya vio durante el aprendizaje. También es importante evitar que copias o noticias casi idénticas queden repartidas entre conjuntos.

## De palabras a predicciones

El modelo convierte el texto en una secuencia de tokens y luego en números o vectores que la red puede procesar. Una LSTM lee la secuencia en orden; una **BiLSTM** la procesa en dos direcciones, de izquierda a derecha y de derecha a izquierda. Con esa información produce una predicción para las clases.

El modelo compara su predicción con la etiqueta correcta mediante una **función de pérdida**, que mide el error. La retropropagación calcula cómo contribuyeron los parámetros a ese error y un **optimizador** los ajusta para intentar reducirlo.

## Lotes y épocas

Los ejemplos suelen procesarse en grupos llamados **lotes** (*batches*). Con un lote de 32, por ejemplo, el modelo procesa hasta 32 textos y después realiza una actualización de sus parámetros.

Una **época** es una pasada completa por todos los ejemplos de entrenamiento. El entrenamiento puede durar varias épocas para que el modelo ajuste sus parámetros gradualmente. Más épocas no siempre son mejores: el modelo puede empezar a memorizar los datos de entrenamiento y perder capacidad para generalizar.

## Validación, parada temprana y checkpoint

Al final de cada época se puede medir una métrica en validación. Si mejora, se guarda esa versión del modelo. Si deja de mejorar durante varias épocas, la **parada temprana** (*early stopping*) detiene el entrenamiento, según una paciencia definida. Esto ayuda a evitar seguir entrenando cuando la mejora ya se estancó o el modelo empieza a sobreajustarse.

Un **checkpoint** es una captura guardada del estado del entrenamiento o del modelo en un momento determinado. Normalmente contiene los parámetros aprendidos (los pesos); para poder volver a usar el modelo también puede guardar información necesaria para interpretarlos, como el vocabulario, las dimensiones de la red y los límites de entrada. Cargar un checkpoint permite continuar desde un estado guardado o hacer predicciones sin entrenar de nuevo. En este proyecto, el `mejor_modelo.pt` guarda el checkpoint seleccionado durante el entrenamiento junto con vocabulario y configuración.

## Semillas y variación entre corridas

La **semilla** (*seed*) inicializa las elecciones aleatorias del proceso, como los pesos iniciales y el orden de los ejemplos. Usar la misma semilla facilita repetir y comparar una corrida. Sin embargo, no siempre garantiza resultados idénticos: también pueden influir el hardware, las versiones de las bibliotecas y operaciones no deterministas.

Por eso, en experimentos se pueden entrenar varias corridas con distintas semillas. La variación entre ellas muestra cuánto depende el resultado de la inicialización y del azar de esa corrida.

## Hiperparámetros importantes

Los **hiperparámetros** son decisiones configuradas antes o durante el entrenamiento; el modelo no las aprende directamente de los ejemplos. Algunos de los más comunes son:

- **Tasa de aprendizaje (*learning rate*):** determina el tamaño de los ajustes de parámetros. Una tasa muy alta puede volver inestable el aprendizaje; una muy baja puede hacerlo lento.
- **Tamaño de lote (*batch size*):** cuántos ejemplos se procesan antes de cada actualización. Afecta el uso de memoria y el comportamiento del entrenamiento.
- **Número máximo de épocas y paciencia:** ponen un límite al entrenamiento y definen cuándo detenerlo si la validación deja de mejorar.
- **Dimensiones de la red:** determinan el tamaño de sus representaciones y parte de su capacidad para aprender patrones.
- **Longitud máxima del texto:** limita cuántos tokens se procesan por noticia; el texto puede truncarse si es más largo.

Estos valores se comparan usando entrenamiento y validación. La prueba se reserva para la evaluación final.

## Sobreajuste y generalización

Hay **sobreajuste** cuando el modelo aprende demasiado bien los ejemplos de entrenamiento —incluso detalles particulares— pero no mejora en textos que no vio. La generalización es su capacidad para funcionar en ejemplos nuevos. Para estimarla se necesitan buenas particiones y una prueba reservada que represente, en lo posible, el uso esperado.

En resumen: **entrenamiento ajusta los parámetros; validación ayuda a elegir la versión y el momento de parar; la prueba estima el rendimiento final; y un checkpoint conserva una versión del modelo para retomarla o usarla después.**

---

# Cómo se aplica en nuestra implementación

Esta parte describe el BiLSTM independiente con fastText que está guardado en `datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/` y que carga el backend. No debe confundirse con los otros experimentos BiLSTM de `bilstm/` ni con mBERT.

## ¿Por qué usamos PyTorch?

**PyTorch** es la biblioteca de aprendizaje automático con la que está implementado y entrenado este modelo. Proporciona los componentes que el código necesita: tensores para representar lotes de datos, capas de embeddings y LSTM, cálculo de la pérdida, retropropagación de gradientes, optimizadores como AdamW y herramientas para usar GPU con CUDA.

En esta implementación, `torch.nn` define la red y la pérdida; `torch.utils.data` organiza los ejemplos en lotes; y el optimizador de `torch.optim` actualiza los parámetros. PyTorch calcula automáticamente cómo fluye el gradiente por la red, así que el código puede centrarse en definir el modelo y el ciclo de entrenamiento. También permite guardar los parámetros en un checkpoint y volver a cargarlos para inferencia.

Se eligió porque encaja directamente con la arquitectura BiLSTM y con el uso de GPU que ya requiere el proyecto. No es una propiedad del algoritmo BiLSTM: la misma idea podría programarse con otra biblioteca, pero habría que reimplementar o adaptar esos componentes. La configuración registrada para el checkpoint indica PyTorch `2.14.1+cu130` y runtime CUDA `13.0`; para reproducir exactamente la corrida importa conservar una versión compatible de PyTorch y CUDA.

## 1. Qué datos entran

El entrenamiento registrado usó `pequeno_mejorado`: **3.066 textos de entrenamiento y 170 de validación**. El entrenamiento aprende los parámetros; la validación sirve para escoger la época. La configuración del checkpoint dice `validation_only: true`, así que esa corrida **no leyó ni evaluó la partición de prueba**. La evaluación posterior de prueba y fuentes reservadas se documentó por separado.

Las etiquetas son `0 = falsa` y `1 = real`. El modelo recibe la columna de texto; los metadatos como la fuente permiten analizar resultados por grupos, pero no son la entrada textual que aprende la red.

El entrenador lee y comprueba las particiones en `load_splits()`, dentro de `bilstm/entrenar.py`. Entre otras cosas, verifica que haya ambas etiquetas, textos no vacíos y grupos de duplicados separados entre conjuntos. En `preentrenados/entrenar.py`, la llamada `load_splits(args.input, include_test=False)` expresa que este entrenamiento concreto usa entrenamiento y validación, sin abrir prueba.

## 2. Cómo construimos la entrada

En `bilstm/entrenar_baseline.py`, el código exacto del tokenizador y del vocabulario es:

```python
def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


def build_vocab(texts: pd.Series, max_size: int = 30000) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(tokenize(text))
    vocab = {"<pad>": 0, "<unk>": 1}
    for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:max_size - 2]:
        vocab[word] = len(vocab)
    return vocab
```

Esto normaliza mayúsculas/minúsculas y extrae secuencias de palabras y números. Después `build_vocab()` cuenta palabras **solo en los textos de entrenamiento** y les asigna identificadores. El vocabulario reserva `0` para relleno (`<pad>`) y `1` para palabras desconocidas (`<unk>`). Así, una palabra nueva que no aparecía en entrenamiento todavía puede representarse.

`NewsDataset` convierte cada noticia en identificadores y conserva como máximo **192 tokens**. El código es:

```python
class NewsDataset(Dataset):
    def __init__(self, frame: pd.DataFrame, vocab: dict[str, int], max_len: int):
        self.ids = []
        self.labels = frame.etiqueta.astype(int).tolist()
        self.sources = frame.dataset.tolist()
        for text in frame.texto:
            tokens = tokenize(text)[:max_len]
            self.ids.append([vocab.get(word, 1) for word in tokens] or [1])

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, index: int):
        return self.ids[index], self.labels[index], self.sources[index]


def collate(batch):
    lengths = torch.tensor([len(row[0]) for row in batch], dtype=torch.long)
    width = int(lengths.max())
    ids = torch.zeros((len(batch), width), dtype=torch.long)
    for i, (sequence, _, _) in enumerate(batch):
        ids[i, :len(sequence)] = torch.tensor(sequence, dtype=torch.long)
    labels = torch.tensor([row[1] for row in batch], dtype=torch.long)
    return ids, lengths, labels, [row[2] for row in batch]
```

Si una noticia es más larga que `max_len`, se corta por el final. En el entrenamiento registrado `max_len` vale 192. Si una noticia es más corta, `collate()` agrega relleno hasta igualar las longitudes dentro del lote. `pack_padded_sequence()` hace que la LSTM ignore ese relleno al recorrer cada secuencia.

### ¿Por qué 192 tokens y no más o menos?

Un token aquí es una palabra o número encontrado por la expresión regular, no un carácter ni necesariamente una palabra lingüística con subpartes. El límite controla cuánta noticia puede leer la red. Si se fija demasiado bajo, se pierde contexto que aparece después del corte; si se fija muy alto, aumenta el cálculo y la memoria, y también puede entrar mucho texto irrelevante o ruidoso.

En el modelo registrado se eligieron 192 tokens como configuración de esa experiencia. No debe interpretarse como un óptimo demostrado para todos los corpus. Para decidir rigurosamente si conviene 128, 192, 256 u otra longitud, se entrenan variantes manteniendo iguales los datos, la arquitectura y las demás opciones, y se comparan con la misma validación (idealmente varias semillas). La longitud se selecciona con validación, no mirando repetidamente la prueba. En inferencia, backend también recorta la entrada a `max_len` guardado en el checkpoint, para que use el mismo límite que el entrenamiento.

## 3. Qué red se entrena

La clase `BiLSTM` está definida en `bilstm/entrenar_baseline.py`. Este es el código exacto de la clase:

```python
class BiLSTM(nn.Module):
    def __init__(self, vocab_size: int, embedding_dim: int = 128,
                 hidden_dim: int = 64, dropout: float = 0.3):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
        self.lstm = nn.LSTM(embedding_dim, hidden_dim, batch_first=True,
                            bidirectional=True)
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_dim * 2, 2)

    def forward(self, ids: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        embedded = self.embedding(ids)
        packed = pack_padded_sequence(embedded, lengths.cpu(), batch_first=True,
                                      enforce_sorted=False)
        _, (hidden, _) = self.lstm(packed)
        representation = torch.cat((hidden[-2], hidden[-1]), dim=1)
        return self.classifier(self.dropout(representation))
```

Cada palabra se transforma en un vector. La LSTM bidireccional procesa la noticia de izquierda a derecha y de derecha a izquierda. Se concatenan los estados finales de las dos direcciones y una capa lineal produce dos puntuaciones, para falsa y real.

En el modelo seleccionado, los vectores de palabras tienen **300 dimensiones** y el estado oculto tiene **64 por dirección**. Los embeddings se inicializan con fastText Common Crawl en español (`cc.es.300.vec.gz`): eso significa que parten de vectores aprendidos previamente a partir de mucho texto en español. El entrenador busca en ese archivo las palabras del vocabulario. Este es el código exacto que realiza esa carga:

```python
def load_vectors(path: Path, vocab: dict[str, int], model: BiLSTM) -> dict:
    """Busca solo las palabras del entrenamiento, sin cargar el archivo entero en RAM."""
    opener = gzip.open if path.suffix == ".gz" else open
    dimension = model.embedding.embedding_dim
    wanted = set(vocab) - {"<pad>", "<unk>"}
    found: set[str] = set()
    malformed = 0
    with opener(path, "rt", encoding="utf-8", errors="replace") as stream:
        header = stream.readline().strip().split()
        if len(header) != 2 or not all(part.isdecimal() for part in header):
            raise ValueError("El archivo de vectores necesita cabecera 'palabras dimensiones'")
        if int(header[1]) != dimension:
            raise ValueError(f"Vectores de {header[1]} dimensiones; modelo de {dimension}")
        with torch.no_grad():
            for line in stream:
                word, separator, values = line.partition(" ")
                if not separator or word not in wanted or word in found:
                    continue
                vector = np.fromstring(values, sep=" ", dtype=np.float32)
                if vector.size != dimension or not np.isfinite(vector).all():
                    malformed += 1
                    continue
                model.embedding.weight[vocab[word]].copy_(torch.from_numpy(vector))
                found.add(word)
                if len(found) == len(wanted):
                    break
    return {"vocabulario": len(wanted), "vectores_encontrados": len(found),
            "cobertura": len(found) / len(wanted) if wanted else 0.0,
            "lineas_invalidas_relevantes": malformed,
            "sin_vector": len(wanted) - len(found)}
```

La función recorre el archivo comprimido línea por línea y solo conserva en memoria los vectores de las palabras que necesita el vocabulario. Verifica que la dimensión del archivo coincida con la capa embedding y que los valores sean finitos. La asignación clave es `model.embedding.weight[vocab[word]].copy_(torch.from_numpy(vector))`: copia el vector fastText a la fila del embedding asociada a esa palabra. `torch.no_grad()` indica que esta inicialización no debe crear historial de gradientes. Después, durante el entrenamiento, estos pesos forman parte de `model.parameters()` y el optimizador puede ajustarlos; el código no los congela.

La corrida registró cobertura de **27.716 de 29.998 palabras (92,4 %)**. Las palabras sin vector mantienen la inicialización inicial de la capa y también pueden aprenderse durante el entrenamiento.

La construcción del modelo y la llamada al cargador en el entrenador son, literalmente:

```python
vocab = build_vocab(frames["entrenamiento"].texto, max_size=args.vocab_size)
model = BiLSTM(len(vocab), 300, args.hidden_dim, args.dropout)
coverage = load_vectors(args.embeddings, vocab, model)
print(f"Cobertura de vectores: {coverage['vectores_encontrados']}/"
      f"{coverage['vocabulario']} ({coverage['cobertura']:.1%})", flush=True)
if coverage["cobertura"] < args.min_coverage:
    raise ValueError("Cobertura inferior al mínimo solicitado")
device = torch.device(args.device)
model.to(device)
```

Primero se crea el vocabulario desde entrenamiento; luego se crea la red con dimensión de embedding 300; después se copian los vectores disponibles a la capa correspondiente y se valida que la cobertura supere el mínimo configurado. Finalmente, la red se mueve al dispositivo elegido, en esta corrida CUDA.

## 4. Qué ocurre en cada lote y cada época

Este es el ciclo exacto del lote en `train()` de `bilstm/preentrenados/entrenar.py`:

```python
for ids, lengths, labels, _ in loaders["entrenamiento"]:
    optimizer.zero_grad(set_to_none=True)
    scores = model(ids.to(device), lengths)
    loss = criterion(scores, labels.to(device))
    loss.backward()
    nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    optimizer.step()
    total_loss += loss.item() * len(labels)
```

Primero el modelo predice para el lote; `CrossEntropyLoss` compara las puntuaciones con las etiquetas; `backward()` calcula los gradientes; el recorte limita su magnitud a 1 para reducir actualizaciones extremas; y AdamW aplica la actualización. `zero_grad()` limpia los gradientes del lote anterior antes de comenzar el siguiente.

La pérdida usa **pesos de clase** calculados a partir del balance de etiquetas del entrenamiento. Esto da más peso a la clase menos frecuente para que el aprendizaje no favorezca simplemente a la clase mayoritaria.

El código que configura la semilla, los lotes, pesos de clase, pérdida, optimizador y scheduler en este entrenador es:

```python
frames, hashes = load_splits(args.input, include_test=False)
set_seed(args.seed)
vocab = build_vocab(frames["entrenamiento"].texto, max_size=args.vocab_size)
model = BiLSTM(len(vocab), 300, args.hidden_dim, args.dropout)
coverage = load_vectors(args.embeddings, vocab, model)
device = torch.device(args.device)
model.to(device)
data = {name: NewsDataset(frame, vocab, args.max_len) for name, frame in frames.items()}
loaders = {
    name: DataLoader(dataset, batch_size=args.batch_size,
                     shuffle=(name == "entrenamiento"), collate_fn=collate,
                     generator=torch.Generator().manual_seed(args.seed))
    for name, dataset in data.items()
}
counts = Counter(data["entrenamiento"].labels)
weights = torch.tensor([len(data["entrenamiento"]) / (2 * counts[i]) for i in (0, 1)],
                       dtype=torch.float32, device=device)
criterion = nn.CrossEntropyLoss(weight=weights)
optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max",
                                                       factor=0.5, patience=2)
```

`set_seed()` inicializa los generadores de Python, NumPy y PyTorch. El `generator` de `DataLoader` determina de forma reproducible el barajado de entrenamiento. La definición exacta de `set_seed()` es:

```python
def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
```

Una vez procesados todos los lotes, se evalúa la validación. El programa registra la pérdida de entrenamiento y métricas como F1 macro. `ReduceLROnPlateau` reduce la tasa de aprendizaje si el F1 macro deja de mejorar; si no hay mejora suficiente durante la paciencia establecida, la parada temprana termina la corrida.

El bloque exacto de validación y selección del checkpoint es:

```python
actual, predicted, _ = predict(model, loaders["validacion"], device)
validation = metrics(actual, predicted)
scheduler.step(validation["f1_macro"])
history.append({"epoch": epoch,
                "train_loss": total_loss / len(data["entrenamiento"]),
                "validation": validation})
(args.output / "historial.json").write_text(
    json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Época {epoch}: F1 macro {validation['f1_macro']:.4f}, "
      f"F1 falsa {validation['f1_falsa']:.4f}", flush=True)
if validation["f1_macro"] > best_f1 + args.min_delta:
    best_f1, best_epoch, stale = validation["f1_macro"], epoch, 0
    checkpoint = {
        "state_dict": {key: value.detach().cpu().clone()
                       for key, value in model.state_dict().items()},
        "vocab": vocab,
        "config": {"max_len": args.max_len, "embedding_dim": 300,
                   "hidden_dim": args.hidden_dim, "dropout": args.dropout,
                   "labels": {0: "falsa", 1: "real"}},
        "best_epoch": best_epoch,
    }
    torch.save(checkpoint, args.output / "mejor_modelo.pt")
else:
    stale += 1
    if stale >= args.patience:
        print("Parada temprana", flush=True)
        break
```

Cada nueva mejora del F1 macro de validación reemplaza `mejor_modelo.pt` con un checkpoint que contiene los pesos de ese momento, vocabulario y configuración. Si no hay mejora, aumenta `stale`; cuando llega a la paciencia, se detiene.

## 5. Cómo se eligió el checkpoint de este modelo

La configuración guardada registra **semilla 42**, hasta **20 épocas**, paciencia **4**, lote **32**, longitud máxima **192**, dropout **0,3**, tasa de aprendizaje **0,001** y weight decay **0,01**. El checkpoint corresponde a la **época 8**, que fue la mejor según el F1 macro de validación de esa corrida. El límite era 20, pero no se necesitó llegar hasta él: la parada temprana decide con base en la validación.

La selección del checkpoint dentro de una corrida y la elección de semilla son decisiones distintas:

- **Época 8** fue la mejor época de esa corrida según validación.
- **Semilla 42** fijó las elecciones aleatorias para realizar esa corrida.
- No significa que se hayan probado 42 semillas ni que se haya llegado hasta la semilla 42 de una secuencia.

### ¿Por qué 42 y no 10 o 100?

**42 no tiene una propiedad matemática que lo haga mejor para entrenar.** Es un valor fijo y reproducible que se eligió para inicializar los aspectos aleatorios y poder repetir la misma receta. Se pudo haber usado 10 o 100: lo importante para reproducir esta corrida es usar el mismo valor junto con los mismos datos, código, configuración y entorno.

En este checkpoint concreto, la documentación registra una corrida con semilla 42; **no registra una comparación controlada entre semillas 10, 42 y 100**. Por tanto, no podemos afirmar que 42 haya ganado frente a 10 o 100. Para saber si la elección de semilla cambia mucho el resultado, habría que entrenar varias semillas —por ejemplo, 10, 42 y 100— manteniendo todo lo demás idéntico, y comparar sus métricas de validación. Conviene informar el promedio y la variación, no quedarse con la semilla que por azar dé el mejor número.

El sufijo `s42` en el nombre `pequeno_mejorado_fasttext_cc300_s42` identifica la semilla usada en esa corrida; `cc300` indica los vectores fastText de 300 dimensiones. No indica el número de épocas ni cuántas corridas se hicieron.

## 6. Qué guarda y cómo se usa

`mejor_modelo.pt` conserva los pesos de la época seleccionada, el vocabulario y la configuración necesaria para reconstruir la red. `config.json` registra además parámetros, particiones, hashes, cobertura de fastText y versiones del entorno; `historial.json` guarda la evolución por época; `resultados.json` conserva el mejor resultado de validación.

El backend carga ese archivo en `backend/models/bilstm.py`, reconstruye la misma arquitectura, carga los pesos y pone el modelo en modo evaluación. Para un texto nuevo aplica el mismo tokenizador y vocabulario, convierte sus primeros 192 tokens en números y calcula `softmax`; la salida de la clase 0 es `probabilidad_falsa`.

## 7. Qué dicen y qué no dicen los resultados

La documentación de este checkpoint reporta F1 macro **0,765 en validación**, **0,774 en prueba interna** y **0,603 en fuentes reservadas**. La evaluación de fuentes reservadas fue exploratoria y se consultó durante el desarrollo. Además, produjo 164 falsas alarmas entre 307 noticias reales de ese conjunto. Esas cifras describen el comportamiento en esos datos: no demuestran el rendimiento futuro en cualquier noticia o medio.

Para mejorar la evidencia, el siguiente experimento debería entrenar varias semillas con la misma partición y receta, guardar cada checkpoint por separado, comparar promedio y dispersión en validación y evaluar una sola vez sobre un conjunto nuevo que no se haya usado para tomar decisiones.

---

# Los tres archivos Python en orden de lectura

Las funciones de cada archivo aparecen aquí en el mismo orden en que se leen de arriba hacia abajo en el código. Al final se muestra aparte la jerarquía de llamadas durante la ejecución del entrenamiento.

## 1. `bilstm/preentrenados/entrenar.py`: punto de entrada y coordinador

Este es el script principal de la corrida fastText. Su bloque final ejecuta `parse_args()` y entrega la configuración a `train()`.

- **`load_vectors(path, vocab, model)`** busca los vectores fastText de las palabras que el modelo conoce y los coloca en su capa de embeddings. Así, el modelo empieza con información aprendida previamente del español en vez de empezar desde cero para todas las palabras. También cuenta cuántas palabras encontró; ese dato permite comprobar si fastText pudo ayudar con una parte suficiente del vocabulario.
- **`train(args)`** organiza el entrenamiento de principio a fin. Prepara los datos y el modelo, carga fastText, y luego le muestra las noticias en lotes para que ajuste sus parámetros. Al terminar cada época revisa cómo le va con textos de validación. Si mejora, guarda esa versión; así se conserva el checkpoint que funcionó mejor durante el entrenamiento. Al final guarda un resumen de la corrida.
- **`parse_args()`** recoge las opciones con las que se quiere ejecutar el entrenamiento, como dónde están los datos, cuántas épocas permitir y qué semilla usar. Sirve para cambiar la configuración desde el comando de ejecución sin modificar la función de entrenamiento.
- **`if __name__ == "__main__":`** indica que la secuencia `train(parse_args())` se ejecuta al lanzar este archivo directamente.

En jerarquía, este archivo decide **qué pasos se ejecutan y en qué orden**. No vuelve a definir todas las utilidades: importa las que ya están en los otros dos módulos.

## 2. `bilstm/entrenar.py`: particiones y reproducibilidad compartidas

El script fastText importa de aquí `load_splits` y `set_seed`. Las funciones se describen en el orden en que aparecen en el archivo. Aunque el archivo también tiene su propio entrenador general, ese `train()` no es el que se ejecuta para el checkpoint fastText.

- **`load_splits(folder, include_test)`** abre los CSV de entrenamiento y validación (y prueba si se solicita) y revisa que tengan los datos esperados. También comprueba que noticias duplicadas no hayan quedado repartidas entre conjuntos. Esto ayuda a que la evaluación sea más justa: el modelo no debería ser probado con una copia de algo que ya vio al entrenar. En la corrida fastText, la prueba no se carga aquí.
- **`set_seed(seed)`** fija el valor que usan las partes aleatorias del entrenamiento. Ayuda a repetir una corrida con la misma configuración y comparar cambios de forma más ordenada; no garantiza que todos los equipos obtengan resultados idénticos.
- **`train(args)`** entrena otro BiLSTM de este proyecto, con embeddings que empiezan desde cero. Sirve para las variantes generales del entrenador. **No es el `train()` que creó el modelo fastText elegido**; ese entrenamiento ocurre en `preentrenados/entrenar.py`.
- **`parse_args()`** recoge las opciones para ese otro entrenador, por ejemplo qué variante y qué archivos usar, el tamaño del modelo y cuántas épocas permitir. Facilita ejecutar configuraciones diferentes desde la consola. El entrenamiento fastText no usa esta función; solo importa `load_splits` y `set_seed` de este archivo.

Su rol en la corrida seleccionada es aportar comprobación de particiones y fijación de semilla; el entrenador fastText lo importa como módulo.

## 3. `bilstm/entrenar_baseline.py`: preparación de texto, red y métricas

Este módulo proporciona las piezas que el entrenador fastText importa para representar los ejemplos y ejecutar la clasificación. Se listan en el orden en que aparecen en el archivo.

- **`tokenize(text)`** separa el texto en palabras y números y pasa todo a minúsculas. Así la palabra “Noticia” y “noticia” se tratan igual y el modelo recibe el texto en un formato constante.
- **`build_vocab(texts, max_size)`** crea la lista de palabras que el modelo podrá reconocer y les asigna números. Se construye con los textos de entrenamiento para que validación no influya en lo que el modelo considera conocido. Las palabras fuera de la lista se convierten en “desconocidas”.
- **`NewsDataset`** prepara cada noticia para que el entrenamiento pueda usarla: convierte sus palabras a números, aplica el límite de tokens y conserva la respuesta correcta (falsa o real). `__len__()` permite saber cuántas noticias hay y `__getitem__()` entrega una noticia cuando el entrenamiento la necesita.
- **`collate(batch)`** junta varias noticias en un lote y completa las más cortas para que tengan el mismo ancho. También guarda la longitud real de cada texto, para que la red pueda ignorar el relleno. Esto permite procesar varias noticias juntas de forma eficiente.
- **`BiLSTM`** describe cómo está formada la red. `__init__()` crea las partes que convierten palabras en vectores, leen el texto en ambas direcciones y producen la clasificación. `forward(ids, lengths)` es el recorrido de una noticia por esas partes y devuelve puntuaciones para falsa y real; durante el entrenamiento esas puntuaciones sirven para calcular el error.
- **`predict(model, loader, device)`** usa el modelo ya entrenado para clasificar los ejemplos, sin cambiar sus parámetros. Se usa para revisar cómo clasifica validación o prueba y comparar las respuestas con las etiquetas correctas.
- **`metrics(actual, predicted)`** resume qué tan bien clasificó el modelo. Incluye métricas para la clase falsa, una medida equilibrada entre ambas clases (F1 macro) y una matriz que muestra aciertos y errores. Ayuda a entender qué tipo de equivocaciones comete, no solo cuántas.
- **`main()`** ejecuta el entrenamiento baseline de comparación cuando se lanza este archivo directamente. Prepara datos y modelo, entrena, evalúa y guarda resultados. **No inicia el entrenamiento del modelo fastText elegido**; el script fastText toma de este archivo las funciones y la arquitectura que necesita.

## Flujo de llamadas durante el entrenamiento

La jerarquía de llamadas para entrenar el modelo elegido queda así:

```text
preentrenados/entrenar.py
└── parse_args()
    └── train(args)
        ├── entrenar.py: load_splits(..., include_test=False)
        ├── entrenar.py: set_seed(args.seed)
        ├── entrenar_baseline.py: build_vocab(...)
        ├── entrenar_baseline.py: BiLSTM(...)
        ├── preentrenados/entrenar.py: load_vectors(...)
        ├── entrenar_baseline.py: NewsDataset(...) y collate(...)
        ├── PyTorch: DataLoader, pérdida, AdamW y scheduler
        ├── entrenar_baseline.py: model.forward(...) y metrics(...)
        └── preentrenados/entrenar.py: guarda mejor_modelo.pt
```

Por eso los tres archivos forman parte de la explicación, pero tienen jerarquías distintas: `preentrenados/entrenar.py` coordina la corrida; `entrenar.py` aporta lectura validada de particiones y semilla; y `entrenar_baseline.py` aporta representación de textos, arquitectura y evaluación.
