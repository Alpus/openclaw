#!/usr/bin/env python3
"""Tests for gym_analytics.py — written BEFORE the implementation (TDD)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT = str(Path(__file__).parent / "gym_analytics.py")


def run_cmd(*args, expect_fail=False):
    """Run gym_analytics.py with args, return (stdout, stderr, returncode)."""
    result = subprocess.run(
        [sys.executable, SCRIPT] + list(args),
        capture_output=True, text=True, timeout=30
    )
    if not expect_fail:
        if result.returncode != 0:
            raise AssertionError(
                f"Command failed (rc={result.returncode}): {args}\n"
                f"stderr: {result.stderr}\nstdout: {result.stdout}"
            )
    return result.stdout, result.stderr, result.returncode


def make_session(date, exercises, day="A", notes="", adherence="full", duration=50, bw=None):
    d = {"date": date, "day": day, "duration_min": duration, "bodyweight_kg": bw,
         "actual": exercises, "notes": notes, "plan_adherence": adherence}
    return json.dumps(d)


def make_exercise(name, muscle_group, sets):
    return {"name": name, "muscle_group": muscle_group, "sets": sets}


def make_set(reps, weight_kg, rpe=None):
    s = {"reps": reps, "weight_kg": weight_kg}
    if rpe is not None:
        s["rpe"] = rpe
    return s


class HistoryFixture:
    """Context manager that creates a temp dir with session JSON files."""
    def __init__(self, sessions=None):
        self.sessions = sessions or []
        self.dir = None

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        for date_str, data in self.sessions:
            with open(os.path.join(self.dir, f"{date_str}.json"), "w") as f:
                f.write(data)
        return self.dir

    def __exit__(self, *args):
        shutil.rmtree(self.dir)


# ---- Fixtures ----

SQUAT_SETS = [make_set(8, 80, 7), make_set(8, 80, 8), make_set(6, 85, 9)]
BENCH_SETS = [make_set(10, 60), make_set(8, 65)]
OHP_SETS = [make_set(10, 40), make_set(10, 40)]
ROW_SETS = [make_set(10, 50), make_set(10, 50)]

SESSION_A = make_session("2026-01-05", [
    make_exercise("Squat", "legs", SQUAT_SETS),
    make_exercise("Bench Press", "chest", BENCH_SETS),
    make_exercise("Seated Cable Row", "back", ROW_SETS),
], day="A", notes="Good session", duration=55)

SESSION_B = make_session("2026-01-07", [
    make_exercise("OHP", "shoulders", OHP_SETS),
    make_exercise("Pull-ups", "back", [make_set(8, 0), make_set(6, 0)]),
    make_exercise("Squat", "legs", [make_set(10, 80), make_set(10, 80)]),
], day="B", notes="Felt tired")

SESSION_C = make_session("2026-01-12", [
    make_exercise("Squat", "legs", [make_set(8, 85, 7), make_set(8, 85, 8)]),
    make_exercise("Bench Press", "chest", [make_set(10, 65), make_set(10, 65)]),
    make_exercise("Seated Cable Row", "back", [make_set(12, 50)]),
], day="A", notes="Progressed squat", duration=50)

SESSION_D = make_session("2026-01-14", [
    make_exercise("OHP", "shoulders", [make_set(10, 42.5)]),
    make_exercise("Lateral Raise", "shoulders", [make_set(15, 10), make_set(15, 10)]),
    make_exercise("Bicep Curl", "arms", [make_set(12, 15), make_set(12, 15)]),
], day="B")

MULTI_SESSIONS = [
    ("2026-01-05", SESSION_A),
    ("2026-01-07", SESSION_B),
    ("2026-01-12", SESSION_C),
    ("2026-01-14", SESSION_D),
]


# ==================== e1rm ====================

class TestE1RM(unittest.TestCase):
    def test_basic(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, rc = run_cmd("e1rm", d)
            self.assertIn("Squat", out)
            self.assertIn("Bench Press", out)

    def test_json_output(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("e1rm", d, "--json")
            data = json.loads(out)
            self.assertIsInstance(data, dict)
            # Should have exercise names as keys
            self.assertIn("Squat", data)

    def test_empty_history(self):
        with HistoryFixture() as d:
            _, _, rc = run_cmd("e1rm", d, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_single_session(self):
        with HistoryFixture([("2026-01-05", SESSION_A)]) as d:
            out, _, _ = run_cmd("e1rm", d)
            self.assertIn("Squat", out)

    def test_bodyweight_exercise_excluded(self):
        """Exercises with 0 weight should not appear in e1rm."""
        with HistoryFixture([("2026-01-07", SESSION_B)]) as d:
            out, _, _ = run_cmd("e1rm", d)
            self.assertNotIn("Pull-ups", out)

    def test_e1rm_values_correct(self):
        """Check Epley formula: 85 * (1 + 6/30) = 102.0"""
        with HistoryFixture([("2026-01-05", SESSION_A)]) as d:
            out, _, _ = run_cmd("e1rm", d, "--json")
            data = json.loads(out)
            # Squat best set: 85kg x 6 = 102.0 e1RM
            self.assertAlmostEqual(data["Squat"]["e1rm"], 102.0, places=1)

    def test_latest_e1rm(self):
        """Should show the latest (most recent session) best e1rm."""
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("e1rm", d, "--json")
            data = json.loads(out)
            # Latest squat: 2026-01-12, 85x8 = 85*(1+8/30) = 107.67
            self.assertAlmostEqual(data["Squat"]["e1rm"], 107.67, places=0)


# ==================== volume ====================

class TestVolume(unittest.TestCase):
    def test_basic(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("volume", d)
            self.assertIn("legs", out.lower())

    def test_json(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("volume", d, "--json")
            data = json.loads(out)
            self.assertIsInstance(data, list)

    def test_empty(self):
        with HistoryFixture() as d:
            _, _, rc = run_cmd("volume", d, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_counts_hard_sets(self):
        """Each working set counts as 1 hard set for its muscle group."""
        with HistoryFixture([("2026-01-05", SESSION_A)]) as d:
            out, _, _ = run_cmd("volume", d, "--json")
            data = json.loads(out)
            # Week of 2026-01-05: legs=3 sets, chest=2, back=2
            week = data[0]
            self.assertEqual(week["legs"], 3)
            self.assertEqual(week["chest"], 2)
            self.assertEqual(week["back"], 2)

    def test_multiple_weeks(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("volume", d, "--json")
            data = json.loads(out)
            self.assertGreaterEqual(len(data), 1)

    def test_bodyweight_sets_counted(self):
        """Pull-ups with 0 weight still count as hard sets for volume."""
        with HistoryFixture([("2026-01-07", SESSION_B)]) as d:
            out, _, _ = run_cmd("volume", d, "--json")
            data = json.loads(out)
            week = data[0]
            self.assertEqual(week["back"], 2)  # 2 sets of pull-ups


# ==================== progress ====================

class TestProgress(unittest.TestCase):
    def test_basic(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("progress", d, "Squat")
            self.assertIn("Squat", out)

    def test_json(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("progress", d, "Squat", "--json")
            data = json.loads(out)
            self.assertIsInstance(data, list)
            self.assertGreater(len(data), 0)

    def test_exercise_not_found(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            _, _, rc = run_cmd("progress", d, "Deadlift", expect_fail=True)
            self.assertEqual(rc, 1)

    def test_shows_dates(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("progress", d, "Squat")
            self.assertIn("2026-01-05", out)
            self.assertIn("2026-01-12", out)

    def test_empty_history(self):
        with HistoryFixture() as d:
            _, _, rc = run_cmd("progress", d, "Squat", expect_fail=True)
            self.assertEqual(rc, 1)

    def test_fuzzy_match(self):
        """Should match 'Bench' to 'Bench Press'."""
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("progress", d, "Bench")
            self.assertIn("Bench", out)


# ==================== summary ====================

class TestSummary(unittest.TestCase):
    def test_basic(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("summary", d)
            # Should show the most recent session
            self.assertIn("2026-01-14", out)

    def test_json(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("summary", d, "--json")
            data = json.loads(out)
            self.assertEqual(data["date"], "2026-01-14")

    def test_empty(self):
        with HistoryFixture() as d:
            _, _, rc = run_cmd("summary", d, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_shows_exercises(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("summary", d)
            self.assertIn("OHP", out)

    def test_shows_adherence(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("summary", d)
            self.assertIn("full", out.lower())

    def test_shows_volume(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("summary", d, "--json")
            data = json.loads(out)
            self.assertIn("total_sets", data)


# ==================== compare ====================

class TestCompare(unittest.TestCase):
    def test_basic(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("compare", d, "2026-01-05", "2026-01-12")
            self.assertIn("Squat", out)

    def test_json(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("compare", d, "2026-01-05", "2026-01-12", "--json")
            data = json.loads(out)
            self.assertIn("date1", data)
            self.assertIn("date2", data)

    def test_missing_date(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            _, _, rc = run_cmd("compare", d, "2026-01-05", "2099-01-01", expect_fail=True)
            self.assertEqual(rc, 1)

    def test_same_date(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("compare", d, "2026-01-05", "2026-01-05")
            self.assertIn("Squat", out)

    def test_shows_diff(self):
        """Compare should show e1RM changes."""
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("compare", d, "2026-01-05", "2026-01-12", "--json")
            data = json.loads(out)
            self.assertIn("exercises", data)


# ==================== chart-e1rm ====================

class TestChartE1RM(unittest.TestCase):
    def test_basic(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out_path = os.path.join(d, "chart.png")
            run_cmd("chart-e1rm", d, out_path)
            self.assertTrue(os.path.exists(out_path))

    def test_vertical_default(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out_path = os.path.join(d, "chart.png")
            run_cmd("chart-e1rm", d, out_path)
            self.assertTrue(os.path.exists(out_path))
            # File should be non-empty
            self.assertGreater(os.path.getsize(out_path), 1000)

    def test_horizontal(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out_path = os.path.join(d, "chart.png")
            run_cmd("chart-e1rm", d, out_path, "--horizontal")
            self.assertTrue(os.path.exists(out_path))

    def test_empty_history(self):
        with HistoryFixture() as d:
            out_path = os.path.join(d, "chart.png")
            _, _, rc = run_cmd("chart-e1rm", d, out_path, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_lifts_filter(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out_path = os.path.join(d, "chart.png")
            run_cmd("chart-e1rm", d, out_path, "--lifts", "Squat,OHP")
            self.assertTrue(os.path.exists(out_path))

    def test_single_session_chart(self):
        with HistoryFixture([("2026-01-05", SESSION_A)]) as d:
            out_path = os.path.join(d, "chart.png")
            run_cmd("chart-e1rm", d, out_path)
            self.assertTrue(os.path.exists(out_path))


# ==================== chart-volume ====================

class TestChartVolume(unittest.TestCase):
    def test_basic(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out_path = os.path.join(d, "vol.png")
            run_cmd("chart-volume", d, out_path)
            self.assertTrue(os.path.exists(out_path))

    def test_empty(self):
        with HistoryFixture() as d:
            out_path = os.path.join(d, "vol.png")
            _, _, rc = run_cmd("chart-volume", d, out_path, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_vertical(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out_path = os.path.join(d, "vol.png")
            run_cmd("chart-volume", d, out_path, "--vertical")
            self.assertTrue(os.path.exists(out_path))

    def test_horizontal(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out_path = os.path.join(d, "vol.png")
            run_cmd("chart-volume", d, out_path, "--horizontal")
            self.assertTrue(os.path.exists(out_path))


# ==================== log ====================

class TestLog(unittest.TestCase):
    def test_log_json_string(self):
        with HistoryFixture() as d:
            session = make_session("2026-03-01", [
                make_exercise("Squat", "legs", [make_set(8, 80)])
            ])
            run_cmd("log", d, session)
            self.assertTrue(os.path.exists(os.path.join(d, "2026-03-01.json")))

    def test_log_from_file(self):
        with HistoryFixture() as d:
            session = make_session("2026-03-02", [
                make_exercise("Bench Press", "chest", [make_set(10, 60)])
            ])
            fpath = os.path.join(d, "input.json")
            with open(fpath, "w") as f:
                f.write(session)
            run_cmd("log", d, fpath)
            self.assertTrue(os.path.exists(os.path.join(d, "2026-03-02.json")))

    def test_log_invalid_json(self):
        with HistoryFixture() as d:
            _, _, rc = run_cmd("log", d, "not-valid-json{{{", expect_fail=True)
            self.assertEqual(rc, 1)

    def test_log_missing_date(self):
        with HistoryFixture() as d:
            bad = json.dumps({"actual": []})
            _, _, rc = run_cmd("log", d, bad, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_log_missing_exercises(self):
        with HistoryFixture() as d:
            bad = json.dumps({"date": "2026-03-01"})
            _, _, rc = run_cmd("log", d, bad, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_log_duplicate_date_overwrites(self):
        """Logging to same date should overwrite."""
        with HistoryFixture() as d:
            s1 = make_session("2026-03-01", [make_exercise("Squat", "legs", [make_set(8, 80)])])
            s2 = make_session("2026-03-01", [make_exercise("Bench", "chest", [make_set(10, 60)])])
            run_cmd("log", d, s1)
            run_cmd("log", d, s2)
            with open(os.path.join(d, "2026-03-01.json")) as f:
                data = json.load(f)
            self.assertEqual(data["actual"][0]["name"], "Bench")

    def test_log_output(self):
        with HistoryFixture() as d:
            session = make_session("2026-03-01", [
                make_exercise("Squat", "legs", [make_set(8, 80)])
            ])
            out, _, _ = run_cmd("log", d, session)
            self.assertIn("2026-03-01", out)


# ==================== validate ====================

class TestValidate(unittest.TestCase):
    def test_valid_sessions(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, rc = run_cmd("validate", d)
            self.assertEqual(rc, 0)

    def test_empty_dir(self):
        with HistoryFixture() as d:
            _, _, rc = run_cmd("validate", d, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_invalid_json(self):
        with HistoryFixture() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                f.write("{bad json")
            _, _, rc = run_cmd("validate", d, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_missing_required_field(self):
        with HistoryFixture() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                json.dump({"date": "2026-01-01"}, f)  # missing exercises
            _, _, rc = run_cmd("validate", d, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_date_mismatch(self):
        """Filename date should match JSON date field."""
        with HistoryFixture() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                json.dump({"date": "2026-01-02", "actual": []}, f)
            _, _, rc = run_cmd("validate", d, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_json_output(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("validate", d, "--json")
            data = json.loads(out)
            self.assertIn("valid", data)

    def test_reports_all_errors(self):
        """Should report errors for each bad file."""
        with HistoryFixture() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                f.write("bad")
            with open(os.path.join(d, "2026-01-02.json"), "w") as f:
                json.dump({"date": "2026-01-02"}, f)
            _, err, rc = run_cmd("validate", d, "--json", expect_fail=True)
            out_text, _, _ = run_cmd("validate", d, "--json", expect_fail=True)
            # rc should be 1
            self.assertEqual(rc, 1)


# ==================== Edge Cases ====================

class TestEdgeCases(unittest.TestCase):
    def test_no_args(self):
        _, _, rc = run_cmd(expect_fail=True)
        self.assertNotEqual(rc, 0)

    def test_invalid_command(self):
        _, _, rc = run_cmd("nonexistent", "/tmp", expect_fail=True)
        self.assertNotEqual(rc, 0)

    def test_nonexistent_dir(self):
        _, _, rc = run_cmd("e1rm", "/tmp/nonexistent_gym_dir_xyz", expect_fail=True)
        self.assertEqual(rc, 1)

    def test_missing_weight_in_set(self):
        """Sets without weight_kg should be handled gracefully."""
        session = make_session("2026-01-01", [
            make_exercise("Hanging Leg Raise", "abs", [{"reps": 12}])
        ])
        with HistoryFixture([("2026-01-01", session)]) as d:
            # volume should still work
            out, _, _ = run_cmd("volume", d, "--json")
            data = json.loads(out)
            self.assertEqual(data[0]["abs"], 1)

    def test_exercise_missing_sets(self):
        session = make_session("2026-01-01", [
            {"name": "Squat", "muscle_group": "legs"}  # no sets key
        ])
        with HistoryFixture([("2026-01-01", session)]) as d:
            # Should handle gracefully
            out, _, _ = run_cmd("volume", d, "--json")
            data = json.loads(out)

    def test_session_missing_optional_fields(self):
        """Session without notes, plan_adherence, duration should still work."""
        minimal = json.dumps({
            "date": "2026-01-01",
            "actual": [make_exercise("Squat", "legs", [make_set(8, 80)])]
        })
        with HistoryFixture([("2026-01-01", minimal)]) as d:
            out, _, _ = run_cmd("summary", d, "--json")
            data = json.loads(out)
            self.assertEqual(data["date"], "2026-01-01")

    def test_non_json_files_ignored(self):
        """Non-json files in history dir should be ignored."""
        with HistoryFixture(MULTI_SESSIONS) as d:
            with open(os.path.join(d, "README.md"), "w") as f:
                f.write("ignore me")
            out, _, _ = run_cmd("e1rm", d, "--json")
            data = json.loads(out)
            self.assertIn("Squat", data)

    def test_corrupt_json_file_skipped(self):
        """A corrupt JSON among valid ones should be skipped with warning."""
        with HistoryFixture(MULTI_SESSIONS) as d:
            with open(os.path.join(d, "2026-01-10.json"), "w") as f:
                f.write("{bad")
            out, err, _ = run_cmd("e1rm", d)
            self.assertIn("Squat", out)
            self.assertIn("skip" , err.lower())


# ==================== Session Duration ====================

def make_timed_session(date, exercises, start_time=None, end_time=None, day="A", notes=""):
    d = {"date": date, "day": day, "actual": exercises, "notes": notes}
    if start_time:
        d["start_time"] = start_time
    if end_time:
        d["end_time"] = end_time
    return json.dumps(d)


SESSION_WITH_TIMES = make_timed_session("2026-02-10", [
    {**make_exercise("Cable Crunch", "abs", [make_set(12, 40)]), "start_time": "20:00", "end_time": "20:05"},
    {**make_exercise("Squat", "legs", [make_set(10, 120)] * 4), "start_time": "20:05", "end_time": "20:40"},
], start_time="20:00", end_time="20:55", day="A")


class TestSessionDuration(unittest.TestCase):
    """Tests for session_duration function."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import session_duration
        self.dur = session_duration

    def test_basic(self):
        result = self.dur({"start_time": "19:00", "end_time": "20:15"})
        self.assertEqual(result, ("19:00", "20:15", 75))

    def test_no_start(self):
        self.assertIsNone(self.dur({"end_time": "20:15"}))

    def test_no_end(self):
        self.assertIsNone(self.dur({"start_time": "19:00"}))

    def test_empty(self):
        self.assertIsNone(self.dur({}))

    def test_crosses_midnight(self):
        result = self.dur({"start_time": "23:30", "end_time": "00:15"})
        self.assertEqual(result[2], 45)

    def test_invalid_time(self):
        self.assertIsNone(self.dur({"start_time": "25:00", "end_time": "20:00"}))


