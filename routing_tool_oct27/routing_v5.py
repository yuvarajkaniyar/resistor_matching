"""
routing_v5.py  –  Matched-array router, rewritten as a four-stage pipeline.

Same input as routing_v3.router1(): `m`, `n` and the flat label list built by
python_array.createArray().  A label that repeats is one multi-link resistor;
each distinct label is one group, routed as a single series chain across the
whole array.  `router1` is exported as an alias, so existing callers and
writeplot.py work unchanged.

Pipeline
--------
    index_occurrences(arr)   -> every group's columns per row, in one pass
    lane_order(...)          -> lane index per (row, group)
    build_plan(...)          -> Plan: paths, vias, taps, terminals — pure data
    emit_*(plan)             -> Virtuoso, matplotlib preview, or path_callback

Only the emit_* functions touch a backend, so the plan can be built and
inspected without drawing anything; that is what makes the invariants below
testable.

How a group is routed
---------------------
Within a row, the group's columns are chained in series: link j joins column
j to column j+1, alternating between the row's bottom lane (ycoord1) and top
lane (ycoord2), so current enters one terminal of a segment and leaves by the
other.  That leaves exactly two *free* terminals per row — one at each end of
the chain — and those are the only places a tap or a terminal may attach.

Rows are walked as a serpentine: a group enters row 0 at its left end, leaves
at its right end, enters row 1 at its right end, and so on, so consecutive
rows hand off on the same side of the array.

A hand-off stays inside the array, to keep the X extent to the array itself:
the group's channel in the row it leaves is extended along its own y until it
reaches the x of the column it is landing on, and the climb happens there.
Channels are ordered so those extensions and climbs nest instead of crossing —
see lane_order(), which sorts them the way py_ops.sort_pairs does.  Only the
two chain terminals leave the array, as horizontal stubs, so the whole routing
costs 2 x MET2_SPACE of X beyond the columns themselves.

Fixed relative to routing_v3
----------------------------
1. v3's tap returned along the destination lane: the leg from the hand-off x
   back to the landing x ran at the landing lane's y, straight over that
   lane's own chain links and pads, shorting them together and bypassing the
   resistors.  v5 never routes along a lane it is landing on.
2. A tap attaches only to a free terminal, never to the node the chain
   already uses — v3 could land on the used node and bypass that segment.
3. Both chain terminals leave on their own lane height and stop at the
   boundary column; v3 sent every net to the same `_edge_target` x, so
   unrelated groups touched.
4. Both ends of a group's chain are brought out.  v3 brought out one end and
   left the other as a bare pad.
5. Taps link consecutive *occupied* rows; v3 looked only one row down, so a
   group that skipped a row was left unconnected.
"""

import os
from dataclasses import dataclass, field
from functools import cmp_to_key


# ======================================================================
# Geometry — every coordinate in one place
# ======================================================================
@dataclass(frozen=True)
class Geometry:
    m: int
    n: int
    height: float
    poly_width: float
    poly_space_x: float
    poly_space_y: float
    n_drc: float
    n_width: float
    n1_drc: float
    n1_width: float
    met2_space: float

    @property
    def pitch_x(self):
        return self.poly_width + self.poly_space_x

    @property
    def row_right(self):
        return (self.n - 1) * self.pitch_x + self.poly_width

    def col_x0(self, col):
        return col * self.pitch_x

    def col_x1(self, col):
        return col * self.pitch_x + self.poly_width

    def col_center(self, col):
        return col * self.pitch_x + self.poly_width / 2

    def row_base(self, row):
        return row * (self.height + self.poly_space_y)

    def row_top(self, row):
        return self.row_base(row) + self.height

    def lane(self, row, index):
        """Bottom (ycoord1) and top (ycoord2) lane of a group in a row."""
        offset = (index - 1) * self.n1_drc
        return {"low": self.row_base(row) + offset,
                "high": self.row_top(row) - offset}

    def inside(self, x):
        """True while x is still within the array's own columns."""
        return -self.met2_space < x < self.row_right + self.met2_space

    @property
    def wire_gap(self):
        """Edge-to-edge gap between parallel MET2, as the lane pitch sets it."""
        return max(0.0, self.n1_drc - self.n1_width)

    def edge_x(self, side, column):
        """X of a routing column beside the array. Column 0 holds terminals."""
        pitch = max(self.n_width, self.n1_width) + self.met2_space
        if side == "right":
            return self.row_right + self.met2_space + column * pitch
        return -self.met2_space - column * pitch


