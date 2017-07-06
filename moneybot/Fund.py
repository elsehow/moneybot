from typing import Dict, Iterator, Type
from .market_adapters import MarketAdapter
from .strategies import Strategy
from .MarketHistory import MarketHistory
from datetime import datetime
from time import sleep, time
import pandas as pd


class Fund (object):

    '''
    TODO Docstring
    '''

    def __init__ (self,
                  strat: Type[Strategy],
                  market_adapter: Type[MarketAdapter],
                  config: Dict) -> None:
        self.config = config
        self.Strategy = strat(self.config)
        # MarketHistory stores historical market data
        self.MarketHistory = MarketHistory(self.config)
        # MarketAdapter executes trades, fetches balances
        self.MarketAdapter = market_adapter(self.MarketHistory,
                                            self.config)


    def step (self,
              time: datetime) -> float:
        market_state = self.MarketAdapter.get_market_state(time)
        # Now, propose trades. If you're writing a strategy, you will override this method.
        proposed_trades = self.Strategy.propose_trades(market_state, self.MarketHistory)
        # If the strategy proposed any trades, we execute them.
        if proposed_trades:
            # The user's propose_trades() method could be returning anything,
            # we don't trust it necessarily. So, we have our MarketAdapter
            # assure that all the trades are legal, by the market's rules.
            # `filter_legal()` will throw informative warnings if any trades
            # get filtered out!
            # TODO Can the Strategy get access to this sanity checker?
            assumed_legal_trades = self.MarketAdapter.filter_legal(proposed_trades, market_state)
            # Finally, the MarketAdapter will execute our trades.
            # If we're backtesting, these trades won't really happen.
            # If we're trading for real, we will attempt to execute the proposed trades
            # at the best price we can.
            # In either case, this method is side-effect-y;
            # it sets MarketAdapter.balances, after all trades have been executed.
            self.MarketAdapter.execute(assumed_legal_trades,
                                       market_state)
        # Finally, we get the USD value of our whole fund,
        # now that all trades (if there were any) have been executed.
        usd_value = market_state.estimate_total_value_usd()
        return usd_value


    def run_live (self) -> None:
        starttime=time()
        PERIOD = self.Strategy.trade_interval
        while True:
            # Get time loop starts, so
            # we can account for the time
            # that the step took to run
            cur_time = datetime.now()
            # Before anything,
            # scrape poloniex
            # to make sure we have freshest data
            self.MarketHistory.scrape_latest()
            # Now the fund can step()
            print('Fund.step({!s})'.format(cur_time))
            usd_val = self.step(cur_time)
            # After its step, we have got the USD value.
            print('Est. USD value', usd_val)
            # Wait until our next time to run,
            # Accounting for the time that this step took to run
            sleep(PERIOD - ((time() - starttime) % PERIOD))


    def begin_backtest (self,
                        start_time: str,
                        end_time: str) -> Iterator[float]:
        '''
        Takes a start time and end time (as parse-able date strings).

        Returns a list of USD values for each point (trade interval)
        between start and end.
        '''
        # MarketAdapter executes trades
        # Set up the historical coinstore
        # A series of trade-times to run each of our strategies through.
        dates = pd.date_range(pd.Timestamp(start_time),
                              pd.Timestamp(end_time),
                              freq='{!s}S'.format(self.Strategy.trade_interval))
        for date in dates:
            val = self.step(date)
            yield val
