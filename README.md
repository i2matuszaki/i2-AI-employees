# アイ・ツー AI社員プロジェクト

## プロジェクト概要。このプロジェクトは、人が仕事を探す会社から、AIが仕事を見つけ、人が判断する会社へを実現するためのAI社員を開発するプロジェクトです。

## 目的、
- AI会議秘書、
- 総務AI、
- 顧客AI、
- メール受付AI、
- 見積AI、
- 保守AI、
- 営業AI、
- 契約AI、
- 経理AI、
- 経営AI
の十人を共通の開発標準に基づいて構築します。

## 開発方針
- ChatGPT、要件定義・設計・レビュー
- Codex、プログラム実装
- GitHub、 設計書・コード管理
- Notion、業務データ管理

## ローカル起動手順

### バックエンド

Python 3.12.1を使用します。

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

起動後、`http://127.0.0.1:8000/health` でヘルスチェックを確認できます。

### データベースマイグレーション

バックエンドの仮想環境を有効にし、`backend` ディレクトリで実行します。
`DATABASE_URL` 未設定時は `sqlite:///./data/meeting_ai.db` を使用します。

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
alembic current
```

利用者・セッションテーブルに加えて、マイグレーション `0003` で `meetings` と
`meeting_participants`、`0004` で `transcript_runs` と `transcript_segments` が追加されます。
`alembic upgrade head` で最新状態まで適用されます。

マイグレーションをすべて取り消す場合は、次を実行します。

```bash
alembic downgrade base
```

### デモ利用者の作成

リポジトリ直下の `.env.example` を参考に、次の環境変数を実行環境へ設定します。
値はソースコードやGitへ保存しないでください。各パスワードは8文字以上128文字以下です。

```text
DEMO_USER_PASSWORD=
DEMO_APPROVER_PASSWORD=
DEMO_ADMIN_PASSWORD=
```

マイグレーション適用後、バックエンドの仮想環境を有効にして実行します。

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
python -m app.scripts.create_demo_users
```

同じメールアドレスの利用者が存在する場合はスキップし、既存の値を変更しません。

### セッション認証設定

セッションの有効期間とCookieのSecure属性は環境変数で設定します。

```text
SESSION_LIFETIME_HOURS=
SESSION_COOKIE_SECURE=
```

`SESSION_LIFETIME_HOURS`の未設定時は8時間です。1以上168以下の整数を指定できます。
`SESSION_COOKIE_SECURE`は`true`または`false`だけを指定でき、ローカル環境で未設定の場合は
`false`です。`APP_ENV=production`では必ず`true`を指定してください。

### ログインAPIの確認

デモ利用者を作成した後、認証情報をシェル環境変数へ設定します。実際のパスワードや
Cookie値をREADMEやシェル履歴へ固定値として保存しないでください。

```bash
export DEMO_LOGIN_EMAIL=user@demo.local
read -r -s -p "Demo password: " DEMO_LOGIN_PASSWORD
export DEMO_LOGIN_PASSWORD
export COOKIE_JAR_PATH=/tmp/meeting-ai-cookies.txt

curl --fail-with-body \
  --cookie-jar "$COOKIE_JAR_PATH" \
  --header 'Content-Type: application/json' \
  --data "{\"email\":\"${DEMO_LOGIN_EMAIL}\",\"password\":\"${DEMO_LOGIN_PASSWORD}\"}" \
  http://127.0.0.1:8000/api/auth/login
```

ログイン後のCookieを使用して現在の利用者を確認できます。

```bash
curl --fail-with-body \
  --cookie "$COOKIE_JAR_PATH" \
  http://127.0.0.1:8000/api/auth/me
```

ログアウトでは、Cookie jarに保存されたCSRF Cookieと同じ値を`X-CSRF-Token`へ指定します。

```bash
export CSRF_TOKEN="$(awk '$6 == "meeting_ai_csrf" {print $7}' "$COOKIE_JAR_PATH")"

curl --fail-with-body \
  --request POST \
  --cookie "$COOKIE_JAR_PATH" \
  --cookie-jar "$COOKIE_JAR_PATH" \
  --header "X-CSRF-Token: ${CSRF_TOKEN}" \
  http://127.0.0.1:8000/api/auth/logout

unset DEMO_LOGIN_PASSWORD CSRF_TOKEN
```

### 会議CRUD API

会議本体と参加者情報を、次のAPIで操作できます。すべてセッション認証が必要です。
`POST`、`PATCH`、`DELETE`では、CSRF Cookieと同じ値を`X-CSRF-Token`ヘッダーへ指定します。

- `POST /api/meetings`: 会議作成
- `GET /api/meetings`: 会議一覧取得
- `GET /api/meetings/{meeting_id}`: 会議詳細取得
- `PATCH /api/meetings/{meeting_id}`: 会議更新
- `DELETE /api/meetings/{meeting_id}`: 会議削除

一覧では`status`、`organizer_user_id`、`created_by_user_id`、`scheduled_from`、
`scheduled_to`、`limit`、`offset`をクエリパラメータとして指定できます。

PATCHで`participants`を省略した場合は既存参加者を維持します。指定した場合は参加者全体を
置き換え、空配列を指定すると全参加者を削除します。参加者単独の部分更新APIはありません。

### 文字起こしデータの保存

`transcript_runs` は文字起こし処理の実行履歴、`transcript_segments` は発言単位の
文字起こしデータを保存します。これらはマイグレーション `0004` で追加され、
`alembic upgrade head` で適用されます。

`raw_response` は監査・再処理のために外部サービスの原文を保持する領域です。
秘密情報や認証情報を保存せず、全文をログへ出力しないでください。

現時点では、文字起こしAPI、外部AI連携、音声アップロード、要約・議事録生成、承認、
Notion連携は提供していません。

### フロントエンド

別のターミナルで、Node.js 24.14.0とnpm 11.9.0を使用して起動します。

```bash
cd frontend
npm install
npm run dev
```

起動後、`http://localhost:3000` へアクセスします。Next.jsサーバーがFastAPIの
`/health` を呼び出し、接続結果を表示します。

接続先を変更する場合は、リポジトリ直下の `.env.example` を参考に
`frontend/.env.local` へ次の環境変数を設定してください。

```text
BACKEND_API_URL=http://127.0.0.1:8000
```

未設定時も `http://127.0.0.1:8000` を使用します。この値はブラウザーへ公開されません。

### 品質確認

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
```

```bash
cd backend
source .venv/bin/activate
ruff check .
pytest
```
