import os
import json
import pytz
import pandas as pd
import calendar
from datetime import datetime, date

import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore
import altair as alt

# ---------- Page & TZ ----------
st.set_page_config(page_title="藥局營業額儀表板", page_icon="💊", layout="wide")
TZ_NAME = st.secrets.get("TIMEZONE", "Asia/Taipei")
TZ = pytz.timezone(TZ_NAME)

# ---------- Firestore ----------
@st.cache_resource(show_spinner=False)
def get_db():
    sa_json_str = st.secrets.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not sa_json_str:
        st.error("尚未設定 GOOGLE_APPLICATION_CREDENTIALS_JSON（請到 Secrets 設定）")
        st.stop()
    sa_info = json.loads(sa_json_str)
    creds = service_account.Credentials.from_service_account_info(sa_info)
    return firestore.Client(project=sa_info.get("project_id"), credentials=creds)

db = get_db()

SALES_COL = "sales"           # docId: YYYY-MM-DD
SETTINGS_DOC = ("settings", "global")

def taipei_today():
    return datetime.now(TZ).date()

@st.cache_data(ttl=60)
def load_settings():
    doc_ref = db.collection(SETTINGS_DOC[0]).document(SETTINGS_DOC[1])
    snap = doc_ref.get()
    if snap.exists:
        data = snap.to_dict()
    else:
        data = {"target_monthly": 600000, "bonus_amount": 6000, "bonus_title": "團體獎金"}
        doc_ref.set(data)
    return data

@st.cache_data(ttl=60)
def load_month_sales(year: int, month: int) -> pd.DataFrame:
    docs = db.collection(SALES_COL).stream()
    rows = []
    for d in docs:
        doc_id = d.id  # YYYY-MM-DD
        try:
            dt = datetime.strptime(doc_id, "%Y-%m-%d").date()
        except:
            continue
        if dt.year == year and dt.month == month:
            rec = d.to_dict() or {}
            rows.append({"date": dt, "amount": float(rec.get("amount", 0))})
    if not rows:
        return pd.DataFrame(columns=["date", "amount"]).astype({"amount": "float"})
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    return df

@st.cache_data(ttl=0, show_spinner=False)
def upsert_sale(d: date, amount: float):
    doc_id = d.strftime("%Y-%m-%d")
    db.collection(SALES_COL).document(doc_id).set(
        {"amount": float(amount), "updated_at": datetime.now(TZ)}, merge=True
    )
    load_month_sales.clear()

@st.cache_data(ttl=0, show_spinner=False)
def save_settings(target_monthly: int, bonus_amount: int, bonus_title: str):
    db.collection(SETTINGS_DOC[0]).document(SETTINGS_DOC[1]).set(
        {
            "target_monthly": int(target_monthly),
            "bonus_amount": int(bonus_amount),
            "bonus_title": str(bonus_title or "團體獎金"),
        },
        merge=True,
    )
    load_settings.clear()

def kpi_card(label: str, value: str, help_text: str = ""):
    st.metric(label, value, help=help_text)

st.title("💊 藥局營業額儀表板｜當日＆當月累計")

tab_dashboard, tab_admin = st.tabs(["📈 儀表板", "🛠️ 管理後台"])

