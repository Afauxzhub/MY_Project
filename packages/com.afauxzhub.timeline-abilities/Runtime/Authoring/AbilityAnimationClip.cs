using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace Afauxzhub.TimelineAbilities.Authoring
{
    public sealed class AbilityAnimationClip : PlayableAsset, ITimelineClipAsset
    {
        public AnimationClip animationClip;
        [Min(0.01f)] public float speed = 1f;
        [Min(0f)] public float fadeDuration = 0.08f;

        public ClipCaps clipCaps => ClipCaps.None;

        public override double duration => animationClip != null
            ? animationClip.length / Mathf.Max(0.01f, speed)
            : base.duration;

        public override Playable CreatePlayable(PlayableGraph graph, GameObject owner)
        {
            return Playable.Create(graph);
        }
    }
}
