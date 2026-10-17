"""Independent thermal-network arithmetic and derating checks."""
import math
import unittest
import losses

class ThermalChecks(unittest.TestCase):
    def test_closed_form_common_sink(self):
        # Identical devices and no spatial allowance reduce to one linear equation.
        case = dict(frequency_hz=36000, i_rms_a=20, target_w=1710, vrms_v=120)
        ambient, rsa, rcs, switching = 50., .15, 1., 12.
        bridge = 2 * 1.05 * 15 * 2 * math.sqrt(2) / math.pi
        alpha = 200 * .018 * 1.2 / 125
        beta = 200 * .018 * (1 - 1.2 * 25 / 125) + switching
        path = 4 * rsa + .28 + rcs
        expected = (ambient + rsa * bridge + path * beta) / (1 - path * alpha)
        result = losses.solve(case, dict.fromkeys(losses.MOS, switching), ambient, rsa, rcs, 0, False)
        for ref in losses.MOS:
            self.assertAlmostEqual(result['tj_C'][ref], expected, places=7)
        self.assertAlmostEqual(result['sink_W'], bridge + 4 * (alpha * expected + beta), places=7)

    def test_unpowered_network_stays_at_ambient(self):
        result = losses.solve(dict(frequency_hz=36000,i_rms_a=0,target_w=0,vrms_v=120),
                              dict.fromkeys(losses.MOS,0),50,.15,1,20,True)
        self.assertEqual(result['tj_C'],dict.fromkeys(losses.REFS,50.))
        self.assertEqual(result['sink_W'],0)

    def test_unusable_interface_has_no_sink_solution(self):
        case = dict(frequency_hz=36000,i_rms_a=20,target_w=1710,vrms_v=120)
        self.assertIsNone(losses.limit_rsa(case,dict.fromkeys(losses.MOS,12),50,100,True))

    def test_resistance_and_derating_reference_points(self):
        self.assertAlmostEqual(losses.rds(25),.018)
        self.assertAlmostEqual(losses.rds(150),.0396)
        for t, expected in [(40,1),(70,1),(100,.7),(125,.45),(170,0),(200,0)]:
            self.assertAlmostEqual(losses.rating_r5(t),expected)

if __name__ == '__main__':
    unittest.main()