# ======================================================================
# Plan — what to draw, before anything is drawn
# ======================================================================
@dataclass(frozen=True)
class Path:
    layer: str
    width: float
    pts: tuple


@dataclass
class Tap:
    """A hand-off between a group's two consecutive occupied rows.

    Runs along `start`'s own channel to the landing column's x, then climbs
    there.  `reach` is how far the channel is extended and `climb` how far it
    rises — both are what the channel sort is trying to keep from crossing.
    """
    group: str
    row_from: int
    row_to: int
    start: tuple            # free terminal it leaves from, in the lower row
    end: tuple              # free terminal it lands on, in the upper row
    side: str = ""          # which side it hands off on
    climb_x: float = 0.0    # x it climbs at
    climb_layer: str = ""   # MET2 inside the array, MET1 beyond it
    tries: int = 0          # how far out it had to search

    @property
    def y_lo(self):
        return min(self.start[1], self.end[1])

    @property
    def y_hi(self):
        return max(self.start[1], self.end[1])

    @property
    def reach(self):
        return abs(self.end[0] - self.start[0])

    @property
    def climb(self):
        return abs(self.end[1] - self.start[1])


def rect_of(width, p0, p1):
    """The footprint of a two-point wire of the given width."""
    (x0, y0), (x1, y1) = p0, p1
    if x0 == x1:
        return (x0 - width / 2, min(y0, y1), x0 + width / 2, max(y0, y1))
    return (min(x0, x1), y0 - width / 2, max(x0, x1), y0 + width / 2)


def rects_overlap(a, b, eps=1e-9):
    """True when two footprints share area. Touching edges do not count."""
    return (a[0] < b[2] - eps and b[0] < a[2] - eps and
            a[1] < b[3] - eps and b[1] < a[3] - eps)


@dataclass
class Terminal:
    group: str
    row: int
    point: tuple
    side: str
    end: str                # "start" or "finish" of the group's chain


@dataclass
class Plan:
    paths: list = field(default_factory=list)
    vias: set = field(default_factory=set)
    taps: list = field(default_factory=list)
    terminals: list = field(default_factory=list)
    notes: list = field(default_factory=list)      # things to act on
    summary: str = ""                              # what the router did

    def wire(self, layer, width, p0, p1):
        if p0 != p1:
            self.paths.append(Path(layer, width, (tuple(p0), tuple(p1))))

    def via(self, x, y):
        self.vias.add((round(x, 4), round(y, 4)))

    def bbox(self):
        xs = [p[0] for path in self.paths for p in path.pts]
        ys = [p[1] for path in self.paths for p in path.pts]
        return min(xs), min(ys), max(xs), max(ys)


# ======================================================================
# Stage 1 — index the array once
# ======================================================================
def index_occurrences(arr):
    """One pass over `arr`.

    Returns (per_row, rows_of):
        per_row[row][group] -> ascending 0-based columns in that row
        rows_of[group]      -> ascending 0-based rows the group appears in
    """
    per_row = []
    rows_of = {}
    for row, labels in enumerate(arr):
        cols = {}
        for col, group in enumerate(labels):
            cols.setdefault(group, []).append(col)
        per_row.append(cols)
        for group in cols:
            rows_of.setdefault(group, []).append(row)
    return per_row, rows_of


# ======================================================================
# Stage 2 — lane order within each row
# ======================================================================
def chain_ends(cols, idx):
    """(entry column, exit column) for one row of a group's serpentine walk.

    Even rows of a group are walked left to right, odd rows right to left, so
    consecutive rows hand off on the same side of the array.
    """
    walk = cols if idx % 2 == 0 else cols[::-1]
    return walk[0], walk[-1]


