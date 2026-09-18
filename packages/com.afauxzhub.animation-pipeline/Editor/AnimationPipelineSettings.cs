using System;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.AnimationPipeline.Editor
{
    [FilePath("ProjectSettings/AfauxzhubAnimationPipelineSettings.asset", FilePathAttribute.Location.ProjectFolder)]
    internal sealed class AnimationPipelineSettings : ScriptableSingleton<AnimationPipelineSettings>
    {
        [SerializeField] private string sourceRoot = "Assets/Art/Animations";
        [SerializeField] private string outputRoot = "Assets/Generated/AnimationClips";
        [SerializeField] private bool autoExportOnImport;
        [SerializeField] private bool groupByFirstTwoNameSegments = true;
        [SerializeField] private bool optimizeCurves = true;
        [SerializeField] private string rootNode = string.Empty;
        [SerializeField] private string motionNodeName = "root";
        [SerializeField] private bool importBlendShapeDeformPercent;
        [SerializeField] private bool resampleCurves;

        internal string SourceRoot => NormalizeAssetPath(sourceRoot);
        internal string OutputRoot => NormalizeAssetPath(outputRoot);
        internal bool AutoExportOnImport => autoExportOnImport;
        internal bool GroupByFirstTwoNameSegments => groupByFirstTwoNameSegments;
        internal bool OptimizeCurves => optimizeCurves;
        internal string RootNode => rootNode ?? string.Empty;
        internal string MotionNodeName => motionNodeName ?? string.Empty;
        internal bool ImportBlendShapeDeformPercent => importBlendShapeDeformPercent;
        internal bool ResampleCurves => resampleCurves;

        internal bool IsSourceFbx(string assetPath)
        {
            string normalized = NormalizeAssetPath(assetPath);
            string root = SourceRoot.TrimEnd('/');
            return normalized.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase)
                   && (string.Equals(normalized, root, StringComparison.OrdinalIgnoreCase)
                       || normalized.StartsWith(root + "/", StringComparison.OrdinalIgnoreCase));
        }

        internal void SaveSettings()
        {
            Save(true);
        }

        private static string NormalizeAssetPath(string path)
        {
            return string.IsNullOrWhiteSpace(path)
                ? string.Empty
                : path.Trim().Replace('\\', '/').TrimEnd('/');
        }
    }

    internal sealed class AnimationPipelineSettingsProvider : SettingsProvider
    {
        private SerializedObject serializedSettings;

        private AnimationPipelineSettingsProvider()
            : base("Project/Afauxzhub Animation Pipeline", SettingsScope.Project)
        {
            keywords = new[] { "animation", "fbx", "clip", "max", "root motion" };
        }

        [SettingsProvider]
        public static SettingsProvider CreateProvider()
        {
            return new AnimationPipelineSettingsProvider();
        }

        [MenuItem("Tools/Animation Pipeline/Settings")]
        private static void OpenSettings()
        {
            SettingsService.OpenProjectSettings("Project/Afauxzhub Animation Pipeline");
        }

        public override void OnActivate(string searchContext, UnityEngine.UIElements.VisualElement rootElement)
        {
            serializedSettings = new SerializedObject(AnimationPipelineSettings.instance);
        }

        public override void OnGUI(string searchContext)
        {
            if (serializedSettings == null)
                serializedSettings = new SerializedObject(AnimationPipelineSettings.instance);

            serializedSettings.Update();
            EditorGUILayout.HelpBox(
                "自动导出默认关闭。确认来源目录和输出目录后再开启，避免意外生成资源。",
                MessageType.Info);

            Draw("sourceRoot", "FBX 来源目录");
            Draw("outputRoot", ".anim 输出目录");
            Draw("autoExportOnImport", "导入 FBX 时自动导出");
            Draw("groupByFirstTwoNameSegments", "按文件名前两段分组");
            Draw("optimizeCurves", "导出后优化曲线");
            Draw("rootNode", "Root 节点");
            Draw("motionNodeName", "Motion 节点");
            Draw("importBlendShapeDeformPercent", "导入 BlendShape Deform Percent");
            Draw("resampleCurves", "Resample Curves");

            if (serializedSettings.ApplyModifiedProperties())
                AnimationPipelineSettings.instance.SaveSettings();
        }

        private void Draw(string propertyName, string label)
        {
            SerializedProperty property = serializedSettings.FindProperty(propertyName);
            EditorGUILayout.PropertyField(property, new GUIContent(label));
        }
    }
}
