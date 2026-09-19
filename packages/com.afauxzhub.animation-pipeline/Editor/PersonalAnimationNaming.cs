using System;
using System.IO;
using System.Text.RegularExpressions;

namespace Afauxzhub.AnimationPipeline.Editor
{
    /// <summary>Character_[Set_]Action. Folder purpose is independent of animation state.</summary>
    public static class PersonalAnimationNaming
    {
        private static readonly Regex NamePattern = new Regex(
            @"\A[A-Z][A-Za-z0-9]*_[A-Z][A-Za-z0-9]*(?:_[A-Z][A-Za-z0-9]*)?\z",
            RegexOptions.CultureInvariant);
        private static readonly string[] ReservedPrefixes =
        {
            "Role", "Monster", "Elite", "Boss", "Npc", "Scene",
            "UL", "EN", "RE", "GA", "DE", "ER", "CS", "QTE", "DI"
        };

        public static bool TryParse(string name, out string character, out string actionSet, out string action)
        {
            character = actionSet = action = string.Empty;
            if (string.IsNullOrEmpty(name) || !NamePattern.IsMatch(name)) return false;
            string[] parts = name.Split('_');
            if (Array.IndexOf(ReservedPrefixes, parts[0]) >= 0) return false;
            character = parts[0];
            actionSet = parts.Length == 3 ? parts[1] : string.Empty;
            action = parts[parts.Length - 1];
            return true;
        }

        public static string GetOutputPath(string sourceRoot, string outputRoot, string fbxPath)
        {
            string source = sourceRoot.Replace('\\', '/').TrimEnd('/') + "/";
            string path = fbxPath.Replace('\\', '/');
            if (!path.StartsWith(source, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Animation FBX is outside the configured source root.");
            string relative = path.Substring(source.Length);
            foreach (string segment in relative.Split('/'))
                if (segment == ".." || segment == "." || segment.Length == 0)
                    throw new ArgumentException("Animation FBX path must be normalized.");
            if (!string.Equals(Path.GetExtension(relative), ".fbx", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Expected an FBX path.");
            return outputRoot.Replace('\\', '/').TrimEnd('/') + "/" + Path.ChangeExtension(relative, ".anim");
        }
    }
}
