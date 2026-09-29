"""
A sheet's plan: how much work each task is, and which task builds on which.
Jev supplies the numbers (integrations.jev.plan_sheet, asked by
cli._plan_sheet); this module only turns them into something to show. The
same plan keeps each task's context selection - see cli._plan_sheet.

EFFORT is a score from 0 to 3 - the expected level on EFFORT_LEVELS, as Jev's
"score" questions answer - shown as 1 to 10 (effort_out_of_ten). DEPENDENCIES are "task b builds on task a" with a
probability; at or above DEPENDS_THRESHOLD it is an edge.

No order is suggested beyond the dependencies themselves: which task to start
with is the reader's call, and "the easiest first" is a guess about them.
Jev's edges can form a cycle (1 needs 2, 2 needs 1); then the least certain
edge of it is dropped.

Depends on nothing else in this project.
"""

# What the four levels of an effort score mean, in the order Jev is given them.
# Written for Jev (see integrations.jev.EFFORT_INSTRUCTIONS), shown short in the UI.
EFFORT_LEVELS = [
    ("routine", "Routine: a direct application of a definition or theorem, a few lines."),
    ("short", "Short: a standard argument or computation, up to half a page."),
    ("medium", "Medium: about a page, combining several results or a longer computation."),
    ("hard", "Hard: needs an idea of its own or a long argument, more than a page."),
]

DEPENDS_THRESHOLD = 0.5


def effort_word(score: float) -> str:
    return EFFORT_LEVELS[min(len(EFFORT_LEVELS) - 1, max(0, round(score)))][0]


def effort_out_of_ten(score: float) -> float:
    """The score on a scale from 1 (routine) to 10 (hard), one decimal.

    Jev's answer is already continuous - the expected level over the four,
    1.49 for a task between short and medium - and showing it as four bars
    rounded that away: 1.49 and 1.51 looked a level apart, 1.51 and 2.49 the
    same. Stretching it to ten is no more than a rescale; the decimals are
    Jev's, not invented."""
    top = len(EFFORT_LEVELS) - 1
    return round(1 + 9 * min(top, max(0.0, score)) / top, 1)


def edges_from(depends_p: dict[tuple[int, int], float],
               threshold: float = DEPENDS_THRESHOLD) -> list[tuple[int, int, float]]:
    """(a, b, p) for every "b builds on a" at or above the threshold, with
    cycles broken by dropping their least certain edge."""
    edges = sorted(((a, b, p) for (a, b), p in depends_p.items() if p >= threshold),
                   key=lambda e: -e[2])
    kept: list[tuple[int, int, float]] = []
    # Most certain first; an edge that would close a cycle is the least
    # certain one of that cycle, since everything already kept is surer.
    for a, b, p in edges:
        if not _reaches(kept, b, a):
            kept.append((a, b, p))
    return kept


def _reaches(edges: list[tuple[int, int, float]], start: int, goal: int) -> bool:
    todo, seen = [start], set()
    while todo:
        node = todo.pop()
        if node == goal:
            return True
        if node in seen:
            continue
        seen.add(node)
        todo += [b for a, b, _ in edges if a == node]
    return False


def dependency_text(edges: list[tuple[int, int, float]]) -> str:
    """"4 → 5, 1 → 3", or "no dependencies"."""
    if not edges:
        return "no dependencies"
    return ", ".join(f"{a} → {b}" for a, b, _ in sorted(edges))


def after(task: int, edges: list[tuple[int, int, float]]) -> list[int]:
    """The tasks `task` builds on."""
    return sorted(a for a, b, _ in edges if b == task)
