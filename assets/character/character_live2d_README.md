# character_live2d.psd layers

Canvas 1438×2576, 46 layers in total (bottom to top).

## 1. Body (27 layers, all shown normally, except those marked ★)
back_hair, topwear, leg_L, leg_R, foot_L, foot_R, bottomwear, arm_L, arm_R,
neck, ears, face, nose, mouth, ★mouth_open,
eyewhite_L, iris_L, eyelash_L, eyewhite_R, iris_R, eyelash_R, brow_L, brow_R,
★eye_closed_L, ★eye_closed_R, front_hair, hair_clip

- _L / _R mean the left / right side of the picture
- ★ hidden normally: eye_closed_* shows while blinking, mouth_open while talking

## 2. Expressions (9 layers, hidden normally, one at a time)
expr_happy, expr_surprised, expr_thinking, expr_sleepy, expr_worried,
expr_sad, expr_pout, expr_shy, expr_smug

Each covers the whole face, below the front hair.

## 3. Poses (6 layers, hidden normally, one at a time)
| Layer | Hide at the same time |
|---|---|
| pose_wave | arm_L |
| pose_point | arm_R |
| pose_chin | arm_L |
| pose_cheer | arm_L, arm_R |
| pose_reading | arm_L, arm_R |
| pose_parasol | arm_R |

Pose layers are on top and cover the front hair.

## 4. Walking (4 layers, hidden normally)
walk1 to walk4: full side-view walking frames. While walking, all layers above are hidden and the four frames take turns.
