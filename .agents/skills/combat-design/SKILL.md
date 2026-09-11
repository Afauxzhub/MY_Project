---
name: combat-design
description: Apply and maintain this project's player-combat rules when designing combat code, animation requirements, skills and builds, enemy attacks, Boss actions, or combat AI.
---

# Combat Design

Use the project's combat specification as the source of truth. Do not reproduce the full design in this skill.

## Required sources

- Always read [`player-combat-spec.md`](../../../docs/design/combat/player-combat-spec.md) completely before doing combat-related design or implementation work.
- Read [`integration-contracts.md`](../../../docs/design/combat/integration-contracts.md) when producing program architecture, data structures, state machines, animation requirements, enemy attacks, Boss actions, AI, or test cases.
- Read [`maintenance-rules.md`](../../../docs/design/combat/maintenance-rules.md) before changing an accepted rule or adding a new one.

## Apply the specification

Preserve the distinction between:

- `[CONFIRMED]`: accepted design invariants. Do not change or contradict them without explicit user approval.
- `[TUNING]`: accepted structural direction whose values require greybox testing. Keep values data-driven and do not present them as final.
- `[OPEN]`: unresolved decisions. Do not silently fill them in when the choice would affect combat behavior.

Reference stable rule IDs in program plans, animation briefs, Boss specifications, AI behavior, and test cases. Keep the specification authoritative instead of copying its rules into multiple documents.

## Route the task

### Program framework

Translate the resource lifecycle, settlement order, action state, cancellation priority, and combat events from the specification into data-driven systems. Explicitly identify which rule IDs each subsystem implements.

### Animation requirements

Specify readable anticipation, active frames, recovery, cancellation points, attack/counter windows, movement or root-motion needs, hit reactions, and transition requirements. Separate animation timing from gameplay timing when the latter must remain tunable.

### Boss actions and AI

Design attacks around the player's full resource loop. State whether an attack can be blocked, dodged, seen through, repelled, or countered; whether its sequence continues; and what telegraph communicates the decision. Do not make every attack solvable by the same response.

### Design revision

Before changing the design, identify the affected rule IDs and derived contracts. After explicit approval, update the authoritative specification first, record the change, then update affected integration contracts or implementation requirements.

## Boundaries

- Do not reintroduce the retired terms `弹反`, `一闪`, or `GP` as current mechanic names. Use `弹开`, `反击`, and `强化反击`.
- Do not add anti-repeat penalties to repeated L1 counter attempts merely to prevent that play style; successful repeated tight-timing counters are intentionally rewarded.
- Do not convert greybox estimates into permanent constants.
- Do not claim code, animation, Boss, or runtime validation unless that validation was actually performed.

