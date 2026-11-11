# Flujo principal de un análisis en ScanTrue

Este documento muestra **solo el recorrido principal de una noticia**. Cada fragmento es literal y se indica su archivo y la función o método que lo contiene. Cada explicación resume qué recibe, qué hace y qué devuelve.

## 1. La extensión envía el texto

**Fragmento de `performAnalysis()`**, en [`frontend/src/extension/analysis.js`](../../frontend/src/extension/analysis.js). Recibe el texto seleccionado o editado y una URL opcional. Envía ambos a `POST /analisis` con el token de sesión y espera la respuesta.

```javascript
    let response = await request('/analisis', {
      method: 'POST',
      headers: { Authorization: `Bearer ${session.access_token}` },
      body: JSON.stringify({ texto: selection.text, url: selection.url ?? null }),
    });
```

## 2. La API prepara los modelos y recibe la noticia

**Fragmento de `lifespan()`**, en [`backend/app.py`](../app.py). Al iniciar el backend, crea los predictores y los entrega a `AnalysisService`, que queda disponible para las peticiones. Los checkpoints se cargan una vez, no por cada noticia. Si mBERT falla al cargar, BiLSTM puede seguir disponible.

```python
    try:
        analysis_settings = AnalysisSettings.from_environment()
        bilstm_predictor = BilstmPredictor()
        try:
            mbert_text_policy = MbertTokenizer()
        except Exception:
            logger.exception("No se pudo cargar el tokenizador mBERT")
            mbert_text_policy = None
        try:
            mbert_predictor = (
                MbertPredictor(mbert_text_policy) if mbert_text_policy else None
            )
        except Exception:
            logger.exception("No se pudo cargar el checkpoint mBERT")
            mbert_predictor = None
        app.state.analysis_service = AnalysisService(
            bilstm_predictor,
            mbert_predictor=mbert_predictor,
            mbert_text_policy=mbert_text_policy,
            mbert_weight=analysis_settings.mbert_weight,
        )
```

**Fragmentos de `analyze()`**, en [`backend/api/routes.py`](../api/routes.py). Esta es la ruta `POST /analisis`. Recibe `AnalysisRequest` (`texto` y `url`), verifica al usuario y pasa la noticia a `AnalysisService.analyze()`. El valor devuelto, `outcome`, contiene el texto preparado y los resultados.

```python
@router.post("/analisis", response_model=CreatedAnalysis)
def analyze(
    payload: AnalysisRequest,
    request: Request,
    token: str = Depends(bearer_token),
    identity: IdentityService = Depends(identity_service),
    repository: SupabaseRepository = Depends(history_repository),
) -> CreatedAnalysis:
```

```python
    user = identity.verify_user(token)
    try:
        outcome = service.analyze(payload)
```

Hay una sola ruta de análisis: el servicio Python llama a los dos modelos y conserva cada respuesta por separado.

## 3. Limpieza y preparación de la noticia

**Función completa `clean_news_text()`**, en [`backend/services/text_cleaning.py`](../services/text_cleaning.py). Recibe el texto original y devuelve texto plano, normalizando caracteres, marcas de formato y espacios. No clasifica la noticia.

```python
def clean_news_text(value: str) -> str:
    """Devuelve texto plano para los modelos, preservando palabras y cifras."""
    text = value
    while (decoded := HTML_ENTITY.sub(lambda match: html.unescape(match[0]), text)) != text:
        text = decoded
    text = unicodedata.normalize("NFKC", text)
    text = INVISIBLE_FORMAT.sub(" ", text)
    text = HEADING_MARKER.sub("", text)
    text = EMPHASIS_MARKER.sub(lambda match: match[2] + match[3], text)
    return WHITESPACE.sub(" ", text).strip()
```

**Fragmento de `AnalysisService.analyze()`**, en [`backend/services/analysis.py`](../services/analysis.py). Recibe el texto limpio. Si hay tokenizador mBERT, `prepare()` lo recorta a su límite y devuelve `(texto, recortado, cantidad_de_tokens)`; si no está disponible, `_bilstm_prefix()` usa el límite de BiLSTM. El resultado `model_input` es el texto que reciben los predictores.

