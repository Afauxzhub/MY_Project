using System;
using System.IO;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    public static class MotionLibraryBuilder
    {
        [MenuItem("Tools/MY Project/Animation/Create No-Wires Library from Selected Profile")]
        public static void CreateSelected()
        {
            var profile = Selection.activeObject as CharacterAnimationProfile;
            if (profile == null) throw new InvalidOperationException("Select a CharacterAnimationProfile asset first.");
            string path = EditorUtility.SaveFilePanelInProject("New no-wires library", "MotionLibrary", "asset", "Existing assets are not overwritten.");
            if (!string.IsNullOrEmpty(path)) MotionWorkbench.Open(Create(profile, path));
        }
        public static MotionLibrary Create(CharacterAnimationProfile source, string path)
        {
            if (Application.isPlaying || source == null) throw new InvalidOperationException("Select a profile outside Play Mode.");
            ValidateNew(path, ".asset"); AnimationBindingTools.RequireLocalDestination(path, source);
            var library = ScriptableObject.CreateInstance<MotionLibrary>(); library.name = Path.GetFileNameWithoutExtension(path);
            library.model = source.previewModel;
            AssetDatabase.CreateAsset(library, path);
            foreach (WeaponStance stance in Enum.GetValues(typeof(WeaponStance)))
            {
                var movement = Object.Instantiate(source.Set(stance).movement); movement.name = stance + " tuning";
                if (stance == WeaponStance.Sheathed) library.relaxedMovement = movement; else library.readyMovement = movement;
                AssetDatabase.AddObjectToAsset(movement, library);
                foreach (MotionSlot slot in Enum.GetValues(typeof(MotionSlot)))
                {
                    var old = source.Set(stance).Find(slot);
                    library.entries.Add(new MotionEntry { stance = stance, slot = slot, clip = old?.clip, speed = old != null ? old.playbackSpeed : 1,
                        direction = slot == MotionSlot.Start ? MotionDirection.Forward : MotionDirection.Any,
                        note = old?.clip != null ? "Imported explicit legacy assignment; verify pose/transition quality." : "MISSING — runtime fallback is not animation acceptance." });
                }
                // Explicit multi-direction start and per-gait targeting gaps; never infer or mirror clips.
                foreach (MotionDirection direction in Enum.GetValues(typeof(MotionDirection)))
                    if (direction != MotionDirection.Any && direction != MotionDirection.Forward)
                        library.entries.Add(new MotionEntry { stance = stance, slot = MotionSlot.Start, direction = direction, note = "MISSING directional start" });
                foreach (MotionGait gait in new[] { MotionGait.Walk, MotionGait.Run, MotionGait.Sprint })
                    for (int s = (int)MotionSlot.StrafeForward; s <= (int)MotionSlot.StrafeBackRight; s++)
                        library.entries.Add(new MotionEntry { stance = stance, slot = (MotionSlot)s, gait = gait, note = "Optional gait-specific override; Any may be explicitly shared." });
            }
            var templates = ScriptableObject.CreateInstance<MotionRecipeTemplates>(); templates.name = "Shared transition templates";
            templates.recipes.Add(new MotionRecipe { label = "Default", from = MotionFamily.Any, to = MotionFamily.Any });
            templates.recipes.Add(new MotionRecipe { label = "Start", to = MotionFamily.Start, blendSeconds = 0.12f });
            templates.recipes.Add(new MotionRecipe { label = "Stop", to = MotionFamily.Stop, blendSeconds = 0.14f });
            templates.recipes.Add(new MotionRecipe { label = "Land", to = MotionFamily.Land, blendSeconds = 0.08f });
            AssetDatabase.AddObjectToAsset(templates, library); library.templates = templates;
            // One immediately editable, scoped override demonstrates the recipe workflow.
            library.overrides.Add(new MotionRecipe { label = "Idle to movement", from = MotionFamily.Idle, to = MotionFamily.Move });
            EditorUtility.SetDirty(library); AssetDatabase.SaveAssetIfDirty(library); return library;
        }
        public static void CreateSceneCopy(string sourceScene, string destination, MotionLibrary library)
        {
            if (Application.isPlaying || library == null) throw new InvalidOperationException("Assign a library outside Play Mode.");
            ValidateNew(destination, ".unity"); AnimationBindingTools.RequireLocalDestination(destination, library);
            for (int i = 0; i < UnityEngine.SceneManagement.SceneManager.sceneCount; i++)
                if (UnityEngine.SceneManagement.SceneManager.GetSceneAt(i).isDirty) throw new InvalidOperationException("A loaded scene is dirty. No scene was closed or saved.");
            if (!AssetDatabase.CopyAsset(sourceScene, destination)) throw new InvalidOperationException("Scene copy failed.");
            var scene = EditorSceneManager.OpenScene(destination, OpenSceneMode.Single);
            AnimatedCharacterDriver driver = null;
            foreach (var root in scene.GetRootGameObjects())
            {
                var candidates = root.GetComponentsInChildren<AnimatedCharacterDriver>(true);
                foreach (var candidate in candidates)
                { if (driver != null) throw new InvalidOperationException("Expected a single lab character."); driver = candidate; }
            }
            if (driver == null) throw new InvalidOperationException("Source scene has no animated character.");
            var player = driver.gameObject.AddComponent<MotionLibraryPlayer>(); player.library = library; player.driver = driver; driver.motionPlayer = player;
            driver.animator.runtimeAnimatorController = null;
            var ik = driver.GetComponent<GenericFootIK>(); if (ik != null) ik.enabled = false;
            PrefabUtility.RecordPrefabInstancePropertyModifications(driver);
            PrefabUtility.RecordPrefabInstancePropertyModifications(driver.animator);
            if (ik != null) PrefabUtility.RecordPrefabInstancePropertyModifications(ik);
            EditorSceneManager.MarkSceneDirty(scene); EditorSceneManager.SaveScene(scene, destination);
            Selection.activeGameObject = driver.gameObject; MotionWorkbench.Open(library);
        }
        private static void ValidateNew(string path, string extension)
        {
            if (string.IsNullOrEmpty(path) || !path.StartsWith("Assets/", StringComparison.Ordinal) || Path.GetExtension(path) != extension || path.Contains("..")) throw new ArgumentException("Choose an Assets path with the correct extension.");
            if (File.Exists(path) || AssetDatabase.LoadMainAssetAtPath(path) != null) throw new InvalidOperationException("Existing assets are never overwritten by creation.");
        }
    }
}
