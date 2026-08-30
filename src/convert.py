r"""Mixamo DAE -> Roblox .rbxmx animation converter.

Converts Mixamo Collada exports of the R15 rig template into Roblox
KeyframeSequence files. See the module docstrings of rig_read / dae_read /
retarget / rbxmx_write for the pipeline stages.

Usage (from the repo root):
    python src/convert.py "Silly Dancing.dae"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dae_read
import rbxmx_write
import retarget
import rig_read

FK_TOL = 1e-3  # studs; hard fail threshold for the self-checks

PRIORITY = {"idle": 0, "movement": 1, "action": 2, "core": 1000}


def convert_one(rig, inp, out_dir, args):
    dae = dae_read.parse_collada(inp)
    name = args.name or inp.stem
    out_path = out_dir / f"{name}.rbxmx"

    clip = retarget.build_clip(
        rig,
        dae,
        name=name,
        root_xz=args.root_xz,
        root_y=args.root_y,
        root_y_offset=args.root_y_offset,
    )

    step = 1
    if args.fps:
        if dae["fps"] <= 0:
            raise SystemExit(f"{inp}: cannot subsample --fps {args.fps} (source fps unknown)")
        step = max(1, round(dae["fps"] / args.fps))
    if step > 1:
        clip["frames"] = clip["frames"][::step]
        clip["times"] = clip["times"][::step]
        clip["indices"] = clip["indices"][::step]

    if not args.no_check:
        if clip["fk_error"] > FK_TOL:
            raise SystemExit(
                f"{inp}: FK self-check failed: max error {clip['fk_error']:.3e} studs "
                f"(tolerance {FK_TOL:.0e}) -- refusing to write output"
            )

    rbxmx_write.write_rbxmx(
        out_path,
        clip,
        hip_height=args.hip_height,
        loop=args.loop,
        priority=PRIORITY[args.priority],
        include_rig_data=args.rig_data == "keep",
    )

    err2 = None
    if not args.no_check:
        back = rbxmx_write.read_rbxmx(out_path)
        # The written file carries the user-selected root-motion filters, which
        # translate the whole character; compare positions relative to the
        # LowerTorso joint so the check is filter-invariant.
        err2 = retarget.fk_error(
            rig,
            dae,
            [f["poses"] for f in back["frames"]],
            indices=clip["indices"],
            relative=True,
        )
        if err2 > FK_TOL:
            raise SystemExit(
                f"{inp}: round-trip check failed: max error {err2:.3e} studs "
                f"(tolerance {FK_TOL:.0e}) -- {out_path} does not round-trip"
            )

    duration = clip["times"][-1] + (1.0 / dae["fps"] if dae["fps"] > 0 else 0.0)
    msg = (
        f"{inp.name}: {len(clip['frames'])} keyframes @ {dae['fps']:g} fps, "
        f"{duration:.3f}s, FK max error {clip['fk_error']:.2e} studs -> {out_path}"
    )
    if err2 is not None:
        msg += f" (round-trip {err2:.2e})"
    print(msg)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="convert.py",
        description="Convert Mixamo .dae animations of the R15 rig into Roblox .rbxmx KeyframeSequence files.",
        epilog=(
            "Root-motion options follow the walk.rbxmx convention: the HumanoidRootPart "
            "pose stays identity (Weight 0) and hip translation/rotation are baked into "
            "the LowerTorso pose. If the character floats or sinks by a constant offset "
            "in Studio, re-run with --root-y-offset set to minus that offset in studs."
        ),
    )
    ap.add_argument("inputs", nargs="+", help="Mixamo .dae file(s) (baked matrix animation)")
    ap.add_argument("--out", help="output directory (default: next to each input)")
    ap.add_argument(
        "--name",
        help="clip name (default: input file stem; only valid with a single input)",
    )
    ap.add_argument("--rig", default=str(rig_read.DEFAULT_RIG), help="R15 template .gltf (rest pose)")
    ap.add_argument(
        "--fps",
        type=float,
        default=0.0,
        help="keep every Nth sample to hit this rate, e.g. 15 or 10 (default 0 = keep all samples)",
    )
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--loop", dest="loop", action="store_true", default=True, help="Loop=true (default)")
    group.add_argument("--no-loop", dest="loop", action="store_false", help="Loop=false")
    ap.add_argument(
        "--priority",
        choices=sorted(PRIORITY),
        default="core",
        help="AnimationPriority (default core=1000, as in walk.rbxmx)",
    )
    ap.add_argument("--hip-height", type=float, default=2.0, help="AuthoredHipHeight (default 2.0)")
    ap.add_argument(
        "--root-xz",
        choices=["frame0", "zero", "raw"],
        default="frame0",
        help="hip XZ translation: frame0 = relative to first frame (in place, default); "
        "zero = none; raw = keep Mixamo travel",
    )
    ap.add_argument(
        "--root-y",
        choices=["frame0", "none"],
        default="frame0",
        help="hip Y translation: frame0 = relative to first frame (default); none = none",
    )
    ap.add_argument(
        "--root-y-offset",
        type=float,
        default=0.0,
        help="additive hip Y offset in studs (grounding fine-tune, default 0)",
    )
    ap.add_argument(
        "--rig-data",
        choices=["keep", "omit"],
        default="keep",
        help="AnimationRigData item: keep (default; its dangling Tags "
        "reference is stripped) or omit entirely if Studio still rejects "
        "the file",
    )
    ap.add_argument(
        "--no-check",
        action="store_true",
        help="skip FK self-check and round-trip verification",
    )
    args = ap.parse_args(argv)

    if args.name and len(args.inputs) > 1:
        ap.error("--name is only valid with a single input")
    if any(not inp.lower().endswith(".dae") for inp in args.inputs):
        ap.error("inputs must be .dae files")

    rig = rig_read.parse_gltf(args.rig)
    for inp in args.inputs:
        inp = Path(inp)
        if not inp.is_file():
            raise SystemExit(f"input not found: {inp}")
        out_dir = Path(args.out) if args.out else inp.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        convert_one(rig, inp, out_dir, args)


if __name__ == "__main__":
    main()
