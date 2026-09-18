using System.Collections.Generic;
using Afauxzhub.TimelineAbilities.Authoring;
using UnityEditor;
using UnityEngine;
using UnityEngine.Timeline;

namespace Afauxzhub.TimelineAbilities.Editor
{
    public static class AbilityPlanCompiler
    {
        [MenuItem("Assets/Afauxzhub/Compile Timeline Ability", true)]
        private static bool CanCompileSelected()
        {
            return Selection.activeObject is AbilityAsset;
        }

        [MenuItem("Assets/Afauxzhub/Compile Timeline Ability")]
        private static void CompileSelected()
        {
            Compile((AbilityAsset)Selection.activeObject);
        }

        public static AbilityRuntimePlan Compile(AbilityAsset ability)
        {
            if (ability == null)
            {
                throw new System.ArgumentNullException(nameof(ability));
            }

            if (ability.AuthoringTimeline == null)
            {
                throw new System.InvalidOperationException($"Ability '{ability.name}' has no authoring Timeline.");
            }

            string abilityPath = AssetDatabase.GetAssetPath(ability);
            if (string.IsNullOrEmpty(abilityPath))
            {
                throw new System.InvalidOperationException("Save the AbilityAsset before compiling it.");
            }

            AbilityRuntimePlan plan = ability.CompiledPlan;
            if (plan == null)
            {
                plan = ScriptableObject.CreateInstance<AbilityRuntimePlan>();
                plan.name = ability.name + "_RuntimePlan";
                AssetDatabase.AddObjectToAsset(plan, ability);
                ability.SetCompiledPlan(plan);
            }

            List<AbilityInstruction> instructions = new List<AbilityInstruction>();
            foreach (TrackAsset rootTrack in ability.AuthoringTimeline.GetRootTracks())
            {
                CollectTrack(rootTrack, instructions);
            }

            instructions.Sort((a, b) =>
            {
                int timeComparison = a.startTime.CompareTo(b.startTime);
                return timeComparison != 0 ? timeComparison : a.endTime.CompareTo(b.endTime);
            });

            float duration = 0f;
            for (int i = 0; i < instructions.Count; i++)
            {
                duration = Mathf.Max(duration, instructions[i].endTime);
            }

            plan.ReplaceCompiledData(duration, instructions);
            EditorUtility.SetDirty(plan);
            EditorUtility.SetDirty(ability);
            AssetDatabase.SaveAssets();
            Debug.Log($"Compiled ability '{ability.name}' with {instructions.Count} instructions.", ability);
            return plan;
        }

        private static void CollectTrack(TrackAsset track, List<AbilityInstruction> instructions)
        {
            if (track == null || track.muted)
            {
                return;
            }

            if (track is GroupTrack)
            {
                foreach (TrackAsset child in track.GetChildTracks())
                {
                    CollectTrack(child, instructions);
                }
                return;
            }

            if (!(track is AbilityCommandTrack))
            {
                return;
            }

            foreach (TimelineClip timelineClip in track.GetClips())
            {
                AbilityInstruction instruction = ConvertClip(timelineClip);
                if (instruction != null)
                {
                    instructions.Add(instruction);
                }
            }
        }

        private static AbilityInstruction ConvertClip(TimelineClip timelineClip)
        {
            float start = Mathf.Max(0f, (float)timelineClip.start);
            float end = Mathf.Max(start, (float)timelineClip.end);
            switch (timelineClip.asset)
            {
                case AbilityEventClip eventClip:
                    RequireKey(eventClip.eventId, timelineClip);
                    return new AbilityInstruction
                    {
                        startTime = start,
                        endTime = start,
                        kind = AbilityInstructionKind.Event,
                        key = eventClip.eventId,
                        payload = eventClip.payload,
                    };

                case AbilityWindowClip windowClip:
                    RequireKey(windowClip.windowId, timelineClip);
                    return new AbilityInstruction
                    {
                        startTime = start,
                        endTime = end,
                        kind = AbilityInstructionKind.Window,
                        windowKind = windowClip.windowKind,
                        key = windowClip.windowId,
                        payload = windowClip.payload,
                    };

                case AbilityAnimationClip animationClip:
                    if (animationClip.animationClip == null)
                    {
                        throw new System.InvalidOperationException(
                            $"Animation clip '{timelineClip.displayName}' has no AnimationClip assigned.");
                    }
                    return new AbilityInstruction
                    {
                        startTime = start,
                        endTime = end,
                        kind = AbilityInstructionKind.Animation,
                        key = animationClip.animationClip.name,
                        animationClip = animationClip.animationClip,
                        speed = Mathf.Max(0.01f, animationClip.speed),
                        fadeDuration = Mathf.Max(0f, animationClip.fadeDuration),
                    };
            }

            return null;
        }

        private static void RequireKey(string key, TimelineClip timelineClip)
        {
            if (string.IsNullOrWhiteSpace(key))
            {
                throw new System.InvalidOperationException(
                    $"Timeline clip '{timelineClip.displayName}' requires a stable id.");
            }
        }
    }
}
