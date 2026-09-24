import PyPDF2
import os

pdf_path = "TigerGraph Agentic Fraud Investigation HHGOA.pdf"
output_file = "fraud_rules.txt"

print(f"Extracting rules from PDF...")

with open(pdf_path, "rb") as file:
    reader = PyPDF2.PdfReader(file)
    rules = ""
    for page in reader.pages:
        rules += page.extract_text() + "\n"

with open(output_file, "w", encoding="utf-8") as f:
    f.write(rules)

print(f"Done! Saved to {output_file}")
