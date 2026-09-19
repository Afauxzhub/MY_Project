using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.AnimationPipeline.Editor
{
    internal static class AnimationClipExporter
    {
        [MenuItem("Assets/Animation Pipeline/Export Selected FBX Clips", false, 2100)]
        private static void ExportSelected()
        {
            var paths = Selection.objects
                .Select(AssetDatabase.GetAssetPath)
                .Where(path => path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();

            if (paths.Length == 0)
            {
                EditorUtility.DisplayDialog("Animation Pipeline", "请先选中至少一个 FBX。", "确定");
                return;
            }

            int exported = 0;
            try
            {
                for (int i = 0; i < paths.Length; i++)
                {
                    EditorUtility.DisplayProgressBar("Animation Pipeline", paths[i], (float)i / paths.Length);
                    FbxAnimationImporter.ConfigureAndReimport(paths[i]);
                    exported += Export(paths[i]).Count;
                }
            }
            finally
            {
                EditorUtility.ClearProgressBar();
                AssetDatabase.SaveAssets();
                AssetDatabase.Refresh();
            }

            Debug.Log($"[AnimationPipeline] Exported {exported} clip(s) from {paths.Length} FBX file(s).");
        }

        [MenuItem("Assets/Animation Pipeline/Export Selected FBX Clips", true)]
        private static bool ValidateExportSelected()
        {
            return Selection.objects.Any(obj => AssetDatabase.GetAssetPath(obj).EndsWith(".fbx", StringComparison.OrdinalIgnoreCase));
        }

        internal static List<string> Export(string fbxPath)
        {
            AnimationPipelineSettings settings = AnimationPipelineSettings.instance;
            string outputFolder = BuildOutputFolder(fbxPath, settings);
            EnsureAssetFolder(outputFolder);

            AnimationClip[] clips = AssetDatabase.LoadAllAssetsAtPath(fbxPath)
                .OfType<AnimationClip>()
                .Where(clip => !clip.name.StartsWith("__preview__", StringComparison.OrdinalIgnoreCase))
                .ToArray();

            var results = new List<string>(clips.Length);
            string fbxName = Path.GetFileNameWithoutExtension(fbxPath);
            for (int i = 0; i < clips.Length; i++)
            {
                string assetName = clips.Length == 1 ? fbxName : fbxName + "_" + clips[i].name;
                string targetPath = outputFolder + "/" + SanitizeFileName(assetName) + ".anim";
                AnimationClip target = AssetDatabase.LoadAssetAtPath<AnimationClip>(targetPath);
                if (target == null)
                {
                    target = new AnimationClip();
                    EditorUtility.CopySerialized(clips[i], target);
                    target.name = assetName;
                    if (settings.OptimizeCurves) AnimationCurveOptimizer.Process(target);
                    AssetDatabase.CreateAsset(target, targetPath);
                }
                else
                {
                    EditorUtility.CopySerialized(clips[i], target);
                    target.name = assetName;
                    if (settings.OptimizeCurves) AnimationCurveOptimizer.Process(target);
                    EditorUtility.SetDirty(target);
                }
                AnimationPipelineHooks.RaiseClipExported(fbxPath, targetPath, target);
                results.Add(targetPath);
            }
            return results;
        }

        private static string BuildOutputFolder(string fbxPath, AnimationPipelineSettings settings)
        {
            if (settings.MirrorPersonalAnimationFolders && PersonalAnimationNaming.TryParse(
                Path.GetFileNameWithoutExtension(fbxPath), out _, out _, out _))
            {
                string outputPath = PersonalAnimationNaming.GetOutputPath(settings.SourceRoot, settings.OutputRoot, fbxPath);
                return Path.GetDirectoryName(outputPath).Replace('\\', '/');
            }
            string root = settings.OutputRoot;
            if (!settings.GroupByFirstTwoNameSegments)
                return root;
            string[] parts = Path.GetFileNameWithoutExtension(fbxPath).Split('_');
            string group = parts.Length >= 2 ? parts[0] + "_" + parts[1] : parts[0];
            return root + "/" + SanitizeFileName(group);
        }

        private static void EnsureAssetFolder(string assetFolder)
        {
            string projectRoot = Directory.GetParent(Application.dataPath).FullName;
            Directory.CreateDirectory(Path.Combine(projectRoot, assetFolder.Replace('/', Path.DirectorySeparatorChar)));
        }

        private static string SanitizeFileName(string value)
        {
            foreach (char invalid in Path.GetInvalidFileNameChars())
                value = value.Replace(invalid, '_');
            return value;
        }
    }

    internal sealed class AnimationAutoExportPostprocessor : AssetPostprocessor
    {
        private static void OnPostprocessAllAssets(
            string[] importedAssets,
            string[] deletedAssets,
            string[] movedAssets,
            string[] movedFromAssetPaths)
        {
            AnimationPipelineSettings settings = AnimationPipelineSettings.instance;
            if (!settings.AutoExportOnImport)
                return;

            bool changed = false;
            foreach (string path in importedAssets)
            {
                if (!settings.IsSourceFbx(path))
                    continue;
                changed |= AnimationClipExporter.Export(path).Count > 0;
            }
            if (changed)
                AssetDatabase.SaveAssets();
        }
    }
}
