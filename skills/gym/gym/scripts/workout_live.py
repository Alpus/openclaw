#!/usr/bin/env python3
"""Live workout tracker — record exercises and display progress.

Usage:
    workout_live.py status <session_file>
        Show current workout progress (plan vs actual)

    workout_live.py log <session_file> <exercise_json>
        Log a completed exercise and show updated progress

Exercise JSON format:
    {"name": "OHP", "sets": [{"reps": 10, "weight_kg": 45}, ...]}
    or shorthand: {"name": "OHP", "reps": 10, "weight_kg": 45, "num_sets": 4}
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def load_session(path):
    """Load session JSON file."""
    p = Path(path)
    if not p.exists():
        print(f"❌ Session file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(p.read_text())


def save_session(path, data):
    """Save session JSON file."""
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _find_by_name(items, exercise_name):
    """Find an item by name with priority: exact > starts_with > contains.

    Returns the first match at the highest priority level.
    """
    name_lower = exercise_name.lower()

    # 1. Exact match
    for item in items:
        if item.get("name", "").lower() == name_lower:
            return item

    # 2. Starts with
    for item in items:
        if item.get("name", "").lower().startswith(name_lower):
            return item

    # 3. Contains (but only if query is 4+ chars to avoid false matches)
    if len(name_lower) >= 4:
        for item in items:
            if name_lower in item.get("name", "").lower():
                return item

    return None


def find_planned(planned, exercise_name):
    """Find a planned exercise by name (exact > starts_with > contains)."""
    return _find_by_name(planned, exercise_name)


def find_actual(actual, exercise_name):
    """Find an actual exercise by name (exact > starts_with > contains)."""
    return _find_by_name(actual, exercise_name)


def format_actual_exercise(actual_ex):
    """Format an actual exercise result using same grouped format."""
    name = actual_ex["name"]
    sets = actual_ex.get("sets", [])
    if not sets:
        return name
    return f"{name} — {_format_sets(sets)}"


def _format_sets(sets):
    """Format a list of sets with grouping.

    Examples: '20kg×10 · 45kg×10 (×3)', 'BW×12 (×3)', 'BW×8 · 6kg×8 (×3)'.
    Weight 0 or missing → 'BW'. Consecutive identical sets grouped with (×N).
    """
    if not sets:
        return ""

    # Build list of (weight, reps) tuples
    entries = []
    for s in sets:
        w = s.get("weight_kg", 0)
        r = s.get("reps", 0)
        entries.append((w, r))

    # Group consecutive identical entries
    groups = []
    for w, r in entries:
        if groups and groups[-1][0] == w and groups[-1][1] == r:
            groups[-1] = (w, r, groups[-1][2] + 1)
        else:
            groups.append((w, r, 1))

    parts = []
    for w, r, count in groups:
        w_str = f"{w}kg" if w > 0 else "BW"
        if count > 1:
            parts.append(f"{w_str}×{r} (×{count})")
        else:
            parts.append(f"{w_str}×{r}")

    return " · ".join(parts)


def format_planned_exercise(planned_ex):
    """Format a planned exercise with grouped sets."""
    name = planned_ex["name"]
    sets = planned_ex.get("sets", [])

    if sets:
        return f"{name} — {_format_sets(sets)}"

    # Legacy format fallback
    sets_reps = planned_ex.get("sets_reps", "")
    weight = planned_ex.get("weight_kg", 0)
    if weight and sets_reps:
        return f"{name} — {sets_reps} @ {weight}"
    elif sets_reps:
        return f"{name} — {sets_reps}"
    else:
        return name


def _strikethrough(text):
    """GFM strikethrough — OpenClaw converts ~~text~~ to <s>text</s> for Telegram."""
    return f"~~{text}~~"


def _bold(text):
    """GFM bold — OpenClaw converts **text** to <b>text</b> for Telegram."""
    return f"**{text}**"


def _w_str(w):
    """Format weight: 0 → 'BW', >0 → 'Nkg'."""
    return f"{w}kg" if w > 0 else "BW"


def compare_exercise(planned_ex, actual_ex):
    """Compare planned vs actual set by set. Returns formatted string with deviations.

    Uses Unicode strikethrough (̶) for crossed-out values — works in Telegram, Discord, etc.
    Arrows ↑/↓ for deviations.
    """
    if not planned_ex:
        return format_actual_exercise(actual_ex)

    name = actual_ex["name"]
    a_sets = actual_ex.get("sets", [])
    p_sets = planned_ex.get("sets", [])

    if not p_sets:
        return format_actual_exercise(actual_ex)

    # If all sets match perfectly, use grouped format
    if len(a_sets) == len(p_sets):
        all_match = all(
            p_sets[i].get("weight_kg", 0) == a_sets[i].get("weight_kg", 0)
            and p_sets[i].get("reps", 0) == a_sets[i].get("reps", 0)
            for i in range(len(a_sets))
        )
        if all_match:
            return format_actual_exercise(actual_ex)

    # Compare all sets by index, then group consecutive identical results
    raw_parts = []  # list of (formatted_str, is_match) tuples
    max_len = max(len(p_sets), len(a_sets))

    for i in range(max_len):
        p = p_sets[i] if i < len(p_sets) else None
        a = a_sets[i] if i < len(a_sets) else None

        if a and not p:
            raw_parts.append((f"{_w_str(a.get('weight_kg', 0))}×{a.get('reps', 0)}", True))
        elif p and not a:
            pw, pr = p.get("weight_kg", 0), p.get("reps", 0)
            raw_parts.append((_strikethrough(f"{_w_str(pw)}×{pr}"), False))
        else:
            pw, pr = p.get("weight_kg", 0), p.get("reps", 0)
            aw, ar = a.get("weight_kg", 0), a.get("reps", 0)

            if pw == aw and pr == ar:
                raw_parts.append((f"{_w_str(aw)}×{ar}", True))
            elif pw == aw:
                arrow = "↑" if ar > pr else "↓"
                raw_parts.append((f"{_w_str(aw)}×{_strikethrough(pr)} {_bold(str(ar) + arrow)}", False))
            elif pr == ar:
                arrow = "↑" if aw > pw else "↓"
                raw_parts.append((f"{_strikethrough(_w_str(pw))} {_bold(_w_str(aw) + arrow)}×{ar}", False))
            else:
                w_arrow = "↑" if aw > pw else "↓"
                r_arrow = "↑" if ar > pr else "↓"
                raw_parts.append((f"{_strikethrough(_w_str(pw))} {_bold(_w_str(aw) + w_arrow)}×{_strikethrough(pr)} {_bold(str(ar) + r_arrow)}", False))

    # Group consecutive identical matched parts
    grouped = []
    for text, is_match in raw_parts:
        if is_match and grouped and grouped[-1][0] == text and grouped[-1][1]:
            grouped[-1] = (text, True, grouped[-1][2] + 1)
        else:
            grouped.append((text, is_match, 1))

    set_strings = []
    for text, _, count in grouped:
        if count > 1:
            set_strings.append(f"{text} (×{count})")
        else:
            set_strings.append(text)

    return f"{name} — {' · '.join(set_strings)}"


def display_status(session):
    """Display current workout progress."""
    planned = session.get("planned", [])
    actual = session.get("actual", [])
    day = session.get("day", "?")
    date = session.get("date", "?")

    lines = [f"🏋️ Day {day} — {date}", ""]

    # Track which planned exercises are done
    done_names = set()
    for a in actual:
        done_names.add(a.get("name", "").lower())

    idx = 1
    # Show planned exercises in order
    for p in planned:
        pname = p.get("name", "")
        actual_ex = find_actual(actual, pname)
        if actual_ex:
            lines.append(f"✅ {idx}. {compare_exercise(p, actual_ex)}")
        else:
            lines.append(f"⬜ {idx}. {format_planned_exercise(p)}")
        idx += 1

    # Show any unplanned exercises
    for a in actual:
        aname = a.get("name", "")
        if not find_planned(planned, aname):
            lines.append(f"🆕 {idx}. {format_actual_exercise(a)}")
            idx += 1

    # Find next exercise
    next_ex = None
    for p in planned:
        if not find_actual(actual, p.get("name", "")):
            next_ex = p
            break

    if next_ex:
        lines.append("")
        lines.append(f"Следующее — {next_ex['name']}! 💪")
    else:
        lines.append("")
        lines.append("Все упражнения выполнены! 🎉")

    return "\n".join(lines)


def _now_hhmm():
    """Current time as HH:MM string."""
    return datetime.now().strftime("%H:%M")


def _auto_timestamps(session):
    """Set session start_time on first exercise, update end_time on every exercise."""
    now = _now_hhmm()
    if not session.get("start_time"):
        session["start_time"] = now
    session["end_time"] = now


def log_exercise(session, exercise_json):
    """Add an exercise to actual and return updated session."""
    try:
        ex_data = json.loads(exercise_json) if isinstance(exercise_json, str) else exercise_json
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Support shorthand: {"name": "OHP", "reps": 10, "weight_kg": 45, "num_sets": 4}
    if "sets" not in ex_data and "reps" in ex_data:
        num_sets = ex_data.pop("num_sets", 1)
        reps = ex_data.pop("reps")
        weight = ex_data.pop("weight_kg", 0)
        ex_data["sets"] = []
        for _ in range(num_sets):
            s = {"reps": reps}
            if weight:
                s["weight_kg"] = weight
            ex_data["sets"].append(s)

    # Add muscle_group if not present but found in planned
    if "muscle_group" not in ex_data:
        planned = session.get("planned", [])
        p = find_planned(planned, ex_data.get("name", ""))
        if p and "muscle_group" in p:
            ex_data["muscle_group"] = p["muscle_group"]

    # Check if exercise already exists in actual (update it)
    actual = session.get("actual", [])
    found = False
    for i, a in enumerate(actual):
        if a.get("name", "").lower() == ex_data.get("name", "").lower():
            actual[i] = ex_data
            found = True
            break

    if not found:
        actual.append(ex_data)

    session["actual"] = actual
    _auto_timestamps(session)
    return session


def done_exercise(session, exercise_name=None):
    """Mark next (or named) exercise as done — copy planned to actual.

    If exercise_name is None, marks the next pending exercise.
    Returns updated session.
    """
    planned = session.get("planned", [])
    actual = session.get("actual", [])

    target = None
    if exercise_name:
        target = find_planned(planned, exercise_name)
        if not target:
            print(f"❌ Exercise not found in plan: {exercise_name}", file=sys.stderr)
            sys.exit(1)
    else:
        # Find next pending exercise
        for p in planned:
            if not find_actual(actual, p.get("name", "")):
                target = p
                break
        if not target:
            print("❌ All exercises already done!", file=sys.stderr)
            sys.exit(1)

    # Copy planned to actual (strip warmup flag, keep everything else)
    actual_ex = {
        "name": target["name"],
        "sets": [
            {k: v for k, v in s.items() if k != "warmup"}
            for s in target.get("sets", [])
        ]
    }
    if "muscle_group" in target:
        actual_ex["muscle_group"] = target["muscle_group"]

    # Check if already in actual (update) or add new
    found = False
    for i, a in enumerate(actual):
        if a.get("name", "").lower() == actual_ex["name"].lower():
            actual[i] = actual_ex
            found = True
            break
    if not found:
        actual.append(actual_ex)

    session["actual"] = actual
    _auto_timestamps(session)
    return session


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)

    command = sys.argv[1]
    session_file = sys.argv[2]

    if command == "status":
        session = load_session(session_file)
        print(display_status(session))

    elif command == "log":
        if len(sys.argv) < 4:
            print("Usage: workout_live.py log <session_file> <exercise_json>", file=sys.stderr)
            sys.exit(2)
        exercise_json = sys.argv[3]
        session = load_session(session_file)
        session = log_exercise(session, exercise_json)
        save_session(session_file, session)
        print(display_status(session))

    elif command == "done":
        # Mark next or named exercise as done (planned → actual)
        exercise_name = sys.argv[3] if len(sys.argv) > 3 else None
        session = load_session(session_file)
        session = done_exercise(session, exercise_name)
        save_session(session_file, session)
        print(display_status(session))

    elif command == "remove":
        # Remove an exercise from actual
        if len(sys.argv) < 4:
            print("Usage: workout_live.py remove <session_file> <exercise_name>", file=sys.stderr)
            sys.exit(2)
        exercise_name = sys.argv[3]
        session = load_session(session_file)
        target = find_actual(session.get("actual", []), exercise_name)
        if not target:
            print(f"❌ Exercise not found: {exercise_name}", file=sys.stderr)
            sys.exit(1)
        session["actual"] = [a for a in session["actual"] if a is not target]
        save_session(session_file, session)
        print(display_status(session))

    elif command == "lifts":
        # Output comma-separated weighted exercise names from actual (for chart generation)
        session = load_session(session_file)
        lifts = []
        for ex in session.get("actual", []):
            has_weight = any(s.get("weight_kg", 0) > 0 for s in ex.get("sets", []))
            if has_weight:
                lifts.append(ex["name"])
        print(",".join(lifts))

    elif command == "init":
        # Create a new session from program.json
        # Usage: workout_live.py init <session_file> <program_file> <day>
        if len(sys.argv) < 5:
            print("Usage: workout_live.py init <session_file> <program_file> <day>", file=sys.stderr)
            sys.exit(2)
        program_file = sys.argv[3]
        day = sys.argv[4].upper()

        program = json.loads(Path(program_file).read_text())
        if day not in program.get("days", {}):
            print(f"❌ Day '{day}' not found in program. Available: {list(program['days'].keys())}", file=sys.stderr)
            sys.exit(1)

        if Path(session_file).exists():
            existing = json.loads(Path(session_file).read_text())
            if existing.get("actual"):
                print(f"⚠️ Session file exists with {len(existing['actual'])} logged exercises. Use --force to overwrite.", file=sys.stderr)
                if "--force" not in sys.argv:
                    sys.exit(1)

        day_plan = program["days"][day]
        date_str = Path(session_file).stem  # e.g. 2026-02-13

        session = {
            "date": date_str,
            "day": day,
            "planned": day_plan["exercises"],
            "actual": []
        }

        save_session(session_file, session)
        print(display_status(session))

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
