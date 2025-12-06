# -*- coding: utf-8 -*-
"""
3分診断エンジン｜IT主治医診断（製造現場IT版）
- 単独メニュー版 app.py
- 匿名診断：会社名・メール入力なし
- Google Sheets 連携なし（ログ保存なし）
- OpenAI API で主治医コメント生成
- 結果画面にレーダーチャート＋PDF出力ボタン付き
"""

import io
import textwrap
from typing import Dict, List

import streamlit as st
import plotly.graph_objects as go

from openai import OpenAI

# ====== OpenAI 設定 ======
# 環境変数 OPENAI_API_KEY に API キーを設定しておくこと
client = OpenAI()
OPENAI_MODEL = "gpt-4o-mini"  # 必要に応じて変更してください


# ====== 診断ロジック定義 ======

QUESTIONS_YN: Dict[str, str] = {
    "Q1": "現場がシステム操作について、担当者が休んでも「代わりの人がすぐに操作できる」状態ですか？",
    "Q2": "現場での実績入力（進捗・出来高・不良など）は、抜け漏れなく運用できていますか？",
    "Q3": "品番・工程・標準時間などのマスターデータは、継続的に更新されていますか？",
    "Q4": "システムの工程順序やリードタイムは現場実態と一致していますか？",
    "Q5": "現場の社員は「システムを使うと仕事がラクになる」と感じていますか？",
    "Q6": "経営会議では「Excelで加工し直した資料」ではなく、システムデータそのままを使っていますか？",
    "Q7": "現場や管理部門からの改善要求は定期的に吸い上げられ、システム改修につながっていますか？",
    "Q8": "製造・生産管理・品質・営業が“同じデータ”を見て意思疎通できていますか？",
    "Q9": "新人教育・引き継ぎの仕組みは運用されていますか？",
    "Q10": "経営層はシステム運用を“現場改善の中心”として位置づけていますか？",
}

FREETEXT_QUESTIONS: Dict[str, str] = {
    "Q11": "現在、生産管理システムやIT運用で「最も困っていること」は何ですか？",
    "Q12": "もし“魔法のように”一つだけ改善できるとしたら、どこを変えたいですか？",
}

TYPE_INFO: Dict[str, Dict[str, str]] = {
    "A": {
        "label": "🚨 IT機能不全・重篤（ICU行き）",
        "description": "システム運用がほぼ機能しておらず、現場も管理も疲弊している重症レベルです。",
    },
    "B": {
        "label": "⚠️ メタボリック・システム症候群",
        "description": "表面上は動いているものの、ムダな二重入力や属人化が積み重なり、慢性的な負荷が高い状態です。",
    },
    "C": {
        "label": "💊 慢性・属人化疲労",
        "description": "一部ではうまく活用されているものの、人に依存した運用や更新の遅れがボトルネックになっています。",
    },
    "D": {
        "label": "🏃 リハビリ順調・回復期",
        "description": "仕組みづくりは一定進んでおり、あと一歩のテコ入れで“自走モード”に入れる状態です。",
    },
    "E": {
        "label": "💪 健康優良・アスリート企業",
        "description": "現場と経営が同じデータを見て動けている、理想的な運用状態に近い企業です。",
    },
}


def calc_score_and_type(answers_yn: Dict[str, int]):
    score = sum(answers_yn.values())

    if score <= 3:
        t = "A"
    elif score <= 5:
        t = "B"
    elif score <= 7:
        t = "C"
    elif score <= 9:
        t = "D"
    else:
        t = "E"

    return score, t


# ====== OpenAI コメント生成 ======

def build_ai_prompt(score: int, type_key: str,
                    answers_yn: Dict[str, int],
                    free_text: Dict[str, str]) -> str:
    """主治医コメント生成用のプロンプトを組み立てる"""

    type_label = TYPE_INFO[type_key]["label"]
    q_lines = []
    for q_id, text in QUESTIONS_YN.items():
        ans = "Yes" if answers_yn[q_id] == 1 else "No"
        q_lines.append(f"{q_id}: {text} → {ans}")
    q_block = "\n".join(q_lines)

    prompt = f"""
あなたは「製造業のIT主治医」として、現場のシステム運用状態を診断し、
経営者・工場長にも分かりやすく説明する専門家です。

これから、ある工場の「IT主治医診断」の結果をお伝えします。
600〜800字程度の日本語で、以下の構成に沿ってコメントを作成してください。

【診断情報】
- スコア: {score} / 10
- タイプ: {type_label}
- Yes/No 質問の結果:
{q_block}

【自由記述】
- Q11 現在の困りごと: {free_text.get("Q11", "").strip() or "（未記入）"}
- Q12 魔法のように変えたい点: {free_text.get("Q12", "").strip() or "（未記入）"}

【コメントの構成】
1. 診断結果の総評（タイプ名＋どんな状態かのイメージ）
2. 10問から読み取れる具体的な“症状”（特に弱い部分やリスク）
3. 自由記述（Q11・Q12）から読み取れる課題や背景の整理
4. 主治医としての処方箋（今後3〜6ヶ月で取り組むべき改善ステップを3つ程度）

【トーン】
- 専門用語はできるだけ避け、中堅製造業の経営者・工場長が読んで理解できる文章にする
- いたずらに不安をあおらず、「何から取り組めばよいか」が前向きに分かる表現にする
- 箇条書きも適宜使ってよい

では、この条件に沿ってコメントを書いてください。
"""
    return prompt


