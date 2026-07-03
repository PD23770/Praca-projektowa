from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from data_processing import (
    NBPApiError,
    build_cleaning_report,
    build_currency_summary,
    fetch_exchange_rates,
    prepare_rates,
)

st.set_page_config(
    page_title="Kursy walut NBP | Dashboard",
    page_icon="💱",
    layout="wide",
    initial_sidebar_state="expanded",
)

CURRENCIES = {
    "EUR": "EUR — euro",
    "USD": "USD — dolar amerykański",
    "GBP": "GBP — funt szterling",
    "CHF": "CHF — frank szwajcarski",
    "CAD": "CAD — dolar kanadyjski",
    "AUD": "AUD — dolar australijski",
    "NOK": "NOK — korona norweska",
    "SEK": "SEK — korona szwedzka",
}


@st.cache_data(ttl=60 * 60, show_spinner=False)
def load_rates(codes: tuple[str, ...], start_date: str, end_date: str) -> pd.DataFrame:
    return fetch_exchange_rates(codes, start_date, end_date)


def last_business_day(reference_date: date) -> date:
    result = reference_date
    while result.weekday() >= 5:
        result -= timedelta(days=1)
    return result


def pln(value: float | int | None, decimals: int = 4) -> str:
    if value is None or pd.isna(value):
        return "—"
    formatted = f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return f"{formatted} zł"


def percentage(value: float | int | None, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:+.{decimals}f}%".replace(".", ",")


def make_line_chart(data: pd.DataFrame, metric: str) -> px.line:
    value_column = "mid" if metric == "Kurs średni (PLN)" else "daily_return_pct"
    y_title = "Kurs średni [PLN]" if value_column == "mid" else "Dzienna zmiana [%]"
    chart_data = data.dropna(subset=[value_column])

    fig = px.line(
        chart_data,
        x="date",
        y=value_column,
        color="code",
        hover_data={"currency": True, "date": "|%d.%m.%Y", value_column: ":.4f"},
        labels={"date": "Data", value_column: y_title, "code": "Waluta"},
        title=f"{metric} w czasie",
    )
    fig.update_layout(
        legend_title_text="Waluta",
        hovermode="x unified",
        margin=dict(l=10, r=10, t=55, b=10),
    )
    return fig


def make_bar_chart(summary: pd.DataFrame, ranking_size: int, metric: str) -> px.bar:
    if metric == "Kurs średni (PLN)":
        chart_data = summary.nlargest(ranking_size, "last_rate").sort_values("last_rate")
        x_column, label, title = (
            "last_rate",
            "Ostatni dostępny kurs [PLN]",
            "Ranking: ostatni dostępny kurs",
        )
    else:
        chart_data = summary.nlargest(ranking_size, "volatility_pct").sort_values("volatility_pct")
        x_column, label, title = (
            "volatility_pct",
            "Odchylenie standardowe dziennych zmian [%]",
            "Ranking: zmienność dzienna",
        )

    fig = px.bar(
        chart_data,
        x=x_column,
        y="code",
        orientation="h",
        text=x_column,
        hover_data={"currency": True, "change_pct": ":.2f", "observations": True},
        labels={x_column: label, "code": "Waluta"},
        title=title,
    )
    fig.update_traces(texttemplate="%{text:.4f}", textposition="outside", cliponaxis=False)
    fig.update_layout(margin=dict(l=10, r=40, t=55, b=10), showlegend=False)
    return fig


def make_histogram(data: pd.DataFrame) -> px.histogram:
    chart_data = data.dropna(subset=["daily_return_pct"])
    fig = px.histogram(
        chart_data,
        x="daily_return_pct",
        color="code",
        nbins=35,
        barmode="overlay",
        opacity=0.65,
        labels={
            "daily_return_pct": "Dzienna zmiana [%]",
            "count": "Liczba notowań",
            "code": "Waluta",
        },
        title="Rozkład dziennych zmian kursu",
    )
    fig.update_layout(margin=dict(l=10, r=10, t=55, b=10), legend_title_text="Waluta")
    return fig


def make_box_plot(data: pd.DataFrame) -> px.box:
    chart_data = data.dropna(subset=["daily_return_pct"])
    fig = px.box(
        chart_data,
        x="code",
        y="daily_return_pct",
        points="outliers",
        labels={"code": "Waluta", "daily_return_pct": "Dzienna zmiana [%]"},
        title="Zmienność i wartości odstające dziennych zmian",
    )
    fig.update_layout(margin=dict(l=10, r=10, t=55, b=10))
    return fig


