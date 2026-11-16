"""Pruebas del índice de cruces con comun_v1 (datos_comunes/cruces.py).

Uso: bilstm/.venv/bin/python -m unittest discover -s datos_comunes/tests
"""

import random
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from datos_comunes.cruces import IndiceComun, parecidas, tejas  # noqa: E402
from datos_comunes.grupos import fingerprint  # noqa: E402


def texto(semilla: int, palabras: int = 120) -> str:
    rng = random.Random(semilla)
    return " ".join(f"w{rng.randrange(5000)}" for _ in range(palabras)) + "."


def fila(texto_: str, grupo: str, pliegue: str = "F1") -> dict:
    return {"archivo": "fragmentos_desarrollo.csv", "grupo": grupo, "pliegue": pliegue,
            "texto": texto_}


class CrucesTests(unittest.TestCase):
    def setUp(self):
        self.textos = [texto(i) for i in range(50)]
        self.indice = IndiceComun([fila(t, f"g{i}", "congelada" if i == 7 else "F1")
                                   for i, t in enumerate(self.textos)])

    def test_mismo_texto_contenido_y_ajeno(self):
        self.assertEqual([c.grupo for c in self.indice.cruces(self.textos[3])], ["g3"])
        # Una noticia más larga que contiene el fragmento cuenta como cruce.
        largo = texto(999, 60) + " " + self.textos[12] + " " + texto(998, 60)
        self.assertEqual([c.grupo for c in self.indice.cruces(largo)], ["g12"])
        self.assertTrue(self.indice.cruces(self.textos[7])[0].congelada)
        self.assertEqual(self.indice.cruces(texto(12345)), [])

    def test_huella_exacta_aunque_sea_corto(self):
        corto = "Texto breve sin tejas"
        indice = IndiceComun([fila(corto, "c")])
        self.assertEqual([c.grupo for c in indice.cruces("TEXTO, breve sin tejas!")], ["c"])

    def test_equivale_a_comparar_conjuntos(self):
        rng = random.Random(1)
        for _ in range(30):
            base = self.textos[rng.randrange(50)].split()
            inicio = rng.randrange(len(base) // 2)
            consulta = " ".join(base[inicio:inicio + rng.randrange(20, 100)])
            esperado = {f"g{i}" for i, t in enumerate(self.textos)
                        if fingerprint(t) == fingerprint(consulta)
                        or parecidas(tejas(consulta), tejas(t))}
            self.assertEqual({c.grupo for c in self.indice.cruces(consulta)}, esperado)

    def test_hash_estable_entre_procesos(self):
        # blake2b, no hash(): el mismo valor siempre (PYTHONHASHSEED no influye).
        self.assertEqual(min(tejas("uno dos tres cuatro cinco")), 6558438953886)


if __name__ == "__main__":
    unittest.main()
