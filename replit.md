# Overview

This is a Telegram bot for cryptocurrency trading analysis that provides multi-timeframe technical analysis, automated market scanning, and AI-powered trading recommendations. The bot generates technical charts with trading levels, support/resistance zones, and provides entry/exit signals for various cryptocurrencies across different timeframes.

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
- **Context-Aware Recommendations**: AI-powered analysis combining technical indicators with market context
- **News Integration**: Correlation of trading signals with current cryptocurrency news and market sentiment
- **Multi-Factor Analysis**: Comprehensive evaluation including technical, fundamental, and sentiment factors

# External Dependencies

## Market Data Sources
- **Cryptocurrency Exchange APIs**: Real-time price data and historical market information
- **Market Data Providers**: Third-party services for comprehensive cryptocurrency market data

## Chart Rendering Services
- **Technical Analysis Libraries**: Specialized libraries for calculating technical indicators and chart patterns
- **Image Generation Services**: Chart visualization and technical overlay rendering

## News and Sentiment APIs
- **Cryptocurrency News Aggregators**: Real-time news feed integration for market context
- **Sentiment Analysis Services**: Market sentiment data for comprehensive trading analysis

## Telegram Infrastructure
- **Telegram Bot API**: Core messaging and interaction platform
- **Message Management Services**: Auto-pinning, menu systems, and user session management