using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;

namespace Afauxzhub.Project.Editor
{
    public static class ProjectBaselineValidation
    {
        private const string BootstrapScenePath = "Assets/Scenes/Bootstrap.unity";

        private static readonly string[] RequiredPackages =
        {
            "com.afauxzhub.animation-pipeline",
            "com.afauxzhub.character-locomotion",
            "com.afauxzhub.timeline-abilities"
        };

        [MenuItem("Tools/MY Project/Create or Validate Baseline")]
        public static void CreateOrValidate()
        {
            ValidatePackages();
            CreateOrOpenBootstrapScene();
            EnsureBootstrapSceneIsInBuildSettings();
            AssetDatabase.SaveAssets();

            UnityEngine.Debug.Log(
                "[MY_Project Baseline] PASS: required packages are registered and Bootstrap.unity is saved.");
        }

        private static void ValidatePackages()
        {
            var registeredNames = UnityEditor.PackageManager.PackageInfo.GetAllRegisteredPackages()
                .Select(package => package.name)
                .ToArray();

            var missingPackages = RequiredPackages
                .Where(required => !registeredNames.Contains(required, StringComparer.Ordinal))
                .ToArray();

            if (missingPackages.Length > 0)
            {
                throw new InvalidOperationException(
                    $"Required local packages are not registered: {string.Join(", ", missingPackages)}");
            }
        }

        private static void CreateOrOpenBootstrapScene()
        {
            if (File.Exists(BootstrapScenePath))
            {
                EditorSceneManager.OpenScene(BootstrapScenePath, OpenSceneMode.Single);
                return;
            }

            Directory.CreateDirectory(Path.GetDirectoryName(BootstrapScenePath) ?? "Assets");
            var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);

            if (!EditorSceneManager.SaveScene(scene, BootstrapScenePath))
            {
                throw new InvalidOperationException($"Failed to save bootstrap scene at {BootstrapScenePath}.");
            }
        }

        private static void EnsureBootstrapSceneIsInBuildSettings()
        {
            var scenes = EditorBuildSettings.scenes.ToList();
            var existingIndex = scenes.FindIndex(scene => scene.path == BootstrapScenePath);

            if (existingIndex >= 0)
            {
                scenes[existingIndex] = new EditorBuildSettingsScene(BootstrapScenePath, true);
            }
            else
            {
                scenes.Add(new EditorBuildSettingsScene(BootstrapScenePath, true));
            }

            EditorBuildSettings.scenes = scenes.ToArray();
        }
    }
}
