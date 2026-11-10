#!/usr/bin/env python3
"""Render the room/door graph of the built town stage as an SVG for the README.

Reads town/town_report.json (written by build_oldtown.py). Street blocks are drawn at
their position on the 3x3-tile chunk grid, building interiors in a column on the right.
Street load zones are grey edges, doors are gold edges. Contains no game imagery.
"""
import json
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else P / 'town/room_graph.svg'

rep = json.loads((P / 'town/town_report.json').read_text())
rooms = {r['room']: r for r in rep['rooms'] if 'skipped' not in r}
town = {k: r for k, r in rooms.items() if r['kind'] == 'town'}
inter = {k: r for k, r in rooms.items() if r['kind'] != 'town'}

CW, CH = 150, 112          # chunk cell size in px
BW, BH = 124, 62           # node box
ML, MT = 60, 120
cxs = [r['chunk'][0] for r in town.values()]
cys = [r['chunk'][1] for r in town.values()]
x0, x1, y0, y1 = min(cxs), max(cxs), min(cys), max(cys)
grid_w = (x1 - x0 + 1) * CW
grid_h = (y1 - y0 + 1) * CH

pos = {}
for k, r in town.items():
    cx, cy = r['chunk']
    pos[k] = (ML + (x1 - cx) * CW + CW / 2, MT + (y1 - cy) * CH + CH / 2)   # same orientation as town_map.png

# interiors: two columns right of the grid, ordered by the mean height of their doors' street rooms
links = {}
for d in rep['doors']:
    a, b = d.get('from_room'), d.get('to_room')
    if a is None or b is None:
        continue
    links.setdefault(a, set()).add(b)
    links.setdefault(b, set()).add(a)
def anchor_y(k):
    ys = [pos[t][1] for t in links.get(k, ()) if t in pos]
    return sum(ys) / len(ys) if ys else 0
order = sorted(inter, key=anchor_y)
IX = ML + grid_w + 90
rows = (len(order) + 1) // 2
IH = max(grid_h / max(rows, 1), BH + 14)
for i, k in enumerate(order):
    col, row = i % 2, i // 2
    pos[k] = (IX + col * (BW + 40) + BW / 2, MT + row * IH + IH / 2)

W = int(IX + 2 * BW + 40 + 50)
H = int(MT + max(grid_h, rows * IH) + 70)

edges = set()
for k, r in rooms.items():
    for t in r.get('triggers', []):
        if isinstance(t, dict) and t.get('to_room') in rooms:
            edges.add(('portal',) + tuple(sorted((k, t['to_room']))))
    for d in r.get('doors', []):
        if d.get('to_room') in rooms:
            edges.add(('door',) + tuple(sorted((k, d['to_room']))))

def label(k):
    r = rooms[k]
    if r['kind'] == 'town':
        return f'Block {k}', f"{len(r['tiles'])} tiles · {r['reachable_m2']/1000:.1f}k m²"
    names = ' · '.join(t[3:] for t in r['tiles'])
    return names, f"interior · {r['reachable_m2']:.0f} m²"

o = []
o.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         'role="img" aria-label="Room graph of the converted Old Silent Hill stage: street blocks joined by '
         'load zones, building interiors joined by doors">')
o.append('<style>.t{font-family:"Segoe UI",Helvetica,Arial,sans-serif;fill:#e8e6df}'
         '.h{font-size:14px;font-weight:600}.s{font-size:11.5px;fill:#a9b0ad}'
         '.k{font-size:12px;fill:#8f9794;letter-spacing:2px}</style>')
o.append(f'<rect width="{W}" height="{H}" rx="16" fill="#14181a"/>')
o.append(f'<text x="{ML}" y="44" class="t k">OLD SILENT HILL · ROOM GRAPH</text>')
o.append(f'<text x="{ML}" y="70" class="t s">{len(town)} street blocks (3×3 map tiles each, laid out as on the map) · '
         f'{len(inter)} interiors · {sum(1 for e in edges if e[0]=="portal")} load-zone links · '
         f'{len(rep["doors"])} doors joining {sum(1 for e in edges if e[0]=="door")} room pairs</text>')
