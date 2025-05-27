import os

import logging

from datetime import datetime

import json

 

try:

    from avantis_trader_sdk import AvantisTrader as SDKTrader

except ImportError:

    logging.warning("Avantis SDK not found, using mock implementation")

    SDKTrader = None

 

class AvantisTrader:

    """Enhanced Avantis trading module with 4-position support and optimizations"""

   

    def __init__(self, private_key, rpc_url):

        self.private_key = private_key

        self.rpc_url = rpc_url

        self.usdc_address = os.getenv('USDC_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')

       

        # Initialize SDK if available

        if SDKTrader:

            try:

                self.sdk = SDKTrader(private_key, rpc_url)

                logging.info("✅ Avantis SDK initialized successfully")

            except Exception as e:

                logging.error(f"SDK initialization error: {str(e)}")

                self.sdk = None

        else:

            self.sdk = None

            logging.warning("Using mock implementation - deploy with proper SDK")

       

        # Enhanced tracking

        self.open_positions = {}

        self.position_counter = 0

   

    def get_balance(self):

        """Get USDC balance for position sizing"""

        try:

            if self.sdk:

                # Use SDK to get actual balance

                balance = self.sdk.get_usdc_balance()

                logging.info(f"Account balance: ${balance:.2f}")

                return balance

            else:

                # Mock balance for testing

                mock_balance = 1500.0

                logging.info(f"Mock balance: ${mock_balance:.2f}")

                return mock_balance

               

        except Exception as e:

            logging.error(f"Error getting balance: {str(e)}")

            return 1500.0  # Default balance

   

    def calculate_leverage(self, symbol):

        """Calculate optimal leverage based on asset type"""

        if 'BTC' in symbol or 'ETH' in symbol:

            return 6  # Conservative for major cryptos

        elif 'SOL' in symbol or 'AVAX' in symbol:

            return 5  # Slightly more conservative for altcoins

        else:

            return 5  # Default

   

    def open_position(self, trade_data):

        """

        Open position with enhanced parameters

       

        trade_data should contain:

        - symbol: Trading pair (e.g., 'BTC/USDT')

        - direction: 'LONG' or 'SHORT'

        - position_size: Dollar amount to trade

        - entry_price: Expected entry price

        - tp1_price, tp2_price, tp3_price: Take profit levels

        - stop_loss: Stop loss price

        - tier: Signal tier (1 or 2)

        - market_regime: 'BULL', 'BEAR', 'NEUTRAL', 'VOLATILE'

        """

        try:

            # Extract trade parameters

            symbol = trade_data.get('symbol', 'BTC/USDT')

            direction = trade_data.get('direction', 'LONG').upper()

            position_size = trade_data.get('position_size', 100)

            entry_price = trade_data.get('entry_price', 0)

           

            # Calculate leverage and collateral

            leverage = self.calculate_leverage(symbol)

            collateral = position_size / leverage

           

            # Generate position ID

            self.position_counter += 1

            position_id = f"AVANTIS_{symbol.replace('/', '')}_{self.position_counter}_{int(datetime.now().timestamp())}"

           

            logging.info(f"🚀 Opening {direction} position for {symbol}")

            logging.info(f"   Size: ${position_size:.2f}, Leverage: {leverage}x, Collateral: ${collateral:.2f}")

           

            if self.sdk:

                # Use real SDK for actual trading

                result = self._execute_real_trade(trade_data, leverage, collateral, position_id)

            else:

                # Mock execution for testing

                result = self._execute_mock_trade(trade_data, leverage, collateral, position_id)

           

            if result['success']:

                # Store position for tracking

                self.open_positions[position_id] = {

                    **trade_data,

                    'position_id': position_id,

                    'leverage': leverage,

                    'collateral': collateral,

                    'opened_at': datetime.now().isoformat(),

                    'status': 'OPEN'

                }

               

                logging.info(f"✅ Position {position_id} opened successfully")

           

            return result

           

        except Exception as e:

            logging.error(f"Error opening position: {str(e)}")

            return {

                'success': False,

                'error': str(e),

                'position_id': None

            }

   

    def _execute_real_trade(self, trade_data, leverage, collateral, position_id):

        """Execute trade using real Avantis SDK"""

        try:

            # Convert symbol format for SDK

            symbol_parts = trade_data['symbol'].split('/')

            base_asset = symbol_parts[0]

            quote_asset = symbol_parts[1]

           

            # SDK trade execution

            trade_result = self.sdk.open_position(

                market_id=self._get_market_id(base_asset),

                is_long=(trade_data['direction'].upper() == 'LONG'),

                collateral_amount=collateral,

                leverage=leverage,

                tp_levels=[

                    trade_data.get('tp1_price', 0),

                    trade_data.get('tp2_price', 0),

                    trade_data.get('tp3_price', 0)

                ],

                sl_price=trade_data.get('stop_loss', 0)

            )

           

            return {

                'success': True,

                'position_id': position_id,

                'actual_entry_price': trade_result.get('entry_price', trade_data['entry_price']),

                'transaction_hash': trade_result.get('tx_hash'),

                'collateral_used': collateral,

                'leverage': leverage

            }

           

        except Exception as e:

            logging.error(f"Real trade execution error: {str(e)}")

            return {

                'success': False,

                'error': f"SDK execution failed: {str(e)}",

                'position_id': None

            }

   

    def _execute_mock_trade(self, trade_data, leverage, collateral, position_id):

        """Mock trade execution for testing"""

        logging.info(f"🧪 MOCK TRADE EXECUTION:")

        logging.info(f"   Position ID: {position_id}")

        logging.info(f"   Symbol: {trade_data['symbol']}")

        logging.info(f"   Direction: {trade_data['direction']}")

        logging.info(f"   Entry Price: ${trade_data['entry_price']:.2f}")

        logging.info(f"   TP1: ${trade_data.get('tp1_price', 0):.2f}")

        logging.info(f"   TP2: ${trade_data.get('tp2_price', 0):.2f}")

        logging.info(f"   TP3: ${trade_data.get('tp3_price', 0):.2f}")

        logging.info(f"   Stop Loss: ${trade_data.get('stop_loss', 0):.2f}")

        logging.info(f"   Leverage: {leverage}x")

        logging.info(f"   Collateral: ${collateral:.2f}")

       

        # Simulate successful execution

        return {

            'success': True,

            'position_id': position_id,

            'actual_entry_price': trade_data['entry_price'],

            'transaction_hash': f"0xmock{position_id[-8:]}",

            'collateral_used': collateral,

            'leverage': leverage,

            'note': 'MOCK EXECUTION - Replace with real SDK in production'

        }

   

    def _get_market_id(self, asset):

        """Get Avantis market ID for asset"""

        market_ids = {

            'BTC': 1,

            'ETH': 2,

            'SOL': 15,  # Example market IDs

            'AVAX': 20

        }

        return market_ids.get(asset, 1)

   

    def close_position(self, position_id, close_type='MANUAL'):

        """Close a position"""

        try:

            if position_id not in self.open_positions:

                return {'success': False, 'error': 'Position not found'}

            

            position = self.open_positions[position_id]

           

            if self.sdk:

                # Use SDK to close position

                result = self.sdk.close_position(position_id)

            else:

                # Mock close

                result = {

                    'success': True,

                    'exit_price': position['entry_price'] * 1.02,  # Mock 2% profit

                    'pnl': position['position_size'] * 0.02,

                    'close_type': close_type

                }

           

            if result['success']:

                # Update position status

                self.open_positions[position_id]['status'] = 'CLOSED'

                self.open_positions[position_id]['closed_at'] = datetime.now().isoformat()

               

                logging.info(f"✅ Position {position_id} closed: {close_type}")

           

            return result

           

        except Exception as e:

            logging.error(f"Error closing position: {str(e)}")

            return {'success': False, 'error': str(e)}

   

    def get_open_positions(self):

        """Get all open positions"""

        return {k: v for k, v in self.open_positions.items() if v['status'] == 'OPEN'}

   

    def get_position_count(self):

        """Get number of open positions"""

        return len(self.get_open_positions())

   

    def can_open_position(self, max_positions=4):

        """Check if we can open another position"""

        return self.get_position_count() < max_positions

   

    def get_system_status(self):

        """Get comprehensive system status"""

        balance = self.get_balance()

        open_positions = self.get_open_positions()

       

        return {

            'balance': balance,

            'open_positions': len(open_positions),

            'max_positions': 4,

            'available_slots': 4 - len(open_positions),

            'sdk_connected': self.sdk is not None,

            'positions': list(open_positions.keys()),

            'last_updated': datetime.now().isoformat()

        }

 

# Utility functions for backward compatibility

def create_trader(private_key=None, rpc_url=None):

    """Create AvantisTrader instance with environment variables"""

    private_key = private_key or os.getenv('WALLET_PRIVATE_KEY')

    rpc_url = rpc_url or os.getenv('BASE_RPC_URL')

   

    if not private_key or not rpc_url:

        raise ValueError("Missing required environment variables: WALLET_PRIVATE_KEY, BASE_RPC_URL")

   

    return AvantisTrader(private_key, rpc_url)

 

# Export main class

__all__ = ['AvantisTrader', 'create_trader']

