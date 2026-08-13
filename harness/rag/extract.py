"""Text extraction with no third-party dependencies.

Drop a publication into corpus/ and this pulls the words out of it. Formats:

  .txt .md .csv     read directly
  .html .htm        tags stripped
  .docx .pptx       unzipped and parsed from the office XML
  .pdf              pypdf if it happens to be installed, otherwise a built-in
                    extractor that handles the common case of a text-based PDF

The built-in PDF path handles digitally generated publications (which is what
Army doctrine PDFs are). It cannot read a scanned page — that needs OCR. If a
PDF yields almost nothing, the ingest tool says so rather than silently
indexing an empty document.
"""

import io
import os
import re
import zipfile
import zlib


def extract(path):
    """Return (text, note). `note` is a human-readable caveat or ''. """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml",
               ".yml", ".log"):
        return _read_text(path), ""
    if ext in (".html", ".htm", ".xhtml"):
        return _strip_html(_read_text(path)), ""
    if ext == ".docx":
        return _docx(path), ""
    if ext == ".pptx":
        return _pptx(path), ""
    if ext == ".pdf":
        return _pdf(path)
    return "", "unsupported file type %s" % ext


def _read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _strip_html(html):
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = (html.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"[ \t]{2,}", " ", html)


# ------------------------------------------------------------ office xml --

def _office_xml_text(xml):
    # Paragraph and line breaks become newlines so structure survives.
    xml = re.sub(r"</w:p>|</a:p>", "\n", xml)
    xml = re.sub(r"<w:br[^>]*/>|<a:br[^>]*/>", "\n", xml)
    xml = re.sub(r"</w:tr>", "\n", xml)
    xml = re.sub(r"</w:tc>|</a:tc>", "\t", xml)
    xml = re.sub(r"(?s)<[^>]+>", "", xml)
    xml = (xml.replace("&amp;", "&").replace("&lt;", "<")
              .replace("&gt;", ">").replace("&quot;", '"')
              .replace("&apos;", "'"))
    return re.sub(r"\n{3,}", "\n\n", xml)


def _docx(path):
    out = []
    with zipfile.ZipFile(path) as z:
        names = ["word/document.xml"]
        names += sorted(n for n in z.namelist()
                        if re.match(r"word/(header|footer)\d*\.xml$", n))
        for name in names:
            try:
                out.append(_office_xml_text(z.read(name).decode("utf-8",
                                                                "replace")))
            except KeyError:
                continue
    return "\n".join(out)


def _pptx(path):
    out = []
    with zipfile.ZipFile(path) as z:
        slides = sorted(
            (n for n in z.namelist()
             if re.match(r"ppt/slides/slide\d+\.xml$", n)),
            key=lambda s: int(re.search(r"(\d+)", s).group(1)))
        for i, name in enumerate(slides, 1):
            text = _office_xml_text(z.read(name).decode("utf-8", "replace"))
            out.append("--- Slide %d ---\n%s" % (i, text))
    return "\n\n".join(out)


# ------------------------------------------------------------------- pdf --

def _pdf(path):
    try:
        import pypdf  # optional; better fidelity when present
        reader = pypdf.PdfReader(path)
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        if text.strip():
            return text, ""
    except ImportError:
        pass
    except Exception:
        pass

    text = _pdf_builtin(path)
    words = len(re.findall(r"[A-Za-z]{3,}", text))
    if words < 50:
        return text, ("almost no text recovered — this is probably a scanned "
                      "PDF. Run it through OCR, or `pip install pypdf` for "
                      "better extraction of generated PDFs.")
    return text, ""


_TEXT_OP = re.compile(rb"(?s)BT(.*?)ET")
_SHOW = re.compile(rb"(?s)(\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>)\s*(Tj|TJ|'|\")")
_ARRAY = re.compile(rb"(?s)\[(.*?)\]\s*TJ")
_STR_IN_ARRAY = re.compile(rb"(?s)\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>")
_TD = re.compile(rb"(T\*|Td|TD|TL)")

_ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b",
            b"f": b"\f", b"(": b"(", b")": b")", b"\\": b"\\"}


def _decode_pdf_string(raw):
    if raw.startswith(b"<"):
        hexdigits = re.sub(rb"[^0-9A-Fa-f]", b"", raw[1:-1])
        if len(hexdigits) % 2:
            hexdigits += b"0"
        try:
            data = bytes.fromhex(hexdigits.decode("ascii"))
        except ValueError:
            return ""
        return _maybe_utf16(data)
    body = raw[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        ch = body[i:i + 1]
        if ch == b"\\" and i + 1 < len(body):
            nxt = body[i + 1:i + 2]
            if nxt in _ESCAPES:
                out += _ESCAPES[nxt]
                i += 2
                continue
            if nxt.isdigit():
                octal = body[i + 1:i + 4]
                octal = octal[:len(re.match(rb"[0-7]*", octal).group(0))]
                try:
                    out.append(int(octal, 8) & 0xFF)
                except ValueError:
                    pass
                i += 1 + len(octal)
                continue
            if nxt == b"\n":
                i += 2
                continue
            out += nxt
            i += 2
            continue
        out += ch
        i += 1
    return _maybe_utf16(bytes(out))


def _maybe_utf16(data):
    if data[:2] in (b"\xfe\xff", b"\xff\xfe"):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1", "replace")


def _pdf_builtin(path):
    with open(path, "rb") as fh:
        data = fh.read()

    pieces = []
    for match in re.finditer(rb"stream\r?\n", data):
        start = match.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        blob = data[start:end]
        text = None
        try:
            text = zlib.decompress(blob)
        except zlib.error:
            try:
                text = zlib.decompressobj().decompress(blob)
            except zlib.error:
                # Uncompressed content streams do exist.
                if b"BT" in blob and b"Tj" in blob or b"TJ" in blob:
                    text = blob
        if not text:
            continue
        pieces.append(_pdf_stream_text(text))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(p for p in pieces if p.strip()))


def _pdf_stream_text(stream):
    out = []
    for block in _TEXT_OP.findall(stream):
        line = []
        pos = 0
        for m in re.finditer(rb"(?s)(\[.*?\]\s*TJ|(?:\((?:\\.|[^\\()])*\)|"
                             rb"<[0-9A-Fa-f\s]*>)\s*(?:Tj|'|\")|T\*|Td|TD)",
                             block):
            token = m.group(0)
            if token.endswith(b"TJ") and token.startswith(b"["):
                inner = _ARRAY.match(token)
                body = inner.group(1) if inner else b""
                for s in _STR_IN_ARRAY.findall(body):
                    line.append(_decode_pdf_string(s))
            elif token in (b"T*",) or token.endswith(b"Td") or token.endswith(b"TD"):
                if line:
                    out.append("".join(line))
                    line = []
            else:
                s = _SHOW.match(token)
                if s:
                    line.append(_decode_pdf_string(s.group(1)))
            pos = m.end()
        if line:
            out.append("".join(line))
    return "\n".join(out)


def chunk(text, size=1400, overlap=200):
    """Split text into overlapping chunks on paragraph then sentence bounds."""
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= size:
            cur = (cur + "\n\n" + p).strip()
            continue
        if cur:
            chunks.append(cur)
        while len(p) > size:
            cut = p.rfind(". ", 0, size)
            if cut < size // 2:
                cut = size
            chunks.append(p[:cut + 1].strip())
            p = p[max(0, cut + 1 - overlap):].strip()
        cur = p
    if cur:
        chunks.append(cur)
    return [c for c in chunks if len(c) > 40]
