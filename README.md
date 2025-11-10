# 藥局營業額儀表板（Part 1）

這是以 **Streamlit + Firestore** 製作的 MVP。提供：今日營業額、本月累計、達成率、進度條、達標提示，以及簡易「管理後台」。

## 檔案結構
```
.
├─ app.py
├─ requirements.txt
└─ .streamlit/
   └─ secrets.toml  ← 請自行建立（或用部署平台的 Secrets 介面設定）
```

## 本機啟動
1. 建立 `.streamlit/secrets.toml`：
```toml
ADMIN_PASSWORD = "請自訂"
TIMEZONE = "Asia/Taipei"
GOOGLE_APPLICATION_CREDENTIALS_JSON = """
{ 把 Google Service Account JSON 內容完整貼上 }
"""
```
2. 安裝與執行：
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 部署（Streamlit Community Cloud）
- 將本專案上傳至 GitHub，於 Cloud 的 **Settings → Secrets** 貼上與 `secrets.toml` 相同內容。
- 指定入口檔為 `app.py` 後部署即可。
