using System;
using System.IO;
using UnityEngine;

namespace Afauxzhub.AnimationPipeline.Editor
{
    [Serializable]
    public sealed class WeaponStateMappingDocument
    {
        public int formatVersion;
        public string sourceMaxFile;
        public string exportMode;
        public string actionRoleName;
        public string characterName;
        public WeaponStateMappingEntry[] entries;
        public WeaponHierarchyNodeRecord[] hierarchyNodes;
    }

    [Serializable]
    public sealed class WeaponStateMappingEntry
    {
        public string boneName;
        public string weaponNode;
        public string attributeBlockName;
        public string curveParameterName;
        public WeaponStateMappingState[] states;
        public WeaponStateMappingSegment[] segments;
    }

    [Serializable]
    public sealed class WeaponStateMappingState
    {
        public int id;
        public string displayName;
        public string constraintNode;
    }

    [Serializable]
    public sealed class WeaponHierarchyNodeRecord
    {
        public string nodeName;
        public string parentName;
    }

    [Serializable]
    public sealed class WeaponStateMappingSegment
    {
        public int start;
        public int end;
        public int stateId;
        public string constraintNode;
    }

    /// <summary>Parser for the optional JSON sidecar emitted by the Max weapon-state exporter.</summary>
    public static class WeaponStateMappingJson
    {
        public static bool TryParseFile(string absoluteOrProjectPath, out WeaponStateMappingDocument document, out string error)
        {
            document = null;
            error = null;
            if (string.IsNullOrWhiteSpace(absoluteOrProjectPath))
            {
                error = "Path is empty.";
                return false;
            }

            string path = absoluteOrProjectPath.Trim().Replace('\\', '/');
            if (!Path.IsPathRooted(path))
                path = Path.GetFullPath(Path.Combine(Application.dataPath, "..", path));
            if (!File.Exists(path))
            {
                error = "File not found: " + path;
                return false;
            }

            try
            {
                return TryParse(File.ReadAllText(path), out document, out error);
            }
            catch (Exception exception)
            {
                error = exception.Message;
                return false;
            }
        }

        public static bool TryParse(string json, out WeaponStateMappingDocument document, out string error)
        {
            document = null;
            error = null;
            if (string.IsNullOrWhiteSpace(json))
            {
                error = "JSON is empty.";
                return false;
            }

            try
            {
                document = JsonUtility.FromJson<WeaponStateMappingDocument>(json);
            }
            catch (Exception exception)
            {
                error = "JSON parse failed: " + exception.Message;
                return false;
            }

            if (document == null)
            {
                error = "JSON result is null.";
                return false;
            }
            return true;
        }

        public static string ResolveWeaponNode(WeaponStateMappingEntry entry)
        {
            if (entry == null) return string.Empty;
            return !string.IsNullOrEmpty(entry.weaponNode) ? entry.weaponNode : entry.boneName ?? string.Empty;
        }
    }
}
