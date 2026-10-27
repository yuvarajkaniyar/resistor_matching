# Code Overview

This repository contains a small set of Python utilities for generating and visualising routing layouts.

## `python_array.py`
- Provides helper functions for working with 2‑D arrays represented as `list[list]`.
- Core utilities:
  - `createArray(rows, cols, elements)`: builds a 2‑D array from a flat list.
  - Queries such as `getAllUnique`, `getPositions`, `getCount`, `getUniqueInRow/Col`, `getElement`, and navigation helpers (`near_element`, `getnextPos_in_row`, etc.).
- All indices are **1‑based** to match the conventions used elsewhere in the code.

## `routing_v3.py`
- Implements the main routing algorithm (`router1`).
- Works in two modes:
  1. **Virtuoso mode** – connects to a Cadence/Virtuoso workspace via `skillbridge.Workspace` when a PID file is present.
  2. **Matplotlib preview mode** – falls back to generating a graphical preview when Virtuoso is unavailable.
- Key steps:
  - Draw vertical MET1 tracks (`draw_vertical`).
  - Compute sorted positions for each resistor using `_sort_pos_map`.
  - Draw horizontal MET2 segments (`draw_horizontal`) while optionally collecting via locations.
  - If not in Virtuoso mode, `show_matplotlib` renders the collected paths with Matplotlib.
- The function accepts a *path_callback* allowing callers (e.g., `writeplot.py`) to capture routing segments without invoking Virtuoso.

## `writeplot.py`
- A thin wrapper that calls `router1` with a custom `path_callback` to collect routing segments.
- After routing, it renders the collected segments with Matplotlib, applying distinct colours for MET1 (`steel‑blue`) and MET2 (`crimson`).
- The plot is saved as `routing_plot.png` alongside the script and also shown interactively.
- Can be used as a module (`import writeplot`) or run directly (`python writeplot.py`).

## `test.py`
- Demonstrates a full end‑to‑end run against a real Virtuoso workspace (when available).
- Creates a 2 × 50 resistor array using `createArray` and calls `router1` with a live cell view.
- Includes an optional Matplotlib path (`matplot` flag) that, when enabled, invokes `writeplot.plot_routing` for a preview.

## How the Pieces Fit Together
1. **Array generation** (`python_array.createArray`) builds the logical layout.
2. **Routing** (`routing_v3.router1`) consumes the array and produces geometric paths for MET1, MET2, and vias.
3. **Visualization** (`writeplot.plot_routing`) captures those paths via a callback and renders them.
4. **Testing / integration** (`test.py`) ties everything to a real Virtuoso workspace or falls back to the Matplotlib preview.

---

*This file was generated to give a language model a quick understanding of the codebase.*