class TestSessionTimesValidation(unittest.TestCase):
    """Tests for start_time/end_time validation in log and validate."""

    def test_log_with_valid_times(self):
        with HistoryFixture() as d:
            run_cmd("log", d, SESSION_WITH_TIMES)
            with open(os.path.join(d, "2026-02-10.json")) as f:
                data = json.load(f)
            self.assertEqual(data["start_time"], "20:00")
            self.assertEqual(data["end_time"], "20:55")

    def test_log_invalid_start_time(self):
        with HistoryFixture() as d:
            bad = json.dumps({"date": "2026-02-10", "actual": [], "start_time": "25:00"})
            _, _, rc = run_cmd("log", d, bad, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_log_invalid_exercise_time(self):
        with HistoryFixture() as d:
            bad = json.dumps({"date": "2026-02-10", "exercises": [
                {"name": "Squat", "muscle_group": "legs", "sets": [], "start_time": "99:99"}
            ]})
            _, _, rc = run_cmd("log", d, bad, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_log_no_times_ok(self):
        with HistoryFixture() as d:
            session = make_session("2026-03-01", [make_exercise("Squat", "legs", [make_set(8, 80)])])
            run_cmd("log", d, session)
            self.assertTrue(os.path.exists(os.path.join(d, "2026-03-01.json")))

    def test_validate_with_times(self):
        with HistoryFixture([("2026-02-10", SESSION_WITH_TIMES)]) as d:
            _, _, rc = run_cmd("validate", d)
            self.assertEqual(rc, 0)

    def test_validate_bad_time(self):
        with HistoryFixture() as d:
            bad = json.dumps({"date": "2026-02-10", "actual": [], "start_time": "99:99"})
            with open(os.path.join(d, "2026-02-10.json"), "w") as f:
                f.write(bad)
            _, _, rc = run_cmd("validate", d, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_validate_bad_exercise_time(self):
        with HistoryFixture() as d:
            bad = json.dumps({"date": "2026-02-10", "exercises": [
                {"name": "Squat", "muscle_group": "legs", "sets": [], "end_time": "ab:cd"}
            ]})
            with open(os.path.join(d, "2026-02-10.json"), "w") as f:
                f.write(bad)
            _, _, rc = run_cmd("validate", d, expect_fail=True)
            self.assertEqual(rc, 1)


class TestSummaryWithTimes(unittest.TestCase):
    """Tests for summary using start_time/end_time."""

    def test_summary_shows_duration(self):
        with HistoryFixture([("2026-02-10", SESSION_WITH_TIMES)]) as d:
            out, _, _ = run_cmd("summary", d, "--json")
            data = json.loads(out)
            self.assertEqual(data["started_at"], "20:00")
            self.assertEqual(data["ended_at"], "20:55")
            self.assertEqual(data["computed_duration_min"], 55)

    def test_summary_no_times_still_works(self):
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("summary", d, "--json")
            data = json.loads(out)
            self.assertEqual(data["date"], "2026-01-14")
            self.assertNotIn("started_at", data)


# ==================== Planned Exercises ====================

PLANNED_EXERCISES = [
    {"name": "Cable Crunch", "sets_reps": "1x12", "weight_kg": 40},
    {"name": "Squat", "sets_reps": "4x8-10", "weight_kg": "100-120"},
    {"name": "Bench Press", "sets_reps": "4x8-10", "weight_kg": "60-77.5"},
]

def make_session_with_plan(date, planned, exercises, day="A", notes=""):
    return json.dumps({
        "date": date, "day": day, "actual": exercises,
        "planned": planned, "notes": notes,
    })

SESSION_WITH_PLAN = make_session_with_plan("2026-02-10", PLANNED_EXERCISES, [
    make_exercise("Cable Crunch", "abs", [make_set(12, 40)]),
    make_exercise("Squat", "legs", [make_set(10, 120), make_set(10, 120), make_set(10, 120), make_set(10, 120)]),
    make_exercise("Bench Press", "chest", [make_set(8, 70), make_set(8, 70), make_set(8, 70), make_set(8, 70)]),
])


class TestPlannedExercises(unittest.TestCase):
    """Tests for planned exercises in session JSON."""

    def test_log_with_planned(self):
        """Log should accept and preserve planned array."""
        with HistoryFixture() as d:
            run_cmd("log", d, SESSION_WITH_PLAN)
            with open(os.path.join(d, "2026-02-10.json")) as f:
                data = json.load(f)
            self.assertIn("planned", data)
            self.assertEqual(len(data["planned"]), 3)

    def test_log_without_planned_backward_compat(self):
        """Sessions without planned field should still work."""
        with HistoryFixture() as d:
            session = make_session("2026-02-10", [
                make_exercise("Squat", "legs", [make_set(8, 80)])
            ])
            run_cmd("log", d, session)
            self.assertTrue(os.path.exists(os.path.join(d, "2026-02-10.json")))

    def test_validate_with_planned(self):
        """Validate should accept sessions with valid planned array."""
        with HistoryFixture([("2026-02-10", SESSION_WITH_PLAN)]) as d:
            _, _, rc = run_cmd("validate", d)
            self.assertEqual(rc, 0)

    def test_validate_planned_not_list(self):
        """Validate should reject planned that's not a list."""
        with HistoryFixture() as d:
            bad = json.dumps({"date": "2026-02-10", "actual": [], "planned": "not a list"})
            with open(os.path.join(d, "2026-02-10.json"), "w") as f:
                f.write(bad)
            _, _, rc = run_cmd("validate", d, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_validate_planned_missing_name(self):
        """Each planned exercise must have a name."""
        with HistoryFixture() as d:
            bad = json.dumps({"date": "2026-02-10", "actual": [],
                              "planned": [{"sets_reps": "3x10", "weight_kg": 80}]})
            with open(os.path.join(d, "2026-02-10.json"), "w") as f:
                f.write(bad)
            _, _, rc = run_cmd("validate", d, expect_fail=True)
            self.assertEqual(rc, 1)

    def test_summary_plan_vs_actual(self):
        """Summary should show plan vs actual comparison when planned exists."""
        with HistoryFixture([("2026-02-10", SESSION_WITH_PLAN)]) as d:
            out, _, _ = run_cmd("summary", d, "--json")
            data = json.loads(out)
            self.assertIn("plan_comparison", data)
            self.assertIsInstance(data["plan_comparison"], list)

    def test_summary_plan_comparison_content(self):
        """Plan comparison should show planned vs actual for each exercise."""
        with HistoryFixture([("2026-02-10", SESSION_WITH_PLAN)]) as d:
            out, _, _ = run_cmd("summary", d, "--json")
            data = json.loads(out)
            comp = data["plan_comparison"]
            # Should have entries for planned exercises
            self.assertGreater(len(comp), 0)
            first = comp[0]
            self.assertIn("name", first)
            self.assertIn("planned", first)
            self.assertIn("actual", first)

    def test_summary_no_plan_backward_compat(self):
        """Summary without planned should not have plan_comparison."""
        with HistoryFixture(MULTI_SESSIONS) as d:
            out, _, _ = run_cmd("summary", d, "--json")
            data = json.loads(out)
            self.assertNotIn("plan_comparison", data)


# ==================== Goal Lines ====================

class TestGoalParsing(unittest.TestCase):
    """Tests for parsing goals from plan.md."""

    def test_parse_goals_from_plan(self):
        """Should parse strength targets from plan.md."""
        # Import the function directly
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import parse_goals_from_plan
        plan_text = """### Силовые targets (e1RM)
| Lift | Сейчас | Цель (12 нед) | Прирост |
|------|--------|---------------|---------|
| Squat | ~160 | ~170 | +6% |
| Bench (flat) | ~98 | ~110 | +12% |
| OHP | ~60 | ~67 | +12% |
"""
        goals = parse_goals_from_plan(plan_text)
        self.assertIn("Squat", goals)
        self.assertEqual(goals["Squat"], 170)
        self.assertIn("Bench", goals)
        self.assertEqual(goals["Bench"], 110)
        self.assertIn("OHP", goals)
        self.assertEqual(goals["OHP"], 67)

    def test_parse_goals_empty(self):
        """Should return empty dict when no goals table."""
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import parse_goals_from_plan
        goals = parse_goals_from_plan("No goals here")
        self.assertEqual(goals, {})

    def test_parse_goals_partial(self):
        """Should handle table with some unparseable rows."""
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import parse_goals_from_plan
        plan_text = """### Силовые targets (e1RM)
| Lift | Сейчас | Цель (12 нед) | Прирост |
|------|--------|---------------|---------|
| Squat | ~160 | ~170 | +6% |
| Pull-ups | +6 × 8 | +10 × 8 | +4 kg |
"""
        goals = parse_goals_from_plan(plan_text)
        self.assertIn("Squat", goals)
        self.assertEqual(goals["Squat"], 170)


class TestGoalLineData(unittest.TestCase):
    """Tests for goal line data generation (not rendering)."""

    def test_compute_goal_lines(self):
        """Should compute start/end points for goal lines."""
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import compute_goal_lines
        goals = {"Squat": 170, "Bench": 110}
        start_date = datetime(2026, 1, 5)
        # start_values: current e1RM at start
        start_values = {"Squat": 160, "Bench": 98}
        lines = compute_goal_lines(goals, start_date, start_values, weeks=12)
        self.assertIn("Squat", lines)
        self.assertEqual(lines["Squat"]["start_value"], 160)
        self.assertEqual(lines["Squat"]["end_value"], 170)
        self.assertEqual(lines["Squat"]["start_date"], start_date)
        self.assertEqual(lines["Squat"]["end_date"], start_date + timedelta(weeks=12))

    def test_compute_goal_lines_missing_start(self):
        """Should skip exercises with no starting value."""
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import compute_goal_lines
        goals = {"Squat": 170, "Bench": 110}
        start_values = {"Squat": 160}  # no Bench
        lines = compute_goal_lines(goals, datetime(2026, 1, 5), start_values)
        self.assertIn("Squat", lines)
        self.assertNotIn("Bench", lines)


class TestE1RMEpley(unittest.TestCase):
    """Direct unit tests for e1rm_epley function."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import e1rm_epley
        self.e1rm = e1rm_epley

    def test_single_rep(self):
        self.assertEqual(self.e1rm(100, 1), 100)

    def test_zero_weight(self):
        self.assertEqual(self.e1rm(0, 10), 0)

    def test_zero_reps(self):
        self.assertEqual(self.e1rm(100, 0), 0)

    def test_negative_weight(self):
        self.assertEqual(self.e1rm(-10, 5), 0)

    def test_ten_reps(self):
        # 100 * (1 + 10/30) = 133.33...
        self.assertAlmostEqual(self.e1rm(100, 10), 133.33, places=1)

    def test_five_reps(self):
        # 80 * (1 + 5/30) = 93.33...
        self.assertAlmostEqual(self.e1rm(80, 5), 93.33, places=1)


class TestBestE1RMForExercise(unittest.TestCase):
    """Direct unit tests for best_e1rm_for_exercise."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import best_e1rm_for_exercise
        self.best = best_e1rm_for_exercise

    def test_empty_sets(self):
        self.assertEqual(self.best({"sets": []}), 0)

    def test_no_sets_key(self):
        self.assertEqual(self.best({}), 0)

    def test_single_set(self):
        ex = {"sets": [{"weight_kg": 100, "reps": 10}]}
        self.assertAlmostEqual(self.best(ex), 133.33, places=1)

    def test_picks_best(self):
        ex = {"sets": [
            {"weight_kg": 60, "reps": 10},
            {"weight_kg": 100, "reps": 5},
            {"weight_kg": 80, "reps": 8},
        ]}
        result = self.best(ex)
        # 100*(1+5/30)=116.67, 80*(1+8/30)=101.33, 60*(1+10/30)=80
        self.assertAlmostEqual(result, 116.67, places=1)

    def test_bodyweight_set_zero_weight(self):
        ex = {"sets": [{"weight_kg": 0, "reps": 12}]}
        self.assertEqual(self.best(ex), 0)

    def test_missing_weight_field(self):
        ex = {"sets": [{"reps": 12}]}
        self.assertEqual(self.best(ex), 0)


class TestNormalizeMatch(unittest.TestCase):
    """Direct unit tests for normalize_match."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import normalize_match
        self.match = normalize_match

    def test_exact_match(self):
        self.assertTrue(self.match("Squat", "Squat"))

    def test_case_insensitive(self):
        self.assertTrue(self.match("squat", "SQUAT"))

    def test_substring_match(self):
        self.assertTrue(self.match("Bench Press (flat)", "bench"))

    def test_alias_squat(self):
        self.assertTrue(self.match("Squat", "barbell back squat"))

    def test_alias_ohp(self):
        self.assertTrue(self.match("OHP", "overhead press"))

    def test_alias_row(self):
        self.assertTrue(self.match("Seated Cable Row", "cable row"))

    def test_no_match(self):
        self.assertFalse(self.match("Squat", "Deadlift"))

    def test_alias_bench(self):
        self.assertTrue(self.match("bench press", "flat bench"))


class TestWeekKey(unittest.TestCase):
    """Direct unit tests for week_key."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import week_key
        self.wk = week_key

    def test_basic(self):
        result = self.wk("2026-02-10")
        self.assertRegex(result, r"^\d{4}-W\d{2}$")

    def test_same_week(self):
        self.assertEqual(self.wk("2026-02-10"), self.wk("2026-02-11"))

    def test_different_weeks(self):
        self.assertNotEqual(self.wk("2026-02-10"), self.wk("2026-02-17"))


class TestWeekStart(unittest.TestCase):
    """Direct unit tests for week_start."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import week_start
        self.ws = week_start

    def test_monday_returns_self(self):
        self.assertEqual(self.ws("2026-02-09"), "2026-02-09")  # Monday

    def test_tuesday_returns_monday(self):
        self.assertEqual(self.ws("2026-02-10"), "2026-02-09")  # Tuesday → Monday

    def test_sunday_returns_monday(self):
        self.assertEqual(self.ws("2026-02-15"), "2026-02-09")  # Sunday → Monday



class TestSessionDuration(unittest.TestCase):
    """Direct unit tests for session_duration."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import session_duration
        self.dur = session_duration

    def test_basic(self):
        session = {"start_time": "19:00", "end_time": "20:15"}
        result = self.dur(session)
        self.assertEqual(result, ("19:00", "20:15", 75))

    def test_no_start(self):
        self.assertIsNone(self.dur({"end_time": "20:15"}))

    def test_no_end(self):
        self.assertIsNone(self.dur({"start_time": "19:00"}))

    def test_empty(self):
        self.assertIsNone(self.dur({}))

    def test_crosses_midnight(self):
        session = {"start_time": "23:30", "end_time": "00:30"}
        result = self.dur(session)
        self.assertEqual(result, ("23:30", "00:30", 60))

    def test_invalid_start_time(self):
        self.assertIsNone(self.dur({"start_time": "25:00", "end_time": "20:00"}))

    def test_invalid_end_time(self):
        self.assertIsNone(self.dur({"start_time": "19:00", "end_time": "bad"}))


class TestValidateTimeStr(unittest.TestCase):
    """Direct unit tests for validate_time_str."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import validate_time_str
        self.v = validate_time_str

    def test_valid(self):
        self.assertTrue(self.v("00:00"))
        self.assertTrue(self.v("23:59"))
        self.assertTrue(self.v("12:30"))

    def test_invalid_hour(self):
        self.assertFalse(self.v("24:00"))
        self.assertFalse(self.v("25:00"))

    def test_invalid_minute(self):
        self.assertFalse(self.v("12:60"))

    def test_bad_format(self):
        self.assertFalse(self.v("bad"))
        self.assertFalse(self.v(""))
        self.assertFalse(self.v(None))


class TestComputeKPIs(unittest.TestCase):
    """Direct unit tests for _compute_kpis."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import _compute_kpis
        self.kpis = _compute_kpis

    def test_empty(self):
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis([], {})
        self.assertEqual(adh, 0)
        self.assertEqual(avg, 0)
        self.assertEqual(change, 0)

    def test_single_session(self):
        sessions = [{"date": "2026-02-10"}]
        lift_data = {"Squat": ([datetime(2026, 2, 10)], [160])}
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis(sessions, lift_data)
        self.assertEqual(avg, 160)
        self.assertEqual(change, 0)

    def test_two_sessions_in_same_window(self):
        """Two sessions within 14 days — both in current window, no previous window."""
        sessions = [{"date": "2026-02-03"}, {"date": "2026-02-10"}]
        lift_data = {
            "Squat": ([datetime(2026, 2, 3), datetime(2026, 2, 10)], [150, 160]),
            "Bench": ([datetime(2026, 2, 3), datetime(2026, 2, 10)], [90, 95]),
        }
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis(sessions, lift_data)
        # Both in current window, best Squat=160, best Bench=95, avg=127.5
        self.assertAlmostEqual(avg, 127.5, places=1)
        # No prev window data → change = 0
        self.assertEqual(change, 0)


class TestChartOrientation(unittest.TestCase):
    """Direct unit tests for _chart_orientation."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import _chart_orientation
        self.orient = _chart_orientation

    def test_default_vertical(self):
        args = type('A', (), {'horizontal': False})()
        self.assertEqual(self.orient(args), "vertical")

    def test_horizontal(self):
        args = type('A', (), {'horizontal': True})()
        self.assertEqual(self.orient(args), "horizontal")


# ==================== Goals ====================

class TestGoalsLoadAndGet(unittest.TestCase):
    """Direct unit tests for goals loading functions."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import load_goals, get_latest_goals, default_goals_path
        self.load = load_goals
        self.latest = get_latest_goals
        self.default_path = default_goals_path

    def test_load_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('[]')
            f.flush()
            result = self.load(f.name)
            self.assertEqual(result, [])
            os.unlink(f.name)

    def test_load_nonexistent(self):
        result = self.load('/tmp/nonexistent_goals_xyz.json')
        self.assertEqual(result, [])

    def test_load_valid(self):
        data = [{"date_set": "2026-01-26", "target_date": "2026-04-19",
                 "goals": {"Squat": 170}, "note": "test"}]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = self.load(f.name)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["goals"]["Squat"], 170)
            os.unlink(f.name)

    def test_latest_goals(self):
        data = [
            {"date_set": "2026-01-01", "target_date": "2026-03-01", "goals": {"Squat": 150}},
            {"date_set": "2026-01-26", "target_date": "2026-04-19", "goals": {"Squat": 170}},
        ]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = self.latest(f.name)
            self.assertEqual(result["goals"]["Squat"], 170)
            os.unlink(f.name)

    def test_latest_goals_empty(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('[]')
            f.flush()
            result = self.latest(f.name)
            self.assertIsNone(result)
            os.unlink(f.name)

    def test_default_goals_path(self):
        result = self.default_path('/home/user/health/gym/history')
        self.assertTrue(result.endswith('goals.json'))
        self.assertIn('gym', result)


class TestGoalsCommand(unittest.TestCase):
    """CLI tests for goals command."""

    def test_goals_list(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{"date_set": "2026-01-26", "target_date": "2026-04-19",
                        "goals": {"Squat": 170}, "note": "test"}], f)
            f.flush()
            out, _, _ = run_cmd("goals", "list", "--goals-file", f.name)
            self.assertIn("Squat", out)
            self.assertIn("170", out)
            os.unlink(f.name)

    def test_goals_list_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{"date_set": "2026-01-26", "target_date": "2026-04-19",
                        "goals": {"Squat": 170}}], f)
            f.flush()
            out, _, _ = run_cmd("goals", "list", "--goals-file", f.name, "--json")
            data = json.loads(out)
            self.assertIsInstance(data, list)
            os.unlink(f.name)

    def test_goals_current(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{"date_set": "2026-01-26", "target_date": "2026-04-19",
                        "goals": {"Squat": 170, "OHP": 70}}], f)
            f.flush()
            out, _, _ = run_cmd("goals", "current", "--goals-file", f.name)
            self.assertIn("Squat", out)
            self.assertIn("OHP", out)
            os.unlink(f.name)

    def test_goals_current_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{"date_set": "2026-01-26", "target_date": "2026-04-19",
                        "goals": {"Squat": 170}}], f)
            f.flush()
            out, _, _ = run_cmd("goals", "current", "--goals-file", f.name, "--json")
            data = json.loads(out)
            self.assertEqual(data["goals"]["Squat"], 170)
            os.unlink(f.name)

    def test_goals_add(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([], f)
            f.flush()
            new_goal = json.dumps({"target_date": "2026-06-01", "goals": {"Squat": 180}})
            out, _, _ = run_cmd("goals", "add", "--goals-file", f.name, "--goal-json", new_goal)
            self.assertIn("Goal added", out)
            # Verify file
            with open(f.name) as ff:
                data = json.load(ff)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["goals"]["Squat"], 180)
            os.unlink(f.name)

    def test_goals_add_appends(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{"date_set": "2026-01-01", "target_date": "2026-03-01",
                        "goals": {"Squat": 150}}], f)
            f.flush()
            new_goal = json.dumps({"target_date": "2026-06-01", "goals": {"Squat": 180}})
            run_cmd("goals", "add", "--goals-file", f.name, "--goal-json", new_goal)
            with open(f.name) as ff:
                data = json.load(ff)
            self.assertEqual(len(data), 2)
            os.unlink(f.name)

    def test_goals_list_empty(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([], f)
            f.flush()
            _, _, rc = run_cmd("goals", "list", "--goals-file", f.name, expect_fail=True)
            self.assertEqual(rc, 1)
            os.unlink(f.name)

    def test_goals_add_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([], f)
            f.flush()
            _, _, rc = run_cmd("goals", "add", "--goals-file", f.name,
                               "--goal-json", "not json", expect_fail=True)
            self.assertEqual(rc, 1)
            os.unlink(f.name)

    def test_goals_add_missing_goals_field(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([], f)
            f.flush()
            _, _, rc = run_cmd("goals", "add", "--goals-file", f.name,
                               "--goal-json", '{"target_date": "2026-06-01"}', expect_fail=True)
            self.assertEqual(rc, 1)
            os.unlink(f.name)

    def test_goals_add_missing_target_date(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([], f)
            f.flush()
            _, _, rc = run_cmd("goals", "add", "--goals-file", f.name,
                               "--goal-json", '{"goals": {"Squat": 180}}', expect_fail=True)
            self.assertEqual(rc, 1)
            os.unlink(f.name)


class TestChartWithGoals(unittest.TestCase):
    """Test that chart-e1rm reads goals from goals.json."""

    def test_chart_with_goals_file(self):
        """Chart should render goal lines when goals.json exists as sibling."""
        with HistoryFixture(MULTI_SESSIONS) as d:
            # Create goals.json as sibling to history dir
            goals_path = os.path.join(os.path.dirname(d), "goals.json")
            goals = [{"date_set": "2026-01-05", "target_date": "2026-04-05",
                       "goals": {"Squat": 170, "OHP": 67}}]
            with open(goals_path, "w") as f:
                json.dump(goals, f)
            out_path = os.path.join(d, "chart.png")
            run_cmd("chart-e1rm", d, out_path, "--goals-file", goals_path)
            self.assertTrue(os.path.exists(out_path))
            self.assertGreater(os.path.getsize(out_path), 1000)
            os.unlink(goals_path)

    def test_chart_without_goals(self):
        """Chart should work fine without goals.json."""
        with HistoryFixture(MULTI_SESSIONS) as d:
            out_path = os.path.join(d, "chart.png")
            run_cmd("chart-e1rm", d, out_path)
            self.assertTrue(os.path.exists(out_path))


# ==================== In-process tests for coverage ====================
# The subprocess-based tests above don't register in coverage.
# These tests import and call functions directly.

sys.path.insert(0, str(Path(__file__).parent))
import gym_analytics as ga
from unittest.mock import patch, MagicMock
from argparse import Namespace
from io import StringIO


def _make_args(**kwargs):
    """Create a Namespace with common defaults."""
    defaults = dict(json=False, vertical=False, horizontal=False, lifts=None,
                    period="all", plan=None, goals_file=None)
    defaults.update(kwargs)
    return Namespace(**defaults)


def _write_sessions(tmp, session_list):
    """Write session dicts to tmp dir as JSON files, return dir path."""
    d = str(tmp)
    for s in session_list:
        fname = f"{s['date']}.json"
        with open(os.path.join(d, fname), "w") as f:
            json.dump(s, f)
    return d


def _session(date, exercises, **kwargs):
    """Build a session dict."""
    s = {"date": date, "actual": exercises}
    s.update(kwargs)
    return s


def _ex(name, mg, sets):
    return {"name": name, "muscle_group": mg, "sets": sets}


def _s(w, r, rpe=None):
    s = {"weight_kg": w, "reps": r}
    if rpe is not None:
        s["rpe"] = rpe
    return s


# Sample sessions as dicts (not JSON strings)
SESS_A = _session("2026-01-05", [
    _ex("Squat", "legs", [_s(80, 8), _s(80, 8), _s(85, 6)]),
    _ex("Bench Press", "chest", [_s(60, 10), _s(65, 8)]),
    _ex("Seated Cable Row", "back", [_s(50, 10), _s(50, 10)]),
], day="A", notes="Good session", duration_min=55, plan_adherence="full")

SESS_B = _session("2026-01-07", [
    _ex("OHP", "shoulders", [_s(40, 10), _s(40, 10)]),
    _ex("Pull-ups", "back", [_s(0, 8), _s(0, 6)]),
    _ex("Squat", "legs", [_s(80, 10), _s(80, 10)]),
], day="B", notes="Felt tired")

SESS_C = _session("2026-01-12", [
    _ex("Squat", "legs", [_s(85, 8), _s(85, 8)]),
    _ex("Bench Press", "chest", [_s(65, 10), _s(65, 10)]),
    _ex("Seated Cable Row", "back", [_s(50, 12)]),
], day="A", notes="Progressed squat", duration_min=50)

SESS_D = _session("2026-01-14", [
    _ex("OHP", "shoulders", [_s(42.5, 10)]),
    _ex("Lateral Raise", "shoulders", [_s(10, 15), _s(10, 15)]),
    _ex("Bicep Curl", "arms", [_s(15, 12), _s(15, 12)]),
], day="B")

ALL_SESS = [SESS_A, SESS_B, SESS_C, SESS_D]


class TestLoadSessionsDirect(unittest.TestCase):
    def test_load_valid(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), ALL_SESS)
            sessions = ga.load_sessions(d)
            self.assertEqual(len(sessions), 4)

    def test_load_nonexistent_dir(self):
        sessions = ga.load_sessions("/tmp/nonexistent_xyz_abc")
        self.assertEqual(sessions, [])

    def test_load_skips_bad_json(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), [SESS_A])
            with open(os.path.join(d, "2026-01-10.json"), "w") as f:
                f.write("{bad json")
            sessions = ga.load_sessions(d)
            self.assertEqual(len(sessions), 1)

    def test_load_skips_missing_date(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "2026-01-10.json"), "w") as f:
                json.dump({"actual": []}, f)
            sessions = ga.load_sessions(d)
            self.assertEqual(len(sessions), 0)

    def test_load_legacy_exercises_key(self):
        with tempfile.TemporaryDirectory() as d:
            legacy = {"date": "2026-01-01", "exercises": [_ex("Squat", "legs", [_s(80, 8)])]}
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                json.dump(legacy, f)
            sessions = ga.load_sessions(d)
            self.assertEqual(len(sessions), 1)
            self.assertIn("actual", sessions[0])


