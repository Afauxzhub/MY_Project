using System;
using UnityEngine;

namespace Afauxzhub.TimelineAbilities
{
    public enum AbilityInstructionKind
    {
        Event,
        Window,
        Animation,
    }

    public enum AbilityWindowKind
    {
        Attack,
        Counter,
        CancelToEvade,
        CancelToGuard,
        CancelToSkill,
        Movement,
        Invulnerability,
        Custom,
    }

    [Serializable]
    public sealed class AbilityInstruction
    {
        [Min(0f)] public float startTime;
        [Min(0f)] public float endTime;
        public AbilityInstructionKind kind;
        public AbilityWindowKind windowKind;
        public string key;
        [TextArea] public string payload;
        public AnimationClip animationClip;
        public float speed = 1f;
        [Min(0f)] public float fadeDuration;

        public bool IsInstant => endTime <= startTime;
    }
}