# ========================
# 📈 儀表板
# ========================
with tab_dashboard:
    settings = load_settings()
    today = taipei_today()
    year, month = today.year, today.month
    month_label = f"{year}-{month:02d}"

    df = load_month_sales(year, month)
    today_row = df[df["date"] == today]
    today_amount = float(today_row["amount"].iloc[0]) if not today_row.empty else 0.0
    mtd = float(df["amount"].sum()) if not df.empty else 0.0

    target = float(settings.get("target_monthly", 600000))
    bonus_amt = float(settings.get("bonus_amount", 6000))
    bonus_title = settings.get("bonus_title", "團體獎金")

    progress = 0.0 if target <= 0 else min(mtd / target, 1.0)
    remain = max(target - mtd, 0.0)

    # --- 第一排 KPI ---
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("今日營業額", f"${today_amount:,.0f}")
    with c2:
        kpi_card("本月累計", f"${mtd:,.0f}")
    with c3:
        kpi_card("本月目標", f"${target:,.0f}")
    with c4:
        rate = mtd / target * 100 if target > 0 else 0
        kpi_card("達成率", f"{rate:.1f}%")

    st.progress(progress, text=f"{month_label} 目標達成進度：{progress*100:.1f}%")

    # --- 達標 / 未達提示 ---
    if mtd >= target:
        st.success(f"🎉 已達成 {month_label} 目標！{bonus_title} 已解鎖：${bonus_amt:,.0f}")
    else:
        st.info(f"距離 {bonus_title} 還差：${remain:,.0f}")

    # --- 若有資料，再顯示預估與圖表 ---
    if df.empty:
        st.warning("本月尚無資料。請至後台新增每日營業額。")
    else:
        # 準備基礎資料
        df = df.sort_values("date")
        chart_df = df.copy()
        chart_df["date"] = pd.to_datetime(chart_df["date"])

        # ---------- 第二排 KPI：預估與成長 ----------
        days_in_month = calendar.monthrange(year, month)[1]
        day_today = today.day
        daily_avg = mtd / day_today if day_today > 0 else 0
        projected_month = daily_avg * days_in_month if day_today > 0 else 0

        # 近 7 日與前一個 7 日
        df_sorted = df.sort_values("date")
        last_7 = df_sorted.tail(7)["amount"].sum()
        prev_7 = None
        if len(df_sorted) >= 14:
            prev_7 = df_sorted.tail(14).head(7)["amount"].sum()

        c5, c6, c7, c8 = st.columns(4)
        with c5:
            kpi_card("本月日均營業額", f"${daily_avg:,.0f}" if day_today > 0 else "-", "")
        with c6:
            kpi_card("預估月底營業額", f"${projected_month:,.0f}" if day_today > 0 else "-", "")
        with c7:
            if day_today > 0 and target > 0:
                # 用「目標 - 預估」來看還差多少
                gap = target - projected_month

                if gap > 0:
                    # 只有「預估沒達標」時才提醒
                    v = f"-${gap:,.0f}"
                    h = "照目前速度推估，月底可能仍未達目標，需再加把勁 💪"
                    kpi_card("預估未達目標金額", v, h)
                else:
                    # 已可達標或超標時，不特別提醒，只給個安心訊息
                    kpi_card("預估未達目標金額", "0", "以目前速度推估可達成目標")
            else:
                kpi_card("預估未達目標金額", "-", "資料不足")
        with c8:
            if prev_7 is not None and prev_7 > 0:
                growth_pct = (last_7 / prev_7 - 1) * 100
                help_txt = f"相較前一個 7 日：{growth_pct:+.1f}%"
            else:
                help_txt = "資料不足以計算成長率"
            kpi_card("近 7 日營業額", f"${last_7:,.0f}", help_txt)

        st.divider()

        # ---------- 圖 1：每日營業額 ----------
        st.subheader("📊 每日營業額")
        st.line_chart(chart_df, x="date", y="amount", height=280)

        # ---------- 圖 2：本月累積營業額 + 目標水平線 ----------
        st.subheader("📈 本月累積營業額")

        cum_df = chart_df.copy()
        cum_df["cumulative_amount"] = cum_df["amount"].cumsum()
        cum_df["target"] = target  # 每一點都帶同一個目標值，用來畫水平線

        base = alt.Chart(cum_df).encode(
            x=alt.X("date:T", title="日期"),
        )

        line_cum = base.mark_line().encode(
            y=alt.Y("cumulative_amount:Q", title="累積營業額")
        )

        line_target = base.mark_rule(color="red", strokeDash=[4, 4]).encode(
            y="target:Q"
        )

        chart = (line_cum + line_target).properties(height=320)
        st.altair_chart(chart, use_container_width=True)

# ========================
# 🛠️ 管理後台
# ========================
with tab_admin:
    st.subheader("管理後台（僅管理者）")
    pw = st.text_input("後台密碼", type="password")
    if pw != st.secrets.get("ADMIN_PASSWORD", ""):
        st.stop()

    st.markdown("### 目標與獎金設定")
    s = load_settings()
    col1, col2, col3 = st.columns(3)
    with col1:
        target_in = st.number_input(
            "當月目標金額（元）",
            min_value=0,
            step=10000,
            value=int(s.get("target_monthly", 600000)),
        )
    with col2:
        bonus_in = st.number_input(
            "團體獎金（元）",
            min_value=0,
            step=1000,
            value=int(s.get("bonus_amount", 6000)),
        )
    with col3:
        title_in = st.text_input("獎金名稱", value=s.get("bonus_title", "團體獎金"))

    if st.button("💾 儲存設定", type="primary"):
        save_settings(target_in, bonus_in, title_in)
        st.success("已更新設定！")

    st.divider()

    st.markdown("### 新增/覆蓋單日營業額")
    d_in = st.date_input("日期", value=taipei_today())
    amt_in = st.number_input("營業額（元）", min_value=0, step=100, value=0)
    if st.button("📌 儲存當日營業額"):
        upsert_sale(d_in, amt_in)
        st.success(f"已更新 {d_in}：${amt_in:,.0f}")

    st.divider()

    st.markdown("### 批次上傳（CSV）")
    st.caption("欄位需包含：date,amount；範例：2025-11-01, 12345")
    file = st.file_uploader("選擇 CSV 檔", type=["csv"])
    if file is not None:
        try:
            df_up = pd.read_csv(file)
            df_up.columns = [c.strip().lower() for c in df_up.columns]
            if not {"date", "amount"}.issubset(set(df_up.columns)):
                st.error("CSV 需包含欄位：date, amount")
            else:
                cnt = 0
                for _, row in df_up.iterrows():
                    try:
                        d0 = pd.to_datetime(str(row["date"]).strip()).date()
                        a0 = float(row["amount"]) if pd.notnull(row["amount"]) else 0.0
                    except Exception:
                        continue
                    upsert_sale(d0, a0)
                    cnt += 1
                st.success(f"批次處理完成，共 {cnt} 筆。")
        except Exception as e:
            st.error(f"讀取 CSV 失敗：{e}")
