"""Base de afirmaciones ya verificadas: normalización, comprobaciones y migración 010.

Sin Supabase ni llama-server. Uso:
    PYTHONPATH=. backend/.venv/Scripts/python.exe -m unittest backend.tests.test_known_claims
"""

import re
import unittest
from pathlib import Path
from uuid import uuid4

from backend.core.config import SupabaseSettings
from backend.repositories.supabase import SupabaseRepository
from backend.services.verification.claims import text_reference
from backend.services.verification.known_claims import (
    NEGATIONS,
    SIMILARITY_THRESHOLD,
    claim_hash,
    compatible,
    find_known_claim,
    negations_of,
    normalize_claim,
    numbers_of,
    save_known_claim,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-11-15T14:00:00+00:00"


def row(texto, *, exacta=False, similitud=0.9, veredicto="apoyada"):
    return {"id": str(uuid4()), "texto": texto, "veredicto": veredicto, "fuentes": [{"id": 1}],
            "modelo_llm": "m", "version_prompts": "v1", "verificado_en": NOW, "expira_en": NOW,
            "similitud": similitud, "exacta": exacta}


class FakeRepository:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.searches = []
        self.saved = []

    def find_verified_claims(self, claim_hash, normalized, threshold, limit=5):
        self.searches.append((claim_hash, normalized, threshold))
        return self.rows

    def save_verified_claim(self, **fields):
        self.saved.append(fields)
        return uuid4()


class NormalizationTests(unittest.TestCase):
    def test_minusculas_sin_tildes_ni_puntuacion(self):
        self.assertEqual(normalize_claim("El 70% de ‘Juárez’, no  llegó..."), "el 70 de juarez no llego")

    def test_mismas_palabras_mismo_hash(self):
        a = normalize_claim("El presidente viajó a Lima.")
        b = normalize_claim("el  PRESIDENTE viajó a lima")
        self.assertEqual(a, b)
        self.assertEqual(claim_hash(a), claim_hash(b))
        self.assertEqual(len(claim_hash(a)), 64)
        self.assertNotEqual(claim_hash(a), claim_hash(normalize_claim("El presidente viajó a Quito.")))

    def test_texto_sin_letras_queda_vacio(self):
        self.assertEqual(normalize_claim(" ... ¿? "), "")


class GuardTests(unittest.TestCase):
    def test_una_cifra_distinta_no_es_compatible(self):
        self.assertFalse(compatible("El desempleo subió un 5 por ciento.", "El desempleo subió un 15 por ciento."))
        self.assertFalse(compatible("Fueron 2.000 personas.", "Fueron 2.000 personas y 3 niños."))

    def test_el_mismo_numero_con_otro_formato_si(self):
        self.assertTrue(compatible("Pagaron 100.000 euros.", "Se pagaron 100000 euros."))
        self.assertEqual(numbers_of("2,5 millones y 12"), frozenset({"2.5", "12"}))

    def test_una_negacion_distinta_no_es_compatible(self):
        self.assertFalse(compatible("El alcalde sí firmó el contrato.", "El alcalde no firmó el contrato."))
        self.assertFalse(compatible("Nunca viajó a Lima.", "Viajó a Lima."))
        self.assertTrue(compatible("El alcalde no firmó el contrato.", "El alcalde no firmó el acuerdo."))

    def test_negaciones_con_tilde(self):
        self.assertEqual(negations_of("Jamás ni ningún acuerdo"), frozenset({"jamas", "ni", "ningun"}))
        self.assertIn("no", NEGATIONS)


class FindTests(unittest.TestCase):
    def test_busca_con_el_hash_y_el_umbral(self):
        repo = FakeRepository()
        self.assertIsNone(find_known_claim(repo, "El presidente viajó a Lima."))
        h, norm, threshold = repo.searches[0]
        self.assertEqual((norm, threshold), ("el presidente viajo a lima", SIMILARITY_THRESHOLD))
        self.assertIsNone(SIMILARITY_THRESHOLD)  # búsqueda por similitud apagada: solo exacta
        self.assertEqual(h, claim_hash(norm))

    def test_con_umbral_la_busqueda_por_similitud_sigue_disponible(self):
        repo = FakeRepository([row("El presidente viajó a la ciudad de Lima.")])
        self.assertIsNotNone(find_known_claim(repo, "El presidente viajó a Lima.", threshold=0.8))
        self.assertEqual(repo.searches[0][2], 0.8)

    def test_la_coincidencia_exacta_no_necesita_comprobaciones(self):
        found = find_known_claim(FakeRepository([row("otra redacción", exacta=True, similitud=1.0)]),
                                 "El presidente viajó a Lima.")
        self.assertTrue(found.exacta)
        self.assertEqual(found.origen, "base_anterior")
        self.assertEqual(found.veredicto, "apoyada")

    def test_una_parecida_compatible_se_acepta(self):
        found = find_known_claim(FakeRepository([row("El presidente viajó a la ciudad de Lima.")]),
                                 "El presidente viajó a Lima.")
        self.assertIsNotNone(found)
        self.assertFalse(found.exacta)
        self.assertEqual(found.fuentes, [{"id": 1}])
        self.assertEqual(found.expira_en.year, 2026)

    def test_una_parecida_con_otra_cifra_se_rechaza(self):
        repo = FakeRepository([row("El desempleo subió un 15 por ciento en Lima.", similitud=0.95)])
        self.assertIsNone(find_known_claim(repo, "El desempleo subió un 5 por ciento en Lima."))

    def test_una_parecida_con_otra_negacion_se_rechaza(self):
        repo = FakeRepository([row("El alcalde no firmó el contrato con la empresa.", similitud=0.95)])
        self.assertIsNone(find_known_claim(repo, "El alcalde firmó el contrato con la empresa."))

    def test_salta_la_incompatible_y_usa_la_siguiente(self):
        repo = FakeRepository([
            row("El desempleo subió un 15 por ciento en Lima.", similitud=0.95),
            row("El desempleo subió un 5 por ciento en la ciudad de Lima.", similitud=0.85),
        ])
        found = find_known_claim(repo, "El desempleo subió un 5 por ciento en Lima.")
        self.assertEqual(found.texto, "El desempleo subió un 5 por ciento en la ciudad de Lima.")

    def test_texto_vacio_no_consulta(self):
        repo = FakeRepository([row("algo")])
        self.assertIsNone(find_known_claim(repo, " ... "))
        self.assertEqual(repo.searches, [])


class RepositoryRequestTests(unittest.TestCase):
    """Sin umbral, la base recibe 2,0: devuelve solo la exacta y nunca cae en el 0,3 por omisión."""

    def request_body(self, threshold):
        sent = []
        repository = SupabaseRepository(SupabaseSettings("https://x.test", "pub", "sec"))
        repository._request = lambda method, path, **kw: sent.append((path, kw["body"])) or []
        repository.find_verified_claims("h" * 64, "texto", threshold)
        return sent[0]

    def test_sin_umbral_se_envia_dos(self):
        path, body = self.request_body(None)
        self.assertEqual(path, "rpc/buscar_afirmacion_verificada")
        self.assertEqual(body["p_umbral"], 2.0)

    def test_con_umbral_se_envia_tal_cual(self):
        self.assertEqual(self.request_body(0.85)[1]["p_umbral"], 0.85)


class SaveTests(unittest.TestCase):
    def test_guarda_texto_normalizado_y_hash(self):
        repo = FakeRepository()
        analysis_id = uuid4()
        save_known_claim(repo, "El presidente viajó a Lima.", "contradicha", [{"id": 1, "url": "https://a.test"}],
                         model="qwen", prompt_version="v1", analysis_id=analysis_id)
        saved = repo.saved[0]
        self.assertEqual(saved["normalized"], "el presidente viajo a lima")
        self.assertEqual(saved["claim_hash"], claim_hash(saved["normalized"]))
        self.assertEqual((saved["verdict"], saved["analysis_id"]), ("contradicha", analysis_id))
        self.assertEqual(saved["text"], "El presidente viajó a Lima.")

    def test_rechaza_veredicto_o_texto_invalido(self):
        repo = FakeRepository()
        with self.assertRaises(ValueError):
            save_known_claim(repo, "Algo cierto.", "quizás", [], model=None, prompt_version=None)
        with self.assertRaises(ValueError):
            save_known_claim(repo, " ... ", "apoyada", [], model=None, prompt_version=None)
        self.assertEqual(repo.saved, [])


class TextReferenceTests(unittest.TestCase):
    def test_referencias_al_texto(self):
        for claim, expected in (
            ("Los habitantes de las comunidades mencionadas afirman que sí.", "mencionadas"),
            ("Ricardo Anaya canceló el evento por dicho país.", "dicho país"),
            ("Al escribir esta noticia hubo 3 casos.", "esta noticia"),
            ("Según el texto, el alcalde renunció.", "el texto"),
        ):
            self.assertEqual(text_reference(claim), expected, claim)

    def test_no_son_referencias(self):
        for claim in ("Beatriz ha dicho que no quiere ser llamada así.", "Todos comparten las mismas leyes.",
                      "El presidente dijo que sí."):
            self.assertIsNone(text_reference(claim), claim)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.up = (ROOT / "backend/db/migrations/010_afirmaciones_verificadas.sql").read_text(encoding="utf-8")
        self.down = (ROOT / "backend/db/rollback/010_revertir_afirmaciones_verificadas.sql").read_text(encoding="utf-8")

    def test_la_reversion_borra_las_dos_funciones_y_nada_mas(self):
        created = re.findall(r"create function public\.(\w+)\(", self.up)
        self.assertEqual(sorted(created), ["buscar_afirmacion_verificada", "guardar_afirmacion_verificada"])
        for name in created:
            self.assertIn(f"drop function if exists public.{name}(", self.down)
        self.assertNotIn("drop table", self.down)

    def test_solo_el_backend_ejecuta_las_funciones(self):
        self.assertEqual(len(re.findall(r"revoke execute on function", self.up)), 2)
        self.assertEqual(len(re.findall(r"grant execute on function", self.up)), 2)
        self.assertEqual(self.up.count("to service_role"), 2)

    def test_la_vigencia_de_d5_esta_en_la_base(self):
        self.assertIn("interval '7 days'", self.up)
        self.assertIn("interval '30 days'", self.up)
        self.assertIn("a.expira_en > now()", self.up)


if __name__ == "__main__":
    unittest.main()
