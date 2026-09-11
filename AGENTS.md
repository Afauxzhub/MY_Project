# Project guidance

## Combat design source of truth

For work involving player combat, combat resources, skills, builds, animation requirements, combat programming architecture, enemy attacks, Boss actions, or combat AI:

1. Use the project skill at `.agents/skills/combat-design/SKILL.md`.
2. Treat `docs/design/combat/player-combat-spec.md` as the authoritative player-combat specification.
3. Use `docs/design/combat/integration-contracts.md` when translating the design into code, animation requests, Boss actions, or AI behavior.
4. Follow `docs/design/combat/maintenance-rules.md` whenever an accepted design rule is added, changed, deprecated, or replaced.

Do not silently reinterpret or overwrite a rule marked `[CONFIRMED]`. If requested work conflicts with one, identify the rule ID and obtain explicit design approval before changing the specification or derived work.

