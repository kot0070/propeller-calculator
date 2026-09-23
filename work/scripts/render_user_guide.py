from __future__ import annotations

from pathlib import Path
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[2]
pdf_path = ROOT / "work" / "deliverables" / "Propeller_Calculator_v3_Інструкція_UA.pdf"
output = ROOT / "work" / "pdf_qa" / "guide_v3_3"
output.mkdir(parents=True, exist_ok=True)
document = pdfium.PdfDocument(pdf_path)
for index in range(len(document)):
    page = document[index]
    image = page.render(scale=1.35).to_pil()
    image.save(output / f"page-{index + 1:02d}.png")
print(f"pages={len(document)}")
