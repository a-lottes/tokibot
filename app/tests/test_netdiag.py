import unittest

from tokibot import netdiag


class NetDiagTest(unittest.TestCase):
    def test_report_runs_anywhere_and_hides_password(self):
        text = netdiag.report({"wifi": {"ssid": "casa", "psk": "secret-pass", "country": "DE"}})
        self.assertIn("Configured Wi-Fi: casa, country DE", text)
        self.assertIn("Password set: yes", text)
        self.assertNotIn("secret-pass", text)
        for title, _ in netdiag.COMMANDS:
            self.assertIn(f"== {title}", text)
        self.assertIn("== wpa_supplicant", text)


if __name__ == "__main__":
    unittest.main()
