using System;
using System.Linq;
using Afauxzhub.CharacterLocomotion;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    public static class MotionAuthoringValidation
    {
        [MenuItem("Tools/MY Project/Animation/Validate Authoring Workflow (no source writes)")]
        public static void Run() => Debug.Log(RunChecks());
        public static string RunChecks()
        {
            if (Application.isPlaying) throw new InvalidOperationException("Exit Play first.");
            int count = 0;
            void Check(bool condition, string label) { if (!condition) throw new InvalidOperationException("Authoring check: " + label); count++; }
            bool Throws(Action action) { try { action(); return false; } catch (Exception) { return true; } }
            var scene = EditorSceneManager.NewPreviewScene();
            var root = new GameObject("Synthetic binding model") { hideFlags = HideFlags.HideAndDontSave }; SceneManager.MoveGameObjectToScene(root, scene);
            new GameObject("Bone").transform.SetParent(root.transform, false);
            var library = ScriptableObject.CreateInstance<MotionLibrary>(); library.model = root;
            var movement = ScriptableObject.CreateInstance<LocomotionProfile>(); library.relaxedMovement = movement;
            var a = new AnimationClip { name = "Hero_Run" }; var b = new AnimationClip { name = "Hero_Run" };
            a.SetCurve("Bone", typeof(Transform), "localPosition.x", AnimationCurve.Linear(0, 0, 1, 1));
            b.SetCurve("WrongBone", typeof(Transform), "localPosition.x", AnimationCurve.Linear(0, 0, 1, 1));
            try
            {
                Check(MotionAuthoringTools.Coverage(library).rows.Length == 136, "empty library reports all 136 base and optional selectors");
                Check(MotionCatalog.AddMissing(library) == 136 && MotionCatalog.AddMissing(library) == 0, "catalog migration is idempotent");
                Check(library.entries.Count(e => e.optional) == 50, "48 gait refinements and 2 idle variations optional");
                Check(!library.Validate().Any(), "missing clips are not configuration errors");
                Check(MotionAuthoringTools.Audit(root, a).Compatible && !MotionAuthoringTools.Audit(root, b).Compatible, "binding paths checked");
                Check(!MotionAuthoringTools.Audit(null, a).Compatible, "missing model fails closed");
                var entry = library.entries.First(e => e.stance == WeaponStance.Sheathed && e.slot == MotionSlot.Run);
                string before = EditorJsonUtility.ToJson(library);
                var proposals = MotionAuthoringTools.Propose(library, new[] { a, b }, WeaponStance.Sheathed, "Hero_");
                Check(proposals.Count == 1 && proposals[0].selected == -1, "duplicate names require explicit selection");
                Check(EditorJsonUtility.ToJson(library) == before, "scan never changes draft");
                proposals[0].apply = true;
                Check(Throws(() => MotionAuthoringTools.Apply(library, proposals, false)), "unresolved candidate rejected");
                proposals[0].selected = 1;
                Check(Throws(() => MotionAuthoringTools.Apply(library, proposals, false)) && entry.clip == null, "bad binding applies nothing");
                proposals[0].selected = 0;
                Check(MotionAuthoringTools.Apply(library, proposals, false) == 1 && entry.clip == a && entry.review == MotionReview.Pending, "explicit confirm writes pending draft");
                entry.clip = b;
                Check(Throws(() => MotionAuthoringTools.Apply(library, proposals, false)) && entry.clip == b, "old clip overwrite protected");
                Check(MotionAuthoringTools.Apply(library, proposals, true) == 1 && entry.clip == a, "explicit overwrite works");
                entry.review = MotionReview.Approved; entry.reviewedFingerprint = "old fingerprint";
                Check(MotionAuthoringTools.Status(library, entry).StartsWith("Review stale"), "changed asset review stale");
                entry.review = MotionReview.Placeholder; Check(MotionAuthoringTools.Status(library, entry) == "Placeholder", "placeholder distinct");
                entry.enabled = false; Check(MotionAuthoringTools.Status(library, entry) == "Disabled", "disabled distinct"); entry.enabled = true;
                var free = new MotionEntry { slot = MotionSlot.Run, clip = a, mode = MotionMode.Free }; library.entries.Add(free);
                Check(library.Find(0, MotionSlot.Run, MotionGait.Run, MotionDirection.Any, MotionMode.Free, 4, 0, out _) == free, "mode variant beats shared");
                Check(library.Find(0, MotionSlot.Run, MotionGait.Run, MotionDirection.Any, MotionMode.Targeting, 4, 0, out _) == entry, "target mode cannot leak free variant");
                free.minimumSpeed = 5; Check(library.Find(0, MotionSlot.Run, MotionGait.Run, MotionDirection.Any, MotionMode.Free, 4, 0, out _) == entry, "speed applicability selects shared fallback");
                free.minimumSpeed = 0; free.minimumAngle = 45;
                Check(library.Find(0, MotionSlot.Run, MotionGait.Run, MotionDirection.Any, MotionMode.Free, 6, 0, out _) == entry, "angle applicability");
                entry.referenceSpeed = 4; entry.matchPlaybackToSpeed = true;
                Check(Mathf.Abs(entry.PlaybackScale(6, .5f, 1.25f) - 1.25f) < .001f, "speed matching clamped");
                entry.matchPlaybackToSpeed = false; Check(entry.PlaybackScale(6, .5f, 1.5f) == 1, "speed matching opt in");
                entry.contactAuthored = true; entry.leftContact = AnimationCurve.Constant(0, 1, 1); entry.rightContact = AnimationCurve.Constant(0, 1, 0);
                var support = library.Support(new[] { entry.Sample(.7f, .8f, true) });
                Check(support.Authored && support.StopSlot(.7f) == MotionSlot.StopLeft, "authored support overrides phase guess");
                support = library.Support(new[] { entry.Sample(.7f, .2f, true) });
                Check(!support.Authored && support.StopSlot(.7f) == MotionSlot.StopRight, "unknown majority explicitly estimated");
                entry.leftContact = AnimationCurve.Constant(0, 1, 2); Check(library.Validate().Any(), "invalid contact curve rejected"); entry.contactAuthored = false;
                var turn = library.entries.First(e => e.stance == WeaponStance.Sheathed && e.slot == MotionSlot.TurnInPlaceRight); turn.clip = a; turn.stageSeconds = .7f;
                Check(Mathf.Abs(library.PhaseDuration(LocomotionPhase.TurnInPlaceRight, 0, MotionGait.Run, MotionMode.Free, MotionDirection.Any, MotionSlot.StopLeft, 0, 90, .3f) - .7f) < .001f, "stage duration override used");
                var recipe = new MotionRecipe { fromMode = MotionMode.Free, toMode = MotionMode.Targeting }; library.overrides.Add(recipe);
                Check(library.Resolve(MotionFamily.Idle, MotionFamily.Idle, 0, MotionGait.Run, MotionDirection.Any, MotionMode.Free, MotionMode.Targeting, out _) == recipe, "mode transition recipe selected");
                Check(library.Resolve(MotionFamily.Idle, MotionFamily.Idle, 0, MotionGait.Run, MotionDirection.Any, MotionMode.Targeting, MotionMode.Free, out _) == null, "mode recipe direction enforced");
                movement.turnInterrupt = float.NaN; Check(library.Validate().Any(), "invalid turn interrupt rejected"); movement.turnInterrupt = .25f;
                var dynamics = new LocomotionDynamics();
                void Step(float speed, float angle, float dt = .02f, bool grounded = true) => dynamics.Step(speed, angle, false, grounded, dt, 12, 16, .2f, .3f, .45f, .3f, 140, 75, 1, .08f, .2f, true, true, 60, .35f, .5f, .25f);
                Step(0, 90); Check(dynamics.Phase == LocomotionPhase.TurnInPlaceRight && dynamics.Speed == 0, "stationary right turn");
                Step(5, 90); Check(dynamics.TurningInPlace && dynamics.Speed == 0, "turn input waits interrupt threshold");
                Step(5, 90, .1f); Check(dynamics.Phase == LocomotionPhase.Start, "turn input interruption starts moving");
                dynamics.Reset(); Step(0, -180); Check(dynamics.Phase == LocomotionPhase.PivotInPlaceLeft, "stationary left pivot");
                dynamics.CancelTurn(); Check(dynamics.Phase == LocomotionPhase.Idle, "target loss cancels stationary turn");
                dynamics.Reset(); Step(0, 90); Step(0, 0, .4f); Check(dynamics.Phase == LocomotionPhase.Idle, "turn completes once");
                dynamics.Reset(); Step(5, 0, 1); Step(5, 0, 1); Step(5, 90); Step(0, 0, .1f); Check(dynamics.Phase == LocomotionPhase.Stop, "moving turn release interruption");
                dynamics.Reset(); Step(0, 90); Step(0, 90, .02f, false); Check(dynamics.Phase == LocomotionPhase.Fall, "air overrides facing turn");
                Check(Throws(() => MotionCharacterWizard.Preflight(null, null, "Assets/../Bad", false)), "wizard rejects traversal");
                Check(Throws(() => MotionCharacterWizard.Preflight(null, null, "Assets/Scripts", false)), "wizard refuses existing directory");
                Check(Throws(() => MotionCharacterWizard.Preflight(root, null, "Assets/NewSynthetic", false)), "wizard refuses scene model");
                var report = MotionAuthoringTools.Coverage(library);
                Check(JsonUtility.FromJson<MotionCoverageReport>(JsonUtility.ToJson(report)).rows.Length == 137, "report round trip includes custom variant");
                Check(MotionAuthoringTools.CoverageText(report).Contains("OPTIONAL"), "report distinguishes optional requirements");
                var idleChoice = new MotionEntry { slot = MotionSlot.Idle, clip = a };
                var walkChoice = new MotionEntry { slot = MotionSlot.Walk, clip = a };
                var runChoice = new MotionEntry { slot = MotionSlot.Run, clip = a };
                Check(MotionWorkbench.ResolvePreviewIndex(new[] { idleChoice, walkChoice, runChoice }, runChoice.id, 1) == 2, "filling earlier slot preserves preview selection");
                Check(MotionWorkbench.ResolvePreviewIndex(new[] { runChoice }, runChoice.id, 2) == 0, "removing earlier slots preserves preview selection");
                Check(MotionWorkbench.ResolvePreviewIndex(new[] { runChoice, idleChoice }, runChoice.id, 1) == 0, "reordering preserves preview selection");
                Check(MotionWorkbench.ResolvePreviewIndex(new[] { idleChoice }, runChoice.id, 2) == 0, "missing selected entry clamps fallback");
                Check(MotionWorkbench.ResolvePreviewIndex(new[] { idleChoice, runChoice }, "", 1) == 1, "old window without ID retains valid index");
                Check(MotionWorkbench.ResolvePreviewIndex(Array.Empty<MotionEntry>(), runChoice.id, 1) == -1, "empty preview list safe");
                return "PASS " + count + " authoring assertions; synthetic data, no visual acceptance.";
            }
            finally { Object.DestroyImmediate(library); Object.DestroyImmediate(movement); Object.DestroyImmediate(a); Object.DestroyImmediate(b); EditorSceneManager.ClosePreviewScene(scene); }
        }
    }
}
