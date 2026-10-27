"""
test1.py  –  Visualise the routing produced by router1() from routing_v3.py
             without requiring a live Cadence/Virtuoso connection.

Can be called as a module:
    import test1
    test1.plot_routing(m, n, MET1, POLY_SPACE_X, POLY_SPACE_Y, height,
                       n_width, n_drc, POLY_WIDTH, arr, n1_drc, n1_width, MET2)

Or run standalone (uses the same default inputs as test.py).

Layer colours:
    MET1  ->  steel-blue  (#4da6ff)
    MET2  ->  crimson     (#ff4d4d)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import python_array


# ── Router logic (mirrors routing_v3.py; paths collected instead of drawn) ──

def _collect_segments(m, n, MET1, POLY_SPACE_X, POLY_SPACE_Y, height,
                      n_width, n_drc, POLY_WIDTH, arr, n1_drc, n1_width, MET2):
    """Run the router logic and return a list of path segments."""

    segments = []   # [{layer, width, pts}, ...]

    def add_path(layer, width, pts):
        segments.append({"layer": layer, "width": width,
                         "pts": [list(p) for p in pts]})

    x          = POLY_SPACE_X
    y          = height
    POLY_MID   = POLY_WIDTH / 2
    x_leftmost = POLY_WIDTH + POLY_SPACE_X

    # ── vertical MET1 stubs ──────────────────────────────────────────────────
    for col in range(n):
        xCoord = POLY_MID + col * (POLY_WIDTH + x)
        for row in range(m):
            yBase = (row * y) + (row * POLY_SPACE_Y)
            yMid  = yBase + y / 2
            yTop  = yBase + y

            add_path(MET1, n_width,
                     [[xCoord, yBase], [xCoord, yMid - n_drc / 2]])
            add_path(MET1, n_width,
                     [[xCoord, yTop],  [xCoord, yMid + n_drc / 2]])

    # ── horizontal MET2 connections ──────────────────────────────────────────
    for row in range(m):
        unique_res = python_array.getUniqueInRow(arr, row + 1)
        yBase = (row * height) + (row * POLY_SPACE_Y)
        yTop  = yBase + height

        for res in unique_res:
            pos = python_array.getPos(unique_res, res) - 1   # 0-based offset

            if row % 2 != 0:
                yCoord1 = yBase + pos * n1_drc
                yCoord2 = yTop  - pos * n1_drc
            else:
                yCoord2 = yBase + pos * n1_drc
                yCoord1 = yTop  - pos * n1_drc

            current_count = 2
            total_in_row  = python_array.getCountInRow(arr, row + 1, res)

            for col in range(n):
                if res != python_array.getElement(arr, row + 1, col + 1):
                    continue

                if current_count < total_in_row + 1:
                    nxt = python_array.getnextPos_in_row(
                        arr, row + 1, res, col + 1)
                    if nxt != 0:
                        xCoord2 = ((nxt - 1) * (POLY_SPACE_X + POLY_WIDTH)
                                   + POLY_WIDTH)
                    else:
                        xCoord2 = (len(arr[0]) * (POLY_WIDTH + POLY_SPACE_X)
                                   - n1_drc + pos * n1_drc)
                else:
                    xCoord2 = (len(arr[0]) * (POLY_WIDTH + POLY_SPACE_X)
                               - n1_drc + pos * n1_drc)

                xCoord1 = col * x_leftmost

                cond1 = (abs(int(current_count / 2))       % 2) == 0
                cond2 = (abs(int((current_count - 1) / 2)) % 2) == 0

                if (cond1 and cond2) or (not cond1 and not cond2):
                    add_path(MET2, n1_width,
                             [[xCoord1, yCoord2], [xCoord2, yCoord2]])
                elif cond1 and not cond2:
                    add_path(MET2, n1_width,
                             [[xCoord1, yCoord1], [xCoord2, yCoord1]])
                elif not cond1 and cond2:
                    add_path(MET2, n1_width,
                             [[xCoord1, yCoord1], [xCoord2, yCoord1]])
                    if current_count == 2:
                        x_left = (-1) * (POLY_WIDTH + POLY_SPACE_X) * pos
                        add_path(MET2, n1_width,
                                 [[x_left,              yCoord2],
                                  [xCoord1 + POLY_WIDTH, yCoord2]])

                current_count += 1

    return segments


# ── Public API ───────────────────────────────────────────────────────────────

def plot_routing(m, n, MET1, POLY_SPACE_X, POLY_SPACE_Y, height,
                 n_width, n_drc, POLY_WIDTH, arr, n1_drc, n1_width, MET2):
    """
    Plot the routing for the given router1 parameters (same signature as
    router1 but without the leading 'cv' argument).

    Saves routing_plot.png alongside this file and shows an interactive window.
    """

    segments = _collect_segments(m, n, MET1, POLY_SPACE_X, POLY_SPACE_Y,
                                  height, n_width, n_drc, POLY_WIDTH, arr,
                                  n1_drc, n1_width, MET2)

    n_met1 = sum(1 for s in segments if s["layer"] == MET1)
    n_met2 = sum(1 for s in segments if s["layer"] == MET2)
    print(f"[test1] Collected {len(segments)} segments  "
          f"({n_met1} {MET1}, {n_met2} {MET2})", file=sys.stderr)

    LAYER_COLOUR = {MET1: "#4da6ff",   # steel-blue
                    MET2: "#ff4d4d"}   # crimson
    LAYER_LW     = {MET1: 2.0,
                    MET2: 1.5}

    fig, ax = plt.subplots(figsize=(14, 14))
    fig.patch.set_facecolor("#12121f")
    ax.set_facecolor("#12121f")

    for seg in segments:
        lyr = seg["layer"]
        xs  = [p[0] for p in seg["pts"]]
        ys  = [p[1] for p in seg["pts"]]
        ax.plot(xs, ys,
                color=LAYER_COLOUR.get(lyr, "white"),
                linewidth=LAYER_LW.get(lyr, 1.0),
                solid_capstyle="round",
                alpha=0.9)

    legend_handles = [
        Line2D([0], [0], color=LAYER_COLOUR[MET1],
               linewidth=3, label=f"{MET1}  (w={n_width} um)"),
        Line2D([0], [0], color=LAYER_COLOUR[MET2],
               linewidth=3, label=f"{MET2}  (w={n1_width} um)"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=11,
              facecolor="#1e1e3a", edgecolor="#666688", labelcolor="white")

    ax.set_title(f"router1  {m}x{n} array routing", color="white",
                 fontsize=15, pad=14)
    ax.set_xlabel("X (um)", color="#aaaacc", fontsize=11)
    ax.set_ylabel("Y (um)", color="#aaaacc", fontsize=11)
    ax.tick_params(colors="#aaaacc")
    for sp in ax.spines.values():
        sp.set_edgecolor("#444466")
    ax.grid(True, color="#222240", linewidth=0.6, linestyle="--")
    ax.set_aspect("equal", adjustable="box")

    plt.tight_layout()

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "routing_plot.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"[test1] Plot saved -> {out_path}", file=sys.stderr)
    plt.show()


# ── Standalone entry-point (same defaults as test.py) ───────────────────────
if __name__ == "__main__":
    from python_array import createArray

    arr = createArray(10, 10, [
        "A","B","C","D","A","B","C","D","A","B",
        "C","D","A","B","C","D","A","B","C","D",
        "A","B","C","D","A","B","C","D","A","B",
        "C","D","A","B","C","D","A","B","C","D",
        "A","B","C","D","A","B","C","D","A","B",
        "C","D","A","B","C","D","A","B","C","D",
        "A","B","C","D","A","B","C","D","A","B",
        "C","D","A","B","C","D","A","B","C","D",
        "A","B","C","D","A","B","C","D","A","B",
        "C","D","A","B","C","D","A","B","C","D",
    ])

    plot_routing(10, 10, "MET1", 0.5, 1, 10, 0.5, 0.3, 0.5,
                 arr, 0.5, 0.3, "MET2")
