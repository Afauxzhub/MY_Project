# 单角色左右侧视图 v06

生成方式：内置 imagegen，使用用户已认可的正背面作为共同参考。

## 参考版本

- 正面：../v04/front-character.png
- 背面：../v05/back-character.png
- 本轮仅生成两个侧视图；不改动以上已确认图片。

## 输出

- left-character.png：角色自身左侧，面向画面左方；左腰红色飘带、侧链及帽羽毛在近侧可见。
- right-character.png：角色自身右侧，面向画面右方；左侧飘带与羽毛根部遵循远侧遮挡，不将其镜像复制到右侧。

单角色、无武器、白底；以同一A-Pose的侧投影为目标。生成结果为建模概念参考，局部花纹、衣摆及体型投影尚非严格几何一致，待用户验收。

## 最终提示词

### left

Use case: identity-preserve. Create a single orthographic SIDE-VIEW character modeling reference using TWO APPROVED images: image 1 is the authoritative FRONT and image 2 is the authoritative BACK of the SAME adult Victorian noble female knight. These designs are accepted: rotate this character, do not redesign her. One character alone, no weapons or equipment display, no collage. Portrait 1024x1536 composition, full body from feather tip to boot soles, character centered horizontally, same scale between the two side views, feather top about y=15 and boot soles about y=1495. True orthographic camera at exact 90 degrees to front, level and zero perspective, head/torso/pelvis all strict profile, no three-quarter turn.
Preserve the same neutral modeling A-POSE in world space: upper arms abducted approximately 35 degrees from torso in the frontal plane, elbows straight, hands relaxed, legs straight slightly apart. In strict side projection arms naturally overlap and foreshorten; do NOT pose an arm forward or bend an elbow to show costume, no contrapposto, no movement. Neutral expression.
Exact materials and identity: pale adult woman, white/silver hair in the reference braided low bun, refined black tricorn with deep-red edging and red feather on CHARACTER'S ANATOMICAL LEFT, tall black collar, white front neck cravat, short black leather shoulder cape with a smooth tailored silver-trimmed lower edge and narrow crimson underside (NO wavy ruffles). Fitted black/crimson long leather coat, dark embossed pattern, restrained silver details, gloves and tall boots as reference.
IMPORTANT approved construction: the crossed leather belts belong to the FRONT INNER vest and are concealed beneath outer coat at the back; do not wrap a belt or harness across outer back. Hat silver badge exists ONLY at front/left-front, NEVER duplicate onto back or opposite side. The back cape bears a small simple silver diamond, not a large branching ornament. The coat hem is long to lower calf, with elongated pointed sides and center hem following the approved BACK reference; do not shorten to knee, do not invent short rear tails. Keep physically plausible cloth thickness and lining: dark outer coat from rear, red lining only at front opening or naturally turned edge.
Flat white empty background, even neutral diffuse material inspection illumination, photorealistic PBR leather and metal matching references. No cast shadow, scenery, dramatic lights, floor, text, marks, watermark or detached accessories.

THIS IMAGE: anatomical LEFT side visible, nose points toward LEFT edge of canvas. The character's LEFT-side red feather is on the NEAR side and must be prominent, attached correctly to the tricorn and sweeping backward. Show the existing front-left hat ornament only where naturally visible on the front portion; no rear duplicate. Critical: preserve the small DARK-RED patterned CLOTH RIBBON at the LEFT waist/hip seen on image-right in front reference and image-left in back reference. It is a real fabric hanging strip with a tapered/angled tip down to upper-to-mid thigh, beside the existing silver hip chain/tassel. It is on the NEAR side of this view: include a clearly readable exposed portion, even if the forearm naturally occludes part of it. Do not omit it, turn it into another chain, hide all of it inside coat, duplicate it or change arm pose to reveal it. Its attachment and layering must reconcile both approved views.

### right

Use case: identity-preserve. Create a single orthographic SIDE-VIEW character modeling reference using TWO APPROVED images: image 1 is the authoritative FRONT and image 2 is the authoritative BACK of the SAME adult Victorian noble female knight. These designs are accepted: rotate this character, do not redesign her. One character alone, no weapons or equipment display, no collage. Portrait 1024x1536 composition, full body from feather tip to boot soles, character centered horizontally, same scale between the two side views, feather top about y=15 and boot soles about y=1495. True orthographic camera at exact 90 degrees to front, level and zero perspective, head/torso/pelvis all strict profile, no three-quarter turn.
Preserve the same neutral modeling A-POSE in world space: upper arms abducted approximately 35 degrees from torso in the frontal plane, elbows straight, hands relaxed, legs straight slightly apart. In strict side projection arms naturally overlap and foreshorten; do NOT pose an arm forward or bend an elbow to show costume, no contrapposto, no movement. Neutral expression.
Exact materials and identity: pale adult woman, white/silver hair in the reference braided low bun, refined black tricorn with deep-red edging and red feather on CHARACTER'S ANATOMICAL LEFT, tall black collar, white front neck cravat, short black leather shoulder cape with a smooth tailored silver-trimmed lower edge and narrow crimson underside (NO wavy ruffles). Fitted black/crimson long leather coat, dark embossed pattern, restrained silver details, gloves and tall boots as reference.
IMPORTANT approved construction: the crossed leather belts belong to the FRONT INNER vest and are concealed beneath outer coat at the back; do not wrap a belt or harness across outer back. Hat silver badge exists ONLY at front/left-front, NEVER duplicate onto back or opposite side. The back cape bears a small simple silver diamond, not a large branching ornament. The coat hem is long to lower calf, with elongated pointed sides and center hem following the approved BACK reference; do not shorten to knee, do not invent short rear tails. Keep physically plausible cloth thickness and lining: dark outer coat from rear, red lining only at front opening or naturally turned edge.
Flat white empty background, even neutral diffuse material inspection illumination, photorealistic PBR leather and metal matching references. No cast shadow, scenery, dramatic lights, floor, text, marks, watermark or detached accessories.

THIS IMAGE: anatomical RIGHT side visible, nose points toward RIGHT edge of canvas. Genuine opposite side of the SAME character, NOT a horizontally mirrored left-side design. The dark-red waist RIBBON and main hip chain are on the ANATOMICAL LEFT, now the FAR side: do NOT place or duplicate them prominently on this near right hip. Respect occlusion, only a small far-side glimpse if actually exposed. The red hat feather is likewise rooted on the FAR anatomical left side; its upper/back plume may remain visible beyond hat silhouette but the attachment is hidden by crown. Do NOT invent a second near-side feather or copy the left-front hat badge onto the right or rear. Preserve same hat volume and feather shape as reference, with physically correct far-side occlusion.
