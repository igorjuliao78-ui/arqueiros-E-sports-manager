import unittest

from efootball import (
    calculate_build,
    optimize_allocation,
    progression_cost,
    progression_points_for_level,
)


class ProgressionCalculatorTests(unittest.TestCase):
    def test_two_points_per_level(self):
        self.assertEqual(progression_points_for_level(1), 0)
        self.assertEqual(progression_points_for_level(30), 58)

    def test_escalating_category_cost(self):
        self.assertEqual(progression_cost(0), 0)
        self.assertEqual(progression_cost(4), 4)
        self.assertEqual(progression_cost(8), 12)
        self.assertEqual(progression_cost(12), 24)
        self.assertEqual(progression_cost(13), 28)

    def test_category_points_raise_all_mapped_stats(self):
        result = calculate_build(
            {"kicking_power": 80, "speed": 90, "stamina": 85},
            {"LBS": 4},
            3,
        )
        self.assertEqual(result["spent_pp"], 4)
        self.assertEqual(result["remaining_pp"], 0)
        self.assertEqual(result["final_stats"]["kicking_power"], 84)
        self.assertEqual(result["final_stats"]["speed"], 94)
        self.assertEqual(result["final_stats"]["stamina"], 89)

    def test_progression_caps_at_99_then_booster_applies(self):
        result = calculate_build(
            {"speed": 98},
            {"LBS": 1},
            2,
            {"speed": 2},
        )
        self.assertEqual(result["progression_stats"]["speed"], 99)
        self.assertEqual(result["final_stats"]["speed"], 101)

    def test_rejects_allocation_over_level_budget(self):
        with self.assertRaises(ValueError):
            calculate_build({"finishing": 80}, {"SHO": 5}, 2)

    def test_optimizer_stays_within_budget(self):
        result = optimize_allocation(
            {
                "finishing": 82, "offensive_awareness": 85,
                "kicking_power": 80, "speed": 84, "acceleration": 83,
                "ball_control": 78, "dribbling": 80, "stamina": 79,
            },
            20,
            "CF",
        )
        self.assertLessEqual(result["spent_pp"], progression_points_for_level(20))
        self.assertGreater(result["role_fit_score"], 0)
        self.assertEqual(result["position"], "CF")


if __name__ == "__main__":
    unittest.main()
