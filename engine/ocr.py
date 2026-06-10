# -*- coding: utf-8 -*-
"""OCR сканированных страниц через Apple Vision Framework (pyobjc).

В отличие от референсного pdf->word, извлекает не только текст строк,
но и их координаты (VNRecognizedTextObservation.boundingBox), переводя
нормализованные координаты Vision (начало в левом НИЖНЕМ углу) в систему
координат страницы PDF (начало в левом ВЕРХНЕМ углу).
"""

from typing import List, Optional

import pymupdf

from extractor import TextBlock

# Соответствие кодов языков приложения языкам распознавания Vision
VISION_LANGUAGES = {
    "en": "en-US",
    "ru": "ru-RU",
    "zh": "zh-Hans",
    "de": "de-DE",
    "fr": "fr-FR",
    "it": "it-IT",
    "es": "es-ES",
    "ja": "ja-JP",
}

_OCR_DPI = 300
# Высота bbox строки → приближённый размер шрифта (типографский коэффициент)
_FONT_SIZE_RATIO = 0.75


def ocr_page(page: "pymupdf.Page", src_lang: str = "auto") -> List[TextBlock]:
    """Распознаёт текст страницы-скана, возвращает строки с bbox в координатах PDF."""
    import Vision
    from Foundation import NSData

    mat = pymupdf.Matrix(_OCR_DPI / 72, _OCR_DPI / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csRGB)
    img_bytes = pix.tobytes("png")
    del pix  # освобождаем память сразу после получения PNG

    ns_data = NSData.dataWithBytes_length_(img_bytes, len(img_bytes))
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(ns_data, {})

    page_w, page_h = page.rect.width, page.rect.height
    blocks: List[TextBlock] = []
    ocr_error: List[str] = []

    def on_complete(request, error):
        if error is not None:
            ocr_error.append(str(error))
            return
        for obs in (request.results() or []):
            top = obs.topCandidates_(1)
            if not top or len(top) == 0:
                continue
            text = str(top[0].string()).strip()
            if not text:
                continue
            bb = obs.boundingBox()  # нормализованный rect, origin — левый нижний угол
            x0 = bb.origin.x * page_w
            x1 = (bb.origin.x + bb.size.width) * page_w
            y0 = (1.0 - bb.origin.y - bb.size.height) * page_h  # верх в PDF-координатах
            y1 = (1.0 - bb.origin.y) * page_h
            blocks.append(TextBlock(
                bbox=(x0, y0, x1, y1),
                text=text,
                font_size=max(6.0, (y1 - y0) * _FONT_SIZE_RATIO),
            ))

    req = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(on_complete)
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(True)
    vision_lang: Optional[str] = VISION_LANGUAGES.get(src_lang)
    if vision_lang:
        req.setRecognitionLanguages_([vision_lang])

    handler.performRequests_error_([req], None)

    if ocr_error:
        raise RuntimeError(f"Apple Vision OCR error: {ocr_error[0]}")

    # Сортировка сверху вниз, слева направо
    blocks.sort(key=lambda b: (round(b.bbox[1] / 8.0) * 8.0, b.bbox[0]))
    return blocks