def edge_target(x_ref, geo):
    """routing_v3._edge_target: the boundary a chain end reaches for, on
    whichever side of the row it already sits closest to."""
    return geo.edge_x("left" if x_ref < geo.row_right / 2 else "right", 0)


def lane_order(per_row, rows_of, geo):
    """Lane index (1 = nearest the row edge) per (row, group).

    This is routing_v3._sort_pos_map.  Each group contributes the pair

        (x it leaves this row at, x it lands on in the next row it occupies
         — the edge target when it hands off nowhere)

    which is _sort_pos_map's pair read against the serpentine walk: the walk
    reverses every row, so the hand-off leaves and lands on the same side,
    and the pair follows it.  Feeding the sort v3's literal "first column of
    the next row" instead describes a hand-off v5 does not make, and every
    climb then has to leave the array.

    and py_ops.sort_pairs orders them: a pair whose second element falls
    inside another's range goes first, ties by that element.  A group laned
    early sits nearest the row edge, where its hand-off spans only the row
    gap and blocks nobody, so the hand-offs nest instead of crossing.

    Groups are taken in first-column order, as getUniqueInRow gives them, so
    the sort breaks remaining ties the same way routing_v3 did.

    Ahead of the nesting rule sits one more test: a hand-off that lands on the
    next row's ycoord2 has to climb that whole row, so it gives up the outer
    channel to the hand-offs that only cross the row gap.
    """
    def compare(a, b):
        if a[2] != b[2]:            # a full-row climb gives up the outer lane
            return 1 if a[2] else -1
        (n1, n2), (m1, m2) = a[1], b[1]
        n_in_m = min(m1, m2) < n2 < max(m1, m2)
        m_in_n = min(n1, n2) < m2 < max(n1, n2)
        if n_in_m and not m_in_n:
            return -1
        if m_in_n and not n_in_m:
            return 1
        return (n2 > m2) - (n2 < m2)

    at = {(g, r): i for g, rows in rows_of.items() for i, r in enumerate(rows)}
    lanes = {}
    for row, cols in enumerate(per_row):
        spans = []
        for group, group_cols in cols.items():
            idx = at[(group, row)]
            x1 = geo.col_center(chain_ends(group_cols, idx)[1])
            rows = rows_of[group]
            if idx + 1 < len(rows):
                nxt = rows[idx + 1]
                landing = per_row[nxt][group]
                x2 = geo.col_center(chain_ends(landing, idx + 1)[0])
                # A chain leaves a row on ycoord2 always, but it lands on
                # ycoord1 only when the row it lands in holds an odd number of
                # its columns; an even count puts the landing on ycoord2 and
                # the climb has to cross that whole row.
                far = len(landing) % 2 == 0
            else:
                x2 = edge_target(x1, geo)
                far = False
            spans.append((group, (x1, x2), far))

        for index, (group, _, _) in enumerate(
                sorted(spans, key=cmp_to_key(compare)), 1):
            lanes[(row, group)] = index
    return lanes


@dataclass(frozen=True)
class RowEnds:
    """What one row of a group's chain offers to a hand-off."""
    entry: tuple
    exit: tuple
    exit_side: str
    entry_pad: tuple
    exit_pad: tuple


