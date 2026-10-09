#!/usr/bin/env python3
"""Conceptual matched resistor placement and isolated three-layer series routing."""
import argparse
import collections
import html
import json
import math
from pathlib import Path
import random
import re

COLORS = ['#38bdf8', '#f472b6', '#fbbf24', '#a78bfa', '#34d399', '#fb923c']


def parse_counts(text):
    result = {}
    for token in text.split(','):
        name, count = token.strip().split(':')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name) or name in result or name == 'D':
            raise ValueError('Use unique group names; D is reserved for dummy cells.')
        result[name] = int(count)
    if not result or any(n < 1 for n in result.values()):
        raise ValueError('Counts must be positive integers.')
    if sum(result.values()) > 256:
        raise ValueError('Prototype supports at most 256 active unit resistors.')
    return result


def place(counts, columns=4, mode='centroid', seed=7):
    if columns < 1 or columns > 32:
        raise ValueError('Columns must be between 1 and 32.')
    n = sum(counts.values())
    rows = math.ceil(n / columns)
    rng = random.Random(seed)
    if mode == 'centroid':
        if any(v % 2 for v in counts.values()):
            raise ValueError('Exact paired common-centroid mode requires even counts. Use interdigitated for odd counts.')
        if rows * columns % 2:
            rows += 1
        labels = [k for k, v in counts.items() for _ in range(v // 2)]
        labels += ['D'] * ((rows * columns - n) // 2)
        pairs = [(i, rows * columns - 1 - i) for i in range(rows * columns // 2)]
        rng.shuffle(labels)
        def cost(ls):
            moments = collections.defaultdict(list)
            for (i, _), label in zip(pairs, ls):
                if label != 'D':
                    x, y = i % columns - (columns - 1) / 2, i // columns - (rows - 1) / 2
                    moments[label].append((x*x, y*y))
            means = [(sum(x for x, y in a)/len(a), sum(y for x, y in a)/len(a)) for a in moments.values()]
            return sum((a[0]-b[0])**2 + (a[1]-b[1])**2 for a in means for b in means)
        best = cost(labels)
        for _ in range(2000):
            if len(labels) < 2:
                break
            a, b = rng.sample(range(len(labels)), 2)
            labels[a], labels[b] = labels[b], labels[a]
            score = cost(labels)
            if score <= best:
                best = score
            else:
                labels[a], labels[b] = labels[b], labels[a]
        grid = ['D'] * (rows * columns)
        for (a, b), label in zip(pairs, labels):
            grid[a] = grid[b] = label
    else:
        remaining = dict(counts)
        grid = []
        while any(remaining.values()):
            for label in counts:
                if remaining[label]:
                    grid.append(label)
                    remaining[label] -= 1
        grid += ['D'] * (rows * columns - n)
    # Uniform orientation and a full one-unit dummy ring.
    cells = []
    indexes = collections.Counter()
    for r in range(rows + 2):
        for c in range(columns + 2):
            label = grid[(r-1)*columns+c-1] if 0 < r < rows+1 and 0 < c < columns+1 else 'D'
            indexes[label] += 1
            cells.append(dict(id=f'{label}_{indexes[label]}', group=label, row=r, col=c))
    return cells, rows, columns


def build(counts, columns=4, mode='centroid', unit_ohms=1000, seed=7):
    if not math.isfinite(unit_ohms) or unit_ohms <= 0:
        raise ValueError('Unit resistance must be finite and positive.')
    cells, rows, columns = place(counts, columns, mode, seed)
    # M2 tracks are unique for every active terminal across all rows.
    # M1 local pin escapes; M2 vertical trunks; M3 private horizontal channels.
    pitch_x, pitch_y = max(12, 2*(rows+2)+4), 10
    for cell in cells:
        cell['x'], cell['y'] = (cell['col']+0.5)*pitch_x, (cell['row']+0.5)*pitch_y
        cell['pins'] = {'P': [cell['x'], cell['y']-2], 'N': [cell['x'], cell['y']+2]}
    groups = {}
    routes = []
    channel = 0
    def track(cell, terminal):
        return cell['col']*pitch_x + 2 + 2*cell['row'] + (terminal == 'N')
    for label, count in counts.items():
        members = [c for c in cells if c['group'] == label]
        links = [(None, members[0], 'P')]
        links += [(a, b, 'P') for a, b in zip(members, members[1:])]
        links += [(members[-1], None, 'N')]
        for index, (a, b, _) in enumerate(links):
            y = (rows+2)*pitch_y + 4 + channel*2
            channel += 1
            terminals = [(a, 'N')] if a else []
            if b:
                terminals.append((b, 'P'))
            segs, vias = [], []
            xs = []
            for cell, pin in terminals:
                px, py = cell['pins'][pin]
                tx = track(cell, pin)
                xs.append(tx)
                segs += [dict(layer='M1', points=[[px, py], [tx, py]]), dict(layer='M2', points=[[tx, py], [tx, y]])]
                vias += [dict(layers=['M1','M2'], at=[tx,py]), dict(layers=['M2','M3'], at=[tx,y])]
            port = None
            if len(xs) == 1:
                xs.append(0 if a is None else (columns+2)*pitch_x)
                port = dict(name=f'{label}_{"P" if a is None else "N"}', at=[xs[-1], y], layer='M3')
            segs.append(dict(layer='M3', points=[[min(xs),y],[max(xs),y]]))
            length = sum(abs(s['points'][0][0]-s['points'][1][0])+abs(s['points'][0][1]-s['points'][1][1]) for s in segs)
            routes.append(dict(net=f'{label}_net_{index}', group=label, terminals=[f'{c["id"]}.{p}' for c,p in terminals], segments=segs, vias=vias, port=port, length=length))
        cx = sum(c['x'] for c in members)/count
        cy = sum(c['y'] for c in members)/count
        groups[label] = dict(count=count, nominal_ohms=count*unit_ohms, centroid=[cx,cy], second_moment=[sum((c['x']-cx)**2 for c in members)/count,sum((c['y']-cy)**2 for c in members)/count], route_length=sum(r['length'] for r in routes if r['group']==label))
    centers = [g['centroid'] for g in groups.values()]
    error = max((math.dist(a,b) for a in centers for b in centers), default=0)
    return dict(schema_version=1, mode=mode, units='abstract layout units', topology='independent series strings', unit_ohms=unit_ohms, rows=rows, columns=columns, pitch=[pitch_x,pitch_y], cells=cells, groups=groups, routes=routes, max_centroid_separation=error, width=(columns+2)*pitch_x, height=(rows+2)*pitch_y+channel*2+8, limitations=['Conceptual geometry, not a PDK resistor PCell.', 'No fabrication DRC/LVS or parasitic extraction.', 'Routing lengths are reported, not equalized.', 'Dummy cells are unconnected.', 'No GDS fabrication contacts or via enclosure rules.'])


def svg(layout):
    w,h = layout['width'],layout['height']
    colors = {g: COLORS[i%len(COLORS)] for i,g in enumerate(layout['groups'])}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 {w+8} {h+8}">', '<rect x="-4" y="-4" width="100%" height="100%" fill="#0f172a"/>']
    for c in layout['cells']:
        color = colors.get(c['group'],'#475569')
        parts += [f'<rect x="{c["x"]-2}" y="{c["y"]-2}" width="4" height="4" fill="{color}"/>',f'<text x="{c["x"]}" y="{c["y"]+0.8}" fill="white" text-anchor="middle" font-size="1.8">{html.escape(c["group"])}</text>']
    for r in layout['routes']:
        for s in r['segments']:
            p,q = s['points']
            dash = ' stroke-dasharray="0.8 0.6"' if s['layer']=='M3' else ''
            parts.append(f'<line x1="{p[0]}" y1="{p[1]}" x2="{q[0]}" y2="{q[1]}" stroke="{colors[r["group"]]}" stroke-width="0.18"{dash}/>')
        for v in r['vias']:
            x,y = v['at']
            parts.append(f'<circle cx="{x}" cy="{y}" r="0.25" fill="white"/>')
        if r['port']:
            p=r['port']; x,y=p['at']
            parts.append(f'<text x="{x}" y="{y-0.4}" text-anchor="{"start" if x==0 else "end"}" fill="white" font-size="1.5">{html.escape(p["name"])}</text>')
    return '\n'.join(parts+['</svg>'])


def export(layout, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'layout.json').write_text(json.dumps(layout,indent=2))
    (directory/'layout.svg').write_text(svg(layout))
    lines = ['* Conceptual matched resistor array: independent series strings']
    for label,g in layout['groups'].items():
        for i in range(g['count']):
            p = f'{label}_P' if i == 0 else f'{label}_internal_{i}'
            n = f'{label}_N' if i == g['count']-1 else f'{label}_internal_{i+1}'
            lines.append(f'R_{label}_{i+1} {p} {n} {layout["unit_ohms"]}')
    (directory/'layout.spice').write_text('\n'.join(lines)+'\n')


def gui():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    root = tk.Tk(); root.title('Matched resistor layout — conceptual prototype'); root.geometry('1050x760')
    controls = ttk.Frame(root); controls.pack(fill='x',padx=12,pady=10)
    values = []
    for title,default in [('Groups','A:4,B:4'),('Columns','4'),('Unit Ω','1000')]:
        ttk.Label(controls,text=title).pack(side='left')
        value=tk.StringVar(value=default); values.append(value)
        ttk.Entry(controls,textvariable=value,width=18 if title=='Groups' else 7).pack(side='left',padx=6)
    mode=tk.StringVar(value='centroid')
    ttk.Combobox(controls,textvariable=mode,values=['centroid','interdigitated'],state='readonly',width=15).pack(side='left')
    info=tk.StringVar(); ttk.Label(root,textvariable=info,wraplength=1000).pack(fill='x',padx=12)
    canvas=tk.Canvas(root,bg='#0f172a'); canvas.pack(fill='both',expand=True,padx=12,pady=10)
    state={}
    def draw(event=None):
        if 'layout' not in state: return
        l=state['layout']; canvas.delete('all')
        scale=min((canvas.winfo_width()-30)/l['width'],(canvas.winfo_height()-30)/l['height'])
        def xy(p): return [15+p[0]*scale,15+p[1]*scale]
        colors={g:COLORS[i%len(COLORS)] for i,g in enumerate(l['groups'])}
        for c in l['cells']:
            x,y=xy([c['x'],c['y']]); d=2*scale
            canvas.create_rectangle(x-d,y-d,x+d,y+d,fill=colors.get(c['group'],'#475569'),outline='')
            canvas.create_text(x,y,text=c['group'],fill='white',font=('Arial',max(6,int(scale*1.5))))
        for r in l['routes']:
            for s in r['segments']:
                opts={'dash':(3,2)} if s['layer']=='M3' else {}
                canvas.create_line(*xy(s['points'][0]),*xy(s['points'][1]),fill=colors[r['group']],**opts)
            for v in r['vias']:
                x,y=xy(v['at']); canvas.create_oval(x-1,y-1,x+1,y+1,fill='white',outline='')
            if r['port']:
                p=r['port']; x,y=xy(p['at']); canvas.create_text(x,y-5,text=p['name'],fill='white',anchor='w' if p['at'][0]==0 else 'e',font=('Arial',7))
    def generate():
        try:
            l=build(parse_counts(values[0].get()),int(values[1].get()),mode.get(),float(values[2].get()))
            state['layout']=l
            info.set(' | '.join(f'{k}: {g["nominal_ohms"]:g} Ω, wire {g["route_length"]:g}' for k,g in l['groups'].items())+f' | Centroid separation: {l["max_centroid_separation"]:g}\nM1 local escapes • M2 vertical • M3 dashed channels • white dots: vias. Abstract units; no PDK DRC/LVS; wires are not length matched.')
            draw()
        except (ValueError,TypeError) as e: messagebox.showerror('Input error',str(e))
    def save():
        if 'layout' not in state: return
        path=filedialog.askdirectory(title='Export SVG, JSON and SPICE')
        if path: export(state['layout'],path); messagebox.showinfo('Exported',path)
    ttk.Button(controls,text='Generate',command=generate).pack(side='left',padx=8)
    ttk.Button(controls,text='Export',command=save).pack(side='left')
    canvas.bind('<Configure>',draw); root.after(100,generate); root.mainloop()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gui',action='store_true'); p.add_argument('--counts',default='A:4,B:4'); p.add_argument('--columns',type=int,default=4)
    p.add_argument('--mode',choices=['centroid','interdigitated'],default='centroid'); p.add_argument('--unit-ohms',type=float,default=1000)
    p.add_argument('--seed',type=int,default=7); p.add_argument('--out',default='output')
    a=p.parse_args()
    if a.gui: gui(); return
    try: l=build(parse_counts(a.counts),a.columns,a.mode,a.unit_ohms,a.seed)
    except ValueError as e: p.error(str(e))
    export(l,a.out)
    print(json.dumps({'groups':l['groups'],'max_centroid_separation':l['max_centroid_separation'],'output':str(Path(a.out).resolve())},indent=2))

if __name__=='__main__': main()
