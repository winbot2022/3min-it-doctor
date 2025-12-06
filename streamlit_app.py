# -*- coding: utf-8 -*-
import streamlit as st
import plotly.graph_objects as go
from fpdf import FPDF
from io import BytesIO
from openai import OpenAI
import os

# =========================
#  OpenAI クライアント
# =========================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
#  タイプ分類
# =========================
TYPE_INFO = {
    "A": {"label": "🚨 IT機能不全・重篤（ICU行き）"},
    "B": {"label": "⚠️ メタボリック・システム症候群"},
    "C": {"label": "💊 慢性・属人化疲労"},
    "D": {"label": "🏃 リハビリ順調・回復期"},
    "E": {"label": "💪 健康優良・アスリート企業"},
}

# =========================
# PDF生成（FPDF + 日本語フォント）
# =========================
def generate_pdf(score, type_key, answers, free_text, ai_comment):

    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("Noto", "", "NotoSansJP-Regular.ttf", uni=True)
    pdf.set_font("Noto", size=12)

    pdf.cell(0, 10, "IT主治医診断（結果レポート）", ln=True)

    pdf.ln(5)
    pdf.cell(0, 10, f"■ スコア：{score} / 10", ln=True)
    pdf.cell(0, 10, f"■ タイプ：{TYPE_INFO[type_key]['label']}", ln=True)

    pdf.ln(5)
    pdf.multi_cell(0, 8, f"■ 回答結果：{answers}")

    pdf.ln(5)
    pdf.multi_cell(0, 8, f"■ 自由記述：\n{free_text}")

    pdf.ln(5)
    pdf.multi_cell(0, 8, "■ 主治医コメント（AI生成）\n" + ai_comment)

    buffer = BytesIO()
    buffer.write(pdf.output(dest="S").encode("latin1"))
    buffer.seek(0)
    return buffer


# =========================
# AI コメント生成
# =========================
def generate_ai_comment(score, type_key, answers, free_text):
    prompt = f"""
あなたは製造業の「IT主治医」です。
以下の情報から 600〜800字で診断コメントを作成してください。

【タイプ】{TYPE_INFO[type_key]['label']}
【スコア】{score} / 10
【回答状況】{answers}
【自由記述】{free_text}

コメント構成：
1. まずタイプの状態像を端的に説明
2. 回答10問から推測できる「症状」を具体的に描写
3. 自由記述から読み取れる“背景”“本音”を言語化
4. 主治医として「3〜6ヶ月で改善できる3ステップ処方箋」を提示
"""
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800
    )
    return res.choices[0].message.content


# =========================
# レーダーチャート
# =========================
def radar_chart(answers):
    categories = [f"Q{i}" for i in range(1, 11)]
    values = answers + [answers[0]]  # クローズ

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories + [categories[0]],
        fill="toself",
        name="Score",
        line=dict(color="royalblue")
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1])
        ),
        showlegend=False
    )
    return fig


# =========================
# スコア → タイプ分類
# =========================
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


# =========================
# UI：main()
# =========================
def main():

    st.title("🩺 IT主治医診断（3分）")
    st.write("製造現場に導入したITが『なぜ使われないのか』を3分で可視化する診断です。")

    st.subheader("■ 質問（10問：Yes=1 / No=0）")

    questions = [
        "Q1. 現場がシステム操作を“誰でも代替できる”状態になっていますか？",
        "Q2. 実績入力（進捗・出来高・不良）が漏れなく運用されていますか？",
        "Q3. マスターデータ（品番・工程・標準時間）は更新されていますか？",
        "Q4. システムの工程順序・リードタイムは現場実態と一致していますか？",
        "Q5. 現場は『システムを使うとラクになる』と感じていますか？",
        "Q6. 経営会議では“Excel加工なし”でシステムデータを使っていますか？",
        "Q7. 現場からの改善要求は定期的に吸い上げられていますか？",
        "Q8. 部門間で“同じデータ”を見て意思疎通できていますか？",
        "Q9. 新人教育・引き継ぎの仕組みは運用されていますか？",
        "Q10. 経営層はシステム運用を“現場改善の中心”と位置づけていますか？"
    ]

    answers_yn = []
    for q in questions:
        val = st.radio(q, ["No", "Yes"], horizontal=True)
        answers_yn.append(1 if val == "Yes" else 0)

    st.subheader("■ 自由記述")
    free1 = st.text_area("Q11. IT運用で“最も困っていること”は何ですか？")
    free2 = st.text_area("Q12. 魔法のように一つ改善できるなら、どこを変えたいですか？")
    free_all = f"[困りごと]\n{free1}\n\n[改善したいこと]\n{free2}"

    if st.button("🩺 診断する"):
        score = sum(answers_yn)
        type_key = classify_type(score)

        st.success(f"診断が完了しました。タイプ：{TYPE_INFO[type_key]['label']}")

        # AI コメント生成
        ai_comment = generate_ai_comment(score, type_key, answers_yn, free_all)

        st.subheader("■ 診断結果")
        st.write(f"### {TYPE_INFO[type_key]['label']}")
        st.write(f"**スコア：{score} / 10**")

        st.plotly_chart(radar_chart(answers_yn))

        st.write("### 🩺 主治医コメント")
        st.write(ai_comment)

        # PDF 生成
        pdf = generate_pdf(score, type_key, answers_yn, free_all, ai_comment)
        st.download_button("📄 PDFダウンロード", data=pdf, file_name="it_doctor_report.pdf")


# =========================
# 起動（必ず最後に！）
# =========================
if __name__ == "__main__":
    main()
