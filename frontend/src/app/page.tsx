type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
  environment: string;
};

type HealthResult =
  | { ok: true; data: HealthResponse }
  | { ok: false; message: string };

export const dynamic = "force-dynamic";

const DEFAULT_BACKEND_API_URL = "http://127.0.0.1:8000";

async function getHealth(): Promise<HealthResult> {
  const baseUrl = process.env.BACKEND_API_URL ?? DEFAULT_BACKEND_API_URL;

  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    });

    if (!response.ok) {
      return {
        ok: false,
        message: `バックエンドがエラーを返しました（HTTP ${response.status}）。`,
      };
    }

    const data: unknown = await response.json();
    if (!isHealthResponse(data)) {
      return { ok: false, message: "バックエンドの応答形式が正しくありません。" };
    }

    return { ok: true, data };
  } catch {
    return {
      ok: false,
      message: "バックエンドへ接続できません。FastAPIが起動しているか確認してください。",
    };
  }
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const health = value as Record<string, unknown>;
  return (
    health.status === "ok" &&
    typeof health.service === "string" &&
    typeof health.version === "string" &&
    typeof health.environment === "string"
  );
}

export default async function Home() {
  const health = await getHealth();

  return (
    <main>
      <h1>AI会議秘書</h1>
      <p>バックエンド接続確認</p>

      {health.ok ? (
        <section className="status success" aria-live="polite">
          <h2>接続成功</h2>
          <dl>
            <div><dt>状態</dt><dd>{health.data.status}</dd></div>
            <div><dt>サービス</dt><dd>{health.data.service}</dd></div>
            <div><dt>バージョン</dt><dd>{health.data.version}</dd></div>
            <div><dt>環境</dt><dd>{health.data.environment}</dd></div>
          </dl>
        </section>
      ) : (
        <section className="status error" role="alert">
          <h2>接続失敗</h2>
          <p>{health.message}</p>
        </section>
      )}
    </main>
  );
}
