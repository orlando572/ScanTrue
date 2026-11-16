"""Fase 7: casos, equivalencias, evidencia congelada, referencias, métricas y ejecutor. Sin LLM ni internet.

Uso:
    PYTHONPATH=. backend/.venv/Scripts/python.exe -m unittest backend.tests.test_evaluacion
"""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from backend.core.config import EvidenceLimits
from backend.evaluacion import construir, correr
from backend.evaluacion.casos import (
    CONCLUSIONS, Case, build_manifest, check_manifest, domain_of, load_cases, save_cases, token_count, validate,
)
from backend.evaluacion.equivalencias import as_json, conclusion_for
from backend.evaluacion.evidencia import EvidenceStore, FrozenFetcher, FrozenSearch
from backend.evaluacion.metricas import (
    NO_RESULT, bootstrap_difference, bootstrap_macro_f1, citation_stats, confusion, macro_f1, per_class, summarize, wilson,
)
from backend.evaluacion.referencias import reference_a, reference_b
from backend.schemas.verification import ClaimExtraction, ClaimJudgment
from backend.services.llm_client import LlmUnavailable
from backend.services.verification.conclusion import conclude_verdicts
from backend.services.verification.fetch import FetchedPage, FetchError
from backend.services.verification.search import SearchError, SearchResult
from backend.tests.test_case import CLAIM_A, GARCIA, NOW, TEXT, VARGAS, FakeFetcher, FakeLlm, FakeSearch, judgment

LONG_TEXT = " ".join(f"palabra{n}" for n in range(120))


def make_case(n=1, conclusion="contradicha", partition="ajuste", group=None, **kwargs):
    respaldada = conclusion == "respaldada"
    fields = {
        "id": f"vv1-{n:03d}", "particion": partition, "grupo_evento": group or f"evento-{n}", "texto": f"{LONG_TEXT} caso{n}",
        "conclusion_esperada": conclusion, "fecha_hecho": "2026-03-10", "origen_url": "https://origen.example/nota",
        "etiqueta": (
            {"tipo": "fuentes_independientes", "fuentes": ["https://a.example/1", "https://b.example/2"]} if respaldada else
            {"tipo": "verificador", "verificador": "Maldita.es", "url_verificacion": "https://maldita.es/malditobulo/x",
             "veredicto_original": "Falso", "equivalencia": "falso -> contradicha"}
        ),
        "dominios_excluidos": ["origen.example"] + ([] if respaldada else ["maldita.es"]),
    }
    fields.update(kwargs)
    return Case.model_validate(fields)


def full_set():
    cases, n = [], 0
    for conclusion in CONCLUSIONS:
        for partition in ("ajuste", "final"):
            for _ in range(10):
                n += 1
                cases.append(make_case(n, conclusion, partition))
    return cases


class EquivalenceTests(unittest.TestCase):
    def test_las_cuatro_conclusiones(self):
        for rating, expected in (("Falso", "contradicha"), ("BULO.", "contradicha"), ("Engañoso", "fuera_de_contexto"),
                                 ("Sin contexto", "fuera_de_contexto"), ("Descontextualizado", "fuera_de_contexto"),
                                 ("Sin pruebas", "evidencia_insuficiente"), ("Inchequeable", "evidencia_insuficiente"),
                                 ("No se puede comprobar", "evidencia_insuficiente"), ("Verdadero", "respaldada"), ("Cierto", "respaldada")):
            self.assertEqual(conclusion_for(rating), expected, rating)

    def test_lo_ambiguo_o_desconocido_se_descarta(self):
        for rating in ("Verdad a medias", "Verdadero, pero…", "Parcialmente falso", "Discutible", "Apresurado", "Sátira", "raro", ""):
            self.assertIsNone(conclusion_for(rating), rating)

    def test_ninguna_valoracion_esta_en_dos_conclusiones(self):
        seen = {}
        for conclusion, ratings in as_json()["equivalencias"].items():
            for rating in ratings:
                self.assertNotIn(rating, seen, f"{rating} en {conclusion} y {seen.get(rating)}")
                seen[rating] = conclusion


