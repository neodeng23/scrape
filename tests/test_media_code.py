import unittest

from parser import extract_media_code


class MediaCodeTests(unittest.TestCase):
    def test_standard_codes(self) -> None:
        self.assertEqual(extract_media_code("SSNI00103.mp4"), "SSNI-103")
        self.assertEqual(extract_media_code("ABP-123-cd1.mp4"), "ABP-123")
        self.assertEqual(extract_media_code("FC2-PPV-123456.mp4"), "FC2-123456")

    def test_prefixed_date_codes(self) -> None:
        self.assertEqual(extract_media_code("carib-230101-001.mp4"), "CARIB-230101-001")
        self.assertEqual(extract_media_code("1pondo-240101_001.mp4"), "1PONDO-240101-001")

    def test_brackets_stripped(self) -> None:
        self.assertEqual(extract_media_code("[44x.me]SSIS-001 HD.mp4"), "SSIS-1")

    def test_compact_format(self) -> None:
        self.assertEqual(extract_media_code("ABP123.mp4"), "ABP-123")

    def test_fc2_variants(self) -> None:
        self.assertEqual(extract_media_code("FC2-PPV-1234567.mkv"), "FC2-1234567")
        self.assertEqual(extract_media_code("FC2PPV 1234567.mp4"), "FC2-1234567")

    def test_heyzo(self) -> None:
        self.assertEqual(extract_media_code("HEYZO-1234.mp4"), "HEYZO-1234")

    def test_noise_tokens_ignored(self) -> None:
        code = extract_media_code("[PRESTIGE]ABP-456 FHD.mp4")
        self.assertEqual(code, "ABP-456")


if __name__ == "__main__":
    unittest.main()