class TestValidatePlannedDirect(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(ga.validate_planned([{"name": "Squat"}]), [])

    def test_not_list(self):
        errors = ga.validate_planned("not a list")
        self.assertEqual(len(errors), 1)

    def test_missing_name(self):
        errors = ga.validate_planned([{"sets_reps": "3x10"}])
        self.assertEqual(len(errors), 1)

    def test_not_dict_entry(self):
        errors = ga.validate_planned(["not a dict"])
        self.assertEqual(len(errors), 1)


class TestLoadGoalsCorrupt(unittest.TestCase):
    def test_corrupt_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{bad json")
            f.flush()
            result = ga.load_goals(f.name)
            self.assertEqual(result, [])
            os.unlink(f.name)


class TestErrExit(unittest.TestCase):
    def test_err_exit(self):
        with self.assertRaises(SystemExit) as cm:
            ga.err_exit("test error")
        self.assertEqual(cm.exception.code, 1)


class TestCmdE1RMDirect(unittest.TestCase):
    def test_empty_sessions(self):
        with self.assertRaises(SystemExit):
            ga.cmd_e1rm([], _make_args())

    def test_no_weight_data(self):
        sessions = [_session("2026-01-01", [_ex("Pull-ups", "back", [_s(0, 8)])])]
        with self.assertRaises(SystemExit):
            ga.cmd_e1rm(sessions, _make_args())

    def test_json_output(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_e1rm(ALL_SESS, _make_args(json=True))
            data = json.loads(mock_out.getvalue())
            self.assertIn("Squat", data)
            self.assertIn("e1rm", data["Squat"])

    def test_text_output(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_e1rm(ALL_SESS, _make_args())
            out = mock_out.getvalue()
            self.assertIn("Exercise", out)
            self.assertIn("Squat", out)


class TestCmdVolumeDirect(unittest.TestCase):
    def test_empty(self):
        with self.assertRaises(SystemExit):
            ga.cmd_volume([], _make_args())

    def test_json_output(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_volume(ALL_SESS, _make_args(json=True))
            data = json.loads(mock_out.getvalue())
            self.assertIsInstance(data, list)

    def test_text_output(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_volume(ALL_SESS, _make_args())
            out = mock_out.getvalue()
            self.assertIn("Week", out)


class TestCmdProgressDirect(unittest.TestCase):
    def test_empty(self):
        with self.assertRaises(SystemExit):
            ga.cmd_progress([], _make_args(exercise="Squat"))

    def test_not_found(self):
        with self.assertRaises(SystemExit):
            ga.cmd_progress(ALL_SESS, _make_args(exercise="Deadlift"))

    def test_json_output(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_progress(ALL_SESS, _make_args(json=True, exercise="Squat"))
            data = json.loads(mock_out.getvalue())
            self.assertIsInstance(data, list)
            self.assertGreater(len(data), 0)

    def test_text_output(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_progress(ALL_SESS, _make_args(exercise="Squat"))
            out = mock_out.getvalue()
            self.assertIn("Squat", out)
            self.assertIn("2026-01-05", out)


class TestCmdSummaryDirect(unittest.TestCase):
    def test_empty(self):
        with self.assertRaises(SystemExit):
            ga.cmd_summary([], _make_args())

    def test_json_output(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_summary(ALL_SESS, _make_args(json=True))
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["date"], "2026-01-14")

    def test_text_output(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_summary(ALL_SESS, _make_args())
            out = mock_out.getvalue()
            self.assertIn("2026-01-14", out)
            self.assertIn("OHP", out)

    def test_text_with_duration(self):
        sess = [_session("2026-01-05", [_ex("Squat", "legs", [_s(80, 8)])],
                         duration_min=55, plan_adherence="full")]
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_summary(sess, _make_args())
            out = mock_out.getvalue()
            self.assertIn("55", out)

    def test_text_with_notes(self):
        sess = [_session("2026-01-05", [_ex("Squat", "legs", [_s(80, 8)])],
                         notes="Great workout")]
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_summary(sess, _make_args())
            self.assertIn("Great workout", mock_out.getvalue())

    def test_json_with_times(self):
        sess = [_session("2026-01-05", [_ex("Squat", "legs", [_s(80, 8)])],
                         start_time="19:00", end_time="20:15")]
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_summary(sess, _make_args(json=True))
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["started_at"], "19:00")
            self.assertEqual(data["computed_duration_min"], 75)

    def test_with_planned(self):
        planned = [{"name": "Squat", "sets_reps": "3x8", "weight_kg": 80},
                   {"name": "Bench Press", "sets_reps": "3x10", "weight_kg": 60}]
        sess = [_session("2026-01-05",
                         [_ex("Squat", "legs", [_s(80, 8), _s(80, 8), _s(80, 8)])],
                         planned=planned)]
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_summary(sess, _make_args(json=True))
            data = json.loads(mock_out.getvalue())
            self.assertIn("plan_comparison", data)
            # Bench was planned but not done
            bench_comp = [c for c in data["plan_comparison"] if c["name"] == "Bench Press"]
            self.assertEqual(len(bench_comp), 1)
            self.assertFalse(bench_comp[0]["completed"])

    def test_text_with_planned(self):
        planned = [{"name": "Squat", "sets_reps": "3x8", "weight_kg": 80}]
        sess = [_session("2026-01-05",
                         [_ex("Squat", "legs", [_s(80, 8)])],
                         planned=planned)]
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_summary(sess, _make_args())
            out = mock_out.getvalue()
            self.assertIn("Plan vs Actual", out)
            self.assertIn("✓", out)

    def test_text_without_planned(self):
        """When no planned, should show exercises list."""
        sess = [_session("2026-01-05",
                         [_ex("Squat", "legs", [_s(80, 8)])],
                         notes="")]
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_summary(sess, _make_args())
            out = mock_out.getvalue()
            self.assertIn("Exercises", out)


class TestCmdCompareDirect(unittest.TestCase):
    def test_missing_date1(self):
        with self.assertRaises(SystemExit):
            ga.cmd_compare(ALL_SESS, _make_args(date1="2099-01-01", date2="2026-01-05"))

    def test_missing_date2(self):
        with self.assertRaises(SystemExit):
            ga.cmd_compare(ALL_SESS, _make_args(date1="2026-01-05", date2="2099-01-01"))

    def test_json_output(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_compare(ALL_SESS, _make_args(json=True, date1="2026-01-05", date2="2026-01-12"))
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["date1"], "2026-01-05")
            self.assertIn("exercises", data)

    def test_text_output(self):
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_compare(ALL_SESS, _make_args(date1="2026-01-05", date2="2026-01-12"))
            out = mock_out.getvalue()
            self.assertIn("Compare", out)
            self.assertIn("Squat", out)

    def test_diff_zero_shows_equals(self):
        """When e1rm hasn't changed, should show '='."""
        sess1 = _session("2026-01-01", [_ex("Squat", "legs", [_s(80, 8)])])
        sess2 = _session("2026-01-02", [_ex("Squat", "legs", [_s(80, 8)])])
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_compare([sess1, sess2], _make_args(date1="2026-01-01", date2="2026-01-02"))
            self.assertIn("=", mock_out.getvalue())

    def test_new_exercise_in_second(self):
        """Exercise only in session 2 should appear."""
        sess1 = _session("2026-01-01", [_ex("Squat", "legs", [_s(80, 8)])])
        sess2 = _session("2026-01-02", [_ex("Bench Press", "chest", [_s(60, 10)])])
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            ga.cmd_compare([sess1, sess2], _make_args(json=True, date1="2026-01-01", date2="2026-01-02"))
            data = json.loads(mock_out.getvalue())
            names = [e["name"] for e in data["exercises"]]
            self.assertIn("Bench Press", names)


class TestCmdGoalsDirect(unittest.TestCase):
    def _goals_file(self, tmp, data):
        p = os.path.join(str(tmp), "goals.json")
        with open(p, "w") as f:
            json.dump(data, f)
        return p

    def test_list_text(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [
                {"date_set": "2026-01-01", "target_date": "2026-04-01",
                 "goals": {"Squat": 170}, "note": "test note"}
            ])
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="list", goal_json=None))
                out = mock_out.getvalue()
                self.assertIn("Squat", out)
                self.assertIn("test note", out)

    def test_list_json(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [{"date_set": "2026-01-01", "target_date": "2026-04-01",
                                        "goals": {"Squat": 170}}])
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="list", json=True, goal_json=None))
                data = json.loads(mock_out.getvalue())
                self.assertIsInstance(data, list)

    def test_list_empty(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [])
            with self.assertRaises(SystemExit):
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="list", goal_json=None))

    def test_current_text(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [
                {"date_set": "2026-01-01", "target_date": "2026-04-01",
                 "goals": {"Squat": 150}},
                {"date_set": "2026-02-01", "target_date": "2026-05-01",
                 "goals": {"Squat": 170}, "note": "updated"}
            ])
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="current", goal_json=None))
                out = mock_out.getvalue()
                self.assertIn("170", out)
                self.assertIn("updated", out)

    def test_current_json(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [{"date_set": "2026-01-01", "target_date": "2026-04-01",
                                        "goals": {"Squat": 170}}])
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="current", json=True, goal_json=None))
                data = json.loads(mock_out.getvalue())
                self.assertEqual(data["goals"]["Squat"], 170)

    def test_current_empty(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [])
            with self.assertRaises(SystemExit):
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="current", goal_json=None))

    def test_add(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [])
            goal_json = json.dumps({"target_date": "2026-06-01", "goals": {"Squat": 180}})
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="add", goal_json=goal_json))
                self.assertIn("Goal added", mock_out.getvalue())
            with open(gp) as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertIn("date_set", data[0])

    def test_add_no_json(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [])
            with self.assertRaises(SystemExit):
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="add", goal_json=None))

    def test_add_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [])
            with self.assertRaises(SystemExit):
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="add", goal_json="not json"))

    def test_add_missing_goals_field(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [])
            with self.assertRaises(SystemExit):
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="add",
                                        goal_json='{"target_date": "2026-06-01"}'))

    def test_add_missing_target_date(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [])
            with self.assertRaises(SystemExit):
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="add",
                                        goal_json='{"goals": {"Squat": 180}}'))

    def test_unknown_subcmd(self):
        with tempfile.TemporaryDirectory() as d:
            gp = self._goals_file(d, [])
            with self.assertRaises(SystemExit):
                ga.cmd_goals(_make_args(goals_file=gp, goals_command="unknown", goal_json=None))


