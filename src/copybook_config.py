"""Multi-book profile configuration."""
from dataclasses import dataclass
import os
from config import BASE_DIR, OUTPUT_DIR


@dataclass
class CopybookProfile:
    name: str
    pdf_path: str
    calligrapher: str
    source_text: str
    layout_direction: str = "vertical"
    pages_dir: str = ""
    cropped_dir: str = ""
    obsidian_vault: str = r"D:\notebooks\Lmc\brew"

    def __post_init__(self):
        if not self.pages_dir:
            self.pages_dir = os.path.join(OUTPUT_DIR, "pages")
        if not self.cropped_dir:
            self.cropped_dir = os.path.join(OUTPUT_DIR, "cropped")


COPYBOOK_PROFILES: dict[str, CopybookProfile] = {}


def register_profile(profile: CopybookProfile):
    COPYBOOK_PROFILES[profile.name] = profile


def get_profile(name: str) -> CopybookProfile:
    if name not in COPYBOOK_PROFILES:
        raise ValueError(f"Unknown copybook profile: {name}")
    return COPYBOOK_PROFILES[name]


def list_profiles() -> list[str]:
    return list(COPYBOOK_PROFILES.keys())


from config import PDF_PATH, CALLIGRAPHER, SOURCE_TEXT
register_profile(CopybookProfile(
    name="wys_hongloumeng",
    pdf_path=PDF_PATH,
    calligrapher=CALLIGRAPHER,
    source_text=SOURCE_TEXT,
))
