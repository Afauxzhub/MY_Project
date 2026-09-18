# Binding family adapter contracts

These files contain exceptional semantic name changes between whole rig
families. They are not generated for Vxx-to-Vyy updates.

Normal migration uses the source binding's six-layer membership, `rrGuid`,
same-layer stable names, and bind-relative local PRS against the source and
target neutral bindings. CBT1-to-CBT2 does not itself require OP_STD; use a
character/category OP_STD contract only for a reviewed exceptional semantic
bridge that the six-layer identity rules cannot express.

Character-specific filenames use:

`<Character>_<LOD|CS>_<source_family>_to_<target_family>.json`

A generic route may use:

`<source_family>_to_<target_family>.json`

Example payload:

```json
{
  "schema_version": 1,
  "kind": "binding_family_adapter_override",
  "source_family": "cbt1",
  "target_family": "cbt2",
  "objects": {
    "Legacy_Face_Smile_CTRL": "CTRL_Face_Smile",
    "Legacy_Cape_Bone_01": "Cape_Bone_01"
  }
}
```

Keep `objects` small. Add only reviewed semantic renames inside the tracked
layers. Do not copy every same-name node and do not put binding version numbers
in this contract. `Bones` renames must identify the intended weapon/ribbon
owner unambiguously so its constraint and animation transport remain paired.
