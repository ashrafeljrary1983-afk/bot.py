import asyncio
import json
import os
import time
import urllib.request
from threading import Thread
from flask import Flask
import numpy as np
import pandas as pd
from telegram import Bot

# --- إعدادات خادم الويب (لكي يقبل الرابط المجاني على Render) ---
app = Flask(__name__)


@app.route("/")
def home():
  return "Gold Trading Bot is running 24/7! 🚀"


def run_web():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)


# --- إعدادات تليجرام وبوت الذهب ---
TOKEN = "8797846395:AAHDyPh81RAusRUOnOpRG2aBR2Ovut4vNY0"
CHANNEL_NAME = "-1003976097371"  # معرف قناتك الرقمي

bot = Bot(token=TOKEN)


def fetch_gold_data_from_web():
  try:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=5m&range=2d"
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req) as response:
      data = json.loads(response.read().decode())

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    df = pd.DataFrame({
        "Open": quote["open"],
        "High": quote["high"],
        "Low": quote["low"],
        "Close": quote["close"],
        "Volume": quote["volume"],
    }, index=pd.to_datetime(timestamps, unit="s"))

    df.dropna(inplace=True)
    return df
  except Exception as e:
    print(f"خطأ في جلب البيانات من الشبكة: {e}")
    return None


def calculate_heikin_ashi(df):
  ha = pd.DataFrame(index=df.index)
  ha["HA_Close"] = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4

  ha_open = [(df["Open"].iloc[0] + df["Close"].iloc[0]) / 2]
  for i in range(1, len(df)):
    prev_open = (ha_open[i - 1] + ha["HA_Close"].iloc[i - 1]) / 2
    ha_open.append(prev_open)

  ha["HA_Open"] = ha_open
  ha["HA_High"] = df[["High"]].join(ha[["HA_Open", "HA_Close"]]).max(axis=1)
  ha["HA_Low"] = df[["Low"]].join(ha[["HA_Open", "HA_Close"]]).min(axis=1)
  return ha


def calculate_vwap(df):
  v = df["Volume"]
  tp = (df["High"] + df["Low"] + df["Close"]) / 3
  return (tp * v).cumsum() / v.cumsum()


async def send_telegram_alert(message):
  try:
    await bot.send_message(
        chat_id=CHANNEL_NAME, text=message, parse_mode="Markdown"
    )
    print("تم إرسال التنبيه بنجاح إلى قناتك على تليجرام 🚀")
  except Exception as e:
    print(f"خطأ في الإرسال لتليجرام: {e}")


def check_market_and_alert():
  df = fetch_gold_data_from_web()
  if df is None or df.empty:
    print("تعذر جلب البيانات حالياً.")
    return

  ha = calculate_heikin_ashi(df)
  df["VWAP"] = calculate_vwap(df)

  real_close = df["Close"].iloc[-1]
  real_open = df["Open"].iloc[-1]
  prev_real_high = df["High"].iloc[-2]
  prev_real_low = df["High"].iloc[-2]
  current_vwap = df["VWAP"].iloc[-1]

  ha_close = ha["HA_Close"].iloc[-1]
  ha_open = ha["HA_Open"].iloc[-1]
  ha_low = ha["HA_Low"].iloc[-1]
  ha_high = ha["HA_High"].iloc[-1]

  df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
  df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
  ema9 = df["EMA_9"].iloc[-1]
  ema21 = df["EMA_21"].iloc[-1]

  is_above_vwap = real_close > current_vwap
  is_below_vwap = real_close < current_vwap

  ha_bullish = (ha_close > ha_open) and (ha_low == ha_open)
  ha_bearish = (ha_close < ha_open) and (ha_high == ha_open)

  real_bullish_confirm = (real_close > real_open) and (
      real_close > prev_real_high
  )
  real_bearish_confirm = (real_close < real_open) and (
      real_close < prev_real_low
  )

  strength = 20
  if is_above_vwap or is_below_vwap:
    strength += 20
  if ha_bullish or ha_bearish:
    strength += 25
  if real_bullish_confirm or real_bearish_confirm:
    strength += 20
  if (ema9 > ema21 and is_above_vwap) or (ema9 < ema21 and is_below_vwap):
    strength += 15

  if (
      ha_bullish
      and real_bullish_confirm
      and is_above_vwap
      and strength >= 80
  ):
    signal = "شراء مؤكد وقوي (BUY) 🟢"
  elif (
      ha_bearish
      and real_bearish_confirm
      and is_below_vwap
      and strength >= 80
  ):
    signal = "بيع مؤكد وقوي (SELL) 🔴"
  else:
    signal = None

  entry = round(real_close, 2)
  atr_approx = entry * 0.0015

  if signal:
    if "شراء" in signal:
      sl = round(entry - atr_approx, 2)
      tp1 = round(entry + atr_approx, 2)
      tp2 = round(entry + (atr_approx * 2), 2)
    else:
      sl = round(entry + atr_approx, 2)
      tp1 = round(entry - atr_approx, 2)
      tp2 = round(entry - (atr_approx * 2), 2)

    msg = (
        f"🚨 **تنبيه صفقة ذهب جديدة (XAU/USD)** 🚨\n\n"
        f"• **الإشارة:** {signal}\n"
        f"• **منطقة الدخول:** {entry}\n"
        f"• **مؤشر VWAP:** {round(current_vwap, 2)}\n"
        f"• **وقف الخسارة (SL):** {sl}\n"
        f"• **الهدف الأول (TP1):** {tp1}\n"
        f"• **الهدف الثاني (TP2):** {tp2}\n"
        f"• **نسبة قوة الصفقة:** {strength}%\n"
        f"⚡ *تحليل: الهايكن أشي + الشموع العادية + المتوسطات + VWAP*"
    )
    asyncio.run(send_telegram_alert(msg))
  else:
    print(
        f"السعر الحالي: {entry} | لا توجد إشارة مطابقة للشروط حالياً (القوة:"
        f" {strength}%)"
    )


def run_bot_loop():
  print("🤖 بدأ تشغيل حلقة مراقبة الذهب على السحابة...")
  test_msg = (
      "🚨 **رسالة تجريبية** 🚨\n\n• **الحالة:** يعمل البوت مجاناً على Render 24/7 🟢"
  )
  try:
    asyncio.run(send_telegram_alert(test_msg))
  except Exception as e:
    print(f"خطأ: {e}")

  while True:
    try:
      check_market_and_alert()
    except Exception as e:
      print(f"خطأ مؤقت ولكن البوت مستمر: {e}")
    time.sleep(300)


if __name__ == "__main__":
  # تشغيل خادم الويب في خلفية النظام
  t = Thread(target=run_web)
  t.start()

  # تشغيل بوت التداول
  run_bot_loop()
  
