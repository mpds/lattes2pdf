"""Presentation adjustments shared by browser exports and their previews."""


def apply_browser_typography(design):
    if design["theme"] == "moderncv":
        design.setdefault("typography", {})["font_family"] = "XCharter"
