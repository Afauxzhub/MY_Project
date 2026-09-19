using System;
using System.Reflection;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.AnimationPipeline.Editor
{
    internal static class FbxAnimationImporter
    {
        internal static bool Configure(ModelImporter importer, AnimationPipelineSettings settings)
        {
            if (importer == null)
                return false;

            bool changed = false;
            changed |= Set(importer.importBlendShapeDeformPercent, settings.ImportBlendShapeDeformPercent, v => importer.importBlendShapeDeformPercent = v);
            changed |= Set(importer.importAnimation, true, v => importer.importAnimation = v);
            changed |= Set(importer.resampleCurves, settings.ResampleCurves, v => importer.resampleCurves = v);

            if (importer.animationType != ModelImporterAnimationType.Generic)
            {
                importer.animationType = ModelImporterAnimationType.Generic;
                changed = true;
            }

            if (importer.avatarSetup != ModelImporterAvatarSetup.CreateFromThisModel)
            {
                importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                changed = true;
            }

            string motionNodeName = settings.MotionNodeName;
            if (!string.Equals(importer.motionNodeName ?? string.Empty, motionNodeName, StringComparison.Ordinal))
            {
                importer.motionNodeName = motionNodeName;
                changed = true;
            }

            changed |= SetRootNode(importer, settings.RootNode);
            changed |= SetAnimatedCustomProperties(importer, true);

            if (importer.animationCompression != settings.AnimationCompression)
            {
                importer.animationCompression = settings.AnimationCompression;
                changed = true;
            }

            return changed;
        }

        internal static bool ConfigureAndReimport(string assetPath)
        {
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null)
                return false;

            bool changed = Configure(importer, AnimationPipelineSettings.instance);
            if (changed)
                importer.SaveAndReimport();
            return true;
        }

        private static bool Set(bool current, bool desired, Action<bool> setter)
        {
            if (current == desired)
                return false;
            setter(desired);
            return true;
        }

        private static bool SetRootNode(ModelImporter importer, string rootNode)
        {
            var serialized = new SerializedObject(importer);
            SerializedProperty property = serialized.FindProperty("m_HumanDescription.m_RootMotionBoneName");
            if (property == null || property.stringValue == rootNode)
                return false;
            property.stringValue = rootNode;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            return true;
        }

        private static bool SetAnimatedCustomProperties(ModelImporter importer, bool desired)
        {
            PropertyInfo property = typeof(ModelImporter).GetProperty("importAnimatedCustomProperties");
            if (property != null && property.CanRead && property.CanWrite && property.PropertyType == typeof(bool))
            {
                bool current = (bool)property.GetValue(importer, null);
                if (current == desired)
                    return false;
                property.SetValue(importer, desired, null);
                return true;
            }

            var serialized = new SerializedObject(importer);
            SerializedProperty serializedProperty = serialized.FindProperty("m_ImportAnimatedCustomProperties");
            if (serializedProperty == null || serializedProperty.boolValue == desired)
                return false;
            serializedProperty.boolValue = desired;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            return true;
        }
    }

    internal sealed class AnimationModelPreprocessor : AssetPostprocessor
    {
        private void OnPreprocessModel()
        {
            AnimationPipelineSettings settings = AnimationPipelineSettings.instance;
            if (!settings.IsSourceFbx(assetPath))
                return;
            FbxAnimationImporter.Configure(assetImporter as ModelImporter, settings);
        }
    }
}
