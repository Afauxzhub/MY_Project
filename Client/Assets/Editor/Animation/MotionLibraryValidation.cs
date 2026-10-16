using System;
using System.Collections.Generic;
using System.Linq;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    public static class MotionLibraryValidation
    {
        [MenuItem("Tools/MY Project/Animation/Validate No-Wires Core (no scene save)")]
        public static void Run() => Debug.Log(RunChecks());
        public static string RunChecks()
        {
            if (Application.isPlaying) throw new InvalidOperationException("Run core checks outside Play.");
            int count = 0; void Check(bool condition, string text) { if (!condition) throw new InvalidOperationException("No-wires: " + text); count++; }
            var library = ScriptableObject.CreateInstance<MotionLibrary>();
            var templates = ScriptableObject.CreateInstance<MotionRecipeTemplates>(); library.templates = templates;
            var a = new AnimationClip { name = "Synthetic Idle" }; var b = new AnimationClip { name = "Synthetic Run" };
            a.SetCurve("Bone", typeof(Transform), "localPosition.x", AnimationCurve.Linear(0, 0, 1, 0));
            b.SetCurve("Bone", typeof(Transform), "localPosition.x", AnimationCurve.Linear(0, 1, 1, 1));
            var root = new GameObject("No-wires validation (temporary)") { hideFlags = HideFlags.HideAndDontSave };
            var bone = new GameObject("Bone"); bone.transform.SetParent(root.transform, false);
            var animator = root.AddComponent<Animator>(); ClipBlendPlayer player = null;
            try
            {
                var entry = new MotionEntry { clip = a, slot = MotionSlot.Idle }; library.entries.Add(entry);
                Check(library.Find(WeaponStance.Sheathed, MotionSlot.Idle, MotionGait.Run, MotionDirection.Back, out _) == entry, "explicit Any sharing");
                Check(library.Find(WeaponStance.Drawn, MotionSlot.Idle, MotionGait.Run, MotionDirection.Any, out _) == null, "stance cannot leak");
                Check(!library.Validate().Any(), "valid library");
                entry.speed = 1.3f; entry.inPoint = 0.2f; entry.outPoint = 0.8f;
                Check(Mathf.Abs(entry.CycleSeconds - 0.6f / 1.3f) < 0.001f, "trim and playback rate define cycle duration");
                Check(Mathf.Abs(entry.Sample(0.5f, 1, true).normalizedTime - 0.5f) < 0.001f, "shared phase is not multiplied by speed at wrap");
                Check(Mathf.Abs(entry.Sample(0.5f, 1, false).normalizedTime - 0.59f) < 0.001f, "one-shot speed respects authored range");
                entry.speed = 1; entry.inPoint = 0; entry.outPoint = 1;
                library.jumpHeight = float.NaN; Check(library.Validate().Any(), "reject nonfinite jump tuning"); library.jumpHeight = 1.3f;
                Check(MotionLibraryPlayer.FamilyForSlot(MotionSlot.StrafeBack) == MotionFamily.Strafe && MotionLibraryPlayer.FamilyForSlot(MotionSlot.StopLeft) == MotionFamily.Stop, "preview selects runtime recipe families");
                Check(MotionLibraryPlayer.FamilyForSlot(MotionSlot.StrafeBackRight) == MotionFamily.Strafe, "last diagonal uses strafe recipe family");
                var duplicate = new MotionEntry { slot = MotionSlot.Idle }; library.entries.Add(duplicate);
                Check(library.Validate().Any(x => x.Contains("Ambiguous")), "duplicate selector rejected"); library.entries.Remove(duplicate);
                templates.recipes.Add(new MotionRecipe { label = "global" });
                templates.recipes.Add(new MotionRecipe { label = "start", to = MotionFamily.Start });
                Check(library.Resolve(MotionFamily.Idle, MotionFamily.Start, 0, MotionGait.Run, MotionDirection.Forward, out _).label == "start", "specific template precedence");
                var recipe = new MotionRecipe { label = "override", to = MotionFamily.Start }; library.overrides.Add(recipe);
                Check(library.Resolve(MotionFamily.Idle, MotionFamily.Start, 0, MotionGait.Run, MotionDirection.Forward, out _).label == "override", "character override precedence");
                library.overrides.Add(new MotionRecipe { to = MotionFamily.Start });
                Check(library.Resolve(MotionFamily.Idle, MotionFamily.Start, 0, MotionGait.Run, MotionDirection.Forward, out var reason) == null && reason.Contains("CONFLICT"), "equal priority fails to safe default");
                library.overrides.RemoveAt(1);
                recipe.weight = AnimationCurve.Linear(0, 0.4f, 1, 1); Check(library.Validate().Any(), "reject discontinuous weight endpoints"); recipe.weight = AnimationCurve.Linear(0, 0, 1, 1);
                Check(MotionLibraryPlayer.Direction(-90) == MotionDirection.Left && MotionLibraryPlayer.Direction(180) == MotionDirection.Back, "direction quantization");
                player = new ClipBlendPlayer(animator);
                var samples = new List<MotionSample> { new MotionSample("idle", a, 1, 0.25f) };
                player.SetTarget("idle", samples, 0); player.Evaluate(0);
                Check(Mathf.Abs(bone.transform.localPosition.x) < 0.001f, "real graph samples source pose");
                samples[0] = new MotionSample("run", b, 1, 0.2f);
                player.SetTarget("run", samples, 1, AnimationCurve.Linear(0, 0, 1, 1)); player.Evaluate(0.25f);
                Check(Mathf.Abs(bone.transform.localPosition.x - 0.25f) < 0.001f, "real graph blends 25 percent");
                Check(Mathf.Abs(player.WeightSum - 1) < 0.0001f, "weights normalized");
                player.SetTarget("run", samples, 1); player.Evaluate(0.25f);
                Check(Mathf.Abs(bone.transform.localPosition.x - 0.5f) < 0.001f, "same request does not restart blend");
                samples[0] = new MotionSample("run", b, 1, 0);
                player.SetTarget("run/reentry", samples, 0.2f); player.Evaluate(0.01f);
                Check(Math.Abs(player.TimeFor("run", false) - 0.2) < 0.001 && Math.Abs(player.TimeFor("run", true)) < 0.001, "same clip reentry has independent old/new clocks");
                player.Evaluate(1); Check(player.VoiceCount == 1, "finished sources retired");
                for (int i = 0; i < 100; i++)
                { player.SetTarget("stress/" + i, samples, 0.05f); player.Evaluate(0.02f); Check(Mathf.Abs(player.WeightSum - 1) < 0.001f, "rapid interrupt weights"); }
                Check(player.VoiceCount < 30, "rapid interruption graph bounded");
                for (int i = 0; i < 240; i++)
                {
                    player.SetTarget("long-interrupt/" + i, samples, 0.8f); player.Evaluate(1f / 120);
                    Check(player.VoiceCount <= ClipBlendPlayer.MaximumOutgoingVoices + 1 && Mathf.Abs(player.WeightSum - 1) < 0.0001f, "long blend interruption stays bounded and normalized");
                }
                Check(animator.runtimeAnimatorController == null && !animator.fireEvents, "no controller or source events");
                return $"PASS {count} No-wires Editor assertions: real PlayableGraph pose/weights, independent clocks, rule matching and bounded interruptions. Not character animation acceptance.";
            }
            finally { player?.Dispose(); Object.DestroyImmediate(root); Object.DestroyImmediate(a); Object.DestroyImmediate(b); Object.DestroyImmediate(library); Object.DestroyImmediate(templates); }
        }
    }
}
