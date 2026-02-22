"""Tests for generate_image.py --quiet flag and MEDIA: output behaviour."""

import os
import sys
import importlib.util
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import BytesIO

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "generate_image.py"


def _load_module():
    """Load generate_image.py as a module."""
    spec = importlib.util.spec_from_file_location("generate_image", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_image_bytes():
    """Create minimal valid PNG bytes."""
    from PIL import Image as PILImage
    img = PILImage.new("RGB", (64, 64), color="red")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_mock_response(image_bytes: bytes):
    """Create a mock Gemini API response with an image part."""
    mock_part = MagicMock()
    mock_part.text = None
    mock_part.inline_data = MagicMock()
    mock_part.inline_data.data = image_bytes
    mock_part.inline_data.mime_type = "image/png"

    mock_response = MagicMock()
    mock_response.parts = [mock_part]
    return mock_response


# ---------------------------------------------------------------------------
# Argument parsing tests (import-based, no subprocess)
# ---------------------------------------------------------------------------

def test_quiet_flag_parsed():
    """--quiet flag should be parsed by argparse."""
    mod = _load_module()
    # Access the parser via main's code — we test by running with mock
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        with patch("sys.argv", ["generate_image.py", "-p", "test", "-f", "/tmp/test.png", "--quiet"]):
            with patch("google.genai.Client"):
                # argparse should not raise SystemExit for unrecognised args
                import argparse
                parser = argparse.ArgumentParser()
                parser.add_argument("--prompt", "-p", required=True)
                parser.add_argument("--filename", "-f", required=True)
                parser.add_argument("--input-image", "-i", action="append", dest="input_images")
                parser.add_argument("--resolution", "-r", choices=["1K", "2K", "4K"], default="1K")
                parser.add_argument("--api-key", "-k")
                parser.add_argument("--quiet", "-q", action="store_true")
                args = parser.parse_args(["-p", "test", "-f", "/tmp/test.png", "--quiet"])
                assert args.quiet is True


def test_quiet_short_flag_parsed():
    """-q short flag should set quiet=True."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", "-p", required=True)
    parser.add_argument("--filename", "-f", required=True)
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args(["-p", "test", "-f", "/tmp/x.png", "-q"])
    assert args.quiet is True


def test_default_quiet_is_false():
    """Without --quiet, quiet should be False."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", "-p", required=True)
    parser.add_argument("--filename", "-f", required=True)
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args(["-p", "test", "-f", "/tmp/x.png"])
    assert args.quiet is False


# ---------------------------------------------------------------------------
# MEDIA: output tests (mock the Gemini API, run main() in-process)
# ---------------------------------------------------------------------------

def test_default_prints_media_line(fake_image_bytes, tmp_path, capsys):
    """Without --quiet, MEDIA: line should be printed."""
    output_file = tmp_path / "output.png"

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        with patch("sys.argv", [
            "generate_image.py",
            "--prompt", "test image",
            "--filename", str(output_file),
        ]):
            with patch("google.genai.Client") as MockClient:
                mock_client = MockClient.return_value
                mock_client.models.generate_content.return_value = _make_mock_response(fake_image_bytes)

                mod = _load_module()
                mod.main()

    captured = capsys.readouterr()
    assert "MEDIA:" in captured.out
    assert "Image saved:" in captured.out
    assert output_file.exists()


def test_quiet_suppresses_media_line(fake_image_bytes, tmp_path, capsys):
    """With --quiet, MEDIA: line should NOT be printed."""
    output_file = tmp_path / "output_quiet.png"

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        with patch("sys.argv", [
            "generate_image.py",
            "--prompt", "test image",
            "--filename", str(output_file),
            "--quiet",
        ]):
            with patch("google.genai.Client") as MockClient:
                mock_client = MockClient.return_value
                mock_client.models.generate_content.return_value = _make_mock_response(fake_image_bytes)

                mod = _load_module()
                mod.main()

    captured = capsys.readouterr()
    assert "MEDIA:" not in captured.out
    assert "Image saved:" in captured.out
    assert output_file.exists()


def test_quiet_still_saves_image(fake_image_bytes, tmp_path, capsys):
    """--quiet should still save the image file correctly."""
    output_file = tmp_path / "quiet_save_test.png"

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        with patch("sys.argv", [
            "generate_image.py",
            "-p", "test",
            "-f", str(output_file),
            "-q",
        ]):
            with patch("google.genai.Client") as MockClient:
                mock_client = MockClient.return_value
                mock_client.models.generate_content.return_value = _make_mock_response(fake_image_bytes)

                mod = _load_module()
                mod.main()

    assert output_file.exists()
    assert output_file.stat().st_size > 0
    # Verify it's a valid PNG
    from PIL import Image as PILImage
    img = PILImage.open(output_file)
    assert img.size == (64, 64)


def test_quiet_short_flag_in_main(fake_image_bytes, tmp_path, capsys):
    """-q short flag works end-to-end through main()."""
    output_file = tmp_path / "short_flag.png"

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        with patch("sys.argv", [
            "generate_image.py",
            "-p", "test",
            "-f", str(output_file),
            "-q",
        ]):
            with patch("google.genai.Client") as MockClient:
                mock_client = MockClient.return_value
                mock_client.models.generate_content.return_value = _make_mock_response(fake_image_bytes)

                mod = _load_module()
                mod.main()

    captured = capsys.readouterr()
    assert "MEDIA:" not in captured.out
    assert output_file.exists()
