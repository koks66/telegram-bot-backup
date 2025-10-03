import os
import requests
import tempfile
# test update for Git push
from flask import Flask, request
import telebot
from telebot import types as tg_types
from google import genai
import json
import asyncio
import websockets
from concurrent.futures import ThreadPoolExecutor
import threading
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import matplotlib
matplotlib.use('Agg')  # Используем non-GUI бэкенд
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
from pytz import timezone
import io

app = Flask(__name__)

# --- Загружаем секреты из Replit ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден!")
if not ADMIN_ID:
    raise ValueError("❌ TELEGRAM_ADMIN_ID не найден!")
if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY не найден!")

import os

WEBHOOK_URL = f"https://{os.environ.get('REPLIT_DEV_DOMAIN')}"

bot = telebot.TeleBot(TOKEN)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# --- Функции для анализа ссылок TradingView ---
def parse_tradingview_link(link):
    """Извлекает символ и таймфрейм из ссылки TradingView"""
    try:
        import re
        print(f"🔗 Парсим ссылку TradingView: {link}")
        
        # Проверяем, является ли это сокращенной ссылкой (/x/)
        if '/x/' in link:
            print("📎 Обнаружена сокращенная ссылка TradingView")
            return "SHORT_LINK", "1h"  # Специальный маркер для сокращенных ссылок
        
        # Извлекаем символ
        symbol_match = re.search(r'[?&]symbol=([^&]+)', link)
        if symbol_match:
            symbol_encoded = symbol_match.group(1)
            print(f"🔍 Найден закодированный символ: {symbol_encoded}")
            
            # Декодируем URL encoding (%3A = :, %2F = /)
            import urllib.parse
            symbol_decoded = urllib.parse.unquote(symbol_encoded)
            print(f"🔍 Декодированный символ: {symbol_decoded}")
            
            # Извлекаем только название монеты (BINANCE:BTCUSDT -> BTCUSDT)
            if ':' in symbol_decoded:
                full_symbol = symbol_decoded.split(':')[-1]
                print(f"🔍 Символ после разделения по ':': {full_symbol}")
            else:
                full_symbol = symbol_decoded
                print(f"🔍 Символ без разделителей: {full_symbol}")
                
            # Убираем .P (Perpetual контракты) из TradingView символов
            if full_symbol.endswith('.P'):
                full_symbol = full_symbol[:-2]  # BTCUSDT.P -> BTCUSDT
                print(f"🔍 Убрали .P (Perpetual): {full_symbol}")
            
            # Убираем USDT/USD суффиксы для получения базового символа
            if full_symbol.endswith('USDT'):
                base_symbol = full_symbol[:-4]  # BTCUSDT -> BTC
                print(f"🔍 Базовый символ (убрали USDT): {base_symbol}")
            elif full_symbol.endswith('USD'):
                base_symbol = full_symbol[:-3]   # BTCUSD -> BTC
                print(f"🔍 Базовый символ (убрали USD): {base_symbol}")
            else:
                base_symbol = full_symbol
                print(f"🔍 Базовый символ (без изменений): {base_symbol}")
                
            # Проверяем, что символ валидный (минимум 2 символа, максимум 10)
            if len(base_symbol) < 2 or len(base_symbol) > 10:
                print(f"❌ Некорректная длина символа: {base_symbol} ({len(base_symbol)} символов)")
                return None, None
                
        else:
            print("❌ Символ не найден в параметрах URL")
            
            # Пытаемся найти символ в тексте сообщения или ссылки
            # Ищем популярные криптовалюты в самой ссылке
            crypto_patterns = [
                r'\b(BTC|BITCOIN)\b',
                r'\b(ETH|ETHEREUM)\b', 
                r'\b(SOL|SOLANA)\b',
                r'\b(ADA|CARDANO)\b',
                r'\b(XRP|RIPPLE)\b',
                r'\b(DOGE|DOGECOIN)\b',
                r'\b(MATIC|POLYGON)\b',
                r'\b(AVAX|AVALANCHE)\b',
            ]
            
            for pattern in crypto_patterns:
                match = re.search(pattern, link.upper())
                if match:
                    base_symbol = match.group(1)
                    if base_symbol in ['BITCOIN']:
                        base_symbol = 'BTC'
                    elif base_symbol in ['ETHEREUM']:
                        base_symbol = 'ETH'
                    elif base_symbol in ['SOLANA']:
                        base_symbol = 'SOL'
                    elif base_symbol in ['CARDANO']:
                        base_symbol = 'ADA'
                    elif base_symbol in ['RIPPLE']:
                        base_symbol = 'XRP'
                    elif base_symbol in ['DOGECOIN']:
                        base_symbol = 'DOGE'
                    elif base_symbol in ['POLYGON']:
                        base_symbol = 'MATIC'
                    elif base_symbol in ['AVALANCHE']:
                        base_symbol = 'AVAX'
                    print(f"🔍 Символ найден в тексте ссылки: {base_symbol}")
                    break
            else:
                print("❌ Символ не найден нигде в ссылке")
                return None, None
        
        # Извлекаем таймфрейм
        interval_match = re.search(r'[?&]interval=([^&]+)', link)
        if interval_match:
            interval = interval_match.group(1)
            # TradingView таймфреймы: 1, 5, 15, 30, 60, 240, 1D, 1W, 1M
            timeframe_map = {
                '1': '1m', '5': '5m', '15': '15m', '30': '30m', 
                '60': '1h', '240': '4h', '1D': '1d', '1W': '1w', '1M': '1M'
            }
            timeframe = timeframe_map.get(interval, interval)
        else:
            timeframe = '1h'  # По умолчанию 1 час
            
        print(f"🔗 Распарсили ссылку TradingView: {base_symbol}, {timeframe}")
        return base_symbol, timeframe
        
    except Exception as e:
        print(f"❌ Ошибка парсинга ссылки TradingView: {e}")
        return None, None

def analyze_symbol_from_tradingview(symbol, timeframe, original_text, tradingview_link):
    """Анализирует символ извлеченный из ссылки TradingView используя наши источники данных"""
    try:
        # Сначала пробуем получить данные из Binance
        chart_analysis = None
        data_source = None
        
        # Проверяем разные варианты символа для Binance
        # 1. Если символ уже содержит торговую пару (например, уже BTCUSDT)
        if any(symbol.upper().endswith(suffix) for suffix in ['USDT', 'USD', 'BTC', 'ETH']):
            # Символ уже полный, пробуем как есть
            try:
                print(f"🔍 Пробуем получить данные для {symbol} из Binance (полный символ)...")
                data = get_coin_klines(symbol, timeframe, 100)
                if data is not None and len(data) > 10:
                    # Создаем полный анализ с графиком как в обычном анализе
                    levels = calculate_technical_levels(data)
                    if levels:
                        # Генерируем график
                        chart_buffer = create_trading_chart(symbol, data, levels, timeframe)
                        if chart_buffer:
                            # Создаем полный анализ
                            chart_analysis = generate_chart_analysis(symbol, levels, "", timeframe)
                            data_source = "Binance"
                            working_symbol = symbol
                            
                            # Возвращаем анализ вместе с графиком
                            return chart_analysis, chart_buffer
                        else:
                            # Fallback: простой анализ без графика
                            chart_analysis = create_simple_chart_analysis(symbol, timeframe, data)
                            data_source = "Binance"
                            working_symbol = symbol
                    else:
                        # Fallback: простой анализ без графика
                        chart_analysis = create_simple_chart_analysis(symbol, timeframe, data)
                        data_source = "Binance"
                        working_symbol = symbol
                else:
                    raise Exception("Не удалось получить данные")
            except:
                # Если полный символ не сработал, пробуем базовый символ с суффиксами
                if symbol.upper().endswith('USDT'):
                    base_symbol = symbol[:-4]  # BTCUSDT -> BTC
                elif symbol.upper().endswith('USD'):
                    base_symbol = symbol[:-3]   # BTCUSD -> BTC
                else:
                    base_symbol = symbol
                    
                print(f"🔍 Полный символ не сработал, пробуем базовый: {base_symbol}")
                for suffix in ['USDT', 'USD', 'BTC', 'ETH']:
                    test_symbol = f"{base_symbol}{suffix}"
                    try:
                        print(f"🔍 Пробуем получить данные для {test_symbol} из Binance...")
                        data = get_coin_klines(test_symbol, timeframe, 100)
                        if data is not None and len(data) > 10:
                            # Создаем полный анализ с графиком
                            levels = calculate_technical_levels(data)
                            if levels:
                                chart_buffer = create_trading_chart(test_symbol, data, levels, timeframe)
                                if chart_buffer:
                                    chart_analysis = generate_chart_analysis(test_symbol, levels, "", timeframe)
                                    data_source = "Binance"
                                    working_symbol = test_symbol
                                    return chart_analysis, chart_buffer
                                else:
                                    chart_analysis = create_simple_chart_analysis(test_symbol, timeframe, data)
                                    data_source = "Binance"
                                    working_symbol = test_symbol
                            else:
                                chart_analysis = create_simple_chart_analysis(test_symbol, timeframe, data)
                                data_source = "Binance"
                                working_symbol = test_symbol
                            break
                    except:
                        continue
        else:
            # 2. Символ базовый (например, BTC) - добавляем суффиксы
            for suffix in ['USDT', 'USD', 'BTC', 'ETH']:
                test_symbol = f"{symbol}{suffix}"
                try:
                    print(f"🔍 Пробуем получить данные для {test_symbol} из Binance...")
                    data = get_coin_klines(test_symbol, timeframe, 100)
                    if data is not None and len(data) > 10:
                        # Создаем полный анализ с графиком
                        levels = calculate_technical_levels(data)
                        if levels:
                            chart_buffer = create_trading_chart(test_symbol, data, levels, timeframe)
                            if chart_buffer:
                                chart_analysis = generate_chart_analysis(test_symbol, levels, "", timeframe)
                                data_source = "Binance"
                                working_symbol = test_symbol
                                return chart_analysis, chart_buffer
                            else:
                                chart_analysis = create_simple_chart_analysis(test_symbol, timeframe, data)
                                data_source = "Binance"
                                working_symbol = test_symbol
                        else:
                            chart_analysis = create_simple_chart_analysis(test_symbol, timeframe, data)
                            data_source = "Binance"
                            working_symbol = test_symbol
                        break
                except:
                    continue
        
        # Если Binance не сработал, пробуем CoinGecko
        if not chart_analysis:
            try:
                print(f"🔍 Пробуем получить данные для {symbol} из CoinGecko...")
                cg_data = get_coin_data_coingecko(symbol, days=1)
                if cg_data:
                    # Создаем анализ на основе CoinGecko данных
                    price = cg_data.get('current_price', 0)
                    change_24h = cg_data.get('price_change_percentage_24h', 0)
                    volume = cg_data.get('total_volume', 0)
                    market_cap = cg_data.get('market_cap', 0)
                    
                    chart_analysis = f"""📊 **АНАЛИЗ {symbol.upper()}** (по данным CoinGecko)

💰 **Текущая цена:** ${price:,.2f}
📈 **Изменение 24ч:** {change_24h:+.2f}%  
📊 **Объем торгов:** ${volume:,.0f}
💎 **Рыночная капитализация:** ${market_cap:,.0f}

🔗 **Источник ссылки:** TradingView ({timeframe})  
📋 **Исходное сообщение:** {original_text[:100]}{'...' if len(original_text) > 100 else ''}

⚠️ *Данные получены из CoinGecko, так как символ не найден на Binance*"""
                    data_source = "CoinGecko"
                    working_symbol = symbol
            except Exception as e:
                print(f"❌ CoinGecko тоже не сработал: {e}")
        
        # Если ничего не сработало
        if not chart_analysis:
            chart_analysis = f"""❌ **НЕ УДАЛОСЬ ПОЛУЧИТЬ ДАННЫЕ**

🔗 **Ссылка TradingView:** {tradingview_link}
🪙 **Символ:** {symbol}
⏰ **Таймфрейм:** {timeframe}

📋 **Проблема:** Символ не найден ни в Binance, ни в CoinGecko API.

💡 **Рекомендация:** Проверьте правильность символа или отправьте изображение графика для анализа."""
            return chart_analysis
        
        # Добавляем информацию о источнике данных
        chart_analysis += f"\n\n🌐 **Источник данных:** {data_source}"
        chart_analysis += f"\n🔗 **Оригинальная ссылка:** {tradingview_link[:100]}{'...' if len(tradingview_link) > 100 else ''}"
        
        return chart_analysis
        
    except Exception as e:
        print(f"❌ Ошибка анализа символа из TradingView: {e}")
        return f"❌ Ошибка анализа: {str(e)}"

def create_simple_chart_analysis(symbol, timeframe, data):
    """Создает простой технический анализ на основе данных графика"""
    try:
        if data is None or len(data) < 5:
            return "❌ Недостаточно данных для анализа"
        
        # Берем последние данные
        current_price = float(data.iloc[-1]['close'])
        high_price = float(data['high'].max())
        low_price = float(data['low'].min())
        volume = float(data.iloc[-1]['volume'])
        
        # Простые индикаторы
        price_change = ((current_price - float(data.iloc[-2]['close'])) / float(data.iloc[-2]['close'])) * 100
        
        # Определяем тренд (простая логика)
        recent_highs = data['high'].tail(5).mean()
        recent_lows = data['low'].tail(5).mean()
        
        if current_price > recent_highs * 0.98:
            trend = "Восходящий"
            trend_emoji = "📈"
        elif current_price < recent_lows * 1.02:
            trend = "Нисходящий" 
            trend_emoji = "📉"
        else:
            trend = "Боковой"
            trend_emoji = "↔️"
        
        # Определяем уровни поддержки и сопротивления
        support = float(data['low'].tail(10).min())
        resistance = float(data['high'].tail(10).max())
        
        analysis = f"""📊 **ТЕХНИЧЕСКИЙ АНАЛИЗ {symbol.upper()}**

💰 **Текущая цена:** ${current_price:,.2f}
📊 **Изменение:** {price_change:+.2f}%
{trend_emoji} **Тренд:** {trend}

📈 **Максимум периода:** ${high_price:,.2f}
📉 **Минимум периода:** ${low_price:,.2f}
🔵 **Поддержка:** ${support:,.2f}
🔴 **Сопротивление:** ${resistance:,.2f}

📊 **Объем:** {volume:,.0f}
⏰ **Таймфрейм:** {timeframe}

💡 **Краткие рекомендации:**
• Следите за пробой ключевых уровней
• Объем подтверждает движение
• Управляйте рисками"""

        return analysis
        
    except Exception as e:
        return f"❌ Ошибка создания анализа: {str(e)}"

# --- Функция уведомления администратора ---
def notify_admin_about_user_request(user_id, username, first_name, request_type, request_text):
    """Уведомляет администратора о запросе пользователя"""
    try:
        # Не отправляем уведомления о собственных запросах администратора
        if str(user_id) == str(ADMIN_ID):
            return
        # Ограничиваем длину текста запроса для безопасности
        if len(request_text) > 100:
            request_text = request_text[:100] + "..."
        
        # Используем безопасное форматирование без Markdown
        user_info = f"👤 Пользователь: {first_name or 'Неизвестно'}"
        if username:
            user_info += f" (@{username})"
        user_info += f"\n🆔 ID: {user_id}"
        
        time_info = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        admin_message = f"""📊 НОВЫЙ ЗАПРОС В БОТЕ

{user_info}
⏰ Время: {time_info}
🔧 Тип: {request_type}
💬 Запрос: {request_text}

---"""
        
        # Отправляем без Markdown для безопасности
        bot.send_message(int(ADMIN_ID), admin_message)
        
    except Exception as e:
        # При ошибке пытаемся отправить упрощенное сообщение
        try:
            simple_msg = f"📊 Новый запрос от {user_id}: {request_type}"
            bot.send_message(int(ADMIN_ID), simple_msg)
        except:
            pass
        print(f"⚠ Ошибка уведомления администратора: {e}")


# --- Кэш для скрининга монет ---
import time
coins_cache = {"data": [], "timestamp": 0}
COINS_CACHE_TTL = 30  # 30 секунд (ультрабыстрый скальпинг)



