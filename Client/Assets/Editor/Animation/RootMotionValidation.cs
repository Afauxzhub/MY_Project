using System;
using System.Collections.Generic;
using System.Linq;
using Afauxzhub.CharacterLocomotion;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    public static class RootMotionValidation
    {
        public static int Assertions { get; private set; }
        private static void Check(bool value, string message)
        { Assertions++; if (!value) throw new InvalidOperationException("Root Motion: " + message); }
        public static AnimationClip Clip(float distance = 2, float degrees = 0, float rise = 0)
        {
            var clip = new AnimationClip { name = "Synthetic root fixture", hideFlags = HideFlags.HideAndDontSave };
            void Curve(string property, AnimationCurve curve) => AnimationUtility.SetEditorCurve(clip, EditorCurveBinding.FloatCurve("", typeof(Animator), property), curve);
            Curve("MotionT.x", AnimationCurve.Constant(0, 1, 0));
            Curve("MotionT.y", AnimationCurve.Linear(0, 0, 1, rise));
            Curve("MotionT.z", AnimationCurve.Linear(0, 0, 1, distance));
            Curve("MotionQ.x", AnimationCurve.Constant(0, 1, 0)); Curve("MotionQ.z", AnimationCurve.Constant(0, 1, 0));
            var y = new AnimationCurve(); var w = new AnimationCurve();
            for (int i = 0; i <= 120; i++) { var q = Quaternion.Euler(0, degrees * i / 120, 0); y.AddKey(i / 120f, q.y); w.AddKey(i / 120f, q.w); }
            Curve("MotionQ.y", y); Curve("MotionQ.w", w);
            return clip;
        }
        public static GameObject Model()
        {
            var go = new GameObject("Synthetic root model") { hideFlags = HideFlags.HideAndDontSave };
            var root = new GameObject("Root"); root.transform.SetParent(go.transform, false);
            go.AddComponent<Animator>(); return go;
        }
        [MenuItem("Tools/MY Project/Animation/Validate Root Motion Core (no source writes)")]
        public static void Run()
        {
            Assertions = 0;
            var model = Model(); var clip = Clip(); var turn = Clip(2, 90, 1);
            ClipBlendPlayer player = null;
            try
            {
                var straight = RootMotionBaker.Bake(model, clip); var curved = RootMotionBaker.Bake(model, turn);
                Check(Vector3.Distance(straight.At(1).position, Vector3.forward * 2) < 0.002f, "native extraction distance " + straight.At(1).position);
                Check(Vector3.Distance(curved.At(1).position, new Vector3(0, 1, 2)) < 0.02f, "native extraction turning translation " + curved.At(1).position);
                Check(Quaternion.Angle(curved.At(1).rotation, Quaternion.Euler(0, 90, 0)) < 0.1f, "native extraction rotation");
                Check(RootMotionBaker.Current(straight, model, clip), "current extraction fingerprint");
                Check(!RootMotionBaker.Current(straight, model, turn), "different clip rejected");
                Check(Vector3.Distance(straight.Delta(0.9f, 1.1f, 0, 1, true).position, Vector3.forward * 0.4f) < 0.002f, "wrap no backwards jump");
                Check(Mathf.Abs(straight.Delta(0, 3.5f, 0.2f, 0.8f, true).position.z - 4.2f) < 0.002f, "trimmed multiple cycles");
                Check(Mathf.Abs(straight.Delta(1000000.99, 1000001.01, 0, 1, true).position.z - 0.04f) < 0.0001f, "million-cycle clock retains sub-frame root precision");
                Check(Mathf.Abs(straight.Delta(0.8f, 0.2f, 0, 1, false).position.z + 1.2f) < 0.002f, "reverse time curve is explicit reverse motion");
                var repeated = curved.Unwrapped(2, 0, 1, true);
                Check(Vector3.Distance(repeated.position, new Vector3(2, 2, 2)) < 0.04f, "turning cycles compose rigid transforms " + repeated.position);
                foreach (int fps in new[] { 30, 60, 120 })
                {
                    player = new ClipBlendPlayer(model.GetComponent<Animator>());
                    var entry = new MotionEntry { clip = clip, rootMotion = new RootMotionSettings { enabled = true, track = straight }, inPoint = 0.2f, outPoint = 0.8f, phaseOffset = 0.3f };
                    var samples = new List<MotionSample> { entry.Sample(0, 1, true) };
                    player.SetTarget("loop", samples, 0); player.Evaluate(0);
                    Vector3 sum = Vector3.zero;
                    for (int i = 1; i <= fps * 2; i++)
                    {
                        samples[0] = entry.Sample(1.3f * i / fps, 1, true);
                        player.SetTarget("loop", samples, 0); player.Evaluate(1f / fps); sum += player.RootFrame.localDelta;
                        Check(RootMotionSettings.Finite(player.RootFrame.localDelta.sqrMagnitude) && Mathf.Abs(player.WeightSum - 1) < 0.00001f, "finite normalized root mixture");
                    }
                    Check(Mathf.Abs(sum.z - 3.12f) < 0.003f, "speed/crop/offset at " + fps + " fps: " + sum);
                    Check(model.transform.position.sqrMagnitude < 0.00001f, "pose graph does not move actor");
                    player.Evaluate(1f / fps); Check(player.RootFrame.localDelta.sqrMagnitude < 0.000001f, "same sample never repeats delta");
                    samples[0] = entry.Sample(0.2f, 1, false); player.SetTarget("restart", samples, 0.2f); player.Evaluate(1f / fps);
                    Check(player.RootFrame.localDelta.sqrMagnitude < 0.000001f, "new clock/seek never teleports");
                    samples[0] = entry.Sample(0.4f, 1, false); player.SetTarget("restart", samples, 0); player.Evaluate(0);
                    Check(player.RootFrame.localDelta.sqrMagnitude < 0.000001f, "pause rebases without movement");
                    samples[0] = entry.Sample(0.5f, 1, false); player.SetTarget("restart", samples, 0); player.Evaluate(0.2f);
                    Check(Mathf.Abs(player.RootFrame.localDelta.z - 0.12f) < 0.003f, "resume has no accumulated jump");
                    entry.rootMotion.track = null; samples[0] = entry.Sample(0.6f, 1, false); player.SetTarget("restart", samples, 0); player.Evaluate(0.1f);
                    Check(!string.IsNullOrEmpty(player.RootFrame.problem) && player.RootFrame.localDelta.sqrMagnitude < 0.000001f && player.RootFrame.positionWeight > 0.99f, "missing track holds rather than fakes root movement");
                    player.Dispose(); player = null;
                }
                player = new ClipBlendPlayer(model.GetComponent<Animator>());
                var rooted = new MotionEntry { id = "root", clip = turn, rootMotion = new RootMotionSettings { enabled = true, rotation = true, vertical = true, track = curved } };
                var mixture = new List<MotionSample> { new MotionSample("pose-only", clip, 1, 0) };
                player.SetTarget("pose-only", mixture, 0); player.Evaluate(0);
                mixture[0] = rooted.Sample(0, 1, false); player.SetTarget("root", mixture, 1, AnimationCurve.Linear(0, 0, 1, 1)); player.Evaluate(0);
                mixture[0] = rooted.Sample(0.5f, 1, false); player.SetTarget("root", mixture, 1); player.Evaluate(0.5f);
                Check(Mathf.Abs(player.RootFrame.positionWeight - 0.5f) < 0.001f && Mathf.Abs(player.RootFrame.yaw - 22.5f) < 0.1f, "root/pose mixture uses weight once");
                Check(Vector3.Distance(player.RootFrame.localDelta, new Vector3(0, 0.25f, 0.5f)) < 0.02f, "XYZ blend follows pose weights");
                var tail = player.CompleteOneShots();
                Check(tail.localDelta.magnitude > 0.1f && player.CompleteOneShots().localDelta.sqrMagnitude < 0.00001f, "one-shot endpoint consumed exactly once");
                player.Dispose(); player = new ClipBlendPlayer(model.GetComponent<Animator>());
                model.transform.localScale = Vector3.one * 2;
                var scaled = new MotionEntry { clip = clip, rootMotion = new RootMotionSettings { enabled = true, track = straight, scale = 0.5f } };
                mixture[0] = scaled.Sample(0, 1, false); player.SetTarget("scale", mixture, 0); player.Evaluate(0);
                mixture[0] = scaled.Sample(1, 1, false); player.SetTarget("scale", mixture, 0); player.Evaluate(1);
                Check(Mathf.Abs(player.RootFrame.localDelta.z - 2) < 0.003f, "runtime model scale and author scale applied once");
                model.transform.localScale = Vector3.one;
                var bakedJson = JsonUtility.ToJson(straight); var roundtrip = JsonUtility.FromJson<RootMotionTrack>(bakedJson);
                Check(roundtrip.positions.Length == straight.positions.Length && Vector3.Distance(roundtrip.At(0.75f).position, straight.At(0.75f).position) < 0.00001f, "track survives configuration serialization");
                straight.fingerprint = "outdated"; Check(!RootMotionBaker.Current(straight, model, clip), "stale data detected");
                player.Dispose(); player = null;
                CheckFrameAlignment(model, clip, straight);
                CheckHeadingSynchronization();
                Debug.Log("Root Motion core: " + Assertions + " assertions passed (native extraction + deterministic playback; not asset quality).");
            }
            finally { player?.Dispose(); Object.DestroyImmediate(model); Object.DestroyImmediate(clip); Object.DestroyImmediate(turn); }
        }

        private static void CheckFrameAlignment(GameObject model, AnimationClip clip, RootMotionTrack track)
        {
            var library = ScriptableObject.CreateInstance<MotionLibrary>();
            var tuning = ScriptableObject.CreateInstance<LocomotionProfile>();
            var actor = new GameObject("Frame alignment fixture") { hideFlags = HideFlags.HideAndDontSave };
            try
            {
                library.relaxedMovement = tuning; library.readyMovement = tuning; library.defaultBlend = 0;
                library.entries.Add(new MotionEntry { slot = MotionSlot.Idle, clip = clip,
                    rootMotion = new RootMotionSettings { enabled = true, track = track } });
                var driver = actor.AddComponent<AnimatedCharacterDriver>(); driver.animator = model.GetComponent<Animator>();
                var adapter = actor.AddComponent<MotionLibraryPlayer>(); adapter.driver = driver; adapter.library = library; driver.motionPlayer = adapter;
                // Alternating large and tiny intervals exposes one-frame-delayed root debt, including wrap.
                foreach (float dt in new[] { 0.01f, 0.333f, 0.003f, 0.025f, 0.333f, 0.004f, 0.333f, 0.006f })
                {
                    adapter.Tick(null, tuning, dt);
                    Check(Mathf.Abs(adapter.RootFrame.localDelta.z - 2 * dt) < 0.0001f, "loop root uses THIS frame delta " + dt);
                    Check(Math.Abs(adapter.Player.TimeFor(library.entries[0].id, true) - adapter.Cycle) < 0.0001f, "pose/root clocks share end-of-frame sample");
                }
                // Isolate selector ownership: missing pose fallback is not missing root data.
                var add = typeof(MotionLibraryPlayer).GetMethod("Add", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
                var list = (List<MotionSample>)typeof(MotionLibraryPlayer).GetField("samples", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic).GetValue(adapter);
                list.Clear(); add.Invoke(adapter, new object[] { MotionSlot.StrafeRight, MotionGait.Run, MotionDirection.Any, 1f, 0.5, true });
                Check(list.Count == 1 && list[0].rootMotion == null, "missing strafe borrows Idle pose without stealing procedural movement");
                adapter.WorkingLibrary.entries.Add(new MotionEntry { slot = MotionSlot.Start, direction = MotionDirection.Forward, clip = clip,
                    rootMotion = new RootMotionSettings { enabled = true, track = track } });
                list.Clear(); add.Invoke(adapter, new object[] { MotionSlot.Start, MotionGait.Run, MotionDirection.Right, 1f, 0.5, false });
                Check(list.Count == 1 && list[0].rootMotion == null, "missing directional start never substitutes forward root travel");
                Check(adapter.WorkingLibrary.entries[0].rootMotion.enabled && library.entries[0].rootMotion.enabled, "fallback does not edit root configuration");
            }
            finally { Object.DestroyImmediate(actor); Object.DestroyImmediate(library); Object.DestroyImmediate(tuning); }
        }

        private static void CheckHeadingSynchronization()
        {
            var profile = ScriptableObject.CreateInstance<LocomotionProfile>();
            try
            {
                profile.constrainArcRadius = false; profile.maximumYawRate = 360; profile.yawAcceleration = 1200;
                profile.yawDeceleration = 1600; profile.headingCatchUpTime = 0.15f;
                foreach (int fps in new[] { 30, 60, 120 })
                {
                    var solver = new HeadingSolver(); solver.Reset(Vector3.forward);
                    Vector3 desired = Quaternion.Euler(0, 45, 0) * Vector3.forward;
                    for (int i = 0; i < fps; i++)
                    {
                        var intent = solver.Step(solver.SolvedDirection, desired, 5, 1f / fps, profile);
                        float rate = solver.CommandedYawRate;
                        solver.SynchronizeFacing(intent.SolvedDirection);
                        Check(solver.CommandedYawRate == rate, "root reconciliation preserves acceleration at " + fps);
                    }
                    Check(Vector3.Angle(solver.SolvedDirection, desired) < 1, "same heading reached at " + fps);
                    solver.Reset(Vector3.forward); Check(solver.CommandedYawRate == 0, "explicit reset still clears turn state");
                }
            }
            finally { Object.DestroyImmediate(profile); }
        }
    }
}
