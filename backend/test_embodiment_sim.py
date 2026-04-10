import unittest

from embodiment_sim import EmbodimentSimulation


class EmbodimentSimulationTests(unittest.TestCase):
    def test_sim_strain_is_normalized_by_cpu_capacity(self):
        sim = EmbodimentSimulation()
        sim.sim_strain = 0.40

        sim.update_from_telemetry({
            "cpu_cores": [10.0] * 10,
            "load_avg": (2.0, 2.0, 2.0),
            "memory_percent": 32.0,
            "uptime_seconds": 3600,
            "quietude_active": False,
        })

        self.assertLess(sim.sim_strain, 0.40)

    def test_sim_strain_rises_on_sustained_cpu_saturation(self):
        sim = EmbodimentSimulation()

        sim.update_from_telemetry({
            "cpu_cores": [95.0] * 10,
            "load_avg": (12.0, 13.0, 14.0),
            "memory_percent": 44.0,
            "uptime_seconds": 3600,
            "quietude_active": False,
        })

        self.assertGreater(sim.sim_strain, 0.0)

    def test_quietude_accelerates_strain_recovery(self):
        active = EmbodimentSimulation()
        quiet = EmbodimentSimulation()
        active.sim_strain = 0.50
        quiet.sim_strain = 0.50

        low_load = {
            "cpu_cores": [10.0] * 10,
            "load_avg": (0.5, 0.5, 0.5),
            "memory_percent": 32.0,
            "uptime_seconds": 3600,
        }

        active.update_from_telemetry({**low_load, "quietude_active": False})
        quiet.update_from_telemetry({**low_load, "quietude_active": True})

        self.assertLess(quiet.sim_strain, active.sim_strain)


if __name__ == "__main__":
    unittest.main()
