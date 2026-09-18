using System;
using System.Collections.Generic;

namespace Afauxzhub.TimelineAbilities
{
    public interface IAbilityInstructionSink
    {
        void Enter(AbilityInstruction instruction);
        void Update(AbilityInstruction instruction, float elapsedTime, float deltaTime);
        void Exit(AbilityInstruction instruction, bool cancelled);
    }

    /// <summary>
    /// Plays compiled instructions without a PlayableDirector. The combat controller owns
    /// cast permission, resource payment, hit-stun restrictions and cancellation policy.
    /// </summary>
    public sealed class AbilitySequencePlayer
    {
        private readonly IAbilityInstructionSink sink;
        private AbilityRuntimePlan plan;
        private bool[] active;
        private bool[] started;
        private float elapsedTime;
        private int playbackVersion;

        public AbilitySequencePlayer(IAbilityInstructionSink sink)
        {
            this.sink = sink ?? throw new ArgumentNullException(nameof(sink));
        }

        public bool IsPlaying => plan != null;
        public float ElapsedTime => elapsedTime;

        public void Play(AbilityRuntimePlan newPlan)
        {
            if (newPlan == null)
            {
                throw new ArgumentNullException(nameof(newPlan));
            }

            Cancel();
            plan = newPlan;
            active = new bool[plan.Instructions.Count];
            started = new bool[plan.Instructions.Count];
            elapsedTime = 0f;
            playbackVersion++;
            Evaluate(0f, 0f);
            if (plan != null && plan.Duration <= 0f)
            {
                Finish(false);
            }
        }

        public void Advance(float deltaTime)
        {
            if (plan == null || deltaTime < 0f)
            {
                return;
            }

            float previousTime = elapsedTime;
            elapsedTime = Math.Min(plan.Duration, elapsedTime + deltaTime);
            int version = playbackVersion;
            Evaluate(previousTime, deltaTime);
            if (version == playbackVersion && plan != null && elapsedTime >= plan.Duration)
            {
                Finish(false);
            }
        }

        public void Cancel()
        {
            Finish(true);
        }

        private void Evaluate(float previousTime, float deltaTime)
        {
            int version = playbackVersion;
            AbilityRuntimePlan evaluatedPlan = plan;
            bool[] evaluatedActive = active;
            bool[] evaluatedStarted = started;
            IReadOnlyList<AbilityInstruction> instructions = evaluatedPlan.Instructions;
            for (int i = 0; i < instructions.Count; i++)
            {
                AbilityInstruction instruction = instructions[i];
                bool startsNow = !evaluatedStarted[i]
                    && previousTime <= instruction.startTime
                    && elapsedTime >= instruction.startTime;
                if (startsNow)
                {
                    evaluatedStarted[i] = true;
                    evaluatedActive[i] = true;
                    sink.Enter(instruction);
                    if (version != playbackVersion)
                    {
                        return;
                    }
                    if (instruction.IsInstant)
                    {
                        evaluatedActive[i] = false;
                        sink.Exit(instruction, false);
                        if (version != playbackVersion)
                        {
                            return;
                        }
                        continue;
                    }
                }

                if (!evaluatedActive[i])
                {
                    continue;
                }

                float localTime = Math.Max(0f, elapsedTime - instruction.startTime);
                sink.Update(instruction, localTime, deltaTime);
                if (version != playbackVersion)
                {
                    return;
                }
                if (elapsedTime >= instruction.endTime)
                {
                    evaluatedActive[i] = false;
                    sink.Exit(instruction, false);
                    if (version != playbackVersion)
                    {
                        return;
                    }
                }
            }
        }

        private void Finish(bool cancelled)
        {
            if (plan == null)
            {
                return;
            }

            AbilityRuntimePlan finishedPlan = plan;
            bool[] finishedActive = active;
            IReadOnlyList<AbilityInstruction> instructions = finishedPlan.Instructions;
            plan = null;
            active = null;
            started = null;
            elapsedTime = 0f;
            playbackVersion++;

            for (int i = 0; i < finishedActive.Length; i++)
            {
                if (!finishedActive[i])
                {
                    continue;
                }

                finishedActive[i] = false;
                sink.Exit(instructions[i], cancelled);
            }
        }
    }
}
