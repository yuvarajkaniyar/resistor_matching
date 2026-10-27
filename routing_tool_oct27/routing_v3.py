from functools import cmp_to_key
from skillbridge import Workspace
import python_array
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Try to connect to Virtuoso; fall back to matplotlib mode if not available
try:
    with open("/tmp/virtuoso_pid.txt") as _f:
        _pid = int(_f.read().strip())
    ws = Workspace.open(_pid)
    VIRTUOSO_MODE = True
    print("Connected to Virtuoso workspace.")
except Exception as e:
    ws = None
    VIRTUOSO_MODE = False
    print(f"Virtuoso not available ({e}). Running in matplotlib preview mode.")


# ======================================================================
# Helpers
# ======================================================================
def _edge_target(x_ref, n, x_leftmost, poly_width, space):
    row_right = (n - 1) * x_leftmost + poly_width
    if x_ref < row_right / 2:
        return -space
    return row_right + space


def _sort_pos_map(arr, row, n, x_leftmost, POLY_MID, met2_space=0):
    poly_width = 2 * POLY_MID

    def compare(a, b):
        _, (n1, n2) = a
        _, (m1, m2) = b
        n_in_m = min(m1, m2) < n2 < max(m1, m2)
        m_in_n = min(n1, n2) < m2 < max(n1, n2)
        if n_in_m and not m_in_n:
            return -1
        elif m_in_n and not n_in_m:
            return 1
        else:
            return (n2 > m2) - (n2 < m2)

    items = []
    for res in python_array.getUniqueInRow(arr, row):
        last_cur = python_array.edge_element_column(arr, res, row, from_right=True) - 1
        x1 = last_cur * x_leftmost + POLY_MID

        first_next = python_array.edge_element_column(arr, res, row + 1, from_right=False)
        if first_next:
            x2 = (first_next - 1) * x_leftmost + POLY_MID
        else:
            x2 = _edge_target(x1, n, x_leftmost, poly_width, met2_space)

        items.append((res, [x1, x2]))

    sorted_items = sorted(items, key=cmp_to_key(compare))
    pos_map   = {res: idx + 1 for idx, (res, _) in enumerate(sorted_items)}
    pairs_map = {res: (x1, x2) for res, (x1, x2) in items}
    return pos_map, pairs_map


def connect_links(connections, layer, width, draw_fn):
    """
    Draw one wire per entry of `connections`.

    The hand-off leaves row r on its top lane (ycoord2) and lands on row r+1's
    bottom lane (ycoord1), so the normal route is a short hop across the gap:
        start --vertical--> (sx, ey) --horizontal--> end

    When the in-row chain parity forced the hand-off onto the bottom lane,
    draw_horizontal() supplies `edge_x` and the route detours beside the array
    instead of cutting up through the row:
        start --horizontal--> (edge_x, sy) --vertical--> (edge_x, ey)
              --horizontal--> end

    Returns a list of {"res", "pts"} for the routes drawn.
    """
    routed = []

    for c in connections:
        sx, sy = c["start"]
        ex, ey = c["end"]
        edge_x = c.get("edge_x")

        if edge_x is None:
            pts = [(sx, sy)]
            if sy != ey:                               # vertical leg
                draw_fn(layer, width, [[sx, sy], [sx, ey]])
            if sx != ex:                               # horizontal leg
                draw_fn(layer, width, [[sx, ey], [ex, ey]])
                pts.append((sx, ey))
            pts.append((ex, ey))
        else:
            pts = [(sx, sy)]
            if sx != edge_x:                           # out to the edge
                draw_fn(layer, width, [[sx, sy], [edge_x, sy]])
                pts.append((edge_x, sy))
            if sy != ey:                               # up beside the array
                draw_fn(layer, width, [[edge_x, sy], [edge_x, ey]])
                pts.append((edge_x, ey))
            if edge_x != ex:                           # back in to the landing
                draw_fn(layer, width, [[edge_x, ey], [ex, ey]])
            pts.append((ex, ey))

        routed.append({"res": c["res"], "pts": pts})

    return routed


