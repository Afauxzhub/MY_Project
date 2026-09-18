using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.AnimationPipeline.Editor
{
    [InitializeOnLoad]
    internal static class RootMotionPublishBridge
    {
        [Serializable]
        private sealed class LocateRequest
        {
            public string asset_path;
            public string absolute_path;
        }

        private static readonly string RequestFilePath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Afauxzhub",
            "AnimationPipeline",
            "unity_bridge_request.json");

        private static double nextPollTime;
        private static string pendingAssetPath;
        private static double pendingDeadline;

        static RootMotionPublishBridge()
        {
            nextPollTime = EditorApplication.timeSinceStartup + 0.5d;
            EditorApplication.update += OnEditorUpdate;
        }

        [MenuItem("Tools/Animation Pipeline/Process Max Locate Request")]
        private static void ProcessLocateRequestMenu()
        {
            TryLoadRequest();
            TryResolvePendingRequest(true);
        }

        private static void OnEditorUpdate()
        {
            double now = EditorApplication.timeSinceStartup;
            if (now < nextPollTime)
                return;
            nextPollTime = now + 0.5d;
            if (string.IsNullOrEmpty(pendingAssetPath)) TryLoadRequest();
            if (!string.IsNullOrEmpty(pendingAssetPath)) TryResolvePendingRequest(false);
        }

        private static void TryLoadRequest()
        {
            if (!File.Exists(RequestFilePath))
                return;
            try
            {
                string json = File.ReadAllText(RequestFilePath);
                File.Delete(RequestFilePath);
                LocateRequest request = JsonUtility.FromJson<LocateRequest>(json);
                string path = request?.asset_path?.Replace('\\', '/');
                if (string.IsNullOrEmpty(path)
                    || !(path == "Assets" || path.StartsWith("Assets/", StringComparison.Ordinal)))
                {
                    Debug.LogWarning("[AnimationPipeline] Ignored invalid locate request.");
                    return;
                }
                pendingAssetPath = path;
                pendingDeadline = EditorApplication.timeSinceStartup + 20d;
                AssetDatabase.Refresh();
            }
            catch (Exception exception)
            {
                Debug.LogWarning("[AnimationPipeline] Failed to read locate request: " + exception.Message);
            }
        }

        private static void TryResolvePendingRequest(bool forceRefresh)
        {
            if (forceRefresh) AssetDatabase.Refresh();
            UnityEngine.Object target = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(pendingAssetPath);
            if (target != null)
            {
                EditorUtility.FocusProjectWindow();
                Selection.activeObject = target;
                EditorGUIUtility.PingObject(target);
                pendingAssetPath = null;
                pendingDeadline = 0d;
                return;
            }
            if (EditorApplication.timeSinceStartup <= pendingDeadline)
                return;
            Debug.LogWarning("[AnimationPipeline] Timed out locating: " + pendingAssetPath);
            pendingAssetPath = null;
            pendingDeadline = 0d;
        }
    }
}
