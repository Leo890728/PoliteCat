# PoliteCat

PoliteCat 是一個基於 Pycord 的多功能 Discord 機器人，整合了 AI 聊天、音樂播放、實用工具等豐富功能。

> 本專案基於 [Discord Pycord Template](https://github.com/a3510377/discord-py-cord-template) 基礎框架進行開發，感謝原作者 [a3510377](https://github.com/a3510377) 提供優秀的模板。

## 特色功能

- **AI 個性對話**: 
  - **個性化設定**: 支援自訂「人物角色」與「語氣風格」，可透過儀表板隨時切換。
  - **多媒體辨識**: 支援網頁連結預覽、圖片與貼圖內容辨識。
  **自訂互動反應**: 支援自訂互動反應，可針對文字、貼圖進行語音或文字反應。
- **音樂與電台**: 提供音樂播放與電台收聽功能 (Player/Radio)。
- **實用工具**: 
  - 天氣查詢 (Weather)
  - 抽籤功能 (Drawing)
  - 互動指令 (React, Toys)
- **專業架構**:
  - 採用 Cog 模組化設計，易於維護與擴充。
  - 內建 I18n 多語言支援。
  - 完善的日誌 (Logging) 系統與資料庫整合。

---

## 起步指南

### 環境要求

- [Python](https://www.python.org/) 版本 `>= 3.10`
- Discord Bot Token
- OpenAI API Key (用於 AI 對話功能)

### 安裝步驟

1. **複製專案**

   ```sh
   git clone https://github.com/Leo890728/PoliteCat.git
   cd PoliteCat
   ```

2. **建立虛擬環境 (建議)**

   ```sh
   python -m venv env
   # Windows
   .\env\Scripts\activate
   # Linux/Mac
   source env/bin/activate
   ```

3. **安裝相依套件**

   ```sh
   # 生產環境
   pip install -r requirements/prod.txt
   
   # 開發環境 (若需進行開發測試)
   pip install -r requirements/dev.txt
   pip install -r tool/requirements.txt
   ```

4. **設定環境變數**

將 `.env.example` 複製並重新命名為 `.env`，填入您的設定資料：
   
   ```ini
   DISCORD_TOKEN=your_discord_bot_token
   
   # AI 功能 (OpenAI)
   OPENAI_API_KEY=sk-proj-...
   
   # 音樂、收音機功能 (Lavalink)
   LAVA_LINK_URI=http://localhost:2333
   LAVA_LINK_PASSWORD=youshallnotpass
   
   # 天氣功能 (CWA 氣象局 API)
   CWA_AUTHORIZATION=your_cwa_auth_key
   
   # 其他設定 (可選)
   OWNER_IDS=123456789,987654321
   BASE_LANG=zh-TW
   PEM_CERT_PATH=/path/to/cert.pem
   BOT_SHARD=0
   ```

### 執行機器人

```sh
python start.py
```
或是使用模組方式執行：
```sh
python -m bot
```

---

## 資料夾結構

```yml
/                     # 根目錄
├ bot                   # 機器人核心代碼
│ ├ cogs                  # 功能模組
│ │ ├ admin                 # 管理類 (清除訊息等)
│ │ └ util                  # 實用應用類
│ │   ├ ai_chat.py               # AI 對話系統
│ │   ├ player.py                # 音樂播放器
│ │   ├ weather.py               # 天氣功能
│ │   └ ...
│ ├ core                  # 核心系統 (Bot, Events, DB)
│ ├ models                 # 資料庫模型
│ └ utils                  # 通用工具函式
├ logs                  # 運行紀錄
├ requirements          # 依賴套件清單
└ start.py                # 啟動腳本
```

---

## 貢獻者與致謝

### 核心貢獻者
<a href="https://github.com/Leo890728/PoliteCat/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Leo890728/PoliteCat" />
</a>

### 特別致謝
本專案的基礎架構來自 **[Discord Pycord Template](https://github.com/a3510377/discord-py-cord-template)**。  
特別感謝作者 **[a3510377](https://github.com/a3510377)** 提供了這個結構清晰且功能強大的開發模板，大幅降低了開發門檻。

## License

[MIT](LICENSE)
