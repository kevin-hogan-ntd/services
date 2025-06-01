import fitz  # PyMuPDF
import re, os, requests
from collections import Counter

# ----------------------------------------------------------------------
# 0.  ---  PRONUNCIATION SUPPORT  --------------------------------------
# ----------------------------------------------------------------------

DEFAULT_PRONUNCIATION_PATH = "cmudict.txt"
# CMUdict is now published under the shorter name `cmudict.dict`.
# We try the new URL first; if it 404s we fall back to the old file name.
CMUDICT_URLS = [
    "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict",
    "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict-0.7b",
]


def _download_cmudict(dest_path: str):
    """Fetch CMUdict once if it is missing (tries both current & legacy URLs)."""
    for url in CMUDICT_URLS:
        try:
            print(f"Downloading CMU Pronouncing Dictionary … ({url})")
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(resp.content)
            return            # success → stop trying
        except Exception as e:
            print(f"  ↳ failed: {e}")
    print("⚠ All download attempts failed. Pronunciations will be skipped.")


def load_pronunciations(pron_path: str = DEFAULT_PRONUNCIATION_PATH):
    """
    Returns dict[word_lower] = "ARPABET PHONES ..."
    Automatically downloads CMUdict the first time if necessary.
    """
    if not os.path.isfile(pron_path):
        _download_cmudict(pron_path)

    pron_map = {}
    if not os.path.isfile(pron_path):
        return pron_map  # graceful fallback

    with open(pron_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith(";;;") or not line.strip():
                continue
            parts = line.strip().split()
            word = parts[0].lower()
            # Remove variant tags like WORD(2)
            word = re.sub(r"\(\d+\)$", "", word)
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
    cleaned_words = [fix_word(w) for w in words]
    joined = "".join(
        [w if re.fullmatch(r"[^\w\s]", w) else f" {w}" for w in cleaned_words]
    ).strip()
    return joined.replace("[[", "\n\n[[")

def pdf_to_text_cleaned(pdf_path):
    if not os.path.isfile(pdf_path):
        print(f"Error: File not found — {pdf_path}")
        return ""
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += deduplicate_text(page.get_text()) + "\n\n"
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
):
    dictionary     = load_dictionary(dictionary_path)
    pronunciations = load_pronunciations(pronunciation_path)

    # -- (optional) frequency lookup for "least-frequent" section --
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
        # track section headers like [[pkg]]
        section_match = re.search(r"\[\[?\s*([^\[\]]+?)\s*\]?\]", para.lower())
        if section_match:
            label = section_match.group(1)
            current_section = "pkg" if "pkg" in label else "anchor" if "anchor" in label else None

        for word in re.findall(r"\b[a-zA-Z]+\b", para):
            w = word.lower()
            word_counter[w] += 1
            if len(w) >= 12:
                long_words.add(w)
            if (
                w in dictionary
                or w in seen_words
                or is_all_doubled(w)
                or duplicate_pattern.fullmatch(w)
            ):
                continue
            seen_words.add(w)
            word_origins[w] = current_section

    # helper to append pronunciation when we have it
    annotate = lambda w: f"{w}  —  {pronunciations[w]}" if w in pronunciations else w

    with open(output_txt_path, "w", encoding="utf-8") as f:
        # 2-A  Unfamiliar words
        f.write("non-dictionary words\n")
        for w in sorted(word_origins):
            tag = " (pkg?)" if word_origins[w] == "pkg" else ""
            f.write(f"{annotate(w)}{tag}\n")

        # 2-B  Infrequent dictionary words
        f.write("\n\ninfrequent words (<4 occurrences)\n")
        infreq = sorted(
            ((w, c) for w, c in word_counter.items() if w in dictionary and c < 4),
            key=lambda x: (x[1], x[0]),
        )
        for w, c in infreq:
            f.write(f"{annotate(w)}, {c}\n")

        # 2-C  Long words (12+ letters)
        f.write("\n\nlong words\n")
        for w in sorted(long_words):
            f.write(f"{annotate(w)}\n")

        # 2-D  Least-frequent 150 known words
        f.write("\n\nleast frequent 150 known words (from dictionary & en_full.txt)\n")
        ranked = [
            (freq_map[w], w)
            for w in word_counter
            if w in dictionary and w in freq_map
        ]
        for rank, w in sorted(ranked)[:150]:
            f.write(f"{annotate(w)} (rank {rank})\n")

    print(f"{len(word_origins)} unfamiliar words written → {output_txt_path}")

