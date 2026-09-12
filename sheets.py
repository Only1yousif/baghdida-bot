# -*- coding: utf-8 -*-
"""
sheets.py
---------
طبقة التعامل مع Google Sheets (قاعدة البيانات المجانية للمشروع).
Handles all Google Sheets read/write logic for users & survey responses.

يحتاج المشروع اثنين Sheet (تبويبين / Worksheets) داخل نفس الملف:
  1. "users"     -> تخزين المشتركين (user_id, first_name, username, joined_at)
  2. "responses" -> تخزين إجابات الاستبيان (user_id + كل الحقول)
"""

import json
import os
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

USERS_HEADERS = ["user_id", "first_name", "username", "joined_at"]

RESPONSES_HEADERS = [
    "user_id", "first_name", "username", "submitted_at",
    "team_name", "team_color", "team_chant", "team_split_rating",
    "food_rating", "food_notes",
    "entertainment_rating", "entertainment_notes",
    "lectures_rating", "lectures_notes",
    "mosul_trip_rating", "mosul_trip_notes",
    "march_rating", "march_notes",
    "last_day_party_rating", "last_day_party_notes",
    "open_opinion", "improvement_ideas",
]


def _get_client():
    """
    يبني اتصال gspread باستخدام بيانات حساب الخدمة (Service Account).
    يقرأ الـ JSON إما من متغير بيئة نصي أو من مسار ملف.
    """
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_sheet():
    client = _get_client()
    sheet_id = os.environ["SHEET_ID"]
    return client.open_by_key(sheet_id)


def _ensure_worksheet(spreadsheet, title, headers):
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers) + 2)
        ws.append_row(headers)
        return ws

    # تأكد أن الصف الأول هو رؤوس الأعمدة الصحيحة
    first_row = ws.row_values(1)
    if first_row != headers:
        ws.update("A1", [headers])
    return ws


def register_user(user_id: int, first_name: str, username: str) -> bool:
    """
    يسجل مستخدم جديد إن لم يكن موجوداً مسبقاً.
    يرجع True لو كان تسجيلاً جديداً، False لو كان مسجلاً من قبل.
    """
    spreadsheet = _get_sheet()
    ws = _ensure_worksheet(spreadsheet, "users", USERS_HEADERS)

    existing_ids = ws.col_values(1)[1:]  # تجاهل رأس العمود
    if str(user_id) in existing_ids:
        return False

    ws.append_row([
        str(user_id),
        first_name or "",
        username or "",
        datetime.now(timezone.utc).isoformat(),
    ])
    return True


def get_all_user_ids() -> list:
    spreadsheet = _get_sheet()
    ws = _ensure_worksheet(spreadsheet, "users", USERS_HEADERS)
    return [uid for uid in ws.col_values(1)[1:] if uid]


def save_response(user_id: int, first_name: str, username: str, answers: dict) -> None:
    """
    يحفظ إجابات الاستبيان. لو المستخدم أرسل الاستبيان قبل، يحدّث سطره
    بدل ما يكرر السجل (upsert بسيط بالاعتماد على user_id).
    """
    spreadsheet = _get_sheet()
    ws = _ensure_worksheet(spreadsheet, "responses", RESPONSES_HEADERS)

    row = [
        str(user_id),
        first_name or "",
        username or "",
        answers.get("_submitted_at", datetime.now(timezone.utc).isoformat()),
    ]
    for field in RESPONSES_HEADERS[4:]:
        row.append(answers.get(field, ""))

    existing_ids = ws.col_values(1)[1:]
    if str(user_id) in existing_ids:
        row_index = existing_ids.index(str(user_id)) + 2  # +2: رأس العمود + فهرسة من 1
        ws.update(f"A{row_index}", [row])
    else:
        ws.append_row(row)
