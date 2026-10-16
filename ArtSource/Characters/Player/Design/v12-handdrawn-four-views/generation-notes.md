# 左视图发型与链条修订 v12

使用内置 imagegen 编辑 v11/left.png，以 v11/back.png 的脑后盘发为参考。旧版保留。

- 脑后发型由密集小辫结改为较连贯的盘绕发髻侧面，简化外轮廓及内部发束。
- 删除手腕后方伸到飘带外侧的多余链圈，保留前方垂挂吊坠及飘带。

本轮仅更新 left.png；其他三图原样复制 v11。三次局部生成后已目视检查，发型为侧投影近似表达，不是严格三维投影。右视图等尚未同步本轮改动；未测试 Tripo。

## 初次提示词

Use case: precise-object-edit. Image 1 is the LEFT PROFILE EDIT TARGET. Image 2 is the authoritative BACK HAIRSTYLE reference. Output ONE full-body LEFT PROFILE.
Only TWO local corrections:
1 HAIRSTYLE behind ear: replace the current lumpy bunch of small bead/grape-like braids behind the ear in image 1 (roughly x460..515,y155..215) with the correct SIDE projection of the hairstyle in image 2. Image 2 has a centered low coiled chignon at the back of skull: one coherent round braided coil at the occiput/nape, broad smooth curved locks gathered from the sides, neat wrapped braid around central bun, not a cluster of independent round beads. Render that same centrally placed back bun viewed from exact LEFT side: a compact shallow oval/flattened dome protruding slightly behind the head, with a few broad curved interwoven sections to suggest the coiled braid. Its circular rosette face points BACKWARD, so it must be FORESHORTENED/mostly edge-on in this side view, not pasted as a full rear-facing circle on the side of head. Preserve skull shape, visible ear, face, front wisps, hat, feather and simplified diamond hat badge. Pale gray smooth hand-drawn locks, no dense strand noise. Match bun height/size beneath hat and above collar to back reference.
2 EXTRA CHAIN LOOP: remove the entire stray U-shaped chain/loop that emerges BEHIND the wrist/cuff and extends onto/outside the hanging cloth ribbon at image-right of wrist (roughly x494..532,y651..716). Replace with uninterrupted pale ribbon/coat surface. There must be NO curved metal line or dangling fitting behind the wrist outside the ribbon, and no chain loop encircling arm or wrist. Preserve the separate FRONT-OF-HAND vertical hip pendant at roughly x408,y550..702 and its short attachment links, and preserve the long cloth ribbon, its folds, outline and pointed ends. Where a remaining short chain reaches the occluding arm/ribbon it disappears behind it instead of reappearing as a rear loop.
All other image-1 details remain fixed: exact left-facing head profile, neutral expression, full-body A-pose side projection, anatomy, screen position/scale, hands, clothing, waist belt hidden under coat, long coat hem, boots, line weight and very light grayscale hand-drawn shading. No new ornaments, dark fill, texture, text, marks, weapons or collage. White background.

## 发型细化

Precise local hairstyle correction ONLY.
IMAGE 1 is EDIT TARGET: the full-body LEFT profile, with unwanted wrist chain already removed. IMAGE 2 is authoritative BACK hair reference.
Replace ALL existing bubbly, grape-like small braid lumps behind the ear in image 1. They are wrong. Redraw this region as the SIDE of the coherent centrally coiled chignon in image 2: smooth hair gathered backward along skull, one flattened compact oval bun centered at the BACK of head above nape, a simple broad braid wrapping around the bun, 3 or 4 long sweeping curved sections at most in side projection. Show the bun EDGE-ON: smooth convex rear silhouette and elongated curved bands, NOT round bead clusters, NOT many circular lumps, NOT a full rear-facing rosette facing the side camera. The bun should read as a single orderly pinned coil, not a bunch of grapes or a side braid. Use fewer, longer, wider flowing hair shapes with minimal light-gray shading. In image 1 the ONLY edit region is approximately x452..516,y148..221 on 1024x1536 canvas. Keep ear and jaw outlines intact, and preserve little loose tendril in front of ear.
Everything else in image 1 MUST remain unchanged, including hat, diamond badge, feather, face, neck, pose, cuffs, hip pendant, ribbon, absent chain behind wrist, coat, boots, framing and pale-gray style. No new chain loops or hairstyle ornaments. Output the same full-body image, not a head closeup, with no annotations.

## 最终发型修订

Edit image 1. Completely REPAINT the hair bun behind the ear, not a subtle retouch. Replace the current bumpy many-lobed hair cluster with a SMOOTH PINNED COIL: one sleek oval chignon at back of skull above collar, with a single broad curved sweep wrapping around it and only TWO OR THREE long flowing internal lines. The outer bun contour must be one smooth curve with NO small round bumps. Remove all grape/bead shapes and all little braided ovals. Image 2 explains that the bun is at the center BACK of the head, not on the side; show a narrow foreshortened SIDE profile of that rear-centered coil, with its rosette surface facing away from viewer. The bun is about the same height as the ear, slightly behind it, not taller than before. Retain a narrow subtle braid only at far rear edge if needed, not a mass of separate lumps.
Keep all other image-1 pixels as unchanged as possible: ear, face, loose cheek strand, hat, feather, diamond badge, costume, pose, hip pendant, cloth ribbon, absent extra chain loop behind wrist, white background, pale grayscale style. Full body image as before, do not crop. No text.
