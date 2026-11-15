# Data

- `airlines.csv`: carrier codes and names (included).
- `airports.csv`: airport codes with city, state, and coordinates (included).
- `flights.csv`: 2015 US flight delay records (**not included**, about 560 MB).

## Get flights.csv

Download the "2015 Flight Delays and Cancellations" dataset from Kaggle (the U.S. Department of Transportation Bureau of Transportation Statistics data). Save the flights file here as `data/flights.csv`.

The analysis expects these columns: `YEAR`, `MONTH`, `DAY`, `AIRLINE`, `ORIGIN_AIRPORT`, `DESTINATION_AIRPORT`, `ARRIVAL_DELAY`, `CANCELLED`, plus the delay-reason columns and `CANCELLATION_REASON` when present.
