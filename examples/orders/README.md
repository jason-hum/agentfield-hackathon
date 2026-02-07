# Order JSON examples

Validate inline:

```bash
python -m src.app validate --json '{"action":"BUY","symbol":"AAPL","order_type":"MKT","quantity":1}'
```

Validate from file:

```bash
python -m src.app validate --json-file examples/orders/mkt_buy_aapl.json
python -m src.app validate --json-file examples/orders/lmt_sell_msft.json
```
