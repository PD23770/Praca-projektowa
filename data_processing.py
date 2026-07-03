from __future__ import annotations

from datetime import date, timedelta
from typing import Iterator, Sequence

import numpy as np
import pandas as pd
import requests

API_BASE = "https://api.nbp.pl/api/exchangerates/rates/a"
MAX_DAYS_PER_QUERY = 90
REQUEST_TIMEOUT_SECONDS = 20


class NBPApiError(RuntimeError):
    pass


def split_date_range(
    start_date: date,
    end_date: date,
    max_days: int = MAX_DAYS_PER_QUERY,
) -> Iterator[tuple[date, date]]:
    current_start = start_date

    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=max_days - 1), end_date)
        yield current_start, current_end
        current_start = current_end + timedelta(days=1)


def _request_json(url: str) -> dict | None:
    try:
        response = requests.get(
            url,
            params={"format": "json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "streamlit-nbp-currency-dashboard/1.0"},
        )
    except requests.RequestException as exc:
        raise NBPApiError(
            "Nie udało się połączyć z API NBP. Sprawdź połączenie z internetem "
            "albo spróbuj ponownie za chwilę."
        ) from exc

    if response.status_code == 404:
        return None

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise NBPApiError(
            f"API NBP zwróciło błąd {response.status_code}. "
            "Zmniejsz zakres dat lub spróbuj ponownie."
        ) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise NBPApiError(
            "API NBP zwróciło odpowiedź, której nie da się odczytać jako JSON."
        ) from exc


def fetch_exchange_rates(
    currency_codes: Sequence[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    if start > end:
        raise ValueError("Data początkowa nie może być późniejsza niż data końcowa.")

    records: list[dict] = []

    for code in sorted({code.upper() for code in currency_codes}):
        for chunk_start, chunk_end in split_date_range(start, end):
            url = f"{API_BASE}/{code}/{chunk_start.isoformat()}/{chunk_end.isoformat()}/"
            payload = _request_json(url)

            if not payload:
                continue

            currency_name = payload.get("currency", code)

            for quotation in payload.get("rates", []):
                records.append(
                    {
                        "date": quotation.get("effectiveDate"),
                        "code": payload.get("code", code),
                        "currency": currency_name,
                        "mid": quotation.get("mid"),
                        "table_no": quotation.get("no"),
                    }
                )

    return pd.DataFrame(
        records,
        columns=["date", "code", "currency", "mid", "table_no"],
    )


def prepare_rates(raw_data: pd.DataFrame) -> pd.DataFrame:
    if raw_data.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "code",
                "currency",
                "mid",
                "table_no",
                "daily_change_pln",
                "daily_return_pct",
                "month",
                "year",
                "weekday",
            ]
        )

    df = raw_data.copy()

    # Konwersje typów.
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["mid"] = pd.to_numeric(df["mid"], errors="coerce")
    df["code"] = df["code"].astype("string").str.upper().str.strip()
    df["currency"] = df["currency"].astype("string").str.strip()

    # Usunięcie braków oraz błędnych wartości.
    df = df.dropna(subset=["date", "code", "currency", "mid"])
    df = df.loc[df["mid"] > 0].copy()

    # Jedna obserwacja na dzień i walutę.
    df = df.drop_duplicates(subset=["date", "code"], keep="last")
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    # Kolumny pochodne.
    grouped_mid = df.groupby("code", observed=True)["mid"]

    df["daily_change_pln"] = grouped_mid.diff()
    df["daily_return_pct"] = grouped_mid.pct_change(fill_method=None) * 100
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["year"] = df["date"].dt.year
    df["weekday"] = df["date"].dt.day_name()

    return df


def build_currency_summary(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()

    summary = (
        data.groupby(["code", "currency"], observed=True)
        .agg(
            observations=("mid", "size"),
            first_date=("date", "min"),
            last_date=("date", "max"),
            first_rate=("mid", "first"),
            last_rate=("mid", "last"),
            average_rate=("mid", "mean"),
            min_rate=("mid", "min"),
            max_rate=("mid", "max"),
            volatility_pct=("daily_return_pct", "std"),
        )
        .reset_index()
    )

    summary["change_pct"] = (
        (summary["last_rate"] / summary["first_rate"] - 1) * 100
    ).replace([np.inf, -np.inf], np.nan)

    return summary.sort_values("code").reset_index(drop=True)


def build_cleaning_report(
    raw_data: pd.DataFrame,
    prepared_data: pd.DataFrame,
) -> pd.DataFrame:
    raw_rows = len(raw_data)
    valid_rows = 0

    if not raw_data.empty:
        validation_frame = raw_data.copy()
        validation_frame["date"] = pd.to_datetime(
            validation_frame["date"],
            errors="coerce",
        )
        validation_frame["mid"] = pd.to_numeric(
            validation_frame["mid"],
            errors="coerce",
        )

        valid_rows = len(
            validation_frame.dropna(
                subset=["date", "code", "currency", "mid"]
            ).query("mid > 0")
        )

    return pd.DataFrame(
        {
            "Etap": [
                "Dane pobrane z API",
                "Walidacja braków i typów",
                "Usunięcie duplikatów",
                "Kolumny pochodne",
            ],
            "Co zostało zrobione": [
                "Pobrano notowania średnich kursów z tabeli A NBP.",
                "Daty zamieniono na datetime, kursy na liczby; odrzucono braki i kursy ≤ 0.",
                "Zostawiono maksymalnie jeden rekord dla pary data–waluta.",
                "Wyliczono dzienną zmianę, dzienną stopę zwrotu i cechy kalendarzowe.",
            ],
            "Liczba rekordów": [
                raw_rows,
                valid_rows,
                len(prepared_data),
                len(prepared_data),
            ],
        }
    )