class TestCmdLogDirect(unittest.TestCase):
    def test_log_json_string(self):
        with tempfile.TemporaryDirectory() as d:
            source = json.dumps({"date": "2026-03-01", "actual": [_ex("Squat", "legs", [_s(80, 8)])]})
            with patch('sys.stdout', new_callable=StringIO):
                ga.cmd_log(Namespace(history_dir=d, source=source))
            self.assertTrue(os.path.exists(os.path.join(d, "2026-03-01.json")))

    def test_log_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            source_data = {"date": "2026-03-02", "actual": [_ex("Bench", "chest", [_s(60, 10)])]}
            fpath = os.path.join(d, "input.json")
            with open(fpath, "w") as f:
                json.dump(source_data, f)
            with patch('sys.stdout', new_callable=StringIO):
                ga.cmd_log(Namespace(history_dir=d, source=fpath))
            self.assertTrue(os.path.exists(os.path.join(d, "2026-03-02.json")))

    def test_log_invalid_json_string(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                ga.cmd_log(Namespace(history_dir=d, source="not json{{{"))

    def test_log_invalid_json_file(self):
        with tempfile.TemporaryDirectory() as d:
            fpath = os.path.join(d, "bad.json")
            with open(fpath, "w") as f:
                f.write("{bad json")
            with self.assertRaises(SystemExit):
                ga.cmd_log(Namespace(history_dir=d, source=fpath))

    def test_log_missing_date(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                ga.cmd_log(Namespace(history_dir=d, source=json.dumps({"actual": []})))

    def test_log_missing_actual(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                ga.cmd_log(Namespace(history_dir=d, source=json.dumps({"date": "2026-01-01"})))

    def test_log_legacy_exercises_key(self):
        with tempfile.TemporaryDirectory() as d:
            source = json.dumps({"date": "2026-03-01", "exercises": [_ex("Squat", "legs", [_s(80, 8)])]})
            with patch('sys.stdout', new_callable=StringIO):
                ga.cmd_log(Namespace(history_dir=d, source=source))
            self.assertTrue(os.path.exists(os.path.join(d, "2026-03-01.json")))

    def test_log_invalid_date_format(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                ga.cmd_log(Namespace(history_dir=d,
                                     source=json.dumps({"date": "not-a-date", "actual": []})))

    def test_log_invalid_start_time(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                ga.cmd_log(Namespace(history_dir=d,
                                     source=json.dumps({"date": "2026-01-01", "actual": [], "start_time": "25:00"})))

    def test_log_invalid_exercise_time(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                ga.cmd_log(Namespace(history_dir=d,
                                     source=json.dumps({"date": "2026-01-01",
                                                        "actual": [{"name": "Squat", "sets": [], "start_time": "99:99"}]})))

    def test_log_invalid_planned(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                ga.cmd_log(Namespace(history_dir=d,
                                     source=json.dumps({"date": "2026-01-01", "actual": [],
                                                        "planned": [{"sets_reps": "3x10"}]})))

    def test_log_valid_planned(self):
        with tempfile.TemporaryDirectory() as d:
            source = json.dumps({"date": "2026-01-01", "actual": [],
                                 "planned": [{"name": "Squat"}]})
            with patch('sys.stdout', new_callable=StringIO):
                ga.cmd_log(Namespace(history_dir=d, source=source))


class TestCmdValidateDirect(unittest.TestCase):
    def test_valid_files(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), ALL_SESS)
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                ga.cmd_validate(None, _make_args(history_dir=d))
                self.assertIn("valid", mock_out.getvalue())

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                ga.cmd_validate(None, _make_args(history_dir=d))

    def test_empty_dir_json(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                with patch('sys.stdout', new_callable=StringIO) as mock_out:
                    ga.cmd_validate(None, _make_args(history_dir=d, json=True))

    def test_invalid_json_file(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                f.write("{bad")
            with self.assertRaises(SystemExit):
                ga.cmd_validate(None, _make_args(history_dir=d))

    def test_missing_date(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                json.dump({"actual": []}, f)
            with self.assertRaises(SystemExit):
                ga.cmd_validate(None, _make_args(history_dir=d))

    def test_missing_actual(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                json.dump({"date": "2026-01-01"}, f)
            with self.assertRaises(SystemExit):
                ga.cmd_validate(None, _make_args(history_dir=d))

    def test_date_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                json.dump({"date": "2026-01-02", "actual": []}, f)
            with self.assertRaises(SystemExit):
                ga.cmd_validate(None, _make_args(history_dir=d))

    def test_bad_start_time(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                json.dump({"date": "2026-01-01", "actual": [], "start_time": "99:99"}, f)
            with self.assertRaises(SystemExit):
                ga.cmd_validate(None, _make_args(history_dir=d))

    def test_bad_exercise_time(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                json.dump({"date": "2026-01-01",
                           "actual": [{"name": "Squat", "sets": [], "end_time": "ab:cd"}]}, f)
            with self.assertRaises(SystemExit):
                ga.cmd_validate(None, _make_args(history_dir=d))

    def test_bad_planned(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                json.dump({"date": "2026-01-01", "actual": [],
                           "planned": [{"sets_reps": "3x10"}]}, f)
            with self.assertRaises(SystemExit):
                ga.cmd_validate(None, _make_args(history_dir=d))

    def test_json_output_valid(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), ALL_SESS)
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                ga.cmd_validate(None, _make_args(history_dir=d, json=True))
                data = json.loads(mock_out.getvalue())
                self.assertTrue(data["valid"])

    def test_json_output_errors(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                f.write("{bad")
            with self.assertRaises(SystemExit):
                with patch('sys.stdout', new_callable=StringIO) as mock_out:
                    ga.cmd_validate(None, _make_args(history_dir=d, json=True))

    def test_text_output_errors(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                f.write("{bad")
            with self.assertRaises(SystemExit):
                ga.cmd_validate(None, _make_args(history_dir=d))

    def test_legacy_exercises_key(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "2026-01-01.json"), "w") as f:
                json.dump({"date": "2026-01-01", "exercises": []}, f)
            with patch('sys.stdout', new_callable=StringIO):
                ga.cmd_validate(None, _make_args(history_dir=d))


class TestCmdChartE1RMDirect(unittest.TestCase):
    def test_empty(self):
        with self.assertRaises(SystemExit):
            ga.cmd_chart_e1rm([], _make_args(output="/tmp/test.png", history_dir="/tmp"))

    def test_vertical(self):
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "chart.png")
            ga.cmd_chart_e1rm(ALL_SESS, _make_args(output=out_path, history_dir=d))
            self.assertTrue(os.path.exists(out_path))

    def test_horizontal(self):
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "chart.png")
            ga.cmd_chart_e1rm(ALL_SESS, _make_args(output=out_path, history_dir=d, horizontal=True))
            self.assertTrue(os.path.exists(out_path))

    def test_with_lifts_filter(self):
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "chart.png")
            ga.cmd_chart_e1rm(ALL_SESS, _make_args(output=out_path, history_dir=d, lifts="Squat,OHP"))
            self.assertTrue(os.path.exists(out_path))

    def test_current_period(self):
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "chart.png")
            ga.cmd_chart_e1rm(ALL_SESS, _make_args(output=out_path, history_dir=d, period="current"))
            self.assertTrue(os.path.exists(out_path))

    def test_with_goals_file(self):
        with tempfile.TemporaryDirectory() as d:
            gp = os.path.join(d, "goals.json")
            with open(gp, "w") as f:
                json.dump([{"date_set": "2026-01-05", "target_date": "2026-04-05",
                            "goals": {"Squat": 170, "OHP": 67}}], f)
            out_path = os.path.join(d, "chart.png")
            ga.cmd_chart_e1rm(ALL_SESS, _make_args(output=out_path, history_dir=d, goals_file=gp))
            self.assertTrue(os.path.exists(out_path))

    def test_with_plan_file(self):
        with tempfile.TemporaryDirectory() as d:
            plan_path = os.path.join(d, "plan.md")
            with open(plan_path, "w") as f:
                f.write("""### Силовые targets (e1RM)
| Lift | Сейчас | Цель (12 нед) | Прирост |
|------|--------|---------------|---------|
| Squat | ~160 | ~170 | +6% |
| Bench (flat) | ~98 | ~110 | +12% |
""")
            out_path = os.path.join(d, "chart.png")
            ga.cmd_chart_e1rm(ALL_SESS, _make_args(output=out_path, history_dir=d, plan=plan_path))
            self.assertTrue(os.path.exists(out_path))

    def test_horizontal_with_goals(self):
        with tempfile.TemporaryDirectory() as d:
            gp = os.path.join(d, "goals.json")
            with open(gp, "w") as f:
                json.dump([{"date_set": "2026-01-05", "target_date": "2026-04-05",
                            "goals": {"Squat": 170}}], f)
            out_path = os.path.join(d, "chart.png")
            ga.cmd_chart_e1rm(ALL_SESS, _make_args(output=out_path, history_dir=d,
                                                     goals_file=gp, horizontal=True))
            self.assertTrue(os.path.exists(out_path))


class TestCmdChartVolumeDirect(unittest.TestCase):
    def test_empty(self):
        with self.assertRaises(SystemExit):
            ga.cmd_chart_volume([], _make_args(output="/tmp/test.png"))

    def test_vertical(self):
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "vol.png")
            ga.cmd_chart_volume(ALL_SESS, _make_args(output=out_path))
            self.assertTrue(os.path.exists(out_path))

    def test_horizontal(self):
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "vol.png")
            ga.cmd_chart_volume(ALL_SESS, _make_args(output=out_path, horizontal=True))
            self.assertTrue(os.path.exists(out_path))


class TestDrawGoalLines(unittest.TestCase):
    def test_basic(self):
        ax = MagicMock()
        goals = {"Squat": 170}
        start_values = {"Squat": 150}
        ga.draw_goal_lines(ax, goals, datetime(2026, 1, 1), datetime(2026, 4, 1), start_values)
        ax.plot.assert_called()

    def test_missing_start_value(self):
        ax = MagicMock()
        goals = {"Squat": 170}
        start_values = {}
        ga.draw_goal_lines(ax, goals, datetime(2026, 1, 1), datetime(2026, 4, 1), start_values)
        ax.plot.assert_not_called()

    def test_with_colors(self):
        ax = MagicMock()
        goals = {"Squat": 170}
        start_values = {"Squat": 150}
        colors = {"Squat": "#FF0000"}
        ga.draw_goal_lines(ax, goals, datetime(2026, 1, 1), datetime(2026, 4, 1), start_values, colors)
        ax.plot.assert_called()


class TestMainDirect(unittest.TestCase):
    def test_no_command(self):
        with patch('sys.argv', ['gym_analytics.py']):
            with self.assertRaises(SystemExit) as cm:
                ga.main()
            self.assertEqual(cm.exception.code, 2)

    def test_log_command(self):
        with tempfile.TemporaryDirectory() as d:
            source = json.dumps({"date": "2026-03-01", "actual": [_ex("Squat", "legs", [_s(80, 8)])]})
            with patch('sys.argv', ['gym_analytics.py', 'log', d, source]):
                with patch('sys.stdout', new_callable=StringIO):
                    ga.main()
            self.assertTrue(os.path.exists(os.path.join(d, "2026-03-01.json")))

    def test_validate_command(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), ALL_SESS)
            with patch('sys.argv', ['gym_analytics.py', 'validate', d]):
                with patch('sys.stdout', new_callable=StringIO):
                    ga.main()

    def test_goals_command_no_file(self):
        with patch('sys.argv', ['gym_analytics.py', 'goals', 'list']):
            with self.assertRaises(SystemExit):
                ga.main()

    def test_goals_command_with_file(self):
        with tempfile.TemporaryDirectory() as d:
            gp = os.path.join(d, "goals.json")
            with open(gp, "w") as f:
                json.dump([{"date_set": "2026-01-01", "target_date": "2026-04-01",
                            "goals": {"Squat": 170}}], f)
            with patch('sys.argv', ['gym_analytics.py', 'goals', 'list', '--goals-file', gp]):
                with patch('sys.stdout', new_callable=StringIO):
                    ga.main()

    def test_e1rm_command(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), ALL_SESS)
            with patch('sys.argv', ['gym_analytics.py', 'e1rm', d]):
                with patch('sys.stdout', new_callable=StringIO):
                    ga.main()

    def test_nonexistent_dir(self):
        with patch('sys.argv', ['gym_analytics.py', 'e1rm', '/tmp/nonexistent_xyz']):
            with self.assertRaises(SystemExit):
                ga.main()

    def test_volume_command(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), ALL_SESS)
            with patch('sys.argv', ['gym_analytics.py', 'volume', d]):
                with patch('sys.stdout', new_callable=StringIO):
                    ga.main()

    def test_progress_command(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), ALL_SESS)
            with patch('sys.argv', ['gym_analytics.py', 'progress', d, 'Squat']):
                with patch('sys.stdout', new_callable=StringIO):
                    ga.main()

    def test_summary_command(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), ALL_SESS)
            with patch('sys.argv', ['gym_analytics.py', 'summary', d]):
                with patch('sys.stdout', new_callable=StringIO):
                    ga.main()

    def test_compare_command(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), ALL_SESS)
            with patch('sys.argv', ['gym_analytics.py', 'compare', d, '2026-01-05', '2026-01-12']):
                with patch('sys.stdout', new_callable=StringIO):
                    ga.main()

    def test_chart_e1rm_command(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), ALL_SESS)
            out = os.path.join(d, "chart.png")
            with patch('sys.argv', ['gym_analytics.py', 'chart-e1rm', d, out]):
                with patch('sys.stdout', new_callable=StringIO):
                    ga.main()

    def test_chart_volume_command(self):
        with tempfile.TemporaryDirectory() as d:
            _write_sessions(Path(d), ALL_SESS)
            out = os.path.join(d, "vol.png")
            with patch('sys.argv', ['gym_analytics.py', 'chart-volume', d, out]):
                with patch('sys.stdout', new_callable=StringIO):
                    ga.main()


