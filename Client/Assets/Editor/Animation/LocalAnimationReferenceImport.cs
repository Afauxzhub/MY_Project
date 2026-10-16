using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.Project.Editor.Animation
{
    public static class LocalAnimationReferenceImport
    {
        [MenuItem("Tools/MY Project/Animation/Import Prepared LOCAL Reference Pack…")]
        public static void Import()
        {
            if (Application.isPlaying) { EditorUtility.DisplayDialog("Local reference", "Exit Play Mode first.", "OK"); return; }
            string source = EditorUtility.OpenFolderPanel("Select pack prepared by prepare-local-animation-reference.ps1", "", "");
            if (string.IsNullOrEmpty(source)) return;
            if (!File.Exists(Path.Combine(source, "local-manifest.json")) || !File.Exists(Path.Combine(source, "Model.prefab"))) { EditorUtility.DisplayDialog("Local reference", "Not a prepared local reference pack.", "OK"); return; }
            string destination = "Assets/LocalAnimationLab/" + Path.GetFileName(source);
            if (Directory.Exists(destination)) { EditorUtility.DisplayDialog("Local reference", "Destination already exists. No files overwritten.", "OK"); return; }
            if (!EditorUtility.DisplayDialog("Local-only assets", "Import this prepared pack under ignored Assets/LocalAnimationLab? Source files stay untouched. A local neutral material will replace missing source shaders. Do not commit this directory or dependencies.", "Import", "Cancel")) return;
            ImportPreparedPack(source);
            EditorUtility.DisplayDialog("Local reference imported", "Create the character profile, Animator and lab scene inside the same LocalAnimationLab directory. Run binding coverage before mixing movement sets; hierarchy compatibility is not assumed.", "OK");
        }

        public static GameObject ImportPreparedPack(string source)
        {
            if (Application.isPlaying) throw new InvalidOperationException("Exit Play Mode first.");
            source = Path.GetFullPath(source).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (!File.Exists(Path.Combine(source, "local-manifest.json")) || !File.Exists(Path.Combine(source, "Model.prefab"))) throw new InvalidOperationException("Not a prepared local reference pack.");
            string destination = "Assets/LocalAnimationLab/" + Path.GetFileName(source);
            if (Directory.Exists(destination)) throw new InvalidOperationException("Destination exists; no reference files overwritten.");
            foreach (string file in Directory.GetFiles(source, "*", SearchOption.AllDirectories))
            {
                string extension = Path.GetExtension(file).ToLowerInvariant();
                if (extension != ".meta" && extension != ".anim" && extension != ".prefab" && extension != ".asset" && extension != ".json") throw new InvalidOperationException("Unexpected pack file type: " + extension);
            }
            Directory.CreateDirectory(destination);
            AssetDatabase.StartAssetEditing();
            try
            {
                foreach (string file in Directory.GetFiles(source, "*", SearchOption.AllDirectories))
                {
                    string relative = file.Substring(source.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar).Length).TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                    string target = Path.Combine(destination, relative); Directory.CreateDirectory(Path.GetDirectoryName(target)); File.Copy(file, target, false);
                }
            }
            finally { AssetDatabase.StopAssetEditing(); AssetDatabase.Refresh(); }
            var shader = Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard");
            var material = new Material(shader) { name = "LocalNeutral", color = new Color(0.55f, 0.62f, 0.7f) };
            AssetDatabase.CreateAsset(material, destination + "/LocalNeutral.mat");
            string prefabPath = destination + "/Model.prefab";
            var contents = PrefabUtility.LoadPrefabContents(prefabPath);
            try
            {
                foreach (var renderer in contents.GetComponentsInChildren<Renderer>(true))
                {
                    int count = renderer is SkinnedMeshRenderer skin && skin.sharedMesh != null ? skin.sharedMesh.subMeshCount : 1;
                    var materials = new Material[Mathf.Max(1, count)]; for (int i = 0; i < materials.Length; i++) materials[i] = material; renderer.sharedMaterials = materials;
                }
                PrefabUtility.SaveAsPrefabAsset(contents, prefabPath);
            }
            finally { PrefabUtility.UnloadPrefabContents(contents); }
            Selection.activeObject = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath); AssetDatabase.SaveAssetIfDirty(material);
            return (GameObject)Selection.activeObject;
        }
    }
}
