# Project guidance

## Combat design source of truth

For work involving player combat, combat resources, skills, builds, animation requirements, combat programming architecture, enemy attacks, Boss actions, or combat AI:

1. Use the project skill at `.agents/skills/combat-design/SKILL.md`.
2. Treat `docs/design/combat/player-combat-spec.md` as the authoritative player-combat specification.
3. Use `docs/design/combat/integration-contracts.md` when translating the design into code, animation requests, Boss actions, or AI behavior.
4. Follow `docs/design/combat/maintenance-rules.md` whenever an accepted design rule is added, changed, deprecated, or replaced.

Do not silently reinterpret or overwrite a rule marked `[CONFIRMED]`. If requested work conflicts with one, identify the rule ID and obtain explicit design approval before changing the specification or derived work.

## Animation toolchain

For work involving the personal 3ds Max animation tools, Unity animation export package, Root Motion publishing, FBX import, animation curve processing, binding migration, or Max-to-Unity integration:

1. Read `docs/tools/animation-tools-porting.md` before editing.
2. Treat `tools/max-animation-tools` as the Max source package; do not edit an installed copy under the 3ds Max user profile as the source of truth.
3. Treat `packages/com.afauxzhub.animation-pipeline` as the reusable Unity package.
4. Check both sides whenever the request-file path, JSON fields, Unity `Assets/` path conversion, or another cross-tool contract changes.
5. Never commit live user configuration, logs, reports, generated animation assets, company paths, internal server addresses, or project assets.
6. Preserve compatibility with 3ds Max 2020, Python 2.7, PySide2, and MaxScript unless an explicit migration is approved.

Static validation is not a substitute for a real 3ds Max and Unity acceptance pass. State the runtime verification boundary explicitly.
