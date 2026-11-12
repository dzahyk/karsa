"""Generate BPMN 2.0 files (with diagram interchange, so they open in bpmn.io / Camunda Modeler) and matching SVGs
for the AS-IS and TO-BE deal-desk processes. Run: python3 docs/ba/bpmn/build_bpmn.py"""
import pathlib
from xml.sax.saxutils import escape

OUT = pathlib.Path(__file__).resolve().parent
LANE_H, LANE_X, LABEL_W, COL_W = 150, 30, 40, 150
SIZE = {"start": (36, 36), "end": (36, 36), "task": (120, 64), "gw": (50, 50)}
TAG = {"start": "startEvent", "end": "endEvent", "task": "task", "gw": "exclusiveGateway"}


def build(name, title, lanes, nodes, flows, notes=()):
    """lanes: [(id, label)]; nodes: [(id, kind, label, lane, col)]; flows: [(src, dst, label, route)]"""
    lane_y = {lid: 30 + i * LANE_H for i, (lid, _) in enumerate(lanes)}
    width = LANE_X + LABEL_W + (max(n[4] for n in nodes) + 1) * COL_W + 40
    height = 30 + len(lanes) * LANE_H
    box = {}
    for nid, kind, label, lane, col, *dy in nodes:
        w, h = SIZE[kind]
        cx = LANE_X + LABEL_W + col * COL_W + COL_W / 2
        cy = lane_y[lane] + LANE_H / 2 + (dy[0] if dy else 0)  # optional vertical offset inside the lane
        box[nid] = (cx - w / 2, cy - h / 2, w, h)

    def anchor(nid, side):
        x, y, w, h = box[nid]
        return {"r": (x + w, y + h / 2), "l": (x, y + h / 2), "t": (x + w / 2, y), "b": (x + w / 2, y + h)}[side]

    def points(src, dst, route):
        sx, sy, sw, sh = box[src]; dx, dy, dw, dh = box[dst]
        if route == "back":  # loop back over the top of the lane
            a, b = anchor(src, "t"), anchor(dst, "t")
            top = min(sy, dy) - 22
            return [a, (a[0], top), (b[0], top), b]
        if route == "elbow":  # right, down/up at the midpoint, right again
            a, b = anchor(src, "r"), anchor(dst, "l")
            mx = (a[0] + b[0]) / 2
            return [a, (mx, a[1]), (mx, b[1]), b]
        if abs((sy + sh / 2) - (dy + dh / 2)) < 1:
            return [anchor(src, "r"), anchor(dst, "l")]
        a = anchor(src, "b" if dy > sy else "t"); b = anchor(dst, "l")
        return [a, (a[0], b[1]), b]

    proc, di, svg = [], [], []
    flow_ids = {}
    for i, (s, d, label, route) in enumerate(flows):
        flow_ids[(s, d)] = f"Flow_{i}"
    incoming = {n[0]: [] for n in nodes}; outgoing = {n[0]: [] for n in nodes}
    for (s, d), fid in flow_ids.items():
        outgoing[s].append(fid); incoming[d].append(fid)

    proc.append(f'  <bpmn:laneSet id="LaneSet_{name}">')
    for lid, label in lanes:
        refs = "".join(f"<bpmn:flowNodeRef>{n[0]}</bpmn:flowNodeRef>" for n in nodes if n[3] == lid)
        proc.append(f'   <bpmn:lane id="{lid}" name="{escape(label)}">{refs}</bpmn:lane>')
    proc.append("  </bpmn:laneSet>")
    for nid, kind, label, lane, col, *_ in nodes:
        inner = "".join(f"<bpmn:incoming>{f}</bpmn:incoming>" for f in incoming[nid]) + \
                "".join(f"<bpmn:outgoing>{f}</bpmn:outgoing>" for f in outgoing[nid])
        proc.append(f'  <bpmn:{TAG[kind]} id="{nid}" name="{escape(label)}">{inner}</bpmn:{TAG[kind]}>')
    for (s, d, label, route) in flows:
        fid = flow_ids[(s, d)]
        nm = f' name="{escape(label)}"' if label else ""
        proc.append(f'  <bpmn:sequenceFlow id="{fid}"{nm} sourceRef="{s}" targetRef="{d}" />')
    for i, (text, nid) in enumerate(notes):
        proc.append(f'  <bpmn:textAnnotation id="Note_{i}"><bpmn:text>{escape(text)}</bpmn:text></bpmn:textAnnotation>')
        proc.append(f'  <bpmn:association id="Assoc_{i}" sourceRef="{nid}" targetRef="Note_{i}" />')

    di.append(f'   <bpmndi:BPMNShape id="Participant_{name}_di" bpmnElement="Participant_{name}" isHorizontal="true">'
              f'<dc:Bounds x="{LANE_X}" y="30" width="{width - LANE_X - 10}" height="{len(lanes) * LANE_H}" /></bpmndi:BPMNShape>')
    for lid, _ in lanes:
        di.append(f'   <bpmndi:BPMNShape id="{lid}_di" bpmnElement="{lid}" isHorizontal="true"><dc:Bounds x="{LANE_X + 30}" '
                  f'y="{lane_y[lid]}" width="{width - LANE_X - 40}" height="{LANE_H}" /></bpmndi:BPMNShape>')
    for nid, kind, *_ in nodes:
        x, y, w, h = box[nid]
        extra = ' isMarkerVisible="true"' if kind == "gw" else ""
        di.append(f'   <bpmndi:BPMNShape id="{nid}_di" bpmnElement="{nid}"{extra}><dc:Bounds x="{x:.0f}" y="{y:.0f}" '
                  f'width="{w}" height="{h}" /></bpmndi:BPMNShape>')
    all_pts = {}
    for (s, d, label, route) in flows:
        pts = points(s, d, route); all_pts[(s, d)] = pts
        wps = "".join(f'<di:waypoint x="{px:.0f}" y="{py:.0f}" />' for px, py in pts)
        di.append(f'   <bpmndi:BPMNEdge id="{flow_ids[(s, d)]}_di" bpmnElement="{flow_ids[(s, d)]}">{wps}</bpmndi:BPMNEdge>')
    for i, (text, nid) in enumerate(notes):
        x, y, w, h = box[nid]
        di.append(f'   <bpmndi:BPMNShape id="Note_{i}_di" bpmnElement="Note_{i}"><dc:Bounds x="{x:.0f}" y="{y + h + 14:.0f}" '
                  f'width="{COL_W - 10}" height="40" /></bpmndi:BPMNShape>')

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
  xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Defs_{name}" targetNamespace="https://github.com/dzahyk/karsa">
 <bpmn:collaboration id="Collab_{name}">
  <bpmn:participant id="Participant_{name}" name="{escape(title)}" processRef="Process_{name}" />
 </bpmn:collaboration>
 <bpmn:process id="Process_{name}" isExecutable="false">
{chr(10).join(proc)}
 </bpmn:process>
 <bpmndi:BPMNDiagram id="Diagram_{name}">
  <bpmndi:BPMNPlane id="Plane_{name}" bpmnElement="Collab_{name}">
{chr(10).join(di)}
  </bpmndi:BPMNPlane>
 </bpmndi:BPMNDiagram>
