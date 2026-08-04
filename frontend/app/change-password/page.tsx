"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Compass, KeyRound } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { User } from "@/lib/types";

export default function ChangePasswordPage() {
  const router = useRouter();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    api<User>("/api/v1/auth/me")
      .then(setUser)
      .catch(() => router.replace("/login"));
  }, [router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (next !== confirm) {
      setError("两次输入的新密码不一致");
      return;
    }
    try {
      await api<void>("/api/v1/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: current,
          new_password: next,
        }),
      });
      router.replace("/login");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <main className="simple-auth">
      <form className="auth-card" onSubmit={submit}>
        <div className="brand-lockup dark">
          <span className="brand-mark">
            <Compass size={22} />
          </span>
          <span>STEEL—COMPASS</span>
        </div>
        <KeyRound className="form-icon" size={30} />
        <span className="eyebrow">首次登录安全设置</span>
        <h2>{user?.display_name ?? "用户"}，请设置新密码</h2>
        <p>修改后当前会话将退出，请使用新密码重新登录。</p>
        <label>
          当前临时密码
          <input
            type="password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            required
          />
        </label>
        <label>
          新密码
          <input
            type="password"
            minLength={10}
            value={next}
            onChange={(event) => setNext(event.target.value)}
            required
          />
        </label>
        <label>
          再次输入新密码
          <input
            type="password"
            minLength={10}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            required
          />
        </label>
        {error && <div className="inline-error">{error}</div>}
        <button className="primary-button">保存并重新登录</button>
      </form>
    </main>
  );
}
