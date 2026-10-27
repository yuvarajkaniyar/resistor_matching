"""
routing_v4.py  –  Resistance-driven matched resistor array generator.

Port of the resistor flow from the EDA_Layout_Assistant project
(https://github.com/VivianChencwy/EDA_Layout_Assistant) onto this tool's
backends.  The reference implementation emits GDS through `gdstk`; here the
same algorithm drives Virtuoso through skillbridge when it is reachable, and
falls back to a matplotlib preview when it is not (same rule as routing_v3).

Difference from routing_v3.router1()
------------------------------------
routing_v3 takes a *placement* (the 2D `arr` of labels) and routes it.
This module takes the two *resistance values* and derives everything:

    res1, res2  ->  simplify_ratio()            unit count per net
                ->  calculate_resistor_size()   W/L of one unit segment
                ->  calculate_resistors_parameters()  segment coordinates
                ->  assign_resistor_labels()    common-centroid ordering
                ->  calculate_metal_layer_coords()    contact + M1 pads
                ->  build_array()               serpentine M1 routing

Everything drawn is a rectangle, so the same geometry list feeds all backends.

Usage
-----
    from routing_v4 import generate_resistor_array
    generate_resistor_array(res1=2500, res2=3000, magnification=2.0,
                            layout_style="symmetric")

    python3 routing_v4.py          # standalone demo (README's 2500/3000 case)
"""

import os
import sys
from fractions import Fraction
from math import gcd


# ======================================================================
# PDK data (from EDA_Layout_Assistant/resistor/parameter.py)
# ======================================================================
layer_numbers = {
    'NWELL': 2, 'DIFF': 3, 'PIMP': 7, 'NIMP': 8, 'POLY1': 13, 'CONT': 15,
    'METAL1': 16, 'VIA12': 17, 'METAL2': 18, 'VIA23': 27, 'METAL3': 28,
    'VIA34': 29, 'METAL4': 31, 'VIA45': 32, 'METAL5': 33, 'METAL6': 38,
    'WELLBODY': 103, 'RPDUMMY': 54, 'IP': 113,
}

# Virtuoso layer names for the same roles — edit to match your techfile.
layer_names = {
    'RPDUMMY': "RPDUMMY", 'DIFF': "DIFF", 'WELLBODY': "WELLBODY",
    'NIMP': "NIMP", 'CONT': "CONT", 'METAL1': "MET1", 'METAL2': "MET2",
}

drc_params = {
    'COW1_Maxmin_CONT_Square': 0.22,    # contact size
    'COE1_Min_CONT_OD_Spacing': 0.1,
    'COE2_Min_CONT_PD_Spacing': 0.1,
    'MXS2_Min_CONT_M1_Spacing': 0.6,
    'M1E2_Min_M1_CO_Spacing': 0.06,     # metal enclosure of contact
    'Min_Diff_DUMMY_Spacing': 0.32,     # DIFF beyond the RPDUMMY body
    'M1S1_Min_M1_M1_Spacing': 0.23,
    'MARGIN_PO_OD_Distance': 0.22,
    'SLITPOE2_Min_Imp_PO_Spacing': 0.13,
    'Spacing_DIFF__NIMP_Width': 0.18,
    'COC1_Min_CO_PO_Spacing': 0.16,
    'M1W1_Min_METAL1_Width': 0.29,
    'Margin_Guarding__body_elngth': 0.3,
    'Margin_Min_Pimp_Nimp_Spacing': 0.08,
    'M1E2_Min_CONT_M1_Spacing': 0.005,
}

rnlplus_params = {
    'CO_CO_Spacing': 0.25,
    'Spacing_DIFF__NIMP_Width': 0.35,
    'DUMMY_Width_Min': 0.42,
    'DUMMY_Length_Min': 0.35,
    'Min_Segment_Spacing': 0.28,
    'Ohm/Sq': 6.82,
}