```python
        model_input = text
        mbert_predictor = self.mbert_predictor
        mbert_prepare_failed = False
        if self.mbert_text_policy is not None:
            try:
                model_input, truncated, mbert_token_count = self.mbert_text_policy.prepare(
                    model_input
                )
            except Exception:
                logger.exception("Falló la tokenización mBERT")
                model_input, truncated = self._bilstm_prefix(model_input)
                mbert_token_count = None
                mbert_predictor = None
                mbert_prepare_failed = True
        else:
            model_input, truncated = self._bilstm_prefix(model_input)
            mbert_token_count = None
        token_count = len(self.predictor.tokenize(model_input))
```

**Fragmento del mismo método `AnalysisService.analyze()`**. Antes de llamar a los modelos exige al menos **100 tokens** legibles. mBERT trabaja con hasta **512 tokens de su tokenizador**; el BiLSTM seleccionado lee hasta **192 tokens** según su checkpoint.

```python
        if token_count < MIN_INPUT_TOKENS:
            raise InvalidAnalysisInput(
                "texto_insuficiente",
                f"El texto debe tener al menos {MIN_INPUT_TOKENS} tokens; recibí {token_count}.",
                f"Añade contexto hasta llegar a {MIN_INPUT_TOKENS} palabras tokenizables.",
            )
```

## 4. Cómo el backend llama a cada modelo

**Fragmentos del bucle en `AnalysisService.analyze()`**, en [`backend/services/analysis.py`](../services/analysis.py). Recorre BiLSTM y mBERT, les envía el mismo `model_input` mediante `predict()` y guarda sus respuestas en `results`. Cada predictor aplica después su propia tokenización. Si un modelo no responde, el servicio puede continuar con el otro.

```python
        results: dict[str, ModelResult] = {}
        for name, predictor in (
            ("bilstm", self.predictor),
            ("mbert", mbert_predictor),
        ):
```

```python
            try:
                prediction = predictor.predict(model_input)
                model_result = ModelResult(
                    **{**prediction, "modelo": name, "estado": "ok"}
                )
```

**Fragmento de `load_model()`**, en [`backend/models/bilstm.py`](../models/bilstm.py). Antes de analizar noticias, recibe la ruta del checkpoint, reconstruye la red, carga sus pesos aprendidos y devuelve modelo, vocabulario y límite de tokens.

```python
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    model = BiLSTM(
        len(checkpoint["vocab"]),
        config["embedding_dim"],
        config["hidden_dim"],
        config["dropout"],
    )
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device).eval()
    return model, checkpoint["vocab"], config["max_len"], device
```

**Método completo `BilstmPredictor.predict()`**, en [`backend/models/bilstm.py`](../models/bilstm.py). Recibe la noticia preparada. `predict_texts()` la convierte con el vocabulario y los pesos del checkpoint BiLSTM; devuelve una probabilidad de noticia falsa. Este método devuelve además clase, versión y tokens leídos. El umbral de clase falsa es **0,5**.

```python
    def predict(self, text: str) -> dict[str, str | float | int]:
        words = tokenize(text)
        probability_fake = predict_texts(
            self.model, self.vocab, self.max_len, self.device, [text]
        )[0]
        return {
            "modelo": "bilstm",
            "version": self.version,
            "clase": "falsa" if probability_fake >= 0.5 else "real",
            "probabilidad_falsa": probability_fake,
            "tokens_leidos": min(len(words), self.max_len),
        }
```

**Fragmento de `predict_texts()`**, en el mismo archivo. Muestra la parte clave: tokeniza, limita a `max_len`, sustituye cada palabra por su índice de vocabulario y obtiene de `scores[:, 0]` la probabilidad de la clase falsa.

```python
            for value in texts[start : start + batch_size]:
                words = tokenize(value)[:max_len]
                sequences.append([vocab.get(word, 1) for word in words] or [1])
```

```python
            scores = model(padded.to(device), lengths).softmax(dim=1)
            probabilities.extend(scores[:, 0].cpu().tolist())
    return probabilities
```

