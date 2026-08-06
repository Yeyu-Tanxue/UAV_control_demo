# Manual rail-area annotation with Labelme

The working label is one polygon named `ego_track_area`. It must cover the area
between the left and right rails of the track connected to the camera's near
field. At a turnout, follow continuity from the lower image center; do not choose
a neighboring line merely because it is visually clearer.

## Prepare

```powershell
python tools\prepare_labelme_rail_review.py prepare
```

The generated workspace is under
`output/manual-annotations/railgoerl24_winter_labelme`. Images are hard-linked,
while JSON annotations are independent. Re-running without `--overwrite`
preserves manual edits.

## Review order

1. Complete `train` (136 images).
2. Complete `val` (32 images).
3. Review `test` (32 images) last and never use it for training or tuning.

For every image:

1. Correct the existing polygon, or draw one when the model missed.
2. Keep exactly one polygon named `ego_track_area`.
3. Tick the image flag `reviewed`.
4. Save, then move to the next image.

Do not include neighboring tracks. For an occlusion, follow the two visible rails
and interpolate through the obstruction; do not cut a person or object out of
the track-area polygon.

## Check progress

```powershell
python tools\prepare_labelme_rail_review.py status
```

The check writes `annotation_status.csv` and rejects a reviewed image unless it
contains exactly one valid `ego_track_area` polygon.
