"""Visual regression tests for e1RM chart.

Tests chart structure (lines, markers, labels, axis ranges) not pixels.
Uses matplotlib introspection on fig/ax objects.
"""
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta

import matplotlib
matplotlib.use('Agg')

sys.path.insert(0, os.path.dirname(__file__))
from gym_analytics import cmd_chart_e1rm, load_sessions


def _make_session(date, day, exercises):
    """Helper: create a session dict with planned+actual."""
    actual = []
    planned = []
    for name, sets_data in exercises.items():
        sets = [{"reps": r, "weight_kg": w} for w, r in sets_data]
        actual.append({"name": name, "muscle_group": "test", "sets": sets})
        planned.append({"name": name, "muscle_group": "test", "sets": sets})
    return {"date": date, "day": day, "actual": actual, "planned": planned,
            "start_time": "20:00", "end_time": "21:00"}


def _make_goals(goals_dict, target_date="2026-04-19"):
    """Helper: create goals.json content."""
    return [{"date_set": "2026-01-26", "target_date": target_date,
             "goals": goals_dict, "note": "test goals"}]


def _write_sessions_and_goals(tmpdir, sessions, goals=None):
    """Write session files and optional goals.json, return hist dir path."""
    hist = os.path.join(tmpdir, "history")
    os.makedirs(hist, exist_ok=True)
    for s in sessions:
        with open(os.path.join(hist, f"{s['date']}.json"), "w") as f:
            json.dump(s, f)
    if goals is not None:
        with open(os.path.join(tmpdir, "goals.json"), "w") as f:
            json.dump(goals, f)
    return hist


def _render_chart(hist, extra_args=None):
    """Render chart and return (fig, ax) without saving to disk."""
    args = Namespace(
        history_dir=hist,
        output="/dev/null",
        orientation="vertical",
        lifts=None,
        period="all",
        goals_file=None,
        no_goals=False,
        planned=None,
        horizontal=False,
        _return_fig=True,
    )
    if extra_args:
        for k, v in extra_args.items():
            setattr(args, k, v)
    sessions = load_sessions(hist)
    return cmd_chart_e1rm(sessions, args)


def _get_solid_lines(ax):
    """Get lines with solid linestyle and 'o' marker (data lines)."""
    return [l for l in ax.lines if l.get_linestyle() == '-' and l.get_marker() == 'o']


def _get_dashed_lines(ax):
    """Get dashed lines (goal projections)."""
    return [l for l in ax.lines if l.get_linestyle() == '--']


def _get_diamond_markers(ax):
    """Get lines with diamond markers (goal endpoints)."""
    return [l for l in ax.lines if l.get_marker() == 'D']