# ======================================================================
# Router
# ======================================================================
def router1(cv, m, n, MET1, POLY_SPACE_X, POLY_SPACE_Y, height, n_width, n_drc,
            POLY_WIDTH, arr, n1_drc, n1_width, MET2, VIA_NAME="M1_M2",
            path_callback=None, MET2_SPACE=None):

    if MET2_SPACE is None:
        MET2_SPACE = n1_drc

    y = height
    POLY_MID = POLY_WIDTH / 2
    x_leftmost = POLY_WIDTH + POLY_SPACE_X

    via_pts = set()
    mpl_paths = []
    connections = []       # row-to-row links, filled by draw_horizontal()

    def col_center(col):
        return POLY_MID + col * x_leftmost

    def add_via(col, y_coord):
        via_pts.add((round(col_center(col), 4), round(y_coord, 4)))

    # ------------------------------------------------------------------
    def draw_path(layer, width, pts):
        if path_callback is not None:
            path_callback(layer, width, pts)
        elif VIRTUOSO_MODE:
            ws.rod.create_path(cv_id=cv, layer=layer, width=width, pts=pts)
        else:
            mpl_paths.append({"layer": layer, "width": width, "pts": pts})

    # ------------------------------------------------------------------
    def draw_vertical():
        for col in range(n):
            xCoord = col_center(col)
            for row in range(m):
                yBase = row * (y + POLY_SPACE_Y)
                yMid = yBase + (y / 2)
                yTop = yBase + y

                draw_path(MET1, n_width,
                          [[xCoord, yBase], [xCoord, yMid - (n_drc / 2)]])
                draw_path(MET1, n_width,
                          [[xCoord, yTop], [xCoord, yMid + (n_drc / 2)]])

    # ------------------------------------------------------------------
    def hpath(x_start, x_end, y_coord, start_col=None, end_col=None):
        draw_path(MET2, n1_width, [[x_start, y_coord], [x_end, y_coord]])
        if start_col is not None:
            add_via(start_col, y_coord)
        if end_col is not None:
            add_via(end_col, y_coord)

    # ------------------------------------------------------------------
    def occurrence_cols(row_no, res):
        cols = []
        c = python_array.getFirstPosInRow(arr, row_no, res)
        while c:
            cols.append(c - 1)
            c = python_array.getnextPos_in_row(arr, row_no, res, c)
        return cols

    def has_match_below(row_no, res):
        return python_array.edge_element_column(arr, res, row_no + 1,
                                                from_right=False) != 0

    # ------------------------------------------------------------------
    def chain_phase(n_cols, recv, hand, row):
        """Rail phase for one resistor's in-row series chain.

        rail(j) is the top lane when (j + phase) is even.  The phase is picked
        so the row-to-row hand-off leaves on the top lane (ycoord2) and the
        link arriving from the row below lands on the bottom lane (ycoord1).
        Both fit only when the occurrence count is odd; otherwise the landing
        wins and the hand-off is routed around the array edge instead of
        cutting across the row.
        """
        last = n_cols - 1
        if recv:
            return 0                       # rail(0) = top  -> landing on bottom
        if hand and last > 0:
            return last % 2                # rail(last-1) = bottom -> hand-off on top
        return row % 2                     # no links: legacy alternation

    # ------------------------------------------------------------------
    def draw_horizontal():
        pending = {}

        for row in range(m):
            row_no = row + 1
            yBase  = row * (height + POLY_SPACE_Y)
            yTop   = yBase + height
            pos_map, _ = _sort_pos_map(arr, row_no, n, x_leftmost, POLY_MID, MET2_SPACE)

            incoming = pending
            pending = {}

            for res in python_array.getUniqueInRow(arr, row_no):
                offset = (pos_map[res] - 1) * n1_drc
                lane = {"low": yBase + offset, "high": yTop - offset}
                cols = occurrence_cols(row_no, res)
                last = len(cols) - 1

                recv = res in incoming
                hand = has_match_below(row_no, res)

                phase   = chain_phase(len(cols), recv, hand, row)
                is_high = lambda j: (j + phase) % 2 == 0
                rail    = lambda j: lane["high"] if is_high(j) else lane["low"]

                # Free terminal of the first/last column: the one the chain
                # does not use.  A lone column has both terminals free.
                landing_high = False if last == 0 else not is_high(0)
                handoff_high = True  if last == 0 else not is_high(last - 1)
                landing_y = lane["high"] if landing_high else lane["low"]
                handoff_y = lane["high"] if handoff_high else lane["low"]

                # ---- in-row series chain: col[j] -> col[j+1] --------------
                for j in range(last):
                    hpath(cols[j] * x_leftmost,
                          cols[j + 1] * x_leftmost + POLY_WIDTH,
                          rail(j), cols[j], cols[j + 1])

                # ---- landing pad for the link coming up from the row below
                if recv:
                    x_land = cols[0] * x_leftmost
                    hpath(x_land, x_land + POLY_WIDTH, landing_y, cols[0], None)
                    from_row, start_pt, edge_x = incoming.pop(res)
                    connections.append({
                        "res": res,
                        "row_from": from_row,
                        "row_to": row_no,
                        "start": start_pt,
                        "end": (x_land, landing_y),
                        "edge_x": edge_x,
                    })

                # ---- hand-off pad, or the net's terminal out to the edge --
                x_last = cols[last] * x_leftmost
                if hand:
                    hpath(x_last, x_last + POLY_WIDTH, handoff_y, cols[last], None)
                    # Parity put the hand-off on the bottom lane: going
                    # straight up would cross the whole row, so route around
                    # the nearest edge, in its own column beside the array.
                    edge_x = None if handoff_high else _edge_target(
                        col_center(cols[last]), n, x_leftmost, POLY_WIDTH,
                        MET2_SPACE + offset)
                    pending[res] = (row_no, (x_last + POLY_WIDTH, handoff_y),
                                    edge_x)
                else:
                    x_edge = _edge_target(col_center(cols[last]), n, x_leftmost,
                                          POLY_WIDTH, MET2_SPACE)
                    if x_edge > x_last:
                        hpath(x_last, x_edge, handoff_y, cols[last], None)
                    else:
                        hpath(x_edge, x_last + POLY_WIDTH, handoff_y,
                              cols[last], None)

   # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    def drop_vias():
        if VIRTUOSO_MODE:
            tech = ws.tech.get_tech_file(cv)
            via_def = ws.tech.find_via_def_by_name(tech, VIA_NAME)
            if via_def is None:
                raise ValueError(f"Via definition '{VIA_NAME}' not found in tech file")
            for (vx, vy) in sorted(via_pts):
                ws.db.create_via(cv, via_def, [vx, vy], "R0")
            print(f"Dropped {len(via_pts)} vias")

    # ------------------------------------------------------------------
    def show_matplotlib():
        """Render collected paths and vias using matplotlib."""
        layer_colors = {
            MET1: ("steelblue", 0.6),
            MET2: ("tomato", 0.6),
        }

        fig, ax = plt.subplots(figsize=(12, 8))
        ax.set_aspect("equal")
        ax.set_title("Routing Preview (matplotlib — Virtuoso not connected)")
        ax.set_xlabel("X (µm)")
        ax.set_ylabel("Y (µm)")

        for p in mpl_paths:
            color, alpha = layer_colors.get(p["layer"], ("gray", 0.5))
            (x0, y0), (x1, y1) = p["pts"]
            w = p["width"]

            if x0 == x1:   # vertical
                rect_x, rect_y = x0 - w / 2, min(y0, y1)
                rect_w, rect_h = w, abs(y1 - y0)
            else:          # horizontal
                rect_x, rect_y = min(x0, x1), y0 - w / 2
                rect_w, rect_h = abs(x1 - x0), w

            ax.add_patch(patches.Rectangle(
                (rect_x, rect_y), rect_w, rect_h,
                linewidth=0.5, edgecolor="black",
                facecolor=color, alpha=alpha))

        via_size = min(n_width, n1_width) * 0.8
        for (vx, vy) in via_pts:
            ax.add_patch(patches.Rectangle(
                (vx - via_size / 2, vy - via_size / 2),
                via_size, via_size,
                linewidth=0.5, edgecolor="black",
                facecolor="gold", alpha=0.9))

        handles = [
            patches.Patch(facecolor="steelblue", alpha=0.6, label=f"MET1 ({MET1})"),
            patches.Patch(facecolor="tomato",    alpha=0.6, label=f"MET2 ({MET2})"),
            patches.Patch(facecolor="gold",      alpha=0.9, label=f"Via ({VIA_NAME})"),
        ]
        ax.legend(handles=handles, loc="upper right")
        ax.autoscale_view()
        plt.tight_layout()
        plt.show()
        print(f"Preview: {len(mpl_paths)} paths, {len(via_pts)} vias")

    # ------------------------------------------------------------------
    draw_vertical()
    draw_horizontal()
    connect_links(connections, MET2, n1_width, draw_path)   # after draw_horizontal()
    # drop_vias()          # uncomment to place M1_M2 vias in Virtuoso

    if not VIRTUOSO_MODE and path_callback is None:
        show_matplotlib()

    return connections


# Redraw the layout window (only when Virtuoso is connected)
if VIRTUOSO_MODE:
    ws.hi.redraw()
