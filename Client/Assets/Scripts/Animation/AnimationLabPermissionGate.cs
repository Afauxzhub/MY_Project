using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    [AddComponentMenu("MY Project/Animation Lab/Explicit Sandbox Permission Gate")]
    public sealed class AnimationLabPermissionGate : MonoBehaviour, ICombatActionGate
    {
        [Tooltip("SANDBOX ONLY. No resources, skill links, cooldowns or balance are validated.")]
        public bool allowUnpaidPreview;
        public bool TryCommit(ActionDefinition action, out string reason)
        {
            reason = allowUnpaidPreview ? "Sandbox permission; no resource simulation" : "Enable lab-only unpaid preview or supply a real combat adapter";
            return allowUnpaidPreview;
        }
    }
}
