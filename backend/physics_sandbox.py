import pymunk
import json
import math
import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("omega.physics_sandbox")


class PhysicsSandbox:
    """
    Ghost's internal physical imagination engine.
    A 2D rigid-body simulation Ghost uses to mentally rehearse physical
    scenarios — verifying hypotheses about motion, friction, inertia,
    tipping, sliding, and collision before expressing conclusions.
    """

    def __init__(self, gravity: Tuple[float, float] = (0, -900)):
        self.space = pymunk.Space()
        self.space.gravity = gravity
        self.entities: Dict[str, Any] = {}
        self._forces: List[Dict[str, Any]] = []  # scheduled continuous forces
        self._constraints: List[Any] = []

    # ── Shape builders ─────────────────────────────────────────────────────

    def add_static_line(self, name: str, start: Tuple, end: Tuple, friction: float = 0.5):
        segment = pymunk.Segment(self.space.static_body, start, end, 2.0)
        segment.friction = friction
        self.space.add(segment)
        self.entities[name] = segment
        return name

    def add_box(
        self,
        name: str,
        pos: Tuple,
        size: Tuple,
        mass: float = 1.0,
        friction: float = 0.5,
        elasticity: float = 0.1,
    ):
        moment = pymunk.moment_for_box(mass, size)
        body = pymunk.Body(mass, moment)
        body.position = pos
        shape = pymunk.Poly.create_box(body, size)
        shape.friction = friction
        shape.elasticity = elasticity
        self.space.add(body, shape)
        self.entities[name] = (body, shape)
        return name

    def add_circle(
        self,
        name: str,
        pos: Tuple,
        radius: float,
        mass: float = 1.0,
        friction: float = 0.5,
        elasticity: float = 0.1,
    ):
        """For cylindrical objects like glasses, cups, cans."""
        moment = pymunk.moment_for_circle(mass, 0, radius)
        body = pymunk.Body(mass, moment)
        body.position = pos
        shape = pymunk.Circle(body, radius)
        shape.friction = friction
        shape.elasticity = elasticity
        self.space.add(body, shape)
        self.entities[name] = (body, shape)
        return name

    def add_segment_body(
        self,
        name: str,
        pos: Tuple,
        start: Tuple,
        end: Tuple,
        mass: float = 0.5,
        friction: float = 0.3,
    ):
        """Thin plank body — useful for tablecloths, planks, levers."""
        length = math.sqrt((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2)
        moment = pymunk.moment_for_segment(mass, start, end, 2.0)
        body = pymunk.Body(mass, moment)
        body.position = pos
        shape = pymunk.Segment(body, start, end, 2.0)
        shape.friction = friction
        self.space.add(body, shape)
        self.entities[name] = (body, shape)
        return name

    # ── Force / impulse ────────────────────────────────────────────────────

    def apply_impulse(self, name: str, impulse: Tuple, point: Tuple = (0, 0)):
        """Single-frame impulse — for sudden hits."""
        if name in self.entities:
            entity = self.entities[name]
            if isinstance(entity, tuple):
                body, _ = entity
                body.apply_impulse_at_local_point(impulse, point)

    def schedule_force(
        self,
        name: str,
        force: Tuple,
        start_time: float = 0.0,
        end_time: float = 1.0,
        point: Tuple = (0, 0),
    ):
        """
        Schedule a continuous force on an entity over [start_time, end_time].
        Models string pulls, sustained pushes, gravity-like effects.
        """
        self._forces.append(
            {
                "name": name,
                "force": force,
                "start": start_time,
                "end": end_time,
                "point": point,
            }
        )

    # ── Constraints ────────────────────────────────────────────────────────

    def add_pivot_joint(self, name_a: str, name_b: str, anchor: Tuple):
        """Pin two bodies together at a shared anchor point (hinge)."""
        if name_a in self.entities and name_b in self.entities:
            body_a = self.entities[name_a][0]
            body_b = self.entities[name_b][0]
            joint = pymunk.PinJoint(body_a, body_b, anchor, anchor)
            self.space.add(joint)
            self._constraints.append(joint)

    def add_string(self, name_a: str, name_b: str, max_length: Optional[float] = None):
        """
        Inextensible string between two objects.
        Uses a SlideJoint that is slack until taut.
        """
        if name_a in self.entities and name_b in self.entities:
            body_a = self.entities[name_a][0]
            body_b = self.entities[name_b][0]
            dist = body_a.position.get_distance(body_b.position)
            max_len = max_length or dist
            joint = pymunk.SlideJoint(body_a, body_b, (0, 0), (0, 0), 0, max_len)
            self.space.add(joint)
            self._constraints.append(joint)

    # ── Simulation runner ──────────────────────────────────────────────────

    def run_simulation(
        self, duration: float = 2.0, dt: float = 1.0 / 60.0
    ) -> List[Dict[str, Any]]:
        steps = int(duration / dt)
        trace = []
        t = 0.0

        for _ in range(steps):
            # Apply scheduled continuous forces
            for f in self._forces:
                if f["start"] <= t <= f["end"] and f["name"] in self.entities:
                    entity = self.entities[f["name"]]
                    if isinstance(entity, tuple):
                        body, _ = entity
                        body.apply_force_at_local_point(f["force"], f["point"])

            self.space.step(dt)
            t += dt

            state = {}
            for name, entity in self.entities.items():
                if isinstance(entity, tuple):
                    body, _ = entity
                    state[name] = {
                        "x": round(body.position.x, 3),
                        "y": round(body.position.y, 3),
                        "angle_deg": round(math.degrees(body.angle), 2),
                        "vx": round(body.velocity.x, 3),
                        "vy": round(body.velocity.y, 3),
                    }
            trace.append(state)

        return trace

    # ── High-level scenario solver ─────────────────────────────────────────

    def solve_scenario(self, scenario_json: str) -> Dict[str, Any]:
        """
        High-level entry point for Ghost's physical imagination.

        Scenario JSON schema:
        {
          "description": "optional human-readable label",
          "gravity": [0, -900],          // optional override
          "table_friction": 0.5,
          "objects": [
            {"type": "box",    "name": "glass",  "pos": [0,  30], "size": [20, 40], "mass": 0.3, "friction": 0.6},
            {"type": "circle", "name": "ball",   "pos": [50, 30], "radius": 15,     "mass": 0.2, "friction": 0.4},
            {"type": "plank",  "name": "cloth",  "pos": [0,   2], "start": [-250, 0], "end": [250, 0], "mass": 0.1, "friction": 0.2}
          ],
          "constraints": [
            {"type": "string", "a": "hand", "b": "cloth"}
          ],
          "actions": [
            {"type": "impulse",        "target": "glass",  "vector": [200, 0]},
            {"type": "force",          "target": "cloth",  "vector": [3000, 0], "start": 0.0, "end": 0.5},
            {"type": "force_steady",   "target": "glass",  "vector": [500, 0],  "start": 0.0, "end": 2.0}
          ],
          "duration": 2.0,
          "track": ["glass"]  // objects to analyse in the summary
        }
        """
        try:
            config = json.loads(scenario_json) if isinstance(scenario_json, str) else scenario_json

            # Override gravity if specified
            if "gravity" in config:
                self.space.gravity = tuple(config["gravity"])

            # Static table surface
            table_friction = config.get("table_friction", 0.5)
            self.add_static_line("table", (-1000, 0), (1000, 0), friction=table_friction)

            # Build objects
            for obj in config.get("objects", []):
                otype = obj.get("type", "box")
                name = obj["name"]
                pos = tuple(obj["pos"])
                if otype == "box":
                    self.add_box(
                        name, pos,
                        tuple(obj.get("size", [20, 40])),
                        mass=obj.get("mass", 1.0),
                        friction=obj.get("friction", 0.5),
                        elasticity=obj.get("elasticity", 0.1),
                    )
                elif otype == "circle":
                    self.add_circle(
                        name, pos,
                        radius=obj.get("radius", 15),
                        mass=obj.get("mass", 1.0),
                        friction=obj.get("friction", 0.5),
                        elasticity=obj.get("elasticity", 0.1),
                    )
                elif otype == "plank":
                    self.add_segment_body(
                        name, pos,
                        tuple(obj.get("start", (-100, 0))),
                        tuple(obj.get("end", (100, 0))),
                        mass=obj.get("mass", 0.5),
                        friction=obj.get("friction", 0.3),
                    )

            # Constraints
            for con in config.get("constraints", []):
                ctype = con.get("type")
                if ctype == "string":
                    self.add_string(con["a"], con["b"], con.get("max_length"))
                elif ctype == "pivot":
                    self.add_pivot_joint(con["a"], con["b"], tuple(con["anchor"]))

            # Actions
            for act in config.get("actions", []):
                atype = act.get("type", "impulse")
                target = act.get("target")
                if atype == "impulse":
                    self.apply_impulse(target, tuple(act["vector"]))
                elif atype in ("force", "force_steady"):
                    self.schedule_force(
                        target,
                        tuple(act["vector"]),
                        start_time=act.get("start", 0.0),
                        end_time=act.get("end", 1.0),
                        point=tuple(act.get("point", (0, 0))),
                    )

            # Run
            duration = config.get("duration", 2.0)
            trace = self.run_simulation(duration=duration)

            if not trace:
                return {"status": "error", "message": "Simulation produced no frames."}

            # Analyse tracked objects
            track = config.get("track", [])
            if not track:
                # default: track all dynamic objects
                track = [
                    k for k, v in self.entities.items()
                    if isinstance(v, tuple) and k != "table"
                ]

            initial = trace[0]
            final = trace[-1]
            analysis: Dict[str, Any] = {}
            narrative_parts = []

            for obj_name in track:
                if obj_name not in final:
                    continue
                f = final[obj_name]
                i = initial.get(obj_name, f)
                dx = f["x"] - i["x"]
                dy = f["y"] - i["y"]
                dist = round(math.sqrt(dx ** 2 + dy ** 2), 2)
                fell = f["y"] < -50  # fell off table
                tipped = abs(f["angle_deg"]) > 30
                spilled = tipped or fell  # proxy for liquid spill

                analysis[obj_name] = {
                    "initial": i,
                    "final": f,
                    "displacement": {"dx": round(dx, 2), "dy": round(dy, 2), "total": dist},
                    "fell_off_table": fell,
                    "tipped_over": tipped,
                    "spilled": spilled,
                }

                if fell:
                    narrative_parts.append(
                        f"{obj_name} fell off the table (displaced {dist:.1f} units, angle {f['angle_deg']:.1f}°)."
                    )
                elif tipped:
                    narrative_parts.append(
                        f"{obj_name} tipped over (angle {f['angle_deg']:.1f}°, moved {dist:.1f} units). Contents would spill."
                    )
                else:
                    narrative_parts.append(
                        f"{obj_name} slid {dist:.1f} units, remained upright (angle {f['angle_deg']:.1f}°)."
                    )

            description = config.get("description", "physical scenario")
            narrative = (
                f"Simulated: {description}. " + " ".join(narrative_parts)
                if narrative_parts
                else f"Simulated: {description}. No tracked objects moved significantly."
            )

            return {
                "status": "success",
                "description": description,
                "analysis": analysis,
                "narrative": narrative,
                "frame_count": len(trace),
                "duration_s": duration,
            }

        except Exception as e:
            logger.error("PhysicsSandbox.solve_scenario error: %s", e)
            return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    # Tablecloth pull test: slow pull with friction
    sb = PhysicsSandbox()
    scenario = {
        "description": "Glass of water on table, tablecloth pulled slowly",
        "table_friction": 0.8,
        "objects": [
            {
                "type": "circle", "name": "glass",
                "pos": [0, 25], "radius": 15, "mass": 0.3, "friction": 0.7
            },
            {
                "type": "plank", "name": "cloth",
                "pos": [0, 3], "start": [-250, 0], "end": [250, 0],
                "mass": 0.1, "friction": 0.2
            },
        ],
        "actions": [
            {
                "type": "force_steady", "target": "cloth",
                "vector": [1200, 0], "start": 0.0, "end": 1.5
            }
        ],
        "duration": 2.0,
        "track": ["glass"],
    }
    import json as _json
    print(_json.dumps(sb.solve_scenario(scenario), indent=2))
