r"""Read the R15 rig template glTF: the rest pose used by the retarget.

Only node TRS/matrix data is used; the .bin buffer (inverse bind matrices)
is not needed. Units are studs; hips sit at the origin. The template's
Armature (+90 deg X) and Root (-90 deg X) nodes cancel, so rest worlds are
composed strictly below "HumanoidRootNode".

The template node "HumanoidRootNode" corresponds to the Roblox part
"HumanoidRootPart" (the name used in rbxmx Pose hierarchies).
"""

import json
from pathlib import Path

from matrix import identity4, mat4_from, mul4, quat_to_mat3

GLTF_TO_RIG = {"HumanoidRootNode": "HumanoidRootPart"}
RIG_TO_GLTF = {v: k for k, v in GLTF_TO_RIG.items()}

RIG_BONES = [
    "HumanoidRootPart",
    "LowerTorso",
    "UpperTorso",
    "Head",
    "LeftUpperArm",
    "LeftLowerArm",
    "LeftHand",
    "RightUpperArm",
    "RightLowerArm",
    "RightHand",
    "LeftUpperLeg",
    "LeftLowerLeg",
    "LeftFoot",
    "RightUpperLeg",
    "RightLowerLeg",
    "RightFoot",
]

ROOT_EXCLUDE = "HumanoidRootNode"

DEFAULT_RIG = Path(__file__).resolve().parents[1] / "rig" / "Rig_and_Attachments_Template_CLEAN.gltf"


def _node_local(node):
    if "matrix" in node:
        # glTF matrices are column-major
        f = [float(v) for v in node["matrix"]]
        return [[f[c * 4 + r] for c in range(4)] for r in range(4)]
    t = [float(v) for v in node.get("translation", (0.0, 0.0, 0.0))]
    q = [float(v) for v in node.get("rotation", (0.0, 0.0, 0.0, 1.0))]
    s = [float(v) for v in node.get("scale", (1.0, 1.0, 1.0))]
    r = quat_to_mat3(*q)
    rs = [[r[i][j] * s[j] for j in range(3)] for i in range(3)]  # T @ R @ S
    return mat4_from(rs, t)


def parse_gltf(path):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = data["nodes"]
    local = {n["name"]: _node_local(n) for n in nodes}
    parent = {}
    for n in nodes:
        for c in n.get("children", ()):
            parent[nodes[c]["name"]] = n["name"]

    def world_under(name):
        # Compose from `name` up to but excluding ROOT_EXCLUDE; the excluded
        # root itself composes to the identity.
        m = identity4()
        while name is not None and name != ROOT_EXCLUDE:
            m = mul4(local[name], m)
            name = parent.get(name)
        return m

    rest_world = {}
    for bone in RIG_BONES:
        gname = RIG_TO_GLTF.get(bone, bone)
        if gname not in local:
            raise ValueError(f"rig template {path} has no node {gname!r} for bone {bone!r}")
        rest_world[bone] = world_under(gname)  # identity for HumanoidRootPart

    return {
        "path": str(path),
        "local": local,            # glTF node name -> local 4x4 (studs)
        "parent": parent,          # glTF node name -> glTF parent name (or None)
        "rest_world": rest_world,  # Roblox bone name -> world 4x4 under HumanoidRootNode
        "bones": list(RIG_BONES),
    }
