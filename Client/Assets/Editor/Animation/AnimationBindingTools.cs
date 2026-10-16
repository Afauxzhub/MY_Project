using System;
using System.Collections.Generic;
using System.Linq;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    public static class AnimationBindingTools
    {
        public static void RequireLocalDestination(string destination, params Object[] references)
        {
            foreach (var reference in references)
                if (reference != null && AssetDatabase.GetAssetPath(reference).StartsWith("Assets/LocalAnimationLab/", StringComparison.Ordinal) && !destination.StartsWith("Assets/LocalAnimationLab/", StringComparison.Ordinal))
                    throw new InvalidOperationException("An external reference dependency was selected. Keep the derived asset under ignored Assets/LocalAnimationLab/.");
        }
        public static IEnumerable<string> Missing(CharacterAnimationProfile profile)
        {
            foreach (WeaponStance stance in Enum.GetValues(typeof(WeaponStance)))
            {
                var set = profile.Set(stance);
                if (set.movement == null) yield return stance + ": missing movement profile";
                foreach (MotionSlot slot in Enum.GetValues(typeof(MotionSlot)))
                    if (set.Find(slot)?.clip == null) yield return stance + "/" + slot + ": MISSING (state/slot retained)";
            }
            foreach (ActionKind kind in Enum.GetValues(typeof(ActionKind)))
                if (profile.Find(kind) == null) yield return "Actions/" + kind + ": missing action slot";
            foreach (var a in profile.actions)
                if (a != null) foreach (var problem in a.Validate()) yield return a.id + ": " + problem;
        }
        public static string Coverage(GameObject model, AnimationClip clip)
        {
            if (model == null || clip == null) return "Assign model and clip first.";
            var bindings = AnimationUtility.GetCurveBindings(clip).Concat(AnimationUtility.GetObjectReferenceCurveBindings(clip)).ToArray();
            var missing = bindings.Where(b => !Exists(model, b)).Select(b => b.path + " | " + b.type.Name + "." + b.propertyName).Distinct().ToArray();
            return $"{clip.name}: {bindings.Length - bindings.Count(b => !Exists(model, b))}/{bindings.Length} bound curves. Humanoid={clip.isHumanMotion}, RootCurves={clip.hasRootCurves}.\n" +
                (missing.Length == 0 ? "No missing transform/component paths. This does NOT prove correct pose, bone orientation, scale or extracted Root Motion." : string.Join("\n", missing));
        }
        private static bool Exists(GameObject model, EditorCurveBinding binding)
        {
            var t = string.IsNullOrEmpty(binding.path) ? model.transform : model.transform.Find(binding.path);
            if (t == null) return false;
            if (binding.type == typeof(GameObject)) return true;
            return typeof(Component).IsAssignableFrom(binding.type) && t.GetComponent(binding.type) != null;
        }
        public static AnimationClip RemapCopy(AnimationClip source, GameObject model, string from, string to, string destination)
        {
            if (source == null || model == null) throw new ArgumentException("Select source clip and target model.");
            RequireLocalDestination(destination, source, model);
            if (string.IsNullOrEmpty(from) || from == to) throw new ArgumentException("Specify a non-empty old prefix and a different new prefix.");
            if (AssetDatabase.LoadMainAssetAtPath(destination) != null) throw new InvalidOperationException("Destination exists; source curves must never be overwritten.");
            if (!destination.StartsWith("Assets/", StringComparison.Ordinal) || !destination.EndsWith(".anim", StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("Choose an Assets/*.anim destination.");
            var floats = AnimationUtility.GetCurveBindings(source);
            var objects = AnimationUtility.GetObjectReferenceCurveBindings(source);
            var seen = new HashSet<string>();
            bool changed = false;
            EditorCurveBinding Map(EditorCurveBinding b)
            {
                if (b.path == from || b.path.StartsWith(from + "/", StringComparison.Ordinal)) { b.path = to + b.path.Substring(from.Length); b.path = b.path.TrimStart('/'); changed = true; }
                if (!Exists(model, b)) throw new InvalidOperationException("Target binding is missing: " + b.path + " / " + b.propertyName);
                string key = b.path + "|" + b.type.FullName + "|" + b.propertyName;
                if (!seen.Add(key)) throw new InvalidOperationException("Remap would collide: " + key);
                return b;
            }
            var mappedFloats = floats.Select(Map).ToArray(); var mappedObjects = objects.Select(Map).ToArray();
            if (!changed) throw new InvalidOperationException("No bindings match the old prefix. Nothing copied.");
            var copy = Object.Instantiate(source); copy.name = System.IO.Path.GetFileNameWithoutExtension(destination);
            try
            {
                foreach (var b in floats) AnimationUtility.SetEditorCurve(copy, b, null);
                foreach (var b in objects) AnimationUtility.SetObjectReferenceCurve(copy, b, null);
                for (int i = 0; i < floats.Length; i++) AnimationUtility.SetEditorCurve(copy, mappedFloats[i], AnimationUtility.GetEditorCurve(source, floats[i]));
                for (int i = 0; i < objects.Length; i++) AnimationUtility.SetObjectReferenceCurve(copy, mappedObjects[i], AnimationUtility.GetObjectReferenceCurve(source, objects[i]));
                AnimationUtility.SetAnimationEvents(copy, Array.Empty<AnimationEvent>());
                AssetDatabase.CreateAsset(copy, destination); AssetDatabase.SaveAssetIfDirty(copy); return copy;
            }
            catch { if (!AssetDatabase.Contains(copy)) Object.DestroyImmediate(copy); throw; }
        }
    }
}
