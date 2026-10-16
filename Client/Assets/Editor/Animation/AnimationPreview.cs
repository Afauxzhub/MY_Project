using System;
using System.Collections.Generic;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    /// <summary>Builds a render-only copy. Never instantiates model MonoBehaviours or touches a scene character.</summary>
    public static class RenderOnlyModel
    {
        public static GameObject Copy(GameObject source, bool particles = false)
        {
            var map = new Dictionary<Transform, Transform>();
            Transform CopyTransform(Transform original, Transform parent)
            {
                var go = new GameObject(original.name) { hideFlags = HideFlags.HideAndDontSave };
                go.transform.SetParent(parent, false);
                go.transform.localPosition = original.localPosition;
                go.transform.localRotation = original.localRotation;
                go.transform.localScale = original.localScale;
                map.Add(original, go.transform);
                foreach (Transform child in original) CopyTransform(child, go.transform);
                go.SetActive(original.gameObject.activeSelf);
                return go.transform;
            }
            var root = CopyTransform(source.transform, null);
            root.gameObject.SetActive(true);
            root.localPosition = Vector3.zero; root.localRotation = Quaternion.identity;
            foreach (var pair in map)
            {
                var skin = pair.Key.GetComponent<SkinnedMeshRenderer>();
                if (skin != null)
                {
                    var copy = pair.Value.gameObject.AddComponent<SkinnedMeshRenderer>();
                    copy.sharedMesh = skin.sharedMesh; copy.sharedMaterials = skin.sharedMaterials;
                    var bones = new Transform[skin.bones.Length];
                    for (int i = 0; i < bones.Length; i++) if (skin.bones[i] != null) map.TryGetValue(skin.bones[i], out bones[i]);
                    copy.bones = bones;
                    if (skin.rootBone != null && map.TryGetValue(skin.rootBone, out var bone)) copy.rootBone = bone;
                    copy.localBounds = skin.localBounds; copy.updateWhenOffscreen = true;
                    copy.enabled = skin.enabled; copy.shadowCastingMode = skin.shadowCastingMode; copy.receiveShadows = skin.receiveShadows;
                }
                var mesh = pair.Key.GetComponent<MeshFilter>();
                var renderer = pair.Key.GetComponent<MeshRenderer>();
                if (mesh != null && renderer != null)
                {
                    pair.Value.gameObject.AddComponent<MeshFilter>().sharedMesh = mesh.sharedMesh;
                    var copy = pair.Value.gameObject.AddComponent<MeshRenderer>(); copy.sharedMaterials = renderer.sharedMaterials;
                    copy.enabled = renderer.enabled; copy.shadowCastingMode = renderer.shadowCastingMode; copy.receiveShadows = renderer.receiveShadows;
                }
                if (particles && pair.Key.TryGetComponent<ParticleSystem>(out var ps))
                {
                    var copy = pair.Value.gameObject.AddComponent<ParticleSystem>();
                    EditorUtility.CopySerialized(ps, copy);
                    var pr = pair.Key.GetComponent<ParticleSystemRenderer>();
                    if (pr != null) EditorUtility.CopySerialized(pr, copy.GetComponent<ParticleSystemRenderer>());
                    var sub = copy.subEmitters; sub.enabled = false; // Never reference live external particle systems.
                    copy.useAutoRandomSeed = false; copy.randomSeed = 1; copy.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
                }
            }
            var sourceAnimator = source.GetComponentInChildren<Animator>();
            var animator = root.gameObject.AddComponent<Animator>();
            if (sourceAnimator != null) animator.avatar = sourceAnimator.avatar;
            animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            animator.applyRootMotion = false;
            return root.gameObject;
        }
    }

    public sealed class AnimationPreview : IDisposable
    {
        private PreviewRenderUtility utility;
        private GameObject source, model;
        private Transform[] transforms;
        private Vector3[] positions, scales;
        private Quaternion[] rotations;
        private readonly Dictionary<ActionCue, GameObject> effects = new Dictionary<ActionCue, GameObject>();
        private readonly List<GameObject> boxes = new List<GameObject>();
        private Material shapeMaterial;
        private ActionDefinition previousAction;
        private float yaw = 150, pitch = 10, distance = 4, radius = 1;
        private Vector3 center = Vector3.up;
        public bool pinRoot = true;
        public bool showEffects = true;
        public bool showShapes = true;

        public void Dispose()
        {
            ClearExtras();
            if (utility != null) { utility.Cleanup(); utility = null; }
            if (shapeMaterial != null) Object.DestroyImmediate(shapeMaterial);
            model = null; source = null;
        }
        public void InvalidateEffects() { ClearExtras(); previousAction = null; }
        private void ClearExtras()
        {
            foreach (var item in effects.Values) if (item != null) Object.DestroyImmediate(item);
            effects.Clear();
            foreach (var box in boxes) if (box != null) Object.DestroyImmediate(box);
            boxes.Clear();
        }
        private void SetSource(GameObject prefab)
        {
            if (prefab == source && utility != null) return;
            Dispose(); source = prefab;
            utility = new PreviewRenderUtility(); utility.cameraFieldOfView = 30;
            utility.camera.nearClipPlane = 0.01f; utility.camera.farClipPlane = 1000;
            utility.camera.clearFlags = CameraClearFlags.Color;
            utility.camera.backgroundColor = new Color(0.075f, 0.09f, 0.12f);
            utility.lights[0].intensity = 1.3f; utility.lights[0].transform.rotation = Quaternion.Euler(35, 35, 0);
            utility.lights[1].intensity = 0.7f; utility.lights[1].transform.rotation = Quaternion.Euler(330, 210, 0);
            if (prefab == null) return;
            model = RenderOnlyModel.Copy(prefab);
            utility.AddSingleGO(model);
            transforms = model.GetComponentsInChildren<Transform>(true);
            positions = new Vector3[transforms.Length]; rotations = new Quaternion[transforms.Length]; scales = new Vector3[transforms.Length];
            for (int i = 0; i < transforms.Length; i++) { positions[i] = transforms[i].localPosition; rotations[i] = transforms[i].localRotation; scales[i] = transforms[i].localScale; }
            var bounds = new Bounds(Vector3.up, Vector3.one);
            var renderers = model.GetComponentsInChildren<Renderer>();
            if (renderers.Length > 0) { bounds = renderers[0].bounds; foreach (var r in renderers) bounds.Encapsulate(r.bounds); }
            center = bounds.center; radius = Mathf.Max(0.5f, bounds.extents.magnitude); distance = radius * 3.5f;
        }
        public void Draw(Rect rect, GameObject prefab, AnimationClip clip, float clipSeconds, ActionDefinition action = null, float actionSeconds = 0)
        {
            SetSource(prefab);
            var e = Event.current;
            if (rect.Contains(e.mousePosition))
            {
                if (e.type == EventType.MouseDrag && e.button == 0) { yaw += e.delta.x; pitch = Mathf.Clamp(pitch + e.delta.y, -80, 80); e.Use(); }
                if (e.type == EventType.ScrollWheel) { distance = Mathf.Clamp(distance * (1 + e.delta.y * 0.05f), radius, radius * 12); e.Use(); }
            }
            if (e.type != EventType.Repaint) return;
            if (model == null) { EditorGUI.HelpBox(rect, "Assign a preview model. Preview never changes the scene or the source clip.", MessageType.Info); return; }
            for (int i = 0; i < transforms.Length; i++) { transforms[i].localPosition = positions[i]; transforms[i].localRotation = rotations[i]; transforms[i].localScale = scales[i]; }
            if (clip != null) clip.SampleAnimation(model, Mathf.Clamp(clipSeconds, 0, clip.length));
            if (pinRoot) { model.transform.position = Vector3.zero; model.transform.rotation = Quaternion.identity; }
            Extras(action, actionSeconds);
            utility.camera.transform.SetPositionAndRotation(center - Quaternion.Euler(pitch, yaw, 0) * Vector3.forward * distance, Quaternion.Euler(pitch, yaw, 0));
            utility.BeginPreview(rect, GUIStyle.none);
            utility.camera.Render();
            GUI.DrawTexture(rect, utility.EndPreview(), ScaleMode.StretchToFill, false);
            GUI.Label(new Rect(rect.x + 8, rect.y + 5, rect.width - 16, 22), "Isolated pose preview · drag orbit / wheel zoom · foot IK tested in Play Mode", EditorStyles.whiteMiniLabel);
        }
        private void Extras(ActionDefinition action, float time)
        {
            if (previousAction != action) { ClearExtras(); previousAction = action; }
            if (action == null) return;
            foreach (var cue in action.cues)
            {
                if (cue == null || cue.kind != CueKind.Effect || cue.effect == null) continue;
                if (!effects.TryGetValue(cue, out var instance))
                {
                    instance = RenderOnlyModel.Copy(cue.effect, true); utility.AddSingleGO(instance); effects.Add(cue, instance);
                }
                float age = time - cue.time;
                var socket = string.IsNullOrEmpty(cue.socketPath) ? model.transform : model.transform.Find(cue.socketPath);
                bool visible = showEffects && socket != null && age >= 0 && age < cue.lifetime;
                instance.SetActive(visible);
                if (!visible) continue;
                instance.transform.SetPositionAndRotation(socket.TransformPoint(cue.offset), socket.rotation);
                foreach (var ps in instance.GetComponentsInChildren<ParticleSystem>()) ps.Simulate(age, false, true, true);
            }
            while (boxes.Count < action.hitShapes.Count)
            {
                var box = GameObject.CreatePrimitive(PrimitiveType.Cube); Object.DestroyImmediate(box.GetComponent<Collider>());
                box.hideFlags = HideFlags.HideAndDontSave;
                if (shapeMaterial == null)
                {
                    shapeMaterial = new Material(Shader.Find("Unlit/Color") ?? Shader.Find("Standard")) { hideFlags = HideFlags.HideAndDontSave, color = new Color(1, 0.25f, 0.1f) };
                }
                box.GetComponent<Renderer>().sharedMaterial = shapeMaterial; utility.AddSingleGO(box); boxes.Add(box);
            }
            for (int i = 0; i < boxes.Count; i++)
            {
                var shape = i < action.hitShapes.Count ? action.hitShapes[i] : null;
                var window = shape != null ? action.windows.Find(w => w != null && w.id == shape.windowId) : null;
                var bone = shape == null ? null : string.IsNullOrEmpty(shape.bonePath) ? model.transform : model.transform.Find(shape.bonePath);
                bool active = showShapes && bone != null && window != null && window.Contains(time);
                boxes[i].SetActive(active);
                if (!active) continue;
                boxes[i].transform.SetPositionAndRotation(bone.TransformPoint(shape.center), bone.rotation * Quaternion.Euler(shape.euler));
                boxes[i].transform.localScale = Vector3.Scale(bone.lossyScale, shape.halfExtents * 2);
            }
        }
    }
}
