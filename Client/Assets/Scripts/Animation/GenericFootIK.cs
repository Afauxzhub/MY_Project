using System;
using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    /// <summary>Generic-compatible two-bone terrain IK, applied after Animator and Motor.</summary>
    [DefaultExecutionOrder(100)]
    public sealed class GenericFootIK : MonoBehaviour
    {
        [Serializable]
        public sealed class Leg
        {
            public Transform thigh, calf, foot;
            public Vector3 kneeDirection = Vector3.forward;
            public Vector3 soleUp = Vector3.up;
            [NonSerialized] public bool planted;
            [NonSerialized] public Vector3 plant;
            [NonSerialized] public Transform surface;
            [NonSerialized] public Vector3 surfacePoint;
            [NonSerialized] public Vector3 target, normal;
            [NonSerialized] public float weight;
            public bool Valid => thigh != null && calf != null && foot != null && calf.IsChildOf(thigh) && foot.IsChildOf(calf);
        }
        public AnimatedCharacterDriver driver;
        public Transform skeletonRoot;
        public Leg left = new Leg();
        public Leg right = new Leg();
        public bool drawGizmos = true;
        private int lastSequence = -1;
        private Vector3 lastPosition;
        private Transform pelvis;
        private Vector3 pelvisBaseLocal;
        private bool pelvisAdjusted;
        public float PelvisOffset { get; private set; }
        private void OnEnable()
        {
            if (driver != null && driver.profile != null) pelvis = Find(driver.profile.pelvisPath);
        }
        public void Bind(CharacterAnimationProfile p, Transform root)
        {
            skeletonRoot = root;
            BindLeg(left, p.leftFoot); BindLeg(right, p.rightFoot);
            pelvis = Find(p.pelvisPath);
        }
        // Remove only our previous-frame correction before Animator evaluates the authored pose.
        private void Update()
        {
            if (driver != null && driver.combat != null && driver.combat.suspended) return;
            RestorePelvis();
        }
        private void RestorePelvis()
        {
            if (pelvisAdjusted && pelvis != null) pelvis.localPosition = pelvisBaseLocal;
            pelvisAdjusted = false;
        }
        private void OnDisable() { RestorePelvis(); PelvisOffset = 0; }
        private void BindLeg(Leg leg, FootRigPaths paths)
        {
            leg.thigh = Find(paths.thigh); leg.calf = Find(paths.calf); leg.foot = Find(paths.foot);
            leg.kneeDirection = paths.kneeDirection; leg.soleUp = paths.soleUp;
        }
        private Transform Find(string path) => skeletonRoot != null && !string.IsNullOrEmpty(path) ? skeletonRoot.Find(path) : null;
        private void LateUpdate()
        {
            if (driver == null || driver.profile == null || driver.animator == null) return;
            var p = driver.profile;
            var action = driver.combat != null ? driver.combat.Current : null;
            int sequence = driver.combat != null ? driver.combat.Sequence : 0;
            if ((transform.position - lastPosition).sqrMagnitude > 1 || sequence != lastSequence) { left.planted = right.planted = false; PelvisOffset = 0; }
            lastPosition = transform.position; lastSequence = sequence;
            bool grounded = driver.motor != null && driver.motor.IsGrounded;
            float weight = grounded ? p.footIKWeight : 0;
            if (action != null) weight *= Mathf.Clamp01(action.footIK.Evaluate(driver.combat.TimeInAction / Mathf.Max(0.01f, action.duration)));
            if (action != null && action.windows.Exists(w => w != null && w.kind == WindowKind.FootIK) && !driver.combat.IsOpen(WindowKind.FootIK)) weight = 0;
            if (driver.combat != null && driver.combat.suspended) return;
            float lc = Contact(true), rc = Contact(false);
            bool fullAlignment = action != null || driver.Phase == Afauxzhub.CharacterLocomotion.LocomotionPhase.Idle;
            // Swing feet must keep their authored clearance. Only planted portions receive terrain correction.
            PrepareLeg(left, weight * (fullAlignment ? 1 : lc), lc, p);
            PrepareLeg(right, weight * (fullAlignment ? 1 : rc), rc, p);
            ApplyPelvis(p);
            SolveLeg(left); SolveLeg(right);
        }
        private void ApplyPelvis(CharacterAnimationProfile p)
        {
            if (pelvis == null || !left.Valid || !right.Valid || !left.thigh.IsChildOf(pelvis) || !right.thigh.IsChildOf(pelvis))
            { PelvisOffset = 0; return; }
            float drop = RequiredPelvisDrop(left.target.y - left.foot.position.y, left.weight,
                right.target.y - right.foot.position.y, right.weight, p.maxPelvisDrop);
            PelvisOffset = Mathf.Lerp(PelvisOffset, drop, 1 - Mathf.Exp(-p.pelvisResponse * Time.deltaTime));
            pelvisBaseLocal = pelvis.localPosition;
            pelvis.position += Vector3.up * PelvisOffset;
            pelvisAdjusted = true;
        }
        public static float RequiredPelvisDrop(float leftDelta, float leftWeight, float rightDelta, float rightWeight, float limit)
        {
            float drop = Mathf.Min(0, Mathf.Min(leftDelta * Mathf.Clamp01(leftWeight), rightDelta * Mathf.Clamp01(rightWeight)));
            return Mathf.Clamp(drop, -Mathf.Max(0, limit), 0);
        }
        private float Contact(bool leftSide)
        {
            // Dynamic Playables contacts intentionally deferred to MOVE-010; no fake Animator clip queries.
            if (driver.UsesMotionLibrary) return 0;
            var animator = driver.animator;
            if (driver.combat != null && driver.combat.Current != null) return 0;
            var clips = animator.GetCurrentAnimatorClipInfo(0);
            float time = Mathf.Repeat(animator.GetCurrentAnimatorStateInfo(0).normalizedTime, 1);
            float contact = 0;
            foreach (var c in clips)
                foreach (var m in driver.profile.Set(driver.stance).motions)
                    if (m != null && m.clip == c.clip)
                    { contact += Mathf.Clamp01((leftSide ? m.leftContact : m.rightContact).Evaluate(time)) * c.weight; break; }
            if (animator.IsInTransition(0)) contact *= 1 - animator.GetAnimatorTransitionInfo(0).normalizedTime;
            return contact;
        }
        private void PrepareLeg(Leg leg, float requestedWeight, float contact, CharacterAnimationProfile p)
        {
            if (!leg.Valid) { leg.weight = 0; leg.planted = false; return; }
            Vector3 ankle = leg.foot.position;
            bool found = Physics.Raycast(ankle + Vector3.up * p.footRayHeight, Vector3.down, out var hit,
                p.footRayHeight + p.footRayDepth, p.groundMask, QueryTriggerInteraction.Ignore);
            // Exclude the owning character even if the user included its layer in the ground mask.
            found &= hit.collider == null || !hit.collider.transform.IsChildOf(driver.transform);
            if (!found || requestedWeight <= 0 || Mathf.Abs(hit.point.y + p.soleOffset - ankle.y) > p.maxFootCorrection)
            { leg.weight = 0; leg.planted = false; return; }
            leg.weight = Mathf.MoveTowards(leg.weight, requestedWeight, Time.deltaTime * 12);
            Vector3 target = hit.point + Vector3.up * p.soleOffset;
            if (contact >= 0.8f && !leg.planted)
            { leg.planted = true; leg.plant = target; leg.surface = hit.transform; leg.surfacePoint = hit.transform.InverseTransformPoint(target); }
            if (contact < 0.4f || (leg.planted && (ankle - leg.plant).magnitude > p.maxPlantDistance)) leg.planted = false;
            if (leg.planted && leg.surface != null)
            { leg.plant = leg.surface.TransformPoint(leg.surfacePoint); target = leg.plant; }
            leg.target = target; leg.normal = hit.normal;
        }
        private void SolveLeg(Leg leg)
        {
            if (!leg.Valid || leg.weight <= 0) return;
            Vector3 ankle = leg.foot.position;
            Quaternion oldFootRotation = leg.foot.rotation;
            SolveTwoBone(leg.thigh, leg.calf, leg.foot, Vector3.Lerp(ankle, leg.target, leg.weight), driver.transform.TransformDirection(leg.kneeDirection));
            leg.foot.rotation = Quaternion.Slerp(oldFootRotation, Quaternion.FromToRotation(oldFootRotation * leg.soleUp.normalized, leg.normal) * oldFootRotation, leg.weight);
        }
        public static void SolveTwoBone(Transform upper, Transform lower, Transform end, Vector3 target, Vector3 hintDirection)
        {
            Vector3 a = upper.position, b = lower.position, c = end.position;
            float ab = Vector3.Distance(a, b), bc = Vector3.Distance(b, c);
            if (ab < 0.0001f || bc < 0.0001f) return;
            Vector3 direction = target - a;
            float length = Mathf.Clamp(direction.magnitude, Mathf.Abs(ab - bc) + 0.0001f, ab + bc - 0.0001f);
            if (direction.sqrMagnitude < 0.00001f) return;
            direction.Normalize();
            Vector3 bend = Vector3.ProjectOnPlane(b - a, direction).normalized;
            if (bend.sqrMagnitude < 0.001f) bend = Vector3.ProjectOnPlane(hintDirection, direction).normalized;
            if (bend.sqrMagnitude < 0.001f) bend = Vector3.Cross(direction, Vector3.right).normalized;
            float x = (ab * ab + length * length - bc * bc) / (2 * length);
            Vector3 knee = a + direction * x + bend * Mathf.Sqrt(Mathf.Max(0, ab * ab - x * x));
            upper.rotation = Quaternion.FromToRotation(b - a, knee - a) * upper.rotation;
            lower.rotation = Quaternion.FromToRotation(end.position - lower.position, target - lower.position) * lower.rotation;
        }
        private void OnDrawGizmosSelected()
        {
            if (!drawGizmos) return;
            foreach (var leg in new[] { left, right })
            {
                if (!leg.Valid) continue;
                Gizmos.color = leg.planted ? Color.green : Color.cyan;
                Gizmos.DrawWireSphere(leg.target, 0.04f); Gizmos.DrawRay(leg.target, leg.normal * 0.2f);
                Gizmos.DrawLine(leg.thigh.position, leg.calf.position); Gizmos.DrawLine(leg.calf.position, leg.foot.position);
            }
        }
    }
}
