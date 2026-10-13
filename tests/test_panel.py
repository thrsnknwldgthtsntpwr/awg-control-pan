import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from awg_panel.auth import AuthStore
from awg_panel.validate import expires_flag, parse_names, valid_client_name


class TestValidate(unittest.TestCase):
    def test_names(self):
        self.assertTrue(valid_client_name("my_phone-1"))
        self.assertFalse(valid_client_name("bad name"))
        self.assertFalse(valid_client_name("../x"))
        self.assertFalse(valid_client_name("a" * 64))

    def test_parse(self):
        ok, bad = parse_names("a, b;c\nd, a, bad name!")
        self.assertEqual(ok, ["a", "b", "c", "d", "bad"])
        self.assertEqual(bad, ["name!"])

    def test_expires_days_only(self):
        self.assertIsNone(expires_flag(""))
        self.assertIsNone(expires_flag(None))
        self.assertEqual(expires_flag("7"), "--expires=7d")
        with self.assertRaises(ValueError):
            expires_flag("7h")
        with self.assertRaises(ValueError):
            expires_flag("abc")
        with self.assertRaises(ValueError):
            expires_flag("99999")


class TestAuth(unittest.TestCase):
    def test_hash_verify(self):
        import tempfile
        h = AuthStore.hash_password("s3cret-password")
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write(h + "\n")
            path = f.name
        st = AuthStore(path, "/tmp/nonexistent-auth.log", 60)
        self.assertTrue(st.verify("s3cret-password"))
        self.assertFalse(st.verify("wrong"))

    def test_sessions(self):
        st = AuthStore("/nonexistent", "/tmp/nonexistent-auth.log", 60)
        s = st.create("1.2.3.4")
        self.assertIsNotNone(st.get(s.sid))
        st.destroy(s.sid)
        self.assertIsNone(st.get(s.sid))

    def test_rate_limit(self):
        st = AuthStore("/nonexistent", "/tmp/nonexistent-auth.log", 60)
        for _ in range(5):
            st.note_fail("9.9.9.9")
        self.assertTrue(st.blocked("9.9.9.9"))


if __name__ == "__main__":
    unittest.main()
