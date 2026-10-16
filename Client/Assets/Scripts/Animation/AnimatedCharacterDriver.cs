using Afauxzhub.CharacterLocomotion;
using Afauxzhub.Project.Locomotion;
using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    [DefaultExecutionOrder(-40)]
    public sealed class AnimatedCharacterDriver : MonoBehaviour
    {
        public CharacterAnimationProfile profile;
        public Animator animator;
        public CharacterControllerMotor motor;
        public MovementInputSource inputSource;
        public Transform cameraReference;
        public Transform lockTarget;
        public CombatActionController combat;
        public WeaponStance stance;
        public bool sprint;
        public bool walk;
        public Vector2 manualInput;
        public bool useManualInput;
        public MotionLibraryPlayer motionPlayer;
        public bool UsesMotionLibrary => motionPlayer != null && motionPlayer.Ready;
        public LocomotionPhase Phase => UsesMotionLibrary && motionPlayer.WorkingLibrary != null && jumpAge >= 0 && jumpAge < motionPlayer.WorkingLibrary.takeoffSeconds ? LocomotionPhase.JumpTakeoff
            : UsesMotionLibrary && motionPlayer.WorkingLibrary != null && motor != null && !motor.IsGrounded && motor.VerticalSpeed > motionPlayer.WorkingLibrary.apexSpeed ? LocomotionPhase.JumpRise
            : UsesMotionLibrary && motionPlayer.WorkingLibrary != null && motor != null && !motor.IsGrounded && Mathf.Abs(motor.VerticalSpeed) <= motionPlayer.WorkingLibrary.apexSpeed ? LocomotionPhase.JumpApex : dynamics.Phase;
        public float Speed => dynamics.Speed;
        public float TargetSpeed { get; private set; }
        public float HeadingError { get; private set; }
        public float StartAngle { get; private set; }
        public float YawRate { get; private set; }
        public float TurnBlend { get; private set; }
        public Vector2 LocalVelocity { get; private set; }
        public string MotionOwner { get; private set; }
        public bool Targeting => lockTarget != null && lockTarget.gameObject.activeInHierarchy;
        public MotionMode Mode => Targeting ? MotionMode.Targeting : MotionMode.Free;
        public float SelectionSpeed { get; private set; }
        public float SelectionAngle { get; private set; }
        public event System.Action<AnimatedCharacterDriver> FrameCompleted;
        private Vector3 requestedFacing;
        private bool facingRequested, previousTargeting;
        public void RequestFacing(Vector3 worldDirection)
        { worldDirection.y = 0; if (worldDirection.sqrMagnitude > 0.001f) { requestedFacing = worldDirection.normalized; facingRequested = true; } }
        public void ClearFacingRequest() => facingRequested = false;
        public float PhaseNormalized { get; private set; }
        public string LastConfigurationError { get; private set; }
        private readonly LocomotionDynamics dynamics = new LocomotionDynamics();
        private readonly HeadingSolver heading = new HeadingSolver();
        private Quaternion intendedRotation;
        private Vector3 intendedVelocity, rootDelta;
        private Quaternion rootRotation = Quaternion.identity;
        private bool receivedRoot;
        private float turnStartYaw, latchedYaw;
        private WeaponStance previousStance;
        private int lastActionSequence = -1;
        private LocomotionPhase previousPhase;
        private bool wasActing;
        private float phaseSeed;
        private CombatActionController subscribedCombat;
        private float jumpAge = -1;
        private Vector3 airVelocity;
        private Vector3 lastTargetMoveDirection;
        private static readonly int StanceParam = Animator.StringToHash("Stance");
        private static readonly int PhaseParam = Animator.StringToHash("Phase");

        private void OnEnable()
        {
            dynamics.Reset();
            heading.Reset(transform.forward);
            intendedRotation = transform.rotation;
            intendedVelocity = airVelocity = Vector3.zero;
            jumpAge = -1;
            previousStance = stance;
            Subscribe();
        }
        private void Subscribe()
        {
            if (subscribedCombat == combat) return;
            if (subscribedCombat != null) subscribedCombat.Ended -= OnActionEnded;
            subscribedCombat = combat;
            if (subscribedCombat != null) subscribedCombat.Ended += OnActionEnded;
        }
        private void OnDisable() { if (subscribedCombat != null) subscribedCombat.Ended -= OnActionEnded; subscribedCombat = null; if (combat != null) combat.LocomotionInputBlocked = false; }
        public bool RequestJump()
        {
            if (!UsesMotionLibrary || motor == null || combat != null && (combat.suspended || combat.Current != null)) return false;
            motionPlayer.Ensure();
            if (!motor.TryJump(motionPlayer.WorkingLibrary.jumpHeight)) return false;
            jumpAge = 0; airVelocity = intendedVelocity;
            if (combat != null) combat.LocomotionInputBlocked = true;
            return true;
        }
        private void OnActionEnded(ActionDefinition action, bool interrupted)
        {
            if (interrupted) return;
            if (action.kind == ActionKind.DrawWeapon) stance = WeaponStance.Drawn;
            if (action.kind == ActionKind.SheatheWeapon) stance = WeaponStance.Sheathed;
        }
        public bool RequestStance(WeaponStance next)
        {
            if (next == stance) return true;
            var action = profile != null ? profile.Find(next == WeaponStance.Drawn ? ActionKind.DrawWeapon : ActionKind.SheatheWeapon) : null;
            // Missing draw/sheathe clips stay visible as missing slots. Lab may switch sets directly.
            return combat != null && combat.Request(action, false);
        }
        public void ReceiveRootMotion(Vector3 displacement, Quaternion rotation)
        { rootDelta += displacement; rootRotation *= rotation; receivedRoot = true; }

        private void Update()
        {
            Subscribe();
            if (UsesMotionLibrary) motionPlayer.Ensure();
            if (profile == null || motor == null || animator == null || profile.Set(stance).movement == null)
            { LastConfigurationError = "Assign profile, Animator, motor and both movement profiles."; return; }
            var oldBrain = GetComponent<ThirdPersonLocomotionBrain>();
            if (oldBrain != null && oldBrain.enabled)
            { LastConfigurationError = "Disable ThirdPersonLocomotionBrain: only one driver may command this Motor."; return; }
            LastConfigurationError = null;
            var p = UsesMotionLibrary ? motionPlayer.WorkingLibrary.Movement(stance) : profile.Set(stance).movement;
            if (p == null) { LastConfigurationError = "Missing movement tuning for stance"; return; }
            if (stance != previousStance) { heading.Reset(motor.Facing); previousStance = stance; }
            Vector2 input = Vector2.ClampMagnitude(useManualInput ? manualInput : inputSource != null ? inputSource.ReadMoveInput() : Vector2.zero, 1);
            Vector3 forward = cameraReference != null ? cameraReference.forward : Vector3.forward;
            Vector3 right = cameraReference != null ? cameraReference.right : Vector3.right;
            bool hasInput = CameraRelativeMovement.TryGetWorldDirection(input, forward, right, p.inputDeadZone, out var desired);
            bool frozen = combat != null && combat.suspended;
            var action = combat != null ? combat.Current : null;
            if (frozen)
            {
                intendedVelocity = Vector3.zero; intendedRotation = transform.rotation;
                UpdateAnimator(p, action, true, 0); return;
            }
            bool acting = action != null;
            if (UsesMotionLibrary && (Targeting != previousTargeting || acting)) { dynamics.CancelTurn(); heading.Reset(motor.Facing); }
            previousTargeting = Targeting;
            float movementScale = acting ? (combat.IsOpen(WindowKind.Movement) ? action.inputMovementScale : 0) : 1;
            if (frozen) movementScale = 0;
            if (wasActing && !acting) { dynamics.Reset(); heading.Reset(motor.Facing); }
            wasActing = acting;
            float targetSpeed = !hasInput ? 0 : walk ? p.walkSpeed : sprint ? p.sprintSpeed : p.runSpeed;
            if (hasInput) facingRequested = false;
            Vector3 facingTarget = Targeting ? lockTarget.position - transform.position : hasInput ? desired : facingRequested ? requestedFacing : Vector3.zero;
            facingTarget.y = 0;
            if (Targeting && hasInput)
            {
                float backwards = Vector3.Dot(desired, motor.Facing) < -0.1f ? p.backwardSpeedScale : 1;
                targetSpeed = (UsesMotionLibrary ? targetSpeed : p.strafeSpeed) * backwards;
            }
            targetSpeed *= input.magnitude * movementScale;
            TargetSpeed = targetSpeed;
            HeadingError = facingTarget.sqrMagnitude > 0.0001f ? Vector3.SignedAngle(motor.Facing, facingTarget, Vector3.up) : 0;
            float dt = Time.deltaTime;
            if (UsesMotionLibrary)
            {
                if (jumpAge >= 0) jumpAge += dt;
                if (motor.IsGrounded && motor.VerticalSpeed <= 0) jumpAge = -1;
                if (combat != null) combat.LocomotionInputBlocked = jumpAge >= 0 || !motor.IsGrounded;
            }
            previousPhase = dynamics.Phase;
            // A directional start owns its initial heading; moving 90/180 turns remain separate phases.
            bool directionalStart = UsesMotionLibrary && !Targeting && hasInput && (previousPhase == LocomotionPhase.Idle || previousPhase == LocomotionPhase.Stop || previousPhase == LocomotionPhase.Start);
            if (UsesMotionLibrary && hasInput && (previousPhase == LocomotionPhase.Idle || previousPhase == LocomotionPhase.Stop)) StartAngle = Vector3.SignedAngle(motor.Facing, desired, Vector3.up);
            float speed01 = Mathf.Clamp01(Speed / Mathf.Max(0.01f, p.sprintSpeed));
            float previousTime = dynamics.PhaseTime, speedBefore = Speed;
            var gait = walk ? MotionGait.Walk : sprint ? MotionGait.Sprint : MotionGait.Run;
            var lib = UsesMotionLibrary ? motionPlayer.WorkingLibrary : null;
            float Length(LocomotionPhase phase, float fallback)
            {
                var dir = phase == LocomotionPhase.Start ? MotionLibraryPlayer.Direction(StartAngle) : MotionDirection.Any;
                bool current = phase == dynamics.Phase;
                return lib == null ? fallback : lib.PhaseDuration(phase, stance, gait, Mode, dir,
                    current ? motionPlayer.StopChoice : motionPlayer.Support.StopSlot(motionPlayer.Cycle),
                    current ? SelectionSpeed : phase == LocomotionPhase.Stop ? speedBefore : targetSpeed,
                    current ? SelectionAngle : Mathf.Abs(HeadingError), fallback);
            }
            float startLength = Length(LocomotionPhase.Start, p.startDuration), stopLength = Length(LocomotionPhase.Stop, p.stopDuration);
            float turnLength = Length(HeadingError < 0 ? LocomotionPhase.Turn90Left : LocomotionPhase.Turn90Right, p.turn90Duration);
            float pivotLength = Length(HeadingError < 0 ? LocomotionPhase.PivotLeft : LocomotionPhase.PivotRight, p.pivotDuration);
            float idleLength = Length(HeadingError < 0 ? LocomotionPhase.TurnInPlaceLeft : LocomotionPhase.TurnInPlaceRight, p.idleTurnDuration);
            float idlePivotLength = Length(HeadingError < 0 ? LocomotionPhase.PivotInPlaceLeft : LocomotionPhase.PivotInPlaceRight, p.idlePivotDuration);
            if (dynamics.Turning || dynamics.TurningInPlace)
            {
                float lockedLength = Length(dynamics.Phase, dynamics.TurningInPlace ? Mathf.Abs(dynamics.LatchedTurnAngle) >= p.pivotAngle ? p.idlePivotDuration : p.idleTurnDuration : Mathf.Abs(dynamics.LatchedTurnAngle) >= p.pivotAngle ? p.pivotDuration : p.turn90Duration);
                if (dynamics.TurningInPlace) idleLength = idlePivotLength = lockedLength; else turnLength = pivotLength = lockedLength;
            }
            bool idleFacing = UsesMotionLibrary && p.enableTurnInPlace && !acting && (Targeting || facingRequested || dynamics.TurningInPlace);
            dynamics.Step(targetSpeed, !directionalStart && (hasInput || idleFacing) ? HeadingError : 0, Targeting, motor.IsGrounded, dt,
                p.acceleration * Mathf.Max(0.05f, p.accelerationBySpeed.Evaluate(speed01)),
                p.deceleration * Mathf.Max(0.05f, p.decelerationBySpeed.Evaluate(speed01)),
                startLength, stopLength, pivotLength, turnLength,
                p.pivotAngle, p.turn90Angle, p.turnMinimumSpeed, p.releaseDelay, Length(LocomotionPhase.Land, p.landDuration), UsesMotionLibrary,
                idleFacing, p.idleTurnAngle, idleLength, idlePivotLength, p.turnInterrupt);
            if (previousPhase != dynamics.Phase)
            { SelectionSpeed = dynamics.Phase == LocomotionPhase.Stop ? speedBefore : targetSpeed; SelectionAngle = Mathf.Abs(HeadingError); }
            if ((dynamics.Turning || dynamics.TurningInPlace) && previousPhase != dynamics.Phase)
            { turnStartYaw = transform.eulerAngles.y; latchedYaw = turnStartYaw + dynamics.LatchedTurnAngle; }
            float phaseLength = Phase == LocomotionPhase.Start ? startLength : Phase == LocomotionPhase.Stop ? stopLength
                : Phase == LocomotionPhase.Land ? p.landDuration : Phase == LocomotionPhase.Turn90Left || Phase == LocomotionPhase.Turn90Right ? p.turn90Duration : p.pivotDuration;
            phaseLength = Length(Phase, phaseLength);
            PhaseNormalized = Mathf.Clamp01(dynamics.PhaseTime / Mathf.Max(0.01f, phaseLength));
            if (UsesMotionLibrary && Phase == LocomotionPhase.JumpTakeoff) PhaseNormalized = Mathf.Clamp01(jumpAge / Mathf.Max(0.01f, motionPlayer.WorkingLibrary.takeoffSeconds));
            bool endedTurn = !dynamics.Turning && !dynamics.TurningInPlace && IsTurn(previousPhase);
            float previousLength = MotionLibrary.IsInPlace(previousPhase) ? Mathf.Abs(dynamics.LatchedTurnAngle) >= p.pivotAngle ? idlePivotLength : idleLength
                : Mathf.Abs(dynamics.LatchedTurnAngle) >= p.pivotAngle ? pivotLength : turnLength;
            bool completedTurn = endedTurn && previousTime + dt >= previousLength;
            intendedRotation = completedTurn ? Quaternion.Euler(0, latchedYaw, 0) : transform.rotation;
            if (endedTurn) heading.Reset(intendedRotation * Vector3.forward);
            float visualSpeed = Speed;
            if ((dynamics.Turning && !Targeting || dynamics.TurningInPlace) && !acting)
            {
                float length = dynamics.TurningInPlace ? Mathf.Abs(dynamics.LatchedTurnAngle) >= p.pivotAngle ? idlePivotLength : idleLength
                    : Mathf.Abs(dynamics.LatchedTurnAngle) >= p.pivotAngle ? pivotLength : turnLength;
                PhaseNormalized = Mathf.Clamp01(dynamics.PhaseTime / Mathf.Max(0.01f, length));
                intendedRotation = Quaternion.Euler(0, Mathf.LerpUnclamped(turnStartYaw, latchedYaw, p.turnProgress.Evaluate(PhaseNormalized)), 0);
                visualSpeed = dynamics.TurningInPlace ? 0 : visualSpeed * Mathf.Clamp01(p.turnSpeedScale.Evaluate(PhaseNormalized));
                heading.Reset(intendedRotation * Vector3.forward);
            }
            else if (!endedTurn && (Targeting || facingRequested && dynamics.Phase == LocomotionPhase.Idle && Mathf.Abs(HeadingError) < p.idleTurnAngle) && facingTarget.sqrMagnitude > 0.001f)
            {
                intendedRotation = Quaternion.RotateTowards(transform.rotation, Quaternion.LookRotation(facingTarget), p.targetFacingSpeed * dt);
                heading.Reset(intendedRotation * Vector3.forward);
            }
            else if (!endedTurn && hasInput && (!acting || combat.IsOpen(WindowKind.Turn)))
            {
                var solved = heading.Step(motor.Facing, desired, Speed, dt, p);
                intendedRotation = Quaternion.LookRotation(solved.SolvedDirection);
                TurnBlend = Mathf.Sign(solved.YawRate) * solved.TurnBlend;
            }
            else TurnBlend = Mathf.MoveTowards(TurnBlend, 0, dt * 5);
            YawRate = dt > 0 ? Mathf.DeltaAngle(transform.eulerAngles.y, intendedRotation.eulerAngles.y) / dt : 0;
            if (acting && !combat.IsOpen(WindowKind.Turn)) intendedRotation = transform.rotation;
            else if (acting) intendedRotation = Quaternion.Slerp(transform.rotation, intendedRotation, action.turnScale);
            if (hasInput) lastTargetMoveDirection = desired;
            intendedVelocity = (Targeting && (hasInput || UsesMotionLibrary) ? lastTargetMoveDirection : intendedRotation * Vector3.forward) * visualSpeed;
            if (UsesMotionLibrary && !motor.IsGrounded)
            {
                float control = motionPlayer.WorkingLibrary.airControl;
                airVelocity = Vector3.MoveTowards(airVelocity, intendedVelocity, p.acceleration * control * dt);
                intendedVelocity = airVelocity;
            }
            if (acting && movementScale == 0 || frozen) intendedVelocity = Vector3.zero;
            if (frozen) intendedRotation = transform.rotation;
            var local = Quaternion.Inverse(intendedRotation) * intendedVelocity;
            LocalVelocity = new Vector2(local.x, local.z) / Mathf.Max(0.01f, p.strafeSpeed);
            UpdateAnimator(p, action, frozen, dt);
        }

        private static bool IsTurn(LocomotionPhase p) => p == LocomotionPhase.PivotLeft || p == LocomotionPhase.PivotRight || p == LocomotionPhase.Turn90Left || p == LocomotionPhase.Turn90Right || MotionLibrary.IsInPlace(p);

        private void UpdateAnimator(LocomotionProfile p, ActionDefinition action, bool frozen, float dt)
        {
            if (UsesMotionLibrary) { motionPlayer.Tick(action, p, dt); return; }
            if (animator.runtimeAnimatorController == null) return;
            animator.speed = frozen ? 0 : 1;
            animator.SetInteger(StanceParam, (int)stance);
            animator.SetInteger(PhaseParam, (int)Phase);
            float gait = Speed <= p.runSpeed ? Speed / Mathf.Max(0.01f, p.runSpeed) : 1 + (Speed - p.runSpeed) / Mathf.Max(0.01f, p.sprintSpeed - p.runSpeed);
            animator.SetFloat("Gait", gait, profile.parameterDamping, dt);
            animator.SetFloat("Turn", TurnBlend, profile.parameterDamping, dt);
            animator.SetFloat("LocomotionTime", PhaseNormalized);
            animator.SetFloat("MoveX", LocalVelocity.x, profile.parameterDamping, dt);
            animator.SetFloat("MoveY", LocalVelocity.y, profile.parameterDamping, dt);
            animator.SetBool("ActionActive", action != null);
            animator.SetBool("Targeting", Targeting);
            if (action != null)
            {
                animator.SetFloat("ActionTime", action.NormalizedTime(combat.TimeInAction));
                bool alternate = !string.IsNullOrEmpty(action.animatorAlternateState) && (combat.Sequence & 1) == 0;
                string timeParameter = alternate ? action.alternateTimeParameter : action.animationTimeParameter;
                if (!string.IsNullOrEmpty(timeParameter)) animator.SetFloat(timeParameter, action.NormalizedTime(combat.TimeInAction));
                if (lastActionSequence != combat.Sequence)
                {
                    lastActionSequence = combat.Sequence;
                    string path = alternate ? action.animatorAlternateState : string.IsNullOrEmpty(action.animatorState) ? "Base Layer.Actions." + action.id + ".A" : action.animatorState;
                    int hash = Animator.StringToHash(path);
                    if (animator.HasState(0, hash)) animator.CrossFadeInFixedTime(hash, action.blendIn, 0, 0);
                    else Debug.LogWarning("Missing generated Animator state: " + path, this);
                }
            }
            if (previousPhase != Phase)
            {
                var state = animator.GetCurrentAnimatorStateInfo(0);
                phaseSeed = Mathf.Repeat(state.normalizedTime, 1);
            }
            animator.SetFloat("StopFoot", phaseSeed < 0.5f ? 0 : 1);
        }

        private void LateUpdate()
        {
            if (LastConfigurationError == null && profile != null && motor != null && animator != null)
            {
                var action = combat != null ? combat.Current : null;
                bool frozen = combat != null && combat.suspended;
                bool root = !UsesMotionLibrary && !frozen && receivedRoot && animator.hasRootMotion && (action != null ? action.movement == MovementAuthority.RootMotion : profile.locomotionRootMotion);
                Vector3 delta = root ? rootDelta * (action != null ? action.rootMotionScale : 1) : intendedVelocity * Time.deltaTime;
                if (action != null && action.movement == MovementAuthority.Stationary || frozen) delta = Vector3.zero;
                // CharacterController gravity owns vertical displacement for this first grounded controller.
                delta.y = 0;
                Quaternion rotation = root && action != null && action.applyRootRotation ? transform.rotation * rootRotation : intendedRotation;
                MotionOwner = frozen ? "Suspended" : root ? "Motor / Animator delta" : "Motor / procedural";
                if (!frozen)
                {
                    bool groundedBefore = motor.IsGrounded;
                    motor.ApplyDisplacement(delta, rotation, Time.deltaTime);
                    // Walking off a ledge inherits collision-resolved momentum, not the last jump's velocity.
                    if (groundedBefore && motor.VerticalSpeed <= 0)
                    { airVelocity = motor.Velocity; airVelocity.y = 0; }
                    // Input runs before Update: close the airborne gate in the departure frame.
                    if (UsesMotionLibrary && combat != null) combat.LocomotionInputBlocked = jumpAge >= 0 || !motor.IsGrounded;
                }
            }
            rootDelta = Vector3.zero; rootRotation = Quaternion.identity; receivedRoot = false;
            FrameCompleted?.Invoke(this);
        }
    }
}
