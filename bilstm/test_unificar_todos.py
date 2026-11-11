"""Comprueba la deduplicación y el aislamiento de etiquetas incompatibles."""

import unittest
import json

from unificar_todos import fingerprint, merge_entries


def sample(text, label, task="noticia_binaria", dataset="fuente"):
    return {"texto": text, "titulo": "", "label": label, "task": task,
            "raw_label": label, "dataset": dataset, "file": dataset,
            "split": "entrenamiento", "url": "", "date": "", "publisher": "",
            "topic": "", "source_id": "1", "quality": ""}


class UnifiedDatasetTests(unittest.TestCase):
    def test_format_variants_collapse_without_losing_provenance(self):
        one = sample("Una noticia extensa, con información nueva.", "1", dataset="a")
        two = sample("UNA NOTICIA EXTENSA con informacion nueva", "1", dataset="b")
        rows, report = merge_entries([one, two])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["n_registros_origen"], 2)
        self.assertEqual(report["duplicados_por_contenido"], 1)
        self.assertEqual(fingerprint(one["texto"]), fingerprint(two["texto"]))

    def test_disagreeing_labels_are_quarantined(self):
        text = "Una noticia extensa, con información nueva."
        rows, report = merge_entries([sample(text, "0"), sample(text, "1")])
        self.assertEqual(rows[0]["grupo_uso"], "conflicto")
        self.assertEqual(rows[0]["etiqueta_binaria"], "")
        self.assertEqual(report["grupos_con_conflicto"], 1)

    def test_satire_not_converted_to_false(self):
        rows, _ = merge_entries([sample("Una sátira extensa sobre política.", "",
                                         task="satira")])
        self.assertEqual(rows[0]["grupo_uso"], "no_binario")
        self.assertEqual(rows[0]["etiqueta_binaria"], "")

    def test_same_url_near_copy_merges_and_preserves_sources(self):
        first = sample("El parlamento anunció una decisión importante para el país. " * 3,
                       "1", dataset="a")
        second = sample(first["texto"] + "Hoy.", "1", dataset="b")
        first["url"] = second["url"] = "https://ejemplo.org/noticia"
        rows, report = merge_entries([first, second])
        self.assertEqual(len(rows), 1)
        self.assertEqual(report["duplicados_por_url"], 1)
        self.assertEqual(json.loads(rows[0]["datasets_origen"]), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
