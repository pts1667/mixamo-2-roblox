# mixamo-2-roblox

Convert Mixamo animations to Roblox
Instead of complicated setups, this is just a straight .dae -> .rbxmx conversion.
This only works for R15 rigs, and will produce a `KeyframeSequence` you can then use in your animations.

# Instructions

1. Clone/unzip this repo
2. In Mixamo, 'UPLOAD CHARACTER' -> upload the provided `Rig_and_Attachments_Template_CLEAN.fbx` -> 'NEXT'
3. Select whataver animation you want, click 'DOWNLOAD'
4. In the download window, 'Format': 'Collada(.dae)', 'Skin': 'Without Skin', 'Frames per Second': '30', 'Keyframe Reduction': 'none'

You should now have Maximo animation as a Collada .dae. We will now convert this to a `KeyframeSequence`:
5. (script conversion instructions)

You should now have your `KeyframeSequence` in `.rbxmx` format, which is XML data for Roblox.

In Roblox Studio:
6. Right-click any object in Explorer (i.e. `Workspace`), 'Insert' -> 'Import Roblox Model'
7. Select your `.rbxmx` keyframe sequence

You can use raw `KeyframeSequence` objects in scripts. But for the animation editor, you will need to Save to Roblox:
8. When imported, right click your new `KeyframeSequence` -> 'Save / Export' -> 'Save to Roblox...'
9. Fill out and click 'Save'
10. In 'Avatar' -> 'Clip Editor', '...' -> 'Import' -> 'From Roblox...' and select your `KeyframeSequence`

You now have the full Maximo animation loaded in the Clip Editor!