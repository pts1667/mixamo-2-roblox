r"""Retarget Mixamo DAE matrix animation onto the R15 template rig.

Math (validated against direct Mixamo world joint positions to <1e-3 studs):

- rest_w[nm]: template rest world under HumanoidRootNode (glTF; the template's
  Armature +90 deg X / Root -90 deg X nodes cancel, and HumanoidRootNode is
  this rig's HumanoidRootPart).
- A[nm]: animated world under HumanoidRootNode for each DAE frame (the
  Armature/Root/HRN nodes above it are handled as root motion).
- D[nm] = A[nm].R @ rest_w[nm].R^T: world rotation delta, template axes.
- Non-root joint pose rotation = S (D[parent]^T D[nm]) S with S = diag(-1,1,-1)
  (template space faces +Z/left=+X; Roblox faces -Z/left=-X). Pose translation
  is exactly zero for every joint except LowerTorso.
- Root motion: the Armature node carries the uniform unit scale (~100) times
  the character-root transform; strip the scale, fold Root/HRN in, conjugate
  by S. Following walk.rbxmx, the HumanoidRootPart pose stays identity with
  Weight 0 and the root motion is baked into the LowerTorso pose:
  LowerTorso pose = [rootR @ S D[LowerTorso] S | t].

Self-check: forward-kinematics the generated poses and compare against the
direct Mixamo world positions (scale-stripped Armature chain, conjugated) for
all 15 non-root joints. FK uses the validated world-delta semantics: rotations
accumulate relative to rest (Wr[HRP] = I, Wr[c] = Wr[p] @ poseR[c]) and joint
offsets are rest world positions applied in world axes.
"""

from matrix import (
    column_scale,
    conj_s3,
    conj_s_vec,
    identity3,
    identity4,
    mat4_from,
    mul3,
    mul4,
    mul_vec3,
    orthonormalize3,
    rot3,
    trans3,
    transpose3,
)
from rig_read import GLTF_TO_RIG, RIG_TO_GLTF

SKELETON_TOL = 1e-3  # studs; bone-offset guard
FK_TOL = 1e-3        # studs; FK self-check hard fail

