using System;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Afauxzhub.Project.Editor.Animation
{
    // Validate only actors in the scene being played/built. Never rewrites source data on reimport.
    [InitializeOnLoad]
    public sealed class RootMotionGuards : IProcessSceneWithReport
    {
        public int callbackOrder => 0;
        static RootMotionGuards()
        {
            EditorApplication.playModeStateChanged += state =>
            {
                if (state != PlayModeStateChange.ExitingEditMode) return;
                try
                {
                    foreach (var player in UnityEngine.Object.FindObjectsByType<MotionLibraryPlayer>(FindObjectsInactive.Include, FindObjectsSortMode.None)) Validate(player);
                }
                catch (Exception error) { Debug.LogError(error.Message); EditorApplication.isPlaying = false; }
            };
        }
        public static void Validate(MotionLibraryPlayer player)
        {
            if (player.library == null) return;
            RootMotionBaker.RequireCurrent(player.library);
            var profile = player.driver != null ? player.driver.profile : null;
            if (profile == null) return;
            foreach (var action in profile.actions)
            {
                // Old graybox root actions without a baked track remain visibly held at runtime.
                if (action == null || action.movement != MovementAuthority.RootMotion || action.rootMotion?.track == null) continue;
                if (!RootMotionBaker.Current(action.rootMotion.track, player.library.model, action.clip))
                    throw new BuildFailedException("Stale Root Motion action: " + action.name + ". Re-extract for this character before Play/build.");
            }
        }
        public void OnProcessScene(Scene scene, BuildReport report)
        {
            if (report == null) return;
            foreach (var root in scene.GetRootGameObjects()) foreach (var player in root.GetComponentsInChildren<MotionLibraryPlayer>(true)) Validate(player);
        }
    }
}
