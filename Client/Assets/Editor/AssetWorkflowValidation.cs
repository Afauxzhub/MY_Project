using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Afauxzhub.AnimationPipeline.Editor;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.Project.Editor
{
    /// <summary>Read-only validation. Never regenerates scenes, clips, or personal settings.</summary>
    public static class AssetWorkflowValidation
    {
        private static readonly string[] RequiredAssetFolders =
        {
            "Assets/Art/Animations/Role/Role_Player",
            "Assets/Art/Animations/Player/Locomotion",
            "Assets/Art/Characters/Player/Models",
            "Assets/Art/Characters/Player/Materials",
            "Assets/Art/Characters/Player/Textures",
            "Assets/Art/Environments", "Assets/Art/UI", "Assets/Art/Audio",
            "Assets/Generated/AnimationClips/Role_Player",
            "Assets/Generated/AnimationClips/Player/Locomotion",
            "Assets/Animations/Controllers", "Assets/Animations/Masks", "Assets/Animations/Authored",
            "Assets/GameData/Locomotion", "Assets/Prefabs/Characters", "Assets/ThirdParty"
        };

        private static readonly string[] RequiredSourceFolders =
        {
            "ArtSource/Characters/Player/Model", "ArtSource/Characters/Player/Rig",
            "ArtSource/Characters/Player/Animations/Locomotion", "ArtSource/Characters/Player/Textures",
            "ArtSource/Environments", "ArtSource/UI", "ArtSource/Audio"
        };

        private static readonly Regex AnimationName = new Regex(
            @"\A(Role|Monster|Elite|Boss|Npc|Scene)_[A-Z][A-Za-z0-9]*_[A-Z][A-Za-z0-9]*(?:_[A-Z][A-Za-z0-9]*)?\z",
            RegexOptions.CultureInvariant);

        [MenuItem("Tools/MY Project/Validate Asset Workflow")]
        public static void Validate()
        {
            string projectRoot = Directory.GetParent(Application.dataPath).FullName;
            string repositoryRoot = Directory.GetParent(projectRoot).FullName;
            var errors = new List<string>();

            foreach (string folder in RequiredAssetFolders)
                if (!AssetDatabase.IsValidFolder(folder)) errors.Add("Missing Unity folder: " + folder);
            foreach (string folder in RequiredSourceFolders)
                if (!Directory.Exists(Path.Combine(repositoryRoot, folder))) errors.Add("Missing source folder: " + folder);

            string settingsPath = Path.Combine(projectRoot, "ProjectSettings/AfauxzhubAnimationPipelineSettings.asset");
            if (!File.Exists(settingsPath)) errors.Add("Shared animation settings file is missing.");
            if (EditorSettings.serializationMode != SerializationMode.ForceText)
                errors.Add("Unity asset serialization must be Force Text.");

            var settings = AnimationPipelineSettings.instance;
            if (settings.SourceRoot != "Assets/Art/Animations") errors.Add("Unexpected FBX source root.");
            if (settings.OutputRoot != "Assets/Generated/AnimationClips") errors.Add("Unexpected clip output root.");
            if (!settings.GroupByFirstTwoNameSegments) errors.Add("Max bridge requires first-two-segment grouping.");
            if (!settings.MirrorPersonalAnimationFolders) errors.Add("Personal names require mirrored FBX subfolders.");
            if (settings.OptimizeCurves || settings.AnimationCompression != ModelImporterAnimationCompression.Off)
                errors.Add("Initial animation acceptance requires curve optimization and import compression disabled.");
            if (!settings.AutoExportOnImport) errors.Add("Project workflow requires automatic clip export on FBX import.");
            if (settings.RootNode != "Root" || settings.MotionNodeName != "Root")
                errors.Add("Player root and motion node settings must match the confirmed name: Root (case-sensitive).");

            int fbxCount = ValidateAnimationNames(settings.SourceRoot, errors);
            if (errors.Count > 0)
                throw new InvalidOperationException("Asset workflow validation failed:\n" + string.Join("\n", errors));

            string publicationStatus = settings.AutoExportOnImport
                ? "Auto export enabled; verify the real rig/clip separately."
                : "Auto export disabled; rig/first-clip acceptance is pending.";
            Debug.Log($"[MY_Project AssetWorkflow] PASS: directories and shared import settings validated; "
                + $"{fbxCount} animation FBX checked. {publicationStatus}");
        }

        private static int ValidateAnimationNames(string sourceRoot, List<string> errors)
        {
            if (!Directory.Exists(sourceRoot)) return 0;
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            string[] paths = Directory.GetFiles(sourceRoot, "*", SearchOption.AllDirectories)
                .Where(path => string.Equals(Path.GetExtension(path), ".fbx", StringComparison.OrdinalIgnoreCase))
                .ToArray();

            foreach (string path in paths)
            {
                string name = Path.GetFileNameWithoutExtension(path);
                if (!AnimationName.IsMatch(name) && !PersonalAnimationNaming.TryParse(name, out _, out _, out _))
                    errors.Add("Invalid animation name: " + path);
                if (!names.Add(name)) errors.Add("Duplicate FBX basename would overwrite a generated clip: " + name);

                string assetPath = path.Replace('\\', '/');
                int clipCount = AssetDatabase.LoadAllAssetsAtPath(assetPath).OfType<AnimationClip>()
                    .Count(clip => !clip.name.StartsWith("__preview__", StringComparison.OrdinalIgnoreCase));
                if (clipCount != 1) errors.Add($"Expected one imported animation clip, found {clipCount}: {path}");
            }
            return paths.Length;
        }
    }
}