**Fragmento de `MbertPredictor.__init__()`**, en [`backend/models/mbert.py`](../models/mbert.py). Al iniciar la API, carga desde el checkpoint local el modelo mBERT y lo deja en modo evaluación.

```python
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = AutoModelForSequenceClassification.from_pretrained(
            text_policy.model_dir, local_files_only=True, use_safetensors=True
        ).to(self.device).eval()
```

**Método completo `MbertPredictor.predict()`**, en [`backend/models/mbert.py`](../models/mbert.py). Recibe la misma noticia preparada. Su tokenizador genera los tensores de entrada; el modelo calcula las puntuaciones y la posición `[0, 1]` representa `FALSA`. Devuelve probabilidad, clase según el umbral guardado, versión y tokens leídos.

```python
    def predict(self, text: str) -> dict[str, str | float | int]:
        encoded = self.text_policy.tokenizer(
            text, truncation=True, max_length=self.text_policy.max_len,
            return_tensors="pt",
        )
        tokens_read = int(encoded["input_ids"].shape[1])
        encoded = {name: value.to(self.device) for name, value in encoded.items()}
        with torch.inference_mode():
            autocast = (
                torch.autocast("cuda", dtype=torch.bfloat16)
                if self.device.type == "cuda" and torch.cuda.is_bf16_supported()
                else nullcontext()
            )
            with autocast:
                logits = self.model(**encoded).logits
            probability_fake = float(logits.float().softmax(dim=-1)[0, 1].item())
        return {
            "modelo": "mbert",
            "version": self.version,
            "clase": "falsa" if probability_fake >= self.text_policy.fake_threshold else "real",
            "probabilidad_falsa": probability_fake,
            "tokens_leidos": tokens_read,
        }
```

Estas son predicciones estadísticas de los modelos. La salida de cada uno se conserva por separado; ninguno comprueba los hechos de la noticia.

## 5. Se forma el resultado conjunto

**Fragmentos de `AnalysisService.analyze()`**, en [`backend/services/analysis.py`](../services/analysis.py). Usa solo modelos con `estado == "ok"`. Si responden ambos, compara sus clases. Si responde uno, recibe todo el peso; si responden dos, el peso predeterminado es **0,3 para BiLSTM y 0,7 para mBERT**. Devuelve las predicciones individuales, la probabilidad combinada, el texto utilizado y si hubo recorte.

```python
        successful = [
            result for result in results.values()
            if result.estado == "ok" and result.probabilidad_falsa is not None
        ]
        if not successful:
            raise ModelUnavailableError(
                "Ningún modelo produjo una predicción; puedes volver a intentar el análisis."
            )
        comparison = "no_disponible"
        if len(successful) == 2:
            comparison = (
                "coinciden"
                if successful[0].clase == successful[1].clase
                else "discrepan"
            )
```

```python
        if len(successful) == 1:
            weights = AppliedWeights(
                bilstm=1.0 if successful[0].modelo == "bilstm" else 0.0,
                mbert=1.0 if successful[0].modelo == "mbert" else 0.0,
            )
        else:
            weights = AppliedWeights(
                bilstm=1.0 - self.mbert_weight,
                mbert=self.mbert_weight,
            )
        probability = sum(
            result.probabilidad_falsa * getattr(weights, result.modelo)
            for result in successful
        )
        probability = min(1.0, max(0.0, probability))
        response = AnalysisResponse(
            resultados=results,
            resultado_unificado=UnifiedResult(
                probabilidad_falsa=probability,
                modelos_utilizados=[result.modelo for result in successful],
                pesos_aplicados=weights,
            ),
            comparacion=comparison,
            nota="Las probabilidades son salidas experimentales de clasificadores; no verifican hechos.",
        )
        return AnalysisOutcome(
            response=response, text=model_input, truncated=truncated,
        )
```

## 6. Se guarda y se devuelve la respuesta

**Fragmento final de `analyze()`**, en [`backend/api/routes.py`](../api/routes.py). Recibe `outcome`, calcula SHA-256 del texto preparado, llama a `SupabaseRepository.create_analysis()` y devuelve al frontend el ID, los resultados individuales, el resultado conjunto y el indicador de recorte. El guardado sucede antes de responder.

