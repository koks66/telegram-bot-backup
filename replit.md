# Overview

This is a Telegram bot for cryptocurrency trading analysis that provides multi-timeframe technical analysis, automated market scanning, and AI-powered trading recommendations. The bot generates technical charts with trading levels, support/resistance zones, and provides entry/exit signals for various cryptocurrencies across different timeframes.

# Recent Changes (October 2025)

## Latest Update (October 8, 2025)
- **OCR Chart Recognition**: Added automatic recognition of cryptocurrency symbols and timeframes from chart screenshots using Tesseract OCR
- **Dark/Light Background Detection**: Intelligent background detection for better OCR accuracy on different chart themes
- **Gemini Vision Fallback**: Automatic fallback to Gemini 2.0 Flash Vision API when OCR fails
- **Caption Support**: Priority parsing of photo captions for quick manual symbol specification
- **Auto-Link Analysis**: TradingView links are now automatically analyzed without additional commands
- **Enhanced TradingView Parser**: Improved extraction of symbols and timeframes from complex TradingView URLs
- **Timeframe Validation**: Strict validation of timeframes (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M) to prevent invalid values
- **Improved Error Messages**: Clear messages when tokens are unavailable on exchanges with suggestions for popular alternatives

## Previous Updates
- **Fixed critical code errors**: Resolved matplotlib chart rendering issues with datetime conversion
- **API Integration**: Configured automatic fallback from Binance to MEXC API (due to regional restrictions)
- **Gemini AI**: Successfully integrated Google Gemini 2.0 Flash for market analysis
- **Workflow**: Bot running on port 5000 with Flask webhook system
- **All commands verified working**: /start, /help, /scan, /ftrade, /autogrid, coin analysis

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Bot Framework
- **Telegram Bot API Integration**: Core bot functionality built around Telegram's bot platform for user interaction
- **Command-Based Interface**: Structured command system with Russian and English language support
- **Persistent Menu System**: Auto-pinned help menus for quick access to bot functions

## Trading Analysis Engine
- **Multi-Timeframe Analysis**: Supports minute (1m-30m), hourly (1h-12h), daily (1d-3d), and weekly/monthly (1w-1M) timeframes
- **Technical Indicator Processing**: Automated calculation of entry points, stop-loss levels, take-profit targets, and support/resistance zones
- **Risk/Reward Calculation**: Built-in risk management analysis for trading recommendations

## Chart Generation System
- **Visual Chart Rendering**: Dynamic generation of technical analysis charts with colored indicators
- **Overlay System**: Multiple data layers including price action, technical levels, and trading signals
- **Real-time Data Processing**: Live market data integration for current price analysis

## Automated Scanning Module
- **Periodic Market Scanning**: 30-second interval automated scanning for trading opportunities
- **Opportunity Ranking**: Algorithm-based scoring system for identifying best trading setups
- **Real-time Notifications**: Push notifications for high-probability trading signals

## AI Analysis Component
- **Google Gemini 2.0 Flash**: AI-powered analysis combining technical indicators with market context
- **Context-Aware Recommendations**: Multi-factor evaluation for trading signals
- **Automated Coin Ranking**: AI-based scoring and ranking for scalping opportunities

# External Dependencies

## Market Data Sources
- **MEXC Exchange API**: Primary data source for real-time price data and historical klines (automatic fallback from Binance)
- **Binance API**: Secondary source (currently blocked in this region, error 451)
- **CoinGecko API**: Alternative source for trending coins and wide market coverage

## Chart Rendering Services
- **Technical Analysis Libraries**: Specialized libraries for calculating technical indicators and chart patterns
- **Image Generation Services**: Chart visualization and technical overlay rendering

## News and Sentiment APIs
- **Cryptocurrency News Aggregators**: Real-time news feed integration for market context
- **Sentiment Analysis Services**: Market sentiment data for comprehensive trading analysis

## Telegram Infrastructure
- **Telegram Bot API**: Core messaging and interaction platform
- **Message Management Services**: Auto-pinning, menu systems, and user session management