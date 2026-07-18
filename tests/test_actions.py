import unittest

from app import VisionEngine, resolve_action_name, resolve_action_sequence


class ActionBehaviorTests(unittest.TestCase):
    def test_resolve_action_prefers_resource_action(self):
        self.assertEqual(resolve_action_name({"action": "swipe"}, "click"), "swipe")
        self.assertEqual(resolve_action_name({"action": "CLICK"}, "click"), "click")
        self.assertEqual(resolve_action_name({}, "click"), "click")
        self.assertEqual(resolve_action_name({"action": "unknown"}, "click"), "click")

    def test_resolve_action_sequence_supports_wait_and_click(self):
        self.assertEqual(resolve_action_sequence("click->wait:0.4->swipe"), ["click", "wait:0.4", "swipe"])
        self.assertEqual(resolve_action_sequence("tap;swipe"), ["tap", "swipe"])
        self.assertEqual(resolve_action_sequence(""), ["click"])

    def test_perform_action_swipe_uses_drag(self):
        class FakePyAutoGUI:
            def __init__(self):
                self.moves = []
                self.clicks = []
                self.drags = []

            def moveTo(self, x, y, duration=0.0):
                self.moves.append((x, y, duration))

            def click(self, x, y):
                self.clicks.append((x, y))

            def dragTo(self, x, y, duration=0.0, button=None):
                self.drags.append((x, y, duration, button))

        fake_pyautogui = FakePyAutoGUI()
        engine = VisionEngine.__new__(VisionEngine)
        engine._get_pyautogui = lambda: fake_pyautogui

        success = engine.perform_action("swipe", (200, 300), screen_size=(1280, 720))

        self.assertTrue(success)
        self.assertEqual(len(fake_pyautogui.drags), 1)
        self.assertEqual(fake_pyautogui.drags[0][0], 320)
        self.assertEqual(fake_pyautogui.drags[0][1], 220)


if __name__ == "__main__":
    unittest.main()
