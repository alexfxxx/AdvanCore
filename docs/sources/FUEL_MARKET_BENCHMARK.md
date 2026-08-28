# Singapore Fuel Market Benchmark

Snapshot retrieval date: 28 August 2026.

## Definition

All values are Singapore dollars per litre at the gross pump rate before card,
membership, promotion or other discounts. They are dated reference evidence,
not a live quote, invoice, forecast or AdvanCore business transaction.

## Sources

- [Motorist Singapore](https://www.motorist.sg/petrol-prices) supplies the
  cross-market comparison used for the diesel benchmark: Esso 3.95, Shell
  3.95, SPC 3.89, Caltex 4.05 and Sinopec 3.89. Retrieved 28 August 2026.
- [SPC Singapore](https://www.spc.com.sg/) officially displayed LEVO Diesel
  3.890, LEVO 95 3.360 and LEVO 98 3.880, updated 7 July 2026 at 17:40 SGT,
  before discounts and savings.
- [Shell Singapore](https://www.shell.com.sg/fuels-oils-and-coolants/shell-fuels/shell-station-price-board.html)
  publishes its dated price-board workbook and defines gross price as the pump
  price before discounts. The workbook updated 9 August 2026 at 22:15 SGT lists
  Shell FuelSave Diesel 3.95, FuelSave 95 3.37 and FuelSave 98 3.89.

## Calculated diesel comparison

The five Motorist values produce a low of SGD 3.89/L, median of SGD 3.95/L and
high of SGD 4.05/L. AdvanCore calculates these three values from the stored
observations rather than storing an unexplained benchmark.

The SPC and Shell official observations deliberately keep their own update
timestamps. The UI labels them as dated and does not imply they are live.

## Refresh rule

Refresh requires a new governed, source-checked snapshot. Normal application
startup performs no web scraping and makes no database change.
