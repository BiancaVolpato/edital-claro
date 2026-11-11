"""Build the mixed text/scanned sample used by the OCR tests.

Takes pages 3 to 5 of a real edital and replaces the middle one with a picture
of itself, which is what a scanned page looks like to a PDF reader: an image
with no text layer. The original text of that page stays available in the
source file, so tests can check what OCR recovers.

Run from the backend folder:
    uv run python ../data/samples/build_ocr_sample.py
"""

from pathlib import Path

import pymupdf

SAMPLES = Path(__file__).resolve().parent
SOURCE = SAMPLES / "lauro_muller_cc_233_2026.pdf"
TARGET = SAMPLES / "lauro_muller_cc_233_2026_ocr_misto.pdf"

FIRST_PAGE = 3  # 1-based, inclusive
LAST_PAGE = 5
SCANNED_PAGE = 4
SCAN_DPI = 200


def main() -> None:
    with pymupdf.open(SOURCE) as source, pymupdf.open() as target:
        for number in range(FIRST_PAGE, LAST_PAGE + 1):
            page = source[number - 1]
            if number != SCANNED_PAGE:
                target.insert_pdf(source, from_page=number - 1, to_page=number - 1)
                continue
            picture = page.get_pixmap(dpi=SCAN_DPI, colorspace=pymupdf.csGRAY)
            scanned = target.new_page(width=page.rect.width, height=page.rect.height)
            scanned.insert_image(scanned.rect, stream=picture.tobytes("jpg", jpg_quality=70))
        target.save(TARGET, garbage=4, deflate=True)
    print(f"wrote {TARGET.name} ({TARGET.stat().st_size / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