def make_scatter(summary: pd.DataFrame) -> px.scatter:
    fig = px.scatter(
        summary,
        x="average_rate",
        y="volatility_pct",
        size="observations",
        color="change_pct",
        hover_name="code",
        hover_data={
            "currency": True,
            "average_rate": ":.4f",
            "volatility_pct": ":.3f",
            "change_pct": ":.2f",
            "observations": True,
        },
        labels={
            "average_rate": "Średni kurs [PLN]",
            "volatility_pct": "Zmienność dzienna [%]",
            "change_pct": "Zmiana w okresie [%]",
            "observations": "Liczba notowań",
        },
        title="Średni kurs a zmienność",
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=55, b=10),
        coloraxis_colorbar_title="Zmiana [%]",
    )
    return fig


def make_heatmap(data: pd.DataFrame) -> px.imshow | None:
    wide_returns = data.pivot(index="date", columns="code", values="daily_return_pct")
    correlation = wide_returns.corr(min_periods=10)

    if correlation.shape[0] < 2:
        return None

    fig = px.imshow(
        correlation.round(2),
        text_auto=".2f",
        aspect="auto",
        zmin=-1,
        zmax=1,
        labels={"x": "Waluta", "y": "Waluta", "color": "Korelacja"},
        title="Korelacja dziennych zmian kursów",
    )
    fig.update_layout(margin=dict(l=10, r=10, t=55, b=10))
    return fig


