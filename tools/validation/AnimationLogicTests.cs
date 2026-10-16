using System;
using System.Collections.Generic;
using Afauxzhub.CharacterLocomotion;
using Afauxzhub.Project.Animation;

internal static class AnimationLogicTests
{
    private static int passed;
    private static void Check(bool value, string name) { if (!value) throw new Exception("FAIL: " + name); passed++; Console.WriteLine("PASS " + name); }
    private static ActionWindow W(float start, float end) => new ActionWindow { start = start, end = end };
    private static void Step(LocomotionDynamics d, float speed = 5, float angle = 0, bool target = false, bool ground = true, float dt = 0.05f)
        => d.Step(speed, angle, target, ground, dt, 12, 16, 0.25f, 0.3f, 0.45f, 0.3f, 140, 75, 1, 0.08f, 0.2f);
    private static int Main()
    {
        try
        {
            ClockTests(); RuleTests(); LocomotionTests();
            Console.WriteLine($"{passed} assertions passed. Pure logic only; no Unity API or renderer executed."); return 0;
        }
        catch (Exception e) { Console.Error.WriteLine(e); return 1; }
    }
    private static void ClockTests()
    {
        var clock = new ActionClock(); var events = new List<string>();
        clock.WindowChanged += (i, enter) => events.Add((enter ? "+" : "-") + i);
        clock.Cue += i => events.Add("c" + i);
        clock.Start(1, new[] { W(0, 0.25f), W(0.25f, 0.5f), W(0.75f, 1) }, new[] { 0f, 0.25f, 0.8f });
        Check(string.Join(",", events) == "+0,c0", "time-zero events dispatched once");
        events.Clear(); clock.Advance(0.25);
        Check(string.Join(",", events) == "-0,+1,c1", "same-time boundary order: exit, enter, cue");
        Check(!clock.IsActive(0) && clock.IsActive(1), "half-open interval state");
        events.Clear(); clock.Advance(2);
        Check(string.Join(",", events) == "-1,+2,c2,-2", "large delta crosses every boundary");
        Check(clock.Finished && clock.Time == 1 && !clock.IsActive(2), "natural finish clamps and closes");
        events.Clear(); clock.Advance(1); Check(events.Count == 0, "completed action never refires");
        clock.Start(2, new[] { W(0, 1), W(0, 1.5f) }, Array.Empty<float>()); events.Clear(); clock.Stop();
        Check(string.Join(",", events) == "-0,-1", "interrupt closes all active windows once");
        events.Clear(); clock.Stop(); Check(events.Count == 0, "stop is idempotent");
        clock.Start(1, new[] { W(0.25f, 0.5f) }, Array.Empty<float>()); clock.Advance(0); clock.Advance(-1); clock.Advance(double.NaN); clock.Advance(double.PositiveInfinity);
        Check(clock.Time == 0 && !clock.IsActive(0), "pause and invalid delta do not advance");
        var interrupted = new ActionClock(); int cues = 0;
        interrupted.WindowChanged += (i, enter) => { if (enter) interrupted.Stop(); };
        interrupted.Cue += i => cues++;
        interrupted.Start(1, new[] { W(0.1f, 0.2f) }, new[] { 0.15f }); interrupted.Advance(1);
        Check(interrupted.Finished && cues == 0, "callback interrupt prevents stale dispatch");
        var replacement = new ActionClock(); bool replaced = false;
        replacement.Cue += i => { if (!replaced) { replaced = true; replacement.Start(2, new[] { W(0, 1) }, Array.Empty<float>()); } };
        replacement.Start(1, Array.Empty<ActionWindow>(), new[] { 0.1f }); replacement.Advance(0.9);
        Check(replaced && replacement.Time == 0 && replacement.IsActive(0) && !replacement.Finished, "callback action replacement has independent clock");
        var duringExit = new ActionClock(); bool restartOnExit = false;
        duringExit.WindowChanged += (i, enter) => { if (!enter && !restartOnExit) { restartOnExit = true; duringExit.Start(2, new[] { W(0, 1) }, Array.Empty<float>()); } };
        duringExit.Start(1, new[] { W(0, 0.5f), W(0, 0.8f) }, Array.Empty<float>());
        duringExit.Stop(); Check(duringExit.IsActive(0) && !duringExit.Finished, "exit callback replacement is not closed by stale exits");
        bool invalidDuration = false; try { new ActionClock().Start(double.NaN, Array.Empty<ActionWindow>(), Array.Empty<float>()); } catch (ArgumentOutOfRangeException) { invalidDuration = true; }
        Check(invalidDuration, "NaN duration fails closed");
        foreach (int fps in new[] { 15, 30, 60, 120 })
        {
            var c = new ActionClock(); int entries = 0, exits = 0;
            c.WindowChanged += (i, enter) => { if (enter) entries++; else exits++; };
            c.Start(1, new[] { W(0.031f, 0.033f), W(0.6f, 0.7f) }, Array.Empty<float>());
            for (int i = 0; i <= fps; i++) c.Advance(1.0 / fps);
            Check(entries == 2 && exits == 2 && c.Finished, "narrow windows survive " + fps + " fps");
        }
    }
    private static void RuleTests()
    {
        var open = new HashSet<WindowKind>(); bool Has(WindowKind k) => open.Contains(k);
        Check(ActionRules.CanRequest(null, ActionKind.LightAttack, Has), "free state accepts ordinary attack");
        Check(!ActionRules.CanRequest(null, ActionKind.Counter, Has), "counter cannot be a button action");
        Check(!ActionRules.CanRequest(ActionKind.LightAttack, ActionKind.Counter, Has, true), "resolved counter still requires live attack window");
        open.Add(WindowKind.Counter);
        Check(ActionRules.CanRequest(ActionKind.LightAttack, ActionKind.Counter, Has, true), "resolved collision inside attack window may trigger counter");
        Check(!ActionRules.CanRequest(ActionKind.LightHit, ActionKind.Counter, Has, true), "hit-stun rejects stale counter result");
        Check(!ActionRules.CanRequest(null, ActionKind.LightHit, Has), "reaction requires combat result");
        Check(ActionRules.CanRequest(ActionKind.LightAttack, ActionKind.LightHit, Has, true), "authoritative hit can interrupt attack");
        Check(!ActionRules.CanRequest(ActionKind.LightAttack, ActionKind.Dodge, Has), "closed cancel window blocks dodge");
        open.Add(WindowKind.CancelToEvade); Check(ActionRules.CanRequest(ActionKind.LightAttack, ActionKind.Dodge, Has), "dodge window grants dodge only");
        Check(!ActionRules.CanRequest(ActionKind.LightAttack, ActionKind.Guard, Has), "dodge window does not grant guard");
        open.Add(WindowKind.CancelToGuard); open.Add(WindowKind.CancelToSkill); open.Add(WindowKind.Combo);
        Check(ActionRules.CanRequest(ActionKind.LightAttack, ActionKind.Skill, Has), "skill window permits request before payment gate");
        Check(ActionRules.CanRequest(ActionKind.LightAttack, ActionKind.HeavyAttack, Has), "combo window accepts attack branch");
        foreach (ActionKind reaction in new[] { ActionKind.LightHit, ActionKind.HeavyHit, ActionKind.Launch, ActionKind.Knockdown, ActionKind.WallHit })
            Check(!ActionRules.CanRequest(reaction, ActionKind.Skill, Has), reaction + " never skill-cancelled");
        Check(!ActionRules.CanRequest(ActionKind.HeavyHit, ActionKind.Dodge, Has), "ordinary dodge window cannot escape hit-stun");
        open.Add(WindowKind.EvadeEscape); Check(ActionRules.CanRequest(ActionKind.HeavyHit, ActionKind.Dodge, Has), "separate explicit hit-stun escape window");
        Check(!ActionRules.CanRequest(ActionKind.Death, ActionKind.LightHit, Has, true), "death blocks interruption");
        Check(ActionRules.NeedsGate(ActionKind.Guard) && ActionRules.NeedsGate(ActionKind.Skill) && ActionRules.NeedsGate(ActionKind.Ultimate), "paid actions require external permission gate");
    }
    private static void LocomotionTests()
    {
        var d = new LocomotionDynamics(); Step(d);
        Check(d.Phase == LocomotionPhase.Start && d.Speed > 0 && d.Speed < 5, "input starts accelerating, not instant run");
        for (int i = 0; i < 20; i++) Step(d);
        Check(d.Phase == LocomotionPhase.Move && Math.Abs(d.Speed - 5) < 0.001, "steady run converges");
        Step(d, 8); Check(d.Phase == LocomotionPhase.Accelerate, "sprint change enters acceleration");
        Step(d, 2); Check(d.Phase == LocomotionPhase.Decelerate, "walk change enters deceleration");
        Step(d, 0); Check(d.Phase != LocomotionPhase.Stop, "input release debounce avoids one-frame stop");
        for (int i = 0; i < 20; i++) Step(d, 0);
        Check(d.Phase == LocomotionPhase.Idle && d.Speed == 0, "stop reaches idle after duration");
        d.Reset(); Step(d, 5, 180); Check(d.Phase == LocomotionPhase.PivotRight, "180-degree pivot state exists");
        Step(d, 5, -90); Check(d.Phase == LocomotionPhase.PivotRight && d.LatchedTurnAngle == 180, "pivot target is latched");
        for (int i = 0; i < 10; i++) Step(d, 5, 0);
        Check(!d.Turning, "pivot finishes without retrigger loop");
        d.Reset(); Step(d, 5, -90); Check(d.Phase == LocomotionPhase.Turn90Left, "dedicated left 90-degree turn");
        d.Reset(); Step(d, 5, 90); Check(d.Phase == LocomotionPhase.Turn90Right, "dedicated right 90-degree turn");
        Step(d, 3, 180, true); Check(d.Phase == LocomotionPhase.Strafe, "targeting overrides free-facing pivot");
        Step(d, 3, 0, true, false); Check(d.Phase == LocomotionPhase.Fall, "airborne overrides strafe");
        Step(d, 3, 0, true); Check(d.Phase == LocomotionPhase.Land, "landing has dedicated state");
        var targeted = new LocomotionDynamics();
        targeted.Step(3, 180, true, true, 0.05f, 12, 16, 0.25f, 0.3f, 0.45f, 0.3f, 140, 75, 1, 0.08f, 0.2f, true);
        Check(targeted.Phase == LocomotionPhase.Start, "opt-in targeting has directional start instead of pivot");
        for (int i = 0; i < 20; i++) targeted.Step(3, 180, true, true, 0.05f, 12, 16, 0.25f, 0.3f, 0.45f, 0.3f, 140, 75, 1, 0.08f, 0.2f, true);
        Check(targeted.Phase == LocomotionPhase.Strafe, "opt-in targeting reaches steady strafe");
        for (int i = 0; i < 2; i++) targeted.Step(0, 180, true, true, 0.05f, 12, 16, 0.25f, 0.3f, 0.45f, 0.3f, 140, 75, 1, 0.08f, 0.2f, true);
        Check(targeted.Phase == LocomotionPhase.Stop, "opt-in targeting has stop phase");
        float previous = d.Speed, elapsed = d.PhaseTime; Step(d, 9, 0, true, true, 0);
        Check(d.Speed == previous && d.PhaseTime == elapsed, "zero delta freezes locomotion");
        foreach (int fps in new[] { 15, 30, 60, 120 })
        {
            d.Reset(); for (int i = 0; i < fps * 2; i++) Step(d, 5, 0, false, true, 1f / fps);
            Check(Math.Abs(d.Speed - 5) < 0.001 && d.Phase == LocomotionPhase.Move, "speed converges at " + fps + " fps");
        }
    }
}
