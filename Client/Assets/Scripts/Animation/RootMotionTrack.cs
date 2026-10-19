using System;
using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    /// <summary>Read-only, model-specific trajectory sampled by the Editor. Never rewrites a source Clip.</summary>
    [Serializable]
    public sealed class RootMotionTrack
    {
        public AnimationClip clip;
        public GameObject model;
        public string fingerprint;
        public float length;
        public Vector3 modelScale = Vector3.one;
        public Vector3[] positions = Array.Empty<Vector3>();
        public Quaternion[] rotations = Array.Empty<Quaternion>();
        public bool Valid(AnimationClip source) => source != null && source == clip && length > 0
            && Mathf.Abs(length - source.length) < 0.0001f && positions != null && positions.Length >= 2
            && rotations != null && rotations.Length == positions.Length
            && modelScale.x > 0 && modelScale.y > 0 && modelScale.z > 0 && RootMotionSettings.Finite(modelScale.sqrMagnitude);

        public Pose At(float normalized)
        {
            float t = Mathf.Clamp01(normalized) * (positions.Length - 1);
            int a = Mathf.Min(Mathf.FloorToInt(t), positions.Length - 2);
            return new Pose(Vector3.Lerp(positions[a], positions[a + 1], t - a), Quaternion.Slerp(rotations[a], rotations[a + 1], t - a));
        }
        public static Pose Multiply(Pose a, Pose b) => new Pose(a.position + a.rotation * b.position, a.rotation * b.rotation);
        public static Pose Relative(Pose a, Pose b) => new Pose(Quaternion.Inverse(a.rotation) * (b.position - a.position), Quaternion.Inverse(a.rotation) * b.rotation);
        private static Pose Power(Pose value, int count)
        {
            if (count < 0) { value = Relative(value, new Pose(Vector3.zero, Quaternion.identity)); count = -count; }
            var result = new Pose(Vector3.zero, Quaternion.identity);
            while (count > 0) { if ((count & 1) != 0) result = Multiply(result, value); value = Multiply(value, value); count >>= 1; }
            return result;
        }
        // A trimmed loop composes its end transform, not just its translation. Curved cycles stay curved.
        public Pose Unwrapped(double phase, float start, float end, bool loop)
        {
            var origin = At(start);
            if (!loop) return Relative(origin, At(Mathf.Lerp(start, end, Mathf.Clamp01((float)phase))));
            int cycles = (int)Math.Floor(phase);
            var cycle = Relative(origin, At(end));
            var partial = Relative(origin, At(Mathf.Lerp(start, end, (float)(phase - cycles))));
            return Multiply(Power(cycle, cycles), partial);
        }
        public Pose Delta(double from, double to, float start, float end, bool loop)
        {
            if (!loop) return Relative(Unwrapped(from, start, end, false), Unwrapped(to, start, end, false));
            // Only compose cycles crossed THIS sample. Subtracting two huge accumulated positions
            // loses sub-frame precision after a long session even when the clocks are doubles.
            double firstCycle = Math.Floor(from), lastCycle = Math.Floor(to);
            var origin = At(start); var cycle = Relative(origin, At(end));
            var a = Relative(origin, At(Mathf.Lerp(start, end, (float)(from - firstCycle))));
            var b = Relative(origin, At(Mathf.Lerp(start, end, (float)(to - lastCycle))));
            return Relative(a, Multiply(Power(cycle, (int)(lastCycle - firstCycle)), b));
        }
    }

    [Serializable]
    public sealed class RootMotionSettings
    {
        public bool enabled;
        public bool rotation;
        [Tooltip("ActionDefinition only: use authored vertical travel instead of gravity. Locomotion always uses the Motor's ballistic policy.")]
        public bool vertical;
        [Min(0)] public float scale = 1;
        [HideInInspector] public RootMotionTrack track;
        public bool Valid(AnimationClip clip) => !enabled || track != null && track.Valid(clip) && Finite(scale) && scale >= 0;
        public static bool Finite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);
        public static bool Finite(double value) => !double.IsNaN(value) && !double.IsInfinity(value);
    }

    public struct RootMotionFrame
    {
        public Vector3 localDelta;
        public float yaw, positionWeight, rotationWeight, verticalWeight;
        public string problem;
        public void Add(Pose delta, RootMotionSettings settings, float weight)
        {
            if (!RootMotionSettings.Finite(delta.position.sqrMagnitude) || !RootMotionSettings.Finite(delta.rotation.x + delta.rotation.y + delta.rotation.z + delta.rotation.w))
            { problem = "Nonfinite Root Motion sample (movement held)"; delta = new Pose(Vector3.zero, Quaternion.identity); }
            var position = delta.position; if (!settings.vertical) position.y = 0;
            localDelta += position * ((RootMotionSettings.Finite(settings.scale) ? Mathf.Max(0, settings.scale) : 0) * weight);
            positionWeight += weight;
            if (settings.rotation) { rotationWeight += weight; yaw += Mathf.DeltaAngle(0, delta.rotation.eulerAngles.y) * weight; }
            if (settings.vertical) verticalWeight += weight;
        }
    }
}
