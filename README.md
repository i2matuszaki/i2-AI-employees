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

利用者・セッションテーブルを含む最新状態まで適用されます。

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
