using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    [DefaultExecutionOrder(150)]
    public sealed class AnimationLabCamera : MonoBehaviour
    {
        public Transform target;
        public ActionPresentation presentation;
        public float distance = 5, yaw, pitch = 20, sensitivity = 3;
        [System.NonSerialized] public bool externalLook;
        private float impulse;
        private void OnEnable() { if (presentation != null) presentation.CameraImpulse += Shake; }
        private void OnDisable() { if (presentation != null) presentation.CameraImpulse -= Shake; }
        private void Shake(float strength) => impulse = Mathf.Max(impulse, strength);
        private void LateUpdate()
        {
            if (target == null) return;
            if (!externalLook) ApplyLook(Input.GetMouseButton(1) ? new Vector2(Input.GetAxisRaw("Mouse X"), Input.GetAxisRaw("Mouse Y")) : Vector2.zero, Input.mouseScrollDelta.y);
            var rotation = Quaternion.Euler(pitch, yaw, 0);
            transform.SetPositionAndRotation(target.position + Vector3.up * 1.1f - rotation * Vector3.forward * distance + Random.insideUnitSphere * impulse * 0.05f, rotation);
            impulse = Mathf.MoveTowards(impulse, 0, Time.deltaTime * 3);
        }
        public void ApplyLook(Vector2 delta, float scroll)
        {
            yaw = Mathf.Repeat(yaw + delta.x * sensitivity + 180, 360) - 180;
            pitch = Mathf.Clamp(pitch - delta.y * sensitivity, -10, 70);
            distance = Mathf.Clamp(distance - scroll * 0.3f, 2, 10);
        }
    }
}