class TestChartLifts(unittest.TestCase):
    """Test which lifts appear on chart."""

    def test_default_lifts_from_goals(self):
        """Without --lifts, chart shows lifts from goals.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = [
                _make_session("2026-02-01", "A", {
                    "Squat": [(100, 10), (100, 10)],
                    "Bench Press (flat)": [(70, 10)],
                    "OHP": [(45, 10)],
                    "Seated Cable Row": [(80, 10)],
                    "Barbell Curl": [(35, 10)],  # not in goals
                }),
            ]
            goals = _make_goals({
                "Squat": {"target": 170, "short": "Squat"},
                "Bench Press (flat)": {"target": 110, "short": "Bench"},
                "OHP": {"target": 70, "short": "OHP"},
                "Seated Cable Row": {"target": 120, "short": "Row"},
            })
            hist = _write_sessions_and_goals(tmpdir, sessions, goals)
            fig, ax = _render_chart(hist)

            lines = _get_solid_lines(ax)
            self.assertEqual(len(lines), 4, f"Expected 4 data lines, got {len(lines)}")
            matplotlib.pyplot.close(fig)

    def test_explicit_lifts_override(self):
        """--lifts overrides goals.json selection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = [
                _make_session("2026-02-01", "A", {
                    "Squat": [(100, 10)],
                    "OHP": [(45, 10)],
                    "Barbell Curl": [(35, 10)],
                }),
            ]
            goals = _make_goals({"Squat": 170, "OHP": 70})
            hist = _write_sessions_and_goals(tmpdir, sessions, goals)
            fig, ax = _render_chart(hist, {"lifts": "OHP,Barbell Curl"})

            lines = _get_solid_lines(ax)
            self.assertEqual(len(lines), 2)
            matplotlib.pyplot.close(fig)

    def test_no_goals_falls_back_to_defaults(self):
        """Without goals.json, chart shows DEFAULT_LIFTS (Squat, Bench, OHP, Row)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = [
                _make_session("2026-02-01", "A", {
                    "Squat": [(100, 10)],
                    "OHP": [(45, 10)],
                    "RDL": [(110, 10)],  # not in defaults → not shown
                }),
            ]
            hist = _write_sessions_and_goals(tmpdir, sessions, goals=None)
            fig, ax = _render_chart(hist)

            lines = _get_solid_lines(ax)
            # Only Squat and OHP match defaults (Bench, Row have no data)
            self.assertEqual(len(lines), 2,
                             f"Expected 2 lines (Squat+OHP from defaults), got {len(lines)}")
            matplotlib.pyplot.close(fig)


class TestChartGoalLines(unittest.TestCase):
    """Test goal projection dashed lines and diamonds."""

    def test_goal_diamonds_exist(self):
        """Goal diamonds should exist for each tracked lift with goals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = [
                _make_session("2026-02-01", "A", {
                    "Squat": [(100, 10)],
                    "OHP": [(45, 10)],
                }),
            ]
            goals = _make_goals({"Squat": 170, "OHP": 70}, target_date="2026-04-19")
            hist = _write_sessions_and_goals(tmpdir, sessions, goals)
            fig, ax = _render_chart(hist)

            diamonds = _get_diamond_markers(ax)
            # Should have diamonds for both Squat and OHP
            self.assertGreaterEqual(len(diamonds), 2,
                                    f"Expected ≥2 goal diamonds, got {len(diamonds)}")

            # Check diamond y-values match goal targets
            diamond_ys = set()
            for d in diamonds:
                for y in d.get_ydata():
                    diamond_ys.add(round(float(y)))
            self.assertIn(170, diamond_ys, f"Missing Squat goal diamond at 170. Got: {diamond_ys}")
            self.assertIn(70, diamond_ys, f"Missing OHP goal diamond at 70. Got: {diamond_ys}")
            matplotlib.pyplot.close(fig)

    def test_goal_dashed_lines_exist(self):
        """Dashed lines should connect last data point to goal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = [
                _make_session("2026-02-01", "A", {"Squat": [(100, 10)]}),
            ]
            goals = _make_goals({"Squat": 170})
            hist = _write_sessions_and_goals(tmpdir, sessions, goals)
            fig, ax = _render_chart(hist)

            dashed = _get_dashed_lines(ax)
            self.assertGreaterEqual(len(dashed), 1, "Expected at least 1 dashed goal line")
            matplotlib.pyplot.close(fig)

    def test_no_goals_flag_hides_projections(self):
        """--no-goals should hide goal lines and diamonds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = [
                _make_session("2026-02-01", "A", {"Squat": [(100, 10)]}),
            ]
            goals = _make_goals({"Squat": 170})
            hist = _write_sessions_and_goals(tmpdir, sessions, goals)
            fig, ax = _render_chart(hist, {"no_goals": True})

            diamonds = _get_diamond_markers(ax)
            self.assertEqual(len(diamonds), 0, "No diamonds expected with --no-goals")
            matplotlib.pyplot.close(fig)


class TestChartDateRange(unittest.TestCase):
    """Test x-axis date range."""

    def test_xlim_extends_to_goal_target_date(self):
        """X-axis should extend to goal target_date when goals shown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = [
                _make_session("2026-02-01", "A", {"Squat": [(100, 10)]}),
            ]
            goals = _make_goals({"Squat": 170}, target_date="2026-04-19")
            hist = _write_sessions_and_goals(tmpdir, sessions, goals)
            fig, ax = _render_chart(hist)

            xlim = ax.get_xlim()
            xmax_date = matplotlib.dates.num2date(xlim[1]).replace(tzinfo=None)
            # xmax should be at or after Apr 19
            self.assertGreaterEqual(xmax_date.date(), datetime(2026, 4, 19).date(),
                                    f"X-axis ends at {xmax_date.date()}, should reach Apr 19")
            matplotlib.pyplot.close(fig)

    def test_xlim_tight_without_goals(self):
        """Without goals, x-axis should be tight to data range."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = [
                _make_session("2026-02-01", "A", {"Squat": [(100, 10)]}),
                _make_session("2026-02-10", "A", {"Squat": [(105, 10)]}),
            ]
            hist = _write_sessions_and_goals(tmpdir, sessions, goals=None)
            fig, ax = _render_chart(hist)

            xlim = ax.get_xlim()
            xmax_date = matplotlib.dates.num2date(xlim[1]).replace(tzinfo=None)
            # Should NOT extend to April
            self.assertLess(xmax_date.date(), datetime(2026, 3, 1).date(),
                            f"X-axis extends to {xmax_date.date()}, should be tight to data")
            matplotlib.pyplot.close(fig)


