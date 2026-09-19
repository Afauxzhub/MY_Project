using UnityEngine;

namespace Afauxzhub.Project.Locomotion
{
    /// <summary>
    /// Minimal fixed-offset observer used by the greybox. It supplies reference
    /// axes and follows the player, but does not own player movement or rotation.
    /// </summary>
    public sealed class FixedFollowCameraReference : MonoBehaviour
    {
        [SerializeField] private Transform target;
        [SerializeField] private Vector3 offset = new Vector3(0f, 6f, -8f);
        [SerializeField, Min(0f)] private float lookHeight = 1.25f;

        public Vector3 Forward => transform.forward;
        public Vector3 Right => transform.right;
        public bool IsConfigured => target != null;

        public void Configure(Transform followTarget, Vector3 followOffset, float targetLookHeight)
        {
            target = followTarget;
            offset = followOffset;
            lookHeight = Mathf.Max(0f, targetLookHeight);
            RefreshPose();
        }

        private void LateUpdate()
        {
            RefreshPose();
        }

        private void RefreshPose()
        {
            if (target == null)
            {
                return;
            }

            transform.position = target.position + offset;
            Vector3 focusPoint = target.position + Vector3.up * lookHeight;
            transform.rotation = Quaternion.LookRotation(focusPoint - transform.position, Vector3.up);
        }
    }
}