```python
    analysis_id = repository.create_analysis(
        user_id=UUID(user.id),
        url=(payload.url or "").strip() or None,
        text=outcome.text,
        text_hash=sha256(outcome.text.encode("utf-8")).hexdigest(),
        response=outcome.response,
    )
    return CreatedAnalysis(
        **outcome.response.model_dump(), id=analysis_id,
        texto_recortado=outcome.truncated,
    )
```

**Fragmento de `SupabaseRepository.create_analysis()`**, en [`backend/repositories/supabase.py`](../repositories/supabase.py). Envía a Supabase el texto y `predictions` (las salidas de los modelos con estado `ok`) a través de `crear_analisis_texto_unico`; devuelve el ID creado. Supabase guarda el historial de uso; los CSV de `datasets/` se usan para entrenar y no reciben estas noticias.

```python
        value = self._request(
            "POST",
            "rpc/crear_analisis_texto_unico",
            admin=True,
            body={
                "p_usuario_id": str(user_id),
                "p_url": url,
                "p_texto": text,
                "p_hash_texto": text_hash,
                "p_comparacion": response.comparacion,
                "p_resultados": predictions,
                "p_resultado_unificado": response.resultado_unificado.model_dump(),
            },
        )
        return UUID(value)
```

## 7. Registro local en blockchain

Después del guardado, `BlockchainWorker.process_one()` de [`backend/blockchain/worker.py`](../blockchain/worker.py) toma el análisis pendiente. **El siguiente fragmento es el método completo `RegistryClient.send()`**, en [`backend/blockchain/client.py`](../blockchain/client.py). Recibe el registro guardado, firma una transacción con ID, hash del texto, fecha y predicciones, la envía a Anvil y devuelve el hash de la transacción. El texto completo y la URL no entran en el contrato.

```python
    def send(self, record: HistoryRecord) -> str:
        nonce = self.web3.eth.get_transaction_count(self.account.address, "pending")
        transaction = self.contract.functions.registrar(
            record.id.bytes,
            bytes.fromhex(record.hash_texto),
            int(record.fecha.timestamp()),
            canonical_data(record),
        ).build_transaction(
            {
                "from": self.account.address,
                "nonce": nonce,
                "chainId": self.settings.chain_id,
                "gas": 500_000,
                "gasPrice": self.web3.eth.gas_price,
            }
        )
        signed = self.account.sign_transaction(transaction)
        return Web3.to_hex(self.web3.eth.send_raw_transaction(signed.raw_transaction))
```

**Función `registrar()`**, en [`backend/blockchain/contracts/ScanTrueRegistry.sol`](../blockchain/contracts/ScanTrueRegistry.sol). Recibe esos datos, exige la cuenta autorizada, impide repetir el ID y emite `AnalisisRegistrado`. Después `RegistryClient.verify()` compara el evento con los datos de Supabase; si coinciden, el trabajador marca el registro como confirmado.

```solidity
    function registrar(bytes16 id, bytes32 hashTexto, uint64 fecha, bytes calldata datos)
        external
    {
        if (msg.sender != registrador) revert NoAutorizado();
        if (registrado[id]) revert YaRegistrado();
        registrado[id] = true;
        emit AnalisisRegistrado(id, hashTexto, fecha, datos);
    }
```

### Por qué se usa este stack

| Pieza | Papel |
| --- | --- |
| **Solidity** | Define las reglas del contrato. |
| **Forge y solc** | Compilan el contrato a bytecode y ABI. |
| **Anvil** | Ejecuta localmente bloques, transacciones y eventos compatibles con Ethereum. |
| **Web3.py** | Permite al backend Python firmar, enviar y comprobar transacciones. |
| **Supabase** | Guarda la noticia, las predicciones y el estado del registro. |

Anvil ejecuta el contrato en una **EVM local**: reproduce el proceso técnico de una blockchain, pero la cadena está controlada por este equipo y no tiene validadores independientes. La coincidencia del evento con los datos guardados demuestra el registro local de esa huella y esas predicciones; no demuestra la veracidad de la noticia. La verificación actual tampoco recalcula el hash a partir del texto almacenado.
