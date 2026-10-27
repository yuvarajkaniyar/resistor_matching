from routing_v5 import router5, connect_virtuoso
from python_array import createArray

# Array size and routing parameters (keep these in sync with `arr` below)
M, N = 2, 50
ARGS = ("MET1", 0.5, 1, 10, 0.5, 0.3, 0.5)      # MET1, POLY_SPACE_X, POLY_SPACE_Y, height, n_width, n_drc, POLY_WIDTH
ARGS2 = (0.5, 0.3, "MET2")                      # n1_drc, n1_width, MET2

matplot = True          # also show the matplotlib plot when Virtuoso IS connected
place_vias = True       # drop M1_M2 vias; the tap climbs need them to connect

ws, VIRTUOSO_MODE = connect_virtuoso()

if VIRTUOSO_MODE:
    cv = ws.db.open_cell_view_by_type("TCAN942H", "pcell_resiistor",
                                      "layout", "maskLayout", "a")
else:
    cv = None       # no Virtuoso -> matplotlib preview only (cv is never touched)

# ── Saved test cases ───────────────────────────────────────────
# ── Saved test cases ───────────────────────────────────────────
# arr = createArray(3, 3, ["A","B","C","B","C","A","C","A","B"])
# router1(cv, 3, 3, "MET1", 0.5, 1, 10, 0.5, 0.3,
#             0.5, arr, 0.5, 0.5, "MET2")
# arr = createArray(3 3 list("A","B","C","B","C","A","C","A","B"))
# arr = createArray(7 7 list("A","B","A","B","B","B","C","C","C","A","B","A","B","B","B","C","C","C","A","B","A","B","B","B","C","C","C","A","B","A","B","B","B","C","C","C","A","B","A","B","B","B","C","C","C","A","B","A","B","B"))
# router1(geGetEditCellView() 3 3 "MET1" 0.5 1 10 0.5 0.3 0.5 arr 0.5 0.3 "MET2")
# router1(geGetEditCellView() 7 7 "MET1" 0.5 1 10 0.5 0.3 0.5 arr 0.5 0.3 "MET2")
#arr = createArray(1,100,["A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C", "A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C",  "A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C","A","B","C","C"])
#arr = createArray(10,10,["A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H", "A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D"])
arr = createArray(2,50, ["A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D","A","B","C","D"])
# arr = createArray(2,100,["A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H","A","B","C","D","E","F","G","H"])

#arr = createArray(2,50, ["A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B","A","B","C","B"])

# router5 draws in Virtuoso when it is up and previews when it is not.
plan = router5(cv, M, N, *ARGS, arr, *ARGS2, ws=ws,
               place_vias=place_vias, preview=matplot)

print(f"{len(plan.paths)} paths, {len(plan.vias)} vias, "
      f"{len(plan.taps)} taps, {len(plan.terminals)} terminals")
for tap in plan.taps:
    print(f"  tap {tap.group}: row {tap.row_from} -> {tap.row_to}, "
          f"climbs at x={tap.climb_x:.2f} on {tap.climb_layer} "
          f"(reach {tap.reach:.2f} um, rise {tap.climb:.2f} um)")
for t in plan.terminals:
    print(f"  terminal {t.group} {t.end}: {t.point} -> {t.side} edge")
