"""
writeplot.py  –  Visualise the routing produced by router1() from routing_v3.py
                 without requiring a live Cadence/Virtuoso connection.

Hooks into router1() via path_callback so it always mirrors the real routing
logic exactly — no duplicated code.

Can be called as a module:
    import writeplot
    writeplot.plot_routing(cv, m, n, MET1, POLY_SPACE_X, POLY_SPACE_Y, height,
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

from routing_v3 import router1


# ── Public API ───────────────────────────────────────────────────────────────

def plot_routing(cv, m, n, MET1, POLY_SPACE_X, POLY_SPACE_Y, height,
                 n_width, n_drc, POLY_WIDTH, arr, n1_drc, n1_width, MET2,
                 VIA_NAME="M1_M2"):
    """
    Plot the routing by hooking into router1() via path_callback.
    Saves routing_plot.png alongside this file and shows an interactive window.
    """

    segments = []

    def _collect(layer, width, pts):
        segments.append({"layer": layer, "width": width,
                         "pts": [list(p) for p in pts]})

    # Run the real router with our collector — no Virtuoso calls made
    router1(cv, m, n, MET1, POLY_SPACE_X, POLY_SPACE_Y, height,
            n_width, n_drc, POLY_WIDTH, arr, n1_drc, n1_width, MET2,
            VIA_NAME=VIA_NAME, path_callback=_collect)

    n_met1 = sum(1 for s in segments if s["layer"] == MET1)
    n_met2 = sum(1 for s in segments if s["layer"] == MET2)
    print(f"[writeplot] Collected {len(segments)} segments  "
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
    print(f"[writeplot] Plot saved -> {out_path}", file=sys.stderr)
    plt.show()


# ── Standalone entry-point ───────────────────────────────────────────────────
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

    # cv=None is fine — path_callback bypasses all Virtuoso calls
    plot_routing(None, 10, 10, "MET1", 0.5, 1, 10, 0.5, 0.3, 0.5,
                 arr, 0.5, 0.3, "MET2")
