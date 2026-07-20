import importlib
import unittest


class GenerateMetricsImportTest(unittest.TestCase):
    def test_generate_metrics_import_and_data(self):
        module = importlib.import_module("generate_metrics")
        data = module.get_confusion_matrix_data()
        self.assertEqual(data["categories"], ["Politics", "Sports", "Tech", "Entertainment", "Business"])
        self.assertEqual(len(data["matrix"]), 5)
        self.assertEqual(len(data["per_class"]), 5)
        self.assertIsInstance(data["overall_acc"], (int, float))


if __name__ == "__main__":
    unittest.main()
