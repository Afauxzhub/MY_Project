using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    /// <summary>Opt-in local lab copy. No asset names, company paths, or trajectory samples in code.</summary>
    public static class RootMotionLabSetup
    {
        [MenuItem("Tools/MY Project/Animation/Create Root Motion Lab Copy")]
        public static void CreateSelected()
        {
            string scenePath = EditorUtility.SaveFilePanelInProject("Name a new LOCAL lab folder", "RootMotionLab", "unity", "Choose an existing LocalAnimationLab parent and a NEW name. A same-named folder containing RootMotionLab.unity will be created. Timings are lab tuning only.", "Assets/LocalAnimationLab");
            if (!string.IsNullOrEmpty(scenePath)) Create(Path.GetDirectoryName(scenePath).Replace('\\', '/') + "/" + Path.GetFileNameWithoutExtension(scenePath));
        }

        public static MotionLibrary Create(string folder, string sceneName = "RootMotionLab.unity")
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode || SceneManager.sceneCount != 1) throw new InvalidOperationException("Use one clean saved local lab outside Play.");
            var scene = SceneManager.GetActiveScene();
            var actors = Object.FindObjectsByType<MotionLibraryPlayer>(FindObjectsSortMode.None);
            if (scene.isDirty || !scene.path.StartsWith("Assets/LocalAnimationLab/", StringComparison.Ordinal) || actors.Length != 1)
                throw new InvalidOperationException("Expected one no-wires actor in a clean LOCAL reference scene.");
            if (!folder.StartsWith("Assets/LocalAnimationLab/", StringComparison.Ordinal) || Path.GetFileName(sceneName) != sceneName || Path.GetExtension(sceneName) != ".unity")
                throw new ArgumentException("Root trajectories derived from reference clips stay in a new LocalAnimationLab subfolder.");
            var source = actors[0];
            if (source.library == null || source.driver == null || source.driver.animator == null || source.driver.combat == null
                || source.library.relaxedMovement == null || source.library.readyMovement == null)
                throw new InvalidOperationException("Assign the library, both movement profiles, driver, Animator and combat adapter first.");
            var sourceProfile = source.driver.profile;
            MotionCharacterWizard.Preflight(source.library.model, source.library, folder, true);
            if (sourceProfile == null) throw new InvalidOperationException("Combat profile missing.");
            // Audit/extract BEFORE any persistent writes. Never guesses missing root curves or bone paths.
            var tracks = new Dictionary<AnimationClip, RootMotionTrack>();
            foreach (var clip in source.library.entries.Where(e => e.clip != null).Select(e => e.clip)
                .Concat(sourceProfile.actions.Where(a => a != null && a.clip != null).Select(a => a.clip)).Distinct())
                tracks[clip] = RootMotionBaker.Bake(source.library.model, clip);
            var library = Object.Instantiate(source.library); library.name = "Root Motion library";
            string parent = folder.Substring(0, folder.LastIndexOf('/'));
            if (!AssetDatabase.IsValidFolder(parent)) throw new ArgumentException("Parent folder must exist.");
            AssetDatabase.CreateFolder(parent, Path.GetFileName(folder));
            AssetDatabase.CreateAsset(library, folder + "/Motions.asset");
            library.relaxedMovement = Object.Instantiate(source.library.relaxedMovement);
            library.readyMovement = Object.Instantiate(source.library.readyMovement);
            AssetDatabase.AddObjectToAsset(library.relaxedMovement, library); AssetDatabase.AddObjectToAsset(library.readyMovement, library);
            if (source.library.templates != null) { library.templates = Object.Instantiate(source.library.templates); AssetDatabase.AddObjectToAsset(library.templates, library); }
            // Slow run fallbacks remain marked missing Walk; never pretend a different gait was authored.
            library.minimumPlaybackScale = Mathf.Min(0.1f, library.minimumPlaybackScale);
            foreach (var e in library.entries.Where(e => e.clip != null))
            {
                var track = tracks[e.clip];
                bool arc = e.slot >= MotionSlot.ArcLeft && e.slot <= MotionSlot.SprintRight;
                e.rootMotion = new RootMotionSettings { enabled = true, track = track, rotation = arc };
                bool loop = e.slot == MotionSlot.Walk || e.slot == MotionSlot.Run || e.slot == MotionSlot.Sprint || arc
                    || e.slot >= MotionSlot.StrafeForward && e.slot <= MotionSlot.StrafeBackRight;
                float travel = 0;
                for (int i = 1; i < track.positions.Length; i++) travel += Vector3.Distance(track.positions[i - 1], track.positions[i]);
                if (loop && travel > 0.001f) { e.referenceSpeed = travel / e.clip.length; e.matchPlaybackToSpeed = true; }
                if (!loop && e.slot != MotionSlot.Idle && e.slot != MotionSlot.IdleVariation)
                    e.stageSeconds = e.clip.length * (e.outPoint - e.inPoint);
                e.note += "\nLOCAL ROOT LAB: native extracted trajectory; authored speed matching for loops; one-shot timing follows clip. Missing slots unchanged.";
            }
            var profile = Object.Instantiate(sourceProfile); profile.name = "Root Motion combat profile"; profile.controller = null; profile.footIKWeight = 0;
            profile.sheathed.movement = library.relaxedMovement; profile.drawn.movement = library.readyMovement;
            AssetDatabase.CreateAsset(profile, folder + "/Combat.asset");
            var map = new Dictionary<ActionDefinition, ActionDefinition>();
            ActionDefinition CopyAction(ActionDefinition original)
            {
                if (original == null) return null;
                if (map.TryGetValue(original, out var existing)) return existing;
                var copy = Object.Instantiate(original); copy.name = original.name; map.Add(original, copy);
                AssetDatabase.AddObjectToAsset(copy, profile);
                copy.nextLight = CopyAction(original.nextLight); copy.nextHeavy = CopyAction(original.nextHeavy); copy.onRelease = CopyAction(original.onRelease);
                if (copy.clip != null)
                {
                    if (!tracks.TryGetValue(copy.clip, out var track)) track = RootMotionBaker.Bake(library.model, copy.clip);
                    copy.rootMotion = new RootMotionSettings { enabled = true, track = track };
                    copy.movement = MovementAuthority.RootMotion; copy.applyRootRotation = true;
                    // Explicit LOCAL presentation retime; preserve relative permission ordering, not balance values.
                    float scale = copy.clip.length / Mathf.Max(0.01f, copy.duration);
                    copy.duration = copy.clip.length; copy.activeStart *= scale; copy.recoveryStart *= scale;
                    foreach (var w in copy.windows) { w.start *= scale; w.end *= scale; }
                    foreach (var cue in copy.cues) cue.time *= scale;
                    copy.notes += "\nLOCAL ROOT LAB: duration/windows scaled together to source clip length. Not accepted combat balance.";
                }
                EditorUtility.SetDirty(copy); return copy;
            }
            profile.actions = sourceProfile.actions.Select(CopyAction).ToList();
            EditorUtility.SetDirty(profile); EditorUtility.SetDirty(library);
            AssetDatabase.SaveAssetIfDirty(profile); AssetDatabase.SaveAssetIfDirty(library);
            string destination = folder + "/" + sceneName;
            if (!AssetDatabase.CopyAsset(scene.path, destination)) throw new InvalidOperationException("Could not copy scene. New assets kept for inspection.");
            var created = EditorSceneManager.OpenScene(destination, OpenSceneMode.Single);
            // Opening a scene unloads unused assets: local managed references are not a Unity retain.
            library = AssetDatabase.LoadAssetAtPath<MotionLibrary>(folder + "/Motions.asset");
            profile = AssetDatabase.LoadAssetAtPath<CharacterAnimationProfile>(folder + "/Combat.asset");
            if (library == null || profile == null) throw new InvalidOperationException("New configuration could not be reloaded.");
            var player = Object.FindFirstObjectByType<MotionLibraryPlayer>(); var driver = player.driver;
            // Unpack only the new scene's instance, so no source Prefab overrides can be applied accidentally.
            var prefab = PrefabUtility.GetOutermostPrefabInstanceRoot(driver.gameObject);
            if (prefab != null) PrefabUtility.UnpackPrefabInstance(prefab, PrefabUnpackMode.Completely, InteractionMode.AutomatedAction);
            player.library = library; driver.profile = profile; driver.combat.profile = profile;
            driver.animator.runtimeAnimatorController = null; driver.animator.applyRootMotion = false;
            foreach (var ik in driver.GetComponentsInChildren<GenericFootIK>(true)) ik.enabled = false;
            RootMotionGuards.Validate(player);
            EditorSceneManager.MarkSceneDirty(created);
            if (!EditorSceneManager.SaveScene(created)) throw new InvalidOperationException("New lab scene save failed.");
            return library;
        }
    }
}