class TestChartDataPoints(unittest.TestCase):
    """Test that data points are correctly plotted."""

    def test_new_session_adds_point(self):
        """Adding a session should add a new data point on the line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = [
                _make_session("2026-02-01", "A", {"OHP": [(45, 10)]}),
                _make_session("2026-02-06", "B", {"OHP": [(45, 10)]}),
            ]
            goals = _make_goals({"OHP": 70})
            hist = _write_sessions_and_goals(tmpdir, sessions, goals)
            fig1, ax1 = _render_chart(hist)
            lines1 = _get_solid_lines(ax1)
            points_before = len(list(lines1[0].get_xdata()))

            # Add third session
            s3 = _make_session("2026-02-13", "B", {"OHP": [(45, 8)]})
            with open(os.path.join(hist, "2026-02-13.json"), "w") as f:
                json.dump(s3, f)

            fig2, ax2 = _render_chart(hist)
            lines2 = _get_solid_lines(ax2)
            points_after = len(list(lines2[0].get_xdata()))

            self.assertEqual(points_after, points_before + 1,
                             f"Expected {points_before + 1} points, got {points_after}")
            matplotlib.pyplot.close(fig1)
            matplotlib.pyplot.close(fig2)

    def test_e1rm_values_correct(self):
        """Data point y-values should be correct e1RM calculations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 100kg × 10 reps → e1RM = 100 * (1 + 10/30) = 133.3
            sessions = [
                _make_session("2026-02-01", "A", {"Squat": [(100, 10)]}),
            ]
            goals = _make_goals({"Squat": 170})
            hist = _write_sessions_and_goals(tmpdir, sessions, goals)
            fig, ax = _render_chart(hist)

            lines = _get_solid_lines(ax)
            self.assertEqual(len(lines), 1)
            ydata = list(lines[0].get_ydata())
            expected_e1rm = 100 * (1 + 10/30)  # 133.33
            self.assertAlmostEqual(ydata[0], expected_e1rm, places=0,
                                   msg=f"e1RM should be ~{expected_e1rm:.0f}, got {ydata[0]:.1f}")
            matplotlib.pyplot.close(fig)


class TestChartPlannedMarkers(unittest.TestCase):
    """Test hollow planned markers (pre-workout state)."""

    def test_planned_only_session_shows_hollow_markers(self):
        """Session with planned but no actual should show hollow markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First session with actual data
            s1 = _make_session("2026-02-01", "A", {"OHP": [(45, 10)]})
            # Second session: planned only (pre-workout). Planned uses flat weight_kg/target_reps
            s2 = {"date": "2026-02-13", "day": "B",
                   "planned": [{"name": "OHP", "muscle_group": "shoulders",
                               "weight_kg": 45, "target_reps": 10}],
                   "actual": []}
            hist = _write_sessions_and_goals(tmpdir, [s1, s2],
                                              _make_goals({"OHP": 70}))
            fig, ax = _render_chart(hist)

            # Look for hollow markers (markerfacecolor='none')
            hollow = [l for l in ax.lines
                      if l.get_marker() == 'o'
                      and str(l.get_markerfacecolor()).lower() == 'none']
            self.assertGreaterEqual(len(hollow), 1,
                                    "Expected hollow marker for planned-only session")
            matplotlib.pyplot.close(fig)

    def test_completed_session_no_hollow_markers(self):
        """Session with both planned and actual should NOT show hollow markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            s1 = _make_session("2026-02-01", "A", {"OHP": [(45, 10)]})
            s2 = _make_session("2026-02-13", "B", {"OHP": [(45, 8)]})
            hist = _write_sessions_and_goals(tmpdir, [s1, s2],
                                              _make_goals({"OHP": 70}))
            fig, ax = _render_chart(hist)

            hollow = [l for l in ax.lines
                      if l.get_marker() == 'o'
                      and l.get_markerfacecolor() == 'none']
            self.assertEqual(len(hollow), 0,
                             "No hollow markers expected for completed sessions")
            matplotlib.pyplot.close(fig)


class TestChartLegend(unittest.TestCase):
    """Test legend rendering."""

    def test_legend_has_all_lifts(self):
        """Legend should contain entries for all plotted lifts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = [
                _make_session("2026-02-01", "A", {
                    "Squat": [(100, 10)],
                    "Bench Press (flat)": [(70, 10)],
                    "OHP": [(45, 10)],
                    "Seated Cable Row": [(80, 10)],
                }),
            ]
            goals = _make_goals({
                "Squat": {"target": 170, "short": "Squat"},
                "Bench Press (flat)": {"target": 110, "short": "Bench"},
                "OHP": {"target": 70, "short": "OHP"},
                "Seated Cable Row": {"target": 120, "short": "Row"},
            })
            hist = _write_sessions_and_goals(tmpdir, sessions, goals)
            fig, ax = _render_chart(hist)

            # Check fig.texts for legend labels
            texts = [t.get_text() for t in fig.texts]
            for label in ["Squat", "Bench", "OHP", "Row"]:
                self.assertTrue(any(label in t for t in texts),
                                f"Legend missing '{label}'. Texts: {texts}")
            matplotlib.pyplot.close(fig)


if __name__ == "__main__":
    unittest.main()