def generate_ai_comment(score: int, type_key: str,
                        answers_yn: Dict[str, int],
                        free_text: Dict[str, str]) -> str:
    prompt = build_ai_prompt(score, type_key, answers_yn, free_text)

    try:
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "あなたは製造業のIT主治医です。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        # APIエラー時はメッセージを返す
        return f"※AIコメントの生成中にエラーが発生しました。APIキーやネットワーク設定をご確認ください。\n\nエラー内容：{e}"


# ====== レーダーチャート ======

def plot_radar(answers_yn: Dict[str, int]):
    categories = list(QUESTIONS_YN.keys())
    values = [answers_yn[q_id] for q_id in categories]
    # レーダーを閉じるために先頭要素を末尾に追加
    values.append(values[0])
    categories_closed = categories + [categories[0]]

    fig = go.Figure(
        data=[
            go.Scatterpolar(
                r=values,
                theta=categories_closed,
                fill="toself",
                name="Yes=1 / No=0",
            )
        ]
    )

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                tickvals=[0, 1],
                ticktext=["No", "Yes"],
            )
        ),
        showlegend=False,
        margin=dict(l=40, r=40, t=40, b=40),
    )

    st.plotly_chart(fig, use_container_width=True)


# ====== PDF 出力 ======

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4


def _wrap_text(text: str, width: int = 40) -> List[str]:
    # 日本語もざっくり 1文字=1カラムとして扱う簡易折り返し
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(paragraph, width=width, break_long_words=True))
    return lines


def create_pdf_bytes(
    score: int,
    type_key: str,
    answers_yn: Dict[str, int],
    free_text: Dict[str, str],
    ai_comment: str,
) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    x_margin = 40
    y = height - 40

    type_label = TYPE_INFO[type_key]["label"]

    c.setFont("Helvetica-Bold", 16)
    c.drawString(x_margin, y, "IT主治医診断レポート")
    y -= 30

    c.setFont("Helvetica", 11)
    c.drawString(x_margin, y, f"タイプ：{type_label}")
    y -= 16
    c.drawString(x_margin, y, f"スコア：{score} / 10")
    y -= 24

    # Yes/No の概要
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_margin, y, "設問ごとの回答（Yes=1 / No=0）")
    y -= 16
    c.setFont("Helvetica", 10)
    for q_id, text_q in QUESTIONS_YN.items():
        ans = answers_yn[q_id]
        line = f"{q_id}: {ans}  - {text_q}"
        for wrapped in _wrap_text(line, width=60):
            if y < 60:
                c.showPage()
                y = height - 40
                c.setFont("Helvetica", 10)
            c.drawString(x_margin, y, wrapped)
            y -= 14
    y -= 10

    # 自由記述
    for q_id in ["Q11", "Q12"]:
        title = "Q11 現在の困りごと" if q_id == "Q11" else "Q12 改善したい点"
        c.setFont("Helvetica-Bold", 11)
        if y < 70:
            c.showPage()
            y = height - 40
        c.drawString(x_margin, y, title)
        y -= 16

        c.setFont("Helvetica", 10)
        txt = free_text.get(q_id, "").strip() or "（未記入）"
        for wrapped in _wrap_text(txt, width=60):
            if y < 60:
                c.showPage()
                y = height - 40
                c.setFont("Helvetica", 10)
            c.drawString(x_margin, y, wrapped)
            y -= 14
        y -= 8

    # 主治医コメント
    c.setFont("Helvetica-Bold", 11)
    if y < 70:
        c.showPage()
        y = height - 40
    c.drawString(x_margin, y, "IT主治医コメント")
    y -= 18

    c.setFont("Helvetica", 10)
    for wrapped in _wrap_text(ai_comment, width=70):
        if y < 60:
            c.showPage()
            y = height - 40
            c.setFont("Helvetica", 10)
        c.drawString(x_margin, y, wrapped)
        y -= 14

    c.showPage()
    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ====== Streamlit UI ======

