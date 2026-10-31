"use client";

import { FormEvent, useState } from "react";
import { FolderPlus, X } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { User } from "@/lib/types";

export function InviteDialog({ onClose }: { onClose: () => void }) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      await api<User>("/api/v1/auth/users", {
        method: "POST",
        body: JSON.stringify({
          username,
          display_name: displayName,
          temporary_password: password,
          is_admin: false,
        }),
      });
      setMessage(`已创建 ${displayName}，首次登录必须修改密码。`);
      setUsername("");
      setDisplayName("");
      setPassword("");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <form className="modal-card" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div>
            <span className="eyebrow">INVITED TEAM ONLY</span>
            <h2>邀请团队成员</h2>
          </div>
          <button type="button" className="remove-button" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        <label>
          用户名
          <input
            value={username}
            pattern="[A-Za-z0-9_.-]+"
            minLength={3}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
        </label>
        <label>
          显示名称
          <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
        </label>
        <label>
          临时密码
          <input
            type="password"
            minLength={10}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {error && <div className="inline-error">{error}</div>}
        {message && <div className="inline-success">{message}</div>}
        <button className="primary-button">
          <FolderPlus size={17} /> 创建受邀账号
        </button>
      </form>
    </div>
  );
}
