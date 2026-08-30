r"""Emit Roblox .rbxmx KeyframeSequence files; parse them back for the
round-trip check.

The format mirrors scripts/example-anims/walk.rbxmx (Roblox-authored):
- <roblox version="4"> header with ExplicitAutoJoints / External lines.
- KeyframeSequence with minimal properties (AuthoredHipHeight, Loop, Priority,
  Name); boilerplate (GuidBinaryString, AttributesSerialize, Tags, ...) is
  omitted on purpose, and so is the <SharedStrings> section (no dangling
  references since the Tags properties are omitted too).
- One Keyframe per baked sample (the last one named "End", as the Animation
  Editor does), each holding the full 16-part Pose tree.
- HumanoidRootPart pose: identity CFrame, Weight 0. All other poses: Weight 1,
  EasingStyle/EasingDirection 0 (samples are already densely baked, LINEAR).
- The AnimationRigData Item is inserted verbatim from animation_rig_data.xml
  (extracted byte-for-byte from walk.rbxmx).
"""

import xml.etree.ElementTree as ET
from math import isfinite
from pathlib import Path
from xml.sax.saxutils import escape

RIG_DATA_PATH = Path(__file__).resolve().parent / "animation_rig_data.xml"

ROOT_BONE = "HumanoidRootPart"

# Pose hierarchy nesting, in walk.rbxmx child order.
POSE_CHILDREN = {
    "HumanoidRootPart": ["LowerTorso"],
    "LowerTorso": ["UpperTorso", "LeftUpperLeg", "RightUpperLeg"],
    "UpperTorso": ["LeftUpperArm", "RightUpperArm", "Head"],
    "LeftUpperArm": ["LeftLowerArm"],
    "LeftLowerArm": ["LeftHand"],
    "RightUpperArm": ["RightLowerArm"],
    "RightLowerArm": ["RightHand"],
    "LeftUpperLeg": ["LeftLowerLeg"],
    "LeftLowerLeg": ["LeftFoot"],
    "RightUpperLeg": ["RightLowerLeg"],
    "RightLowerLeg": ["RightFoot"],
    "Head": [],
    "LeftHand": [],
    "RightHand": [],
    "LeftFoot": [],
    "RightFoot": [],
}


def _fmt(x):
    x = float(x)
    if not isfinite(x):
        raise ValueError(f"non-finite value in clip: {x!r}")
    return "%.9g" % x


def write_rbxmx(path, clip, *, hip_height=2.0, loop=True, priority=1000,
                include_rig_data=True):
    rig_data = RIG_DATA_PATH.read_text(encoding="utf-8").rstrip("\n")
    # The verbatim block carries a <SharedString name="Tags"> property that
    # references the <SharedStrings> section this writer intentionally omits;
    # strip those lines so the file has no dangling shared-string references
    # (Studio reports unresolvable ones as "file is corrupted").
    rig_data = "\n".join(
        line for line in rig_data.splitlines() if "<SharedString name=" not in line
    )
    lines = []
    add = lines.append
    counter = 0

    def next_ref():
        nonlocal counter
        r = f"RBX{counter:032X}"
        counter += 1
        return r

    add(
        '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" '
        'version="4">'
    )
    add('\t<Meta name="ExplicitAutoJoints">true</Meta>')
    add("\t<External>null</External>")
    add("\t<External>nil</External>")
    add(f'\t<Item class="KeyframeSequence" referent="{next_ref()}">')
    add("\t\t<Properties>")
    add(f'\t\t\t<float name="AuthoredHipHeight">{_fmt(hip_height)}</float>')
    add(f"\t\t\t<bool name=\"Loop\">{'true' if loop else 'false'}</bool>")
    add(f"\t\t\t<token name=\"Priority\">{int(priority)}</token>")
    add(f"\t\t\t<string name=\"Name\">{escape(clip['name'])}</string>")
    add("\t\t</Properties>")

    def emit_pose(bone, depth, poses):
        R, t = poses[bone]
        weight = 0 if bone == ROOT_BONE else 1
        ind = "\t" * depth
        add(f'{ind}<Item class="Pose" referent="{next_ref()}">')
        add(f"{ind}\t<Properties>")
        add(f'{ind}\t\t<CoordinateFrame name="CFrame">')
        for tag, v in (("X", t[0]), ("Y", t[1]), ("Z", t[2])):
            add(f"{ind}\t\t\t<{tag}>{_fmt(v)}</{tag}>")
        for r in range(3):
            for c in range(3):
                add(f"{ind}\t\t\t<R{r}{c}>{_fmt(R[r][c])}</R{r}{c}>")
        add(f"{ind}\t\t</CoordinateFrame>")
        add(f'{ind}\t\t<token name="EasingDirection">0</token>')
        add(f'{ind}\t\t<token name="EasingStyle">0</token>')
        add(f'{ind}\t\t<float name="Weight">{weight}</float>')
        add(f"{ind}\t\t<string name=\"Name\">{bone}</string>")
        add(f"{ind}\t</Properties>")
        for child in POSE_CHILDREN[bone]:
            emit_pose(child, depth + 1, poses)
        add(f"{ind}</Item>")

    n_frames = len(clip["frames"])
    for i, frame in enumerate(clip["frames"]):
        add(f'\t\t<Item class="Keyframe" referent="{next_ref()}">')
        add("\t\t\t<Properties>")
        add(f"\t\t\t\t<float name=\"Time\">{_fmt(frame['time'])}</float>")
        add(f"\t\t\t\t<string name=\"Name\">{'End' if i == n_frames - 1 else 'Keyframe'}</string>")
        add("\t\t\t</Properties>")
        emit_pose(ROOT_BONE, 3, frame["poses"])
        add("\t\t</Item>")

    if include_rig_data:
        add(rig_data)
    add("\t</Item>")
    add("</roblox>")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_rbxmx(path):
    """Parse a KeyframeSequence .rbxmx back into clip data."""
    root = ET.parse(str(path)).getroot()
    ks = root.find("Item[@class='KeyframeSequence']")
    if ks is None:
        raise ValueError(f"{path}: no KeyframeSequence item")
    props = ks.find("Properties")

    def prop(name):
        el = props.find(f"*[@name='{name}']")
        return el.text if el is not None else None

    frames = []
    for kf in ks.findall("Item[@class='Keyframe']"):
        kprops = kf.find("Properties")
        time = float(kprops.find("float[@name='Time']").text)
        poses = {}

        def collect(item):
            p = item.find("Properties")
            bone = p.find("string[@name='Name']").text
            cf = p.find("CoordinateFrame[@name='CFrame']")

            def g(tag):
                return float(cf.find(tag).text)

            poses[bone] = ([[g(f"R{r}{c}") for c in range(3)] for r in range(3)],
                           [g("X"), g("Y"), g("Z")])
            for child in item.findall("Item[@class='Pose']"):
                collect(child)

        top = kf.find("Item[@class='Pose']")
        if top is not None:
            collect(top)
        frames.append({"time": time, "poses": poses})

    return {
        "name": prop("Name"),
        "loop": (prop("Loop") or "").lower() == "true",
        "priority": int(prop("Priority") or 0),
        "frames": frames,
    }
