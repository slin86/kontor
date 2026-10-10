from decimal import Decimal

from fastapi.testclient import TestClient

from kontor.domain import verify as vf
from tests.test_ai_api import FakeAi, _b64, _pdf, fake  # noqa: F401


def _upload(client: TestClient, path: str, text: str, **extra: object) -> object:
    return client.post(
        path,
        json={"filename": "x.pdf", "content_base64": _b64(_pdf(text)), **extra},
    )


# --------------------------------------------------------------------------------------
# verification helpers
# --------------------------------------------------------------------------------------


def test_isin_checksum() -> None:
    assert vf.isin_valid("IE00B4L5Y983")
    assert vf.isin_valid("DE000BASF111")
    assert not vf.isin_valid("IE00B4L5Y984")
    assert not vf.isin_valid("nonsense")


def test_amount_must_stand_in_the_text() -> None:
    text = "Beitrag 1.234,50 EUR, Rate 89,90 EUR, Nr. 2189,90"
    assert vf.amount_in_text(text, Decimal("1234.50"))
    assert vf.amount_in_text(text, 89.9)
    assert not vf.amount_in_text(text, Decimal("9.90"))  # only part of 89,90
    assert not vf.amount_in_text(text, Decimal("189.90"))  # only part of 2189,90
    assert vf.amount_in_text("Rate 3.5 % p.a.", Decimal("3.5"))
    assert vf.quantity_in_text("0,3456 Stück", Decimal("0.3456"))
    assert not vf.quantity_in_text("10,3456 Stück", Decimal("0.3456"))


# --------------------------------------------------------------------------------------
# contracts
# --------------------------------------------------------------------------------------


def test_contract_becomes_an_item_and_unverified_amounts_are_flagged(
    client: TestClient,
    fake: FakeAi,  # noqa: F811
) -> None:
    fake.doc_kind = "recurring_contract"
    fake.answers["contracts"] = {
        "contracts": [
            {
                "name": "Haftpflicht Muster-Versicherung",
                "amount": 89.9,
                "months": 12,
                "income": False,
                "category_id": fake.cats["Abos"],
                "reason": "Jahresbeitrag",
            },
            {
                "name": "Erfundener Posten",
                "amount": 555.55,
                "months": 1,
                "income": False,
                "category_id": 99999,
                "reason": "",
            },
            {
                "name": "Einmalig",
                "amount": 10,
                "months": 0,
                "income": False,
                "category_id": None,
                "reason": "",
            },
        ]
    }
    text = "Versicherungsschein Haftpflicht Jahresbeitrag 89,90 EUR " * 3
    r = _upload(client, "/api/ai/contracts/analyze", text)
    assert r.status_code == 200, r.text  # type: ignore[attr-defined]
    rows = r.json()["candidates"]  # type: ignore[attr-defined]
    assert [c["name"] for c in rows] == ["Haftpflicht Muster-Versicherung", "Erfundener Posten"]
    assert rows[0]["frequency"] == "yearly" and rows[0]["check"] is None
    assert rows[1]["category_id"] is None and "Text" in rows[1]["check"]


def test_wrong_document_points_to_the_right_place(client: TestClient, fake: FakeAi) -> None:  # noqa: F811
    fake.doc_kind = "broker_statement"
    r = _upload(client, "/api/ai/contracts/analyze", "Wertpapierabrechnung " * 10)
    assert r.status_code == 422 and "Depot" in r.json()["detail"]  # type: ignore[attr-defined]
    fake.doc_kind = "loan_contract"
    r = _upload(client, "/api/ai/statements/analyze", "Darlehensvertrag " * 10)
    assert r.status_code == 422 and "Finanzierungen" in r.json()["detail"]  # type: ignore[attr-defined]


def test_unsure_classification_still_tries(client: TestClient, fake: FakeAi) -> None:  # noqa: F811
    fake.doc_kind = "other"
    fake.answers["contracts"] = {"contracts": []}
    r = _upload(client, "/api/ai/contracts/analyze", "irgendein Text " * 10)
    assert r.status_code == 200 and r.json()["candidates"] == []  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------
# financings
# --------------------------------------------------------------------------------------

LOAN_FIELDS = {
    "contract": "loan",
    "name": "Baudarlehen Muster-Bank",
    "principal": 250000,
    "monthly_payment": 1100,
    "contract_sum": None,
    "monthly_saving": None,
    "fee_amount": None,
    "loan_payment": None,
    "limit": None,
    "balance": None,
    "annual_rate_percent": 3.45,
    "initial_repayment_percent": 2,
    "fee_percent": None,
    "deposit_rate_percent": None,
    "prefinance_rate_percent": None,
    "loan_rate_percent": None,
    "start": "2026-11",
    "allocation": None,
}


def test_loan_contract_prefills_the_form(client: TestClient, fake: FakeAi) -> None:  # noqa: F811
    fake.doc_kind = "loan_contract"
    fake.answers["contract"] = LOAN_FIELDS
    text = "Darlehensvertrag Nettodarlehen 250.000,00 EUR Sollzins 3,45 % Rate 1.100,00 EUR " * 2
    r = _upload(client, "/api/ai/financings/analyze", text)
    assert r.status_code == 200, r.text  # type: ignore[attr-defined]
    body = r.json()  # type: ignore[attr-defined]
    assert body["form_kind"] == "loan"
    assert body["fields"]["principal"] == "250000" and body["fields"]["start"] == "2026-11"
    assert body["fields"]["annual_rate_percent"] == "3.45"
    assert body["unverified"] == ["initial_repayment_percent"]  # "2" is not in the text


