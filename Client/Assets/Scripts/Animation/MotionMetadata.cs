using System;
using System.Collections.Generic;
using Afauxzhub.CharacterLocomotion;
using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    public struct MotionSupport
    {
        public float left, right, knownWeight;
        public bool Authored => knownWeight > 0.5f && Mathf.Abs(left - right) > 0.05f;
        public MotionSlot StopSlot(float fallbackPhase) => Authored
            ? left >= right ? MotionSlot.StopLeft : MotionSlot.StopRight
            : Mathf.Repeat(fallbackPhase, 1) < 0.5f ? MotionSlot.StopLeft : MotionSlot.StopRight;
        public override string ToString() => $"L {left:F2} / R {right:F2} · known {knownWeight:P0} · {(Authored ? "authored contact" : "estimated half-cycle (no foot lock)")}";
    }

    public sealed partial class MotionLibrary
    {
        public MotionSupport Support(IList<MotionSample> pose)
        {
            var result = new MotionSupport();
            foreach (var sample in pose)
            {
                var entry = ById(sample.id);
                if (entry == null || !entry.contactAuthored || entry.leftContact == null || entry.rightContact == null) continue;
                result.knownWeight += sample.weight;
                result.left += Mathf.Clamp01(entry.leftContact.Evaluate(sample.normalizedTime)) * sample.weight;
                result.right += Mathf.Clamp01(entry.rightContact.Evaluate(sample.normalizedTime)) * sample.weight;
            }
            return result;
        }

        public static bool IsInPlace(LocomotionPhase phase) => phase == LocomotionPhase.TurnInPlaceLeft || phase == LocomotionPhase.TurnInPlaceRight
            || phase == LocomotionPhase.PivotInPlaceLeft || phase == LocomotionPhase.PivotInPlaceRight;

        public float PhaseDuration(LocomotionPhase phase, WeaponStance stance, MotionGait gait, MotionMode mode, MotionDirection direction,
            MotionSlot stop, float speed, float angle, float fallback)
        {
            var slot = phase == LocomotionPhase.Stop ? stop : MotionLibraryPlayer.SlotFor(phase, 0);
            var entry = Find(stance, slot, gait, direction, mode, speed, angle, out _);
            return entry != null && entry.stageSeconds > 0 ? Mathf.Max(0.01f, entry.stageSeconds) : Mathf.Max(0.01f, fallback);
        }
    }

    /// <summary>Explicit slot requirements, not filename-driven runtime behavior. Optional refinements are not mandatory missing clips.</summary>
    public static class MotionCatalog
    {
        public static IEnumerable<MotionEntry> Requirements()
        {
            foreach (WeaponStance stance in Enum.GetValues(typeof(WeaponStance)))
            {
                foreach (MotionSlot slot in Enum.GetValues(typeof(MotionSlot)))
                    yield return new MotionEntry { stance = stance, slot = slot, direction = slot == MotionSlot.Start ? MotionDirection.Forward : MotionDirection.Any,
                        optional = slot == MotionSlot.IdleVariation, note = "Missing resource; a fallback is not visual acceptance." };
                foreach (MotionDirection direction in Enum.GetValues(typeof(MotionDirection)))
                    if (direction != MotionDirection.Any && direction != MotionDirection.Forward)
                        yield return new MotionEntry { stance = stance, slot = MotionSlot.Start, direction = direction };
                foreach (MotionGait gait in new[] { MotionGait.Walk, MotionGait.Run, MotionGait.Sprint })
                    for (int slot = (int)MotionSlot.StrafeForward; slot <= (int)MotionSlot.StrafeBackRight; slot++)
                        yield return new MotionEntry { stance = stance, slot = (MotionSlot)slot, gait = gait, optional = true, note = "Optional gait refinement: reviewed Any entry may be explicitly shared." };
            }
        }
        public static string Selector(MotionEntry e) => $"{e.stance}/{e.mode}/{e.slot}/{e.gait}/{e.direction}";
        public static string SuggestedSuffix(MotionEntry e)
        {
            string name = e.slot.ToString();
            if (e.gait != MotionGait.Any) name += e.gait;
            if (e.direction != MotionDirection.Any && !(e.slot == MotionSlot.Start && e.direction == MotionDirection.Forward)) name += e.direction;
            if (e.mode != MotionMode.Any) name += e.mode;
            return name;
        }
        public static int AddMissing(MotionLibrary library)
        {
            int count = 0;
            foreach (var requirement in Requirements())
                if (!library.entries.Exists(e => e != null && Selector(e) == Selector(requirement))) { library.entries.Add(requirement); count++; }
            return count;
        }
    }
}
