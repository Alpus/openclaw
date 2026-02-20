# Analytics System Reference

Detailed procedures for post-session analysis, weekly reviews, and ad-hoc analysis. Loaded when doing analysis work, not during workouts.

## Post-Session Analysis (after every workout)

After every workout, generate an `analysis` object inside the session JSON (`history/YYYY-MM-DD.json`). This is a formal checklist — think of it like KPIs, always anchored to 12-week goals.

**Checklist (in order):**

1. **Goal alignment**: Start from 12-week goals (`goals.json`). For each tracked lift (Squat/Bench/OHP/Row), compute current e1RM vs target trajectory. Are we on pace? Weeks remaining × required weekly gain.
2. **Session performance**: Plan vs actual for every exercise. What hit, what missed, why? Be specific — "Bench sets 3-4 dropped to 8,6 (fatigue)" not "Bench was hard."
3. **e1RM tracking**: Compute for each compound using Epley (weight × (1 + reps/30), best set). Compare to last session with same exercise. Note trend direction (↑/→/↓).
4. **Volume check**: Total hard sets per muscle group this week so far. On track for 10-20 sets/muscle/week? Flag if under MEV or over MRV.
5. **Weak points**: What's falling behind? Specific muscles, specific lifts. Anchor to goals — "Bench e1RM stalled at 98 for 2 sessions, need +1.3/week to hit 110 by April 19."
6. **Strong points**: What's progressing well? Don't change what works.
7. **Adjustments for next session**: Concrete, specific. Not "maybe increase weight" but "Bench: keep 77.5, aim 10/10/9/7" or "Dips: +18 next Day A."
8. **Recovery signals**: Sleep, stress, energy, soreness mentioned during session. Flag if negative pattern emerging.

**Analysis JSON format** (added to session file as `"analysis"` key):

```json
{
  "analysis": {
    "e1rm": { "Squat": 160.0, "Bench Press (flat)": 98.2, "Seated Cable Row": 113.3 },
    "e1rm_delta": {
      "Squat": {
        "previous": 160.0,
        "current": 160.0,
        "delta": 0,
        "trend": "→",
        "sessions_at_current": 3
      }
    },
    "volume_sets": { "chest": 7, "back": 3, "legs": 3, "shoulders": 3, "abs": 3, "triceps": 3 },
    "volume_week_total": { "chest": 7, "back": 3, "legs": 3 },
    "plan_adherence": 0.85,
    "plan_adherence_detail": {
      "hit": ["Squat", "Seated Cable Row"],
      "exceeded": ["Dips: 12 vs planned 10 reps"],
      "missed": ["Bench: sets 3-4 dropped to 8,6 vs planned 10"],
      "swapped": ["Cable Crunch → Hanging Leg Raise"]
    },
    "strengths": ["Dips +16 × 12 all sets — ready for +18"],
    "weaknesses": ["Bench 77.5 stalled — 8,6 on last sets for 2nd session in a row"],
    "next_session_adjustments": ["Day B: OHP push for 45×10 all 4 sets"],
    "goal_progress": {
      "Squat": {
        "current": 160.0,
        "target": 170,
        "remaining_weeks": 9.7,
        "needed_per_week": 1.03,
        "status": "on_track"
      }
    },
    "mesocycle_position": "Week 3 of Mesocycle 1 (5 weeks + deload)",
    "notes": "Free text — bench strategy, recovery observations, etc."
  }
}
```

**Continuity rule:** Before each session, read the previous session's `analysis.next_session_adjustments` to inform the plan.

## Weekly Review (Saturday morning, via cron)

Deeper analysis. Runs as a cron job — can take more time/tokens since it's not mid-workout.

Store in `<workspace>/health/gym/reviews/YYYY-WXX.md`.

**Checklist:**

1. **Week summary**: Sessions completed vs planned (3/week target). Which days missed? Why?
2. **Volume per muscle group**: Sum hard sets across all sessions. Compare to target ranges (10-20 sets/muscle/week). Flag under-MEV or over-MRV.
3. **e1RM trends**: Week-over-week for all 4 tracked lifts. Direction and magnitude. Generate/update chart.
4. **Goal trajectory**: At current rate, will we hit 12-week targets? For each lift: current e1RM, target, weeks remaining, required weekly gain. Flag if off pace.
5. **Weak point deep dive**: Pick the #1 lagging area. Research solutions (volume, intensity, exercise swap). Propose specific changes with rationale.
6. **Plan adjustments**: What to change next week (if anything). Remember: don't change exercises mid-mesocycle unless necessary. Only adjust volume/intensity/weight.
7. **Previous review follow-up**: Did we execute on last week's recommendations? What worked, what didn't?