def plan_row(plan, geo, row, cols, lane_index, idx, MET2, n1_width):
    """Chain one group's columns in one row.

    Walks from the entry end to the exit end so consecutive rows hand off on
    the same side.  Link i of the walk runs along the top lane when i is even,
    so the entry end's free terminal is always its bottom one.

    Returns a RowEnds: the two free terminals, the side the exit sits on,
    and the two pad footprints — a hand-off is allowed to touch those and
    nothing else.
    """
    lane = geo.lane(row, lane_index)
    walk = cols if idx % 2 == 0 else cols[::-1]
    exit_side = "right" if idx % 2 == 0 else "left"
    steps = len(walk) - 1

    # Phase is set so the exit end's free terminal is the top lane, which
    # keeps every hand-off climbing from the top of one row.
    phase = steps % 2

    def on_top(i):
        return (i + phase) % 2 == 0

    for i in range(steps):
        y = lane["high"] if on_top(i) else lane["low"]
        a, b = sorted((walk[i], walk[i + 1]))
        plan.wire(MET2, n1_width, (geo.col_x0(a), y), (geo.col_x1(b), y))
        plan.via(geo.col_center(a), y)
        plan.via(geo.col_center(b), y)

    # The free terminal at each end of the walk: the lane the chain left
    # unused there.  Attaching anywhere else bypasses that resistor.
    if steps == 0:
        entry_y, exit_y = lane["low"], lane["high"]
    else:
        entry_y = lane["low"] if on_top(0) else lane["high"]
        exit_y = lane["low"] if on_top(steps - 1) else lane["high"]

    pads = {}
    for which, col, y in (("entry", walk[0], entry_y), ("exit", walk[-1], exit_y)):
        p0, p1 = (geo.col_x0(col), y), (geo.col_x1(col), y)
        plan.wire(MET2, n1_width, p0, p1)
        plan.via(geo.col_center(col), y)
        pads[which] = rect_of(n1_width, p0, p1)

    return RowEnds(entry=(geo.col_center(walk[0]), entry_y),
                   exit=(geo.col_center(walk[-1]), exit_y),
                   exit_side=exit_side,
                   entry_pad=pads["entry"], exit_pad=pads["exit"])


def build_plan(arr, geo, MET1, n_width, MET2, n1_width):
    """Turn the label array into a Plan. Draws nothing."""
    plan = Plan()
    per_row, rows_of = index_occurrences(arr)
    lanes = lane_order(per_row, rows_of, geo)

    deepest = max(lanes.values())
    if (deepest - 1) * geo.n1_drc > geo.height / 2 - geo.n_drc:
        plan.notes.append(
            f"{deepest} lanes per row at n1_drc={geo.n1_drc} reach the segment "
            f"mid-gap (height={geo.height}); raise height or lower n1_drc")

    # ---- the resistor segments themselves -----------------------------
    for col in range(geo.n):
        x = geo.col_center(col)
        for row in range(geo.m):
            base, top = geo.row_base(row), geo.row_top(row)
            mid = base + geo.height / 2
            plan.wire(MET1, n_width, (x, base), (x, mid - geo.n_drc / 2))
            plan.wire(MET1, n_width, (x, top), (x, mid + geo.n_drc / 2))

    # ---- each group's chain, row by row, as a serpentine --------------
    ends = {}
    for group, rows in rows_of.items():
        for idx, row in enumerate(rows):
            ends[(group, row)] = plan_row(
                plan, geo, row, per_row[row][group], lanes[(row, group)],
                idx=idx,
                MET2=MET2, n1_width=n1_width)

    # ---- both ends of every chain out to the boundary -----------------
    # Drawn before the hand-offs so a hand-off is tested against them too.
    for group, rows in rows_of.items():
        first, last = ends[(group, rows[0])], ends[(group, rows[-1])]
        for point, side, which, row in ((first.entry, "left", "start", rows[0]),
                                        (last.exit, last.exit_side, "finish",
                                         rows[-1])):
            plan.wire(MET2, n1_width, point, (geo.edge_x(side, 0), point[1]))
            plan.terminals.append(Terminal(group, row, point, side, which))

    # ---- hand-offs between consecutive occupied rows ------------------
    for group, rows in rows_of.items():
        for idx in range(len(rows) - 1):
            row, nxt = rows[idx], rows[idx + 1]
            plan.taps.append(Tap(group, row, nxt,
                                 ends[(group, row)].exit,
                                 ends[(group, nxt)].entry,
                                 side=ends[(group, row)].exit_side))

    route_taps(plan, geo, ends, lanes, MET2, n1_width, MET1, n_width)

    if plan.taps:
        at_column = sum(1 for t in plan.taps if t.tries <= 2)
        inside = sum(1 for t in plan.taps
                     if t.climb_x < geo.row_right + geo.met2_space)
        beyond = max((t.climb_x for t in plan.taps), default=0) - geo.row_right
        plan.summary = (
            f"{len(plan.taps)} hand-offs: {at_column} climb at their own "
            f"column, {inside} stay within the array, "
            f"{max(beyond, 0):.2f} um of X beyond the last column")
    return plan


