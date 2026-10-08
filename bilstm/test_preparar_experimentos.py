import unittest

import pandas as pd

from preparar_experimentos import POLITICAL, build_variants, choose_political


class ExperimentosTests(unittest.TestCase):
    def test_limited_sample_never_exceeds_one_quarter(self):
        common = pd.DataFrame({"etiqueta": ["0"] * 40 + ["1"] * 60})
        political = pd.DataFrame({"etiqueta": ["0"] * 100 + ["1"] * 100})
        sample = choose_political(common, political)
        self.assertEqual(len(sample), 33)
        self.assertLessEqual(len(sample) / (len(common) + len(sample)), 0.25)
        self.assertEqual(sample.etiqueta.value_counts().to_dict(), {"1": 20, "0": 13})

    def test_evaluation_is_identical_and_contains_no_politics(self):
        rows = []
        for split, count in (("entrenamiento", 12), ("validacion", 4), ("prueba", 4)):
            for i in range(count):
                rows.append(dict(dataset="externo", particion=split,
                                 etiqueta=str(i % 2), texto=f"externo {split} {i}",
                                 grupo_duplicados=f"e-{split}-{i}"))
        for i in range(30):
            rows.append(dict(dataset=POLITICAL, particion="entrenamiento",
                             etiqueta=str(i % 2), texto=f"politico {i}",
                             grupo_duplicados=f"p-{i}"))
        variants = build_variants(pd.DataFrame(rows))
        self.assertTrue(variants["sin_politica"]["validacion"].equals(
            variants["politica_25"]["validacion"]))
        self.assertTrue(variants["sin_politica"]["prueba"].equals(
            variants["politica_25"]["prueba"]))
        self.assertEqual(len(variants["politica_25"]["entrenamiento"]), 16)
        self.assertFalse((variants["sin_politica"]["entrenamiento"].dataset == POLITICAL).any())


if __name__ == "__main__":
    unittest.main()