# ==================== Change 1: Dashboard lifts from goals.json ====================

class TestDashboardLiftsFromGoals(unittest.TestCase):
    """chart-e1rm should use goals.json keys as tracked lifts when --goals-file is given."""

    def test_lifts_from_goals_file(self):
        """When goals.json exists, its keys should determine which lifts are tracked."""
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import _get_tracked_lifts
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{"date_set": "2026-01-26", "target_date": "2026-04-19",
                        "goals": {"Squat": 170, "Bench Press (flat)": 110, "OHP": 70, "Seated Cable Row": 120}}], f)
            f.flush()
            lifts = _get_tracked_lifts(f.name)
            self.assertEqual(lifts, ["Squat", "Bench Press (flat)", "OHP", "Seated Cable Row"])
            os.unlink(f.name)

    def test_lifts_fallback_no_file(self):
        """Without goals file, should return default 4 lifts."""
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import _get_tracked_lifts
        lifts = _get_tracked_lifts("/tmp/nonexistent_xyz.json")
        self.assertEqual(lifts, ["Squat", "Bench Press", "OHP", "Seated Cable Row"])

    def test_lifts_fallback_empty_goals(self):
        """Empty goals array should fallback to defaults."""
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import _get_tracked_lifts
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([], f)
            f.flush()
            lifts = _get_tracked_lifts(f.name)
            self.assertEqual(lifts, ["Squat", "Bench Press", "OHP", "Seated Cable Row"])
            os.unlink(f.name)

    def test_lifts_from_latest_goal_entry(self):
        """Should use the LAST entry in goals array."""
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import _get_tracked_lifts
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([
                {"date_set": "2026-01-01", "target_date": "2026-03-01",
                 "goals": {"Squat": 150, "Deadlift": 200}},
                {"date_set": "2026-01-26", "target_date": "2026-04-19",
                 "goals": {"Squat": 170, "OHP": 70}},
            ], f)
            f.flush()
            lifts = _get_tracked_lifts(f.name)
            self.assertEqual(lifts, ["Squat", "OHP"])
            os.unlink(f.name)


