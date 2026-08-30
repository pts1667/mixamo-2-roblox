# mixamo-2-roblox

Convert Mixamo animations to Roblox.
Instead of complicated setups, this is just a straight `.dae` -> `.rbxmx` conversion.
This only works for R15 rigs, and will produce a `KeyframeSequence` you can then use in your animations.
Requires Python 3.8+

- Input: Mixamo **Collada (.dae)** exports of the R15 rig template (baked matrix animation).
- Output: Roblox **`.rbxmx` `KeyframeSequence`** — one keyframe per Mixamo sample, LINEAR interpolation.
- Every conversion runs a built-in **forward-kinematics self-check** (generated poses are compared against the raw Mixamo joint positions, tolerance 0.001 studs) plus a **round-trip check** of the written file, and refuses to emit a bad animation.

## Instructions

0. Install Python 3.8 or newer
1. Clone/unzip this repo; click the '< > Code' button at top of this page -> 'Download ZIP' and extract somewhere
2. In Mixamo, 'UPLOAD CHARACTER' -> upload the provided `Rig_and_Attachments_Template_CLEAN.fbx` -> 'NEXT'
3. Select whatever animation you want, click 'DOWNLOAD'
4. In the download window, 'Format': 'Collada(.dae)', 'Skin': 'Without Skin', 'Frames per Second': '30', 'Keyframe Reduction': 'none'

You should now have a Mixamo animation as a Collada `.dae`. We will now convert this to a `KeyframeSequence`:

5. In the folder you extracted the ZIP to (should have a `README.md`), right click an empty space -> 'Open in Terminal'
6. run:

   ```sh
   python src/convert.py "<YOUR ANIMATION>.dae"
   ```

   For `Silly Dancing.dae`, this writes `Silly Dancing.rbxmx` next to the input and prints the self-check result, e.g.:

   ```
   Silly Dancing.dae: 116 keyframes @ 30 fps, 3.867s, FK max error 9.91e-05 studs -> Silly Dancing.rbxmx (round-trip 9.91e-05)
   ```

   Multiple files and common options:

   ```sh
   # convert several clips at once
   python src/convert.py "Silly Dancing.dae" "Capoeira.dae"

   # collect outputs into one folder, named clip, Action priority, non-looping
   python src/convert.py "Silly Dancing.dae" --out animations --name "Silly Dancing" --priority action --no-loop

   # halve the keyframe count (every 2nd sample; 30 -> 15 fps)
   python src/convert.py "Silly Dancing.dae" --fps 15
   ```

You should now have your `KeyframeSequence` in `.rbxmx` format, which is XML data for Roblox.

In Roblox Studio:
7. Right-click any object in Explorer (i.e. `Workspace`), 'Insert' -> 'Import Roblox Model'
8. Select your `.rbxmx` keyframe sequence

You can use raw `KeyframeSequence` objects in scripts. But for the animation editor, you will need to Save to Roblox:
9. When imported, right click your new `KeyframeSequence` -> 'Save / Export' -> 'Save to Roblox...'
10. Fill out and click 'Save'
11. In 'Avatar' -> 'Clip Editor', '...' -> 'Import' -> 'From Roblox...' and select your `KeyframeSequence`

You now have the full Mixamo animation loaded in the Clip Editor!

## Troubleshooting

- **"skeleton mismatch" error** — the `.dae` was not exported from the R15 template rig. Make sure you uploaded the provided FBX to Mixamo.
- **"not baked matrix data" / self-check failure** — the export was not sampled. In the Mixamo download dialog use 'Keyframe Reduction': 'none' and 'Frames per Second': '30'.
- **Character floats or sinks** — see `--root-y-offset` above.

**-- USELESS DETAILS BELOW --**

## Command-line reference

```
python src/convert.py INPUT.dae [INPUT2.dae ...] [options]
```

| Option | Default | Description |
|---|---|---|
| `--out DIR` | next to each input | Output directory for the `.rbxmx` files |
| `--name NAME` | input file stem | Clip name (`KeyframeSequence.Name`); single input only |
| `--rig PATH` | `rig/Rig_and_Attachments_Template_CLEAN.gltf` | Rig template glTF providing the rest pose |
| `--fps N` | 0 (keep all) | Keep every Nth sample to hit this rate, e.g. `15` or `10` |
| `--loop` / `--no-loop` | `--loop` | `KeyframeSequence.Loop` |
| `--priority {core,action,movement,idle}` | `core` | `AnimationPriority` (`core` = 1000, as in Studio-authored clips) |
| `--hip-height F` | 2.0 | `AuthoredHipHeight` metadata |
| `--root-xz {frame0,zero,raw}` | `frame0` | Hip XZ translation filter (see below) |
| `--root-y {frame0,none}` | `frame0` | Hip Y translation filter (see below) |
| `--root-y-offset F` | 0.0 | Additive hip Y offset in studs (grounding fine-tune) |
| `--rig-data {keep,omit}` | `keep` | Keep the `AnimationRigData` item (Animation Editor metadata) or omit it |
| `--no-check` | off | Skip the FK self-check and round-trip verification |

## Root motion & grounding

The generated poses follow the same convention as Studio-authored clips (e.g. the classic walk export): the `HumanoidRootPart` pose stays identity with `Weight 0`, and the whole-character motion (hip translation + rotation) is baked into the `LowerTorso` pose. The filters control how much of Mixamo's root motion is kept:

- `--root-xz frame0` (default) — the clip plays **in place**, anchored at its first frame. Use `raw` to keep forward/side travel, `zero` to remove it entirely.
- `--root-y frame0` (default) — vertical hip bob is kept **relative to the first frame**. `none` removes it.
- `--root-y-offset` — nudge the whole clip up/down in studs. If the character **floats or sinks** by a constant amount in Studio, re-run with `--root-y-offset` set to minus that amount (e.g. floats 0.4 studs -> `--root-y-offset -0.4`).

The root **rotation** (dances that turn) is always kept.

## License

[MIT](LICENSE)
