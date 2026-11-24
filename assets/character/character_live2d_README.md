# character_live2d.psd 图层说明

画布 1438×2576，共 46 个图层（从下到上）。

## 1. 本体（27 层，平时全部显示，除了标 ★ 的）
back_hair, topwear, leg_L, leg_R, foot_L, foot_R, bottomwear, arm_L, arm_R,
neck, ears, face, nose, mouth, ★mouth_open,
eyewhite_L, iris_L, eyelash_L, eyewhite_R, iris_R, eyelash_R, brow_L, brow_R,
★eye_closed_L, ★eye_closed_R, front_hair, hair_clip

- _L / _R 指画面上的左边 / 右边
- ★ 平时隐藏：眨眼时显示 eye_closed_*，说话时显示 mouth_open

## 2. 表情（9 层，平时隐藏，一次只显示一个）
expr_happy, expr_surprised, expr_thinking, expr_sleepy, expr_worried,
expr_sad, expr_pout, expr_shy, expr_smug

整块盖在五官上，位于前发下面。

## 3. 动作（6 层，平时隐藏，一次只显示一个）
| 图层 | 显示时要同时隐藏 |
|---|---|
| pose_wave | arm_L |
| pose_point | arm_R |
| pose_chin | arm_L |
| pose_cheer | arm_L、arm_R |
| pose_reading | arm_L、arm_R |
| pose_parasol | arm_R |

动作层在最上面，盖住前发。

## 4. 走路（4 层，平时隐藏）
walk1 ~ walk4：完整的侧身走路帧，播放时隐藏上面所有图层，四帧轮流显示。
