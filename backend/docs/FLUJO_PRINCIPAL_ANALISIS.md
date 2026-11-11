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

**Fragmento de `lifespan()`**, en [`backend/app.py`](../app.py). Al iniciar el backend, carga la combinación calibrada (`datasets/combinacion_produccion/combinacion.json`), crea los predictores a partir de sus contratos y comprueba que cada contrato coincide con la combinación (misma versión y temperatura). Los checkpoints se cargan una vez, no por cada noticia. Si BETO (clave `mbert`) falla al cargar, el BiLSTM puede seguir disponible.

```python
    try:
        analysis_settings = AnalysisSettings.from_environment()
        combination = Combination.load(analysis_settings.combination_file)
        bilstm_predictor = BilstmPredictor()
        combination.check(bilstm_predictor.contract)
        try:
            mbert_text_policy = MbertTokenizer()
            combination.check(mbert_text_policy.contract)
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
            combination=combination,
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

**Fragmento de `AnalysisService.analyze()`**, en [`backend/services/analysis.py`](../services/analysis.py). Recibe el texto limpio. `_bilstm_prefix()` lo recorta a las 192 palabras del BiLSTM y, si hay tokenizador de BETO, `prepare()` lo recorta a sus 256 subpalabras y devuelve `(texto, recortado, cantidad_de_tokens)`. Los dos recortes son prefijos del mismo texto: `model_input` es el más largo, y cada predictor lee dentro de él hasta su propio límite.

```python
        # Cada modelo lee hasta su propio límite (BiLSTM 192 palabras, mBERT 256 subpalabras).
        # Los dos recortes son prefijos del mismo texto: se guarda y se envía el más largo y
        # cada predictor recorta dentro de él lo que le corresponde.
        model_input, truncated = self._bilstm_prefix(text)
        mbert_predictor = self.mbert_predictor
        mbert_prepare_failed = False
        mbert_token_count = None
        if self.mbert_text_policy is not None:
            try:
                mbert_input, mbert_truncated, mbert_token_count = self.mbert_text_policy.prepare(
                    text
                )
                if len(mbert_input) > len(model_input):
                    model_input = mbert_input
                truncated = truncated and mbert_truncated
            except Exception:
                logger.exception("Falló la tokenización mBERT")
                mbert_token_count = None
                mbert_predictor = None
                mbert_prepare_failed = True
        token_count = len(self.predictor.tokenize(model_input))
```

**Fragmento del mismo método `AnalysisService.analyze()`**. Antes de llamar a los modelos exige al menos **100 tokens** legibles. BETO trabaja con hasta **256 subpalabras de su tokenizador**; el BiLSTM lee hasta **192 palabras**, según sus contratos.

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

**Fragmento de `load_model()`**, en [`backend/models/bilstm.py`](../models/bilstm.py). Antes de analizar noticias, recibe el contrato (`datasets/bilstm_produccion/modelo/contrato.json`), verifica el SHA-256 del checkpoint y que su orden de clases, longitud y pooling coinciden con el contrato, reconstruye la red, carga sus pesos y devuelve modelo, vocabulario y límite de tokens.

```python
        contract.verify(path)
    device = resolve_device(device_name)
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    if config.get("etiquetas") != contract.data["etiquetas"]:
        raise ValueError("El orden de clases del checkpoint BiLSTM no coincide con su contrato")
    if int(config["max_len"]) != contract.max_tokens:
        raise ValueError("La longitud del checkpoint BiLSTM no coincide con su contrato")
    if config.get("pooling", "final") != contract.data.get("pooling", "final"):
        raise ValueError("El pooling del checkpoint BiLSTM no coincide con su contrato")
    model = BiLSTM(
        len(checkpoint["vocab"]),
        config["embedding_dim"],
        config["hidden_dim"],
        config["dropout"],
        config.get("pooling", "final"),
    )
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device).eval()
    return model, checkpoint["vocab"], contract.max_tokens, device
```

**Fragmento de `predict_logits()`**, en el mismo archivo. Tokeniza, limita a `max_len` y devuelve, por texto, `logit_falsa − logit_real` (salida 1 = falsa, salida 0 = real, como en el contrato).

```python
            logits = model(padded.to(device), lengths).float()
            # Contrato: salida 0 = real, salida 1 = falsa.
            margins.extend((logits[:, 1] - logits[:, 0]).cpu().tolist())
    return margins
