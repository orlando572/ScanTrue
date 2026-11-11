"""Pruebas de limpieza y grupos que protegen contra fuga de datos."""

import json
import unittest

from depurar_y_particionar import group_related, new_partitions, quality_reason


def row(index, title="", body="", source="spanish_political_fake_news", label="1"):
    text = (title + " " + body).strip()
    return {"id": str(index), "texto": text, "titulo": title, "url": "",
            "huella_texto": str(index), "dataset_principal": source,
            "datasets_origen": json.dumps([source]), "etiqueta_binaria": label}


class CleaningTests(unittest.TestCase):
    def test_headline_length_alone_does_not_exclude(self):
        self.assertEqual(quality_reason(row(1, "El Congreso aprobó la reforma")), "")
        self.assertEqual(quality_reason(row(2, "Sanciones: ilegalidad amparada")),
                         "menos_de_cinco_palabras")

    def test_satire_contamination_quarantined(self):
        sample = row(1, "Titular de prueba con contenido", source="spanish_fake_and_real_news_acosta", label="0")
        self.assertEqual(quality_reason(sample), "acosta_fuente_con_satira_en_clase_fake")
        sample["etiqueta_binaria"] = "1"
        self.assertEqual(quality_reason(sample), "acosta_fuente_con_satira_en_clase_fake")

    def test_incomplete_speech_quarantined(self):
        sample = row(1, "", "Discurso íntegro de Javier Zarzalejos Estimados conciudadanos y conciudadanas,")
        self.assertEqual(quality_reason(sample), "discurso_incompleto")

    def test_same_body_with_different_headline_remains_together(self):
        body = "El ministro explicó ante el Congreso todas las medidas de la reforma. " * 3
        rows = [row(1, "El ministro presenta la reforma", body),
                row(2, "El ministro rechaza la reforma", body)]
        groups, _ = group_related(rows)
        self.assertEqual(groups[0], groups[1])

    def test_reserved_source_and_related_text_stay_out_of_training(self):
        rows = [row(i, f"Titular diferente número {i}", "Texto completo " * 10,
                    source="fakedes_iberlef_2021" if i == 0 else "spanish_political_fake_news",
                    label=str(i % 2)) for i in range(20)]
        # Una única URL conecta dos registros de fuentes diferentes.
        rows[0]["url"] = rows[1]["url"] = "https://ejemplo.org/noticia"
        groups, _ = group_related(rows)
        self.assertTrue(all(group == groups[0] for group in groups))

    def test_partitioning_never_splits_a_related_group(self):
        rows = [row(i, f"Titular de la noticia número {i}",
                    f"Contenido distinto del caso {i} con suficientes detalles.",
                    source="fakedes_iberlef_2021" if i == 0 else "spanish_political_fake_news",
                    label=str(i % 2)) for i in range(100)]
        rows[1]["url"] = rows[2]["url"] = "https://ejemplo.org/copia"
        groups, _ = group_related(rows)
        splits = new_partitions(rows, groups)
        self.assertEqual(splits[0], "prueba_fuentes_reservadas")
        self.assertEqual(splits[1], splits[2])
        self.assertEqual(len(set(splits)), 4)


if __name__ == "__main__":
    unittest.main()
