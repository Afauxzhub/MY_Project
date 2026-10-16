using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    [Serializable] public sealed class MotionCoverageRow
    {
        public string selector, expectedName, status, clip, note;
        public bool optional;
    }
    [Serializable] public sealed class MotionCoverageReport
    {
        public string library, generatedUtc;
        public MotionCoverageRow[] rows;
    }
    public sealed class MotionBindingAudit
    {
        public int curves;
        public readonly List<string> missing = new List<string>();
        public bool Compatible => curves > 0 && missing.Count == 0;
        public override string ToString() => $"{curves} curves; {missing.Count} binding issues" + (missing.Count > 0 ? "\n" + string.Join("\n", missing.Take(12)) : "");
    }
    public sealed class MotionCandidate
    {
        public MotionEntry entry;
        public AnimationClip[] choices;
        public int selected;
        public bool apply;
        public AnimationClip Clip => selected >= 0 && selected < choices.Length ? choices[selected] : null;
    }

    /// <summary>Editor-only audit and explicit assignment. Scanning never edits assets or approves animation quality.</summary>
    public static class MotionAuthoringTools
    {
        public static MotionBindingAudit Audit(GameObject model, AnimationClip clip)
        {
            var result = new MotionBindingAudit();
            if (model == null) result.missing.Add("No model assigned");
            if (clip == null) { result.missing.Add("No clip assigned"); return result; }
            var bindings = AnimationUtility.GetCurveBindings(clip).Concat(AnimationUtility.GetObjectReferenceCurveBindings(clip)).ToArray();
            result.curves = bindings.Length;
            if (clip.humanMotion)
            {
                var animator = model != null ? model.GetComponentInChildren<Animator>(true) : null;
                if (animator == null || animator.avatar == null || !animator.avatar.isValid || !animator.avatar.isHuman)
                    result.missing.Add("Humanoid clip requires a valid Humanoid avatar on the model");
            }
            foreach (var binding in bindings)
            {
                var node = model == null ? null : string.IsNullOrEmpty(binding.path) ? model.transform : model.transform.Find(binding.path);
                // Humanoid muscle and root curves bind to the preview Animator, not a transform component.
                if (clip.humanMotion && binding.type == typeof(Animator) && string.IsNullOrEmpty(binding.path)) continue;
                if (node == null || binding.type != typeof(GameObject) && binding.type != typeof(Transform) && node.GetComponent(binding.type) == null)
                {
                    string item = binding.path + " [" + binding.type.Name + "]";
                    if (!result.missing.Contains(item)) result.missing.Add(item);
                }
            }
            if (bindings.Length == 0) result.missing.Add("Clip has no editable animation curves");
            return result;
        }
        public static string Fingerprint(GameObject model, AnimationClip clip)
        {
            string Stamp(Object asset)
            {
                if (asset == null) return "null";
                string path = AssetDatabase.GetAssetPath(asset);
                if (string.IsNullOrEmpty(path)) return "unsaved:" + asset.GetInstanceID();
                AssetDatabase.TryGetGUIDAndLocalFileIdentifier(asset, out string guid, out long id);
                return guid + ":" + id + ":" + AssetDatabase.GetAssetDependencyHash(path);
            }
            return Stamp(model) + "|" + Stamp(clip);
        }
        public static string Status(MotionLibrary library, MotionEntry entry)
        {
            if (entry == null) return "Missing slot";
            if (!entry.enabled) return "Disabled";
            if (entry.clip == null) return "Missing clip";
            if (entry.review == MotionReview.Placeholder) return "Placeholder";
            if (entry.review != MotionReview.Approved) return "Pending review";
            return entry.reviewedFingerprint == Fingerprint(library.model, entry.clip) ? "Reviewed" : "Review stale (asset changed)";
        }
        public static MotionCoverageReport Coverage(MotionLibrary library)
        {
            var expected = MotionCatalog.Requirements().ToList();
            var keys = new HashSet<string>(expected.Select(MotionCatalog.Selector));
            expected.AddRange(library.entries.Where(e => e != null && keys.Add(MotionCatalog.Selector(e))));
            return new MotionCoverageReport { library = library.name, generatedUtc = DateTime.UtcNow.ToString("o"), rows = expected.Select(requirement =>
            {
                var actual = library.entries.FirstOrDefault(e => e != null && MotionCatalog.Selector(e) == MotionCatalog.Selector(requirement));
                string status = Status(library, actual);
                // Gait refinements can deliberately share the generic slot. Do not count them as mandatory missing clips.
                if (requirement.optional && (actual == null || actual.clip == null) && requirement.gait != MotionGait.Any)
                {
                    var shared = library.Find(requirement.stance, requirement.slot, requirement.gait, requirement.direction, requirement.mode, -1, -1, out _);
                    if (shared != null) status = "Optional; shares " + shared.slot + " (" + Status(library, shared) + ")";
                }
                return new MotionCoverageRow { selector = MotionCatalog.Selector(requirement), expectedName = MotionCatalog.SuggestedSuffix(requirement),
                    status = status, optional = requirement.optional || actual != null && actual.optional,
                    clip = actual?.clip != null ? AssetDatabase.GetAssetPath(actual.clip) + " :: " + actual.clip.name : "", note = actual?.note ?? requirement.note };
            }).ToArray() };
        }
        public static string CoverageText(MotionCoverageReport report)
        {
            var text = new StringBuilder("Motion coverage — " + report.library + "\n" + report.generatedUtc + "\n");
            text.AppendLine("Any = deliberately shared selector; optional refinements are not mandatory assets. Reviewed means human-marked, not automatic visual acceptance.");
            foreach (var row in report.rows) text.AppendLine($"{row.selector} | {(row.optional ? "OPTIONAL" : "BASE")} | {row.status} | name: {row.expectedName} | {row.clip} | {row.note}");
            return text.ToString();
        }
        private static string Normalize(string value) => new string((value ?? "").Where(char.IsLetterOrDigit).Select(char.ToLowerInvariant).ToArray());
        public static List<MotionCandidate> Propose(MotionLibrary library, IEnumerable<AnimationClip> clips, WeaponStance stance, string prefix)
        {
            var available = clips.Where(c => c != null && !c.name.StartsWith("__preview__", StringComparison.Ordinal)).Distinct().ToArray();
            var result = new List<MotionCandidate>();
            foreach (var entry in library.entries.Where(e => e != null && e.stance == stance))
            {
                string expected = Normalize(string.IsNullOrWhiteSpace(entry.matchName) ? MotionCatalog.SuggestedSuffix(entry) : entry.matchName);
                var matches = available.Where(c =>
                {
                    string name = c.name;
                    if (!string.IsNullOrEmpty(prefix)) { if (!name.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) return false; name = name.Substring(prefix.Length); }
                    return Normalize(name) == expected;
                }).ToArray();
                if (matches.Length > 0) result.Add(new MotionCandidate { entry = entry, choices = matches, selected = matches.Length == 1 ? 0 : -1 });
            }
            return result;
        }
        public static AnimationClip[] Scan(string folder)
        {
            if (!AssetDatabase.IsValidFolder(folder) || !folder.StartsWith("Assets/", StringComparison.Ordinal)) throw new ArgumentException("Select an Assets subfolder.");
            return AssetDatabase.FindAssets("t:AnimationClip", new[] { folder }).Select(AssetDatabase.GUIDToAssetPath).Distinct()
                .SelectMany(AssetDatabase.LoadAllAssetsAtPath).OfType<AnimationClip>().Where(c => !c.name.StartsWith("__preview__", StringComparison.Ordinal)).ToArray();
        }
        public static int Apply(MotionLibrary draft, IEnumerable<MotionCandidate> candidates, bool overwrite)
        {
            var rows = candidates.Where(c => c.apply).ToArray();
            // Preflight the entire request before one assignment is made.
            foreach (var row in rows)
            {
                if (!draft.entries.Contains(row.entry) || row.Clip == null) throw new InvalidOperationException("Resolve every checked candidate explicitly.");
                if (row.entry.clip != null && row.entry.clip != row.Clip && !overwrite) throw new InvalidOperationException("Existing clip protected: " + MotionCatalog.Selector(row.entry));
                var audit = Audit(draft.model, row.Clip);
                if (!audit.Compatible) throw new InvalidOperationException(row.Clip.name + ": " + audit);
            }
            Undo.RecordObject(draft, "Apply reviewed motion candidates");
            foreach (var row in rows) { row.entry.clip = row.Clip; row.entry.review = MotionReview.Pending; row.entry.reviewedFingerprint = ""; }
            return rows.Length;
        }
        public static void GuardDestination(string destination, params Object[] references)
        {
            if (destination.StartsWith("Assets/LocalAnimationLab/", StringComparison.Ordinal)) return;
            foreach (var reference in references.Where(r => r != null))
            {
                string path = AssetDatabase.GetAssetPath(reference);
                AnimationBindingTools.RequireLocalDestination(destination, reference);
                if (!string.IsNullOrEmpty(path) && AssetDatabase.GetDependencies(path, true).Any(p => p.StartsWith("Assets/LocalAnimationLab/", StringComparison.Ordinal)))
                    throw new InvalidOperationException("Reference-only dependencies must remain in Assets/LocalAnimationLab.");
            }
        }
    }
}
