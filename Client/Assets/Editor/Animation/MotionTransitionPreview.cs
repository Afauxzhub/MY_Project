using System;
using System.Collections.Generic;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    public sealed class MotionTransitionPreview : IDisposable
    {
        private PreviewRenderUtility utility;
        private GameObject model, source;
        private ClipBlendPlayer player;
        private float yaw = 180, pitch = 8, distance = 5;
        private Vector3 center = Vector3.up;
        private int frame;
        public string DebugText => player?.Describe() ?? "Select a model and two clips";
        public void Dispose() { player?.Dispose(); player = null; if (model != null) Object.DestroyImmediate(model); utility?.Cleanup(); utility = null; source = null; }
        private void Bind(GameObject prefab)
        {
            if (source == prefab && utility != null) return;
            Dispose(); source = prefab; utility = new PreviewRenderUtility();
            utility.cameraFieldOfView = 30; utility.camera.nearClipPlane = 0.01f; utility.camera.farClipPlane = 100;
            utility.camera.clearFlags = CameraClearFlags.Color; utility.camera.backgroundColor = new Color(0.06f, 0.08f, 0.11f);
            utility.lights[0].intensity = 1.4f; utility.lights[0].transform.rotation = Quaternion.Euler(35, 35, 0);
            utility.lights[1].intensity = 0.8f; utility.lights[1].transform.rotation = Quaternion.Euler(320, 210, 0);
            if (prefab == null) return;
            model = RenderOnlyModel.Copy(prefab); utility.AddSingleGO(model);
            player = new ClipBlendPlayer(model.GetComponent<Animator>());
            var renderers = model.GetComponentsInChildren<Renderer>();
            if (renderers.Length > 0) { var b = renderers[0].bounds; foreach (var r in renderers) b.Encapsulate(r.bounds); center = b.center; distance = Mathf.Max(2, b.extents.magnitude * 3.8f); }
        }
        private static MotionSample Sample(MotionEntry entry, float seconds, float startPhase = 0)
        {
            var family = MotionLibraryPlayer.FamilyForSlot(entry.slot);
            bool loop = family == MotionFamily.Idle || family == MotionFamily.Move || family == MotionFamily.Strafe || family == MotionFamily.Air;
            return entry.Sample(startPhase + seconds / (loop ? entry.CycleSeconds : entry.stageSeconds > 0 ? entry.stageSeconds : entry.clip.length * (entry.outPoint - entry.inPoint)), 1, loop);
        }
        public void Draw(Rect rect, MotionLibrary library, MotionEntry from, MotionEntry to, MotionRecipe recipe, float seconds, float lead)
        {
            Bind(library.model); var e = Event.current;
            if (rect.Contains(e.mousePosition))
            {
                if (e.type == EventType.MouseDrag && e.button == 0) { yaw += e.delta.x; pitch = Mathf.Clamp(pitch + e.delta.y, -75, 75); e.Use(); }
                if (e.type == EventType.ScrollWheel) { distance = Mathf.Clamp(distance * (1 + e.delta.y * 0.05f), 1, 20); e.Use(); }
            }
            if (e.type != EventType.Repaint) return;
            if (model == null || from?.clip == null || to?.clip == null) { EditorGUI.HelpBox(rect, "Choose a model and assigned source/target clips. Missing clips remain missing.", MessageType.Info); return; }
            var samples = new List<MotionSample> { Sample(from, Mathf.Min(seconds, lead)) };
            string token = (++frame).ToString();
            player.SetTarget(token + "/source", samples, 0); player.Evaluate(0);
            if (seconds >= lead)
            {
                float age = seconds - lead;
                var bridge = recipe != null ? library.ById(recipe.bridgeEntry) : null;
                float targetPhase = recipe != null && recipe.preserveCyclePhase ? Mathf.Repeat(lead / from.CycleSeconds, 1) : recipe?.targetPhase ?? 0;
                if (bridge?.clip != null)
                {
                    samples.Clear(); samples.Add(bridge.Sample(Mathf.Clamp01(age / recipe.bridgeSeconds), 1, false));
                    player.SetTarget(token + "/bridge", samples, recipe.blendSeconds, recipe.weight); player.Evaluate(Mathf.Min(age, recipe.bridgeSeconds));
                    if (age >= recipe.bridgeSeconds)
                    {
                        age -= recipe.bridgeSeconds; samples.Clear(); samples.Add(Sample(to, age, targetPhase));
                        player.SetTarget(token + "/target", samples, recipe.bridgeOutSeconds, recipe.weight); player.Evaluate(age);
                    }
                }
                else
                {
                    samples.Clear(); samples.Add(Sample(to, age, targetPhase));
                    player.SetTarget(token + "/target", samples, recipe?.blendSeconds ?? library.defaultBlend, recipe?.weight); player.Evaluate(age);
                }
            }
            model.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            var rotation = Quaternion.Euler(pitch, yaw, 0);
            utility.camera.transform.SetPositionAndRotation(center - rotation * Vector3.forward * distance, rotation);
            utility.BeginPreview(rect, GUIStyle.none); utility.camera.Render(); GUI.DrawTexture(rect, utility.EndPreview(), ScaleMode.StretchToFill, false);
            GUI.Label(new Rect(rect.x + 10, rect.y + 8, rect.width - 20, 24), "同一 Playables 混合核心 · 拖动旋转 / 滚轮缩放 · 不修改场景", EditorStyles.whiteMiniLabel);
        }
    }
}
