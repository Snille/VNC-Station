import unittest

from app.logic import find_remote_holder, parse_chat_command


class LogicTests(unittest.TestCase):
    def test_parse_chat_command(self):
        self.assertEqual(parse_chat_command("/nick Station-2"), ("/nick", "Station-2"))
        self.assertEqual(parse_chat_command("/notify"), ("/notify", ""))
        self.assertEqual(parse_chat_command("hello"), ("", "hello"))

    def test_find_remote_holder(self):
        remote = {
            ("A", "view"): "Station 02",
            ("B", "control"): "Station 03",
        }
        self.assertEqual(find_remote_holder("A", remote, "Station 01"), "Station 02")
        self.assertIsNone(find_remote_holder("B", remote, "Station 03"))
        self.assertIsNone(find_remote_holder("X", remote, "Station 01"))


if __name__ == "__main__":
    unittest.main()