# ==================== Change 2: Rolling 14-day KPI windows ====================

class TestRolling14DayKPIs(unittest.TestCase):
    """KPIs should use rolling 14-day windows instead of weekly."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from gym_analytics import _compute_kpis
        self.kpis = _compute_kpis

    def test_current_window_14_days(self):
        """Current window = last 14 days from latest session."""
        sessions = [
            {"date": "2026-01-15"},  # prev window
            {"date": "2026-01-20"},  # prev window
            {"date": "2026-01-28"},  # current window
            {"date": "2026-02-03"},  # current window
            {"date": "2026-02-08"},  # current window
        ]
        lift_data = {
            "Squat": (
                [datetime(2026, 1, 15), datetime(2026, 1, 20), datetime(2026, 1, 28), datetime(2026, 2, 3), datetime(2026, 2, 8)],
                [100, 105, 110, 115, 120]
            ),
        }
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis(sessions, lift_data)
        self.assertEqual(adh, 50)  # 3/6*100
        self.assertAlmostEqual(avg, 120, places=1)  # best Squat in current window

    def test_prev_window_no_overlap(self):
        """Previous window should be days 15-28 (no overlap with current 1-14)."""
        sessions = [
            {"date": "2026-01-12"},  # prev window
            {"date": "2026-01-25"},  # prev window
            {"date": "2026-02-05"},  # current window
            {"date": "2026-02-08"},  # current window
        ]
        lift_data = {
            "Squat": (
                [datetime(2026, 1, 12), datetime(2026, 1, 25), datetime(2026, 2, 5), datetime(2026, 2, 8)],
                [90, 100, 110, 115]
            ),
        }
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis(sessions, lift_data)
        self.assertAlmostEqual(change, 15.0, places=1)  # 115 - 100

    def test_volume_kpi(self):
        """Volume KPI = total hard sets in current window."""
        sessions = [
            {"date": "2026-02-01", "actual": [
                {"name": "Squat", "sets": [{"weight_kg": 80, "reps": 8}] * 3},
                {"name": "Bench", "sets": [{"weight_kg": 60, "reps": 10}] * 3},
            ]},
            {"date": "2026-02-08", "actual": [
                {"name": "Squat", "sets": [{"weight_kg": 85, "reps": 8}] * 4},
            ]},
        ]
        lift_data = {
            "Squat": ([datetime(2026, 2, 1), datetime(2026, 2, 8)], [100, 110]),
        }
        adh, avg, change, volume, vol_change, cur_cnt, prev_cnt = self.kpis(sessions, lift_data)
        self.assertEqual(volume, 10)  # 3+3+4

    def test_adherence_formula(self):
        """Adherence = actual_sessions / (14/7 * 3) = actual / 6."""
        sessions = [
            {"date": "2026-02-02"},
            {"date": "2026-02-04"},
            {"date": "2026-02-06"},
            {"date": "2026-02-08"},
            {"date": "2026-02-09"},
            {"date": "2026-02-10"},
        ]
        lift_data = {"Squat": ([datetime(2026, 2, 10)], [100])}
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis(sessions, lift_data)
        self.assertEqual(adh, 100)

    def test_empty_sessions(self):
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis([], {})
        self.assertEqual(adh, 0)
        self.assertEqual(avg, 0)
        self.assertEqual(change, 0)

    def test_single_session(self):
        sessions = [{"date": "2026-02-10"}]
        lift_data = {"Squat": ([datetime(2026, 2, 10)], [160])}
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis(sessions, lift_data)
        self.assertAlmostEqual(avg, 160, places=1)
        self.assertEqual(change, 0)

    def test_session_counts_returned(self):
        """Verify cur_cnt and prev_cnt reflect actual session counts per window."""
        sessions = [
            {"date": "2026-01-20"},  # prev window
            {"date": "2026-01-22"},  # prev window
            {"date": "2026-01-28"},  # current window
            {"date": "2026-02-03"},  # current window
            {"date": "2026-02-08"},  # current window
        ]
        lift_data = {"Squat": ([datetime(2026, 2, 8)], [100])}
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis(sessions, lift_data)
        self.assertEqual(cur_cnt, 3)
        self.assertEqual(prev_cnt, 2)

    def test_session_counts_empty_prev(self):
        """All sessions in current window → prev_cnt = 0."""
        sessions = [
            {"date": "2026-02-05"},
            {"date": "2026-02-08"},
            {"date": "2026-02-10"},
        ]
        lift_data = {"Squat": ([datetime(2026, 2, 10)], [100])}
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis(sessions, lift_data)
        self.assertEqual(cur_cnt, 3)
        self.assertEqual(prev_cnt, 0)

    def test_session_counts_both_full(self):
        """Both windows have >= 3 sessions."""
        sessions = [
            {"date": "2026-01-15"},
            {"date": "2026-01-18"},
            {"date": "2026-01-20"},
            {"date": "2026-01-28"},
            {"date": "2026-02-01"},
            {"date": "2026-02-05"},
            {"date": "2026-02-08"},
        ]
        lift_data = {
            "Squat": (
                [datetime(2026, 1, 15), datetime(2026, 1, 18), datetime(2026, 1, 20),
                 datetime(2026, 1, 28), datetime(2026, 2, 1), datetime(2026, 2, 5), datetime(2026, 2, 8)],
                [100, 105, 110, 115, 120, 125, 130]
            ),
        }
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis(sessions, lift_data)
        self.assertEqual(cur_cnt, 4)
        self.assertEqual(prev_cnt, 3)
        # Delta should be computed (both >= 3)
        # Current best: 130, Prev best: 110 → change = 20
        self.assertAlmostEqual(change, 20.0, places=1)

    def test_delta_suppressed_when_prev_under_3(self):
        """When prev_cnt < 3, delta is still computed but caller should hide it."""
        sessions = [
            {"date": "2026-01-20"},  # prev window (only 1)
            {"date": "2026-02-01"},
            {"date": "2026-02-05"},
            {"date": "2026-02-08"},
        ]
        lift_data = {
            "Squat": (
                [datetime(2026, 1, 20), datetime(2026, 2, 1), datetime(2026, 2, 5), datetime(2026, 2, 8)],
                [150, 100, 110, 120]
            ),
        }
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis(sessions, lift_data)
        self.assertEqual(prev_cnt, 1)
        self.assertLess(prev_cnt, 3)  # caller should show "——"

    def test_empty_returns_zero_counts(self):
        adh, avg, change, vol, vol_change, cur_cnt, prev_cnt = self.kpis([], {})
        self.assertEqual(cur_cnt, 0)
        self.assertEqual(prev_cnt, 0)


if __name__ == "__main__":
    unittest.main()
