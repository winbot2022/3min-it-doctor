# -*- coding: utf-8 -*-
import os
import re
from io import BytesIO
from datetime import datetime
import pytz

import streamlit as st
import plotly.graph_objects as go
from fpdf import FPDF
from openai import OpenAI

# ===== Google Sheets（イベント計測）=====
import gspread
from google.oauth2.service_account import Credentials


# =====================================================
# 共通：日本時間
# =====================================================
def _jst_now_str():
    jst = pytz.timezone("Asia/Tokyo")
    return datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")


# =====================================================
# Google Sheets 接続（EVENTS_IT_DOCTOR）
# =====================================================
import json

@st.cache_resource
def _open_ws():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    sa_info = st.secrets["GOOGLE_SERVICE_JSON"]

    # ★ここが重要：Secrets が文字列で入っている場合は JSON として parse
    if isinstance(sa_info, str):
        sa_info = sa_info.strip()
        sa_info = json.loads(sa_info)

    creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(st.secrets["SPREADSHEET_ID"])
    ws = sh.worksheet(st.secrets["EVENTS_TAB"])  # "EVENTS_IT_DOCTOR"
    return ws

def log_event(event_type: str, path: str = ""):
    """visit / click_start のみ記録（失敗してもアプリは落とさない）"""
    try:
        ws = _open_ws()
        ua = ""
        try:
            ua = st.context.headers.get("user-agent", "")
        except Exception:
            ua = ""
        ws.append_row(
            [_jst_now_str(), event_type, "it_doctor", path],
            value_input_option="RAW",
        )
    except Exception:
        pass


# =====================================================
# OpenAI クライアント
# =====================================================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# =====================================================
# タイプ分類
# =====================================================
TYPE_INFO = {
    "A": {"label": "🚨 IT機能不全・重篤（ICU行き）"},
    "B": {"label": "⚠️ メタボリック・システム症候群"},
    "C": {"label": "💊 慢性・属人化疲労"},
    "D": {"label": "🏃 リハビリ順調・回復期"},
    "E": {"label": "💪 健康優良・アスリート企業"},
}


# =====================================================
# PDF生成
# =====================================================
def generate_pdf(score, type_key, answers, free_text, ai_comment):
    body = ai_comment

    # Markdown / 強調 / 絵文字除去
    body = re.sub(r'^\s*#{1,6}\s*', '', body, flags=re.MULTILINE)
    body = body.replace('*', '').replace('＊', '')
    body = re.sub(r'\n{3,}', '\n\n', body)
    body = ''.join(ch for ch in body if ord(ch) <= 0xFFFF)

    pdf = FPDF(format='A4')
    pdf.add_page()
    pdf.add_font("Noto", "", "NotoSansJP-Regular.ttf", uni=True)
    pdf.set_auto_page_break(auto=True, margin=18)

    # タイトル
    pdf.set_font("Noto", size=18)
    pdf.cell(0, 12, "IT主治医 診断レポート（要約と処方箋）", ln=True)

    # タイプ
    raw_label = TYPE_INFO[type_key]["label"]
    type_label = "".join(ch for ch in raw_label if ord(ch) <= 0xFFFF)

    pdf.ln(4)
    pdf.set_font("Noto", size=12)
    pdf.multi_cell(0, 7, f"診断コメント：{type_label}")
    pdf.ln(6)

    # 本文
    pdf.set_font("Noto", size=11)
    pdf.multi_cell(0, 6, body)

    buffer = BytesIO()
    buffer.write(pdf.output(dest="S").encode("latin1"))
    buffer.seek(0)
    return buffer.getvalue()


