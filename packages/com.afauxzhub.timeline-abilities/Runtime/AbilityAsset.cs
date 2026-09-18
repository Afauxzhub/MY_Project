using UnityEngine;
using UnityEngine.Timeline;

namespace Afauxzhub.TimelineAbilities
{
    [CreateAssetMenu(fileName = "Ability", menuName = "Afauxzhub/Combat/Timeline Ability")]
    public sealed class AbilityAsset : ScriptableObject
    {
        [SerializeField] private string abilityId = string.Empty;
        [SerializeField] private TimelineAsset authoringTimeline = null;
        [SerializeField, HideInInspector] private AbilityRuntimePlan compiledPlan;

        public string AbilityId => abilityId;
        public TimelineAsset AuthoringTimeline => authoringTimeline;
        public AbilityRuntimePlan CompiledPlan => compiledPlan;

        public void SetCompiledPlan(AbilityRuntimePlan plan)
        {
            compiledPlan = plan;
        }
    }
}
