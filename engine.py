"""
Career matching engine.

Input:  a dict of form answers (see sample_answers.json for the exact shape —
        it mirrors the 15 questions in next-move-career-flow.html)
Output: a context dict ready to feed straight into report_template.html.j2
"""

from careers import DIMENSIONS, SKILL_KEYWORDS, DIMENSION_BLURB, DIMENSION_PHRASE, CAREERS


def score_text(text, dims):
    """Bump dimension scores based on keyword hits in free-text answers."""
    t = (text or "").lower()
    for dim, kws in SKILL_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                dims[dim] = min(10, dims.get(dim, 5) + 2.2)


def compute_profile(answers, text_scores=None):
    """Turn form answers into (v, w, priority_scores).

    text_scores: optional {dimension: 1-10} already derived from the
    free-text answers (e.g. via llm_interpreter.get_text_scores). When
    provided, it replaces the keyword scorer for the text-derived
    dimensions. When None, falls back to the keyword scan below.
    """
    v = {d: 5 for d in DIMENSIONS}
    w = {d: 0.35 for d in DIMENSIONS}

    if text_scores:
        for d in DIMENSIONS:
            val = text_scores.get(d, 5)
            v[d] = val
            if val != 5:
                w[d] = 1
    else:
        score_text(answers.get("goodAt", ""), v)
        score_text(answers.get("compliments", ""), v)
        dislike_text = (answers.get("dislike", "") or "").lower()
        for dim, kws in SKILL_KEYWORDS.items():
            for kw in kws:
                if kw in dislike_text:
                    v[dim] = max(1, v.get(dim, 5) - 3)
        for d in DIMENSIONS:
            if v[d] != 5:
                w[d] = 1

    style = answers.get("teamstyle")
    v["Independence"] = {"Independent": 9, "Small": 6, "Large": 3}.get(style, 5)
    w["Independence"] = 1 if style else 0.35

    env = answers.get("environment")
    v["Flexibility"] = {"Remote": 8, "Hybrid": 6, "Office": 4}.get(env, 5)
    w["Flexibility"] = 0.8 if env else 0.35

    income_sel = answers.get("income", "")
    if income_sel.startswith("High"):
        v["Income"] = 9
    elif income_sel.startswith("Moderate"):
        v["Income"] = 6
    else:
        v["Income"] = 4
    w["Income"] = 1

    priority_map = {"Money": "Income", "Freedom": "Flexibility", "Stability": "Stability",
                     "Creativity": "Creativity", "Meaning": "Empathy", "Growth": "Analytical"}
    priority_scores = {k: 4 for k in priority_map}
    priorities = answers.get("priorities", [])
    for p in priorities:
        if p in priority_scores:
            priority_scores[p] = 9
            dim = priority_map[p]
            v[dim] = max(v.get(dim, 5), 8)
            w[dim] = 1
    if not priorities:
        v["Stability"] = max(v.get("Stability", 5), 6)

    for d in DIMENSIONS:
        v[d] = max(1, min(10, round(v[d])))

    return v, w, priority_scores


def score_careers(v, w):
    scored = []
    for c in CAREERS:
        diff, wsum = 0.0, 0.0
        for d in DIMENSIONS:
            diff += w[d] * abs(v[d] - c["v"][d])
            wsum += w[d] * 9
        score = max(35, round(100 * (1 - diff / wsum)))
        scored.append({**c, "score": score})
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored


def _challenge_text(answers):
    changing = answers.get("changing")
    return {
        "Yes": "Ready to make a change, but unsure which direction fits best.",
        "Maybe": "Exploring whether a change makes sense, without a clear direction yet.",
        "No": "Looking to grow within the current path rather than switch entirely.",
    }.get(changing, "Weighing a few different directions at once.")


def _top_priority_text(priorities):
    if not priorities:
        return "A stable, well-rounded fit over any single factor"
    return priorities[0]


