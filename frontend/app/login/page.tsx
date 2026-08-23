"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Compass, LockKeyhole, ShieldCheck } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { User } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api<User>("/api/v1/auth/me")
      .then((user) =>
        router.replace(user.must_change_password ? "/change-password" : "/"),
      )
      .catch(() => undefined);
  }, [router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const user = await api<User>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      router.replace(user.must_change_password ? "/change-password" : "/");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-story">
        <div className="brand-lockup">
          <span className="brand-mark">
            <Compass size={24} />
          </span>
          <span>STEEL—COMPASS</span>
        </div>
        <div className="auth-copy">
          <span className="eyebrow">LANDSCAPE STRUCTURAL WORKSPACE</span>
          <h1>让每一次方案判断，都有清楚的工程依据。</h1>
          <p>
            面向非结构设计人员的景观结构方案筛查工具：用统一项目条件向导完成风雪与地震输入，并保留可追溯的版本报告。
          </p>
        </div>
        <div className="trust-row">
          <span>
            <ShieldCheck size={18} /> 受邀团队
          </span>
          <span>
            <LockKeyhole size={18} /> 服务端权限
          </span>
        </div>
      </section>
      <section className="auth-panel">
        <form className="auth-card" onSubmit={submit}>
          <span className="eyebrow">团队登录</span>
          <h2>欢迎回来</h2>
          <p>使用管理员分配的账号进入工作台。</p>
          <label>
            用户名
            <input
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="your.name"
              required
            />
          </label>
          <label>
            密码
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••••"
              required
            />
          </label>
          {error && <div className="inline-error">{error}</div>}
          <button className="primary-button" disabled={loading}>
            {loading ? "正在验证…" : "进入工作台"}
            <ArrowRight size={18} />
          </button>
          <small>首次登录后必须修改临时密码。</small>
        </form>
      </section>
    </main>
  );
}
