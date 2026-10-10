"""Reading uploaded documents: text out of PDFs and text files, and what kind of document it is.

Only text goes to the AI server, never the file. Scanned PDFs without a text layer are refused.
"""

import io
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from kontor.services import ai

PDF_CHUNK_CHARS = 6000

KINDS = (
    "bank_statement",
    "broker_statement",
    "loan_contract",
    "building_savings_contract",
    "credit_line_contract",
    "recurring_contract",
    "other",
)

# where the user finds the right import for each kind
WHERE: dict[str, str] = {
    "bank_statement": "Das ist ein Kontoauszug. Lade ihn unter Cashflow / Posten / „Aus Kontoauszug“ hoch.",  # noqa: E501
    "broker_statement": "Das ist eine Broker-Abrechnung. Lade sie unter Depot / Ist-Daten hoch.",
    "loan_contract": "Das ist ein Darlehensvertrag. Lade ihn unter Finanzierungen / „Aus Vertrag“ hoch.",  # noqa: E501
    "building_savings_contract": "Das ist ein Bausparvertrag. Lade ihn unter Finanzierungen / „Aus Vertrag“ hoch.",  # noqa: E501
    "credit_line_contract": "Das ist ein Rahmenkredit. Lade ihn unter Finanzierungen / „Aus Vertrag“ hoch.",  # noqa: E501
    "recurring_contract": "Das ist ein Vertrag mit regelmäßigen Zahlungen. Lade ihn unter Cashflow / Posten / „Aus Dokument“ hoch.",  # noqa: E501
}

KIND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"kind": {"type": "string", "enum": list(KINDS)}},
    "required": ["kind"],
    "additionalProperties": False,
}


class DocumentError(ValueError):
    """The document cannot be used here; the message says why and where it belongs."""


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def pdf_pages(raw: bytes) -> list[str]:
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise DocumentError("Das PDF ist passwortgeschützt.")
        pages = [(p.extract_text() or "").strip() for p in reader.pages]
    except PyPdfError as exc:
        raise DocumentError("Das PDF ist nicht lesbar.") from exc
    if sum(len(p) for p in pages) < 80:
        raise DocumentError(
            "Das PDF enthält keinen Text (vermutlich ein Scan). Lade stattdessen eine Datei mit "
            "Text hoch, bei Kontoauszügen die CSV- oder CAMT-Datei deiner Bank."
        )
    return pages


def document_text(raw: bytes) -> str:
    if raw[:5] == b"%PDF-":
        return "\n".join(pdf_pages(raw))
    return decode_text(raw)


def chunks(text: str, size: int = PDF_CHUNK_CHARS) -> list[str]:
    """Pieces that fit a small context window, cut at line breaks."""
    out: list[str] = []
    current = ""
    for line in text.splitlines():
        if current and len(current) + len(line) > size:
            out.append(current)
            current = ""
        current += line[:size] + "\n"
    if current.strip():
        out.append(current)
    return out


def detect_kind(text: str) -> str:
    system = (
        "Du ordnest ein Dokument ein. bank_statement: Kontoauszug oder Umsatzliste einer Bank "
        "oder Kreditkarte. broker_statement: Wertpapierabrechnung, Depotauszug, Orderliste, "
        "Dividendenabrechnung. loan_contract: Darlehens- oder Kreditvertrag mit Zins und Rate. "
        "building_savings_contract: Bausparvertrag. credit_line_contract: Rahmenkredit, "
        "Dispo, Kreditkarte mit Rahmen. recurring_contract: Vertrag mit regelmäßigen Zahlungen "
        "(Versicherung, Strom, Gas, Internet, Mobilfunk, Miete, Kita, Fitnessstudio, Abo). "
        "other: alles andere."
    )
    answer = ai.complete_json(system, text[:3000], KIND_SCHEMA, allow_cloud=False)
    kind = answer.data.get("kind")
    return kind if kind in KINDS else "other"


def require_kind(text: str, accepted: set[str]) -> None:
    """Refuse a document that clearly belongs to another import, and say where it goes.

    "other" passes: the model is unsure, and an empty result is a better answer than a refusal.
    """
    kind = detect_kind(text)
    if kind != "other" and kind not in accepted:
        raise DocumentError(WHERE[kind])