# legend
lx = W - 300
o.append(f'<line x1="{lx}" y1="66" x2="{lx+34}" y2="66" stroke="#6d7674" stroke-width="3"/>'
         f'<text x="{lx+42}" y="70" class="t s">street load zone</text>')
o.append(f'<line x1="{lx+150}" y1="66" x2="{lx+184}" y2="66" stroke="#c9a227" stroke-width="2.5" stroke-dasharray="6 4"/>'
         f'<text x="{lx+192}" y="70" class="t s">door</text>')
o.append(f'<text x="{IX}" y="{MT-14}" class="t k">INTERIORS</text>')
o.append(f'<text x="{ML}" y="{MT-14}" class="t k">STREETS</text>')

for kind, a, b in sorted(edges):
    (xa, ya), (xb, yb) = pos[a], pos[b]
    if kind == 'portal':
        o.append(f'<line x1="{xa:.1f}" y1="{ya:.1f}" x2="{xb:.1f}" y2="{yb:.1f}" stroke="#6d7674" stroke-width="3"/>')
# doors: street -> interior edges run orthogonally through the gaps above each street row,
# so they never read as a link between two street blocks; interior <-> interior edges are direct.
gap_count = {}
door_edges = sorted((e for e in edges if e[0] == 'door'), key=lambda e: (pos[e[1]][0], pos[e[2]][0]))
for n, (kind, a, b) in enumerate(door_edges):
    if rooms[a]['kind'] != 'town':
        a, b = b, a
    (xa, ya), (xb, yb) = pos[a], pos[b]
    style = 'fill="none" stroke="#c9a227" stroke-width="2.2" stroke-dasharray="6 4" opacity="0.9"'
    if rooms[a]['kind'] != 'town':          # interior <-> interior
        if abs(xa - xb) < 1:
            o.append(f'<path d="M{xa:.1f} {min(ya, yb) + BH/2:.1f} V{max(ya, yb) - BH/2:.1f}" {style}/>')
        else:
            if xa > xb:
                (xa, ya), (xb, yb) = (xb, yb), (xa, ya)
            o.append(f'<path d="M{xa + BW/2:.1f} {ya:.1f} C{(xa + xb)/2:.1f} {ya:.1f} {(xa + xb)/2:.1f} {yb:.1f} '
                     f'{xb - BW/2:.1f} {yb:.1f}" {style}/>')
        continue
    gy = ya - CH / 2
    k = gap_count.get(round(gy), 0); gap_count[round(gy)] = k + 1
    gy += (k - 1) * 7
    sx = xa + BW / 2 - 14 - k * 9
    lane = IX - 34 + (n % 5) * 5
    o.append(f'<circle cx="{sx:.1f}" cy="{ya - BH/2:.1f}" r="3.2" fill="#c9a227"/>')
    o.append(f'<path d="M{sx:.1f} {ya - BH/2:.1f} V{gy:.1f} H{lane:.1f} C{lane + 18:.1f} {gy:.1f} {lane + 18:.1f} {yb:.1f} '
             f'{xb - BW/2:.1f} {yb:.1f}" {style}/>')
for k in rooms:
    x, y = pos[k]
    t1, t2 = label(k)
    town_node = rooms[k]['kind'] == 'town'
    fill, stroke = ('#1f2528', '#4a5355') if town_node else ('#2a2620', '#c9a227')
    if k == 0:
        stroke = '#9fb36a'
    o.append(f'<rect x="{x-BW/2:.1f}" y="{y-BH/2:.1f}" width="{BW}" height="{BH}" rx="9" fill="{fill}" '
             f'stroke="{stroke}" stroke-width="1.6"/>')
    o.append(f'<text x="{x:.1f}" y="{y-4:.1f}" text-anchor="middle" class="t h">{t1}</text>')
    o.append(f'<text x="{x:.1f}" y="{y+15:.1f}" text-anchor="middle" class="t s">{t2}</text>')
o.append(f'<text x="{ML}" y="{H-28}" class="t s">Generated by pipeline/tools/make_room_graph.py from the build report. '
         'Block 0 (green) is the starting area.</text>')
o.append('</svg>')
OUT.write_text('\n'.join(o) + '\n')
print('wrote', OUT, len(rooms), 'rooms', len(edges), 'edges')
