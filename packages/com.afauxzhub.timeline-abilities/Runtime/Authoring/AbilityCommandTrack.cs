using UnityEngine.Timeline;

namespace Afauxzhub.TimelineAbilities.Authoring
{
    [TrackColor(0.25f, 0.65f, 0.95f)]
    [TrackClipType(typeof(AbilityEventClip))]
    [TrackClipType(typeof(AbilityWindowClip))]
    [TrackClipType(typeof(AbilityAnimationClip))]
    public sealed class AbilityCommandTrack : TrackAsset
    {
    }
}