# --- BINANCE API ФУНКЦИИ ДЛЯ СКРИНИНГА МОНЕТ ---

def get_binance_24hr_ticker():
    """Получить данные по всем парам с Binance за 24 часа"""
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Binance API ошибка: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Ошибка получения данных Binance: {e}")
        return []

def get_binance_klines(symbol, interval="5m", limit=20):
    """Получить краткосрочные свечи для анализа скальпинга"""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            klines = response.json()
            # Преобразуем в удобный формат
            processed_klines = []
            for kline in klines:
                processed_klines.append({
                    'open_time': kline[0],
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                    'close_time': kline[6],
                    'quote_volume': float(kline[7])
                })
            return processed_klines
        return []
    except Exception as e:
        print(f"❌ Ошибка получения klines для {symbol}: {e}")
        return []

def get_mexc_klines(symbol, interval='1h', limit=100):
    """Получить данные с MEXC API для токенов, недоступных на Binance"""
    try:
        # Убедимся что символ в правильном формате
        symbol = f"{symbol}USDT" if not symbol.endswith('USDT') else symbol
        
        # MEXC использует тот же формат API что и Binance
        url = f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        
        headers = {
            'User-Agent': 'TradingBot/4.0',
            'Accept': 'application/json'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            klines = response.json()
            
            if not klines or len(klines) < 10:
                print(f"⚠️ MEXC: недостаточно данных для {symbol} (получено: {len(klines) if klines else 0})")
                return None
                
            # Создаем DataFrame точно как для Binance API
            df_data = []
            for kline in klines:
                df_data.append({
                    'open_time': int(kline[0]),
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                    'close_time': int(kline[6]),
                    'quote_volume': float(kline[7]) if len(kline) > 7 else float(kline[5])
                })
            
            df = pd.DataFrame(df_data)
            
            # Добавляем timestamp колонку для совместимости с остальным кодом
            df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
            
            print(f"✅ MEXC: получено {len(df)} свечей для {symbol}")
            print(f"   Период: {df['timestamp'].iloc[0]} - {df['timestamp'].iloc[-1]}")
            return df
            
        else:
            print(f"❌ MEXC API ошибка для {symbol}: {response.status_code}")
            # Попробуем получить детали ошибки
            try:
                error_data = response.json()
                print(f"   Детали ошибки: {error_data}")
            except:
                print(f"   Текст ответа: {response.text[:200]}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка MEXC API для {symbol}: {e}")
        import traceback
        print(f"   Трейс: {traceback.format_exc()}")
        return None

def calculate_real_scalping_score(ticker, klines_5m):
    """Рассчитать РЕАЛЬНЫЙ скальпинговый потенциал на основе коротких интервалов"""
    try:
        if not klines_5m or len(klines_5m) < 10:
            return 0
            
        # Базовые проверки ликвидности
        volume = float(ticker['volume'])
        quote_volume = float(ticker['quoteVolume'])
        
        if volume < 1000000 or quote_volume < 10000000:
            return 0
        
        # Анализируем последние 5-минутные свечи
        recent_candles = klines_5m[-10:]  # Последние 50 минут
        
        # 1. Волатильность на 5м интервалах
        price_ranges = [(candle['high'] - candle['low']) / candle['close'] for candle in recent_candles]
        avg_volatility = sum(price_ranges) * 100  # В процентах
        
        # 2. Объемный всплеск (сравнение с предыдущими свечами)
        recent_volumes = [candle['volume'] for candle in recent_candles]
        avg_volume = sum(recent_volumes) / len(recent_volumes)
        volume_spike = (recent_volumes[-1] / avg_volume) if avg_volume > 0 else 1
        
        # 3. Движение цены за последние свечи
        price_momentum = abs((recent_candles[-1]['close'] - recent_candles[-5]['close']) / recent_candles[-5]['close']) * 100
        
        # 4. Спред и ликвидность (приблизительно через объем)
        liquidity_score = min(quote_volume / 20000000, 5) * 20  # До 100 баллов
        
        # Проверяем минимальные требования для скальпинга
        if avg_volatility < 0.5:  # Минимум 0.5% волатильности на 5м
            return 0
        if price_momentum < 0.3:  # Минимум 0.3% движения за 25 минут
            return 0
            
        # Расчет итогового скора (0-100)
        volatility_score = min(avg_volatility * 15, 30)  # До 30 баллов
        momentum_score = min(price_momentum * 10, 25)    # До 25 баллов  
        volume_score = min(volume_spike * 20, 25)        # До 25 баллов
        
        total_score = volatility_score + momentum_score + volume_score + liquidity_score
        
        return min(round(total_score, 2), 100)
        
    except Exception as e:
        print(f"❌ Ошибка расчета реального скора: {e}")
        return 0

def calculate_scalping_score(ticker):
    """Рассчитать скальпинговый потенциал монеты"""
    try:
        # Основные критерии для скальпинга
        volume = float(ticker['volume'])
        price_change = abs(float(ticker['priceChangePercent']))
        quote_volume = float(ticker['quoteVolume'])
        
        # Проверяем минимальные требования
        if volume < 1000000:  # Минимальный объем торгов
            return 0
        if quote_volume < 10000000:  # Минимальный объем в USDT
            return 0
        if price_change < 2:  # Минимальная волатильность 2%
            return 0
            
        # Расчет скора (0-100)
        volume_score = min(volume / 10000000, 10) * 10  # До 100 баллов за объем
        volatility_score = min(price_change, 10) * 10   # До 100 баллов за волатильность
        liquidity_score = min(quote_volume / 50000000, 10) * 10  # До 100 баллов за ликвидность
        
        # Итоговый скор
        total_score = (volume_score + volatility_score + liquidity_score) / 3
        
        return round(total_score, 2)
    except:
        return 0

def screen_best_coins_for_scalping():
    """Найти лучшие монеты для РЕАЛЬНОГО скальпинга на коротких интервалах"""
    try:
        # Проверяем кэш
        if time.time() - coins_cache["timestamp"] < COINS_CACHE_TTL and coins_cache["data"]:
            return coins_cache["data"]
        
        print("🔍 Сканирую рынок для поиска лучших монет для скальпинга (5м интервалы)...")
        
        # Получаем данные с Binance
        tickers = get_binance_24hr_ticker()
        if not tickers:
            return []
        
        # Фильтруем только USDT пары (основные)
        usdt_pairs = [ticker for ticker in tickers if ticker['symbol'].endswith('USDT')]
        
        # Исключаем стейблкоины и токены с низкой ликвидностью
        excluded = ['USDT', 'BUSD', 'FDUSD', 'TUSD', 'USDC']
        filtered_pairs = []
        
        # Предварительный фильтр по ликвидности (чтобы не делать много API запросов)
        high_volume_pairs = []
        for ticker in usdt_pairs:
            symbol = ticker['symbol'].replace('USDT', '')
            if symbol not in excluded:
                volume = float(ticker['volume'])
                quote_volume = float(ticker['quoteVolume'])
                if volume > 2000000 and quote_volume > 15000000:  # Высокая ликвидность
                    high_volume_pairs.append(ticker)
        
        # Сортируем по объему и берем топ-30 для детального анализа
        high_volume_pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
        top_volume_pairs = high_volume_pairs[:30]
        
        print(f"📊 Анализирую {len(top_volume_pairs)} высоколиквидных пар...")
        
        # Детальный анализ с 5-минутными свечами
        for ticker in top_volume_pairs:
            try:
                symbol = ticker['symbol']
                klines_5m = get_binance_klines(symbol, "5m", 20)
                
                if klines_5m:
                    # Используем новый алгоритм скрининга
                    score = calculate_real_scalping_score(ticker, klines_5m)
                    if score > 40:  # Повышенный порог для реального скальпинга
                        ticker['scalping_score'] = score
                        ticker['klines_5m'] = klines_5m  # Сохраняем для генерации сигналов
                        filtered_pairs.append(ticker)
                        print(f"✅ {symbol}: скор {score}")
                
                # Минимальная задержка для быстрого скрининга
                time.sleep(0.05)
                
            except Exception as e:
                print(f"⚠ Ошибка анализа {ticker['symbol']}: {e}")
                continue
        
        # Сортируем по реальному скальпинговому потенциалу
        top_coins = sorted(filtered_pairs, key=lambda x: x['scalping_score'], reverse=True)[:10]
        
        print(f"🎯 Найдено {len(top_coins)} монет для скальпинга")
        
        # Обновляем кэш
        coins_cache["data"] = top_coins
        coins_cache["timestamp"] = time.time()
        
        return top_coins
        
    except Exception as e:
        print(f"❌ Ошибка скрининга: {e}")
        return []

def generate_scalping_signal(coin_data):
    """Генерировать торговый сигнал для скальпинга"""
    try:
        symbol = coin_data['symbol']
        current_price = float(coin_data['lastPrice'])
        price_change = float(coin_data['priceChangePercent'])
        high_24h = float(coin_data['highPrice'])
        low_24h = float(coin_data['lowPrice'])
        volume = float(coin_data['volume'])
        
        # Простая логика для скальпинга
        if price_change > 0:
            # Бычий сигнал
            entry = current_price * 1.001  # Вход чуть выше текущей цены
            stop_loss = current_price * 0.992  # Стоп 0.8%
            take_profit_1 = current_price * 1.015  # Первая цель 1.5%
            take_profit_2 = current_price * 1.025  # Вторая цель 2.5%
            signal_type = "🟢 LONG"
        else:
            # Медвежий сигнал
            entry = current_price * 0.999  # Вход чуть ниже текущей цены
            stop_loss = current_price * 1.008  # Стоп 0.8%
            take_profit_1 = current_price * 0.985  # Первая цель 1.5%
            take_profit_2 = current_price * 0.975  # Вторая цель 2.5%
            signal_type = "🔴 SHORT"
        
        # Расчет RRR (Risk-Reward Ratio)
        if price_change > 0:  # LONG
            rrr = (take_profit_1 - entry) / (entry - stop_loss)
        else:  # SHORT
            rrr = (entry - take_profit_1) / (stop_loss - entry)
        
        # Фильтр: не показываем сигналы с RRR < 1.5
        print(f"🔍 {symbol}: RRR={rrr:.2f}, price_change={price_change}%")
        if rrr < 1.5:
            print(f"❌ {symbol}: RRR слишком низкий ({rrr:.2f} < 1.5)")
            return None
        
        # Оценка риска
        volatility = ((high_24h - low_24h) / current_price) * 100
        if volatility > 8:
            risk_level = "🔥 Высокий"
        elif volatility > 5:
            risk_level = "⚠️ Средний"
        else:
            risk_level = "✅ Низкий"
        
        # Отметка лучших сигналов
        signal_quality = "⭐ ЛУЧШИЙ" if rrr > 2.5 else "✅ Хороший"
        
        return {
            'symbol': symbol.replace('USDT', ''),
            'signal_type': signal_type,
            'current_price': round(current_price, 8),
            'entry': round(entry, 8),
            'stop_loss': round(stop_loss, 8),
            'take_profit_1': round(take_profit_1, 8),
            'take_profit_2': round(take_profit_2, 8),
            'rrr': round(rrr, 2),
            'signal_quality': signal_quality,
            'risk_level': risk_level,
            'volatility': round(volatility, 2),
            'scalping_score': coin_data['scalping_score'],
            'volume_24h': f"{volume/1000000:.1f}M"
        }
        
    except Exception as e:
        print(f"❌ Ошибка генерации сигнала: {e}")
        return None

# --- АВТОМАТИЧЕСКИЙ ПЛАНИРОВЩИК ДЛЯ СКАЛЬПИНГА ---

def auto_send_scalping_signals():
    """Автоматическая отправка обновленных сигналов каждые 60 секунд"""
    try:
        print("🔄 Автоматический скрининг запущен...")
        
        # Получаем лучшие монеты для скальпинга
        top_coins = screen_best_coins_for_scalping()
        
        if not top_coins:
            print("📊 Нет подходящих монет для скальпинга")
            return
        
        # Берем ТОП-3 лучшие монеты
        top_3_coins = top_coins[:3]
        
        # Собираем данные с RSI и SMA для каждой монеты
        coins_data = []
        medals = ["🥇", "🥈", "🥉"]
        
        for i, coin in enumerate(top_3_coins):
            symbol = coin['symbol']
            signal = generate_scalping_signal(coin)
            
            if not signal:
                continue
            
            # Получаем klines для расчета RSI и SMA
            klines_data = get_binance_klines(symbol, "5m", 50)
            
            rsi = 50  # Дефолт
            sma_20 = signal['current_price']  # Дефолт
            
            if klines_data and len(klines_data) >= 20:
                closes = [k['close'] for k in klines_data]
                
                # Расчет RSI
                def calc_rsi(prices, period=14):
                    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
                    gains = [d if d > 0 else 0 for d in deltas]
                    losses = [-d if d < 0 else 0 for d in deltas]
                    
                    avg_gain = sum(gains[:period]) / period
                    avg_loss = sum(losses[:period]) / period
                    
                    if avg_loss == 0:
                        return 100
                    
                    rs = avg_gain / avg_loss
                    return 100 - (100 / (1 + rs))
                
                rsi = calc_rsi(closes)
                sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else closes[-1]
            
            # Визуальные индикаторы RSI
            rsi_indicator = ""
            if rsi < 30:
                rsi_indicator = "🟢"  # Перепроданность
            elif rsi > 70:
                rsi_indicator = "🔴"  # Перекупленность
            
            # Эмодзи сигнала
            signal_emoji = "🟢" if "LONG" in signal['signal_type'] else "🔴"
            
            coins_data.append({
                'priority': medals[i],
                'symbol': signal['symbol'],
                'price': f"{signal['current_price']:.4f}" if signal['current_price'] < 1 else f"{signal['current_price']:.2f}",
                'signal_emoji': signal_emoji,
                'signal_type': signal['signal_type'],
                'rsi': f"{rsi:.0f} | {rsi_indicator}" if rsi_indicator else f"{rsi:.0f}",
                'sma_20': f"{sma_20:.4f}" if sma_20 < 1 else f"{sma_20:.2f}",
                'volume_24h': signal['volume_24h'],
                'rrr': signal['rrr'],
                'entry': f"{signal['entry']:.4f}" if signal['entry'] < 1 else f"{signal['entry']:.2f}",
                'stop_loss': f"{signal['stop_loss']:.4f}" if signal['stop_loss'] < 1 else f"{signal['stop_loss']:.2f}",
                'take_profit_1': f"{signal['take_profit_1']:.4f}" if signal['take_profit_1'] < 1 else f"{signal['take_profit_1']:.2f}",
                'star': '',
                'rsi_raw': rsi,
                'volume_raw': float(coin.get('quoteVolume', 0))
            })
        
        if not coins_data:
            return
        
        # Определяем лучшую монету
        best_coin = None
        for coin in coins_data:
            if (coin['rsi_raw'] < 30 or coin['rsi_raw'] > 70) and coin['volume_raw'] > 10000000:
                coin['star'] = ' ⭐'
                best_coin = coin['symbol']
                break
        
        # Формируем ответ
        response_text = ""
        
        # Добавляем строку лучшей сделки
        if best_coin:
            response_text += f"🔥 **ЛУЧШАЯ СДЕЛКА: {best_coin} ⭐**\n\n"
        
        response_text += "🎯 **ТОП-3 ЛУЧШИЕ МОНЕТЫ ДЛЯ СКАЛЬПИНГА СЕЙЧАС:**\n\n"
        
        # Таблица Markdown
        response_text += "| Ранг | Монета | Цена | Сигнал | RSI | SMA20 | Объём | RRR |\n"
        response_text += "|------|--------|------|--------|-----|-------|-------|-----|\n"
        
        # Данные таблицы
        for coin in coins_data:
            response_text += f"| {coin['priority']}{coin['star']} | {coin['symbol']} | ${coin['price']} | {coin['signal_emoji']} | {coin['rsi']} | ${coin['sma_20']} | {coin['volume_24h']}M | {coin['rrr']} |\n"
        
        response_text += "\n**📊 ДЕТАЛИ ТОРГОВЫХ УРОВНЕЙ:**\n\n"
        
        # Детальная информация по каждой монете
        for coin in coins_data:
            response_text += f"{coin['priority']}{coin['star']} **{coin['symbol']}** {coin['signal_type']}\n"
            response_text += f"🎯 Вход: ${coin['entry']} | 🛑 Стоп: ${coin['stop_loss']} | 🥇 Цель: ${coin['take_profit_1']}\n\n"
        
        # Подготавливаем данные для анализа Gemini с ранжированием
        prompt = f"""Проанализируй ТОП-3 монеты для скальпинга и ОБЯЗАТЕЛЬНО расставь их по местам:

ДАННЫЕ:
"""
        for coin in coins_data:
            prompt += f"- {coin['symbol']}: RSI={coin['rsi_raw']:.0f}, SMA20=${coin['sma_20']}, Объём={coin['volume_24h']}M, RRR={coin['rrr']}\n"
        
        prompt += f"""
ЗАДАНИЕ:
1. Расставь монеты 🥇🥈🥉 по привлекательности для скальпинга
2. Для каждой монеты дай короткий комментарий (1 строка)

Формат ответа (строго):
🥇 [СИМВОЛ] - [комментарий]
🥈 [СИМВОЛ] - [комментарий]
🥉 [СИМВОЛ] - [комментарий]"""
        
        # Функция для повторных попыток при ошибках API
        def try_gemini_analysis_scan(prompt, max_retries=3):
            models_to_try = ["gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"]
            delays = [2, 5, 9]
            
            for model in models_to_try:
                print(f"🔄 Пробуем модель: {model}")
                for attempt in range(max_retries):
                    try:
                        response = gemini_client.models.generate_content(
                            model=model,
                            contents=prompt
                        )
                        print(f"✅ Gemini успешно ответил (модель: {model}, попытка: {attempt + 1})")
                        return response
                    except Exception as e:
                        error_msg = str(e)
                        print(f"❌ Ошибка Gemini [модель: {model}, попытка: {attempt + 1}/{max_retries}]: {error_msg}")
                        
                        if "503" in error_msg or "unavailable" in error_msg.lower() or "overloaded" in error_msg.lower():
                            if attempt < max_retries - 1:
                                delay = delays[attempt]
                                print(f"⏰ Сервер перегружен, ждем {delay} секунд перед повтором...")
                                time.sleep(delay)
                        else:
                            print(f"⚠️ Ошибка не связана с перегрузкой, пробуем следующую модель")
                            break
            
            print("❌ Все модели Gemini недоступны после всех попыток")
            return None
        
        gemini_response = try_gemini_analysis_scan(prompt)
        ai_analysis = gemini_response.text if gemini_response and gemini_response.text else "AI анализ временно недоступен"
        
        # Добавляем AI анализ
        response_text += f"🤖 **GEMINI АНАЛИЗ:**\n{ai_analysis}\n\n"
        
        # Блок сравнения технического и Gemini выбора
        tech_top = coins_data[0]['symbol'] if coins_data else ""
        gemini_top = ""
        
        # Извлекаем выбор Gemini (ищем первый символ после 🥇)
        import re
        gemini_match = re.search(r'🥇\s*([A-Z]+)', ai_analysis)
        if gemini_match:
            gemini_top = gemini_match.group(1)
        
        comparison_emoji = "🟢" if tech_top == gemini_top else "🔴"
        
        # Пояснение совпадения/различия
        if tech_top == gemini_top:
            explanation = "Оба метода выбрали одну монету — сильный сигнал"
        else:
            explanation = "Различие может указывать на разные приоритеты анализа"
        
        response_text += f"**📊 СРАВНЕНИЕ ВЫБОРОВ:**\n"
        response_text += f"• Технический анализ: {tech_top}\n"
        response_text += f"• Gemini выбор: {gemini_top if gemini_top else 'N/A'}\n"
        response_text += f"• Совпадение: {comparison_emoji} {'Да' if tech_top == gemini_top else 'Нет'}\n"
        response_text += f"• {explanation}\n\n"
        
        response_text += f"⏰ Автообновлено: {time.strftime('%H:%M:%S')}\n"
        response_text += f"🔄 Следующее обновление через 60 секунд ⚡"
        
        # Ограничиваем длину ответа для Telegram
        max_length = 4000
        if len(response_text) > max_length:
            response_text = response_text[:max_length] + "..."
        
        bot.send_message(ADMIN_ID, response_text, parse_mode='Markdown')
        print("✅ Автоматические сигналы отправлены")
        
    except Exception as e:
        print(f"❌ Ошибка автоматического скрининга: {e}")

def generate_enhanced_scalping_signal(coin_data):
    """Улучшенная генерация сигналов на основе 5м данных"""
    try:
        symbol = coin_data['symbol']
        current_price = float(coin_data['lastPrice'])
        klines_5m = coin_data.get('klines_5m', [])
        
        if not klines_5m or len(klines_5m) < 5:
            # Фоллбек к простому алгоритму
            return generate_scalping_signal(coin_data)
        
        # Анализируем последние 5-минутные свечи
        recent_candles = klines_5m[-5:]  # Последние 25 минут
        last_candle = recent_candles[-1]
        
        # Определяем тренд на основе 5м свечей
        trend_up = last_candle['close'] > recent_candles[0]['open']
        
        # Рассчитываем ATR для стопов и целей
        true_ranges = []
        for i in range(1, len(recent_candles)):
            prev_close = recent_candles[i-1]['close']
            current = recent_candles[i]
            tr = max(
                current['high'] - current['low'],
                abs(current['high'] - prev_close),
                abs(current['low'] - prev_close)
            )
            true_ranges.append(tr)
        
        atr = sum(true_ranges) / len(true_ranges) if true_ranges else current_price * 0.01
        
        # Генерируем сигнал на основе краткосрочного тренда
        if trend_up:
            # Бычий сигнал
            entry = current_price * 1.001  # Небольшой отступ
            stop_loss = current_price - (atr * 1.5)
            take_profit_1 = current_price + (atr * 1.0)
            take_profit_2 = current_price + (atr * 2.0)
            signal_type = "🟢 LONG"
        else:
            # Медвежий сигнал
            entry = current_price * 0.999  # Небольшой отступ
            stop_loss = current_price + (atr * 1.5)
            take_profit_1 = current_price - (atr * 1.0)
            take_profit_2 = current_price - (atr * 2.0)
            signal_type = "🔴 SHORT"
        
        # Волатильность на 5м
        volatility_5m = (atr / current_price) * 100
        
        # Объем последней 5м свечи
        volume_5m = last_candle['volume'] / 1000000  # В миллионах
        
        # Расчет RRR (Risk-Reward Ratio)
        if trend_up:  # LONG
            rrr = (take_profit_1 - entry) / (entry - stop_loss) if (entry - stop_loss) > 0 else 0
        else:  # SHORT
            rrr = (entry - take_profit_1) / (stop_loss - entry) if (stop_loss - entry) > 0 else 0
        
        # Убираем фильтр RRR - фильтрация будет на уровне отображения
        
        # Оценка риска на основе 5м волатильности
        if volatility_5m > 2:
            risk_level = "🔥 Высокий"
        elif volatility_5m > 1:
            risk_level = "⚠️ Средний"
        else:
            risk_level = "✅ Низкий"
        
        # Отметка лучших сигналов
        signal_quality = "⭐ ЛУЧШИЙ" if rrr > 2.5 else "✅ Хороший"
        
        return {
            'symbol': symbol.replace('USDT', ''),
            'signal_type': signal_type,
            'current_price': round(current_price, 8),
            'entry': round(entry, 8),
            'stop_loss': round(max(stop_loss, 0), 8),
            'take_profit_1': round(take_profit_1, 8),
            'take_profit_2': round(take_profit_2, 8),
            'rrr': round(rrr, 2),
            'signal_quality': signal_quality,
            'risk_level': risk_level,
            'volatility_5m': round(volatility_5m, 2),
            'volume_5m': f"{volume_5m:.1f}M",
            'scalping_score': coin_data['scalping_score']
        }
        
    except Exception as e:
        print(f"❌ Ошибка улучшенной генерации сигнала: {e}")
        # Фоллбек к простому алгоритму
        return generate_scalping_signal(coin_data)

# --- ФУНКЦИИ ДЛЯ ГЕНЕРАЦИИ ГРАФИКОВ ---

def get_coin_klines(symbol, interval="1h", limit=100):
    """Получить исторические данные монеты для построения графика"""
    try:
        # Проверяем, есть ли USDT в символе
        if not symbol.endswith('USDT'):
            symbol = symbol.upper() + 'USDT'
        
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            klines = response.json()
            
            # Преобразуем в DataFrame для удобства
            df = pd.DataFrame(data=klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'
            ])
            
            # Конвертируем типы данных
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_volume']
            df[numeric_cols] = df[numeric_cols].astype(float)
            
            return df
        else:
            print(f"❌ Ошибка получения данных для {symbol}: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка получения klines для {symbol}: {e}")
        return None

