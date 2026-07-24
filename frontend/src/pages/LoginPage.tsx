import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function LoginPage() {
  const navigate = useNavigate();
  const [login, setLogin] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api.post("/auth/login", { login, password });
      navigate("/");
    } catch {
      setError("Неверный логин или пароль");
    }
  };

  return (
    <div className="login-page">
      <div className="card login-card">
        <p className="login-brand">CCSA Analytics</p>
        <h1 className="page-title">Вход</h1>
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Логин</label>
            <input value={login} onChange={(e) => setLogin(e.target.value)} required autoComplete="username" />
          </div>
          <div className="form-group">
            <label>Пароль</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>
          {error && <p className="text-error mb-4">{error}</p>}
          <button type="submit" className="btn btn-primary btn-block">
            Войти
          </button>
        </form>
      </div>
    </div>
  );
}
