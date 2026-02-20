# reCAPTCHA Solving Guide

When a visual reCAPTCHA challenge appears (image grid with "Select all images with X"), solve it using coordinate clicks. **Don't give up — keep solving until it passes.**

## Grid layout

reCAPTCHA grids are either 3×3 or 4×4. To find exact cell coordinates:

1. **Screenshot** the page — grid position varies per site
2. **Crop the grid area** (see crop endpoint) to see cells up close
3. **Calculate cell centers**: identify grid top-left corner and cell size from the screenshot

Typical 3×3 grid: ~400px wide, cells ~133px each. But always verify with crop/aim.

## Recognition rules

- **Partial objects count**: If only part of a car/bus/crosswalk is visible in a cell, **select it**. reCAPTCHA expects you to click any cell containing even a small piece of the target.
- **Images are intentionally noisy/blurry**: Use the **crop endpoint** to zoom into individual cells if unsure.
- **After selecting cells, new ones may appear**: reCAPTCHA replaces selected cells with new images. Check if new images also contain the target — select those too.
- **"Click verify once there are none left"**: Keep selecting matching cells until no more appear, then click VERIFY.
- **"Please try again"** / "Please select all matching images": You missed some cells. Look more carefully — partial objects, small/distant objects, ambiguous cells.

## Crop endpoint — zoom into regions

```bash
# Crop a region and zoom 2x (default)
curl "http://localhost:9377/tabs/TAB_ID/crop?userId=main&x=560&y=120&w=400&h=400" -o grid.png

# Crop a single cell with 3x zoom for detail
curl "http://localhost:9377/tabs/TAB_ID/crop?userId=main&x=560&y=120&w=133&h=133&scale=3" -o cell.png
```

Parameters: `x, y` = top-left corner, `w, h` = size, `scale` = zoom factor (default 2).

## Solving workflow

1. **Screenshot** → identify the reCAPTCHA grid and task ("Select all images with X")
2. **Crop the full grid** → zoom in to see all cells clearly
3. **If unsure about specific cells** → crop individual cells at 3x zoom
4. **Calculate click coordinates** for matching cells (center of each cell)
5. **Aim** → verify crosshairs land inside the correct cells
6. **Click** all matching cells (including partial objects)
7. **Screenshot** → check if new cells appeared (replacements)
8. **If new matching cells** → click those too
9. **Click VERIFY** button
10. **If "Please try again"** → you missed cells. Look for partial/distant objects
11. **Repeat** until passed or new challenge appears

## Tips

- Better to over-select than under-select — reCAPTCHA is more forgiving of extra clicks than missed ones
- Distant/tiny objects still count (e.g., a car far away in the background)
- Traffic lights include the pole, crosswalks include the painted lines even if faded
- Buses/trucks count as vehicles, motorcycles/scooters are separate from cars
- When in doubt, select the cell
