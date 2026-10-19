using System;
using System.Linq;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    public static class RootMotionBaker
    {
        public const int SampleRate = 120;
        public static string Fingerprint(GameObject model, AnimationClip clip)
        {
            string Signature(Object value)
            {
                string path = AssetDatabase.GetAssetPath(value);
                return string.IsNullOrEmpty(path) ? "transient:" + value?.GetInstanceID() : AssetDatabase.AssetPathToGUID(path) + ":" + AssetDatabase.GetAssetDependencyHash(path);
            }
            return "root-v1/120/" + Signature(model) + "/" + Signature(clip);
        }
        public static bool Current(RootMotionTrack track, GameObject model, AnimationClip clip)
            => track != null && track.Valid(clip) && track.model == model && track.fingerprint == Fingerprint(model, clip);
        public static string Status(RootMotionSettings settings, GameObject model, AnimationClip clip)
        {
            if (settings == null || !settings.enabled) return "程序位移（Root Motion 未启用）";
            if (!Current(settings.track, model, clip)) return "根轨迹缺失 / 已过期：请重新提取，不会自动修改原动画。";
            var end = settings.track.At(1);
            return $"根轨迹已就绪 · {settings.track.length:F2}s · 净位移 {end.position} · 净转角 {Mathf.DeltaAngle(0, end.rotation.eulerAngles.y):F1}° · {settings.track.positions.Length} 采样";
        }
        public static void RequireCurrent(MotionLibrary library)
        {
            foreach (var entry in library.entries)
                if (entry.enabled && entry.rootMotion != null && entry.rootMotion.enabled && !Current(entry.rootMotion.track, library.model, entry.clip))
                    throw new InvalidOperationException("Root Motion missing/stale: " + entry.id + ". Re-extract in the workbench.");
        }
        public static void DrawTrajectory(RootMotionTrack track, float phase = 0)
        {
            if (track == null || !track.Valid(track.clip)) return;
            Rect area = GUILayoutUtility.GetRect(120, 110, GUILayout.ExpandWidth(true));
            EditorGUI.DrawRect(area, new Color(0.08f, 0.09f, 0.12f));
            var bounds = new Bounds(Vector3.zero, Vector3.one * 0.1f);
            foreach (var point in track.positions) bounds.Encapsulate(point);
            float scale = Mathf.Min((area.width - 30) / Mathf.Max(0.1f, bounds.size.x), (area.height - 30) / Mathf.Max(0.1f, bounds.size.z));
            Vector3 Map(Vector3 point) => new Vector3(area.center.x + (point.x - bounds.center.x) * scale, area.center.y - (point.z - bounds.center.z) * scale, 0);
            Handles.BeginGUI(); var color = Handles.color; Handles.color = Color.cyan;
            Handles.DrawAAPolyLine(2, track.positions.Select(Map).ToArray());
            Handles.color = Color.yellow; Handles.DrawSolidDisc(Map(track.At(phase).position), Vector3.forward, 4);
            Handles.color = color; Handles.EndGUI();
            GUI.Label(new Rect(area.x + 4, area.y + 3, area.width - 8, 20), "根轨迹俯视 XZ · 黄点=源动画相位", EditorStyles.whiteMiniLabel);
        }
        public static RootMotionTrack Bake(GameObject source, AnimationClip clip)
        {
            if (source == null || clip == null || clip.legacy || clip.length <= 0 || clip.length > 300)
                throw new InvalidOperationException("Choose a model and a non-Legacy clip of 0–300 seconds.");
            if (!clip.hasRootCurves && !clip.hasMotionCurves)
                throw new InvalidOperationException("No imported root trajectory. Confirm the FBX Root/Motion node and Bake Into Pose settings; no bone name is guessed.");
            var copy = RenderOnlyModel.Copy(source);
            var graph = PlayableGraph.Create("Isolated root trajectory extraction");
            try
            {
                var animator = copy.GetComponent<Animator>();
                if (clip.isHumanMotion && (animator.avatar == null || !animator.avatar.isHuman))
                    throw new InvalidOperationException("Humanoid trajectory needs the actual Humanoid Avatar.");
                animator.runtimeAnimatorController = null; animator.applyRootMotion = true; animator.fireEvents = false;
                // The relay prevents automatic transform writes. Accumulate deltas in the reference frame ourselves.
                copy.AddComponent<AnimatorMotionRelay>();
                graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
                var playable = AnimationClipPlayable.Create(graph, clip);
                playable.SetApplyFootIK(false); playable.SetApplyPlayableIK(false);
                var output = AnimationPlayableOutput.Create(graph, "Root sample", animator); output.SetSourcePlayable(playable);
                graph.Play(); playable.SetTime(0); graph.Evaluate(0);
                int steps = Mathf.Max(2, Mathf.CeilToInt(clip.length * SampleRate));
                var track = new RootMotionTrack { clip = clip, model = source, modelScale = copy.transform.lossyScale, length = clip.length, fingerprint = Fingerprint(source, clip),
                    positions = new Vector3[steps + 1], rotations = new Quaternion[steps + 1] };
                track.rotations[0] = Quaternion.identity;
                float dt = clip.length / steps;
                for (int i = 1; i <= steps; i++)
                {
                    graph.Evaluate(dt);
                    var delta = animator.deltaPosition; var rotation = animator.deltaRotation;
                    if (!RootMotionSettings.Finite(delta.sqrMagnitude) || !RootMotionSettings.Finite(rotation.x + rotation.y + rotation.z + rotation.w))
                        throw new InvalidOperationException("Nonfinite native root sample.");
                    track.positions[i] = track.positions[i - 1] + track.rotations[i - 1] * delta;
                    track.rotations[i] = (track.rotations[i - 1] * rotation).normalized;
                }
                return track;
            }
            finally { if (graph.IsValid()) graph.Destroy(); Object.DestroyImmediate(copy); }
        }
    }
}