**Weekly review template:**

```markdown
# Week Review: YYYY-WXX (Mon DD – Sun DD)

## Sessions

- Planned: 3 (A/B/C) | Completed: X
- [list sessions with dates and day labels]

## e1RM Dashboard

| Lift | Last Week | This Week | Δ   | 12-Week Target | Weeks Left | Needed/Week | Status |
| ---- | --------- | --------- | --- | -------------- | ---------- | ----------- | ------ |

## Volume (hard sets/week)

| Muscle Group | Mon | Wed | Fri | Total | Target (10-20) | Status |
| ------------ | --- | --- | --- | ----- | -------------- | ------ |

## Highlights

- [what went well — be specific]

## Concerns

- [what needs attention — with data]

## Weak Point Deep Dive

- [#1 lagging area, analysis, proposed fix]

## Previous Review Follow-up

- [did we do what we said we'd do?]

## Decisions for Next Week

- [concrete changes, if any, with rationale]
```

## Goal Setting & Cascade

### Goal Setting Rules

- Goals set once at start of mesocycle (12 weeks). **NOT changed mid-cycle.**
- Goals are like KPIs — you strive for them, don't move goalposts.
- Weekly review can note "off track" but doesn't change the target.
- New goals only when starting a new mesocycle.
- If a goal is hit early, celebrate and maintain — don't immediately set a new one until next mesocycle.

### Goal Cascade: 12-Week → Weekly → Per-Session

1. **12-week goals** (`goals.json`): e1RM targets. Set at mesocycle start. Immutable during cycle.
2. **Weekly targets**: derived from goals. "To hit Bench 110 in 10 weeks, need ~+1.2 kg/week on e1RM." Reviewed in Saturday digest.
3. **Per-session targets**: specific weights/reps from plan.md, adjusted by previous session's `analysis.next_session_adjustments`.

### Continuity Protocol

- **Before each session**: read last session's `analysis` object (especially `next_session_adjustments` and `goal_progress`)
- **Before weekly review**: read last weekly review from `reviews/`
- **Cascade**: 12-week goals → weekly plan → per-session targets

### When to Adjust the Plan

**Keep the plan if:** progression is happening (even slowly), adherence is good, no pain.

**Adjust if:**

- Same e1RM for 3+ sessions on a lift → try: increase volume, change rep scheme, or swap variation
- Consistently missing reps on an exercise → weight too high, back off 5-10%
- User skipping an exercise repeatedly → swap for something they'll actually do
- Recovery issues (fatigue, sleep, stress) → reduce volume temporarily
- Ahead of schedule → don't change, just ride it

### Dashboard Lifts (Tracked on Charts)

Track these 4 lifts as primary indicators:

1. **Squat** — lower body compound, strongest lift, overall strength barometer
2. **Bench Press (flat)** — upper push, key weak point to monitor
3. **OHP** — shoulder strength, secondary weak point
4. **Seated Cable Row** — upper pull, balances the push lifts

**Why these 4:** Covers all 4 movement patterns (squat/push horizontal/push vertical/pull). Two are weak points (Bench, OHP) giving early warning on stalls. Squat and Row represent strengths — tracking ensures they don't regress while focusing on weaknesses.

## Ad-Hoc Analysis Process

When the user asks a specific training question (e.g., "should I track deadlift?", "is my bicep lagging?", "am I doing enough back work?"), follow this framework:

### 1. Hypothesis → Analysis → Pick Best

1. **State the question clearly** — what exactly are we trying to answer?
2. **Generate hypotheses** — list the plausible options
3. **Gather data** — pull from session history (e1RM, volume, progression trends), plan.md, goals.json, research
4. **Analyze each hypothesis** — pros/cons backed by numbers, not vibes
5. **Pick the best option** — commit to a clear recommendation with rationale
6. **Don't be wishy-washy** — the user wants a decision, not "it depends"

### 2. Always Use Data

- Compute e1RM (Epley) for every relevant exercise
- Compare strength ratios to standards (bench:squat 0.75, OHP:bench 0.60-0.65, row:bench 0.90-1.00)
- Sum hard sets per muscle group per week against MEV/MAV ranges
- Reference session history for trends

### 3. Always Anchor to Goals

Every analysis must connect back to the 12-week goals in `goals.json`. If a change doesn't serve a goal, question whether it matters.

### 4. Document Findings

- **Quick answers**: note in `memory/YYYY-MM-DD.md`
- **Deep analyses**: write to `health/gym/analysis-*.md`
- **Program changes**: update `plan.md` after user approves
- **Always commit** analysis files to git
