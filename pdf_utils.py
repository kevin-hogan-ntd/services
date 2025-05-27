import fitz  # PyMuPDF
import re
import os
from collections import Counter

# === STEP 1: Clean PDF text ===
def deduplicate_text(text):
    def fix_word(word):
        if re.fullmatch(r'((\w)\2)+', word, flags=re.IGNORECASE):
            return re.sub(r'(.)\1', r'\1', word)
        return word

    words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    cleaned_words = [fix_word(word) for word in words]
    output = ''.join([w if re.fullmatch(r'[^\w\s]', w) else f' {w}' for w in cleaned_words]).strip()
    output = output.replace('[[', '\n\n[[')
    return output

def pdf_to_text_cleaned(pdf_path):
    if not os.path.isfile(pdf_path):
        print(f"Error: File not found — {pdf_path}")
        return ""
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            raw_text = page.get_text()
            cleaned_text = deduplicate_text(raw_text)
            full_text += cleaned_text + "\n\n"
        doc.close()
        return full_text
    except Exception as e:
        print(f"Error processing PDF: {e}")
        return ""

# === STEP 2: Dictionary comparison with enhancements ===
def load_dictionary(dictionary_path):
    if not os.path.isfile(dictionary_path):
        print(f"Error: Dictionary file not found — {dictionary_path}")
        return set()
    with open(dictionary_path, "r", encoding="utf-8") as f:
        return set(word.strip().lower() for word in f if word.strip())

def is_all_doubled(word):
    return re.fullmatch(r'(..)+', word) and all(word[i] == word[i+1] for i in range(0, len(word)-1, 2))

def extract_non_dictionary_words(text, dictionary_path, output_txt_path):
    dictionary = load_dictionary(dictionary_path)
    paragraphs = text.split('\n\n')
    word_first_seen = []
    word_counter = Counter()
    long_words = []
    word_seen_set = set()
    long_word_set = set()
    non_dict_set = set()
    non_dict_info = {}

    current_section = None
    duplicate_pattern = re.compile(r'^((\w)\2{2,})+$', re.IGNORECASE)

    for para in paragraphs:
        para_lower = para.lower()
        section_match = re.search(r'\[\[?\s*([^\[\]]+?)\s*\]?\]', para_lower)
        if section_match:
            section_text = section_match.group(1)
            if 'pkg' in section_text.lower():
                current_section = 'pkg'
            elif 'anchor' in section_text.lower():
                current_section = 'anchor'

        words = re.findall(r"\b[a-zA-Z]+\b", para)
        for word in words:
            w = word.lower()
            if w not in word_seen_set:
                word_first_seen.append(w)
                word_seen_set.add(w)
            word_counter[w] += 1

            if len(w) >= 12 and w not in long_word_set:
                long_words.append(w)
                long_word_set.add(w)

            if (
                w not in dictionary and
                w not in non_dict_set and
                not is_all_doubled(w) and
                not duplicate_pattern.fullmatch(w)
            ):
                non_dict_info[w] = current_section
                non_dict_set.add(w)

    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write("non-dictionary words\n")
        for word in word_first_seen:
            if word in non_dict_info:
                tag = " (pkg?)" if non_dict_info[word] == 'pkg' else ""
                f.write(f"{word}{tag}\n")

        f.write("\n\ninfrequent words\n")
        for freq in [1, 2, 3]:
            for word in word_first_seen:
                if word in dictionary and word_counter[word] == freq:
                    f.write(f"{word}, {freq}\n")

        f.write("\n\nlong words\n")
        for word in word_first_seen:
            if word in long_word_set:
                f.write(f"{word}\n")

    print(f"{len(non_dict_set)} unfamiliar words written to: {output_txt_path}")