class CaseTests(unittest.TestCase):
    def test_un_conjunto_completo_y_bien_formado_valida(self):
        self.assertEqual(validate(full_set(), complete=True), [])

    def test_texto_corto(self):
        problems = validate([make_case(texto="muy corto")])
        self.assertTrue(any("tokens" in p for p in problems))
        self.assertEqual(token_count("uno dos tres, cuatro."), 4)

    def test_ids_y_textos_repetidos(self):
        problems = validate([make_case(1), make_case(1, texto=LONG_TEXT + " caso1")])
        self.assertTrue(any("id repetido" in p for p in problems))
        self.assertTrue(any("texto repetido" in p for p in problems))

    def test_los_casos_de_un_mismo_hecho_no_se_reparten(self):
        problems = validate([make_case(1, partition="ajuste", group="paro"), make_case(2, partition="final", group="paro")])
        self.assertTrue(any("repartido entre ajuste y final" in p for p in problems))

    def test_respaldada_exige_dos_fuentes_de_dominios_distintos(self):
        bad = make_case(1, "respaldada", etiqueta={"tipo": "fuentes_independientes", "fuentes": ["https://a.example/1", "https://a.example/2"]})
        self.assertTrue(any("2 fuentes de dominios distintos" in p for p in validate([bad])))
        self.assertEqual(validate([make_case(1, "respaldada")]), [])

    def test_la_etiqueta_de_un_verificador_necesita_sus_datos(self):
        bad = make_case(1, etiqueta={"tipo": "verificador", "verificador": "Maldita.es"})
        self.assertTrue(any("necesita nombre, enlace" in p for p in validate([bad])))

    def test_los_dominios_del_verificador_y_del_origen_se_excluyen(self):
        problems = validate([make_case(1, dominios_excluidos=[])])
        self.assertTrue(any("maldita.es" in p for p in problems))
        self.assertTrue(any("origen.example" in p for p in problems))
        self.assertEqual(domain_of("https://www.Maldita.es/x"), "maldita.es")

    def test_fecha_invalida_y_reparto_incompleto(self):
        self.assertTrue(any("fecha_hecho" in p for p in validate([make_case(1, fecha_hecho="ayer")])))
        problems = validate(full_set()[:-1], complete=True)
        self.assertTrue(any("79 casos" in p for p in problems))
        self.assertTrue(any("evidencia_insuficiente en final: 9" in p for p in problems))

    def test_solo_aprobados(self):
        self.assertTrue(any("pendiente" in p for p in validate([make_case(1)], approved_only=True)))
        approved = make_case(1, revision={"estado": "aprobado", "revisor": "Ana", "fecha": "2026-11-16"})
        self.assertEqual(validate([approved], approved_only=True), [])

    def test_una_descripcion_del_verificador_no_puede_traer_el_veredicto(self):
        clean = make_case(1, tipo_texto="descripcion_verificador", texto=LONG_TEXT + " circula un comunicado atribuido a una organización")
        self.assertEqual(validate([clean]), [])
        for word in ("falso", "bulo", "Engañoso", "desmienten", "verificado", "estafa", "sin pruebas"):
            leaking = make_case(1, tipo_texto="descripcion_verificador", texto=f"{LONG_TEXT} el contenido es {word} según se dice")
            self.assertTrue(any("palabras del veredicto" in p for p in validate([leaking])), word)
        # En un texto original esas palabras son legítimas (una noticia puede hablar de bulos).
        self.assertEqual(validate([make_case(1, texto=f"{LONG_TEXT} el bulo circuló ayer")]), [])
        self.assertEqual(make_case(1).tipo_texto, "original")

    def test_no_acepta_campos_desconocidos(self):
        with self.assertRaises(ValueError):
            make_case(1, inventado=True)
        with self.assertRaises(ValueError):
            make_case(1, id="caso-1")


class ManifestAndSheetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        save_cases([make_case(1), make_case(2, "respaldada", partition="final")], self.dir / "casos.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip_de_casos(self):
        self.assertEqual([c.id for c in load_cases(self.dir / "casos.jsonl")], ["vv1-001", "vv1-002"])

    def test_linea_mal_formada_dice_cual(self):
        (self.dir / "casos.jsonl").write_text('{"id": "x"}\n', encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            load_cases(self.dir / "casos.jsonl")
        self.assertIn("línea 1", str(caught.exception))

    def test_manifiesto_detecta_cualquier_cambio(self):
        (self.dir / "equivalencias.json").write_text(json.dumps(as_json()), encoding="utf-8")
        (self.dir / "manifest.json").write_text(json.dumps(build_manifest(self.dir)), encoding="utf-8")
        self.assertEqual(check_manifest(self.dir), [])
        manifest = json.loads((self.dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["casos"], manifest["por_particion"]), (2, {"ajuste": 1, "final": 1}))
        with (self.dir / "casos.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("\n")
        self.assertTrue(any("cambió" in p for p in check_manifest(self.dir)))

    def test_hoja_de_revision_y_su_aplicacion(self):
        path = self.dir / "hoja.csv"
        self.assertEqual(construir.review_sheet(self.dir, path), 2)
        self.assertIn("vv1-001", path.read_text(encoding="utf-8-sig"))
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[0]["decision"], rows[0]["nota"] = "aprobado", "bien traducido"
        rows[1]["decision"] = "descartado"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        self.assertEqual(construir.apply_review(self.dir, path, "Ana"), (1, 1))
        cases = {c.id: c for c in load_cases(self.dir / "casos.jsonl")}
        self.assertEqual((cases["vv1-001"].revision.estado, cases["vv1-001"].revision.revisor, cases["vv1-001"].revision.nota), ("aprobado", "Ana", "bien traducido"))
        self.assertEqual(cases["vv1-002"].revision.estado, "descartado")
        self.assertEqual(construir.review_sheet(self.dir, path), 0)  # ya no hay pendientes

    def test_congelar_exige_el_conjunto_completo_y_aprobado(self):
        with self.assertRaises(SystemExit):
            construir.main(["congelar", "--directorio", str(self.dir)])


class FrozenEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = EvidenceStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_la_busqueda_se_graba_en_vivo_y_se_reproduce_congelada(self):
        live = FakeSearch()
        recorded = FrozenSearch(self.store, "en_vivo", live).search("consulta de prueba", max_results=5, exclude_domains=["b.example", "a.example"])
        self.assertEqual(len(live.queries), 1)
        replay = FrozenSearch(self.store, "congelado")
        again = replay.search("  Consulta  de PRUEBA ", max_results=5, exclude_domains=["a.example", "b.example"])
        self.assertEqual(again, recorded)

    def test_lo_que_no_se_guardo_no_se_busca_y_se_cuenta(self):
        replay = FrozenSearch(self.store, "congelado")
        self.assertEqual(replay.search("otra consulta"), [])  # sin resultados, no un error del caso
        self.assertEqual(replay.search("y otra más"), [])
        self.assertEqual(replay.misses, 2)

    def test_las_fallas_tambien_se_reproducen(self):
        class Broken:
            def search(self, *args, **kwargs):
                raise SearchError("sin cupo", "busqueda_cupo_agotado")

        with self.assertRaises(SearchError):
            FrozenSearch(self.store, "en_vivo", Broken()).search("consulta")
        with self.assertRaises(SearchError) as caught:
            FrozenSearch(self.store, "congelado").search("consulta")
        self.assertEqual(caught.exception.code, "busqueda_cupo_agotado")

    def test_paginas_grabadas_y_reproducidas_con_su_huella(self):
        live = FakeFetcher({"https://a.example/1": GARCIA})
        page = FrozenFetcher(self.store, "en_vivo", live).fetch("https://a.example/1")
        again = FrozenFetcher(self.store, "congelado").fetch("https://a.example/1")
        self.assertEqual((again.url, again.texto, again.sha256, again.consultada_en), (page.url, page.texto, page.sha256, page.consultada_en))
        self.assertEqual(self.store.page_text("https://a.example/1"), GARCIA)

    def test_la_descarga_que_fallo_falla_igual_al_repetirla(self):
        class Broken:
            def fetch(self, url):
                raise FetchError("404", "error_http")

        with self.assertRaises(FetchError):
            FrozenFetcher(self.store, "en_vivo", Broken()).fetch("https://a.example/x")
        replay = FrozenFetcher(self.store, "congelado")
        with self.assertRaises(FetchError) as caught:
            replay.fetch("https://a.example/x")
        self.assertEqual(caught.exception.code, "error_http")
        with self.assertRaises(FetchError) as missing:
            replay.fetch("https://a.example/otra")
        self.assertEqual((missing.exception.code, replay.misses), ("no_congelada", 1))

    def test_el_texto_se_encuentra_tambien_por_la_direccion_final(self):
        class Redirecting:
            def fetch(self, url):
                return FetchedPage("https://a.example/final", "t", "texto de la página final", NOW, "0" * 64, False)

        FrozenFetcher(self.store, "en_vivo", Redirecting()).fetch("https://a.example/corta")
        self.assertEqual(EvidenceStore(Path(self.tmp.name)).page_text("https://a.example/final"), "texto de la página final")
        self.assertIsNone(EvidenceStore(Path(self.tmp.name)).page_text("https://nadie.example"))

    def test_el_modo_en_vivo_necesita_un_proveedor(self):
        with self.assertRaises(ValueError):
            FrozenSearch(self.store, "en_vivo")
        with self.assertRaises(ValueError):
            FrozenFetcher(self.store, "en_vivo")


class ReferenceTests(unittest.TestCase):
    def test_a_nunca_se_atreve(self):
        self.assertEqual(reference_a("cualquier texto"), "evidencia_insuficiente")

    def test_la_regla_de_conclusion_sobre_veredictos_sueltos(self):
        for verdicts, expected in (([], "evidencia_insuficiente"), (["apoyada", "apoyada"], "respaldada"), (["apoyada", "contradicha"], "contradicha"),
                                   (["apoyada", "fuera_de_contexto"], "fuera_de_contexto"), (["apoyada", "insuficiente"], "evidencia_insuficiente")):
            self.assertEqual(conclude_verdicts(verdicts), expected)

    def test_b_juzga_sin_pasajes_con_las_afirmaciones_del_sistema(self):
        llm = FakeLlm(judgments=[ClaimJudgment(veredicto="contradicha", pasajes=[], cita=""), ClaimJudgment(veredicto="apoyada", pasajes=[], cita="")])
        result = reference_b(llm, TEXT, claims=[CLAIM_A, "Mario Vargas Llosa obtuvo el Premio Nobel de Literatura en 2010"])
        self.assertEqual(result.conclusion, "contradicha")
        self.assertEqual([c["veredicto"] for c in result.claims], ["contradicha", "apoyada"])
        self.assertEqual([call for call in llm.calls], [ClaimJudgment, ClaimJudgment])  # sin extracción nueva ni búsqueda

    def test_b_extrae_si_no_recibe_afirmaciones(self):
        llm = FakeLlm(claims=(CLAIM_A,), judgments=[ClaimJudgment(veredicto="insuficiente", pasajes=[], cita="")])
        self.assertEqual(reference_b(llm, TEXT).conclusion, "evidencia_insuficiente")


class MetricTests(unittest.TestCase):
    PAIRS = [("respaldada", "respaldada"), ("respaldada", "evidencia_insuficiente"), ("contradicha", "contradicha"),
             ("contradicha", "respaldada"), ("fuera_de_contexto", None), ("evidencia_insuficiente", "evidencia_insuficiente")]

    def test_matriz_y_casos_sin_resultado(self):
        matrix = confusion(self.PAIRS)
        self.assertEqual(matrix["respaldada"]["evidencia_insuficiente"], 1)
        self.assertEqual(matrix["fuera_de_contexto"][NO_RESULT], 1)
        self.assertEqual(sum(sum(row.values()) for row in matrix.values()), len(self.PAIRS))

    def test_f1_por_clase_y_macro(self):
        classes = per_class(self.PAIRS)
        self.assertAlmostEqual(classes["respaldada"]["precision"], 0.5)
        self.assertAlmostEqual(classes["respaldada"]["recall"], 0.5)
        self.assertAlmostEqual(classes["contradicha"]["f1"], 2 * 1 * 0.5 / 1.5)
        self.assertEqual(classes["fuera_de_contexto"]["f1"], 0.0)
        expected = sum(c["f1"] for c in classes.values()) / 4
        self.assertAlmostEqual(macro_f1(self.PAIRS), expected)

    def test_referencia_a_tiene_f1_macro_bajo_y_conocido(self):
        pairs = [(c, "evidencia_insuficiente") for c in CONCLUSIONS for _ in range(10)]
        self.assertAlmostEqual(macro_f1(pairs), (2 * 0.25 * 1 / 1.25) / 4)

    def test_wilson(self):
        low, high = wilson(8, 10)
        self.assertTrue(0.4 < low < 0.5 and 0.9 < high < 0.98)
        self.assertEqual(wilson(0, 0), (0.0, 0.0))
        self.assertEqual(wilson(10, 10)[1], 1.0)

    def test_bootstrap_es_reproducible_y_acota_el_valor(self):
        low, high = bootstrap_macro_f1(self.PAIRS, resamples=300, seed=1)
        self.assertEqual((low, high), bootstrap_macro_f1(self.PAIRS, resamples=300, seed=1))
        self.assertLessEqual(low, macro_f1(self.PAIRS) + 0.3)
        self.assertLess(low, high)
        perfect = [(c, c) for c in CONCLUSIONS for _ in range(5)]
        weak = [(c, "evidencia_insuficiente") for c in CONCLUSIONS for _ in range(5)]
        low, high = bootstrap_difference(perfect, weak, resamples=200)
        self.assertGreater(low, 0.3)
        self.assertEqual(bootstrap_difference([], []), (0.0, 0.0))


class CitationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = EvidenceStore(Path(self.tmp.name))
        FrozenFetcher(self.store, "en_vivo", FakeFetcher({"https://a.example/1": GARCIA})).fetch("https://a.example/1")

    def tearDown(self):
        self.tmp.cleanup()

    def result(self, claims):
        return {"esperado": "respaldada", "predicho": "respaldada", "segundos": 1.0, "afirmaciones": claims}

    def test_cuenta_propuestas_validas_y_fuentes_comprobadas(self):
        good = {"veredicto": "apoyada", "motivo": None, "fuentes": [{"url": "https://a.example/1", "extracto": "Premio Nobel de Literatura en 1982"}]}
        invented = {"veredicto": "apoyada", "motivo": None, "fuentes": [{"url": "https://inventada.example/x", "extracto": "algo que no existe en ninguna página"}]}
        wrong_quote = {"veredicto": "apoyada", "motivo": None, "fuentes": [{"url": "https://a.example/1", "extracto": "una frase que la página no contiene en absoluto"}]}
        downgraded = {"veredicto": "insuficiente", "motivo": "cita_no_literal", "fuentes": []}
        guarded = {"veredicto": "insuficiente", "motivo": "apoyo_incompleto", "fuentes": []}
        quiet = {"veredicto": "insuficiente", "motivo": "sin_evidencia", "fuentes": []}
        stats = citation_stats([self.result([good, invented, wrong_quote, downgraded, guarded, quiet])], self.store)
        self.assertEqual((stats["propuestas"], stats["validas_modelo"]), (6 - 1, 4))  # la última no propuso evidencia
        self.assertEqual((stats["presentadas"], stats["verificadas"], stats["urls_inventadas"]), (3, 1, 1))
        self.assertAlmostEqual(stats["tasa_validas_modelo"], 4 / 5)

    def test_sin_copia_no_se_puede_comprobar_aparte(self):
        stats = citation_stats([self.result([{"veredicto": "apoyada", "motivo": None, "fuentes": [{"url": "https://a.example/1", "extracto": "x"}]}])], None)
        self.assertEqual((stats["presentadas"], stats["verificadas"], stats["urls_inventadas"]), (1, None, None))

    def test_resumen_completo_con_referencias(self):
        results = []
        for n, conclusion in enumerate(CONCLUSIONS * 3):
            results.append({
                "id": f"vv1-{n:03d}", "esperado": conclusion, "predicho": conclusion if n % 4 else "evidencia_insuficiente", "segundos": 10.0 + n,
                "error": None, "afirmaciones": [{"veredicto": "insuficiente", "motivo": "sin_evidencia", "fuentes": []}],
                "referencia_a": {"predicho": "evidencia_insuficiente"}, "referencia_b": {"predicho": "evidencia_insuficiente"},
            })
        results[0]["predicho"], results[0]["error"] = None, {"codigo": "llm_no_disponible"}
        summary = summarize(results, self.store)
        self.assertEqual((summary["casos"], summary["con_resultado"], summary["fallas"]), (12, 11, {"llm_no_disponible": 1}))
        self.assertGreater(summary["referencia_a"]["diferencia_sistema_menos_referencia"], 0)
        self.assertEqual(summary["error_grave"], {"respaldada_cuando_era_contradicha": 0, "contradicha_cuando_era_respaldada": 0})
        self.assertAlmostEqual(summary["duracion"]["media"], sum(r["segundos"] for r in results) / 12)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.case = make_case(1, "respaldada", texto=TEXT, dominios_excluidos=["origen.example"])

    def tearDown(self):
        self.tmp.cleanup()

    def services(self, llm=None, search=None):
        return {"llm": llm or FakeLlm(judgments=[judgment()]), "search": search or FakeSearch(),
                "fetcher": FakeFetcher({"https://a.test/1": GARCIA, "https://b.test/2": VARGAS}),
                "limits": EvidenceLimits(), "case_seconds": 300.0}

    def test_un_caso_completo_con_su_registro(self):
        record = correr.evaluate_case(self.case, **self.services())
        self.assertEqual((record["predicho"], record["error"], record["esperado"]), ("respaldada", None, "respaldada"))
        claim = record["afirmaciones"][0]
        self.assertEqual((claim["veredicto"], claim["motivo"], claim["paginas"]), ("apoyada", None, 2))
        self.assertEqual(claim["fuentes"][0]["url"], "https://a.test/1")
        self.assertEqual(record["extraccion"]["afirmaciones"], 1)

    def test_se_excluyen_los_verificadores_y_el_origen_del_caso(self):
        seen = []

        class Spy(FakeSearch):
            def search(self, query, *, max_results=5, exclude_domains=()):
                seen.append(set(exclude_domains))
                return super().search(query, max_results=max_results, exclude_domains=exclude_domains)

        correr.evaluate_case(self.case, **self.services(search=Spy()))
        self.assertTrue({"maldita.es", "newtral.es", "chequeado.com", "origen.example"} <= seen[0])

    def test_una_falla_no_tumba_la_corrida(self):
        record = correr.evaluate_case(self.case, **self.services(llm=FakeLlm(errors={ClaimExtraction: LlmUnavailable("caído")})))
        self.assertEqual((record["predicho"], record["error"]["codigo"]), (None, "llm_no_disponible"))
        record = correr.evaluate_case(self.case, **self.services(search=FakeSearch(error=SearchError("sin cupo", "busqueda_cupo_agotado"))))
        self.assertEqual(record["error"]["codigo"], "busqueda_cupo_agotado")

    def test_las_referencias_van_con_las_mismas_afirmaciones(self):
        llm = FakeLlm(judgments=[judgment(), ClaimJudgment(veredicto="contradicha", pasajes=[], cita="")])
        record = correr.evaluate_case(self.case, references=True, **self.services(llm=llm))
        self.assertEqual(record["referencia_a"]["predicho"], "evidencia_insuficiente")
        self.assertEqual(record["referencia_b"]["predicho"], "contradicha")
        self.assertEqual(record["referencia_b"]["afirmaciones"][0]["texto"], CLAIM_A)

    def test_la_corrida_guarda_cada_caso_y_se_retoma(self):
        out = self.dir / "corrida"
        first = correr.run([self.case], out, references=False, store=None, log=lambda *_: None, **self.services())
        self.assertEqual(first["casos"], 1)
        self.assertTrue((out / "RESUMEN.md").is_file() and (out / "resumen.json").is_file())
        lines = (out / "resultados.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        # Al repetir, no vuelve a evaluar lo que ya estaba (un LLM que fallaría no se llama).
        broken = FakeLlm(errors={ClaimExtraction: LlmUnavailable("no debería llamarse")})
        again = correr.run([self.case], out, references=False, store=None, log=lambda *_: None, **self.services(llm=broken))
        self.assertEqual(again["con_resultado"], 1)
        self.assertEqual(len((out / "resultados.jsonl").read_text(encoding="utf-8").splitlines()), 1)

    def test_la_prueba_final_se_abre_una_sola_vez_y_con_cifra_minima(self):
        save_cases(full_set(), self.dir / "casos.jsonl")
        (self.dir / "equivalencias.json").write_text(json.dumps(as_json()), encoding="utf-8")
        (self.dir / "manifest.json").write_text(json.dumps(build_manifest(self.dir)), encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:  # sin umbrales.json
            correr.open_final_test(self.dir)
        self.assertIn("umbrales.json", str(caught.exception))
        (self.dir / "umbrales.json").write_text(json.dumps({"f1_macro_minimo": 0.6}), encoding="utf-8")
        correr.open_final_test(self.dir)
        self.assertTrue((self.dir / correr.FINAL_OPENED).is_file())
        with self.assertRaises(SystemExit) as caught:  # segunda vez
            correr.open_final_test(self.dir)
        self.assertIn("ya se abrió", str(caught.exception))

    def test_no_se_abre_la_prueba_final_si_el_conjunto_cambio(self):
        save_cases(full_set(), self.dir / "casos.jsonl")
        (self.dir / "equivalencias.json").write_text(json.dumps(as_json()), encoding="utf-8")
        (self.dir / "manifest.json").write_text(json.dumps(build_manifest(self.dir)), encoding="utf-8")
        (self.dir / "umbrales.json").write_text(json.dumps({"f1_macro_minimo": 0.6}), encoding="utf-8")
        with (self.dir / "casos.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("\n")
        with self.assertRaises(SystemExit) as caught:
            correr.open_final_test(self.dir)
        self.assertIn("cambió", str(caught.exception))
        self.assertFalse((self.dir / correr.FINAL_OPENED).exists())

    def test_las_faltas_de_evidencia_congelada_quedan_en_el_resumen(self):
        out = self.dir / "congelada"
        store = EvidenceStore(self.dir / "copia")
        search, fetcher = FrozenSearch(store, "congelado"), FrozenFetcher(store, "congelado")
        summary = correr.run([self.case], out, llm=FakeLlm(), search=search, fetcher=fetcher, limits=EvidenceLimits(), case_seconds=300.0,
                             references=False, store=store, log=lambda *_: None)
        self.assertEqual(summary["evidencia_faltante"], {"busquedas": 1, "paginas": 0})
        self.assertIn("Evidencia congelada incompleta", (out / "RESUMEN.md").read_text(encoding="utf-8"))

    def test_el_informe_resume_y_lista_los_casos(self):
        out = self.dir / "corrida"
        correr.run([self.case], out, references=True, store=None, log=lambda *_: None, **self.services(llm=FakeLlm(judgments=[judgment(), ClaimJudgment(veredicto="apoyada", pasajes=[], cita="")])))
        text = (out / "RESUMEN.md").read_text(encoding="utf-8")
        for fragment in ("# Corrida «corrida»", "F1 macro", "Matriz de confusión", "vv1-001", "Referencia A", "Referencia B"):
            self.assertIn(fragment, text)


if __name__ == "__main__":
    unittest.main()
