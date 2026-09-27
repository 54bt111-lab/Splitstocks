name: Reverse Split Bot Runner

on:
  # التشغيل المجدول: كل يوم أحد الساعة 19:00 UTC (الساعة 22:00 بتوقيت مكة المكرمة)
  schedule:
    - cron: '0 19 * * 0'
  
  # إمكانية التشغيل اليدوي من واجهة GitHub
  workflow_dispatch:

jobs:
  run-bot:
    runs-runs-on: ubuntu-latest

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run Weekly Split Search
        env:
          FMP_API_KEY: ${{ secrets.FMP_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          python main.py --action weekly
