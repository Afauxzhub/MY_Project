using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.AnimationPipeline.Editor
{
    internal static class AnimationCurveOptimizer
    {
        private const float PositionTolerance = 0.00001f;
        private const float RotationTolerance = 0.00001f;
        private const float ScaleTolerance = 0.01f;

        internal static void Process(AnimationClip clip)
        {
            foreach (EditorCurveBinding binding in AnimationUtility.GetCurveBindings(clip))
            {
                AnimationCurve curve = AnimationUtility.GetEditorCurve(clip, binding);
                if (curve == null)
                    continue;
                if (Simplify(binding.propertyName, curve, Tolerance(binding.propertyName)))
                    AnimationUtility.SetEditorCurve(clip, binding, curve);
            }
        }

        private static float Tolerance(string propertyName)
        {
            string lower = propertyName.ToLowerInvariant();
            if (lower.Contains("scale")) return ScaleTolerance;
            if (lower.Contains("rotation") || lower.Contains("euler")) return RotationTolerance;
            return PositionTolerance;
        }

        private static bool Simplify(string propertyName, AnimationCurve curve, float tolerance)
        {
            Keyframe[] keys = curve.keys;
            bool changed = false;

            for (int i = 0; i < keys.Length; i++)
            {
                float value = keys[i].value;
                if (Mathf.Abs(value) <= tolerance)
                {
                    keys[i].value = 0f;
                    changed = true;
                }
                else if (Mathf.Abs(value - 1f) <= tolerance)
                {
                    keys[i].value = 1f;
                    changed = true;
                }
            }

            if (propertyName.ToLowerInvariant().Contains("scale"))
            {
                for (int i = 0; i < keys.Length - 1; i++)
                {
                    float timeDiff = Mathf.Abs(keys[i + 1].time - keys[i].time);
                    float valueDiff = Mathf.Abs(keys[i + 1].value - keys[i].value);
                    if (timeDiff <= 0.0333334f && valueDiff > 0.9999f && valueDiff < 1.0001f)
                    {
                        keys[i].outTangent = float.PositiveInfinity;
                        keys[i + 1].inTangent = float.PositiveInfinity;
                        changed = true;
                    }
                }
            }

            Keyframe[] reduced = ReduceByGlobalError(keys, tolerance);
            if (reduced != null)
            {
                curve.keys = reduced;
                return true;
            }

            if (changed)
                curve.keys = keys;
            return changed;
        }

        private static Keyframe[] ReduceByGlobalError(Keyframe[] keys, float tolerance)
        {
            int count = keys.Length;
            if (count <= 2)
                return null;

            var source = new AnimationCurve(keys);
            var keep = new bool[count];
            keep[0] = keep[count - 1] = true;
            var spans = new Stack<int>();
            spans.Push(0);
            spans.Push(count - 1);

            while (spans.Count > 0)
            {
                int right = spans.Pop();
                int left = spans.Pop();
                if (right - left <= 1)
                    continue;

                int maxIndex = -1;
                float maxError = 0f;
                var approximation = new AnimationCurve(keys[left], keys[right]);
                for (int i = left + 1; i < right; i++)
                {
                    float error = Mathf.Abs(approximation.Evaluate(keys[i].time) - source.Evaluate(keys[i].time));
                    if (error > maxError)
                    {
                        maxError = error;
                        maxIndex = i;
                    }
                }

                if (maxIndex < 0 || maxError < tolerance)
                    continue;
                keep[maxIndex] = true;
                spans.Push(left);
                spans.Push(maxIndex);
                spans.Push(maxIndex);
                spans.Push(right);
            }

            var result = new List<Keyframe>(count);
            for (int i = 0; i < count; i++)
                if (keep[i]) result.Add(keys[i]);
            return result.Count < count ? result.ToArray() : null;
        }
    }
}
