import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from models import Movie
from nfo import write_nfo


class NfoTests(unittest.TestCase):
    def _write_and_parse(self, movie: Movie) -> ET.Element:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "movie.nfo"
            write_nfo(path, movie)
            tree = ET.parse(path)
            return tree.getroot()

    def test_minimal_movie(self) -> None:
        root = self._write_and_parse(Movie(code="ABP-123", title="Test"))
        self.assertEqual(root.find("title").text, "Test")
        self.assertEqual(root.find("sorttitle").text, "ABP-123")
        uid = root.find("uniqueid")
        self.assertEqual(uid.text, "ABP-123")
        self.assertEqual(uid.get("type"), "num")
        self.assertEqual(uid.get("default"), "true")
        self.assertEqual(root.find("mpaa").text, "NC-17")

    def test_full_movie(self) -> None:
        m = Movie(
            code="ABP-123",
            title="Title",
            originaltitle="Original",
            plot="A plot.",
            released="2024-01-15",
            year="2024",
            runtime="120",
            studio="Studio",
            director="Director",
            series="Series",
            actors=["Alice", "Bob"],
            genres=["Genre1", "Genre2"],
            poster_url="https://example.com/poster.jpg",
            fanart_url="https://example.com/fanart.jpg",
            trailer_url="https://example.com/trailer.mp4",
        )
        root = self._write_and_parse(m)

        self.assertEqual(root.find("originaltitle").text, "Original")
        self.assertEqual(root.find("premiered").text, "2024-01-15")
        self.assertEqual(root.find("year").text, "2024")
        self.assertEqual(root.find("runtime").text, "120")
        self.assertEqual(root.find("studio").text, "Studio")
        self.assertEqual(root.find("director").text, "Director")
        self.assertEqual(root.find("set/name").text, "Series")

        genres = [g.text for g in root.findall("genre")]
        self.assertEqual(genres, ["Genre1", "Genre2"])

        actors = [a.find("name").text for a in root.findall("actor")]
        self.assertEqual(actors, ["Alice", "Bob"])

        thumb = root.find("thumb")
        self.assertEqual(thumb.text, "https://example.com/poster.jpg")
        self.assertEqual(thumb.get("aspect"), "poster")

        fanart = root.find("fanart")
        self.assertIsNotNone(fanart)
        self.assertEqual(fanart.find("thumb").text, "https://example.com/fanart.jpg")

        self.assertEqual(root.find("trailer").text, "https://example.com/trailer.mp4")

    def test_empty_fields_omitted(self) -> None:
        root = self._write_and_parse(Movie(code="ABP-123", title="Test"))
        self.assertIsNone(root.find("plot"))
        self.assertIsNone(root.find("premiered"))
        self.assertIsNone(root.find("studio"))
        self.assertIsNone(root.find("set"))
        self.assertIsNone(root.find("fanart"))


if __name__ == "__main__":
    unittest.main()
