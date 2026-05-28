import unittest

from parsers.media_code import extract_media_code


class MediaCodeTests(unittest.TestCase):
    def test_extracts_standard_codes(self) -> None:
        self.assertEqual(extract_media_code("SSNI00103.mp4"), "SSNI-103")
        self.assertEqual(extract_media_code("ABP-123-cd1.mp4"), "ABP-123")
        self.assertEqual(extract_media_code("FC2-PPV-123456.mp4"), "FC2-123456")

    def test_preserves_prefixed_date_codes(self) -> None:
        self.assertEqual(extract_media_code("carib-230101-001.mp4"), "CARIB-230101-001")
        self.assertEqual(extract_media_code("1pondo-240101_001.mp4"), "1PONDO-240101-001")


if __name__ == "__main__":
    unittest.main()
