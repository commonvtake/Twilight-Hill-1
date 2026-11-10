"""Read Silent Hill 1 door links from the SH decomp's map data (text files, not executed).

src/maps/<map>/map_points.h  : s_MapPoint2d array - positionX/positionZ (metres, Q12), triggerParam0
                              (heading, Q8 angle: 256 = full turn), triggerParam1 (trigger size).
src/maps/<map>/map_events.c : s_EventData array. SysState_LoadRoom events are doors within one map
                              overlay: the player presses the action button while touching/facing
                              mapPointIdx (the door) and is moved to map point eventParam.
Exporter space (sh_ipd2obj): x = -X_sh, z = Z_sh (checked against the cafe tile THR0006).
"""
import re
from pathlib import Path

POINT_FIELDS = ('positionX', 'positionZ', 'triggerParam0', 'triggerParam1', 'field_4_5')


def _blocks(text):
    for m in re.finditer(r'//\s*\[(\d+)\]\s*\{(.*?)\n\s*\}', text, re.S):
        yield int(m.group(1)), m.group(2)


def _value(body, name):
    m = re.search(r'\.' + name + r'\s*=\s*([^,\n]+)', body)
    if not m:
        return None
    v = m.group(1).strip()
    q = re.match(r'Q12\(\s*(-?[\d.]+)f?\s*\)', v)
    if q:
        return float(q.group(1))
    try:
        return int(v, 0)
    except ValueError:
        return v


def load_points(map_dir):
    pts = {}
    for i, body in _blocks((Path(map_dir) / 'map_points.h').read_text()):
        pts[i] = {k: _value(body, k) for k in POINT_FIELDS}
        pts[i]['heading_deg'] = ((pts[i]['triggerParam0'] or 0) % 256) * 360.0 / 256.0
    return pts


def load_doors(map_dir):
    """Return LoadRoom door events: {src, dst, required_flag, button}."""
    text = (Path(map_dir) / 'map_events.c').read_text()
    doors = []
    for i, body in _blocks(text):
        if _value(body, 'sysState') != 'SysState_LoadRoom':
            continue
        doors.append({'event': i, 'src': _value(body, 'mapPointIdx'), 'dst': _value(body, 'eventParam'),
                      'required_flag': _value(body, 'requiredFlag'),
                      'button': _value(body, 'activationType') == 'EventActivationType_Button',
                      'trigger': _value(body, 'triggerType')})
    return doors


def to_exporter_m(point):
    return (-point['positionX'], point['positionZ'])
