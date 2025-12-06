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

def _sanitize_for_pdf(text: str) -> str:
    """FPDFが苦手な絵文字などを除去（BMP外の文字を削る）"""
    if not isinstance(text, str):
        text = str(text)
    # ord(c) <= 0xFFFF の文字だけ残す（多くの日本語はこの範囲）
    return "".join(ch for ch in text if ord(ch) <= 0xFFFF)

def generate_pdf(score, type_key, answers, free_text, ai_comment):
    """1ページ版の簡易レポートPDFを生成"""

    # PDFで使う文字列だけサニタイズ（絵文字など除去）
    type_label = _sanitize_for_pdf(TYPE_INFO[type_key]["label"])
    ai_comment_pdf = _sanitize_for_pdf(ai_comment)

    pdf = FPDF()
    pdf.add_page()
    # 自動改ページは切って「1枚だけ」にする
    pdf.set_auto_page_break(auto=False, margin=0)

    pdf.add_font("Noto", "", "NotoSansJP-Regular.ttf", uni=True)
    pdf.set_font("Noto", size=16)

    # タイトル
    pdf.cell(0, 10, "IT主治医診断レポート", ln=True)

    pdf.ln(6)
    pdf.set_font("Noto", size=12)
    pdf.multi_cell(0, 8, f"【タイプ】{type_label}")

    pdf.ln(4)
    pdf.set_font("Noto", size=11)
    pdf.cell(0, 8, "【IT主治医コメント】", ln=True)

    pdf.ln(2)
    pdf.set_font("Noto", size=10)
    # コメント本体（長くても2ページ目は作らず、1枚に収まるところまで）
    pdf.multi_cell(0, 6, ai_comment_pdf)

    buffer = BytesIO()
    buffer.write(pdf.output(dest="S").encode("latin1"))
    buffer.seek(0)
    return buffer





# =========================
# AI コメント生成
# =========================
def generate_ai_comment(score, type_key, answers, free_text):
    """IT主治医コメントを生成（製造現場のITに限定）"""
    type_label = TYPE_INFO[type_key]["label"]

    prompt = f"""
    あなたは製造業の生産管理・IT活用に詳しい「IT主治医コンサルタント」です。
    これから、中小製造業の「ITがうまく使われていない理由」を診断コメントとして日本語で作成してください。
    
    【前提】
    - 対象は工場や製造部門の「システム運用」「データ活用」「現場への定着状況」です。
    - 医療メタファー（ICU・メタボ・リハビリ等）は、
      あくまで ITシステムや業務プロセスの状態を表す比喩としてだけ使ってください。
    - 人間の健康状態や肥満・運動不足・食生活・生活習慣病など、
      医学的な健康診断の話題は一切書かないでください。
    - 会社の規模は中小企業を想定してください。
    
    【診断タイプ】
    {type_label}
    
    【スコア】
    {score} / 10
    
    【Yes/No回答の概要】
    {answers}
    
    【自由記述】
    {free_text}
    
    コメント構成（600〜800字程度）で、以下の流れで書いてください。
    
    1. 診断タイプにもとづき、現在の IT・システム運用の状態像を一言でまとめる。
       （例：データはあるが活かしきれていない、現場には負担感だけが残っている 等）
    2. 10問から読み取れる具体的な「症状」を2〜3点挙げる。
       例：属人化（特定担当者に依存）、マスタ未整備、多重管理（Excelと二重入力）、
           現場の入力負担が大きい、経営会議でシステムが使われていない 等。
    3. 自由記述から読み取れる現場の本音や背景を整理する。
       例：過去のシステム導入失敗経験、人員・時間の不足、経営層と現場の温度差、
           「システムのための仕事」が増えてしまっている など。
    4. 「IT主治医」として、今後3〜6か月で取り組むべき改善ステップを3つに分けて提案する。
       「STEP1：〜」「STEP2：〜」「STEP3：〜」という形式で、
       できるだけ具体的なアクション（例：入力画面の簡略化、マスタ整備プロジェクト、
       経営会議でのダッシュボード活用トライアル 等）を書く。
    
    注意事項：
    - 人間の体調や肥満・食事・運動など、健康や生活習慣の話題は絶対に書かない。
    - コメント全体を通じて、工場・製造現場のIT活用と業務プロセス改善の話題に限定する。
    - 読み手は製造現場や生産管理に責任を持つ管理職クラスを想定し、
      専門用語はかみ砕いて分かりやすく説明する。
    """

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        temperature=0.7,
    )
    return res.choices[0].message.content.strip()



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

    # =========================
    # ドクターイエロー配色（薄黄色テーマ）
    # =========================
    st.markdown("""
    <style>
        /* 背景色（全体） */
        .stApp {
            background-color: #FFFDE7;
        }

        /* サイドバー */
        section[data-testid="stSidebar"] {
            background-color: #FFF9C4;
        }

        /* ボタン */
        .stButton>button {
            background-color: #FDD835;
            color: black;
            border-radius: 8px;
            font-weight: bold;
            border: none;
        }
        .stButton>button:hover {
            background-color: #FBC02D;
            color: black;
        }

        /* タイトル系 */
        h1, h2, h3 {
            color: #F57F17;
        }

        /* 質問テキスト */
        label {
            color: #6D4C41;
            font-weight: 600;
        }

        /* ラジオボタン（Yes / No） */
        div[role="radiogroup"] > label {
            display: inline-flex;
            align-items: center;
            padding: 4px 12px;
            margin-right: 8px;
            margin-bottom: 4px;
            border-radius: 999px;
            background-color: #FFF9C4;
            border: 1px solid #FBC02D;
        }

        /* ホバー時 */
        div[role="radiogroup"] > label:hover {
            background-color: #FFE082;
        }

        /* 選択されている方を濃い黄色＋太字に */
        div[role="radiogroup"] input:checked + div {
            background-color: #FDD835 !important;
            color: #000000 !important;
            font-weight: 700;
        }
    </style>
""", unsafe_allow_html=True)


    st.title("🩺 IT主治医診断（3分）")
    st.write("製造現場に導入したITが『なぜ使われないのか』を3分で可視化する診断です。")

    st.subheader("■ 質問（10問）")

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

    st.subheader("■ 自由記述（任意）")
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
