using System;
using UnityEngine;

namespace Afauxzhub.AnimationPipeline.Editor
{
    /// <summary>
    /// Optional extension point for project-specific post-processing.
    /// The package itself deliberately has no dependency on combat or weapon runtime code.
    /// </summary>
    public static class AnimationPipelineHooks
    {
        public static event Action<string, string, AnimationClip> ClipExported;

        internal static void RaiseClipExported(string sourceFbxPath, string exportedClipPath, AnimationClip clip)
        {
            ClipExported?.Invoke(sourceFbxPath, exportedClipPath, clip);
        }
    }
}
