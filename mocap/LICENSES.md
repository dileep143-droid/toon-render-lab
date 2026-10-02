# Motion-capture licences (files fetched by `fetch_mocap.py`)

## What is in this folder

19 BVH clips (13.6 MB) listed with their CMU subject/trial numbers in `mocap/index.json`, plus `CMU_BVH_READMEFIRST.txt`
(Bruce Hahne's notes that ship with the BVH conversion).

## 1. Carnegie Mellon University Graphics Lab Motion Capture Database

Source: http://mocap.cs.cmu.edu/ (read 2026-10-02). The front page says, verbatim:

> This dataset of motions is free for all uses.

> This data is free for use in research projects. You may include this data in commercially-sold products, but you may
> not resell this data directly, even in converted form. If you publish results obtained using this data, we would
> appreciate it if you would send the citation to your published paper to jkh+mocap@cs.cmu.edu, and also would add this
> text to your acknowledgments section: The data used in this project was obtained from mocap.cs.cmu.edu. The database was
> created with funding from NSF EIA-0196217.

What this means for us: animation made from these clips may be used in monetised videos (a video is a product that
*includes* the data). We must **not** sell or re-publish the BVH files themselves as a motion pack. A credit line
"Motion capture: CMU Graphics Lab Motion Capture Database (mocap.cs.cmu.edu)" in the video description is a courtesy,
not a requirement.

## 2. The BVH conversion (Bruce Hahne / cgspeed, 2010 "MotionBuilder-friendly" release)

Original location: https://sites.google.com/a/cgspeed.com/cgspeed/motion-capture/cmu-bvh-conversion
Mirror we download from (file-by-file over HTTPS): https://github.com/una-dinosauria/cmu-mocap - its README says it "is a
copy of the CMU mocap dataset in bvh format, as ported by Bruce Hahne" and points to READMEFIRST.txt for the terms.
READMEFIRST.txt (saved here as `CMU_BVH_READMEFIRST.txt`), "USAGE RIGHTS", verbatim:

> CMU places no restrictions on the use of the original dataset, and I (Bruce) place no additional restrictions on the
> use of this particular BVH conversion.
>
> Here's the relevant paragraph from mocap.cs.cmu.edu:
>
>   Use this data!  This data is free for use in research and commercial projects worldwide. [...]

(The CMU wording quoted in section 1 is the current one; it adds the "may not resell this data directly, even in
converted form" condition, which we follow.)

Technical notes for retargeting: frame 1 of every file is a T-pose added by the conversion (skip it); the T-pose faces
+Z with Y up; 120 fps (`Frame Time: .0083333`); length unit is the CMU ASF unit (about 0.057 m - hips stand ~17.3 units
high); joint names are MotionBuilder style (`Hips, LeftUpLeg, LeftLeg, LeftFoot, Spine, Spine1, Neck, Neck1, Head,
LeftShoulder, LeftArm, LeftForeArm, LeftHand, ...`). The finger/thumb joints carry no captured data.

## 3. Other motion datasets checked and NOT used

| dataset | licence | verdict |
|---|---|---|
| Ubisoft La Forge LAFAN1 (github.com/ubisoft/ubisoft-laforge-animation-dataset) | CC BY-NC-ND 4.0 ("can be used under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0") | excluded - non-commercial |
| Bandai Namco Research Motiondataset 1 & 2 (github.com/BandaiNamcoResearchInc/Bandai-Namco-Research-Motiondataset) | CC BY-NC 4.0 | excluded - non-commercial |
| 100STYLE (zenodo.org/records/8127870, Ian Mason) | CC BY 4.0 | allowed commercially **with attribution**; not auto-downloaded (multi-GB zip, Xsens skeleton, 60 fps). Optional manual add; credit "100STYLE dataset, Mason et al., CC BY 4.0". |
| Mixamo (Adobe) | Adobe terms, no redistribution of the raw files | not used (cannot be put in a public repo) |