WIRE_WIDTH = 0.34           # routing wire width (reference: hard-coded 0.34)
RIGHT_TUCK = 0.06           # extra inward shift of the right-hand trunks
LEFT_TUCK  = 0.05           # extra inward shift of R2's left-hand trunks


# ======================================================================
# Step 1 — resistance ratio  ->  unit segment counts
# ======================================================================
def simplify_ratio(res1, res2, layout_style='symmetric', verbose=True):
    """Reduce res1:res2 to unit-segment counts and the unit resistance.

    Returns (res1_num, res2_num, basic_resistance, swapped).

    `swapped` is True when the pair was exchanged to keep res1_num even (the
    reference does this so only one routing variant has to be written); the
    caller needs it because in that case "R1" refers to the *second* value.
    """
    if isinstance(res1, int) and isinstance(res2, int):
        divisor = gcd(res1, res2)
        res1_num, res2_num = res1 // divisor, res2 // divisor
    else:   # non-integer values: nearest small rational
        ratio = Fraction(res1 / res2).limit_denominator(100)
        res1_num, res2_num = ratio.numerator, ratio.denominator

    basic_resistance = res1 / res1_num

    # Keep the odd count on net 2 so a single routing variant covers both.
    swapped = False
    if res1_num % 2 == 1:
        res1_num, res2_num = res2_num, res1_num
        res1, res2 = res2, res1
        basic_resistance = res1 / res1_num
        swapped = True

    if layout_style == 'symmetric':
        # Both odd -> double both so a symmetry axis exists.
        if res1_num % 2 == 1 and res2_num % 2 == 1:
            res1_num, res2_num = res1_num * 2, res2_num * 2
            basic_resistance /= 2
    elif layout_style in ('symmetric_even', 'even_segment'):
        # Force both counts even.
        if res1_num % 2 == 1 or res2_num % 2 == 1:
            res1_num, res2_num = res1_num * 2, res2_num * 2
            basic_resistance /= 2

    if verbose:
        print(f"Resistor 1: {res1_num}, Resistor 2: {res2_num}, "
              f"Basic Resistance: {basic_resistance}")

    return res1_num, res2_num, basic_resistance, swapped


# ======================================================================
# Step 2 — unit resistance  ->  segment geometry
# ======================================================================
def calculate_resistor_size(target_resistance, magnification, ohms_per_square,
                            min_width, min_length):
    """R = rho * L / W, solved at minimum width then scaled by magnification."""
    width  = round(min_width, 2)
    length = round((target_resistance / ohms_per_square) * width, 2)

    # Theoretical length below the minimum -> pin the length, widen instead.
    if length < min_length:
        length = round(min_length, 2)
        width  = round((ohms_per_square * length) / target_resistance, 2)

    width  *= round(magnification, 2)
    length *= round(magnification, 2)
    area = round(width * length, 2)
    actual_resistance = round(ohms_per_square * length / width, 2)
    return width, length, area, actual_resistance


def calculate_resistors_parameters(start_x, start_y, res1, res2,
                                   rnlplus_params, magnification,
                                   layout_style, verbose=True):
    """Stack (res1_num + res2_num) identical segments along Y."""
    res1_num, res2_num, basic_resistance, _ = simplify_ratio(
        res1, res2, layout_style, verbose=verbose)

    width, length, area, actual = calculate_resistor_size(
        basic_resistance, magnification,
        rnlplus_params['Ohm/Sq'],
        rnlplus_params['DUMMY_Width_Min'],
        rnlplus_params['DUMMY_Length_Min'],
    )

    coordinates = []
    current_y = start_y
    for _ in range(res1_num + res2_num):
        coordinates.append((start_x, current_y))
        current_y += width + rnlplus_params['Min_Segment_Spacing']

    return width, length, coordinates


