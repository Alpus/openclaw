#!/usr/bin/env python3
"""Gym analytics CLI — e1RM, volume, progress, charts, logging, validation.

Usage:
    gym_analytics.py <command> <history_dir> [args...] [--json] [--vertical|--horizontal]

Commands:
    e1rm       <dir>                    Estimated 1RM for all lifts (best per exercise, latest session)
    volume     <dir>                    Weekly volume (hard sets) per muscle group
    progress   <dir> <exercise>         Progression for a specific exercise over time
    summary    <dir>                    Last session summary
    compare    <dir> <date1> <date2>    Compare two sessions side by side
    chart-e1rm <dir> <output>           e1RM progress chart
    chart-volume <dir> <output>         Weekly volume per muscle group chart
    log        <dir> <json_or_file>     Validate and save a session JSON
    validate   <dir>                    Validate all session JSONs
    goals      list|add|current         Manage strength goals
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


# ---- Constants ----

SHORT_NAMES = {
    "Squat": "Squat",
    "Barbell Squat": "Squat",
    "Squat (lighter)": "Squat (light)",
    "Bench Press (flat)": "Bench",
    "Bench Press": "Bench",
    "Bench Press (decline)": "Decline Bench",
    "OHP": "OHP",
    "Seated Cable Row": "Row",
    "Barbell Row": "Row",
    "RDL": "RDL",
    "Barbell Curl": "Curl",
    "Incline DB Curl": "Inc. Curl",
    "Hammer Curl": "Hammer Curl",
    "Wide Grip Pull-ups (weighted)": "Pull-ups",
    "Pull-ups (weighted)": "Pull-ups",
    "Dips (weighted)": "Dips",
    "Lateral Raise": "Lat. Raise",
    "Face Pull": "Face Pull",
    "Leg Curl": "Leg Curl",
    "Hanging Leg Raise": "HLR",
    "Cable Crunch": "Cable Crunch",
    "Tricep Pushdown": "Tri. Push",
}

# ---- Helpers ----

def e1rm_epley(weight, reps):
    if reps <= 0 or weight <= 0:
        return 0
    if reps == 1:
        return weight
    return weight * (1 + reps / 30)


def best_e1rm_for_exercise(ex):
    best = 0
    for s in ex.get("sets", []):
        w = s.get("weight_kg", 0) or 0
        r = s.get("reps", 0) or 0
        e = e1rm_epley(w, r)
        if e > best:
            best = e
    return best


def load_sessions(history_dir):
    """Load all valid YYYY-MM-DD.json files, sorted by date. Warn on bad files."""
    sessions = []
    p = Path(history_dir)
    if not p.exists():
        return sessions
    for f in sorted(p.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            if "date" not in data:
                raise ValueError("missing date")
            # Normalize: support both "actual" and legacy "exercises" key
            if "actual" not in data and "exercises" in data:
                data["actual"] = data["exercises"]
            sessions.append(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: skipping {f.name}: {e}", file=sys.stderr)
    return sessions


def normalize_match(name, target):
    nl, tl = name.lower(), target.lower()
    # "Squat (lighter)" should NOT match plain "Squat" — they're separate exercises
    if "lighter" in nl and "lighter" not in tl:
        return False
    if "lighter" in tl and "lighter" not in nl:
        return False
    if nl == tl or tl in nl or nl in tl:
        return True
    aliases = {
        "bench press": ["bench", "flat bench", "incline bench", "decline bench press"],
        "squat": ["barbell squat", "barbell back squat", "back squat"],
        "ohp": ["overhead press", "standing press", "military press"],
        "seated cable row": ["seated row", "cable row"],
        "barbell row": ["bent over row", "pendlay row"],
    }
    for canonical, names in aliases.items():
        all_names = [canonical] + names
        if tl in all_names and nl in all_names:
            return True
    return False


def week_key(date_str):
    """ISO week key from date string."""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def week_start(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")





def validate_time_str(t):
    """Validate HH:MM time string. Returns True if valid."""
    try:
        h, m = t.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except (ValueError, AttributeError):
        return False


def session_duration(session):
    """Compute duration in minutes from top-level start_time/end_time. Returns (start, end, minutes) or None."""
    start = session.get("start_time")
    end = session.get("end_time")
    if not start or not end:
        return None
    if not validate_time_str(start) or not validate_time_str(end):
        return None
    sh, sm = start.split(":")
    eh, em = end.split(":")
    start_min = int(sh) * 60 + int(sm)
    end_min = int(eh) * 60 + int(em)
    dur = end_min - start_min
    if dur < 0:
        dur += 24 * 60  # crosses midnight
    return (start, end, dur)


def validate_planned(planned):
    """Validate planned exercises array. Returns list of error strings."""
    errors = []
    if not isinstance(planned, list):
        return ["planned must be a list"]
    for i, entry in enumerate(planned):
        if not isinstance(entry, dict):
            errors.append(f"planned[{i}]: must be an object")
            continue
        if "name" not in entry:
            errors.append(f"planned[{i}]: missing 'name'")
    return errors


def parse_goals_from_plan(plan_text):
    """Parse strength targets from plan.md text. Returns {exercise: goal_e1rm}."""
    import re
    goals = {}
    in_targets = False
    for line in plan_text.split("\n"):
        if "Силовые targets" in line:
            in_targets = True
            continue
        if in_targets and line.startswith("|") and "---" not in line and "Lift" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3:
                name = parts[0]
                goal_str = parts[2]
                # Extract number from goal like "~170", "~110"
                m = re.search(r'~?(\d+(?:\.\d+)?)', goal_str)
                if m:
                    # Simplify name: "Bench (flat)" -> "Bench"
                    simple_name = re.sub(r'\s*\(.*\)', '', name).strip()
                    goals[simple_name] = float(m.group(1))
                    if goals[simple_name] == int(goals[simple_name]):
                        goals[simple_name] = int(goals[simple_name])
        elif in_targets and not line.startswith("|") and line.strip() and not line.startswith("#"):
            break
    return goals


def compute_goal_lines(goals, start_date, start_values, weeks=12):
    """Compute goal line data for plotting. Returns {exercise: {start_date, end_date, start_value, end_value}}."""
    lines = {}
    end_date = start_date + timedelta(weeks=weeks)
    for name, goal in goals.items():
        if name in start_values:
            lines[name] = {
                "start_date": start_date,
                "end_date": end_date,
                "start_value": start_values[name],
                "end_value": goal,
            }
    return lines


def load_goals(goals_path):
    """Load goals from goals.json. Returns list of goal entries."""
    p = Path(goals_path)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, ValueError):
        return []


def get_latest_goals(goals_path):
    """Get the latest goal entry from goals.json. Returns dict or None."""
    goals = load_goals(goals_path)
    if not goals:
        return None
    return goals[-1]


def default_goals_path(history_dir):
    """Derive default goals.json path from history dir (sibling file)."""
    return str(Path(history_dir).parent / "goals.json")


def _goal_target(val):
    """Extract numeric target from goal value (supports int/float or {"target": N})."""
    if isinstance(val, dict):
        return val.get("target", 0)
    return val


def _goal_short(name, val):
    """Extract short name from goal value, fallback to exercise name."""
    if isinstance(val, dict) and val.get("short"):
        return val["short"]
    return name


def _get_tracked_lifts(goals_path):
    """Get tracked lift names from goals.json, or fallback to defaults."""
    DEFAULT_LIFTS = ["Squat", "Bench Press", "OHP", "Seated Cable Row"]
    if not goals_path:
        return DEFAULT_LIFTS
    latest = get_latest_goals(goals_path)
    if not latest or not latest.get("goals"):
        return DEFAULT_LIFTS
    return list(latest["goals"].keys())


def _get_short_names(goals_path):
    """Get {full_name: short_name} mapping. Merges SHORT_NAMES with goals.json overrides."""
    result = dict(SHORT_NAMES)  # Start with hardcoded defaults
    if goals_path:
        latest = get_latest_goals(goals_path)
        if latest and latest.get("goals"):
            for name, val in latest["goals"].items():
                result[name] = _goal_short(name, val)
    return result


def err_exit(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


# ---- Commands ----

def cmd_e1rm(sessions, args):
    if not sessions:
        err_exit("No session data found")
    
    # For each exercise, find the best e1RM from the most recent session it appears in
    exercises = {}
    for s in sessions:
        for ex in s.get("actual", []):
            name = ex["name"]
            e = best_e1rm_for_exercise(ex)
            if e > 0:
                exercises[name] = {"e1rm": round(e, 2), "date": s["date"]}

    if not exercises:
        err_exit("No exercises with weight data found")

    if args.json:
        print(json.dumps(exercises, indent=2))
    else:
        print(f"{'Exercise':<30} {'e1RM (kg)':>10} {'Date':>12}")
        print("-" * 54)
        for name, info in sorted(exercises.items()):
            print(f"{name:<30} {info['e1rm']:>10.1f} {info['date']:>12}")


def cmd_volume(sessions, args):
    if not sessions:
        err_exit("No session data found")

    weeks = {}
    for s in sessions:
        wk = week_key(s["date"])
        ws = week_start(s["date"])
        if wk not in weeks:
            weeks[wk] = {"week": wk, "week_start": ws}
        for ex in s.get("actual", []):
            mg = ex.get("muscle_group", "unknown")
            n_sets = len(ex.get("sets", []))
            weeks[wk][mg] = weeks[wk].get(mg, 0) + n_sets

    result = [weeks[k] for k in sorted(weeks)]

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # Collect all muscle groups
        all_mg = sorted({k for w in result for k in w if k not in ("week", "week_start")})
        header = f"{'Week':<12}" + "".join(f"{mg:>12}" for mg in all_mg)
        print(header)
        print("-" * len(header))
        for w in result:
            row = f"{w['week']:<12}" + "".join(f"{w.get(mg, 0):>12}" for mg in all_mg)
            print(row)


def cmd_progress(sessions, args):
    if not sessions:
        err_exit("No session data found")

    target = args.exercise
    entries = []
    for s in sessions:
        for ex in s.get("actual", []):
            if normalize_match(ex["name"], target):
                e = best_e1rm_for_exercise(ex)
                sets = ex.get("sets", [])
                best_set = max(sets, key=lambda s: s.get("weight_kg", 0) * s.get("reps", 0)) if sets else {}
                entries.append({
                    "date": s["date"],
                    "exercise": ex["name"],
                    "e1rm": round(e, 2),
                    "best_weight": best_set.get("weight_kg", 0),
                    "best_reps": best_set.get("reps", 0),
                    "num_sets": len(sets),
                })

    if not entries:
        err_exit(f"Exercise '{target}' not found in history")

    if args.json:
        print(json.dumps(entries, indent=2))
    else:
        print(f"Progress: {target}")
        print(f"{'Date':<12} {'Exercise':<25} {'Best Set':>12} {'e1RM':>10} {'Sets':>6}")
        print("-" * 67)
        for e in entries:
            bs = f"{e['best_weight']}x{e['best_reps']}"
            print(f"{e['date']:<12} {e['exercise']:<25} {bs:>12} {e['e1rm']:>10.1f} {e['num_sets']:>6}")


def cmd_summary(sessions, args):
    if not sessions:
        err_exit("No session data found")

    s = sessions[-1]
    total_sets = sum(len(ex.get("sets", [])) for ex in s.get("actual", []))
    muscles = list({ex.get("muscle_group", "unknown") for ex in s.get("actual", [])})

    result = {
        "date": s["date"],
        "day": s.get("day", ""),
        "duration_min": s.get("duration_min"),
        "exercises": [ex["name"] for ex in s.get("actual", [])],
        "total_sets": total_sets,
        "muscle_groups": muscles,
        "plan_adherence": s.get("plan_adherence", "unknown"),
        "notes": s.get("notes", ""),
    }

    # Add duration info from start_time/end_time
    td = session_duration(s)
    if td:
        result["started_at"] = td[0]
        result["ended_at"] = td[1]
        result["computed_duration_min"] = td[2]

    # Plan vs actual comparison
    planned = s.get("planned")
    if planned:
        comparison = []
        actual_map = {ex["name"]: ex for ex in s.get("actual", [])}
        for p in planned:
            pname = p["name"]
            # Find matching actual exercise
            actual = None
            for aname, aex in actual_map.items():
                if normalize_match(aname, pname):
                    actual = aex
                    break
            entry = {"name": pname, "planned": p.get("sets_reps", ""), "planned_weight": p.get("weight_kg", "")}
            if actual:
                sets = actual.get("sets", [])
                actual_sets = len(sets)
                actual_reps = [st.get("reps", 0) for st in sets]
                actual_weights = [st.get("weight_kg", 0) for st in sets]
                entry["actual"] = f"{actual_sets}x{actual_reps[0] if actual_reps else '?'}"
                entry["actual_weight"] = max(actual_weights) if actual_weights else 0
                entry["completed"] = True
            else:
                entry["actual"] = "skipped"
                entry["actual_weight"] = 0
                entry["completed"] = False
            comparison.append(entry)
        result["plan_comparison"] = comparison

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Session: {result['date']} (Day {result['day']})")
        if result["duration_min"]:
            print(f"Duration: {result['duration_min']} min")
        print(f"Adherence: {result['plan_adherence']}")
        print(f"Total sets: {result['total_sets']}")
        print(f"Muscles: {', '.join(muscles)}")
        if planned:
            print(f"\nPlan vs Actual:")
            for c in result.get("plan_comparison", []):
                status = "✓" if c.get("completed") else "✗"
                print(f"  {status} {c['name']}: planned {c['planned']} @ {c['planned_weight']}kg → actual {c['actual']} @ {c['actual_weight']}kg")
        else:
            print(f"\nExercises:")
            for ex in s.get("actual", []):
                sets_str = ", ".join(
                    f"{st.get('weight_kg', 'BW')}x{st.get('reps', '?')}" for st in ex.get("sets", [])
                )
                print(f"  {ex['name']}: {sets_str}")
        if result["notes"]:
            print(f"\nNotes: {result['notes']}")


def cmd_compare(sessions, args):
    date1, date2 = args.date1, args.date2
    s1 = next((s for s in sessions if s["date"] == date1), None)
    s2 = next((s for s in sessions if s["date"] == date2), None)

    if not s1:
        err_exit(f"No session found for {date1}")
    if not s2:
        err_exit(f"No session found for {date2}")

    # Build exercise comparison
    exercises = {}
    for ex in s1.get("actual", []):
        name = ex["name"]
        exercises[name] = {"name": name, "e1rm_1": best_e1rm_for_exercise(ex), "e1rm_2": 0, "sets_1": len(ex.get("sets", [])), "sets_2": 0}
    for ex in s2.get("actual", []):
        name = ex["name"]
        if name not in exercises:
            exercises[name] = {"name": name, "e1rm_1": 0, "e1rm_2": 0, "sets_1": 0, "sets_2": 0}
        exercises[name]["e1rm_2"] = best_e1rm_for_exercise(ex)
        exercises[name]["sets_2"] = len(ex.get("sets", []))

    for v in exercises.values():
        v["e1rm_diff"] = round(v["e1rm_2"] - v["e1rm_1"], 2)

    result = {
        "date1": date1, "date2": date2,
        "exercises": list(exercises.values()),
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Compare: {date1} vs {date2}")
        print(f"{'Exercise':<25} {'e1RM 1':>8} {'e1RM 2':>8} {'Diff':>8} {'Sets':>10}")
        print("-" * 61)
        for e in result["exercises"]:
            diff = f"{e['e1rm_diff']:+.1f}" if e["e1rm_diff"] != 0 else "="
            sets = f"{e['sets_1']} → {e['sets_2']}"
            print(f"{e['name']:<25} {e['e1rm_1']:>8.1f} {e['e1rm_2']:>8.1f} {diff:>8} {sets:>10}")


def cmd_goals(args):
    """Manage strength goals."""
    goals_path = args.goals_file
    subcmd = args.goals_command

    if subcmd == "list":
        goals = load_goals(goals_path)
        if not goals:
            err_exit("No goals found")
        if args.json:
            print(json.dumps(goals, indent=2))
        else:
            for i, entry in enumerate(goals):
                print(f"Goal set #{i+1} — {entry.get('date_set', '?')} → {entry.get('target_date', '?')}")
                if entry.get('note'):
                    print(f"  Note: {entry['note']}")
                for name, val in entry.get('goals', {}).items():
                    print(f"  {name}: {_goal_target(val)} e1RM")
                print()

    elif subcmd == "current":
        latest = get_latest_goals(goals_path)
        if not latest:
            err_exit("No goals found")
        if args.json:
            print(json.dumps(latest, indent=2))
        else:
            print(f"Current goals ({latest.get('date_set', '?')} → {latest.get('target_date', '?')})")
            if latest.get('note'):
                print(f"Note: {latest['note']}")
            for name, val in latest.get('goals', {}).items():
                print(f"  {name}: {_goal_target(val)} e1RM")

    elif subcmd == "add":
        if not args.goal_json:
            err_exit("--json argument required for 'goals add'")
        try:
            new_entry = json.loads(args.goal_json)
        except json.JSONDecodeError as e:
            err_exit(f"Invalid JSON: {e}")
        # Validate required fields
        if "goals" not in new_entry:
            err_exit("Missing 'goals' field")
        if "target_date" not in new_entry:
            err_exit("Missing 'target_date' field")
        if "date_set" not in new_entry:
            new_entry["date_set"] = datetime.now().strftime("%Y-%m-%d")

        goals = load_goals(goals_path)
        goals.append(new_entry)
        Path(goals_path).parent.mkdir(parents=True, exist_ok=True)
        with open(goals_path, "w") as f:
            json.dump(goals, f, indent=2)
        print(f"Goal added. Total: {len(goals)} goal set(s)")

    else:
        err_exit(f"Unknown goals subcommand: {subcmd}. Use list, add, or current.")


def _chart_orientation(args):
    if args.horizontal:
        return "horizontal"
    return "vertical"  # default


def draw_goal_lines(ax, goals, start_date, end_date, start_values, colors=None):
    """Draw dashed goal lines on a chart from start_value to goal_value.
    
    Args:
        ax: matplotlib axes
        goals: {exercise_name: target_e1rm}
        start_date: datetime
        end_date: datetime  
        start_values: {exercise_name: current_e1rm}
        colors: {exercise_name: color_string} or None for gray
    """
    for name, target in goals.items():
        if name not in start_values:
            continue
        start_val = start_values[name]
        c = (colors or {}).get(name, '#888888')
        ax.plot([start_date, end_date], [start_val, target],
                '--', color=c, alpha=0.4, linewidth=1.5, zorder=1)
        ax.plot(end_date, target, marker='D', color=c, alpha=0.6,
                markersize=8, zorder=1)


def _compute_kpis(sessions, lift_data):
    """Compute KPIs using rolling 14-day windows.
    
    Args:
        sessions: list of session dicts
        lift_data: {lift_name: (dates_as_datetime, values)} from chart data collection
    Returns:
        (adherence_pct, avg_e1rm, avg_e1rm_change, volume, volume_change,
         current_session_count, prev_session_count)
    """
    if not sessions:
        return 0, 0, 0, 0, 0, 0, 0

    latest_date = datetime.strptime(sessions[-1]["date"], "%Y-%m-%d")
    current_start = latest_date - timedelta(days=13)  # last 14 days inclusive
    prev_end = current_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=13)

    # Adherence: sessions in current 14-day window / expected (14/7 * 3 = 6)
    current_sessions = [s for s in sessions
                        if current_start <= datetime.strptime(s["date"], "%Y-%m-%d") <= latest_date]
    prev_sessions = [s for s in sessions
                     if prev_start <= datetime.strptime(s["date"], "%Y-%m-%d") <= prev_end]
    expected = 14 / 7 * 3  # 6
    adherence = min(100, round(len(current_sessions) / expected * 100))

    # e1RM: best per lift in each window, then average across lifts
    def best_in_window(dates, values, win_start, win_end):
        best = None
        for d, v in zip(dates, values):
            if win_start <= d <= win_end and (best is None or v > best):
                best = v
        return best

    current_bests = []
    prev_bests = []
    for name, (dates, values) in lift_data.items():
        cb = best_in_window(dates, values, current_start, latest_date)
        if cb is not None:
            current_bests.append(cb)
        pb = best_in_window(dates, values, prev_start, prev_end)
        if pb is not None:
            prev_bests.append(pb)

    avg_e1rm = round(sum(current_bests) / len(current_bests), 1) if current_bests else 0
    if prev_bests:
        avg_prev = round(sum(prev_bests) / len(prev_bests), 1)
        avg_change = round(avg_e1rm - avg_prev, 1)
    else:
        avg_change = 0

    # Volume: total hard sets in window
    def count_sets_in_window(sess_list, win_start, win_end):
        total = 0
        for s in sess_list:
            sd = datetime.strptime(s["date"], "%Y-%m-%d")
            if win_start <= sd <= win_end:
                for ex in s.get("actual", []):
                    total += len(ex.get("sets", []))
        return total

    volume = count_sets_in_window(sessions, current_start, latest_date)
    prev_volume = count_sets_in_window(sessions, prev_start, prev_end)
    vol_change = volume - prev_volume

    return adherence, avg_e1rm, avg_change, volume, vol_change, len(current_sessions), len(prev_sessions)


def cmd_chart_e1rm(sessions, args):
    if not sessions:
        err_exit("No session data found")

    # Period filtering
    period = getattr(args, 'period', 'all')
    if period == "current" and sessions:
        cutoff = datetime.strptime(sessions[-1]["date"], "%Y-%m-%d") - timedelta(weeks=6)
        sessions = [s for s in sessions if datetime.strptime(s["date"], "%Y-%m-%d") >= cutoff]

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib.patches import FancyBboxPatch
    except ImportError:
        err_exit("matplotlib not installed")

    orientation = _chart_orientation(args)
    lifts = [l.strip() for l in args.lifts.split(",")] if args.lifts else None

    if not lifts:
        # First try goals.json for tracked lifts
        goals_path = getattr(args, 'goals_file', None) or default_goals_path(args.history_dir)
        lifts = _get_tracked_lifts(goals_path)

    # -- Dark dashboard palette --
    BG = '#0d1117'
    COLORS = ['#4FC3F7', '#EF5350', '#66BB6A', '#FFA726', '#AB47BC', '#26C6DA', '#FF7043', '#9CCC65', '#5C6BC0', '#FFCA28', '#8D6E63', '#78909C']
    CURRENT_BAND = '#4FC3F7'
    PREV_BAND = '#FFA726'
    GRID_C = 'white'
    TICK_C = '#999999'

    # Collect data for all lifts
    lift_data = {}  # {name: (dates, values)}
    for lift in lifts:
        dates, values = [], []
        for s in sessions:
            for ex in s.get("actual", []):
                if normalize_match(ex["name"], lift):
                    e = best_e1rm_for_exercise(ex)
                    if e > 0:
                        dates.append(datetime.strptime(s["date"], "%Y-%m-%d"))
                        values.append(round(e, 1))
                    break
        if dates:
            lift_data[lift] = (dates, values)

    if orientation == "vertical":
        # iPhone Pro Max: 1290x2796 @ 150dpi
        fig = plt.figure(figsize=(1290/150, 2796/150), dpi=150, facecolor=BG)

        # Content zone: top ~82%, bottom ~13% for iOS safe areas
        # KPI at top, then legend, then chart
        ax = fig.add_axes([0.12, 0.13, 0.82, 0.52], facecolor=BG)

        # -- KPI section --
        adherence, avg_e1rm, avg_change, volume, vol_change, cur_cnt, prev_cnt = _compute_kpis(sessions, lift_data)
        show_delta = cur_cnt >= 3 and prev_cnt >= 3

        # Adherence color
        if adherence >= 90:
            adh_color = '#66BB6A'
        elif adherence >= 60:
            adh_color = '#FFA726'
        else:
            adh_color = '#EF5350'

        if show_delta:
            change_arrow = '▲' if avg_change > 0 else ('▼' if avg_change < 0 else '—')
            change_color = '#66BB6A' if avg_change > 0 else ('#EF5350' if avg_change < 0 else TICK_C)
        else:
            change_arrow = None
            change_color = TICK_C

        # KPI text at top — HORIZONTAL layout (side by side) — slightly larger
        fig.text(0.30, 0.83, f"{adherence}%", fontsize=60, fontweight='bold',
                 color=adh_color, ha='center', va='center')
        fig.text(0.30, 0.805, "adherence", fontsize=17, color='#555555', ha='center', va='center')
        # Adherence delta
        if show_delta:
            adh_prev_sessions = prev_cnt
            adh_prev = min(100, round(adh_prev_sessions / (14 / 7 * 3) * 100))
            adh_change = adherence - adh_prev
            adh_arrow = '▲' if adh_change > 0 else ('▼' if adh_change < 0 else '—')
            adh_ch_color = '#66BB6A' if adh_change > 0 else ('#EF5350' if adh_change < 0 else TICK_C)
            fig.text(0.30, 0.78, f"{adh_arrow} {abs(adh_change)}%", fontsize=27, fontweight='bold',
                     color=adh_ch_color, ha='center', va='center')
        else:
            fig.text(0.245, 0.78, "▲▼ no", fontsize=20,
                     color='#555555', ha='right', va='center')
            fig.text(0.30, 0.78, " past ", fontsize=20, fontweight='bold',
                     color=PREV_BAND, alpha=0.7, ha='center', va='center')
            fig.text(0.355, 0.78, "data", fontsize=20,
                     color='#555555', ha='left', va='center')

        fig.text(0.72, 0.83, f"{avg_e1rm:.0f} kg", fontsize=60, fontweight='bold',
                 color='white', ha='center', va='center')
        fig.text(0.72, 0.805, "avg e1RM", fontsize=17, color='#555555', ha='center', va='center')
        if show_delta:
            fig.text(0.72, 0.78, f"{change_arrow} {abs(avg_change):.1f} kg", fontsize=27, fontweight='bold',
                     color=change_color, ha='center', va='center')
        else:
            fig.text(0.665, 0.78, "▲▼ no", fontsize=20,
                     color='#555555', ha='right', va='center')
            fig.text(0.72, 0.78, " past ", fontsize=20, fontweight='bold',
                     color=PREV_BAND, alpha=0.7, ha='center', va='center')
            fig.text(0.775, 0.78, "data", fontsize=20,
                     color='#555555', ha='left', va='center')

        # -- Legend between KPI and chart (single row, 4 items) --
        lift_names = list(lift_data.keys())
        goals_path_for_names = getattr(args, 'goals_file', None) or default_goals_path(args.history_dir)
        short_names = _get_short_names(goals_path_for_names)
        legend_y = 0.70
        n_lifts = min(len(lift_names), 8)
        # Build legend string centered: "● Squat   ● Bench   ● OHP   ● Row"
        legend_items = []
        legend_colors = []
        for i, name in enumerate(lift_names[:n_lifts]):
            short = short_names.get(name, name[:15])
            legend_items.append(short)
            legend_colors.append(COLORS[i % len(COLORS)])
        # Evenly space across center
        spacing = 1.0 / (n_lifts + 1)
        for i, (label, c) in enumerate(zip(legend_items, legend_colors)):
            x = spacing * (i + 1)
            fig.text(x - 0.02, legend_y, '●', fontsize=22, color=c, ha='center', va='center')
            fig.text(x + 0.01, legend_y, label, fontsize=17, fontweight='bold',
                     color=c, ha='left', va='center')

    else:
        # Horizontal: simpler layout
        fig = plt.figure(figsize=(12, 6), facecolor=BG)
        ax = fig.add_axes([0.08, 0.15, 0.88, 0.75], facecolor=BG)

    # -- Plot lines --
    lift_names = list(lift_data.keys())
    for i, (lift, (dates, values)) in enumerate(lift_data.items()):
        c = COLORS[i % len(COLORS)]
        lw = 6 if orientation == "vertical" else 3
        ms = 16 if orientation == "vertical" else 8
        ax.plot(dates, values, 'o-', color=c, linewidth=lw, markersize=ms, zorder=3)

        # Value badge: LEFT of last point
        if values:
            last_val = values[-1]
            last_date = dates[-1]
            badge_fs = 14 if orientation == "vertical" else 10
            ax.annotate(
                f" {last_val:.0f} ",
                (last_date, last_val),
                textcoords="offset points",
                xytext=(20, 0) if orientation == "vertical" else (16, 0),
                fontsize=badge_fs, fontweight='bold', color='white',
                ha='left', va='center',
                bbox=dict(boxstyle='round,pad=0.3', facecolor=c, edgecolor='none', alpha=0.9),
                zorder=4,
            )

    # -- Goal lines from goals.json --
    skip_goals = getattr(args, 'no_goals', False)
    goals_path = getattr(args, 'goals_file', None) or default_goals_path(args.history_dir)
    latest_goals = get_latest_goals(goals_path) if not skip_goals else None
    if latest_goals and sessions:
        goal_targets = latest_goals.get("goals", {})
        target_date_str = latest_goals.get("target_date")
        if goal_targets and target_date_str:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
            # For each goal, find matching lift and draw line from first data point to target
            for gname, goal_val in goal_targets.items():
                target_val = _goal_target(goal_val)
                matched_lift = None
                matched_color = '#888888'
                for i, lname in enumerate(lift_data.keys()):
                    if normalize_match(lname, gname):
                        matched_lift = lname
                        matched_color = COLORS[i % len(COLORS)]
                        break
                if not matched_lift or matched_lift not in lift_data:
                    continue
                dates, values = lift_data[matched_lift]
                if not dates:
                    continue
                # Line from first data point to goal target at target_date
                start_date = dates[0]
                start_val = values[0]
                ax.plot([start_date, target_date], [start_val, target_val],
                        '--', color=matched_color, alpha=0.4, linewidth=1.5, zorder=1)
                ax.plot(target_date, target_val, marker='D', color=matched_color, alpha=0.6,
                        markersize=8, zorder=1)

    # Also support legacy --plan flag
    elif hasattr(args, 'plan') and args.plan and os.path.isfile(args.plan):
        plan_text = Path(args.plan).read_text()
        goals = parse_goals_from_plan(plan_text)
        filtered_goals = {}
        for gname, target in goals.items():
            for lname in lift_data:
                if normalize_match(lname, gname):
                    filtered_goals[gname] = (target, lname)
                    break
        if filtered_goals and sessions:
            first_date = datetime.strptime(sessions[0]["date"], "%Y-%m-%d")
            start_values = {}
            for gname in filtered_goals:
                for s in sessions[:1]:
                    for ex in s.get("actual", []):
                        if normalize_match(ex["name"], gname):
                            e = best_e1rm_for_exercise(ex)
                            if e > 0:
                                start_values[gname] = e
                            break
            for gname, (target, _) in filtered_goals.items():
                if gname not in start_values:
                    continue
                end_date = first_date + timedelta(weeks=12)
                ax.plot([first_date, end_date], [start_values[gname], target],
                        '--', color='#888888', alpha=0.4, linewidth=1.5, zorder=1)
                ax.plot(end_date, target, marker='D', color='#888888', alpha=0.6,
                        markersize=8, zorder=1)

    # -- Planned points (hollow markers) from session files --
    # Find sessions that have "planned" but no "actual" (pre-workout state)
    # Also support --planned JSON override for manual use
    planned_points = {}  # {lift_name: (date, e1rm)}

    # Auto-detect from sessions: if a session has planned exercises but no actual
    for s in sessions:
        has_actual = bool(s.get("actual"))
        has_planned = bool(s.get("planned"))
        if has_planned and not has_actual:
            s_date = datetime.strptime(s["date"], "%Y-%m-%d")
            for p in s["planned"]:
                pname = p.get("name", "")
                pe1rm = 0
                # Try nested sets first (session format from workout_live.py init)
                if p.get("sets"):
                    pe1rm = best_e1rm_for_exercise(p)
                else:
                    # Legacy flat format: weight_kg + target_reps at top level
                    pw = p.get("weight_kg", 0)
                    preps = p.get("target_reps", p.get("reps", 0))
                    if pw and preps:
                        pe1rm = e1rm_epley(pw, preps)
                if pe1rm > 0:
                    planned_points[pname] = (s_date, round(pe1rm, 1))

    # Override with --planned JSON if provided
    planned_json = getattr(args, 'planned', None)
    if planned_json:
        try:
            planned_data = json.loads(planned_json)
        except json.JSONDecodeError:
            planned_data = {}
        if planned_data:
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            for pname, p_e1rm in planned_data.items():
                planned_points[pname] = (today, p_e1rm)

    # Draw planned points
    for pname, (p_date, p_e1rm) in planned_points.items():
        matched_lift = None
        matched_color = '#888888'
        for i, lname in enumerate(lift_data.keys()):
            if normalize_match(lname, pname):
                matched_lift = lname
                matched_color = COLORS[i % len(COLORS)]
                break
        if matched_lift and matched_lift in lift_data:
            dates, values = lift_data[matched_lift]
            if dates and values:
                last_date = dates[-1]
                last_val = values[-1]
                ms_planned = 18 if orientation == "vertical" else 10
                lw_planned = 3 if orientation == "vertical" else 2
                # Dashed line from last actual to planned
                ax.plot([last_date, p_date], [last_val, p_e1rm],
                        '--', color=matched_color, alpha=0.5, linewidth=lw_planned, zorder=2)
                # Hollow circle marker at planned point
                ax.plot(p_date, p_e1rm, 'o', color=matched_color,
                        markersize=ms_planned, markerfacecolor='none',
                        markeredgewidth=lw_planned, zorder=5)

    # -- Window background bands --
    if sessions:
        latest = datetime.strptime(sessions[-1]["date"], "%Y-%m-%d")
        cur_start = latest - timedelta(days=13)
        prv_end = cur_start - timedelta(days=1)
        prv_start = prv_end - timedelta(days=13)
        ax.axvspan(cur_start, latest, alpha=0.07, color=CURRENT_BAND, zorder=0)
        ax.axvspan(prv_start, prv_end, alpha=0.04, color=PREV_BAND, zorder=0)

    # -- Axis styling --
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.06, linewidth=0.8, color=GRID_C)
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.tick_params(axis='both', colors=TICK_C, labelsize=15 if orientation == "vertical" else 11)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    fig.autofmt_xdate(rotation=0, ha='center')

    # No Y-axis label (saves space)
    ax.set_ylabel('')
    ax.set_xlabel('')

    # Subtle metric label below chart
    ax.text(0.5, -0.06, 'e1RM (kg)', transform=ax.transAxes,
            fontsize=18, color='white', alpha=0.35, ha='center', va='top',
            fontfamily='monospace')
    ax.text(0.32, -0.10, 'last 14 days', transform=ax.transAxes,
            fontsize=13, color=CURRENT_BAND, alpha=0.5, ha='right', va='top')
    ax.text(0.5, -0.10, ' vs ', transform=ax.transAxes,
            fontsize=13, color='white', alpha=0.35, ha='center', va='top')
    ax.text(0.68, -0.10, '14 days before', transform=ax.transAxes,
            fontsize=13, color=PREV_BAND, alpha=0.5, ha='left', va='top')

    # Horizontal mode: legend below chart
    if orientation != "vertical":
        legend_parts = []
        for i, name in enumerate(lift_data.keys()):
            c = COLORS[i % len(COLORS)]
            legend_parts.append(ax.plot([], [], 'o-', color=c, linewidth=3, markersize=8, label=name)[0])
        if legend_parts:
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.12), ncol=len(legend_parts),
                      frameon=False, fontsize=11,
                      labelcolor='white')

    if getattr(args, '_return_fig', False):
        return fig, ax

    if orientation == "vertical":
        plt.savefig(args.output, dpi=150, facecolor=BG)
    else:
        plt.savefig(args.output, dpi=150, facecolor=BG, bbox_inches='tight')
    plt.close()
    print(f"Chart saved to {args.output}")


def cmd_chart_volume(sessions, args):
    if not sessions:
        err_exit("No session data found")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        err_exit("matplotlib not installed")

    orientation = _chart_orientation(args)

    # Compute weekly volume per muscle group
    weeks = {}
    for s in sessions:
        wk = week_key(s["date"])
        if wk not in weeks:
            weeks[wk] = {}
        for ex in s.get("actual", []):
            mg = ex.get("muscle_group", "unknown")
            weeks[wk][mg] = weeks[wk].get(mg, 0) + len(ex.get("sets", []))

    sorted_weeks = sorted(weeks.keys())
    all_mg = sorted({mg for w in weeks.values() for mg in w})

    if orientation == "vertical":
        fig, ax = plt.subplots(figsize=(6, 10))
    else:
        fig, ax = plt.subplots(figsize=(12, 6))

    colors = ['#2196F3', '#F44336', '#4CAF50', '#FF9800', '#9C27B0', '#00BCD4', '#795548', '#607D8B']
    import numpy as np
    x = np.arange(len(sorted_weeks))
    width = 0.8 / max(len(all_mg), 1)

    for i, mg in enumerate(all_mg):
        vals = [weeks[w].get(mg, 0) for w in sorted_weeks]
        ax.bar(x + i * width, vals, width, label=mg, color=colors[i % len(colors)])

    ax.set_xticks(x + width * len(all_mg) / 2)
    ax.set_xticklabels(sorted_weeks, rotation=45)
    ax.set_title("Weekly Volume (Hard Sets) by Muscle Group", fontweight="bold")
    ax.set_ylabel("Hard Sets")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(args.output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Chart saved to {args.output}")



def cmd_log(args):
    history_dir = args.history_dir
    source = args.source

    # Try as file first
    data = None
    if os.path.isfile(source):
        try:
            data = json.loads(Path(source).read_text())
        except json.JSONDecodeError as e:
            err_exit(f"Invalid JSON in file: {e}")
    else:
        try:
            data = json.loads(source)
        except json.JSONDecodeError:
            err_exit("Invalid JSON string (and not a file path)")

    # Validate required fields
    if "date" not in data:
        err_exit("Missing required field: date")
    # Support both "actual" and legacy "exercises"
    if "actual" not in data and "exercises" in data:
        data["actual"] = data["exercises"]
    if "actual" not in data and "actual" not in data:
        err_exit("Missing required field: actual (or exercises)")

    # Validate date format
    try:
        datetime.strptime(data["date"], "%Y-%m-%d")
    except ValueError:
        err_exit(f"Invalid date format: {data['date']}")

    # Validate start_time/end_time if present
    for field in ("start_time", "end_time"):
        if field in data and data[field] is not None:
            if not validate_time_str(data[field]):
                err_exit(f"Invalid {field} format: {data[field]} (expected HH:MM)")

    # Validate per-exercise start_time/end_time
    for ex in data.get("actual", []):
        for field in ("start_time", "end_time"):
            if field in ex and ex[field] is not None:
                if not validate_time_str(ex[field]):
                    err_exit(f"Invalid {field} in exercise '{ex.get('name', '?')}': {ex[field]}")

    # Validate planned if present
    if "planned" in data:
        pl_errors = validate_planned(data["planned"])
        if pl_errors:
            err_exit("Planned validation failed:\n  " + "\n  ".join(pl_errors))

    out_path = os.path.join(history_dir, f"{data['date']}.json")
    os.makedirs(history_dir, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved session to {out_path}")


def cmd_validate(sessions_raw, args):
    """Validate all JSONs in history dir."""
    history_dir = args.history_dir
    p = Path(history_dir)
    files = sorted(p.glob("*.json"))

    if not files:
        if args.json:
            print(json.dumps({"valid": False, "errors": ["No JSON files found"]}))
        err_exit("No JSON files found")

    errors = []
    valid_count = 0

    for f in files:
        fname = f.name
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            errors.append({"file": fname, "error": f"Invalid JSON: {e}"})
            continue

        if "date" not in data:
            errors.append({"file": fname, "error": "Missing field: date"})
            continue
        # Support both "actual" and legacy "exercises"
        if "actual" not in data and "exercises" in data:
            data["actual"] = data["exercises"]
        if "actual" not in data and "actual" not in data:
            errors.append({"file": fname, "error": "Missing field: actual (or exercises)"})
            continue

        # Check filename matches date
        expected_fname = f"{data['date']}.json"
        if fname != expected_fname:
            errors.append({"file": fname, "error": f"Filename/date mismatch: file={fname}, date={data['date']}"})
            continue

        # Validate start_time/end_time if present
        for field in ("start_time", "end_time"):
            val = data.get(field)
            if val is not None and not validate_time_str(val):
                errors.append({"file": fname, "error": f"Invalid {field}: {val}"})
                continue

        # Validate per-exercise start_time/end_time
        ex_time_err = False
        for ex in data.get("actual", []):
            for field in ("start_time", "end_time"):
                val = ex.get(field)
                if val is not None and not validate_time_str(val):
                    errors.append({"file": fname, "error": f"Invalid {field} in exercise '{ex.get('name', '?')}': {val}"})
                    ex_time_err = True
                    break
            if ex_time_err:
                break
        if ex_time_err:
            continue

        # Validate planned if present
        if "planned" in data:
            pl_errors = validate_planned(data["planned"])
            if pl_errors:
                errors.append({"file": fname, "error": f"Planned errors: {'; '.join(pl_errors)}"})
                continue

        valid_count += 1

    if args.json:
        result = {"valid": len(errors) == 0, "files": len(files), "valid_count": valid_count, "errors": errors}
        print(json.dumps(result, indent=2))

    if errors:
        if not args.json:
            for e in errors:
                print(f"  ✗ {e['file']}: {e['error']}", file=sys.stderr)
        sys.exit(1)
    else:
        if not args.json:
            print(f"All {valid_count} files valid ✓")


# ---- CLI ----

def _add_common(p):
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--vertical", action="store_true", help="Vertical (portrait) chart")
    p.add_argument("--horizontal", action="store_true", help="Horizontal (landscape) chart")
    p.add_argument("--lifts", type=str, default=None, help="Comma-separated lift names")
    p.add_argument("--period", type=str, default="all", choices=["current", "all"], help="Period: current mesocycle or all time")
    p.add_argument("--plan", type=str, default=None, help="Path to plan.md for goal lines")
    p.add_argument("--goals-file", type=str, default=None, dest="goals_file",
                   help="Path to goals.json")
    p.add_argument("--no-goals", action="store_true", default=False, dest="no_goals",
                   help="Disable goal projection lines on chart")
    p.add_argument("--planned", type=str, default=None,
                   help='JSON object of planned e1RM for today, e.g. \'{"OHP": 62, "RDL": 150}\'.'
                        ' Shown as hollow markers on today\'s date with dashed line from last actual.')


def main():
    parser = argparse.ArgumentParser(description="Gym analytics CLI")
    sub = parser.add_subparsers(dest="command")

    for cmd in ["e1rm", "volume"]:
        p = sub.add_parser(cmd)
        p.add_argument("history_dir")
        _add_common(p)

    p = sub.add_parser("progress")
    p.add_argument("history_dir")
    p.add_argument("exercise")
    _add_common(p)

    p = sub.add_parser("summary")
    p.add_argument("history_dir")
    _add_common(p)

    p = sub.add_parser("compare")
    p.add_argument("history_dir")
    p.add_argument("date1")
    p.add_argument("date2")
    _add_common(p)

    for cmd in ["chart-e1rm", "chart-volume"]:
        p = sub.add_parser(cmd)
        p.add_argument("history_dir")
        p.add_argument("output")
        _add_common(p)

    p = sub.add_parser("log")
    p.add_argument("history_dir")
    p.add_argument("source")
    _add_common(p)

    p = sub.add_parser("validate")
    p.add_argument("history_dir")
    _add_common(p)

    p = sub.add_parser("goals")
    p.add_argument("goals_command", choices=["list", "add", "current"], help="Goals subcommand")
    p.add_argument("--goal-json", type=str, default=None, dest="goal_json",
                   help="JSON string for new goal entry (used with 'add')")
    _add_common(p)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(2)

    if args.command == "log":
        cmd_log(args)
        return

    if args.command == "validate":
        cmd_validate(None, args)
        return

    if args.command == "goals":
        if not args.goals_file:
            err_exit("--goals-file is required for goals command")
        cmd_goals(args)
        return

    history_dir = args.history_dir
    if not os.path.isdir(history_dir):
        err_exit(f"Directory not found: {history_dir}")

    sessions = load_sessions(history_dir)

    dispatch = {
        "e1rm": cmd_e1rm,
        "volume": cmd_volume,
        "progress": cmd_progress,
        "summary": cmd_summary,
        "compare": cmd_compare,
        "chart-e1rm": cmd_chart_e1rm,
        "chart-volume": cmd_chart_volume,
    }

    dispatch[args.command](sessions, args)


if __name__ == "__main__":
    main()
