import pytest

from foreground import is_distracting

CFG = {
    "distracting_processes": ["Discord.exe"],
    "distracting_title_keywords": ["YouTube", "reddit", "x.com"],
}


@pytest.mark.parametrize(
    "process, title, expected",
    [
        ("discord.exe", "General", True),  # process match, case-insensitive both ways
        ("DISCORD.EXE", None, True),
        ("chrome.exe", "Funny cats - YouTube", True),  # title keyword, case-insensitive
        ("chrome.exe", "r/all - REDDIT", True),
        ("code.exe", "app.py - Visual Studio Code", False),
        (None, None, False),
        (None, "", False),
    ],
)
def test_is_distracting(process, title, expected):
    assert is_distracting(process, title, CFG) is expected


def test_empty_config_never_flags_anything():
    assert is_distracting("discord.exe", "youtube", {}) is False
