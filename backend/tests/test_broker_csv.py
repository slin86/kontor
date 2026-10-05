from datetime import date
from decimal import Decimal

import pytest

from kontor.domain import broker_csv as csv_dom

HEADER = (
    "datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,amount,fee,"
    "tax,currency,original_amount,original_currency,fx_rate,description,transaction_id,"
    "counterparty_name,counterparty_iban,payment_reference,mcc_code"
)

TR_SAMPLE = "\n".join(
    [
        HEADER,
        '"2026-08-03T07:00:00.000Z","2026-08-03","DEFAULT","TRADING","BUY","STOCK",'
        '"Invesco MSCI World","IE00B60SX394","3.5","71.40","-250","-1","","EUR","","","",'
        '"Sparplan","t-1","","","",""',
        '"2026-09-03T07:00:00.000Z","2026-09-03","DEFAULT","TRADING","BUY","STOCK",'
        '"Invesco MSCI World","IE00B60SX394","3.4","73.52","-250","","","EUR","","","",'
        '"Sparplan","t-2","","","",""',
        '"2026-09-10T10:00:00.000Z","2026-09-10","DEFAULT","TRADING","SELL","STOCK",'
        '"Invesco MSCI World","IE00B60SX394","1","74.00","74","-1","","EUR","","","",'
        '"Verkauf","t-3","","","",""',
        '"2026-09-15T10:00:00.000Z","2026-09-15","DEFAULT","CASH","DIVIDEND","STOCK",'
        '"Apple","US0378331005","","","2.40","","0.36","EUR","","","","Dividende","t-4","","","",""',
        '"2026-09-20T10:00:00.000Z","2026-09-20","DEFAULT","CASH","CUSTOMER_INBOUND","",'
        '"","","","","1000","","","EUR","","","","Einzahlung","t-5","","","",""',
        '"2026-09-21T10:00:00.000Z","2026-09-21","DEFAULT","CASH","CARD_TRANSACTION",'
        '"","","","","","-12.5","","","EUR","","","","Kartenzahlung","t-6","","","",""',
        '"2026-09-22","2026-09-22","DEFAULT","TRADING","BUY","STOCK","Kaputt","IE00B60SX394",'
        '"1","1","abc","","","EUR","","","","","t-7","","","",""',
    ]
)


def test_parses_trade_republic_layout() -> None:
    r = csv_dom.parse_broker_csv(TR_SAMPLE)
    kinds = [(x.kind, x.amount, x.isin) for x in r.rows]
    assert kinds == [
        ("buy", Decimal(250), "IE00B60SX394"),
        ("buy", Decimal(250), "IE00B60SX394"),
        ("sell", Decimal(74), "IE00B60SX394"),
        ("dividend", Decimal("2.40"), "US0378331005"),
    ]
    first = r.rows[0]
    assert (
        first.day == date(2026, 8, 3) and first.fee == Decimal(1) and first.shares == Decimal("3.5")
    )
    assert first.external_id == "t-1"
    # everything else is counted, not guessed
    assert r.skipped == {"CASH/CUSTOMER_INBOUND": 1, "CASH/CARD_TRANSACTION": 1}
    assert len(r.errors) == 1 and "Zeile 8" in r.errors[0]


def test_parses_simple_layout_with_semicolons_and_german_numbers() -> None:
    text = (
        "Datum;Typ;ISIN;Name;Stücke;Kurs;Betrag;Gebühr\n"
        "03.09.2026;Kauf;IE00B4L5Y983;iShares Core MSCI World;2,5;80,10;-200,25;1,00\n"
        "04.09.2026;Sparplan;IE00B4L5Y983;iShares Core MSCI World;1;80,00;-1.080,50;0\n"
    )
    r = csv_dom.parse_broker_csv(text)
    assert [(x.kind, x.amount, x.shares, x.fee) for x in r.rows] == [
        ("buy", Decimal("200.25"), Decimal("2.5"), Decimal(1)),
        ("buy", Decimal("1080.50"), Decimal(1), Decimal(0)),
    ]
    assert r.rows[0].day == date(2026, 9, 3)


def test_rows_without_transaction_id_get_stable_distinct_ids() -> None:
    line = "2026-09-03,Buy,IE00B4L5Y983,Fonds,1,10,-10,0\n"
    text = "Date,Type,ISIN,Name,Shares,Price,Amount,Fee\n" + line * 2
    a = csv_dom.parse_broker_csv(text).rows
    b = csv_dom.parse_broker_csv(text).rows
    assert a[0].external_id != a[1].external_id
    assert [x.external_id for x in a] == [x.external_id for x in b]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("12,5", "12.5"),
        ("-3.5", "-3.5"),
        ("", None),
    ],
)
def test_number_formats(raw: str, expected: str | None) -> None:
    got = csv_dom.parse_number(raw)
    assert (str(got) if got is not None else None) == expected


def test_rejects_files_that_are_not_transaction_exports() -> None:
    with pytest.raises(csv_dom.CsvError):
        csv_dom.parse_broker_csv("foo,bar\n1,2\n")
    with pytest.raises(csv_dom.CsvError):
        csv_dom.parse_broker_csv("")
