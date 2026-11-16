"""Pruebas del estándar de fila (datos_comunes/estandar.py).

Uso: bilstm/.venv/bin/python -m unittest discover -s datos_comunes/tests
"""

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "datos_comunes"))
from datos_comunes.estandar import (  # noqa: E402
    COLUMNAS_BASE, TOKEN_PATTERN, contar_tokens, filas_estandar, preparar_noticia,
    separar_oraciones,
)

FINALES = tuple(".!?…")


def noticia(oraciones: int, palabras: int = 15, tema: str = "el puerto") -> str:
    return " ".join(
        f"El informe sobre {tema} dice que la medida {i} " + " ".join(
            f"dato{i}x{j}" for j in range(palabras - 9)) + " para todos."
        for i in range(oraciones))


def termina_en_oracion(texto: str) -> bool:
    return texto.rstrip("\"'”’»)]").endswith(FINALES)


class EstandarTests(unittest.TestCase):
    def test_mismas_columnas_y_tokenizador_que_comun_v1(self):
        from construir_comun import COLUMNAS
        from modelo import TOKEN_PATTERN as PATRON_BILSTM
        self.assertEqual(COLUMNAS_BASE, COLUMNAS)
        self.assertEqual(TOKEN_PATTERN.pattern, PATRON_BILSTM.pattern)

    def test_noticia_larga_tope_y_fragmentos_completos(self):
        resultado = preparar_noticia([noticia(40)])  # 600 tokens
        self.assertIsNone(resultado.motivo)
        self.assertIn("tope_noticia", resultado.recortes)
        self.assertIn(len(resultado.fragmentos), (2, 3))
        self.assertLessEqual(resultado.tokens, 400)
        for fragmento in resultado.fragmentos:
            self.assertTrue(100 <= contar_tokens(fragmento) <= 200)
            self.assertTrue(termina_en_oracion(fragmento))
            self.assertTrue(fragmento.startswith("El informe"))
        self.assertAlmostEqual(resultado.peso * len(resultado.fragmentos), 1.0)

    def test_noticia_corta_un_fragmento(self):
        resultado = preparar_noticia([noticia(10)])  # 150 tokens
        self.assertEqual(len(resultado.fragmentos), 1)
        self.assertEqual(resultado.peso, 1.0)
        self.assertEqual(resultado.recortes, [])

    def test_prefiere_pocos_fragmentos_parejos(self):
        texto = noticia(18)  # 18 oraciones de 18 tokens = 324 → 2 de 162, no 3 ni 200 + 124
        self.assertEqual(contar_tokens(texto), 324)
        resultado = preparar_noticia([texto])
        self.assertEqual([contar_tokens(f) for f in resultado.fragmentos], [162, 162])

    def test_limpia_marcas_de_medio(self):
        texto = noticia(10) + " Lee también: Otra cosa distinta. Por María Starostina"
        resultado = preparar_noticia([texto])
        self.assertIn("enlace_relacionado", resultado.patrones)
        self.assertNotIn("Lee también", " ".join(resultado.fragmentos))
        self.assertNotIn("Starostina", " ".join(resultado.fragmentos))

    def test_bordes_de_fragmentos_marcados(self):
        resultado = preparar_noticia([
            "Titular breve de la noticia",
            "a media oración empezó esto. " + noticia(8),
            "Y aquí se cortó la selección sin",
        ])
        self.assertEqual(resultado.recortes, ["inicio_incompleto", "final_incompleto"])
        self.assertTrue(resultado.fragmentos[0].startswith("Titular breve de la noticia El informe"))
        self.assertNotIn("a media oración", resultado.fragmentos[0])
        self.assertTrue(termina_en_oracion(resultado.fragmentos[-1]))

    def test_exclusiones(self):
        ingles = " ".join(["The government said that the law is in effect for all of them."] * 15)
        self.assertEqual(preparar_noticia([ingles]).motivo, "no_espanol")
        sin_puntos = " ".join(f"palabra{i}" for i in range(300))
        self.assertEqual(preparar_noticia([sin_puntos]).motivo, "sin_fin_de_oracion")
        self.assertEqual(preparar_noticia([noticia(5)]).motivo, "menos_de_100_tokens")
        larga = "El informe " + " ".join(f"dato{i}" for i in range(250)) + " para todos."
        self.assertEqual(preparar_noticia([larga]).motivo, "oraciones_demasiado_largas")

    def test_separar_oraciones(self):
        oraciones, resto = separar_oraciones(
            'Dijo "basta." Luego, etc. y más. EE. UU. firmó el acuerdo. ¿Y ahora? Queda sin')
        self.assertEqual(oraciones, ['Dijo "basta."', "Luego, etc. y más.",
                                     "EE. UU. firmó el acuerdo.", "¿Y ahora?"])
        self.assertEqual(resto, "Queda sin")

    def test_filas_estandar(self):
        resultado = preparar_noticia([noticia(30)])
        filas = filas_estandar(resultado, id_articulo="a1", grupo="g", fuente="panel",
                               dominio="d.pe", etiqueta_falsa=1, pliegue="panel")
        self.assertEqual([tuple(fila) for fila in filas], [COLUMNAS_BASE] * len(filas))
        self.assertEqual([fila["id_fragmento"] for fila in filas],
                         [f"a1#{n}" for n in range(len(filas))])
        self.assertAlmostEqual(sum(fila["peso"] for fila in filas), 1.0)
        with self.assertRaises(ValueError):
            filas_estandar(resultado, id_articulo="a", grupo="g", fuente="f", dominio="",
                           etiqueta_falsa=2, pliegue="p")


if __name__ == "__main__":
    unittest.main()
