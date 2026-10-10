from datetime import date
from decimal import Decimal

import pytest

from kontor.domain import statements as st

CSV = """Girokonto;DE00 1234
Buchungstag;Valuta;Name Zahlungsbeteiligter;Verwendungszweck;Betrag
05.08.2026;05.08.2026;Netflix International B.V.;Abo 1234;-12,99
05.09.2026;05.09.2026;Netflix International B.V.;Abo 5678;-12,99
05.10.2026;05.10.2026;Netflix International B.V.;Abo 9;-12,99
01.10.2026;01.10.2026;Shell Tankstelle 4711;Karte;-61,20
01.09.2026;01.09.2026;Arbeitgeber GmbH;Gehalt;3.100,00
01.10.2026;01.10.2026;Arbeitgeber GmbH;Gehalt;3.100,00
15.08.2026;15.08.2026;Stadtwerke;Abschlag;-80,00
15.09.2026;15.09.2026;Stadtwerke;Abschlag;-84,00
"""

CAMT = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:camt.053.001.02"><BkToCstmrStmt><Stmt>
<Ntry><Amt Ccy="EUR">12.99</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-09-05</Dt></BookgDt>
<NtryDtls><TxDtls><RltdPties><Cdtr><Nm>Netflix</Nm></Cdtr></RltdPties>
<RmtInf><Ustrd>Abo</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
<Ntry><Amt Ccy="EUR">3100.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2026-09-01</Dt></BookgDt>
<NtryDtls><TxDtls><RltdPties><Dbtr><Nm>Arbeitgeber</Nm></Dbtr></RltdPties></TxDtls></NtryDtls></Ntry>
</Stmt></BkToCstmrStmt></Document>"""

MT940 = """:20:STARTUMS
:25:12345678/987654321
:28C:1/1
:60F:C260831EUR1000,00
:61:2609050905D12,99NMSCNONREF
:86:105?00Lastschrift?20Abo Netflix?32Netflix International
:61:2609010901C3100,00NTRFNONREF
:86:051?00Gutschrift?20Gehalt?32Arbeitgeber GmbH
:62F:C260930EUR4087,01
"""


def test_amounts_and_dates() -> None:
    assert st.parse_amount("1.234,56") == Decimal("1234.56")
    assert st.parse_amount("-12,99") == Decimal("-12.99")
    assert st.parse_amount("12,99-") == Decimal("-12.99")
    assert st.parse_amount("1234.50") == Decimal("1234.50")
    assert st.parse_day("05.08.2026") == date(2026, 8, 5)
    assert st.parse_day("2026-08-05T10:00:00") == date(2026, 8, 5)
    with pytest.raises(st.StatementError):
        st.parse_day("morgen")


def test_csv_with_preamble_and_german_numbers() -> None:
    lines = st.parse_csv(CSV)
    assert len(lines) == 8
    assert lines[0].counterparty == "Netflix International B.V." and lines[0].amount == Decimal(
        "-12.99"
    )
    assert lines[4].amount == Decimal("3100.00")


def test_csv_without_date_column_is_rejected() -> None:
    with pytest.raises(st.StatementError):
        st.parse_csv("a;b\n1;2\n")


def test_camt_and_mt940() -> None:
    camt = st.parse_camt(CAMT)
    assert [(x.counterparty, x.amount) for x in camt] == [
        ("Netflix", Decimal("-12.99")),
        ("Arbeitgeber", Decimal("3100.00")),
    ]
    mt = st.parse_mt940(MT940)
    assert (mt[0].counterparty, mt[0].amount, mt[0].day) == (
        "Netflix International",
        Decimal("-12.99"),
        date(2026, 9, 5),
    )
    assert mt[1].amount == Decimal("3100.00") and "Gehalt" in mt[1].purpose


def test_xml_with_entities_is_refused() -> None:
    with pytest.raises(st.StatementError):
        st.parse_camt('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><Document/>')


def test_recurring_payments_are_found_by_rhythm_and_amount() -> None:
    found, rest = st.find_recurring(st.parse_csv(CSV))
    by_name = {r.name: r for r in found}
    assert set(by_name) == {"Netflix International B.V.", "Arbeitgeber GmbH", "Stadtwerke"}
    netflix = by_name["Netflix International B.V."]
    assert (netflix.months, netflix.count, netflix.income) == (1, 3, False)
    assert by_name["Arbeitgeber GmbH"].income and by_name["Arbeitgeber GmbH"].amount == Decimal(
        "3100.00"
    )
    assert by_name["Stadtwerke"].amount == Decimal("84.00")  # varies a little, still one payee
    assert [x.counterparty for x in rest] == ["Shell Tankstelle 4711"]


def test_a_changing_rhythm_is_not_recurring() -> None:
    lines = [
        st.BankLine(date(2026, 1, 3), Decimal("-20"), "Kiosk", ""),
        st.BankLine(date(2026, 1, 9), Decimal("-20"), "Kiosk", ""),
        st.BankLine(date(2026, 3, 30), Decimal("-20"), "Kiosk", ""),
    ]
    assert st.find_recurring(lines)[0] == []


def test_yearly_payment_needs_two_years() -> None:
    lines = [
        st.BankLine(date(2025, 6, 1), Decimal("-300"), "Haftpflicht Versicherung", ""),
        st.BankLine(date(2026, 6, 1), Decimal("-300"), "Haftpflicht Versicherung", ""),
    ]
    (found,), _ = st.find_recurring(lines)
    assert found.months == 12