</bpmn:definitions>
'''
    (OUT / f"{name}.bpmn").write_text(xml)

    # ---- SVG (same geometry) ----
    ink, line, fill, accent = "#1f2933", "#52606d", "#ffffff", "#0b6e4f"
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height + 70}" font-family="Inter, Arial, sans-serif" font-size="12">',
         f'<rect width="100%" height="100%" fill="#f7f7f5"/>',
         '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
         f'<path d="M0,0 L10,5 L0,10 z" fill="{line}"/></marker></defs>',
         f'<text x="{LANE_X}" y="20" font-size="14" font-weight="700" fill="{ink}">{escape(title)}</text>']
    s.append(f'<rect x="{LANE_X}" y="30" width="{width - LANE_X - 10}" height="{len(lanes) * LANE_H}" fill="none" stroke="{ink}"/>')
    for lid, label in lanes:
        y = lane_y[lid]
        s.append(f'<rect x="{LANE_X + 30}" y="{y}" width="{width - LANE_X - 40}" height="{LANE_H}" fill="none" stroke="#9aa5b1"/>')
        s.append(f'<text transform="translate({LANE_X + 20},{y + LANE_H / 2}) rotate(-90)" text-anchor="middle" fill="{ink}" font-weight="600">{escape(label)}</text>')
    for (s_, d, label, route), pts in zip(flows, all_pts.values()):
        path = " ".join(f"{'M' if i == 0 else 'L'}{px:.0f},{py:.0f}" for i, (px, py) in enumerate(pts))
        s.append(f'<path d="{path}" fill="none" stroke="{line}" stroke-width="1.4" marker-end="url(#arr)"/>')
        if label:
            mx, my = pts[0] if len(pts) == 2 else pts[1]
            s.append(f'<text x="{mx + 6:.0f}" y="{my - 6:.0f}" fill="{accent}" font-size="11" font-weight="600">{escape(label)}</text>')
    for nid, kind, label, lane, col, *_ in nodes:
        x, y, w, h = box[nid]
        if kind == "task":
            s.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{ink}" stroke-width="1.4"/>')
            words, lines_, cur = label.split(), [], ""
            for wd in words:
                if len(cur + " " + wd) > 18 and cur: lines_.append(cur); cur = wd
                else: cur = (cur + " " + wd).strip()
            lines_.append(cur)
            for i, ln in enumerate(lines_):
                s.append(f'<text x="{x + w / 2:.0f}" y="{y + h / 2 - (len(lines_) - 1) * 7 + i * 14 + 4:.0f}" text-anchor="middle" fill="{ink}">{escape(ln)}</text>')
        elif kind == "gw":
            cx, cy = x + w / 2, y + h / 2
            s.append(f'<path d="M{cx},{y} L{x + w},{cy} L{cx},{y + h} L{x},{cy} z" fill="{fill}" stroke="{ink}" stroke-width="1.4"/>')
            s.append(f'<text x="{x - 6:.0f}" y="{cy - 16:.0f}" text-anchor="end" fill="{ink}" font-size="11">{escape(label)}</text>')
        else:
            cx, cy = x + w / 2, y + h / 2
            sw = 3.5 if kind == "end" else 1.4
            s.append(f'<circle cx="{cx}" cy="{cy}" r="18" fill="{fill}" stroke="{ink}" stroke-width="{sw}"/>')
            s.append(f'<text x="{cx:.0f}" y="{y + h + 15:.0f}" text-anchor="middle" fill="{ink}" font-size="11">{escape(label)}</text>')
    for i, (text, nid) in enumerate(notes):
        x, y, w, h = box[nid]
        ny = y + h + 14
        nx = x + w / 2 + 8
        s.append(f'<path d="M{nx + 8:.0f},{ny:.0f} h-8 v40 h8" fill="none" stroke="#b44d12"/>')
        rows, cur = [], ""
        for wd in text.split():
            if len(cur + " " + wd) > 24 and cur: rows.append(cur); cur = wd
            else: cur = (cur + " " + wd).strip()
        rows.append(cur)
        for k, row in enumerate(rows[:2]):
            s.append(f'<text x="{nx + 4:.0f}" y="{ny + 14 + 14 * k:.0f}" fill="#b44d12" font-size="11">{escape(row)}</text>')
    s.append("</svg>")
    (OUT / f"{name}.svg").write_text("\n".join(s))


build("asis", "AS-IS (assumed): manual deal desk",
      [("Lane_A", "Analyst"), ("Lane_M", "Manager"), ("Lane_O", "Ops")],
      [("S", "start", "Brief by email/chat", "Lane_A", 0), ("A1", "task", "Retype numbers into a spreadsheet", "Lane_A", 1),
       ("A2", "task", "Price in own spreadsheet", "Lane_A", 2), ("M1", "task", "Approve in chat", "Lane_M", 3),
       ("O1", "task", "Type deal into CRM", "Lane_O", 4), ("O2", "task", "Create project in tracker", "Lane_O", 5),
       ("E", "end", "Deal live", "Lane_O", 6)],
      [("S", "A1", "", ""), ("A1", "A2", "", ""), ("A2", "M1", "", ""), ("M1", "O1", "", ""), ("O1", "O2", "", ""),
       ("O2", "E", "", "")],
      [("PP1: no source per value", "A1"), ("PP2: formulas differ", "A2"), ("PP3: approval not tied to values", "M1"),
       ("PP4: timeout → duplicate", "O1")])

build("tobe", "TO-BE: Karsa deal desk",
      [("Lane_A", "Analyst"), ("Lane_S", "Karsa (system)"), ("Lane_P", "Approver"), ("Lane_X", "Automation Eng.")],
      [("S", "start", "Brief received", "Lane_A", 0), ("A1", "task", "Create case (paste / upload)", "Lane_A", 1),
       ("Y1", "task", "Extract drafts with evidence", "Lane_S", 2), ("A2", "task", "Review and confirm requirements", "Lane_A", 3),
       ("G1", "gw", "All critical confirmed?", "Lane_A", 4), ("A3", "task", "Clarify with client (channel + ref)", "Lane_A", 5),
       ("Y2", "task", "Price deterministically", "Lane_S", 5), ("Y3", "task", "Freeze package (SHA-256)", "Lane_S", 6),
       ("G2", "gw", "High risk?", "Lane_P", 7), ("P1", "task", "Approve (single)", "Lane_P", 8, -38),
       ("P2", "task", "Exception + two approvers", "Lane_P", 8, 38), ("P3", "task", "Authorize execution", "Lane_P", 9),
       ("Y4", "task", "Write CRM + tracker (idempotent)", "Lane_S", 10), ("G3", "gw", "Read-back = hash?", "Lane_S", 11),
       ("E1", "end", "Completed (verified)", "Lane_S", 12), ("X1", "task", "Reconcile / exception queue", "Lane_X", 12)],
      [("S", "A1", "", ""), ("A1", "Y1", "", ""), ("Y1", "A2", "", ""), ("A2", "G1", "", ""), ("G1", "A3", "no", ""),
       ("A3", "A2", "", "back"), ("G1", "Y2", "yes", ""), ("Y2", "Y3", "", ""), ("Y3", "G2", "", ""), ("G2", "P1", "no", ""),
       ("G2", "P2", "yes", ""), ("P1", "P3", "", "elbow"), ("P2", "P3", "", "elbow"), ("P3", "Y4", "", ""),
       ("Y4", "G3", "", ""), ("G3", "E1", "yes", ""), ("G3", "X1", "no", "")],
      [("BR-009: quote + offsets", "Y1"), ("BR-001 gate", "Y3"), ("BR-003: binds hash", "P3"),
       ("BR-007, AC-06", "Y4")])
print("written:", sorted(p.name for p in OUT.glob("*.bpmn")), sorted(p.name for p in OUT.glob("*.svg")))