def main() -> None:
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 2.5rem;}
        [data-testid="stMetricValue"] {font-size: 1.65rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Kursy walut NBP")
    st.caption(
        "Interaktywny dashboard analityczny oparty na średnich kursach walut "
        "z tabeli A Narodowego Banku Polskiego."
    )

    today = last_business_day(date.today())
    default_start = today - timedelta(days=180)

    with st.sidebar:
        st.header("Filtry analizy")

        selected_dates = st.date_input(
            "Zakres dat",
            value=(default_start, today),
            min_value=date(2002, 1, 2),
            max_value=date.today(),
            help="Możesz wybrać maksymalnie 365 dni, aby dashboard działał sprawnie.",
        )

        selected_codes = st.multiselect(
            "Waluty",
            options=list(CURRENCIES),
            default=["EUR", "USD", "GBP", "CHF"],
            format_func=lambda code: CURRENCIES[code],
        )

        metric = st.selectbox(
            "Miara na wykresach",
            options=["Kurs średni (PLN)", "Dzienna zmiana (%)"],
        )

        ranking_size = st.slider(
            "Liczba walut w rankingu",
            min_value=1,
            max_value=len(CURRENCIES),
            value=4,
        )

        st.divider()
        st.caption(
            "Dane są cache’owane na 60 minut. Zmiana filtrów pobiera "
            "i przelicza odpowiedni zestaw danych."
        )

    if not selected_codes:
        st.info("Wybierz co najmniej jedną walutę w panelu po lewej stronie.")
        st.stop()

    if not isinstance(selected_dates, tuple) or len(selected_dates) != 2:
        st.warning("Wybierz pełny zakres: datę początkową i końcową.")
        st.stop()

    start_date, end_date = selected_dates

    if start_date > end_date:
        st.error("Data początkowa nie może być późniejsza niż data końcowa.")
        st.stop()

    if (end_date - start_date).days > 365:
        st.error("Zakres może obejmować maksymalnie 365 dni. Wybierz krótszy okres.")
        st.stop()

    with st.spinner("Pobieranie danych z API NBP i przygotowanie analizy…"):
        try:
            raw_data = load_rates(
                tuple(sorted(selected_codes)),
                start_date.isoformat(),
                end_date.isoformat(),
            )
        except (NBPApiError, ValueError) as exc:
            st.error(str(exc))
            st.stop()

    prepared_data = prepare_rates(raw_data)

    if prepared_data.empty:
        st.warning(
            "Brak notowań dla wybranych filtrów. Spróbuj innego zakresu dat lub innych walut."
        )
        st.stop()

    summary = build_currency_summary(prepared_data)
    latest_date = prepared_data["date"].max()
    highest_change = summary.loc[summary["change_pct"].idxmax()]

    volatility_candidates = summary.dropna(subset=["volatility_pct"])
    highest_volatility = (
        volatility_candidates.loc[volatility_candidates["volatility_pct"].idxmax()]
        if not volatility_candidates.empty
        else None
    )

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)

    metric_1.metric("Ostatnie notowanie", latest_date.strftime("%d.%m.%Y"))
    metric_2.metric("Obserwacje", f"{len(prepared_data):,}".replace(",", " "))
    metric_3.metric(
        "Największa zmiana w okresie",
        highest_change["code"],
        percentage(highest_change["change_pct"]),
    )
    metric_4.metric(
        "Najwyższa zmienność",
        highest_volatility["code"] if highest_volatility is not None else "—",
        percentage(highest_volatility["volatility_pct"])
        if highest_volatility is not None
        else "Brak danych",
    )

    lead = summary.sort_values("change_pct", ascending=False).iloc[0]

    st.info(
        f"**Szybki wniosek:** w wybranym okresie najsilniej zmienił się kurs "
        f"**{lead['code']}** ({percentage(lead['change_pct'])}); "
        f"ostatni dostępny kurs wyniósł {pln(lead['last_rate'])}."
    )

    tab_overview, tab_volatility, tab_correlation, tab_data = st.tabs(
        [
            "Trend i ranking",
            "Zmienność",
            "Korelacje",
            "Dane i przygotowanie",
        ]
    )

    with tab_overview:
        st.plotly_chart(make_line_chart(prepared_data, metric), use_container_width=True)

        left, right = st.columns([1, 1])

        with left:
            st.plotly_chart(
                make_bar_chart(
                    summary,
                    ranking_size=min(ranking_size, len(summary)),
                    metric=metric,
                ),
                use_container_width=True,
            )

        with right:
            display_summary = summary[
                [
                    "code",
                    "last_rate",
                    "average_rate",
                    "min_rate",
                    "max_rate",
                    "change_pct",
                    "volatility_pct",
                    "observations",
                ]
            ].copy()

            display_summary.columns = [
                "Waluta",
                "Ostatni kurs [PLN]",
                "Średni kurs [PLN]",
                "Min. [PLN]",
                "Max. [PLN]",
                "Zmiana [%]",
                "Zmienność [%]",
                "Notowania",
            ]

            st.subheader("Podsumowanie walut")

            st.dataframe(
                display_summary.style.format(
                    {
                        "Ostatni kurs [PLN]": "{:.4f}",
                        "Średni kurs [PLN]": "{:.4f}",
                        "Min. [PLN]": "{:.4f}",
                        "Max. [PLN]": "{:.4f}",
                        "Zmiana [%]": "{:+.2f}",
                        "Zmienność [%]": "{:.3f}",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    with tab_volatility:
        col_left, col_right = st.columns(2)

        with col_left:
            st.plotly_chart(make_histogram(prepared_data), use_container_width=True)

        with col_right:
            st.plotly_chart(make_box_plot(prepared_data), use_container_width=True)

        st.plotly_chart(make_scatter(summary), use_container_width=True)

        st.caption(
            "Wartości odstające na boxplocie to dni o nietypowo dużej zmianie kursu. "
            "Zmienność to odchylenie standardowe dziennych procentowych zmian."
        )

    with tab_correlation:
        heatmap = make_heatmap(prepared_data)

        if heatmap is None:
            st.info("Do wyznaczenia korelacji wybierz co najmniej dwie waluty.")
        else:
            st.plotly_chart(heatmap, use_container_width=True)

            st.caption(
                "Korelacja bliska 1 oznacza podobny kierunek dziennych zmian, "
                "a bliska -1 — kierunek przeciwny. Korelacja nie dowodzi związku przyczynowego."
            )

    with tab_data:
        st.subheader("Widoczny etap czyszczenia i przygotowania")

        st.dataframe(
            build_cleaning_report(raw_data, prepared_data),
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            "Braki dat wynikające z weekendów i świąt nie są sztucznie uzupełniane — "
            "NBP publikuje tabele tylko w dniach notowań."
        )

        st.subheader("Próbka danych po przygotowaniu")

        preview = prepared_data.sort_values(
            ["date", "code"],
            ascending=[False, True],
        ).head(100).copy()

        preview["date"] = preview["date"].dt.strftime("%Y-%m-%d")

        st.dataframe(preview, use_container_width=True, hide_index=True)

        csv_data = prepared_data.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            label="Pobierz dane po przygotowaniu (CSV)",
            data=csv_data,
            file_name=f"kursy_nbp_{start_date}_{end_date}.csv",
            mime="text/csv",
        )

    st.divider()

    st.caption(
        "Źródło: publiczne API NBP, tabela A — średnie kursy walut. "
        "Dashboard ma charakter edukacyjny i nie stanowi rekomendacji inwestycyjnej."
    )


if __name__ == "__main__":
    main()