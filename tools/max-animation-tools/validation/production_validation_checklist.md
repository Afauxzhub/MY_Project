# Reference Rig Production Validation Checklist

Run this checklist before enabling automatic rig updates for animators.

## Test Assets

Prepare at least:

- 3 representative characters using the current BIP-based rig.
- 20-50 existing animation files.
- One Freeform BIP animation.
- One Footstep BIP animation.
- One animation with IK blend/key usage.
- One weapon constrained to right-hand socket.
- One weapon switching between right hand, left hand, and back sockets.
- One rig update adding twist bones.
- One rig update adding ribbon bones or ribbon controls.
- One manifest migration that renames a stable weapon socket.

## Acceptance Tests

| Case | Expected Result |
| --- | --- |
| Open old BIP animation against newer rig | BIP keys remain unchanged and validator passes. |
| Freeform animation | Validator reports freeform/unknown mode and no fatal errors. |
| Footstep animation | Validator reports footstep mode and does not alter footsteps. |
| IK blend keys | Keys remain in the shot; no controller replacement occurs. |
| Add `HP_Back_Weapon` | Old shot opens, reports new additive socket, no animation loss. |
| Weapon Position/Orientation constraint | Target maps to current socket; weight keys remain on the same controller. |
| Weapon left/right/back switching | Target order is preserved or the report blocks unsafe relink. |
| Add twist bones | Twist system uses rig default drive; old shot does not receive generated twist keys. |
| Add ribbon bones | Ribbon controls appear in default pose and can be keyed after update. |
| Rename stable socket via manifest migration | Constraint relinks through migration and report lists the mapping. |
| Delete stable socket | Update reports an error and does not guess an alternative. |
| Missing BIP core node | Update stops before relinking. |
| Failed update | Backup file opens successfully and original shot is not overwritten. |

## Batch Validation

1. Open 3ds Max 2020.
2. Load `maxscript/ReferenceRigCore.ms`.
3. Load `maxscript/BatchValidate.ms`.
4. Run:

```maxscript
RR_BatchValidate.run @"D:\Project\Shots" @"D:\Project\Rig\Character_RigManifest_v001.json" @"D:\Project\Reports\ReferenceRig"
```

Review `ReferenceRig_BatchSummary.txt` and each per-shot report.

## Go/No-Go Criteria

Enable animator-facing updates only when:

- 95% or more of representative shots validate without errors.
- 100% of BIP core validation passes.
- Every failed constraint has a clear report entry.
- Backup and restore are tested on at least 5 updated shots.
- Binding artists have signed off the stable socket list.
