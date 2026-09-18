using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace Afauxzhub.TimelineAbilities.Authoring
{
    public sealed class AbilityEventClip : PlayableAsset, ITimelineClipAsset
    {
        public string eventId;
        [TextArea] public string payload;

        public ClipCaps clipCaps => ClipCaps.None;

        public override Playable CreatePlayable(PlayableGraph graph, GameObject owner)
        {
            return Playable.Create(graph);
        }
    }
}