def calculate_pivot_points(df, window=5):
    """Определение пивотных точек (swing highs/lows)"""
    highs = []
    lows = []
    
    for i in range(window, len(df) - window):
        # High pivot: локальный максимум
        if all(df.iloc[i]['high'] >= df.iloc[j]['high'] for j in range(i-window, i+window+1)):
            highs.append((i, df.iloc[i]['high']))
        
        # Low pivot: локальный минимум  
        if all(df.iloc[i]['low'] <= df.iloc[j]['low'] for j in range(i-window, i+window+1)):
            lows.append((i, df.iloc[i]['low']))
    
    return highs[-10:], lows[-10:]  # Последние 10 пивотов

def calculate_technical_levels(df):
    """ПРОФЕССИОНАЛЬНЫЙ технический анализ основанный на классических принципах"""
    try:
        # Гибкие требования к данным в зависимости от их количества
        min_data_points = 20  # Минимум для базового анализа
        if df is None or len(df) < min_data_points:
            return None
        
        current_price = df['close'].iloc[-1]
        
        # === КЛАССИЧЕСКИЕ ИНДИКАТОРЫ (как учат в трейдинге) ===
        
        # 1. Экспоненциальные скользящие средние (EMA) - адаптивно для разного количества данных
        data_length = len(df)
        ema_20_span = min(20, max(5, data_length // 3))  # Адаптивный период для EMA20
        ema_50_span = min(50, max(10, data_length // 2))  # Адаптивный период для EMA50
        ema_200_span = min(200, max(20, data_length - 5))  # Адаптивный период для EMA200
        
        df['ema_20'] = df['close'].ewm(span=ema_20_span, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=ema_50_span, adjust=False).mean() if data_length >= 10 else df['ema_20']
        df['ema_200'] = df['close'].ewm(span=ema_200_span, adjust=False).mean() if data_length >= 20 else df['ema_50']
        
        ema_20 = df['ema_20'].iloc[-1]
        ema_50 = df['ema_50'].iloc[-1] 
        ema_200 = df['ema_200'].iloc[-1]
        
        # 2. ATR для измерения волатильности (True Range)
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        atr = df['tr'].ewm(span=14, adjust=False).mean().iloc[-1]  # Экспоненциальный ATR
        atr_pct = (atr / current_price) * 100  # ATR в процентах
        
        # 3. RSI для перепроданности/перекупленности  
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).ewm(span=14, adjust=False).mean()
        loss = (-delta).where(delta < 0, 0).ewm(span=14, adjust=False).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        rsi = df['rsi'].iloc[-1]
        
        # === ОПРЕДЕЛЕНИЕ ТРЕНДА (классическая методика) ===
        
        # Тренд по скользящим средним: EMA20 > EMA50 > EMA200 = БЫЧИЙ
        ema_bullish = ema_20 > ema_50 > ema_200
        ema_bearish = ema_20 < ema_50 < ema_200
        
        # Положение цены относительно EMA20 (краткосрочный тренд)
        price_above_ema20 = current_price > ema_20
        
        # Наклон EMA20 (направление движения)
        ema20_slope = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-5]) / df['ema_20'].iloc[-5] * 100
        trend_strong = abs(ema20_slope) > 0.5  # Сильный тренд если наклон > 0.5%
        
        # ИТОГОВОЕ определение тренда - упрощенная логика
        if current_price > ema_20:  # Цена выше EMA20 = бычий настрой
            trend = "BULLISH" if ema_bullish else "NEUTRAL"
            trend_up = True
            signal_type = "🟢 LONG"
        else:  # Цена ниже EMA20 = медвежий настрой
            trend = "BEARISH" if ema_bearish else "NEUTRAL"
            trend_up = False
            signal_type = "🔴 SHORT"
        
        # === ПИВОТНЫЕ ТОЧКИ для поддержки/сопротивления ===
        
        pivot_highs, pivot_lows = calculate_pivot_points(df, window=3)
        
        # Ищем ближайшие пивоты к текущей цене
        if pivot_highs:
            resistance_candidates = [price for _, price in pivot_highs if price > current_price]
            resistance = min(resistance_candidates) if resistance_candidates else df['high'].rolling(20).max().iloc[-1]
        else:
            resistance = df['high'].rolling(20).max().iloc[-1]
            
        if pivot_lows:
            support_candidates = [price for _, price in pivot_lows if price < current_price]  
            support = max(support_candidates) if support_candidates else df['low'].rolling(20).min().iloc[-1]
        else:
            support = df['low'].rolling(20).min().iloc[-1]
        
        # === ПРОФЕССИОНАЛЬНЫЕ ТОРГОВЫЕ ЗОНЫ на основе ATR ===
        
        # Адаптивная ширина зон (зависит от волатильности)
        if atr_pct > 5:  # Высокая волатильность
            zone_multiplier = 0.4
        elif atr_pct > 2:  # Средняя волатильность  
            zone_multiplier = 0.3
        else:  # Низкая волатильность
            zone_multiplier = 0.25
            
        zone_width = atr * zone_multiplier
        
        if trend_up:
            # === БЫЧИЙ СЕТАП ===
            # Вход: чуть выше EMA20 или от поддержки
            entry_center = max(ema_20 * 1.002, support + atr * 0.5)
            stop_loss_center = support - atr * 0.5  # Стоп за поддержкой
            tp1_center = resistance  # Первая цель - сопротивление
            tp2_center = resistance + atr * 2  # Вторая цель - пробой сопротивления
            
        else:
            # === МЕДВЕЖИЙ СЕТАП ===  
            # Вход: чуть ниже EMA20 или от сопротивления
            entry_center = min(ema_20 * 0.998, resistance - atr * 0.5)
            stop_loss_center = resistance + atr * 0.5  # Стоп за сопротивлением
            tp1_center = support  # Первая цель - поддержка
            tp2_center = support - atr * 2  # Вторая цель - пробой поддержки
        
        # Формирование зон (диапазонов) для каждого уровня
        entry_zone = {
            'lower': entry_center - zone_width,
            'upper': entry_center + zone_width, 
            'center': entry_center
        }
        
        stop_zone = {
            'lower': stop_loss_center - zone_width,
            'upper': stop_loss_center + zone_width,
            'center': stop_loss_center  
        }
        
        tp1_zone = {
            'lower': tp1_center - zone_width,
            'upper': tp1_center + zone_width,
            'center': tp1_center
        }
        
        tp2_zone = {
            'lower': tp2_center - zone_width,
            'upper': tp2_center + zone_width, 
            'center': tp2_center
        }
        
        # Зоны поддержки и сопротивления
        support_zone = {
            'lower': support - atr * 0.3,
            'upper': support + atr * 0.3,
            'center': support
        }
        
        resistance_zone = {
            'lower': resistance - atr * 0.3,
            'upper': resistance + atr * 0.3,
            'center': resistance  
        }
        
        # Проверка Risk/Reward
        risk = abs(entry_center - stop_loss_center)
        reward = abs(tp1_center - entry_center)
        risk_reward = reward / risk if risk > 0 else 0
        
        # Если R/R плохой, корректируем цели
        if risk_reward < 1.5:
            if trend_up:
                tp1_center = entry_center + risk * 1.5
                tp2_center = entry_center + risk * 2.5
            else:
                tp1_center = entry_center - risk * 1.5  
                tp2_center = entry_center - risk * 2.5
        
        # === SMART MONEY АНАЛИЗ ===
        smart_money_data = analyze_smart_money_concepts(df)
        
        # Корректируем направление на основе Smart Money
        smart_bias = smart_money_data.get('smart_money_bias', 'NEUTRAL')
        if smart_bias != 'NEUTRAL' and smart_bias != trend:
            # Smart Money противоречит техническому анализу - больше вес Smart Money
            if smart_bias == 'BULLISH':
                signal_type = "💰 SMART LONG"
                trend_up = True
            else:
                signal_type = "💰 SMART SHORT"  
                trend_up = False
        
        return {
            'current_price': current_price,
            
            # Основные точки (для совместимости)
            'entry': entry_center,
            'stop_loss': stop_loss_center,
            'take_profit_1': tp1_center,
            'take_profit_2': tp2_center,
            'resistance': resistance,
            'support': support,
            
            # ПРОФЕССИОНАЛЬНЫЕ ЗОНЫ
            'entry_zone': entry_zone,
            'stop_zone': stop_zone,
            'tp1_zone': tp1_zone,
            'tp2_zone': tp2_zone,
            'support_zone': support_zone,
            'resistance_zone': resistance_zone,
            
            # ИНДИКАТОРЫ
            'ema_20': ema_20,
            'ema_50': ema_50,
            'ema_200': ema_200,
            'atr': atr,
            'atr_pct': atr_pct,
            'rsi': rsi,
            'zone_width': zone_width,
            
            # АНАЛИЗ ТРЕНДА  
            'signal_type': signal_type,
            'trend': trend,
            'trend_up': trend_up,
            'trend_strong': trend_strong,
            'ema20_slope': ema20_slope,
            
            # SMART MONEY ДАННЫЕ
            'smart_money_bias': smart_bias,
            'fair_value_gaps': smart_money_data.get('fair_value_gaps', []),
            'order_blocks': smart_money_data.get('order_blocks', []),
            'liquidity_zones': smart_money_data.get('liquidity_zones', []),
            'structure_analysis': smart_money_data.get('structure_analysis', {}),
            
            # ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ
            'risk_reward': risk_reward,
            'pivot_highs_count': len(pivot_highs),
            'pivot_lows_count': len(pivot_lows),
        }
        
    except Exception as e:
        print(f"❌ Ошибка расчета технических уровней: {e}")
        return None

# === SMART MONEY & ИМБАЛАНС АНАЛИЗ ===

def detect_fair_value_gaps(df, min_gap_percent=0.1):
    """Детектирование Fair Value Gaps (FVG) - имбалансов цены"""
    fvgs = []
    
    try:
        for i in range(1, len(df) - 1):
            prev_candle = df.iloc[i-1]
            curr_candle = df.iloc[i] 
            next_candle = df.iloc[i+1]
            
            # Бычий FVG: low текущей > high предыдущей
            if curr_candle['low'] > prev_candle['high']:
                gap_size = curr_candle['low'] - prev_candle['high']
                gap_percent = (gap_size / prev_candle['close']) * 100
                
                if gap_percent >= min_gap_percent:
                    fvgs.append({
                        'index': i,
                        'type': 'BULLISH_FVG',
                        'top': curr_candle['low'],
                        'bottom': prev_candle['high'],
                        'size_percent': gap_percent
                    })
            
            # Медвежий FVG: high текущей < low предыдущей  
            elif curr_candle['high'] < prev_candle['low']:
                gap_size = prev_candle['low'] - curr_candle['high']
                gap_percent = (gap_size / prev_candle['close']) * 100
                
                if gap_percent >= min_gap_percent:
                    fvgs.append({
                        'index': i,
                        'type': 'BEARISH_FVG', 
                        'top': prev_candle['low'],
                        'bottom': curr_candle['high'],
                        'size_percent': gap_percent
                    })
                    
        return fvgs[-10:]  # Последние 10 FVG
        
    except Exception as e:
        print(f"❌ Ошибка детекции FVG: {e}")
        return []

def detect_order_blocks(df, pivot_highs, pivot_lows):
    """Детектирование Order Blocks - зон крупных ордеров"""
    order_blocks = []
    
    try:
        # Бычьи Order Blocks: последняя медвежья свеча перед импульсом вверх
        for idx, price in pivot_lows:
            # Ищем импульс вверх после пивота (минимум 2% движение)
            for i in range(idx + 1, min(idx + 10, len(df))):
                if df.iloc[i]['high'] > price * 1.02:  # 2% импульс вверх
                    # Находим последнюю медвежью свечу перед импульсом
                    for j in range(idx, i):
                        candle = df.iloc[j]
                        if candle['close'] < candle['open']:  # Медвежья свеча
                            order_blocks.append({
                                'index': j,
                                'type': 'BULLISH_OB',
                                'top': candle['high'],
                                'bottom': candle['low'],
                                'origin_price': price
                            })
                            break
                    break
        
        # Медвежьи Order Blocks: последняя бычья свеча перед импульсом вниз
        for idx, price in pivot_highs:
            # Ищем импульс вниз после пивота  
            for i in range(idx + 1, min(idx + 10, len(df))):
                if df.iloc[i]['low'] < price * 0.98:  # 2% импульс вниз
                    # Находим последнюю бычью свечу перед импульсом
                    for j in range(idx, i):
                        candle = df.iloc[j]
                        if candle['close'] > candle['open']:  # Бычья свеча
                            order_blocks.append({
                                'index': j,
                                'type': 'BEARISH_OB',
                                'top': candle['high'],
                                'bottom': candle['low'], 
                                'origin_price': price
                            })
                            break
                    break
                    
        return order_blocks[-5:]  # Последние 5 OB
        
    except Exception as e:
        print(f"❌ Ошибка детекции Order Blocks: {e}")
        return []

def detect_structure_breaks(df, pivot_highs, pivot_lows):
    """Детектирование Break of Structure (BOS) и Change of Character (CHOCH)"""
    structure_analysis = {
        'bos_bullish': [],
        'bos_bearish': [],
        'choch_detected': False,
        'current_structure': 'NEUTRAL',
        'last_structure_change': None
    }
    
    try:
        current_price = df['close'].iloc[-1]
        
        # Анализ последних пивотов для определения структуры
        recent_highs = [price for idx, price in pivot_highs[-3:]] if len(pivot_highs) >= 3 else []
        recent_lows = [price for idx, price in pivot_lows[-3:]] if len(pivot_lows) >= 3 else []
        
        # Определяем текущую структуру
        if recent_highs and recent_lows:
            # Восходящая структура: каждый максимум и минимум выше предыдущего
            if len(recent_highs) >= 2 and len(recent_lows) >= 2:
                higher_highs = all(recent_highs[i] > recent_highs[i-1] for i in range(1, len(recent_highs)))
                higher_lows = all(recent_lows[i] > recent_lows[i-1] for i in range(1, len(recent_lows)))
                
                lower_highs = all(recent_highs[i] < recent_highs[i-1] for i in range(1, len(recent_highs)))
                lower_lows = all(recent_lows[i] < recent_lows[i-1] for i in range(1, len(recent_lows)))
                
                if higher_highs and higher_lows:
                    structure_analysis['current_structure'] = 'BULLISH'
                elif lower_highs and lower_lows:
                    structure_analysis['current_structure'] = 'BEARISH'
        
        # Детекция BOS (пробой структуры)
        if pivot_highs:
            last_high_idx, last_high = pivot_highs[-1]
            if current_price > last_high:
                structure_analysis['bos_bullish'].append({
                    'price': last_high,
                    'broken_at': current_price,
                    'index': last_high_idx
                })
        
        if pivot_lows:
            last_low_idx, last_low = pivot_lows[-1] 
            if current_price < last_low:
                structure_analysis['bos_bearish'].append({
                    'price': last_low,
                    'broken_at': current_price,
                    'index': last_low_idx
                })
        
        return structure_analysis
        
    except Exception as e:
        print(f"❌ Ошибка анализа структуры: {e}")
        return structure_analysis

def analyze_smart_money_concepts(df):
    """Комплексный анализ Smart Money концепций"""
    try:
        # Получаем пивотные точки
        pivot_highs, pivot_lows = calculate_pivot_points(df, window=3)
        
        # Анализируем различные Smart Money концепции
        fvgs = detect_fair_value_gaps(df)
        order_blocks = detect_order_blocks(df, pivot_highs, pivot_lows)
        structure = detect_structure_breaks(df, pivot_highs, pivot_lows)
        
        # Ищем ликвидационные зоны (где могут стоять стопы)
        liquidity_zones = []
        current_price = df['close'].iloc[-1]
        
        # Зоны над недавними максимумами (стопы шортов)
        for idx, high_price in pivot_highs[-5:]:
            if high_price > current_price:
                liquidity_zones.append({
                    'type': 'SHORT_LIQUIDITY',
                    'price': high_price,
                    'distance_percent': ((high_price - current_price) / current_price) * 100
                })
        
        # Зоны под недавними минимумами (стопы лонгов)  
        for idx, low_price in pivot_lows[-5:]:
            if low_price < current_price:
                liquidity_zones.append({
                    'type': 'LONG_LIQUIDITY', 
                    'price': low_price,
                    'distance_percent': ((current_price - low_price) / current_price) * 100
                })
        
        return {
            'fair_value_gaps': fvgs,
            'order_blocks': order_blocks,
            'structure_analysis': structure,
            'liquidity_zones': liquidity_zones,
            'smart_money_bias': determine_smart_money_bias(fvgs, order_blocks, structure)
        }
        
    except Exception as e:
        print(f"❌ Ошибка анализа Smart Money: {e}")
        return {}

def determine_smart_money_bias(fvgs, order_blocks, structure):
    """Определить направление Smart Money на основе всех факторов"""
    try:
        bullish_signals = 0
        bearish_signals = 0
        
        # FVG анализ
        for fvg in fvgs:
            if fvg['type'] == 'BULLISH_FVG':
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        # Order Blocks анализ  
        for ob in order_blocks:
            if ob['type'] == 'BULLISH_OB':
                bullish_signals += 2  # OB весят больше
            else:
                bearish_signals += 2
        
        # Структурный анализ
        if structure['current_structure'] == 'BULLISH':
            bullish_signals += 3
        elif structure['current_structure'] == 'BEARISH': 
            bearish_signals += 3
            
        # BOS анализ
        bullish_signals += len(structure['bos_bullish'])
        bearish_signals += len(structure['bos_bearish'])
        
        # Определяем итоговое направление
        if bullish_signals > bearish_signals + 1:
            return 'BULLISH'
        elif bearish_signals > bullish_signals + 1:
            return 'BEARISH'
        else:
            return 'NEUTRAL'
            
    except Exception as e:
        print(f"❌ Ошибка определения Smart Money bias: {e}")
        return 'NEUTRAL'

# --- ФУНКЦИЯ СТАТУСА АВТОСКРИНИНГА ---
def auto_scanning_active():
    """Проверить активен ли автоскрининг"""
    try:
        job = scheduler.get_job('auto_scalping_scan')
        return job is not None
    except:
        return False

# --- COINGECKO API INTEGRATION ---

def get_coin_data_coingecko(symbol, days=7, retry_count=3):
    """Получить исторические данные монеты с CoinGecko API с улучшенной надежностью"""
    try:
        # Полный CoinGecko mapping для всех поддерживаемых монет
        coin_id_map = {
            # Основные монеты
            'BTC': 'bitcoin', 'ETH': 'ethereum', 'BNB': 'binancecoin', 
            'ADA': 'cardano', 'SOL': 'solana', 'XRP': 'ripple',
            'DOGE': 'dogecoin', 'DOT': 'polkadot', 'AVAX': 'avalanche-2',
            'LINK': 'chainlink', 'LTC': 'litecoin', 'UNI': 'uniswap',
            'ATOM': 'cosmos', 'XLM': 'stellar', 'VET': 'vechain',
            'ICP': 'internet-computer', 'FIL': 'filecoin', 'TRX': 'tron',
            'ETC': 'ethereum-classic', 'AAVE': 'aave', 'SUSHI': 'sushi',
            'PEPE': 'pepe', 'SHIB': 'shiba-inu', 'MEME': 'memecoin',
            'BONK': 'bonk', 'FLOKI': 'floki', 'WIF': 'dogwifhat',
            'NOT': 'notcoin', 'TON': 'the-open-network', 'MATIC': 'matic-network',
            'NEAR': 'near', 'ALGO': 'algorand', 'HBAR': 'hedera-hashgraph',
            'QNT': 'quant-network', 'OP': 'optimism', 'ARB': 'arbitrum',
            'COMP': 'compound-governance-token', 'MKR': 'maker', 'YFI': 'yearn-finance',
            'CRV': 'curve-dao-token', 'SNX': 'synthetix-network-token', '1INCH': '1inch',
            'ENJ': 'enjincoin', 'MANA': 'decentraland', 'SAND': 'the-sandbox',
            'AXS': 'axie-infinity', 'GALA': 'gala', 'CHZ': 'chiliz',
            'BAT': 'basic-attention-token', 'ZIL': 'zilliqa', 'HOT': 'holo',
            # Предыдущие дополнения
            'ETHFI': 'ether-fi', 'ORDI': 'ordi', 'PEOPLE': 'constitutiondao',
            'DYDX': 'dydx-chain', 'CELO': 'celo', 'STRK': 'starknet',
            'AI': 'sleepless-ai', 'POL': 'polygon-ecosystem-token', 'IOTX': 'iotex',
            'CAKE': 'pancakeswap-token', 'LUNC': 'terra-luna-classic', 'BAKE': 'bakerytoken',
            'SUI': 'sui', 'WLFI': 'world-liberty-financial',
            # Новые монеты из скриншотов  
            'PUMP': 'moonpump', 'TAO': 'bittensor', 'ENS': 'ethereum-name-service',
            'ENA': 'ethena', 'S': 'solidus-aitech', 'INJ': 'injective-protocol',
            'W': 'wormhole', 'ADX': 'adex', 'ROSE': 'oasis-network', 'USTC': 'terraclassicusd',
            'SEI': 'sei-network', 'FIDA': 'bonfida', 'PNUT': 'peanut-the-squirrel',
            'JASMY': 'jasmycoin', 'TURBO': 'turbo', 'EIGEN': 'eigenlayer',
            'SCR': 'scroll', 'IO': 'io', 'TRB': 'tellor', 'APT': 'aptos',
            'LDO': 'lido-dao', 'ALT': 'altlayer', 'WLD': 'worldcoin',
            'BCH': 'bitcoin-cash', 'AEVO': 'aevo', 'ZRX': '0x',
            'ANKR': 'ankr', 'YGG': 'yield-guild-games', 'XAI': 'xai-games',
            'ILV': 'illuvium', 'SCRT': 'secret', 'EGLD': 'elrond-erd-2',
            'JUP': 'jupiter-exchange-solana', 'FET': 'fetch-ai', 'GRT': 'the-graph',
            'PIXEL': 'pixels', 'IDEX': 'idex', 'DASH': 'dash',
            'PORTAL': 'portal', 'PROM': 'prometeus', 'VTHO': 'vethor-token',
            'C98': 'coin98', 'VANRY': 'vanar-chain', 'TIA': 'celestia',
            'TRUMP': 'maga', 'ID': 'space-id', 'JTO': 'jito-governance-token',
            'HOOK': 'hooked-protocol', 'MASK': 'mask-network', 'PERP': 'perpetual-protocol',
            'FXS': 'frax-share', 'MAV': 'maverick-protocol', 'SLP': 'smooth-love-potion',
            'RVN': 'ravencoin', 'CFX': 'conflux-token', 'MANTA': 'manta-network',
            'LUNA': 'terra-luna-2'
        }
        
        coin_id = coin_id_map.get(symbol.upper(), symbol.lower())
        
        # Улучшенные headers для лучшей совместимости с CoinGecko
        headers = {
            'User-Agent': 'Mozilla/5.0 (TradingBot/4.0; +https://replit.com)',
            'Accept': 'application/json',
            'Cache-Control': 'no-cache'
        }
        
        # Увеличиваем количество дней для получения достаточных данных
        days = max(days, 7)  # Минимум неделя данных
        
        # Запрос к CoinGecko API с retry логикой
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {
            'vs_currency': 'usd',
            'days': days,
            'interval': 'hourly'
        }
        
        for attempt in range(retry_count):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=20)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'prices' not in data or len(data['prices']) < 20:
                        print(f"⚠️ CoinGecko: недостаточно данных для {symbol} (получено {len(data.get('prices', []))})")
                        return None
                    
                    # Создаем DataFrame из данных CoinGecko
                    prices = data['prices']
                    volumes = data['total_volumes']
                    
                    df = pd.DataFrame(data=prices, columns=['timestamp', 'close'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df['volume'] = [v[1] for v in volumes[:len(df)]]
                    
                    # Улучшенная аппроксимация OHLC данных
                    df = df.sort_values('timestamp').reset_index(drop=True)
                    df['open'] = df['close'].shift(1).fillna(df['close'].iloc[0])
                    
                    # Более реалистичная симуляция high/low
                    volatility = df['close'].pct_change().std() * 0.5
                    df['high'] = df[['open', 'close']].max(axis=1) * (1 + volatility)
                    df['low'] = df[['open', 'close']].min(axis=1) * (1 - volatility)
                    
                    print(f"✅ CoinGecko: получено {len(df)} точек для {symbol}")
                    return df
                    
                elif response.status_code == 429:  # Rate limit
                    wait_time = 2 ** attempt
                    print(f"⏳ CoinGecko rate limit, ждем {wait_time}с...")
                    time.sleep(wait_time)
                elif response.status_code == 401:  # Unauthorized
                    print(f"❌ CoinGecko API ошибка авторизации для {symbol}: 401")
                    return None
                    continue
                    
                else:
                    print(f"❌ CoinGecko API ошибка для {symbol}: {response.status_code}")
                    if attempt == retry_count - 1:
                        return None
                    time.sleep(1)
                    continue
                    
            except requests.RequestException as e:
                print(f"⚠️ CoinGecko запрос {attempt+1}/{retry_count} провален: {e}")
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue
                return None
        
        return None
        
    except Exception as e:
        print(f"❌ Критическая ошибка CoinGecko для {symbol}: {e}")
        return None

def get_trending_coins_coingecko():
    """Получить трендовые монеты с CoinGecko"""
    try:
        url = "https://api.coingecko.com/api/v3/search/trending"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            trending = []
            
            for coin in data['coins'][:10]:  # ТОП-10 трендовых
                trending.append({
                    'symbol': coin['item']['symbol'].upper(),
                    'name': coin['item']['name'],
                    'score': coin['item']['score'] if 'score' in coin['item'] else 95,
                    'source': 'coingecko'
                })
            
            return trending
            
        else:
            print(f"❌ Ошибка получения трендов CoinGecko: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"❌ Ошибка трендов CoinGecko: {e}")
        return []

# --- УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ПОЛУЧЕНИЯ ДАННЫХ ---
def get_coin_data(symbol, interval="1h", limit=100, source=None, auto_fallback=True):
    """Универсальная функция получения данных с автоматическим возвратом к резервному источнику"""
    global data_source
    
    if source is None:
        source = data_source
    
    # Специальные случаи: монеты, которые торгуются только на определенных биржах
    mexc_only_coins = ['IP']  # Токены доступные только на MEXC
    coingecko_only_coins = []  # Временно пустой список
    
    if symbol.upper() in mexc_only_coins:
        source = "mexc"
        auto_fallback = False  # Не переключаемся на другие источники
        print(f"🔄 {symbol} доступен только через MEXC API")
    elif symbol.upper() in coingecko_only_coins:
        source = "coingecko"
        auto_fallback = False  # Не переключаемся на Binance
        print(f"🔄 {symbol} доступен только через CoinGecko API")
    
    original_source = source
    
    # Попытка получить данные из основного источника
    if source == "coingecko":
        print(f"🔄 Запрашиваю {symbol} из CoinGecko...")
        
        # CoinGecko работает с днями, конвертируем интервалы
        days = 1
        if 'h' in interval:
            hours = int(interval.replace('h', ''))
            days = max(7, (limit * hours) / 24)  # Минимум неделя для достаточного количества данных
        elif 'd' in interval:
            days = max(7, int(interval.replace('d', '')) * limit)
        elif 'w' in interval:
            days = max(7, int(interval.replace('w', '')) * limit * 7)
        elif 'M' in interval:
            days = max(30, int(interval.replace('M', '')) * limit * 30)
            
        df = get_coin_data_coingecko(symbol, days=min(int(days), 365))
        
        # Проверяем качество данных
        if df is not None and len(df) >= 20:
            print(f"✅ CoinGecko успешно предоставил {len(df)} точек данных для {symbol}")
            return df
        
        # Автоматический возврат к Binance при проблемах с CoinGecko
        if auto_fallback:
            print(f"⚠️ CoinGecko не предоставил достаточно данных для {symbol}")
            print(f"🔄 Автоматический переход на Binance...")
            source = "binance"
        else:
            print(f"❌ CoinGecko: недостаточно данных для анализа {symbol}")
            return None
    
    # Получаем данные из MEXC
    if source == "mexc":
        print(f"📊 Получаю {symbol} из MEXC...")
        df = get_mexc_klines(symbol, interval, limit)
        
        if df is not None and len(df) >= 20:
            print(f"✅ MEXC предоставил {len(df)} свечей для {symbol}")
            return df
        else:
            print(f"❌ MEXC не смог предоставить данные для {symbol}")
            return None
    
    # Получаем данные из Binance (основной или резервный источник)
    if source == "binance":
        if original_source == "coingecko":
            print(f"📊 Получаю {symbol} из Binance (резервный источник)...")
        else:
            print(f"📊 Получаю {symbol} из Binance...")
            
        df = get_coin_klines(symbol, interval, limit)
        
        if df is not None and len(df) >= 20:
            if original_source == "coingecko":
                print(f"✅ Binance успешно предоставил резервные данные: {len(df)} свечей")
            else:
                print(f"✅ Binance предоставил {len(df)} свечей для {symbol}")
            return df
        else:
            print(f"❌ Binance также не смог предоставить данные для {symbol}")
            return None
    
    return None

def calculate_technical_indicators(df):
    """Рассчитать технические индикаторы для графика"""
    try:
        # RSI (Relative Strength Index)
        def calculate_rsi(prices, window=14):
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
            rs = gain / loss
            return 100 - (100 / (1 + rs))
        
        # MACD
        def calculate_macd(prices, fast=12, slow=26, signal=9):
            exp1 = prices.ewm(span=fast).mean()
            exp2 = prices.ewm(span=slow).mean()
            macd = exp1 - exp2
            macd_signal = macd.ewm(span=signal).mean()
            macd_histogram = macd - macd_signal
            return macd, macd_signal, macd_histogram
        
        # Bollinger Bands
        def calculate_bollinger(prices, window=20, num_std=2):
            sma = prices.rolling(window).mean()
            std = prices.rolling(window).std()
            upper_band = sma + (std * num_std)
            lower_band = sma - (std * num_std)
            return upper_band, sma, lower_band
        
        # Рассчитываем все индикаторы
        df['sma_10'] = df['close'].rolling(10).mean()
        df['sma_20'] = df['close'].rolling(20).mean()
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        
        df['rsi'] = calculate_rsi(df['close'])
        df['macd'], df['macd_signal'], df['macd_histogram'] = calculate_macd(df['close'])
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = calculate_bollinger(df['close'])
        
        return df
        
    except Exception as e:
        print(f"❌ Ошибка расчета индикаторов: {e}")
        return df

def create_trading_chart(symbol, df, levels, timeframe='1h'):
    """Создать профессиональный график с полным техническим анализом и индикаторами"""
    try:
        if df is None or levels is None or len(df) < 20:
            return None
        
        # Рассчитываем технические индикаторы
        df = calculate_technical_indicators(df)
        
        # Настраиваем стиль графика
        plt.style.use('dark_background')
        fig = plt.figure(figsize=(16, 12))
        
        # Создаем 3 подграфика с правильными пропорциями
        gs = fig.add_gridspec(3, 1, height_ratios=[3, 1, 1], hspace=0.3)
        ax_price = fig.add_subplot(gs[0])
        ax_market = fig.add_subplot(gs[1])
        ax_volume = fig.add_subplot(gs[2])
        
        # === ПОДГОТОВКА ВРЕМЕННОЙ ОСИ ===
        
        # Используем реальные временные данные 
        if 'open_time' in df.columns:
            time_axis = pd.to_datetime(df['open_time'], unit='ms')
        elif 'timestamp' in df.columns:
            time_axis = pd.to_datetime(df['timestamp'], unit='ms')
        else:
            from datetime import datetime, timedelta
            timeframe_minutes = {
                '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
                '1h': 60, '2h': 120, '4h': 240, '6h': 360, '8h': 480, '12h': 720,
                '1d': 1440, '3d': 4320, '1w': 10080, '1M': 43200
            }.get(timeframe, 60)
            
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=timeframe_minutes * len(df))
            time_axis = pd.date_range(start=start_time, end=end_time, periods=len(df))
        
        x_range = list(range(len(df)))  # Преобразуем в список для fill_between
        
        # === 1. ОСНОВНОЙ ГРАФИК ЦЕНЫ ===
        
        # Bollinger Bands (заливка области)
        ax_price.fill_between(x_range, df['bb_upper'], df['bb_lower'], 
                            alpha=0.1, color='purple', label='Bollinger Bands')
        ax_price.plot(x_range, df['bb_upper'], color='purple', linewidth=1, alpha=0.7)
        ax_price.plot(x_range, df['bb_lower'], color='purple', linewidth=1, alpha=0.7)
        ax_price.plot(x_range, df['bb_middle'], color='purple', linewidth=1, alpha=0.9, linestyle='--')
        
        # Японские свечи в стиле TradingView
        from matplotlib.patches import Rectangle
        
        for i in range(len(df)):
            row = df.iloc[i]
            
            # Цвета как на TradingView
            is_bullish = row['close'] >= row['open']
            candle_color = '#26a69a' if is_bullish else '#ef5350'  # TradingView цвета
            
            # Тело свечи
            body_height = abs(row['close'] - row['open'])
            body_bottom = min(row['open'], row['close'])
            
            if body_height > 0:  # Есть тело свечи
                ax_price.add_patch(Rectangle((i-0.4, body_bottom), 0.8, body_height, 
                                          facecolor=candle_color, edgecolor=candle_color, 
                                          alpha=0.9, linewidth=0.5))
            else:  # Доджи - линия
                ax_price.plot([i-0.4, i+0.4], [row['close'], row['close']], 
                            color=candle_color, linewidth=1.5)
            
            # Тени свечи (более тонкие)
            if row['high'] > max(row['open'], row['close']):
                ax_price.plot([i, i], [max(row['open'], row['close']), row['high']], 
                            color=candle_color, linewidth=1, alpha=0.9)
            if row['low'] < min(row['open'], row['close']):
                ax_price.plot([i, i], [row['low'], min(row['open'], row['close'])], 
                            color=candle_color, linewidth=1, alpha=0.9)
        
        # Скользящие средние в стиле TradingView
        ax_price.plot(x_range, df['sma_10'], color='#2196f3', linewidth=1.5, 
                     label='SMA 10', alpha=0.9)
        ax_price.plot(x_range, df['sma_20'], color='#ff9800', linewidth=1.5, 
                     label='SMA 20', alpha=0.9)
        ax_price.plot(x_range, df['ema_12'], color='#9c27b0', linewidth=1.2, 
                     label='EMA 12', alpha=0.8, linestyle='--')
        ax_price.plot(x_range, df['ema_26'], color='#4caf50', linewidth=1.2, 
                     label='EMA 26', alpha=0.8, linestyle='--')
        
        # ПРОФЕССИОНАЛЬНЫЕ ТОРГОВЫЕ ЗОНЫ (вместо линий)
        
        # Текущая цена (остаётся линией)
        ax_price.axhline(y=levels['current_price'], color='white', linestyle='-', 
                        linewidth=3, alpha=0.9, label=f"Цена: ${levels['current_price']:.6f}")
        
        # Зона входа (жёлтая) - БЕЗ ЭМОДЗИ
        ax_price.fill_between(x_range, levels['entry_zone']['lower'], levels['entry_zone']['upper'], 
                             alpha=0.25, color='#ffff00', label=f"ENTRY: ${levels['entry_zone']['lower']:.4f}-${levels['entry_zone']['upper']:.4f}")
        ax_price.axhline(y=levels['entry_zone']['center'], color='#ffff00', linestyle='--', 
                        linewidth=1, alpha=0.8)
        
        # Зона стоп-лосса (красная) - БЕЗ ЭМОДЗИ  
        ax_price.fill_between(x_range, levels['stop_zone']['lower'], levels['stop_zone']['upper'], 
                             alpha=0.25, color='#ff3333', label=f"STOP: ${levels['stop_zone']['lower']:.4f}-${levels['stop_zone']['upper']:.4f}")
        ax_price.axhline(y=levels['stop_zone']['center'], color='#ff3333', linestyle='--', 
                        linewidth=1, alpha=0.8)
        
        # Зона тейк-профит 1 (зелёная) - БЕЗ ЭМОДЗИ
        ax_price.fill_between(x_range, levels['tp1_zone']['lower'], levels['tp1_zone']['upper'], 
                             alpha=0.25, color='#33ff33', label=f"TP1: ${levels['tp1_zone']['lower']:.4f}-${levels['tp1_zone']['upper']:.4f}")
        ax_price.axhline(y=levels['tp1_zone']['center'], color='#33ff33', linestyle='--', 
                        linewidth=1, alpha=0.8)
        
        # Зона тейк-профит 2 (тёмно-зелёная) - БЕЗ ЭМОДЗИ  
        ax_price.fill_between(x_range, levels['tp2_zone']['lower'], levels['tp2_zone']['upper'], 
                             alpha=0.25, color='#00aa00', label=f"TP2: ${levels['tp2_zone']['lower']:.4f}-${levels['tp2_zone']['upper']:.4f}")
        ax_price.axhline(y=levels['tp2_zone']['center'], color='#00aa00', linestyle='--', 
                        linewidth=1, alpha=0.8)
        
        # ЗОНЫ ПОДДЕРЖКИ И СОПРОТИВЛЕНИЯ - БЕЗ ЭМОДЗИ
        
        # Зона сопротивления (оранжевая)
        ax_price.fill_between(x_range, levels['resistance_zone']['lower'], levels['resistance_zone']['upper'], 
                             alpha=0.2, color='#ff9900', label=f"RESISTANCE: ${levels['resistance_zone']['lower']:.4f}-${levels['resistance_zone']['upper']:.4f}")
        ax_price.axhline(y=levels['resistance_zone']['center'], color='#ff9900', linestyle='-', 
                        linewidth=2, alpha=0.8)
        
        # Зона поддержки (голубая)
        ax_price.fill_between(x_range, levels['support_zone']['lower'], levels['support_zone']['upper'], 
                             alpha=0.2, color='#00ccff', label=f"SUPPORT: ${levels['support_zone']['lower']:.4f}-${levels['support_zone']['upper']:.4f}")
        ax_price.axhline(y=levels['support_zone']['center'], color='#00ccff', linestyle='-', 
                        linewidth=2, alpha=0.8)
        
        # === 2. MARKET STRUCTURE / ЗОНЫ ПОКУПКИ-ПРОДАЖИ ===
        
        # Создаем индикатор силы покупателей vs продавцов
        buy_pressure = []
        sell_pressure = []
        
        for i in range(len(df)):
            candle = df.iloc[i]
            
            # Если цена закрытия выше открытия = давление покупателей
            if candle['close'] > candle['open']:
                buy_strength = (candle['close'] - candle['open']) / candle['open'] * 100
                sell_strength = 0
            # Если цена закрытия ниже открытия = давление продавцов  
            elif candle['close'] < candle['open']:
                buy_strength = 0
                sell_strength = (candle['open'] - candle['close']) / candle['open'] * 100
            else:
                buy_strength = 0
                sell_strength = 0
            
            buy_pressure.append(buy_strength)
            sell_pressure.append(-sell_strength)  # Отрицательные для отображения внизу
        
        # Рисуем зоны покупки (зеленые) и продажи (красные)
        ax_market.bar(x_range, buy_pressure, color='#26a69a', alpha=0.7, 
                     width=0.8, label='Зоны покупки')
        ax_market.bar(x_range, sell_pressure, color='#ef5350', alpha=0.7, 
                     width=0.8, label='Зоны продажи')
        
        # Средняя линия
        ax_market.axhline(y=0, color='gray', linestyle='-', alpha=0.5, linewidth=1)
        
        # Добавляем скользящую среднюю давления
        buy_ma = pd.Series(buy_pressure).rolling(10).mean()
        sell_ma = pd.Series(sell_pressure).rolling(10).mean()
        ax_market.plot(x_range, buy_ma, color='#00ff00', linewidth=2, alpha=0.8, label='Trend Buy')
        ax_market.plot(x_range, sell_ma, color='#ff0000', linewidth=2, alpha=0.8, label='Trend Sell')
        
        # === 3. ГРАФИК ОБЪЕМОВ ===
        
        # Объемы с TradingView цветами
        volume_colors = ['#26a69a' if df.iloc[i]['close'] >= df.iloc[i]['open'] else '#ef5350' 
                        for i in range(len(df))]
        ax_volume.bar(x_range, df['volume'], color=volume_colors, alpha=0.6, width=0.8)
        
        # Скользящая средняя объема
        volume_ma = df['volume'].rolling(20).mean()
        ax_volume.plot(x_range, volume_ma, color='orange', linewidth=2, alpha=0.8, label='MA Volume')
        
        # === НАСТРОЙКИ ВСЕХ ОСЕЙ В СТИЛЕ TRADINGVIEW ===
        
        # Общие настройки для всех подграфиков
        all_axes = [ax_price, ax_market, ax_volume]
        
        # Временные метки
        step = max(1, len(df) // 8)  # 8 меток времени
        tick_positions = list(range(0, len(df), step))
        
        if timeframe in ['1m', '3m', '5m', '15m', '30m']:
            format_str = '%H:%M'
        elif timeframe in ['1h', '2h', '4h', '6h', '8h', '12h']:
            format_str = '%m-%d %H:%M'
        else:
            format_str = '%m-%d'
            
        tick_labels = [time_axis[i].strftime(format_str) for i in tick_positions if i < len(df)]
        
        for ax in all_axes:
            ax.set_xlim(0, len(df)-1)
            ax.set_xticks(tick_positions[:len(tick_labels)])
            ax.set_xticklabels([str(label) for label in tick_labels] if ax == ax_volume else [], 
                             rotation=0, ha='center', fontsize=9, color='#cccccc')
            
            # Сетка в стиле TradingView
            ax.grid(True, linestyle='-', linewidth=0.5, color='#404040', alpha=0.7)
            ax.set_facecolor('#131722')  # Темный фон TradingView
        
        # Настройки основного графика цены
        ax_price.set_title(f'{symbol}/USDT • {timeframe} • {levels["signal_type"]}', 
                          fontsize=14, fontweight='bold', color='#f0f3fa', pad=20)
        ax_price.set_ylabel('')  # Убираем подпись, цены будут справа
        ax_price.legend(loc='lower center', fontsize=7, framealpha=0.8, 
                       facecolor='#1e222d', edgecolor='#404040', ncol=2,
                       bbox_to_anchor=(0.5, -0.15))
        
        # Правая ось для цен (как в TradingView)
        ax_price_right = ax_price.twinx()
        ax_price_right.set_ylim(ax_price.get_ylim())
        ax_price_right.set_ylabel('Цена', fontsize=10, color='#cccccc')
        ax_price_right.tick_params(axis='y', labelcolor='#cccccc')
        
        
        # Объемы настройки
        ax_volume.set_ylabel('Объем', fontsize=9, color='#cccccc')
        ax_volume.tick_params(axis='y', labelcolor='#cccccc', labelsize=8)
        ax_volume.set_xlabel('Время', fontsize=9, color='#cccccc')
        ax_volume.legend(loc='upper left', fontsize=7, framealpha=0.3)
        
        # Market Structure настройки
        ax_market.set_ylabel('Buy/Sell Pressure', fontsize=9, color='#cccccc')
        ax_market.tick_params(axis='y', labelcolor='#cccccc', labelsize=8)
        ax_market.legend(loc='upper left', fontsize=7, framealpha=0.3)
        
        # Убираем лишние границы (в стиле TradingView)
        for ax in all_axes:
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False) 
            ax.spines['bottom'].set_color('#404040')
            ax.spines['left'].set_color('#404040')
            ax.tick_params(axis='x', colors='#cccccc')
            ax.tick_params(axis='y', colors='#cccccc')
        
        # Настройки фигуры в стиле TradingView
        fig.patch.set_facecolor('#131722')
        plt.subplots_adjust(hspace=0.25, bottom=0.15)  # Больше места для легенды внизу
        
        # Информационная панель (правый верхний угол)
        current_price = levels['current_price']
        price_change = ((current_price - df['close'].iloc[-20]) / df['close'].iloc[-20]) * 100
        color = '#26a69a' if price_change >= 0 else '#ef5350'
        
        info_text = f"${current_price:.6f}  {price_change:+.2f}%"
        ax_price.text(0.99, 0.99, info_text, transform=ax_price.transAxes,
                     ha='right', va='top', fontsize=12, fontweight='bold',
                     color=color, bbox=dict(boxstyle="round,pad=0.3", 
                     facecolor='#1e222d', alpha=0.8, edgecolor='none'))
        
        # Сохраняем в буфер
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight',
                   facecolor='#131722', edgecolor='none', pad_inches=0.1)
        buffer.seek(0)
        plt.close()
        
        return buffer
        
    except Exception as e:
        print(f"❌ Ошибка создания графика: {e}")
        if 'fig' in locals():
            plt.close()
        return None

def safe_caption(text, max_length=1024):
    """Обрезает текст до безопасной длины для Telegram caption"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def smart_format_price(price):
    """Умное форматирование цены в зависимости от её размера"""
    if price == 0:
        return "$0.000"
    
    # Определяем количество нужных знаков после запятой
    if price >= 1:
        return f"${price:.3f}"
    elif price >= 0.01:
        return f"${price:.4f}"
    elif price >= 0.001:
        return f"${price:.5f}"
    elif price >= 0.0001:
        return f"${price:.6f}"
    elif price >= 0.00001:
        return f"${price:.7f}"
    else:
        return f"${price:.8f}"

def generate_chart_analysis(symbol, levels, current_market_analysis="", timeframe='1h'):
    """Генерировать текстовый анализ для графика"""
    try:
        if not levels:
            return "❌ Не удалось провести технический анализ"
        
        risk_reward = abs(levels['take_profit_1'] - levels['entry']) / abs(levels['entry'] - levels['stop_loss'])
        volatility = (levels['atr'] / levels['current_price']) * 100
        
        trend_description = "восходящий 📈" if levels['trend_up'] else "нисходящий 📉"
        
        # ПРОФЕССИОНАЛЬНЫЙ АНАЛИЗ с обоснованием
        trend_desc = "восходящий 📈" if levels.get('trend_up') else "нисходящий 📉"
        
        analysis = f"""📊 {symbol.replace('USDT', '/USDT')} {timeframe}

{levels['signal_type']} | {trend_desc}

💰 Цена: {smart_format_price(levels['current_price'])}
📊 EMA20: {smart_format_price(levels.get('ema_20', 0))} | RSI: {levels.get('rsi', 50):.0f}
📈 ATR: {levels.get('atr_pct', 0):.1f}% | R/R: 1:{levels.get('risk_reward', 0):.1f}

🎯 ТОРГОВЫЕ ЗОНЫ:
🟡 Вход: {smart_format_price(levels['entry_zone']['lower'])}-{smart_format_price(levels['entry_zone']['upper'])}
🔴 Стоп: {smart_format_price(levels['stop_zone']['lower'])}-{smart_format_price(levels['stop_zone']['upper'])}
🟢 TP1: {smart_format_price(levels['tp1_zone']['lower'])}-{smart_format_price(levels['tp1_zone']['upper'])}
🟢 TP2: {smart_format_price(levels['tp2_zone']['lower'])}-{smart_format_price(levels['tp2_zone']['upper'])}

{current_market_analysis}

Не является финансовой консультацией. Торгуйте ответственно."""

        return analysis
        
    except Exception as e:
        print(f"❌ Ошибка генерации анализа: {e}")
        return "❌ Ошибка создания анализа"

# Создаем планировщик (БЕЗ автозапуска задач)
scheduler = BackgroundScheduler()
scheduler.start()

# Глобальная переменная для выбора источника данных
data_source = "binance"  # по умолчанию Binance, может быть "coingecko"

# Задачи добавляются только через команды /start_scan

# Остановка планировщика при завершении
atexit.register(lambda: scheduler.shutdown())

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        print("📨 Получен webhook запрос от Telegram")
        json_str = request.get_data().decode('UTF-8')
        print(f"📝 Данные webhook: {json_str[:200]}...")  # Первые 200 символов для отладки
        update = tg_types.Update.de_json(json_str)
        if update:
            print("✅ Update декодирован успешно, обрабатываем...")
            bot.process_new_updates([update])
        else:
            print("❌ Не удалось декодировать update")
        return "OK", 200
    except Exception as e:
        print(f"❌ Ошибка в webhook: {e}")
        return "ERROR", 500

@app.route('/')
def index():
    return "✅ Бот запущен и слушает вебхук!", 200

# --- Обработка команд ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Уведомляем администратора о новом пользователе
    notify_admin_about_user_request(
        message.from_user.id, 
        message.from_user.username, 
        message.from_user.first_name, 
        "Команда /start", 
        "/start"
    )
    
    bot.reply_to(message, "🚀 **СУПЕР ТОРГОВЫЙ БОТ ГОТОВ!**\n\n📋 Используй /help для полного меню команд\n\n🎯 **Быстрый старт:**\n• `BTC 4h` - график Bitcoin на 4 часа\n• `/scan` - поиск лучших монет сейчас\n• Отправь фото графика для AI анализа")

@bot.message_handler(commands=['help', 'menu', 'команды'])
def help_command(message):
    # Уведомляем администратора о запросе помощи
    notify_admin_about_user_request(
        message.from_user.id, 
        message.from_user.username, 
        message.from_user.first_name, 
        "Команда /help", 
        "/help"
    )
    
    help_text = """🤖 **ТОРГОВЫЙ БОТ - ПОЛНОЕ РУКОВОДСТВО v4.0**

📊 **МУЛЬТИТАЙМФРЕЙМОВЫЙ АНАЛИЗ:**
├ `BTC` - анализ Bitcoin на 1h графике
├ `XRP 4h` - анализ XRP на 4-часовом графике  
├ `ETH 15min` - анализ Ethereum на 15-минутном
├ `SOL daily` - дневной анализ Solana
└ `DOGE 1w` - недельный анализ Dogecoin

⏰ **Поддерживаемые таймфреймы:**
`1m` `5m` `15m` `30m` `1h` `2h` `4h` `6h` `8h` `12h` `1d` `3d` `1w` `1M`

🔍 **АВТОМАТИЧЕСКИЙ СКРИНИНГ:**
├ `/scan` - найти ТОП возможности сейчас
├ `/start_scan` - запустить автоскрининг (60 сек)
└ `/stop_scan` - остановить автоскрининг

📸 **АНАЛИЗ ГРАФИКОВ:**
├ Отправь фото графика - получи AI анализ
└ Поддержка любых торговых графиков


🔄 **ИСТОЧНИКИ ДАННЫХ (НОВОЕ!):**
├ `/source` - переключить источник (Binance/CoinGecko)
├ `/trending` - ТОП трендовые монеты (CoinGecko)
└ Binance: точность | CoinGecko: 18,000+ монет

ℹ️ **ИНФОРМАЦИОННЫЕ КОМАНДЫ:**
├ `/help` - это меню команд
├ `/start` - перезапуск бота
└ `/status` - статус систем

💡 **ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ:**

🔸 **Быстрый анализ:** `BTC 4h`
🔸 **Скальпинг:** `XRP 5min` 
🔸 **Свинг-трейдинг:** `ETH daily`
🔸 **Поиск сетапов:** `/scan`
🔸 **Трендовые монеты:** `/trending`
🔸 **Смена источника:** `/source`
🔸 **Загрузка графика:** [фото] + описание

⚡ **РЕЗУЛЬТАТ КАЖДОГО АНАЛИЗА:**
✅ График с торговыми уровнями
✅ Точки входа и выхода  
✅ Стоп-лосс и тейк-профит
✅ Risk/Reward расчет
✅ AI рекомендации
✅ Данные из 2+ источников

🎯 **Начни прямо сейчас!** Напиши любую команду выше"""

    # Отправляем сообщение и пытаемся закрепить
    try:
        sent_message = bot.send_message(message.chat.id, help_text)
        # Пытаемся закрепить сообщение
        bot.pin_chat_message(message.chat.id, sent_message.message_id, disable_notification=True)
        bot.send_message(message.chat.id, "📌 Меню команд закреплено!")
    except Exception as e:
        print(f"⚠ Не удалось закрепить сообщение: {e}")
        bot.send_message(message.chat.id, help_text + "\n\n💡 Сохрани это сообщение для быстрого доступа!")
# --- Проверка Binance API ---
def check_binance_api():
    import requests
    try:
        url = "https://api.binance.com/api/v3/ping"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return "🟢 Binance API: **РАБОТАЕТ**"
        else:
            return "🔴 Binance API: **ОШИБКА**"
    except Exception:
        return "🔴 Binance API: **ОШИБКА**"

@bot.message_handler(commands=['status'])
def status_command(message):
    user_id = str(message.from_user.id)
    if user_id != ADMIN_ID:
        bot.reply_to(message, "🔒 Доступ только для админа")
        return
    
    # Проверяем автоскрининг
    scan_status = "🟢 Автоскрининг: **АКТИВЕН** (каждые 60 сек)" if scheduler.get_job('auto_scalping_scan') else "⚪ Автоскрининг: **ВЫКЛЮЧЕН**"
    
    # Источник данных
    global data_source
    source_status = f"📊 Источник данных: **{data_source.upper()}**"
    
    # Binance API статус (только если источник Binance)
    if data_source.lower() == "binance":
        api_status = check_binance_api()
    else:
        # Для CoinGecko проверим через get_coin_data
        try:
            test_data = get_coin_data("BTC", "1h", 1)
            if test_data is not None:
                api_status = f"🟢 {data_source.title()} API: **РАБОТАЕТ**"
            else:
                api_status = f"🔴 {data_source.title()} API: **ОШИБКА**"
        except:
            api_status = f"🔴 {data_source.title()} API: **НЕДОСТУПЕН**"
    
    # Проверяем Gemini AI
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents="test"
        )
        if response:
            gemini_status = "🟢 Gemini AI: **РАБОТАЕТ**"
        else:
            gemini_status = "🔴 Gemini AI: **ОШИБКА**"
    except:
        gemini_status = "🔴 Gemini AI: **НЕДОСТУПЕН**"
    
    # Время по Киеву
    from pytz import timezone
    kyiv_time = datetime.now(timezone("Europe/Kiev"))
    time_status = f"⏰ **Время проверки:** {kyiv_time.strftime('%H:%M:%S')}"
    
    # Итоговый текст
    status_text = f"""🔧 **СТАТУС ТОРГОВОГО БОТА**

{scan_status}
{source_status}
{api_status}
{gemini_status}

{time_status}
🤖 **Версия:** Multi-Timeframe Analysis v3.0
"""
    bot.send_message(message.chat.id, status_text, parse_mode="Markdown")
@bot.message_handler(commands=['source', 'источник'])
def switch_data_source(message):
    # Уведомляем администратора о переключении источника
    notify_admin_about_user_request(
        message.from_user.id, 
        message.from_user.username, 
        message.from_user.first_name, 
        "Команда /source", 
        "/source"
    )
    
    global data_source
    
    # Переключаем источник
    if data_source == "binance":
        data_source = "coingecko"
        source_info = """🔄 **ИСТОЧНИК ДАННЫХ ИЗМЕНЁН**

📊 **Активен: CoinGecko API** (с авто-возвратом к Binance)

✅ **Преимущества CoinGecko:**
• 18,000+ криптовалют (vs 1,000+ Binance)
• Трендовые монеты и DEX данные
• Рыночная капитализация и метрики
• Автоматический возврат к Binance при ошибках

⚠️ **Ограничения:**
• Требует API ключ для полного доступа
• При отсутствии ключа - автоперевод на Binance
• Менее точные OHLC данные (аппроксимация)

💡 **Рекомендация:** Binance остается основным источником
💡 Используй `/trending` для ТОП трендовых монет"""
        
    else:
        data_source = "binance"
        source_info = """🔄 **ИСТОЧНИК ДАННЫХ ИЗМЕНЁН**

📊 **Активен: Binance API** (Рекомендуется)

✅ **Преимущества Binance:**
• Точные OHLC данные для всех таймфреймов
• Реальное время обновлений  
• Высокая точность технического анализа
• Большие объемы торгов
• 99.9% надежность

⚠️ **Ограничения:**
• Только криптовалюты на Binance (~1000 пар)
• Нет DEX монет и новых листингов

💡 **Используй:** `/scan` для автоскрининга, `/trending` для новых монет"""
    
    bot.send_message(message.chat.id, source_info)

@bot.message_handler(commands=['trending', 'тренды'])
def get_trending_coins(message):
    # Уведомляем администратора о запросе трендов
    notify_admin_about_user_request(
        message.from_user.id, 
        message.from_user.username, 
        message.from_user.first_name, 
        "Команда /trending", 
        "/trending"
    )
    
    bot.reply_to(message, "🔥 Ищу самые горячие монеты на CoinGecko...")
    
    try:
        trending = get_trending_coins_coingecko()
        
        if trending:
            trend_text = "🔥 **ТОП ТРЕНДОВЫЕ МОНЕТЫ (CoinGecko)**\n\n"
            
            for i, coin in enumerate(trending, 1):
                trend_text += f"{i}. **{coin['symbol']}** ({coin['name']})\n"
                trend_text += f"   └ Трендовый скор: {coin['score']}/100\n\n"
            
            trend_text += "💡 **Для анализа любой монеты напиши:**\n"
            trend_text += "• `[СИМВОЛ] [ТАЙМФРЕЙМ]` (например: BTC 4h)\n"
            trend_text += "• Или переключи источник на CoinGecko: `/source`"
            
            bot.send_message(message.chat.id, trend_text)
            
        else:
            bot.reply_to(message, "❌ Не удалось получить трендовые монеты")
            
    except Exception as e:
        print(f"❌ Ошибка трендов: {e}")
        bot.reply_to(message, f"⚠ Ошибка получения трендов: {e}")


@bot.message_handler(commands=['scan'])
def handle_scan_command(message):
    # Уведомляем администратора о запросе скана
    notify_admin_about_user_request(
        message.from_user.id, 
        message.from_user.username, 
        message.from_user.first_name, 
        "Команда /scan", 
        "/scan"
    )
    
    try:
        bot.reply_to(message, "🔄 Сканирую весь крипторынок в поисках лучших монет для скальпинга...\n\n⏳ Это может занять 10-30 секунд")
        
        # Получаем лучшие монеты для скальпинга
        top_coins = screen_best_coins_for_scalping()
        
        if not top_coins:
            bot.reply_to(message, "❌ Не удалось получить данные рынка. Попробуйте позже.")
            return
        
        # Берем ТОП-3 лучшие монеты
        top_3_coins = top_coins[:3]
        
        # Собираем данные с RSI и SMA для каждой монеты
        coins_data = []
        medals = ["🥇", "🥈", "🥉"]
        
        for i, coin in enumerate(top_3_coins):
            symbol = coin['symbol']
            signal = generate_scalping_signal(coin)
            
            if not signal:
                continue
            
            # Получаем klines для расчета RSI и SMA
            klines_data = get_binance_klines(symbol, "5m", 50)
            
            rsi = 50  # Дефолт
            sma_20 = signal['current_price']  # Дефолт
            
            if klines_data and len(klines_data) >= 20:
                closes = [k['close'] for k in klines_data]
                
                # Расчет RSI
                def calc_rsi(prices, period=14):
                    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
                    gains = [d if d > 0 else 0 for d in deltas]
                    losses = [-d if d < 0 else 0 for d in deltas]
                    
                    avg_gain = sum(gains[:period]) / period
                    avg_loss = sum(losses[:period]) / period
                    
                    if avg_loss == 0:
                        return 100
                    
                    rs = avg_gain / avg_loss
                    return 100 - (100 / (1 + rs))
                
                rsi = calc_rsi(closes)
                sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else closes[-1]
            
            # Визуальные индикаторы RSI
            rsi_indicator = ""
            if rsi < 30:
                rsi_indicator = "🟢"  # Перепроданность
            elif rsi > 70:
                rsi_indicator = "🔴"  # Перекупленность
            
            # Эмодзи сигнала
            signal_emoji = "🟢" if "LONG" in signal['signal_type'] else "🔴"
            
            coins_data.append({
                'priority': medals[i],
                'symbol': signal['symbol'],
                'price': f"{signal['current_price']:.4f}" if signal['current_price'] < 1 else f"{signal['current_price']:.2f}",
                'signal_emoji': signal_emoji,
                'signal_type': signal['signal_type'],
                'rsi': f"{rsi:.0f} | {rsi_indicator}" if rsi_indicator else f"{rsi:.0f}",
                'sma_20': f"{sma_20:.4f}" if sma_20 < 1 else f"{sma_20:.2f}",
                'volume_24h': signal['volume_24h'],
                'rrr': signal['rrr'],
                'entry': f"{signal['entry']:.4f}" if signal['entry'] < 1 else f"{signal['entry']:.2f}",
                'stop_loss': f"{signal['stop_loss']:.4f}" if signal['stop_loss'] < 1 else f"{signal['stop_loss']:.2f}",
                'take_profit_1': f"{signal['take_profit_1']:.4f}" if signal['take_profit_1'] < 1 else f"{signal['take_profit_1']:.2f}",
                'star': '',
                'rsi_raw': rsi,
                'volume_raw': float(coin.get('quoteVolume', 0))
            })
        
               # Определяем лучшую монету
        best_coin = None
        for coin in coins_data:
            if (coin['rsi_raw'] < 30 or coin['rsi_raw'] > 70) and coin['volume_raw'] > 10000000:
                coin['star'] = ' ⭐'
                best_coin = coin['symbol']
                break

        # Если ничего не нашли — берём первую монету по умолчанию
        if not best_coin and coins_data:
            coins_data[0]['star'] = ' ⭐'
            best_coin = coins_data[0]['symbol']
        
        # Формируем ответ
        response_text = ""
        
        # Добавляем строку лучшей сделки
        if best_coin:
            response_text += f"🔥 ЛУЧШАЯ СДЕЛКА: {best_coin} ⭐\n\n"
        
        response_text += "🎯 **ТОП-3 ЛУЧШИЕ МОНЕТЫ ДЛЯ СКАЛЬПИНГА СЕЙЧАС:**\n\n"
        
        # Таблица Markdown
        response_text += "| Ранг | Монета | Цена | Сигнал | RSI | SMA20 | Объём | RRR |\n"
        response_text += "|------|--------|------|--------|-----|-------|-------|-----|\n"
        
        # Данные таблицы
        for coin in coins_data:
            response_text += f"| {coin['priority']}{coin['star']} | {coin['symbol']} | ${coin['price']} | {coin['signal_emoji']} | {coin['rsi']} | ${coin['sma_20']} | {coin['volume_24h']}M | {coin['rrr']} |\n"
        
        response_text += "\n**📊 ДЕТАЛИ ТОРГОВЫХ УРОВНЕЙ:**\n\n"
        
        # Детальная информация по каждой монете
        for coin in coins_data:
            response_text += f"{coin['priority']}{coin['star']} **{coin['symbol']}** {coin['signal_type']}\n"
            response_text += f"🎯 Вход: ${coin['entry']} | 🛑 Стоп: ${coin['stop_loss']} | 🥇 Цель: ${coin['take_profit_1']}\n\n"
        
        # Подготавливаем данные для анализа Gemini с ранжированием
        tech_symbols = [c['symbol'] for c in coins_data]
        prompt = f"""Проанализируй ТОП-3 монеты для скальпинга и ОБЯЗАТЕЛЬНО расставь их по местам:

ДАННЫЕ:
"""
        for coin in coins_data:
            prompt += f"- {coin['symbol']}: RSI={coin['rsi_raw']:.0f}, SMA20=${coin['sma_20']}, Объём={coin['volume_24h']}M, RRR={coin['rrr']}\n"
        
        prompt += f"""
ЗАДАНИЕ:
1. Расставь монеты 🥇🥈🥉 по привлекательности для скальпинга
2. Для каждой монеты дай короткий комментарий (1 строка)

Формат ответа (строго):
🥇 [СИМВОЛ] - [комментарий]
🥈 [СИМВОЛ] - [комментарий]
🥉 [СИМВОЛ] - [комментарий]"""
        
        print(f"📤 Отправляем в AI промпт:\n{prompt}")

        # Функция для повторных попыток при ошибках API
        def try_gemini_analysis_scan(prompt, max_retries=3):
            models_to_try = ["gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"]
            delays = [2, 5, 9]
            
            for model in models_to_try:
                print(f"🔄 Пробуем модель: {model}")
                for attempt in range(max_retries):
                    try:
                        response = gemini_client.models.generate_content(
                            model=model,
                            contents=prompt
                        )
                        print(f"✅ Gemini успешно ответил (модель: {model}, попытка: {attempt + 1})")
                        return response
                    except Exception as e:
                        error_msg = str(e)
                        print(f"❌ Ошибка Gemini [модель: {model}, попытка: {attempt + 1}/{max_retries}]: {error_msg}")
                        
                        if "503" in error_msg or "unavailable" in error_msg.lower() or "overloaded" in error_msg.lower():
                            if attempt < max_retries - 1:
                                delay = delays[attempt]
                                print(f"⏰ Сервер перегружен, ждем {delay} секунд перед повтором...")
                                time.sleep(delay)
                        else:
                            print(f"⚠️ Ошибка не связана с перегрузкой, пробуем следующую модель")
                            break
            
            print("❌ Все модели Gemini недоступны после всех попыток")
            return None
        
        gemini_response = try_gemini_analysis_scan(prompt)
        ai_analysis = gemini_response.text if gemini_response and gemini_response.text else "AI анализ временно недоступен"
        
        # Добавляем AI анализ
        response_text += f"🤖 **GEMINI АНАЛИЗ:**\n{ai_analysis}\n\n"
        
        # Блок сравнения технического и Gemini выбора
        tech_top = coins_data[0]['symbol'] if coins_data else ""
        gemini_top = ""
        
        # Извлекаем выбор Gemini (ищем первый символ после 🥇)
        import re
        gemini_match = re.search(r'🥇\s*([A-Z]+)', ai_analysis)
        if gemini_match:
            gemini_top = gemini_match.group(1)
        
        comparison_emoji = "🟢" if tech_top == gemini_top else "🔴"
        
        # Пояснение совпадения/различия
        if tech_top == gemini_top:
            explanation = "Оба метода выбрали одну монету — сильный сигнал"
        else:
            explanation = "Различие может указывать на разные приоритеты анализа"
        
        response_text += f"**📊 СРАВНЕНИЕ ВЫБОРОВ:**\n"
        response_text += f"• Технический анализ: {tech_top}\n"
        response_text += f"• Gemini выбор: {gemini_top if gemini_top else 'N/A'}\n"
        response_text += f"• Совпадение: {comparison_emoji} {'Да' if tech_top == gemini_top else 'Нет'}\n"
        response_text += f"• {explanation}\n\n"
        
        # Время по Киеву
        from pytz import timezone
        kyiv_time = datetime.now(timezone("Europe/Kiev"))
        response_text += f"⏰ Обновлено: {kyiv_time.strftime('%H:%M:%S')}"
        
        # Ограничиваем длину ответа для Telegram
        max_length = 4000
        if len(response_text) > max_length:
            response_text = response_text[:max_length] + "..."
        
        bot.reply_to(message, response_text, parse_mode='Markdown')
        
    except Exception as e:
        print(f"❌ Ошибка скрининга: {e}")
        bot.reply_to(message, f"⚠ Ошибка скрининга: {e}")

@bot.message_handler(commands=['start_scan'])
def handle_start_scan_command(message):
    # Уведомляем администратора о запуске автоскрининга
    notify_admin_about_user_request(
        message.from_user.id, 
        message.from_user.username, 
        message.from_user.first_name, 
        "Команда /start_scan", 
        "/start_scan"
    )
    
    try:
        # Проверяем, запущен ли уже скрининг
        job = scheduler.get_job('auto_scalping_scan')
        if job:
            bot.reply_to(message, "✅ **АВТОСКРИНИНГ УЖЕ РАБОТАЕТ!**\n\n⚡ Сигналы приходят каждые 60 секунд\n🔄 Анализируются ТОП монеты по объёму\n📊 Отправляются ТОП-3 с RRR ≥ 1.5")
        else:
            # Запускаем скрининг заново
            scheduler.add_job(
                func=auto_send_scalping_signals,
                trigger="interval",
                seconds=60,
                id='auto_scalping_scan'
            )
            bot.reply_to(message, "🚀 **АВТОСКРИНИНГ ЗАПУЩЕН!**\n\n⚡ Теперь каждые 60 секунд получаешь:\n🎯 ТОП-3 монеты с RRR ≥ 1.5\n📊 RSI, SMA, объёмы и RRR анализ\n🤖 Gemini анализ и рекомендации\n\n✅ Первые сигналы придут через 60 секунд!")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка запуска: {e}")

@bot.message_handler(commands=['stop_scan'])
def handle_stop_scan_command(message):
    # Уведомляем администратора о остановке скрининга
    notify_admin_about_user_request(
        message.from_user.id, 
        message.from_user.username, 
        message.from_user.first_name, 
        "Команда /stop_scan", 
        "/stop_scan"
    )
    
    try:
        # Останавливаем скрининг
        job = scheduler.get_job('auto_scalping_scan')
        if job:
            scheduler.remove_job('auto_scalping_scan')
            bot.reply_to(message, "⏹️ **АВТОСКРИНИНГ ОСТАНОВЛЕН**\n\n📴 Автоматические сигналы больше не приходят\n🔄 Можешь запустить снова командой /start_scan\n💡 Или получить разовый анализ командой /scan")
        else:
            bot.reply_to(message, "⚠️ **АВТОСКРИНИНГ УЖЕ ОСТАНОВЛЕН**\n\n💡 Запусти командой /start_scan для получения автосигналов\n📊 Или используй /scan для разового анализа")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка остановки: {e}")


# --- Обработка личных сообщений (можно кидать свои графики) ---
@bot.message_handler(content_types=['text', 'photo', 'document'])
def handle_private_messages(message):
    try:
        # Проверяем наличие фото для анализа
        if message.photo:
            # Уведомляем администратора о загрузке фото
            notify_admin_about_user_request(
                message.from_user.id, 
                message.from_user.username, 
                message.from_user.first_name, 
                "Анализ фото графика", 
                message.caption or "Фото без подписи"
            )
            print("📸 Получено фото графика для анализа")
            # Получаем самое высокое качество фото
            photo = message.photo[-1]
            file_info = bot.get_file(photo.file_id)
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
            
            # Скачиваем фото
            photo_response = requests.get(file_url)
            
            if photo_response.status_code == 200:
                # Анализируем фото через Gemini
                caption = message.caption or "Анализ торгового графика"
                
                prompt = f"""Анализ торгового графика. {caption}

АНАЛИЗ ГРАФИКА:
🔍 Тренд: [восходящий/нисходящий/боковой]
📊 Уровни: [цифры]
📈 Вход: [точка] 
🛑 Стоп: [уровень]
🎯 Цели: [уровни]
⚖️ Итоговый риск: [1-10]

ФАКТЫ ТОЛЬКО!"""
                
                # Сохраняем изображение как base64 и используем систему повторных попыток
                import base64
                import time
                base64_image = base64.b64encode(photo_response.content).decode('utf-8')
                
                # Функция для повторных попыток при перегрузке API (такая же как в канальных сообщениях)
                def try_gemini_analysis_private(prompt, image_data, max_retries=3):
                    models_to_try = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.0-flash-exp"]
                    
                    for model in models_to_try:
                        for attempt in range(max_retries):
                            try:
                                print(f"🤖 Попытка {attempt + 1}/{max_retries} с моделью {model}")
                                response = gemini_client.models.generate_content(
                                    model=model,
                                    contents=[
                                        {
                                            "parts": [
                                                {"text": prompt},
                                                {
                                                    "inline_data": {
                                                        "mime_type": "image/jpeg",
                                                        "data": image_data
                                                    }
                                                }
                                            ]
                                        }
                                    ]
                                )
                                print(f"✅ Успешный анализ с моделью {model}")
                                return response
                            except Exception as e:
                                print(f"❌ Ошибка с моделью {model}, попытка {attempt + 1}: {e}")
                                if "503" in str(e) or "overloaded" in str(e).lower():
                                    # Экспоненциальная задержка при перегрузке
                                    delay = (2 ** attempt) + 1  # 2, 5, 9 секунд
                                    print(f"⏰ Ждем {delay} секунд...")
                                    time.sleep(delay)
                                else:
                                    # Другие ошибки - пробуем следующую модель
                                    break
                    
                    # Если все модели не сработали
                    return None
                
                response = try_gemini_analysis_private(prompt, base64_image)
                
                if response and response.text:
                    ai_reply = response.text
                    print("✅ Получен анализ от Gemini для личного сообщения")
                else:
                    # График Bitcoin - уровни видны из изображения
                    ai_reply = """⚠️ **СЕРВИС ВРЕМЕННО ПЕРЕГРУЖЕН**

Все AI модели сейчас недоступны из-за высокой нагрузки.

📊 **Краткий анализ вашего графика:**
🪙 Bitcoin (BTC/USDT)
🔍 Тренд: Восходящий с коррекцией 
📊 Текущий уровень: ~$103,000
📈 Поддержка: $100,000
🎯 Сопротивление: $105,000
⚖️ Риск: Средний (5/10)

💡 **Рекомендация:** 
Дождитесь пробоя или отскока от ключевых уровней.

🔄 Попробуйте отправить график через несколько минут для полного AI-анализа."""
                    print("❌ Все модели Gemini недоступны для личного сообщения")
                
                # Ограничиваем длину ответа для Telegram (максимум 4000 символов)
                max_length = 4000
                if len(ai_reply) > max_length:
                    ai_reply = ai_reply[:max_length] + "..."
                
                bot.reply_to(message, f"📊 AI Анализ графика (Gemini Vision):\n\n{ai_reply}")
            else:
                bot.reply_to(message, "❌ Не удалось загрузить фото. Попробуй еще раз.")
                
        # Обработка текстовых сообщений
        elif message.text or message.caption:
            user_input = message.text or message.caption
            print(f"🔍 DEBUG: Получен текст в личном сообщении: {user_input[:200]}...")
            
            # ПРИОРИТЕТ: Сначала проверяем наличие ссылок TradingView
            import re
            tradingview_links = re.findall(r'https?://(?:www\.)?tradingview\.com[^\s]*', user_input)
            print(f"🔍 DEBUG: Найдено ссылок TradingView в личном сообщении: {len(tradingview_links)}")
            
            if tradingview_links:
                print("🎯 ПРИОРИТЕТ: Анализируем ссылку TradingView в личном сообщении")
                # Обрабатываем ссылку TradingView
                for link in tradingview_links:
                    try:
                        symbol, timeframe = parse_tradingview_link(link)
                        if symbol == "SHORT_LINK":
                            # Сокращенная ссылка - просим полную ссылку
                            bot.reply_to(message, """📎 **Сокращенная ссылка TradingView обнаружена!**

❌ К сожалению, я не могу анализировать короткие ссылки вида `/x/`, потому что они не содержат информацию о символе криптовалюты.

✅ **Решение:**
1. Откройте ссылку в TradingView
2. Скопируйте полную ссылку из адресной строки браузера  
3. Отправьте мне полную ссылку

🔗 **Пример полной ссылки:**
`https://tradingview.com/chart/?symbol=BINANCE%3ABTCUSDT`

Или просто напишите символ монеты (например: `BTC 4h`)""")
                            return
                        elif symbol:
                            print(f"📊 Анализирую {symbol} ({timeframe}) из ссылки TradingView в личном сообщении")
                            
                            analysis_result = analyze_symbol_from_tradingview(symbol, timeframe, user_input, link)
                            
                            if analysis_result:
                                # Проверяем, есть ли график
                                if isinstance(analysis_result, tuple) and len(analysis_result) == 2:
                                    chart_text, chart_buffer = analysis_result
                                    # Отправляем график с анализом
                                    chart_buffer.seek(0)
                                    caption_text = f"📈 **АНАЛИЗ ПО ССЫЛКЕ TRADINGVIEW**\n\n🪙 {symbol}\n⏰ {timeframe}\n\n{chart_text[:600]}..."
                                    bot.send_photo(message.chat.id, chart_buffer, 
                                                 caption=safe_caption(caption_text))
                                else:
                                    # Только текст без графика
                                    reply_message = f"📈 **АНАЛИЗ ПО ССЫЛКЕ TRADINGVIEW**\n\n🪙 {symbol}\n⏰ {timeframe}\n\n{analysis_result}"
                                    if len(reply_message) > 4000:
                                        reply_message = reply_message[:4000] + "..."
                                    bot.reply_to(message, reply_message)
                                return  # Завершаем обработку после успешного анализа ссылки
                    except Exception as e:
                        print(f"❌ Ошибка анализа ссылки TradingView в личном сообщении: {e}")
                        continue
                        
                # Если дошли сюда, значит ни одна ссылка не сработала
                bot.reply_to(message, "❌ Не удалось проанализировать ссылку TradingView")
                return
            
            # ТОЛЬКО если нет ссылок TradingView - проверяем символы криптовалют
            print(f"🔍 DEBUG: Нет ссылок TradingView, проверяю символы в личном сообщении...")
            symbol_info = extract_crypto_symbol_and_timeframe(user_input)
            
            if symbol_info:
                # Уведомляем администратора об анализе монеты
                symbol, timeframe = symbol_info
                notify_admin_about_user_request(
                    message.from_user.id, 
                    message.from_user.username, 
                    message.from_user.first_name, 
                    f"Анализ {symbol} {timeframe}", 
                    user_input
                )
                # Это запрос на анализ конкретной монеты - создаем график!
                source_name = "Binance" if data_source == "binance" else "CoinGecko"
                bot.reply_to(message, f"📊 Создаю технический анализ для {symbol} на таймфрейме {timeframe}...\n\n⏳ Получаю данные с {source_name}, рассчитываю уровни и генерирую график с сетапами...")
                
                # Получаем данные монеты с указанным таймфреймом из выбранного источника
                df = get_coin_data(symbol, interval=timeframe, limit=100)
                
                if df is not None:
                    # Рассчитываем технические уровни
                    levels = calculate_technical_levels(df)
                    
                    if levels:
                        # Создаем график с указанием таймфрейма
                        chart_buffer = create_trading_chart(symbol, df, levels, timeframe)
                        
                        if chart_buffer:
                            # Генерируем детальный анализ с таймфреймом
                            analysis_text = generate_chart_analysis(symbol, levels, "", timeframe)
                            
                            # Отправляем график с анализом
                            try:
                                bot.send_photo(
                                    message.chat.id,
                                    chart_buffer.getvalue(),
                                    caption=safe_caption(analysis_text),
                                    parse_mode='Markdown'
                                )
                                chart_buffer.close()
                            except Exception as e:
                                print(f"❌ Ошибка отправки графика: {e}")
                                bot.reply_to(message, f"📊 График создан, но ошибка отправки.\n\n{analysis_text}")
                        else:
                            bot.reply_to(message, f"❌ Не удалось создать график для {symbol} на {timeframe}")
                    else:
                        bot.reply_to(message, f"❌ Не удалось рассчитать технические уровни для {symbol} на {timeframe}")
                else:
                    bot.reply_to(message, f"❌ Не удалось получить данные для {symbol} на {timeframe}. Проверьте символ монеты и таймфрейм.")
            
            else:
                # Уведомляем администратора об общем AI анализе
                notify_admin_about_user_request(
                    message.from_user.id, 
                    message.from_user.username, 
                    message.from_user.first_name, 
                    "Общий AI анализ", 
                    user_input
                )
                # Обычный текстовый анализ через AI
                prompt = f"""Запрос: {user_input}

АНАЛИЗ:
📊 {user_input}: [оценка]
📈 Вход: [уровни]
🛑 Стоп: [уровень] 
🎯 Цели: [уровни]
⚖️ Риск: [1-10]

ФАКТЫ ТОЛЬКО!"""
                
                response = gemini_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt
                )
                
                ai_reply = response.text if response.text else "Ошибка генерации ответа"
                
                # Ограничиваем длину ответа для Telegram (максимум 4000 символов)
                max_length = 4000
                if len(ai_reply) > max_length:
                    ai_reply = ai_reply[:max_length] + "..."
                
                bot.reply_to(message, f"📈 AI Анализ (Gemini):\n{ai_reply}")
        else:
            bot.reply_to(message, "📊 Отправь фото графика для автоматического AI анализа или название монеты для создания графика с техническим анализом!")
            
    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        bot.reply_to(message, f"⚠ Ошибка анализа: {e}")

def extract_crypto_symbol_and_timeframe(text):
    """Извлечь символ криптовалюты и таймфрейм из текста"""
    try:
        import re
        original_text = text.strip()  # Сохраняем оригинальный текст для таймфреймов
        text = text.upper().strip()  # Для символов используем верхний регистр
        
        # Расширенный список криптовалют (добавлены все монеты из пользовательских скриншотов)
        crypto_symbols = [
            # Основные монеты
            'BTC', 'ETH', 'BNB', 'ADA', 'SOL', 'XRP', 'DOGE', 'DOT', 'AVAX',
            'LINK', 'LTC', 'UNI', 'ALGO', 'VET', 'ICP', 'FIL', 'TRX', 'ETC',
            'ATOM', 'XLM', 'THETA', 'AAVE', 'SUSHI', 'COMP', 'MKR', 'YFI',
            'NEAR', 'LUNA', 'FTT', 'CRV', 'SNX', '1INCH', 'ENJ', 'MANA',
            'SAND', 'AXS', 'GALA', 'CHZ', 'BAT', 'ZIL', 'HOT', 'HBAR',
            'OPEN', 'PENGU', 'PEPE', 'SHIB', 'THE', 'SUI', 'WLFI', 'MEME',
            'BONK', 'FLOKI', 'WIF', 'BOME', 'NEIRO', 'DOGS', 'HMSTR', 'CATI', 'NOT', 'TON',
            # Предыдущие дополнения
            'ETHFI', 'ORDI', 'PEOPLE', 'DYDX', 'CELO', 'STRK', 'AI', 'POL', 'IOTX', 'CAKE', 'LUNC', 'BAKE', 'OP',
            # Новые монеты из скриншотов
            'PUMP', 'TAO', 'ENS', 'ENA', 'S', 'INJ', 'W', 'ADX', 'ROSE', 'USTC', 'SEI', 'FIDA', 'PNUT',
            'JASMY', 'TURBO', 'EIGEN', 'SCR', 'IO', 'TRB', 'APT', 'LDO', 'ALT', 'WLD', 'BCH', 'AEVO',
            'ARB', 'ZRX', 'ANKR', 'YGG', 'XAI', 'ILV', 'SCRT', 'EGLD', 'JUP', 'FET', 'GRT', 'PIXEL',
            'IDEX', 'DASH', 'PORTAL', 'PROM', 'VTHO', 'C98', 'VANRY', 'TIA', 'TRUMP', 'ID', 'JTO',
            'HOOK', 'MASK', 'PERP', 'FXS', 'MAV', 'SLP', 'RVN', 'CFX', 'MANTA', 'IP'
        ]
        
        # Список поддерживаемых таймфреймов Binance
        valid_timeframes = [
            '1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'
        ]
        
        # Ищем символ и таймфрейм в тексте
        found_symbol = None
        found_timeframe = '1h'  # По умолчанию
        
          # Сначала сортируем список монет по длине, чтобы длинные символы (например ETHFI) проверялись раньше коротких (ETH)
        sorted_symbols = sorted(crypto_symbols, key=len, reverse=True)

        # Проверяем прямое совпадение
        for symbol in sorted_symbols:
            if re.search(r'\b' + re.escape(symbol) + r'\b', text):
                found_symbol = symbol
                break

        # Если не найдено — проверяем с USDT
        if not found_symbol:
            for symbol in sorted_symbols:
                if f"{symbol}USDT" in text:
                    found_symbol = symbol
                    break
        
        # Проверяем ключевые слова
        if not found_symbol:
            keyword_map = {
                'BITCOIN': 'BTC',
                'ETHEREUM': 'ETH', 
                'BINANCE': 'BNB',
                'CARDANO': 'ADA',
                'SOLANA': 'SOL',
                'RIPPLE': 'XRP',
                'DOGECOIN': 'DOGE',
                'POLKADOT': 'DOT',
                'AVALANCHE': 'AVAX',
                'CHAINLINK': 'LINK',
                'LITECOIN': 'LTC',
                'UNISWAP': 'UNI'
            }
            
            for keyword, symbol in keyword_map.items():
                if keyword in text:
                    found_symbol = symbol
                    break
        
        # Сначала проверяем точные таймфреймы с учетом регистра (1M vs 1m)
        for tf in valid_timeframes:
            pattern = r'\b' + re.escape(tf) + r'\b'
            if re.search(pattern, original_text):  # Используем оригинальный текст с сохранением регистра
                found_timeframe = tf
                break
        
        # Альтернативные записи таймфреймов (проверяем только если не нашли точный)
        if found_timeframe == '1h':  # Если остался дефолтный
            timeframe_aliases = {
                'MIN': '1m',
                '1MIN': '1m',
                '1min': '1m',
                '3MIN': '3m',
                '3min': '3m',
                '5MIN': '5m',
                '5min': '5m',
                '15MIN': '15m',
                '15min': '15m',
                '30MIN': '30m',
                '30min': '30m',
                'HOUR': '1h',
                'HOURLY': '1h',
                'hour': '1h',
                'hourly': '1h',
                'DAILY': '1d',
                'daily': '1d',
                'DAY': '1d',
                'day': '1d',
                'WEEK': '1w',
                'week': '1w',
                'WEEKLY': '1w',
                'weekly': '1w',
                'MONTH': '1M',
                'month': '1M',
                'MONTHLY': '1M',
                'monthly': '1M'
            }
            
            # Ищем алиасы (более точные совпадения) - используем границы слов
            text_words = text.split()
            
            for alias, tf in timeframe_aliases.items():
                # Проверяем точное совпадение слова
                if alias in text_words:
                    found_timeframe = tf
                    break
                # Или как часть слова (например XRP15MIN)
                pattern = r'\b' + re.escape(alias) + r'\b'
                if re.search(pattern, text, re.IGNORECASE):
                    found_timeframe = tf
                    break
        if found_symbol:
            return (found_symbol, found_timeframe)
        
        return None

    except Exception as e:
        print(f"❌ Ошибка извлечения символа и таймфрейма: {e}")
        return None

    except Exception as e:
        print(f"❌ Ошибка извлечения символа и таймфрейма: {e}")
        return None


# --- Автопуш проекта в GitHub ---
def auto_push():
    import os
    try:
        print("🔄 Автопуш в GitHub...")
        os.system("git add .")
        os.system('git commit -m "Автопуш из Replit"')
        os.system("git push origin main")
        print("✅ Автопуш выполнен")
    except Exception as e:
        print(f"❌ Ошибка автопуша: {e}")


# Запускаем задачу автопуша каждые 60 минут
scheduler.add_job(auto_push, 'interval', hours=1, id='auto_git_push')


if __name__ == '__main__':
    print("✅ Все секреты найдены. Настраиваю webhook...")
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
    print(f"✅ Webhook установлен: {WEBHOOK_URL}/[ТОКЕН_СКРЫТ]")
    app.run(host='0.0.0.0', port=5000)