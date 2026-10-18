import io

import pytest
from PIL import Image, ImageCms

from conftest import fake_decoder, make_fake_arw
from core.converter import compute_output_size, convert_file
from core.errors import CancelledError, DecodeError, ValidationError
from models.conversion_job import ResizeMode, ResizeSettings


@pytest.mark.parametrize("rs,expected", [
    (ResizeSettings(), (6000, 4000)),
    (ResizeSettings(mode=ResizeMode.PERCENT, percent=50), (3000, 2000)),
    (ResizeSettings(mode=ResizeMode.PERCENT, percent=200), (6000, 4000)),   # no upscale
    (ResizeSettings(mode=ResizeMode.PERCENT, percent=200, allow_upscale=True), (12000, 8000)),
    (ResizeSettings(mode=ResizeMode.MAX_DIMENSIONS, max_width=1920, max_height=1920), (1920, 1280)),
    (ResizeSettings(mode=ResizeMode.MAX_DIMENSIONS, max_width=10000, max_height=10000), (6000, 4000)),
])
def test_resize_preserves_aspect_and_never_upscales(rs, expected):
    assert compute_output_size(6000, 4000, rs) == expected


@pytest.mark.parametrize("rs", [
    ResizeSettings(mode=ResizeMode.PERCENT, percent=0),
    ResizeSettings(mode=ResizeMode.MAX_DIMENSIONS, max_width=0, max_height=100),
])
def test_resize_validation(rs):
    with pytest.raises(ValidationError):
        compute_output_size(6000, 4000, rs)


def test_single_file_conversion(tmp_path, settings):
    src = make_fake_arw(tmp_path / "DSC00001.ARW")
    before = src.read_bytes()
    target = settings.output.output_dir / "DSC00001.jpg"
    size = convert_file(src, target, settings, decoder=fake_decoder)
    assert target.read_bytes()[:3] == b"\xff\xd8\xff"
    with Image.open(target) as im:
        assert im.format == "JPEG" and im.size == size == (400, 600)
    assert src.read_bytes() == before  # source untouched


def test_exif_and_icc_preserved(tmp_path, settings):
    src = make_fake_arw(tmp_path / "a.ARW")
    target = tmp_path / "a.jpg"
    convert_file(src, target, settings, decoder=fake_decoder)
    with Image.open(target) as im:
        exif = im.getexif()
        assert exif[0x010F] == "SONY" and exif[0x0110] == "ILCE-7M3"
        assert exif[0x0112] == 1  # pixels already rotated
        sub = exif.get_ifd(0x8769)
        assert sub[0x9003] == "2024:05:01 10:20:30"
        assert sub[0x8827] == 400
        assert sub[0xA434] == "FE 24-70mm F2.8 GM"
        assert float(sub[0x829D]) == pytest.approx(2.8)
        profile = ImageCms.ImageCmsProfile(io.BytesIO(im.info["icc_profile"]))
        assert "sRGB" in ImageCms.getProfileDescription(profile)


def test_metadata_can_be_disabled(tmp_path, settings):
    settings.jpeg.preserve_metadata = False
    settings.jpeg.embed_srgb_profile = False
    src = make_fake_arw(tmp_path / "a.ARW")
    convert_file(src, tmp_path / "a.jpg", settings, decoder=fake_decoder)
    with Image.open(tmp_path / "a.jpg") as im:
        assert 0x010F not in im.getexif() and "icc_profile" not in im.info


def test_quality_affects_file_size(tmp_path, settings):
    def noisy(path, rs):
        img = Image.radial_gradient("L").resize((600, 400)).convert("RGB")
        return Image.blend(img, Image.effect_noise((600, 400), 40).convert("RGB"), 0.3)
    src = make_fake_arw(tmp_path / "a.ARW")
    settings.jpeg.quality = 40
    convert_file(src, tmp_path / "low.jpg", settings, decoder=noisy)
    settings.jpeg.quality = 100
    convert_file(src, tmp_path / "high.jpg", settings, decoder=noisy)
    assert (tmp_path / "high.jpg").stat().st_size > (tmp_path / "low.jpg").stat().st_size


def test_invalid_quality_rejected(tmp_path, settings):
    settings.jpeg.quality = 0
    with pytest.raises(ValidationError):
        convert_file(make_fake_arw(tmp_path / "a.ARW"), tmp_path / "a.jpg", settings, decoder=fake_decoder)


def test_resized_output_dimensions(tmp_path, settings):
    settings.resize = ResizeSettings(mode=ResizeMode.MAX_DIMENSIONS, max_width=300, max_height=300)
    src = make_fake_arw(tmp_path / "a.ARW")
    assert convert_file(src, tmp_path / "a.jpg", settings, decoder=fake_decoder) == (200, 300)


def test_cancel_before_decode(tmp_path, settings):
    with pytest.raises(CancelledError):
        convert_file(make_fake_arw(tmp_path / "a.ARW"), tmp_path / "a.jpg", settings,
                     decoder=fake_decoder, is_cancelled=lambda: True)
    assert not (tmp_path / "a.jpg").exists()


def test_corrupted_raw_fails_cleanly_with_real_decoder(tmp_path, settings):
    """Valid TIFF header but garbage body: LibRaw must reject it, no output left behind."""
    src = tmp_path / "corrupt.ARW"
    src.write_bytes(b"II*\x00" + b"\x13" * 200_000)
    with pytest.raises((DecodeError, ValidationError)):
        convert_file(src, tmp_path / "corrupt.jpg", settings)
    assert not (tmp_path / "corrupt.jpg").exists()


def test_real_arw_conversion(tmp_path, settings, real_arw):
    """Integration test with a genuine Sony ARW (set SONY_ARW_SAMPLE)."""
    from core.raw_decoder import read_info
    info = read_info(real_arw)
    target = tmp_path / "real.jpg"
    size = convert_file(real_arw, target, settings)
    assert size == (info.width, info.height)
    with Image.open(target) as im:
        assert im.format == "JPEG" and im.size == size
        assert im.getexif().get(0x010F, "").upper().startswith("SONY")
