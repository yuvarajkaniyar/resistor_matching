# Python matched resistor layout prototype

Python 3.10+; no packages required for command-line use. The desktop GUI uses tkinter (on Ubuntu: `sudo apt install python3-tk`).

## Run

```bash
python3 resistor_layout.py --gui
python3 resistor_layout.py --counts A:4,B:8 --columns 4 --unit-ohms 1000 --out output
python3 resistor_layout.py --counts A:3,B:5 --mode interdigitated --columns 4
python3 -m unittest discover -v
```

A:4,B:8 means four identical units in string A and eight in string B. With 1 kΩ units, nominal total resistances are 4 kΩ and 8 kΩ. Group names must start with a letter and contain only letters, digits and underscores. D is reserved for dummies. Maximum 256 active units and 32 columns.

## Features

- Exact 180-degree paired common-centroid placement for even group counts. Automatically inserts symmetric interior dummies when the rectangular array has spare sites.
- Interdigitated round-robin placement for arbitrary positive counts. This mode does not guarantee a common centroid.
- Deterministic randomized pair swapping to reduce group second-moment differences. This is a heuristic, not a global optimum or a complete matching objective.
- Full perimeter dummy ring and uniform unit orientation.
- Independent series strings, with accessible P/N ports per group. No divider tap sharing or general netlist routing.
- Three abstract routing layers: M1 pin escape, unique M2 terminal trunks, private M3 channels. Crossings on different layers are insulated unless an explicit via joins them.
- SVG drawing, JSON geometry/metrics and SPICE connectivity exports.
- Desktop preview and command-line batch operation.

## Metrics and limits

Coordinates, lengths and second moments use ABSTRACT units, not micrometers. Centroid separation is geometric and is not an electrical mismatch estimate. Identical centroids cancel an ideal first-order linear spatial gradient under the identical-unit assumption; unequal second moments, edge effects, local random variations, thermal gradients and routing parasitics remain. No statistical mismatch model is included.

The conservative dedicated-track router becomes large for large arrays. It does not minimize area, enforce actual metal/via design rules, equalize wire resistance/capacitance, route guard rings or connect dummy terminals. Route lengths are reported, not balanced. SVG distinguishes M3 with dashed lines; JSON is the authoritative layer/connectivity description.

The layout is conceptual: resistor bodies are illustrative rectangles and via markers are abstract. No PDK PCells, fabrication contacts, GDSII, DRC/LVS, antenna checking or parasitic extraction are provided. Do not use these outputs for tapeout. To develop a fabrication-ready version, supply the PDK, resistor type/unit dimensions, terminal geometry, layer map, contact/via rules and required schematic topology. Integrate a PDK-aware geometry backend and real verification tools.

## Validation

Tests cover counts, exact centroids across several array shapes and ratios, perimeter dummies, every active pin used once, per-net graph connectivity, two external ports per series string, and absence of same-layer centerline intersections between different nets. These checks are not foundry DRC. GUI code is included but was not interactively tested in the headless build environment.

## Similar existing projects

- EDA Layout Assistant: https://github.com/VivianChencwy/EDA_Layout_Assistant — repository describes Python/gdstk resistor and capacitor matching automation; closest scope. Repository implementation was not locally audited.
- ALIGN: https://github.com/ALIGN-analoglayout/ALIGN-public — broader analog SPICE-to-layout flow, configurable primitive cells and analog constrained placement/routing.
- IIC-RALF: https://github.com/iic-jku/IIC-RALF — research analog layout flow with SKY130, placement optimization and routing.

This prototype was independently written; it does not bundle code from those repositories.