def climb_candidates(tap, geo, count, outside_only=False):
    """Climb positions for one hand-off, nearest its pads first.

    The landing column and the column it leaves from come first — the "as
    usual" taps, which cost nothing — then positions between the two pads,
    then steps outward on either side at the minimum MET2 pitch.  Ordering by
    distance to the nearer pad keeps the legs short and the array narrow:
    a climb only moves out as far as it must.

    `outside_only` drops the in-array positions, for a hand-off that was found
    to be in another one's way.
    """
    step = geo.n1_width + geo.wire_gap
    sx, ex = tap.start[0], tap.end[0]
    lo, hi = min(sx, ex), max(sx, ex)

    xs = [ex, sx]
    span = int((hi - lo) / step)
    xs += [lo + i * step for i in range(1, span + 1)]       # between the pads
    for i in range(1, count + 1):                           # outward, both ways
        xs += [hi + i * step, lo - i * step]

    seen, ordered = set(), []
    for x in sorted(xs, key=lambda x: (min(abs(x - sx), abs(x - ex)), abs(x))):
        key = round(x, 6)
        if key in seen:
            continue
        seen.add(key)
        if outside_only and geo.inside(x):
            continue
        ordered.append(x)
    return ordered


def route_taps(plan, geo, ends, lanes, MET2, n1_width, MET1, n_width):
    """Route every hand-off at the innermost x that is provably free.

    Hand-offs are taken in channel order — the order py_ops.sort_pairs put
    them in — and each takes the first candidate climb that clears every wire
    already placed by the lane gap.  A climb inside the array stays on MET2;
    past the last column it moves to MET1, where no lane can reach it.
    Nothing is reserved in advance, so X grows only as far as the outermost
    climb actually needed.

    A hand-off that skips a row has to cross that row on the way back in, and
    an in-array climb placed earlier can sit in its path.  When a hand-off
    cannot be placed at all, whichever in-array climbs blocked it are pushed
    out of the array and the whole set is routed again.  Each pass pushes out
    at least one, so it settles.
    """
    static = {}
    for path in plan.paths:
        static.setdefault(path.layer, []).append(
            (rect_of(path.width, *path.pts), None))

    order = sorted(plan.taps,
                   key=lambda t: (lanes[(t.row_from, t.group)], t.row_from,
                                  t.group))
    budget = 8 + 4 * len(plan.taps)
    gap = geo.wire_gap

    def shape_of(tap, x):
        """The wires a climb at x needs, as (layer, width, leg) triples."""
        sx, sy = tap.start
        ex, ey = tap.end
        inside = geo.inside(x)
        legs = [(MET2, n1_width, ((sx, sy), (x, sy))),
                (MET2 if inside else MET1, n1_width if inside else n_width,
                 ((x, sy), (x, ey))),
                (MET2, n1_width, ((x, ey), (ex, ey)))]
        return [l for l in legs if l[2][0] != l[2][1]], inside

    def attempt(banned):
        occupied = {k: list(v) for k, v in static.items()}
        occupied.setdefault(MET1, [])
        occupied.setdefault(MET2, [])
        chosen, failed, blockers = {}, [], set()

        for tap in order:
            allowed = (ends[(tap.group, tap.row_from)].exit_pad,
                       ends[(tap.group, tap.row_to)].entry_pad)
            picked = None
            for tries, x in enumerate(
                    climb_candidates(tap, geo, budget, tap.group in banned
                                     and (tap.row_from, tap.row_to) in
                                     banned[tap.group]), 1):
                wires, inside = shape_of(tap, x)
                clash = []
                for layer, width, leg in wires:
                    r = rect_of(width, *leg)
                    probe = (r[0] - gap, r[1] - gap, r[2] + gap, r[3] + gap)
                    clash += [owner for other, owner in occupied[layer]
                              if rects_overlap(probe, other)
                              and other not in allowed]
                if clash:
                    blockers |= {o for o in clash if o is not None}
                    continue
                picked = (x, wires, inside, tries)
                break

            if picked is None:
                failed.append(tap)
                continue
            x, wires, inside, tries = picked
            chosen[id(tap)] = picked
            for layer, width, leg in wires:
                key = (tap.group, tap.row_from, tap.row_to) if inside else None
                occupied[layer].append((rect_of(width, *leg), key))
        return chosen, failed, blockers

    banned = {}
    while True:
        chosen, failed, blockers = attempt(banned)
        if not failed:
            break
        pushed = False
        for group, row_from, row_to in blockers:
            rows = banned.setdefault(group, set())
            if (row_from, row_to) not in rows:
                rows.add((row_from, row_to))
                pushed = True
        if not pushed:
            for tap in failed:
                plan.notes.append(
                    f"hand-off {tap.group} rows {tap.row_from}->{tap.row_to} "
                    f"has no clear climb; it is left unrouted")
            break

    for tap in order:
        if id(tap) not in chosen:
            continue
        x, wires, inside, tries = chosen[id(tap)]
        tap.climb_x, tap.tries = x, tries
        tap.climb_layer = MET2 if inside else MET1
        for layer, width, leg in wires:
            plan.wire(layer, width, *leg)
        if not inside:                          # the layer change needs vias
            plan.via(x, tap.start[1])
            plan.via(x, tap.end[1])


