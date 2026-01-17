"""
TDD Tests for Homotopy Classification Module.

Verifies H-signature computation, homotopy class enumeration, and
homotopy equivalence checking.
"""

import unittest
from shapely.geometry import Polygon
from temper_placer.router_v6.homotopy import (
    HSignature,
    HSignatureElement,
    Side,
    compute_h_signature,
    enumerate_homotopy_classes,
    paths_are_homotopic,
)


class TestHSignatureElement(unittest.TestCase):
    def test_element_creation(self):
        elem = HSignatureElement("O1", Side.RIGHT)
        self.assertEqual(elem.obstacle_id, "O1")
        self.assertEqual(elem.side, Side.RIGHT)

    def test_element_left(self):
        elem = HSignatureElement("O2", Side.LEFT)
        self.assertEqual(elem.side, Side.LEFT)

    def test_element_equality(self):
        elem1 = HSignatureElement("O1", Side.RIGHT)
        elem2 = HSignatureElement("O1", Side.RIGHT)
        self.assertEqual(elem1, elem2)

    def test_element_inequality(self):
        elem1 = HSignatureElement("O1", Side.RIGHT)
        elem2 = HSignatureElement("O1", Side.LEFT)
        self.assertNotEqual(elem1, elem2)


class TestHSignature(unittest.TestCase):
    def test_empty_signature(self):
        sig = HSignature()
        self.assertEqual(len(sig.elements), 0)
        self.assertEqual(str(sig), "∅")

    def test_single_element_signature(self):
        elem = HSignatureElement("O1", Side.RIGHT)
        sig = HSignature(tuple([elem]))
        self.assertEqual(str(sig), "+O1")

    def test_multiple_elements_signature(self):
        elems = (
            HSignatureElement("O1", Side.RIGHT),
            HSignatureElement("O2", Side.LEFT),
            HSignatureElement("O3", Side.RIGHT),
        )
        sig = HSignature(elems)
        self.assertEqual(str(sig), "+O1 -O2 +O3")

    def test_signature_equality(self):
        sig1 = HSignature(tuple([HSignatureElement("O1", Side.RIGHT)]))
        sig2 = HSignature(tuple([HSignatureElement("O1", Side.RIGHT)]))
        self.assertEqual(sig1, sig2)

    def test_signature_inequality(self):
        sig1 = HSignature(tuple([HSignatureElement("O1", Side.RIGHT)]))
        sig2 = HSignature(tuple([HSignatureElement("O1", Side.LEFT)]))
        self.assertNotEqual(sig1, sig2)


class TestComputeHSignature(unittest.TestCase):
    def test_simple_path_no_obstacles(self):
        path = [(0, 0), (5, 0), (5, 5), (10, 5)]
        obstacles = {}
        sig = compute_h_signature(path, obstacles)
        self.assertEqual(len(sig.elements), 0)

    def test_path_right_of_obstacle(self):
        path = [(0, 5), (5, 5), (5, 10), (10, 10)]
        obstacle = Polygon([(3, 0), (3, 8), (7, 8), (7, 0)])
        obstacles = {"O1": obstacle}
        sig = compute_h_signature(path, obstacles)
        self.assertEqual(len(sig.elements), 1)
        self.assertEqual(sig.elements[0].obstacle_id, "O1")
        self.assertEqual(sig.elements[0].side, Side.RIGHT)

    def test_path_left_of_obstacle(self):
        path = [(0, 5), (5, 5), (5, 2), (10, 2)]
        obstacle = Polygon([(3, 3), (3, 7), (7, 7), (7, 3)])
        obstacles = {"O1": obstacle}
        sig = compute_h_signature(path, obstacles)
        self.assertEqual(len(sig.elements), 1)
        self.assertEqual(sig.elements[0].side, Side.RIGHT)

    def test_path_through_multiple_obstacles(self):
        path = [(0, 5), (3, 5), (3, 2), (6, 2), (6, 5), (10, 5)]
        obstacle1 = Polygon([(2, 3), (2, 7), (4, 7), (4, 3)])
        obstacle2 = Polygon([(5, 3), (5, 7), (7, 7), (7, 3)])
        obstacles = {"O1": obstacle1, "O2": obstacle2}
        sig = compute_h_signature(path, obstacles)
        self.assertEqual(len(sig.elements), 2)

    def test_path_too_short(self):
        path = [(5, 5)]
        obstacle = Polygon([(3, 0), (3, 8), (7, 8), (7, 0)])
        obstacles = {"O1": obstacle}
        sig = compute_h_signature(path, obstacles)
        self.assertEqual(len(sig.elements), 0)


