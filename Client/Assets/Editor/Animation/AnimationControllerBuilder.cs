using System;
using System.Collections.Generic;
using System.IO;
using Afauxzhub.CharacterLocomotion;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace Afauxzhub.Project.Editor.Animation
{
    public static class AnimationControllerBuilder
    {
        public static AnimatorController Build(CharacterAnimationProfile profile, string path)
        {
            if (profile == null) throw new ArgumentNullException(nameof(profile));
            AnimationBindingTools.RequireLocalDestination(path, profile, profile.previewModel);
            foreach (var set in new[] { profile.sheathed, profile.drawn }) foreach (var binding in set.motions) if (binding != null) AnimationBindingTools.RequireLocalDestination(path, binding.clip);
            foreach (var action in profile.actions) if (action != null) AnimationBindingTools.RequireLocalDestination(path, action, action.clip);
            if (EditorApplication.isPlaying) throw new InvalidOperationException("Leave Play Mode before generating assets.");
            if (!path.StartsWith("Assets/", StringComparison.Ordinal) || Path.GetExtension(path) != ".controller") throw new ArgumentException("Choose an Assets/*.controller path.");
            if (File.Exists(path)) throw new InvalidOperationException("Generate to a new file; hand-edited controllers are never overwritten.");
            var actionIds = new HashSet<string>();
            foreach (var action in profile.actions)
            {
                if (action == null) continue;
                if (string.IsNullOrWhiteSpace(action.id) || action.id.Contains(".") || !actionIds.Add(action.id))
                    throw new InvalidOperationException("Action IDs must be unique, non-empty and contain no dots.");
                string expected = "Base Layer.Actions." + action.id;
                if ((!string.IsNullOrEmpty(action.animatorState) && action.animatorState != expected + ".A") ||
                    (!string.IsNullOrEmpty(action.animatorAlternateState) && action.animatorAlternateState != expected + ".B"))
                    throw new InvalidOperationException("Custom/stale action state paths on " + action.id + ". Keep editing the custom graph, or explicitly clear both paths before generating a new graph.");
            }
            profile.EnsureSlots();
            var controller = AnimatorController.CreateAnimatorControllerAtPath(path);
            foreach (string p in new[] { "Gait", "Turn", "MoveX", "MoveY", "ActionTime", "ActionTimeA", "ActionTimeB", "LocomotionTime", "StopFoot" }) controller.AddParameter(p, AnimatorControllerParameterType.Float);
            controller.AddParameter("Phase", AnimatorControllerParameterType.Int);
            controller.AddParameter("Stance", AnimatorControllerParameterType.Int);
            controller.AddParameter("ActionActive", AnimatorControllerParameterType.Bool);
            controller.AddParameter("Targeting", AnimatorControllerParameterType.Bool);
            var root = controller.layers[0].stateMachine;
            root.defaultState = root.AddState("Entry", new Vector3(200, 0));
            root.defaultState.motion = profile.sheathed.Find(MotionSlot.Idle)?.clip;
            var locomotion = new List<(AnimatorState state, WeaponStance stance, LocomotionPhase phase)>();
            foreach (WeaponStance stance in Enum.GetValues(typeof(WeaponStance)))
            {
                var set = profile.Set(stance);
                var machine = root.AddStateMachine(stance.ToString(), new Vector3(450, (int)stance * 180));
                int i = 0;
                foreach (LocomotionPhase phase in Enum.GetValues(typeof(LocomotionPhase)))
                {
                    var state = machine.AddState(phase.ToString(), new Vector3(260 + (i % 3) * 230, (i / 3) * 100)); i++;
                    state.motion = PhaseMotion(controller, set, phase);
                    state.tag = "Locomotion";
                    if (phase == LocomotionPhase.Start || phase == LocomotionPhase.Stop || phase == LocomotionPhase.PivotLeft || phase == LocomotionPhase.PivotRight || phase == LocomotionPhase.Turn90Left || phase == LocomotionPhase.Turn90Right || phase == LocomotionPhase.Land)
                    { state.timeParameter = "LocomotionTime"; state.timeParameterActive = true; }
                    state.writeDefaultValues = false; // All clips should bind the same skeleton; coverage checker makes omissions visible.
                    locomotion.Add((state, stance, phase));
                    if (phase == LocomotionPhase.Idle) machine.defaultState = state;
                }
                // Optional authored variation, visible but not automatically scheduled by gameplay.
                var variation = machine.AddState("IdleVariation_Manual", new Vector3(950, 500));
                variation.motion = Clip(controller, set, MotionSlot.IdleVariation); variation.writeDefaultValues = false;
            }
            // Local explicit transitions, not global Any State. Selecting a state exposes its editable exits.
            // All phase pairs are supported so simultaneous target/stance/grounding changes cannot strand a state.
            foreach (var target in locomotion)
            {
                AddMotionTransition(root.defaultState, target.state, target.stance, target.phase, 0);
                foreach (var origin in locomotion)
                    if (origin.state != target.state)
                        AddMotionTransition(origin.state, target.state, target.stance, target.phase,
                            origin.stance == target.stance ? profile.motionBlend : profile.stanceBlend);
            }
            var actions = root.AddStateMachine("Actions", new Vector3(450, 380));
            int n = 0;
            foreach (var action in profile.actions)
            {
                if (action == null) continue;
                var actionMachine = actions.AddStateMachine(action.id, new Vector3(260 + (n % 3) * 240, (n / 3) * 95)); n++;
                foreach (string channel in new[] { "A", "B" })
                {
                    var state = actionMachine.AddState(channel, new Vector3(250, channel == "A" ? 0 : 150));
                    state.motion = action.clip;
                    state.writeDefaultValues = false;
                    state.timeParameter = "ActionTime" + channel;
                    state.timeParameterActive = true;
                    // Rules command action entry; the visible graph owns the blend back to locomotion.
                    foreach (WeaponStance stance in Enum.GetValues(typeof(WeaponStance)))
                    {
                        foreach (LocomotionPhase phase in Enum.GetValues(typeof(LocomotionPhase)))
                        {
                            var exit = state.AddTransition(FindState(root, stance.ToString(), phase.ToString()));
                            exit.hasExitTime = false; exit.hasFixedDuration = true; exit.duration = action.blendOut;
                            exit.AddCondition(AnimatorConditionMode.IfNot, 0, "ActionActive");
                            exit.AddCondition(AnimatorConditionMode.Equals, (int)stance, "Stance");
                            exit.AddCondition(AnimatorConditionMode.Equals, (int)phase, "Phase");
                        }
                    }
                }
                // Preserve custom paths: changing a generated ID is an explicit user edit, not a silent overwrite.
                string generated = "Base Layer.Actions." + action.id;
                if (string.IsNullOrEmpty(action.animatorState) || action.animatorState == generated + ".A")
                {
                    Undo.RecordObject(action, "Set generated state paths");
                    action.animatorState = generated + ".A"; action.animatorAlternateState = generated + ".B";
                    action.animationTimeParameter = "ActionTimeA"; action.alternateTimeParameter = "ActionTimeB"; EditorUtility.SetDirty(action);
                }
            }
            Undo.RecordObject(profile, "Assign Animator controller"); profile.controller = controller;
            EditorUtility.SetDirty(profile); AssetDatabase.SaveAssetIfDirty(profile); AssetDatabase.SaveAssetIfDirty(controller);
            foreach (var action in profile.actions) if (action != null) AssetDatabase.SaveAssetIfDirty(action);
            return controller;
        }

        private static void AddMotionTransition(AnimatorState source, AnimatorState target, WeaponStance stance, LocomotionPhase phase, float blend)
        {
            var transition = source.AddTransition(target);
            transition.name = stance + "/" + phase;
            transition.hasExitTime = false; transition.hasFixedDuration = true; transition.duration = blend;
            // Query the destination's exits while blending. Re-evaluating the source with
            // unordered interruption can repeatedly restart this same always-true edge.
            transition.interruptionSource = TransitionInterruptionSource.Destination;
            transition.orderedInterruption = false;
            transition.canTransitionToSelf = false;
            transition.AddCondition(AnimatorConditionMode.IfNot, 0, "ActionActive");
            transition.AddCondition(AnimatorConditionMode.Equals, (int)stance, "Stance");
            transition.AddCondition(AnimatorConditionMode.Equals, (int)phase, "Phase");
        }

        private static AnimatorState FindState(AnimatorStateMachine root, string machine, string name)
        {
            foreach (var m in root.stateMachines) if (m.stateMachine.name == machine)
                foreach (var s in m.stateMachine.states) if (s.state.name == name) return s.state;
            throw new InvalidOperationException("Missing generated state " + machine + "/" + name);
        }
        private static Motion PhaseMotion(AnimatorController c, StanceAnimationSet set, LocomotionPhase phase)
        {
            switch (phase)
            {
                case LocomotionPhase.Move: return Gait(c, set);
                case LocomotionPhase.Strafe:
                    var strafe = Tree(c, "Targeted locomotion (missing slots use idle)", "MoveX");
                    strafe.blendType = BlendTreeType.FreeformCartesian2D; strafe.blendParameterY = "MoveY";
                    strafe.AddChild(Clip(c, set, MotionSlot.Idle), Vector2.zero);
                    var slots = new[] { MotionSlot.StrafeForward, MotionSlot.StrafeBack, MotionSlot.StrafeLeft, MotionSlot.StrafeRight, MotionSlot.StrafeForwardLeft, MotionSlot.StrafeForwardRight, MotionSlot.StrafeBackLeft, MotionSlot.StrafeBackRight };
                    var positions = new[] { Vector2.up, Vector2.down, Vector2.left, Vector2.right, new Vector2(-1,1).normalized, new Vector2(1,1).normalized, new Vector2(-1,-1).normalized, new Vector2(1,-1).normalized };
                    for (int i = 0; i < slots.Length; i++) strafe.AddChild(Clip(c, set, slots[i]), positions[i]);
                    return strafe;
                case LocomotionPhase.Stop:
                    var stop = Tree(c, "Stop foot", "StopFoot"); stop.AddChild(Clip(c, set, MotionSlot.StopLeft), 0); stop.AddChild(Clip(c, set, MotionSlot.StopRight), 1); return stop;
                default:
                    if (Enum.TryParse(phase.ToString(), out MotionSlot slot))
                    {
                        var binding = set.Find(slot);
                        if (binding != null && binding.clip != null)
                        {
                            var single = Tree(c, slot.ToString(), "Gait");
                            single.children = new[] { new ChildMotion { motion = binding.clip, timeScale = Mathf.Max(0.01f, binding.playbackSpeed), threshold = 0 } };
                            return single;
                        }
                        if (phase == LocomotionPhase.Accelerate || phase == LocomotionPhase.Decelerate) return Gait(c, set);
                        return Clip(c, set, slot);
                    }
                    return Clip(c, set, MotionSlot.Idle);
            }
        }
        private static BlendTree Gait(AnimatorController c, StanceAnimationSet set)
        {
            var gait = Tree(c, "Speed and curved steering", "Gait");
            gait.AddChild(Clip(c, set, MotionSlot.Idle), 0);
            gait.AddChild(Clip(c, set, MotionSlot.Walk, MotionSlot.Run), set.movement != null ? Mathf.Clamp(set.movement.walkSpeed / Mathf.Max(0.01f, set.movement.runSpeed), 0.01f, 0.99f) : 0.4f);
            var run = Tree(c, "Run arcs", "Turn");
            run.AddChild(Clip(c, set, MotionSlot.ArcSharpLeft, MotionSlot.ArcLeft, MotionSlot.Run), -1);
            run.AddChild(Clip(c, set, MotionSlot.ArcLeft, MotionSlot.Run), -0.45f);
            run.AddChild(Clip(c, set, MotionSlot.Run), 0);
            run.AddChild(Clip(c, set, MotionSlot.ArcRight, MotionSlot.Run), 0.45f);
            run.AddChild(Clip(c, set, MotionSlot.ArcSharpRight, MotionSlot.ArcRight, MotionSlot.Run), 1);
            var sprint = Tree(c, "Sprint arcs", "Turn");
            sprint.AddChild(Clip(c, set, MotionSlot.SprintLeft, MotionSlot.Sprint, MotionSlot.Run), -1);
            sprint.AddChild(Clip(c, set, MotionSlot.Sprint, MotionSlot.Run), 0);
            sprint.AddChild(Clip(c, set, MotionSlot.SprintRight, MotionSlot.Sprint, MotionSlot.Run), 1);
            gait.AddChild(run, 1); gait.AddChild(sprint, 2); return gait;
        }
        private static BlendTree Tree(AnimatorController controller, string name, string parameter)
        {
            var tree = new BlendTree { name = name, blendType = BlendTreeType.Simple1D, blendParameter = parameter, useAutomaticThresholds = false };
            AssetDatabase.AddObjectToAsset(tree, controller); return tree;
        }
        private static Motion Clip(AnimatorController controller, StanceAnimationSet set, params MotionSlot[] candidates)
        {
            MotionBinding binding = null;
            foreach (var slot in candidates) { var b = set.Find(slot); if (b != null && b.clip != null) { binding = b; break; } }
            binding = binding ?? set.Find(MotionSlot.Idle); // Missing directional clips are explicitly reported by the workbench.
            if (binding?.clip == null) return null;
            var tree = Tree(controller, candidates[0] + (binding.slot == candidates[0] ? "" : " [PLACEHOLDER: " + binding.slot + "]"), "Gait");
            tree.children = new[] { new ChildMotion { motion = binding.clip, timeScale = Mathf.Max(0.01f, binding.playbackSpeed), threshold = 0 } };
            return tree;
        }
    }
}
