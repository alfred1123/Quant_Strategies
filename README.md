##############################Quant strategies########################################
Author: Alfred Cheung (updated on 18/3/2023

This is a project to develop new trading strategies focusing on Hong Kong Equity, America Equity and Cryptocurrencies assets traded in the secondary market.
Different factor will be explored:
i.e. price, economic data, exchange data, raw materials indexes, demands, cross asset relationships etc. (To be confirmed)
Main Goal of this project is to find strategies higher than 1.5 Sharpe and Calmar ratios.

Current Development:

Created samples of notebooks to understand requirements for utils script to abstract complexity of calculations
Developed Bollinger Band strategy and Moving Average strategy under utils/factors.price.py
Developed perf calculation functions under utils/perf.py


The folder system will be organised as below )
C:.
│  README.md
│  tree.txt
│
├─data
│  ├─processed
│  │      btcusd_20200510_20230310.xlsx
│  │      btc_exchange_netflow_20200510_20230310.xlsx
│  │
│  └─raw
│          btcusd_20200510_20230310.xlsx
│          btc_exchange_netflow_20200510_20230310.xlsx
│          CBBC01.zip
│          CBBC02.zip
│          CBBC03.zip
│          CBBC04.zip
│          CBBC05.zip
│          CBBC06.zip
│          CBBC07.zip
│          CBBC08.zip
│          CBBC09.zip
│          CBBC10.zip
│          CBBC11.zip
│          CBBC12.zip
│
├─notebooks
│      btc_flow_exchange_analysis.ipynb
│      btc_MA_analysis.ipynb
│
├─scripts
├─strategies
├─tests
└─utils
    │  perf.py
    │
    ├─factors
    │      price.py
    │
    └─__pycache__
            interface.cpython-310.pyc
            perf.cpython-310.pyc


The project is still under development, thank you for support!