# ======================================================================
# Step 3 — common-centroid ordering of the segments
# ======================================================================
def assign_resistor_labels(res1, res2, layout_style, verbose=True):
    """1-based segment positions belonging to each net.

    Fills the half above the symmetry axis by repeating the majority net
    `repeat_value` times between single minority segments, then mirrors it.
    A leftover odd segment sits on the axis.
    """
    res1_num, res2_num, _, _ = simplify_ratio(res1, res2, layout_style,
                                              verbose=False)
    total_res = res1_num + res2_num

    odd_res = 0
    odd_in_middle = None
    if layout_style == 'symmetric' and (res1_num % 2 == 1 or res2_num % 2 == 1):
        if res1_num % 2 == 1:
            odd_in_middle = ('R1', total_res // 2 + 1)
            res1_num -= 1
        else:
            odd_in_middle = ('R2', total_res // 2 + 1)
            res2_num -= 1
        total_res -= 1
        odd_res = 1

    major_num, minor_num = max(res1_num, res2_num), min(res1_num, res2_num)
    major_label = 'R1' if res1_num >= res2_num else 'R2'
    minor_label = 'R2' if major_label == 'R1' else 'R1'

    total_res_half = (res1_num + res2_num) // 2
    repeat_value = int((major_num / 2) / (minor_num / 2 + 1)) or 1

    labels_for_r1, labels_for_r2 = [], []
    major_placed = minor_placed = 0
    position = total_res_half + 1 + odd_res      # first slot past the axis

    while major_placed < major_num // 2 or minor_placed < minor_num // 2:
        for _ in range(repeat_value):
            if major_placed < major_num // 2:
                (labels_for_r1 if major_label == 'R1'
                 else labels_for_r2).append(position)
                position += 1
                major_placed += 1
        if minor_placed < minor_num // 2:
            (labels_for_r1 if minor_label == 'R1'
             else labels_for_r2).append(position)
            position += 1
            minor_placed += 1

    # Mirror the upper half across the axis.
    mirror = lambda xs: [total_res_half * 2 - x + 1 + odd_res
                         for x in xs if x > total_res_half]
    labels_for_r1 = mirror(labels_for_r1) + [x for x in labels_for_r1
                                             if x > total_res_half]
    labels_for_r2 = mirror(labels_for_r2) + [x for x in labels_for_r2
                                             if x > total_res_half]

    if odd_in_middle:
        (labels_for_r1 if odd_in_middle[0] == 'R1'
         else labels_for_r2).append(odd_in_middle[1])

    labels_for_r1.sort()
    labels_for_r2.sort()
    if verbose:
        print("Resistor1 labels:", labels_for_r1,
              "Resistor2 labels:", labels_for_r2)

    return labels_for_r1, labels_for_r2


# ======================================================================
# Step 4 — contacts and METAL1 landing pads
# ======================================================================
def _contact_plan(coord_y, width, drc_params, rnlplus_params):
    """How many contacts fit on one side of a segment, and where they start."""
    contact_margin  = drc_params['M1E2_Min_M1_CO_Spacing']
    contact_size    = drc_params['COW1_Maxmin_CONT_Square']
    contact_spacing = rnlplus_params['CO_CO_Spacing']
    od_co_spacing   = drc_params['COE1_Min_CONT_OD_Spacing']

    count = int((width - 2 * contact_margin + contact_spacing
                 - 2 * od_co_spacing) / (contact_size + contact_spacing))
    count = max(count, 1)       # a segment always needs one contact per side

    span = count * contact_size + (count - 1) * contact_spacing
    first_y = coord_y + (width - span) / 2
    return count, first_y, span


def calculate_metal_layer_coords(start_x, start_y, res1, res2, rnlplus_params,
                                 drc_params, magnification, layout_style,
                                 verbose=True):
    """Per-segment METAL1 pad rectangles, split per net.

    The pads overlap the body by `contact_margin` on the inner edge, matching
    placing.create_resistor() in the reference (its routing.py quoted a
    slightly different inner edge; the drawn pad is the authoritative one).
    """
    width, length, coordinates = calculate_resistors_parameters(
        start_x, start_y, res1, res2, rnlplus_params, magnification,
        layout_style, verbose=False)
    if verbose:
        print(f"width: {width} length: {length} segments: {len(coordinates)}")

    contact_margin = drc_params['M1E2_Min_M1_CO_Spacing']
    contact_size   = drc_params['COW1_Maxmin_CONT_Square']

    metal_coords = []
    for coord_x, coord_y in coordinates:
        _, first_y, span = _contact_plan(coord_y, width, drc_params,
                                         rnlplus_params)
        y_lo = first_y - contact_margin
        y_hi = first_y + span + contact_margin

        metal_coords.append({
            "left": {
                "top_left":     (coord_x - contact_size - contact_margin, y_lo),
                "bottom_right": (coord_x + contact_margin, y_hi),
            },
            "right": {
                "top_left":     (coord_x + length - contact_margin, y_lo),
                "bottom_right": (coord_x + length + contact_size
                                 + contact_margin, y_hi),
            },
        })

    labels_for_r1, labels_for_r2 = assign_resistor_labels(res1, res2,
                                                          layout_style,
                                                          verbose=verbose)
    r1_metal_coords = [metal_coords[i - 1] for i in labels_for_r1]
    r2_metal_coords = [metal_coords[i - 1] for i in labels_for_r2]
    return r1_metal_coords, r2_metal_coords


# ======================================================================
# Geometry collector — one rectangle list, three backends
# ======================================================================
class Shapes(list):
    """Collected rectangles: {'role', 'net', 'p0', 'p1'}."""

    def add(self, role, p0, p1, net=None):
        (x0, y0), (x1, y1) = p0, p1
        self.append({"role": role, "net": net,
                     "p0": (min(x0, x1), min(y0, y1)),
                     "p1": (max(x0, x1), max(y0, y1))})

    def bbox(self):
        xs = [p for s in self for p in (s["p0"][0], s["p1"][0])]
        ys = [p for s in self for p in (s["p0"][1], s["p1"][1])]
        return (min(xs), min(ys), max(xs), max(ys))


# ======================================================================
# Step 5 — one resistor segment
# ======================================================================
def build_resistor(shapes, start_x, start_y, length, width, drc_params,
                   rnlplus_params):
    """RPDUMMY body + contacts + METAL1 pads + DIFF/WELLBODY/NIMP enclosures."""
    if width < rnlplus_params['DUMMY_Width_Min']:
        width = rnlplus_params['DUMMY_Width_Min']
        print('RPDUMMY width clamped to the 420nm minimum')
    if length < rnlplus_params['DUMMY_Length_Min']:
        length = rnlplus_params['DUMMY_Length_Min']
        print('RPDUMMY length clamped to the 350nm minimum')

    contact_margin  = drc_params['M1E2_Min_M1_CO_Spacing']
    contact_size    = drc_params['COW1_Maxmin_CONT_Square']
    contact_spacing = rnlplus_params['CO_CO_Spacing']
    diff_extension  = drc_params['Min_Diff_DUMMY_Spacing']
    nimp_spacing    = rnlplus_params['Spacing_DIFF__NIMP_Width']

    # Enclosures first so the preview layers stack sensibly.
    shapes.add('NIMP',
               (start_x - diff_extension - nimp_spacing, start_y - nimp_spacing),
               (start_x + length + diff_extension + nimp_spacing,
                start_y + width + nimp_spacing))
    shapes.add('DIFF', (start_x - diff_extension, start_y),
               (start_x + length + diff_extension, start_y + width))
    shapes.add('WELLBODY', (start_x - diff_extension, start_y),
               (start_x + length + diff_extension, start_y + width))
    shapes.add('RPDUMMY', (start_x, start_y),
               (start_x + length, start_y + width))

    count, first_y, span = _contact_plan(start_y, width, drc_params,
                                         rnlplus_params)
    for i in range(count):
        y = first_y + i * (contact_size + contact_spacing)
        shapes.add('CONT', (start_x - contact_size, y),
                   (start_x, y + contact_size))
        shapes.add('CONT', (start_x + length, y),
                   (start_x + length + contact_size, y + contact_size))

    shapes.add('METAL1',
               (start_x - contact_size - contact_margin, first_y - contact_margin),
               (start_x + contact_margin, first_y + span + contact_margin))
    shapes.add('METAL1',
               (start_x + length - contact_margin, first_y - contact_margin),
               (start_x + length + contact_size + contact_margin,
                first_y + span + contact_margin))


# ======================================================================
# Step 6 — serpentine routing of the segments of one net
# ======================================================================
def build_array(start_x, start_y, res1, res2, drc_params, rnlplus_params,
                magnification, layout_style, verbose=True):
    """Build the whole array and return (shapes, info)."""
    shapes = Shapes()

    width, length, coordinates = calculate_resistors_parameters(
        start_x, start_y, res1, res2, rnlplus_params, magnification,
        layout_style, verbose=verbose)
    r1_metal_coords, r2_metal_coords = calculate_metal_layer_coords(
        start_x, start_y, res1, res2, rnlplus_params, drc_params,
        magnification, layout_style, verbose=verbose)
    r1_num, r2_num, basic_resistance, swapped = simplify_ratio(
        res1, res2, layout_style, verbose=False)

    for coord_x, coord_y in coordinates:
        build_resistor(shapes, coord_x, coord_y, length, width, drc_params,
                       rnlplus_params)

    shift_distance = WIRE_WIDTH + drc_params['M1S1_Min_M1_M1_Spacing']

    # A leftover odd segment leaves one pad of net 2 as the array terminal.
    r2_modify = 0
    if layout_style == 'symmetric' and r1_num % 2 == 0 and r2_num % 2 == 1:
        r2_modify = 1

    def trunk(anchor, y_from, y_to, shift, net):
        """Vertical METAL1 bar linking two pads of the same net."""
        x = anchor[0] + shift
        shapes.add('WIRE', (x, y_from), (x + WIRE_WIDTH, y_to), net=net)

    def stub(anchor, y_lo, y_hi, shift, net):
        """Horizontal METAL1 bridge from a trunk to the pad beside it."""
        shapes.add('WIRE', (anchor[0] + shift + WIRE_WIDTH, y_lo),
                   (anchor[0], y_hi), net=net)

    # ---- net 1: trunks on the left, alternating left/right per link --------
    for i in range(len(r1_metal_coords) - 1):
        if i % 2 == 0:
            a = r1_metal_coords[i]['left']['top_left']
            b = r1_metal_coords[i + 1]['left']['bottom_right']
            trunk(a, a[1], b[1], -shift_distance, 'R1')
        else:
            a = r1_metal_coords[i]['right']['top_left']
            b = r1_metal_coords[i + 1]['right']['bottom_right']
            trunk(a, a[1], b[1], -shift_distance - RIGHT_TUCK, 'R1')

    for i, pad in enumerate(r1_metal_coords):
        a, b = pad['left']['top_left'], pad['left']['bottom_right']
        stub(a, a[1], b[1], -shift_distance, 'R1')
        if 0 < i < len(r1_metal_coords) - 1:
            a, b = pad['right']['top_left'], pad['right']['bottom_right']
            stub(a, a[1], b[1], -shift_distance - RIGHT_TUCK, 'R1')

    # ---- net 2: mirrored, trunks on the right -----------------------------
    for i in range(len(r2_metal_coords) - 1):
        if i % 2 == 1:
            a = r2_metal_coords[i]['left']['top_left']
            b = r2_metal_coords[i + 1]['left']['bottom_right']
            trunk(a, a[1], b[1], shift_distance + LEFT_TUCK, 'R2')
        else:
            a = r2_metal_coords[i]['right']['top_left']
            b = r2_metal_coords[i + 1]['right']['bottom_right']
            trunk(a, a[1], b[1], shift_distance, 'R2')

    for i, pad in enumerate(r2_metal_coords):
        if i != len(r2_metal_coords) - r2_modify:
            a, b = pad['right']['top_left'], pad['right']['bottom_right']
            stub(a, a[1], b[1], shift_distance, 'R2')
        if 0 < i != len(r2_metal_coords) - 1 + r2_modify:
            a, b = pad['left']['top_left'], pad['left']['bottom_right']
            stub(a, a[1], b[1], shift_distance, 'R2')

    info = {
        "width": width, "length": length,
        "segments": len(coordinates),
        "r1_num": r1_num, "r2_num": r2_num,
        "basic_resistance": basic_resistance,
        "swapped": swapped,
        "r1_pads": len(r1_metal_coords), "r2_pads": len(r2_metal_coords),
    }
    return shapes, info


# ======================================================================
# Backends
# ======================================================================
def _connect_virtuoso():
    """Return (ws, True) when Virtuoso is reachable, else (None, False)."""
    try:
        from skillbridge import Workspace
        with open("/tmp/virtuoso_pid.txt") as f:
            pid = int(f.read().strip())
        ws = Workspace.open(pid)
        print("Connected to Virtuoso workspace.")
        return ws, True
    except Exception as e:
        print(f"Virtuoso not available ({e}). Running in matplotlib "
              f"preview mode.")
        return None, False


def emit_virtuoso(shapes, ws, cv):
    """Draw every rectangle with dbCreateRect()."""
    for s in shapes:
        role = 'METAL1' if s["role"] == 'WIRE' else s["role"]
        layer = layer_names.get(role, role)
        ws.db.create_rect(cv, [layer, "drawing"], [list(s["p0"]), list(s["p1"])])
    ws.hi.redraw()
    print(f"Drew {len(shapes)} rectangles in Virtuoso")


def emit_gds(shapes, filename="resistor_array_cell.gds",
             cell_name="RESISTOR_ARRAY"):
    """Write a GDS with gdstk, as the reference project does."""
    try:
        import gdstk
    except ImportError:
        raise SystemExit("backend='gds' needs gdstk: pip install gdstk")

    cell = gdstk.Cell(cell_name)
    for s in shapes:
        role = 'METAL1' if s["role"] == 'WIRE' else s["role"]
        cell.add(gdstk.rectangle(s["p0"], s["p1"],
                                 layer=layer_numbers[role]))
    library = gdstk.Library()
    library.add(cell)
    library.write_gds(filename)
    print(f"GDS file saved to: {filename}")
    return filename


# role -> (facecolor, alpha, zorder) for the preview
_PREVIEW_STYLE = {
    'NIMP':     ("#3a3a5c", 0.45, 1),
    'DIFF':     ("#2e8b57", 0.35, 2),
    'WELLBODY': ("#1f6f5c", 0.25, 3),
    'RPDUMMY':  ("#9b6bd6", 0.75, 4),
    'CONT':     ("#ffd24d", 0.95, 6),
    'METAL1':   ("#4da6ff", 0.55, 5),
}
_NET_STYLE = {'R1': ("#4da6ff", 0.85, 7), 'R2': ("#ff4d4d", 0.85, 7)}


def emit_matplotlib(shapes, info, title, out_png="resistor_array_v4.png"):
    """Render the collected rectangles — no Virtuoso calls made."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    fig, ax = plt.subplots(figsize=(13, 10))
    fig.patch.set_facecolor("#12121f")
    ax.set_facecolor("#12121f")

    for s in shapes:
        if s["role"] == 'WIRE':
            color, alpha, z = _NET_STYLE.get(s["net"], ("white", 0.8, 7))
        else:
            color, alpha, z = _PREVIEW_STYLE.get(s["role"], ("gray", 0.4, 1))
        (x0, y0), (x1, y1) = s["p0"], s["p1"]
        ax.add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0,
                                       linewidth=0.3, edgecolor="#000000",
                                       facecolor=color, alpha=alpha, zorder=z))

    handles = [patches.Patch(facecolor=c, alpha=a, label=r)
               for r, (c, a, _) in _PREVIEW_STYLE.items()]
    handles += [patches.Patch(facecolor=c, alpha=a, label=f"{n} wiring")
                for n, (c, a, _) in _NET_STYLE.items()]
    ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.01, 0.5),
              fontsize=9, facecolor="#1e1e3a", edgecolor="#666688",
              labelcolor="white")

    x0, y0, x1, y1 = shapes.bbox()
    pad = 0.05 * max(x1 - x0, y1 - y0)
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

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), out_png)
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"Preview saved -> {out_path}")
    plt.show()
    return out_path


# ======================================================================
# Top-level entry point
# ======================================================================
def generate_resistor_array(res1, res2, magnification=2.0,
                            layout_style='symmetric', start_x=0, start_y=0,
                            cv=None, ws=None, backend='auto',
                            cell_name="RESISTOR_ARRAY", verbose=True):
    """Generate the matched array and emit it.

    backend: 'auto'       Virtuoso if reachable, else matplotlib preview
             'virtuoso'   require Virtuoso (needs cv, and ws unless auto-found)
             'matplotlib' preview only
             'gds'        write a GDS through gdstk

    Returns (shapes, info).
    """
    shapes, info = build_array(start_x, start_y, res1, res2, drc_params,
                               rnlplus_params, magnification, layout_style,
                               verbose=verbose)

    net1, net2 = ('R2', 'R1') if info["swapped"] else ('R1', 'R2')
    if verbose:
        print(f"{info['segments']} segments of "
              f"{info['width']:.3f} x {info['length']:.3f} um "
              f"({info['basic_resistance']:.2f} ohm each)")
        print(f"  net {net1} = {res1} ohm -> "
              f"{info['r1_num'] if not info['swapped'] else info['r2_num']} units")
        print(f"  net {net2} = {res2} ohm -> "
              f"{info['r2_num'] if not info['swapped'] else info['r1_num']} units")
        print("  order (bottom -> top): " + " ".join(sequence_string(
            res1, res2, layout_style)))

    if backend == 'auto':
        if ws is None:
            ws, ok = _connect_virtuoso()
        else:
            ok = True
        backend = 'virtuoso' if (ok and cv is not None) else 'matplotlib'

    if backend == 'virtuoso':
        if ws is None:
            ws, ok = _connect_virtuoso()
            if not ok:
                raise RuntimeError("Virtuoso is not reachable")
        if cv is None:
            raise ValueError("backend='virtuoso' needs an open cellview (cv)")
        emit_virtuoso(shapes, ws, cv)
    elif backend == 'gds':
        emit_gds(shapes, f"{cell_name.lower()}.gds", cell_name)
    else:
        title = (f"{res1} / {res2} ohm matched array  –  "
                 f"{layout_style}, {magnification}x  (matplotlib preview)")
        emit_matplotlib(shapes, info, title)

    return shapes, info


def sequence_string(res1, res2, layout_style):
    """The segment order as a list of 'R1'/'R2' labels, bottom to top."""
    r1, r2 = assign_resistor_labels(res1, res2, layout_style, verbose=False)
    order = {}
    for i in r1:
        order[i] = 'R1'
    for i in r2:
        order[i] = 'R2'
    return [order[k] for k in sorted(order)]


# ======================================================================
# Standalone demo — the README's 2500 / 3000 ohm case
# ======================================================================
if __name__ == "__main__":
    generate_resistor_array(
        res1=2500,
        res2=3000,
        magnification=2.0,
        layout_style='symmetric',
        start_x=0,
        start_y=0,
    )
