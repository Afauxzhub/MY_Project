using System;
using System.Collections.Generic;
using Afauxzhub.CharacterLocomotion;
using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    public enum MotionSlot
    {
        Idle, IdleVariation, Walk, Run, Sprint, Start, StopLeft, StopRight,
        Accelerate, Decelerate, ArcLeft, ArcRight, ArcSharpLeft, ArcSharpRight,
        SprintLeft, SprintRight, PivotLeft, PivotRight, Turn90Left, Turn90Right,
        StrafeForward, StrafeBack, StrafeLeft, StrafeRight,
        StrafeForwardLeft, StrafeForwardRight, StrafeBackLeft, StrafeBackRight,
        Fall, Land,
        JumpTakeoff, JumpRise, JumpApex,
        TurnInPlaceLeft, TurnInPlaceRight, PivotInPlaceLeft, PivotInPlaceRight
    }

    [Serializable]
    public sealed class MotionBinding
    {
        public MotionSlot slot;
        public AnimationClip clip;
        [Min(0.01f)] public float playbackSpeed = 1;
        public AnimationCurve leftContact = AnimationCurve.Constant(0, 1, 0);
        public AnimationCurve rightContact = AnimationCurve.Constant(0, 1, 0);
        [TextArea] public string note;
    }

    [Serializable]
    public sealed class StanceAnimationSet
    {
        public LocomotionProfile movement;
        public List<MotionBinding> motions = new List<MotionBinding>();
        public MotionBinding Find(MotionSlot slot) => motions.Find(m => m != null && m.slot == slot);
        public void EnsureSlots()
        {
            foreach (MotionSlot slot in Enum.GetValues(typeof(MotionSlot)))
                if (Find(slot) == null) motions.Add(new MotionBinding { slot = slot });
        }
    }

    [Serializable]
    public sealed class FootRigPaths
    {
        public string thigh, calf, foot;
        public Vector3 kneeDirection = Vector3.forward;
        public Vector3 soleUp = Vector3.up;
    }

    [CreateAssetMenu(menuName = "MY Project/Animation/Character Profile")]
    public sealed class CharacterAnimationProfile : ScriptableObject
    {
        public GameObject previewModel;
        public RuntimeAnimatorController controller;
        public StanceAnimationSet sheathed = new StanceAnimationSet();
        public StanceAnimationSet drawn = new StanceAnimationSet();
        public List<ActionDefinition> actions = new List<ActionDefinition>();
        public FootRigPaths leftFoot = new FootRigPaths();
        public FootRigPaths rightFoot = new FootRigPaths();
        [Min(0)] public float motionBlend = 0.15f;
        [Min(0)] public float stanceBlend = 0.2f;
        [Min(0)] public float parameterDamping = 0.12f;
        [Min(0)] public float inputBufferSeconds = 0.15f;
        public bool locomotionRootMotion;
        [Range(0, 1)] public float footIKWeight = 1;
        [Min(0)] public float footRayHeight = 0.45f;
        [Min(0)] public float footRayDepth = 0.55f;
        [Tooltip("Ground-to-ankle pivot height in metres, not shoe sole thickness. Calibrate on the actual rig; a target below the reachable leg length will not be reached by two-bone IK.")]
        [Min(0)] public float soleOffset = 0.025f;
        [Min(0)] public float maxFootCorrection = 0.3f;
        [Min(0)] public float maxPlantDistance = 0.35f;
        [Tooltip("Optional model-relative common parent of both legs. Empty disables pelvis correction; never moves the collision motor.")]
        public string pelvisPath;
        [Min(0)] public float maxPelvisDrop = 0.2f;
        [Min(0)] public float pelvisResponse = 12;
        public LayerMask groundMask = 1;
        public StanceAnimationSet Set(WeaponStance stance) => stance == WeaponStance.Sheathed ? sheathed : drawn;
        public ActionDefinition Find(ActionKind kind) => actions.Find(a => a != null && a.kind == kind);
        public void EnsureSlots() { sheathed.EnsureSlots(); drawn.EnsureSlots(); }
    }
}
