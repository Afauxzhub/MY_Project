using System;
using System.Collections.Generic;
using UnityEngine;

namespace Afauxzhub.Project.Editor.Animation
{
    [Serializable]
    public sealed class ClipPathMapping
    {
        public string sourcePath;
        public string targetPath;
        public bool omitFromCopy;
        public bool approved;
    }
    /// <summary>Editor-only review record. Never performs a mathematical retarget or edits source curves.</summary>
    public sealed class ClipBindingMap : ScriptableObject
    {
        public GameObject targetModel;
        public AnimationClip exampleClip;
        public List<ClipPathMapping> paths = new List<ClipPathMapping>();
    }
}
