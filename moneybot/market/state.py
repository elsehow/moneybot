# -*- coding: utf-8 -*-
from datetime import datetime
from logging import getLogger
from typing import Dict
from typing import FrozenSet
from typing import Optional
from typing import Tuple


logger = getLogger(__name__)


class MarketState:
    '''
    TODO Docstring
    '''

    def __init__(
        self,
        chart_data: Dict[str, Dict[str, float]],
        balances: Dict[str, float],
        time: datetime,
        fiat: str,
    ) -> None:
        self.chart_data = chart_data
        self.balances = balances
        self.time = time
        self.fiat = fiat

    '''
    Private methods
    '''

    def _held_coins(self) -> FrozenSet[str]:
        return frozenset(
            coin for (coin, balance)
            in self.balances.items()
            if balance > 0
        )

    def _coin_names(self, market_name: str) -> Tuple[str, str]:
        base, quote = market_name.split('_', 1)
        return (base, quote)

    def _available_markets(self) -> FrozenSet[str]:
        return frozenset(
            filter(
                lambda market: market.startswith(self.fiat),
                self.chart_data.keys(),
            )
        )

    '''
    Public methods
    '''

    def balance(self, coin: str) -> float:
        '''
        Returns the quantity of a coin held.
        '''
        return self.balances[coin]

    def price(self, market: str, key='weighted_average') -> float:
        '''
        Returns the price of a market, in terms of the base asset.
        '''
        return self.chart_data[market][key]

    def only_holding(self, coin: str) -> bool:
        '''
        Returns true if the only thing we are holding is `coin`
        '''
        return self._held_coins() == {coin}

    def available_coins(self) -> FrozenSet[str]:
        markets = self._available_markets()  # All of these start with fiat
        return frozenset(self._coin_names(m)[1] for m in markets) | {self.fiat}

    def available_coins_not_held(self) -> FrozenSet[str]:
        return self.available_coins() - self._held_coins()

    def held_coins_with_chart_data(self) -> FrozenSet[str]:
        return self._held_coins() & self.available_coins()

    def estimate_value(
        self,
        coin: str,
        amount: float,
        reference_coin: str,
    ) -> Optional[float]:
        """Given `amount` of `coin`, estimate its value in terms of
        `reference_coin`.

        TODO: It would be super awesome if we could calculate this value across
        multiple hops, e.g. be able to tell the value of x ETH in BCH if we
        only have access to the markets BTC_ETH and BTC_BCH.
        """
        if coin == reference_coin:
            return amount

        chart_key = 'weighted_average'

        market = f'{reference_coin}_{coin}'
        if market in self.chart_data:
            reference_per_coin = self.chart_data[market][chart_key]
            return amount * reference_per_coin

        # We may have to flip the coins around to find the market
        market = f'{coin}_{reference_coin}'
        if market in self.chart_data:
            coin_per_reference = self.chart_data[market][chart_key]
            return amount / coin_per_reference

        logger.warning(
            f"Couldn't find a market for {reference_coin}:{coin}; has it been delisted?",
        )
        return None

    def estimate_values(
        self,
        balances: Dict[str, float],
        reference_coin: str,
    ) -> Dict[str, float]:
        """Return a dict mapping coin names to value in terms of the reference
        coin.
        """
        estimated_values = {}
        for coin, amount in balances.items():
            value = self.estimate_value(coin, amount, reference_coin)
            estimated_values[coin] = 0 if value is None else value
        return estimated_values

    def estimate_total_value(
        self,
        balances: Dict[str, float],
        reference_coin: str,
    ) -> float:
        """Calculate the total value of all holdings in terms of the reference
        coin.
        """
        return sum(self.estimate_values(balances, reference_coin).values())

    def estimate_total_value_usd(self, balances: Dict[str, float]) -> float:
        '''
        Returns the sum of all holding values, in USD.
        '''
        btc_val = self.estimate_total_value(balances, 'BTC')
        usd_val = btc_val * self.price('USD_BTC')
        return round(usd_val, 2)

    # TODO Not sure this really belongs here
    #       maybe more the job of BacktestMarketAdapter
    def simulate_trades(self, proposed_trades):
        '''
        TODO Docstring

        TODO State assumptions going into this simulation

        We can get fancier with this later,
        observe trends in actual trades we propose vs execute,
        and use that to make more realistic simulations~!
        (after all, our proposed price will not always be achievable)
        '''
        def simulate(proposed, new_balances):
            proposed = self.set_sell_amount(proposed)
            # TODO This makes sense as logic, but new_balances is confusing
            new_balances[proposed.sell_coin] -= proposed.sell_amount
            if proposed.buy_coin not in new_balances:
                new_balances[proposed.buy_coin] = 0
            est_trade_amt = proposed.sell_amount / proposed.price
            new_balances[proposed.buy_coin] += est_trade_amt
            return new_balances
        '''
        This method sanity-checks all proposed purchases,
        before shipping them off to the backtest / live-market.
        '''
        # TODO I hate copying this
        new_balances = self.balances.copy()
        new_proposed = proposed_trades.copy()
        for proposed in new_proposed:
            # Actually simulate purchase of the proposed trade
            # TODO I hate mutating stuff out of scope, so much
            new_balances = simulate(proposed, new_balances)

        return new_balances

    def estimate_price(self, trade):
        '''
        Sets the approximate price of the quote value, given some chart data.
        '''
        base_price = self.price(trade.market_name)
        # The price (when buying/selling)
        # should match the self.market_name.
        # So, we keep around a self.market_price to match
        # self.price is always in the quote currency.
        trade.market_price = base_price
        # Now, we find out what price matters for our trade.
        # The base price is always in the base currency,
        # So we will need to figure out if we are trading from,
        # or to, this base currency.
        if trade.buy_coin == trade.market_base_currency:
            trade.price = 1 / base_price
        else:
            trade.price = base_price
        return trade

    def set_sell_amount(
        self,
        trade,
    ):
        '''
        Sets `self.sell_amount`, `self.buy_amount`, `self.price`
        such that the proposed trade would leave us with a
        holding of `self.fiat_to_trade`.`
        '''
        trade = self.estimate_price(trade)
        if trade.sell_coin == trade.fiat:
            trade.sell_amount = trade.fiat_value_to_trade
        # If we are trying to buy fiat,
        elif trade.buy_coin == trade.fiat:
            # first we'll find the value of the coin we currently hold.
            current_value = self.balance(trade.sell_coin) * trade.price
            # To find how much coin we want to sell,
            # we'll subtract our holding's value from the ideal value
            # to produce the value of coin we must sell.
            value_to_sell = current_value - trade.fiat_value_to_trade
            # Now we find the amount of coin equal to this value.
            trade.sell_amount = value_to_sell / trade.price
            if trade.sell_amount < 0:
                trade.sell_amount = 0
        else:
            logger.warning('Proposing trade neither to nor from fiat', trade)
            raise
        # Figure out how much we will actually buy, account for fees
        inv_amt = trade.sell_amount - (trade.sell_amount * trade.fee)
        trade.buy_amount = inv_amt / trade.price
        return trade
