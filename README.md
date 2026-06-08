# Expense Tracker – Smart Financial Management with OCR

![Status](https://img.shields.io/badge/status-complete-brightgreen)
![Python](https://img.shields.io/badge/python-3.14-blue)
![Flask](https://img.shields.io/badge/flask-3.1-red)
![License](https://img.shields.io/badge/license-MIT-green)

## 📌 Overview

**Expense Tracker** is a full-stack web and mobile application designed to help individuals and small business owners track their daily expenses, manage debts, and gain financial awareness. The application features OCR-based receipt scanning, AI-powered expense categorization, offline support, and installable mobile app capabilities.

🌐 **Live Demo:** [https://kidist.pythonanywhere.com](https://kidist.pythonanywhere.com)

📱 **APK Download:** Available upon request or via PWABuilder

---

## 🎯 Problem Statement

Many individuals and small business owners in Ethiopia struggle with:

- ❌ Forgetting expenses due to reliance on memory or paper notebooks
- ❌ No clear overview of monthly spending patterns
- ❌ Difficulty tracking cash-based transactions
- ❌ Confusion when managing borrowed/lent money
- ❌ Time-consuming manual data entry

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Manual Expense Entry** | Record expenses with amount, description, date, and category |
| **OCR Receipt Scanner** | Upload bank SMS/receipt screenshots; system auto-extracts details |
| **Smart Categorization** | AI automatically categorizes expenses based on keywords |
| **Spending Analytics** | Interactive pie and bar charts show spending patterns |
| **Debt Tracking** | Track money owed to you and money you owe others |
| **Offline Support** | Works without internet; syncs when back online |
| **Mobile App** | Installable on Android phones (PWA + APK) |
| **User Authentication** | Secure login/register with password hashing |

---

## 🛠️ Technology Stack

| Category | Technologies |
|----------|--------------|
| **Backend** | Python, Flask, SQLAlchemy |
| **Database** | SQLite |
| **Frontend** | HTML5, CSS3, JavaScript, Bootstrap 5 |
| **OCR** | Tesseract OCR |
| **Charts** | Chart.js |
| **PWA** | Service Workers, IndexedDB, Web App Manifest |
| **Deployment** | PythonAnywhere |
| **Mobile APK** | PWABuilder, Bubblewrap TWA |

---

## 📁 Project Structure
expense-tracker/
├── app.py # Main Flask application
├── requirements.txt # Python dependencies
├── templates/ # HTML templates
│ ├── base.html # Main layout with sidebar
│ ├── auth_base.html # Login/register layout
│ ├── login.html # Login page
│ ├── register.html # Registration page
│ ├── dashboard.html # Dashboard with charts
│ ├── add_expense.html # Add expense (manual + OCR)
│ ├── transactions.html # View all transactions
│ ├── debts.html # Debt tracking page
│ ├── search.html # Search and filter
│ └── ocr_confirm.html # OCR confirmation page
├── static/ # Static assets
│ ├── css/style.css # Custom styles
│ ├── js/ # JavaScript files
│ ├── icons/ # App icons (PWA)
│ ├── manifest.json # PWA manifest
│ └── sw.js # Service Worker
├── uploads/ # Temporary upload folder
└── instance/ # Database (auto-generated)