def main():
    st.set_page_config(
        page_title="IT主治医診断｜3分セルフチェック",
        page_icon="🩺",
        layout="centered",
    )

    st.title("🩺 製造現場のIT主治医診断（3分セルフチェック）")

    st.markdown(
        """
製造現場に導入した「生産管理システム・IoT・各種IT」が  
**なぜ“うまく使われないまま終わってしまうのか”** を、  
10問のチェックと自由記述から見立てる **IT主治医の簡易診断** です。

- 回答時間の目安：3分
- 匿名診断：会社名・メールアドレスの入力は不要です
- 結果はブラウザ上と PDF で確認できます
        """
    )

    st.markdown("---")

    with st.form("it_doctor_form"):
        st.subheader("1. Yes / No 質問（10問）")

        answers_yn: Dict[str, int] = {}

        for q_id, text_q in QUESTIONS_YN.items():
            col_q = st.columns([1, 9])
            with col_q[1]:
                choice = st.radio(
                    label=f"{q_id}. {text_q}",
                    options=["はい", "いいえ"],
                    key=q_id,
                    horizontal=True,
                )
            answers_yn[q_id] = 1 if choice == "はい" else 0

        st.markdown("---")
        st.subheader("2. 自由記述（任意）")

        free_text: Dict[str, str] = {}
        free_text["Q11"] = st.text_area(
            "Q11. 現在、生産管理システムやIT運用で「最も困っていること」は何ですか？",
            height=80,
        )
        free_text["Q12"] = st.text_area(
            "Q12. もし“魔法のように”一つだけ改善できるとしたら、どこを変えたいですか？",
            height=80,
        )

        submitted = st.form_submit_button("🔍 診断する")

    if not submitted:
        st.info("上の質問に回答し、「🔍 診断する」ボタンを押すと結果が表示されます。")
        return

    # ===== 結果計算 =====
    score, type_key = calc_score_and_type(answers_yn)
    type_label = TYPE_INFO[type_key]["label"]
    type_desc = TYPE_INFO[type_key]["description"]

    st.markdown("---")
    st.header("🩺 IT主治医カルテ（診断結果）")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("タイプ")
        st.markdown(f"**{type_label}**")
        st.write(type_desc)

        st.subheader("スコア")
        st.markdown(f"**{score} / 10**")

    with col2:
        st.subheader("レーダーチャート")
        plot_radar(answers_yn)

    # ===== AI コメント =====
    with st.spinner("IT主治医がカルテを記入しています…（AIコメント生成中）"):
        ai_comment = generate_ai_comment(score, type_key, answers_yn, free_text)

    st.subheader("IT主治医コメント（AIによる所見）")
    st.write(ai_comment)

    # ===== 自由記述まとめ =====
    st.subheader("自由記述のメモ")
    st.markdown("**Q11 現在の困りごと**")
    st.write(free_text.get("Q11", "").strip() or "（未記入）")

    st.markdown("**Q12 改善したい点**")
    st.write(free_text.get("Q12", "").strip() or "（未記入）")

    st.markdown("---")

    # ===== PDF ダウンロード =====
    pdf_bytes = create_pdf_bytes(score, type_key, answers_yn, free_text, ai_comment)

    st.download_button(
        label="📄 診断結果をPDFでダウンロード",
        data=pdf_bytes,
        file_name="it_doctor_diagnosis.pdf",
        mime="application/pdf",
    )

    # ===== 相談ボタン =====
    st.markdown(
        """
### 次の一歩に進みたくなったら…

診断結果を踏まえて「一度相談してみたい」と感じた場合は、  
以下のボタンから IT主治医（勝）宛てにメールをお送りください。

※ 匿名診断のため、必要に応じて会社名やご担当者名をご記入ください。
"""
    )

    mailto_link = (
        "mailto:3mindx@gmail.com"
        "?subject=IT主治医診断の結果について相談したい"
        "&body=※このまま送信していただいても構いません。"
        "%0D%0A%0D%0A---"
        "%0D%0A【ご相談のきっかけ】IT主治医診断を受けた"
        "%0D%0A【会社名／お名前】"
        "%0D%0A【ご相談内容の概要】"
    )

    st.markdown(f"[📧 IT主治医に相談する]({mailto_link})")

    st.markdown(
        '<div style="text-align:center; margin-top:20px;">'
        '<a href="#" onclick="location.reload(); return false;">🔁 もう一度診断する</a>'
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<p style='font-size:11px; color:#6b7280; margin-top:24px;'>"
        "※ この診断は、限られた設問に基づく簡易チェックです。最終的な判断は必ず自社の状況に照らして行ってください。"
        "</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()



