# Non-root bones, parents before children (HumanoidRootPart is emitted
# separately as the identity tree root with Weight 0).
ORDER = [
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


class ConversionError(ValueError):
    pass


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _prepare_rig(rig):
    """Per-bone rest data in Roblox axes: rig parent and rest joint position."""
    parents = {}
    for bone in rig["bones"]:
        gname = RIG_TO_GLTF.get(bone, bone)
        parent_g = rig["parent"].get(gname)
        parent_rb = GLTF_TO_RIG.get(parent_g, parent_g)
        if bone != "HumanoidRootPart" and parent_rb not in rig["bones"]:
            raise ConversionError(
                f"unexpected rig hierarchy at {bone!r} (parent {parent_rb!r})"
            )
        parents[bone] = parent_rb
    rp = {bone: conj_s_vec(trans3(rig["rest_world"][bone])) for bone in rig["bones"]}
    return {"parent": parents, "rp": rp}


def _frame_worlds(rig, dae, f, scale):
    """For DAE frame f return (Mroot, A):
    Mroot = scale-stripped Armature @ Root @ HumanoidRootNode (glTF axes),
    A[glTF name] = animated world under HumanoidRootNode."""
    frames = dae["frames"]
    m = frames["Armature"][f]
    arm_r = orthonormalize3([[m[i][j] / scale for j in range(3)] for i in range(3)])
    arm_t = [m[i][3] / scale for i in range(3)]
    mroot = mul4(
        mat4_from(arm_r, arm_t),
        mul4(frames["Root"][f], frames["HumanoidRootNode"][f]),
    )
    A = {"HumanoidRootNode": identity4()}
    for bone in rig["bones"]:  # parents-first order
        gname = RIG_TO_GLTF.get(bone, bone)
        if gname == "HumanoidRootNode":
            continue
        loc = frames[gname][f]
        pg = rig["parent"].get(gname)
        A[gname] = mul4(A[pg], loc) if pg in A else loc
    return mroot, A


def _deltas(rig, A):
    """D[glTF name] = A.R @ rest_w.R^T for every rig bone."""
    D = {}
    for bone in rig["bones"]:
        gname = RIG_TO_GLTF.get(bone, bone)
        rw = rot3(rig["rest_world"][bone])
        D[gname] = mul3(rot3(A[gname]), transpose3(rw))
    return D


def _fk_positions(pre, poses):
    r"""World-delta FK (the validated pose semantics): rotations accumulate
    relative to rest (Wr[HRP] = I, Wr[c] = Wr[p] @ poseR[c], so Wr telescopes
    to the world rotation delta D), and joint offsets are rest world
    positions applied in world axes. At rest every pose is the identity and
    X reproduces the template rest positions exactly."""
    Wr = {"HumanoidRootPart": identity3()}
    X = {"HumanoidRootPart": [0.0, 0.0, 0.0]}
    for bone in ORDER:
        R, t = poses[bone]
        p = pre["parent"][bone]
        Wr[bone] = mul3(Wr[p], R)
        off = _add(_sub(pre["rp"][bone], pre["rp"][p]), t)
        X[bone] = _add(X[p], mul_vec3(Wr[p], off))
    return X


def fk_error(rig, dae, pose_frames, indices=None, relative=False):
    """Max joint-position error (studs) between the forward kinematics of
    `pose_frames` (list of {bone: (R, t)}) and the direct Mixamo world
    positions over all 15 non-root joints.

    relative=True compares positions relative to the LowerTorso joint, which
    cancels any whole-character translation (e.g. the root-motion filters)."""
    pre = rig.setdefault("_prepared", _prepare_rig(rig))
    n = len(dae["times"])
    indices = list(range(n)) if indices is None else list(indices)
    scale = column_scale(dae["frames"]["Armature"][0])
    worst = 0.0
    for k, f in enumerate(indices):
        mroot, A = _frame_worlds(rig, dae, f, scale)
        Xd = {}
        for bone in rig["bones"]:
            gname = RIG_TO_GLTF.get(bone, bone)
            Xd[bone] = conj_s_vec(trans3(mul4(mroot, A[gname])))
        Xf = _fk_positions(pre, pose_frames[k])
        base_f = Xf["LowerTorso"]
        base_d = Xd["LowerTorso"]
        for bone in ORDER:
            a = Xf[bone]
            b = Xd[bone]
            if relative:
                a = _sub(a, base_f)
                b = _sub(b, base_d)
            worst = max(worst, max(abs(a[i] - b[i]) for i in range(3)))
    return worst


def build_clip(
    rig,
    dae,
    *,
    name,
    root_xz="frame0",
    root_y="frame0",
    root_y_offset=0.0,
    check=True,
):
    """Build the retargeted clip.

    Returns {name, fps, times, indices, frames, fk_error} where frames is a
    list of {bone: (R3x3, t3)} in Roblox part names, one per DAE sample, with
    the root-motion filters applied to the LowerTorso pose translation.
    """
    pre = rig.setdefault("_prepared", _prepare_rig(rig))
    frames = dae["frames"]
    n = len(dae["times"])

    required = [RIG_TO_GLTF.get(b, b) for b in rig["bones"]] + ["Armature", "Root"]
    missing = sorted({g for g in required if g not in frames})
    if missing:
        raise ConversionError(
            f"DAE is missing rig node(s) {missing} -- was it exported from the "
            "R15 template rig? ('mixamorig:*' node names mean the wrong "
            "skeleton was uploaded to Mixamo; re-upload "
            "scripts/rig/Rig_and_Attachments_Template_CLEAN.fbx)"
        )

    # Skeleton guard: bone local translations must be constant and equal to
    # the template locals (Mixamo preserved the rig; fail loudly otherwise).
    for bone in rig["bones"]:
        gname = RIG_TO_GLTF.get(bone, bone)
        gl_t = trans3(rig["local"][gname])
        worst = 0.0
        for f in range(n):
            t = trans3(frames[gname][f])
            worst = max(worst, max(abs(t[i] - gl_t[i]) for i in range(3)))
        if worst > SKELETON_TOL:
            raise ConversionError(
                f"skeleton mismatch ({bone}): bone offset deviates by "
                f"{worst:.2e} studs from the template -- this DAE was not "
                "exported from the R15 template rig; re-upload "
                "scripts/rig/Rig_and_Attachments_Template_CLEAN.fbx to Mixamo"
            )

    scale = column_scale(frames["Armature"][0])
    if scale <= 0.0:
        raise ConversionError("Armature node has a degenerate scale")

    frames_raw = []  # root translation unfiltered (used for the FK check)
    t0 = None
    for f in range(n):
        mroot, A = _frame_worlds(rig, dae, f, scale)
        rootR = conj_s3(rot3(mroot))
        rootT = conj_s_vec(trans3(mroot))
        if f == 0:
            t0 = rootT
        D = _deltas(rig, A)
        poses = {"HumanoidRootPart": (identity3(), [0.0, 0.0, 0.0])}
        for bone in ORDER:
            gname = RIG_TO_GLTF.get(bone, bone)
            if bone == "LowerTorso":
                # The HRP-relative pose would cancel the root motion; fold it
                # back in so the HumanoidRootPart pose can stay identity.
                R = mul3(rootR, conj_s3(D[gname]))
                t = rootT
            else:
                pg = pre["parent"][bone]
                R = conj_s3(mul3(transpose3(D[RIG_TO_GLTF.get(pg, pg)]), D[gname]))
                t = [0.0, 0.0, 0.0]
            poses[bone] = (R, t)
        frames_raw.append(poses)

    err = fk_error(rig, dae, frames_raw) if check else None
    if err is not None and err > FK_TOL:
        raise ConversionError(
            f"FK self-check failed: max error {err:.3e} studs (tolerance {FK_TOL:.0e})"
        )

    def _filter(t):
        if root_xz == "frame0":
            x, z = t[0] - t0[0], t[2] - t0[2]
        elif root_xz == "zero":
            x = z = 0.0
        else:  # raw
            x, z = t[0], t[2]
        y = (t[1] - t0[1] if root_y == "frame0" else 0.0) + root_y_offset
        return [x, y, z]

    frames_out = []
    for f, poses in enumerate(frames_raw):
        p2 = dict(poses)
        R, t = poses["LowerTorso"]
        p2["LowerTorso"] = (R, _filter(t))
        frames_out.append({"time": dae["times"][f], "poses": p2})

    return {
        "name": name,
        "fps": dae["fps"],
        "times": list(dae["times"]),
        "indices": list(range(n)),
        "frames": frames_out,
        "fk_error": err,
    }
