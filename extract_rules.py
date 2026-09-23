import PyPDF2

pdf_path = r"C:\Users\khann\.gemini\antigravity-ide\brain\b8687f02-95f5-4011-8161-68c87ffd03b1\.tempmediaStorage\media_1789898966134.pdf"
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