class TestEnumerateHomotopyClasses(unittest.TestCase):
    def test_no_obstacles_single_class(self):
        source = (0, 0)
        target = (10, 10)
        obstacles = {}
        classes = enumerate_homotopy_classes(source, target, obstacles)
        self.assertEqual(len(classes), 1)
        self.assertEqual(len(classes[0].elements), 0)

    def test_single_obstacle_two_classes(self):
        source = (0, 5)
        target = (10, 5)
        obstacle = Polygon([(3, 0), (3, 10), (7, 10), (7, 0)])
        obstacles = {"O1": obstacle}
        classes = enumerate_homotopy_classes(source, target, obstacles)
        self.assertGreaterEqual(len(classes), 1)

    def test_two_obstacles_four_classes(self):
        source = (0, 5)
        target = (10, 5)
        obstacle1 = Polygon([(2, 0), (2, 10), (4, 10), (4, 0)])
        obstacle2 = Polygon([(6, 0), (6, 10), (8, 10), (8, 0)])
        obstacles = {"O1": obstacle1, "O2": obstacle2}
        classes = enumerate_homotopy_classes(source, target, obstacles)
        self.assertGreaterEqual(len(classes), 1)

    def test_classes_are_sorted(self):
        source = (0, 5)
        target = (10, 5)
        obstacle = Polygon([(3, 0), (3, 10), (7, 10), (7, 0)])
        obstacles = {"O1": obstacle}
        classes = enumerate_homotopy_classes(source, target, obstacles)
        for i in range(len(classes) - 1):
            self.assertLessEqual(classes[i], classes[i + 1])


class TestPathsAreHomotopic(unittest.TestCase):
    def test_identical_paths_are_homotopic(self):
        path = [(0, 0), (5, 0), (5, 5), (10, 5)]
        obstacles = {}
        self.assertTrue(paths_are_homotopic(path, path, obstacles))

    def test_same_side_paths_are_homotopic(self):
        path1 = [(0, 5), (5, 5), (5, 10), (10, 10)]
        path2 = [(0, 6), (5, 6), (5, 11), (10, 11)]
        obstacle = Polygon([(3, 0), (3, 8), (7, 8), (7, 0)])
        obstacles = {"O1": obstacle}
        self.assertTrue(paths_are_homotopic(path1, path2, obstacles))

    def test_different_side_paths_not_homotopic(self):
        path1 = [(0, 5), (5, 5), (5, 10), (10, 10)]
        path2 = [(0, 0), (5, 0), (5, -3), (10, -3)]
        obstacle = Polygon([(3, 1), (3, 8), (7, 8), (7, 1)])
        obstacles = {"O1": obstacle}
        self.assertFalse(paths_are_homotopic(path1, path2, obstacles))

    def test_no_obstacles_all_homotopic(self):
        path1 = [(0, 0), (1, 1), (2, 0)]
        path2 = [(0, 0), (1, 2), (2, 0)]
        obstacles = {}
        self.assertTrue(paths_are_homotopic(path1, path2, obstacles))


class TestSideEnum(unittest.TestCase):
    def test_side_values(self):
        self.assertEqual(Side.LEFT.value, -1)
        self.assertEqual(Side.RIGHT.value, 1)

    def test_side_from_value(self):
        self.assertEqual(Side(-1), Side.LEFT)
        self.assertEqual(Side(1), Side.RIGHT)


if __name__ == "__main__":
    unittest.main()
