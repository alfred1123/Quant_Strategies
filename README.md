##############################Quant strategies########################################
Author: Alfred Cheung

This is a project to develop new trading strategies focusing on Hong Kong Equity, America Equity and Cryptocurrencies assets traded in the secondary market.
Different factor will be explored:
i.e. price, economic data, exchange data, raw materials indexes, demands, cross asset relationships etc. (To be confirmed)
Currently, we will aim for strategies higher than 1.5 Sharpe and Calmar ratios.

The folder system will be organised as below (files are written as examples)
Project/
├── data/
│   ├── raw/
│   │   ├── raw_data_1.csv
│   │   ├── raw_data_2.xlsx
│   │   └── ...
│   ├── processed/
│   │   ├── processed_data_1.csv
│   │   ├── processed_data_2.xlsx
│   │   └── ...
│   └── ...
├── notebooks/
│   ├── data_exploration.ipynb
│   ├── feature_engineering.ipynb
│   ├── model_training.ipynb
│   └── ...
├── scripts/
│   ├── data_processing.py
│   ├── feature_extraction.py
│   ├── model_training.py
│   └── ...
├── strategies/
│   ├── momentum_strategy.py
│   ├── mean_reversion_strategy.py
│   ├── pairs_trading_strategy.py
│   └── ...
├── utils/
│   ├── data_loading.py
│   ├── data_preprocessing.py
│   ├── model_evaluation.py
│   └── ...
├── tests/
│   ├── test_data_loading.py
│   ├── test_data_preprocessing.py
│   ├── test_model_evaluation.py
│   └── ...
└── README.md


The project is still under development, thank you for support!