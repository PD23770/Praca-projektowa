Interaktywna aplikacja do analizy średnich kursów walut publikowanych przez Narodowy Bank Polski. Użytkownik wybiera okres, waluty oraz miarę analizy, a dashboard automatycznie pobiera dane z API, czyści je, tworzy kolumny pochodne i aktualizuje wizualizacje.

---- Link do działającej wersji

https://praca-projektowa-cqmnqunjaiexahpk2jzzea.streamlit.app/

---- Dane pochodzą z publicznego API NBP, tabela A — średnie kursy walut:
dokumentacja API: https://api.nbp.pl/en.html

---- Co robi aplikacja?

1. Pobiera rzeczywiste dane kursowe dla wybranych walut z API NBP.
2. Czyści i przygotowuje dane:
   -konwertuje daty i kursy na prawidłowe typy,
   -usuwa braki, wartości niedodatnie i duplikaty,
   -sortuje dane po walucie oraz dacie,
   =oblicza dzienną zmianę kursu, dzienną stopę zwrotu i cechy kalendarzowe.
3. Pozwala filtrować wyniki przez:
   -zakres dat,
   -listę walut,
   -miarę analizy,
   -liczbę walut widocznych w rankingu.
4. Pokazuje tabelę podsumowań i co najmniej sześć rodzajów wykresów:
   -liniowy - kurs lub dzienna zmiana w czasie,
   -słupkowy - ranking kursu lub zmienności,
   -histogram - rozkład dziennych zmian,
   -boxplot - zmienność i wartości odstające,
   -scatter plot - relacja średniego kursu i zmienności,
   -heatmapa - korelacja dziennych zmian walut.
5. Udostępnia przygotowany zbiór danych do pobrania jako CSV.

---- Struktura projektu
-app.py
-data_processing.py
-requirements.txt
-README.md
-.gitignore

PD