def test_bauspar_with_advance_loan_uses_the_prefinanced_form(
    client: TestClient,
    fake: FakeAi,  # noqa: F811
) -> None:
    fake.doc_kind = "building_savings_contract"
    fake.answers["contract"] = {
        **LOAN_FIELDS,
        "contract": "building_savings",
        "contract_sum": 100000,
        "prefinance_rate_percent": 3.45,
        "principal": None,
        "monthly_payment": None,
    }
    text = "Bausparvertrag Bausparsumme 100.000,00 EUR Vorfinanzierung 3,45 % " * 2
    body = _upload(client, "/api/ai/financings/analyze", text).json()  # type: ignore[attr-defined]
    assert body["form_kind"] == "prefinanced" and body["fields"]["contract_sum"] == "100000"


# --------------------------------------------------------------------------------------
# broker documents
# --------------------------------------------------------------------------------------


def _position(client: TestClient, isin: str) -> int:
    r = client.post(
        "/api/depot/instruments",
        json={
            "kind": "etf",
            "name": "MSCI World",
            "isin": isin,
            "expected_return_percent": "6",
            "cost_percent": "0.05",
            "entry_fee_percent": "0",
            "start": "2026-08",
            "start_value": "0",
            "monthly_rate": "250",
        },
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


BROKER_TEXT = (
    "Wertpapierabrechnung Kauf 05.10.2026 iShares MSCI World IE00B4L5Y983 "
    "Stück 0,3456 Betrag 100,00 EUR. Dividende 15.10.2026 IE00B4L5Y983 12,34 EUR. "
) * 2


def test_broker_pdf_preview_import_and_dedupe(client: TestClient, fake: FakeAi) -> None:  # noqa: F811
    _position(client, "IE00B4L5Y983")
    fake.doc_kind = "broker_statement"
    fake.answers["rows"] = {
        "rows": [
            {
                "date": "2026-10-05",
                "kind": "buy",
                "isin": "IE00B4L5Y983",
                "name": "iShares",
                "shares": 0.3456,
                "amount": 100,
                "fee": None,
            },
            {
                "date": "2026-10-15",
                "kind": "dividend",
                "isin": "IE00B4L5Y983",
                "name": "iShares",
                "shares": None,
                "amount": 12.34,
                "fee": None,
            },
            {
                "date": "2026-10-20",
                "kind": "buy",
                "isin": "IE00B4L5Y983",
                "name": "iShares",
                "shares": 2,
                "amount": 777,
                "fee": None,
            },
            {
                "date": "2026-10-21",
                "kind": "other",
                "isin": "",
                "name": "Zinsen",
                "shares": None,
                "amount": 1,
                "fee": None,
            },
        ]
    }
    r = _upload(client, "/api/ai/depot/analyze", BROKER_TEXT)
    assert r.status_code == 200, r.text  # type: ignore[attr-defined]
    prev = r.json()  # type: ignore[attr-defined]
    assert prev["method"] == "ai" and len(prev["rows"]) == 3 and prev["skipped"] == 1
    ok, _, bad = prev["rows"]
    assert ok["check"] is None and ok["instrument_id"] is not None
    assert "Betrag" in bad["check"] and "Stückzahl" in bad["check"]

    body = {
        "rows": [
            {
                k: v
                for k, v in x.items()
                if k in {"day", "kind", "amount", "fee", "shares", "isin", "name", "external_id"}
            }
            for x in prev["rows"][:2]
        ]
    }
    first = client.post("/api/ai/depot/import", json=body).json()
    assert first == {"imported": 2, "duplicates": 0, "unmatched": 0}
    again = client.post("/api/ai/depot/import", json=body).json()
    assert again["duplicates"] == 2 and again["imported"] == 0
    # a second preview marks them as already known
    prev2 = _upload(client, "/api/ai/depot/analyze", BROKER_TEXT).json()  # type: ignore[attr-defined]
    assert prev2["duplicate_count"] == 2


def test_unknown_isin_is_reported_not_guessed(client: TestClient, fake: FakeAi) -> None:  # noqa: F811
    fake.doc_kind = "broker_statement"
    fake.answers["rows"] = {
        "rows": [
            {
                "date": "2026-10-05",
                "kind": "buy",
                "isin": "IE00B4L5Y984",
                "name": "x",
                "shares": 0.3456,
                "amount": 100,
                "fee": None,
            },
        ]
    }
    prev = _upload(client, "/api/ai/depot/analyze", BROKER_TEXT).json()  # type: ignore[attr-defined]
    assert prev["rows"][0]["isin"] is None and "ISIN" in prev["rows"][0]["check"]
    assert prev["unmatched"][0]["count"] == 1


# --------------------------------------------------------------------------------------
# unknown CSV layouts
# --------------------------------------------------------------------------------------


def test_unknown_csv_columns_are_mapped_by_the_ai(client: TestClient, fake: FakeAi) -> None:  # noqa: F811
    fake.answers["header_row"] = {
        "header_row": 0,
        "date": 0,
        "amount": 2,
        "debit": None,
        "credit": None,
        "counterparty": 1,
        "purpose": 3,
    }
    csv = "Tag;Wer;Summe;Info\n05.08.2026;Netflix;-12,99;Abo\n05.09.2026;Netflix;-12,99;Abo\n"
    r = client.post(
        "/api/ai/statements/analyze",
        json={"filename": "x.csv", "content_base64": _b64(csv)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["lines"] == 2 and r.json()["candidates"][0]["name"] == "Netflix"
    # nonsense columns are refused instead of producing garbage
    fake.answers["header_row"]["date"] = 9
    r = client.post(
        "/api/ai/statements/analyze",
        json={"filename": "x.csv", "content_base64": _b64(csv)},
    )
    assert r.status_code == 422
