using System.Collections.Generic;
using UnityEngine;

namespace Afauxzhub.TimelineAbilities
{
    public sealed class AbilityRuntimePlan : ScriptableObject
    {
        [SerializeField, Min(0f)] private float duration;
        [SerializeField] private List<AbilityInstruction> instructions = new List<AbilityInstruction>();

        public float Duration => duration;
        public IReadOnlyList<AbilityInstruction> Instructions => instructions;

        public void ReplaceCompiledData(float newDuration, List<AbilityInstruction> newInstructions)
        {
            duration = Mathf.Max(0f, newDuration);
            instructions = newInstructions ?? new List<AbilityInstruction>();
        }
    }
}
