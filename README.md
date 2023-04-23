# **Quant Strategies**

#### Author: Alfred Cheung (updated on 11/04/2023)

### **Introduction**
This is a project to backtesting and developing new trading strategies focusing on Hong Kong Equity, America Equity and Cryptocurrencies assets traded in the secondary market.
Different factor will be explored, the strategies are will be executed under continuous deployment on AWS EC2 cloud:

i.e. price, economic data, exchange data, raw materials indexes, demands, cross asset relationships etc. (To be confirmed)
Main Goal of this project is to find strategies higher than 1.5 Sharpe and Calmar ratios.

### **Current Development**:

- *notebook*: testing to understand requirements for scripts
- *scripts*:
    1. retrieve data from futu and glassnode api
    2. technical analysis for price and factors
    3. performance of trading strategy
    4. parameter optimization
    5. real-time trade data and placing order in bybit exchange online

### **Future Development**:
- add parameter optimization functions
- exploring code efficiency for api request by possible implementation of REDIS
- create a bot on telegram or discord for trading messages
- explore ways of continuous deployment (i.e. Azure or EC2)




The project is still under development, **thank you for support!**