# Event location

Code: `src/bfl/integrators.py` (`Event`, `locate_in_step`, `integrate`) and
`src/bfl/phases.py` (the takeoff events).

An **event** is a function $g(t, y)$ whose zero marks something happening:

| Event | $g(t, y)$ | Direction |
|---|---|---|
| reach V1 / VR | $V_a - V_{\text{target}}$ | upward |
| lift-off | $N$ (unclamped normal force) | downward |
| 35 ft screen | $h - 35$ | upward |
| stopped | $V$ | downward |
| touchback | $h + 0.01$ | downward |

## The method

After every accepted step $[t_n, t_n + h]$, check whether $g$ changed sign in the
required direction. If it did, find the crossing time $t^* = t_n + s^*$ by solving

$$
\varphi(s) = g\big(t_n + s,\; \Phi(t_n, y_n, s)\big) = 0, \qquad s \in [0, h],
$$

where $\Phi(t_n, y_n, s)$ is **one RK step of size $s$ taken again from the start of the
step**. The root is found with the [safeguarded secant method](root_finding.md) to a
tolerance of $10^{-9}$ s. Then:

* the state at the event, $\Phi(t_n, y_n, s^*)$, is as accurate as an ordinary step of
  the method (no lower-order interpolation);
* the event point is inserted into the output, and a *terminal* event stops the
  integration there.

A step that *starts* exactly on $g = 0$ (for example the first step of a segment that
began at an event) does not count as a new crossing.

## Why not just interpolate?

Linear interpolation between $y_n$ and $y_{n+1}$ would introduce an $O(h^2)$ error in
the event time and state, wasting RK4's $O(h^4)$ accuracy. Re-taking the step
costs a few extra function evaluations per event, and there are only about a dozen
events per branch.

## Evidence

The event time for $y' = -0.7y$ crossing $y = 0.3$ is the same to about
$4\times10^{-7}$ s whether $h = 0.1$, $0.03$ or $0.0071$
(`tests/test_integrators.py::test_event_location_independent_of_step`). The remaining
difference is the RK4 step accuracy, not the choice of step size.

## The cached roll trick

The all-engines roll is integrated once, to VR. To find the state at an arbitrary
airspeed (needed for V_EF in every inner iteration), `phases.state_at_airspeed` uses a
**binary search** over the stored rows to find the bracketing step. It then runs the
same partial-step event location inside that step. This makes each inner iteration
cost one second of simulation, not a whole roll.
