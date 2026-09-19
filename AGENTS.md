# Project guidance

## Project planning and task records

1. Treat `docs/project/overview.md` as the current project-stage and milestone summary.
2. Treat `docs/project/tasks.md` as the single task index. Do not maintain a separate backlog in chat.
3. Use one task for one coherent, reviewable outcome. Create a task card under `docs/project/tasks/` when work spans multiple sessions, systems, or validation steps.
4. Before implementation, record the goal, scope, authoritative references, dependencies, acceptance criteria, and required validation. Update the task status and handoff notes before ending the work session.
5. Keep durable decisions in their authoritative design or architecture document. Task cards reference those documents; they do not become a second design specification.
6. Use the statuses defined in `docs/project/tasks.md`. Mark work `Done` only after its stated acceptance criteria pass. Use `Awaiting Runtime Validation` when static work is complete but Unity, 3ds Max, animation, or gameplay validation is still outstanding.
7. Subagents are temporary helpers for bounded investigation, test, or review work. The primary task remains responsible for integration, validation, and updating the task record.
8. Do not let concurrent tasks edit the same files. Use separate Git worktrees for genuinely independent parallel implementation.
9. At the start of a task, inspect the worktree and relevant task record. At handoff, report completed work, validation performed, remaining runtime gaps, and the next concrete action.

The confirmed Unity editor baseline is Unity 6000.3.24f1 (Unity 6.3 LTS). `ProjectSettings/ProjectVersion.txt` becomes the repository source of truth after the Unity project is created. Do not silently upgrade it.

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
5. Never commit company assets, live user configuration, logs, reports, company paths, or internal server addresses. Personal project source assets under `ArtSource/` and game assets under `Client/Assets/` are allowed under `docs/production/asset-workflow.md`, including generated `.anim` and their stable `.meta` files. Keep game assets out of reusable `tools/` and `packages/`.
6. Preserve compatibility with 3ds Max 2020, Python 2.7, PySide2, and MaxScript unless an explicit migration is approved.

Static validation is not a substitute for a real 3ds Max and Unity acceptance pass. State the runtime verification boundary explicitly.

## Personal asset production

1. Read `docs/production/asset-workflow.md` before adding assets, changing naming or directories, configuring import/export, or changing LFS rules.
2. Record skeleton-specific decisions in `docs/production/characters/Player.md` (or the corresponding character record). An unconfirmed bone name is not an import default to invent.
3. Keep DCC source files in `ArtSource/`, published animation FBX in `Client/Assets/Art/Animations`, and extracted clips in `Client/Assets/Generated/AnimationClips`. Generated clips are overwritten by publishing; author gameplay metadata separately.
4. Preserve `.meta` files and stable asset names on re-export. Large binary source/assets use Git LFS; `.meta`, scenes, Prefabs, and configuration remain text unless an explicit file-specific policy says otherwise.
5. Run `Tools > MY Project > Validate Asset Workflow` after changing shared asset settings. This checks structure/configuration, not real FBX correctness or animation quality. Actual Max-to-Unity acceptance belongs to ANIM-001.

## Reusable Unity gameplay packages

For third-person locomotion or Timeline-authored abilities:

1. Read `docs/architecture/company-reference-reuse-review.md` first.
2. Use `packages/com.afauxzhub.character-locomotion` as the source of truth for camera-relative movement intent and heading math.
3. Use `packages/com.afauxzhub.timeline-abilities` as the source of truth for Timeline authoring, compilation, and runtime instruction scheduling.
4. Keep input, camera, collision motor, animation playback, and combat policy behind project adapters. Do not add company project types or paths to either reusable package.
5. Timeline ability code must continue to follow `docs/design/combat/player-combat-spec.md` and `docs/design/combat/integration-contracts.md`. Timeline schedules accepted actions; it does not own resource payment, hit-stun permission, cancellation priority, or skill-link state.
6. Keep animation timing and gameplay windows independently tunable. Treat all greybox values as data, not permanent constants.

Static package checks do not prove Unity import, Timeline authoring, character movement feel, camera behavior, or animation blending. Report those runtime gaps explicitly.
