using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    /// <summary>Attach to the Animator object. Only forwards deltas; never moves the actor.</summary>
    [RequireComponent(typeof(Animator))]
    public sealed class AnimatorMotionRelay : MonoBehaviour
    {
        public AnimatedCharacterDriver driver;
        private Animator animator;
        private void Awake() => animator = GetComponent<Animator>();
        private void OnAnimatorMove()
        {
            if (animator == null) animator = GetComponent<Animator>();
            if (driver != null) driver.ReceiveRootMotion(animator.deltaPosition, animator.deltaRotation);
        }
    }
}