```

**Función `calibrated_probability()`**, en [`backend/models/contrato.py`](../models/contrato.py). Convierte esa diferencia en probabilidad calibrada dividiéndola entre la temperatura del contrato (escalado de temperatura).

```python
def calibrated_probability(logit_fake_minus_real: float, temperature: float) -> float:
    return sigmoid(logit_fake_minus_real / temperature)
```

**Método completo `BilstmPredictor.predict()`**, en [`backend/models/bilstm.py`](../models/bilstm.py). Devuelve probabilidad calibrada, clase según el umbral del contrato (0,5), versión del contrato y tokens leídos.

```python
    def predict(self, text: str) -> dict[str, str | float | int]:
        words = tokenize(text)
        margin = predict_logits(
            self.model, self.vocab, self.max_len, self.device, [text]
        )[0]
        probability_fake = calibrated_probability(margin, self.contract.temperature)
        return {
            "modelo": "bilstm",
            "version": self.version,
            "clase": "falsa" if probability_fake >= self.contract.threshold else "real",
            "probabilidad_falsa": probability_fake,
            "tokens_leidos": min(len(words), self.max_len),
        }
```

**Fragmento de `MbertPredictor.__init__()`**, en [`backend/models/mbert.py`](../models/mbert.py). Al iniciar la API, tras verificar el SHA-256 de los pesos y el orden de clases, carga BETO desde el checkpoint local y lo deja en modo evaluación.

```python
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = AutoModelForSequenceClassification.from_pretrained(
            text_policy.model_dir, local_files_only=True, use_safetensors=True
        ).to(self.device).eval()
```

**Método completo `MbertPredictor.predict()`**, en [`backend/models/mbert.py`](../models/mbert.py). Recibe la misma noticia preparada y la recorta a 256 subpalabras con su tokenizador. Calcula `logit_falsa − logit_real` y la calibra con la temperatura de su contrato.

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
                logits = self.model(**encoded).logits.float()[0]
        margin = float((logits[1] - logits[0]).item())
        probability_fake = calibrated_probability(margin, self.contract.temperature)
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

**Fragmentos de `AnalysisService.analyze()`**, en [`backend/services/analysis.py`](../services/analysis.py). Usa solo modelos con `estado == "ok"`. Si responden ambos, compara sus clases. La probabilidad conjunta la calcula `Combination.combine()`: si responde uno, se usa su probabilidad calibrada; si responden los dos, se combinan sus logits calibrados con **0,2 para el BiLSTM y 0,8 para BETO** (calibración conjunta, [04_CALIBRACION_CONJUNTA.md](../../docs/mejora_modelos/04_CALIBRACION_CONJUNTA.md)). Devuelve las predicciones individuales, la probabilidad combinada con la versión de la combinación, el texto utilizado y si hubo recorte.

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
        # Cada modelo ya devuelve su probabilidad calibrada; se combinan sus logits
        # (docs/mejora_modelos/04_CALIBRACION_CONJUNTA.md).
        probability, used_weights = self.combination.combine(
            {result.modelo: result.probabilidad_falsa for result in successful}
        )
        weights = AppliedWeights(
            bilstm=used_weights.get("bilstm", 0.0),
            mbert=used_weights.get("mbert", 0.0),
        )
        probability = min(1.0, max(0.0, probability))
        response = AnalysisResponse(
            resultados=results,
            resultado_unificado=UnifiedResult(
                probabilidad_falsa=probability,
                modelos_utilizados=[result.modelo for result in successful],
                pesos_aplicados=weights,
                version_combinacion=self.combination.version,
            ),
            comparacion=comparison,
            nota="Las probabilidades son salidas experimentales de clasificadores; no verifican hechos.",
        )
        return AnalysisOutcome(
            response=response, text=model_input, truncated=truncated,
        )
```

**Método `Combination.combine()`**, en [`backend/models/contrato.py`](../models/contrato.py).

```python
    def combine(self, probabilities: dict[str, float]) -> tuple[float, dict[str, float]]:
        """Combina las probabilidades calibradas disponibles. Si solo hay un modelo, usa la suya."""
        if not probabilities:
            raise ValueError("No hay probabilidades que combinar")
        if len(probabilities) == 1:
            (name, probability), = probabilities.items()
            return probability, {name: 1.0}
        weights = {name: self.weights[name] for name in probabilities}
        value = sum(weight * logit(probabilities[name]) for name, weight in weights.items())
        return sigmoid(value), weights
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
