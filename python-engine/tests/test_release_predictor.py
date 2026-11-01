import unittest

from prediction.release_predictor import predict_next_release


class ReleasePredictorTests(unittest.TestCase):
    def test_requires_minimum_history(self):
        result = predict_next_release([
            "2022-01-01",
            "2023-01-01",
            "2024-01-01",
        ])
        self.assertIsNone(result["predicted_date"])
        self.assertEqual(result["data_points"], 2)

    def test_predicts_from_last_five_intervals(self):
        result = predict_next_release([
            "2020-01-01",
            "2021-01-01",
            "2022-01-01",
            "2023-01-01",
            "2024-01-01",
            "2025-01-01",
        ])
        self.assertIsNotNone(result["predicted_date"])
        self.assertEqual(result["data_points"], 5)
        self.assertLessEqual(result["window_start"], result["predicted_date"])
        self.assertGreaterEqual(result["window_end"], result["predicted_date"])


if __name__ == "__main__":
    unittest.main()
