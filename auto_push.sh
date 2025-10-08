#!/bin/bash
git config --global user.name "replit-bot"
git config --global user.email "bot@replit.com"
git add .
git commit -m "Авто-пуш из Replit" || echo "⚠️ Нет изменений для коммита"
git push origin main