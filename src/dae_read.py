r"""Parse Mixamo COLLADA (.dae) exports: baked per-node matrix animation.

Expected Mixamo layout (verified on the example exports): unit meter="0.01"
(cm), Y_UP, a library_visual_scenes node tree whose nodes carry
<matrix sid="transform">, and library_animations channels targeting
"<Node>/matrix" with MAT4 LINEAR samples at a fixed rate. The uniform unit
scale (~100) baked into the Armature node is read at runtime (see retarget),
so exports with other unit scales also work as long as they are baked the
same way. Anything else (e.g. per-channel curve animation) fails loudly.
"""

import statistics
import xml.etree.ElementTree as ET
from math import cos, radians, sin, sqrt
from pathlib import Path

from matrix import identity4, mat4_from, mul4

NS = "http://www.collada.org/2005/11/COLLADASchema"


def _q(tag):
    return f"{{{NS}}}{tag}"


class DaeError(ValueError):
    pass


def _floats(text):
    return [float(v) for v in (text or "").split()]


def _rotate_mat4(x, y, z, angle_deg):
    n = sqrt(x * x + y * y + z * z)
    if n == 0.0:
        return identity4()
    x, y, z = x / n, y / n, z / n
    a = radians(angle_deg)
    c, s = cos(a), sin(a)
    t = 1.0 - c
    return mat4_from(
        [
            [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
        ],
        [0.0, 0.0, 0.0],
    )


def _node_transform(node_el):
    """Compose the node's own transform elements in document order."""
    m = identity4()
    for el in node_el:
        if el.tag == _q("matrix"):
            f = _floats(el.text)
            if len(f) != 16:
                raise DaeError(f"node {node_el.get('id')!r}: matrix with {len(f)} values (expected 16)")
            m = mul4(m, [f[i * 4 : i * 4 + 4] for i in range(4)])
        elif el.tag == _q("translate"):
            f = _floats(el.text)
            t = identity4()
            for i in range(3):
                t[i][3] = f[i]
            m = mul4(m, t)
        elif el.tag == _q("rotate"):
            f = _floats(el.text)
            m = mul4(m, _rotate_mat4(*f[:4]))
        elif el.tag == _q("scale"):
            f = _floats(el.text)
            s = identity4()
            for i in range(3):
                s[i][i] = f[i]
            m = mul4(m, s)
    return m


def _source_arrays(src):
    arr = src.find(_q("float_array"))
    if arr is not None:
        return "float", _floats(arr.text)
    narr = src.find(_q("Name_array"))
    if narr is not None:
        return "name", (narr.text or "").split()
    raise DaeError(f"source {src.get('id')!r} has no float_array/Name_array")


def _accessor(src):
    acc = src.find(f"{_q('technique_common')}/{_q('accessor')}")
    if acc is None:
        raise DaeError(f"source {src.get('id')!r} has no accessor")
    params = [p.get("name") for p in acc.findall(_q("param"))]
    stride = int(acc.get("stride") or (len(params) if params else 1))
    return int(acc.get("count")), stride, params


def _time_series(src):
    kind, values = _source_arrays(src)
    if kind != "float":
        raise DaeError("animation TIME source is not a float array")
    count, stride, params = _accessor(src)
    if stride == 1:
        return values[:count]
    try:
        col = params.index("TIME")
    except ValueError:
        col = 0
    return [values[i * stride + col] for i in range(count)]


def _mat_series(src):
    kind, values = _source_arrays(src)
    if kind != "float":
        raise DaeError("animation OUTPUT source is not a float array")
    count, stride, _params = _accessor(src)
    if stride != 16:
        raise DaeError(
            "animation output is not baked MAT4 matrices -- re-export from "
            "Mixamo with sampling/bake enabled"
        )
    return [
        [[values[i * 16 + r * 4 + c] for c in range(4)] for r in range(4)]
        for i in range(count)
    ]


def parse_collada(path):
    path = Path(path)
    root = ET.parse(str(path)).getroot()

    # --- animations -------------------------------------------------------
    sources = {s.get("id"): s for s in root.iter(_q("source"))}
    samplers = {s.get("id"): s for s in root.iter(_q("sampler"))}
    anim = {}  # node -> (times, [m4 per frame])
    for ch in root.iter(_q("channel")):
        target = ch.get("target") or ""
        node, sep, sid = target.partition("/")
        if not sep or sid not in ("matrix", "transform"):
            raise DaeError(
                f"channel target {target!r} is not baked matrix data "
                "(expected '<Node>/matrix') -- re-export from Mixamo with "
                "sampling/bake enabled"
            )
        sampler = samplers.get((ch.get("source") or "").lstrip("#"))
        if sampler is None:
            raise DaeError(f"channel target {target!r} references a missing sampler")
        inputs = {
            i.get("semantic"): (i.get("source") or "").lstrip("#")
            for i in sampler.findall(_q("input"))
        }
        for required in ("INPUT", "OUTPUT"):
            if required not in inputs or inputs[required] not in sources:
                raise DaeError(f"sampler for {node!r} is missing its {required} input")
        interp = inputs.get("INTERPOLATION")
        if interp:
            kind, vals = _source_arrays(sources[interp])
            bad = sorted({v for v in vals if v != "LINEAR"})
            if bad:
                raise DaeError(f"unsupported interpolation step(s) {bad} (only LINEAR)")
        times = _time_series(sources[inputs["INPUT"]])
        mats = _mat_series(sources[inputs["OUTPUT"]])
        if len(times) != len(mats):
            raise DaeError(f"channel {target!r}: {len(times)} times vs {len(mats)} matrices")
        anim[node] = (times, mats)

    if not anim:
        raise DaeError("no <channel> animations found in the DAE")

    # All Mixamo channels share one baked time grid; enforce it.
    base_node = next((n for n in ("Armature", "Root", "HumanoidRootNode") if n in anim), next(iter(anim)))
    times = anim[base_node][0]
    for node, (t, _) in anim.items():
        if len(t) != len(times) or max(abs(a - b) for a, b in zip(t, times)) > 1e-5:
            raise DaeError(
                f"channel {node!r} has a different sample grid than {base_node!r} -- "
                "non-uniform bakes are unsupported"
            )
    n_frames = len(times)
    dts = [b - a for a, b in zip(times, times[1:])]
    fps = round(1.0 / statistics.median(dts)) if dts else 0.0

    # --- visual scene node tree ------------------------------------------
    scenes = {vs.get("id"): vs for vs in root.iter(_q("visual_scene"))}
    scene_el = None
    ivs = root.find(f"{_q('scene')}/{_q('instance_visual_scene')}")
    if ivs is not None:
        scene_el = scenes.get((ivs.get("url") or "").lstrip("#"))
    if scene_el is None and scenes:
        scene_el = next(iter(scenes.values()))
    if scene_el is None:
        raise DaeError("no library_visual_scenes found")

    frames = {}
    static = {}

    def walk(el, _par):
        key = el.get("id") or el.get("sid") or el.get("name")
        if key:
            static[key] = _node_transform(el)
            frames[key] = anim.get(key, (None, None))[1]
        for child in el.findall(_q("node")):
            walk(child, key)

    for top in scene_el.findall(_q("node")):
        walk(top, None)

    # Nodes with no channel use their static visual-scene matrix for all frames.
    for node, mats in frames.items():
        if mats is None:
            if node not in static:
                raise DaeError(f"visual scene node {node!r} has no transform")
            frames[node] = [static[node]] * n_frames

    missing = sorted(n for n, mats in frames.items() if mats is None)
    if missing:
        raise DaeError(f"visual scene nodes missing animation data: {missing}")

    return {
        "name": path.stem,
        "times": times,
        "fps": float(fps),
        "frames": frames,  # node -> local 4x4 per frame (static nodes constant)
    }
