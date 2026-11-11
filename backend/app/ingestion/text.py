"""Text of a PDF page."""

import pymupdf

# PyMuPDF's default extraction drops characters it considers outside the media
# box. Some PDFs (e.g. the Palhoça sample) have visible text that this test
# rejects: the default lost 53% of that file. Clipping to the page rectangle
# instead keeps every visible character and still excludes text placed off-page.
_TEXT_FLAGS = pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_MEDIABOX_CLIP


def page_text(page: pymupdf.Page) -> str:
    """Text of a page as a reader sees it."""
    return str(page.get_text(flags=_TEXT_FLAGS, clip=page.rect))
