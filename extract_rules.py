import os
import re
import PyPDF2

pdf_path = "TigerGraph Agentic Fraud Investigation HHGOA.pdf"
if not os.path.exists(pdf_path):
    pdf_path = r"C:\Users\khann\.gemini\antigravity-ide\brain\b8687f02-95f5-4011-8161-68c87ffd03b1\.tempmediaStorage\media_1789898966134.pdf"

output_file = "fraud_rules.txt"

print("Extracting rules from PDF...")

with open(pdf_path, "rb") as file:
    reader = PyPDF2.PdfReader(file)
    pages = []
    for p in reader.pages:
        raw = p.extract_text()
        cleaned = re.sub(r'[\r\n]+', '\n', raw)
        lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
        pages.append(' '.join(lines))
    full_text = '\n\n'.join(pages)

with open(output_file, "w", encoding="utf-8") as f:
    f.write(full_text)

print(f"Done! Clean rules saved to {output_file}")