# ======================================================================
# Stage 4 — emit
# ======================================================================
def connect_virtuoso():
    """(ws, True) when Virtuoso is reachable, else (None, False)."""
    try:
        from skillbridge import Workspace
        with open("/tmp/virtuoso_pid.txt") as f:
            ws = Workspace.open(int(f.read().strip()))
        print("Connected to Virtuoso workspace.")
        return ws, True
    except Exception as e:
        print(f"Virtuoso not available ({e}). Running in matplotlib "
              f"preview mode.")
        return None, False


def emit_virtuoso(plan, ws, cv, via_name, place_vias):
    for path in plan.paths:
        ws.rod.create_path(cv_id=cv, layer=path.layer, width=path.width,
                           pts=[list(p) for p in path.pts])
    if place_vias:
        tech = ws.tech.get_tech_file(cv)
        via_def = ws.tech.find_via_def_by_name(tech, via_name)
        if via_def is None:
            raise ValueError(f"Via definition '{via_name}' not found")
        for x, y in sorted(plan.vias):
            ws.db.create_via(cv, via_def, [x, y], "R0")
        print(f"Dropped {len(plan.vias)} vias")
    ws.hi.redraw()
    print(f"Drew {len(plan.paths)} paths in Virtuoso")


def emit_preview(plan, geo, title, out_png="routing_v5.png"):
    """Render the plan — no Virtuoso calls made."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    palette = ["#4da6ff", "#ff4d4d", "#9b6bd6", "#5ad48a"]
    colors = {}
    fig, ax = plt.subplots(figsize=(14, 10))
    fig.patch.set_facecolor("#12121f")
    ax.set_facecolor("#12121f")

    for path in plan.paths:
        (x0, y0), (x1, y1) = path.pts
        w = path.width
        if x0 == x1:
            rect = ((x0 - w / 2, min(y0, y1)), w, abs(y1 - y0))
        else:
            rect = ((min(x0, x1), y0 - w / 2), abs(x1 - x0), w)
        color = colors.setdefault(path.layer, palette[len(colors) % len(palette)])
        ax.add_patch(patches.Rectangle(*rect, linewidth=0.3,
                                       edgecolor="#000000", facecolor=color,
                                       alpha=0.75, zorder=3))

    via_size = min(p.width for p in plan.paths) * 0.8
    for x, y in plan.vias:
        ax.add_patch(patches.Rectangle((x - via_size / 2, y - via_size / 2),
                                       via_size, via_size, linewidth=0.3,
                                       edgecolor="#000000", facecolor="#ffd24d",
                                       alpha=0.95, zorder=4))
    for t in plan.terminals:
        x = geo.edge_x(t.side, 0)
        ax.plot([x], [t.point[1]], marker="o", markersize=4, color="#7CFC9A",
                zorder=5)
        ax.annotate(t.group, (x, t.point[1]), color="#7CFC9A", fontsize=7,
                    zorder=5, xytext=(6 if t.side == "right" else -12, -3),
                    textcoords="offset points")

    handles = [patches.Patch(facecolor=c, alpha=0.75, label=l)
               for l, c in colors.items()]
    handles += [patches.Patch(facecolor="#ffd24d", alpha=0.95, label="via"),
                patches.Patch(facecolor="#7CFC9A", label="terminal")]
    ax.legend(handles=handles, loc="upper right", fontsize=9,
              facecolor="#1e1e3a", edgecolor="#666688", labelcolor="white")

    x0, y0, x1, y1 = plan.bbox()
    pad = 0.04 * max(x1 - x0, y1 - y0)
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title, color="white", fontsize=13, pad=12)
    ax.set_xlabel("X (um)", color="#aaaacc")
    ax.set_ylabel("Y (um)", color="#aaaacc")
    ax.tick_params(colors="#aaaacc")
    for sp in ax.spines.values():
        sp.set_edgecolor("#444466")
    ax.grid(True, color="#222240", linewidth=0.5, linestyle="--", zorder=0)
    plt.tight_layout()

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), out_png)
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Preview saved -> {out}")
    plt.show()
    return out


# ======================================================================
# Entry point — same signature as routing_v3.router1()
# ======================================================================
def router5(cv, m, n, MET1, POLY_SPACE_X, POLY_SPACE_Y, height, n_width, n_drc,
            POLY_WIDTH, arr, n1_drc, n1_width, MET2, VIA_NAME="M1_M2",
            path_callback=None, MET2_SPACE=None, place_vias=True, ws=None,
            preview=False):
    """Route `arr` and emit it. Returns the Plan.

    Draws in Virtuoso when it is reachable and a cellview is given, and
    falls back to the matplotlib preview when it is not.  `preview=True`
    also renders the preview alongside a Virtuoso draw."""
    geo = Geometry(m=m, n=n, height=height, poly_width=POLY_WIDTH,
                   poly_space_x=POLY_SPACE_X, poly_space_y=POLY_SPACE_Y,
                   n_drc=n_drc, n_width=n_width, n1_drc=n1_drc,
                   n1_width=n1_width,
                   met2_space=n1_drc if MET2_SPACE is None else MET2_SPACE)

    plan = build_plan(arr, geo, MET1, n_width, MET2, n1_width)
    if plan.summary:
        print(plan.summary)
    for note in plan.notes:
        print(f"warning: {note}")

    if path_callback is not None:
        for path in plan.paths:
            path_callback(path.layer, path.width, [list(p) for p in path.pts])
        return plan

    if ws is None and cv is not None:
        ws, live = connect_virtuoso()
    else:
        live = ws is not None

    title = (f"router5  {m}x{n} array  –  {len(plan.taps)} taps, "
             f"{len(plan.terminals)} terminals")

    if live and cv is not None:
        emit_virtuoso(plan, ws, cv, VIA_NAME, place_vias)
        if preview:
            emit_preview(plan, geo, title)
    else:
        if cv is None and ws is not None:
            print("Virtuoso is up but no cellview was given. Running in "
                  "matplotlib preview mode.")
        emit_preview(plan, geo, title)
    return plan


router1 = router5       # drop-in for `from routing_v5 import router1`


# ======================================================================
# Standalone demo
# ======================================================================
if __name__ == "__main__":
    from python_array import createArray

    arr = createArray(2, 50, ["A", "B", "C", "B"] * 25)
    router5(None, 2, 50, "MET1", 0.5, 1, 10, 0.5, 0.3, 0.5, arr, 0.5, 0.3,
            "MET2")
