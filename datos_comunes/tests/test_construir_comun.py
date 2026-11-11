"""Pruebas del conjunto común: limpieza, fragmentos, grupos y carga por pliegue.

Uso: bilstm/.venv/bin/python -m unittest discover -s datos_comunes/tests
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comun import particiones, separar_interna  # noqa: E402
from construir_comun import (  # noqa: E402
    agrupar, dominio, elegir_congelada, fragmentar, separar_titulo, tokenize,
)
from limpieza import idioma_probable, limpiar  # noqa: E402


def oraciones(n: int, palabras: int = 10, prefijo: str = "palabra") -> str:
    return " ".join(" ".join(f"{prefijo}{i}x{j}" for j in range(palabras)) + "." for i in range(n))


class LimpiezaTests(unittest.TestCase):
    def test_quita_marcas_de_procedencia(self):
        casos = {
            "México.- Luego de que se anunciara la medida": "Luego de que se anunciara la medida",
            "MÉXICO, D.F. (apro).- El general habló": "El general habló",
            "Texto final.Conforme a los criterios deThe Trust Project": "Texto final.",
            "Algo pasó.FuenteNoticias relevantes no encontradas.": "Algo pasó.",
            "El día *NUMBER* de mayo": "El día de mayo",
            "Ver https://ejemplo.com/a?b=1 ahora": "Ver ahora",
            "Lo dijo @usuario en la red #fin #cierre": "Lo dijo en la red",
            "Cierre del texto. Por María Starostina": "Cierre del texto.",
        }
        for antes, esperado in casos.items():
            with self.subTest(antes=antes):
                self.assertEqual(limpiar(antes)[0], esperado)

    def test_normaliza_sin_perder_mayusculas_ni_tildes(self):
        texto, cambios = limpiar("La &quot;Unión&quot;  dijo '\"'\"sí'\"'\" ayer")
        self.assertEqual(texto, 'La "Unión" dijo "sí" ayer')
        self.assertIn("comillas_escapadas", cambios)

    def test_no_toca_texto_normal(self):
        texto = "El presidente dijo que por la tarde habrá reunión con Pedro Sánchez."
        self.assertEqual(limpiar(texto), (texto, []))

    def test_registra_ejemplos(self):
        ejemplos = {}
        limpiar("México.- Algo ocurrió en la ciudad", ejemplos)
        self.assertEqual(len(ejemplos["dateline_inicio"]), 1)


class FragmentosTests(unittest.TestCase):
    def test_articulo_corto_se_descarta(self):
        self.assertEqual(fragmentar("", oraciones(5), np.random.default_rng(0), 400), [])

    def test_articulo_menor_que_el_objetivo_se_toma_completo(self):
        cuerpo = oraciones(12)  # 120 tokens
        trozos = fragmentar("Un titular", cuerpo, np.random.default_rng(1), 400)
        if len(trozos) == 1:
            self.assertEqual(trozos[0], "Un titular " + cuerpo)

    def test_limites_tamano_titular_y_maximo(self):
        titulo = "Titular de prueba"
        cuerpo = oraciones(300)  # 3000 tokens
        for semilla in range(30):
            trozos = fragmentar(titulo, cuerpo, np.random.default_rng(semilla), 400)
            self.assertTrue(1 <= len(trozos) <= 4)
            self.assertTrue(trozos[0].startswith(titulo))
            for i, trozo in enumerate(trozos):
                self.assertTrue(100 <= len(tokenize(trozo)) <= 400, len(tokenize(trozo)))
                if i:
                    self.assertNotIn("Titular", trozo)
            # Cortes en límite de oración en un texto con oraciones de 10 tokens.
            for trozo in trozos[1:]:
                self.assertTrue(trozo.endswith("."))

    def test_fragmentos_sin_solaparse(self):
        cuerpo = oraciones(200)
        trozos = fragmentar("", cuerpo, np.random.default_rng(3), 400)
        palabras = [set(tokenize(t)) for t in trozos]
        for i in range(len(palabras)):
            for j in range(i + 1, len(palabras)):
                self.assertFalse(palabras[i] & palabras[j])

    def test_tamano_no_depende_de_la_clase(self):
        # La función no recibe la etiqueta: misma longitud y semilla => mismos tamaños.
        a = fragmentar("", oraciones(100, prefijo="a"), np.random.default_rng(7), 400)
        b = fragmentar("", oraciones(100, prefijo="b"), np.random.default_rng(7), 400)
        self.assertEqual([len(tokenize(t)) for t in a], [len(tokenize(t)) for t in b])

    def test_texto_sin_puntuacion_se_corta_por_palabras(self):
        cuerpo = " ".join(f"p{i}" for i in range(2000))
        trozos = fragmentar("", cuerpo, np.random.default_rng(5), 400)
        self.assertTrue(all(100 <= len(tokenize(t)) <= 400 for t in trozos))


class GruposTests(unittest.TestCase):
    def fila(self, i, texto, url="", titulo="", forzado=""):
        return {"id": str(i), "texto": texto, "titulo": titulo, "url": url, "grupo_forzado": forzado}

    def test_une_url_casi_duplicados_y_forzados(self):
        base = oraciones(30)
        filas = [self.fila(0, base, url="http://a.com/x"), self.fila(1, "otro " + base[:-40]),
                 self.fila(2, oraciones(30, prefijo="z"), url="https://a.com/x/"),
                 self.fila(3, oraciones(30, prefijo="q")), self.fila(4, oraciones(30, prefijo="r"), forzado="p"),
                 self.fila(5, oraciones(30, prefijo="s"), forzado="p")]
        grupos, _ = agrupar(filas)
        self.assertEqual(grupos[0], grupos[1])
        self.assertEqual(grupos[0], grupos[2])
        self.assertNotEqual(grupos[0], grupos[3])
        self.assertEqual(grupos[4], grupos[5])

    def test_dominio_y_titulo(self):
        self.assertEqual(dominio("www.ElMundo.es/a"), "elmundo.es")
        self.assertEqual(dominio("https://m.facebook.com/x"), "m.facebook.com")
        self.assertEqual(separar_titulo("Hola mundo cuerpo", "Hola mundo"), ("Hola mundo", "cuerpo"))

    def test_congelada_estratificada(self):
        articulos = [{"id_articulo": f"{f}{i}", "grupo": f"{f}{i // 2}", "fuente": f,
                      "etiqueta_falsa": i % 2} for f in ("v1", "fakedes") for i in range(400)]
        elegidos = elegir_congelada(articulos, 0.15, 42)
        for fuente in ("v1", "fakedes"):
            n = sum(a["grupo"] in elegidos for a in articulos if a["fuente"] == fuente)
            self.assertAlmostEqual(n / 400, 0.15, delta=0.02)


class CargaTests(unittest.TestCase):
    def setUp(self):
        filas = []
        for fuente, pliegue in (("v1", "F1"), ("fakedes", "F2"), ("polyglot", "F3")):
            for i in range(100):
                filas.append({"id_fragmento": f"{fuente}{i}#0", "id_articulo": f"{fuente}{i}",
                              "grupo": f"g{fuente}{i}", "fuente": fuente, "dominio": "",
                              "texto": "t", "etiqueta_falsa": i % 2, "peso": 1.0,
                              "tokens_bilstm": 100, "pliegue": pliegue})
        filas[0]["grupo"] = "compartido"   # v1 y fakedes comparten un grupo
        filas[100]["grupo"] = "compartido"
        self.frame = pd.DataFrame(filas)

    def test_pliegue_sin_fugas(self):
        p = particiones("F1", desarrollo=self.frame)
        self.assertEqual(set(p["validacion"].fuente), {"v1"})
        self.assertNotIn("compartido", set(p["entrenamiento"].grupo))
        self.assertEqual(set(p["entrenamiento"].fuente), {"fakedes", "polyglot"})
        total = len(p["entrenamiento"]) + len(p["validacion_interna"])
        self.assertEqual(total, 199)
        self.assertAlmostEqual(len(p["validacion_interna"]) / total, 0.10, delta=0.03)

    def test_interna_fija(self):
        a = separar_interna(self.frame)
        b = separar_interna(self.frame)
        self.assertTrue((a == b).all())

    def test_todo_sin_validacion(self):
        p = particiones("todo", desarrollo=self.frame)
        self.assertEqual(len(p["entrenamiento"]), 300)
        self.assertTrue(p["validacion"].empty and p["validacion_interna"].empty)


class IdiomaTests(unittest.TestCase):
    def test_detecta_textos_que_no_son_espanol(self):
        self.assertEqual(idioma_probable("The editorial office of the newspaper published that it was on the list "
                                         "and this is from the government"), "en")
        self.assertEqual(idioma_probable("Le gouvernement est dans une situation qui pour les citoyens "
                                         "sont avec cette crise"), "fr")
        self.assertEqual(idioma_probable("Il governo che è della crisi sono gli stessi nel paese anche questo"), "it")

    def test_espanol_con_cita_breve_sigue_siendo_espanol(self):
        texto = ("El presidente dijo que los datos del informe son falsos y que la oposición "
                 "miente sobre el gasto. Según el texto, «the end of the story» no está cerca.")
        self.assertEqual(idioma_probable(texto), "es")

    def test_texto_corto_sin_evidencia_queda_en_espanol(self):
        self.assertEqual(idioma_probable("Les Corts aprueban la ley"), "es")


if __name__ == "__main__":
    unittest.main()
