using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    public sealed class ClipBindingMapEditor : EditorWindow
    {
        [SerializeField] private ClipBindingMap map;
        private Vector2 scroll;
        private string status = "";
        private bool onlyUnapproved = true;
        [MenuItem("Tools/MY Project/Animation/Explicit Clip Binding Map")]
        public static void Open() => GetWindow<ClipBindingMapEditor>("Clip Binding Map");
        public static void Open(GameObject model, AnimationClip clip)
        {
            string path = EditorUtility.SaveFilePanelInProject("New reviewed binding map", "ClipBindingMap", "asset", "For external references choose Assets/LocalAnimationLab. Existing files are not overwritten.");
            if (string.IsNullOrEmpty(path) || File.Exists(path)) return;
            AnimationBindingTools.RequireLocalDestination(path, model, clip);
            var data = CreateInstance<ClipBindingMap>(); data.targetModel = model; data.exampleClip = clip;
            AssetDatabase.CreateAsset(data, path);
            var window = GetWindow<ClipBindingMapEditor>("Clip Binding Map"); window.map = data; window.AddSuggestions(); window.Show();
        }
        private void OnGUI()
        {
            map = (ClipBindingMap)EditorGUILayout.ObjectField("Mapping asset", map, typeof(ClipBindingMap), false);
            if (map == null) { EditorGUILayout.HelpBox("Create a mapping from Character Workbench > Bindings. Mapping suggestions are not accepted until reviewed. Missing LOD helpers may be explicitly omitted from the COPY only.", MessageType.Info); return; }
            using (new EditorGUI.DisabledScope(Application.isPlaying))
            {
                var so = new SerializedObject(map); so.Update();
                EditorGUILayout.PropertyField(so.FindProperty("targetModel")); EditorGUILayout.PropertyField(so.FindProperty("exampleClip")); so.ApplyModifiedProperties();
                EditorGUILayout.HelpBox("Path mapping is NOT skeletal retargeting. Different rest poses, parent transforms or bone orientation can still deform the result. Unique leaf-name matches are suggestions only. Every changed or omitted path requires explicit approval; curve-key values and source clips remain untouched.", MessageType.Warning);
                EditorGUILayout.BeginHorizontal();
                if (GUILayout.Button("Add suggestions for clip")) AddSuggestions();
                if (GUILayout.Button("Save map")) AssetDatabase.SaveAssetIfDirty(map);
                onlyUnapproved = GUILayout.Toggle(onlyUnapproved, "Only pending"); EditorGUILayout.EndHorizontal();
                scroll = EditorGUILayout.BeginScrollView(scroll);
                foreach (var entry in map.paths)
                {
                    if (onlyUnapproved && entry.approved) continue;
                    EditorGUILayout.BeginVertical(EditorStyles.helpBox);
                    EditorGUILayout.SelectableLabel(entry.sourcePath, GUILayout.Height(18));
                    EditorGUI.BeginChangeCheck();
                    bool omit = EditorGUILayout.Toggle("Omit from COPY", entry.omitFromCopy);
                    string destination = EditorGUILayout.TextField("Exact target path", entry.targetPath);
                    if (EditorGUI.EndChangeCheck()) { Undo.RecordObject(map, "Edit binding mapping"); entry.omitFromCopy = omit; entry.targetPath = destination; entry.approved = false; EditorUtility.SetDirty(map); }
                    bool valid = omit || map.targetModel != null && (string.IsNullOrEmpty(destination) || map.targetModel.transform.Find(destination) != null);
                    using (new EditorGUI.DisabledScope(!valid))
                    {
                        bool approved = EditorGUILayout.Toggle("Reviewed / approved", entry.approved);
                        if (approved != entry.approved) { Undo.RecordObject(map, "Approve binding mapping"); entry.approved = approved; EditorUtility.SetDirty(map); }
                    }
                    if (!valid) EditorGUILayout.HelpBox("Target path does not exist. Choose a real target or explicitly omit this path.", MessageType.Error);
                    EditorGUILayout.EndVertical();
                }
                EditorGUILayout.EndScrollView();
                if (GUILayout.Button("Create NEW mapped clip copy…"))
                {
                    string path = EditorUtility.SaveFilePanelInProject("Mapped clip copy", map.exampleClip != null ? map.exampleClip.name + "_Mapped" : "Mapped", "anim", "No source files will be overwritten.");
                    if (!string.IsNullOrEmpty(path))
                    {
                        try { var clip = MakeCopy(map, map.exampleClip, path); status = AnimationBindingTools.Coverage(map.targetModel, clip); Selection.activeObject = clip; }
                        catch (Exception e) { status = e.Message; }
                    }
                }
                EditorGUILayout.HelpBox(status.Length == 0 ? "Select a different example clip to reuse approved mappings; add new paths, review, then create another copy." : status, MessageType.Info);
            }
        }
        private void AddSuggestions()
        {
            if (map == null || map.targetModel == null || map.exampleClip == null) return;
            Undo.RecordObject(map, "Suggest unapproved binding mappings");
            var targets = map.targetModel.GetComponentsInChildren<Transform>(true).Select(t => AnimationUtility.CalculateTransformPath(t, map.targetModel.transform)).ToArray();
            foreach (string path in AnimationUtility.GetCurveBindings(map.exampleClip).Concat(AnimationUtility.GetObjectReferenceCurveBindings(map.exampleClip)).Select(b => b.path).Distinct())
            {
                if (map.paths.Exists(e => e.sourcePath == path)) continue;
                bool exact = targets.Contains(path);
                string leaf = path.Split('/').Last();
                var candidates = targets.Where(p => p.Split('/').Last() == leaf).ToArray();
                map.paths.Add(new ClipPathMapping { sourcePath = path, targetPath = exact ? path : candidates.Length == 1 ? candidates[0] : "<unresolved>", approved = exact });
            }
            EditorUtility.SetDirty(map);
        }
        public static AnimationClip MakeCopy(ClipBindingMap map, AnimationClip source, string destination)
        {
            if (map == null || map.targetModel == null || source == null) throw new ArgumentException("Assign mapping, target model and source clip.");
            if (!destination.StartsWith("Assets/", StringComparison.Ordinal) || !destination.EndsWith(".anim", StringComparison.OrdinalIgnoreCase) || File.Exists(destination)) throw new ArgumentException("Choose a new Assets/*.anim path.");
            AnimationBindingTools.RequireLocalDestination(destination, map.targetModel, source);
            var floats = AnimationUtility.GetCurveBindings(source); var objects = AnimationUtility.GetObjectReferenceCurveBindings(source);
            var rows = new Dictionary<string, ClipPathMapping>();
            foreach (var row in map.paths) { if (rows.ContainsKey(row.sourcePath)) throw new InvalidOperationException("Duplicate source mapping: " + row.sourcePath); rows.Add(row.sourcePath, row); }
            var seen = new HashSet<string>();
            EditorCurveBinding? Map(EditorCurveBinding binding)
            {
                if (!rows.TryGetValue(binding.path, out var row) || !row.approved) throw new InvalidOperationException("Unreviewed source path: " + binding.path);
                if (row.omitFromCopy) return null;
                binding.path = row.targetPath;
                var target = string.IsNullOrEmpty(binding.path) ? map.targetModel.transform : map.targetModel.transform.Find(binding.path);
                if (target == null || binding.type != typeof(GameObject) && (!typeof(Component).IsAssignableFrom(binding.type) || target.GetComponent(binding.type) == null)) throw new InvalidOperationException("Missing target transform/component: " + binding.path);
                if (!seen.Add(binding.path + "|" + binding.type.FullName + "|" + binding.propertyName)) throw new InvalidOperationException("Curve collision after mapping: " + binding.path + "/" + binding.propertyName);
                return binding;
            }
            var mappedFloats = floats.Select(Map).ToArray(); var mappedObjects = objects.Select(Map).ToArray();
            if (mappedFloats.All(b => !b.HasValue) && mappedObjects.All(b => !b.HasValue)) throw new InvalidOperationException("All curves were omitted. No empty clip created.");
            var copy = Object.Instantiate(source); copy.name = Path.GetFileNameWithoutExtension(destination);
            try
            {
                foreach (var b in floats) AnimationUtility.SetEditorCurve(copy, b, null);
                foreach (var b in objects) AnimationUtility.SetObjectReferenceCurve(copy, b, null);
                for (int i = 0; i < floats.Length; i++) if (mappedFloats[i].HasValue) AnimationUtility.SetEditorCurve(copy, mappedFloats[i].Value, AnimationUtility.GetEditorCurve(source, floats[i]));
                for (int i = 0; i < objects.Length; i++) if (mappedObjects[i].HasValue) AnimationUtility.SetObjectReferenceCurve(copy, mappedObjects[i].Value, AnimationUtility.GetObjectReferenceCurve(source, objects[i]));
                AnimationUtility.SetAnimationEvents(copy, Array.Empty<AnimationEvent>());
                AssetDatabase.CreateAsset(copy, destination); AssetDatabase.SaveAssetIfDirty(copy); return copy;
            }
            catch { if (!AssetDatabase.Contains(copy)) Object.DestroyImmediate(copy); throw; }
        }
    }
}
