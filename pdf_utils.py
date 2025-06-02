import fitz   # PyMuPDF
import re, os, requests
from collections import Counter

# ----------------------------------------------------------------------
# 0.  ---  PRONUNCIATION SUPPORT  --------------------------------------
# ----------------------------------------------------------------------

DEFAULT_PRONUNCIATION_PATH = "cmudict.txt"
CMUDICT_URLS = [
    "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict",
    "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict-0.7b",
]

def _download_cmudict(dest_path: str):
    for url in CMUDICT_URLS:
        try:
            print(f"Downloading CMU Pronouncing Dictionary … ({url})")
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(resp.content)
            return
        except Exception as e:
            print(f"  ↳ failed: {e}")
    print("⚠ All download attempts failed. Pronunciations will be skipped.")

def load_pronunciations(pron_path: str = DEFAULT_PRONUNCIATION_PATH):
    if not os.path.isfile(pron_path):
        _download_cmudict(pron_path)

    pron_map = {}
    if not os.path.isfile(pron_path):
        return pron_map

    with open(pron_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith(";;;") or not line.strip():
                continue
            parts = line.strip().split()
            word = re.sub(r"\(\d+\)$", "", parts[0].lower())  # WORD(2) → WORD
            pron_map.setdefault(word, []).append(" ".join(parts[1:]))
    return {w: " | ".join(p) for w, p in pron_map.items()}

# ----------------------------------------------------------------------
# 1.  ---  PDF CLEAN-UP PIPELINE  --------------------------------------
# ----------------------------------------------------------------------

def deduplicate_text(text):
    def fix_word(word):
        if re.fullmatch(r"((\w)\2)+", word, flags=re.IGNORECASE):
            return re.sub(r"(.)\1", r"\1", word)
        return word

    words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    cleaned = [fix_word(w) for w in words]
    joined = "".join(
        w if re.fullmatch(r"[^\w\s]", w) else f" {w}" for w in cleaned
    ).strip()
    return joined.replace("[[", "\n\n[[")

def pdf_to_text_cleaned(pdf_path):
    if not os.path.isfile(pdf_path):
        print(f"Error: File not found — {pdf_path}")
        return ""
    try:
        doc = fitz.open(pdf_path)
        full_text = "".join(deduplicate_text(p.get_text()) + "\n\n" for p in doc)
        doc.close()
        return full_text
    except Exception as e:
        print(f"Error processing PDF: {e}")
        return ""

# ----------------------------------------------------------------------
# 2.  ---  WORD ANALYSIS & OUTPUT  -------------------------------------
# ----------------------------------------------------------------------

def load_dictionary(dictionary_path):
    if not os.path.isfile(dictionary_path):
        print(f"Error: Dictionary file not found — {dictionary_path}")
        return set()
    with open(dictionary_path, "r", encoding="utf-8") as f:
        return {w.strip().lower() for w in f if w.strip()}

def is_all_doubled(word):
    return re.fullmatch(r"(..)+", word) and all(
        word[i] == word[i + 1] for i in range(0, len(word) - 1, 2)
    )

def extract_non_dictionary_words(
    text,
    dictionary_path,
    output_txt_path,
    frequency_path="en_full.txt",
    pronunciation_path=DEFAULT_PRONUNCIATION_PATH,
    extra_pronunciations=None,          # ← NEW
):
    dictionary     = load_dictionary(dictionary_path)
    pronunciations = load_pronunciations(pronunciation_path)

    # merge/override with Sheet-supplied pronunciations
    if extra_pronunciations:
        pronunciations.update({k.lower(): v for k, v in extra_pronunciations.items()})

    # optional word-frequency lookup
    freq_map = {}
    if os.path.isfile(frequency_path):
        with open(frequency_path, "r", encoding="utf-8") as f:
            for line in f:
                w, *rest = line.strip().split()
                if rest and rest[0].isdigit():
                    freq_map[w.lower()] = int(rest[0])

    paragraphs        = text.split("\n\n")
    word_origins      = {}
    seen_words        = set()
    word_counter      = Counter()
    long_words        = set()
    current_section   = None
    duplicate_pattern = re.compile(r"^((\w)\2{2,})+$", re.IGNORECASE)

    for para in paragraphs:
        hdr = re.search(r"\[\[?\s*([^\[\]]+?)\s*\]?\]", para.lower())
        if hdr:
            lbl = hdr.group(1)
            current_section = "pkg" if "pkg" in lbl else "anchor" if "anchor" in lbl else None

        for word in re.findall(r"\b[a-zA-Z]+\b", para):
            w = word.lower()
            word_counter[w] += 1
            if len(w) >= 12:
                long_words.add(w)
            if (
                w in dictionary or w in seen_words or is_all_doubled(w)
                or duplicate_pattern.fullmatch(w)
            ):
                continue
            seen_words.add(w)
            word_origins[w] = current_section

    annotate = lambda w: f"{w}  —  {pronunciations[w]}" if w in pronunciations else w

    with open(output_txt_path, "w", encoding="utf-8") as f:
        # 2-A  unfamiliar
        f.write("non-dictionary words\n")
        for w in sorted(word_origins):
            tag = " (pkg?)" if word_origins[w] == "pkg" else ""
            f.write(f"{annotate(w)}{tag}\n")

        # 2-B  infrequent
        f.write("\n\ninfrequent words (<4 occurrences)\n")
        rare = sorted(
            ((w, c) for w, c in word_counter.items() if w in dictionary and c < 4),
            key=lambda x: (x[1], x[0]),
        )
        for w, c in rare:
            f.write(f"{annotate(w)}, {c}\n")

        # 2-C  long words
        f.write("\n\nlong words\n")
        for w in sorted(long_words):
            f.write(f"{annotate(w)}\n")

        # 2-D  least-frequent 150
        f.write("\n\nleast frequent 150 known words (dictionary ∩ en_full.txt)\n")
        ranked = [
            (freq_map[w], w) for w in word_counter if w in dictionary and w in freq_map
        ]
        for rank, w in sorted(ranked)[:150]:
            f.write(f"{annotate(w)} (rank {rank})\n")

    print(f"{len(word_origins)} unfamiliar words written → {output_txt_path}")

