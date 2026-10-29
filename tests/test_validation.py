import pytest

from app.config import Settings
from app.validation import InvalidInquiryError, clean_inquiry

S = Settings(min_inquiry_chars=20, max_inquiry_chars=100)  # small limits for easy testing


def test_valid_inquiry_is_returned_clean():
    raw = "  We need   a booking app\x00 for our salon.  "
    assert clean_inquiry(raw, S) == "We need a booking app for our salon."


@pytest.mark.parametrize("bad", ["", "   ", "\n\n\t"])
def test_empty_rejected(bad):
    with pytest.raises(InvalidInquiryError, match="empty"):
        clean_inquiry(bad, S)


def test_too_short_rejected():
    with pytest.raises(InvalidInquiryError, match="too short"):
        clean_inquiry("need app", S)


def test_too_long_rejected():
    with pytest.raises(InvalidInquiryError, match="too long"):
        clean_inquiry("a" * 101, S)


def test_non_text_rejected():
    for bad in (None, 123, ["list"]):
        with pytest.raises(InvalidInquiryError, match="must be text"):
            clean_inquiry(bad, S)


def test_symbol_only_rejected():
    with pytest.raises(InvalidInquiryError, match="text description"):
        clean_inquiry("!!!! ???? 1234 5678 #### ====", S)
