# Limits: what is not modelled

* **Thrust lapse with altitude.** Thrust tables are sea-level tables (read at the actual
  temperature if they have a temperature column). High-elevation results are optimistic
  unless the table is for that altitude.
* **Pitch dynamics.** Point-mass, longitudinal model: the attitude is prescribed (hold,
  rotate at a set rate, hold), not flown.
* **Lateral-directional motion.** Only V_mcg, as a lower limit on V1.
* **Time-varying wind** on the main pages: a steady headwind or tailwind only. Turbulence
  is covered by the [Gust analysis](gusts.md).
* **Sloped airborne segment.** After lift-off the ground is treated as flat, with h above
  the lift-off point (an error of order 10⁻⁵ rad/s in dγ/dt on a sloped runway).
* **Ground effect on lift.** The Raymer method changes drag only.
* **Tire and brake limits.** The maximum tire ground speed and the rejected-takeoff brake
  energy are reported (tire speed warned against `app/reference_aircraft.yaml`), not
  enforced.
* **Climb requirements** after the screen height (e.g. Part 25.121 second segment).
* **Wet-runway rule changes** (Part 25 wet V1 and 15 ft screen); a wet runway is modelled
  through friction only.
* **Reverser stowing** at low speed during the landing roll.
* **Pitot-static position error** (KEAS is used for KCAS).