# =====================================================
# AIコメント生成
# =====================================================
def generate_ai_comment(score, type_key, answers, free_text):
    type_label = TYPE_INFO[type_key]["label"]

    prompt = f"""
あなたは製造業の生産管理・IT活用に詳しい「IT主治医コンサルタント」です。

【診断タイプ】
{type_label}

【スコア】
{score} / 10

【Yes/No回答】
{answers}

【自由記述】
{free_text}

以下の流れで、600〜800字でコメントしてください。

1. 現在のIT・システム運用の状態像
2. 10問から読み取れる症状（2〜3点）
3. 自由記述から見える現場の本音
4. 今後3〜6か月の改善ステップ（STEP1〜3）

注意：
- 人間の健康・食事・運動の話は書かない
- 製造現場のIT・業務プロセスに限定
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        temperature=0.7,
    )
    return res.choices[0].message.content.strip()


# =====================================================
# レーダーチャート
# =====================================================
def radar_chart(answers):
    categories = [f"Q{i}" for i in range(1, 11)]
    values = answers + [answers[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories + [categories[0]],
        fill="toself",
        name="Score",
        line=dict(color="royalblue")
    ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        showlegend=False
    )
    return fig


# =====================================================
# スコア → タイプ
# =====================================================
def classify_type(score):
    if score <= 3:
        return "A"
    elif score <= 5:
        return "B"
    elif score <= 7:
        return "C"
    elif score <= 9:
        return "D"
    else:
        return "E"


# =====================================================
# main()
# =====================================================
def main():

    # ---- UIテーマ（ドクターイエロー）----
    st.markdown("""
    <style>
        .stApp { background-color: #FFFDE7; }
        section[data-testid="stSidebar"] { background-color: #FFF9C4; }
        .stButton>button {
            background-color: #FDD835;
            color: black;
            border-radius: 8px;
            font-weight: bold;
            border: none;
        }
        .stButton>button:hover { background-color: #FBC02D; }
        h1, h2, h3 { color: #F57F17; }
    </style>
    """, unsafe_allow_html=True)

    st.title("🩺 IT主治医診断（3分）")

    # visit（1セッション1回）
    if "visit_logged" not in st.session_state:
        st.session_state.visit_logged = True
        log_event("visit", path="top")

    st.write("製造現場に導入したITが『なぜ使われないのか』を3分で可視化します。")

    questions = [
        "Q1. 現場がシステム操作を誰でも代替できる状態ですか？",
        "Q2. 実績入力は漏れなく行われていますか？",
        "Q3. マスタは継続的に更新されていますか？",
        "Q4. 工程・LTは現場と一致していますか？",
        "Q5. 現場は『使うと楽』と感じていますか？",
        "Q6. 経営会議でシステムデータを直接使っていますか？",
        "Q7. 改善要望は反映されていますか？",
        "Q8. 部門間で同じデータを見ていますか？",
        "Q9. 教育・引継ぎは仕組み化されていますか？",
        "Q10. 経営層はITを現場改善の中心と見ていますか？"
    ]

    answers_yn = []
    for q in questions:
        val = st.radio(q, ["No", "Yes"], horizontal=True)
        answers_yn.append(1 if val == "Yes" else 0)

    free1 = st.text_area("IT運用で最も困っていること")
    free2 = st.text_area("一つだけ改善できるなら？")
    free_all = f"[困りごと]\n{free1}\n\n[改善]\n{free2}"

    if st.button("🩺 診断する"):
        log_event("click_start", path="top")

        score = sum(answers_yn)
        type_key = classify_type(score)

        ai_comment = generate_ai_comment(score, type_key, answers_yn, free_all)

        st.success(f"診断完了：{TYPE_INFO[type_key]['label']}")
        st.plotly_chart(radar_chart(answers_yn))
        st.write("### 🩺 主治医コメント")
        st.write(ai_comment)

        pdf = generate_pdf(score, type_key, answers_yn, free_all, ai_comment)
        st.download_button("📄 PDFダウンロード", data=pdf, file_name="it_doctor_report.pdf")


# =====================================================
# 起動
# =====================================================
if __name__ == "__main__":
    main()

