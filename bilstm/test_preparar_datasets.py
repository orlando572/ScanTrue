"""Pruebas de las reglas que afectan la validez de la evaluación."""

import unittest
from pathlib import Path

from preparar_datasets import FALLEDESINFO_LABELS, record, split_groups, unify


class PreparacionTests(unittest.TestCase):
    def make(self, name, title, text, label, split="entrenamiento", url=""):
        return record(name, Path("ejemplo.csv"), title, title, text, label, label,
                      "noticia", split, "entrenamiento_binario", url=url)

    def test_holds_out_duplicate_text_and_url(self):
        direct = [self.make("a", "Uno", "Noticia con suficientes palabras para evaluar.", 0),
                  self.make("a", "Dos", "Otro texto suficiente para una noticia real.", 1,
                            url="https://ejemplo.org/a")]
        nondirect = [self.make("b", "Uno", "Noticia con suficientes palabras para evaluar.", 0,
                               split="prueba"),
                     self.make("b", "Tres", "La misma URL contiene un texto con más datos.", 1,
                               split="validacion", url="https://ejemplo.org/a")]
        unified, audit = unify(direct, nondirect)
        self.assertEqual(len(unified), 2)
        self.assertEqual({r["particion"] for r in unified}, {"prueba", "validacion"})
        self.assertEqual(audit["duplicados_retirados"], 1)
        self.assertEqual(audit["urls_duplicadas_retiradas"], 1)

    def test_conflicting_labels_are_quarantined(self):
        a = self.make("a", "Uno", "Esta misma noticia aparece con etiquetas diferentes.", 0)
        b = self.make("b", "Uno", "Esta misma noticia aparece con etiquetas diferentes.", 1)
        unified, audit = unify([a], [b])
        self.assertEqual(unified, [])
        self.assertEqual(audit["etiquetas_conflictivas"], 2)

    def test_group_split_keeps_equal_titles_together(self):
        rows = [self.make("politico", f"Titular {i // 2}",
                          f"Noticia política de ejemplo con texto suficiente número {i}.", i % 2)
                for i in range(40)]
        split_groups(rows)
        splits = {}
        for row in rows:
            splits.setdefault(row["titulo"], set()).add(row["particion"])
        self.assertTrue(all(len(value) == 1 for value in splits.values()))
        self.assertEqual({r["particion"] for r in rows},
                         {"entrenamiento", "validacion", "prueba"})

    def test_short_text_is_not_used_for_training(self):
        row = self.make("a", "Hola", "Texto corto", 0)
        self.assertEqual(row["uso"], "excluido")

    def test_same_title_in_external_test_is_removed_from_training(self):
        title = "El mismo titular aparece con texto modificado"
        train = self.make("a", title, "Versión larga del texto de entrenamiento.", 0)
        test = self.make("b", title, "Versión larga del texto para prueba externa.", 0,
                         split="prueba")
        unified, audit = unify([train], [test])
        self.assertEqual(len(unified), 1)
        self.assertEqual(unified[0]["particion"], "prueba")
        self.assertEqual(audit["titulares_cruzados_retirados"], 1)

    def test_falledesinfo_verdicts(self):
        self.assertEqual(FALLEDESINFO_LABELS, {"T1": 0, "T2": 1, "T3": 1})


if __name__ == "__main__":
    unittest.main()