def build_context(answers, text_scores=None):
    v, w, priority_scores = compute_profile(answers, text_scores=text_scores)
    scored = score_careers(v, w)
    top3 = scored[:3]

    # ---- strengths (top 5 dimensions) ----
    top_dims = sorted(v.items(), key=lambda kv: kv[1], reverse=True)[:5]
    strengths = [{"name": d, "value": val * 10, "blurb": DIMENSION_BLURB[d]} for d, val in top_dims]

    # ---- work style spectrum (page 5) ----
    style = answers.get("teamstyle")
    indep_pos = {"Independent": 82, "Small": 55, "Large": 22}.get(style, 50)
    env = answers.get("environment")
    flex_pos = {"Remote": 78, "Hybrid": 52, "Office": 25}.get(env, 50)
    generalist_pos = 62 if "Growth" in answers.get("priorities", []) else 35

    # ---- career values (page 6) — relabel priority_scores for display ----
    values_display = [
        ("Creativity", priority_scores["Creativity"]),
        ("Growth", priority_scores["Growth"]),
        ("Freedom", priority_scores["Freedom"]),
        ("Income", priority_scores["Money"]),
        ("Stability", priority_scores["Stability"]),
        ("Impact", priority_scores["Meaning"]),
    ]
    values_display.sort(key=lambda kv: kv[1], reverse=True)
    career_values = [{"name": n, "value": val} for n, val in values_display]

    # ---- top matches (page 7) + deep dives (pages 8-10) ----
    matches = []
    for c in top3:
        shared = [d for d, _ in top_dims if c["v"][d] >= 7][:2]
        if not shared:
            shared = [top_dims[0][0]]
        why_short = f"Strong overlap between your {' and '.join(p.lower() for p in [DIMENSION_PHRASE[d] for d in shared])} and what this role draws on day to day."
        why_long = (
            f"{c['name']} rewards {', '.join(DIMENSION_PHRASE[d] for d in shared)}, "
            f"which lines up with how you described your strengths. "
            f"It also fits your preference for "
            f"{'independent, focused work' if style == 'Independent' else 'collaborative, team-based work' if style in ('Small','Large') else 'a flexible working style'}."
        )
        already_have = [DIMENSION_PHRASE[d].capitalize() for d, _ in top_dims[:3]]
        matches.append({
            "name": c["name"], "score": c["score"],
            "why_short": why_short, "why_long": why_long,
            "uses": c["uses"], "challenges": c["challenges"],
            "build_next": c["build_next"], "already_have": already_have,
        })

    # ---- skills gap (page 11) ----
    already_have_names = [DIMENSION_PHRASE[d].capitalize() for d, _ in top_dims[:4]]
    build_next = top3[0]["build_next"]

    # ---- executive summary / callout (pages 2, 14) ----
    occupation = answers.get("occupation") or "your current role"
    industry = answers.get("industry")
    experience = answers.get("experience", "")
    current_situation = f"{occupation}" + (f", {industry.lower()}" if industry else "") + (f" ({experience})" if experience else "")
    top_phrase_pair = ' and '.join(DIMENSION_PHRASE[d] for d, _ in top_dims[:2])
    next_move_text = (
        f"Your profile points toward roles that combine {top_phrase_pair} — "
        f"{top3[0]['name']} is your strongest direction, with {top3[1]['name']} close behind."
    )

    # ---- roadmap / actions (pages 12-13), personalized with top career name ----
    top_name = top3[0]["name"]
    roadmap = [
        {"days": "DAYS 1–30", "title": "Explore", "tasks": [
            f"Complete one short {top_name.split('/')[0].strip()} fundamentals course",
            f"Talk to two people currently working as a {top_name.split('/')[0].strip()}",
            "Audit things you already do that resemble this work",
        ]},
        {"days": "DAYS 31–60", "title": "Build", "tasks": [
            "Start your first portfolio / proof-of-work project",
            f"Pick up {build_next[0].lower()}",
            "Get feedback from one person already in the field",
        ]},
        {"days": "DAYS 61–90", "title": "Launch", "tasks": [
            "Publish a small portfolio or work sample",
            "Update LinkedIn and resume around this direction",
            "Apply to 10 relevant roles or opportunities",
        ]},
    ]
    first_actions = [
        "Choose your primary direction",
        f"Research 10 real {top_name.split('/')[0].strip()} roles",
        "Identify the recurring required skills",
        "Pick one structured learning path",
        "Build your first portfolio project",
        "Update your resume around transferable strengths",
        "Update your LinkedIn headline and summary",
        "Start networking with 5 people in the field",
        "Apply strategically, not broadly",
        "Review progress at the 90-day mark",
    ]

    return {
        "person_name": answers.get("name", "you"),
        "current_situation": current_situation,
        "career_goal": answers.get("idealCareer") or "Not specified",
        "primary_challenge": _challenge_text(answers),
        "top_priority": _top_priority_text(answers.get("priorities", [])),
        "next_move_text": next_move_text,
        "strengths": strengths,
        "indep_pos": indep_pos, "flex_pos": flex_pos, "generalist_pos": generalist_pos,
        "career_values": career_values,
        "matches": matches,
        "already_have": already_have_names,
        "build_next": build_next,
        "roadmap": roadmap,
        "first_actions": first_actions,
        "final_best": top3[0]["name"],
        "final_second": top3[1]["name"],
        "final_wildcard": top3[2]["name"],
    }
